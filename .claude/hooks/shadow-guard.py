#!/usr/bin/env python3
"""Nothing a turn did is reported until a shadow agent has re-derived it.

THE AFTER-GATE. Its sibling gates the beginning of a turn: no tool runs until the
advisor has been consulted and its plan printed. That one asks whether the plan
was advised. This one asks whether the account of what happened is TRUE, and it
asks a process that did not write the account.

WHY IT IS NOT ENOUGH TO ASK NICELY. The claims a turn makes about itself are
produced by the same thing that did the work, and they fail in a specific,
repeatable way: numbers get reported that were never read, a suite is called
green from a partial run, and a deletion is described by what was intended
rather than by what left the disk. In one measured turn, 544 files were swept
out of the repository and reported as a success; one of them was read by the
test suite, and nothing in that turn's own account of itself revealed it. The
account cannot audit the account.

WHAT IT REQUIRES, mechanically:

  If this turn used any tool that is not on the exempt list, then the turn must
  ALSO contain an Agent call whose subagent_type is one of SHADOW_TYPES,
  positioned AFTER the last such tool call, whose result carries the line
  VERDICT: CONFIRMED. The type list, and why it is a list, is at SHADOW_TYPES.

THREE PROPERTIES THAT MATTER, each for a reason:

  AFTER THE LAST TOOL CALL — this is what closes verdict-shopping. If a shadow
  run anywhere in the turn counted, the move would be to run it early, get a
  confirmation of very little, and then do the real work behind it. Requiring it
  after the last action means the confirmed state and the final state are the
  same state. Doing more work after a confirmation simply invalidates it, which
  is correct: the new work has not been verified either.

  IT READS THE SHADOW'S WORDS, NOT MINE — a guard that triggers on the phrasing
  of the reply it is guarding is a guard that can be satisfied by rephrasing.
  This one reads a verdict written by a separate process.

  Two limits of that, stated rather than implied. The shadow holds Bash, so it
  is not read-only in fact and is only asked to behave as though it were. And
  the transcript this reads is a file the judged turn can also write, so a turn
  determined to forge a verdict can append one — proven by doing it. What the
  separation buys is that the ordinary path runs a real second process; it is
  not a cryptographic boundary and must not be described as one.

  NO ESCAPE HATCH — no token, no environment variable, no ceiling that disarms
  after N refusals. The remedy is always available: run the shadow. A ceiling
  would only ever grant permission to skip the check on the turn that most
  needed it, since the turns that trip a guard repeatedly are the bad ones.

  That premise carries an obligation this file once failed. A remedy is only
  "always available" if every complaint here can be answered by a NEW run, and
  two of them read a finished reply, which is written once and can never be
  edited. Checking those over every run in the turn made one malformed early
  reply permanent: measured 2026-08-29, four consecutive foreground shadows
  opening with an exact confirmation were all refused because a superseded run
  earlier in the same turn had put a sentence above its verdict line. The gate
  was unsatisfiable — the starved-rule failure it rules out — and it was
  blocking the reply rather than the mistake. Those two checks now read only the
  runs the decision rests on; see `governing` in main() for why shape and
  verdict stand or fall together.

THE SHADOW MUST RUN IN THE FOREGROUND. A backgrounded Agent call returns launch
metadata immediately and its real answer arrives later, out of band — measured
on this project's own transcript, where every backgrounded Agent tool result
reads "Async agent launched successfully" and contains no agent output at all.
A verdict that has not arrived cannot be checked, so a backgrounded shadow is
refused by name, with the reason, rather than silently passing.

HOW IT MATCHES. Records are walked and their fields compared — never scanned for
a shape. Two places do read free text, and both are named here rather than left
for a reader to discover: the verdict is the first non-empty line of the shadow's
reply compared for EQUALITY against one of two constants, and a backgrounded
Agent call is recognised by the launch metadata it returns in place of an answer.
An earlier version of this file claimed no text was read at all while doing both,
which is the same defect as a guard whose docstring promises a check its code
does not make.
"""

import json
import sys
from pathlib import Path

#: The subagent type that may carry a verdict, and the only Agent call exempt
#: from needing one.
#:
#: EXACTLY ONE TYPE, and the reasoning that briefly made it a list is recorded
#: here because it was wrong twice over.
#:
#: Agent definitions register when a session starts, so a session that WRITES
#: this definition cannot spawn it by name, and the first run of this gate
#: refused every reply while offering a remedy that did not yet exist. The
#: response was to widen the list to `general-purpose` and friends, on the
#: argument that the routing label is not the evidence — a separate process with
#: read-only tools is, and the author writes the prompt either way.
#:
#: That argument is true about VERDICTS and false about EXEMPTION, and the same
#: list was being used for both. `_is_exempt` lets a shadow run pass ungated,
#: because requiring a shadow to verify the shadow would never terminate. With
#: `general-purpose` in the list, ANY delegated work became exempt: a turn whose
#: single tool call was an agent told to delete a directory had nothing left to
#: verify and ended clean. Widening the verdict list quietly widened the hole.
#:
#: And the premise expired. The definition registers on the next session, so a
#: gate written today is spawnable tomorrow; a permanent widening to survive one
#: session is a permanent hole to fix a temporary inconvenience.
#:
#: One name. The contract, in full, so reading this file is enough to know what
#: a verdict means: the agent is handed the turn's claims, holds Read, Grep,
#: Glob and Bash and is instructed to use them only to observe, defaults to
#: REJECTED, and confirms only what it re-derived by running
#: commands itself — every number recomputed, every deleted path checked gone
#: from disk AND index, every claim of "passed" re-run, and `git status` read
#: directly and compared against the account to catch what went unmentioned.
SHADOW_TYPES = ("shadow",)

#: The two answers the shadow may give, matched against the FIRST LINE of its
#: reply and nowhere else.
#:
#: This file used to claim exactly that and not do it: the check was plain
#: substring containment, and the confirmation was tested before the rejection.
#: So a shadow that rejected honestly — "I checked whether this meets the bar
#: for VERDICT: CONFIRMED. It does not: ... so my answer is VERDICT: REJECTED."
#: — opened the gate it had just refused. A shadow explaining its reasoning is
#: the normal case, not an attack, which made this the most likely way for the
#: guard to bless a turn nobody had verified.
#:
#: Anchoring to the first line also removes the mirror-image problem: a verdict
#: quoted, discussed or reported inside a longer answer is a mention, not a
#: ruling, and only the line the shadow was told to open with is a ruling.
CONFIRMED = "VERDICT: CONFIRMED"
REJECTED = "VERDICT: REJECTED"


def _verdict_of(text):
    """The shadow's ruling: the first non-empty line, and it must be EXACTLY one
    of the two constants.

    Equality, not a prefix. Prefix matching was this check's second attempt and
    it reproduced the defect it replaced: `VERDICT: CONFIRMED-ish, I could not
    check the numbers` and `VERDICT: CONFIRMED?? actually no, REJECTED` both
    opened the gate, because both START with the confirmation. A hedged
    confirmation is not a confirmation, and hedging is what a verifier does when
    it is unsure — precisely the case the gate exists for.

    The shadow is told to open with exactly one of these lines, so demanding
    exactly one of these lines asks nothing of it that it was not already told.
    Anything else is a reply that did not rule, and a reply that did not rule is
    not a pass.

    A leading harness notice is skipped, and skipping it is not a loophole. The
    harness inserts that line into a subagent's reply itself, and the shadow is
    told to check settings.json on every hook change — which is what triggers
    it. So for the entire class of turn this gate exists for, line one was the
    harness speaking, the verdict read as absent, and the gate could never be
    satisfied at all. Worse than a livelock: a genuine rejection was downgraded
    to "no verdict", and the branch that relays the shadow's findings back never
    ran, so the reasons were discarded. Both of this gate's own rejections
    arrived that way. The shadow cannot write or suppress that prefix, so it
    cannot be used to smuggle a verdict past anything.

    Returns CONFIRMED, REJECTED, or None.
    """
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith(HARNESS_NOTICE_PREFIX):
            continue
        if line == REJECTED:
            return REJECTED
        if line == CONFIRMED:
            return CONFIRMED
        return None
    return None

#: What a backgrounded Agent call returns instead of an answer.
ASYNC_LAUNCH_MARKER = "Async agent launched"

#: The harness's own annotation, prepended to a subagent reply when its text
#: trips an instruction-shaped pattern. Written by the harness, never by the
#: shadow, so it can be stepped over without giving anyone a way past the check.
HARNESS_NOTICE_PREFIX = "[harness:"

#: Tools whose use does not, by itself, oblige a verification pass.
#:
#: `Agent` is NOT here, and that is the correction that matters most. Exempting
#: it by name meant a turn whose only tool calls were Agent calls had nothing to
#: verify: `last_unverified_action` returned -1 and the gate allowed before it
#: ever looked for a shadow. That is not an exotic forgery — it is what an
#: ordinary delegating turn looks like, because the parent transcript records
#: only the spawn and its summary while the real commands run in the child's own
#: transcript. Demonstrated against this file: an Agent call whose prompt was
#: "run rm -rf data/old_exports and confirm it is gone", with no shadow anywhere,
#: was allowed to end the turn.
#:
#: An Agent call is exempt only when it IS the verification — see _is_exempt.
#: The others ask the owner something or record intent; none makes a claim about
#: the repository and none changes it.
EXEMPT_TOOLS = ("advisor", "AskUserQuestion", "ExitPlanMode", "TodoWrite")


def _is_exempt(block):
    """Does this tool call escape the obligation to be verified?

    A named exempt tool always does. An Agent call does so ONLY when it is a
    shadow run — otherwise delegating the work would delegate away the checking
    with it, which is the hole this replaced.
    """
    name = block.get("name")
    if name in EXEMPT_TOOLS:
        return True
    if name != "Agent":
        return False
    return (block.get("input") or {}).get("subagent_type") in SHADOW_TYPES

TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024


def allow():
    sys.exit(0)


def block(reason):
    print(json.dumps({"decision": "block", "reason": reason}))
    sys.exit(0)


def records(transcript_path):
    """Every JSONL record in the transcript's tail, oldest first.

    Reading a tail rather than the whole file keeps a long session cheap. The
    first line of the tail is dropped when the file is larger than the window,
    because a seek lands mid-line and half a record parses as nothing.
    """
    try:
        with open(transcript_path, "rb") as handle:
            handle.seek(0, 2)
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

    Every `user` record carries a stamp saying what produced it. Measured on this
    project's transcripts: `origin.kind` is "human" for a typed message and
    "task-notification" for a background job reporting in, and `isMeta` is true
    for a hook's own feedback and for skill prompts. So "did a person type this"
    has a field that answers it and no text needs reading.

    An earlier guard here screened text prefixes instead. It worked, but a prefix
    list is a word list, and a word list is what silently starved a sibling rule
    that knew one spelling of a word and not another. Structure cannot be spelled
    a new way.

    An unrecognised `origin.kind` is NOT treated as human: a machine origin this
    code has not met yet is far likelier than a person, and admitting it would
    let an invented origin end the turn early. The cost is the opposite error —
    a genuinely new human origin would not anchor the turn — which is why the
    no-anchor path refuses rather than allows when work is in view.
    """
    if entry.get("type") != "user":
        return False
    if entry.get("isMeta"):
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


def _blocks(entry):
    content = (entry.get("message") or {}).get("content")
    return [block for block in content or [] if isinstance(block, dict)]


def last_unverified_action(turn):
    """Position of the last tool call that obliges a verification, or -1."""
    found = -1
    for index, entry in enumerate(turn):
        if entry.get("type") != "assistant":
            continue
        for block in _blocks(entry):
            if block.get("type") != "tool_use":
                continue
            if not _is_exempt(block):
                found = index
    return found


def shadow_runs(turn):
    """(position, tool_use_id) for every shadow Agent call in the turn."""
    out = []
    for index, entry in enumerate(turn):
        if entry.get("type") != "assistant":
            continue
        for block in _blocks(entry):
            if block.get("type") != "tool_use" or block.get("name") != "Agent":
                continue
            if (block.get("input") or {}).get("subagent_type") in SHADOW_TYPES:
                out.append((index, block.get("id")))
    return out


def result_text(turn, tool_use_id):
    """The text a tool call returned, flattened. Empty when it has not returned."""
    parts = []
    for entry in turn:
        # A tool result is delivered in a `user` record. Reading any entry type
        # let a verdict planted in an assistant record answer for a run that had
        # not answered, and an errored result — the tool failed — was read as
        # though it were the agent's considered reply.
        if entry.get("type") != "user":
            continue
        for block in _blocks(entry):
            if block.get("type") != "tool_result":
                continue
            if block.get("tool_use_id") != tool_use_id:
                continue
            if block.get("is_error"):
                continue
            content = block.get("content")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for chunk in content:
                    if isinstance(chunk, dict) and chunk.get("type") == "text":
                        parts.append(chunk.get("text") or "")
    return "\n".join(parts)


HOW_TO_RUN = (
    "Run it now, in the FOREGROUND. Only subagent_type \"shadow\" is accepted:\n"
    "any other type is ordinary work, and work cannot certify itself.\n\n"
    "    Agent(subagent_type=\"shadow\", run_in_background=false,\n"
    "          description=\"verify this turn\",\n"
    "          prompt=\"<every claim this turn makes, in full: each number, each\n"
    "                  path deleted or written, each test result, each 'done'>\")\n\n"
    "A backgrounded shadow returns launch metadata, not a verdict, and is refused."
)


def main():
    # EVERY read of the payload sits inside this guard. It used to stop one line
    # earlier, so a payload that parsed as valid JSON but was not an object — a
    # null, a number, a list — reached `.get` and raised AttributeError. The
    # harness treats any exit code other than 2 as "carry on" and sends stderr
    # only to a debug log, so the crash was a SILENT pass: the gate did not run,
    # the turn ended, and nothing anywhere recorded that it had been skipped. A
    # gate that fails open on malformed input is worse than no gate, because it
    # is trusted.
    try:
        payload = json.load(sys.stdin)
        transcript = payload.get("transcript_path") if isinstance(payload, dict) else None
    except Exception:
        transcript = None

    if not transcript:
        block(
            "THE SHADOW GATE COULD NOT READ THIS TURN.\n\n"
            "No transcript path arrived, so there is no way to tell whether this "
            "turn did anything or whether anyone checked it. Refusing is the only "
            "honest answer: the alternative is a gate that goes quiet exactly when "
            "it has been blinded.\n\n" + HOW_TO_RUN
        )

    if not Path(transcript).is_file():
        block(
            "THE SHADOW GATE COULD NOT READ THIS TURN.\n\n"
            f"The transcript path it was given does not exist: {transcript!r}. "
            "An unreadable transcript used to read as an empty one, so pointing "
            "the gate at nothing turned it off silently.\n\n" + HOW_TO_RUN
        )

    entries = records(transcript)
    turn = turn_slice(entries)

    # The shadow checks below run over the WHOLE window when the turn boundary
    # cannot be found. They used to sit after the no-anchor branch, so pushing
    # the owner's last message out of the readable window — which one oversized
    # tool result does — skipped them entirely, and a backgrounded or unanswered
    # shadow sailed through. Whether a shadow answered does not depend on
    # knowing where the turn began.
    scope = entries if turn is None else turn
    all_runs = shadow_runs(scope)

    # AN UNANSWERED RUN IS CHECKED WHEREVER IT SITS, because "no answer yet" is
    # the one TRANSIENT complaint in this file: the result arrives and it goes
    # away on its own. Demanding it of every run therefore costs nothing and can
    # never wedge a turn shut, which is exactly what separates it from the two
    # checks below.
    #
    # SPLITTING IT OUT MOVED IT AHEAD of the backgrounded check, and that changes
    # one reported REASON: a turn holding both a backgrounded run and an
    # unanswered one used to be refused for the backgrounding and is now refused
    # for the missing answer. Both still refuse, so nothing is weakened — it is
    # written down because an undocumented change of behaviour is how a file
    # starts promising a check it does not make.
    for _position, call_id in all_runs:
        if not result_text(scope, call_id):
            block(
                "A SHADOW RUN HAS NOT ANSWERED.\n\n"
                "One was started and no result has come back. An unanswered check "
                "is not a passed check, and another run's verdict does not stand "
                "in for this one's.\n\n" + HOW_TO_RUN
            )

    action = -1 if turn is None else last_unverified_action(turn)

    #: THE RUNS THE DECISION RESTS ON, and the repair for a gate that made itself
    #: unsatisfiable.
    #:
    #: The two checks below read a FINISHED reply, and a reply is written once and
    #: can never be edited. Running them over every run in the turn therefore made
    #: a single malformed early reply permanent: MEASURED on this project
    #: 2026-08-29, one run opened with "All six claims re-derive. Writing the
    #: ruling." above its verdict line, and from that moment four consecutive
    #: foreground shadows — each opening with an exact `VERDICT: CONFIRMED` — were
    #: all refused, because the offending reply could not be gone back and fixed.
    #: The no-escape-hatch paragraph above rests on "the remedy is always
    #: available: run the shadow"; for that turn it was not available, and a gate
    #: whose only remedy cannot work has stopped blocking mistakes and started
    #: blocking replies.
    #:
    #: The narrowing is the same fact the verdict-shopping rule already states. A
    #: run with work after it has been SUPERSEDED: the state it examined is not
    #: the state being reported, which is why its verdict does not count. Its
    #: SHAPE cannot count either — one cannot be evidence while the other is not.
    #:
    #: When the boundary is unknown, or when the turn holds no action at all,
    #: nothing has superseded anything, so every run in view still answers for
    #: itself. `action < 0` covers both.
    governing = (
        all_runs
        if action < 0
        else [(position, call_id) for position, call_id in all_runs if position > action]
    )

    for _position, call_id in governing:
        text = result_text(scope, call_id)

        if ASYNC_LAUNCH_MARKER in text:
            block(
                "THE SHADOW WAS BACKGROUNDED.\n\n"
                "A backgrounded Agent call returns launch metadata immediately and "
                "its real answer arrives later, out of band. Whatever else is in "
                "that result, the verdict is not in it yet.\n\n" + HOW_TO_RUN
            )

        if _verdict_of(text) is None:
            block(
                "THE SHADOW GAVE NO VERDICT.\n\n"
                "A shadow ran but its reply does not open with a verdict line. "
                "Either it did not rule, or it was handed work rather than a "
                "verification — and both spend the exemption that lets a shadow "
                "run ungated on something that checked nothing.\n\n"
                "The first non-empty line must be exactly one of the two verdict "
                "lines. A hedged or qualified confirmation is not a "
                "confirmation.\n\n" + HOW_TO_RUN
            )

    if turn is None:
        # No message from the owner is in view. That is normally an empty
        # session — but it is also what a LONG one looks like, because only the
        # last 8 MB is read and one large tool result can push the owner's last
        # message out of the window. Demonstrated against this file: a 9.5 MB
        # transcript whose destructive command and its result sat intact a few
        # hundred bytes from the end, with the anchor evicted, ended the turn
        # with nothing verified. The two cases are told apart by what is
        # actually in view — work with no anchor is a LOST anchor, not an empty
        # session.
        if any(
            item.get("type") == "tool_use" and not _is_exempt(item)
            for entry in entries
            for item in _blocks(entry)
        ):
            block(
                "THE TURN BOUNDARY IS OUT OF VIEW.\n\n"
                "This transcript holds tool calls but no message from the owner "
                "inside the readable window, so which of those calls belong to "
                "this turn cannot be established. Treating that as 'nothing "
                "happened' is how a long session quietly loses its gate.\n\n"
                + HOW_TO_RUN
            )
        allow()  # genuinely nothing asked and nothing done

    if action < 0:
        if all_runs:
            # A verification with nothing to verify is not a verification. The
            # shadow holds Bash and its spawn is exempt, so a shadow given a
            # destructive prompt does the work while exempt — and if it also
            # types a verdict line, every other check here is satisfied by a run
            # that checked nothing. What gives that away is that the turn
            # contains no action for it to have been about.
            block(
                "A SHADOW RAN WITH NOTHING TO VERIFY.\n\n"
                "This turn's only tool calls were shadow spawns. A shadow is "
                "exempt from being verified because verifying the verifier does "
                "not terminate — spending that exemption on the work itself, and "
                "then having the worker certify it, is the one way the exemption "
                "can be abused.\n\n"
                "Do the work with ordinary tools, then run a shadow over it."
            )
        allow()  # the turn changed nothing and claims nothing about the repo

    if not governing:
        block(
            "NOT VERIFIED.\n\n"
            "This turn used tools and is about to report on itself, and no shadow "
            "has re-derived what it did SINCE the last of those tools ran. The "
            "account of a turn is written by the same thing that did the work, and "
            "that account has been wrong here before: one turn swept 544 files out "
            "of the repository, reported success, and had deleted a file the test "
            "suite reads.\n\n" + HOW_TO_RUN
        )

    # A rejection after the last action is final, whatever else was said. Deciding
    # on the first verdict in positional order rewarded re-running the shadow and
    # stopping at the answer you wanted.
    for _position, call_id in governing:
        text = result_text(turn, call_id)
        if _verdict_of(text) == REJECTED:
            block(
                "THE SHADOW REJECTED THIS TURN.\n\n"
                "Its verdict is below. Fix what it found — do not argue with it and "
                "do not re-run it hoping for a different answer: a rejection after "
                "the last action stands even if another run confirms, so the fix "
                "has to happen first.\n\n"
                "----- shadow -----\n" + text.strip()[:4000]
            )

    allow()


if __name__ == "__main__":
    main()
