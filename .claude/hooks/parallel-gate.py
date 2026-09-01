#!/usr/bin/env python3
"""Batch independent background spawns, or say why not.

OWNER RULING, 2026-08-31: "Parallelize. Build a hook to force you to parallelize
when and where possible. As much as possible. You have been too slow."

THE SHAPE THIS CATCHES. Two `run_in_background: true` calls — `Agent` or `Bash`
— issued from SEPARATE, consecutive assistant turns with nothing genuinely
consumed in between. Both could have been requested together and started at the
same instant; splitting them across two turns costs a whole extra round trip
for no reason the transcript can show.

FIRE ONLY ON WHAT IS MECHANICALLY DECIDABLE, or this fires on ordinary
sequential work and gets deleted — and then it guards nothing. Four
conditions, ALL of which must hold, or this allows:

  1. THIS call is `Agent` or `Bash` with `run_in_background` EXACTLY `True`.
     Omitted is deliberately out of scope: some harness versions default an
     Agent call to background, and inferring that default here would mean
     guessing at version behaviour instead of reading a literal field — the
     invented-fixture failure this project's own hooks keep finding in
     themselves (advisor-consult-guard's `server_tool_use` postmortem;
     shadow-guard's own admission of the identical defect). Build the check
     from what the payload actually says.

  2. A PRIOR background spawn P sits earlier in this turn, and P actually
     ran — its own tool_result is not `is_error`. A spawn a SIBLING guard
     already refused never launched, so it cannot be the other half of an
     avoidable pair; counting it anyway is class 17b of the failures ledger,
     a boundary check reading a refusal — its own or another guard's — as if
     it were work done.

  3. NOTHING ELSE completed between P and now: no `tool_result` anywhere in
     the turn after P carries a `tool_use_id` other than P's own launch
     acknowledgement. Any other result means the assistant read something
     first, and this spawn might genuinely depend on it — the mark of a real
     sequential need, not an oversight.

  4. AT LEAST ONE assistant record after P carries a DIFFERENT `message.id`
     than P's own. Two tool calls requested by ONE inference are, at the API
     level, one `message` object. Measured on this project's own session
     transcript, 2026-08-31: a `thinking` block and the `tool_use` block that
     followed it in the same turn shared one `message.id`
     (`msg_011CebcSpTpmJEvR7XxrcUVN`), while the NEXT tool call — a fresh
     `thinking` block ahead of it — carried a different id entirely
     (`msg_011CebcTcp7pYsAq74s9UYku`). A different id appearing after P is
     the signature of a NEW inference having started, which is what
     "separate, consecutive messages" means mechanically. Two blocks
     produced by ONE inference never trip this, because nothing between them
     carries a different id at all.

     When P's own `message.id` is missing, or nothing after it carries an
     id of its own, this condition is simply not met and the spawn is
     ALLOWED — the safe direction for a check built to fire only when it can
     actually tell.

SELF-CLEARING BY CONSTRUCTION, not by a special case written for it. Once this
denies a second spawn, P has already launched and cannot be un-launched — a
rule that kept denying the retry forever would be the exact unsatisfiable-
boundary failure this project's guards keep documenting (advisor-consult-
guard's transcript-lag reversal; shadow-guard's superseded-run repair). No
special case is needed: the denial itself is written to the transcript as an
`is_error` tool_result for the SECOND call, which is a tool_result after P
whose `tool_use_id` is not P's — so condition 3 no longer holds, and the retry
is allowed on its own terms without anything remembering a denial happened.

THE CEILING exists for the same reason advisor-consult-guard.py grew one on
2026-08-31, and the owner's own hard constraint for this session says to copy
it rather than argue past it again: the transcript this reads can lag the live
session, so a denial can be correct about the file and wrong about the world.
Three consecutive denials in one turn stand this arm down for that turn,
loudly, rather than wedging a session shut over a file that will not agree
with it. A successful pass, or a new message from the owner, resets the count
— `turn_id` below is copied from advisor-consult-guard.py's own fix for the
identical problem.

WHAT THIS DOES NOT CATCH, stated so nobody mistakes silence for safety: two
independent SYNCHRONOUS (non-background) calls made one-at-a-time across two
turns waste the same round trip, and this hook says nothing about them,
because a synchronous call's own result IS something to consume — the
mechanical signal this file relies on cannot tell an avoidable wait from a
needed one once the call blocks. Only `run_in_background: true` pairs are ever
unambiguously side-by-side.
"""

import contextlib
import json
import os
import sys
from pathlib import Path

#: Overridable so payload tests get their own file — see the sibling guards'
#: identical reasoning: a shared path makes tests order-dependent on each
#: other and on whatever live session happens to be open on this machine.
STATE_PATH = Path(
    os.environ.get("ONDOWAY_PARALLEL_GATE_STATE", "/tmp/ondoway-parallel-gate-state.json")
)

#: Three consecutive denials, matching advisor-consult-guard.py's
#: PRE_TOOL_MAX_BLOCKS and its reasoning exactly: enough to distinguish a
#: transcript the guard cannot read the truth out of from a rule being
#: ignored, without conceding the arm on the first or second refusal.
MAX_BLOCKS = 3

TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024

REASON_TEMPLATE = (
    "PARALLEL GATE — batch them into one message.\n\n"
    "This is a second `{tool}` call with run_in_background=true, issued in a "
    "separate turn right after the last background spawn launched, with "
    "nothing else completed in between. Both could have been requested "
    "together and started running at the same instant instead of one round "
    "trip apart.\n\n"
    "Put every independent background spawn you already know you need into "
    "ONE assistant message, as multiple tool calls in that one turn — not one "
    "spawn per message. If this one genuinely depends on something the last "
    "spawn's result told you, do that reading first; a real result in between "
    "satisfies this gate on the next attempt."
)

STANDDOWN_MESSAGE = (
    "PARALLEL GATE STOOD DOWN for this turn after "
    f"{MAX_BLOCKS} consecutive denials.\n\n"
    "That many denials in a row within one turn means this guard is reading a "
    "transcript that lags the live session rather than a rule being ignored — "
    "see advisor-consult-guard.py's own 2026-08-31 reversal for the identical "
    "failure. Refusing again would wedge the session, not enforce anything.\n\n"
    "The rule still stands: independent background spawns you already know "
    "you need belong in one message. The owner should know this arm is not "
    "enforcing it right now."
)


def allow():
    sys.exit(0)


def deny_tool(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
                "systemMessage": reason,
            }
        )
    )
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
    """Every JSONL record in the transcript's tail, oldest first.

    Unfamiliar top-level record types (this project's own transcripts carry
    bookkeeping rows like `attachment`, `agent-name`, `bridge-session` beside
    the `user`/`assistant` records) are returned as-is; every reader below
    filters on `type` itself; nothing here needs to recognise them.
    """
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
        lines = lines[1:]  # first line is half a record we cut through
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
    """A real person typing — classified by the record's STRUCTURE, never its
    text. Copied from advisor-consult-guard.py / shadow-guard.py: `isMeta` is
    the harness's own feedback, `isCompactSummary` is a machine-written
    summary with no origin stamp, and everything else falls back to reading
    `origin.kind`. Fails LOUD (an unfamiliar shape counts as human) because
    the dangerous direction for a boundary check is one that stops firing.
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


def turn_slice(entries):
    """Everything after the last human message — this turn. None if there is none."""
    last_human = -1
    for index, entry in enumerate(entries):
        if _is_human_turn(entry):
            last_human = index
    if last_human < 0:
        return None
    return entries[last_human + 1:]


def turn_id(entries):
    """A stable name for the CURRENT turn: the last human record's own uuid.

    Copied from advisor-consult-guard.py's identical fix. The fallback carries
    the human count rather than a bare constant so that two DIFFERENT turns
    lacking a uuid still produce different fingerprints — otherwise the owner
    speaking again would not reset the ceiling.
    """
    last = None
    humans = 0
    for entry in entries:
        if _is_human_turn(entry):
            humans += 1
            last = entry
    if last is None:
        return "no-human-in-window"
    return last.get("uuid") or last.get("timestamp") or f"human-{humans}"


def _assistant_blocks(entry):
    if entry.get("type") != "assistant":
        return []
    content = (entry.get("message") or {}).get("content")
    return [b for b in content or [] if isinstance(b, dict)]


def _message_id(entry):
    return (entry.get("message") or {}).get("id")


def is_background_spawn(name, tool_input):
    return name in ("Agent", "Bash") and (tool_input or {}).get("run_in_background") is True


def background_spawns(turn):
    """(position, tool_use_id, message_id) for every background spawn in the
    turn, oldest first."""
    out = []
    for index, entry in enumerate(turn):
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use":
                continue
            if is_background_spawn(block.get("name"), block.get("input")):
                out.append((index, block.get("id"), _message_id(entry)))
    return out


def refused_call_ids(turn):
    """Tool calls whose result came back an ERROR — they never ran.

    Same reasoning as advisor-consult-guard.py's `_failed_call_ids` and
    shadow-guard.py's `refused_call_ids`: a call a SIBLING guard refused is
    still written to the transcript as a `tool_use` block, and only its
    RESULT — a `tool_result` carrying `is_error: true` — tells the two apart.
    Counting a refused spawn as "a prior spawn that ran" is class 17b of the
    failures ledger: a boundary check reading a refusal as if it were work.
    """
    refused = set()
    for entry in turn:
        if entry.get("type") != "user":
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            if block.get("is_error"):
                call_id = block.get("tool_use_id")
                if call_id:
                    refused.add(call_id)
    return refused


def other_tool_result_after(turn, position, call_id):
    """A tool_result after `position` whose tool_use_id is NOT `call_id`.

    Evidence that some OTHER call's result was consumed before now — the mark
    of a genuine sequential dependency rather than an oversight. This is also
    what makes a denial self-clearing on retry: the denial's own `is_error`
    result is exactly such a tool_result, so the next attempt no longer sees
    "nothing else completed" and is judged fresh on its own terms.
    """
    for entry in turn[position + 1:]:
        if entry.get("type") != "user":
            continue
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                if block.get("tool_use_id") != call_id:
                    return True
    return False


def new_message_after(turn, position, message_id):
    """An assistant record after `position` whose message.id differs from
    `message_id` — evidence a fresh inference began without this spawn's
    company. See the module docstring for the measured id-sharing evidence.

    `message_id is None` returns False outright: with nothing to compare
    against, this condition cannot be established, and an established-can't-
    tell case must resolve to ALLOW, not to a guess.
    """
    if message_id is None:
        return False
    for entry in turn[position + 1:]:
        if entry.get("type") != "assistant":
            continue
        mid = _message_id(entry)
        if mid is not None and mid != message_id:
            return True
    return False


def spawn_should_be_denied(turn):
    """True iff the CURRENT, not-yet-recorded background spawn is the second
    half of an avoidable consecutive pair. See the module docstring for the
    four conditions this checks, in order.
    """
    valid = [s for s in background_spawns(turn) if s[1] not in refused_call_ids(turn)]
    if not valid:
        return False
    position, call_id, message_id = valid[-1]
    if other_tool_result_after(turn, position, call_id):
        return False
    return new_message_after(turn, position, message_id)


def main():
    # This IS a judge subprocess spawned by a sibling guard (truth-gate.py's
    # advisor/verifier, or any future one) — never gate its own tool calls.
    # Shared convention across this project's guards; see truth-gate.py.
    if os.environ.get("CLAUDE_NO_EXCUSES_JUDGE"):
        allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
    if not isinstance(payload, dict):
        allow()

    # Bail before ever touching the transcript: this fires on EVERY tool
    # call, and reading an 8 MB tail for a Read or an Edit is pure waste.
    tool = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    if not is_background_spawn(tool, tool_input):
        allow()

    transcript = payload.get("transcript_path")
    if not transcript:
        allow()  # nothing to compare this spawn against

    entries = records(transcript)
    turn = turn_slice(entries)
    if turn is None:
        allow()  # no human turn in view; nothing has been asked yet

    session = payload.get("session_id") or "unknown"
    state = read_state()
    here = turn_id(entries)
    if state.get("session") != session or state.get("turn") != here:
        state = {"session": session, "turn": here, "blocks": 0}

    if state.get("blocks", 0) >= MAX_BLOCKS:
        print(json.dumps({"systemMessage": STANDDOWN_MESSAGE}))
        sys.exit(0)

    if not spawn_should_be_denied(turn):
        state["blocks"] = 0
        write_state(state)
        allow()

    state["blocks"] = state.get("blocks", 0) + 1
    write_state(state)
    deny_tool(REASON_TEMPLATE.format(tool=tool))


if __name__ == "__main__":
    main()
