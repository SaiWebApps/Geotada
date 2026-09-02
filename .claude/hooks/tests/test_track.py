"""Tests for .claude/ledger/track.py — the shared tracker every agent writes to.

WHY THIS EXISTS. Every record of what an agent did was written by that same agent,
in prose, into a file it could reformat at will. The scribe in
`.claude/team-engine.js` spawns a haiku agent and asks it to edit `state.json`;
nothing checked whether the status it wrote was true. `track` closes that: it
re-runs the step's own command and records the exit code IT observed, so a claim
never becomes a row on the claimant's word.

The load-bearing assertions here are the refusals. A tracker that records what it
is told is a prettier `state.json`, and worth nothing.

WHERE THIS LIVES. Beside the guards, not in `tests/` — the subject is agent
supervision, not Ondoway. `pyproject.toml` sets `testpaths = ["tests"]`, so this
file is outside `make test` by construction, which is what keeps the product
suite free of the assistant's own scaffolding.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TRACK = REPO / ".claude" / "ledger" / "track.py"


def run(*args: str, db: Path, expect_ok: bool = True) -> dict:
    """Invoke track as the agents do — a subprocess, JSON on stdout.

    Called as a subprocess rather than imported on purpose: that is how every
    caller reaches it (the engine's agents have a shell, not a Python import),
    and an in-process test would not exercise the argument parsing that is the
    only interface any of them use.
    """
    result = subprocess.run(
        [sys.executable, str(TRACK), *args, "--db", str(db)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        check=False,
    )
    if expect_ok and result.returncode != 0:
        raise AssertionError(
            f"track {' '.join(args)} exited {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    payload = {}
    if result.stdout.strip():
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - failure path
            raise AssertionError(f"track did not print JSON: {result.stdout!r}") from exc
    payload["_exit"] = result.returncode
    payload["_stderr"] = result.stderr
    return payload


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "tracker.db"
    run("init", db=path)
    return path


@pytest.fixture
def plan(db: Path) -> Path:
    """One feature, one story, one issue — the smallest thing worth tracking."""
    run("feature-add", "--slug", "walking-a-tour",
        "--title", "Walking a tour on the phone",
        "--for-whom", "a tourist in a city they do not know",
        "--tier", "2", db=db)
    run("story-add", "--feature", "walking-a-tour", "--id", "S-1",
        "--text", "I walk up to a statue and it just starts talking to me.",
        "--said-by", "Nadia, walking with a six-year-old", db=db)
    return db


# ------------------------------------------------------------------ the schema


def test_init_creates_every_table_the_dashboard_reads(db: Path) -> None:
    with sqlite3.connect(db) as conn:
        names = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"features", "stories", "criteria", "issues",
            "events", "test_runs", "approvals"} <= names


def test_init_is_idempotent(db: Path) -> None:
    """Agents re-run it blindly; a second init must not wipe the first."""
    run("feature-add", "--slug", "f", "--title", "T", "--for-whom", "w", "--tier", "1", db=db)
    run("init", db=db)
    shown = run("show", "--json", db=db)
    assert [f["slug"] for f in shown["features"]] == ["f"]


def test_wal_is_on_so_the_dashboard_can_read_while_agents_write(db: Path) -> None:
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


# ------------------------------------------------- the story is the unit


def test_a_story_belongs_to_a_feature_and_starts_with_the_pm(plan: Path) -> None:
    shown = run("show", "--json", db=plan)
    story = shown["stories"][0]
    assert story["id"] == "S-1"
    assert story["feature"] == "walking-a-tour"
    assert story["state"] == "PM"
    assert story["sent_back"] == 0


def test_an_issue_belongs_to_a_story(plan: Path) -> None:
    run("issue-add", "--story", "S-1", "--id", "1",
        "--name", "Arrival starts the stop's audio",
        "--test-command", "true",
        "--files", "src/fx.py", db=plan)
    shown = run("show", "--json", db=plan)
    assert shown["issues"][0]["story"] == "S-1"


def test_an_issue_without_a_story_is_refused(plan: Path) -> None:
    """The dashboard is organised by story. A step with no story is invisible on
    it, and the owner ruled the story is the unit at every level."""
    out = run("issue-add", "--story", "S-404", "--id", "9", "--name", "orphan",
              "--test-command", "true", "--files", "src/fx.py",
              db=plan, expect_ok=False)
    assert out["_exit"] != 0


# ------------------------------------- the refusal that is the whole design


def test_completed_is_refused_when_the_command_fails(plan: Path) -> None:
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "n",
        "--test-command", "false", "--files", "src/fx.py", db=plan)
    out = run("step-status", "--id", "1", "--status", "completed",
              db=plan, expect_ok=False)
    assert out["_exit"] != 0
    shown = run("show", "--json", db=plan)
    assert shown["issues"][0]["status"] != "completed"


def test_completed_is_granted_only_after_track_runs_the_command_itself(plan: Path) -> None:
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "n",
        "--test-command", "true", "--files", "src/fx.py", db=plan)
    run("step-status", "--id", "1", "--status", "completed", db=plan)
    shown = run("show", "--json", db=plan)
    assert shown["issues"][0]["status"] == "completed"


def test_the_recorded_exit_code_is_the_one_track_observed(plan: Path) -> None:
    """Not one an agent reported. The row must name the command that produced it."""
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "n",
        "--test-command", "false", "--files", "src/fx.py", db=plan)
    run("step-status", "--id", "1", "--status", "completed", db=plan, expect_ok=False)
    with sqlite3.connect(plan) as conn:
        rows = conn.execute(
            "SELECT command, exit_code FROM test_runs ORDER BY id DESC").fetchall()
    assert rows, "a refused claim must still leave the evidence behind"
    assert rows[0][0] == "false"
    assert rows[0][1] != 0


def test_a_status_that_is_not_a_pass_claim_needs_no_run(plan: Path) -> None:
    """Only `completed` asserts something was proved. Marking a step in_progress
    or blocked is bookkeeping, and re-running a suite for it would be waste."""
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "n",
        "--test-command", "false", "--files", "src/fx.py", db=plan)
    run("step-status", "--id", "1", "--status", "in_progress", db=plan)
    shown = run("show", "--json", db=plan)
    assert shown["issues"][0]["status"] == "in_progress"


# --------------------------------------------- a story advances mechanically


def test_a_story_advances_only_when_every_issue_under_it_is_complete(plan: Path) -> None:
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "a",
        "--test-command", "true", "--files", "src/a.py", db=plan)
    run("issue-add", "--story", "S-1", "--id", "2", "--name", "b",
        "--test-command", "true", "--files", "src/b.py", db=plan)

    run("step-status", "--id", "1", "--status", "completed", db=plan)
    out = run("story-state", "--id", "S-1", "--state", "Done", db=plan, expect_ok=False)
    assert out["_exit"] != 0, "one of two issues done is not a finished story"

    run("step-status", "--id", "2", "--status", "completed", db=plan)
    run("story-state", "--id", "S-1", "--state", "Done", db=plan)
    shown = run("show", "--json", db=plan)
    assert shown["stories"][0]["state"] == "Done"


def test_sending_a_story_back_counts(plan: Path) -> None:
    """The manager's replan trigger is arithmetic over this number."""
    run("story-state", "--id", "S-1", "--state", "Implementer", db=plan)
    run("story-state", "--id", "S-1", "--state", "Verifier", db=plan)
    run("story-state", "--id", "S-1", "--state", "Implementer",
        "--sent-back", "--why", "gate red", db=plan)
    shown = run("show", "--json", db=plan)
    assert shown["stories"][0]["sent_back"] == 1


# ------------------------------------------------------- events and approvals


def test_every_write_appends_an_event(plan: Path) -> None:
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "n",
        "--test-command", "true", "--files", "src/fx.py", db=plan)
    run("step-status", "--id", "1", "--status", "completed", db=plan)
    with sqlite3.connect(plan) as conn:
        kinds = [r[0] for r in conn.execute("SELECT kind FROM events ORDER BY id")]
    assert "feature_added" in kinds
    assert "story_added" in kinds
    assert "issue_added" in kinds
    assert "status_changed" in kinds


def test_events_are_append_only(plan: Path) -> None:
    """The event log is what draws the state machine. A rewritable log is a log
    the thing being logged can edit."""
    with sqlite3.connect(plan) as conn:
        before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE events SET kind = 'rewritten'")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM events")
        assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == before


def test_approval_is_a_row_with_a_name_and_a_time(plan: Path) -> None:
    assert run("show", "--json", db=plan)["approved"] is False
    run("approve", "--feature", "walking-a-tour", "--by", "owner", db=plan)
    shown = run("show", "--json", db=plan)
    assert shown["approved"] is True
    with sqlite3.connect(plan) as conn:
        row = conn.execute("SELECT approved_by, approved_at FROM approvals").fetchone()
    assert row[0] == "owner"
    assert row[1]


# ---------------------------------------------------- the caller keeps no copy


def test_every_write_prints_the_full_status_set(plan: Path) -> None:
    """So the engine never maintains its own mirror. The mirror in
    team-engine.js went stale against the file and stranded 8 of 10 steps."""
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "a",
        "--test-command", "true", "--files", "src/a.py", db=plan)
    out = run("issue-add", "--story", "S-1", "--id", "2", "--name", "b",
              "--test-command", "true", "--files", "src/b.py", db=plan)
    assert {i["id"] for i in out["issues"]} == {"1", "2"}
    assert {s["id"] for s in out["stories"]} == {"S-1"}

    out = run("step-status", "--id", "1", "--status", "completed", db=plan)
    assert {i["id"]: i["status"] for i in out["issues"]}["1"] == "completed"


def test_a_refusal_still_prints_the_status_set(plan: Path) -> None:
    """A caller that only learns the truth when it wins learns nothing."""
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "n",
        "--test-command", "false", "--files", "src/fx.py", db=plan)
    out = run("step-status", "--id", "1", "--status", "completed",
              db=plan, expect_ok=False)
    assert out["_exit"] != 0
    assert "issues" in out, "the refusal must still hand back current state"


# ------------------------------------------------------------- the manager


def test_health_is_ok_on_a_clean_run(plan: Path) -> None:
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "n",
        "--test-command", "true", "--files", "src/fx.py", db=plan)
    run("step-status", "--id", "1", "--status", "completed", db=plan)
    assert run("health", "--json", db=plan)["replan_required"] is False


def test_health_calls_a_replan_when_a_story_is_sent_back_twice(plan: Path) -> None:
    run("story-state", "--id", "S-1", "--state", "Implementer", db=plan)
    run("story-state", "--id", "S-1", "--state", "Verifier", db=plan)
    run("story-state", "--id", "S-1", "--state", "Implementer",
        "--sent-back", "--why", "same failure", db=plan)
    run("story-state", "--id", "S-1", "--state", "Verifier", db=plan)
    run("story-state", "--id", "S-1", "--state", "Implementer",
        "--sent-back", "--why", "same failure again", db=plan)
    health = run("health", "--json", db=plan)
    assert health["replan_required"] is True
    assert health["story"] == "S-1", "the trigger must name the story, not the run"


def test_health_calls_a_replan_when_a_passing_test_goes_red(plan: Path) -> None:
    """green -> red is the signal that something already proved has broken."""
    issue = REPO / ".claude" / "ledger" / ".test_flag"
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "n",
        "--test-command", "true", "--files", "src/fx.py", db=plan)
    run("step-status", "--id", "1", "--status", "completed", db=plan)
    run("issue-set", "--id", "1", "--test-command", "false", db=plan)
    run("step-status", "--id", "1", "--status", "completed", db=plan, expect_ok=False)
    assert run("health", "--json", db=plan)["replan_required"] is True
    assert not issue.exists(), "track must not write outside its database"


def test_progress_is_computed_from_completed_issues(plan: Path) -> None:
    run("issue-add", "--story", "S-1", "--id", "1", "--name", "a",
        "--test-command", "true", "--files", "src/a.py", db=plan)
    run("issue-add", "--story", "S-1", "--id", "2", "--name", "b",
        "--test-command", "false", "--files", "src/b.py", db=plan)
    run("step-status", "--id", "1", "--status", "completed", db=plan)
    assert run("health", "--json", db=plan)["progress"] == 50


def test_progress_is_zero_with_nothing_to_do(plan: Path) -> None:
    """Never a divide by zero, and never a run that reports itself finished
    because it planned nothing."""
    assert run("health", "--json", db=plan)["progress"] == 0
