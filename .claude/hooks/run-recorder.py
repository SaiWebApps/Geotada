#!/usr/bin/env python3
"""What the HOOK saw a command do — not what the session remembers it doing.

THE PROBLEM. Nothing in this repository records what a command actually
returned. Every number about a test run reaches the owner through the
assistant's memory of it, and the median lag between a turn's first file write
and a verifier catching an error in that turn was measured today at 21.9
minutes. Two of today's real catches were stale test counts: a number that was
true when it was quoted and false by the time it was read. Both are a timestamp
comparison, and until now there was nothing to compare.

THE EXIT CODE IS NOT IN THE PAYLOAD. Stated plainly, because the honest answer
matters more than a full column. A PostToolUse payload's `tool_response` for
Bash was read off this project's own transcripts on 2026-09-01 — every distinct
`toolUseResult` shape across the six newest session files — and Bash results
carry exactly these keys:

    {"stdout": ..., "stderr": ..., "interrupted": false,
     "isImage": false, "noOutputExpected": false}

with `persistedOutputPath` and `persistedOutputSize` added when the output was
spilled to a file, and `gitOperation` added for a git command. There is NO
returncode, NO exit_code, NO status field in any of them. So this hook does not
record one. `test_runs.exit_code` is NOT NULL, so every row this hook writes
carries EXIT_CODE_UNOBSERVED (-1), which means "no exit code was available to
the observer" and never "the command failed". A -1 row is evidence about the
command and its output, not about its success.

Nothing here guesses. A hook that scanned stdout for the word "passed" and
wrote a 0 would be manufacturing the exact kind of number this file exists to
replace. What IS recorded is what the hook genuinely saw: the command, the
moment, the sha256 of the complete stdout+stderr, the tail of that text, the
interrupted flag, and the literal key list of the payload it was handed — so
the day the harness starts sending a returncode, the rows say so themselves and
nobody has to guess whether the shape changed.

THE SIBLING TABLE. `file_writes` answers the question behind both stale-count
catches: has any file this test covers been written since the test ran? A Write
or Edit `tool_response` carries `filePath` (measured, same survey), and the hook
runs after the write, so the file's mtime on disk is the post-write mtime. Row
plus row is then a timestamp comparison and nobody has to remember anything.

ALWAYS EXITS 0. A hook that crashes is a hook that is switched off, and a
recorder that blocks a command is worse than no recorder. Every failure path
here — unreadable stdin, unwritable database, a payload shaped in a way nobody
has seen — ends in a silent exit 0.

NO PATTERN MATCHING on records: the transcript entries are walked and their
fields compared, copied from `.claude/hooks/advisor-consult-guard.py`, because a
pattern catches only the spellings someone thought of.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sqlite3
import sys
# NOT `from datetime import UTC` — that is a Python 3.11 API and the harness
# runs /usr/bin/python3, which is 3.9.6 on this machine. Registered with the
# 3.11 spelling this hook raised ImportError on every single fire and wrote
# nothing; measured 2026-09-02, ten silent failures before anyone looked.
from datetime import datetime, timezone
from pathlib import Path

#: Written into `test_runs.exit_code`, which is NOT NULL, when no exit code was
#: in the payload — which, as of the 2026-09-01 survey, is every Bash payload.
#: Negative on purpose: 0 would read as success and any positive number as a
#: specific failure, and both would be inventions.
EXIT_CODE_UNOBSERVED = -1

#: Tools whose result records a command run.
COMMAND_TOOLS = ("Bash", "BashOutput")

#: Tools whose result records a file being written. NotebookEdit is here for the
#: same reason Write and Edit are: it changes a file on disk and its payload
#: names the path.
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

#: How much of a command's combined output is kept. The same 2000 the tracker's
#: own `observe()` keeps, so a row written here and a row written by
#: `track step-status` are the same size of evidence.
EXCERPT_CHARS = 2000

TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024

DEFAULT_DB = Path(__file__).resolve().parents[1] / "ledger" / "tracker.db"

#: `test_runs` is `.claude/ledger/track.py`'s table, repeated here verbatim so
#: this hook can create the database when the tracker has never been run. It is
#: CREATE TABLE IF NOT EXISTS, so when track.py made it first this is a no-op.
#: `file_writes` is new and belongs to this hook.
SCHEMA = """
CREATE TABLE IF NOT EXISTS test_runs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    at        TEXT NOT NULL,
    issue     TEXT,
    command   TEXT NOT NULL,
    exit_code INTEGER NOT NULL,
    excerpt   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS file_writes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    at        TEXT NOT NULL,
    path      TEXT NOT NULL,
    mtime     REAL,
    tool      TEXT NOT NULL,
    turn_at   TEXT,
    session   TEXT
);

CREATE INDEX IF NOT EXISTS file_writes_by_path ON file_writes (path);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_path() -> Path:
    override = os.environ.get("ONDOWAY_TRACKER_DB")
    return Path(override) if override else DEFAULT_DB


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


# ------------------------------------------------------- reading the payload


def command_of(payload: dict) -> str:
    """The command that ran, from `tool_input.command`.

    Measured shape, 2026-09-01: a Bash PreToolUse and PostToolUse payload both
    carry `tool_input` as `{"command": ..., "description": ...}`. Nothing is
    lowercased or normalised here — this is evidence, and evidence is stored the
    way it arrived.
    """
    raw = (payload.get("tool_input") or {}).get("command")
    return raw if isinstance(raw, str) else ""


def output_of(response: dict) -> str:
    """stdout followed by stderr, exactly as the harness spelled them.

    Both are strings on every Bash result measured. A response that is a bare
    string — the shape some tools use — is taken as the output itself, so an
    unfamiliar spelling records something rather than nothing.
    """
    if isinstance(response, str):
        return response
    if not isinstance(response, dict):
        return ""
    parts = []
    for key in ("stdout", "stderr"):
        value = response.get(key)
        if isinstance(value, str):
            parts.append(value)
    return "".join(parts)


def response_keys(response: object) -> str:
    """The literal key list of the response, sorted.

    This is how a change in the harness announces itself. The day `exit_code`
    or `returncode` appears in this list, the rows say so and the docstring
    above is out of date — which is a great deal better than a hook that
    silently keeps writing -1 forever.
    """
    if isinstance(response, dict):
        return ",".join(sorted(str(key) for key in response))
    return type(response).__name__


def build_excerpt(response: object, output: str) -> str:
    """The evidence line plus the tail of the output.

    A header of facts the hook measured, then the last EXCERPT_CHARS of the
    combined output. The header is first so that reading one row tells you
    whether its exit code was observed or unobtainable, without having to know
    this file.
    """
    digest = hashlib.sha256(output.encode("utf-8", "replace")).hexdigest()
    interrupted = bool(isinstance(response, dict) and response.get("interrupted"))
    header = (
        f"exit_code=unobserved sha256={digest} chars={len(output)} "
        f"interrupted={str(interrupted).lower()} response_keys={response_keys(response)}"
    )
    return header + "\n" + output[-EXCERPT_CHARS:]


def written_path(payload: dict) -> str:
    """The file a write tool touched.

    Measured 2026-09-01 across this project's transcripts. A Write result is
    `{"type": "create"|"update", "filePath": ..., "content": ...,
    "structuredPatch": ..., "originalFile": ..., "userModified": ...}` and an
    Edit result is `{"filePath": ..., "oldString": ..., "newString": ...,
    "structuredPatch": ..., "replaceAll": ..., "originalFile": ...,
    "userModified": ...}`. Both name the path as `filePath`. The tool_input's
    `file_path` is the same path under the snake_case spelling and is the
    fallback, so a result shaped in some new way still records the file.
    """
    response = payload.get("tool_response")
    if isinstance(response, dict):
        for key in ("filePath", "file_path"):
            value = response.get(key)
            if isinstance(value, str) and value:
                return value
    value = (payload.get("tool_input") or {}).get("file_path")
    return value if isinstance(value, str) else ""


def mtime_of(path: str) -> float | None:
    """The file's modification time as the hook sees it, or None if it is gone.

    PostToolUse runs after the write, so this is the post-write mtime. None
    rather than 0.0 when the file cannot be stat'd, because 1970 is a timestamp
    a comparison would believe.
    """
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


# -------------------------------------- the transcript walk, from the advisor guard


def records(transcript_path: str) -> list:
    try:
        with open(transcript_path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - TRANSCRIPT_TAIL_BYTES))
            blob = handle.read().decode("utf-8", "replace")
    except OSError:
        return []
    lines = blob.split("\n")
    if size > TRANSCRIPT_TAIL_BYTES:
        lines = lines[1:]
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _is_human_turn(entry: dict) -> bool:
    """A real person typing — classified by the record's STRUCTURE, never its text.

    Copied unchanged from `.claude/hooks/advisor-consult-guard.py`, including
    the two machine markers it learned the hard way: `isMeta` (a hook's own
    block feedback and skill prompts) and `isCompactSummary` (the harness's
    out-of-context summary, a `user` record with plain text, no origin stamp
    and nobody behind it). An unrecognised record carrying text counts as human,
    which here costs a turn boundary in the wrong place and never a lost row.
    """
    if entry.get("type") != "user":
        return False
    if entry.get("isMeta"):
        return False
    if entry.get("isCompactSummary"):
        return False

    origin_kind = (entry.get("origin") or {}).get("kind")
    if origin_kind == "human":
        return True
    if origin_kind is not None:
        return False  # task-notification, and any future machine origin

    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    if isinstance(content, list):
        for chunk in content:
            if isinstance(chunk, dict) and chunk.get("type") == "tool_result":
                return False
        return any(
            isinstance(chunk, dict)
            and chunk.get("type") == "text"
            and chunk.get("text", "").strip()
            for chunk in content
        )
    return False


def turn_started_at(transcript_path: object) -> str | None:
    """When the person who is waiting last said something.

    Stamped on every file_writes row so a later check can scope "written since
    the test ran" to the turn the owner is actually reading about, rather than
    to every write in the session's history. None when no human record is in
    view — a turn that has outgrown the window, or a file with nothing in it.
    """
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    stamp = None
    for entry in records(transcript_path):
        if _is_human_turn(entry):
            value = entry.get("timestamp")
            if isinstance(value, str) and value:
                stamp = value
    return stamp


# -------------------------------------------------------------------- writing


def record_command(conn: sqlite3.Connection, payload: dict) -> bool:
    command = command_of(payload)
    if not command:
        return False
    response = payload.get("tool_response")
    excerpt = build_excerpt(response, output_of(response))
    conn.execute(
        "INSERT INTO test_runs (at, issue, command, exit_code, excerpt) VALUES (?,?,?,?,?)",
        (now(), None, command, EXIT_CODE_UNOBSERVED, excerpt),
    )
    return True


def record_write(conn: sqlite3.Connection, payload: dict) -> bool:
    path = written_path(payload)
    if not path:
        return False
    conn.execute(
        "INSERT INTO file_writes (at, path, mtime, tool, turn_at, session) VALUES (?,?,?,?,?,?)",
        (
            now(),
            path,
            mtime_of(path),
            payload.get("tool_name") or "",
            turn_started_at(payload.get("transcript_path")),
            payload.get("session_id") or None,
        ),
    )
    return True


def handle(payload: dict) -> bool:
    """Write the row this payload deserves. True when one landed."""
    tool = payload.get("tool_name") or ""
    if tool in COMMAND_TOOLS:
        writer = record_command
    elif tool in WRITE_TOOLS:
        writer = record_write
    else:
        return False

    conn = connect(db_path())
    try:
        wrote = writer(conn, payload)
        conn.commit()
        return wrote
    finally:
        conn.close()


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    # A recorder that blocks a command is worse than no recorder. Nothing this
    # hook can fail at is worth stopping the session for.
    with contextlib.suppress(Exception):
        handle(payload)
    sys.exit(0)


if __name__ == "__main__":
    main()
