#!/usr/bin/env python3
"""Which model answers the advisor: Fable when it can, Opus when it cannot.

OWNER REQUIREMENT, 2026-09-02: Fable quota available -> Fable; exhausted or
unavailable -> Opus, automatically; a failed quota check gets a DEFINED
behaviour, never a silently skipped consult; and the working agent does not
get to make this choice.

WHAT THE HARNESS OFFERS, measured against the 2.1.259 binary rather than
assumed: `advisorModel` is a settings key; the harness subscribes to settings
changes and re-derives the advisor model when the key changes, so a write to
`.claude/settings.local.json` takes effect in the running session. There is no
quota API. What there IS, in the transcript, is the result of every consult:
`advisor_tool_result` on success, `advisor_tool_result_error` on failure.

THE POLICY, exactly:

  1. Default is `fable`.
  2. A consult that comes back as an error WHILE routed to fable marks fable
     failed at that moment, and the router switches the setting to `opus`.
  3. The switch holds for COOLDOWN_SECONDS (six hours), then fable is tried
     again at the next decision point. A second failure re-arms the cooldown.
  4. Quota state that cannot be determined (no error seen yet, no probe run)
     counts as AVAILABLE: the cost of being wrong is one failed consult, which
     the advisor guard treats as a consult performed and which flips the route
     on the spot. Nothing is skipped, and the flip is visible as a system
     message.
  5. A consult that comes back as an error while ALREADY routed to opus is
     recorded and reported, and the route stays on opus — there is nothing
     cheaper to fall to, and the guard still demands the consult.

WHO CALLS THIS. SessionStart, so a fresh session starts on the right model;
and advisor-consult-guard.py, the moment it reads an advisor error in the
transcript, so the switch happens mid-session without anyone's cooperation.
`settings.local.json` is machine-local and gitignored, so a route on one
machine never leaks to another.

`--force fable|opus` and `--status` exist for a person at a keyboard.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from hookenv import LOCAL_SETTINGS_PATH, ROUTER_PATH, doctor_report, read_json, write_json

PREFERRED = "fable"
FALLBACK = "opus"
COOLDOWN_SECONDS = 6 * 60 * 60
LOCAL_SETTINGS = LOCAL_SETTINGS_PATH


def decide(state: dict, now: float | None = None) -> tuple[str, str]:
    """(model, reason) from the recorded history alone. Pure."""
    now = time.time() if now is None else now
    forced = state.get("forced")
    if forced in (PREFERRED, FALLBACK):
        return forced, f"forced to {forced} by hand (`advisor-router.py --force`)"
    if state.get("fable_in_catalog") == "no":
        return FALLBACK, "this harness does not know the model `fable` (doctor catalog probe)"
    failed_at = state.get("fable_failed_at")
    if isinstance(failed_at, (int, float)) and now - failed_at < COOLDOWN_SECONDS:
        remaining = int((COOLDOWN_SECONDS - (now - failed_at)) / 60)
        return FALLBACK, (
            f"fable consult failed at {time.strftime('%H:%M:%SZ', time.gmtime(failed_at))}; "
            f"opus for another {remaining} minutes"
        )
    return PREFERRED, "fable is the preferred advisor and no recent failure is recorded"


def apply(model: str) -> bool:
    """Write `advisorModel` into settings.local.json, keeping every other key."""
    settings = read_json(LOCAL_SETTINGS)
    if settings.get("advisorModel") == model:
        return True
    settings["advisorModel"] = model
    return write_json(LOCAL_SETTINGS, settings)


def record_failure(model_in_use: str | None, detail: str = "") -> tuple[str, str]:
    """An advisor consult errored. Returns the (model, reason) now in force."""
    state = read_json(ROUTER_PATH)
    now = time.time()
    if (model_in_use or PREFERRED) == PREFERRED:
        state["fable_failed_at"] = now
    state["last_error"] = {"model": model_in_use, "at": now, "detail": detail[:500]}
    model, reason = decide(state, now)
    state["model"], state["reason"] = model, reason
    write_json(ROUTER_PATH, state)
    apply(model)
    return model, reason


def route(now: float | None = None) -> tuple[str, str]:
    state = read_json(ROUTER_PATH)
    state["fable_in_catalog"] = doctor_report().get("fable_in_catalog", "unknown")
    model, reason = decide(state, now)
    state["model"], state["reason"], state["decided_at"] = model, reason, time.time()
    write_json(ROUTER_PATH, state)
    apply(model)
    return model, reason


def main() -> None:
    import os

    if os.environ.get("CLAUDE_NO_EXCUSES_JUDGE"):
        return  # a judge/probe child must not re-route the parent's advisor
    args = sys.argv[1:]
    if args[:1] == ["--force"] and len(args) > 1:
        state = read_json(ROUTER_PATH)
        state["forced"] = None if args[1] == "auto" else args[1]
        write_json(ROUTER_PATH, state)
        print(json.dumps({"forced": state["forced"]}))
        return
    if args[:1] == ["--status"]:
        print(json.dumps(read_json(ROUTER_PATH), indent=2))
        return
    event = ""
    if not sys.stdin.isatty():
        try:
            payload = json.load(sys.stdin)
            event = payload.get("hook_event_name") or "" if isinstance(payload, dict) else ""
        except Exception:
            event = ""
    model, reason = route()
    text = f"Advisor routed to `{model}`: {reason}."
    if event == "SessionStart":
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": text}}))
    else:
        print(text)


if __name__ == "__main__":
    main()
