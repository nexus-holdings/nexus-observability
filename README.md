# {Company Name}

> Part of the Nexus Holdings platform.

## Mission

<!-- One-sentence mission statement -->

## Quick Start

1. Read `wiki/WIKI.md` for full context
2. Check the GitHub Project for current milestones and tickets
3. Review `wiki/conventions.md` before writing any code

## Structure

```
wiki/                   # Company knowledge base
  WIKI.md               # Index — load this first
  architecture.md       # System design
  conventions.md        # Coding standards + process
  domain.md             # Business context + terminology
  decisions/            # ADR-style decision log
MEMORY.md               # Claude Code AutoMemory index
.claude/memory/         # AutoDream topic files (session learnings)
src/                    # Source code
```

## Agents

This company uses agents provisioned from the [Nexus agent catalog](https://github.com/nexus-holdings/agent-catalog).
All agent definitions, skills, and performance data live there — not here.

## Escalation

Execution agent → Tech Lead → Company Lead → COO → Board meeting
