#!/usr/bin/env python3
"""The citation guard (owner ruling 2026-08-29).

Every claim about this repository must be provable, and a claim about code must
point at the line. Written rules did not hold — this session produced "the audio
is made earlier, on our computer", which was false, cost the owner an hour, and
made a real feature look pointless.

THREE ARMS, and they must ship together.

  1. EVERY CITATION IS TRUE. For each `path:line` in the reply: the file exists,
     it was actually READ in this session, and the line is inside it. A citation
     to a file never opened is the exact shape of a guess wearing evidence.

  2. NAMING THE CODE OBLIGES YOU TO POINT AT IT. If the reply names a product
     file, or names a FUNCTION OR CLASS DEFINED under src/, it must carry a
     citation into the file that defines what it named.

  3. TOUCHING THE CODE OBLIGES YOU TO CITE IT. If any tool call THIS TURN opened,
     edited or named a file under src/ or mobile/lib/, the reply must carry a
     true citation — whatever words it happens to use.

WHY ARM 3 EXISTS (owner ruling 2026-08-29, second sitting). Arms 1 and 2 both
trigger on the TEXT OF THE REPLY, which means the writer chooses whether they
fire. Measured that day: a reply asserted that the workbench "signs in with a
real identity and calls the same phone endpoints, in the phone order, with the
phone payloads" — read off a commit message, never verified against the code —
and this guard stayed silent, because the sentence named no path outside
backticks. The owner's ruling was exact: "It should ALWAYS fire. It should NEVER
EVER stop firing just because of how you write."

A trigger the writer controls is not a guard. Arm 3 moves the trigger to the
SESSION'S BEHAVIOUR, which the writer cannot edit after the fact: open a product
file and you owe a line, in any wording, including no wording at all.

Arm 2 exists because arm 1 alone creates a perverse incentive: a guard that only
checks the citations you give rewards giving fewer. Arm 3 exists because arms 1
and 2 together still reward saying less. Together they push the other way — touch
the code, name the code, prove the line.

NO REGEX (owner ruling 2026-08-29, enforced by no-regex-in-hooks.py). This file
does not pattern-match; it TOKENIZES and then LOOKS UP, and it PARSES src/ with
`ast` to learn the product's own vocabulary. Every token of the reply is trimmed
of its punctuation and markdown adornment and asked two questions the repository
can answer: are you a file I track, and are you a name I define? A set lookup
cannot miss a spelling variant nobody thought to teach it, which is exactly how
the sibling no-excuses prefilter came to know `flaky` but not `flake` and
silently starved its own rubric.

AMBIGUOUS NAMES ARE DROPPED ON PURPOSE. src/ defines functions called `generate`,
`gravity` and `spotlight`; "generate the trip" in ordinary prose is not a code
claim, and a guard that blocks it is the noise the owner's ledger records as
fatal to a guard. Only names that could not be an English word survive into the
vocabulary — a name carrying an underscore, or two or more CamelCase humps.
`plan_premium_full_telling` qualifies. `generate` does not, and a bare-word
sentence is the anchor-free class arm 3 was built to cover anyway.

Quote checking is +/- QUOTE_SLACK lines, not exact: an edit later in the session
moves every line below it, and a guard that fires on its own staleness is noise —
the owner's ledger records that a noisy hook gets deleted, which costs the
classes that do work.

WHAT THIS STILL CANNOT DO, stated here so nobody mistakes it for total: a reply
that makes a plain-English claim, names nothing, AND follows a turn that touched
no product file carries nothing to check and triggers no arm. That residue
belongs to the verification-gate reviewer, which reads the request and the design
docs and tries to disprove the claim.
"""

import ast
import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STATE_PATH = Path("/tmp/ondoway-citation-guard-state.json")
MAX_BLOCKS = 3
TRANSCRIPT_TAIL_BYTES = 4 * 1024 * 1024  # tool calls span the whole turn, not just its tail
QUOTE_SLACK = 3

REPO = Path(__file__).resolve().parents[2]

# Extensions whose contents are CODE CLAIMS. Prose and data are excluded: a reply
# may discuss a markdown plan or a JSON fixture without pointing at a line.
CODE_SUFFIXES = {".py", ".dart", ".js", ".ts", ".tsx", ".html", ".sh", ".yaml", ".yml"}

# Product code — the scope of arms 2 and 3. A test-run report legitimately names
# tests/ files with no line to cite, and blocking an honest "389 passed" is the
# noise that gets a hook deleted, so tests/ stays out.
#
# frontend/ IS product code, and leaving it out was the first version's own blind
# spot: the false sentence this guard was rewritten for — the workbench "signs in
# with a real identity and calls the same phone endpoints" — is a claim about
# frontend/review.html, the one file the new arms could not see. CLAUDE.md rule 1
# binds the workbench and the app equally; so does this.
PRODUCT_ROOTS = ("src/", "mobile/lib/", "frontend/")

# Records that are typed `user` but are the HARNESS speaking, not the person.
# A background task finishing mid-turn lands as a plain user string; treating it
# as the person would move the turn boundary and silence arm 3 for the reply
# written right after it — the same "stops firing" class as the wording escape,
# triggered by timing instead. Verified against this project's own transcript,
# 2026-08-29: task notifications arrive as `type: "user"` with string content and
# no tool_result chunk, identical in shape to a typed message.
HARNESS_MARKERS = ("<task-notification>", "<system-reminder>", "<local-command-stdout>")

# Tools whose file_path is an act of opening product code (arm 3).
FILE_TOOLS = {"Read", "Edit", "Write", "NotebookEdit"}

# Characters that surround a token in prose and markdown without being part of
# it. Stripped from both ends until nothing more comes off. The curly quotes,
# dashes and ellipsis are deliberate and load-bearing: a reply is prose, and a
# path arrives wrapped in the punctuation a writer actually types. Ruff's
# ambiguous-glyph rule is silenced because those glyphs ARE the target here.
ADORNMENT = "()[]{}<>`'\"*_,;!?“”‘’—–…|"  # noqa: RUF001


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
    """Every JSON record in the transcript tail, oldest first."""
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

    Two kinds of record wear the `user` type without being a typed message: a
    tool handing its result back (a `tool_result` chunk), and the harness posting
    a background-task notification (a plain string carrying one of
    HARNESS_MARKERS). Both are excluded, because both would otherwise move the
    turn boundary that scopes arm 3.

    Scoping matters in the other direction too: without ANY boundary, one Read of
    a product file would oblige a citation in every reply for the rest of the
    session, which is the noise that gets a guard deleted.
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
    """The records since the person last spoke."""
    start = 0
    for index, entry in enumerate(records):
        if is_human_turn(entry):
            start = index + 1
    return records[start:]


def last_assistant_text(records):
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


def tool_uses(records):
    """Every tool_use chunk in these records, as (name, input) pairs."""
    for entry in records:
        content = (entry.get("message") or {}).get("content") or []
        for chunk in content:
            if isinstance(chunk, dict) and chunk.get("type") == "tool_use":
                yield chunk.get("name"), (chunk.get("input") or {})


def files_opened(records):
    """Repo-relative paths this session actually opened with the Read tool.

    ONLY Read counts. A `cat` in Bash is not a reading credential: the no-grep
    guard exists because shell excerpting hides the context that changes the
    correct edit, and a citation earned from an excerpt is the thing this guard
    is trying to stop.
    """
    seen = set()
    for name, data in tool_uses(records):
        if name != "Read":
            continue
        path = data.get("file_path")
        if path:
            relative = to_repo_relative(path)
            if relative:
                seen.add(relative)
    return seen


def product_code_touched(records):
    """Product files this turn's tool calls opened, edited, or named in a command.

    Arm 3's trigger. A file tool is judged by its path; Bash is judged by whether
    its command mentions a product root at all, which is a substring question the
    language answers directly.
    """
    touched = set()
    for name, data in tool_uses(records):
        if name in FILE_TOOLS:
            raw = data.get("file_path") or ""
            relative = to_repo_relative(raw) if raw else None
            if relative and any(relative.startswith(root) for root in PRODUCT_ROOTS):
                touched.add(relative)
        elif name == "Bash":
            command = data.get("command") or ""
            for root in PRODUCT_ROOTS:
                if root in command:
                    touched.add(root)
    return touched


def to_repo_relative(path):
    try:
        return str(Path(path).resolve().relative_to(REPO))
    except (ValueError, OSError):
        return str(path).lstrip("./") or None


def tracked_files():
    """Every path git tracks, plus a basename index for short citations."""
    try:
        result = subprocess.run(["git", "ls-files"], cwd=REPO,
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return set(), {}
    paths = {line for line in result.stdout.splitlines() if line}
    by_basename = {}
    for path in paths:
        by_basename.setdefault(Path(path).name, []).append(path)
    return paths, by_basename


def could_be_an_english_word(name):
    """True when this symbol name is indistinguishable from ordinary prose.

    An underscore settles it — no English word carries one. Otherwise the test is
    CamelCase humps: `TripService` and `GeneratedTrip` are names, `generate` and
    `gravity` are words a sentence uses innocently.
    """
    if name.startswith("__") and name.endswith("__"):
        return True
    if "_" in name:
        return False
    humps = 1 if name[:1].isupper() else 0
    previous_is_lower = False
    for character in name:
        if character.isupper() and previous_is_lower:
            humps += 1
        previous_is_lower = character.islower()
    return humps < 2


def product_vocabulary():
    """Unambiguous function and class names defined under src/, and where.

    Parsed, never matched: `ast` reports the definitions the module actually
    makes, so a name cannot hide behind an unusual spelling or a decorator.
    """
    homes = {}
    source_root = REPO / "src"
    if not source_root.is_dir():
        return homes
    for path in sorted(source_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except (OSError, SyntaxError):
            continue
        relative = str(path.relative_to(REPO))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if could_be_an_english_word(node.name):
                continue
            homes.setdefault(node.name, set()).add(relative)
    return homes


def outside_backticks(reply):
    """The reply with every backtick-quoted run removed.

    A path inside backticks is being QUOTED, not claimed: "`sed -i '' …
    scripts/workbench.sh`" in a table of test fixtures says nothing about that
    file's contents, while "workbench.sh pins the provider" does. The PATH half
    of arm 2 asks only about the second kind. Found 2026-08-29, when this guard
    blocked a report whose only mention of two source files was inside a table of
    shell commands used as hook payloads.

    The SYMBOL half deliberately does NOT use this. Backticks are how a writer
    spells a function name in prose — `plan_premium_full_telling` is the normal,
    correct way to write it — so exempting them there would exempt every real
    code claim. That is precisely the hole the owner closed on 2026-08-29.

    Splitting on the backtick is the parse — odd-indexed pieces are inside a
    quote — the same technique quotes_around uses. No pattern involved.
    """
    pieces = reply.split("`")
    return " ".join(piece for index, piece in enumerate(pieces) if index % 2 == 0)


def tokens_of(reply):
    """The reply split into candidate tokens, adornment trimmed off each end.

    Deliberately not a pattern. Split on whitespace, then peel punctuation from
    both ends until the token stops changing. `(src/audio/provider.py:222),`
    becomes `src/audio/provider.py:222` without anyone having to anticipate the
    parenthesis or the comma.
    """
    out = []
    for raw in reply.split():
        token = raw
        while True:
            trimmed = token.strip(ADORNMENT)
            # A tracked path never ENDS in a dot, so a trailing one is always the
            # sentence's, never the token's. Leading dots stay: `./src/...` is a
            # real way to write a path. Found by the payload tests, 2026-08-29 —
            # `provider.py:222.` parsed its line number as "222." and silently
            # became a non-citation, disarming arm 1 entirely.
            trimmed = trimmed.rstrip(".")
            if trimmed == token:
                break
            token = trimmed
        if token:
            out.append(token)
    return out


def symbol_tokens(reply):
    """Tokens with adornment peeled, keeping the underscores a symbol needs.

    `tokens_of` strips underscores as markdown emphasis, which is right for a
    path and fatal for a symbol: it turns `_walk_arrivals` into `walk_arrivals`
    and `plan_premium_full_telling` keeps its inner ones only by luck of position.
    Here the underscore is part of the name, so it is peeled from neither end.
    """
    adornment = ADORNMENT.replace("_", "")
    out = []
    for raw in reply.split():
        token = raw
        while True:
            trimmed = token.strip(adornment).rstrip(".")
            if trimmed == token:
                break
            token = trimmed
        if token:
            out.append(token)
    return out


def split_citation(token):
    """(path, line) when the token ends in `:NN` or `:NN-MM`, else (token, None).

    int() is the parser. A tail that is not a number is simply not a line
    number, which is a fact the language can answer without a pattern.
    """
    if ":" not in token:
        return token, None
    head, _, tail = token.rpartition(":")
    if not head:
        return token, None
    start = tail.split("-", 1)[0]
    try:
        return head, int(start)
    except ValueError:
        return token, None


def resolve(cited, paths, by_basename):
    """The tracked path a citation names, or None. A bare basename is accepted."""
    cited = cited.lstrip("./")
    if cited in paths:
        return cited
    candidates = by_basename.get(Path(cited).name, [])
    suffix_matches = [p for p in candidates if p.endswith(cited)]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    return candidates[0] if len(candidates) == 1 else None


def quotes_around(reply, token):
    """Backtick-delimited quotes sitting near `token` in the reply.

    Splitting on the backtick is the parse: odd-indexed pieces are inside a
    quote. No pattern involved.
    """
    where = reply.find(token)
    if where == -1:
        return []
    window = reply[max(0, where - 240): where + 240]
    pieces = window.split("`")
    return [p.strip() for i, p in enumerate(pieces)
            if i % 2 == 1 and len(p.strip()) >= 12 and "\n" not in p]


def quote_mismatch(reply, token, path, line, vocabulary):
    """An error string when a quote beside the citation is nowhere near it.

    A quote that CONTAINS the citation is talking ABOUT the citation, not
    quoting the file — "`provider.py:222.` parsed `222.` as a line number" is a
    sentence about parsing, and demanding that text appear at line 222 is
    nonsense. Found when this guard blocked a reply describing its own bug fix,
    2026-08-29. Self-referential quotes are dropped before the check.

    A bare SYMBOL NAME is dropped too. `plan_premium_full_telling` beside a
    citation is the name of the thing being discussed, not a line lifted out of
    the file, and arm 2 already answers the question it raises — does the reply
    point into the file that DEFINES it. Letting arm 1 judge the same string as
    a failed quotation is double jeopardy, and it fired on an honest reply the
    first time these payload tests ran.
    """
    quoted = [q for q in quotes_around(reply, token)
              if path not in q and Path(path).name not in q and token not in q
              and q not in vocabulary]
    if not quoted:
        return None
    try:
        body = (REPO / path).read_text(errors="replace").splitlines()
    except OSError:
        return None
    low = max(0, line - 1 - QUOTE_SLACK)
    high = min(len(body), line + QUOTE_SLACK)
    near = "\n".join(body[low:high])
    for text in quoted:
        if text and text in near:
            return None
    return (f"none of the quoted text beside {token} appears within "
            f"{QUOTE_SLACK} lines of {path}:{line}")


def check_citations(reply, paths, by_basename, opened, vocabulary):
    """Arm 1 plus the PATH half of arm 2.

    Returns (problems, verified_paths, named_product_files).
    """
    problems = []
    verified_paths = set()
    named_files = set()
    claimed_text = outside_backticks(reply)

    for token in tokens_of(reply):
        cited, line = split_citation(token)
        path = resolve(cited, paths, by_basename)
        if path is None:
            # Only complain when the token was clearly MEANT as a citation: it
            # carried a line number and looks like a path. `10:30` (a clock) has
            # no dot and no slash, so it never reaches here.
            if line is not None and ("/" in cited or "." in cited):
                problems.append(f"{token} — no such file is tracked in this repo")
            continue
        if Path(path).suffix not in CODE_SUFFIXES:
            if line is not None:
                verified_paths.add(path)
            continue

        if line is not None:
            if path not in opened:
                problems.append(
                    f"{token} — you never opened {path} this session, so this "
                    f"citation is a guess wearing evidence. Read it, then cite it.")
                continue
            try:
                total = len((REPO / path).read_text(errors="replace").splitlines())
            except OSError:
                problems.append(f"{token} — {path} could not be read back")
                continue
            if line < 1 or line > total:
                problems.append(
                    f"{token} — {path} has {total} lines; {line} is outside it")
                continue
            mismatch = quote_mismatch(reply, token, path, line, vocabulary)
            if mismatch:
                problems.append(mismatch)
                continue
            verified_paths.add(path)
        elif any(path.startswith(root) for root in PRODUCT_ROOTS):
            # Only a path named OUTSIDE backticks is a claim about the code; one
            # that appears solely inside a quoted command is being shown, not
            # asserted.
            if cited in claimed_text or Path(path).name in claimed_text:
                named_files.add(path)

    return problems, verified_paths, named_files


def unproven_symbols(reply, vocabulary, verified_paths):
    """Product symbols the reply names without pointing into their own file."""
    unproven = {}
    for token in symbol_tokens(reply):
        homes = vocabulary.get(token)
        if homes and not (homes & verified_paths):
            unproven[token] = sorted(homes)
    return unproven


def main():
    if os.environ.get("CLAUDE_NO_EXCUSES_JUDGE") or os.environ.get("ONDOWAY_CITATION_GUARD"):
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
        allow()

    records = transcript_records(transcript)
    reply = last_assistant_text(records)
    if not reply:
        allow()
    # No length floor. The no-excuses guard next door once skipped short replies
    # because a one-liner rarely contains an excuse; a one-liner very easily
    # contains a false citation ("see src/audio/provider.py:99999"). Found by the
    # payload tests, 2026-08-29.

    paths, by_basename = tracked_files()
    if not paths:
        allow()  # not a git checkout we can reason about; never wedge the session
    opened = files_opened(records)

    vocabulary = product_vocabulary()
    problems, verified_paths, named_files = check_citations(
        reply, paths, by_basename, opened, vocabulary)

    # ---- ARM 2 (symbols): the product's own vocabulary was used --------------
    if not problems:
        unproven = unproven_symbols(reply, vocabulary, verified_paths)
        if unproven:
            listed = ", ".join(
                f"{name} (defined in {', '.join(homes)})"
                for name, homes in sorted(unproven.items())[:4])
            problems.append(
                f"this reply names {listed} and cites no line in the file that "
                f"defines it. Naming the code is claiming to know it — open that "
                f"file and point at the line, or say it without the name.")

    # ---- ARM 2 (paths): product file named, nothing cited anywhere -----------
    if not problems and not verified_paths and named_files:
        problems.append(
            "this reply talks about " + ", ".join(sorted(named_files)[:4])
            + " and cites no line at all. Point at the line (path:NN) or drop the "
              "claim — an unproven statement about the code is exactly what this "
              "guard exists to stop.")

    # ---- ARM 3: this turn touched product code, so the reply owes a line -----
    if not problems and not verified_paths:
        touched = product_code_touched(this_turn(records))
        if touched:
            problems.append(
                "this turn opened or ran against " + ", ".join(sorted(touched)[:4])
                + " and the reply cites no line at all. Work on product code is "
                  "reported with a citation whatever words the report uses — a "
                  "guard you can silence by rephrasing is not a guard.")

    if not problems:
        allow()

    state["blocks"] = state.get("blocks", 0) + 1
    write_state(state)
    block(
        "CITATION GUARD — prove it or drop it.\n\n"
        + "\n".join(f"  - {p}" for p in problems)
        + "\n\nEvery claim about this repo carries its source; a claim about code "
          "carries the line. Open the file, quote the line, cite it as path:NN — "
          "then say it.")


if __name__ == "__main__":
    main()
