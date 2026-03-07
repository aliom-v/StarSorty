#!/usr/bin/env python3
import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.app.db import close_db_pool, init_db, init_db_pool, prune_star_user, prune_users_not_in, upsert_repos
from api.app.db.classification import update_classifications_bulk
from api.app.db.pool import get_connection
from api.app.db.search import RELEVANCE_CANDIDATE_LIMIT, list_repos
from api.app.taxonomy import load_taxonomy
from api.app.taxonomy_schema import normalize_tag_ids


PATTERNS = [
    {
        "slug": "llm-agent",
        "language": "Python",
        "category": "ai",
        "subcategory": "llm",
        "tags": ["LLM", "Agent", "工具"],
        "keywords": ["llm", "agent", "chat"],
        "query": "llm agent chat",
    },
    {
        "slug": "rag-framework",
        "language": "Python",
        "category": "ai",
        "subcategory": "rag",
        "tags": ["RAG", "框架", "库"],
        "keywords": ["rag", "retrieval", "embedding"],
        "query": "rag retrieval embedding",
    },
    {
        "slug": "monitor-docker",
        "language": "Go",
        "category": "devops",
        "subcategory": "monitor",
        "tags": ["监控", "Docker", "自托管"],
        "keywords": ["monitor", "docker", "alert"],
        "query": "docker monitor alert",
    },
    {
        "slug": "notes-markdown",
        "language": "TypeScript",
        "category": "productivity",
        "subcategory": "notes",
        "tags": ["笔记", "Markdown", "知识库"],
        "keywords": ["notes", "markdown", "knowledge"],
        "query": "markdown notes knowledge",
    },
    {
        "slug": "proxy-network",
        "language": "Rust",
        "category": "network",
        "subcategory": "proxy",
        "tags": ["代理", "CLI", "工具"],
        "keywords": ["proxy", "network", "tunnel"],
        "query": "proxy network tunnel",
    },
    {
        "slug": "frontend-ui",
        "language": "TypeScript",
        "category": "dev",
        "subcategory": "frontend",
        "tags": ["Web应用", "框架", "模板"],
        "keywords": ["frontend", "ui", "components"],
        "query": "frontend ui components",
    },
]

SYNC_PATTERN = {
    "language": "Python",
    "category": "dev",
    "subcategory": "backend",
    "tags": ["工具", "库"],
    "keywords": ["sync", "repo", "benchmark"],
}


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * p
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def round_metrics(values: Sequence[float]) -> Dict[str, float]:
    if not values:
        return {"min_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "mean_ms": 0.0, "max_ms": 0.0}
    return {
        "min_ms": round(min(values), 2),
        "p50_ms": round(percentile(values, 0.50), 2),
        "p95_ms": round(percentile(values, 0.95), 2),
        "mean_ms": round(statistics.fmean(values), 2),
        "max_ms": round(max(values), 2),
    }


def sqlite_url(path: Path) -> str:
    resolved = str(path.resolve())
    return f"sqlite:////{resolved.lstrip('/')}"


async def prepare_database(db_path: Path) -> None:
    await close_db_pool()
    if db_path.exists():
        db_path.unlink()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["DATABASE_URL"] = sqlite_url(db_path)
    await init_db_pool(pool_size=1)
    await init_db()


async def repo_count() -> int:
    async with get_connection() as conn:
        row = await (await conn.execute("SELECT COUNT(*) FROM repos")).fetchone()
    return int(row[0] or 0)


async def seed_repos(repo_payloads: List[Dict[str, Any]], classification_payloads: List[Dict[str, Any]], batch_size: int) -> None:
    for start in range(0, len(repo_payloads), batch_size):
        chunk = repo_payloads[start : start + batch_size]
        await upsert_repos(chunk)
    for start in range(0, len(classification_payloads), batch_size):
        chunk = classification_payloads[start : start + batch_size]
        await update_classifications_bulk(chunk)


def build_search_dataset(total: int, taxonomy: Dict[str, Any]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    repos: List[Dict[str, Any]] = []
    classifications: List[Dict[str, Any]] = []
    cases_by_name: Dict[str, Dict[str, Any]] = {}

    for index in range(total):
        pattern = PATTERNS[index % len(PATTERNS)]
        tag_ids, _unknown = normalize_tag_ids(pattern["tags"], taxonomy)
        full_name = f"bench/{pattern['slug']}-{index:05d}"
        repos.append(
            {
                "full_name": full_name,
                "name": f"{pattern['slug']}-{index:05d}",
                "owner": "bench",
                "html_url": f"https://example.com/{full_name}",
                "description": (
                    f"{pattern['slug']} benchmark repository {index} "
                    f"covering {' '.join(pattern['keywords'])} and {pattern['category']}"
                ),
                "language": pattern["language"],
                "stargazers_count": 5000 - index,
                "forks_count": index % 300,
                "topics": [pattern["category"], pattern["subcategory"], *pattern["keywords"]],
                "pushed_at": "2026-03-01T00:00:00+00:00",
                "updated_at": f"2026-03-{(index % 28) + 1:02d}T00:00:00+00:00",
                "starred_at": "2026-03-01T00:00:00+00:00",
                "star_users": ["bench-user"],
            }
        )
        classifications.append(
            {
                "full_name": full_name,
                "category": pattern["category"],
                "subcategory": pattern["subcategory"],
                "confidence": 0.92,
                "tags": pattern["tags"],
                "tag_ids": tag_ids,
                "provider": "benchmark",
                "model": "synthetic-v1",
                "summary_zh": f"{pattern['slug']} synthetic benchmark repo {index}",
                "keywords": pattern["keywords"],
                "reason": "synthetic benchmark seed",
                "decision_source": "benchmark",
                "rule_candidates": [],
            }
        )
        cases_by_name.setdefault(
            pattern["slug"],
            {
                "name": f"relevance_{pattern['slug']}",
                "kind": "search",
                "query": pattern["query"],
                "sort": "relevance",
                "limit": 50,
                "offset": 0,
            },
        )

    cases = list(cases_by_name.values())
    cases.extend(
        [
            {
                "name": "stars_ai_filter",
                "kind": "filter",
                "query": None,
                "category": "ai",
                "sort": "stars",
                "limit": 50,
                "offset": 0,
            },
            {
                "name": "updated_typescript_filter",
                "kind": "filter",
                "query": None,
                "language": "TypeScript",
                "sort": "updated",
                "limit": 50,
                "offset": 0,
            },
        ]
    )
    return repos, classifications, cases


def build_sync_payloads(full_names: Sequence[str], user: str) -> List[Dict[str, Any]]:
    repos: List[Dict[str, Any]] = []
    for index, full_name in enumerate(full_names):
        repo_name = full_name.split("/", 1)[-1]
        repos.append(
            {
                "full_name": full_name,
                "name": repo_name,
                "owner": full_name.split("/", 1)[0],
                "html_url": f"https://example.com/{full_name}",
                "description": f"sync benchmark repo {repo_name} for {user}",
                "language": SYNC_PATTERN["language"],
                "stargazers_count": 100000 - index,
                "forks_count": index % 100,
                "topics": ["sync", "benchmark", "starred"],
                "pushed_at": "2026-03-01T00:00:00+00:00",
                "updated_at": "2026-03-01T00:00:00+00:00",
                "starred_at": "2026-03-01T00:00:00+00:00",
                "star_users": [user],
            }
        )
    return repos


async def measure_call(callable_obj, *args, **kwargs) -> tuple[float, Any]:
    started = time.perf_counter()
    result = await callable_obj(*args, **kwargs)
    return (time.perf_counter() - started) * 1000, result


async def run_search_benchmark(args, workdir: Path) -> Dict[str, Any]:
    db_path = workdir / "search_benchmark.db"
    await prepare_database(db_path)
    taxonomy = load_taxonomy(args.taxonomy_path)
    repo_payloads, classification_payloads, cases = build_search_dataset(args.dataset_size, taxonomy)
    await seed_repos(repo_payloads, classification_payloads, args.batch_size)

    results: List[Dict[str, Any]] = []
    for case in cases:
        for _ in range(args.warmup_runs):
            await list_repos(
                q=case.get("query"),
                language=case.get("language"),
                category=case.get("category"),
                sort=case.get("sort", "stars"),
                limit=case.get("limit", 50),
                offset=case.get("offset", 0),
            )

        latencies: List[float] = []
        total_hits = 0
        returned_items = 0
        for _ in range(args.search_runs):
            started = time.perf_counter()
            page = await list_repos(
                q=case.get("query"),
                language=case.get("language"),
                category=case.get("category"),
                sort=case.get("sort", "stars"),
                limit=case.get("limit", 50),
                offset=case.get("offset", 0),
            )
            latencies.append((time.perf_counter() - started) * 1000)
            total_hits = page.total
            returned_items = len(page.items)

        results.append(
            {
                "name": case["name"],
                "query": case.get("query"),
                "sort": case.get("sort", "stars"),
                "language": case.get("language"),
                "category": case.get("category"),
                "total_hits": total_hits,
                "returned_items": returned_items,
                **round_metrics(latencies),
            }
        )

    overall_p95 = max((item["p95_ms"] for item in results), default=0.0)
    return {
        "dataset_size": args.dataset_size,
        "relevance_candidate_limit": RELEVANCE_CANDIDATE_LIMIT,
        "warmup_runs": args.warmup_runs,
        "measured_runs": args.search_runs,
        "repo_count": await repo_count(),
        "overall_p95_ms": overall_p95,
        "cases": results,
    }


async def run_sync_benchmark(args, workdir: Path) -> Dict[str, Any]:
    db_path = workdir / "sync_benchmark.db"
    await prepare_database(db_path)

    alice_initial = [f"sync/repo-{index:05d}" for index in range(args.sync_repo_count)]
    alice_next = alice_initial[args.sync_churn :] + [
        f"sync/repo-{args.sync_repo_count + index:05d}" for index in range(args.sync_churn)
    ]

    overlap = int(args.sync_repo_count * args.sync_overlap_ratio)
    bob_names = alice_initial[:overlap] + [
        f"sync-b/repo-{index:05d}" for index in range(args.sync_repo_count - overlap)
    ]
    carol_names = alice_initial[: overlap // 2] + [
        f"sync-c/repo-{index:05d}" for index in range(args.sync_repo_count - (overlap // 2))
    ]

    scenarios: List[Dict[str, Any]] = []

    alice_payloads = build_sync_payloads(alice_initial, "alice")
    upsert_ms, upsert_count = await measure_call(upsert_repos, alice_payloads)
    prune_ms, prune_result = await measure_call(prune_star_user, "alice", alice_initial)
    scenarios.append(
        {
            "name": "initial_sync_alice",
            "repo_input": len(alice_payloads),
            "upserted": upsert_count,
            "upsert_ms": round(upsert_ms, 2),
            "prune_ms": round(prune_ms, 2),
            "pruned_star_links": prune_result[0],
            "deleted_repos": prune_result[1],
            "repo_count": await repo_count(),
        }
    )

    alice_next_payloads = build_sync_payloads(alice_next, "alice")
    upsert_ms, upsert_count = await measure_call(upsert_repos, alice_next_payloads)
    prune_ms, prune_result = await measure_call(prune_star_user, "alice", alice_next)
    scenarios.append(
        {
            "name": f"incremental_sync_alice_{args.sync_churn}_churn",
            "repo_input": len(alice_next_payloads),
            "upserted": upsert_count,
            "upsert_ms": round(upsert_ms, 2),
            "prune_ms": round(prune_ms, 2),
            "pruned_star_links": prune_result[0],
            "deleted_repos": prune_result[1],
            "repo_count": await repo_count(),
        }
    )

    bob_payloads = build_sync_payloads(bob_names, "bob")
    carol_payloads = build_sync_payloads(carol_names, "carol")
    bob_ms, bob_count = await measure_call(upsert_repos, bob_payloads)
    bob_prune_ms, bob_prune = await measure_call(prune_star_user, "bob", bob_names)
    carol_ms, carol_count = await measure_call(upsert_repos, carol_payloads)
    carol_prune_ms, carol_prune = await measure_call(prune_star_user, "carol", carol_names)
    cleanup_ms, cleanup_result = await measure_call(prune_users_not_in, ["alice", "bob"])
    scenarios.append(
        {
            "name": "multi_user_merge_and_cleanup",
            "users": 3,
            "repo_input": len(bob_payloads) + len(carol_payloads),
            "upsert_ms": round(bob_ms + carol_ms, 2),
            "prune_ms": round(bob_prune_ms + carol_prune_ms, 2),
            "cleanup_ms": round(cleanup_ms, 2),
            "upserted": bob_count + carol_count,
            "pruned_star_links": bob_prune[0] + carol_prune[0] + cleanup_result[0],
            "deleted_repos": bob_prune[1] + carol_prune[1] + cleanup_result[1],
            "repo_count": await repo_count(),
        }
    )

    return {
        "sync_repo_count": args.sync_repo_count,
        "sync_overlap_ratio": args.sync_overlap_ratio,
        "sync_churn": args.sync_churn,
        "scenarios": scenarios,
    }


async def async_main(args) -> Dict[str, Any]:
    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "search": await run_search_benchmark(args, workdir),
        "sync": await run_sync_benchmark(args, workdir),
    }
    await close_db_pool()
    return payload


def main() -> None:
    default_workdir = REPO_ROOT / "evaluation" / "benchmarks"
    default_taxonomy = REPO_ROOT / "api" / "config" / "taxonomy.yaml"
    default_output = default_workdir / "latest-report.json"

    parser = argparse.ArgumentParser(description="Offline benchmark for StarSorty search and sync paths.")
    parser.add_argument("--dataset-size", type=int, default=5000)
    parser.add_argument("--search-runs", type=int, default=30)
    parser.add_argument("--warmup-runs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--sync-repo-count", type=int, default=5000)
    parser.add_argument("--sync-overlap-ratio", type=float, default=0.7)
    parser.add_argument("--sync-churn", type=int, default=500)
    parser.add_argument("--taxonomy-path", default=str(default_taxonomy))
    parser.add_argument("--workdir", default=str(default_workdir))
    parser.add_argument("--output", default=str(default_output))
    args = parser.parse_args()

    report = asyncio.run(async_main(args))
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
