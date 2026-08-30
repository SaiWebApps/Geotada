"""Payload tests for .claude/hooks/advisor-consult-guard.py.

The guard has two arms. The Stop arm refuses to let a turn END without an
advisor consult in it. The PreToolUse arm refuses to let a tool RUN until the
turn contains a consult and a printed plan, and refuses a second destructive
command on a single piece of advice.

WHY THE SECOND ARM IS THE ONE THAT MATTERS. Gating only the reply gates only
what is said. A turn that consulted once at the start went on to delete 544
files, and one of them was a file this very suite reads — lost to a
case-sensitivity bug in the delete rule. The Stop arm was satisfied throughout,
because a consult had happened; it simply had not happened anywhere near the act.

EVERY RECORD SHAPE HERE WAS READ OFF A REAL TRANSCRIPT, never invented. That is
not a stylistic preference. An earlier version of this guard looked for
``{"type": "tool_use", "name": "advisor"}`` — the shape every OTHER tool uses.
The advisor is a server-side tool and records as ``server_tool_use`` with a
separate ``advisor_tool_result`` block, so the check could never match: the guard
blocked every reply, consult or not, and its thirteen payload tests all passed
because they were built from the same assumed shape. A fixture invented alongside
the code it tests proves only that the two agree with each other.

The shapes below were measured directly:

    human      {"type": "user", "origin": {"kind": "human"},
                "message": {"content": "<a string, not a list>"}}
    text       {"type": "assistant",
                "message": {"content": [{"type": "text", "text": "..."}]}}
    advisor    {"type": "assistant", "message": {"content": [
                   {"type": "server_tool_use", "id": "...", "name": "advisor",
                    "input": {}}]}}
    result     {"type": "assistant", "message": {"content": [
                   {"type": "advisor_tool_result", "tool_use_id": "...",
                    "content": {}}]}}
    tool call  {"type": "assistant", "message": {"content": [
                   {"type": "tool_use", "name": "Bash", "input": {...}}]}}

Text and tool calls arrive as SEPARATE assistant records, text first — which is
what makes "was the plan printed before this tool ran" answerable at all.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / ".claude" / "hooks" / "advisor-consult-guard.py"

#: Long enough to clear the guard's own floor for a printed plan. The guard asks
#: for length rather than wording, so this is deliberately dull prose.
A_PRINTED_PLAN = (
    "1. Read the file in full before editing it. "
    "2. Write the failing test first and watch it fail. "
    "3. Make the change. "
    "4. Confirm that test passes. "
    "5. Run the linter. "
    "6. Run the whole suite once at the end and read what it prints. "
    "7. Consult again before anything that cannot be undone."
)


# ---------------------------------------------------------------- record shapes


def human(text="do the thing"):
    return {"type": "user", "origin": {"kind": "human"}, "message": {"content": text}}


def assistant_text(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def advisor_call():
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "server_tool_use", "id": "srvtoolu_x", "name": "advisor", "input": {}}
            ]
        },
    }


def advisor_result():
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "advisor_tool_result", "tool_use_id": "srvtoolu_x", "content": {}}
            ]
        },
    }


def bash_call(command):
    return {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": command}}]
        },
    }


# ---------------------------------------------------------------------- harness


def decide(tmp_path, records, *, tool="Bash", command="ls -la", event="PreToolUse"):
    """Run the guard over `records` and return its decision ({} means allowed)."""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    payload = {
        "hook_event_name": event,
        "tool_name": tool,
        "tool_input": {"command": command},
        "transcript_path": str(transcript),
        "session_id": "test-session",
    }
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else {}


def denied(decision):
    return decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def reason(decision):
    out = decision.get("hookSpecificOutput", {})
    return out.get("permissionDecisionReason") or decision.get("reason", "")


# ------------------------------------------------- arm: no action before a consult


def test_a_tool_call_with_no_consult_in_the_turn_is_refused(tmp_path):
    decision = decide(tmp_path, [human()])
    assert denied(decision)
    assert "NO CONSULT, NO ACTION." in reason(decision)


def test_a_consult_in_an_earlier_turn_does_not_pay_for_this_one(tmp_path):
    """New words from the owner are a new thing to be advised about.

    Without this, one consult at the start of a session would license every
    action taken in it, which is the failure the arm exists to remove.
    """
    records = [
        human("first ask"),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        human("second ask"),
    ]
    assert denied(decide(tmp_path, records))


def test_a_consult_with_the_plan_printed_lets_the_tool_run(tmp_path):
    records = [human(), advisor_call(), advisor_result(), assistant_text(A_PRINTED_PLAN)]
    assert not denied(decide(tmp_path, records))


def test_the_advisor_itself_is_never_blocked(tmp_path):
    """The one action that satisfies this guard must always be available.

    Blocking it would make the guard unsatisfiable, and an unsatisfiable guard
    is why every other guard here carries an escape hatch. This one needs none
    precisely because its remedy is exempt.
    """
    assert not denied(decide(tmp_path, [human()], tool="advisor", command=""))


# ------------------------------------------------------- arm: the plan is printed


def test_a_consult_whose_advice_was_never_written_down_is_refused(tmp_path):
    """A consult nobody can see is indistinguishable from one that was ignored."""
    records = [human(), advisor_call(), advisor_result()]
    decision = decide(tmp_path, records)
    assert denied(decision)
    assert "THE PLAN WAS NOT PRINTED." in reason(decision)


def test_a_bare_acknowledgement_is_not_a_printed_plan(tmp_path):
    records = [human(), advisor_call(), advisor_result(), assistant_text("Consulting now.")]
    decision = decide(tmp_path, records)
    assert denied(decision)
    assert "THE PLAN WAS NOT PRINTED." in reason(decision)


def test_text_printed_before_the_consult_does_not_count(tmp_path):
    """Otherwise any long preamble would pay for a consult that came after it."""
    records = [human(), assistant_text(A_PRINTED_PLAN), advisor_call(), advisor_result()]
    assert denied(decide(tmp_path, records))


# ------------------------------------------ arm: one consult per destructive act


def test_a_second_destructive_command_on_one_consult_is_refused(tmp_path):
    """The exact shape of the sweep that deleted a file the suite reads."""
    records = [
        human(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        bash_call("git rm -r --cached tests/reports"),
    ]
    decision = decide(tmp_path, records, command="rm -rf specs/2026-08-06-tour-time-model")
    assert denied(decision)
    assert "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT." in reason(decision)


def test_the_first_destructive_command_after_a_consult_is_allowed(tmp_path):
    records = [human(), advisor_call(), advisor_result(), assistant_text(A_PRINTED_PLAN)]
    assert not denied(decide(tmp_path, records, command="git rm -r --cached tests/reports"))


def test_a_fresh_consult_re_arms_the_next_destructive_command(tmp_path):
    """Consult, delete, consult again, delete again — that sequence is the point."""
    records = [
        human(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        bash_call("git rm -r --cached tests/reports"),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
    ]
    assert not denied(decide(tmp_path, records, command="rm -rf graphify-out"))


def test_a_harmless_command_after_a_destructive_one_is_not_taxed(tmp_path):
    """A guard that fires on ordinary work gets deleted, and then guards nothing."""
    records = [
        human(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        bash_call("git rm -r --cached tests/reports"),
    ]
    assert not denied(decide(tmp_path, records, command="git status --porcelain"))


# ------------------------------------------------------------- the Stop arm holds


def test_the_stop_arm_still_refuses_a_reply_with_no_consult(tmp_path):
    decision = decide(tmp_path, [human()], event="Stop")
    assert decision.get("decision") == "block"
    assert "NO CONSULT, NO REPLY." in reason(decision)


def test_the_stop_arm_is_satisfied_by_a_consult(tmp_path):
    records = [human(), advisor_call(), advisor_result()]
    assert decide(tmp_path, records, event="Stop") == {}
