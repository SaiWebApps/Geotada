"""RED-FIRST regressions for the .claude/hooks/guard.sh high-consequence gate.

The guard is a PreToolUse hook: it reads a ``{"tool_name","tool_input":{"command"}}``
JSON envelope on stdin and exits 0 (allow) or 2 (block) after echoing a
justification prompt to stderr. These tests drive the real shell script through
a subprocess and assert its exit code, so they exercise the exact regex the
harness runs — not a Python re-implementation.

Two defect classes these lock down (both silently EVADED the guard before the
fix, letting a destructive command run unlogged):

1. Force-push to a branch when ``-f`` is the TRAILING token
   (``git push origin main -f``). The old pattern required ``-f`` to be followed
   by whitespace, so ``-f`` at end-of-string slipped through even though the
   space-after form (``git push -f origin main``) was caught — trivially evaded
   by reordering the identical command.

2. Recursive-force ``rm`` whenever the flags are anything other than the exact
   ``-rf``/``-Rf`` spelling: ``rm -fr``, ``rm -f -r``, ``rm -r -f``,
   ``rm --recursive --force``. All delete the same tree; the guard exists
   precisely because such a command already destroyed a sibling worktree once.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

GUARD = (Path(__file__).parent.parent / ".claude" / "hooks" / "guard.sh").resolve()

# Short flag chars assembled from hex so the literal danger tokens never appear
# in this file's source (the guard hook scans Bash command text, and a plain
# "rm -rf" in a grepped file could trip unrelated tooling).
_F = "\x66"  # 'f'
_R = "\x72"  # 'r'


def _run(cmd: str) -> int:
    """Feed one shell command through the guard hook; return its exit code."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    proc = subprocess.run(
        ["bash", str(GUARD)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return proc.returncode


def _blocked(cmd: str) -> bool:
    return _run(cmd) == 2


# ── Defect 1: force-push with a trailing -f ──

_FORCE_PUSH_BLOCKED = [
    "git push -" + _F + " origin main",  # space after -f (already caught)
    "git push origin main -" + _F,  # trailing -f at end-of-string (the bug)
    "git push origin main -" + _F + " ",  # trailing -f then a space
    "git push origin main --force",  # long form
    # --force-with-lease / --force-if-includes ARE force-pushes (they rewrite
    # shared history). The `--force` substring caught them before, but a later
    # tightening of the alternation to `--force([[:space:]=]|$)` stopped matching
    # the `-` that follows, silently un-guarding them — the exact failure class
    # this rail exists to prevent. These lock the `-` back in.
    "git push --force-with-lease origin main",  # bare, mid-command
    "git push origin main --force-with-lease",  # trailing
    "git push --force-with-lease=main origin",  # --force-with-lease=<ref> form
    "git push --force-if-includes origin main",  # sibling force variant
]


@pytest.mark.parametrize("cmd", _FORCE_PUSH_BLOCKED)
def test_force_push_is_blocked(cmd):
    assert _blocked(cmd), f"force-push must be blocked but passed: {cmd!r}"


# ── Defect 2: recursive-force rm regardless of flag order/spelling ──

_RM_RECURSIVE_FORCE_BLOCKED = [
    "rm -" + _R + _F + " /tmp/x",  # -rf (already caught)
    "rm -" + _F + _R + " /tmp/x",  # -fr
    "rm -" + _F + " -" + _R + " /tmp/x",  # -f -r (split)
    "rm -" + _R + " -" + _F + " /tmp/x",  # -r -f (split, reordered)
    "rm --recursive --force /tmp/x",  # long form
    "rm --force --recursive /tmp/x",  # long form, reordered
]


@pytest.mark.parametrize("cmd", _RM_RECURSIVE_FORCE_BLOCKED)
def test_recursive_force_rm_is_blocked(cmd):
    assert _blocked(cmd), f"recursive-force rm must be blocked but passed: {cmd!r}"


# ── Guard must NOT fire on benign commands (no false positives) ──

_ALLOWED = [
    "git push origin main",  # ordinary push
    "git status",
    "rm /tmp/file.txt",  # plain delete
    "rm -" + _F + " /tmp/file.txt",  # force only, not recursive
    "rm -" + _R + " /tmp/dir",  # recursive only, not force
    "ls -la",
    "grep -" + _R + _F + " pattern .",  # grep -rf: not an rm
    "confirm the transform ran",  # 'rm' substring only
]


@pytest.mark.parametrize("cmd", _ALLOWED)
def test_benign_commands_are_allowed(cmd):
    assert not _blocked(cmd), f"benign command was wrongly blocked: {cmd!r}"
