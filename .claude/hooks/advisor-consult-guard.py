#!/usr/bin/env python3
"""Nothing happens in a turn before the advisor is consulted and its plan printed.

TWO ARMS.

  PreToolUse  No tool runs until this turn contains an advisor consult AND a
              printed step-by-step plan following it. This is the arm that
              matters, because it gates ACTIONS. Every destructive action gets
              its own fresh consult on top of that.
  Stop        No reply ends the turn without a consult in it.

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

WHY THE PRE-TOOL ARM NOW HAS A CEILING, having argued at length that it must not.
The original reasoning was that a refusal always has an immediate remedy — call
`advisor`, which is exempt — so a ceiling could only ever grant permission to skip
the rule. That reasoning assumed the remedy, once performed, is VISIBLE. Measured
on this session's own transcript, 2026-08-31, it is not:

    the guard reads the transcript FILE, and the file lags the live conversation.
    Replaying the guard against the real records at a refused `cat Makefile`
    reproduced consult_index=28 and plan_printed_after=True with
    grounded_before=False — the `Read` that grounded the consult had happened,
    and its record was not yet on disk. The refusal was therefore correct about
    the file and wrong about the world, and repeating the remedy could not change
    it: every retry re-read the same lagging file.

That is not a rule being skipped, it is a rule that cannot be satisfied, and this
project has shipped an unsatisfiable boundary check twice already (ledger class
17b, and the `_failed_call_ids` deadlock below). The ceiling is therefore narrow
and loud: `PRE_TOOL_MAX_BLOCKS` consecutive refusals of ACTING tools within one
turn stand the arm down for that turn, and say so in the systemMessage. An exempt
look does not reset it — Read/Grep/Glob were exactly what the deadlocked loop
kept doing — and the owner speaking resets it, because that is a new turn.

MECHANICAL, NOT SEMANTIC. Nothing here judges whether a consult was thoughtful or
whether the printed plan is a good one. It asks three yes-or-no questions of the
transcript: did an advisor record appear in this turn, did assistant text of real
length follow it, and — for a destructive command — did a consult follow the
previous destructive command. The transcript is the record; agreeing to a rule
and skipping it are identical in every place except there.

NO PATTERN MATCHING on records: the JSONL entries are walked and their fields
compared, because a pattern catches only the spellings someone thought of.
"""

import contextlib
import json
import os
import sys
import time
from pathlib import Path

#: Where the two ceilings keep their tallies. Overridable so the payload tests
#: get their own file: they drive the guard as a subprocess, and sharing one path
#: would make a test run reach into whatever live session is open on this machine
#: — and make the tests themselves order-dependent on each other.
STATE_PATH = Path(
    os.environ.get("ONDOWAY_ADVISOR_STATE", "/tmp/ondoway-advisor-consult-state.json")
)
#: The Stop arm's ceiling, and ONLY the Stop arm's. Every human message resets the
#: turn and demands a fresh consult, and this owner interjects often — 36 human
#: records in one measured session's transcript tail. At a ceiling of 2, two rapid
#: interjections during tool work burned both blocks and the guard silently
#: disarmed itself, which is the starved-rule failure it exists to prevent. A
#: successful consult resets the count to 0, so this is only ever reached by
#: genuine repeated failure.
#:
#: The PreToolUse arm has its own ceiling, PRE_TOOL_MAX_BLOCKS below, and this
#: comment used to say it must never grow one — on the reasoning that blocking a
#: TOOL leaves the remedy fully available, so there is nothing to rescue. That
#: reasoning was measured wrong on 2026-08-31: the remedy can be performed and
#: stay invisible, because this guard reads a transcript FILE that lags the live
#: conversation. The module docstring carries the evidence and the reversal.
MAX_BLOCKS = 5

#: The PRE-TOOL arm's ceiling. Three consecutive refusals of acting tools inside a
#: single turn, with a correct consult performed before each one, is the signature
#: of a transcript the guard cannot read the truth out of rather than a rule being
#: ignored — see the module docstring. Three rather than one or two because a
#: genuine unconsulted stretch should still be refused more than once before the
#: arm concedes, and rather than five because past three the session is simply
#: burning turns against a file that will not agree with it.
PRE_TOOL_MAX_BLOCKS = 3

#: The shortest assistant message that can plausibly BE a step-by-step plan.
#: Measured against a real printed plan of nine numbered steps: 700 characters.
#: A bare acknowledgement ("consulting now", "will do") runs under 100. 250 sits
#: between them with room on both sides. Length is used rather than wording on
#: purpose: a rule that reads my words is a rule I can satisfy by choosing
#: different words, and the only way past a length floor is to actually write
#: something.
MIN_PLAN_CHARS = 250

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


def turn_id(entries):
    """A stable name for the CURRENT turn, so the ceiling below resets when the
    owner speaks and not merely when the process restarts.

    The last human record's own uuid, because that record IS the turn boundary
    `turn_slice` computes.

    THE FALLBACK CARRIES THE HUMAN COUNT, and that is not decoration. An earlier
    version fell back to a bare constant when a record had neither uuid nor
    timestamp, so two DIFFERENT turns produced the same fingerprint and the owner
    speaking did not clear the ceiling — caught by
    test_the_owner_speaking_starts_the_tally_again, which is the whole reason to
    write the test from the behaviour rather than from the implementation.

    The count is read off the 8 MB window, which slides as the transcript grows,
    so an old human record aging out can change the fingerprint with nobody
    having spoken. That costs a spurious RESET — the arm re-arms and refuses
    again — which is the safe direction for a guard: it fires once too often
    rather than once too few.
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


def deny_tool(reason, state=None):
    """Refuse the tool call. Always exit 0: a guard that crashes is a guard that
    is switched off, and the decision travels in the printed JSON, not the code.

    `state` is the breaker's tally. Counting the refusal HERE rather than at each
    call site means a new refusal reason added later is counted without anyone
    remembering to, which is how the ceiling stays honest as the arm grows.
    """
    if state is not None:
        state["pre_blocks"] = state.get("pre_blocks", 0) + 1
        write_state(state)
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


def _assistant_blocks(entry):
    """The content blocks of an assistant record, or an empty list."""
    if entry.get("type") != "assistant":
        return []
    content = (entry.get("message") or {}).get("content")
    return [block for block in content or [] if isinstance(block, dict)]


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


def plan_printed_after(turn, index):
    """Did assistant text of real length follow the consult at `index`?

    Text and tool calls arrive as SEPARATE assistant records, and the text record
    is written first — measured directly on this project's transcript, where one
    assistant turn appears as three consecutive records: a thinking record, a
    text record of 282 characters, and a tool_use record. So by the time a tool
    call reaches this hook, any text printed before it is already on disk and can
    be counted. If that ordering ever changed, this arm would refuse every tool
    call in a turn, loudly and immediately, rather than passing silently.

    The lengths are SUMMED across every text block after the consult, not checked
    one at a time. Because text arrives as separate records, a plan written as an
    opening line, then a numbered list, then a closing line is three short blocks
    and no single one of them clears the floor — a per-block test would refuse
    every tool call for the rest of that turn, with the plan sitting in plain
    view above it. The question is whether the plan was written, not whether it
    was written in one breath.
    """
    printed = 0
    for entry in turn[index + 1:]:
        for block in _assistant_blocks(entry):
            if block.get("type") == "text":
                printed += len(block.get("text") or "")
    return printed >= MIN_PLAN_CHARS


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


def _failed_call_ids(turn):
    """Tool calls whose result came back an ERROR — including this guard's own denials.

    THIS EXISTS BECAUSE THE GUARD DEADLOCKED ITSELF, measured 2026-08-31.

    A refused tool call is still written to the transcript as a `tool_use` block;
    only its RESULT distinguishes it, as a `tool_result` carrying
    `is_error: true` with the refusal text. The destructive scan below read the
    calls and not the results, so a `git commit` this very guard had just
    REFUSED was counted as "a destructive command that already ran". Refusing it
    therefore created the condition for refusing it again — three times, with the
    remedy (consult, print the plan) performed correctly before each one and
    making no difference, because the offending record was the previous refusal.
    That is class 17b of the failures ledger exactly: a boundary check counting
    its own output as input. There was no way out except editing the guard.

    The tradeoff, stated rather than hidden: a command that genuinely RAN and
    then errored is also skipped here, and a destructive command can fail partway
    through having already changed something. That direction costs one missed
    consult on a half-completed command. The other direction costs the session,
    with no available remedy, which is not a trade — it is the guard breaking.
    """
    failed = set()
    for entry in turn:
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            if block.get("is_error"):
                call_id = block.get("tool_use_id")
                if call_id:
                    failed.add(call_id)
    return failed


def destructive_calls_in(turn):
    """Positions in `turn` of acts that ACTUALLY changed the world.

    Two kinds. A Bash call whose command carries a destructive marker, and ANY
    Write — because by the time this runs the written file exists either way, so
    whether that Write created or overwrote is no longer answerable from the
    transcript. Counting every Write costs an extra consult after writing a new
    file; not counting them would let an overwrite go unnoticed. The cheap
    mistake is the one to make.

    Calls that never ran are excluded — see _failed_call_ids.
    """
    failed = _failed_call_ids(turn)
    out = []
    for index, entry in enumerate(turn):
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use":
                continue
            if block.get("id") in failed:
                continue  # refused or errored: it changed nothing
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


def handle_pre_tool_use(payload, turn, state):
    """Gate the action itself. Three questions, each answered by the transcript."""

    def refuse(reason):
        deny_tool(reason, state)

    tool = payload.get("tool_name") or ""
    if tool in EXEMPT_TOOLS:
        # Deliberately does NOT clear the tally. Read, Grep, Glob and codegraph
        # are what a deadlocked loop keeps doing while it tries to satisfy an
        # unsatisfiable rule, so letting a look reset the ceiling would mean the
        # ceiling never arrives in the one situation it exists for.
        allow()

    # THE CEILING. See the module docstring: a refusal can be correct about the
    # transcript file and wrong about the world, because the file lags. Three
    # consecutive refusals of acting tools in one turn is that condition, not a
    # rule being ignored, so the arm stands down for this turn and says so where
    # the owner can read it.
    if state.get("pre_blocks", 0) >= PRE_TOOL_MAX_BLOCKS:
        print(
            json.dumps(
                {
                    "systemMessage": (
                        "ADVISOR GATE STOOD DOWN for this turn after "
                        f"{PRE_TOOL_MAX_BLOCKS} consecutive refusals.\n\n"
                        "That many refusals in a row, with a consult performed "
                        "before each, means this guard is reading a transcript "
                        "file that lags the live conversation — the remedy it "
                        "asks for has already been done and cannot be seen. "
                        "Refusing again would wedge the session, not enforce "
                        "anything.\n\n"
                        "The rule still stands: consult the advisor and print "
                        "its plan before acting. The owner should know this arm "
                        "is not enforcing it right now."
                    )
                }
            )
        )
        sys.exit(0)

    index = consult_index(turn)
    if index < 0:
        refuse(
            "NO CONSULT, NO ACTION.\n\n"
            f"This turn has not called the advisor, and `{tool}` would act on it "
            "anyway. Consulting after the fact is not consulting.\n\n"
            "Call `advisor()` now. It takes no arguments and forwards this whole "
            "conversation. Then PRINT the step-by-step plan it gives you, in "
            "numbered steps, and follow that plan."
        )

    if not plan_printed_after(turn, index):
        refuse(
            "THE PLAN WAS NOT PRINTED.\n\n"
            "The advisor was consulted in this turn, but nothing of substance was "
            "written down afterwards, so the advice it gave is invisible to the "
            "person who has to live with the result — and a silent deviation from "
            "it would be invisible too.\n\n"
            "Print the advisor's step-by-step plan as numbered steps "
            f"(at least {MIN_PLAN_CHARS} characters), then act on it."
        )

    if not grounded_before(turn, index):
        refuse(
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
            "  3. Print the plan, then act."
        )

    # A destructive act with another one already run since the last consult would
    # be the second in a row on a single piece of advice.
    command = _command_of(payload)
    destroys = (command and is_destructive(command)) or _overwrites_existing_file(payload)
    unadvised = destroys and any(
        position > index for position in destructive_calls_in(turn)
    )
    if unadvised:
        refuse(
            "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT.\n\n"
            "This command changes the world in a way an apology cannot undo, and "
            "another destructive command has already run in this turn since the "
            "last consult. One consult does not cover a sequence of them: a turn "
            "that consulted once and then swept 544 files deleted a file the test "
            "suite reads, and did not find out until afterwards.\n\n"
            "Call `advisor()` again, print what it says, then run this command."
        )

    state["pre_blocks"] = 0
    write_state(state)
    allow()


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

    event = payload.get("hook_event_name") or ""
    if event == "PreToolUse":
        entries = records(transcript)
        turn = turn_slice(entries)
        if turn is None:
            allow()  # no human turn in view; nothing has been asked yet
        state = read_state()
        here = turn_id(entries)
        # A new session, or the owner speaking, starts the tally again. Both are
        # genuinely new ground to be advised about, and neither is the lagging
        # transcript the ceiling exists for.
        if state.get("session") != session or state.get("turn") != here:
            state = {"session": session, "turn": here, "blocks": 0, "pre_blocks": 0,
                     "ts": time.time()}
        handle_pre_tool_use(payload, turn, state)
        allow()

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
