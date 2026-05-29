from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.table import Table

from agent_atlas.config import AtlasConfig, LlmWikiConfig, expand_path, load_config, project_root, write_default_config
from agent_atlas.memory import MEMORY_KINDS, write_memory_note
from agent_atlas.registry import load_projects, validate_projects
from agent_atlas.repo_map import generate_repo_map
from agent_atlas.router import build_briefing, build_briefing_markdown, find_projects, route_task
from agent_atlas.scanner import scan
from agent_atlas.wiki import find_wiki, scan_wiki


app = typer.Typer(help="Agent Atlas local control plane.")
wiki_app = typer.Typer(help="LLM Wiki commands.")
app.add_typer(wiki_app, name="wiki")
console = Console()


@app.command()
def init(wizard: bool = typer.Option(False, "--wizard", help="Prompt for local paths.")) -> None:
    root = project_root()
    if wizard:
        write_wizard_config(root)
    else:
        write_default_config(root)
    for directory in ["projects", "indexes/repo-maps", "indexes/wiki", "skills"]:
        (root / directory).mkdir(parents=True, exist_ok=True)
    console.print(f"Initialized Agent Atlas at [bold]{root}[/bold]")


def scan_cmd() -> None:
    root = project_root()
    config = load_config(root)
    projects = scan(root, config)
    console.print(f"Scanned {len(projects)} repositories.")


app.command("scan")(scan_cmd)


@app.command("list")
def list_projects() -> None:
    root = project_root()
    projects = load_projects(root)
    table = Table(title="Agent Atlas Projects")
    for column in ["id", "status", "stack", "tags", "path", "last_scanned"]:
        table.add_column(column)
    for project in projects:
        table.add_row(
            project.get("id", ""),
            project.get("status", ""),
            ", ".join(project.get("stack", [])),
            ", ".join(project.get("tags", [])),
            project.get("path", ""),
            project.get("last_scanned", ""),
        )
    console.print(table)


@app.command()
def find(query: str) -> None:
    root = project_root()
    config = load_config(root)
    ranked = find_projects(load_projects(root, config), query)
    if not ranked:
        console.print("No matching projects.")
        return
    table = Table(title=f"Matches for: {query}")
    for column in ["score", "id", "status", "path", "why"]:
        table.add_column(column)
    for project in ranked[:20]:
        table.add_row(
            str(project["_score"]),
            project.get("id", ""),
            project.get("status", ""),
            project.get("path", ""),
            "; ".join(project.get("_reasons", [])),
        )
    console.print(table)


@app.command()
def route(
    task: str,
    json_output: bool = typer.Option(False, "--json", help="Print stable JSON for agents."),
    open_plan: bool = typer.Option(False, "--open-plan", help="Print a starter briefing for a planning pass."),
) -> None:
    root = project_root()
    config = load_config(root)
    result = route_task(root, load_projects(root, config), task, config.routing.max_secondary_repos, config)
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    primary = result["primary"]
    if not primary:
        console.print("No route found. Run `atlas scan` and `atlas wiki scan` first.")
        return
    if open_plan:
        print_open_plan(result)
        return
    console.print(f"[bold]Primary[/bold]: {primary['id']} ({primary['path']})")
    console.print(f"[bold]Why[/bold]: {'; '.join(primary.get('_reasons', []))}")
    if result["secondary"]:
        console.print("[bold]Secondary[/bold]: " + ", ".join(project["id"] for project in result["secondary"]))
    if result["repo_map"]:
        console.print(f"[bold]Repo map[/bold]: {result['repo_map']}")
    if result["wiki"]:
        console.print("[bold]Wiki[/bold]")
        for entry in result["wiki"][:5]:
            snippet = entry.get("snippets", [""])[0] if entry.get("snippets") else ""
            console.print(f"- {entry['relative_path']} :: {entry.get('title', '')}")
            if snippet:
                console.print(f"  {snippet}")
    console.print(f"[bold]Command[/bold]: {result['command']}")
    for note in result["safety_notes"]:
        console.print(f"- {note}")


@app.command()
def task(
    task: str,
    json_output: bool = typer.Option(False, "--json", help="Print stable JSON for agents."),
    no_write_memory: bool = typer.Option(False, "--no-write-memory", help="Do not write task memory candidates."),
) -> None:
    root = project_root()
    config = load_config(root)
    scan_wiki(root, config)
    result = route_task(root, load_projects(root, config), task, config.routing.max_secondary_repos, config)
    primary = result["primary"]
    if primary and not result["repo_map"]:
        generate_repo_map(root, primary, config)
        result = route_task(root, load_projects(root, config), task, config.routing.max_secondary_repos, config)
        primary = result["primary"]
    written_memory: list[str] = []
    if primary and config.memory.auto_write and not no_write_memory:
        for candidate in result.get("memory_candidates", []):
            if candidate.get("accepted"):
                path = write_memory_note(
                    root,
                    config,
                    task,
                    project_id=primary.get("id", ""),
                    kind=candidate.get("kind"),
                    source="atlas task",
                )
                written_memory.append(str(path))
        if written_memory:
            scan_wiki(root, config)
    result["written_memory"] = written_memory
    if json_output:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if not primary:
        console.print("No route found. Run `atlas scan` first.")
        return
    print_task_briefing(result)


@app.command()
def remember(
    text: str,
    project: str = typer.Option("", "--project", "-p", help="Project id for the wiki note."),
    kind: str | None = typer.Option(None, "--kind", help="Memory kind."),
) -> None:
    root = project_root()
    config = load_config(root)
    if kind and kind not in MEMORY_KINDS:
        raise typer.BadParameter(f"kind must be one of: {', '.join(MEMORY_KINDS)}")
    if project:
        projects = {item.get("id") for item in load_projects(root, config)}
        if project not in projects:
            raise typer.BadParameter(f"Unknown project: {project}")
    try:
        path = write_memory_note(root, config, text, project_id=project, kind=kind)
    except ValueError as exc:
        console.print(f"[yellow]Skipped[/yellow]: {exc}")
        raise typer.Exit(1)
    scan_wiki(root, config)
    console.print(f"Wrote memory note: [bold]{path}[/bold]")


@app.command("map")
def map_project(project_id: str) -> None:
    root = project_root()
    config = load_config(root)
    project = next((item for item in load_projects(root, config) if item.get("id") == project_id), None)
    if not project:
        raise typer.BadParameter(f"Unknown project: {project_id}")
    path = generate_repo_map(root, project, config)
    console.print(f"Wrote {path}")


@app.command()
def brief(project_id: str) -> None:
    root = project_root()
    config = load_config(root)
    project = get_project(root, config, project_id)
    repo_map = str(root / "indexes" / "repo-maps" / f"{project['id']}.md")
    if not Path(repo_map).exists():
        repo_map = ""
    wiki = find_wiki(root, project_id, limit=5, project_ids=[project_id])
    command = f"cd {project['path']} && codex"
    briefing = build_briefing(project, [], wiki, repo_map, command)
    console.print(build_briefing_markdown(briefing, wiki))


@app.command()
def handoff(task: str) -> None:
    root = project_root()
    config = load_config(root)
    result = route_task(root, load_projects(root, config), task, config.routing.max_secondary_repos, config)
    if not result["primary"]:
        console.print("No route found.")
        raise typer.Exit(1)
    console.print(result["briefing_markdown"])
    console.print("\n## Agent Rules")
    for note in result["safety_notes"]:
        console.print(f"- {note}")


@app.command()
def stale(days: int = typer.Option(14, "--days", help="Age threshold in days.")) -> None:
    root = project_root()
    now = datetime.now(timezone.utc)
    projects = []
    for project in load_projects(root):
        last_scanned = project.get("last_scanned", "")
        if not last_scanned:
            projects.append((project.get("id", ""), "never"))
            continue
        try:
            scanned_at = datetime.fromisoformat(last_scanned)
        except ValueError:
            projects.append((project.get("id", ""), last_scanned))
            continue
        if (now - scanned_at).days >= days:
            projects.append((project.get("id", ""), last_scanned))
    if not projects:
        console.print("No stale project manifests.")
        return
    table = Table(title=f"Stale projects ({days}+ days)")
    table.add_column("id")
    table.add_column("last_scanned")
    for project_id, last_scanned in projects:
        table.add_row(project_id, last_scanned)
    console.print(table)


@wiki_app.command("scan")
def wiki_scan() -> None:
    root = project_root()
    entries = scan_wiki(root, load_config(root))
    console.print(f"Indexed {len(entries)} wiki markdown files.")


@wiki_app.command("search")
def wiki_search(
    query: str,
    limit: int = typer.Option(8, "--limit", "-n", help="Maximum wiki notes to return."),
    json_output: bool = typer.Option(False, "--json", help="Print stable JSON for agents."),
) -> None:
    root = project_root()
    matches = find_wiki(root, query, limit=limit)
    if json_output:
        typer.echo(json.dumps(matches, ensure_ascii=False, indent=2))
        return
    if not matches:
        console.print("No matching wiki notes.")
        return
    for entry in matches:
        console.print(f"[bold]{entry['relative_path']}[/bold] :: {entry.get('title', '')}")
        for snippet in entry.get("snippets", [])[:2]:
            console.print(f"- {snippet}")


@app.command()
def doctor(fix: bool = typer.Option(False, "--fix", help="Create missing local directories.")) -> None:
    root = project_root()
    config = load_config(root)
    ok = True
    if shutil.which("git"):
        console.print("[green]ok[/green] git found")
    else:
        ok = False
        console.print("[red]fail[/red] git missing")
    for root_value in config.allowlisted_roots:
        path = expand_path(root_value)
        if fix and not path.exists():
            path.mkdir(parents=True, exist_ok=True)
        exists = path.exists()
        ok = ok and exists
        console.print(f"[{'green' if exists else 'red'}]{'ok' if exists else 'fail'}[/] allowlist root {path}")
    wiki_path = expand_path(config.llm_wiki.path)
    if fix and not wiki_path.exists():
        wiki_path.mkdir(parents=True, exist_ok=True)
    console.print(f"[{'green' if wiki_path.exists() else 'yellow'}]{'ok' if wiki_path.exists() else 'warn'}[/] wiki path {wiki_path}")
    for directory in ["projects", "indexes/repo-maps", "indexes/wiki", "skills"]:
        path = root / directory
        if fix:
            path.mkdir(parents=True, exist_ok=True)
        exists = path.exists()
        ok = ok and exists
        console.print(f"[{'green' if exists else 'red'}]{'ok' if exists else 'fail'}[/] local dir {path}")
    for error in validate_projects(root, config):
        ok = False
        console.print(f"[red]fail[/red] {error}")
    raise typer.Exit(0 if ok else 1)


def write_wizard_config(root: Path) -> Path:
    default_dev = str(Path.home() / "dev")
    default_wiki = str(Path.home() / "dev" / "md")
    allowlisted = typer.prompt("Allowlisted roots, comma-separated", default=default_dev)
    wiki_path = typer.prompt("LLM Wiki path", default=default_wiki)
    roots = [item.strip() for item in allowlisted.split(",") if item.strip()]
    config = AtlasConfig(allowlisted_roots=roots, llm_wiki=LlmWikiConfig(path=wiki_path))
    path = root / "atlas.yaml"
    if path.exists() and not typer.confirm(f"{path} exists. Overwrite?", default=False):
        return path
    path.write_text(yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def get_project(root: Path, config: AtlasConfig, project_id: str) -> dict:
    project = next((item for item in load_projects(root, config) if item.get("id") == project_id), None)
    if not project:
        raise typer.BadParameter(f"Unknown project: {project_id}")
    return project


def print_task_briefing(result: dict) -> None:
    primary = result["primary"]
    console.print(f"[bold]Task[/bold]: {result['task']}")
    console.print(f"[bold]Primary[/bold]: {primary['id']} ({primary['path']})")
    console.print(f"[bold]Why[/bold]: {'; '.join(primary.get('_reasons', [])) or 'best registry match'}")
    if result["secondary"]:
        console.print("[bold]Secondary[/bold]: " + ", ".join(project["id"] for project in result["secondary"]))
    if result["repo_map"]:
        console.print(f"[bold]Repo map[/bold]: {result['repo_map']}")
    if result["wiki"]:
        console.print("[bold]Wiki[/bold]")
        for entry in result["wiki"][:5]:
            console.print(f"- {entry['relative_path']} :: {entry.get('title', '')}")
    if result.get("written_memory"):
        console.print("[bold]Memory[/bold]: " + ", ".join(result["written_memory"]))
    console.print(f"[bold]Command[/bold]: {result['command']}")


def print_open_plan(result: dict) -> None:
    primary = result["primary"]
    console.print("# Atlas Route Briefing")
    for line in result["briefing"]:
        console.print(f"- {line}")
    if result["wiki"]:
        console.print("\n## Wiki Notes")
        for entry in result["wiki"][:5]:
            console.print(f"- {entry['relative_path']} :: {entry.get('title', '')}")
            for snippet in entry.get("snippets", [])[:2]:
                console.print(f"  {snippet}")
    console.print("\n## Safety")
    for note in result["safety_notes"]:
        console.print(f"- {note}")
    console.print(f"\n## Start\ncd {primary['path']} && codex")


if __name__ == "__main__":
    app()
