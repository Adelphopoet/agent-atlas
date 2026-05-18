from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


CONFIG_FILE = "atlas.yaml"


def default_dev_root() -> str:
    return str(Path.home() / "dev")


def default_wiki_path() -> str:
    return str(Path.home() / "dev" / "md")


class LlmWikiConfig(BaseModel):
    path: str = Field(default_factory=default_wiki_path)
    index_markdown: bool = True


class DeprecatedProject(BaseModel):
    path: str
    reason: str = ""


class CanonicalProject(BaseModel):
    id: str
    path: str
    tags: list[str] = Field(default_factory=list)


class RoutingConfig(BaseModel):
    max_secondary_repos: int = 3
    prefer_repos_with_agent_files: bool = True


class SafetyConfig(BaseModel):
    ignored_dirs: list[str] = Field(
        default_factory=lambda: [
            "node_modules",
            ".venv",
            "venv",
            "dist",
            "build",
            ".next",
            ".turbo",
            ".git",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".pnpm-store",
        ]
    )
    never_scan: list[str] = Field(default_factory=list)


ProjectStatus = Literal["active", "deprecated", "archived"]


class ProjectManifest(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str = ""
    path: str
    status: ProjectStatus = "active"
    canonical: bool = False
    stack: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""
    wiki_links: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    git: dict[str, str] = Field(default_factory=dict)
    agent_files: list[str] = Field(default_factory=list)
    top_level_files: list[str] = Field(default_factory=list)
    last_scanned: str = ""

    @field_validator("id", "path")
    @classmethod
    def required_string(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("stack", "tags", "wiki_links", "depends_on", "agent_files", "top_level_files")
    @classmethod
    def clean_string_list(cls, values: list[str]) -> list[str]:
        cleaned = [str(value).strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("must not contain empty strings")
        return cleaned


class AtlasConfig(BaseModel):
    name: str = "Agent Atlas"
    version: str = "0.1.0"
    allowlisted_roots: list[str] = Field(default_factory=lambda: [default_dev_root()])
    llm_wiki: LlmWikiConfig = Field(default_factory=LlmWikiConfig)
    deprecated_projects: list[DeprecatedProject] = Field(default_factory=list)
    canonical_projects: list[CanonicalProject] = Field(default_factory=list)
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)


def project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / CONFIG_FILE).exists() or (candidate / ".git").exists():
            return candidate
    return current


def expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def load_config(root: Path | None = None) -> AtlasConfig:
    root = root or project_root()
    path = root / CONFIG_FILE
    if not path.exists():
        return AtlasConfig()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AtlasConfig.model_validate(data)


def write_default_config(root: Path) -> Path:
    path = root / CONFIG_FILE
    if path.exists():
        return path
    dev_root = Path.home() / "dev"
    data: dict[str, Any] = AtlasConfig(
        deprecated_projects=[
            DeprecatedProject(
                path=str(dev_root / "rhetorica"),
                reason=f"Old open-source version. Use {dev_root / 'dgdq' / 'rhetorica'}.",
            )
        ],
        canonical_projects=[
            CanonicalProject(
                id="rhetorica",
                path=str(dev_root / "dgdq" / "rhetorica"),
                tags=["rhetorica", "current"],
            )
        ],
    ).model_dump(mode="json")
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path
