"""
Tests for dashboard rendering and query plumbing.

Query functions are tested via a FakeConn / FakeCursor that returns
pre-canned rows — no live database required.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import date
from decimal import Decimal

import pytest

sys.path.insert(0, ".")

from src.queries import (
    active_routines,
    agent_spend,
    guard_activity,
    recovery_comment_counts,
    sessions_per_company_per_day,
)
from src.dashboard import (
    _fmt_cents,
    render,
    render_json,
    _render_sessions,
    _render_spend,
    _render_routines,
    _render_recovery,
    _render_guard_activity,
)


# ---------------------------------------------------------------------------
# Fake DB helpers
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, rows, cols):
        self._rows = rows
        self.description = [(c,) for c in cols]

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class FakeConn:
    """Returns the same rows/cols for every cursor() call."""
    def __init__(self, rows, cols):
        self._rows = rows
        self._cols = cols

    def cursor(self):
        return FakeCursor(self._rows, self._cols)


class MultiConn:
    """Returns a different FakeCursor per call, in order."""
    def __init__(self, responses):
        # responses: list of (rows, cols) tuples
        self._responses = iter(responses)

    def cursor(self):
        rows, cols = next(self._responses)
        return FakeCursor(rows, cols)


# ---------------------------------------------------------------------------
# Query function tests
# ---------------------------------------------------------------------------

def test_sessions_per_company_per_day_returns_dicts():
    rows = [("Acme Corp", date(2026, 6, 4), 42, 5)]
    cols = ["company", "day", "runs", "recovery_runs"]
    result = sessions_per_company_per_day(FakeConn(rows, cols), days=7)
    assert len(result) == 1
    assert result[0]["company"] == "Acme Corp"
    assert result[0]["runs"] == 42
    assert result[0]["recovery_runs"] == 5


def test_agent_spend_returns_dicts():
    rows = [("Acme Corp", 10000, 3500, 1200000, 95000, 0.0)]
    cols = ["company", "budget_cents", "spent_cents", "input_tokens", "output_tokens", "cost_usd"]
    result = agent_spend(FakeConn(rows, cols))
    assert result[0]["budget_cents"] == 10000
    assert result[0]["input_tokens"] == 1200000


def test_active_routines_returns_dicts():
    rows = [("Acme Corp", "paused", 3), ("Acme Corp", "active", 1)]
    cols = ["company", "status", "count"]
    result = active_routines(FakeConn(rows, cols))
    assert len(result) == 2
    assert result[1]["status"] == "active"


def test_recovery_comment_counts_returns_dicts():
    rows = [("Nexus Memory", 874)]
    cols = ["company", "recovery_comments"]
    result = recovery_comment_counts(FakeConn(rows, cols), days=7)
    assert result[0]["recovery_comments"] == 874


def test_guard_activity_returns_dicts():
    rows = [(date(2026, 7, 10), "Acme Corp", "cancelled", 4)]
    cols = ["day", "company", "status", "count"]
    result = guard_activity(FakeConn(rows, cols), days=7)
    assert result[0]["company"] == "Acme Corp"
    assert result[0]["status"] == "cancelled"
    assert result[0]["count"] == 4


# ---------------------------------------------------------------------------
# _fmt_cents
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cents,expected", [
    (0,    "$0.00"),
    (None, "$0.00"),
    (100,  "$1.00"),
    (9999, "$99.99"),
])
def test_fmt_cents(cents, expected):
    assert _fmt_cents(cents) == expected


# ---------------------------------------------------------------------------
# render helpers
# ---------------------------------------------------------------------------

def test_render_sessions_empty():
    buf = io.StringIO()
    _render_sessions([], file=buf)
    assert "(no data)" in buf.getvalue()


def test_render_sessions_rows():
    rows = [{"company": "Nexus Memory", "day": date(2026, 6, 3), "runs": 6450, "recovery_runs": 2240}]
    buf = io.StringIO()
    _render_sessions(rows, file=buf)
    out = buf.getvalue()
    assert "Nexus Memory" in out
    assert "6,450" in out
    assert "2,240" in out


def test_render_spend_empty():
    buf = io.StringIO()
    _render_spend([], file=buf)
    assert "(no data)" in buf.getvalue()


def test_render_spend_rows():
    rows = [{
        "company": "Acme Corp",
        "budget_cents": 50000,
        "spent_cents": 12000,
        "input_tokens": 500000,
        "output_tokens": 42000,
        "cost_usd": 0.0,
    }]
    buf = io.StringIO()
    _render_spend(rows, file=buf)
    out = buf.getvalue()
    assert "Acme Corp" in out
    assert "$500.00" in out
    assert "$120.00" in out


def test_render_routines_empty():
    buf = io.StringIO()
    _render_routines([], file=buf)
    assert "(no data)" in buf.getvalue()


def test_render_routines_rows():
    rows = [{"company": "Acme", "status": "paused", "count": 3}]
    buf = io.StringIO()
    _render_routines(rows, file=buf)
    out = buf.getvalue()
    assert "paused" in out
    assert "3" in out


def test_render_recovery_empty():
    buf = io.StringIO()
    _render_recovery([], file=buf)
    assert "(no data)" in buf.getvalue()


def test_render_recovery_rows():
    rows = [{"company": "Nexus Memory", "recovery_comments": 874}]
    buf = io.StringIO()
    _render_recovery(rows, file=buf)
    out = buf.getvalue()
    assert "Nexus Memory" in out
    assert "874" in out


# ---------------------------------------------------------------------------
# _render_guard_activity
# ---------------------------------------------------------------------------

def test_render_guard_activity_empty():
    buf = io.StringIO()
    _render_guard_activity([], file=buf)
    assert "(no data)" in buf.getvalue()


def test_render_guard_activity_normal_mix():
    rows = [
        {"day": date(2026, 7, 10), "company": "Acme Corp", "status": "succeeded", "count": 40},
        {"day": date(2026, 7, 10), "company": "Acme Corp", "status": "cancelled", "count": 3},
        {"day": date(2026, 7, 10), "company": "Acme Corp", "status": "failed", "count": 1},
    ]
    buf = io.StringIO()
    _render_guard_activity(rows, file=buf)
    out = buf.getvalue()
    assert "Acme Corp" in out
    assert "40" in out
    assert "!!" not in out


def test_render_guard_activity_all_cancelled_flags():
    rows = [
        {"day": date(2026, 7, 9), "company": "F12 Holdings", "status": "cancelled", "count": 12},
    ]
    buf = io.StringIO()
    _render_guard_activity(rows, file=buf)
    out = buf.getvalue()
    assert "F12 Holdings" in out
    assert "!!" in out


def test_render_guard_activity_cancelled_not_exceeding_succeeded_no_flag():
    rows = [
        {"day": date(2026, 7, 9), "company": "Acme Corp", "status": "succeeded", "count": 10},
        {"day": date(2026, 7, 9), "company": "Acme Corp", "status": "cancelled", "count": 10},
    ]
    buf = io.StringIO()
    _render_guard_activity(rows, file=buf)
    out = buf.getvalue()
    assert "!!" not in out


def test_render_guard_activity_days_descending():
    rows = [
        {"day": date(2026, 7, 8), "company": "Acme Corp", "status": "succeeded", "count": 5},
        {"day": date(2026, 7, 10), "company": "Acme Corp", "status": "succeeded", "count": 5},
        {"day": date(2026, 7, 9), "company": "Acme Corp", "status": "succeeded", "count": 5},
    ]
    buf = io.StringIO()
    _render_guard_activity(rows, file=buf)
    lines = [line for line in buf.getvalue().splitlines() if "2026-07" in line]
    days_in_order = [line.split()[1] for line in lines]
    assert days_in_order == sorted(days_in_order, reverse=True)


# ---------------------------------------------------------------------------
# render() integration
# ---------------------------------------------------------------------------

def test_render_contains_all_sections():
    data = {
        "sessions": [{"company": "Co A", "day": date(2026, 6, 4), "runs": 10, "recovery_runs": 1}],
        "spend": [{"company": "Co A", "budget_cents": 0, "spent_cents": 0,
                   "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}],
        "routines": [{"company": "Co A", "status": "paused", "count": 2}],
        "recovery": [{"company": "Co A", "recovery_comments": 5}],
        "guard_activity": [
            {"day": date(2026, 6, 4), "company": "Co A", "status": "succeeded", "count": 3}
        ],
    }
    buf = io.StringIO()
    render(data, file=buf)
    out = buf.getvalue()
    assert "Sessions per Company per Day" in out
    assert "Agent Spend" in out
    assert "Active Routines" in out
    assert "Recovery Comments" in out
    assert "Guard Activity" in out



# ---------------------------------------------------------------------------
# render_json — JSON output mode
# ---------------------------------------------------------------------------

FULL_DATA = {
    "sessions": [{"company": "Co A", "day": date(2026, 6, 4), "runs": 10, "recovery_runs": 1}],
    "spend": [{"company": "Co A", "budget_cents": 5000, "spent_cents": 1200,
               "input_tokens": 100000, "output_tokens": 8000, "cost_usd": 0.5}],
    "routines": [{"company": "Co A", "status": "active", "count": 3}],
    "recovery": [{"company": "Co A", "recovery_comments": 7}],
    "cap_alerts": [],
    "guard_activity": [
        {"day": date(2026, 6, 4), "company": "Co A", "status": "cancelled", "count": 2}
    ],
}


def test_render_json_is_parseable():
    buf = io.StringIO()
    render_json(FULL_DATA, file=buf)
    parsed = json.loads(buf.getvalue())
    assert isinstance(parsed, dict)


def test_render_json_top_level_keys():
    buf = io.StringIO()
    render_json(FULL_DATA, file=buf)
    parsed = json.loads(buf.getvalue())
    assert set(parsed.keys()) == {
        "sessions", "spend", "routines", "recovery", "cap_alerts", "guard_activity",
    }


def test_render_json_includes_guard_activity_key():
    buf = io.StringIO()
    render_json(FULL_DATA, file=buf)
    parsed = json.loads(buf.getvalue())
    assert "guard_activity" in parsed
    assert parsed["guard_activity"][0]["company"] == "Co A"
    assert parsed["guard_activity"][0]["status"] == "cancelled"
    assert parsed["guard_activity"][0]["day"] == "2026-06-04"


def test_render_json_date_serialized_as_string():
    buf = io.StringIO()
    render_json(FULL_DATA, file=buf)
    parsed = json.loads(buf.getvalue())
    assert parsed["sessions"][0]["day"] == "2026-06-04"


def test_render_json_single_line():
    """stdout must be exactly one JSON object — no extra lines."""
    buf = io.StringIO()
    render_json(FULL_DATA, file=buf)
    lines = [line for line in buf.getvalue().splitlines() if line.strip()]
    assert len(lines) == 1


def test_render_json_data_values():
    buf = io.StringIO()
    render_json(FULL_DATA, file=buf)
    parsed = json.loads(buf.getvalue())
    assert parsed["sessions"][0]["runs"] == 10
    assert parsed["spend"][0]["budget_cents"] == 5000
    assert parsed["routines"][0]["status"] == "active"
    assert parsed["recovery"][0]["recovery_comments"] == 7
    assert parsed["cap_alerts"] == []


def test_render_json_empty_sections():
    data = {
        "sessions": [], "spend": [], "routines": [], "recovery": [], "cap_alerts": [],
        "guard_activity": [],
    }
    buf = io.StringIO()
    render_json(data, file=buf)
    parsed = json.loads(buf.getvalue())
    for key in ("sessions", "spend", "routines", "recovery", "cap_alerts", "guard_activity"):
        assert parsed[key] == []


def test_render_json_with_cap_alerts():
    data = dict(FULL_DATA)
    data["cap_alerts"] = [
        {"company": "Co A", "level": "critical", "pct_used": 95.0,
         "current": 4750, "cap": 5000, "estimated_days_to_cap": 2.3}
    ]
    buf = io.StringIO()
    render_json(data, file=buf)
    parsed = json.loads(buf.getvalue())
    assert len(parsed["cap_alerts"]) == 1
    assert parsed["cap_alerts"][0]["level"] == "critical"


def test_render_json_no_text_output():
    """JSON mode must not emit any text-report markers."""
    buf = io.StringIO()
    render_json(FULL_DATA, file=buf)
    out = buf.getvalue()
    assert "===" not in out
    assert "Sessions per Company" not in out


def test_render_json_decimal_and_date_serialized():
    """Live DB rows carry decimal.Decimal (numeric columns), not floats."""
    data = {
        "sessions": [{"company": "Co A", "day": date(2026, 6, 4), "runs": 10, "recovery_runs": 1}],
        "spend": [{"company": "Co A", "budget_cents": 5000, "spent_cents": 1200,
                   "input_tokens": 100000, "output_tokens": 8000,
                   "cost_usd": Decimal("0.50")}],
        "routines": [{"company": "Co A", "status": "active", "count": 3}],
        "recovery": [{"company": "Co A", "recovery_comments": 7}],
        "cap_alerts": [
            {"company": "Co A", "level": "warn", "pct_used": Decimal("82.5"),
             "current": Decimal("4125"), "cap": Decimal("5000"),
             "estimated_days_to_cap": Decimal("3.2")}
        ],
    }
    buf = io.StringIO()
    render_json(data, file=buf)
    parsed = json.loads(buf.getvalue())
    assert parsed["sessions"][0]["day"] == "2026-06-04"
    assert parsed["spend"][0]["cost_usd"] == 0.5
    assert parsed["cap_alerts"][0]["pct_used"] == 82.5
