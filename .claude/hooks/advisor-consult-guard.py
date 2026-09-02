#!/usr/bin/env python3
"""Nothing happens in a turn before the advisor is consulted and its plan printed.

TWO ARMS.

  PreToolUse  No tool runs until this turn contains an advisor consult AND a
              visible plan following it. This is the arm that matters, because
              it gates ACTIONS. Every destructive action gets its own fresh
              consult on top of that.
  Stop        No reply ends the turn without a consult in it. On any model
              that is not Fable, the turn's LAST consult must also come after
              its last action, with a written report in between, so the
              advisor has seen the finished work before the owner does.

WHY THE PRE-TOOL ARM EXISTS. The Stop arm alone gates only what is SAID. A turn
could consult once, then delete five hundred files, and the Stop arm would be
satisfied. That is not a hypothetical: a turn that consulted once at the start
went on to sweep 544 files out of the repository, and one of them was a file the
test suite reads — lost to a case-sensitivity bug in the delete rule that a
consult immediately before the sweep would have caught. Consulting about a plan
is not consulting about the act.

WHY THE PLAN MUST BE PRINTED. A consult whose answer is never written down is
indistinguishable from a consult that was ignored. Printing the numbered plan
before acting makes the advice visible to the person who has to live with the
result, and makes a silent deviation from it obvious.

WHY THE CLOSING CONSULT EXISTS. Owner ruling, 2026-09-01, for Opus or anything
that is not Fable: "FORCE the model to ALWAYS check in with the advisor and
then show the advisor that it listened. It should be blocked and should choke
on itself until the advisor is happy." The advisor forwards the live
conversation, so a consult placed AFTER the last action is the advisor seeing
what was actually done against what it advised; a reply whose last consult
predates its last action has shown the advisor a plan and hidden the result.
The advisor's own answer is stored encrypted — of the 233 advisor results
across this project's transcripts, surveyed 2026-09-01, 228 are
{"type": "advisor_redacted_result", "encrypted_content": ...} blocks and the
other five are errors; none is readable — so its verdict cannot be read by a
hook. What CAN be enforced is that it was asked
after the work, with a report of the work in front of it, and that its answer
was acted on: an action taken after the closing consult reopens the
requirement, so "fix this" from the advisor forces another closing consult
once the fix is in.

NO CEILINGS, and this is a reversal. An earlier version stood the pre-tool arm
down after three consecutive refusals, and the Stop arm after five, on the
theory that the transcript file lagged the live conversation so the remedy
could not be seen. Owner ruling, 2026-09-01: "You must consult the advisor.
Always. No lags. Fix the lags." Both ceilings are gone, along with the state
file that kept their tallies — a file that turned out to be shared by every
session on the machine, so a parallel session reset the count every few
minutes and the ceiling was never even deterministic. The three things the
ceilings were papering over are fixed where they actually live:

  1. THE FILE LAGS THE CALL — measured. Claude Code appends every block of an
     assistant message in one batch after the message completes, and the
     PreToolUse hook can run before that batch lands. Session a798c91b,
     2026-09-01: a Bash call's own record is stamped 22:13:21.918Z, the hook
     ran at 22:13:21.95Z, and it saw a file with no consult in it — the
     consult, its result and the plan were all in the same unlanded batch.
     Later in that session the file held 392 records from 22:26:41Z until
     past 22:31Z while tool calls kept coming. So this guard now WAITS for
     the record of the very call it is gating — the payload's `tool_use_id`,
     present on every payload measured — before it reads anything, up to
     LAG_WAIT_SECONDS. The file is append-only, so once that record is there
     everything before it is too. If it does not land in time, the refusal
     says so and the next attempt waits again. No count, no stand-down.

  2. THE PLAN WAS NEVER A TEXT BLOCK — measured. On Claude Fable 5.1 through
     claude-desktop (Claude Code 2.1.255), every visible line after a turn's
     first one is stored not as {"type": "text"} but as a {"type": "thinking"}
     block whose server signature names the kind "narration", holding a
     one-paragraph rendering of what was said: ten of them in one session ran
     184 to 617 characters, median 278, and the shortest stood in for a
     printed plan of about 1,500. Opus 5 sessions in the same survey store
     hundreds of mid-turn text blocks, Sonnet 5 sessions a handful, and
     neither stores narration at all. A check that counted only text blocks
     was unsatisfiable on Fable for the whole turn, and the ceiling was
     invented to escape it. Visible prose is now text blocks PLUS narration
     blocks, and the floor is set from the measured narration length rather
     than a text block's.

  3. A SPAWNED AGENT CANNOT CONSULT. The advisor is a server tool of the main
     session, so a subagent's actions can never satisfy this arm, and the
     ceiling was what let qa, judge, shadow and the rest through — silently,
     after three refusals apiece. Measured 2026-09-01: a subagent's hook
     payload carries `agent_id` and `agent_type`, and its `transcript_path`
     is the MAIN session's file. The Agent call that spawned it was itself
     gated, and the prompt it was given is the plan it follows, so its calls
     are let through on that structural stamp. What a subagent may do is
     bounded by its prompt and its agent definition, not by this file — said
     here rather than implied.

MECHANICAL, NOT SEMANTIC. Nothing here judges whether a consult was thoughtful or
whether the printed plan is a good one. It asks yes-or-no questions of the
transcript: did an advisor record appear in this turn, did visible prose of real
length follow it, did a look at the code precede it, did a consult follow the
previous destructive command, and — off Fable — did the last consult follow the
last action. The transcript is the record; agreeing to a rule and skipping it
are identical in every place except there.

NO PATTERN MATCHING on records: the JSONL entries are walked and their fields
compared, because a pattern catches only the spellings someone thought of.
"""

import base64
import json
import os
import sys
import time
from pathlib import Path

#: The shortest visible message that can plausibly BE a plan or a report.
#: Measured 2026-09-01 on this project's own transcript: a narration block —
#: the harness's rendering of a printed plan on Fable 5.1 — ran 184 to 617
#: characters across ten of them, however long the plan behind it was; a bare
#: acknowledgement ("consulting now", "will do") runs under 100. 150 sits
#: between them. A text plan used to need 250; the floor is now 150 for text
#: and narration alike, deliberately, so both channels are held to one rule.
#: Length is used rather than wording on purpose: a rule that reads my words is
#: a rule I can satisfy by choosing different words, and the only way past a
#: length floor is to actually write something.
MIN_PLAN_CHARS = 150

#: How long the pre-tool arm waits for the gated call's own record to land
#: before judging the file — see the module docstring. Ten seconds against the
#: twenty-second hook timeout in settings.json. Overridable so the payload
#: tests can run the never-lands case in a fraction of a second; a malformed
#: override falls back to the default rather than crashing the hook at import.
try:
    LAG_WAIT_SECONDS = float(os.environ.get("ONDOWAY_ADVISOR_LAG_WAIT", "10"))
except ValueError:
    LAG_WAIT_SECONDS = 10.0
LAG_POLL_SECONDS = 0.05
#: The gated call is always among the newest records in the file, so its id is
#: looked for in the last megabyte rather than the whole file on every poll.
LAG_TAIL_BYTES = 1024 * 1024

#: Commands that change the world in a way an apology cannot undo. Each one needs
#: a consult of its own, not merely a consult somewhere earlier in the turn.
#: Plain substrings, compared against the command with surrounding spaces
#: normalised — deliberately a SHORT list, because a guard that fires on ordinary
#: work is a guard that gets deleted, and then it guards nothing.
DESTRUCTIVE_MARKERS = (
    "rm -r", "rm -f", "rmtree", "git rm", "git commit", "git push", "git reset",
    "git checkout", "git clean", "git branch -d", "docker compose down",
    "docker rm", "docker stop", "docker kill", "drop database", "truncate",
    "--apply", "--force", "-delete",
)

#: Tools the PreToolUse arm never blocks. `advisor` is the remedy this guard
#: demands, so blocking it would make the guard unsatisfiable. The rest are the
#: tools that produce the reply itself, plus the read-only tools that LOOK at the
#: codebase.
#:
#: Reading is not acting, and the exemption is load-bearing rather than lenient:
#: the grounding rule below requires a look at the real code BEFORE the consult,
#: and without these four exempt that rule would be unsatisfiable — every way of
#: grounding would itself be blocked for want of a consult. A guard that cannot
#: be satisfied by the remedy it prints is the class-17 failure this project has
#: already shipped twice, so the escape is designed in rather than discovered.
#: Bash, Write, Edit and Agent stay gated: those change things or spend money.
EXEMPT_TOOLS = (
    "advisor", "AskUserQuestion", "ExitPlanMode", "TodoWrite",
    "Read", "Grep", "Glob", "mcp__codegraph__codegraph_explore",
)

#: Looking at the actual code. The advisor has NO TOOLS — it forwards this
#: conversation and reads nothing else — so anything not already in the
#: transcript is invisible to it, and advice given before one of these ran is
#: advice about software in general.
#:
#: Measured 2026-08-31. Asked for screenshot proof that a browser ran the test
#: suite, the advisor designed a DevTools-attach scheme from scratch; the
#: repository already had tests/test_workbench_ui.py, with a _take_screenshot
#: helper and 36 call sites driving the real product through Playwright. The
#: advisor could not have known — that file had never been named in the
#: conversation. The owner's verdict on the delivered result: "means nothing".
GROUNDING_TOOLS = ("Read", "Grep", "Glob", "mcp__codegraph__codegraph_explore")
TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024

HEADLINE = "NO CONSULT, NO REPLY."


def allow():
    sys.exit(0)


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def deny_tool(reason):
    """Refuse the tool call. Always exit 0: a guard that crashes is a guard that
    is switched off, and the decision travels in the printed JSON, not the code.
    """
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


def _tail_text(transcript_path):
    """The newest LAG_TAIL_BYTES of the file as text, or nothing if it cannot be read."""
    try:
        with open(transcript_path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            handle.seek(max(0, end - LAG_TAIL_BYTES))
            return handle.read().decode("utf-8", "replace")
    except OSError:
        return ""


def wait_for_call_record(transcript_path, tool_use_id, wait_seconds=None):
    """Block until the record of the call being gated is on disk, or time runs out.

    Returns True when it landed. The file is append-only, so the presence of
    this call's id — first written in its own `tool_use` record — means every
    record before it is there too, and the judgement below is about the
    conversation rather than about a file that is behind it. Without an id
    there is nothing to wait for and the file is judged as it stands; every
    payload measured on 2026-09-01 carried one, so that branch is an
    older-harness fallback, not the norm.
    """
    if not isinstance(tool_use_id, str) or not tool_use_id:
        return False
    if wait_seconds is None:
        wait_seconds = LAG_WAIT_SECONDS
    deadline = time.monotonic() + wait_seconds
    while True:
        if tool_use_id in _tail_text(transcript_path):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(LAG_POLL_SECONDS)


def _late_note(caught_up):
    """Appended to a refusal issued over a file that had not caught up, so the
    session retries the call rather than performing a remedy it has already
    performed. Nothing here says the verdict was wrong; it says what it was
    about."""
    if caught_up:
        return ""
    return (
        "\n\nTHE TRANSCRIPT FILE HAD NOT CAUGHT UP: this very call had still not been "
        f"recorded after {LAG_WAIT_SECONDS:g} seconds, so the verdict above is about "
        "the file as it stood, which may be behind the conversation. If the remedy "
        "has already been done, try the call again — the guard waits for the file on "
        "every attempt."
    )


def _is_subagent_call(payload):
    """A tool call made by a spawned agent rather than by the session itself.

    Read off a real payload, 2026-09-01: a subagent's PreToolUse payload carries
    `"agent_id": "a7a21be1cd7843808", "agent_type": "claude"`, and the main
    session's own payloads carry neither. See the module docstring for why a
    spawned agent is not held to a consult it cannot perform.
    """
    return bool(payload.get("agent_id") or payload.get("agent_type"))


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

    # THE COMPACTION SUMMARY. Written by the harness when a session runs out of
    # context, and it is a `user` record carrying plain text with NO `origin`
    # stamp and NO `isMeta`, so the fail-loud default below called it a person
    # typing. Read off this session's own transcript, 2026-08-31:
    #
    #   {"type": "user", "isCompactSummary": true,
    #    "isVisibleInTranscriptOnly": true,
    #    "message": {"content": "This session is being continued from a previous
    #                            conversation that ran out of context. ..."}}
    #
    # Nobody typed it. Left classified as human it becomes the last human record
    # in the file, so every compaction demands a fresh consult at the exact moment
    # the session has the least context to consult ABOUT — and in a 21 MB
    # transcript it made a machine-written summary the boundary of "this turn".
    # This is a POSITIVE machine marker, so the fail-loud default is untouched:
    # a shape carrying neither this field nor an origin stamp still counts human.
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
    """Everything after the last human message — this turn.

    When no human record is in view the whole window IS the turn. That happens
    for a turn that has outgrown the window and for a file that has nothing in
    it yet, and both are judged rather than waved through: a consult must then
    appear somewhere in what can be seen, which fires once too often rather
    than once too few.
    """
    last_human = -1
    for index, entry in enumerate(entries):
        if _is_human_turn(entry):
            last_human = index
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


def _assistant_blocks(entry):
    """The content blocks of an assistant record, or an empty list."""
    if entry.get("type") != "assistant":
        return []
    content = (entry.get("message") or {}).get("content")
    return [block for block in content or [] if isinstance(block, dict)]


def consulted(turn):
    """Did an advisor call happen in this turn? Either the call or its result."""
    return consult_index(turn) >= 0


def consult_index(turn):
    """Position in `turn` of the LAST advisor record, or -1 if there is none.

    The last rather than the first, because a turn may consult several times and
    what matters is whether the most recent advice precedes what happens next.
    """
    found = -1
    for index, entry in enumerate(turn):
        for block in _assistant_blocks(entry):
            kind = block.get("type")
            called = kind in ADVISOR_CALL_TYPES and block.get("name") == "advisor"
            if called or kind == ADVISOR_RESULT_TYPE:
                found = index
    return found


def grounded_before(turn, index):
    """Did anyone LOOK at the real code before the consult at `index`?

    Walks tool_use blocks structurally and compares tool names — no text is read,
    so this cannot be satisfied by describing a codebase instead of opening it.

    Before, not after, and that ordering is the whole point. The advisor sees the
    conversation as it stands when it is called; a file read afterwards is a file
    it never saw. Grounding that arrives late informs the implementer and leaves
    the advice exactly as uninformed as it was.
    """
    for entry in turn[:index]:
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use":
                continue
            if block.get("name") in GROUNDING_TOOLS:
                return True
    return False


def _is_narration(block):
    """A visible line the harness stored as a signed thinking block.

    Measured on this project's own transcript, 2026-09-01 (session a798c91b):
    on Claude Fable 5.1 through claude-desktop, every visible line after a
    turn's first one arrives as {"type": "thinking", "thinking": "<one
    paragraph>", "signature": "CAQSjRQKEQgRGAI4AUIJbmFycmF0aW9u..."} rather
    than as a text block. The kind is not a field of the record; it sits inside
    the server signature, whose first bytes spell "narration" (or "thinking",
    for the private kind) once the base64 is decoded. That prefix is the only
    structural handle there is. A block whose signature cannot be decoded, or
    names no such kind — every Opus 5 and Sonnet 5 thinking block in the same
    survey — is treated as private thinking and not counted: the direction
    that refuses, never the one that waves through.
    """
    if block.get("type") != "thinking":
        return False
    signature = block.get("signature")
    if not isinstance(signature, str) or not signature:
        return False
    head = signature[:96]
    try:
        raw = base64.b64decode(head + "=" * (-len(head) % 4))
    except (TypeError, ValueError):
        return False
    return b"narration" in raw


def visible_chars(turn, start, stop=None):
    """Characters of owner-visible prose in turn[start:stop]: text blocks plus
    narration blocks, summed. Summed rather than checked one block at a time,
    because a plan written as an opening line, then a numbered list, then a
    closing line arrives as three records and no single one need clear the
    floor on its own. The question is whether it was written, not whether it
    was written in one breath.
    """
    printed = 0
    for entry in turn[start:stop]:
        for block in _assistant_blocks(entry):
            if block.get("type") == "text":
                printed += len(block.get("text") or "")
            elif _is_narration(block):
                printed += len(block.get("thinking") or "")
    return printed


def plan_printed_after(turn, index):
    """Did visible prose of real length follow the consult at `index`?"""
    return visible_chars(turn, index + 1) >= MIN_PLAN_CHARS


def _overwrites_existing_file(payload):
    """A Write whose target already exists — destruction with no command to scan.

    The marker list reads shell commands, and a Write carries none: it names a
    path and a body, and if something is already at that path the previous
    contents are gone. That is the same irreversible act as `rm` followed by a
    new file, reached through a different tool, so it earns the same fresh
    consult. A Write to a path that does not exist yet creates something and
    destroys nothing, and is left alone.

    Edit is deliberately NOT here. An Edit must match existing text to apply, so
    it cannot silently erase a file, and gating every Edit behind its own consult
    would make ordinary work impossible — which is how a guard gets deleted.
    """
    if (payload.get("tool_name") or "") != "Write":
        return False
    target = (payload.get("tool_input") or {}).get("file_path")
    return isinstance(target, str) and bool(target) and Path(target).exists()


def _command_of(payload):
    """The shell command a Bash call would run, lowercased and space-normalised.

    Normalising runs of whitespace to single spaces means `git   rm` and a command
    split across lines are compared as the same thing, so the marker list does not
    have to carry every spacing a command can be written with.
    """
    tool_input = payload.get("tool_input") or {}
    raw = tool_input.get("command")
    if not isinstance(raw, str):
        return ""
    return " ".join(raw.lower().split())


def is_destructive(command):
    return any(marker in command for marker in DESTRUCTIVE_MARKERS)


def _call_results(turn):
    """Every tool call's outcome in the turn, keyed by call id: True when its
    result came back clean, False when it came back an error.

    Read off a real transcript: a call's result is a `tool_result` block in a
    later user record, `is_error: true` when it was refused or failed. A call
    with no result at all has not run — it is the call being gated right now,
    or a sibling issued in the same message and still queued behind it.
    """
    results = {}
    for entry in turn:
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            call_id = block.get("tool_use_id")
            if call_id:
                results[call_id] = not block.get("is_error")
    return results


def _failed_call_ids(turn):
    """Tool calls whose result came back an ERROR — including this guard's own denials.

    A refused tool call is still written to the transcript as a `tool_use` block;
    only its RESULT distinguishes it. Measured 2026-08-31, when the destructive
    scan read the calls and not the results and counted a `git commit` this very
    guard had just refused as an act that ran: refusing it created the condition
    for refusing it again, three times, with the remedy performed correctly
    before each. Class 17b of the failures ledger — a boundary check counting
    its own output as input. The destructive scan now keys on completion (see
    destructive_calls_in); this set keeps a refused call out of the closing
    consult arm's idea of "the last action".
    """
    return {call_id for call_id, ran in _call_results(turn).items() if not ran}


def destructive_calls_in(turn):
    """Positions in `turn` of acts that ACTUALLY changed the world.

    Two kinds. A Bash call whose command carries a destructive marker, and ANY
    Write — because by the time this runs the written file exists either way, so
    whether that Write created or overwrote is no longer answerable from the
    transcript. Counting every Write costs an extra consult after writing a new
    file; not counting them would let an overwrite go unnoticed. The cheap
    mistake is the one to make.

    ONLY CALLS THAT RAN COUNT: a call with a clean result in the turn. A refused
    call changed nothing (the 2026-08-31 self-deadlock, class 17b). A call with
    no result yet has not happened — and because the guard waits for the whole
    batch to land before judging, such calls ARE in the turn: the call being
    gated, and any sibling issued in the same message. Counting those would make
    every pair of destructive calls in one message refuse each other, and every
    destructive call refuse itself.

    The tradeoff, stated rather than hidden: a destructive command that ran and
    then errored is skipped too, though it may have changed something before it
    failed. That direction costs one missed consult on a half-completed command.
    The other direction costs the session, with no remedy — the guard breaking.
    """
    ran = {call_id for call_id, ok in _call_results(turn).items() if ok}
    out = []
    for index, entry in enumerate(turn):
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use":
                continue
            if block.get("id") not in ran:
                continue  # refused, errored, or not yet run: it changed nothing
            name = block.get("name")
            if name == "Write":
                out.append(index)
                continue
            if name != "Bash":
                continue
            raw = (block.get("input") or {}).get("command")
            if isinstance(raw, str) and is_destructive(" ".join(raw.lower().split())):
                out.append(index)
    return out


def last_acting_call_index(turn):
    """Position in `turn` of the last tool call that ACTED — not exempt, not
    refused — or -1 if the turn only looked and consulted."""
    failed = _failed_call_ids(turn)
    found = -1
    for index, entry in enumerate(turn):
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use":
                continue
            if block.get("name") in EXEMPT_TOOLS:
                continue
            if block.get("id") in failed:
                continue
            found = index
    return found


def session_model(entries):
    """The model of the newest assistant record in view, or "" if none names one.

    Read off every assistant record in this project's transcripts, 2026-09-01:
    `message.model` is "claude-fable-5-1", "claude-opus-5", "claude-sonnet-5"
    and so on — and "<synthetic>" on the stub the harness writes in place of an
    answer when the API errors, which names no model and is walked past. The
    newest real record rather than the first, so a session switched mid-way is
    judged by what is answering now.
    """
    for entry in reversed(entries):
        if entry.get("type") != "assistant":
            continue
        model = (entry.get("message") or {}).get("model")
        if isinstance(model, str) and model and not model.startswith("<"):
            return model
    return ""


def is_fable(model):
    """Fable is the model the owner scoped the closing consult AWAY from. A
    session whose model cannot be read is held to the stricter rule."""
    return "fable" in model.lower()


def handle_pre_tool_use(payload, turn, caught_up):
    """Gate the action itself. Four questions, each answered by the transcript."""
    tool = payload.get("tool_name") or ""
    late = _late_note(caught_up)

    index = consult_index(turn)
    if index < 0:
        deny_tool(
            "NO CONSULT, NO ACTION.\n\n"
            f"This turn has not called the advisor, and `{tool}` would act on it "
            "anyway. Consulting after the fact is not consulting.\n\n"
            "Call `advisor()` now. It takes no arguments and forwards this whole "
            "conversation. Then PRINT the step-by-step plan it gives you, in "
            "numbered steps, and follow that plan." + late
        )

    if not plan_printed_after(turn, index):
        deny_tool(
            "THE PLAN WAS NOT PRINTED.\n\n"
            "The advisor was consulted in this turn, but nothing of substance was "
            "written down afterwards, so the advice it gave is invisible to the "
            "person who has to live with the result — and a silent deviation from "
            "it would be invisible too.\n\n"
            "Print the advisor's step-by-step plan as numbered steps "
            f"(at least {MIN_PLAN_CHARS} characters of visible text), then act on it."
            + late
        )

    if not grounded_before(turn, index):
        deny_tool(
            "THE ADVICE WAS NOT GROUNDED IN THIS CODEBASE.\n\n"
            "The advisor was consulted and a plan was printed, but nothing in this "
            "turn looked at the actual code before asking. The advisor has NO "
            "TOOLS — it forwards this conversation and reads nothing else — so "
            "anything not already written here is invisible to it, and what comes "
            "back is advice about software in general.\n\n"
            "Measured 2026-08-31: asked to prove with screenshots that a browser "
            "ran the test suite, it designed a DevTools-attach scheme from "
            "scratch. tests/test_workbench_ui.py was already in the repository, "
            "with a _take_screenshot helper and 36 call sites driving the real "
            "product through Playwright. The plan was followed, and the owner's "
            "verdict on the result was \"means nothing\".\n\n"
            "Three steps, and the first two are never blocked:\n"
            "  1. LOOK: `mcp__codegraph__codegraph_explore` on the symbols in "
            "question, or `Read` the files. Read/Grep/Glob/codegraph are exempt "
            "from this guard precisely so this step is always available.\n"
            "  2. CONSULT again, so the advisor sees what you just read.\n"
            "  3. Print the plan, then act." + late
        )

    # A destructive act with another one already run since the last consult would
    # be the second in a row on a single piece of advice.
    command = _command_of(payload)
    destroys = (command and is_destructive(command)) or _overwrites_existing_file(payload)
    if destroys and any(position > index for position in destructive_calls_in(turn)):
        deny_tool(
            "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT.\n\n"
            "This command changes the world in a way an apology cannot undo, and "
            "another destructive command has already run in this turn since the "
            "last consult. One consult does not cover a sequence of them: a turn "
            "that consulted once and then swept 544 files deleted a file the test "
            "suite reads, and did not find out until afterwards.\n\n"
            "Call `advisor()` again, print what it says, then run this command." + late
        )

    allow()


def handle_stop(turn, entries):
    """Gate the reply. A consult in the turn for every model; a closing consult
    after the last action, with a report in front of it, off Fable."""
    if not consulted(turn):
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

    if is_fable(session_model(entries)):
        allow()

    last_act = last_acting_call_index(turn)
    if last_act < 0:
        allow()  # the turn only looked and consulted; there is no work to show

    index = consult_index(turn)
    if index < last_act:
        block(
            "SHOW THE ADVISOR WHAT YOU DID.\n\n"
            "This session is not on Fable, and the owner's ruling for that case is "
            "that the advisor sees the finished work before the owner does. The last "
            "consult in this turn came BEFORE the last action, so the advisor has "
            "seen a plan and not the result.\n\n"
            "Write a short report of what was done against the plan — what the "
            "advisor said, what actually ran, what the evidence shows — then call "
            "`advisor()` again, then reply. Anything the advisor asks to fix is an "
            "action, and an action after the closing consult reopens this "
            "requirement."
        )

    if visible_chars(turn, last_act + 1, index) < MIN_PLAN_CHARS:
        block(
            "THE ADVISOR WAS NOT SHOWN A REPORT.\n\n"
            "The closing consult came after the last action, but nothing of "
            "substance was written between the two, so the advisor was asked to "
            "judge work it had to reconstruct from tool output alone.\n\n"
            f"Write the report first (at least {MIN_PLAN_CHARS} characters of visible "
            "text: what the plan said, what was done, what the evidence shows), then "
            "call `advisor()`, then reply."
        )

    allow()


def main():
    if os.environ.get("CLAUDE_NO_EXCUSES_JUDGE"):
        allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
    if not isinstance(payload, dict):
        allow()

    transcript = payload.get("transcript_path")
    if not transcript:
        allow()

    event = payload.get("hook_event_name") or ""
    if event == "PreToolUse":
        if (payload.get("tool_name") or "") in EXEMPT_TOOLS:
            allow()
        if _is_subagent_call(payload):
            allow()
        caught_up = wait_for_call_record(transcript, payload.get("tool_use_id"))
        turn = turn_slice(records(transcript))
        handle_pre_tool_use(payload, turn, caught_up)
        allow()

    entries = records(transcript)
    handle_stop(turn_slice(entries), entries)
    allow()


if __name__ == "__main__":
    main()
