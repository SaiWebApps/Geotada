#!/usr/bin/env python3
"""Do the ten-second checks BEFORE spending the six-minute verifier.

A PreToolUse hook on `Agent`, awake only when `tool_input.subagent_type` is
"shadow".

WHY, measured 2026-09-01. The shadow ran 21 times in one day, mean 386 seconds,
2.25 hours in total, and 61% of that time went to re-verifying careless errors
the session had just made. Eleven of sixteen verdicts were rejections, and the
grounds clustered into three mechanical classes — every one of them answerable
by opening a file:

  1. A `path:NN` citation that no longer resolves, because the session's own
     edit moved the line. About twenty of them in a single turn, after a
     113-line insertion pushed every citation below it out of place.
  2. A number in the report that appears in no tool result from that turn: a
     stale test count, "four refused" when the transcript held nine, "three
     coding rules" when the file has seven.
  3. "The engine is green" when its guard was never re-run after the edit.

None of those needs a language model. They need a file opened, a set looked up,
and a subprocess run. So they happen here, before the expensive agent starts,
and the refusal names exactly which citation, which number, which guard.

MECHANICAL, NOT SEMANTIC. Nothing here judges whether the shadow's prompt is a
good one or whether the work is right. It asks three yes-or-no questions of the
files and the transcript. The shadow still does the thinking; it just stops
doing the typo-hunting.

NO PATTERN MATCHING, per the owner's ruling of 2026-08-29 and the enforcer at
~/.claude/hooks/no-regex-in-hooks.py: lines are walked and string methods and
`int()` do the deciding. A pattern catches only the spellings someone thought
of, and it fails silently.

A CEILING, unlike the advisor guard. Three consecutive refusals in one turn and
this stands down, saying so in the allowed message. The advisor guard has no
ceiling because its remedy — call the advisor — is always available; this
guard's remedy is editing files, and a check that reads the wrong file cannot
be satisfied at all. This project has shipped an unsatisfiable guard twice.

IT MUST NOT COUNT ITS OWN REFUSALS AS INPUT. See `_files_written_in`: class 17b
of the failures ledger is a boundary check reading its own output, which is how
the advisor guard deadlocked on 2026-08-31 by counting a `git commit` it had
itself refused as a commit that ran. Every call this guard reads is filtered to
the ones whose result came back CLEAN, so a Write this or any other hook denied
is not a file this guard then goes looking for.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

#: Where the per-turn refusal tally lives. Keyed by session AND by turn, so a
#: parallel session cannot reset this one's count — the bug that made the
#: advisor guard's old shared ceiling non-deterministic.
STATE_DIR = Path(
    os.environ.get("ONDOWAY_SHADOW_STATE_DIR")
    or (Path(os.environ.get("TMPDIR") or "/tmp") / "ondoway-pre-shadow")
)

#: Refusals in one turn before the guard stands down and lets the shadow run.
CEILING = 3

#: Integers that are not claims. Years, and anything a person would write
#: without having counted: "the three checks", "one file". The unsourced-number
#: rejections measured on 2026-09-01 were all counts of ten or more or exact
#: test tallies, so the floor costs nothing real.
SMALL_NUMBER = 10
YEAR_FLOOR = 1900
YEAR_CEILING = 2100

TRANSCRIPT_TAIL_BYTES = 8 * 1024 * 1024

#: The engine and the guard that proves it. Named here rather than discovered,
#: because check 3 is about ONE pair of files.
ENGINE = ".claude/team-engine.js"
ENGINE_GUARD = ".claude/team-engine.test.js"

#: Tools that put text on disk.
WRITING_TOOLS = ("Write", "Edit", "NotebookEdit", "MultiEdit")


def allow(message=None):
    """Let the spawn through. Always exit 0: a guard that crashes is a guard
    that gets switched off, and the decision travels in the printed JSON."""
    if message:
        print(json.dumps({"systemMessage": message}))
    sys.exit(0)


def deny(reason):
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


# ------------------------------------------------------------------ transcript
#
# Every record shape below is the one the advisor guard measured off this
# project's own JSONL and documents in its module docstring. Nothing here is
# invented: a fixture invented alongside the code it tests proves only that the
# two agree with each other, which is how thirteen passing tests once sat on
# top of a guard that blocked every reply.


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
    """A real person typing — classified by STRUCTURE, never by text.

    Copied in substance from advisor-consult-guard.py, whose docstring records
    the survey behind it: `origin.kind` is "human" for a typed message and
    something else for a task notification, `isMeta` marks a hook's own
    feedback and skill prompts, and `isCompactSummary` marks the machine-written
    record the harness leaves when a session runs out of context. Left
    classified as human, that summary becomes the boundary of "this turn" at
    the exact moment there is least context to work with.

    FAILS LOUD: an unrecognised record carrying text counts as human, so an
    unfamiliar shape shortens the turn rather than silently widening it.
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
    """Everything after the last human message. No human record in view means
    the whole window is the turn — judged, not waved through."""
    last_human = -1
    for index, entry in enumerate(entries):
        if _is_human_turn(entry):
            last_human = index
    return entries[last_human + 1:]


def turn_key(entries):
    """A stable name for THIS turn, for the ceiling's tally.

    The last human record's uuid when it has one, else its timestamp, else the
    count of records before it. Whatever it is, it changes when the owner types
    again — which is what resets the ceiling.
    """
    last_human = -1
    for index, entry in enumerate(entries):
        if _is_human_turn(entry):
            last_human = index
    if last_human < 0:
        return "no-human"
    entry = entries[last_human]
    for field in ("uuid", "timestamp"):
        value = entry.get(field)
        if isinstance(value, str) and value:
            return value
    return "index-%d" % last_human


def _assistant_blocks(entry):
    if entry.get("type") != "assistant":
        return []
    content = (entry.get("message") or {}).get("content")
    return [block for block in content or [] if isinstance(block, dict)]


def _call_results(turn):
    """Each tool call's outcome, keyed by call id: True when the result came
    back clean, False when it came back an error. A call with no result has not
    finished and is absent."""
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


def _files_written_in(turn):
    """Absolute paths this turn actually PUT ON DISK.

    ONLY CALLS THAT RAN COUNT — a call with a clean result in the turn. This is
    the line that keeps the guard from reading its own output as input. A Write
    this hook (or any other) denied is still a `tool_use` record in the
    transcript; only its result distinguishes it. Counting refused writes would
    make a refusal the reason for the next refusal, which is exactly the
    self-deadlock the advisor guard walked into on 2026-08-31 (class 17b of the
    failures ledger): three `git commit` refusals in a row, each one caused by
    the last, with the correct remedy performed before each attempt.

    A call still awaiting its result has not written anything yet either, so it
    is absent for the same reason and by the same rule.
    """
    ran = {call_id for call_id, ok in _call_results(turn).items() if ok}
    out = []
    for entry in turn:
        for block in _assistant_blocks(entry):
            if block.get("type") != "tool_use":
                continue
            if block.get("name") not in WRITING_TOOLS:
                continue
            if block.get("id") not in ran:
                continue  # refused, errored, or not yet run: nothing on disk
            target = (block.get("input") or {}).get("file_path")
            if isinstance(target, str) and target and target not in out:
                out.append(target)
    return out


def _tool_result_text(turn):
    """Every tool result's text in this turn, joined. The evidence a number in
    the report is allowed to rest on."""
    chunks = []
    for entry in turn:
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            body = block.get("content")
            if isinstance(body, str):
                chunks.append(body)
            elif isinstance(body, list):
                for piece in body:
                    if isinstance(piece, dict) and isinstance(piece.get("text"), str):
                        chunks.append(piece["text"])
    return "\n".join(chunks)


# ------------------------------------------------------------------- numbers
#
# Digit runs are found by walking characters and asking the language, never by
# a pattern. `str.isdigit()` answers "is this a digit" for every spelling there
# is, and `int()` answers "is this a number".


def integers_in(text):
    """Every run of digits in `text`, as (value, literal) pairs, in order.

    A run is bounded by any non-digit, so "113-line" yields 113 and "2.25"
    yields 2 and 25. Splitting a decimal is deliberate: both halves are still
    figures the report is asserting, and both must be findable in the evidence.
    """
    out = []
    current = []
    for char in text:
        if char.isdigit():
            current.append(char)
            continue
        if current:
            literal = "".join(current)
            out.append((int(literal), literal))
            current = []
    if current:
        literal = "".join(current)
        out.append((int(literal), literal))
    return out


def claimed_integers_in(text):
    """The integers in `text` that are actually ASSERTING a quantity.

    `integers_in` walks characters, so it reads a digit run out of anything —
    including the middle of an identifier. That is right for EVIDENCE, where any
    appearance of a number sources it, and wrong for the PROMPT, where the
    question is what the report claims.

    MEASURED, 2026-09-02, on this guard's first live firing: the shadow's prompt
    must carry the session transcript path, and that path holds a uuid —
    `1d64ca6b-bc57-436b-…`. Walked as characters it yields 64, 57 and 436, none
    of which anything in the turn could ever source, and the path is not
    optional. The guard refused a spawn it made impossible to fix: an
    unsatisfiable boundary check, which this project has now shipped three times.

    So a digit run only counts when its whole whitespace-delimited token is a
    number once ordinary punctuation is trimmed. `329` counts; `1d64ca6b`,
    `.claude/team-engine.test.js` and `sha256` do not. A quantity written inside
    an identifier is not a quantity the report is asserting.
    """
    out = []
    for token in text.split():
        bare = token.strip(TRIM)
        if not bare:
            continue
        # `512/600` is TWO figures the report asserts, so each half is offered
        # separately. Splitting only on `/` keeps a path out of it: the halves
        # of `.claude/hooks/x.py` are not numbers and fall out below.
        for part in bare.split("/"):
            value = _quantity_of(part.strip(TRIM))
            if value is not None:
                out.append(value)
    return out


#: Characters a figure is commonly introduced by, which are not part of it:
#: `n=512`, `#512`, `$4200`, `~30`, `+15`.
QUANTITY_PREFIX = "nN=#$~+<>≈"


def _quantity_of(token):
    """The (value, literal) a token asserts, or None if it asserts no quantity.

    THE FIRST VERSION OF THIS WAS TOO STRICT AND THAT WAS WORSE THAN TOO LOOSE.
    Requiring the whole token to be digits fixed the uuid case and silently
    stopped counting `61%`, `21.9`, `334ms`, `240s`, `n=512` and `512/600` —
    the ordinary spellings of a report's own figures, including three used in
    this guard's own docstring. Measured 2026-09-02 by a verifier, after the
    over-correction shipped.

    So the rule is shape, not purity. A quantity is an optional prefix, then
    digits (with `,` or `_` separators), then optionally a decimal part, then
    optionally a unit made only of letters or `%`. What it is NOT is an
    identifier: letters BEFORE the digits, or letters BETWEEN two digit runs,
    means `1d64ca6b` or `9525b4a5` — a name, not a count.
    """
    body = token.lstrip(QUANTITY_PREFIX)
    if not body or not body[0].isdigit():
        return None

    digits = []
    index = 0
    while index < len(body) and (body[index].isdigit() or body[index] in ",_"):
        if body[index].isdigit():
            digits.append(body[index])
        index += 1
    if not digits:
        return None

    rest = body[index:]
    # A decimal part is still the same figure; take the integer half.
    if rest.startswith(".") and rest[1:2].isdigit():
        rest = rest[1:].lstrip("0123456789")
    # A slash pair — `512/600` — is two figures; the caller sees this token
    # once, so take the first and let the second be found on its own token.
    if rest.startswith("/"):
        rest = ""
    # Anything left must be a unit: letters or a percent sign, never digits.
    if any(char.isdigit() for char in rest):
        return None
    if rest and not all(char.isalpha() or char == "%" for char in rest):
        return None

    literal = "".join(digits)
    return int(literal), literal


def is_exempt_number(value):
    """Integers that assert nothing. Single digits and small counts, which get
    written without counting, and anything in the range of a year."""
    if value < SMALL_NUMBER:
        return True
    return YEAR_FLOOR <= value <= YEAR_CEILING


def _citation_line_numbers(text):
    """The NN of every `path:NN` in `text`, as literal strings.

    Check 1 already resolves these against the files, so check 2 must not
    refuse them a second time for being unsourced — a line number is a location,
    not a claim about a quantity.
    """
    out = set()
    for path, line_no, _raw in citations_in(text):
        if path:
            out.add(str(line_no))
    return out


def unsourced_numbers(prompt, evidence):
    """Numbers in the prompt that appear nowhere in this turn's tool results.

    The evidence is split into WHOLE digit runs and compared as numbers, not
    searched as text. A substring search would let "210 files scanned" pay for
    the claim "ran 21 times" — the prefix of a bigger number sourcing a
    different one — and a claim proven by a coincidence is not proven. Found by
    this file's own test on the first run.

    Ordered, deduplicated, exemptions removed.
    """
    # Evidence is read generously — a digit run anywhere in a tool result
    # sources the claim. The prompt is read strictly: only a token that IS a
    # number is a claim. See claimed_integers_in for why the two differ.
    sourced = {value for value, _literal in integers_in(evidence)}
    covered = _citation_line_numbers(prompt)
    seen = set()
    out = []
    for value, literal in claimed_integers_in(prompt):
        if literal in seen:
            continue
        if is_exempt_number(value):
            continue
        if literal in covered:
            continue
        seen.add(literal)
        if value not in sourced:
            out.append(literal)
    return out


# ----------------------------------------------------------------- citations
#
# A citation is `some/path.py:214`. It is found by splitting the line on
# whitespace and asking the language about each piece — `int()` for the line
# number, `in` for the separators — because the previous version of this idea
# used a pattern, the pattern did not anticipate a sentence-ending period, and
# `provider.py:222.` silently stopped being a citation. The whole arm went
# quiet and looked satisfied.

#: Characters that end a sentence rather than a path, stripped from both ends
#: of a token before it is read. `:` is deliberately absent — it is the
#: separator itself.
TRIM = " \t\r\n.,;!?)(][}{'\"`*_<>|"


def citations_in(text):
    """Every `path:NN` in `text`, as (path, line_number, raw_token) triples.

    A token qualifies when it splits on its LAST colon into a non-empty left
    side that looks like a file (it carries a dot or a slash) and a right side
    that is entirely digits. That rejects "note: 5" (no path), "http://x" (no
    digits after the last colon) and "12:30" (no dot or slash), and accepts
    "src/a.py:214", "a.py:9" and a citation with a period glued to its end.
    """
    out = []
    for line in text.split("\n"):
        for token in line.split():
            raw = token
            piece = token.strip(TRIM)
            if ":" not in piece:
                continue
            path, _sep, tail = piece.rpartition(":")
            if not path or not tail or not tail.isdigit():
                continue
            if "." not in path and "/" not in path:
                continue
            try:
                number = int(tail)
            except ValueError:
                continue
            if number < 1:
                continue
            out.append((path, number, raw))
    return out


def _resolve(path, root):
    """The citation's path as it exists on disk, or None."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    here = root / candidate
    if here.is_file():
        return here
    return None


def _line_count(path):
    try:
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8", "replace").count("\n") + 1
    except OSError:
        return None


def broken_citations(md_paths, root):
    """Citations in this turn's markdown that no longer point at a line.

    Returns a list of human sentences, empty when every one resolves. Only the
    files this turn wrote are opened: a citation the session did not touch is
    not this turn's error, and a guard that fires on other people's work is one
    that gets deleted.
    """
    failures = []
    for md in md_paths:
        source = Path(md)
        if not source.is_absolute():
            source = root / source
        try:
            body = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for path, number, _raw in citations_in(body):
            target = _resolve(path, root)
            if target is None:
                failures.append(
                    "%s cites `%s:%d` — no such file" % (source.name, path, number)
                )
                continue
            total = _line_count(target)
            if total is None:
                failures.append(
                    "%s cites `%s:%d` — the file could not be read"
                    % (source.name, path, number)
                )
            elif number > total:
                failures.append(
                    "%s cites `%s:%d` — that file has %d lines"
                    % (source.name, path, number, total)
                )
    return failures


# --------------------------------------------------------------- engine guard


def engine_guard_result(root):
    """Run the engine's own guard. Returns (ok, output).

    Hermetic and fast — it is `node` over one file with no network, no database
    and no fixtures — so running it here costs seconds against the shadow's
    mean of 386.
    """
    guard = root / ENGINE_GUARD
    if not guard.is_file():
        return False, "%s does not exist, so nothing proves the engine" % ENGINE_GUARD
    try:
        done = subprocess.run(
            ["node", str(guard)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        return False, "`node` is not on PATH, so the engine guard cannot be run"
    except subprocess.TimeoutExpired:
        return False, "the engine guard did not finish within 120 seconds"
    if done.returncode == 0:
        return True, ""
    tail = (done.stdout + done.stderr).strip().split("\n")
    return False, "\n".join("    " + line for line in tail[-25:])


# -------------------------------------------------------------------- ceiling


def _state_path(session_id):
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in session_id)
    return STATE_DIR / ("%s.json" % (safe or "session"))


def refusals_so_far(session_id, key):
    try:
        data = json.loads(_state_path(session_id).read_text())
    except (OSError, ValueError):
        return 0
    if not isinstance(data, dict) or data.get("turn") != key:
        return 0
    count = data.get("count")
    return count if isinstance(count, int) and count > 0 else 0


def record_refusal(session_id, key, count):
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state_path(session_id).write_text(json.dumps({"turn": key, "count": count}))
    except OSError:
        pass  # a tally that cannot be written costs a ceiling, never the guard


# ----------------------------------------------------------------------- main


def project_root(payload):
    for candidate in (os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd"), os.getcwd()):
        if candidate:
            return Path(candidate)
    return Path(".")


def build_reason(broken, unsourced, engine_output):
    parts = ["THE TURN IS NOT CLEAN ENOUGH TO VERIFY."]
    parts.append(
        "The shadow ran 21 times on 2026-09-01, mean 386 seconds, and 61% of that "
        "time went to re-verifying careless errors like the ones below. They are "
        "answerable by opening a file. Fix them, then spawn the shadow."
    )
    if broken:
        parts.append(
            "BROKEN CITATIONS (%d) — your own edit moved the line:\n%s"
            % (len(broken), "\n".join("  - " + item for item in broken))
        )
    if unsourced:
        parts.append(
            "UNSOURCED NUMBERS (%d) — stated in the shadow's prompt, present in no "
            "tool result from this turn:\n%s\n  Re-derive each one with a command in "
            "THIS turn, or delete it."
            % (len(unsourced), "\n".join("  - " + item for item in unsourced))
        )
    if engine_output is not None:
        parts.append(
            "THE ENGINE GUARD IS NOT GREEN. %s was written this turn and "
            "`node %s` does not pass:\n%s" % (ENGINE, ENGINE_GUARD, engine_output)
        )
    return "\n\n".join(parts)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()
    if not isinstance(payload, dict):
        allow()

    if (payload.get("tool_name") or "") != "Agent":
        allow()

    tool_input = payload.get("tool_input") or {}
    if (tool_input.get("subagent_type") or "") != "shadow":
        allow()

    transcript = payload.get("transcript_path")
    if not transcript:
        allow()

    root = project_root(payload)
    entries = records(transcript)
    turn = turn_slice(entries)
    key = turn_key(entries)
    session_id = payload.get("session_id") or "session"

    already = refusals_so_far(session_id, key)
    if already >= CEILING:
        allow(
            "PRE-SHADOW CHECK STOOD DOWN. It has refused this turn %d times, which "
            "is its ceiling, so the shadow runs and judges the work itself. A guard "
            "that cannot be satisfied wedges the session, and this project has "
            "shipped that twice." % already
        )

    written = _files_written_in(turn)
    md_written = [path for path in written if path.lower().endswith(".md")]

    broken = broken_citations(md_written, root)

    prompt = tool_input.get("prompt")
    unsourced = unsourced_numbers(prompt, _tool_result_text(turn)) if isinstance(prompt, str) else []

    engine_output = None
    if any(path.endswith(ENGINE) or path == ENGINE for path in written):
        ok, output = engine_guard_result(root)
        if not ok:
            engine_output = output

    if not broken and not unsourced and engine_output is None:
        allow()

    record_refusal(session_id, key, already + 1)
    deny(build_reason(broken, unsourced, engine_output))


if __name__ == "__main__":
    main()
