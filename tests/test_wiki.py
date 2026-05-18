from agent_atlas.config import AtlasConfig, LlmWikiConfig
from agent_atlas.wiki import find_wiki, scan_wiki


def test_wiki_scan_indexes_markdown(tmp_path):
    wiki = tmp_path / "md"
    wiki.mkdir()
    (wiki / "dbt.md").write_text(
        "---\ntags: [dbt, run]\n---\n# DBT Run\n\n## Vars\n\nUse vars to pass runtime parameters into dbt commands.\n",
        encoding="utf-8",
    )
    config = AtlasConfig(allowlisted_roots=[str(tmp_path / "dev")], llm_wiki=LlmWikiConfig(path=str(wiki)))

    entries = scan_wiki(tmp_path, config)
    matches = find_wiki(tmp_path, "dbt vars")

    assert entries[0]["title"] == "DBT Run"
    assert entries[0]["tags"] == ["dbt", "run"]
    assert entries[0]["snippets"]
    assert matches[0]["relative_path"] == "dbt.md"


def test_wiki_scan_reads_yaml_block_frontmatter(tmp_path):
    wiki = tmp_path / "md"
    wiki.mkdir()
    (wiki / "app.md").write_text(
        """---
tags:
  - python
  - agents
aliases:
  - atlas start
projects:
  - agent-atlas
commands:
  - uv run pytest
---
# Agent Atlas

## Start

Use Atlas as the first routing step before opening a product repo.
""",
        encoding="utf-8",
    )
    config = AtlasConfig(allowlisted_roots=[str(tmp_path / "dev")], llm_wiki=LlmWikiConfig(path=str(wiki)))

    entries = scan_wiki(tmp_path, config)
    matches = find_wiki(tmp_path, "atlas routing pytest", project_ids=["agent-atlas"])

    assert entries[0]["tags"] == ["python", "agents"]
    assert entries[0]["aliases"] == ["atlas start"]
    assert entries[0]["project_ids"] == ["agent-atlas"]
    assert entries[0]["commands"] == ["uv run pytest"]
    assert "routing" in entries[0]["token_index"]
    assert matches[0]["relative_path"] == "app.md"
    assert matches[0]["snippets"][0] == "Use Atlas as the first routing step before opening a product repo."
