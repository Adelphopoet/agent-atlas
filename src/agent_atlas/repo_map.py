from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent_atlas.config import AtlasConfig
from agent_atlas.safety import should_ignore_dir


IMPORTANT_NAMES = {
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "Dockerfile",
    "dbt_project.yml",
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
}
IMPORTANT_PARTS = ("route", "controller", "service", "test", "spec", "model", "schema", "dag")


def generate_repo_map(root: Path, project: dict[str, Any], config: AtlasConfig) -> Path:
    repo = Path(project["path"])
    lines = [f"# Repo Map: {project['id']}", "", f"Path: `{repo}`", ""]
    lines += ["## Top Level", *[f"- {item}" for item in project.get("top_level_files", [])], ""]
    important = important_files(repo, config)
    lines += ["## Important Files", *[f"- {path}" for path in important[:120]], ""]
    commands = read_commands(repo)
    if commands:
        lines += ["## Commands", *[f"- `{cmd}`" for cmd in commands], ""]
    out = root / "indexes" / "repo-maps" / f"{project['id']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def important_files(repo: Path, config: AtlasConfig) -> list[str]:
    results: list[str] = []
    for current, dirs, files in repo_walk(repo):
        current_path = Path(current)
        rel_dir = current_path.relative_to(repo)
        depth = 0 if str(rel_dir) == "." else len(rel_dir.parts)
        dirs[:] = sorted(d for d in dirs if not should_ignore_dir(d, config))
        if depth > 3:
            dirs[:] = []
        for name in sorted(files):
            rel = current_path.joinpath(name).relative_to(repo)
            lower = name.lower()
            if name in IMPORTANT_NAMES or any(part in lower for part in IMPORTANT_PARTS):
                results.append(str(rel))
    return results


def repo_walk(repo: Path):
    import os

    return os.walk(repo)


def read_commands(repo: Path) -> list[str]:
    commands: list[str] = []
    package = repo / "package.json"
    if package.exists():
        try:
            scripts = json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
            commands.extend(f"npm run {name}" for name in sorted(scripts))
        except json.JSONDecodeError:
            pass
    pyproject = repo / "pyproject.toml"
    if pyproject.exists():
        commands.append("uv sync")
        commands.append("uv run pytest")
    return commands
