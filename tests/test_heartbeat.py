"""Unit tests for scripts/heartbeat.py.

All tests are pure-Python — no live DB or Paperclip API required.
"""

from __future__ import annotations

import argparse
import datetime
import sys
import types

import pytest

# Make scripts/ importable
sys.path.insert(0, "scripts")
import heartbeat as hb


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue(
    id="issue-1",
    identifier="NEXAA-1",
    title="Do something",
    status="todo",
    priority="medium",
    assignee_agent=None,
    assignee_user=None,
    blocked_by=None,
    labels=None,
    description="",
    started_at=None,
    created_at="2026-01-01T00:00:00Z",
):
    return {
        "id": id,
        "identifier": identifier,
        "title": title,
        "status": status,
        "priority": priority,
        "assigneeAgentId": assignee_agent,
        "assigneeUserId": assignee_user,
        "blockedBy": blocked_by or [],
        "labels": labels or [],
        "description": description,
        "startedAt": started_at,
        "createdAt": created_at,
    }


def _now_utc(**kwargs):
    return datetime.datetime.now(datetime.timezone.utc).replace(**kwargs)


# ---------------------------------------------------------------------------
# extract_dependencies
# ---------------------------------------------------------------------------

class TestExtractDependencies:
    def test_empty_description(self):
        issue = _issue(description="")
        assert hb.extract_dependencies(issue) == set()

    def test_depends_on_single(self):
        issue = _issue(description="depends-on: NEXAA-12\nDo something")
        assert hb.extract_dependencies(issue) == {"NEXAA-12"}

    def test_depends_on_multiple_csv(self):
        issue = _issue(description="depends-on: NEXAA-5, NEXAA-6")
        assert hb.extract_dependencies(issue) == {"NEXAA-5", "NEXAA-6"}

    def test_depends_keyword(self):
        issue = _issue(description="depends: NEXAA-99")
        assert hb.extract_dependencies(issue) == {"NEXAA-99"}

    def test_after_label(self):
        issue = _issue(labels=[{"name": "after:NEXAA-20"}])
        assert hb.extract_dependencies(issue) == {"NEXAA-20"}

    def test_both_description_and_label(self):
        issue = _issue(
            description="depends-on: NEXAA-3",
            labels=[{"name": "after:NEXAA-7"}],
        )
        assert hb.extract_dependencies(issue) == {"NEXAA-3", "NEXAA-7"}

    def test_case_insensitive_dep(self):
        issue = _issue(description="Depends-On: nexaa-42")
        assert "NEXAA-42" in hb.extract_dependencies(issue)

    def test_no_labels_field(self):
        issue = _issue()
        issue.pop("labels")
        # Should not raise; returns empty set
        assert hb.extract_dependencies(issue) == set()


# ---------------------------------------------------------------------------
# is_eligible
# ---------------------------------------------------------------------------

class TestIsEligible:
    def test_todo_unassigned_eligible(self):
        issue = _issue()
        assert hb.is_eligible(issue, {}) is True

    def test_in_progress_not_eligible(self):
        issue = _issue(status="in_progress")
        assert hb.is_eligible(issue, {}) is False

    def test_done_not_eligible(self):
        issue = _issue(status="done")
        assert hb.is_eligible(issue, {}) is False

    def test_assigned_agent_not_eligible(self):
        issue = _issue(assignee_agent="agent-abc")
        assert hb.is_eligible(issue, {}) is False

    def test_assigned_user_not_eligible(self):
        issue = _issue(assignee_user="user-abc")
        assert hb.is_eligible(issue, {}) is False

    def test_heartbeat_issue_excluded(self):
        issue = _issue(id="hb-id")
        assert hb.is_eligible(issue, {}, heartbeat_issue_id="hb-id") is False

    def test_heartbeat_issue_id_none_not_excluded(self):
        issue = _issue(id="hb-id")
        assert hb.is_eligible(issue, {}, heartbeat_issue_id=None) is True

    def test_blocked_by_in_progress_not_eligible(self):
        issue = _issue(blocked_by=[{"id": "b1", "status": "in_progress"}])
        assert hb.is_eligible(issue, {}) is False

    def test_blocked_by_done_eligible(self):
        issue = _issue(blocked_by=[{"id": "b1", "status": "done"}])
        assert hb.is_eligible(issue, {}) is True

    def test_blocked_by_cancelled_eligible(self):
        issue = _issue(blocked_by=[{"id": "b1", "status": "cancelled"}])
        assert hb.is_eligible(issue, {}) is True

    def test_dep_done_eligible(self):
        dep = _issue(id="d1", identifier="NEXAA-5", status="done")
        issue = _issue(description="depends-on: NEXAA-5")
        assert hb.is_eligible(issue, {"NEXAA-5": dep}) is True

    def test_dep_in_progress_not_eligible(self):
        dep = _issue(id="d1", identifier="NEXAA-5", status="in_progress")
        issue = _issue(description="depends-on: NEXAA-5")
        assert hb.is_eligible(issue, {"NEXAA-5": dep}) is False

    def test_unknown_dep_not_eligible(self):
        issue = _issue(description="depends-on: NEXAA-999")
        assert hb.is_eligible(issue, {}) is False


# ---------------------------------------------------------------------------
# sort_by_priority
# ---------------------------------------------------------------------------

class TestSortByPriority:
    def test_critical_first(self):
        issues = [
            _issue(id="1", priority="low"),
            _issue(id="2", priority="critical"),
            _issue(id="3", priority="medium"),
        ]
        result = hb.sort_by_priority(issues)
        assert result[0]["id"] == "2"

    def test_high_before_medium(self):
        issues = [
            _issue(id="a", priority="medium"),
            _issue(id="b", priority="high"),
        ]
        result = hb.sort_by_priority(issues)
        assert result[0]["id"] == "b"

    def test_same_priority_older_first(self):
        issues = [
            _issue(id="new", priority="high", created_at="2026-06-10T00:00:00Z"),
            _issue(id="old", priority="high", created_at="2026-06-01T00:00:00Z"),
        ]
        result = hb.sort_by_priority(issues)
        assert result[0]["id"] == "old"

    def test_unknown_priority_treated_as_low(self):
        issues = [
            _issue(id="a", priority=None),
            _issue(id="b", priority="high"),
        ]
        result = hb.sort_by_priority(issues)
        assert result[0]["id"] == "b"

    def test_empty_list(self):
        assert hb.sort_by_priority([]) == []

    def test_single_issue(self):
        issue = _issue()
        assert hb.sort_by_priority([issue]) == [issue]


# ---------------------------------------------------------------------------
# count_in_progress
# ---------------------------------------------------------------------------

class TestCountInProgress:
    def test_none_in_progress(self):
        issues = [_issue(status="todo"), _issue(status="done")]
        assert hb.count_in_progress(issues) == 0

    def test_counts_in_progress(self):
        issues = [
            _issue(id="1", status="in_progress"),
            _issue(id="2", status="in_progress"),
            _issue(id="3", status="todo"),
        ]
        assert hb.count_in_progress(issues) == 2

    def test_excludes_heartbeat_issue(self):
        issues = [
            _issue(id="hb", status="in_progress"),
            _issue(id="other", status="in_progress"),
        ]
        assert hb.count_in_progress(issues, heartbeat_issue_id="hb") == 1

    def test_heartbeat_id_none_counts_all(self):
        issues = [_issue(id="hb", status="in_progress")]
        assert hb.count_in_progress(issues, heartbeat_issue_id=None) == 1

    def test_empty_list(self):
        assert hb.count_in_progress([]) == 0


# ---------------------------------------------------------------------------
# within_cooldown
# ---------------------------------------------------------------------------

_FIXED_NOW = datetime.datetime(2026, 7, 16, 12, 0, 0, tzinfo=datetime.timezone.utc)


class TestWithinCooldown:
    def test_no_in_progress_not_in_cooldown(self):
        issues = [_issue(status="todo")]
        assert hb.within_cooldown(issues, cooldown_seconds=60, now=_FIXED_NOW) is False

    def test_recent_spawn_in_cooldown(self):
        ts = (_FIXED_NOW - datetime.timedelta(seconds=30)).isoformat()
        issues = [_issue(status="in_progress", started_at=ts)]
        assert hb.within_cooldown(issues, cooldown_seconds=60, now=_FIXED_NOW) is True

    def test_old_spawn_not_in_cooldown(self):
        ts = (_FIXED_NOW - datetime.timedelta(seconds=120)).isoformat()
        issues = [_issue(status="in_progress", started_at=ts)]
        assert hb.within_cooldown(issues, cooldown_seconds=60, now=_FIXED_NOW) is False

    def test_exactly_at_cooldown_boundary_not_in_cooldown(self):
        ts = (_FIXED_NOW - datetime.timedelta(seconds=60)).isoformat()
        issues = [_issue(status="in_progress", started_at=ts)]
        assert hb.within_cooldown(issues, cooldown_seconds=60, now=_FIXED_NOW) is False

    def test_uses_most_recent_started_at(self):
        old_ts = (_FIXED_NOW - datetime.timedelta(seconds=120)).isoformat()
        new_ts = (_FIXED_NOW - datetime.timedelta(seconds=10)).isoformat()
        issues = [
            _issue(id="1", status="in_progress", started_at=old_ts),
            _issue(id="2", status="in_progress", started_at=new_ts),
        ]
        assert hb.within_cooldown(issues, cooldown_seconds=60, now=_FIXED_NOW) is True

    def test_falls_back_to_created_at(self):
        ts = (_FIXED_NOW - datetime.timedelta(seconds=10)).isoformat()
        issues = [_issue(status="in_progress", started_at=None, created_at=ts)]
        assert hb.within_cooldown(issues, cooldown_seconds=60, now=_FIXED_NOW) is True

    def test_unparseable_timestamp_not_in_cooldown(self):
        issues = [_issue(status="in_progress", started_at="not-a-date")]
        assert hb.within_cooldown(issues, cooldown_seconds=60, now=_FIXED_NOW) is False

    def test_zero_cooldown_never_blocked(self):
        ts = (_FIXED_NOW - datetime.timedelta(seconds=0)).isoformat()
        issues = [_issue(status="in_progress", started_at=ts)]
        assert hb.within_cooldown(issues, cooldown_seconds=0, now=_FIXED_NOW) is False


# ---------------------------------------------------------------------------
# spawn_agent
# ---------------------------------------------------------------------------

class FakeRun:
    """Captures subprocess.run calls and returns a configurable result."""

    def __init__(self, returncode=0, stderr=""):
        self.calls = []
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        r = types.SimpleNamespace(returncode=self.returncode, stderr=self.stderr)
        return r


class TestSpawnAgent:
    def test_dry_run_does_not_call_runner(self, capsys):
        runner = FakeRun()
        issue = _issue()
        result = hb.spawn_agent(issue, dry_run=True, runner=runner)
        assert result is True
        assert runner.calls == []
        out = capsys.readouterr().out
        assert "[dry-run]" in out
        assert "NEXAA-1" in out

    def test_live_spawn_calls_runner(self, capsys):
        runner = FakeRun(returncode=0)
        issue = _issue(id="abc-123")
        result = hb.spawn_agent(issue, dry_run=False, runner=runner)
        assert result is True
        assert len(runner.calls) == 1
        assert "abc-123" in runner.calls[0]

    def test_spawn_failure_returns_false(self, capsys):
        runner = FakeRun(returncode=1, stderr="connection refused")
        issue = _issue()
        result = hb.spawn_agent(issue, dry_run=False, runner=runner)
        assert result is False
        err = capsys.readouterr().err
        assert "ERROR" in err

    def test_dry_run_prints_identifier(self, capsys):
        runner = FakeRun()
        issue = _issue(identifier="NEXAA-99", title="Important task")
        hb.spawn_agent(issue, dry_run=True, runner=runner)
        out = capsys.readouterr().out
        assert "NEXAA-99" in out
        assert "Important task" in out


# ---------------------------------------------------------------------------
# run() — core orchestration
# ---------------------------------------------------------------------------

def _make_issues_list(*args):
    return list(args)


class TestRun:
    def _call(self, issues, **kwargs):
        defaults = dict(
            dry_run=True,
            session_cap=2,
            cooldown_seconds=0,
            _issues=issues,
            _now=_FIXED_NOW,
        )
        defaults.update(kwargs)
        return hb.run(**defaults)

    def test_no_issues_returns_zero(self, capsys):
        code = self._call([])
        assert code == 0
        assert "No eligible" in capsys.readouterr().out

    def test_session_cap_reached_skips(self, capsys):
        issues = [
            _issue(id="1", status="in_progress"),
            _issue(id="2", status="in_progress"),
            _issue(id="3", status="todo"),
        ]
        code = self._call(issues, session_cap=2)
        assert code == 0
        assert "cap reached" in capsys.readouterr().out

    def test_picks_highest_priority(self, capsys):
        issues = [
            _issue(id="low-1", identifier="NEXAA-2", priority="low"),
            _issue(id="crit-1", identifier="NEXAA-1", priority="critical"),
        ]
        code = self._call(issues)
        assert code == 0
        out = capsys.readouterr().out
        assert "NEXAA-1" in out
        assert "CRITICAL" in out

    def test_excludes_heartbeat_ticket_from_cap(self, capsys):
        issues = [
            _issue(id="hb", status="in_progress"),
            _issue(id="w1", identifier="NEXAA-10", status="todo"),
        ]
        code = self._call(issues, session_cap=1, heartbeat_issue_id="hb")
        assert code == 0
        out = capsys.readouterr().out
        assert "NEXAA-10" in out

    def test_cooldown_active_skips(self, capsys):
        ts = (_FIXED_NOW - datetime.timedelta(seconds=10)).isoformat()
        issues = [
            _issue(id="1", status="in_progress", started_at=ts),
            _issue(id="2", identifier="NEXAA-5", status="todo"),
        ]
        code = self._call(issues, cooldown_seconds=60, session_cap=5)
        assert code == 0
        assert "cooldown" in capsys.readouterr().out

    def test_dry_run_no_subprocess(self, capsys):
        issues = [_issue()]
        code = self._call(issues, dry_run=True)
        assert code == 0
        out = capsys.readouterr().out
        assert "[dry-run]" in out

    def test_ineligible_blocked_skips(self, capsys):
        issues = [_issue(blocked_by=[{"id": "b", "status": "todo"}])]
        code = self._call(issues)
        assert code == 0
        assert "No eligible" in capsys.readouterr().out

    def test_dependency_in_progress_skips(self, capsys):
        dep = _issue(id="d1", identifier="NEXAA-2", status="in_progress")
        main_issue = _issue(id="m1", identifier="NEXAA-3", description="depends-on: NEXAA-2")
        code = self._call([dep, main_issue])
        assert code == 0
        assert "No eligible" in capsys.readouterr().out

    def test_dependency_done_picks_up(self, capsys):
        dep = _issue(id="d1", identifier="NEXAA-2", status="done")
        main_issue = _issue(id="m1", identifier="NEXAA-3", description="depends-on: NEXAA-2")
        code = self._call([dep, main_issue])
        assert code == 0
        out = capsys.readouterr().out
        assert "NEXAA-3" in out


# ---------------------------------------------------------------------------
# CLI flag tests (via main())
# ---------------------------------------------------------------------------

class TestCLI:
    def _run_main(self, extra_argv, issues):
        """Patch fetch_issues to return *issues* and call main()."""
        original = hb.fetch_issues

        def fake_fetch(*args, **kwargs):
            return issues

        hb.fetch_issues = fake_fetch
        try:
            return hb.main(["--dry-run"] + extra_argv)
        finally:
            hb.fetch_issues = original

    def test_dry_run_flag_accepted(self, capsys):
        code = self._run_main([], [_issue()])
        assert code == 0

    def test_session_cap_flag(self, capsys):
        issues = [
            _issue(id="1", status="in_progress"),
            _issue(id="2", status="todo"),
        ]
        code = self._run_main(["--session-cap", "1"], issues)
        assert code == 0
        assert "cap reached" in capsys.readouterr().out

    def test_cooldown_flag(self, capsys):
        ts = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5)).isoformat()
        issues = [
            _issue(id="1", status="in_progress", started_at=ts),
            _issue(id="2", status="todo"),
        ]
        code = self._run_main(["--cooldown", "3600"], issues)
        assert code == 0
        assert "cooldown" in capsys.readouterr().out

    def test_no_eligible_returns_zero(self, capsys):
        issues = [_issue(status="done")]
        code = self._run_main([], issues)
        assert code == 0
        assert "No eligible" in capsys.readouterr().out

    def test_unknown_flag_exits_nonzero(self):
        with pytest.raises(SystemExit) as exc_info:
            hb.main(["--no-such-flag"])
        assert exc_info.value.code != 0
