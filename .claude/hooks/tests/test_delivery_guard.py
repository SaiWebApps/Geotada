"""Payload tests for .claude/hooks/delivery-guard.py.

The guard exists because of a loop the OTHER Stop guards create between them: a
guard refuses the reply, the fix is a tool call, the tool call re-arms the next
guard, and around it goes with no work being done. Measured on 2026-09-02, after
the owner said "Go — build it": three verifier runs, two judge rulings, three
advisor consults, zero product work.

So the load-bearing pair is at the top:

  * two refusals with nothing delivered -> BLOCK, and point at the work;
  * two refusals with a tracker row written -> ALLOW, because the work moved.

A guard that only had the first would refuse every long turn and be switched off
within a day.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / ".claude" / "hooks" / "delivery-guard.py"

#: The turn starts here. Everything below is stamped relative to it.
TURN_START = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)


def stamp(minutes):
    return (TURN_START + timedelta(minutes=minutes)).isoformat()


def transcript(tmp_path, *, blocks, asked_question=False):
    """A turn: the owner speaks, then `blocks` Stop-hook refusals come back."""
    records = [
        {
            "type": "user",
            "uuid": "owner-1",
            "timestamp": TURN_START.isoformat(),
            "origin": {"kind": "human"},
            "message": {"content": "Go — build it"},
        }
    ]
    for n in range(blocks):
        records.append({
            "type": "assistant",
            "uuid": f"reply-{n}",
            "timestamp": stamp(n + 1),
            "message": {"content": [{"type": "text", "text": "Here is the report."}]},
        })
        records.append({
            "type": "user",
            "isMeta": True,
            "uuid": f"refusal-{n}",
            "timestamp": stamp(n + 1),
            "message": {"content": "Stop hook feedback:\nCITATION GUARD — prove it or drop it."},
        })
    if asked_question:
        records.append({
            "type": "assistant",
            "uuid": "asked",
            "timestamp": stamp(9),
            "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "AskUserQuestion", "input": {}}
            ]},
        })
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    return path


def tracker(tmp_path, *, event_at=None):
    """A tracker database, optionally carrying one event at `event_at`."""
    path = tmp_path / "tracker.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, "
        "kind TEXT NOT NULL, story TEXT, issue TEXT, who TEXT NOT NULL, detail TEXT)"
    )
    if event_at is not None:
        conn.execute(
            "INSERT INTO events (at, kind, who, detail) VALUES (?,?,?,?)",
            (event_at, "status_changed", "engine", "S1.1 pending -> completed"),
        )
    conn.commit()
    conn.close()
    return path


def quiet_repo(tmp_path):
    """A repository whose newest commit predates the turn.

    Load-bearing, not scaffolding. Without it the guard reads THIS repository,
    whose newest commit is always newer than a turn stamped in the past — so
    every test would take the "a commit landed" branch and pass for the wrong
    reason. The three tests that must BLOCK all failed exactly that way first.
    """
    repo = tmp_path / "quiet-repo"
    repo.mkdir(exist_ok=True)
    if not (repo / ".git").is_dir():
        for args in (
            ["init", "-q"],
            ["config", "user.email", "t@t"],
            ["config", "user.name", "t"],
        ):
            subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
        (repo / "a.txt").write_text("x\n")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-qm", "old"],
            cwd=repo,
            check=True,
            capture_output=True,
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                "HOME": str(Path.home()),
                "GIT_AUTHOR_DATE": stamp(-1440),
                "GIT_COMMITTER_DATE": stamp(-1440),
            },
        )
    return repo


def decide(tmp_path, *, blocks, event_at=None, asked_question=False, no_db=False):
    """Run the guard. {} means it let the reply through."""
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(Path.home()),
        "ONDOWAY_DELIVERY_STATE": str(tmp_path / f"state-{blocks}-{event_at}.json"),
        "ONDOWAY_DELIVERY_REPO": str(quiet_repo(tmp_path)),
    }
    if not no_db:
        env["ONDOWAY_DELIVERY_TRACKER_DB"] = str(tracker(tmp_path, event_at=event_at))
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({
            "hook_event_name": "Stop",
            "session_id": "test-session",
            "transcript_path": str(
                transcript(tmp_path, blocks=blocks, asked_question=asked_question)
            ),
        }),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else {}


def blocked(decision):
    return decision.get("decision") == "block"


def why(decision):
    return decision.get("reason", "")


# ── the load-bearing pair ────────────────────────────────────────────────────


def test_two_refusals_with_nothing_delivered_is_refused(tmp_path):
    """The loop, exactly. This is the whole reason the file exists."""
    decision = decide(tmp_path, blocks=2)
    assert blocked(decision)
    assert "STOP FIXING THE REPLY" in why(decision)
    assert "track.py show --json" in why(decision), "point at the work, don't just scold"


def test_two_refusals_are_fine_when_the_work_actually_moved(tmp_path):
    """The matched half. Without it, "block every long turn" would pass above.

    A tracker event after the turn began means a row was written by the one
    command that re-runs a step's own test before recording it. That is work,
    and the report is then the other guards' business, not this one's.
    """
    assert not blocked(decide(tmp_path, blocks=2, event_at=stamp(3)))


# ── it must not fire on ordinary turns ───────────────────────────────────────


def test_one_refusal_is_not_a_loop(tmp_path):
    """One guard catching one mistake is the system working, not spinning."""
    assert not blocked(decide(tmp_path, blocks=1))


def test_a_turn_with_no_refusals_at_all_is_untouched(tmp_path):
    assert not blocked(decide(tmp_path, blocks=0))


def test_an_event_from_before_the_turn_does_not_count(tmp_path):
    """Yesterday's work is not this turn's delivery."""
    assert blocked(decide(tmp_path, blocks=2, event_at=stamp(-600)))


def test_asking_a_real_question_is_always_allowed(tmp_path):
    """The sanctioned way to stop, same as proceed-guard.py recognises."""
    assert not blocked(decide(tmp_path, blocks=3, asked_question=True))


# ── it must never wedge the session ──────────────────────────────────────────


def test_a_missing_tracker_counts_as_delivered(tmp_path):
    """A guard that cannot read the repo must not accuse on its own outage."""
    assert not blocked(decide(tmp_path, blocks=2, no_db=True))


def test_a_malformed_payload_never_blocks():
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input="not json",
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
        timeout=60,
    )
    assert done.returncode == 0
    assert not done.stdout.strip()


def test_it_stands_down_rather_than_wedge_the_turn(tmp_path):
    """Its own trigger gets MORE true the longer it fires — a blocked reply
    cannot commit anything. So it has to concede."""
    state = tmp_path / "shared-state.json"
    db = tracker(tmp_path)
    repo = quiet_repo(tmp_path)

    def run_once():
        done = subprocess.run(
            [sys.executable, str(GUARD)],
            input=json.dumps({
                "hook_event_name": "Stop",
                "session_id": "wedge",
                "transcript_path": str(transcript(tmp_path, blocks=2)),
            }),
            capture_output=True,
            text=True,
            env={
                "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
                "HOME": str(Path.home()),
                "ONDOWAY_DELIVERY_STATE": str(state),
                "ONDOWAY_DELIVERY_TRACKER_DB": str(db),
                "ONDOWAY_DELIVERY_REPO": str(repo),
            },
            timeout=60,
        )
        assert done.returncode == 0
        return json.loads(done.stdout) if done.stdout.strip() else {}

    assert blocked(run_once())
    assert blocked(run_once())
    assert blocked(run_once())
    conceded = run_once()
    assert not blocked(conceded)
    assert "STOOD DOWN" in conceded.get("systemMessage", "")


# ── it is actually wired ─────────────────────────────────────────────────────


def test_the_guard_is_wired_as_a_stop_hook_and_runs_first():
    """An unwired guard is a guard that guards nothing.

    First in the Stop chain on purpose: it exists to end a loop the guards
    after it create, so it has to speak before they do.
    """
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    stop = settings["hooks"]["Stop"]
    commands = [h["command"] for group in stop for h in group["hooks"]]
    assert any("delivery-guard.py" in c for c in commands), "not wired at all"
    assert "delivery-guard.py" in commands[0], "it must run before the guards it unblocks"
