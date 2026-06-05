"""Read-only SQL queries for the Nexus Observability dashboard.

Each function accepts a DB-API 2.0 connection and returns plain dicts keyed
by the SELECT column aliases, so callers can format or test without a live DB.
check_cap_proximity() is a pure function — no connection needed.
"""

from __future__ import annotations


def _dict_rows(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def sessions_per_company_per_day(conn, days: int = 7) -> list[dict]:
    """Heartbeat run counts per company per UTC day.

    recovery_runs = retried or continuation runs (churn signal).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.name AS company,
                   DATE(hr.started_at AT TIME ZONE 'UTC') AS day,
                   COUNT(*) AS runs,
                   COUNT(*) FILTER (
                     WHERE hr.retry_of_run_id IS NOT NULL
                        OR COALESCE(hr.continuation_attempt, 0) > 0
                   ) AS recovery_runs
            FROM heartbeat_runs hr
            JOIN companies c ON c.id = hr.company_id
            WHERE hr.started_at >= NOW() - make_interval(days => %s)
            GROUP BY c.name, day
            ORDER BY day DESC, runs DESC
            """,
            (days,),
        )
        return _dict_rows(cur)


def agent_spend(conn) -> list[dict]:
    """Per-company budgets vs spend plus lifetime token/cost totals."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.name AS company,
                   c.budget_monthly_cents AS budget_cents,
                   c.spent_monthly_cents  AS spent_cents,
                   COALESCE(SUM(ce.input_tokens),  0) AS input_tokens,
                   COALESCE(SUM(ce.output_tokens), 0) AS output_tokens,
                   COALESCE(SUM(ce.cost_cents), 0) / 100.0 AS cost_usd
            FROM companies c
            LEFT JOIN cost_events ce ON ce.company_id = c.id
            WHERE c.status != 'archived'
            GROUP BY c.id, c.name
            ORDER BY c.name
            """
        )
        return _dict_rows(cur)


def active_routines(conn) -> list[dict]:
    """Routine counts per company per status (paused/active posture)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.name AS company, r.status, COUNT(*) AS count
            FROM routines r
            JOIN companies c ON c.id = r.company_id
            GROUP BY c.name, r.status
            ORDER BY c.name, r.status
            """
        )
        return _dict_rows(cur)


def recovery_comment_counts(conn, days: int = 30) -> list[dict]:
    """Orphan-recovery and retry comments per company (noise / churn signal)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.name AS company, COUNT(*) AS recovery_comments
            FROM issue_comments ic
            JOIN companies c ON c.id = ic.company_id
            WHERE ic.body ILIKE %s
              AND ic.created_at >= NOW() - make_interval(days => %s)
            GROUP BY c.name
            ORDER BY recovery_comments DESC
            """,
            ("%recovery%", days),
        )
        return _dict_rows(cur)


def check_cap_proximity(
    spend_rows: list[dict],
    warn_pct: float = 80,
    crit_pct: float = 95,
    days_elapsed: int | None = None,
) -> list[dict]:
    """Return alert dicts for companies near their monthly budget cap.

    Skips companies with zero or missing budget.  Returns one dict per
    company at or above *warn_pct*, keyed:
      company, metric, current, cap, pct_used,
      level ('warn' | 'critical'), estimated_days_to_cap (float | None).

    days_elapsed: days elapsed in the billing period — used to compute burn
    rate and ETA.  Pass 0 or omit to skip ETA calculation.
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

        eta: float | None = None
        if days_elapsed > 0 and spent > 0:
            daily_rate = spent / days_elapsed
            remaining = budget - spent
            if daily_rate > 0 and remaining > 0:
                eta = remaining / daily_rate

        alerts.append(
            {
                "company": row["company"],
                "metric": "spend",
                "current": spent,
                "cap": budget,
                "pct_used": pct,
                "level": level,
                "estimated_days_to_cap": eta,
            }
        )
    return alerts
