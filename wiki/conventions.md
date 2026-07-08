# Conventions

> Placeholder — populate when company is provisioned.

## Code Style

<!-- Language-specific style guides, linters, formatters -->

## Naming

<!-- Variable, file, branch, PR naming conventions -->

## Git Workflow

<!-- Branch strategy, commit message format, PR process -->

## Testing

<!-- Test coverage expectations, testing frameworks, test naming -->

## Review Process

<!-- Who reviews, what triggers review, approval criteria -->


## Escalating to a human

When you genuinely need a human decision (ambiguous requirements, a failed
automated step you cannot safely retry, permission to deviate from the
ticket), use the interactions API — do NOT invent request shapes:

```
POST /api/issues/<issue-id>/interactions
{
  "kind": "request_confirmation",
  "idempotencyKey": "<stable-key-per-question>",
  "title": "<one line, ≤240 chars>",
  "summary": "<optional, ≤1000 chars>",
  "continuationPolicy": "wake_assignee",
  "payload": {
    "version": 1,
    "prompt": "<the yes/no question, ≤1000 chars>",
    "detailsMarkdown": "<optional longer context, ≤20000 chars>",
    "acceptLabel": "approve",
    "rejectLabel": "reject"
  }
}
```

The `payload.version: 1` and `payload.prompt` fields are mandatory — a 400
means your shape is wrong, not that escalation is unavailable. One
escalation per question (the idempotencyKey enforces this); never loop on
a 400 — post a plain comment instead and mark the ticket `blocked`.
