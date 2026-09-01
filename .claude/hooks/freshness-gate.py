#!/usr/bin/env python3
"""The freshness gate (owner ruling 2026-08-31): a number said today must be
proven today.

DIAGNOSED FROM ONE SESSION'S OWN RECORD. The owner caught this agent stating
eight false things to them in a single session on 2026-08-31. Read back
afterwards, all eight share exactly one shape: a NUMBER restated from memory
instead of re-derived at the moment it was said. None was invented from
nothing — each was true at some earlier point and then carried forward past
the moment it stopped being true.

    1. "4 of 9 test groups pass"                   — was 3 of 8; a commit had
                                                       been counted as a group.
    2. "88 commits ahead"                           — was 90; two more had
                                                       landed since it was
                                                       counted.
    3. "make flutter-test VM 18 passed, chrome 327  — that run predated three
       passed" (commit 9164e834's own message)        later edits to the file
                                                       it described.
    4. "six of those eight numbers are a background — was seven of eight.
       agent's measurements"
    5. "Nothing of the phone app was lost."         — 720 files had left the
                                                       remote tree.
    6. "The push removed one file from your GitHub  — 720.
       copy."
    7. "I did not delete these today; they were     — 513 of the 720 were
       removed by commits that already existed        this session's own
       before this session."                          sweep.
    8. "trip_service.dart:147 says ..."             — a path:NN citation for
                                                       a file never opened.

A `shadow` verification agent caught seven of the eight — but only AFTER each
one reached the owner. Catching is not preventing. citation-guard.py already
caught #8, by exactly the right mechanism: it checks whether the file was
actually READ this session before a path:NN citation is allowed. This hook
generalises that mechanism from file citations to NUMBERS.

THE RULE. Every number in a reply to the owner must appear in a tool RESULT
from the CURRENT TURN — not from memory, not from an earlier turn, not from
the assistant's own earlier prose. A number that was true an hour ago is not
true now merely because nobody re-checked it: #3 above was true once, right
up until three edits made it false, and got said again anyway.

THE TURN BOUNDARY IS COPIED, NOT RE-DERIVED. `is_human_turn` and `this_turn`
below are citation-guard.py's own functions (owner ruling 2026-08-29),
verbatim: a record typed `user` is the harness, not the owner, when it carries
a `tool_result` chunk or one of HARNESS_MARKERS — a background task finishing
mid-turn lands as a plain `user` string carrying `<task-notification>`, and
treating that as the owner speaking would move the turn boundary and silence
this gate for the reply written right after it. See citation-guard.py's own
docstring for the fuller history; it is not repeated here.

A compaction summary is a `user` record with no origin stamp and no `isMeta`
(measured 2026-08-31, in advisor-consult-guard.py's own docstring), so
`is_human_turn` calls it human and `this_turn` ends the previous turn there.
That is the RIGHT direction for a freshness gate — every number needs
re-deriving after a compaction regardless — so it is left exactly as
citation-guard wrote it. But the summary is machine-written, not the owner's
own words, and its prose is full of exactly the numbers this gate exists to
re-check, so `current_user_message` below (the "quoting the owner back"
exemption) skips past it on purpose. Conflating the two would exempt the
numbers a compaction just wrote back into the transcript.

FRESH EVIDENCE IS MORE THAN TOOL RESULTS. Seven of the eight real numbers
above were a BACKGROUND AGENT'S measurements, reported back mid-turn. A
finished background task lands as a `user` record carrying a plain string
(a HARNESS_MARKERS case again), never a tool_result — so if only tool_result
chunks counted as fresh, this gate would false-positive on the single most
common legitimate pattern in this repository. The rule actually implemented:
every `user`-type record inside `this_turn` counts, with no further check —
`this_turn`'s own construction has already excluded every record where the
owner is speaking, so nothing left typed `user` there can BE the owner. Tool
CALL inputs count too (a `git log -4` that names "4" is real evidence). The
advisor's own output does not count: `server_tool_use` / `advisor_tool_result`
are ASSISTANT-record chunks, not a user tool result, and the advisor has no
tools of its own — it forwards the conversation and reads nothing else — so
anything it says is only as fresh as what was already in the transcript
before it was called.

EXEMPTIONS, KEPT TIGHT ON PURPOSE — a guard that fires on ordinary work is a
guard that gets deleted, and then it guards nothing:

  - `path:NN` citations are citation-guard's domain already, whole and
    working; this gate does not duplicate it.
  - A markdown link's URL target is being SHOWN, not claimed — the visible
    text beside it still is.
  - A numbered list's own `1.`/`1)` marker, first on its line, is structure.
  - A number appearing in the CURRENT user message (never a compaction
    summary standing in for one) is the owner's own words quoted back, not a
    claim.
  - ISO dates and clock times need no dedicated rule: a numeral run
    containing `-` or `:` fails the digit/decimal character test below before
    any date-specific exemption would be needed.

NO REGEX (owner ruling 2026-08-29, citation-guard's precedent). Tokens come
from a plain whitespace split; punctuation is peeled from the ends the same
way citation-guard's `tokens_of` does; a unit suffix ("434.65s", "3MB", "50%")
is peeled from a short, fixed allowlist, never by stripping arbitrary trailing
letters — that is exactly what would turn "sha256" into a claim of "256" and
"utf8" into a claim of "8". Recognising a number is a character-class test on
what remains, the same style as citation-guard using `int()` as its parser.

THE CEILING mirrors advisor-consult-guard.py's PRE_TOOL_MAX_BLOCKS exactly,
and for the same reason, stated there at length after that guard wedged a
session shut on 2026-08-31: a hook that reads the transcript FILE can be
correct about the file and wrong about the world, because the file lags the
live conversation. Three consecutive blocks IN ONE TURN stand this arm down
FOR THAT TURN, loudly, rather than refuse forever on a transcript that will
never agree with it. The next turn re-arms in full.

WHAT THIS STILL CANNOT DO, stated here so nobody mistakes partial coverage for
total, and measured directly against the eight above rather than guessed:

  - A number spelled out in words ("six", "one") is not a digit token and is
    not extracted at all. #4 and #6 above were both spoken this way and both
    slip through untouched. Parsing English number words was considered and
    rejected: "one" and "two" saturate ordinary prose ("no one", "one more
    thing") in a way that would make this gate noise, which is the failure
    mode that gets a hook deleted.
  - A false claim that states NO number carries nothing for a NUMBER gate to
    check. #5 and #7 above are both omissions ("nothing was lost", "I did not
    delete these") rather than misstated counts, and are entirely outside
    what this mechanism can see. That broader class of claim is a different
    hook's job.
  - A number the agent itself WRITES into a tool call this turn — a commit
    message, a file it creates — launders itself: it now appears in a tool
    INPUT, which this gate treats as a legitimate source on the theory that a
    `git log -4` naming "4" is real evidence. It is not real evidence when the
    number and the command were typed in the same breath with nothing run in
    between. Proven in this file's own test suite rather than argued around.
  - A number describing the agent's OWN actions this turn ("I made 3 edits")
    is real but appears in no tool TEXT — an Edit's input is a file path and a
    string to replace, not a tally of how many edits happened. This gate
    blocks it as stale, which is a false positive by the letter of the rule;
    the remedy it prints ("re-run the command that produces it, or drop the
    claim") is still workable — count with `git log`, or say "a few edits"
    instead of a specific number — so it is left as a known, accepted cost
    rather than special-cased away.
"""

import contextlib
import json
import os
import sys
import time
from pathlib import Path

#: Own state file, isolated from citation-guard's and advisor-consult-guard's
#: so three Stop-hook ceilings never read each other's tallies. Overridable so
#: tests get a private path per run — see those guards' own test harnesses.
STATE_PATH = Path(
    os.environ.get("ONDOWAY_FRESHNESS_STATE", "/tmp/ondoway-freshness-gate-state.json")
)

#: Consecutive blocks in ONE TURN before this arm stands down for that turn.
#: Copied from advisor-consult-guard.py's PRE_TOOL_MAX_BLOCKS, same value and
#: same reasoning: three genuine refusals is not too few to give up on early,
#: and by the fourth the session is burning turns against a transcript that
#: will not agree with it. See the module docstring for the fuller precedent.
MAX_BLOCKS = 3

TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024

#: Records that are typed `user` but are the HARNESS speaking. Copied verbatim
#: from citation-guard.py (owner ruling 2026-08-29) — see that file for the
#: measurement behind each marker.
HARNESS_MARKERS = ("<task-notification>", "<system-reminder>", "<local-command-stdout>")

#: Characters that surround a token without being part of it. Copied from
#: citation-guard.py's ADORNMENT.
ADORNMENT = "()[]{}<>`'\"*_,;!?“”‘’—–…|"  # noqa: RUF001

#: Unit suffixes peeled from a number token. A closed, short allowlist on
#: purpose: peeling ANY trailing letters is what would turn "sha256" into a
#: claim of "256". Order does not affect correctness — a wrong partial match
#: always fails the digit-purity check below and the loop keeps going — but
#: multi-character suffixes are listed first for clarity.
UNIT_SUFFIXES = ("ms", "kb", "mb", "gb", "s", "m", "h", "x", "%")

HEX_CHARS = set("0123456789abcdefABCDEF")

#: Characters that, sitting beside a matched number, mean the match is really
#: part of a LONGER run — so a claimed "18" is not satisfied by a tool result
#: that actually says "180", and a claimed "88" is not satisfied by a hex
#: string that happens to contain "88" in the middle of it.
NUMBER_BOUNDARY = set("0123456789.") | set("abcdefABCDEF")
SHA_BOUNDARY = set("0123456789abcdefABCDEF")

#: Shortest abbreviation git itself will print. A claimed full 40-char SHA is
#: judged fresh if even this many of its leading characters were actually
#: seen this turn — otherwise restating a hash git only echoed abbreviated
#: would be flagged stale for no reason, which is noise, not enforcement.
MIN_SHA_PREFIX = 7


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


def transcript_records(transcript_path):
    """Every JSON record in the transcript tail, oldest first.

    Copied from citation-guard.py.
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
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    return records


def is_human_turn(entry):
    """True when this record is the PERSON speaking, not the harness.

    Copied verbatim from citation-guard.py (owner ruling 2026-08-29). See that
    file's docstring for the measurement behind it; not re-derived here.
    """
    if entry.get("type") != "user":
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return not any(marker in content for marker in HARNESS_MARKERS)
    if not isinstance(content, list):
        return False
    for chunk in content:
        if not isinstance(chunk, dict):
            continue
        if chunk.get("type") == "tool_result":
            return False
        text = chunk.get("text") or ""
        if any(marker in text for marker in HARNESS_MARKERS):
            return False
    return True


def this_turn(records):
    """The records since the person last spoke. Copied from citation-guard.py."""
    start = 0
    for index, entry in enumerate(records):
        if is_human_turn(entry):
            start = index + 1
    return records[start:]


def last_assistant_text(records):
    """Copied from citation-guard.py."""
    for entry in reversed(records):
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content") or []
        parts = [c.get("text", "") for c in content
                 if isinstance(c, dict) and c.get("type") == "text"]
        text = "\n".join(p for p in parts if p).strip()
        if text:
            return text
    return ""


def _text_of(content):
    """Flatten a `message.content` field (string, or list of blocks) to text.

    A tool_result's own `content` can be either shape — measured directly off
    this project's transcripts, 2026-08-31: a Bash or Read result comes back a
    plain string, but an Agent/subagent result comes back as
    `[{"type": "text", "text": "..."}]`. Recursion covers a tool_result nested
    inside a list the same way.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for chunk in content:
            if not isinstance(chunk, dict):
                continue
            if "text" in chunk:
                parts.append(str(chunk.get("text") or ""))
            elif chunk.get("type") == "tool_result":
                parts.append(_text_of(chunk.get("content")))
            else:
                parts.append(json.dumps(chunk, default=str))
        return "\n".join(parts)
    return ""


def current_user_message(records):
    """The text the OWNER most recently typed — for the quote-back exemption.

    Deliberately narrower than the turn boundary above. A compaction summary
    counts as human for `is_human_turn` (right for this gate: everything
    after one must still be re-derived), but it is machine-written, not the
    owner's words, and skipping it here only WIDENS what gets checked — the
    safe direction. See the module docstring.
    """
    for entry in reversed(records):
        if entry.get("isCompactSummary"):
            continue
        if is_human_turn(entry):
            return _text_of((entry.get("message") or {}).get("content"))
    return ""


def fresh_blob_of(turn):
    """Every scrap of text this turn actually EARNED.

    Every `user`-type record inside `turn` qualifies with no further check:
    `this_turn`'s own slicing has already removed every record where the
    owner is speaking, so nothing left typed `user` here can be the owner —
    it is a tool_result, or a background task's `<task-notification>`, or an
    unfamiliar machine record, and all three are legitimate evidence. Tool
    CALL inputs are included too (`git log -4` naming "4" is a real source).
    The advisor is deliberately excluded: `server_tool_use` /
    `advisor_tool_result` are ASSISTANT-record chunks, not a user tool
    result, and the advisor has no tools of its own to have earned anything
    with — see the module docstring.
    """
    parts = []
    for entry in turn:
        etype = entry.get("type")
        if etype == "user":
            parts.append(_text_of((entry.get("message") or {}).get("content")))
        elif etype == "assistant":
            for chunk in (entry.get("message") or {}).get("content") or []:
                if isinstance(chunk, dict) and chunk.get("type") == "tool_use":
                    parts.append(json.dumps(chunk.get("input") or {}, default=str))
    return "\n".join(parts)


def _drop_markdown_link_targets(reply):
    """`[text](url)` with the url span blanked out.

    A linked address is being SHOWN, not claimed: "[see the 90 commits](url)"
    still asserts 90 in its visible text; only the address after it is exempt.
    """
    out = []
    index, length = 0, len(reply)
    while index < length:
        if reply[index] == "]" and index + 1 < length and reply[index + 1] == "(":
            close = reply.find(")", index + 2)
            if close != -1:
                out.append("]")
                index = close + 1
                continue
        out.append(reply[index])
        index += 1
    return "".join(out)


def _peel(raw):
    """Adornment and a trailing period, peeled repeatedly until stable.

    Copied from citation-guard.py's `tokens_of` loop: `.strip(ADORNMENT)` does
    not touch a bare trailing `.` (it is not in ADORNMENT — a path never ends
    in one, but a sentence does), so the two steps alternate until nothing
    more comes off. Handles nesting like "(90)." in one call.
    """
    token = raw
    while True:
        trimmed = token.strip(ADORNMENT).rstrip(".")
        if trimmed == token:
            return token
        token = trimmed


def _is_list_marker(raw):
    """`1.` or `1)` opening a line — a numbered list's own furniture.

    Only ever checked against the FIRST token of a line (the call site
    enforces that): "3 of 9 groups" opening a line is a claim, "3." opening a
    numbered list item is not.
    """
    if len(raw) < 2 or raw[-1] not in ".)":
        return False
    return raw[:-1].isdigit()


def _looks_like_path_citation(token):
    """`path:NN` or `path:NN-MM` — citation-guard's domain, not this gate's.

    Mirrors citation-guard's `split_citation` exactly: int() is the parser,
    not a pattern.
    """
    if ":" not in token:
        return False
    head, _, tail = token.rpartition(":")
    if not head or ("/" not in head and "." not in head):
        return False
    first = tail.split("-", 1)[0]
    try:
        int(first)
    except ValueError:
        return False
    return True


def _numeric_token(token):
    """The digits `token` reduces to, or None if it is not a number claim.

    A unit suffix is peeled from UNIT_SUFFIXES only — never arbitrary trailing
    letters — so "sha256" and "utf8" cannot be misread as the claims "256" and
    "8". Whatever remains must be ENTIRELY digits/`.`/`,`; one stray letter
    anywhere in it (not just the tail) rejects the whole token.
    """
    if token.startswith("$"):
        token = token[1:]
    lowered = token.lower()
    for suffix in UNIT_SUFFIXES:
        if lowered.endswith(suffix) and len(token) > len(suffix):
            candidate = token[: -len(suffix)]
            if candidate and all(c.isdigit() or c in ".," for c in candidate):
                token = candidate
                break
    negative = token.startswith("-")
    body = token[1:] if negative else token
    if not body or not all(c.isdigit() or c in ".," for c in body):
        return None
    if not any(c.isdigit() for c in body):
        return None
    if body.count(".") > 1:
        return None
    normalised = body.replace(",", "")
    return ("-" + normalised) if negative else normalised


def _looks_like_git_sha(token):
    """7-40 hex characters with at least one LETTER among them.

    A pure-digit run of the same length is just a large integer and is left
    to `_numeric_token`, which checks it the identical way: does this literal
    text appear in this turn's evidence.
    """
    if not (7 <= len(token) <= 40):
        return False
    if not all(c in HEX_CHARS for c in token):
        return False
    return any(c.isalpha() for c in token)


def numeric_claims(reply):
    """Every number-shaped token in `reply` that is a CLAIM, not structure.

    Returns (raw_token, kind, value) triples, kind in {"number", "sha"}.
    """
    claims = []
    cleaned = _drop_markdown_link_targets(reply)
    for line in cleaned.splitlines():
        tokens = line.split()
        for index, raw in enumerate(tokens):
            if index == 0 and _is_list_marker(raw):
                continue
            token = _peel(raw)
            if not token or _looks_like_path_citation(token):
                continue
            number = _numeric_token(token)
            if number is not None:
                claims.append((raw, "number", number))
                continue
            if _looks_like_git_sha(token):
                claims.append((raw, "sha", token))
    return claims


def _found_in(blob, value, boundary_chars):
    """True when `value` sits in `blob` as a standalone run, not as a slice of
    a longer run of `boundary_chars`.
    """
    start = 0
    while True:
        index = blob.find(value, start)
        if index == -1:
            return False
        before = blob[index - 1] if index > 0 else ""
        after_index = index + len(value)
        after = blob[after_index] if after_index < len(blob) else ""
        if before not in boundary_chars and after not in boundary_chars:
            return True
        start = index + 1


def _sha_fresh(value, blob):
    """A full SHA counts as seen if any git-legal ABBREVIATION of it does.

    git itself prints short hashes; an agent that expands what it saw into
    the full form should not be flagged for writing more digits than git
    echoed. A FABRICATED hash's prefix will not match real evidence either, so
    this only removes noise, never a real catch — see the module docstring.
    """
    if _found_in(blob, value, SHA_BOUNDARY):
        return True
    for length in range(len(value) - 1, MIN_SHA_PREFIX - 1, -1):
        if _found_in(blob, value[:length], SHA_BOUNDARY):
            return True
    return False


def is_fresh(kind, value, blob):
    if kind == "sha":
        return _sha_fresh(value, blob)
    return _found_in(blob, value, NUMBER_BOUNDARY)


def stale_claims(reply, fresh_blob, user_text):
    """Numeric claims in `reply` that appear in neither evidence blob."""
    stale = []
    seen = set()
    for raw, kind, value in numeric_claims(reply):
        key = (kind, value)
        if key in seen:
            continue
        seen.add(key)
        if is_fresh(kind, value, user_text) or is_fresh(kind, value, fresh_blob):
            continue
        stale.append((raw, kind, value))
    return stale


def turn_id(records):
    """A stable name for the CURRENT turn.

    Copied from advisor-consult-guard.py's turn_id: the last human record's
    own uuid, so the ceiling below resets when the owner speaks and not
    merely when the process restarts. The human-count fallback is
    load-bearing, not decoration — see that file's docstring for the test
    that caught its absence.
    """
    last = None
    humans = 0
    for entry in records:
        if is_human_turn(entry):
            humans += 1
            last = entry
    if last is None:
        return "no-human-in-window"
    return last.get("uuid") or last.get("timestamp") or f"human-{humans}"


def main():
    if os.environ.get("CLAUDE_NO_EXCUSES_JUDGE") or os.environ.get("ONDOWAY_FRESHNESS_GATE"):
        allow()

    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    transcript = payload.get("transcript_path")
    if not transcript:
        allow()

    session = payload.get("session_id") or "unknown"
    records = transcript_records(transcript)
    reply = last_assistant_text(records)
    if not reply:
        allow()

    here = turn_id(records)
    state = read_state()
    if state.get("session") != session or state.get("turn") != here:
        state = {"session": session, "turn": here, "blocks": 0, "ts": time.time()}

    # THE CEILING. See the module docstring: a refusal can be correct about
    # the transcript file and wrong about the world, because the file lags.
    # Three consecutive blocks in one turn is that condition, not a rule
    # being ignored, so the arm stands down for THIS TURN and says so loudly.
    if state.get("blocks", 0) >= MAX_BLOCKS:
        print(json.dumps({
            "systemMessage": (
                f"FRESHNESS GATE STOOD DOWN for this turn after {MAX_BLOCKS} "
                "consecutive blocks.\n\n"
                "That many refusals in a row on one reply means either the "
                "same stale number is being restated without a fix, or this "
                "gate is asking for evidence the transcript cannot supply. "
                "Refusing again would wedge the session rather than correct "
                "a number.\n\n"
                "The rule still stands: re-derive every number before "
                "stating it. The owner should know this gate is not "
                "enforcing that right now."
            )
        }))
        sys.exit(0)

    turn = this_turn(records)
    fresh_blob = fresh_blob_of(turn)
    user_text = current_user_message(records)
    stale = stale_claims(reply, fresh_blob, user_text)

    if not stale:
        state["blocks"] = 0
        write_state(state)
        allow()

    state["blocks"] = state.get("blocks", 0) + 1
    write_state(state)
    listed = "\n".join(
        f"  - {raw} — not in any tool result from this turn" for raw, _, _ in stale
    )
    block(
        "FRESHNESS GATE — a number said today must be proven today.\n\n"
        + listed
        + "\n\nRe-run the command that produces each one, or drop the claim. "
          "A number that was true earlier in the session is not true now "
          "just because nobody re-checked it."
    )


if __name__ == "__main__":
    main()
