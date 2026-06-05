"""
Session & spend dashboard — read-only CLI over Paperclip Postgres.

Usage:
    uv run python -m src.dashboard
    uv run python -m src.dashboard --session-days 14 --recovery-days 30
"""
from __future__ import annotations
import argparse, datetime, os, sys
from typing import Any
from .queries import (
    active_routines, agent_spend, recovery_comment_counts,
    sessions_per_company_per_day,
)
DEFAULT_DSN = "postgresql://paperclip:paperclip@127.0.0.1:54329/paperclip"

def _fmt_cents(cents):
    if not cents: return "$0.00"
    return f"${cents / 100:.2f}"

def collect(conn, *, session_days=7, recovery_days=7):
    return {
        "sessions": sessions_per_company_per_day(conn, days=session_days),
        "spend":    agent_spend(conn),
        "routines": active_routines(conn),
        "recovery": recovery_comment_counts(conn, days=recovery_days),
    }

def _table(rows, headers):
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

def _render_sessions(rows, *, file=None):
    if file is None: file = sys.stdout
    print("Sessions per Company per Day", file=file)
    if not rows:
        print("  (no data)", file=file); return
    print(_table(
        [[r["company"], str(r["day"]), f"{r['runs']:,}", f"{r['recovery_runs']:,}"] for r in rows],
        ["Company", "Day", "Runs", "Recovery"]
    ), file=file)

def _render_spend(rows, *, file=None):
    if file is None: file = sys.stdout
    print("Agent Spend (current month)", file=file)
    if not rows:
        print("  (no data)", file=file); return
    print(_table(
        [[r["company"], _fmt_cents(r["budget_cents"]), _fmt_cents(r["spent_cents"]),
          f"{r['input_tokens']:,}", f"{r['output_tokens']:,}",
          f"${float(r['cost_usd'] or 0):.4f}"] for r in rows],
        ["Company", "Budget", "Spent", "In Tokens", "Out Tokens", "Cost USD"]
    ), file=file)

def _render_routines(rows, *, file=None):
    if file is None: file = sys.stdout
    print("Active Routines", file=file)
    if not rows:
        print("  (no data)", file=file); return
    print(_table([[r["company"], r["status"], str(r["count"])] for r in rows],
                 ["Company", "Status", "Count"]), file=file)

def _render_recovery(rows, *, file=None):
    if file is None: file = sys.stdout
    print("Recovery Comments", file=file)
    if not rows:
        print("  (no data)", file=file); return
    print(_table([[r["company"], str(r["recovery_comments"])] for r in rows],
                 ["Company", "Recovery Comments"]), file=file)

def render(data, *, file=None):
    """Render all four dashboard sections to *file* (defaults to stdout)."""
    if file is None: file = sys.stdout
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'=' * 64}", file=file)
    print(f"  Nexus Observability Dashboard  [{now}]", file=file)
    print(f"{'=' * 64}\n", file=file)
    _render_sessions(data["sessions"], file=file); print(file=file)
    _render_spend(data["spend"], file=file); print(file=file)
    _render_routines(data["routines"], file=file); print(file=file)
    _render_recovery(data["recovery"], file=file)
    _render_alerts(data.get("alerts", []), file=file); print(file=file)

def _render_alerts(alerts: list[dict], *, file) -> None:
    print("=== Cap Proximity Alerts ===", file=file)
    if not alerts:
        print("  (no alerts)", file=file)
    else:
        hdr = f"  {'Level':<10} {'Company':<32} {'Metric':<8} {'Used':>7}  {'Cap':>10} {'ETA (days)':>11}"
        print(hdr, file=file)
        print(f"  {'-'*10} {'-'*32} {'-'*8} {'-'*7}  {'-'*10} {'-'*11}", file=file)
        for a in alerts:
            eta = f"{a['estimated_days_to_cap']:.1f}" if a.get("estimated_days_to_cap") is not None else "—"
            print(
                f"  {a['level'].upper():<10} {a['company']:<32} {a['metric']:<8}"
                f" {a['pct_used']:>6.1f}%  {a['cap']:>10,} {eta:>11}",
                file=file,
            )
    print(file=file)


def main(argv=None):
    p = argparse.ArgumentParser(description="Nexus platform observability dashboard")
    p.add_argument("--dsn", default=os.environ.get("PAPERCLIP_DB", DEFAULT_DSN))
    p.add_argument("--session-days", type=int, default=7, metavar="N")
    p.add_argument("--recovery-days", type=int, default=7, metavar="N")
    a = p.parse_args(argv)
    import psycopg
    try:
        with psycopg.connect(a.dsn) as conn:
            render(collect(conn, session_days=a.session_days, recovery_days=a.recovery_days))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
