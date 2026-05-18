from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from agent_atlas.config import AtlasConfig, expand_path


def scan_wiki(root: Path, config: AtlasConfig) -> list[dict[str, Any]]:
    if not config.llm_wiki.index_markdown:
        write_index(root, [])
        return []
    wiki_path = expand_path(config.llm_wiki.path)
    entries: list[dict[str, Any]] = []
    if not wiki_path.exists():
        write_index(root, entries)
        return entries
    for path in sorted(wiki_path.rglob("*.md")):
        entries.append(parse_markdown(path, wiki_path))
    write_index(root, entries)
    return entries


def parse_markdown(path: Path, wiki_root: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    frontmatter, body = parse_frontmatter(text)
    headings = re.findall(r"^(#{1,6})\s+(.+)$", body, flags=re.MULTILINE)
    title = next((heading for level, heading in headings if level == "#"), path.stem)
    relative_path = str(path.relative_to(wiki_root))
    tags = as_string_list(frontmatter.get("tags"))
    aliases = as_string_list(frontmatter.get("aliases"))
    project_ids = as_string_list(frontmatter.get("projects") or frontmatter.get("project_ids"))
    stack = as_string_list(frontmatter.get("stack"))
    commands = as_string_list(frontmatter.get("commands"))
    snippets = extract_snippets(body)
    token_index = sorted(
        set(
            tokenize(
                " ".join(
                    [
                        relative_path,
                        title,
                        " ".join(heading for _level, heading in headings),
                        " ".join(tags),
                        " ".join(aliases),
                        " ".join(project_ids),
                        " ".join(stack),
                        " ".join(commands),
                        " ".join(snippets),
                    ]
                )
            )
        )
    )
    return {
        "path": str(path),
        "relative_path": relative_path,
        "title": title.strip(),
        "headings": [heading.strip() for _level, heading in headings[:30]],
        "tags": tags,
        "aliases": aliases,
        "project_ids": project_ids,
        "stack": stack,
        "commands": commands,
        "updated": str(frontmatter.get("updated", "") or ""),
        "mtime": int(path.stat().st_mtime),
        "snippets": snippets,
        "token_index": token_index,
    }


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw_frontmatter = text[3:end]
    body = text[end + len("\n---") :].lstrip("\n")
    data = yaml.safe_load(raw_frontmatter) or {}
    return data if isinstance(data, dict) else {}, body


def as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    else:
        items = [value]
    return [str(item).strip() for item in items if str(item).strip()]


def extract_snippets(text: str, limit: int = 3, max_chars: int = 260) -> list[str]:
    snippets: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = re.sub(r"^#{1,6}\s+", "", block.strip())
        block = re.sub(r"\s+", " ", block)
        if not block or len(block) < 20:
            continue
        snippets.append(block[:max_chars].rstrip())
        if len(snippets) >= limit:
            break
    return snippets


def wiki_index_path(root: Path) -> Path:
    return root / "indexes" / "wiki" / "index.json"


def write_index(root: Path, entries: list[dict[str, Any]]) -> Path:
    path = wiki_index_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_wiki_index(root: Path) -> list[dict[str, Any]]:
    path = wiki_index_path(root)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def find_wiki(
    root: Path,
    query: str,
    limit: int = 8,
    project_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    tokens = tokenize(query)
    scored = []
    for entry in load_wiki_index(root):
        entry = hydrate_entry(entry)
        score, matched_tokens = score_entry(entry, tokens, project_ids or [])
        if score:
            item = dict(entry)
            item["_score"] = score
            item["_matched_tokens"] = matched_tokens
            scored.append((score, item))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _score, entry in scored[:limit]]


def hydrate_entry(entry: dict[str, Any]) -> dict[str, Any]:
    item = dict(entry)
    path_value = item.get("path")
    if not path_value:
        return item
    path = Path(path_value)
    if not path.exists():
        return item
    text = path.read_text(encoding="utf-8", errors="ignore")
    frontmatter, body = parse_frontmatter(text)
    item["tags"] = as_string_list(frontmatter.get("tags")) or item.get("tags", [])
    item.setdefault("aliases", as_string_list(frontmatter.get("aliases")))
    item.setdefault("project_ids", as_string_list(frontmatter.get("projects") or frontmatter.get("project_ids")))
    item.setdefault("stack", as_string_list(frontmatter.get("stack")))
    item.setdefault("commands", as_string_list(frontmatter.get("commands")))
    item.setdefault("updated", str(frontmatter.get("updated", "") or ""))
    item.setdefault("mtime", int(path.stat().st_mtime))
    item.setdefault("snippets", extract_snippets(body))
    if "token_index" not in item:
        item["token_index"] = sorted(
            set(
                tokenize(
                    " ".join(
                        [
                            item.get("relative_path", ""),
                            item.get("title", ""),
                            " ".join(item.get("headings", [])),
                            " ".join(item.get("tags", [])),
                            " ".join(item.get("aliases", [])),
                            " ".join(item.get("project_ids", [])),
                            " ".join(item.get("stack", [])),
                            " ".join(item.get("commands", [])),
                            " ".join(item.get("snippets", [])),
                        ]
                    )
                )
            )
        )
    return item


def score_entry(entry: dict[str, Any], tokens: list[str], project_ids: list[str]) -> tuple[int, list[str]]:
    weighted_fields = [
        (entry.get("relative_path", ""), 4),
        (entry.get("title", ""), 5),
        (" ".join(entry.get("headings", [])), 3),
        (" ".join(entry.get("tags", [])), 6),
        (" ".join(entry.get("aliases", [])), 6),
        (" ".join(entry.get("project_ids", [])), 7),
        (" ".join(entry.get("stack", [])), 5),
        (" ".join(entry.get("commands", [])), 3),
        (" ".join(entry.get("snippets", [])), 2),
    ]
    score = 0
    matched: list[str] = []
    for token in tokens:
        token_score = sum(weight for value, weight in weighted_fields if token in str(value).lower())
        if token_score:
            score += token_score
            matched.append(token)
    project_matches = set(project_ids) & set(entry.get("project_ids", []))
    if project_matches:
        score += 10 * len(project_matches)
        matched.extend(sorted(project_matches))
    return score, matched


def tokenize(value: str) -> list[str]:
    return [token for token in re.split(r"\W+", value.lower()) if len(token) > 2]
