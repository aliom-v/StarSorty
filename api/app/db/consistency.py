import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from ..db.schema import is_fts_enabled
from ..taxonomy import load_taxonomy
from ..taxonomy_schema import normalize_tag_ids
from .pool import get_connection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json_list(value: Any) -> Tuple[List[str], bool]:
    if value is None or value == "":
        return [], False
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()], False
    try:
        loaded = json.loads(value)
    except Exception:
        return [], True
    if not isinstance(loaded, list):
        return [], True
    return [str(item).strip() for item in loaded if str(item).strip()], False


def _push_issue(
    issues: List[Dict[str, Any]],
    *,
    code: str,
    detail: str,
    count: int,
    samples: List[str],
    level: str = "warning",
) -> None:
    if count <= 0:
        return
    issues.append(
        {
            "code": code,
            "level": level,
            "count": count,
            "detail": detail,
            "sample_full_names": sorted(samples)[:5],
        }
    )


def _build_fts_probe_query(*values: Any) -> str | None:
    tokens: List[str] = []
    for value in values:
        for token in re.split(r"[^0-9A-Za-z_]+", str(value or "")):
            normalized = token.strip().lower()
            if normalized:
                tokens.append(normalized)
    if not tokens:
        return None
    deduped: List[str] = []
    for token in tokens:
        if token not in deduped:
            deduped.append(token)
    return " AND ".join(f'"{token}"' for token in deduped)


async def _has_fts_entry(conn, row_id: int, full_name: str, name: str) -> bool:
    probe = _build_fts_probe_query(full_name, name)
    if not probe:
        return True
    row = await (
        await conn.execute(
            "SELECT 1 FROM repos_fts WHERE rowid = ? AND repos_fts MATCH ? LIMIT 1",
            (row_id, probe),
        )
    ).fetchone()
    return row is not None


async def get_repo_consistency_report(taxonomy_path: str) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    taxonomy_error: str | None = None
    taxonomy: Dict[str, Any] | None = None
    try:
        taxonomy = load_taxonomy(taxonomy_path)
    except Exception as exc:
        taxonomy_error = str(exc)

    async with get_connection() as conn:
        repos_total = int(
            (
                await (
                    await conn.execute("SELECT COUNT(*) FROM repos")
                ).fetchone()
            )[0]
            or 0
        )
        fts_enabled = bool(is_fts_enabled())
        fts_total = 0

        rows = await (
            await conn.execute(
                """
                SELECT
                    id,
                    full_name,
                    name,
                    category,
                    subcategory,
                    override_category,
                    override_subcategory,
                    ai_tags,
                    ai_tag_ids,
                    override_tags,
                    override_tag_ids
                FROM repos
                ORDER BY full_name ASC
                """
            )
        ).fetchall()

        if fts_enabled:
            indexed_total = 0
            for row in rows:
                if await _has_fts_entry(
                    conn,
                    int(row["id"] or 0),
                    str(row["full_name"] or ""),
                    str(row["name"] or ""),
                ):
                    indexed_total += 1
            fts_total = indexed_total

    counters: Dict[str, int] = {
        "blank_category": 0,
        "blank_subcategory": 0,
        "invalid_category": 0,
        "invalid_subcategory": 0,
        "orphan_subcategory": 0,
        "ai_tags_malformed": 0,
        "ai_tag_ids_malformed": 0,
        "override_tags_malformed": 0,
        "override_tag_ids_malformed": 0,
        "ai_tags_not_normalized": 0,
        "override_tags_not_normalized": 0,
    }
    samples: Dict[str, List[str]] = {key: [] for key in counters}

    valid_categories = set((taxonomy or {}).get("category_map", {}).keys())

    for row in rows:
        full_name = str(row["full_name"])

        for category_field, subcategory_field in (
            ("category", "subcategory"),
            ("override_category", "override_subcategory"),
        ):
            raw_category = row[category_field]
            raw_subcategory = row[subcategory_field]
            category = str(raw_category or "").strip()
            subcategory = str(raw_subcategory or "").strip()

            if raw_category == "":
                counters["blank_category"] += 1
                samples["blank_category"].append(full_name)
            if raw_subcategory == "":
                counters["blank_subcategory"] += 1
                samples["blank_subcategory"].append(full_name)

            if category:
                if valid_categories and category not in valid_categories:
                    counters["invalid_category"] += 1
                    samples["invalid_category"].append(full_name)
                else:
                    allowed_subcategories = set((taxonomy or {}).get("category_map", {}).get(category, []))
                    if subcategory and allowed_subcategories and subcategory not in allowed_subcategories:
                        counters["invalid_subcategory"] += 1
                        samples["invalid_subcategory"].append(full_name)
            elif subcategory:
                counters["orphan_subcategory"] += 1
                samples["orphan_subcategory"].append(full_name)

        for tag_field, tag_ids_field, malformed_key, malformed_ids_key, normalized_key in (
            ("ai_tags", "ai_tag_ids", "ai_tags_malformed", "ai_tag_ids_malformed", "ai_tags_not_normalized"),
            (
                "override_tags",
                "override_tag_ids",
                "override_tags_malformed",
                "override_tag_ids_malformed",
                "override_tags_not_normalized",
            ),
        ):
            raw_tags = row[tag_field]
            raw_tag_ids = row[tag_ids_field]
            parsed_tags, tags_malformed = _parse_json_list(raw_tags)
            parsed_tag_ids, tag_ids_malformed = _parse_json_list(raw_tag_ids)

            if tags_malformed:
                counters[malformed_key] += 1
                samples[malformed_key].append(full_name)
            if tag_ids_malformed:
                counters[malformed_ids_key] += 1
                samples[malformed_ids_key].append(full_name)

            if taxonomy is None or tags_malformed or tag_ids_malformed:
                continue

            normalized_tag_ids, _unknown = normalize_tag_ids(parsed_tag_ids + parsed_tags, taxonomy)
            if parsed_tag_ids != normalized_tag_ids:
                counters[normalized_key] += 1
                samples[normalized_key].append(full_name)

    if taxonomy_error:
        _push_issue(
            issues,
            code="taxonomy_load_failed",
            detail=f"Failed to load taxonomy: {taxonomy_error}",
            count=1,
            samples=[],
            level="error",
        )

    if fts_enabled:
        _push_issue(
            issues,
            code="fts_row_count_mismatch",
            detail="FTS row count differs from repos row count",
            count=abs(repos_total - fts_total),
            samples=[],
            level="error",
        )

    _push_issue(
        issues,
        code="blank_category_fields",
        detail="Category fields contain empty strings instead of NULL",
        count=counters["blank_category"],
        samples=samples["blank_category"],
    )
    _push_issue(
        issues,
        code="blank_subcategory_fields",
        detail="Subcategory fields contain empty strings instead of NULL",
        count=counters["blank_subcategory"],
        samples=samples["blank_subcategory"],
    )
    _push_issue(
        issues,
        code="invalid_categories",
        detail="Category values are outside taxonomy",
        count=counters["invalid_category"],
        samples=samples["invalid_category"],
        level="error",
    )
    _push_issue(
        issues,
        code="invalid_subcategories",
        detail="Subcategory values do not belong to the current category",
        count=counters["invalid_subcategory"],
        samples=samples["invalid_subcategory"],
        level="error",
    )
    _push_issue(
        issues,
        code="orphan_subcategories",
        detail="Subcategory is set while category is empty",
        count=counters["orphan_subcategory"],
        samples=samples["orphan_subcategory"],
        level="error",
    )
    _push_issue(
        issues,
        code="malformed_ai_tags",
        detail="`ai_tags` is not a valid JSON array",
        count=counters["ai_tags_malformed"],
        samples=samples["ai_tags_malformed"],
        level="error",
    )
    _push_issue(
        issues,
        code="malformed_ai_tag_ids",
        detail="`ai_tag_ids` is not a valid JSON array",
        count=counters["ai_tag_ids_malformed"],
        samples=samples["ai_tag_ids_malformed"],
        level="error",
    )
    _push_issue(
        issues,
        code="malformed_override_tags",
        detail="`override_tags` is not a valid JSON array",
        count=counters["override_tags_malformed"],
        samples=samples["override_tags_malformed"],
        level="error",
    )
    _push_issue(
        issues,
        code="malformed_override_tag_ids",
        detail="`override_tag_ids` is not a valid JSON array",
        count=counters["override_tag_ids_malformed"],
        samples=samples["override_tag_ids_malformed"],
        level="error",
    )
    _push_issue(
        issues,
        code="non_normalized_ai_tag_ids",
        detail="`ai_tag_ids` is not normalized against taxonomy and current labels",
        count=counters["ai_tags_not_normalized"],
        samples=samples["ai_tags_not_normalized"],
    )
    _push_issue(
        issues,
        code="non_normalized_override_tag_ids",
        detail="`override_tag_ids` is not normalized against taxonomy and current labels",
        count=counters["override_tags_not_normalized"],
        samples=samples["override_tags_not_normalized"],
    )

    error_count = sum(1 for issue in issues if issue["level"] == "error")
    warning_count = sum(1 for issue in issues if issue["level"] != "error")

    return {
        "checked_at": _now_iso(),
        "ok": not issues,
        "repos_total": repos_total,
        "issues_total": len(issues),
        "error_count": error_count,
        "warning_count": warning_count,
        "fts": {
            "enabled": fts_enabled,
            "repos_total": repos_total,
            "fts_total": fts_total,
            "drift": abs(repos_total - fts_total) if fts_enabled else 0,
            "consistent": (repos_total == fts_total) if fts_enabled else True,
        },
        "issues": issues,
    }
