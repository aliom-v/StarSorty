import re
from typing import Any, Dict, List, Tuple


_DEFAULT_LEGACY_TAG_ALIASES = {
    "agent": "Agent",
    "ai": "LLM",
    "ai-art": "图像生成",
    "ai-dev": "代码生成",
    "algorithm": "教程",
    "android": "移动App",
    "api-debug": "API调试",
    "backend": "后台服务",
    "blog": "博客",
    "build": "脚手架",
    "chatgpt": "ChatGPT",
    "ci": "CI/CD",
    "cloud-drive": "网盘",
    "course": "教程",
    "database": "数据库",
    "dev-community": "资源合集",
    "docker": "Docker",
    "docs": "文档生成",
    "download": "视频下载",
    "editor": "编辑器",
    "frontend": "Web应用",
    "iac": "配置管理",
    "linux": "本地运行",
    "llm": "LLM",
    "media-server": "后台服务",
    "mobile-dev": "移动App",
    "monitor": "监控",
    "nas": "NAS",
    "nginx": "反向代理",
    "notes": "笔记",
    "observability": "监控",
    "os": "本地运行",
    "paper": "教程",
    "privacy": "隐私保护",
    "programming": "库",
    "proxy": "代理",
    "rag": "RAG",
    "rss": "RSS",
    "security": "隐私保护",
    "social": "订阅",
    "terminal": "命令行",
    "testing": "调试器",
    "tools": "工具",
    "vector-db": "向量数据库",
    "video": "视频处理",
    "vpn": "VPN",
    "vps": "云服务",
}


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def normalize_tag_token(value: str) -> str:
    return str(value or "").strip().lower()


def build_taxonomy_schema(raw: Dict[str, Any]) -> Dict[str, Any]:
    categories = raw.get("categories") or []
    tags = raw.get("tags") or []
    raw_tag_defs = raw.get("tag_defs") or []
    legacy_map_raw = raw.get("legacy_tag_map") or {}

    if not isinstance(categories, list):
        raise ValueError("Taxonomy categories must be a list")
    if not isinstance(tags, list):
        raise ValueError("Taxonomy tags must be a list")
    if not isinstance(raw_tag_defs, list):
        raise ValueError("Taxonomy tag_defs must be a list")
    if not isinstance(legacy_map_raw, dict):
        raise ValueError("Taxonomy legacy_tag_map must be a map")

    normalized_categories: List[Dict[str, Any]] = []
    category_map: Dict[str, List[str]] = {}
    for item in categories:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        subcategories = item.get("subcategories") or []
        if not isinstance(subcategories, list):
            subcategories = []
        normalized_subs = [str(sub).strip() for sub in subcategories if str(sub).strip()]
        normalized_categories.append({"name": name, "subcategories": normalized_subs})
        category_map[name] = normalized_subs

    tag_defs: List[Dict[str, str]] = []
    tag_id_to_name: Dict[str, str] = {}
    tag_name_to_id: Dict[str, str] = {}

    for item in raw_tag_defs:
        if not isinstance(item, dict):
            continue
        tag_id = str(item.get("id") or "").strip()
        name_zh = str(item.get("zh") or item.get("name_zh") or "").strip()
        group = str(item.get("group") or "misc").strip() or "misc"
        if not tag_id:
            continue
        if not name_zh:
            name_zh = tag_id
        if tag_id in tag_id_to_name:
            continue
        tag_defs.append({"id": tag_id, "zh": name_zh, "group": group})
        tag_id_to_name[tag_id] = name_zh
        tag_name_to_id[normalize_tag_token(name_zh)] = tag_id
        tag_name_to_id[normalize_tag_token(tag_id)] = tag_id

    # Backward compatibility: derive tag_defs from legacy tags list when missing.
    if not tag_defs and tags:
        for item in tags:
            name_zh = str(item).strip()
            if not name_zh:
                continue
            tag_id = _slugify(name_zh) or normalize_tag_token(name_zh)
            if not tag_id or tag_id in tag_id_to_name:
                continue
            tag_defs.append({"id": tag_id, "zh": name_zh, "group": "legacy"})
            tag_id_to_name[tag_id] = name_zh
            tag_name_to_id[normalize_tag_token(name_zh)] = tag_id
            tag_name_to_id[normalize_tag_token(tag_id)] = tag_id

    legacy_tag_map: Dict[str, str] = {}
    for key, value in legacy_map_raw.items():
        src = normalize_tag_token(str(key))
        target = str(value or "").strip()
        if not src or not target:
            continue
        if target not in tag_id_to_name:
            continue
        legacy_tag_map[src] = target

    # Auto-generate fallback legacy mapping from old rules tags to existing IDs.
    for token, tag_id in list(tag_name_to_id.items()):
        if token and tag_id:
            legacy_tag_map.setdefault(token, tag_id)
    for legacy_token, target in _DEFAULT_LEGACY_TAG_ALIASES.items():
        mapped = tag_name_to_id.get(normalize_tag_token(target))
        if mapped:
            legacy_tag_map.setdefault(normalize_tag_token(legacy_token), mapped)

    normalized_tags = [tag_id_to_name[tag_id] for tag_id in tag_id_to_name]

    return {
        "categories": normalized_categories,
        "category_map": category_map,
        "tags": normalized_tags,
        "tag_defs": tag_defs,
        "tag_id_to_name": tag_id_to_name,
        "tag_name_to_id": tag_name_to_id,
        "legacy_tag_map": legacy_tag_map,
    }


def normalize_tag_ids(values: List[str], taxonomy: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    tag_id_to_name = taxonomy.get("tag_id_to_name") or {}
    tag_name_to_id = taxonomy.get("tag_name_to_id") or {}
    legacy_map = taxonomy.get("legacy_tag_map") or {}
    normalized: List[str] = []
    unknown: List[str] = []
    seen: set[str] = set()

    for raw in values:
        token = normalize_tag_token(str(raw))
        if not token:
            continue
        mapped = legacy_map.get(token) or tag_name_to_id.get(token)
        if not mapped and token in tag_id_to_name:
            mapped = token
        if not mapped:
            unknown.append(str(raw))
            continue
        if mapped in seen:
            continue
        seen.add(mapped)
        normalized.append(mapped)
    return normalized, unknown


def tag_ids_to_labels(tag_ids: List[str], taxonomy: Dict[str, Any]) -> List[str]:
    tag_id_to_name = taxonomy.get("tag_id_to_name") or {}
    labels: List[str] = []
    for tag_id in tag_ids:
        if tag_id in tag_id_to_name:
            labels.append(tag_id_to_name[tag_id])
    return labels
