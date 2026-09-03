#!/usr/bin/env python3
"""The plain-words gate (owner ruling 2026-09-02): every reply must be readable.

WHAT THE OWNER SAW. Mid-session they stopped on this sentence and asked "What?":

    "The Vallois campaign is campaign_status: deferred since 2026-04-24 — the
     owner pivoted to /pipeline-batch. It and its command go; git keeps them
     recoverable."

Then: "Every line of output needs to be simple and extremely easy to understand.
Stop using jargon." The reply to that promised plain words from then on, and the
owner answered: "I don't believe you. Add a hook to enforce this."

They were right not to believe it. The same instruction had already been given
earlier in the same session and did not hold. A promise about how the next reply
will read is not checkable by anyone until after it is read.

WHY THERE IS NO WORD LIST. The obvious build is a dictionary of banned jargon.
It was considered and rejected: a list somebody curates is a list somebody edits,
and the agent that trips it is the agent that would be maintaining it. Every
guard in this directory that actually holds fires on something STRUCTURAL. So do
these three, and none of them can be rephrased past:

  1. A CODE WORD USED AS ENGLISH. `campaign_status: deferred` is a field name
     from a file, dropped into a sentence as though it were a phrase. The rule:
     a code-shaped word must sit inside backticks, or in a fenced block. The
     backticks are the author admitting it is a name, which is the moment they
     also owe a plain sentence saying what it names.

  2. TOO MANY NAMED THINGS. A reply that names one file and explains it is
     useful. A reply that names a dozen is a wall. Backticks make check 1 pass
     but do not make a reply readable, so the count is capped.

     A `file.py:123` citation does NOT count toward that cap. citation-guard.py
     runs one slot above this one in `.claude/settings.json` and exists to
     DEMAND those citations; capping them would put two wired guards in direct
     opposition, and the reply caught in the middle could satisfy neither. That
     collision was found by a judge before this gate was committed, having
     already been shipped live — the first draft blocked a seven-citation reply
     that citation-guard was simultaneously blocking for having too few.

  3. A SENTENCE TOO LONG TO FOLLOW. The owner asked for simple lines. The
     quoted sentence above ran three clauses and two semicolon-joined thoughts.
     Anything past MAX_SENTENCE_WORDS is refused on length alone.

     The marker is stripped before counting, so a long sentence does not escape
     by wearing a bullet. The first draft skipped any line starting with `-`,
     `*`, `>`, `#` or a number, and bulleted prose is this repository's most
     common reply shape — a 49-word sentence passed all four ways.

WHAT THIS DELIBERATELY DOES NOT DO, named rather than left to be discovered.
Three kinds of jargon pass, and no character test would catch them without
firing on ordinary English:

  - PLAIN-ENGLISH JARGON. "The idempotent reconciliation converges on a
    canonical invariant" is every one of these checks satisfied and not a word
    of it readable.
  - ACRONYMS. `CI`, `TTL`, `SHA`. Telling those from `OK`, `US` or `AM` needs a
    dictionary, and a dictionary is the thing this file refuses to be.
  - HYPHENATED NAMES. `pre-shadow-check` is a filename; `well-engineered` is
    English. They are the same shape.

So this is a floor, not a ceiling. `.claude/agents/editor.md` is the pass that
judges whether prose actually reads; this gate only refuses the shapes that make
a reply unreadable no matter what it says. It exists because the floor is what a
promise kept failing to reach.

EXEMPTIONS, KEPT TIGHT — a guard that fires on ordinary work gets deleted, and
then it guards nothing:

  - A fenced code block is stripped before every check. That is where a command
    the owner should run belongs, and their own standing rule is that paths,
    commands and numbers stay exact.
  - Text inside backticks passes check 1 (that is the sanctioned way to name a
    file) and still counts toward check 2.
  - A line the owner themselves just wrote is skipped. They used
    `campaign_status` in their own message; answering them must be possible.
  - A markdown link's address is being shown, not spoken.
  - Brand names that happen to be spelled like code — iOS, macOS, TestFlight —
    are listed. An EXEMPTION list only ever makes this quieter; it can never
    make it blind to a new piece of jargon, which is why one is safe here and a
    detection list was not.

NO REGEX, following citation-guard.py's precedent (owner ruling 2026-08-29).
Every test below is a character-class check or a string operation.

THE CEILING mirrors freshness-gate.py's exactly, and for the same reason stated
there: a hook reading the transcript FILE can be right about the file and wrong
about the world, because the file lags the live conversation. Three consecutive
blocks in one turn stand this arm down for that turn, loudly, rather than wedge
the session. The next turn re-arms in full.
"""

import contextlib
import json
import os
import sys
import time
from pathlib import Path

from textkind import drop_link_targets, is_web_address

#: Own state file, isolated from the other Stop-hook ceilings so none of them
#: reads another's tally. Overridable so the test suite gets a private path.
STATE_PATH = Path(
    os.environ.get("ONDOWAY_PLAIN_WORDS_STATE", "/tmp/ondoway-plain-words-state.json")
)

#: Consecutive blocks in ONE TURN before this arm stands down for that turn.
#: Copied from freshness-gate.py's MAX_BLOCKS, same value, same reasoning.
MAX_BLOCKS = 3

TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024

#: Records typed `user` that are the HARNESS speaking. Copied verbatim from
#: citation-guard.py by way of freshness-gate.py.
HARNESS_MARKERS = ("<task-notification>", "<system-reminder>", "<local-command-stdout>")

#: Characters that surround a word without being part of it.
ADORNMENT = "()[]{}<>'\"*,;!?“”‘’—–…|:"  # noqa: RUF001

#: How many named things one reply may carry before it stops being readable.
#: `file.py:123` citations are excluded from this count entirely — see
#: `is_citation` and the module docstring. What remains is bare names, and a
#: dozen of those in one reply is a wall rather than an explanation.
MAX_NAMED_THINGS = 12

#: Longest sentence allowed. The owner asked for simple lines; thirty words is
#: already long for one.
MAX_SENTENCE_WORDS = 30

#: File endings that make a word a filename rather than English.
CODE_ENDINGS = (
    ".py", ".js", ".ts", ".md", ".dart", ".sh", ".json", ".yaml", ".yml",
    ".html", ".css", ".swift", ".toml", ".lock", ".txt", ".cfg", ".ini",
)

#: Spelled like code, but they are products people say out loud. An exemption
#: list is safe where a detection list was not: leaving a name off this one only
#: makes the gate noisier, never blind.
BRAND_WORDS = {
    "ios", "ipados", "iphone", "ipad", "macos", "watchos", "tvos",
    "npm", "npx", "github", "gitlab", "testflight", "appstore", "javascript",
    "typescript", "eslint", "playwright", "sqlite", "postgresql", "openai",
    "elevenlabs", "anthropic", "wikipedia", "wikivoyage", "openstreetmap",
    "youtube", "paypal", "ebay",
}

#: Line openings that are a MARKER in front of a real sentence. The marker is
#: stripped and the words behind it are still counted — a long sentence does not
#: get shorter by wearing a bullet.
LIST_MARKERS = ("#", "-", "*", ">", "+")

#: Line openings that are furniture, with no sentence behind them at all: a
#: table row and a horizontal rule.
NOT_PROSE_PREFIXES = ("|", "=")


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

    Copied from freshness-gate.py, which copied it from citation-guard.py.
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
    """True when this record is the PERSON speaking, not the harness."""
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


def last_assistant_text(records):
    """The reply about to reach the owner."""
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
    """Flatten a `message.content` field (string, or list of blocks) to text."""
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
    """The text the OWNER most recently typed — for the quote-back exemption."""
    for entry in reversed(records):
        if entry.get("isCompactSummary"):
            continue
        if is_human_turn(entry):
            return _text_of((entry.get("message") or {}).get("content"))
    return ""


def turn_id(records):
    """A stable name for the CURRENT turn, so the ceiling resets when the owner
    speaks and not merely when the process restarts."""
    last = None
    humans = 0
    for entry in records:
        if is_human_turn(entry):
            humans += 1
            last = entry
    if last is None:
        return "no-human-in-window"
    return last.get("uuid") or last.get("timestamp") or f"human-{humans}"


# ── reading the reply, minus the parts that are allowed to look like code ────


def strip_fenced_blocks(reply):
    """The reply with every ``` fenced block removed.

    A fenced block is where a command the owner should run belongs, and their
    standing rule is that commands stay exact. Nothing inside one is judged.
    """
    kept = []
    inside = False
    for line in reply.split("\n"):
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            kept.append(line)
    return "\n".join(kept)


def split_on_backticks(text):
    """(text outside backticks, list of backticked spans).

    Naming a file inside backticks is the sanctioned way to name it, so those
    spans are exempt from check 1. They still count toward check 2 — backticks
    make a name legal, not readable.
    """
    outside = []
    inside = []
    buffer = []
    in_span = False
    for char in text:
        if char == "`":
            joined = "".join(buffer)
            (inside if in_span else outside).append(joined)
            buffer = []
            in_span = not in_span
            continue
        buffer.append(char)
    # An unclosed span is treated as ordinary prose: refusing to judge the rest
    # of a reply because one backtick was dropped would be the wrong direction.
    joined = "".join(buffer)
    if in_span:
        outside.append(joined)
    else:
        outside.append(joined)
    return " ".join(outside), [s for s in inside if s.strip()]


def peel(raw):
    """Adornment and a trailing period, peeled until nothing more comes off."""
    token = raw
    while True:
        trimmed = token.strip(ADORNMENT).rstrip(".")
        if trimmed == token:
            return token
        token = trimmed


def is_code_shaped(token):
    """True when this word is a name from the code, not a word from English.

    Six shapes, each a character test rather than a pattern. A word that
    matches any of them is a name the owner should see in backticks, with a
    plain sentence saying what it is.
    """
    if not token:
        return False
    if token.lower().strip("./-") in BRAND_WORDS:
        return False

    # AN ADDRESS IS NOT A NAME FROM THE CODE. Asked of the URL parser, never of
    # the token's shape — see textkind.py. The path test below fires on a slash
    # and a dot, which every web address has, and on 2026-09-02 that refused the
    # dashboard link the owner had just demanded at the top of every reply.
    if is_web_address(token):
        return False

    # A command-line flag: --something, or -f
    if token.startswith("--") and len(token) > 2 and token[2].isalpha():
        return True

    # A slash command: /pipeline-batch
    if token.startswith("/") and len(token) > 1:
        rest = token[1:]
        if rest and any(c.isalpha() for c in rest) and all(
            c.isalnum() or c in "-_" for c in rest
        ):
            return True

    # A function call: something()
    if token.endswith("()") and len(token) > 2:
        return True

    # A filename: something.py
    lowered = token.lower()
    for ending in CODE_ENDINGS:
        if lowered.endswith(ending) and len(token) > len(ending):
            return True

    # A path: has a slash and a dot and no spaces
    if "/" in token and "." in token:
        return True

    # snake_case: an underscore with letters or digits on both sides
    for index in range(1, len(token) - 1):
        if token[index] == "_" and token[index - 1].isalnum() and token[index + 1].isalnum():
            return True

    # camelCase: starts lowercase, then a capital appears
    if token[0].islower():
        for first, second in zip(token, token[1:]):
            if first.islower() and second.isupper():
                return True

    return False


def bare_code_words(outside_text, owner_text):
    """Code-shaped words sitting in plain prose, with no backticks around them.

    A line the owner themselves wrote is skipped: they used `campaign_status`
    in their own message, and answering them has to be possible.
    """
    found = []
    seen = set()
    for line in outside_text.split("\n"):
        stripped = line.strip()
        if stripped and stripped in owner_text:
            continue
        for raw in line.split():
            token = peel(raw)
            if not token or token in seen:
                continue
            if is_code_shaped(token):
                seen.add(token)
                found.append(token)
    return found


def is_citation(span):
    """True for a `file.py:123` or `dir/file.py:12-20` span.

    These belong to citation-guard.py, which runs one slot above this gate and
    exists to DEMAND them. Counting them here would set two wired guards against
    each other, and a reply with seven grounded citations would be refused by
    this one for having too many while the other refused it for having too few.
    Parsed with `int()` rather than a pattern, the same way citation-guard does.
    """
    token = span.strip()
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


def named_things(backticked):
    """Distinct backticked spans that are NAMES rather than citations."""
    seen = []
    for span in backticked:
        name = span.strip()
        if not name or is_citation(name):
            continue
        if name not in seen:
            seen.append(name)
    return seen


def strip_marker(line):
    """A line with its bullet, heading or number marker removed.

    The marker is furniture; the words behind it are a sentence and are counted.
    A first draft skipped these lines whole, and a 49-word sentence passed by
    wearing a `- `, a `1. `, a `> ` or a `#`. Bulleted prose is this
    repository's most common reply shape, so that was most of the coverage.
    """
    text = line.strip()
    while text and text[0] in LIST_MARKERS:
        text = text[1:].lstrip()
    # A numbered marker: "1." or "1)" at the very front.
    head = text.split(" ", 1)[0] if " " in text else text
    if len(head) > 1 and head[-1] in ".)" and head[:-1].isdigit():
        text = text[len(head):].lstrip()
    return text


def long_sentences(text, owner_text):
    """Sentences longer than MAX_SENTENCE_WORDS, as (word_count, opening) pairs.

    A table row and a horizontal rule carry no sentence and are skipped. So is
    anything the owner wrote themselves. Everything else is measured, marker
    stripped first.
    """
    offenders = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped[0] in NOT_PROSE_PREFIXES:
            continue
        if stripped in owner_text:
            continue
        for sentence in _sentences(strip_marker(stripped)):
            words = sentence.split()
            if len(words) > MAX_SENTENCE_WORDS:
                offenders.append((len(words), " ".join(words[:9])))
    return offenders


def _sentences(line):
    """`line` cut at every full stop, question mark or exclamation mark."""
    out = []
    buffer = []
    for char in line:
        buffer.append(char)
        if char in ".!?":
            out.append("".join(buffer).strip())
            buffer = []
    tail = "".join(buffer).strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def findings(reply, owner_text):
    """Every reason this reply is not plain. Empty means it passes."""
    body = strip_fenced_blocks(drop_link_targets(reply))
    outside, backticked = split_on_backticks(body)

    problems = []

    bare = bare_code_words(outside, owner_text)
    if bare:
        listed = ", ".join(bare[:8])
        problems.append(
            "CODE WORDS USED AS ENGLISH — "
            f"{listed}\n"
            "      These are names from the code, written as though they were "
            "English words.\n"
            "      Put each one in backticks, then say in a plain sentence what "
            "it is or what it does."
        )

    names = named_things(backticked)
    if len(names) > MAX_NAMED_THINGS:
        problems.append(
            f"TOO MANY NAMED THINGS — {len(names)} of them: "
            + ", ".join(names[:8])
            + "\n      A reply that names one file and explains it is useful. "
            "One that names this\n      many is a wall. Cut it down, or move "
            "the commands into a fenced block."
        )

    for count, opening in long_sentences(outside, owner_text):
        problems.append(
            f"SENTENCE TOO LONG — {count} words, starting \"{opening}…\"\n"
            "      Break it into shorter ones. One idea per sentence."
        )

    return problems


def main():
    if os.environ.get("ONDOWAY_PLAIN_WORDS_GATE"):
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

    # THE CEILING. Three refusals in a row on one reply means either the same
    # shape is being restated without a fix, or this gate is asking for
    # something the reply cannot give. Refusing again would wedge the session.
    if state.get("blocks", 0) >= MAX_BLOCKS:
        print(json.dumps({
            "systemMessage": (
                f"PLAIN-WORDS GATE STOOD DOWN for this turn after {MAX_BLOCKS} "
                "consecutive blocks.\n\n"
                "The rule still stands: plain words, short sentences, and an "
                "explanation beside every name. The owner should know this "
                "gate is not enforcing it right now."
            )
        }))
        sys.exit(0)

    owner_text = current_user_message(records)
    problems = findings(reply, owner_text)

    if not problems:
        state["blocks"] = 0
        write_state(state)
        allow()

    state["blocks"] = state.get("blocks", 0) + 1
    write_state(state)
    block(
        "PLAIN-WORDS GATE — the owner asked for replies they can read.\n\n"
        "Owner ruling, 2026-09-02, after being handed a sentence they could "
        "not parse: \"Every line of output needs to be simple and extremely "
        "easy to understand. Stop using jargon.\" Then, to the promise that "
        "followed it: \"I don't believe you. Add a hook to enforce this.\"\n\n"
        + "\n\n".join(f"  - {p}" for p in problems)
        + "\n\nRewrite the reply and send it again. Naming a file is fine — put "
        "it in backticks and say what it does right after. Commands belong in "
        "a fenced block, where nothing here judges them."
    )


if __name__ == "__main__":
    main()
