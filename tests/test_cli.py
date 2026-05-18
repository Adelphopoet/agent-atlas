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
