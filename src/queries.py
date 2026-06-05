"""
Read-only SQL queries against the Paperclip Postgres database.

Each function accepts a DB-API 2.0 connection and returns plain dicts
so callers can format or test without a live database.
"""

from __future__ import annotations

from typing import Any


def sessions_per_company_per_day(conn: Any, days: int = 7) -> list[dict]:
    """Heartbeat runs grouped by company and calendar day."""
    sql = """
        SELECT
            c.name                                      AS company,
            DATE(hr.started_at AT TIME ZONE 'UTC')   AS day,
            COUNT(*)                                    AS runs,
            COUNT(hr.retry_of_run_id)                  AS recovery_runs
        FROM heartbeat_runs hr
        JOIN companies c ON c.id = hr.company_id
        WHERE hr.started_at >= NOW() - (%(days)s || ' days')::interval
        GROUP BY c.name, day
        ORDER BY day DESC, runs DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"days": days})
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def agent_spend(conn: Any) -> list[dict]:
    """Per-company spend: budget/spent cents + token totals for current month."""
    sql = """
        SELECT
            c.name                                          AS company,
            c.budget_monthly_cents                          AS budget_cents,
            c.spent_monthly_cents                           AS spent_cents,
            COALESCE(t.input_tokens,  0)                   AS input_tokens,
            COALESCE(t.output_tokens, 0)                   AS output_tokens,
            COALESCE(t.cost_usd,      0)                   AS cost_usd
        FROM companies c
        LEFT JOIN (
            SELECT
                company_id,
                SUM((usage_json->>'inputTokens' )::bigint)  AS input_tokens,
                SUM((usage_json->>'outputTokens')::bigint)  AS output_tokens,
                SUM((usage_json->>'costUsd'     )::numeric) AS cost_usd
            FROM heartbeat_runs
            WHERE usage_json IS NOT NULL
              AND started_at >= DATE_TRUNC('month', NOW())
            GROUP BY company_id
        ) t ON t.company_id = c.id
        ORDER BY c.name
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def active_routines(conn: Any) -> list[dict]:
    """Non-archived routines grouped by company and status."""
    sql = """
        SELECT
            c.name   AS company,
            r.status AS status,
            COUNT(*) AS count
        FROM routines r
        JOIN companies c ON c.id = r.company_id
        WHERE r.status != 'archived'
        GROUP BY c.name, r.status
        ORDER BY c.name, r.status
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def recovery_comment_counts(conn: Any, days: int = 7) -> list[dict]:
    """Issue comments mentioning recovery/retry, grouped by company."""
    sql = """
        SELECT
            c.name       AS company,
            COUNT(ic.id) AS recovery_comments
        FROM issue_comments ic
        JOIN companies c ON c.id = ic.company_id
        WHERE ic.created_at >= NOW() - (%(days)s || ' days')::interval
          AND (
                ic.body ILIKE '%%recovery%%'
             OR ic.body ILIKE '%%retry%%'
             OR ic.body ILIKE '%%recover%%'
          )
        GROUP BY c.name
        ORDER BY recovery_comments DESC
    """
    with conn.cursor() as cur:
        cur.execute(sql, {"days": days})
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def check_cap_proximity(
    spend_rows: list[dict],
    warn_pct: float = 80,
    crit_pct: float = 95,
    days_elapsed: int | None = None,
) -> list[dict]:
    """Return alert dicts for companies near their monthly budget cap.

    Compares each company's spent_cents against budget_cents.  Returns an
    alert dict for every company at or above warn_pct.  Skips companies with
    zero or missing budget.

    Args:
        spend_rows:    Output of agent_spend().
        warn_pct:      Percentage threshold for a warn-level alert (default 80).
        crit_pct:      Percentage threshold for a critical-level alert (default 95).
        days_elapsed:  Days into the month for burn-rate projection.  Defaults
                       to the current calendar day when None.

    Returns:
        List of dicts with keys: company, metric, current, cap, pct_used,
        level ('warn' | 'critical'), estimated_days_to_cap (float | None).
    """
    import datetime

    if days_elapsed is None:
        days_elapsed = datetime.datetime.now().day

    alerts = []
    for row in spend_rows:
        budget = row.get("budget_cents") or 0
        spent = row.get("spent_cents") or 0
        if budget <= 0:
            continue
        pct = (spent / budget) * 100
        if pct < warn_pct:
            continue

        level = "critical" if pct >= crit_pct else "warn"

        estimated_days: float | None = None
        if days_elapsed > 0 and spent > 0:
            daily_rate = spent / days_elapsed
            remaining = budget - spent
            if daily_rate > 0 and remaining > 0:
                estimated_days = remaining / daily_rate

        alerts.append(
            {
                "company": row["company"],
                "metric": "spend",
                "current": spent,
                "cap": budget,
                "pct_used": pct,
                "level": level,
                "estimated_days_to_cap": estimated_days,
            }
        )

    return alerts


def check_cap_proximity(
    spend: list[dict],
    warn_pct: float = 80,
    crit_pct: float = 95,
) -> list[dict]:
    """Return alert dicts for companies approaching their monthly budget cap."""
    alerts = []
    for row in spend:
        budget = row.get("budget_cents") or 0
        if budget <= 0:
            continue
        spent = row.get("spent_cents") or 0
        pct = spent / budget * 100
        if pct >= warn_pct:
            level = "crit" if pct >= crit_pct else "warn"
            alerts.append({
                "company": row["company"],
                "metric": "monthly spend",
                "level": level,
                "pct_used": pct,
                "current": spent,
                "cap": budget,
                "estimated_days_to_cap": None,
            })
    return alerts
