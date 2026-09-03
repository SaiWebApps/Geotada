#!/usr/bin/env python3
"""What every hook needs to know about the machine it is running on.

ONE PLACE, because the hooks used to answer these questions eleven different
ways and each answer carried a machine-specific assumption:

  * `python3 "$CLAUDE_PROJECT_DIR"/.claude/hooks/x.py` in settings.json — on a
    harness that does not export CLAUDE_PROJECT_DIR the command becomes
    `python3 /.claude/hooks/x.py`, python exits 2, and for a PreToolUse hook
    exit 2 is BLOCK. Every tool refused, with a traceback for a reason.
    Measured 2026-09-02 by running one hook with the variable unset.
  * `"repo_root": "/Users/sairambkrishnan/git/ondoway"` in
    failure-patterns.json — on any other machine that directory does not exist,
    `git ls-files` there raises, three ledger classes fail open silently, and
    the class-1 refusal tells the reader to run `make -C /Users/sairambkrishnan/…`.
  * Six state files under `/tmp/ondoway-*.json`, shared by every session and
    every user on the machine.

So: the repository root is derived from THIS FILE'S OWN LOCATION and nothing
else — `.claude/hooks/hookenv.py` is always exactly two directories below the
root, on every machine, in every checkout. State lives under
`.claude/state/`, which `.gitignore` already excludes under `.claude/*`, keyed
by session id so two sessions never read each other's tallies.

`doctor.py` writes `.claude/state/doctor.json`; `doctor_report()` here is how
every guard reads it. A guard whose remedy does not exist on this machine
(no advisor tool, no `claude` CLI) reads that fact from the report and says so
loudly instead of refusing forever — see advisor-consult-guard.py and
truth-gate.py for the two places that matters.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

#: `.claude/hooks/hookenv.py` -> `.claude/hooks` -> `.claude` -> the root.
ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = Path(__file__).resolve().parent
#: Overridable so the payload tests get a private state directory, a private
#: doctor report and a private settings.local.json instead of the live ones —
#: the same reasoning every sibling guard's STATE_PATH override carries.
STATE_DIR = Path(os.environ.get("ONDOWAY_STATE_DIR") or (ROOT / ".claude" / "state"))
DOCTOR_PATH = STATE_DIR / "doctor.json"
ROUTER_PATH = STATE_DIR / "advisor-router.json"
LOCAL_SETTINGS_PATH = Path(
    os.environ.get("ONDOWAY_LOCAL_SETTINGS") or (ROOT / ".claude" / "settings.local.json")
)
PROJECT_SETTINGS_PATH = ROOT / ".claude" / "settings.json"


def repo_root() -> Path:
    """The checkout this hook belongs to. Never the payload's cwd, never an
    environment variable: both are absent or wrong on some machine."""
    return ROOT


def state_dir() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR


def session_state_path(name: str, session_id: str | None) -> Path:
    """`.claude/state/sessions/<session>/<name>.json`, created on demand.

    Keyed by session so a parallel session cannot reset this one's count — the
    defect that made the old shared `/tmp` ceilings non-deterministic.
    """
    safe = "".join(
        char if char.isalnum() or char in "-_" else "-" for char in (session_id or "session")
    )
    folder = state_dir() / "sessions" / (safe or "session")
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{name}.json"


def read_json(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: dict) -> bool:
    """Atomic enough: write beside, then rename. Never raises."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def doctor_report() -> dict:
    """What doctor.py last found about this machine, or {} if it never ran."""
    return read_json(DOCTOR_PATH)


def router_state() -> dict:
    return read_json(ROUTER_PATH)


def load_sibling(filename: str, module_name: str | None = None):
    """Import a sibling hook by path (their names carry hyphens).

    Returns the module, or None on ANY failure — including SystemExit, because
    importing a module runs its top level. A guard that dies importing a
    sibling is a guard that takes the session with it.
    """
    source = HOOKS_DIR / filename
    try:
        spec = importlib.util.spec_from_file_location(
            module_name or filename.replace("-", "_").replace(".py", ""), source
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except BaseException:
        return None


def effective_advisor_model() -> str | None:
    """The `advisorModel` the harness will use: local settings win over project."""
    for path in (LOCAL_SETTINGS_PATH, PROJECT_SETTINGS_PATH):
        data = read_json(path)
        value = data.get("advisorModel")
        if isinstance(value, str) and value:
            return value
    return None


def is_subagent(payload: dict) -> bool:
    """A spawned agent's call. Measured 2026-09-01: its payload carries
    `agent_id` and `agent_type`; the main session's carries neither."""
    return bool(payload.get("agent_id") or payload.get("agent_type"))


def print_system_message(text: str) -> None:
    print(json.dumps({"systemMessage": text}))


if __name__ == "__main__":
    print(json.dumps({"root": str(ROOT), "state": str(STATE_DIR),
                      "advisorModel": effective_advisor_model(),
                      "python": sys.version.split()[0]}))
