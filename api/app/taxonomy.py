from pathlib import Path
from typing import Any, Dict, List

import yaml

from .taxonomy_schema import build_taxonomy_schema, normalize_tag_ids, tag_ids_to_labels


def load_taxonomy(path: str) -> Dict[str, Any]:
    if not path:
        raise ValueError("AI_TAXONOMY_PATH is not set")
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Taxonomy file not found: {file_path}")
    data = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    return build_taxonomy_schema(data)


def format_taxonomy_for_prompt(taxonomy: Dict[str, Any]) -> str:
    lines: List[str] = []
    for category in taxonomy.get("categories", []):
        name = category.get("name")
        subs = category.get("subcategories") or []
        if not name:
            continue
        if subs:
            lines.append(f"- {name}: {', '.join(subs)}")
        else:
            lines.append(f"- {name}: (no subcategories)")
    return "\n".join(lines)


def validate_classification(
    result: Dict[str, Any],
    taxonomy: Dict[str, Any],
) -> Dict[str, Any]:
    category_map = taxonomy.get("category_map") or {}

    category = result.get("category") if isinstance(result, dict) else None
    subcategory = result.get("subcategory") if isinstance(result, dict) else None
    tags = result.get("tags") if isinstance(result, dict) else []
    tag_ids = result.get("tag_ids") if isinstance(result, dict) else []
    confidence = result.get("confidence") if isinstance(result, dict) else 0.0
    summary_zh = result.get("summary_zh") if isinstance(result, dict) else None
    keywords = result.get("keywords") if isinstance(result, dict) else None
    reason = result.get("reason") if isinstance(result, dict) else None

    if category not in category_map:
        category = "uncategorized"
    allowed_subs = category_map.get(category) or []
    if subcategory not in allowed_subs:
        subcategory = (
            "other"
            if "other" in allowed_subs
            else (allowed_subs[0] if allowed_subs else "other")
        )

    normalized_tag_inputs: List[str] = []
    if isinstance(tag_ids, list):
        normalized_tag_inputs.extend([str(tag).strip() for tag in tag_ids if str(tag).strip()])
    if isinstance(tags, list):
        normalized_tag_inputs.extend([str(tag).strip() for tag in tags if str(tag).strip()])
    normalized_tag_ids, _unknown = normalize_tag_ids(normalized_tag_inputs, taxonomy)
    normalized_tags = tag_ids_to_labels(normalized_tag_ids, taxonomy)

    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
    if confidence_value < 0 or confidence_value > 1:
        confidence_value = 0.0

    validated: Dict[str, Any] = {
        "category": category,
        "subcategory": subcategory,
        "tags": normalized_tags,
        "tag_ids": normalized_tag_ids,
        "confidence": confidence_value,
    }
    if summary_zh:
        validated["summary_zh"] = str(summary_zh).strip()[:200]
    if keywords and isinstance(keywords, list):
        validated["keywords"] = [str(k).strip() for k in keywords if str(k).strip()][:5]
    if reason:
        validated["reason"] = str(reason).strip()[:500]
    return validated


def validate_classification_v2(result: Dict[str, Any]) -> Dict[str, Any]:
    summary_zh = str(result.get("summary_zh") or "").strip()[:200]
    raw_tags = result.get("tags") or []
    tags = [str(t).strip() for t in raw_tags if str(t).strip()][:8]
    raw_keywords = result.get("keywords") or []
    keywords = [str(k).strip() for k in raw_keywords if str(k).strip()][:5]
    return {"summary_zh": summary_zh, "tags": tags, "keywords": keywords}


def normalize_tags_to_ids(tags: List[str], taxonomy: Dict[str, Any]) -> List[str]:
    normalized, _unknown = normalize_tag_ids(tags, taxonomy)
    return normalized
