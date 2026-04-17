"""Tests for report generation."""

import json
from pathlib import Path

from incident_commander.runbook import load_runbook, discover_runbooks, builtin_runbook_dir
from incident_commander.incident import (
    create_incident, advance_step, resolve_incident,
    STEP_DONE, STEP_SKIPPED,
)
from incident_commander.report import to_markdown, to_text, to_json


# ----- Helpers ----------------------------------------------------------------


def _make_resolved_incident(tmp_path: Path):
    store = tmp_path / "inc.json"
    paths = discover_runbooks(builtin_runbook_dir())
    rb = load_runbook(paths[0])
    inc = create_incident(rb, store=store)
    for step in inc.steps:
        advance_step(inc.id, step.id, STEP_DONE, store=store)
    from incident_commander.incident import load_incident
    inc = load_incident(inc.id, store=store)
    resolve_incident(inc.id, notes="All fixed.", store=store)
    return load_incident(inc.id, store=store)


# ----- Markdown ---------------------------------------------------------------


def test_markdown_contains_incident_id(tmp_path):
    inc = _make_resolved_incident(tmp_path)
    md = to_markdown(inc)
    assert inc.id in md


def test_markdown_contains_all_step_titles(tmp_path):
    inc = _make_resolved_incident(tmp_path)
    md = to_markdown(inc)
    for step in inc.steps:
        assert step.title in md


def test_markdown_contains_resolution_notes(tmp_path):
    inc = _make_resolved_incident(tmp_path)
    md = to_markdown(inc)
    assert "All fixed." in md


def test_markdown_starts_with_header(tmp_path):
    inc = _make_resolved_incident(tmp_path)
    md = to_markdown(inc)
    assert md.startswith("# Post-Incident Report")


# ----- Text -------------------------------------------------------------------


def test_text_contains_incident_id(tmp_path):
    inc = _make_resolved_incident(tmp_path)
    txt = to_text(inc)
    assert inc.id in txt


def test_text_contains_runbook_name(tmp_path):
    inc = _make_resolved_incident(tmp_path)
    txt = to_text(inc)
    assert inc.runbook_name in txt


def test_text_contains_steps(tmp_path):
    inc = _make_resolved_incident(tmp_path)
    txt = to_text(inc)
    for step in inc.steps:
        assert step.title in txt


# ----- JSON -------------------------------------------------------------------


def test_json_is_valid(tmp_path):
    inc = _make_resolved_incident(tmp_path)
    j = to_json(inc)
    data = json.loads(j)
    assert data["id"] == inc.id
    assert data["status"] == "resolved"
    assert len(data["steps"]) == len(inc.steps)


def test_json_has_resolution_notes(tmp_path):
    inc = _make_resolved_incident(tmp_path)
    data = json.loads(to_json(inc))
    assert data["resolution_notes"] == "All fixed."


def test_json_step_fields(tmp_path):
    inc = _make_resolved_incident(tmp_path)
    data = json.loads(to_json(inc))
    step = data["steps"][0]
    assert "id" in step
    assert "title" in step
    assert "status" in step
    assert "team" in step
