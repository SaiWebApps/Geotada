#!/usr/bin/env python3
"""Keep going. Stop only by asking a real question.

OWNER RULING, verbatim, 2026-09-01: "add a hook or a guard to force you to
proceed and only stop for seriously critical decisions. And in those cases -
show questions. Be proactive."

ONE ARM, on Stop. A turn that still has plan left to build, took actions, and
put no question on the table is a stall, and the reply is blocked with an
instruction to carry on into the next phase.

THE TRIGGER IS STRUCTURAL, NOT A READ OF MY OWN WORDS. Three yes-or-no
questions, none of which touches the text of the reply:

  1. Does `.claude/ledger/shared-tracker-plan.md` still name an unfinished
     phase?
  2. Did this turn call `AskUserQuestion`?
  3. Did this turn use any tool at all?

A guard that greps the reply for "shall I continue" or "let me know how you
want to proceed" is a guard I can walk past by choosing different words — and
this project has a written rule saying exactly that (`a-guard-must-not-read-my-
own-words`). None of the three questions above has a spelling to evade. The
first reads a file the owner writes, the other two read the transcript's own
structure.

`AskUserQuestion` IS THE ONLY SANCTIONED WAY TO STOP. That is the "show
questions" half of the ruling. A question written in prose at the end of a
reply is not a question: it is a stall wearing a question mark, the owner has
to type an answer nobody offered them options for, and the turn is over either
way. The tool puts real options on the screen and keeps the turn alive.

THE BLOCK IS A NUDGE, NOT A WALL. Nothing here asks for work to be redone,
re-verified, or re-reported. It asks for the turn not to END. The expected
response to a block is to keep working in the SAME turn, straight into the next
outstanding phase.

WHY THERE IS A CEILING, and why it is not optional. This guard's own conditions
get MORE true the more its nudge is obeyed. "Phases outstanding" cannot be
cleared inside one turn — P1 of that plan is a session's work — and "the turn
used tools" becomes true the instant the nudge is followed. So complying with a
block makes the next block more certain, and without a ceiling this guard would
refuse every reply for the rest of a multi-phase build. That is a boundary
check feeding on its own output: ledger class 17b, the same shape as the
`_failed_call_ids` deadlock in `advisor-consult-guard.py`, and this project has
shipped an unsatisfiable boundary twice already. `MAX_BLOCKS` consecutive
blocks in one turn therefore stand the arm down for that turn, loudly, so a
legitimate end-of-turn report eventually gets through.

WHY THE BLOCK FEEDBACK ITSELF CANNOT RESTART THE TURN. A blocked reply's reason
is written back into the transcript, and if it counted as a person speaking it
would become the new turn boundary — a fresh turn with no tools in it, which
this guard ALLOWS, so one block would silently disarm it forever after. Read
off a real transcript, 2026-09-01, the record is:

    {"type": "user", "isMeta": true,
     "message": {"content": "Stop hook feedback: <the reason>"}}

`_is_human_turn` returns False on `isMeta`, so the boundary holds. That is not
an assumption inherited from the sibling guard; it was measured, and there is a
test named for it.

NO PATTERN MATCHING. The plan is parsed by walking lines and asking string
methods; the transcript is walked as records and its fields compared. A pattern
catches only the spellings someone thought of.
"""

import contextlib
import json
import os
import string
import sys
import time
from pathlib import Path

#: Where the ceiling keeps its tally. Overridable so the payload tests get their
#: own file: they drive the guard as a subprocess, and sharing one path would
#: make a test run reach into whatever live session is open on this machine —
#: and make the tests order-dependent on each other.
STATE_PATH = Path(
    os.environ.get("ONDOWAY_PROCEED_STATE", "/tmp/ondoway-proceed-guard-state.json")
)

#: The ceiling, copied from `PRE_TOOL_MAX_BLOCKS` in `advisor-consult-guard.py`,
#: value and reasoning both. Three rather than one or two because a genuine
#: stall should be pushed back on more than once before the guard concedes, and
#: rather than five because past three the session is burning turns against a
#: condition that a single turn cannot clear. See the module docstring: this
#: guard's conditions get more true the more its nudge is obeyed, so the ceiling
#: is what keeps it from becoming an unsatisfiable boundary.
MAX_BLOCKS = 3

#: The word that retires a phase, matched as a WORD and never as a substring.
#:
#: MEASURED BY THIS GUARD'S OWN TEST, 2026-09-01, before the check was tightened:
#: `ABANDONED` is A-B-A-N-D-O-N-E-D, and `DONE` sits inside it at index 4 — in
#: capitals, so being case-sensitive rescues nothing. `### P3 — ABANDONED
#: dashboard approach` was read as a FINISHED phase and the guard went silent on
#: it. A guard that stops firing looks exactly like a satisfied one.
#:
#: Splitting the heading into words and trimming punctuation asks the question
#: that was actually meant. With that, folding case is safe as well as more
#: accurate: `abandoned` is not the word `done` in any casing, while a heading
#: written `Done 2026-09-02` plainly means the phase is finished.
FINISHED_MARKER = "DONE"

#: Trimmed off a word before comparing it. Markdown wraps a heading's words in
#: emphasis and the owner ends them with punctuation, so `**DONE**`, `(DONE)` and
#: `DONE.` all have to answer the same as `DONE`. The two dashes are written as
#: escapes rather than as themselves: the plan's headings use an em dash, and a
#: literal one here is indistinguishable on screen from an en dash or a hyphen.
TRIMMED = string.punctuation + chr(0x2014) + chr(0x2013)

TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024

HEADLINE = "KEEP GOING — THIS IS A NUDGE, NOT A WALL."


def allow():
    sys.exit(0)


def block(reason):
    """End the reply with a reason. Always exit 0: a guard that crashes is a
    guard that is switched off, so the decision travels in the printed JSON and
    never in the exit code."""
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


def _is_human_turn(entry):
    """A real person typing — classified by the record's STRUCTURE, never its text.

    Copied from `advisor-consult-guard.py`, where the field counts behind each
    branch were measured on this project's own transcript. The load-bearing
    branch for THIS guard is `isMeta`: a blocked reply's reason comes back as an
    `isMeta` user record, and if that counted as a person speaking it would open
    a fresh turn with no tools in it, which this guard allows — one block would
    disarm the guard for good. See the module docstring for the measured shape.

    FAILS LOUD. An unrecognised record with text and no `isMeta` counts as
    human, so an unfamiliar shape costs at most one missed nudge rather than
    silently disarming the guard.
    """
    if entry.get("type") != "user":
        return False

    if entry.get("isMeta"):
        return False

    # The compaction summary is written by the harness, not typed by anyone, and
    # it carries plain text with no `origin` stamp and no `isMeta`.
    if entry.get("isCompactSummary"):
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


def turn_id(entries):
    """A stable name for the CURRENT turn, so the ceiling resets when the owner
    speaks and not merely when the process restarts.

    The last human record's own uuid, because that record IS the turn boundary
    `turn_slice` computes. The fallback carries the human count so that two
    DIFFERENT turns whose records lack both uuid and timestamp still fingerprint
    differently — a bare constant there would mean the owner speaking never
    cleared the ceiling.
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
    """The content blocks of an assistant record, or an empty list."""
    if entry.get("type") != "assistant":
        return []
    content = (entry.get("message") or {}).get("content")
    return [block for block in content or [] if isinstance(block, dict)]


# --------------------------------------------------------------- the written plan


def plan_path():
    """The plan this guard governs.

    Derived from this file's own location rather than from the payload's `cwd`,
    because the hook and the ledger move together: `.claude/hooks/` up one to
    `.claude/`, then down into `ledger/`. Overridable so the payload tests can
    point at a plan of their own instead of the owner's live one.
    """
    override = os.environ.get("ONDOWAY_PROCEED_PLAN")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "ledger" / "shared-tracker-plan.md"


def _heading_text(line):
    """The text of a markdown heading, or None when this line is not one.

    Any heading level is accepted, not just `###`. The plan writes phases as
    `### P<N> — ...`, but a phase demoted to `##` or promoted to `####` is still
    a phase, and missing one would make the guard go quiet — the one direction
    that matters, since a guard that stops firing looks exactly like a satisfied
    one.
    """
    stripped = line.strip()
    if not stripped.startswith("#"):
        return None
    return stripped.lstrip("#").strip()


def _phase_label(text):
    """`P0`, `P17` — the leading phase name of a heading, or None.

    Walks the characters and asks the language whether each is a digit, rather
    than matching a shape. `P` alone is not a phase, so a heading like
    `Phase notes` or `Plan` returns None: the digits are what make it a phase.
    """
    if not text:
        return None
    if text[0] not in ("P", "p"):
        return None
    end = 1
    while end < len(text) and text[end].isdigit():
        end += 1
    if end == 1:
        return None
    return text[:end]


def says_finished(heading):
    """Does this heading declare its phase finished?

    Walks the heading's words and compares each one, rather than searching the
    line for four letters in a row. See FINISHED_MARKER: `ABANDONED` contains
    `DONE`, so a substring test retires a phase that was explicitly given up on.
    """
    return any(word.strip(TRIMMED).upper() == FINISHED_MARKER for word in heading.split())


def outstanding_phases(path):
    """Phases the written plan still owes.

    Returns a list of heading strings, oldest first. Returns None when there is
    no plan file at all — a DIFFERENT answer from "the plan is finished", and
    the caller treats it differently: this guard only governs a run that has a
    written plan, so no plan means no opinion.

    EACH HEADING IS JUDGED ON ITS OWN, and headings are NOT collapsed by phase
    label. Measured on the real plan at 15:10 on 2026-09-01, while this guard
    was being written: the file had just been rewritten to carry TWO headings per
    phase — a status one (`### P1 — DONE 2026-09-01.`) and a standing design one
    (`### P1 — what was built`) that will never say DONE. Collapsing by label —
    "P1 is finished if any P1 heading says DONE" — was tried against that same
    file and marked every phase finished, including
    `### P2 — engine side DONE 2026-09-01. Front half in progress.`, which says
    in its own words that it is not. That would have left the guard silent on the
    one phase actually outstanding.

    So the cost is paid in the other direction: a standing design section is
    listed as owed. That is noise, it is bounded by MAX_BLOCKS, and the genuinely
    outstanding phase is named alongside it. A guard that over-lists is read and
    corrected; a guard that goes quiet is indistinguishable from a satisfied one.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    out = []
    for line in text.split("\n"):
        heading = _heading_text(line)
        if heading is None:
            continue
        if _phase_label(heading) is None:
            continue
        if says_finished(heading):
            continue
        out.append(heading)
    return out


# ------------------------------------------------------------- the turn's shape


def asked_a_question(turn):
    """Did this turn call `AskUserQuestion`?

    The measured shape, read off this project's own transcript on 2026-09-01, is
    an ordinary tool call — not the server-side shape the advisor uses:

        {"type": "tool_use", "id": "toolu_...", "name": "AskUserQuestion",
         "input": {"questions": [...]}}

    Deliberately lenient: a call whose result came back an error still counts.
    The strict reading — "only a question that was successfully ANSWERED lets
    you stop" — is unsatisfiable by the remedy this guard prints, which is the
    failure class it exists downstream of. An allow-path must always be
    reachable.
    """
    for entry in turn:
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use":
                continue
            if block.get("name") == "AskUserQuestion":
                return True
    return False


def tools_used(turn):
    """Did this turn actually do anything? A turn that only talked is not a stall.

    Counts every `tool_use` block, including calls that came back as errors. A
    failing test run is the single most common thing to stall on — `pytest` exits
    non-zero, its result carries `is_error`, and the turn stops to ask whether to
    keep going. Excluding errored calls the way `advisor-consult-guard.py`
    excludes them from its destructive tally would wave through exactly that
    stall. The two guards ask different questions of the same records: that one
    asks "did this change the world", which a failed command did not; this one
    asks "was this turn working", which a failed command certainly was.

    `server_tool_use` is deliberately NOT counted. The only tool that records
    that way here is `advisor`, which the sibling guard forces into every single
    turn, so counting it would mean no turn is ever tool-free and the allowance
    below could never fire. Consulting and then answering a question is not
    work; it is the shape of a turn that should be allowed to end.
    """
    for entry in turn:
        for block in _assistant_blocks(entry):
            if block.get("type") == "tool_use":
                return True
    return False


# ------------------------------------------------------------------- the messages


def refusal(outstanding):
    owed = "\n".join(f"  - {heading}" for heading in outstanding)
    nxt = outstanding[0]
    return (
        HEADLINE + "\n\n"
        "You are ending the turn with work still on the plan and no question on "
        "the table.\n\n"
        ".claude/ledger/shared-tracker-plan.md still owes:\n\n"
        f"{owed}\n\n"
        "Nothing here asks you to redo, re-verify or re-report anything. It asks "
        "you not to STOP. Carry straight on, in THIS SAME TURN, into:\n\n"
        f"  {nxt}\n\n"
        "IF A DECISION GENUINELY BLOCKS YOU, stopping is allowed — but there is "
        "exactly one way to do it: call the `AskUserQuestion` tool with real, "
        "concrete options. A question written in prose is not a question. It "
        "ends the turn, it offers the owner nothing to choose between, and it "
        "reads as giving up. The tool puts the options on the screen and keeps "
        "the turn alive.\n\n"
        "Owner's ruling, 2026-09-01: \"add a hook or a guard to force you to "
        "proceed and only stop for seriously critical decisions. And in those "
        "cases - show questions. Be proactive.\"\n\n"
        f"This guard stands down after {MAX_BLOCKS} blocks in one turn, so a "
        "genuine end-of-turn report is never trapped."
    )


def stand_down():
    print(
        json.dumps(
            {
                "systemMessage": (
                    "PROCEED GUARD STOOD DOWN for this turn after "
                    f"{MAX_BLOCKS} consecutive blocks.\n\n"
                    "The conditions this guard blocks on cannot be cleared "
                    "inside a single turn — a phase of that plan is a session's "
                    "work, and 'this turn used tools' only gets more true the "
                    "more the nudge is obeyed. Blocking again would wedge the "
                    "session rather than enforce anything.\n\n"
                    "The rule still stands: keep going while the plan owes work, "
                    "and stop only by calling AskUserQuestion with real options. "
                    "The owner should know this guard is not enforcing it right "
                    "now."
                )
            }
        )
    )
    sys.exit(0)


def main():
    if os.environ.get("CLAUDE_NO_EXCUSES_JUDGE"):
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

    outstanding = outstanding_phases(plan_path())
    if outstanding is None:
        allow()  # no written plan: this guard has no opinion about this run
    if not outstanding:
        allow()  # every phase heading says DONE

    entries = records(transcript)
    turn = turn_slice(entries)
    if turn is None:
        allow()  # no human turn in view; nothing was asked

    session = payload.get("session_id") or "unknown"
    here = turn_id(entries)
    state = read_state()
    # A new session, or the owner speaking, starts the tally again. Both are a
    # genuinely new thing to be working on, not the self-feeding condition the
    # ceiling exists for.
    if state.get("session") != session or state.get("turn") != here:
        state = {"session": session, "turn": here, "blocks": 0, "ts": time.time()}

    def let_through():
        state["blocks"] = 0
        write_state(state)
        allow()

    if asked_a_question(turn):
        let_through()  # the sanctioned way to stop

    if not tools_used(turn):
        let_through()  # a turn that only answered a question is not a stall

    if state.get("blocks", 0) >= MAX_BLOCKS:
        stand_down()

    state["blocks"] = state.get("blocks", 0) + 1
    write_state(state)
    block(refusal(outstanding))


if __name__ == "__main__":
    main()
