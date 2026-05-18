# Agent Atlas Instructions

Agent Atlas is a local control plane for LLM coding agents. It is not a product-code repository and must not copy code from other repositories.

## Operating Rules

- Start with `atlas.yaml` and `projects/*.yaml`; do not scan the whole home directory.
- Treat `allowlisted_roots` as the hard boundary for local project discovery.
- Do not read or write outside allowlisted paths unless the user explicitly asks.
- Do not run destructive commands.
- For work in another repository, route first, explain the target repo, then present a plan before edits.
- After useful new information is discovered, propose updating the project manifest or the configured LLM Wiki path.

## Local Defaults

- Read local paths from `atlas.yaml`.
- `atlas.yaml`, generated manifests, and generated indexes are intentionally gitignored.

## Commands

- Install: `uv sync`
- Scan repos: `uv run atlas scan`
- Scan wiki: `uv run atlas wiki scan`
- List projects: `uv run atlas list`
- Route task: `uv run atlas route "..."`
- Test: `uv run pytest`
