# IT Incident Commander

[![CI](https://github.com/intruderfr/it-incident-commander/actions/workflows/ci.yml/badge.svg)](https://github.com/intruderfr/it-incident-commander/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A **YAML-driven incident response CLI** for IT teams. Define your runbooks once, execute them consistently every time — with step-by-step tracking, SLA monitoring, and automatic post-incident report generation.

```
$ incident start server-down

  Incident created: INC-3A7F92B1
  Runbook : Server Down
  Severity: P1
  Escalate: Head of IT / on-call engineer

  Steps:
    1. [verify-outage]       Verify the outage                — IT Operations  [SLA: 5m]
    2. [notify-stakeholders] Notify stakeholders              — IT Operations  [SLA: 10m]
    3. [check-console]       Access console / IPMI / ...      — IT Operations  [SLA: 15m]
    ...

  Run 'incident step INC-3A7F92B1 verify-outage start' to begin.
```

---

## Features

- **YAML runbooks** — define steps, teams, SLA targets, and escalation contacts
- **Step lifecycle** — `start` → `done` / `skip` with timestamps and optional notes
- **SLA tracking** — warns when a step exceeds its time target
- **Post-incident reports** — plain text, Markdown, or JSON
- **4 bundled runbooks** — server-down, network-outage, security-breach, email-service-down
- **Custom runbooks** — bring your own YAML
- **Zero external dependencies** beyond PyYAML
- **Persistent incident log** — stored at `~/.local/share/it-incident-commander/incidents.json`

---

## Installation

```bash
pip install PyYAML
pip install git+https://github.com/intruderfr/it-incident-commander.git
```

Or clone and install locally:

```bash
git clone https://github.com/intruderfr/it-incident-commander.git
cd it-incident-commander
pip install -e .
```

---

## Quick Start

### 1. Start an incident

```bash
incident start server-down
# Output: Incident created: INC-ABCD1234
```

### 2. Work through the steps

```bash
# Start the first step
incident step INC-ABCD1234 verify-outage start

# Mark it done with notes
incident step INC-ABCD1234 verify-outage done --notes "Confirmed: web01 unreachable from 3 locations"

# Skip an optional step
incident step INC-ABCD1234 change-record skip
```

### 3. Check progress

```bash
incident status INC-ABCD1234
```

### 4. Resolve the incident

```bash
incident resolve INC-ABCD1234 --notes "Root cause: disk full on /var/log. Cleared logs, added log rotation."
```

### 5. Generate the post-incident report

```bash
# Plain text (default)
incident report INC-ABCD1234

# Markdown (great for Confluence, Notion, GitHub)
incident report INC-ABCD1234 --format markdown --output incident-report.md

# JSON (for ITSM integrations)
incident report INC-ABCD1234 --format json
```

---

## Available Runbooks

| Runbook | Severity | Steps | Description |
|---------|----------|-------|-------------|
| `server-down` | P1 | 8 | Production server unresponsive |
| `network-outage` | P1 | 8 | Network connectivity loss |
| `security-breach` | P1 | 10 | Suspected compromise — contain, eradicate, recover |
| `email-service-down` | P2 | 9 | Corporate email unavailable |

---

## Writing Custom Runbooks

```yaml
name: Database Failover
severity: P1
category: database
description: Primary database is down — fail over to replica.
escalation_contact: "DBA Team / AWS Support"

steps:
  - id: confirm-primary-down
    title: Confirm the primary is unreachable
    team: DBA Team
    sla_minutes: 5

  - id: promote-replica
    title: Promote read replica to primary
    team: DBA Team
    sla_minutes: 15
```

Run it:

```bash
incident start ./my-runbooks/db-failover.yaml
```

---

## CLI Reference

```
incident start <runbook>
incident step <INC-ID> <step-id> start|done|skip [--notes TEXT]
incident status <INC-ID>
incident resolve <INC-ID> [--notes TEXT]
incident cancel <INC-ID>
incident list [--status open|resolved|cancelled]
incident report <INC-ID> [--format text|markdown|json] [--output FILE]
incident list-runbooks [--runbook-dir DIR]
incident validate <runbook>
```

---

## Author

**Aslam Ahamed** — Head of IT @ Prestige One Developments, Dubai
[LinkedIn](https://www.linkedin.com/in/aslam-ahamed/)

---

## License

MIT — see [LICENSE](LICENSE)
