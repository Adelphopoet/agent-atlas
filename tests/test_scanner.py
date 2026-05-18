import subprocess
from pathlib import Path

from agent_atlas.config import AtlasConfig, CanonicalProject, DeprecatedProject, LlmWikiConfig, SafetyConfig
from agent_atlas.scanner import discover_repos, inspect_repo, suggest_wiki_links


def make_git_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=path, check=True, stdout=subprocess.DEVNULL)


def test_discover_repos_stays_inside_allowlist(tmp_path):
    allowed = tmp_path / "dev"
    outside = tmp_path / "outside"
    make_git_repo(allowed / "good")
    make_git_repo(outside / "bad")
    config = AtlasConfig(allowlisted_roots=[str(allowed)], llm_wiki=LlmWikiConfig(path=str(tmp_path / "md")))

    repos = discover_repos(config)

    assert repos == [(allowed / "good").resolve()]


def test_deprecated_and_canonical_rhetorica(tmp_path):
    root = tmp_path / "dev"
    old = root / "rhetorica"
    current = root / "dgdq" / "rhetorica"
    make_git_repo(old)
    make_git_repo(current)
    config = AtlasConfig(
        allowlisted_roots=[str(root)],
        llm_wiki=LlmWikiConfig(path=str(tmp_path / "md")),
        deprecated_projects=[DeprecatedProject(path=str(old), reason="old")],
        canonical_projects=[CanonicalProject(id="rhetorica", path=str(current), tags=["current"])],
        safety=SafetyConfig(),
    )

    current_project = inspect_repo(current, config, set())
    old_project = inspect_repo(old, config, {"rhetorica"})

    assert current_project["id"] == "rhetorica"
    assert current_project["canonical"] is True
    assert current_project["status"] == "active"
    assert old_project["status"] == "deprecated"
    assert old_project["id"] == "rhetorica-legacy"


def test_suggest_wiki_links_from_project_metadata():
    project = {"id": "agent-atlas", "name": "agent-atlas", "tags": ["agents"], "stack": ["python"]}
    wiki_entries = [
        {
            "relative_path": "agents/atlas.md",
            "title": "Agent Atlas",
            "aliases": [],
            "project_ids": ["agent-atlas"],
            "tags": ["agents"],
            "stack": ["python"],
        }
    ]

    assert suggest_wiki_links(project, wiki_entries) == ["agents/atlas.md"]
