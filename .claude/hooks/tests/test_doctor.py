"""The doctor must tell a tool that STARTS from a tool that ANSWERS.

Every judge, verifier and advisor in this directory runs by spawning the CLI.
When that spawn fails, the guards that depend on it print an error with no
reason in it, and the session stalls with nothing to act on. The doctor is the
one place that difference gets established, so it is the one place it is tested.

Each case drives the real `doctor.py` as a subprocess against a stand-in CLI on
PATH, with a private state directory, so nothing here touches the live report.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1]
DOCTOR = HOOKS / "doctor.py"

#: What the CLI prints when a login has expired. Verbatim from a real run.
AUTH_FAILURE = "Failed to authenticate: OAuth session expired and could not be refreshed"

#: A stand-in CLI. It always reports a version, so the old version-only check
#: passes; whether it can ANSWER is decided by the exit code below.
STANDIN = """#!/bin/sh
for a in "$@"; do [ "$a" = "--version" ] && { echo "2.1.259 (Claude Code)"; exit 0; }; done
%s
"""

ANSWERS = 'echo OK; exit 0'
REFUSES = 'echo "%s" >&2; exit 1' % AUTH_FAILURE


def run_doctor(tmp_path, body=None):
    """Run the doctor against a stand-in CLI. `body` None means no CLI at all."""
    binaries = tmp_path / "bin"
    binaries.mkdir(parents=True)
    if body is not None:
        cli = binaries / "claude"
        cli.write_text(STANDIN % body)
        cli.chmod(0o755)

    # A PATH with the stand-in FIRST, and the real tool directories after it, so
    # `git`, `node` and `uv` still resolve and only the CLI is substituted.
    real = [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    if body is None:
        # Drop any directory that really holds a `claude`, so "missing" means it.
        real = [part for part in real if not (Path(part) / "claude").exists()]

    state = tmp_path / "state"
    env = {**os.environ,
           "PATH": os.pathsep.join([str(binaries), *real]),
           "ONDOWAY_STATE_DIR": str(state)}

    done = subprocess.run([sys.executable, str(DOCTOR)], capture_output=True, text=True,
                          timeout=120, stdin=subprocess.DEVNULL, env=env, cwd=str(HOOKS))
    assert done.returncode == 0, done.stderr
    report = json.loads((state / "doctor.json").read_text())
    return report, done.stdout


def test_a_cli_that_answers_is_recorded_as_working(tmp_path):
    report, printed = run_doctor(tmp_path, ANSWERS)
    cli = report["claude_cli"]
    assert cli["installed"] is True
    assert cli["answers"] is True
    assert cli["ok"] is True
    assert "answers" in printed
    assert not [p for p in report["problems"] if "claude" in p]


def test_a_cli_that_starts_but_cannot_authenticate_is_not_ok(tmp_path):
    """The case that cost a session: a version check passes, every real call
    fails, and `ok` was true anyway — so the judges ran and died with an empty
    reason instead of the doctor saying what was wrong."""
    report, printed = run_doctor(tmp_path, REFUSES)
    cli = report["claude_cli"]
    assert cli["installed"] is True, "the stand-in does report a version"
    assert cli["answers"] is False
    assert cli["ok"] is False, "a CLI that cannot answer must not read as ok"
    assert AUTH_FAILURE in cli["why"]
    assert "CANNOT ANSWER" in printed


def test_the_failure_names_the_command_that_fixes_it(tmp_path):
    """A guard that reports a problem without its remedy is a guard that stalls
    the session. The remedy is a login, which only a person can perform."""
    report, _ = run_doctor(tmp_path, REFUSES)
    problems = [p for p in report["problems"] if "cannot answer" in p]
    assert len(problems) == 1, report["problems"]
    assert "claude login" in problems[0]


def test_ok_is_what_the_judge_running_hooks_already_read(tmp_path):
    """`truth-gate.py` disarms on `claude_cli.ok` being false. This asserts the
    field it reads still exists and now carries the answer-ability, so the fix
    reaches that hook with no edit to it."""
    working, _ = run_doctor(tmp_path / "a", ANSWERS)
    broken, _ = run_doctor(tmp_path / "b", REFUSES)
    assert working["claude_cli"]["ok"] is True
    assert broken["claude_cli"]["ok"] is False


def test_no_cli_at_all_is_reported_as_missing_not_as_silent(tmp_path):
    report, _ = run_doctor(tmp_path, None)
    cli = report["claude_cli"]
    assert cli["installed"] is False
    assert cli["path"] is None
    assert [p for p in report["problems"] if "claude" in p]
