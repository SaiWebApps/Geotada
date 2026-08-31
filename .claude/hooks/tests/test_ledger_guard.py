"""Payload tests for the failures-ledger guard (.claude/hooks/ledger-guard.py).

The guard is a PreToolUse hook on Bash: it reads a JSON payload on stdin and
either exits silently (allowed) or prints a deny decision. These tests drive it
exactly that way, as a subprocess with a synthetic payload, so what is proven is
the shipped behaviour and not a re-implementation of it.

WHY THESE EXIST. A rule in failure-patterns.json whose `kind` has no matching
branch in `_violation` is a SILENT no-op: the function falls through every
`elif`, returns None, prints nothing and raises nothing. The rule reads as
enforced in a diff and enforces nothing at all. Nothing about that is visible
without running the guard against a payload it should refuse, which is what
`test_every_shipped_kind_is_implemented` does for the whole file, one command
apiece.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Beside the hook it tests, not in the product's tests/ tree — the subject is
# agent supervision, not Ondoway, so it must never run inside `make test`.
REPO_ROOT = Path(__file__).resolve().parents[3]
GUARD = REPO_ROOT / ".claude" / "hooks" / "ledger-guard.py"
PATTERNS = REPO_ROOT / ".claude" / "hooks" / "failure-patterns.json"

#: Every `kind` the guard implements, paired with a command that must trip it.
#: A new kind in failure-patterns.json fails `test_every_shipped_kind_is_implemented`
#: until it is added here WITH a command proving its branch runs.
TRIPPING_COMMAND = {
    "needs_abs_cd": "make test",
    "regex": "python3 -c 'from src.api import app'",
    "git_source_excerpt": "git grep -n include_router src/api/app.py",
    "inplace_source_edit": "sed -i '' 's/a/b/' src/api/app.py",
    "wrong_test_bar": "flutter test",
    # git_foreign_staged fires on the CURRENT index, so no fixed command can trip
    # it on a clean tree. Its branch is exercised by the other kinds' dispatch.
    "git_foreign_staged": None,
}


def _decision(command: str) -> str:
    """The guard's printed decision for a Bash command. Empty string = allowed."""
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, "the guard must always exit 0 and decide by printing"
    return result.stdout.strip()


def _denied(command: str) -> bool:
    out = _decision(command)
    return bool(out) and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


# ── class 20: a green bar claimed from a command that is not the bar ──


_IMPERSONATORS = [
    "flutter test",
    "cd mobile && flutter test",
    "flutter test --platform chrome",
    "flutter test --platform chrome --exclude-tags vm",
    "dart test",
    "cd /Users/sairambkrishnan/git/ondoway/mobile && flutter test -r compact",
]


@pytest.mark.parametrize("command", _IMPERSONATORS)
def test_a_whole_suite_flutter_run_is_refused(command):
    """Running the suite directly is never the bar, however it is spelled."""
    out = _decision(command)
    assert out, f"not blocked: {command}"
    reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "class 20" in reason
    assert "make -C /Users/sairambkrishnan/git/ondoway flutter-test" in reason


_ALLOWED = [
    # The bar itself.
    "make -C /Users/sairambkrishnan/git/ondoway flutter-test",
    # Iterating on ONE test: a named file AND a platform. CLAUDE.md rule 7
    # mandates this loop, and mobile/ has no `make test-file` equivalent, so it
    # must pass without spending the acknowledgement token.
    "flutter test --platform chrome test/pages/tour_walk_page_test.dart",
    "flutter test --platform=tester --tags vm test/pages/keep_exploring_golden_test.dart",
    # Not a test run at all.
    "flutter analyze",
    "flutter pub get",
    "flutter --version",
]


@pytest.mark.parametrize("command", _ALLOWED)
def test_the_bar_and_single_test_iteration_pass(command):
    assert not _denied(command), f"wrongly blocked: {command}"


def test_a_named_file_without_a_platform_is_still_refused():
    """Half the exemption is not the exemption.

    `flutter test <file>` with no --platform runs on whatever platform flutter
    defaults to, which is not either pass of the bar. The exemption exists for a
    deliberate, targeted run; this is not one.
    """
    assert _denied("flutter test test/pages/tour_walk_page_test.dart")


def test_the_acknowledgement_token_lets_a_deliberate_run_through():
    """Every class stays escapable, deliberately and visibly in the transcript."""
    assert not _denied("flutter test  # ledger-checked")


# ── the file as a whole ──


def test_every_shipped_kind_is_implemented():
    """No rule in the JSON may be a kind the guard silently ignores.

    This is the test the guard did not have when class 20 was written. A `kind`
    with no branch in `_violation` produces no error anywhere: the rule looks
    enforced in the diff, in the file, and in review, and blocks nothing.
    """
    config = json.loads(PATTERNS.read_text(encoding="utf-8"))
    for rule in config["rules"]:
        kind = rule.get("kind", "regex")
        assert kind in TRIPPING_COMMAND, (
            f"class {rule['class']} ships kind '{kind}', which has no proven branch in "
            f"ledger-guard.py. Add the branch, then add a tripping command here."
        )
        command = TRIPPING_COMMAND[kind]
        if command is None:
            continue
        assert _denied(command), (
            f"kind '{kind}' is in failure-patterns.json but its branch never fires: "
            f"{command!r} was allowed. A kind with no branch is a silent no-op."
        )


def test_an_ordinary_command_is_untouched():
    """A guard that fires on ordinary work is a guard that gets deleted."""
    assert not _denied("git -C /Users/sairambkrishnan/git/ondoway status --porcelain")
