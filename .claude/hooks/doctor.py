#!/usr/bin/env python3
"""Can this machine satisfy the guards' remedies? Written down, once, per session.

WHY. On 2026-09-02 the advisor gate broke a co-founder's session for reasons
nobody could see from the owner's machine. Every guard in this directory prints
a remedy — "call advisor()", "run the shadow", "the judge will re-check" — and
each remedy has a prerequisite that is true on the machine the guard was written
on and unverified anywhere else:

  * the advisor tool exists only when the harness knows the configured
    `advisorModel` (a public alias, or any id with the experimental flag set);
  * truth-gate's judges need a `claude` CLI on the hook's PATH that can
    authenticate;
  * every hook needs a python3 of at least 3.9 (`from datetime import UTC` once
    broke ten fires silently on 3.9);
  * pre-shadow-check needs `node`; code-grounding-guard wants `codegraph`.

A guard that demands a remedy the machine cannot perform is a lockout, not a
guard. So this runs at SessionStart (and lazily from run.sh when the report is
missing), writes `.claude/state/doctor.json`, and every guard reads that file
before demanding anything. What it finds is also printed into the session's
starting context so the person can see it without opening a file.

NO NETWORK. A quota probe would cost a model call per session start and, on
this machine, the CLI cannot even authenticate from a hook subprocess (measured
2026-09-02: "OAuth session expired and could not be refreshed"). Availability is
learned from the advisor's own error records instead — see advisor-router.py.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from hookenv import DOCTOR_PATH, ROOT, effective_advisor_model, read_json, write_json

#: Model names the harness resolves without the experimental flag. Read off the
#: harness's own error text, 2026-09-02: "Switch to a public model alias (opus,
#: sonnet, fable) or set CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1."
PUBLIC_ALIASES = {"opus", "sonnet", "fable", "haiku"}
ADVISOR_FLAG = "CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL"
MIN_PYTHON = (3, 9)


def _run(argv, timeout=8):
    """stdin is /dev/null, and that is load-bearing: a hook's own stdin is the
    payload pipe, and a child `claude -p` that inherits it waits for EOF that
    never comes — measured 2026-09-02, the catalog probe hit its 20-second
    timeout and answered "unknown" while the same command finished in one
    second at a shell. truth-gate's judges carry the same fix."""
    env = {**os.environ, "ONDOWAY_DOCTOR_NO_PROBE": "1", "CLAUDE_NO_EXCUSES_JUDGE": "1"}
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    return done.returncode, (done.stdout + done.stderr).strip()


def flag_set() -> bool:
    if os.environ.get(ADVISOR_FLAG) == "1":
        return True
    for name in ("settings.local.json", "settings.json"):
        env = read_json(ROOT / ".claude" / name).get("env") or {}
        if isinstance(env, dict) and str(env.get(ADVISOR_FLAG, "")) == "1":
            return True
    return False


#: The phrase the harness prints when a model name is not in its catalog. Read
#: off the 2.1.259 binary's own answer to `claude -p ok --model
#: claude-nonexistent-9`, 2026-09-02: it arrives in three seconds, BEFORE any
#: authentication is attempted, so it can be asked on a machine whose hook
#: subprocesses cannot log in. This is the harness answering, not a list.
CATALOG_REFUSAL = "model catalog"
PROBE_TIMEOUT = 20

#: One round trip per (cli, model) per process. The probe below is the only
#: place this file spends a model call, and two callers want its answer.
_PROBE_CACHE: dict = {}


def probe(claude: str | None, model: str | None) -> dict:
    """Ask the CLI to answer, once, and report everything that call revealed.

    Returns {"ran", "exit", "answered", "known", "detail"}. `answered` is the
    field this file used to lack: the round trip already happened, but only its
    OUTPUT was read, so a run that exited non-zero without the catalog phrase
    was reported as a working tool. A tool that starts is not a tool that can
    answer, and every judge in this directory depends on the difference.
    """
    key = (claude, model)
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]

    if not claude or not model:
        result = {"ran": False, "exit": None, "answered": False, "known": "unknown",
                  "detail": "no `claude` CLI to ask, or no model configured"}
        _PROBE_CACHE[key] = result
        return result

    # `--setting-sources user`, and the two env marks, are what stop the probe
    # from RECURSING: a child `claude` that loads this project's settings runs
    # its SessionStart hooks, which run this doctor, which spawns another
    # child. Measured 2026-09-02: every probe hit its 20-second cap until the
    # project settings were kept out of the child.
    code, out = _run(
        [claude, "-p", "Reply with exactly the word OK.", "--model", model,
         "--tools", "", "--setting-sources", "user"],
        timeout=PROBE_TIMEOUT,
    )
    first = out.splitlines()[0][:200] if out else ""

    if code is None:
        result = {"ran": False, "exit": None, "answered": False, "known": "unknown",
                  "detail": f"the probe could not run: {out[:200]}"}
    elif CATALOG_REFUSAL in out:
        result = {"ran": True, "exit": code, "answered": False, "known": "no",
                  "detail": f"the harness does not know `{model}`: {first}"}
    elif code == 0:
        result = {"ran": True, "exit": 0, "answered": True, "known": "yes",
                  "detail": f"`{model}` answered"}
    else:
        # The model name was accepted — the refusal came later, from auth or
        # quota. That is exactly the state the old code called "yes".
        result = {"ran": True, "exit": code, "answered": False, "known": "yes",
                  "detail": f"`{model}` was accepted but the call exited {code}: {first}"}

    _PROBE_CACHE[key] = result
    return result


def catalog_probe(claude: str | None, model: str | None) -> tuple[str, str]:
    """("yes"|"no"|"unknown", why): does THIS harness know `model`?"""
    answer = probe(claude, model)
    return answer["known"], answer["detail"]


def advisor_support(model: str | None, flag: bool, claude: str | None = None) -> tuple[str, str]:
    """("yes"|"no"|"unknown", why).

    The harness is asked first (catalog_probe). Only when it cannot be asked
    does this fall back to reasoning from the configuration: a public alias is
    a yes, a full id with the flag is a yes, a full id without it is a no.
    """
    if not model:
        return "unknown", "no advisorModel is configured in settings.json or settings.local.json"
    if os.environ.get("ONDOWAY_DOCTOR_NO_PROBE") != "1":
        verdict, why = catalog_probe(claude, model)
        if verdict != "unknown":
            return verdict, why
    if model in PUBLIC_ALIASES:
        return "yes", f"advisorModel `{model}` is a public alias every harness knows"
    if flag:
        return "yes", f"advisorModel `{model}` is a full id and {ADVISOR_FLAG}=1 is set"
    return "no", (
        f"advisorModel `{model}` is a full model id and {ADVISOR_FLAG} is not set, so a "
        "harness whose catalog lacks it disables the advisor tool entirely"
    )


def examine() -> dict:
    report: dict = {"written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "root": str(ROOT), "problems": []}
    report["python"] = {"executable": sys.executable,
                        "version": ".".join(str(part) for part in sys.version_info[:3]),
                        "ok": sys.version_info >= MIN_PYTHON}
    if not report["python"]["ok"]:
        report["problems"].append(f"python {report['python']['version']} is below 3.9")

    report["git_root_ok"] = (ROOT / ".git").exists()
    if not report["git_root_ok"]:
        report["problems"].append(f"{ROOT} does not look like a git checkout")

    model = effective_advisor_model()
    flag = flag_set()

    claude = shutil.which("claude")
    version = None
    if claude:
        code, out = _run([claude, "--version"])
        version = out.split("\n")[0] if code == 0 else None
    installed = bool(claude and version)

    # Does it ANSWER, not just start. A login that has expired leaves a binary
    # that prints its version and refuses every call, and every judge in this
    # directory then fails with an error nobody can read.
    answered = None
    detail = "not asked: the CLI is not installed"
    if installed and os.environ.get("ONDOWAY_DOCTOR_NO_PROBE") != "1":
        attempt = probe(claude, model)
        detail = attempt["detail"]
        if attempt["ran"]:
            answered = attempt["answered"]

    report["claude_cli"] = {"path": claude, "version": version, "installed": installed,
                            "answers": answered, "why": detail,
                            # `ok` is what every judge-running hook already reads.
                            # A CLI that cannot answer is not ok, so those hooks
                            # disarm loudly instead of paying a timeout to find out.
                            # An unasked probe leaves `ok` on the version check:
                            # not knowing is not evidence of failure.
                            "ok": installed and answered is not False}
    if not installed:
        report["problems"].append(
            "no working `claude` CLI on the hook's PATH: truth-gate's judges cannot run"
        )
    elif answered is False:
        report["problems"].append(
            f"the `claude` CLI cannot answer, so every judge and verifier is dead: {detail}. "
            "Run `claude login` in a terminal, then start a new session."
        )

    for binary in ("node", "codegraph", "git", "uv"):
        report[f"has_{binary}"] = shutil.which(binary) is not None
    if not report["has_git"]:
        report["problems"].append("`git` is not on PATH")
    support, why = advisor_support(model, flag, claude if report["claude_cli"]["ok"] else None)
    report["advisor"] = {"model": model, "flag_set": flag, "supported": support, "why": why}
    if support == "no":
        report["problems"].append("advisor tool: " + why)
    # Can the ROUTER's preferred model be named on this harness at all? Asked
    # once here so advisor-router.py can fall to opus before a consult fails.
    fable_support = "unknown"
    if model == "fable" and support != "unknown":
        fable_support = support  # the probe above already asked about fable
    elif report["claude_cli"]["ok"] and os.environ.get("ONDOWAY_DOCTOR_NO_PROBE") != "1":
        fable_support = catalog_probe(claude, "fable")[0]
    report["fable_in_catalog"] = fable_support

    report["project_dir_env"] = os.environ.get("CLAUDE_PROJECT_DIR") or None
    return report


def summary(report: dict) -> str:
    cli = report["claude_cli"]
    if not cli["installed"]:
        cli_word = "MISSING"
    elif cli["answers"] is False:
        cli_word = "CANNOT ANSWER"
    elif cli["answers"] is True:
        cli_word = "answers"
    else:
        cli_word = "installed, not asked"
    lines = [f"Hook doctor ({report['written_at']}): root {report['root']}, "
             f"python {report['python']['version']}, "
             f"claude CLI {cli_word}, "
             f"advisor {report['advisor']['supported']} ({report['advisor']['model']})."]
    for problem in report["problems"]:
        lines.append(f"  PROBLEM: {problem}")
    return "\n".join(lines)


def main() -> None:
    # Inside a judge or probe child (truth-gate's `claude -p`, this file's own
    # catalog probe) nothing here may run: writing the report from a child's
    # environment would be wrong, and probing again would recurse.
    if os.environ.get("CLAUDE_NO_EXCUSES_JUDGE"):
        return
    quiet = "--quiet" in sys.argv
    event = ""
    if not sys.stdin.isatty() and "--quiet" not in sys.argv:
        try:
            payload = json.load(sys.stdin)
            event = payload.get("hook_event_name") or "" if isinstance(payload, dict) else ""
        except Exception:
            event = ""
    report = examine()
    write_json(DOCTOR_PATH, report)
    if quiet:
        return
    text = summary(report)
    if event == "SessionStart":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": text}}))
    else:
        print(text)


if __name__ == "__main__":
    main()
