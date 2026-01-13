import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _parse_rules(data: Any) -> List[Dict[str, Any]]:
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list):
        return []
    return [rule for rule in rules if isinstance(rule, dict)]


def load_rules(raw: str, fallback_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
        if data:
            parsed = _parse_rules(data)
            if parsed:
                return parsed

    if fallback_path and fallback_path.exists():
        try:
            data = json.loads(fallback_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return _parse_rules(data)
    return []


def match_rule(repo: Dict[str, Any], rules: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not rules:
        return None
    haystack = " ".join(
        [
            str(repo.get("name") or ""),
            str(repo.get("full_name") or ""),
            str(repo.get("description") or ""),
            " ".join(repo.get("topics") or []),
            str(repo.get("readme_summary") or ""),
        ]
    ).lower()
    for rule in rules:
        keywords = rule.get("keywords") or []
        if not isinstance(keywords, list):
            continue
        if any(str(keyword).lower() in haystack for keyword in keywords):
            return rule
    return None
