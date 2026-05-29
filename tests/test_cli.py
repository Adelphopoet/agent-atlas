import json

import yaml
from typer.testing import CliRunner

from agent_atlas.cli import app
from agent_atlas.config import AtlasConfig, LlmWikiConfig
from agent_atlas.wiki import scan_wiki


def test_route_json_contract(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dev = tmp_path / "dev"
    repo = dev / "agent-atlas"
    repo.mkdir(parents=True)
    wiki = tmp_path / "md"
    wiki.mkdir()
    (wiki / "agent-atlas.md").write_text(
        """---
tags: [agents, python]
projects: [agent-atlas]
---
# Agent Atlas

Use this note to route agent work before opening another repository.
""",
        encoding="utf-8",
    )
    config = AtlasConfig(allowlisted_roots=[str(dev)], llm_wiki=LlmWikiConfig(path=str(wiki)))
    (tmp_path / "atlas.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json")), encoding="utf-8")
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "agent-atlas.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "agent-atlas",
                "name": "agent-atlas",
                "path": str(repo),
                "status": "active",
                "canonical": False,
                "tags": ["agents"],
                "stack": ["python"],
                "notes": "",
                "wiki_links": ["agent-atlas.md"],
                "depends_on": [],
                "agent_files": ["AGENTS.md"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    scan_wiki(tmp_path, config)

    result = CliRunner().invoke(app, ["route", "agent atlas python", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["task"] == "agent atlas python"
    assert payload["primary"]["id"] == "agent-atlas"
    assert payload["next_command"] == f"cd {repo} && codex"
    assert payload["wiki"][0]["relative_path"] == "agent-atlas.md"
    assert payload["wiki"][0]["snippets"][0] == "Use this note to route agent work before opening another repository."
    assert "safety_notes" in payload
    assert "briefing_markdown" in payload
    assert "memory_candidates" in payload


def test_task_json_generates_repo_map(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dev = tmp_path / "dev"
    repo = dev / "fake-repo"
    repo.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[project]\nname = \"fake-repo\"\n", encoding="utf-8")
    wiki = tmp_path / "md"
    wiki.mkdir()
    config = AtlasConfig(allowlisted_roots=[str(dev)], llm_wiki=LlmWikiConfig(path=str(wiki)))
    (tmp_path / "atlas.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json")), encoding="utf-8")
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "fake-repo.yaml").write_text(
        yaml.safe_dump(
            {
                "id": "fake-repo",
                "name": "fake-repo",
                "path": str(repo),
                "status": "active",
                "canonical": False,
                "tags": ["fake"],
                "stack": ["python"],
                "notes": "",
                "wiki_links": [],
                "depends_on": [],
                "agent_files": ["README.md"],
                "top_level_files": ["pyproject.toml"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(app, ["task", "fix fake python task", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["primary"]["id"] == "fake-repo"
    assert payload["repo_map"].endswith("indexes/repo-maps/fake-repo.md")
    assert (tmp_path / "indexes" / "repo-maps" / "fake-repo.md").exists()
    assert payload["next_command"] == f"cd {repo} && codex"


def test_init_wizard_writes_local_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dev = tmp_path / "dev"
    wiki = tmp_path / "wiki"

    result = CliRunner().invoke(app, ["init", "--wizard"], input=f"{dev}\n{wiki}\n")

    assert result.exit_code == 0
    config = yaml.safe_load((tmp_path / "atlas.yaml").read_text(encoding="utf-8"))
    assert config["allowlisted_roots"] == [str(dev)]
    assert config["llm_wiki"]["path"] == str(wiki)
    assert (tmp_path / "projects").exists()
    assert (tmp_path / "indexes" / "repo-maps").exists()


def test_remember_writes_wiki_note(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    dev = tmp_path / "dev"
    repo = dev / "fake-repo"
    repo.mkdir(parents=True)
    wiki = tmp_path / "md"
    wiki.mkdir()
    config = AtlasConfig(allowlisted_roots=[str(dev)], llm_wiki=LlmWikiConfig(path=str(wiki)))
    (tmp_path / "atlas.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json")), encoding="utf-8")
    projects = tmp_path / "projects"
    projects.mkdir()
    (projects / "fake-repo.yaml").write_text(
        yaml.safe_dump({"id": "fake-repo", "name": "fake-repo", "path": str(repo), "status": "active"}),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        app,
        [
            "remember",
            "Use `uv run pytest` before changing Agent Atlas routing code.",
            "--project",
            "fake-repo",
            "--kind",
            "runbook",
        ],
    )

    assert result.exit_code == 0
    notes = list((wiki / "atlas-memory" / "fake-repo").glob("*.md"))
    assert len(notes) == 1
    text = notes[0].read_text(encoding="utf-8")
    assert "kind: runbook" in text
    assert "projects:" in text
    assert "fake-repo" in text


def test_remember_rejects_secret_like_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wiki = tmp_path / "md"
    wiki.mkdir()
    config = AtlasConfig(allowlisted_roots=[str(tmp_path / "dev")], llm_wiki=LlmWikiConfig(path=str(wiki)))
    (tmp_path / "atlas.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json")), encoding="utf-8")

    result = CliRunner().invoke(app, ["remember", "Use password=super-secret for local debug.", "--kind", "runbook"])

    assert result.exit_code == 1
    assert not list(wiki.rglob("*.md"))


def test_remember_rejects_disposable_noise(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    wiki = tmp_path / "md"
    wiki.mkdir()
    config = AtlasConfig(allowlisted_roots=[str(tmp_path / "dev")], llm_wiki=LlmWikiConfig(path=str(wiki)))
    (tmp_path / "atlas.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json")), encoding="utf-8")

    result = CliRunner().invoke(app, ["remember", "ok", "--kind", "insight"])

    assert result.exit_code == 1
    assert not list(wiki.rglob("*.md"))
