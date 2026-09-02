#!/usr/bin/env python3
"""Payload tests for `.claude/hooks/run-recorder.py`.

EVERY PAYLOAD HERE WAS MEASURED, NOT INVENTED. The sibling suite
`test_advisor_consult_guard.py` documents why that sentence is in this
docstring: an earlier guard's thirteen payload tests all passed while the guard
blocked every reply, because the fixtures were invented alongside the code and
proved only that the two agreed with each other.

The shapes below were read off this project's own transcripts on 2026-09-01, by
collecting every distinct `toolUseResult` key set across the six most recently
modified session files in
`~/.claude/projects/-Users-sairambkrishnan-git-ondoway/`:

    Bash    stdout, stderr, interrupted, isImage, noOutputExpected
    Bash    stdout, stderr, interrupted, isImage, noOutputExpected,
            persistedOutputPath, persistedOutputSize        (output spilled to a file)
    Bash    stdout, stderr, interrupted, isImage, noOutputExpected,
            gitOperation                                    (a git command)
    Write   type, filePath, content, originalFile, structuredPatch, userModified
    Edit    filePath, oldString, newString, originalFile, structuredPatch,
            replaceAll, userModified

NO EXIT CODE APPEARS IN ANY OF THEM, which is the finding the whole recorder is
built around and which `test_no_exit_code_is_ever_fabricated` pins down.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "run-recorder.py"


# --------------------------------------------------------------- the harness


def run_hook(payload: dict, db: Path) -> subprocess.CompletedProcess:
    """Run the hook exactly as the harness does: JSON on stdin, read the exit."""
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "ONDOWAY_TRACKER_DB": str(db)},
        check=False,
    )


def rows(db: Path, table: str) -> list[dict]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY id")]
    finally:
        conn.close()


# ---------------------------------------------------------- measured payloads


def bash_payload(command: str, stdout: str = "", stderr: str = "", **extra) -> dict:
    """A PostToolUse payload for Bash, in the measured shape.

    The envelope fields (`session_id`, `transcript_path`, `cwd`,
    `hook_event_name`, `tool_name`, `tool_input`, `tool_response`) are the ones
    every hook in this directory reads off a live payload; the `tool_response`
    is the Bash key set measured above.
    """
    response = {
        "stdout": stdout,
        "stderr": stderr,
        "interrupted": False,
        "isImage": False,
        "noOutputExpected": False,
    }
    response.update(extra)
    return {
        "session_id": "1d64ca6b-bc57-436b-ae8b-ac6bad8eecaf",
        "transcript_path": "",
        "cwd": "/Users/sairambkrishnan/git/ondoway",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "a command"},
        "tool_response": response,
    }


def write_payload(path: str, kind: str = "create") -> dict:
    """A PostToolUse payload for Write, in the measured shape."""
    return {
        "session_id": "1d64ca6b-bc57-436b-ae8b-ac6bad8eecaf",
        "transcript_path": "",
        "cwd": "/Users/sairambkrishnan/git/ondoway",
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": path, "content": "body"},
        "tool_response": {
            "type": kind,
            "filePath": path,
            "content": "body",
            "originalFile": "",
            "structuredPatch": [],
            "userModified": False,
        },
    }


def edit_payload(path: str) -> dict:
    """A PostToolUse payload for Edit, in the measured shape."""
    return {
        "session_id": "1d64ca6b-bc57-436b-ae8b-ac6bad8eecaf",
        "transcript_path": "",
        "cwd": "/Users/sairambkrishnan/git/ondoway",
        "hook_event_name": "PostToolUse",
        "tool_name": "Edit",
        "tool_input": {"file_path": path, "old_string": "a", "new_string": "b"},
        "tool_response": {
            "filePath": path,
            "oldString": "a",
            "newString": "b",
            "originalFile": "a",
            "structuredPatch": [],
            "replaceAll": False,
            "userModified": False,
        },
    }


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "tracker.db"


# ----------------------------------------------------------- the finding itself


def test_no_exit_code_is_ever_fabricated(db: Path) -> None:
    """The Bash payload has no exit code, so no row claims one.

    A green-looking run and a failing run produce the SAME exit_code, because
    the hook did not see one either time. If this test ever fails because the
    hook started writing 0 for the passing run, the hook has begun inventing.
    """
    run_hook(bash_payload("pytest -q", stdout="12 passed in 0.4s"), db)
    run_hook(bash_payload("pytest -q", stdout="1 failed, 11 passed", stderr="boom"), db)
    codes = [r["exit_code"] for r in rows(db, "test_runs")]
    assert codes == [-1, -1]


def test_the_measured_payload_really_carries_no_exit_code() -> None:
    """The premise, asserted rather than trusted.

    Guards against a future edit that adds an exit-code key to the fixture and
    then 'proves' the hook reads it. The fixture must keep matching what was
    measured on 2026-09-01.
    """
    response = bash_payload("true")["tool_response"]
    assert set(response) == {
        "stdout", "stderr", "interrupted", "isImage", "noOutputExpected"
    }
    for name in ("exit_code", "exitCode", "returncode", "returnCode", "code", "status"):
        assert name not in response


def test_excerpt_says_the_exit_code_was_unobserved(db: Path) -> None:
    run_hook(bash_payload("make test", stdout="ok"), db)
    assert rows(db, "test_runs")[0]["excerpt"].startswith("exit_code=unobserved ")


def test_excerpt_records_the_payload_key_list(db: Path) -> None:
    """The shape-drift alarm. The row itself names the keys the hook was handed,
    so the day a returncode appears nobody has to guess."""
    run_hook(bash_payload("make test", stdout="ok"), db)
    header = rows(db, "test_runs")[0]["excerpt"].split("\n")[0]
    assert "response_keys=interrupted,isImage,noOutputExpected,stderr,stdout" in header


# ------------------------------------------------------------ what IS recorded


def test_the_command_is_recorded_verbatim(db: Path) -> None:
    command = "uv run pytest tests/test_x.py -k 'a or b' --tb=short"
    run_hook(bash_payload(command, stdout="1 passed"), db)
    assert rows(db, "test_runs")[0]["command"] == command


def test_the_excerpt_hashes_the_whole_output_and_keeps_the_tail(db: Path) -> None:
    import hashlib

    stdout = "x" * 5000
    stderr = "warning: stale\n"
    run_hook(bash_payload("make test", stdout=stdout, stderr=stderr), db)
    excerpt = rows(db, "test_runs")[0]["excerpt"]
    header, body = excerpt.split("\n", 1)
    whole = stdout + stderr
    assert hashlib.sha256(whole.encode()).hexdigest() in header
    assert f"chars={len(whole)}" in header
    assert body == whole[-2000:]


def test_a_session_run_has_a_null_issue(db: Path) -> None:
    run_hook(bash_payload("make test", stdout="ok"), db)
    assert rows(db, "test_runs")[0]["issue"] is None


def test_the_timestamp_is_written(db: Path) -> None:
    run_hook(bash_payload("make test", stdout="ok"), db)
    at = rows(db, "test_runs")[0]["at"]
    assert at and at[4] == "-" and "T" in at


def test_interrupted_is_carried_through(db: Path) -> None:
    payload = bash_payload("sleep 999")
    payload["tool_response"]["interrupted"] = True
    run_hook(payload, db)
    assert "interrupted=true" in rows(db, "test_runs")[0]["excerpt"]


def test_the_spilled_output_shape_still_records(db: Path) -> None:
    """The measured variant with persistedOutputPath/persistedOutputSize."""
    run_hook(
        bash_payload(
            "make test",
            stdout="EEEE",
            persistedOutputPath="/tmp/out.txt",
            persistedOutputSize=91234,
        ),
        db,
    )
    assert len(rows(db, "test_runs")) == 1


def test_the_git_operation_shape_still_records(db: Path) -> None:
    """The measured variant with gitOperation."""
    run_hook(
        bash_payload("git commit -m x", stdout="[main abc] x", gitOperation={"type": "commit"}),
        db,
    )
    assert len(rows(db, "test_runs")) == 1


# ------------------------------------------------------------- the sibling table


def test_a_write_records_path_and_post_write_mtime(db: Path, tmp_path: Path) -> None:
    """The exact shape of both stale-count catches: a file, and when it changed."""
    target = tmp_path / "src.py"
    target.write_text("after the write\n")
    run_hook(write_payload(str(target)), db)
    row = rows(db, "file_writes")[0]
    assert row["path"] == str(target)
    assert row["tool"] == "Write"
    assert row["mtime"] == pytest.approx(target.stat().st_mtime)


def test_an_edit_records_the_same_way(db: Path, tmp_path: Path) -> None:
    target = tmp_path / "src.py"
    target.write_text("edited\n")
    run_hook(edit_payload(str(target)), db)
    row = rows(db, "file_writes")[0]
    assert row["path"] == str(target) and row["tool"] == "Edit"


def test_a_write_to_a_vanished_file_records_a_null_mtime(db: Path, tmp_path: Path) -> None:
    """None, not 1970 — a timestamp a comparison would believe is worse than none."""
    run_hook(write_payload(str(tmp_path / "gone.py")), db)
    assert rows(db, "file_writes")[0]["mtime"] is None


def test_a_run_and_a_write_can_be_compared_by_time(db: Path, tmp_path: Path) -> None:
    """The whole point: was this file written after that test ran?"""
    target = tmp_path / "src.py"
    target.write_text("v1\n")
    run_hook(bash_payload("pytest -q", stdout="12 passed"), db)
    target.write_text("v2\n")
    run_hook(write_payload(str(target)), db)
    ran_at = rows(db, "test_runs")[0]["at"]
    wrote_at = rows(db, "file_writes")[0]["at"]
    assert wrote_at >= ran_at


# -------------------------------------------- the turn stamp, structural only


def _transcript(tmp_path: Path, entries: list[dict]) -> str:
    path = tmp_path / "transcript.jsonl"
    path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    return str(path)


def test_the_turn_stamp_comes_from_the_last_human_record(db: Path, tmp_path: Path) -> None:
    target = tmp_path / "src.py"
    target.write_text("x\n")
    transcript = _transcript(tmp_path, [
        {"type": "user", "origin": {"kind": "human"}, "timestamp": "2026-09-01T10:00:00Z",
         "message": {"content": "first"}},
        {"type": "user", "origin": {"kind": "human"}, "timestamp": "2026-09-01T12:00:00Z",
         "message": {"content": "second"}},
    ])
    payload = write_payload(str(target))
    payload["transcript_path"] = transcript
    run_hook(payload, db)
    assert rows(db, "file_writes")[0]["turn_at"] == "2026-09-01T12:00:00Z"


def test_a_meta_record_is_not_a_human_turn(db: Path, tmp_path: Path) -> None:
    """isMeta is a hook's own block feedback or a skill prompt. Nobody typed it."""
    target = tmp_path / "src.py"
    target.write_text("x\n")
    transcript = _transcript(tmp_path, [
        {"type": "user", "origin": {"kind": "human"}, "timestamp": "2026-09-01T10:00:00Z",
         "message": {"content": "the real message"}},
        {"type": "user", "isMeta": True, "timestamp": "2026-09-01T11:00:00Z",
         "message": {"content": "NO CONSULT, NO REPLY."}},
    ])
    payload = write_payload(str(target))
    payload["transcript_path"] = transcript
    run_hook(payload, db)
    assert rows(db, "file_writes")[0]["turn_at"] == "2026-09-01T10:00:00Z"


def test_a_compaction_summary_is_not_a_human_turn(db: Path, tmp_path: Path) -> None:
    """The harness's out-of-context summary: a user record, plain text, no origin."""
    target = tmp_path / "src.py"
    target.write_text("x\n")
    transcript = _transcript(tmp_path, [
        {"type": "user", "origin": {"kind": "human"}, "timestamp": "2026-09-01T10:00:00Z",
         "message": {"content": "the real message"}},
        {"type": "user", "isCompactSummary": True, "isVisibleInTranscriptOnly": True,
         "timestamp": "2026-09-01T11:00:00Z",
         "message": {"content": "This session is being continued from a previous conversation"}},
    ])
    payload = write_payload(str(target))
    payload["transcript_path"] = transcript
    run_hook(payload, db)
    assert rows(db, "file_writes")[0]["turn_at"] == "2026-09-01T10:00:00Z"


def test_a_task_notification_is_not_a_human_turn(db: Path, tmp_path: Path) -> None:
    target = tmp_path / "src.py"
    target.write_text("x\n")
    transcript = _transcript(tmp_path, [
        {"type": "user", "origin": {"kind": "human"}, "timestamp": "2026-09-01T10:00:00Z",
         "message": {"content": "the real message"}},
        {"type": "user", "origin": {"kind": "task-notification"},
         "timestamp": "2026-09-01T11:00:00Z", "message": {"content": "agent finished"}},
    ])
    payload = write_payload(str(target))
    payload["transcript_path"] = transcript
    run_hook(payload, db)
    assert rows(db, "file_writes")[0]["turn_at"] == "2026-09-01T10:00:00Z"


def test_no_transcript_leaves_the_turn_stamp_null(db: Path, tmp_path: Path) -> None:
    target = tmp_path / "src.py"
    target.write_text("x\n")
    run_hook(write_payload(str(target)), db)
    assert rows(db, "file_writes")[0]["turn_at"] is None


# ------------------------------------------------------------- never in the way


def test_the_hook_always_exits_zero_and_says_nothing(db: Path) -> None:
    """A recorder that blocks a command is worse than no recorder."""
    result = run_hook(bash_payload("make test", stdout="ok"), db)
    assert result.returncode == 0
    assert result.stdout == ""


def test_malformed_stdin_exits_zero(db: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input="not json at all",
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "ONDOWAY_TRACKER_DB": str(db)},
        check=False,
    )
    assert result.returncode == 0
    assert not db.exists()


def test_an_empty_payload_exits_zero_and_writes_nothing(db: Path) -> None:
    result = run_hook({}, db)
    assert result.returncode == 0
    assert not db.exists()


def test_an_unwritable_database_still_exits_zero(tmp_path: Path) -> None:
    """The database path is a directory. Nothing can be written and nothing breaks."""
    blocked = tmp_path / "adir"
    blocked.mkdir()
    result = run_hook(bash_payload("make test", stdout="ok"), blocked)
    assert result.returncode == 0


def test_another_tool_records_nothing(db: Path) -> None:
    payload = bash_payload("make test", stdout="ok")
    payload["tool_name"] = "Read"
    run_hook(payload, db)
    assert not db.exists()


def test_a_bash_payload_with_no_command_records_nothing(db: Path) -> None:
    payload = bash_payload("make test")
    payload["tool_input"] = {}
    run_hook(payload, db)
    assert rows(db, "test_runs") == []


# ------------------------------------------------------------------ the schema


def test_the_database_is_created_with_the_trackers_own_test_runs_shape(db: Path) -> None:
    """`test_runs` is track.py's table. This hook must create it identically or
    the two would write to different databases with the same name."""
    run_hook(bash_payload("make test", stdout="ok"), db)
    conn = sqlite3.connect(db)
    try:
        cols = {r[1]: (r[2], r[3]) for r in conn.execute("PRAGMA table_info(test_runs)")}
    finally:
        conn.close()
    assert cols["at"] == ("TEXT", 1)
    assert cols["issue"][0] == "TEXT" and cols["issue"][1] == 0
    assert cols["command"] == ("TEXT", 1)
    assert cols["exit_code"] == ("INTEGER", 1)
    assert cols["excerpt"] == ("TEXT", 1)


def test_it_writes_into_a_database_the_tracker_made_first(db: Path) -> None:
    """The real case: `track init` ran, then this hook appends to its table."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ledger"))
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "track", Path(__file__).resolve().parents[2] / "ledger" / "track.py")
    track = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(track)
    conn = track.connect(db)
    conn.executescript(track.SCHEMA)
    conn.commit()
    conn.close()

    run_hook(bash_payload("make test", stdout="ok"), db)
    assert len(rows(db, "test_runs")) == 1
