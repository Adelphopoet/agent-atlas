from __future__ import annotations

from pathlib import Path

from agent_atlas.config import AtlasConfig, expand_path


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def is_allowlisted(path: Path, config: AtlasConfig) -> bool:
    resolved = path.expanduser().resolve()
    return any(is_within(resolved, expand_path(root)) for root in config.allowlisted_roots)


def is_never_scan(path: Path, config: AtlasConfig) -> bool:
    resolved = path.expanduser().resolve()
    return any(is_within(resolved, expand_path(root)) or resolved == expand_path(root) for root in config.safety.never_scan)


def should_ignore_dir(name: str, config: AtlasConfig) -> bool:
    return name in set(config.safety.ignored_dirs)
