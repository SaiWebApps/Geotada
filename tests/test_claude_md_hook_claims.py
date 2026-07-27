"""Guards against docs promising a safety mechanism that does not exist.

Root cause this locks down: CLAUDE.md's Judge Protocol asserted that
``.claude/hooks/guard.sh`` "mechanically BLOCKS" destructive commands and
logged every attempt to ``.claude/hooks/guard-log.txt`` for human audit. The
hook was deliberately removed in 643d0d9 (measured: 0/70 destructive commands
blocked, 16/20 harmless ones blocked) and nothing replaced it, but the claim
stayed. An agent or operator reading it believes a backstop exists when the
commands in fact run unimpeded — and a judge told to consult a nonexistent
audit log reads its absence as a clean record.

The rule these tests encode: a project-relative ``.claude/hooks/<file>`` path
named in the instruction docs must exist on disk AND be wired in
``.claude/settings.json``. Documentation of a guard IS the guard's interface;
if the file is gone, the prose must go with it.

User-level paths (``~/.claude/hooks/...``) are out of scope — they live on the
operator's machine, not in this repo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SETTINGS = _REPO_ROOT / ".claude" / "settings.json"

# Docs that instruct an agent and may name a hook as an active mechanism.
_DOC_PATHS = [_REPO_ROOT / "CLAUDE.md", *sorted((_REPO_ROOT / ".claude" / "agents").glob("*.md"))]

# Project-relative hook references only: a leading "~" or "$HOME" means the
# user's own config directory, which this repo does not own. In PROSE the path is
# written bare, so any "/" before it means a longer path we do not own either.
_HOOK_REF = re.compile(r"(?<![~\w/])\.claude/hooks/([\w.-]+)")

# The SAME path inside a settings.json command is legitimately preceded by "/",
# because the registration form is `"$CLAUDE_PROJECT_DIR"/.claude/hooks/<file>`.
# Reusing _HOOK_REF here (as this module did until 2026-07-26) made
# _wired_hook_files() return the EMPTY SET for every correctly-registered hook —
# measured against both real registrations, team-gate.sh and
# render-deploy-watch.sh. The guard was therefore inverted: it could never confirm
# a hook was wired, only ever accuse a correctly-wired one, and it did exactly that
# to team-gate.sh. Only the user-home form is excluded here.
_WIRED_HOOK_REF = re.compile(r"(?<!~/)\.claude/hooks/([\w.-]+)")


def _referenced_hooks(doc: Path) -> set[str]:
    return set(_HOOK_REF.findall(doc.read_text(encoding="utf-8")))


def _wired_hook_files() -> set[str]:
    """Every hook filename actually registered in .claude/settings.json."""
    if not _SETTINGS.exists():
        return set()
    settings = json.loads(_SETTINGS.read_text(encoding="utf-8"))
    commands = [
        hook.get("command", "")
        for matchers in settings.get("hooks", {}).values()
        for matcher in matchers
        for hook in matcher.get("hooks", [])
    ]
    return {name for cmd in commands for name in _WIRED_HOOK_REF.findall(cmd)}


@pytest.mark.parametrize("doc", _DOC_PATHS, ids=lambda p: p.name)
def test_documented_hooks_exist_on_disk(doc: Path) -> None:
    hooks_dir = _REPO_ROOT / ".claude" / "hooks"
    missing = sorted(name for name in _referenced_hooks(doc) if not (hooks_dir / name).exists())
    assert not missing, (
        f"{doc.relative_to(_REPO_ROOT)} references .claude/hooks/{missing} which do(es) not exist. "
        "Docs must not promise a mechanism the repo lacks: either restore the file or delete the "
        "claim (the regex command guard was removed in 643d0d9 as measured-ineffective)."
    )


@pytest.mark.parametrize("doc", _DOC_PATHS, ids=lambda p: p.name)
def test_documented_hooks_are_actually_wired(doc: Path) -> None:
    """A hook file that exists but is not registered still blocks nothing."""
    wired = _wired_hook_files()
    unwired = sorted(name for name in _referenced_hooks(doc) if name not in wired)
    assert not unwired, (
        f"{doc.relative_to(_REPO_ROOT)} references .claude/hooks/{unwired}, which is not "
        f"registered in {_SETTINGS.relative_to(_REPO_ROOT)}. An unwired script never runs."
    )


def test_judge_protocol_does_not_promise_a_command_guard() -> None:
    """The removed guard's specific promises must not reappear in CLAUDE.md.

    Naming the hook is fine (the doc now explains that it was removed); what is
    forbidden is asserting it currently blocks or logs anything.
    """
    text = (_REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    forbidden = [
        "mechanically BLOCKS",
        "guard-log.txt` for\n   human audit",
        "Never work around the guard",
    ]
    present = [phrase for phrase in forbidden if phrase in text]
    assert not present, (
        f"CLAUDE.md still claims an active command guard: {present}. No such guard exists — "
        "destructive-command safety rests entirely on the mandatory judge consult."
    )
