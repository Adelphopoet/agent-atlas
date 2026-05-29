# Agent Atlas

Local control plane for LLM coding agents. Atlas keeps a registry of local repos, indexes your LLM Wiki, and routes natural-language tasks to the right project.

It does not copy product code, call LLM APIs, run MCP servers, or start agents automatically in v0.

## Quickstart

Install from GitHub:

```bash
uv tool install git+https://github.com/Adelphopoet/agent-atlas.git
atlas init --wizard
atlas doctor --fix
atlas scan
atlas task "добавить проверку качества в rhetorica"
```

For local development:

```bash
uv sync
uv run atlas init
uv run atlas scan
uv run atlas wiki scan
uv run atlas list
uv run atlas route "добавить проверку качества в rhetorica"
```

## Local Config

`atlas.yaml` is intentionally ignored by git because it contains local paths and repository metadata. Commit `atlas.example.yaml`, keep your real `atlas.yaml` private.

## Main CLI

- `atlas task "..."` routes a natural-language task, refreshes the wiki index, creates a repo map when needed, and prints the agent handoff command.
- `atlas route "..." --json` is the stable agent-facing routing contract.
- `atlas remember "..." --project <id> --kind runbook` writes durable knowledge into the configured LLM Wiki after filtering secrets and disposable noise.
- `atlas brief <project_id>` prints a short repo briefing.
- `atlas handoff "..."` prints a markdown prompt for another coding agent.
- `atlas stale` shows manifests that need a fresh scan.

## Later: MCP Server

Atlas can later expose a read-only MCP server:

- `atlas.find_projects`
- `atlas.get_manifest`
- `atlas.get_repo_map`
- `atlas.search_wiki`
- `atlas.route_task`

Keep it allowlist-only. Do not expose shell execution until the safety model is boring and explicit.
