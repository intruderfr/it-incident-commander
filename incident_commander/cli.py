"""IT Incident Commander — CLI entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from . import __version__
from .incident import (
    STATUS_OPEN, STATUS_RESOLVED, STATUS_CANCELLED,
    STEP_DONE, STEP_SKIPPED, STEP_IN_PROGRESS,
    create_incident, load_incident, list_incidents,
    advance_step, resolve_incident, cancel_incident,
)
from .report import to_markdown, to_text, to_json
from .runbook import (
    discover_runbooks, builtin_runbook_dir,
    load_runbook, resolve_runbook_path,
)


# ----- Formatting helpers -----------------------------------------------------


def _fmt_duration(seconds: float) -> str:
    secs = int(seconds)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


def _severity_color(severity: str) -> str:
    colors = {"P1": "\033[91m", "P2": "\033[93m", "P3": "\033[96m", "P4": "\033[92m"}
    return colors.get(severity, "")


RESET = "\033[0m"
BOLD = "\033[1m"


def _c(text: str, code: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"{code}{text}{RESET}"


def _use_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""


# ----- Sub-command handlers ---------------------------------------------------


def cmd_start(args: argparse.Namespace) -> int:
    extra_dir = Path(args.runbook_dir) if args.runbook_dir else None
    path = resolve_runbook_path(args.runbook, extra_dir=extra_dir)
    runbook = load_runbook(path)

    errors = runbook.validate()
    if errors:
        print(f"Runbook validation failed ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(f"  • {e}", file=sys.stderr)
        return 1

    store = Path(args.store) if args.store else None
    incident = create_incident(runbook, store=store)

    color = _use_color()
    sev_code = _severity_color(incident.severity)
    print()
    print(_c(f"  Incident created: {incident.id}", BOLD, color))
    print(f"  Runbook : {incident.runbook_name}")
    print(f"  Severity: {_c(incident.severity, sev_code, color)}")
    if incident.description:
        print(f"  Desc    : {incident.description}")
    if incident.escalation_contact:
        print(f"  Escalate: {incident.escalation_contact}")
    print()
    print("  Steps:")
    for i, step in enumerate(incident.steps, 1):
        sla = f"  [SLA: {step.sla_minutes}m]" if step.sla_minutes else ""
        opt = "  (optional)" if step.optional else ""
        print(f"    {i:2}. [{step.id}] {step.title}  — {step.team}{sla}{opt}")
    print()
    print(f"  Run 'incident status {incident.id}' to check progress.")
    print(f"  Run 'incident step {incident.id} {incident.steps[0].id} start' to begin.")
    print()
    return 0


def cmd_step(args: argparse.Namespace) -> int:
    store = Path(args.store) if args.store else None
    action_map = {
        "start": STEP_IN_PROGRESS,
        "done": STEP_DONE,
        "skip": STEP_SKIPPED,
    }
    new_status = action_map.get(args.action)
    if new_status is None:
        print(f"Unknown action '{args.action}'. Use: start | done | skip", file=sys.stderr)
        return 1

    incident, step = advance_step(
        args.incident_id,
        args.step_id,
        new_status,
        notes=args.notes or "",
        store=store,
    )
    symbol = {"done": "✓", "skip": "→", "start": "~"}.get(args.action, "?")
    done, total = incident.progress()
    print(f"  [{symbol}] Step '{step.title}' → {new_status}")
    print(f"  Progress: {done}/{total} steps complete")
    if step.sla_breached():
        print(f"  ⚠  SLA target ({step.sla_minutes}m) was exceeded for this step.")

    next_step = incident.current_step()
    if next_step and next_step.id != step.id:
        print(f"  Next: [{next_step.id}] {next_step.title}  — {next_step.team}")
    elif done == total:
        print(f"  All steps complete. Run 'incident resolve {incident.id}' to close.")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    store = Path(args.store) if args.store else None
    incident = load_incident(args.incident_id, store=store)
    color = _use_color()
    sev_code = _severity_color(incident.severity)
    done, total = incident.progress()
    elapsed = _fmt_duration(incident.elapsed_seconds())

    status_sym = {"open": "U0001f534", "resolved": "✅", "cancelled": "U0001f6ab"}.get(incident.status, "")
    print()
    print(_c(f"  {status_sym} {incident.id}  —  {incident.runbook_name}", BOLD, color))
    print(f"  Severity : {_c(incident.severity, sev_code, color)}")
    print(f"  Status   : {incident.status}")
    print(f"  Elapsed  : {elapsed}")
    print(f"  Progress : {done}/{total} steps")
    print()
    print("  Step breakdown:")
    for i, step in enumerate(incident.steps, 1):
        sym = {
            STEP_DONE: "✓", STEP_SKIPPED: "→",
            STEP_IN_PROGRESS: "~", "pending": " "
        }.get(step.status, "?")
        dur_str = ""
        if step.duration_seconds() is not None:
            dur_str = f"  ({_fmt_duration(step.duration_seconds())})"
        sla_warn = "  ⚠ SLA!" if step.sla_breached() else ""
        print(f"    {i:2}. [{sym}] {step.id:<20} {step.title}{dur_str}{sla_warn}")
    print()

    current = incident.current_step()
    if current:
        print(f"  Current step: [{current.id}] {current.title}  — {current.team}")
    if incident.resolution_notes:
        print(f"  Resolution  : {incident.resolution_notes}")
    print()
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    store = Path(args.store) if args.store else None
    incident = resolve_incident(args.incident_id, notes=args.notes or "", store=store)
    elapsed = _fmt_duration(incident.elapsed_seconds())
    print(f"  ✅ Incident {incident.id} resolved in {elapsed}.")
    if args.notes:
        print(f"  Notes: {args.notes}")
    print(f"  Run 'incident report {incident.id}' to generate the post-incident report.")
    return 0


def cmd_cancel(args: argparse.Namespace) -> int:
    store = Path(args.store) if args.store else None
    incident = cancel_incident(args.incident_id, notes=args.notes or "", store=store)
    print(f"  U0001f6ab Incident {incident.id} cancelled.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = Path(args.store) if args.store else None
    status_filter = args.status if args.status != "all" else None
    incidents = list_incidents(store=store, status_filter=status_filter)
    if not incidents:
        print("  No incidents found.")
        return 0

    color = _use_color()
    print()
    fmt = "  {:<16} {:<6} {:<12} {:<10} {:<6}  {}"
    print(fmt.format("ID", "SEV", "RUNBOOK", "STATUS", "PROG", "ELAPSED"))
    print("  " + "─" * 70)
    for inc in incidents:
        done, total = inc.progress()
        elapsed = _fmt_duration(inc.elapsed_seconds())
        sev_code = _severity_color(inc.severity)
        print(fmt.format(
            inc.id,
            _c(inc.severity, sev_code, color),
            inc.runbook_name[:12],
            inc.status,
            f"{done}/{total}",
            elapsed,
        ))
    print()
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    store = Path(args.store) if args.store else None
    incident = load_incident(args.incident_id, store=store)

    fmt = args.format.lower()
    if fmt == "markdown":
        output = to_markdown(incident)
    elif fmt == "json":
        output = to_json(incident)
    else:
        output = to_text(incident)

    if args.output:
        Path(args.output).write_text(output)
        print(f"  Report written to {args.output}")
    else:
        print(output)
    return 0


def cmd_list_runbooks(args: argparse.Namespace) -> int:
    search_dirs = [builtin_runbook_dir()]
    if args.runbook_dir:
        search_dirs.insert(0, Path(args.runbook_dir))

    print()
    found_any = False
    for d in search_dirs:
        paths = discover_runbooks(d)
        if not paths:
            continue
        found_any = True
        print(f"  {d}/")
        for p in paths:
            try:
                rb = load_runbook(p)
                errs = rb.validate()
                err_str = f"  ⚠ {len(errs)} error(s)" if errs else ""
                print(f"    {p.stem:<30} {rb.severity:<4}  {rb.name}{err_str}")
            except Exception as exc:
                print(f"    {p.stem:<30}  (load error: {exc})")
    if not found_any:
        print("  No runbooks found.")
    print()
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    extra_dir = Path(args.runbook_dir) if args.runbook_dir else None
    path = resolve_runbook_path(args.runbook, extra_dir=extra_dir)
    try:
        rb = load_runbook(path)
    except Exception as exc:
        print(f"  Parse error: {exc}", file=sys.stderr)
        return 1
    errors = rb.validate()
    if errors:
        print(f"  Runbook '{rb.name}' has {len(errors)} error(s):", file=sys.stderr)
        for e in errors:
            print(f"    • {e}", file=sys.stderr)
        return 1
    print(f"  ✓ Runbook '{rb.name}' is valid  ({len(rb.steps)} steps, severity {rb.severity})")
    return 0


# ----- Parser -----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="incident",
        description="IT Incident Commander — YAML-driven incident response CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  incident start server-down
  incident step INC-ABCD1234 isolate-server start
  incident step INC-ABCD1234 isolate-server done --notes "rebooted via IPMI"
  incident status INC-ABCD1234
  incident resolve INC-ABCD1234 --notes "Root cause: disk full on /var"
  incident report INC-ABCD1234 --format markdown --output report.md
  incident list-runbooks
  incident validate security-breach
""",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--store", metavar="PATH",
        help="path to incidents JSON store (default: ~/.local/share/it-incident-commander/incidents.json)",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # start
    p_start = sub.add_parser("start", help="Start a new incident from a runbook")
    p_start.add_argument("runbook", help="Runbook name or path (e.g. server-down)")
    p_start.add_argument("--runbook-dir", metavar="DIR", help="Additional directory to search for runbooks")
    p_start.set_defaults(func=cmd_start)

    # step
    p_step = sub.add_parser("step", help="Advance a step: start | done | skip")
    p_step.add_argument("incident_id", help="Incident ID (e.g. INC-ABCD1234)")
    p_step.add_argument("step_id", help="Step ID from the runbook")
    p_step.add_argument("action", choices=["start", "done", "skip"])
    p_step.add_argument("--notes", metavar="TEXT", help="Optional notes for this step")
    p_step.set_defaults(func=cmd_step)

    # status
    p_status = sub.add_parser("status", help="Show incident status and step breakdown")
    p_status.add_argument("incident_id")
    p_status.set_defaults(func=cmd_status)

    # resolve
    p_resolve = sub.add_parser("resolve", help="Mark an incident as resolved")
    p_resolve.add_argument("incident_id")
    p_resolve.add_argument("--notes", metavar="TEXT", help="Resolution notes / root cause")
    p_resolve.set_defaults(func=cmd_resolve)

    # cancel
    p_cancel = sub.add_parser("cancel", help="Cancel an open incident")
    p_cancel.add_argument("incident_id")
    p_cancel.add_argument("--notes", metavar="TEXT")
    p_cancel.set_defaults(func=cmd_cancel)

    # list
    p_list = sub.add_parser("list", help="List all incidents")
    p_list.add_argument(
        "--status", default="all",
        choices=["all", STATUS_OPEN, STATUS_RESOLVED, STATUS_CANCELLED],
        help="Filter by status (default: all)",
    )
    p_list.set_defaults(func=cmd_list)

    # report
    p_report = sub.add_parser("report", help="Generate a post-incident report")
    p_report.add_argument("incident_id")
    p_report.add_argument(
        "--format", default="text",
        choices=["text", "markdown", "json"],
        help="Output format (default: text)",
    )
    p_report.add_argument("--output", metavar="FILE", help="Write report to file instead of stdout")
    p_report.set_defaults(func=cmd_report)

    # list-runbooks
    p_lrb = sub.add_parser("list-runbooks", help="List available runbooks")
    p_lrb.add_argument("--runbook-dir", metavar="DIR")
    p_lrb.set_defaults(func=cmd_list_runbooks)

    # validate
    p_val = sub.add_parser("validate", help="Validate a runbook YAML file")
    p_val.add_argument("runbook", help="Runbook name or path")
    p_val.add_argument("--runbook-dir", metavar="DIR")
    p_val.set_defaults(func=cmd_validate)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        rc = args.func(args)
        sys.exit(rc or 0)
    except KeyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
