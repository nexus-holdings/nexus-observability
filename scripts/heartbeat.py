#!/usr/bin/env python3
"""Heartbeat: scan Nexus Observability backlog and spawn agents.

Picks the highest-priority eligible ticket and spawns an agent on it,
subject to the session cap and spawn cooldown.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

PAPERCLIP_API_URL = os.environ.get("PAPERCLIP_API_URL", "http://localhost:3000")
PAPERCLIP_API_KEY = os.environ.get("PAPERCLIP_API_KEY", "")
COMPANY_ID = os.environ.get("PAPERCLIP_COMPANY_ID", "")

DEFAULT_SESSION_CAP = 2
DEFAULT_COOLDOWN_SECONDS = 60

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
TERMINAL_STATUSES = {"done", "cancelled"}
IN_PROGRESS_STATUS = "in_progress"
TODO_STATUS = "todo"


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _api_headers(api_key: str = "") -> dict:
    key = api_key or PAPERCLIP_API_KEY
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def fetch_issues(
    company_id: str,
    status_csv: str = "todo,in_progress",
    api_url: str = "",
    api_key: str = "",
) -> list[dict]:
    """Return issues from Paperclip API for *company_id*."""
    base = api_url or PAPERCLIP_API_URL
    cid = company_id or COMPANY_ID
    params = urllib.parse.urlencode({"status": status_csv})
    url = f"{base}/api/companies/{cid}/issues?{params}"
    req = urllib.request.Request(url, headers=_api_headers(api_key))
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Eligibility logic
# ---------------------------------------------------------------------------

_DEP_RE = re.compile(
    r"(?:depends[-_ ]?on|depends):\s*([A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)*)",
    re.IGNORECASE,
)
_AFTER_LABEL_RE = re.compile(r"after:([A-Z]+-\d+)", re.IGNORECASE)


def extract_dependencies(issue: dict) -> set[str]:
    """Return set of issue identifiers that *issue* declares as dependencies."""
    desc = issue.get("description") or ""
    deps: set[str] = set()

    for m in _DEP_RE.finditer(desc):
        for raw in re.split(r"[\s,]+", m.group(1)):
            ident = raw.strip()
            if ident:
                deps.add(ident.upper())

    for label in issue.get("labels") or []:
        m2 = _AFTER_LABEL_RE.match(label.get("name", ""))
        if m2:
            deps.add(m2.group(1).upper())

    return deps


def is_eligible(
    issue: dict,
    issues_by_identifier: dict[str, dict],
    heartbeat_issue_id: str | None = None,
) -> bool:
    """Return True if *issue* may be picked up by the heartbeat."""
    if issue.get("status") != TODO_STATUS:
        return False

    if issue.get("assigneeAgentId") or issue.get("assigneeUserId"):
        return False

    if heartbeat_issue_id and issue.get("id") == heartbeat_issue_id:
        return False

    for blocker in issue.get("blockedBy") or []:
        if blocker.get("status") not in TERMINAL_STATUSES:
            return False

    for dep_id in extract_dependencies(issue):
        dep = issues_by_identifier.get(dep_id)
        if dep is None or dep.get("status") not in TERMINAL_STATUSES:
            return False

    return True


# ---------------------------------------------------------------------------
# Session-cap / cooldown checks
# ---------------------------------------------------------------------------

def count_in_progress(
    issues: list[dict],
    heartbeat_issue_id: str | None = None,
) -> int:
    """Count in-progress tickets, excluding the heartbeat ticket itself."""
    return sum(
        1
        for i in issues
        if i.get("status") == IN_PROGRESS_STATUS
        and i.get("id") != heartbeat_issue_id
    )


def within_cooldown(
    issues: list[dict],
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    now: datetime.datetime | None = None,
) -> bool:
    """Return True if a spawn happened more recently than *cooldown_seconds* ago.

    Uses `startedAt` (or `createdAt` as fallback) on in-progress tickets to
    estimate the last spawn time.
    """
    in_progress = [i for i in issues if i.get("status") == IN_PROGRESS_STATUS]
    if not in_progress:
        return False

    timestamps = []
    for i in in_progress:
        ts = i.get("startedAt") or i.get("createdAt")
        if ts:
            timestamps.append(ts)

    if not timestamps:
        return False

    latest_str = max(timestamps)
    try:
        started = datetime.datetime.fromisoformat(latest_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return False

    reference = now or datetime.datetime.now(datetime.timezone.utc)
    elapsed = (reference - started).total_seconds()
    return elapsed < cooldown_seconds


# ---------------------------------------------------------------------------
# Priority sort
# ---------------------------------------------------------------------------

def sort_by_priority(issues: list[dict]) -> list[dict]:
    """Sort *issues* by priority (critical first) then creation time (oldest first)."""
    return sorted(
        issues,
        key=lambda i: (
            PRIORITY_ORDER.get(i.get("priority") or "low", 99),
            i.get("createdAt") or "",
        ),
    )


# ---------------------------------------------------------------------------
# Agent spawning
# ---------------------------------------------------------------------------

def spawn_agent(
    issue: dict,
    dry_run: bool = False,
    runner: object = None,
) -> bool:
    """Spawn an agent on *issue* via the paperclipai CLI.

    *runner* is injectable for testing; must expose `.run(cmd, **kwargs)`.
    """
    identifier = issue.get("identifier") or issue.get("id", "?")
    title = issue.get("title", "")

    if dry_run:
        print(f"[dry-run] Would spawn agent on {identifier}: {title}")
        return True

    cmd = ["paperclipai", "heartbeat", "trigger", "--issue-id", issue["id"]]
    run_fn = runner if runner is not None else subprocess.run
    result = run_fn(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"ERROR: spawn failed for {identifier}: {result.stderr}",
            file=sys.stderr,
        )
        return False

    print(f"Spawned agent on {identifier}: {title}")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(
    *,
    dry_run: bool = False,
    session_cap: int = DEFAULT_SESSION_CAP,
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
    company_id: str = "",
    heartbeat_issue_id: str | None = None,
    api_url: str = "",
    api_key: str = "",
    runner: object = None,
    _now: datetime.datetime | None = None,
    _issues: list[dict] | None = None,
) -> int:
    """Core heartbeat logic. Returns an exit code."""
    if _issues is not None:
        issues = _issues
    else:
        try:
            issues = fetch_issues(
                company_id=company_id or COMPANY_ID,
                api_url=api_url,
                api_key=api_key,
            )
        except (urllib.error.URLError, Exception) as exc:
            print(f"ERROR fetching issues: {exc}", file=sys.stderr)
            return 1

    by_identifier: dict[str, dict] = {
        i["identifier"]: i for i in issues if i.get("identifier")
    }

    active = count_in_progress(issues, heartbeat_issue_id=heartbeat_issue_id)
    if active >= session_cap:
        print(
            f"Session cap reached: {active}/{session_cap} in progress. "
            "Skipping spawn."
        )
        return 0

    if within_cooldown(issues, cooldown_seconds=cooldown_seconds, now=_now):
        print(
            f"Spawn cooldown active (last spawn < {cooldown_seconds}s ago). "
            "Skipping spawn."
        )
        return 0

    eligible = [
        i
        for i in issues
        if is_eligible(i, by_identifier, heartbeat_issue_id=heartbeat_issue_id)
    ]

    if not eligible:
        print("No eligible tickets found.")
        return 0

    candidates = sort_by_priority(eligible)
    pick = candidates[0]
    priority = (pick.get("priority") or "low").upper()
    print(
        f"Picking: [{priority}] {pick.get('identifier', '?')}: {pick.get('title', '')}"
    )

    ok = spawn_agent(pick, dry_run=dry_run, runner=runner)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Heartbeat: scan backlog and spawn agents"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended action without making API calls or spawning agents",
    )
    parser.add_argument(
        "--session-cap",
        type=int,
        default=int(os.environ.get("NEXUS_SESSION_CAP", DEFAULT_SESSION_CAP)),
        metavar="N",
        help=f"Max concurrent in-progress sessions (default: {DEFAULT_SESSION_CAP})",
    )
    parser.add_argument(
        "--cooldown",
        type=int,
        default=DEFAULT_COOLDOWN_SECONDS,
        metavar="SECS",
        help=f"Seconds since last spawn before another is allowed (default: {DEFAULT_COOLDOWN_SECONDS})",
    )
    parser.add_argument(
        "--company-id",
        default=os.environ.get("PAPERCLIP_COMPANY_ID", COMPANY_ID),
        help="Paperclip company ID",
    )
    parser.add_argument(
        "--heartbeat-issue-id",
        default=os.environ.get("PAPERCLIP_TASK_ID"),
        help="Issue ID of this heartbeat ticket (excluded from cap count)",
    )
    args = parser.parse_args(argv)

    return run(
        dry_run=args.dry_run,
        session_cap=args.session_cap,
        cooldown_seconds=args.cooldown,
        company_id=args.company_id,
        heartbeat_issue_id=args.heartbeat_issue_id,
    )


if __name__ == "__main__":
    sys.exit(main())
