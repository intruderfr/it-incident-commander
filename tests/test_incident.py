"""Tests for incident lifecycle management."""

import json
from pathlib import Path

import pytest

from incident_commander.runbook import load_runbook, builtin_runbook_dir
from incident_commander.incident import (
    create_incident, load_incident, list_incidents,
    advance_step, resolve_incident, cancel_incident,
    STATUS_OPEN, STATUS_RESOLVED, STATUS_CANCELLED,
    STEP_PENDING, STEP_IN_PROGRESS, STEP_DONE, STEP_SKIPPED,
)


# ----- Helpers ----------------------------------------------------------------


def _first_runbook():
    from incident_commander.runbook import discover_runbooks
    paths = discover_runbooks(builtin_runbook_dir())
    return load_runbook(paths[0])


def make_incident(tmp_path: Path):
    store = tmp_path / "incidents.json"
    rb = _first_runbook()
    inc = create_incident(rb, store=store)
    return inc, store


# ----- create_incident --------------------------------------------------------


def test_create_incident_returns_open(tmp_path):
    inc, _ = make_incident(tmp_path)
    assert inc.status == STATUS_OPEN
    assert inc.id.startswith("INC-")
    assert len(inc.steps) > 0


def test_create_incident_persists(tmp_path):
    inc, store = make_incident(tmp_path)
    loaded = load_incident(inc.id, store=store)
    assert loaded.id == inc.id
    assert loaded.runbook_name == inc.runbook_name


def test_create_incident_initial_steps_pending(tmp_path):
    inc, _ = make_incident(tmp_path)
    for step in inc.steps:
        assert step.status == STEP_PENDING


# ----- advance_step -----------------------------------------------------------


def test_advance_step_start(tmp_path):
    inc, store = make_incident(tmp_path)
    first_id = inc.steps[0].id
    updated_inc, step = advance_step(inc.id, first_id, STEP_IN_PROGRESS, store=store)
    assert step.status == STEP_IN_PROGRESS
    assert step.started_at is not None


def test_advance_step_done(tmp_path):
    inc, store = make_incident(tmp_path)
    first_id = inc.steps[0].id
    advance_step(inc.id, first_id, STEP_IN_PROGRESS, store=store)
    _, step = advance_step(inc.id, first_id, STEP_DONE, store=store)
    assert step.status == STEP_DONE
    assert step.completed_at is not None


def test_advance_step_skip(tmp_path):
    inc, store = make_incident(tmp_path)
    first_id = inc.steps[0].id
    _, step = advance_step(inc.id, first_id, STEP_SKIPPED, store=store)
    assert step.status == STEP_SKIPPED


def test_advance_step_invalid_transition(tmp_path):
    inc, store = make_incident(tmp_path)
    first_id = inc.steps[0].id
    advance_step(inc.id, first_id, STEP_DONE, store=store)
    with pytest.raises(ValueError, match="Cannot transition"):
        advance_step(inc.id, first_id, STEP_IN_PROGRESS, store=store)


def test_advance_step_with_notes(tmp_path):
    inc, store = make_incident(tmp_path)
    first_id = inc.steps[0].id
    _, step = advance_step(inc.id, first_id, STEP_DONE, notes="All good", store=store)
    assert step.notes == "All good"


def test_advance_step_unknown_step(tmp_path):
    inc, store = make_incident(tmp_path)
    with pytest.raises(KeyError, match="not found"):
        advance_step(inc.id, "nonexistent-step", STEP_DONE, store=store)


# ----- resolve / cancel -------------------------------------------------------


def test_resolve_incident(tmp_path):
    inc, store = make_incident(tmp_path)
    resolved = resolve_incident(inc.id, notes="Fixed", store=store)
    assert resolved.status == STATUS_RESOLVED
    assert resolved.resolved_at is not None
    assert resolved.resolution_notes == "Fixed"


def test_cancel_incident(tmp_path):
    inc, store = make_incident(tmp_path)
    cancelled = cancel_incident(inc.id, notes="False alarm", store=store)
    assert cancelled.status == STATUS_CANCELLED


def test_double_resolve_raises(tmp_path):
    inc, store = make_incident(tmp_path)
    resolve_incident(inc.id, store=store)
    with pytest.raises(ValueError, match="already"):
        resolve_incident(inc.id, store=store)


# ----- list_incidents ---------------------------------------------------------


def test_list_incidents_returns_all(tmp_path):
    store = tmp_path / "incidents.json"
    rb = _first_runbook()
    inc1 = create_incident(rb, store=store)
    inc2 = create_incident(rb, store=store)
    all_incidents = list_incidents(store=store)
    ids = [i.id for i in all_incidents]
    assert inc1.id in ids
    assert inc2.id in ids


def test_list_incidents_filter_by_status(tmp_path):
    store = tmp_path / "incidents.json"
    rb = _first_runbook()
    inc_open = create_incident(rb, store=store)
    inc_resolved = create_incident(rb, store=store)
    resolve_incident(inc_resolved.id, store=store)

    open_list = list_incidents(store=store, status_filter=STATUS_OPEN)
    resolved_list = list_incidents(store=store, status_filter=STATUS_RESOLVED)

    assert any(i.id == inc_open.id for i in open_list)
    assert all(i.status == STATUS_OPEN for i in open_list)
    assert any(i.id == inc_resolved.id for i in resolved_list)


# ----- progress / current_step ------------------------------------------------


def test_progress_tracking(tmp_path):
    inc, store = make_incident(tmp_path)
    done, total = inc.progress()
    assert done == 0
    assert total == len(inc.steps)

    for step in inc.steps[:2]:
        advance_step(inc.id, step.id, STEP_DONE, store=store)

    inc2 = load_incident(inc.id, store=store)
    done2, total2 = inc2.progress()
    assert done2 == 2


def test_current_step_advances(tmp_path):
    inc, store = make_incident(tmp_path)
    current = inc.current_step()
    assert current is not None
    assert current.id == inc.steps[0].id
    advance_step(inc.id, inc.steps[0].id, STEP_DONE, store=store)
    inc2 = load_incident(inc.id, store=store)
    current2 = inc2.current_step()
    assert current2 is not None
    assert current2.id == inc.steps[1].id
