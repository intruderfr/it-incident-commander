"""Tests for runbook loading and validation."""

import textwrap
from pathlib import Path

import pytest
import yaml

from incident_commander.runbook import (
    Runbook, Step, load_runbook, discover_runbooks, builtin_runbook_dir
)


# ----- Fixtures ---------------------------------------------------------------


def write_runbook(tmp_path: Path, content: str, filename: str = "test.yaml") -> Path:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(content))
    return p


VALID_YAML = """
    name: Test Runbook
    severity: P2
    steps:
      - id: step-one
        title: Do the first thing
        team: Ops
        sla_minutes: 10
      - id: step-two
        title: Do the second thing
        optional: true
"""


# ----- load_runbook -----------------------------------------------------------


def test_load_valid_runbook(tmp_path):
    p = write_runbook(tmp_path, VALID_YAML)
    rb = load_runbook(p)
    assert rb.name == "Test Runbook"
    assert rb.severity == "P2"
    assert len(rb.steps) == 2
    assert rb.steps[0].id == "step-one"
    assert rb.steps[0].sla_minutes == 10
    assert rb.steps[1].optional is True


def test_load_missing_file():
    with pytest.raises(FileNotFoundError):
        load_runbook("/nonexistent/path.yaml")


def test_load_missing_required_key(tmp_path):
    p = write_runbook(tmp_path, "name: Only Name\nsteps: []\n")
    with pytest.raises(ValueError, match="missing required key"):
        load_runbook(p)


def test_load_unknown_step_key(tmp_path):
    yaml_content = """
        name: Bad
        severity: P3
        steps:
          - id: s1
            title: Step 1
            bogus_key: oops
    """
    p = write_runbook(tmp_path, yaml_content)
    with pytest.raises(ValueError, match="Unknown step key"):
        load_runbook(p)


# ----- Runbook.validate -------------------------------------------------------


def test_validate_passes_clean_runbook(tmp_path):
    p = write_runbook(tmp_path, VALID_YAML)
    rb = load_runbook(p)
    assert rb.validate() == []


def test_validate_invalid_severity():
    rb = Runbook(name="X", severity="P5", steps=[Step(id="s1", title="S1")])
    errors = rb.validate()
    assert any("severity" in e for e in errors)


def test_validate_empty_steps():
    rb = Runbook(name="X", severity="P1", steps=[])
    errors = rb.validate()
    assert any("no steps" in e.lower() for e in errors)


def test_validate_duplicate_step_ids():
    steps = [Step(id="dup", title="A"), Step(id="dup", title="B")]
    rb = Runbook(name="X", severity="P1", steps=steps)
    errors = rb.validate()
    assert any("Duplicate" in e for e in errors)


def test_validate_bad_step_id():
    steps = [Step(id="BAD ID!", title="broken")]
    rb = Runbook(name="X", severity="P1", steps=steps)
    errors = rb.validate()
    assert any("BAD ID!" in e for e in errors)


# ----- discover_runbooks + builtin --------------------------------------------


def test_discover_runbooks_finds_yaml(tmp_path):
    (tmp_path / "a.yaml").write_text(VALID_YAML)
    (tmp_path / "b.yml").write_text(VALID_YAML)
    (tmp_path / "c.txt").write_text("ignored")
    found = discover_runbooks(tmp_path)
    names = [p.name for p in found]
    assert "a.yaml" in names
    assert "b.yml" in names
    assert "c.txt" not in names


def test_builtin_runbooks_are_valid():
    """Every bundled runbook must load and pass validation."""
    runbook_dir = builtin_runbook_dir()
    paths = discover_runbooks(runbook_dir)
    assert len(paths) >= 4, "Expected at least 4 bundled runbooks"
    for p in paths:
        rb = load_runbook(p)
        errors = rb.validate()
        assert errors == [], f"Runbook {p.name} has validation errors: {errors}"
