#!/usr/bin/env python3
import argparse
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _resolve_db_path(database_url: str) -> str:
    if database_url.startswith("sqlite:////"):
        return "/" + database_url[len("sqlite:////") :]
    if database_url.startswith("sqlite:///"):
        return database_url[len("sqlite:///") :]
    if database_url.startswith("/"):
        return database_url
    raise ValueError("Only sqlite database URL/path is supported")


def _json_list(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    try:
        loaded = json.loads(value)
    except Exception:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(v) for v in loaded if str(v).strip()]


@dataclass
class EvalCounters:
    total: int = 0
    category_hit: int = 0
    subcategory_hit: int = 0
    tag_tp: int = 0
    tag_fp: int = 0
    tag_fn: int = 0
    query_total: int = 0
    query_hit_at_10: int = 0
    query_zero_result: int = 0


def _search_top10(conn: sqlite3.Connection, query: str) -> List[str]:
    if not query.strip():
        return []
    like = f"%{query.strip()}%"
    rows = conn.execute(
        """
        SELECT full_name
        FROM repos
        WHERE name LIKE ?
           OR full_name LIKE ?
           OR description LIKE ?
           OR topics LIKE ?
           OR readme_summary LIKE ?
           OR summary_zh LIKE ?
           OR ai_keywords LIKE ?
           OR override_keywords LIKE ?
        ORDER BY stargazers_count DESC, full_name ASC
        LIMIT 10
        """,
        (like, like, like, like, like, like, like, like),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _compute_tag_f1(tp: int, fp: int, fn: int) -> float:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _snapshot_current(conn: sqlite3.Connection, full_names: List[str]) -> Dict[str, Dict[str, Any]]:
    if not full_names:
        return {}
    placeholders = ",".join("?" for _ in full_names)
    rows = conn.execute(
        f"""
        SELECT
            full_name,
            COALESCE(NULLIF(override_category, ''), category) AS category,
            COALESCE(NULLIF(override_subcategory, ''), subcategory) AS subcategory,
            COALESCE(NULLIF(override_tags, ''), ai_tags) AS tags,
            COALESCE(NULLIF(override_keywords, ''), ai_keywords) AS keywords
        FROM repos
        WHERE full_name IN ({placeholders})
        """,
        full_names,
    ).fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        out[str(row[0])] = {
            "category": row[1],
            "subcategory": row[2],
            "tags": _json_list(row[3]),
            "keywords": _json_list(row[4]),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay evaluation on a golden set.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", "sqlite:////data/app.db"))
    parser.add_argument("--golden-set", default="evaluation/golden_set.json")
    parser.add_argument("--write-snapshot", default="")
    parser.add_argument("--baseline-snapshot", default="")
    parser.add_argument("--diff-output", default="evaluation/replay_diff.json")
    args = parser.parse_args()

    db_path = _resolve_db_path(args.database_url)
    golden_path = Path(args.golden_set)
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    if not isinstance(golden, list):
        raise ValueError("golden_set.json must be an array")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    counters = EvalCounters()
    mismatches: List[Dict[str, Any]] = []
    full_names_for_snapshot: List[str] = []

    try:
        for item in golden:
            if not isinstance(item, dict):
                continue
            full_name = str(item.get("full_name") or "").strip()
            expected = item.get("expected") or {}
            if not full_name or not isinstance(expected, dict):
                continue
            full_names_for_snapshot.append(full_name)

            row = conn.execute(
                """
                SELECT
                    COALESCE(NULLIF(override_category, ''), category) AS category,
                    COALESCE(NULLIF(override_subcategory, ''), subcategory) AS subcategory,
                    COALESCE(NULLIF(override_tags, ''), ai_tags) AS tags
                FROM repos
                WHERE full_name = ?
                """,
                (full_name,),
            ).fetchone()
            if row is None:
                mismatches.append({"full_name": full_name, "error": "missing_repo"})
                continue

            actual_category = str(row["category"] or "")
            actual_subcategory = str(row["subcategory"] or "")
            actual_tags = set(_json_list(row["tags"]))
            expected_category = str(expected.get("category") or "")
            expected_subcategory = str(expected.get("subcategory") or "")
            expected_tags = set(str(v) for v in (expected.get("tags") or []) if str(v).strip())

            counters.total += 1
            if actual_category == expected_category:
                counters.category_hit += 1
            if actual_subcategory == expected_subcategory:
                counters.subcategory_hit += 1

            counters.tag_tp += len(actual_tags & expected_tags)
            counters.tag_fp += len(actual_tags - expected_tags)
            counters.tag_fn += len(expected_tags - actual_tags)

            if (
                actual_category != expected_category
                or actual_subcategory != expected_subcategory
                or actual_tags != expected_tags
            ):
                mismatches.append(
                    {
                        "full_name": full_name,
                        "expected": {
                            "category": expected_category,
                            "subcategory": expected_subcategory,
                            "tags": sorted(expected_tags),
                        },
                        "actual": {
                            "category": actual_category,
                            "subcategory": actual_subcategory,
                            "tags": sorted(actual_tags),
                        },
                    }
                )

            for query in item.get("query_samples") or []:
                query_text = str(query).strip()
                if not query_text:
                    continue
                counters.query_total += 1
                top10 = _search_top10(conn, query_text)
                if not top10:
                    counters.query_zero_result += 1
                if full_name in top10:
                    counters.query_hit_at_10 += 1

        metrics = {
            "classification": {
                "evaluated": counters.total,
                "category_accuracy": counters.category_hit / counters.total if counters.total else 0.0,
                "subcategory_accuracy": counters.subcategory_hit / counters.total if counters.total else 0.0,
                "tag_f1": _compute_tag_f1(counters.tag_tp, counters.tag_fp, counters.tag_fn),
            },
            "search": {
                "queries": counters.query_total,
                "query_at_10_hit_rate": counters.query_hit_at_10 / counters.query_total
                if counters.query_total
                else 0.0,
                "zero_result_rate": counters.query_zero_result / counters.query_total
                if counters.query_total
                else 0.0,
            },
            "mismatch_count": len(mismatches),
        }

        snapshot = _snapshot_current(conn, full_names_for_snapshot)
    finally:
        conn.close()

    if args.write_snapshot:
        snapshot_path = Path(args.write_snapshot)
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    diff_payload = {}
    if args.baseline_snapshot:
        baseline = json.loads(Path(args.baseline_snapshot).read_text(encoding="utf-8"))
        if not isinstance(baseline, dict):
            raise ValueError("baseline snapshot must be a JSON object keyed by full_name")
        diffs: List[Dict[str, Any]] = []
        for full_name, current in snapshot.items():
            before = baseline.get(full_name)
            if not isinstance(before, dict):
                continue
            if (
                before.get("category") == current.get("category")
                and before.get("subcategory") == current.get("subcategory")
                and before.get("tags") == current.get("tags")
                and before.get("keywords") == current.get("keywords")
            ):
                continue
            diffs.append(
                {
                    "full_name": full_name,
                    "before": before,
                    "after": current,
                }
            )
        diff_payload = {"changed": len(diffs), "items": diffs}
        diff_path = Path(args.diff_output)
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text(json.dumps(diff_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    output = {
        "metrics": metrics,
        "mismatches": mismatches[:200],
        "diff": diff_payload,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
