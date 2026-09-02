"""Payload tests for .claude/hooks/team-gate.sh.

WHY THIS FILE EXISTS NOW. Until 2026-09-02 this hook had no test, and on that
day it was found to be answering nothing at all: it looked for
`specs/<dated-dir>/state.json`, and `state.json` had been replaced by the SQLite
tracker the day before while `specs/` was deleted the same morning. Every branch
fell through to `exit 0`. A guard that cannot refuse, but still reads in a diff
as though it can, is worse than no guard — someone trusts it.

Nothing would have caught that, because nothing ran it. So the rewrite gets the
test the original never had, and the assertions are shaped around the failure:
each one names the state of the world, and both directions are proved. A test
that only checks "an unapproved plan is refused" would have passed on the broken
version if the fixture had happened to include a `state.json`.

The hook reads `$CLAUDE_PROJECT_DIR/.claude/ledger/track.py`, so these point
that at the real repo — the tracker is the thing under test's collaborator, and
a copy of it could drift from the one that ships. The DATABASE is redirected
with `TEAM_GATE_TRACKER_DB` instead, so the owner's own run is never read and
never written.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HOOK = REPO / ".claude" / "hooks" / "team-gate.sh"
TRACK = REPO / ".claude" / "ledger" / "track.py"

RUN_DIR = ".claude/runs/2026-09-02-a-worked-example"


def track(db: Path, *args: str) -> int:
    """One tracker command against a scratch database. Returns the exit code."""
    done = subprocess.run(
        [sys.executable, str(TRACK), *args, "--db", str(db)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=60,
    )
    return done.returncode


def decide(db: Path | None, prompt: str) -> dict:
    """Feed the hook one Agent-spawn payload; {} means it allowed the spawn."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": {"prompt": prompt},
    }
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(Path.home()),
        "CLAUDE_PROJECT_DIR": str(REPO),
    }
    if db is not None:
        env["TEAM_GATE_TRACKER_DB"] = str(db)
    done = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert done.returncode == 0, f"the hook must always exit 0: {done.stderr}"
    return json.loads(done.stdout) if done.stdout.strip() else {}


def denied(decision: dict) -> bool:
    return decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def reason(decision: dict) -> str:
    return decision.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")


def planned(tmp_path: Path) -> Path:
    """A scratch tracker holding one feature and one story — a plan, unapproved."""
    db = tmp_path / "tracker.db"
    assert track(db, "init") == 0
    assert track(
        db, "feature-add",
        "--slug", "worked-example",
        "--title", "A worked example",
        "--for-whom", "the test",
        "--tier", "1",
    ) == 0
    return db


# ----------------------------------------------- the gate, in both directions


def test_an_unapproved_plan_refuses_the_spawn(tmp_path):
    """The whole point: agents do not fan out on a plan nobody said go to."""
    decision = decide(planned(tmp_path), f"Do the work described in {RUN_DIR}/run-context.md")
    assert denied(decision)
    assert "nobody has approved" in reason(decision)
    assert "track approve" in reason(decision), "say how the go-ahead gets recorded"


def test_an_approved_plan_lets_the_spawn_through(tmp_path):
    """The matched half. Without it, 'always deny' would pass the test above.

    This is the assertion the original hook would have failed for the wrong
    reason — it allowed everything, so it would have passed here while failing
    the refusal above, and only running both tells the two apart.
    """
    db = planned(tmp_path)
    assert track(db, "approve", "--feature", "worked-example", "--by", "the-owner") == 0
    assert not denied(decide(db, f"Do the work described in {RUN_DIR}/run-context.md"))


def test_an_empty_tracker_is_not_a_refusal(tmp_path):
    """No plan written yet is not the same as a plan nobody approved.

    This mirrors the old hook's "state.json does not exist -> continue". A
    session that has not reached Step 4 must still be able to spawn agents —
    that is how the plan gets researched in the first place.
    """
    db = tmp_path / "empty.db"
    assert track(db, "init") == 0
    assert not denied(decide(db, f"Do the work described in {RUN_DIR}/run-context.md"))


# ------------------------------------------------------- scope: it stays narrow


def test_an_ordinary_agent_spawn_is_untouched(tmp_path):
    """Explore, Plan, audit and every other spawn must not pay for this gate.

    The removed guard.sh blocked 16 of 20 harmless commands and 0 of 70
    destructive ones. Narrowness is the design, so it gets an assertion.
    """
    db = planned(tmp_path)  # a plan exists and is unapproved — the firing state
    for prompt in [
        "Walk src/tour/ and report what is half-built.",
        "Read the Makefile and list every public target.",
        "Fix the failing test in tests/test_tour_selection.py",
    ]:
        assert not denied(decide(db, prompt)), prompt


def test_the_old_specs_path_no_longer_arms_the_gate(tmp_path):
    """`specs/` is deleted. A prompt naming it must not resurrect the old branch.

    Pinned deliberately: the failure being fixed was a hook still looking at a
    path that no longer exists, and the repair must not leave the dead spelling
    half-alive.
    """
    db = planned(tmp_path)
    assert not denied(decide(db, "Do the work in specs/2026-09-02-a-worked-example/run-context.md"))


def test_a_prompt_naming_no_run_folder_is_ignored(tmp_path):
    assert not denied(decide(planned(tmp_path), "Summarise the last three commits."))


# ---------------------------------------------------------------- fails open


def test_a_malformed_payload_never_blocks():
    """A gate that cannot read its input must not become a gate on all work."""
    done = subprocess.run(
        ["bash", str(HOOK)],
        input="this is not json",
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
            "HOME": str(Path.home()),
            "CLAUDE_PROJECT_DIR": str(REPO),
        },
        timeout=120,
    )
    assert done.returncode == 0
    assert not done.stdout.strip()


def test_an_unreadable_tracker_database_fails_open(tmp_path):
    """A broken store is an unanswered question, not a refusal."""
    db = tmp_path / "not-a-database.db"
    db.write_bytes(b"\x00\x01\x02 definitely not sqlite")
    assert not denied(decide(db, f"Do the work described in {RUN_DIR}/run-context.md"))
