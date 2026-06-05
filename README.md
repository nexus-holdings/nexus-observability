# Nexus Observability

> Dashboards, alerts, and forensic views over Nexus platform behaviour: sessions, spend, recovery events, contract and goal flow.

## Mission

Make Nexus platform behaviour observable so that runaway execution, budget overruns, and recovery cascades are caught before they hit guardrail caps.

## Quick Start

1. Read `wiki/WIKI.md` for full context
2. Check the GitHub Project for current milestones and tickets
3. Review `wiki/conventions.md` before writing any code

## Session & Spend Dashboard

A read-only CLI that queries Paperclip Postgres and prints four sections:

| Section | What it shows |
|---------|--------------|
| Sessions per Company per Day | Heartbeat run counts + recovery-run counts, last N days |
| Agent Spend | Budget vs. spent (cents) and token totals per company, current month |
| Active Routines | Non-archived routines grouped by company and status |
| Recovery Comments | Issue comments mentioning recovery/retry, last N days |

### Usage

```bash
# Default: last 7 days, standard DSN
uv run python -m src.dashboard

# Custom lookback and DSN
uv run python -m src.dashboard --days 14 --dsn postgresql://...
```

Environment variable `PAPERCLIP_DB` overrides the default DSN.

### Running Tests

```bash
uv run pytest
```

Tests use a fake DB-API 2.0 connection — no live Postgres required.

## Structure

```
wiki/                   # Company knowledge base
  WIKI.md               # Index — load this first
  architecture.md       # System design
  conventions.md        # Coding standards + process
  domain.md             # Business context + terminology
  decisions/            # ADR-style decision log
src/
  queries.py            # Read-only SQL queries (DB-API 2.0)
  dashboard.py          # CLI: collect + render
tests/
  test_dashboard.py     # Fake-conn unit tests
MEMORY.md               # Claude Code AutoMemory index
```

## Agents

This company uses agents provisioned from the [Nexus agent catalog](https://github.com/nexus-holdings/agent-catalog).
All agent definitions, skills, and performance data live there — not here.

## Escalation

Execution agent → Tech Lead → Company Lead → COO → Board meeting
