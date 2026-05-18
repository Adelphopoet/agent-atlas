from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from agent_atlas.config import expand_path, load_config, project_root, write_default_config
from agent_atlas.registry import load_projects, validate_projects
from agent_atlas.repo_map import generate_repo_map
from agent_atlas.router import find_projects, route_task
from agent_atlas.scanner import scan
from agent_atlas.wiki import find_wiki, scan_wiki


app = typer.Typer(help="Agent Atlas local control plane.")
wiki_app = typer.Typer(help="LLM Wiki commands.")
app.add_typer(wiki_app, name="wiki")
console = Console()


@app.command()
def init() -> None:
    root = project_root()
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


@app.command("map")
def map_project(project_id: str) -> None:
    root = project_root()
    config = load_config(root)
    project = next((item for item in load_projects(root, config) if item.get("id") == project_id), None)
    if not project:
        raise typer.BadParameter(f"Unknown project: {project_id}")
    path = generate_repo_map(root, project, config)
    console.print(f"Wrote {path}")


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
def doctor() -> None:
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
        exists = path.exists()
        ok = ok and exists
        console.print(f"[{'green' if exists else 'red'}]{'ok' if exists else 'fail'}[/] allowlist root {path}")
    wiki_path = expand_path(config.llm_wiki.path)
    console.print(f"[{'green' if wiki_path.exists() else 'yellow'}]{'ok' if wiki_path.exists() else 'warn'}[/] wiki path {wiki_path}")
    for error in validate_projects(root, config):
        ok = False
        console.print(f"[red]fail[/red] {error}")
    raise typer.Exit(0 if ok else 1)


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
