#!/usr/bin/env python3
"""The delivery guard. Stop polishing the reply and go do the work.

OWNER RULING, verbatim, 2026-09-02, after a turn that produced three verifier
runs, two judge rulings, three advisor consults and zero product work:

    "I don't give a fuck about your excuses. Fix the /team skill and hooks to
     keep you on track and delivering items. YOU ARE NOT ALLOWED TO SPIN BEING A
     PIECE OF SHIT... I want manager agents whose job is to expect you to fail
     and kill everything + force you to obey me and do the fucking job."

WHAT THIS EXISTS TO BREAK, and it is a loop the OTHER GUARDS CREATE. Every Stop
hook in `.claude/settings.json` measures whether the REPORT is honest: citations
resolve, numbers are fresh, a verifier re-derived the claims, an advisor saw the
result. Each one is right on its own. Together they have a failure mode nobody
was watching:

    a guard blocks the reply -> the fix is a tool call -> the tool call re-arms
    the next guard -> that guard blocks the reply -> ...

Measured on this session, 2026-09-02: after the owner said "Go — build it", the
next hours produced three shadow runs, two judge rulings, three consults, two
docstring commits, and NOT ONE line of the work that had been approved. Every
individual block was correct. The session was still failing, and no guard could
see it, because not one of them asks whether the WORK moved.

This one asks only that.

THE TRIGGER IS THREE STRUCTURAL FACTS, none of which reads a word of the reply:

  1. How many times has a Stop hook blocked THIS reply? (Counted from the
     `isMeta` records the harness writes back into the transcript.)
  2. Has a commit landed since the owner last spoke?
  3. Has any row in the tracker's `events` log been written since then?

Two or more blocks with no commit and no tracker event is the loop, exactly.
Nothing about it can be reworded past: a guard that greps the reply for "let me
just fix" is a guard that a different sentence walks around.

WHY THE CEILING IS TWO, WHERE EVERY OTHER GUARD USES THREE. It exists to fire
BEFORE the others have each had three attempts. At three it would be the last
guard to speak in a loop it is meant to end, and the session would already have
burned six blocks. Two is the first moment the pattern is distinguishable from
one guard legitimately catching one mistake.

WHAT IT DOES NOT DO. It never says the report was wrong — the other guards own
that, and they are better at it. It says: whatever is wrong with the report,
stop editing it and go run the next thing the tracker is waiting on. If a
decision genuinely blocks the work, `AskUserQuestion` is the sanctioned exit,
the same one `proceed-guard.py` recognises.

IT ALSO STANDS DOWN, for the reason every guard here does: its own condition
gets more true the longer it fires, because a blocked reply cannot commit
anything. `MAX_BLOCKS` refusals in one turn and it steps aside loudly.
"""

import contextlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

#: Its own tally file, isolated from every other Stop guard's.
STATE_PATH = Path(
    os.environ.get("ONDOWAY_DELIVERY_STATE", "/tmp/ondoway-delivery-guard-state.json")
)

#: How many OTHER Stop-hook blocks on one reply count as the loop. Two, not the
#: three every sibling guard uses — see the module docstring. At three this
#: would speak last in a loop it exists to end.
BLOCKS_THAT_MEAN_A_LOOP = 2

#: This guard's own ceiling. A blocked reply cannot land a commit, so its
#: trigger only becomes more true the longer it refuses.
MAX_BLOCKS = 3

TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024

#: The literal the harness writes when a Stop hook refuses a reply. Measured on
#: this project's transcript, 2026-09-02: the refusal comes back as
#: `{"type": "user", "isMeta": true, "message": {"content": "Stop hook feedback: …"}}`
#: — so counting these records counts exactly the blocks on the current reply.
BLOCK_MARKER = "Stop hook feedback"


def allow():
    sys.exit(0)


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def read_state():
    try:
        return json.loads(STATE_PATH.read_text())
    except (OSError, ValueError):
        return {}


def write_state(state):
    with contextlib.suppress(OSError):
        STATE_PATH.write_text(json.dumps(state))


def records(transcript_path):
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


def _content_text(entry):
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for chunk in content:
            if isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                parts.append(chunk["text"])
        return "\n".join(parts)
    return ""


def is_human_turn(entry):
    """A real person typing. Copied from proceed-guard.py, same reasoning.

    `isMeta` is the load-bearing branch here for a second reason: a Stop-hook
    refusal comes back as an isMeta user record, and if that counted as the owner
    speaking, every block would reset the turn and this guard could never see two
    of them in a row.
    """
    if entry.get("type") != "user":
        return False
    if entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    origin_kind = (entry.get("origin") or {}).get("kind")
    if origin_kind == "human":
        return True
    if origin_kind is not None:
        return False
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


def turn_start(entries):
    """(index after the last human record, that record's timestamp or None)."""
    last = -1
    stamp = None
    for index, entry in enumerate(entries):
        if is_human_turn(entry):
            last = index
            stamp = entry.get("timestamp")
    return last + 1, stamp


def turn_id(entries):
    last = None
    humans = 0
    for entry in entries:
        if is_human_turn(entry):
            humans += 1
            last = entry
    if last is None:
        return "no-human-in-window"
    return last.get("uuid") or last.get("timestamp") or f"human-{humans}"


def blocks_this_turn(turn):
    """How many Stop hooks have already refused this reply."""
    count = 0
    for entry in turn:
        if entry.get("type") != "user" or not entry.get("isMeta"):
            continue
        if BLOCK_MARKER in _content_text(entry):
            count += 1
    return count


def asked_a_question(turn):
    """`AskUserQuestion` is the sanctioned way to stop, here as in proceed-guard."""
    for entry in turn:
        if entry.get("type") != "assistant":
            continue
        for chunk in (entry.get("message") or {}).get("content") or []:
            if isinstance(chunk, dict) and chunk.get("type") == "tool_use":
                if chunk.get("name") == "AskUserQuestion":
                    return True
    return False


# ── the two facts that decide whether the WORK moved ─────────────────────────


def _repo_root():
    """The checkout this guard asks about.

    Overridable so the payload tests can point at a scratch repository. Without
    it they cannot fail honestly: a synthetic turn is stamped in the past, the
    real repository's newest commit is always newer than that, and every test
    would take the "a commit landed" branch and pass by accident.
    """
    override = os.environ.get("ONDOWAY_DELIVERY_REPO")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent.parent


def _parse(stamp):
    """An ISO-8601 stamp as an aware datetime, or None. Never raises."""
    if not stamp:
        return None
    try:
        text = stamp.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    except (ValueError, AttributeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def commit_landed_since(stamp):
    """Did a commit land after `stamp`? Asked of git, so there is nothing to fake.

    Unknown answers count as DELIVERED. A guard that cannot read the repository
    must not accuse the session of idling on the strength of its own outage.
    """
    since = _parse(stamp)
    if since is None:
        return True
    try:
        done = subprocess.run(
            ["git", "log", "-1", "--format=%cI"],
            cwd=str(_repo_root()),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return True
    latest = _parse(done.stdout.strip())
    if latest is None:
        return True
    return latest > since


def worktree_changed_since(stamp):
    """Did any file in the working tree change after `stamp`?

    Added 2026-09-02. The two facts above — a commit, a tracker row — are the
    right ones for a /team run, but `/team` itself says "The engine does not
    commit; the human does", and most owner-directed work lands as uncommitted
    edits. Counting only commits meant a turn that had rewritten six hook files
    was still ruled "nothing delivered" the moment two Stop guards disagreed
    with its wording. Modified paths are asked of `git status`; their mtimes
    are asked of the filesystem. Unknown answers count as DELIVERED, as above.
    """
    since = _parse(stamp)
    if since is None:
        return True
    root = _repo_root()
    try:
        done = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(root), capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return True
    threshold = since.timestamp()
    for line in done.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        try:
            if (root / path).stat().st_mtime > threshold:
                return True
        except OSError:
            continue
    return False


def tracker_moved_since(stamp):
    """Did any row land in the tracker's append-only event log after `stamp`?

    `events` is written only by `.claude/ledger/track.py`, and a `completed` row
    there is earned — that command re-runs the issue's own test itself. So an
    event after the turn started means real work was recorded, not described.
    Unknown answers count as DELIVERED, for the same reason as above.
    """
    since = _parse(stamp)
    if since is None:
        return True
    database = _repo_root() / ".claude" / "ledger" / "tracker.db"
    override = os.environ.get("ONDOWAY_DELIVERY_TRACKER_DB")
    if override:
        database = Path(override)
    if not database.is_file():
        return True
    try:
        import sqlite3

        conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        try:
            rows = conn.execute("SELECT at FROM events ORDER BY id DESC LIMIT 40").fetchall()
        finally:
            conn.close()
    except Exception:
        return True
    for (at,) in rows:
        moment = _parse(at)
        if moment is not None and moment > since:
            return True
    return False


# ── the message ──────────────────────────────────────────────────────────────


def refusal(blocks):
    return (
        "DELIVERY GUARD — STOP FIXING THE REPLY. GO DO THE WORK.\n\n"
        f"This reply has been refused {blocks} times, and since the owner last "
        "spoke there is NO new commit and NO new row in the tracker's event "
        "log. That is not a reporting problem any more. That is a session "
        "polishing a message instead of building the thing it was told to "
        "build.\n\n"
        "Owner ruling, 2026-09-02: \"YOU ARE NOT ALLOWED TO SPIN BEING A PIECE "
        "OF SHIT.\" And: \"Fix the /team skill and hooks to keep you on track "
        "and delivering items.\"\n\n"
        "DO EXACTLY ONE OF THESE, NOW, IN THIS TURN:\n\n"
        "  1. Run the next thing the tracker is waiting on. Read it with\n"
        "     `python3 .claude/ledger/track.py show --json`, take the first "
        "issue whose\n"
        "     status is `pending`, and run its command. If a run is approved "
        "and not\n"
        "     started, start it.\n\n"
        "  2. If a decision genuinely blocks the work, call `AskUserQuestion` "
        "with real\n"
        "     options. That is the only sanctioned way to stop, and it keeps "
        "the turn alive.\n\n"
        "DO NOT: re-run a verifier, re-run the advisor, re-word the report, "
        "re-check a number, or add another citation. Every one of those is what "
        "got you here. The other guards will judge the report when there is "
        "work behind it to report.\n\n"
        "Invoke `Agent(subagent_type:'deliverables')` if you cannot tell what "
        "has actually landed — it counts commits and green runs out of the "
        "repository and rules PROGRESSING or SPINNING."
    )


def stand_down():
    print(
        json.dumps(
            {
                "systemMessage": (
                    f"DELIVERY GUARD STOOD DOWN after {MAX_BLOCKS} blocks in one "
                    "turn.\n\nA blocked reply cannot land a commit, so this "
                    "guard's own trigger only gets more true the longer it "
                    "refuses. Blocking again would wedge the session rather "
                    "than move the work.\n\nThe rule still stands: two refusals "
                    "with nothing delivered means go and build, not edit the "
                    "message. The owner should know this guard is not enforcing "
                    "it right now."
                )
            }
        )
    )
    sys.exit(0)


def main():
    if os.environ.get("ONDOWAY_DELIVERY_GUARD"):
        allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    event = payload.get("hook_event_name") or ""
    if event and event != "Stop":
        allow()

    transcript = payload.get("transcript_path")
    if not transcript:
        allow()

    entries = records(transcript)
    start, stamp = turn_start(entries)
    if not entries or start <= 0:
        allow()
    turn = entries[start:]

    if asked_a_question(turn):
        allow()  # the sanctioned way to stop

    blocks = blocks_this_turn(turn)
    if blocks < BLOCKS_THAT_MEAN_A_LOOP:
        allow()  # one guard catching one mistake is not a loop

    if commit_landed_since(stamp) or tracker_moved_since(stamp) or worktree_changed_since(stamp):
        allow()  # the work moved; the report is the other guards' business

    session = payload.get("session_id") or "unknown"
    here = turn_id(entries)
    state = read_state()
    if state.get("session") != session or state.get("turn") != here:
        state = {"session": session, "turn": here, "blocks": 0, "ts": time.time()}

    if state.get("blocks", 0) >= MAX_BLOCKS:
        stand_down()

    state["blocks"] = state.get("blocks", 0) + 1
    write_state(state)
    block(refusal(blocks))


if __name__ == "__main__":
    main()
