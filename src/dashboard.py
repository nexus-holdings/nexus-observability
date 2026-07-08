"""Session & spend dashboard — read-only CLI over Paperclip Postgres."""

from __future__ import annotations

import argparse
import datetime
import decimal
import json
import os
import sys
from typing import Any

from src import queries

DEFAULT_DSN = "postgresql://paperclip:paperclip@127.0.0.1:54329/paperclip"


def _connect(dsn: str):
    import psycopg
    return psycopg.connect(dsn)


def _fmt_cents(cents: int | None) -> str:
    if not cents:
        return "$0.00"
    return f"${cents / 100:.2f}"


def _json_default(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def collect(conn: Any, *, days: int = 7) -> dict:
    """Run all queries and return results keyed by section name."""
    spend = queries.agent_spend(conn)
    return {
        "sessions":   queries.sessions_per_company_per_day(conn, days=days),
        "spend":      spend,
        "routines":   queries.active_routines(conn),
        "recovery":   queries.recovery_comment_counts(conn, days=days),
        "cap_alerts": queries.check_cap_proximity(spend),
    }


def render(data: dict, *, file=None) -> None:
    """Print all dashboard sections to *file* (defaults to stdout)."""
    if file is None:
        file = sys.stdout
    cap_alerts = data.get("cap_alerts", [])
    if cap_alerts:
        _render_cap_alerts(cap_alerts, file=file)
    _render_sessions(data["sessions"], file=file)
    _render_spend(data["spend"], file=file)
    _render_routines(data["routines"], file=file)
    _render_recovery(data["recovery"], file=file)


def render_json(data: dict, *, file=None) -> None:
    """Print the report as a single JSON object to *file* (defaults to stdout)."""
    if file is None:
        file = sys.stdout
    print(json.dumps(data, default=_json_default), file=file)


def _render_cap_alerts(alerts: list[dict], *, file) -> None:
    print("=== !! VOLUME CAP PROXIMITY ALERTS ===", file=file)
    for a in alerts:
        level_tag = "[CRITICAL]" if a["level"] == "critical" else "[WARN]   "
        eta = a["estimated_days_to_cap"]
        eta_str = f"  →  ETA {eta:.1f}d" if eta is not None else ""
        print(
            f"  {level_tag} {a['company']:<32} {a['pct_used']:5.1f}%"
            f"  ({_fmt_cents(a['current'])} / {_fmt_cents(a['cap'])}){eta_str}",
            file=file,
        )
    print(file=file)


def _render_sessions(rows: list[dict], *, file) -> None:
    print("=== Sessions per Company per Day (last N days) ===", file=file)
    if not rows:
        print("  (no data)", file=file)
    else:
        print(f"  {'Company':<32} {'Day':<12} {'Runs':>6}  {'Recovery':>9}", file=file)
        print(f"  {'-'*32} {'-'*12} {'-'*6}  {'-'*9}", file=file)
        for r in rows:
            print(
                f"  {r['company']:<32} {str(r['day']):<12}"
                f" {int(r['runs']):>6,}  {int(r['recovery_runs']):>9,}",
                file=file,
            )
    print(file=file)


def _render_spend(rows: list[dict], *, file) -> None:
    print("=== Agent Spend (current month) ===", file=file)
    if not rows:
        print("  (no data)", file=file)
    else:
        print(
            f"  {'Company':<32} {'Budget':>10} {'Spent':>10}"
            f" {'In tok':>10} {'Out tok':>10} {'Cost USD':>10}",
            file=file,
        )
        print(
            f"  {'-'*32} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}",
            file=file,
        )
        for r in rows:
            print(
                f"  {r['company']:<32}"
                f" {_fmt_cents(r['budget_cents']):>10}"
                f" {_fmt_cents(r['spent_cents']):>10}"
                f" {int(r['input_tokens']):>10,}"
                f" {int(r['output_tokens']):>10,}"
                f" ${float(r['cost_usd'] or 0):>9.2f}",
                file=file,
            )
    print(file=file)


def _render_routines(rows: list[dict], *, file) -> None:
    print("=== Active Routines ===", file=file)
    if not rows:
        print("  (no data)", file=file)
    else:
        print(f"  {'Company':<32} {'Status':<14} {'Count':>6}", file=file)
        print(f"  {'-'*32} {'-'*14} {'-'*6}", file=file)
        for r in rows:
            print(
                f"  {r['company']:<32} {r['status']:<14} {int(r['count']):>6,}",
                file=file,
            )
    print(file=file)


def _render_recovery(rows: list[dict], *, file) -> None:
    print("=== Recovery Comments (last N days) ===", file=file)
    if not rows:
        print("  (no data)", file=file)
    else:
        print(f"  {'Company':<32} {'Recovery Comments':>18}", file=file)
        print(f"  {'-'*32} {'-'*18}", file=file)
        for r in rows:
            print(
                f"  {r['company']:<32} {int(r['recovery_comments']):>18,}",
                file=file,
            )
    print(file=file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Nexus Observability: session & spend dashboard"
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("PAPERCLIP_DB", DEFAULT_DSN),
        help="Paperclip Postgres DSN",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Lookback window in days (default: 7)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output report as a single JSON object instead of formatted text",
    )
    args = parser.parse_args(argv)

    conn = _connect(args.dsn)
    try:
        data = collect(conn, days=args.days)
    finally:
        conn.close()

    if args.json_output:
        render_json(data)
    else:
        render(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
