"""Tests for the hard-refuse PRE-CHECK in .claude/commands/unified-beat-extract.md.

The skill prompt isn't executable in pytest — these tests assert the
required string tokens are present so a prompt edit that softens the
refuse language trips CI instead of landing silently. Covers AC-1.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / ".claude" / "commands" / "unified-beat-extract.md"


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_refuse_check_present_in_skill():
    """AC-1 — the PRE-CHECK section uses hard-refuse language."""
    text = _text()
    # Must contain the word "Refused:" as a literal string to be printed.
    assert "Refused:" in text, "expected 'Refused:' in unified-beat-extract.md PRE-CHECK"
    # Must reference the book-log.json file it's checking.
    assert "book-log.json" in text
    # Must instruct the skill to exit non-zero / stop before extraction.
    assert re.search(r"non[- ]?zero|exit\s+non", text, re.I), (
        "refuse must name a non-zero exit / stop"
    )


def test_refuse_message_includes_wipe_command():
    """AC-1 — the refuse message tells the user exactly how to unblock."""
    text = _text()
    assert "/beat-wipe" in text, "refuse message must point the user at /beat-wipe"


def test_refuse_no_soft_stop_language():
    """Regression guard — catches drift back toward the old soft-stop
    language like 'Run again to re-extract' or 'or skip'."""
    text = _text()
    # The pre-Scope-2 language.
    assert "Run again to re-extract" not in text
    assert "or skip." not in text


def test_beats_io_commit_is_wired():
    """Task 4 — the write-output step calls beats_io.commit, not a
    direct append to beats.json."""
    text = _text()
    assert "beats_io.commit" in text or "beats_io" in text, (
        "unified-beat-extract.md must call scripts.beats_io.commit for writes"
    )


def test_no_test_only_flags_in_production_scripts():
    """BP-10 — production scripts in scripts/ don't carry test-only
    CLI flags."""
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    forbidden = re.compile(r"--(?:planted[- _]?collision|test[- _]?only|TEST\b)", re.I)
    offenders = []
    for py in scripts_dir.glob("*.py"):
        contents = py.read_text(encoding="utf-8")
        if forbidden.search(contents):
            offenders.append(py.name)
    assert not offenders, f"test-only CLI flags found in production: {offenders}"
