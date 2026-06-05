"""
Tests for dashboard rendering and query plumbing.

Query functions are tested via a FakeConn / FakeCursor that returns
pre-canned rows — no live database required.
"""

from __future__ import annotations

import io
import sys
from datetime import date

import pytest

sys.path.insert(0, ".")

from src.queries import (
    active_routines,
    agent_spend,
    recovery_comment_counts,
    sessions_per_company_per_day,
)
from src.dashboard import (
    _fmt_cents,
    collect,
    render,
    _render_sessions,
    _render_spend,
    _render_routines,
    _render_recovery,
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
# render() integration
# ---------------------------------------------------------------------------

def test_render_contains_all_sections():
    data = {
        "sessions": [{"company": "Co A", "day": date(2026, 6, 4), "runs": 10, "recovery_runs": 1}],
        "spend": [{"company": "Co A", "budget_cents": 0, "spent_cents": 0,
                   "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}],
        "routines": [{"company": "Co A", "status": "paused", "count": 2}],
        "recovery": [{"company": "Co A", "recovery_comments": 5}],
    }
    buf = io.StringIO()
    render(data, file=buf)
    out = buf.getvalue()
    assert "Sessions per Company per Day" in out
    assert "Agent Spend" in out
    assert "Active Routines" in out
    assert "Recovery Comments" in out
