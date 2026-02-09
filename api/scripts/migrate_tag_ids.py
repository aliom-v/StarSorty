#!/usr/bin/env python3
import argparse
import json
import os
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app.rules import load_rules
from api.app.taxonomy_schema import build_taxonomy_schema, normalize_tag_ids

try:
    from api.app.taxonomy import load_taxonomy as _load_taxonomy  # type: ignore
except Exception:
    _load_taxonomy = None


def _resolve_db_path(database_url: str) -> str:
    if database_url.startswith("sqlite:////"):
        return "/" + database_url[len("sqlite:////") :]
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///") :]
    if database_url.startswith("/"):
        return database_url
    raise ValueError("Only sqlite database URL/path is supported")


def _load_json_list(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(v).strip() for v in parsed if str(v).strip()]


def _scan_and_migrate_repos(
    conn: sqlite3.Connection,
    taxonomy: Dict[str, Any],
    apply: bool,
) -> Tuple[Dict[str, int], Counter]:
    columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(repos)").fetchall()
    }
    has_ai_tag_ids = "ai_tag_ids" in columns
    has_override_tag_ids = "override_tag_ids" in columns
    cursor = conn.execute(
        f"""
        SELECT
            full_name,
            ai_tags,
            {"ai_tag_ids" if has_ai_tag_ids else "NULL AS ai_tag_ids"},
            override_tags,
            {"override_tag_ids" if has_override_tag_ids else "NULL AS override_tag_ids"}
        FROM repos
        """
    )
    unknown_counter: Counter = Counter()
    stats = {
        "repos_total": 0,
        "ai_rows_seen": 0,
        "override_rows_seen": 0,
        "ai_tag_ids_updated": 0,
        "override_tag_ids_updated": 0,
        "has_ai_tag_ids_column": int(has_ai_tag_ids),
        "has_override_tag_ids_column": int(has_override_tag_ids),
    }
    updates: List[Tuple[str, str, str]] = []
    for row in cursor.fetchall():
        full_name = str(row[0])
        ai_tags = _load_json_list(row[1])
        ai_tag_ids = _load_json_list(row[2])
        override_tags = _load_json_list(row[3])
        override_tag_ids = _load_json_list(row[4])
        stats["repos_total"] += 1

        if ai_tags or ai_tag_ids:
            stats["ai_rows_seen"] += 1
        if override_tags or override_tag_ids:
            stats["override_rows_seen"] += 1

        normalized_ai_tag_ids, unknown_ai = normalize_tag_ids(ai_tag_ids + ai_tags, taxonomy)
        normalized_override_tag_ids, unknown_override = normalize_tag_ids(
            override_tag_ids + override_tags, taxonomy
        )
        for unknown in unknown_ai + unknown_override:
            unknown_counter[unknown] += 1

        if normalized_ai_tag_ids != ai_tag_ids:
            stats["ai_tag_ids_updated"] += 1
        if normalized_override_tag_ids != override_tag_ids:
            stats["override_tag_ids_updated"] += 1

        if apply:
            updates.append(
                (
                    json.dumps(normalized_ai_tag_ids, ensure_ascii=False),
                    json.dumps(normalized_override_tag_ids, ensure_ascii=False),
                    full_name,
                )
            )

    if apply and updates and has_ai_tag_ids and has_override_tag_ids:
        conn.executemany(
            """
            UPDATE repos
            SET ai_tag_ids = ?, override_tag_ids = ?
            WHERE full_name = ?
            """,
            updates,
        )
        conn.commit()

    return stats, unknown_counter


def _load_taxonomy_with_fallback(path: str) -> Dict[str, Any]:
    if _load_taxonomy is not None:
        return _load_taxonomy(path)
    text = Path(path).read_text(encoding="utf-8")
    categories: List[Dict[str, Any]] = []
    tags: List[str] = []

    lines = text.splitlines()
    in_categories = False
    in_tags = False
    current_name = ""
    current_subs: List[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("categories:"):
            in_categories = True
            in_tags = False
            continue
        if stripped.startswith("tags:"):
            if current_name:
                categories.append({"name": current_name, "subcategories": current_subs})
            current_name = ""
            current_subs = []
            in_categories = False
            in_tags = True
            continue
        if in_categories:
            name_match = re.match(r"^\s*-\s*name:\s*(.+)$", line)
            if name_match:
                if current_name:
                    categories.append({"name": current_name, "subcategories": current_subs})
                current_name = name_match.group(1).strip().strip('"').strip("'")
                current_subs = []
                continue
            subs_match = re.match(r"^\s*subcategories:\s*\[(.*)\]\s*$", line)
            if subs_match:
                raw_items = [item.strip() for item in subs_match.group(1).split(",")]
                current_subs = [item.strip('"').strip("'") for item in raw_items if item]
                continue
        if in_tags:
            tag_match = re.match(r"^\s*-\s*(.+)$", line)
            if tag_match:
                value = tag_match.group(1).strip().strip('"').strip("'")
                if value and not value.startswith("#"):
                    tags.append(value)

    if current_name:
        categories.append({"name": current_name, "subcategories": current_subs})

    return build_taxonomy_schema({"categories": categories, "tags": tags})


def _migrate_rules(
    rules_path: Path,
    taxonomy: Dict[str, Any],
    write_path: Path | None,
) -> Tuple[Dict[str, int], Counter]:
    raw = json.loads(rules_path.read_text(encoding="utf-8"))
    normalized_rules = load_rules("", fallback_path=rules_path)
    unknown_counter: Counter = Counter()
    rules_out: List[Dict[str, Any]] = []

    stats = {
        "rules_total": 0,
        "rules_with_unknown_tags": 0,
    }

    for index, rule in enumerate(normalized_rules):
        stats["rules_total"] += 1
        combined_tags = [str(v).strip() for v in (rule.get("tag_ids") or []) if str(v).strip()]
        combined_tags.extend([str(v).strip() for v in (rule.get("tags") or []) if str(v).strip()])
        normalized_tag_ids, unknowns = normalize_tag_ids(combined_tags, taxonomy)
        if unknowns:
            stats["rules_with_unknown_tags"] += 1
            for token in unknowns:
                unknown_counter[token] += 1
        rules_out.append(
            {
                "rule_id": rule.get("rule_id") or f"rule_{index + 1}",
                "must_keywords": rule.get("must_keywords") or [],
                "should_keywords": rule.get("should_keywords") or [],
                "exclude_keywords": rule.get("exclude_keywords") or [],
                "candidate_category": rule.get("candidate_category") or "uncategorized",
                "candidate_subcategory": rule.get("candidate_subcategory") or "other",
                "tag_ids": normalized_tag_ids,
                "priority": int(rule.get("priority", 0) or 0),
            }
        )

    if write_path:
        write_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 2, "rules": rules_out}
        write_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Ensure raw file is valid JSON even if no rules were parsed; this is a safety read.
    _ = raw.get("rules", [])
    return stats, unknown_counter


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy tags to stable tag_ids.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:////data/app.db"))
    parser.add_argument("--taxonomy", default="api/config/taxonomy.yaml")
    parser.add_argument("--rules", default="api/config/rules.json")
    parser.add_argument("--apply", action="store_true", help="Apply DB updates for *_tag_ids columns.")
    parser.add_argument(
        "--write-rules",
        default="",
        help="Optional output path for normalized rules.json with tag_ids.",
    )
    parser.add_argument("--report", default="api/migration/tag_id_migration_report.json")
    args = parser.parse_args()

    taxonomy = _load_taxonomy_with_fallback(args.taxonomy)
    db_path = _resolve_db_path(args.database_url)
    rules_path = Path(args.rules)
    write_rules_path = Path(args.write_rules) if args.write_rules else None

    conn = sqlite3.connect(db_path)
    try:
        repo_stats, unknown_repo_tags = _scan_and_migrate_repos(conn, taxonomy, args.apply)
    finally:
        conn.close()

    rule_stats, unknown_rule_tags = _migrate_rules(rules_path, taxonomy, write_rules_path)

    unknown_all = unknown_repo_tags + unknown_rule_tags
    report = {
        "database_path": db_path,
        "taxonomy_path": args.taxonomy,
        "rules_path": str(rules_path),
        "applied": bool(args.apply),
        "repo_stats": repo_stats,
        "rule_stats": rule_stats,
        "unknown_tags_total": sum(unknown_all.values()),
        "unknown_tags_top": unknown_all.most_common(50),
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
