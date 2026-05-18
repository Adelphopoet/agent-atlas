import pytest
import yaml

from agent_atlas.config import AtlasConfig, LlmWikiConfig
from agent_atlas.registry import load_projects, merge_manifest, validate_projects


def test_merge_preserves_manual_fields():
    existing = {
        "id": "demo",
        "tags": ["manual"],
        "notes": "keep this",
        "wiki_links": ["wiki/demo.md"],
        "depends_on": ["core"],
        "status": "active",
    }
    discovered = {
        "id": "demo",
        "tags": ["auto"],
        "notes": "",
        "wiki_links": [],
        "depends_on": [],
        "status": "deprecated",
        "path": "/tmp/demo",
    }

    merged = merge_manifest(existing, discovered)

    assert merged["tags"] == ["manual"]
    assert merged["notes"] == "keep this"
    assert merged["wiki_links"] == ["wiki/demo.md"]
    assert merged["depends_on"] == ["core"]
    assert merged["status"] == "active"
    assert merged["path"] == "/tmp/demo"


def test_load_projects_rejects_outside_allowlist(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "outside.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "outside",
                "name": "outside",
                "path": str(tmp_path / "outside" / "repo"),
                "status": "active",
            }
        ),
        encoding="utf-8",
    )
    config = AtlasConfig(allowlisted_roots=[str(tmp_path / "dev")], llm_wiki=LlmWikiConfig(path=str(tmp_path / "md")))

    with pytest.raises(ValueError, match="outside allowlist"):
        load_projects(tmp_path, config)

    assert validate_projects(tmp_path, config)


def test_project_manifest_rejects_unknown_status(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "bad.yaml").write_text(
        yaml.safe_dump({"id": "bad", "name": "bad", "path": str(tmp_path / "dev" / "bad"), "status": "weird"}),
        encoding="utf-8",
    )
    config = AtlasConfig(allowlisted_roots=[str(tmp_path / "dev")], llm_wiki=LlmWikiConfig(path=str(tmp_path / "md")))

    errors = validate_projects(tmp_path, config)

    assert errors
    assert "weird" in errors[0]
