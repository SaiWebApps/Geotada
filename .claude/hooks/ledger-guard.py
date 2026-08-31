#!/usr/bin/env python3
"""Failures-ledger guard — enforcement at the action, not advice in context.

Reads the machine-checkable half of the failures ledger
(.claude/hooks/failure-patterns.json, beside this file) and blocks a Bash command
that matches a recorded mistake class, quoting that class's own remedy.

Project-scoped by design: the patterns cite this repo's paths and its own
incidents, so the guard is wired in .claude/settings.json (which the repo tracks)
rather than in the user's global settings. The prose half of the ledger lives in
the user's memory directory, which is not version-controlled — this file is the
half that can be reviewed in a diff.

WHY THIS EXISTS, measured rather than assumed. Across this project's sessions the
same mistake classes recurred while their rules sat written down and loaded:
the stale-working-directory class was recorded on 2026-08-25 and repeated on
2026-08-28; the never-pipe-test-output rule was in standing memory, was
re-authored into the ledger mid-session, and was still broken twice within the
hour. Over the same stretch the existing PreToolUse hooks blocked every in-scope
violation, every time, and each block produced an immediate correction. Advice
loses to enforcement, so a class that can be recognised from the pending command
belongs here instead of only in prose.

The rules live in JSON so /harvest-failures can add one without touching code.
Two kinds need structure rather than a regex and are implemented below:
``needs_abs_cd`` (does this command establish its own working directory?) and
``git_foreign_staged`` (would this commit reset an index another session owns?).

Wired as a PreToolUse hook on Bash. A command matching nothing exits instantly.
Protocol (stdin JSON, deny-by-printed-JSON, always exit 0) copied from
~/.claude/hooks/auditable-tests.py.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

PATTERNS_PATH = Path(__file__).resolve().parent / "failure-patterns.json"


def _load() -> dict:
    try:
        return json.loads(PATTERNS_PATH.read_text(encoding="utf-8"))
    except Exception:
        # A broken or absent sidecar must never block the owner's work.
        return {}


# ── kind: needs_abs_cd ───────────────────────────────────────────────────────


def _names_its_own_root(token: str) -> bool:
    """A path that names its own root, so no inherited directory can move it."""
    return token.startswith("/") or token.startswith("~")


def _establishes_cwd(command: str, repo_root: str) -> bool:
    """Does the command set its own directory before the guarded program runs?

    Accepted: an absolute `cd /path`, `make -C /path`, `git -C /path`, or an
    absolute path to the program itself. A bare relative `cd` is NOT accepted:
    it inherits whatever directory the previous call left behind, which is the
    defect this class exists for.

    Structural, not a pattern (owner ruling 2026-08-29). The earlier version
    hand-enumerated the quote spellings it expected around the path -- `"/`,
    `'/`, `"~`, `'~` -- which is class 17's disease living inside the guard
    itself: a hand-written list catches only what someone thought of, and it
    fails silently. shlex strips quotes as part of lexing, so every spelling is
    handled without anyone having to predict it.
    """
    for argv in _segments(command):
        if not argv:
            continue
        program = Path(argv[0]).name
        if program == "cd" and len(argv) > 1 and _names_its_own_root(argv[1]):
            return True
        if program in ("make", "git"):
            for index, token in enumerate(argv[:-1]):
                if token == "-C" and _names_its_own_root(argv[index + 1]):
                    return True
        if repo_root and argv[0].startswith(repo_root + "/"):
            return True
    return False


# ── kind: git_foreign_staged ─────────────────────────────────────────────────


def _pathspec(command: str) -> list[str]:
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    return tokens[tokens.index("--") + 1 :] if "--" in tokens else []


def _is_pathspec_commit(command: str) -> bool:
    """Is this a `git commit -- <paths>` — the ONLY form that resets the index?

    `git commit -m ...` and `git commit -F file` commit whatever is staged and
    cannot unstage anything, so they are outside this class entirely. Without
    this distinction the guard fired on every no-pathspec commit — twice on
    2026-08-29 — and the only way past was the acknowledgement token, which
    trains the habit of waving guards through and costs them the cases they were
    built for.

    Token inspection over the operator-separated segments, not a pattern: `cd
    /repo && git commit ...` is two segments and the second one is the commit.
    """
    for argv in _segments(command):
        if len(argv) < 2:
            continue
        if Path(argv[0]).name != "git":
            continue
        verbs = [a for a in argv[1:] if not a.startswith("-")]
        if verbs and verbs[0] == "commit":
            return "--" in argv
    return False


def _foreign_staged(command: str, repo_root: str) -> list[str]:
    """Staged paths this command does not name — another session's index entries."""
    if not _is_pathspec_commit(command):
        return []
    try:
        out = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except Exception:
        return []
    named = _pathspec(command)
    foreign = []
    for line in out.splitlines():
        if len(line) < 4 or line[0] not in "MADRC":
            continue  # unstaged or untracked — a pathspec commit cannot touch it
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        if not any(path == n or path.startswith(n.rstrip("/") + "/") for n in named):
            foreign.append(path)
    return foreign


# ── kind: inplace_source_edit ────────────────────────────────────────────────
#
# Editing a TRACKED source file with sed/awk/perl in place. Measured 2026-08-29:
# `sed -i '' 's/pipeline\.get_provider\b/.../g' tests/test_audio_stop_trip_api.py`
# reported success and changed nothing, because macOS sed has no `\b`. Eleven
# tests stayed broken, the failure surfaced only on the next full run, and the
# whole suite had to be repeated. A stream editor reports success for a pattern
# that matched nothing; the Edit tool fails loudly when its target text is absent.
#
# Structural, not a pattern (owner ruling 2026-08-29): the command is lexed into
# segments, each segment's program is looked at by name, its flags are examined
# for an in-place spelling, and its file arguments are checked against
# `git ls-files`. A scratchpad or /tmp target passes; only tracked files are
# guarded. Reading with sed/awk/perl is untouched — the no-grep guard owns that.

_INPLACE_TOOLS = {"sed", "awk", "gawk", "perl"}
_OPERATORS = {"&&", "||", ";", "|", "&", "(", ")"}


def _segments(command: str) -> list[list[str]]:
    """The command split into its operator-separated parts, each as argv."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        tokens = command.split()
    segments: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token in _OPERATORS:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _is_inplace_flag(tool: str, arg: str) -> bool:
    """Does this argument put the tool into in-place mode?

    Spellings observed in the wild and covered: `-i`, `-i.bak`, `--in-place`,
    `--in-place=.bak`, gawk's `-i inplace`, and perl's single-dash clusters
    (`-pi`, `-pie`, `-0pi`) where the letter i rides along with other switches.
    """
    if not arg.startswith("-") or arg == "-":
        return False
    if arg in ("-i", "--in-place"):
        return True
    if arg.startswith("--in-place="):
        return True
    if arg.startswith("--"):
        return False
    if arg.startswith("-i"):
        return True  # -i.bak
    if tool == "perl":
        return "i" in arg[1:]  # cluster membership, not a pattern
    return False


def _tracked_files(repo_root: str) -> set[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout
    except Exception:
        return set()
    return {line for line in out.splitlines() if line}


def _inplace_targets(command: str, repo_root: str) -> list[str]:
    """Tracked files this command would rewrite in place."""
    if not repo_root:
        return []
    tracked = None
    hits: list[str] = []
    for argv in _segments(command):
        if not argv:
            continue
        tool = Path(argv[0]).name
        if tool not in _INPLACE_TOOLS:
            continue
        if not any(_is_inplace_flag(tool, a) for a in argv[1:]):
            continue
        if tracked is None:
            tracked = _tracked_files(repo_root)
        for arg in argv[1:]:
            if arg.startswith("-"):
                continue
            candidate = arg.lstrip("./")
            if candidate in tracked:
                hits.append(candidate)
            else:
                try:
                    resolved = str(Path(arg).resolve().relative_to(Path(repo_root)))
                except (ValueError, OSError):
                    continue
                if resolved in tracked:
                    hits.append(resolved)
    return hits


# ── kind: git_source_excerpt ─────────────────────────────────────────────────
#
# Reaching a tracked file's CONTENT through git, which walks straight around the
# global whole-source-file guard. Measured 2026-08-29: `grep -n RENDER_LOCAL_EXEC
# Makefile` was blocked by ~/.claude/hooks/no-grep.py, while `git grep -n
# RENDER_LOCAL_EXEC Makefile | head -5` ran unchallenged in the same session —
# that guard looks at the program named `grep`, and `git` is a different program.
# `git show <rev>:<path> | head` is the same door, and it is the one I would use
# next, so it is closed here too.
#
# Structural, not a pattern (owner ruling 2026-08-29): the command is lexed into
# segments, git's own subcommand is found by stepping over the global flags that
# carry a value, and the arguments are checked against `git ls-files`.
#
# Deliberately NOT blocked, because each is either the remedy or ordinary work:
# `git grep -l` (which files match — that locates a file to Read), `git log`,
# `git status`, `git diff` (a diff is the legitimate artifact for reviewing a
# change), and an unpiped `git show <rev>:<path>`, which prints the whole file
# and is the one thing the Read tool genuinely cannot do.

#: git-grep flags whose output is file NAMES or a count, never quoted lines.
_GIT_NAMES_ONLY = {
    "-l",
    "--files-with-matches",
    "-L",
    "--files-without-match",
    "--name-only",
    "-c",
    "--count",
}

#: git's own global flags that consume the NEXT token, so the subcommand scan
#: must step over both. `-c` is global before the subcommand and git-grep's
#: --count after it; position is what tells them apart, and position is what
#: this scan reads.
_GIT_VALUE_FLAGS = {"-C", "-c"}

#: Programs that turn printed output into an excerpt.
_FILTERS = {
    "head",
    "tail",
    "sed",
    "awk",
    "gawk",
    "grep",
    "egrep",
    "fgrep",
    "cut",
    "wc",
    "sort",
    "uniq",
    "perl",
}


def _git_subcommand(argv: list[str]) -> tuple[str | None, list[str]]:
    """git's subcommand and the arguments after it."""
    index = 1
    while index < len(argv):
        token = argv[index]
        if not token.startswith("-"):
            return token, argv[index + 1 :]
        index += 2 if token in _GIT_VALUE_FLAGS else 1
    return None, []


def _git_source_excerpts(command: str, repo_root: str) -> list[str]:
    """Ways this command would quote tracked file content through git."""
    if not repo_root:
        return []
    segments = _segments(command)
    programs = {Path(argv[0]).name for argv in segments if argv}
    tracked = None
    hits: list[str] = []
    for argv in segments:
        if not argv or Path(argv[0]).name != "git":
            continue
        subcommand, rest = _git_subcommand(argv)
        if subcommand == "grep":
            if any(flag in _GIT_NAMES_ONLY for flag in rest):
                continue  # listing which files match, not quoting their lines
            hits.append("git grep")
        elif subcommand == "show":
            if not programs & _FILTERS:
                continue  # a whole file at a revision is a whole-file read
            if tracked is None:
                tracked = _tracked_files(repo_root)
            for arg in rest:
                if arg.startswith("-") or ":" not in arg:
                    continue
                candidate = arg.rpartition(":")[2].lstrip("./")
                if candidate in tracked:
                    hits.append(f"git show …:{candidate}")
    return hits


# ── kind: wrong_test_bar ─────────────────────────────────────────────────────
#
# Claiming a green bar from a command that is NOT this repository's bar. Measured
# 2026-08-30: a session used bare `flutter test` as its green bar for about ten
# commits. It reported 340 passing while `make flutter-test` — the real target,
# which runs scripts/flutter_test.sh — had 15 RED, every failure in a file that
# same session had just added.
#
# This class is why the guard exists rather than another verifier. The claim
# "flutter test: 340 passed" was TRUE, so re-deriving it confirms it: no
# after-the-fact checker of claims can see the error, because nothing false was
# ever said. The wrongness is in the command, and the command is visible only
# here. ~/.claude/hooks/auditable-tests.py does not reach it either — that guard
# recognises `pytest` and `make <target>`, and a bare `flutter test` is neither,
# so the right command is guarded and the wrong one runs unchallenged.
#
# Structural, not a pattern (owner ruling 2026-08-29): the command is lexed into
# segments and each segment's program is looked at by name, so `cd mobile &&
# flutter test` is caught by the second segment without anyone predicting the
# spelling of the first.
#
# THE EXEMPTION IS THE DESIGN. CLAUDE.md rule 7 mandates iterating on a single
# targeted test, and mobile/ has no `make test-file` equivalent, so a predicate
# that fired on every direct `flutter test` would spend the acknowledgement token
# on every iteration loop — the habituation failure that class 12's narrowing was
# written to stop, since a guard that is wrong is not harmless: it spends the
# escape hatch the real cases need. A run that names a *_test.dart file AND a
# --platform is that legitimate iteration and passes clean. A whole-suite or
# platform-defaulted run is the bar impersonator and is refused.

_TEST_RUNNERS = {"flutter", "dart"}


def _is_bar_impersonator(argv: list[str]) -> bool:
    """Is this segment a whole-suite `flutter test`, standing in for the bar?"""
    if Path(argv[0]).name not in _TEST_RUNNERS:
        return False
    verbs = [a for a in argv[1:] if not a.startswith("-")]
    if not verbs or verbs[0] != "test":
        return False
    names_a_file = any(a.endswith("_test.dart") for a in argv[1:])
    names_platform = any(
        a == "--platform" or a.startswith("--platform=") for a in argv[1:]
    )
    return not (names_a_file and names_platform)


def _wrong_test_bar(command: str) -> bool:
    """Does any segment run the flutter/dart suite in place of the real target?"""
    return any(argv and _is_bar_impersonator(argv) for argv in _segments(command))


# ── kind: blanket_conflict_resolution ────────────────────────────────────────
#
# Settling a whole merge with one `git checkout --ours`. Measured 2026-08-31: a
# merge produced 19 conflicts and all 19 were resolved in a single command. Not
# one of them was read. The sweep happened to be right — this side was the
# hand-port of the other's redesign — but nobody knew that when it ran, and the
# owner's ruling on the one file where it was wrong was: "NO. No flinching. ONLY
# keep the feature that ensures a richer product experience."
#
# A conflict is git saying two people answered the same question differently.
# `--ours` across a list answers every one of them the same way without looking,
# which is the same deferral as keeping both, wearing the opposite mask.
#
# ONE FILE IS STILL ALLOWED, and that limit is the whole design. Resolving a
# single named path is a considered act: you can only type it after deciding
# about that file. The threshold sits at four because a three-file resolution
# still reads as three decisions typed together, while a sweep is what a sweep
# looks like — and a directory or `.` argument is a sweep at any size.

_SIDE_FLAGS = frozenset({"--ours", "--theirs"})
_MAX_NAMED_PATHS = 3


def _blanket_conflict_resolution(command: str) -> str:
    """The path count when this settles many conflicts at once; "" otherwise."""
    for argv in _segments(command):
        if not argv or Path(argv[0]).name != "git":
            continue
        subcommand, rest = _git_subcommand(argv)
        if subcommand != "checkout":
            continue
        if not any(token in _SIDE_FLAGS for token in rest):
            continue
        paths = [
            token
            for token in rest
            if not token.startswith("-") and token != "--"
        ]
        for path in paths:
            if path in (".", "..") or path.endswith("/"):
                return f"a whole directory ({path})"
        if len(paths) > _MAX_NAMED_PATHS:
            return f"{len(paths)} files at once"
    return ""


# ── evaluation ───────────────────────────────────────────────────────────────


def _violation(command: str, config: dict) -> tuple[int, str, str] | None:
    repo_root = config.get("repo_root", "")
    for rule in config.get("rules", []):
        kind = rule.get("kind", "regex")
        hit = False
        detail = ""

        if kind == "regex":
            hit = all(
                re.search(p, command) for p in rule.get("require_all", []) or ["(?!)"]
            ) and not any(re.search(p, command) for p in rule.get("forbid_any", []))

        elif kind == "needs_abs_cd":
            applies = rule.get("applies_to", "(?!)")
            hit = bool(re.search(applies, command)) and not _establishes_cwd(
                command, repo_root
            )

        elif kind == "git_foreign_staged":
            foreign = _foreign_staged(command, repo_root)
            hit = bool(foreign)
            if hit:
                shown = ", ".join(foreign[:6]) + ("…" if len(foreign) > 6 else "")
                detail = f" Staged but unnamed: {shown}"

        elif kind == "inplace_source_edit":
            targets = _inplace_targets(command, repo_root)
            hit = bool(targets)
            if hit:
                detail = f" Would rewrite in place: {', '.join(sorted(set(targets))[:6])}"

        elif kind == "git_source_excerpt":
            excerpts = _git_source_excerpts(command, repo_root)
            hit = bool(excerpts)
            if hit:
                detail = f" The excerpting call: {', '.join(sorted(set(excerpts))[:4])}"

        elif kind == "wrong_test_bar":
            hit = _wrong_test_bar(command)

        elif kind == "blanket_conflict_resolution":
            scope = _blanket_conflict_resolution(command)
            hit = bool(scope)
            if hit:
                detail = f" This one settles {scope}."

        if hit:
            return rule.get("class", 0), rule.get("name", "?"), rule.get("message", "") + detail
    return None


def _deny(reason: str) -> None:
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


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if (payload.get("tool_name") or "") != "Bash":
        sys.exit(0)

    command = str((payload.get("tool_input") or {}).get("command") or "")
    if not command:
        sys.exit(0)

    config = _load()
    token = config.get("acknowledge_token", "")
    if token and token in command:
        sys.exit(0)  # deliberate, acknowledged, and visible in the transcript

    found = _violation(command, config)
    if found:
        klass, name, message = found
        _deny(
            f"BLOCKED by the failures-ledger guard "
            f"(.claude/hooks/ledger-guard.py, class {klass} — {name}): {message} "
            f"The full class is in failures-ledger.md (memory); its pattern is in "
            f".claude/hooks/failure-patterns.json. To proceed deliberately, append "
            f"'{token}' to the command and say why in your report."
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
