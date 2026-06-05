"""
Session & spend dashboard — read-only CLI over Paperclip Postgres.

Usage:
    uv run python -m src.dashboard
    uv run python -m src.dashboard --session-days 14 --recovery-days 30
    PAPERCLIP_DB=postgresql://... uv run python -m src.dashboard
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from typing import Any

from .queries import (
    active_routines,
    agent_spend,
    recovery_comment_counts,
    sessions_per_company_per_day,
)

DEFAULT_DSN = "postgresql://paperclip:paperclip@127.0.0.1:54329/paperclip"


def _fmt_cents(cents: int | None) -> str:
    if not cents:
        return "$0.00"
    return f"${cents / 100:.2f}"


def collect(conn: Any, *, session_days: int = 7, recovery_days: int = 7) -> dict:
    """Run all four queries; return a dict keyed by section name."""
    return {
        "sessions": sessions_per_company_per_day(conn, days=session_days),
        "spend":    agent_spend(conn),
        "routines": active_routines(conn),
        "recovery": recovery_comment_counts(conn, days=recovery_days),
    }


def _table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    sep  = "  ".join("-" * w for w in widths)
    head = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    lines = [head, sep]
    for row in rows:
        lines.append("  ".join(str(c).ljust(w) for c, w in zip(row, widths)))
    return "\n".join(lines)


def _render_sessions(rows: list[dict], *, file=None) -> None:
    if file is None:
        file = sys.stdout
    print("Sessions per Company per Day", file=file)
    if not rows:
        print("  (no data)", file=file)
        return
    table_rows = [
        [r["company"], str(r["day"]), f"{r['runs']:,}", f"{r['recovery_runs']:,}"]
        for r in rows
    ]
    print(_table(table_rows, ["Company", "Day", "Runs", "Recovery"]), file=file)


def _render_spend(rows: list[dict], *, file=None) -> None:
    if file is None:
        file = sys.stdout
    print("Agent Spend (current month)", file=file)
    if not rows:
        print("  (no data)", file=file)
        return
    table_rows = [
        [
            r["company"],
            _fmt_cents(r["budget_cents"]),
            _fmt_cents(r["spent_cents"]),
            f"{r['input_tokens']:,}",
            f"{r['output_tokens']:,}",
            f"${float(r['cost_usd'] or 0):.4f}",
        ]
        for r in rows
    ]
    print(
        _table(table_rows, ["Company", "Budget", "Spent", "In Tokens", "Out Tokens", "Cost USD"]),
        file=file,
    )


def _render_routines(rows: list[dict], *, file=None) -> None:
    if file is None:
        file = sys.stdout
    print("Active Routines", file=file)
    if not rows:
        print("  (no data)", file=file)
        return
    table_rows = [[r["company"], r["status"], str(r["count"])] for r in rows]
    print(_table(table_rows, ["Company", "Status", "Count"]), file=file)


def _render_recovery(rows: list[dict], *, file=None) -> None:
    if file is None:
        file = sys.stdout
    print("Recovery Comments", file=file)
    if not rows:
        print("  (no data)", file=file)
        return
    table_rows = [[r["company"], str(r["recovery_comments"])] for r in rows]
    print(_table(table_rows, ["Company", "Recovery Comments"]), file=file)


def render(data: dict, *, file=None) -> None:
    """Render all four sections to *file* (defaults to stdout)."""
    if file is None:
        file = sys.stdout
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'=' * 64}", file=file)
    print(f"  Nexus Observability Dashboard  [{now}]", file=file)
    print(f"{'=' * 64}\n", file=file)
    _render_sessions(data["sessions"], file=file)
    print(file=file)
    _render_spend(data["spend"], file=file)
    print(file=file)
    _render_routines(data["routines"], file=file)
    print(file=file)
    _render_recovery(data["recovery"], file=file)
    print(file=file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nexus platform observability dashboard")
    parser.add_argument("--dsn", default=os.environ.get("PAPERCLIP_DB", DEFAULT_DSN))
    parser.add_argument("--session-days", type=int, default=7, metavar="N",
                        help="Lookback for sessions in days (default: 7)")
    parser.add_argument("--recovery-days", type=int, default=7, metavar="N",
                        help="Lookback for recovery comments in days (default: 7)")
    args = parser.parse_args(argv)

    import psycopg
    try:
        with psycopg.connect(args.dsn) as conn:
            data = collect(conn, session_days=args.session_days, recovery_days=args.recovery_days)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    render(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
