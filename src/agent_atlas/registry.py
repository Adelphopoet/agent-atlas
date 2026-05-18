from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agent_atlas.config import AtlasConfig, ProjectManifest, expand_path
from agent_atlas.safety import is_allowlisted


MANUAL_FIELDS = {"tags", "notes", "wiki_links", "depends_on", "status", "canonical"}


def manifests_dir(root: Path) -> Path:
    return root / "projects"


def load_project(path: Path, config: AtlasConfig | None = None) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    project = ProjectManifest.model_validate(data).model_dump(mode="json")
    if config and not is_allowlisted(Path(project["path"]), config):
        raise ValueError(f"Project outside allowlist: {project['id']} {project['path']}")
    return project


def load_projects(root: Path, config: AtlasConfig | None = None) -> list[dict[str, Any]]:
    directory = manifests_dir(root)
    if not directory.exists():
        return []
    projects: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        data = load_project(path, config)
        if data:
            projects.append(data)
    return projects


def validate_projects(root: Path, config: AtlasConfig) -> list[str]:
    errors: list[str] = []
    directory = manifests_dir(root)
    if not directory.exists():
        return errors
    wiki_root = expand_path(config.llm_wiki.path)
    for path in sorted(directory.glob("*.yaml")):
        try:
            project = load_project(path)
        except (ValidationError, ValueError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if not is_allowlisted(Path(project["path"]), config):
            errors.append(f"{path.name}: project outside allowlist: {project['path']}")
        for link in project.get("wiki_links", []):
            link_path = Path(link)
            if link_path.is_absolute():
                errors.append(f"{path.name}: wiki link must be relative: {link}")
            elif not (wiki_root / link).exists():
                errors.append(f"{path.name}: wiki link not found: {link}")
    return errors


def merge_manifest(existing: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in discovered.items():
        if key in MANUAL_FIELDS and key in existing and existing[key]:
            continue
        merged[key] = value
    for key in MANUAL_FIELDS:
        merged.setdefault(key, [] if key in {"tags", "wiki_links", "depends_on"} else "")
    merged["last_scanned"] = discovered.get("last_scanned") or now_iso()
    return merged


def save_project(root: Path, project: dict[str, Any]) -> Path:
    directory = manifests_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{project['id']}.yaml"
    merged = merge_manifest(load_project(path), project)
    path.write_text(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
