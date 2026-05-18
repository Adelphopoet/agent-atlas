# Agent Atlas

Local control plane for LLM coding agents. Atlas keeps a registry of local repos, indexes your LLM Wiki, and routes natural-language tasks to the right project.

It does not copy product code, call LLM APIs, run MCP servers, or start agents automatically in v0.

## Quickstart

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

## V1: MCP Server

V1 can expose Atlas as an MCP server with read-only tools:

- `atlas.find_projects`
- `atlas.get_manifest`
- `atlas.get_repo_map`
- `atlas.search_wiki`
- `atlas.route_task`

Keep it allowlist-only. Do not expose shell execution until the safety model is boring and explicit.
