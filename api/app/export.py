import io
import re
import zipfile
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List


def sanitize_filename(name: str) -> str:
    """Replace invalid filename characters with underscores."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)


def escape_yaml_string(value: str) -> str:
    """Escape a string for safe YAML output."""
    if not value:
        return '""'
    # If contains special chars, wrap in quotes and escape internal quotes
    if any(c in value for c in [':', '#', '"', "'", '\n', '[', ']', '{', '}']):
        escaped = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        return f'"{escaped}"'
    return value


def sanitize_tag_for_obsidian(tag: str) -> str:
    """Convert tag to Obsidian-compatible format (no spaces)."""
    return tag.replace(" ", "-")


def format_stars(count: int | None) -> str:
    if not count:
        return "0"
    if count >= 1000:
        return f"{count / 1000:.1f}k"
    return str(count)


def generate_repo_markdown(repo: Dict[str, Any]) -> str:
    """Generate Obsidian-compatible Markdown for a single repo."""
    name = repo.get("name", "")
    owner = repo.get("owner", "")
    full_name = repo.get("full_name", "")
    url = repo.get("html_url", "")
    language = repo.get("language") or ""
    stars = repo.get("stargazers_count") or 0
    forks = repo.get("forks_count") or 0
    category = repo.get("category") or ""
    tags = repo.get("tags") or []
    keywords = repo.get("keywords") or []
    starred_at = repo.get("starred_at") or ""
    summary_zh = repo.get("summary_zh") or repo.get("description") or ""
    exported_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Build YAML frontmatter with proper escaping
    tags_yaml = "[" + ", ".join(f'"{t}"' for t in tags) + "]" if tags else "[]"
    keywords_yaml = "[" + ", ".join(f'"{k}"' for k in keywords) + "]" if keywords else "[]"

    frontmatter = f"""---
name: {escape_yaml_string(name)}
owner: {escape_yaml_string(owner)}
full_name: {escape_yaml_string(full_name)}
url: {escape_yaml_string(url)}
language: {escape_yaml_string(language)}
stars: {stars}
forks: {forks}
category: {escape_yaml_string(category)}
tags: {tags_yaml}
keywords: {keywords_yaml}
starred_at: {escape_yaml_string(starred_at)}
exported_at: {exported_at}
---"""

    # Build body - sanitize tags for Obsidian hashtag format
    tags_line = " ".join(f"#{sanitize_tag_for_obsidian(t)}" for t in tags) if tags else ""
    starred_date = starred_at[:10] if starred_at else "N/A"
    display_summary = summary_zh if summary_zh else "暂无描述"

    body = f"""
# {name}

> {display_summary}

## 信息

| 属性 | 值 |
|------|-----|
| 仓库 | [{full_name}]({url}) |
| 语言 | {language or "N/A"} |
| Stars | {format_stars(stars)} |
| 收藏时间 | {starred_date} |

## 标签

{tags_line}

---

## 我的笔记

<!-- 在这里添加你的笔记 -->
"""

    return frontmatter + body


def generate_obsidian_zip(repos: List[Dict[str, Any]]) -> bytes:
    """Generate a ZIP file with Markdown files organized by category."""
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for repo in repos:
            category = repo.get("category") or "未分类"
            owner = repo.get("owner", "unknown")
            name = repo.get("name", "unknown")

            safe_category = sanitize_filename(category)
            safe_owner = sanitize_filename(owner)
            safe_name = sanitize_filename(name)

            filename = f"{safe_category}/{safe_owner}_{safe_name}.md"
            content = generate_repo_markdown(repo)

            zf.writestr(filename, content.encode("utf-8"))

    buffer.seek(0)
    return buffer.getvalue()


async def generate_obsidian_zip_streaming(repo_iter: AsyncIterator[Any]) -> bytes:
    """Generate a ZIP file from an async iterator of repos (memory-efficient)."""
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        async for repo in repo_iter:
            repo_dict = repo.model_dump() if hasattr(repo, "model_dump") else repo
            category = repo_dict.get("category") or "未分类"
            owner = repo_dict.get("owner", "unknown")
            name = repo_dict.get("name", "unknown")

            safe_category = sanitize_filename(category)
            safe_owner = sanitize_filename(owner)
            safe_name = sanitize_filename(name)

            filename = f"{safe_category}/{safe_owner}_{safe_name}.md"
            content = generate_repo_markdown(repo_dict)

            zf.writestr(filename, content.encode("utf-8"))

    buffer.seek(0)
    return buffer.getvalue()
