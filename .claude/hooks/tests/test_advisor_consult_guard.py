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
import os
import subprocess
import sys
from pathlib import Path

# Beside the hook it tests, not in the product's tests/ tree — the subject is
# agent supervision, not Ondoway, so it must never run inside `make test`.
REPO = Path(__file__).resolve().parents[3]
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


def grounding_call(name="mcp__codegraph__codegraph_explore"):
    """A look at the real code — what the advisor must be able to see.

    The advisor has no tools: it forwards this conversation and reads nothing
    else, so a consult with none of these before it produces advice about
    software in general. Every fixture below whose subject is a DIFFERENT arm
    carries one of these, so those tests keep measuring the arm they are named
    for instead of failing on this one.
    """
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": {"query": "x"}}]},
    }


# ---------------------------------------------------------------------- harness


def decide(
    tmp_path,
    records,
    *,
    tool="Bash",
    command="ls -la",
    event="PreToolUse",
    session=None,
):
    """Run the guard over `records` and return its decision ({} means allowed).

    Each tmp_path gets its own state file AND its own session id. The guard keeps
    two running tallies on disk — the Stop arm's block count and the pre-tool
    ceiling — so a shared path would make these tests order-dependent on one
    another and let a test run reach into a live session open on this machine.
    Pass `session` explicitly to make several calls share one tally on purpose,
    which is the only way to exercise the ceiling at all.
    """
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    payload = {
        "hook_event_name": event,
        "tool_name": tool,
        "tool_input": {"command": command},
        "transcript_path": str(transcript),
        "session_id": session or f"test-{tmp_path.name}",
    }
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "ONDOWAY_ADVISOR_STATE": str(tmp_path / "state.json")},
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
    records = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
    ]
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


# --------------------------------------- arm: the advice was grounded in the code
#
# The advisor has NO TOOLS. It forwards this conversation and reads nothing else,
# so a consult with no look at the code before it produces advice about software
# in general. Measured 2026-08-31: asked to prove with screenshots that a browser
# had run the suite, it designed a DevTools-attach scheme from scratch while
# tests/test_workbench_ui.py sat in the repo doing exactly that job through
# Playwright, with 36 call sites. The owner's verdict on the result: "means
# nothing". The advisor could not have known — that file had never been named in
# the conversation.


def test_a_consult_with_no_look_at_the_code_cannot_be_acted_on(tmp_path):
    records = [human(), advisor_call(), advisor_result(), assistant_text(A_PRINTED_PLAN)]
    decision = decide(tmp_path, records)
    assert denied(decision)
    assert "THE ADVICE WAS NOT GROUNDED IN THIS CODEBASE." in reason(decision)


def test_grounding_after_the_consult_is_too_late(tmp_path):
    """The advisor saw the conversation as it stood when it was called.

    A file read afterwards is a file it never saw: that grounding informs the
    implementer and leaves the advice exactly as uninformed as it was.
    """
    records = [
        human(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        grounding_call(name="Read"),
    ]
    assert denied(decide(tmp_path, records))


def test_any_of_the_grounding_tools_satisfies_it(tmp_path):
    for name in ("Read", "Grep", "Glob", "mcp__codegraph__codegraph_explore"):
        records = [
            human(),
            grounding_call(name=name),
            advisor_call(),
            advisor_result(),
            assistant_text(A_PRINTED_PLAN),
        ]
        assert not denied(decide(tmp_path, records)), f"{name} should count as grounding"


def test_the_grounding_tools_are_never_themselves_blocked(tmp_path):
    """Otherwise the rule would be unsatisfiable by the remedy it prints.

    A guard that cannot be satisfied by its own instructions is the class-17
    failure this project has already shipped twice: the only way past becomes the
    escape token, which trains the habit of waving guards through.
    """
    for name in ("Read", "Grep", "Glob", "mcp__codegraph__codegraph_explore"):
        assert not denied(decide(tmp_path, [human()], tool=name)), f"{name} must stay exempt"


def test_acting_tools_are_still_gated_with_no_consult(tmp_path):
    """The exemption is for LOOKING. Changing things still needs the full gate.

    Each tool gets its OWN session, because four refusals sharing one tally would
    trip the ceiling on the fourth and this test would then be measuring the
    ceiling instead of the gate. That is the ceiling behaving correctly — see
    test_three_refusals_in_one_turn_stand_the_arm_down — and it belongs in the
    test named for it.
    """
    for name in ("Bash", "Write", "Edit", "Agent"):
        decision = decide(tmp_path, [human()], tool=name, session=f"gated-{name}")
        assert denied(decision), f"{name} must stay gated"


# ------------------------------------------ arm: one consult per destructive act


def test_a_second_destructive_command_on_one_consult_is_refused(tmp_path):
    """The exact shape of the sweep that deleted a file the suite reads."""
    records = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        bash_call("git rm -r --cached tests/reports"),
    ]
    decision = decide(tmp_path, records, command="rm -rf specs/2026-08-06-tour-time-model")
    assert denied(decision)
    assert "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT." in reason(decision)


def test_the_first_destructive_command_after_a_consult_is_allowed(tmp_path):
    records = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
    ]
    assert not denied(decide(tmp_path, records, command="git rm -r --cached tests/reports"))


def test_a_fresh_consult_re_arms_the_next_destructive_command(tmp_path):
    """Consult, delete, consult again, delete again — that sequence is the point."""
    records = [
        human(),
        grounding_call(),
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
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        bash_call("git rm -r --cached tests/reports"),
    ]
    assert not denied(decide(tmp_path, records, command="git status --porcelain"))


# ------------------------------- the arm must not count its OWN refusals as acts


def tool_result_error(call_id, text="A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT."):
    """How a REFUSED tool call comes back — read off a real transcript.

        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_x",
             "is_error": true, "content": "<the refusal text>"}]}}

    The `tool_use` block for a refused call is written to the transcript exactly
    like one that ran. Only this result tells them apart.
    """
    return {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": call_id,
                    "is_error": True,
                    "content": text,
                }
            ]
        },
    }


def bash_call_with_id(command, call_id):
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": call_id,
                    "name": "Bash",
                    "input": {"command": command},
                }
            ]
        },
    }


def test_a_refused_destructive_command_does_not_count_as_one(tmp_path):
    """The deadlock this guard walked into on 2026-08-31.

    A refused `git commit` is still a `tool_use` record. Counting it made the
    refusal itself the reason for the next refusal: three consecutive attempts,
    each preceded by a correct fresh consult and a printed plan, each blocked by
    the previous block. There was no way out except editing the guard — which is
    class 17b of the ledger, a boundary check reading its own output as input.
    """
    records = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        bash_call_with_id("git commit --no-edit", "toolu_refused"),
        tool_result_error("toolu_refused"),
    ]
    assert not denied(decide(tmp_path, records, command="git commit --no-edit")), (
        "a command this guard REFUSED never ran, so it cannot be the destructive "
        "act that forces the next consult"
    )


def test_a_destructive_command_that_actually_RAN_still_counts(tmp_path):
    """The other direction, so the fix above cannot become a blanket exemption."""
    records = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        bash_call_with_id("git rm -r --cached tests/reports", "toolu_ran"),
        # no error result: the command ran
    ]
    decision = decide(tmp_path, records, command="rm -rf specs/old")
    assert denied(decision)
    assert "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT." in reason(decision)


# ------------------------------------------------------------- the Stop arm holds


def test_the_stop_arm_still_refuses_a_reply_with_no_consult(tmp_path):
    decision = decide(tmp_path, [human()], event="Stop")
    assert decision.get("decision") == "block"
    assert "NO CONSULT, NO REPLY." in reason(decision)


def test_the_stop_arm_is_satisfied_by_a_consult(tmp_path):
    records = [human(), advisor_call(), advisor_result()]
    assert decide(tmp_path, records, event="Stop") == {}


# ------------------------------- the compaction summary is not a person typing
#
# READ OFF THIS SESSION'S OWN TRANSCRIPT, 2026-08-31. A 21 MB session ran out of
# context; the harness wrote a summary record and the guard made it the boundary
# of "this turn", so every consult that followed landed in a turn that had
# already ended. The record carries plain text, no `origin` stamp and no
# `isMeta`, so the fail-loud default called it human. Nobody typed it.


def compaction_summary():
    return {
        "type": "user",
        "isCompactSummary": True,
        "isVisibleInTranscriptOnly": True,
        "message": {
            "content": (
                "This session is being continued from a previous conversation "
                "that ran out of context. The summary below covers the earlier "
                "portion of the conversation."
            )
        },
        "uuid": "9d0b2f6e-compact",
        "timestamp": "2026-08-31T21:39:22.375Z",
    }


def test_a_compaction_summary_does_not_end_the_turn(tmp_path):
    """The consult still counts on the other side of a compaction."""
    records = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        compaction_summary(),
    ]
    assert not denied(decide(tmp_path, records))


def test_a_real_message_after_a_compaction_summary_still_ends_the_turn(tmp_path):
    """So the fix above cannot become a blanket exemption for `user` records."""
    records = [
        human("first ask"),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        compaction_summary(),
        human("second ask"),
    ]
    assert denied(decide(tmp_path, records))


def test_an_unfamiliar_user_record_still_counts_as_human(tmp_path):
    """The fail-loud default is untouched: the fix keys on a POSITIVE marker.

    A shape carrying neither `isCompactSummary` nor an origin stamp is exactly
    the case the default exists for — an unfamiliar record costs one extra
    consult rather than silently disarming the guard.
    """
    records = [
        human("first ask"),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        {"type": "user", "message": {"content": "[Request interrupted by user]"}},
    ]
    assert denied(decide(tmp_path, records))


# --------------------------------- the ceiling, for a transcript that lags
#
# MEASURED 2026-08-31, replaying this guard against the real records at a refused
# `cat Makefile`: consult_index=28, plan_printed_after=True, grounded_before=False
# — the `Read` that grounded the consult HAD happened and its record was not yet
# on disk. The guard reads the transcript FILE, and the file lags the live
# conversation, so a refusal can be correct about the file and wrong about the
# world. Repeating the remedy could not clear it: every retry re-read the same
# lagging file, and Bash, Write and Edit were all gated, including on this guard.
#
# That is not a rule being skipped. It is a rule that cannot be satisfied, which
# is ledger class 17b, the same failure as the `_failed_call_ids` deadlock above.


NO_CONSULT = [{"type": "user", "origin": {"kind": "human"}, "message": {"content": "go"}}]


def test_three_refusals_in_one_turn_stand_the_arm_down(tmp_path):
    for attempt in range(3):
        assert denied(decide(tmp_path, NO_CONSULT, session="wedged")), attempt
    decision = decide(tmp_path, NO_CONSULT, session="wedged")
    assert not denied(decision)
    assert "ADVISOR GATE STOOD DOWN" in decision.get("systemMessage", "")


def test_looking_at_the_code_does_not_reset_the_ceiling(tmp_path):
    """Read/Grep/Glob are what the deadlocked loop kept doing between refusals.

    If an exempt look cleared the tally, the ceiling would never arrive in the
    one situation it exists for.
    """
    for _ in range(3):
        assert denied(decide(tmp_path, NO_CONSULT, session="wedged"))
        assert not denied(decide(tmp_path, NO_CONSULT, tool="Read", session="wedged"))
    assert not denied(decide(tmp_path, NO_CONSULT, session="wedged"))


def test_an_acting_tool_getting_through_clears_the_tally(tmp_path):
    """Ordinary work must never accumulate toward the ceiling."""
    good = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
    ]
    assert denied(decide(tmp_path, NO_CONSULT, session="mixed"))
    assert denied(decide(tmp_path, NO_CONSULT, session="mixed"))
    assert not denied(decide(tmp_path, good, session="mixed"))
    # Tally cleared: the next two refusals must not trip a ceiling of three.
    assert denied(decide(tmp_path, NO_CONSULT, session="mixed"))
    assert denied(decide(tmp_path, NO_CONSULT, session="mixed"))


def test_the_owner_speaking_starts_the_tally_again(tmp_path):
    """A new ask is new ground to be advised about, not a lagging transcript."""
    for _ in range(3):
        assert denied(decide(tmp_path, NO_CONSULT, session="spoken"))
    spoke_again = NO_CONSULT + [
        {"type": "user", "origin": {"kind": "human"}, "message": {"content": "now this"}}
    ]
    decision = decide(tmp_path, spoke_again, session="spoken")
    assert denied(decision)
    assert "NO CONSULT, NO ACTION." in reason(decision)
