"""SQL query functions for the Nexus Observability dashboard."""

import datetime


def sessions_per_company_per_day(conn, days: int = 7) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.name, DATE(hr.started_at AT TIME ZONE 'UTC') AS day, COUNT(*) AS sessions
        FROM heartbeat_runs hr
        JOIN companies c ON c.id = hr.company_id
        WHERE hr.started_at >= NOW() - %s
        GROUP BY c.name, day
        ORDER BY day DESC, sessions DESC
        """,
        [datetime.timedelta(days=days)],
    ).fetchall()
    return [{"company": r[0], "day": r[1], "sessions": r[2]} for r in rows]


def company_spend(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT name, budget_monthly_cents, spent_monthly_cents
        FROM companies
        WHERE status != 'archived'
        ORDER BY name
        """
    ).fetchall()
    return [{"company": r[0], "budget_cents": r[1], "spent_cents": r[2]} for r in rows]


def active_routines(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.name, r.title, r.priority, r.last_triggered_at
        FROM routines r
        JOIN companies c ON c.id = r.company_id
        WHERE r.status = 'active'
        ORDER BY r.last_triggered_at DESC NULLS LAST
        """
    ).fetchall()
    return [
        {"company": r[0], "title": r[1], "priority": r[2], "last_triggered_at": r[3]}
        for r in rows
    ]


def recovery_comment_counts(conn, days: int = 30) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.name, COUNT(*) AS recovery_count
        FROM issue_comments ic
        JOIN companies c ON c.id = ic.company_id
        WHERE ic.body ILIKE %s
          AND ic.created_at >= NOW() - %s
        GROUP BY c.name
        ORDER BY recovery_count DESC
        """,
        ["%recovery%", datetime.timedelta(days=days)],
    ).fetchall()
    return [{"company": r[0], "recovery_count": r[1]} for r in rows]
