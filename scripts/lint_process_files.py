"""Lint the process files: no dangling references, no dated scars.

Process files — CLAUDE.md, the agent/command/rule definitions under .claude/,
settings.json, .gitignore, the Makefile — describe the repo to every session
that works on it. Two defects rot them:

- a reference to a path that no longer exists, left behind when the thing it
  named was deleted;
- an incident narrative (recognized by its ISO date) baked into a rule, which
  states history instead of the present constraint.

This lint makes both fail `make lint` with a file:line, so removing a thing
forces removing every mention of it in the same change, and incidents go to
git history and .claude/LEARNINGS.md (exempt: it is the incident log) instead
of into rules.

Stdlib only; run as `uv run python scripts/lint_process_files.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: Scanned for BOTH checks: prose rules where a date is a scar and a path is a claim.
MD_GLOBS = (
    "CLAUDE.md",
    ".claude/agents/*.md",
    ".claude/commands/*.md",
    ".claude/rules/*.md",
)

#: Scanned for dangling references only.
REF_ONLY_FILES = (".claude/settings.json", "Makefile")

#: Repo directories a bare `some/path` token may refer to. A token outside
#: these (an URL fragment, `and/or` prose) is not a repo claim.
TOP_DIRS = (
    "src",
    "tests",
    "scripts",
    "fixtures",
    "docs",
    "data",
    "mobile",
    "frontend",
    "config",
    "Books",
    ".claude",
)

#: Documented example paths that name no real file on purpose.
EXAMPLE_PATHS = frozenset({"tests/test_x.py"})

DATE_RE = re.compile(r"\b20\d{2}-\d{2}\b")
#: A dated freshness stamp is a record by design, like a log entry — not a scar.
DATED_FIELD_RE = re.compile(r"^\s*last_verified:")
#: A token carrying any of these — or an `...` ellipsis — is a template, glob,
#: or make-variable, not a claim.
PLACEHOLDER_RE = re.compile(r"[{}<>*…$]|\.\.\.")
TOKEN_RE = re.compile(r"[^\s`'\"]+")
PATH_CHARS_RE = re.compile(r"[\w\-./]+")
_STRIP = ".,;:()[]"


def find_dates(text: str) -> list[str]:
    """Every ISO year-month in the text — the marker of an incident narrative."""
    return DATE_RE.findall(text)


def find_refs(text: str) -> set[str]:
    """Every repo-relative path the text claims exists.

    A claim is a whole token that either contains `.claude/` or starts with a
    known top-level directory and has a `/`. Tokens carrying placeholder or
    glob characters, or characters a repo path cannot hold, make no claim.
    """
    refs: set[str] = set()
    for raw in TOKEN_RE.findall(text):
        # Right-strip punctuation only: the leading "." of ".claude/" is path.
        token = raw.lstrip("([").rstrip(_STRIP)
        if PLACEHOLDER_RE.search(token):
            continue
        if ".claude/" in token:
            token = token[token.index(".claude/") :]
        elif not any(token.startswith(top + "/") for top in TOP_DIRS):
            continue
        if not PATH_CHARS_RE.fullmatch(token):
            continue
        ref = token.rstrip("/").rstrip(_STRIP)
        if ref and ref not in EXAMPLE_PATHS:
            refs.add(ref)
    return refs


def _ref_violations(root: Path, rel: str, lineno: int, line: str) -> list[str]:
    return [
        f"{rel}:{lineno}: dangling reference — {ref} does not exist"
        for ref in sorted(find_refs(line))
        if not (root / ref).exists()
    ]


def _scan_lines(path: Path):
    yield from enumerate(path.read_text().splitlines(), start=1)


def check_repo(root: Path) -> list[str]:
    """Every violation in the repo's process files, as `path:line: message`."""
    violations: list[str] = []

    for pattern in MD_GLOBS:
        for path in sorted(root.glob(pattern)):
            rel = path.relative_to(root).as_posix()
            in_fence = False
            for lineno, line in _scan_lines(path):
                if line.lstrip().startswith("```"):
                    in_fence = not in_fence
                # A date inside a code fence or a dated metadata field is
                # example data, not a rule narrating its own history.
                if not in_fence and not DATED_FIELD_RE.match(line):
                    violations += [
                        f"{rel}:{lineno}: dated scar — {date} states an incident, "
                        f"not a present constraint (move it to git history or LEARNINGS.md)"
                        for date in find_dates(line)
                    ]
                violations += _ref_violations(root, rel, lineno, line)

    for name in REF_ONLY_FILES:
        path = root / name
        if path.is_file():
            for lineno, line in _scan_lines(path):
                violations += _ref_violations(root, name, lineno, line)

    gitignore = root / ".gitignore"
    if gitignore.is_file():
        for lineno, line in _scan_lines(gitignore):
            stripped = line.strip()
            if stripped.startswith("!"):
                target = stripped[1:].rstrip("/")
                if not PLACEHOLDER_RE.search(target) and not (root / target).exists():
                    violations.append(
                        f".gitignore:{lineno}: dangling reference — "
                        f"negation for {target}, which does not exist"
                    )
            elif stripped.startswith("#"):
                violations += _ref_violations(root, ".gitignore", lineno, stripped)

    return violations


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    violations = check_repo(root)
    for violation in violations:
        print(violation)
    if violations:
        print(f"{len(violations)} process-file violation(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
