# Nexus Observability

> Dashboards, alerts, and forensic views over Nexus platform behaviour: sessions, spend, recovery events, contract and goal flow.

## Company Type

`product` — Full-stack product company

## Team Structure

| Role | Type | Responsibilities |
|------|------|-----------------|
| Company Lead | Persistent | Mission ownership, stakeholder communication |
| Tech Lead | Persistent | Architecture decisions, code review, ticket decomposition |
| Execution Team | Dynamic | Per-ticket agents from agent catalog |

## Escalation Path

Execution agent → Tech Lead → Company Lead → COO → Board meeting

## Agent Catalog

All agents are provisioned from the [Nexus agent catalog](https://github.com/nexus-holdings/agent-catalog).
Agent definitions, skills, and performance data live there — not in this repo.

## Conventions

- Read `wiki/WIKI.md` for full context before starting work
- Check `wiki/conventions.md` for coding standards
- All architecture decisions go in `wiki/decisions/` as ADRs
- Cross-company dependencies use `shared-modules` — no direct coupling

## Repository Layout

```
wiki/                   # Company knowledge base
  WIKI.md               # Index — load this first
  architecture.md       # System design
  conventions.md        # Coding standards + process
  domain.md             # Business context + terminology
  decisions/            # ADR-style decision log
MEMORY.md               # Claude Code AutoMemory index
.claude/memory/         # AutoDream topic files
src/                    # Source code
CLAUDE.md               # This file — company context for Claude Code
```
