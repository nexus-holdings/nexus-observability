"""Tests for check_cap_proximity() and the alert render panel."""

from __future__ import annotations

import io

import pytest

from src.queries import check_cap_proximity
from src.dashboard import _render_alerts


def _row(company: str, budget_cents: int, spent_cents: int) -> dict:
    return {
        "company": company,
        "budget_cents": budget_cents,
        "spent_cents": spent_cents,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_usd": 0.0,
    }


# ── Threshold edge cases ─────────────────────────────────────────────────────

def test_below_warn_no_alert():
    assert check_cap_proximity([_row("Acme", 10_000, 7_900)]) == []


def test_at_warn_boundary_is_warn():
    alerts = check_cap_proximity([_row("Acme", 10_000, 8_000)])
    assert len(alerts) == 1
    assert alerts[0]["level"] == "warn"


def test_between_warn_and_crit_is_warn():
    alerts = check_cap_proximity([_row("Acme", 10_000, 8_500)])
    assert len(alerts) == 1
    assert alerts[0]["level"] == "warn"
    assert alerts[0]["pct_used"] == pytest.approx(85.0)


def test_at_crit_boundary_is_critical():
    alerts = check_cap_proximity([_row("Acme", 10_000, 9_500)])
    assert len(alerts) == 1
    assert alerts[0]["level"] == "critical"


def test_above_crit_is_critical():
    alerts = check_cap_proximity([_row("Acme", 10_000, 9_700)])
    assert len(alerts) == 1
    assert alerts[0]["level"] == "critical"


def test_at_cap_is_critical():
    alerts = check_cap_proximity([_row("Acme", 10_000, 10_000)])
    assert len(alerts) == 1
    assert alerts[0]["level"] == "critical"
    assert alerts[0]["pct_used"] == pytest.approx(100.0)


# ── Alert payload fields ─────────────────────────────────────────────────────

def test_alert_fields_present():
    a = check_cap_proximity([_row("Acme", 10_000, 9_000)])[0]
    assert a["company"] == "Acme"
    assert a["metric"] == "spend"
    assert a["current"] == 9_000
    assert a["cap"] == 10_000
    assert "pct_used" in a
    assert "level" in a
    assert "estimated_days_to_cap" in a


def test_estimated_days_to_cap():
    # 8000 spent in 10 days → 800/day; 2000 remaining → 2.5 days
    alerts = check_cap_proximity([_row("Acme", 10_000, 8_000)], days_elapsed=10)
    assert alerts[0]["estimated_days_to_cap"] == pytest.approx(2.5)


def test_estimated_days_none_when_no_elapsed():
    alerts = check_cap_proximity([_row("Acme", 10_000, 8_000)], days_elapsed=0)
    assert alerts[0]["estimated_days_to_cap"] is None


def test_estimated_days_none_when_at_cap():
    # remaining == 0 → no meaningful ETA
    alerts = check_cap_proximity([_row("Acme", 10_000, 10_000)], days_elapsed=15)
    assert alerts[0]["estimated_days_to_cap"] is None


# ── Edge cases: bad / missing budget ─────────────────────────────────────────

def test_zero_budget_skipped():
    assert check_cap_proximity([_row("Free", 0, 0)]) == []


def test_none_budget_skipped():
    row = _row("Free", 0, 100)
    row["budget_cents"] = None
    assert check_cap_proximity([row]) == []


# ── Multiple companies ───────────────────────────────────────────────────────

def test_multiple_companies_mixed():
    rows = [
        _row("Safe", 10_000, 5_000),   # 50% — no alert
        _row("Warn", 10_000, 8_200),   # 82% — warn
        _row("Crit", 10_000, 9_700),   # 97% — critical
    ]
    alerts = check_cap_proximity(rows)
    assert len(alerts) == 2
    by_company = {a["company"]: a["level"] for a in alerts}
    assert by_company["Warn"] == "warn"
    assert by_company["Crit"] == "critical"


def test_custom_thresholds():
    # 70% — below default 80% but above custom 60%
    alerts = check_cap_proximity([_row("Acme", 10_000, 7_000)], warn_pct=60, crit_pct=90)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "warn"


# ── _render_alerts ───────────────────────────────────────────────────────────

def test_render_alerts_empty():
    buf = io.StringIO()
    _render_alerts([], file=buf)
    assert "(no alerts)" in buf.getvalue()


def test_render_alerts_shows_level_and_company():
    alerts = check_cap_proximity([_row("Acme", 10_000, 9_200)], days_elapsed=10)
    buf = io.StringIO()
    _render_alerts(alerts, file=buf)
    out = buf.getvalue()
    assert "WARN" in out or "CRITICAL" in out
    assert "Acme" in out
    assert "spend" in out
