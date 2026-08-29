#!/usr/bin/env python3
"""The citation guard (owner ruling 2026-08-29).

Every claim about this repository must be provable, and a claim about code must
point at the line. Written rules did not hold — this session produced "the audio
is made earlier, on our computer", which was false, cost the owner an hour, and
made a real feature look pointless.

TWO ARMS, and they must ship together.

  1. EVERY CITATION IS TRUE. For each `path:line` in the reply: the file exists,
     it was actually READ in this session, and the line is inside it. A citation
     to a file never opened is the exact shape of a guess wearing evidence.

  2. A CODE CLAIM WITHOUT A CITATION IS BLOCKED. If the reply names a real file
     under src/ or mobile/lib/ and carries no valid citation at all, it is
     refused.

Arm 2 exists because arm 1 alone creates a perverse incentive: a guard that only
checks the citations you give rewards giving fewer. Together they push the other
way — name the code, prove the line.

NO REGEX (owner ruling 2026-08-29, enforced by no-regex-in-hooks.py). This file
does not pattern-match; it TOKENIZES and then LOOKS UP. Every token of the reply
is trimmed of its punctuation and markdown adornment and asked one question the
repository can answer: are you a file I track? A set lookup cannot miss a
spelling variant nobody thought to teach it, which is exactly how the sibling
no-excuses prefilter came to know `flaky` but not `flake` and silently starved
its own rubric.

Quote checking is +/- QUOTE_SLACK lines, not exact: an edit later in the session
moves every line below it, and a guard that fires on its own staleness is noise —
the owner's ledger records that a noisy hook gets deleted, which costs the
classes that do work.

WHAT THIS CANNOT DO, stated here so nobody mistakes it for total: a plain-English
falsehood that names no file and no symbol — "the audio is made earlier, on our
computer" — carries nothing to check. This guard makes every citation TRUE; it
cannot force a citation onto a sentence that avoids naming anything. That class
belongs to the verification-gate reviewer, which reads the request and the design
docs and tries to disprove the claim.
"""

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

# Product code — arm 2's scope. A test-run report legitimately names tests/ files
# with no line to cite, and blocking an honest "389 passed" is the noise that
# gets a hook deleted.
PRODUCT_ROOTS = ("src/", "mobile/lib/")

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


def files_opened(records):
    """Repo-relative paths this session actually opened with the Read tool.

    ONLY Read counts. A `cat` in Bash is not a reading credential: the no-grep
    guard exists because shell excerpting hides the context that changes the
    correct edit, and a citation earned from an excerpt is the thing this guard
    is trying to stop.
    """
    seen = set()
    for entry in records:
        content = (entry.get("message") or {}).get("content") or []
        for chunk in content:
            if not isinstance(chunk, dict) or chunk.get("type") != "tool_use":
                continue
            if chunk.get("name") != "Read":
                continue
            path = (chunk.get("input") or {}).get("file_path")
            if path:
                relative = to_repo_relative(path)
                if relative:
                    seen.add(relative)
    return seen


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


def outside_backticks(reply):
    """The reply with every backtick-quoted run removed.

    A path inside backticks is being QUOTED, not claimed: "`sed -i '' …
    scripts/workbench.sh`" in a table of test fixtures says nothing about that
    file's contents, while "workbench.sh pins the provider" does. Arm 2 asks
    only about the second kind. Found 2026-08-29, when this guard blocked a
    report whose only mention of two source files was inside a table of shell
    commands used as hook payloads.

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


def quote_mismatch(reply, token, path, line):
    """An error string when a quote beside the citation is nowhere near it.

    A quote that CONTAINS the citation is talking ABOUT the citation, not
    quoting the file — "`provider.py:222.` parsed `222.` as a line number" is a
    sentence about parsing, and demanding that text appear at line 222 is
    nonsense. Found when this guard blocked a reply describing its own bug fix,
    2026-08-29. Self-referential quotes are dropped before the check.
    """
    quoted = [q for q in quotes_around(reply, token)
              if path not in q and Path(path).name not in q and token not in q]
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

    problems = []
    verified = 0
    named_product_code = set()
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
                verified += 1
            continue

        # ---- ARM 1: a citation was given, so it must be true ----------------
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
            mismatch = quote_mismatch(reply, token, path, line)
            if mismatch:
                problems.append(mismatch)
                continue
            verified += 1
        elif any(path.startswith(root) for root in PRODUCT_ROOTS):
            # Only a path named OUTSIDE backticks is a claim about the code; one
            # that appears solely inside a quoted command is being shown, not
            # asserted.
            if cited in claimed_text or Path(path).name in claimed_text:
                named_product_code.add(path)

    # ---- ARM 2: product code named, nothing cited anywhere ------------------
    if not problems and verified == 0 and named_product_code:
        problems.append(
            "this reply talks about " + ", ".join(sorted(named_product_code)[:4])
            + " and cites no line at all. Point at the line (path:NN) or drop the "
              "claim — an unproven statement about the code is exactly what this "
              "guard exists to stop.")

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
