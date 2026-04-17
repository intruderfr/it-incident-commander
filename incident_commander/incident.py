"""Incident state management — create, update, persist."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .runbook import Runbook, Step


# ----- Status constants -------------------------------------------------------

STATUS_OPEN = "open"
STATUS_RESOLVED = "resolved"
STATUS_CANCELLED = "cancelled"

STEP_PENDING = "pending"
STEP_IN_PROGRESS = "in_progress"
STEP_DONE = "done"
STEP_SKIPPED = "skipped"

VALID_STEP_TRANSITIONS = {
    STEP_PENDING: {STEP_IN_PROGRESS, STEP_DONE, STEP_SKIPPED},
    STEP_IN_PROGRESS: {STEP_DONE, STEP_SKIPPED},
    STEP_DONE: set(),
    STEP_SKIPPED: set(),
}


# ----- Data classes -----------------------------------------------------------


@dataclass
class StepRecord:
    id: str
    title: str
    team: str
    optional: bool
    sla_minutes: Optional[int]
    status: str = STEP_PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    notes: str = ""

    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            s = datetime.fromisoformat(self.started_at)
            e = datetime.fromisoformat(self.completed_at)
            return (e - s).total_seconds()
        return None

    def sla_breached(self) -> bool:
        if self.sla_minutes is None:
            return False
        dur = self.duration_seconds()
        if dur is None:
            # If still in progress, measure elapsed so far
            if self.started_at:
                s = datetime.fromisoformat(self.started_at)
                dur = (datetime.now(timezone.utc) - s).total_seconds()
            else:
                return False
        return dur > self.sla_minutes * 60


@dataclass
class Incident:
    id: str
    runbook_name: str
    severity: str
    category: str
    description: str
    escalation_contact: str
    created_at: str
    status: str = STATUS_OPEN
    resolved_at: Optional[str] = None
    resolution_notes: str = ""
    steps: List[StepRecord] = field(default_factory=list)

    # ----- helpers ------------------------------------------------------------

    def current_step(self) -> Optional[StepRecord]:
        for s in self.steps:
            if s.status in (STEP_PENDING, STEP_IN_PROGRESS):
                return s
        return None

    def progress(self) -> tuple[int, int]:
        done = sum(1 for s in self.steps if s.status in (STEP_DONE, STEP_SKIPPED))
        return done, len(self.steps)

    def elapsed_seconds(self) -> float:
        start = datetime.fromisoformat(self.created_at)
        end_ts = self.resolved_at or _now_iso()
        end = datetime.fromisoformat(end_ts)
        return (end - start).total_seconds()

    def breached_steps(self) -> List[StepRecord]:
        return [s for s in self.steps if s.sla_breached()]

    # ----- serialisation ------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Incident":
        steps = [StepRecord(**s) for s in d.pop("steps", [])]
        return cls(**d, steps=steps)


# ----- Storage ----------------------------------------------------------------


def _default_store_path() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(xdg) / "it-incident-commander" / "incidents.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_all(store: Path) -> Dict[str, dict]:
    if not store.exists():
        return {}
    with store.open() as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        return {}
    return data


def _save_all(store: Path, all_incidents: Dict[str, dict]) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    with store.open("w") as fh:
        json.dump(all_incidents, fh, indent=2)


# ----- Public API -------------------------------------------------------------


def create_incident(runbook: Runbook, store: Optional[Path] = None) -> Incident:
    inc_id = "INC-" + uuid.uuid4().hex[:8].upper()
    steps = [
        StepRecord(
            id=s.id,
            title=s.title,
            team=s.team,
            optional=s.optional,
            sla_minutes=s.sla_minutes,
        )
        for s in runbook.steps
    ]
    incident = Incident(
        id=inc_id,
        runbook_name=runbook.name,
        severity=runbook.severity,
        category=runbook.category,
        description=runbook.description,
        escalation_contact=runbook.escalation_contact,
        created_at=_now_iso(),
        steps=steps,
    )
    _persist(incident, store)
    return incident


def load_incident(inc_id: str, store: Optional[Path] = None) -> Incident:
    store = store or _default_store_path()
    all_incidents = _load_all(store)
    if inc_id not in all_incidents:
        raise KeyError(f"Incident '{inc_id}' not found.")
    return Incident.from_dict(dict(all_incidents[inc_id]))


def list_incidents(
    store: Optional[Path] = None,
    status_filter: Optional[str] = None,
) -> List[Incident]:
    store = store or _default_store_path()
    all_incidents = _load_all(store)
    incidents = [Incident.from_dict(dict(v)) for v in all_incidents.values()]
    if status_filter:
        incidents = [i for i in incidents if i.status == status_filter]
    return sorted(incidents, key=lambda i: i.created_at, reverse=True)


def advance_step(
    inc_id: str,
    step_id: str,
    new_status: str,
    notes: str = "",
    store: Optional[Path] = None,
) -> tuple[Incident, StepRecord]:
    incident = load_incident(inc_id, store)
    step = next((s for s in incident.steps if s.id == step_id), None)
    if step is None:
        raise KeyError(f"Step '{step_id}' not found in incident '{inc_id}'.")
    allowed = VALID_STEP_TRANSITIONS.get(step.status, set())
    if new_status not in allowed:
        raise ValueError(
            f"Cannot transition step '{step_id}' from '{step.status}' to '{new_status}'. "
            f"Allowed: {sorted(allowed) or 'none (terminal state)'}."
        )
    if new_status == STEP_IN_PROGRESS and step.started_at is None:
        step.started_at = _now_iso()
    if new_status in (STEP_DONE, STEP_SKIPPED):
        if step.started_at is None:
            step.started_at = _now_iso()
        step.completed_at = _now_iso()
    step.status = new_status
    if notes:
        step.notes = notes
    _persist(incident, store)
    return incident, step


def resolve_incident(
    inc_id: str,
    notes: str = "",
    store: Optional[Path] = None,
) -> Incident:
    incident = load_incident(inc_id, store)
    if incident.status != STATUS_OPEN:
        raise ValueError(f"Incident '{inc_id}' is already {incident.status}.")
    incident.status = STATUS_RESOLVED
    incident.resolved_at = _now_iso()
    incident.resolution_notes = notes
    _persist(incident, store)
    return incident


def cancel_incident(
    inc_id: str,
    notes: str = "",
    store: Optional[Path] = None,
) -> Incident:
    incident = load_incident(inc_id, store)
    if incident.status != STATUS_OPEN:
        raise ValueError(f"Incident '{inc_id}' is already {incident.status}.")
    incident.status = STATUS_CANCELLED
    incident.resolved_at = _now_iso()
    incident.resolution_notes = notes
    _persist(incident, store)
    return incident


def _persist(incident: Incident, store: Optional[Path]) -> None:
    store = store or _default_store_path()
    all_incidents = _load_all(store)
    all_incidents[incident.id] = incident.to_dict()
    _save_all(store, all_incidents)
