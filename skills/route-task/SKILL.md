---
name: route-task
description: Route a natural-language coding task to the right local repository using Agent Atlas registry and wiki indexes.
---

# Route Task

1. Read `atlas.yaml`.
2. Read `projects/*.yaml`.
3. Search by id, path, tags, stack, notes, and wiki links.
4. Prefer canonical active projects over deprecated projects.
5. Check `indexes/wiki/index.json` for relevant notes.
6. Return primary repo, secondary repos, relevant wiki files, reason, risks, and a command like `cd <repo_path> && codex`.
7. Do not start another agent automatically.
