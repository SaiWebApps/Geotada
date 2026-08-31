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
    "blanket_conflict_resolution": "git checkout --ours -- a.dart b.dart c.dart d.dart",
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


# ── class 23: a whole merge settled without reading a single conflict ──


def test_the_real_19_file_sweep_is_refused():
    """The exact command that settled this repository's merge, unread.

    All 19 conflicts went to one side in one call. It happened to be the right
    side — but nobody knew that when it ran, and on the one file where the two
    versions genuinely differed the owner rejected the result outright.
    """
    command = (
        "git checkout --ours -- mobile/ios/Podfile.lock "
        "mobile/ios/Runner.xcodeproj/project.pbxproj mobile/lib/main.dart "
        "mobile/lib/pages/lens_selection_page.dart mobile/lib/pages/login_page.dart "
        "mobile/lib/pages/tour_walk_page.dart mobile/lib/pages/trip_itinerary_page.dart "
        "mobile/lib/router.dart mobile/lib/services/audio_service.dart "
        "mobile/lib/services/providers.dart "
        "mobile/lib/services/tour_playback_service.dart mobile/pubspec.yaml "
        "mobile/test/fixtures/paris_golden_trip.json "
        "mobile/test/pages/home_page_test.dart "
        "mobile/test/pages/lens_selection_page_test.dart "
        "mobile/test/pages/trip_itinerary_page_test.dart "
        "mobile/test/services/audio_service_native_routing_test.dart "
        "mobile/test/services/mocks/mock_audio_service.dart scripts/flutter_test.sh"
    )
    out = _decision(command)
    assert out, "the 19-file sweep must not pass"
    reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "class 23" in reason
    assert "19 files at once" in reason


def test_a_directory_sweep_is_refused_at_any_size():
    """One argument, every conflict under it — a sweep however few words it takes."""
    assert _denied("git checkout --theirs -- mobile/lib/")
    assert _denied("git checkout --ours -- .")


@pytest.mark.parametrize(
    "command",
    [
        # One file is a decision you can only type after making it.
        "git checkout --ours -- mobile/lib/main.dart",
        "git checkout --theirs -- mobile/lib/router.dart",
        # Up to three still reads as three decisions typed together.
        "git checkout --ours -- a.dart b.dart c.dart",
    ],
)
def test_resolving_a_few_named_files_is_a_considered_act(command):
    assert not _denied(command), f"wrongly blocked: {command}"


@pytest.mark.parametrize(
    "command",
    [
        # No side flag: this is restoring files, not settling a conflict.
        "git checkout -- a.dart b.dart c.dart d.dart e.dart",
        "git checkout main -- mobile/lib/",
        "git checkout -b some-branch",
    ],
)
def test_an_ordinary_checkout_is_untouched(command):
    assert not _denied(command), f"wrongly blocked: {command}"


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


# ── the hole: a heredoc or a bare newline hid what _inplace_targets should see ──


def test_a_sed_dash_i_inside_a_heredoc_body_is_not_a_real_inplace_edit():
    """DATA that mentions `sed -i` is still data, never a command to guard.

    Before this fix, _segments never ended a segment at a bare newline, so
    the heredoc opener and its body merged into one blob split only at the
    `;` already sitting in the body text — which put `sed` at the START of
    its own spurious segment. A commit whose message documents a cleanup step
    would have been denied for an edit it never made.
    """
    command = (
        "git -C /Users/sairambkrishnan/git/ondoway commit -q -F - <<'MSG'\n"
        "docs: mention cleanup; sed -i '' 's/a/b/' src/api/app.py\n"
        "MSG\n"
    )
    assert not _denied(command)


def test_a_real_sed_dash_i_on_its_own_line_after_another_command_is_still_caught():
    """A bare newline must not hide a real in-place edit the way it used to.

    Before this fix, this two-line command read as ONE segment with `git` at
    argv[0] — `_inplace_targets` only ever looks at a segment's argv[0], so
    `sed` was never examined at all.
    """
    command = (
        "git -C /Users/sairambkrishnan/git/ondoway add mobile/lib/main.dart\n"
        "sed -i '' 's/a/b/' src/api/app.py\n"
    )
    out = _decision(command)
    assert out, "a real in-place edit on a tracked file must still be caught"
    reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "class 14" in reason
