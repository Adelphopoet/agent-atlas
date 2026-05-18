---
name: refresh-index
description: Refresh Agent Atlas project manifests, lightweight repo maps, and LLM Wiki markdown index.
---

# Refresh Index

Run these from the Agent Atlas repo:

```bash
uv run atlas scan
uv run atlas wiki scan
uv run atlas list
```

Generate repo maps only for projects relevant to the current task:

```bash
uv run atlas map <project_id>
```

Do not scan outside `allowlisted_roots`.
