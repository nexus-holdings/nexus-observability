"""
Read-only SQL queries against the Paperclip Postgres database.

Each function accepts a DB-API 2.0 connection and returns plain dicts
so callers can format or test without a live database.
"""

from __future__ import annotations

from typing import Any


def _rows_to_dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


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
        return _rows_to_dicts(cur)


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
        return _rows_to_dicts(cur)


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
        return _rows_to_dicts(cur)


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
        return _rows_to_dicts(cur)
