from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agent_atlas.config import AtlasConfig
from agent_atlas.memory import build_memory_candidates
from agent_atlas.safety import is_allowlisted
from agent_atlas.wiki import find_wiki, hydrate_entry, load_wiki_index


def find_projects(projects: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    ranked = []
    for project in projects:
        score, reasons = score_project(project, query)
        if score > 0:
            item = dict(project)
            item["_score"] = score
            item["_reasons"] = reasons
            ranked.append(item)
    ranked.sort(key=lambda item: (item["_score"], bool(item.get("canonical"))), reverse=True)
    return ranked


def route_task(
    root: Path,
    projects: list[dict[str, Any]],
    task: str,
    max_secondary: int = 3,
    config: AtlasConfig | None = None,
) -> dict[str, Any]:
    safe_projects = filter_safe_projects(projects, config)
    ranked = find_projects(safe_projects, task)
    active = [project for project in ranked if project.get("status") != "deprecated"]
    primary = active[0] if active else (ranked[0] if ranked else None)
    secondaries = [project for project in active if primary and project["id"] != primary["id"]][:max_secondary]
    wiki = route_wiki(root, task, primary) if primary else []
    repo_map = repo_map_path(root, primary) if primary else ""
    command = f"cd {primary['path']} && codex" if primary else ""
    briefing = build_briefing(primary, secondaries, wiki, repo_map, command) if primary else []
    primary_id = primary.get("id", "") if primary else ""
    return {
        "task": task,
        "primary": primary,
        "secondary": secondaries,
        "wiki": wiki,
        "repo_map": repo_map,
        "command": command,
        "next_command": command,
        "briefing": briefing,
        "briefing_markdown": build_briefing_markdown(briefing, wiki),
        "memory_candidates": build_memory_candidates(task, config, project_id=primary_id) if config else [],
        "safety_notes": [
            "Atlas does not start agents automatically.",
            "Route first, inspect the target repo, then present a plan before edits.",
            "Do not read or write outside allowlisted roots unless the user explicitly asks.",
        ],
    }


def score_project(project: dict[str, Any], query: str) -> tuple[int, list[str]]:
    query_l = query.lower()
    tokens = tokenize(query_l)
    score = 0
    reasons: list[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        if reason not in reasons:
            reasons.append(reason)

    tags = [str(tag).lower() for tag in project.get("tags", [])]
    stack = [str(item).lower() for item in project.get("stack", [])]
    wiki_links = [str(item).lower() for item in project.get("wiki_links", [])]
    fields = {
        "id/path/name": " ".join([project.get("id", ""), project.get("name", ""), project.get("path", "")]).lower(),
        "notes": str(project.get("notes", "")).lower(),
        "wiki_links": " ".join(wiki_links),
    }

    for token in tokens:
        if token in tags:
            add(10, f"tag match: {token}")
        if token in stack:
            add(6, f"stack match: {token}")
        for label, haystack in fields.items():
            if token and token in haystack:
                add(4 if label != "id/path/name" else 5, f"{label} match: {token}")
        for link in wiki_links:
            if token and token in link:
                add(4, f"wiki link match: {token}")

    for tag in tags:
        if tag and tag in query_l:
            add(5, f"tag substring: {tag}")

    matched_score = score
    if matched_score > 0 and project.get("agent_files"):
        add(1, "has agent/readme files")
    if matched_score > 0 and project.get("canonical"):
        add(5, "canonical project")
    if project.get("status") == "deprecated":
        score -= 50
        if matched_score > 0:
            reasons.append("deprecated project")

    return max(score, 0), reasons


def tokenize(value: str) -> list[str]:
    return [token for token in re.split(r"\W+", value.lower()) if len(token) > 2]


def filter_safe_projects(projects: list[dict[str, Any]], config: AtlasConfig | None) -> list[dict[str, Any]]:
    if not config:
        return projects
    return [project for project in projects if is_allowlisted(Path(project.get("path", "")), config)]


def route_wiki(root: Path, task: str, primary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not primary:
        return []
    query = " ".join(
        [
            task,
            primary.get("id", ""),
            primary.get("name", ""),
            " ".join(primary.get("tags", [])),
            " ".join(primary.get("stack", [])),
        ]
    )
    wiki = find_wiki(root, query, limit=8, project_ids=[primary.get("id", "")])
    linked = linked_wiki_entries(root, primary)
    seen = {entry.get("relative_path") for entry in linked}
    linked.extend(entry for entry in wiki if entry.get("relative_path") not in seen)
    return linked[:8]


def linked_wiki_entries(root: Path, project: dict[str, Any]) -> list[dict[str, Any]]:
    links = set(project.get("wiki_links", []))
    if not links:
        return []
    entries = []
    for entry in load_wiki_index(root):
        if entry.get("relative_path") in links:
            item = hydrate_entry(entry)
            item["_score"] = 999
            item["_matched_tokens"] = [project.get("id", "")]
            entries.append(item)
    return entries


def repo_map_path(root: Path, primary: dict[str, Any]) -> str:
    path = root / "indexes" / "repo-maps" / f"{primary['id']}.md"
    return str(path) if path.exists() else ""


def build_briefing(
    primary: dict[str, Any],
    secondaries: list[dict[str, Any]],
    wiki: list[dict[str, Any]],
    repo_map: str,
    command: str,
) -> list[str]:
    lines = [
        f"Target repo: {primary['id']} ({primary['path']})",
        f"Why: {'; '.join(primary.get('_reasons', [])) or 'best registry match'}",
    ]
    if secondaries:
        lines.append("Secondary repos: " + ", ".join(project["id"] for project in secondaries))
    if repo_map:
        lines.append(f"Repo map: {repo_map}")
    if wiki:
        lines.append("Read wiki notes: " + ", ".join(entry["relative_path"] for entry in wiki[:5]))
    lines.append(f"Next command: {command}")
    return lines


def build_briefing_markdown(briefing: list[str], wiki: list[dict[str, Any]]) -> str:
    if not briefing:
        return ""
    lines = ["# Atlas Briefing", ""]
    lines.extend(f"- {line}" for line in briefing)
    if wiki:
        lines.extend(["", "## Wiki Notes"])
        for entry in wiki[:5]:
            lines.append(f"- `{entry['relative_path']}` :: {entry.get('title', '')}")
    return "\n".join(lines)
