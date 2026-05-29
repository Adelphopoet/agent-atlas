from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agent_atlas.config import AtlasConfig, expand_path


MEMORY_KINDS = ["insight", "plan", "runbook", "local-guide", "decision"]
DURABLE_PATTERNS = [
    r"\b(always|never|prefer|use|run|install|configure|route|deploy|debug|test)\b",
    r"\b(decision|decided|plan|runbook|guide|recipe|workflow|invariant)\b",
    r"\b(команд|запускай|используй|настрой|план|решени|гайд|правил|инвариант)\b",
    r"`[^`]+`",
    r"```",
]
NOISE_PATTERNS = [
    r"^\s*(ok|done|thanks|спасибо|готово|понял)\s*[.!?]?\s*$",
    r"\b(today|tomorrow|yesterday|сегодня|завтра|вчера)\b",
    r"\b(temporary|one-off|одноразов|временно|пока что)\b",
    r"\b(raw log|stack trace|traceback|debug output)\b",
]


@dataclass(frozen=True)
class MemoryCandidate:
    accepted: bool
    kind: str
    title: str
    reason: str
    project_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "kind": self.kind,
            "title": self.title,
            "reason": self.reason,
            "project_id": self.project_id,
        }


def classify_memory(
    text: str,
    config: AtlasConfig,
    project_id: str = "",
    kind: str | None = None,
) -> MemoryCandidate:
    normalized = normalize_text(text)
    chosen_kind = normalize_kind(kind) if kind else infer_kind(normalized)
    title = infer_title(normalized)
    if chosen_kind not in config.memory.allowed_kinds:
        return MemoryCandidate(False, chosen_kind, title, "kind is disabled by config", project_id)
    if not normalized:
        return MemoryCandidate(False, chosen_kind, title, "empty memory", project_id)
    if len(normalized) > config.memory.max_note_chars:
        return MemoryCandidate(False, chosen_kind, title, "memory is too large", project_id)
    if looks_secret(normalized, config):
        return MemoryCandidate(False, chosen_kind, title, "memory looks secret-like", project_id)
    if looks_noisy(normalized):
        return MemoryCandidate(False, chosen_kind, title, "memory looks disposable", project_id)
    if not looks_durable(normalized, chosen_kind):
        return MemoryCandidate(False, chosen_kind, title, "memory is not durable enough", project_id)
    return MemoryCandidate(True, chosen_kind, title, "durable memory", project_id)


def build_memory_candidates(task: str, config: AtlasConfig, project_id: str = "") -> list[dict[str, Any]]:
    if not has_memory_intent(task):
        return []
    candidate = classify_memory(task, config, project_id=project_id)
    return [candidate.as_dict()] if candidate.accepted else []


def write_memory_note(
    root: Path,
    config: AtlasConfig,
    text: str,
    project_id: str,
    kind: str | None = None,
    source: str = "atlas remember",
) -> Path:
    candidate = classify_memory(text, config, project_id=project_id, kind=kind)
    if not candidate.accepted:
        raise ValueError(candidate.reason)
    wiki_root = expand_path(config.llm_wiki.path)
    wiki_root.mkdir(parents=True, exist_ok=True)
    target_dir = wiki_root / "atlas-memory" / (project_id or "general")
    target_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date().isoformat()
    path = unique_path(target_dir / f"{today}-{slug(candidate.title)}.md")
    frontmatter = {
        "title": candidate.title,
        "tags": ["atlas-memory", candidate.kind],
        "projects": [project_id] if project_id else [],
        "kind": candidate.kind,
        "updated": today,
        "source": source,
    }
    body = [
        "---",
        yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).strip(),
        "---",
        f"# {candidate.title}",
        "",
        normalize_text(text),
        "",
    ]
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines).strip()


def normalize_kind(kind: str) -> str:
    kind = kind.strip().lower()
    aliases = {
        "local_guide": "local-guide",
        "guide": "local-guide",
        "run-book": "runbook",
        "run book": "runbook",
    }
    return aliases.get(kind, kind)


def infer_kind(text: str) -> str:
    lower = text.lower()
    if re.search(r"\b(decision|decided|решени)\b", lower):
        return "decision"
    if re.search(r"\b(plan|todo|roadmap|план)\b", lower):
        return "plan"
    if re.search(r"\b(runbook|debug|troubleshoot|команд|recipe)\b", lower):
        return "runbook"
    if re.search(r"\b(local|setup|install|configure|гайд|настрой)\b", lower):
        return "local-guide"
    return "insight"


def infer_title(text: str) -> str:
    first = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), "Atlas Memory")
    first = re.sub(r"\s+", " ", first)
    return first[:80].rstrip(" .,:;") or "Atlas Memory"


def looks_secret(text: str, config: AtlasConfig) -> bool:
    lower = text.lower()
    if any(pattern.lower() in lower for pattern in config.memory.deny_patterns):
        return True
    secret_regexes = [
        r"(?i)\b[A-Z0-9_]*(TOKEN|SECRET|PASSWORD|API_KEY|PRIVATE_KEY)\b\s*[:=]",
        r"(?i)\b(password|token|secret|api[_-]?key)\b\s*[:=]\s*\S+",
        r"(?i)authorization:\s*(bearer|basic)\s+\S+",
    ]
    return any(re.search(pattern, text) for pattern in secret_regexes)


def looks_noisy(text: str) -> bool:
    if len(text) < 24:
        return True
    lower = text.lower()
    if any(re.search(pattern, lower, flags=re.IGNORECASE) for pattern in NOISE_PATTERNS):
        return True
    if lower.count("\n") > 80:
        return True
    return False


def looks_durable(text: str, kind: str) -> bool:
    if kind in {"plan", "runbook", "local-guide", "decision"}:
        return True
    lower = text.lower()
    return any(re.search(pattern, lower, flags=re.IGNORECASE) for pattern in DURABLE_PATTERNS)


def has_memory_intent(text: str) -> bool:
    return bool(
        re.search(
            r"\b(remember|insight|decision|runbook|local guide|guide|note|запомни|инсайт|решение|гайд)\b",
            text.lower(),
        )
    )


def slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ]+", "-", value.strip().lower()).strip("-")
    return value or "memory"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1
