#!/usr/bin/env python3
"""No reply without a consult. (Owner ruling, 2026-08-29.)

A Stop hook. It refuses to let the turn end unless the `advisor` tool was
actually called during it.

WHY: the owner asked, repeatedly, for the Fable 5 advisor to be consulted before
every response. The instruction was given at least five times in one session and
broken after each one — including replies that opened with the words "consulting
the advisor now" and then did not. An instruction that is agreed to and skipped
is not a rule; it is a habit of saying yes.

MECHANICAL, NOT SEMANTIC. This does not judge whether the consult was thoughtful.
It reads the transcript for a `tool_use` record whose name is `advisor`, inside
this turn — that is, after the last human message. Either the call happened or it
did not, and the transcript is the record. No pattern matching (owner ruling
2026-08-29): the JSONL records are walked and their fields compared.

SCOPE, so it stays a gate and not a tax:
  * Only replies to a HUMAN turn. A background task finishing, or a hook feeding
    a verdict back, must not force a consult about nothing.
  * MAX_BLOCKS, like its siblings: if the advisor itself is failing, the session
    must still be able to end. A guard that can wedge the session shut gets
    deleted, and then it guards nothing.
"""

import json
import os
import sys
import time
from pathlib import Path

STATE_PATH = Path("/tmp/ondoway-advisor-consult-state.json")
#: Raised from 2 on 2026-08-29. Every human message resets the turn and demands a
#: fresh consult, and this owner interjects often — 36 human records in one
#: session's transcript tail. At 2, two rapid interjections while mid-toolwork
#: burned both blocks and the guard silently disarmed itself, which is the
#: starved-rule class it exists to prevent. A successful consult resets the count
#: to 0 (see main), so this ceiling is only ever reached by genuine repeated
#: failure to consult.
MAX_BLOCKS = 5
TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024

HEADLINE = "NO CONSULT, NO REPLY."


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
    try:
        STATE_PATH.write_text(json.dumps(state))
    except OSError:
        pass


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


def _is_human_turn(entry):
    """A real person typing — classified by the record's STRUCTURE, never its text.

    Claude Code stamps every `user` record with what produced it. Measured on this
    project's own transcript, 2026-08-29 (session 710b5e6a, 53 non-tool-result
    user records):

        origin.kind == "human"              36   real messages ("Commit this.")
        origin.kind == "task-notification"   3   a background task reporting in
        isMeta == True                       7   this hook's own block feedback,
                                                 and skill prompts

    So the question "did a person type this" has a field that answers it, and no
    text needs reading at all. An earlier version of this guard screened text
    prefixes instead; it worked, but a prefix list is still a word list, and a
    word list is what silently starved the sibling flake rule when it knew
    `flaky` but not `flake`. Structure cannot be spelled a new way.

    FAILS LOUD, deliberately. An unrecognised record with text and no `isMeta`
    counts as human, so an unfamiliar shape costs one extra consult rather than
    silently disarming the guard. The dangerous direction here is a guard that
    stops firing, never one that fires once too often.

    A genuine mid-turn interjection DOES reset the turn: new words from the owner
    are a new thing to say something about, and they asked for a consult before
    anything is said to them.
    """
    if entry.get("type") != "user":
        return False

    if entry.get("isMeta"):
        return False

    origin_kind = (entry.get("origin") or {}).get("kind")
    if origin_kind == "human":
        return True
    if origin_kind is not None:
        return False  # task-notification, and any future machine origin

    # No origin stamp at all — an older or unfamiliar record. Treat text as human.
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


def turn_slice(entries):
    """Everything after the last human message — this turn."""
    last_human = -1
    for index, entry in enumerate(entries):
        if _is_human_turn(entry):
            last_human = index
    if last_human < 0:
        return None
    return entries[last_human + 1:]


#: How an advisor call ACTUALLY appears in the transcript. Read off this
#: project's own JSONL on 2026-08-29 (session 710b5e6a), not assumed:
#:
#:   {"type": "server_tool_use", "id": "srvtoolu_...", "name": "advisor", "input": "{}"}
#:   {"type": "advisor_tool_result", "tool_use_id": "srvtoolu_...", "content": "..."}
#:
#: The first version of this guard looked for `{"type": "tool_use", "name":
#: "advisor"}` — the shape every OTHER tool uses. The advisor is a server-side
#: tool and uses neither field the same way, so the check could never match: the
#: guard blocked EVERY reply, consult or not, and its thirteen payload tests all
#: passed because they were built from the same assumed shape rather than from a
#: real record. A fixture invented alongside the code under test proves only that
#: the two agree with each other.
ADVISOR_CALL_TYPES = ("server_tool_use", "tool_use")
ADVISOR_RESULT_TYPE = "advisor_tool_result"


def consulted(turn):
    """Did an advisor call happen in this turn? Either the call or its result."""
    for entry in turn:
        if entry.get("type") != "assistant":
            continue
        for chunk in (entry.get("message") or {}).get("content") or []:
            if not isinstance(chunk, dict):
                continue
            kind = chunk.get("type")
            if kind in ADVISOR_CALL_TYPES and chunk.get("name") == "advisor":
                return True
            if kind == ADVISOR_RESULT_TYPE:
                return True
    return False


def main():
    if os.environ.get("CLAUDE_NO_EXCUSES_JUDGE"):
        allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    transcript = payload.get("transcript_path")
    if not transcript:
        allow()

    session = payload.get("session_id") or "unknown"
    state = read_state()
    if state.get("session") != session:
        state = {"session": session, "blocks": 0, "ts": time.time()}
    if state.get("blocks", 0) >= MAX_BLOCKS:
        allow()  # the advisor itself may be down; never wedge the session shut

    entries = records(transcript)
    turn = turn_slice(entries)
    if turn is None:
        allow()  # no human turn in view; nothing was asked

    if consulted(turn):
        state["blocks"] = 0
        write_state(state)
        allow()

    state["blocks"] = state.get("blocks", 0) + 1
    write_state(state)
    block(
        HEADLINE + "\n\n"
        "You are about to answer without having called the advisor in this turn.\n\n"
        "The owner asked for this at least five times in one session, and it was "
        "broken after every one — including replies that opened with the words "
        "\"consulting the advisor now\" and then did not call it. Saying yes is "
        "not doing it, and this hook exists because the difference was invisible "
        "to everyone except the transcript.\n\n"
        "Call `advisor()` now — it takes no arguments and forwards this whole "
        "conversation — read what it says, then reply."
    )


if __name__ == "__main__":
    main()
