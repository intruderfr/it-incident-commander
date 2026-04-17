"""Runbook loading, validation, and discovery."""

from __future__ import annotations

import os
import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


REQUIRED_TOP_KEYS = {"name", "severity", "steps"}
VALID_SEVERITIES = {"P1", "P2", "P3", "P4"}
VALID_STEP_KEYS = {"id", "title", "description", "team", "sla_minutes", "optional"}


@dataclass
class Step:
    id: str
    title: str
    description: str = ""
    team: str = "IT"
    sla_minutes: Optional[int] = None
    optional: bool = False

    def validate(self) -> List[str]:
        errors = []
        if not re.match(r"^[a-z0-9_-]+$", self.id):
            errors.append(f"Step id '{self.id}' must be lowercase alphanumeric with _ or -")
        if not self.title.strip():
            errors.append(f"Step '{self.id}' has an empty title")
        if self.sla_minutes is not None and self.sla_minutes <= 0:
            errors.append(f"Step '{self.id}' sla_minutes must be > 0")
        return errors


@dataclass
class Runbook:
    name: str
    severity: str
    description: str = ""
    category: str = "general"
    escalation_contact: str = ""
    steps: List[Step] = field(default_factory=list)
    source_file: str = ""

    def validate(self) -> List[str]:
        errors = []
        if self.severity not in VALID_SEVERITIES:
            errors.append(
                f"severity '{self.severity}' is invalid; must be one of {sorted(VALID_SEVERITIES)}"
            )
        if not self.steps:
            errors.append("Runbook has no steps")
        ids_seen: set = set()
        for step in self.steps:
            errors.extend(step.validate())
            if step.id in ids_seen:
                errors.append(f"Duplicate step id '{step.id}'")
            ids_seen.add(step.id)
        return errors


def _parse_step(raw: dict) -> Step:
    unknown = set(raw) - VALID_STEP_KEYS
    if unknown:
        raise ValueError(f"Unknown step key(s): {', '.join(sorted(unknown))}")
    if "id" not in raw:
        raise ValueError("Step is missing required key 'id'")
    if "title" not in raw:
        raise ValueError(f"Step '{raw['id']}' is missing required key 'title'")
    return Step(
        id=raw["id"],
        title=raw["title"],
        description=raw.get("description", ""),
        team=raw.get("team", "IT"),
        sla_minutes=raw.get("sla_minutes"),
        optional=bool(raw.get("optional", False)),
    )


def load_runbook(path: str | Path) -> Runbook:
    """Load and return a Runbook from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Runbook file not found: {path}")
    with path.open() as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"Runbook file must be a YAML mapping: {path}")
    missing = REQUIRED_TOP_KEYS - set(raw)
    if missing:
        raise ValueError(f"Runbook is missing required key(s): {', '.join(sorted(missing))}")
    steps = [_parse_step(s) for s in raw["steps"]]
    return Runbook(
        name=raw["name"],
        severity=raw["severity"],
        description=raw.get("description", ""),
        category=raw.get("category", "general"),
        escalation_contact=raw.get("escalation_contact", ""),
        steps=steps,
        source_file=str(path),
    )


def discover_runbooks(runbook_dir: str | Path) -> List[Path]:
    """Return all .yaml / .yml files in runbook_dir (non-recursive)."""
    d = Path(runbook_dir)
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.suffix in {".yaml", ".yml"})


def builtin_runbook_dir() -> Path:
    """Return the path to the bundled runbooks/ directory."""
    return Path(__file__).parent.parent / "runbooks"


def resolve_runbook_path(name_or_path: str, extra_dir: Optional[Path] = None) -> Path:
    """
    Resolve a runbook by file path OR short name.
    Search order: literal path → extra_dir → builtin_runbook_dir.
    """
    p = Path(name_or_path)
    if p.exists():
        return p
    for suffix in ("", ".yaml", ".yml"):
        candidate = p.with_suffix(suffix) if suffix else p
        if candidate.exists():
            return candidate
    # search extra_dir
    for directory in ([extra_dir] if extra_dir else []) + [builtin_runbook_dir()]:
        if directory is None:
            continue
        for suffix in (".yaml", ".yml", ""):
            candidate = directory / (name_or_path + suffix)
            if candidate.exists():
                return candidate
    raise FileNotFoundError(
        f"Could not find runbook '{name_or_path}'. "
        "Use 'incident list-runbooks' to see available options."
    )
