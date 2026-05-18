from pathlib import Path

from agent_atlas.config import AtlasConfig, LlmWikiConfig
from agent_atlas.router import find_projects, route_task
from agent_atlas.wiki import scan_wiki


def test_route_prefers_canonical_active_rhetorica(tmp_path):
    legacy_path = str(tmp_path / "dev" / "rhetorica")
    current_path = str(tmp_path / "dev" / "dgdq" / "rhetorica")
    projects = [
        {
            "id": "rhetorica-legacy",
            "name": "rhetorica",
            "path": legacy_path,
            "status": "deprecated",
            "canonical": False,
            "tags": ["rhetorica"],
            "stack": ["python"],
            "notes": "old open-source version",
            "wiki_links": [],
            "agent_files": ["README.md"],
        },
        {
            "id": "rhetorica",
            "name": "rhetorica",
            "path": current_path,
            "status": "active",
            "canonical": True,
            "tags": ["rhetorica", "current"],
            "stack": ["python"],
            "notes": "",
            "wiki_links": [],
            "agent_files": ["AGENTS.md"],
        },
    ]

    result = route_task(Path(tmp_path), projects, "rhetorica python task")

    assert result["primary"]["id"] == "rhetorica"
    assert result["command"] == f"cd {current_path} && codex"
    assert result["primary"]["_reasons"]


def test_find_explains_match():
    projects = [
        {
            "id": "dbt-greenplum",
            "name": "dbt-greenplum",
            "path": "/dev/dbt-greenplum",
            "status": "active",
            "canonical": False,
            "tags": ["dbt"],
            "stack": ["python"],
            "notes": "greenplum adapter",
            "wiki_links": ["dbt/run.md"],
            "agent_files": [],
        }
    ]

    matches = find_projects(projects, "dbt run")

    assert matches[0]["id"] == "dbt-greenplum"
    assert "tag match: dbt" in matches[0]["_reasons"]


def test_route_filters_projects_outside_allowlist(tmp_path):
    allowed = tmp_path / "dev"
    outside = tmp_path / "outside"
    config = AtlasConfig(allowlisted_roots=[str(allowed)], llm_wiki=LlmWikiConfig(path=str(tmp_path / "md")))
    projects = [
        {
            "id": "outside",
            "name": "outside",
            "path": str(outside / "repo"),
            "status": "active",
            "canonical": False,
            "tags": ["target"],
            "stack": [],
            "notes": "",
            "wiki_links": [],
            "agent_files": [],
        }
    ]

    result = route_task(tmp_path, projects, "target task", config=config)

    assert result["primary"] is None
    assert result["command"] == ""


def test_route_returns_wiki_snippet_for_fake_repo(tmp_path):
    wiki = tmp_path / "md"
    wiki.mkdir()
    (wiki / "fake.md").write_text(
        """---
tags: [fake, python]
projects: [fake-repo]
---
# Fake Repo Runbook

Check the fake repo manifest and run the focused test suite before edits.
""",
        encoding="utf-8",
    )
    config = AtlasConfig(allowlisted_roots=[str(tmp_path / "dev")], llm_wiki=LlmWikiConfig(path=str(wiki)))
    scan_wiki(tmp_path, config)
    projects = [
        {
            "id": "fake-repo",
            "name": "fake-repo",
            "path": str(tmp_path / "dev" / "fake-repo"),
            "status": "active",
            "canonical": False,
            "tags": ["fake"],
            "stack": ["python"],
            "notes": "",
            "wiki_links": [],
            "agent_files": ["AGENTS.md"],
        }
    ]

    result = route_task(tmp_path, projects, "fix fake python task", config=config)

    assert result["primary"]["id"] == "fake-repo"
    assert result["wiki"][0]["relative_path"] == "fake.md"
    assert result["wiki"][0]["snippets"][0] == "Check the fake repo manifest and run the focused test suite before edits."
    assert result["briefing"]
