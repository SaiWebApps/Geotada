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

WHY THERE IS NO ESCAPE HATCH. No token, no environment variable, no ceiling that
disarms after N refusals. Every other guard here carries one so that a broken
dependency cannot wedge the session, and that reasoning does not apply: the
single action that satisfies this guard — calling `advisor` — is never blocked by
it, so a refusal always has an immediate, available remedy. A ceiling would only
ever grant permission to skip the rule, which is the exact failure the guard
exists to remove. If the advisor is genuinely unreachable, the correct move is to
say so and stop, not to proceed unadvised.

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

STATE_PATH = Path("/tmp/ondoway-advisor-consult-state.json")
#: The Stop arm's ceiling, and ONLY the Stop arm's. Every human message resets the
#: turn and demands a fresh consult, and this owner interjects often — 36 human
#: records in one measured session's transcript tail. At a ceiling of 2, two rapid
#: interjections during tool work burned both blocks and the guard silently
#: disarmed itself, which is the starved-rule failure it exists to prevent. A
#: successful consult resets the count to 0, so this is only ever reached by
#: genuine repeated failure.
#:
#: The PreToolUse arm has no equivalent and must never grow one. Blocking a reply
#: forever would leave the owner with silence; blocking a TOOL leaves the one
#: remedy — call the advisor — fully available, so there is nothing to rescue.
MAX_BLOCKS = 5

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
#: tools that produce the reply itself.
EXEMPT_TOOLS = ("advisor", "AskUserQuestion", "ExitPlanMode", "TodoWrite")
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


def deny_tool(reason):
    """Refuse the tool call. Always exit 0: a guard that crashes is a guard that
    is switched off, and the decision travels in the printed JSON, not the code."""
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


def destructive_calls_in(turn):
    """Positions in `turn` of acts that changed the world.

    Two kinds. A Bash call whose command carries a destructive marker, and ANY
    Write — because by the time this runs the written file exists either way, so
    whether that Write created or overwrote is no longer answerable from the
    transcript. Counting every Write costs an extra consult after writing a new
    file; not counting them would let an overwrite go unnoticed. The cheap
    mistake is the one to make.
    """
    out = []
    for index, entry in enumerate(turn):
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use":
                continue
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


def handle_pre_tool_use(payload, turn):
    """Gate the action itself. Three questions, each answered by the transcript."""
    tool = payload.get("tool_name") or ""
    if tool in EXEMPT_TOOLS:
        allow()

    index = consult_index(turn)
    if index < 0:
        deny_tool(
            "NO CONSULT, NO ACTION.\n\n"
            f"This turn has not called the advisor, and `{tool}` would act on it "
            "anyway. Consulting after the fact is not consulting.\n\n"
            "Call `advisor()` now. It takes no arguments and forwards this whole "
            "conversation. Then PRINT the step-by-step plan it gives you, in "
            "numbered steps, and follow that plan."
        )

    if not plan_printed_after(turn, index):
        deny_tool(
            "THE PLAN WAS NOT PRINTED.\n\n"
            "The advisor was consulted in this turn, but nothing of substance was "
            "written down afterwards, so the advice it gave is invisible to the "
            "person who has to live with the result — and a silent deviation from "
            "it would be invisible too.\n\n"
            "Print the advisor's step-by-step plan as numbered steps "
            f"(at least {MIN_PLAN_CHARS} characters), then act on it."
        )

    # A destructive act with another one already run since the last consult would
    # be the second in a row on a single piece of advice.
    command = _command_of(payload)
    destroys = (command and is_destructive(command)) or _overwrites_existing_file(payload)
    unadvised = destroys and any(
        position > index for position in destructive_calls_in(turn)
    )
    if unadvised:
        deny_tool(
            "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT.\n\n"
            "This command changes the world in a way an apology cannot undo, and "
            "another destructive command has already run in this turn since the "
            "last consult. One consult does not cover a sequence of them: a turn "
            "that consulted once and then swept 544 files deleted a file the test "
            "suite reads, and did not find out until afterwards.\n\n"
            "Call `advisor()` again, print what it says, then run this command."
        )

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

    event = payload.get("hook_event_name") or ""
    if event == "PreToolUse":
        entries = records(transcript)
        turn = turn_slice(entries)
        if turn is None:
            allow()  # no human turn in view; nothing has been asked yet
        handle_pre_tool_use(payload, turn)
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
