from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from agent_atlas.config import AtlasConfig, expand_path
from agent_atlas.registry import now_iso, save_project
from agent_atlas.safety import is_allowlisted, is_never_scan, should_ignore_dir
from agent_atlas.wiki import load_wiki_index, tokenize


STACK_FILES = {
    "package.json": "node",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "Cargo.toml": "rust",
    "go.mod": "go",
    "pom.xml": "java",
    "composer.json": "php",
    "Dockerfile": "docker",
    "dbt_project.yml": "dbt",
    "dags": "airflow",
}
AGENT_FILES = ["AGENTS.md", "CLAUDE.md", "README.md"]


def scan(root: Path, config: AtlasConfig) -> list[dict[str, Any]]:
    repos = discover_repos(config)
    wiki_entries = load_wiki_index(root)
    seen_ids: set[str] = set()
    projects = []
    for repo in repos:
        project = inspect_repo(repo, config, seen_ids)
        project["wiki_links"] = suggest_wiki_links(project, wiki_entries)
        seen_ids.add(project["id"])
        save_project(root, project)
        projects.append(project)
    return projects


def discover_repos(config: AtlasConfig) -> list[Path]:
    repos: list[Path] = []
    for root_value in config.allowlisted_roots:
        root = expand_path(root_value)
        if not root.exists() or is_never_scan(root, config):
            continue
        for current, dirs, _files in os_walk(root):
            current_path = Path(current)
            dirs[:] = sorted(d for d in dirs if not should_ignore_dir(d, config))
            dirs[:] = [d for d in dirs if not is_never_scan(current_path / d, config)]
            if (current_path / ".git").exists():
                repos.append(current_path.resolve())
                dirs[:] = []
    return sorted(set(repos))


def os_walk(root: Path):
    import os

    return os.walk(root)


def inspect_repo(repo: Path, config: AtlasConfig, seen_ids: set[str] | None = None) -> dict[str, Any]:
    if not is_allowlisted(repo, config):
        raise ValueError(f"Repository outside allowlist: {repo}")
    canonical = canonical_for(repo, config)
    deprecated = deprecated_for(repo, config)
    if canonical:
        project_id = canonical["id"]
    elif deprecated:
        project_id = make_legacy_project_id(repo, seen_ids or set())
    else:
        project_id = make_project_id(repo, config, seen_ids or set())
    tags = list(canonical.get("tags", [])) if canonical else []
    status = "deprecated" if deprecated else "active"
    top_level = top_level_files(repo, config)
    return {
        "id": project_id,
        "name": repo.name,
        "path": str(repo),
        "status": status,
        "canonical": bool(canonical),
        "stack": detect_stack(repo, top_level),
        "tags": tags,
        "notes": deprecated.get("reason", "") if deprecated else "",
        "wiki_links": [],
        "depends_on": [],
        "git": {
            "remote": git_output(repo, ["config", "--get", "remote.origin.url"]),
            "branch": git_output(repo, ["branch", "--show-current"]),
        },
        "agent_files": [name for name in AGENT_FILES if (repo / name).exists()],
        "top_level_files": top_level,
        "last_scanned": now_iso(),
    }


def canonical_for(repo: Path, config: AtlasConfig) -> dict[str, Any] | None:
    for item in config.canonical_projects:
        if repo.resolve() == expand_path(item.path):
            return item.model_dump()
    return None


def deprecated_for(repo: Path, config: AtlasConfig) -> dict[str, Any] | None:
    for item in config.deprecated_projects:
        if repo.resolve() == expand_path(item.path):
            return item.model_dump()
    return None


def make_project_id(repo: Path, config: AtlasConfig, seen_ids: set[str]) -> str:
    base = slug(repo.name)
    if base not in seen_ids:
        return base
    for root_value in config.allowlisted_roots:
        root = expand_path(root_value)
        try:
            rel = repo.resolve().relative_to(root)
            candidate = slug("-".join(rel.parts))
            if candidate not in seen_ids:
                return candidate
        except ValueError:
            continue
    suffix = 2
    while f"{base}-{suffix}" in seen_ids:
        suffix += 1
    return f"{base}-{suffix}"


def make_legacy_project_id(repo: Path, seen_ids: set[str]) -> str:
    base = slug(f"{repo.name}-legacy")
    if base not in seen_ids:
        return base
    suffix = 2
    while f"{base}-{suffix}" in seen_ids:
        suffix += 1
    return f"{base}-{suffix}"


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return value or "project"


def top_level_files(repo: Path, config: AtlasConfig) -> list[str]:
    names = []
    for child in sorted(repo.iterdir(), key=lambda item: item.name):
        if child.name == ".DS_Store":
            continue
        if should_ignore_dir(child.name, config):
            continue
        names.append(child.name + ("/" if child.is_dir() else ""))
    return names[:80]


def detect_stack(repo: Path, top_level: list[str]) -> list[str]:
    stack: list[str] = []
    normalized = {item.rstrip("/") for item in top_level}
    for marker, name in STACK_FILES.items():
        if marker in normalized and name not in stack:
            stack.append(name)
    return stack


def git_output(repo: Path, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        return result.stdout.strip()
    except OSError:
        return ""


def suggest_wiki_links(project: dict[str, Any], wiki_entries: list[dict[str, Any]], limit: int = 5) -> list[str]:
    project_terms = {
        project.get("id", "").lower(),
        project.get("name", "").lower(),
        *[str(tag).lower() for tag in project.get("tags", [])],
        *[str(item).lower() for item in project.get("stack", [])],
    }
    project_terms = {term for term in project_terms if term}
    scored: list[tuple[int, str]] = []
    for entry in wiki_entries:
        score = 0
        entry_projects = {str(item).lower() for item in entry.get("project_ids", [])}
        entry_tags = {str(item).lower() for item in entry.get("tags", [])}
        entry_stack = {str(item).lower() for item in entry.get("stack", [])}
        score += 10 * len(project_terms & entry_projects)
        score += 4 * len(project_terms & entry_tags)
        score += 3 * len(project_terms & entry_stack)
        haystack = " ".join(
            [
                entry.get("relative_path", ""),
                entry.get("title", ""),
                " ".join(entry.get("aliases", [])),
            ]
        ).lower()
        score += sum(1 for token in tokenize(" ".join(project_terms)) if token in haystack)
        if score:
            scored.append((score, entry["relative_path"]))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [path for _score, path in scored[:limit]]
