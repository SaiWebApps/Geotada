"""Payload tests for .claude/hooks/proceed-guard.py.

The guard has one arm, on Stop. It blocks a reply that ends a turn while the
written plan still owes phases, the turn took actions, and no `AskUserQuestion`
was called. `AskUserQuestion` is the only sanctioned way to stop.

EVERY RECORD SHAPE HERE WAS READ OFF A REAL TRANSCRIPT, never invented. That is
not a stylistic preference. An earlier sibling guard looked for
``{"type": "tool_use", "name": "advisor"}`` — the shape every OTHER tool uses.
The advisor is a server-side tool and records as ``server_tool_use`` with a
separate ``advisor_tool_result`` block, so the check could never match: the
guard blocked every reply, consult or not, and its thirteen payload tests all
passed because they were built from the same assumed shape. A fixture invented
alongside the code it tests proves only that the two agree with each other.

Shapes inherited from tests/test_advisor_consult_guard.py, measured 2026-08-29
on session 710b5e6a:

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

Two more shapes were measured for THIS guard, 2026-09-01, both off
.claude/projects/-Users-sairambkrishnan-git-ondoway/*.jsonl:

    question   {"type": "assistant", "message": {"content": [
                   {"type": "tool_use", "id": "toolu_01XEXtC9qVqLFVVXyGvMbztk",
                    "name": "AskUserQuestion",
                    "input": {"questions": [{"question": "...", "header": "...",
                                             "multiSelect": false,
                                             "options": [{"label": "...",
                                                          "description": "..."}]}]},
                    "caller": {"type": "direct"}}]}}

    block      {"type": "user", "isMeta": true,
     feedback   "message": {"content": "Stop hook feedback: <the reason text>"}}

The second one is load-bearing and is why it was measured rather than assumed:
it is how this guard's OWN block comes back into the transcript. It carries a
plain string, no `origin` stamp — so only `isMeta` keeps `_is_human_turn` from
calling it a person typing. If it did, one block would open a fresh turn with no
tools in it, which this guard allows, and the guard would be disarmed for the
rest of the session after firing exactly once.
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
GUARD = REPO / ".claude" / "hooks" / "proceed-guard.py"


# ------------------------------------------------------------------ plan fixtures
#
# Shaped after the real .claude/ledger/shared-tracker-plan.md, whose phase
# headings on 2026-09-01 are `### P0 — DONE 2026-09-01. ...` followed by P1
# through P4 with no DONE in them.

OUTSTANDING_PLAN = """# Shared tracker — the one source of truth

## The five phases

### P0 — DONE 2026-09-01. Uncommitted; the owner commits.

P0 moved validation into the engine.

### P1 — the `track` command and the database

The command and its tables.

### P2 — engine and front half move onto the database

### P3 — the dashboard

### P4 — the manager

## Out of scope

- Any commit. The engine never commits; the human does.
"""

FINISHED_PLAN = """# Shared tracker — the one source of truth

## The five phases

### P0 — DONE 2026-09-01.

### P1 — DONE 2026-09-02.

### P2 — DONE 2026-09-03.
"""


# ---------------------------------------------------------------- record shapes


def human(text="do the thing"):
    return {"type": "user", "origin": {"kind": "human"}, "message": {"content": text}}


def assistant_text(text="Here is what I found."):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def bash_call(command="ls -la"):
    return {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": command}}]
        },
    }


def ask_user_question():
    """Measured 2026-09-01 — an ORDINARY tool call, not the advisor's server shape."""
    return {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_01XEXtC9qVqLFVVXyGvMbztk",
                    "name": "AskUserQuestion",
                    "input": {
                        "questions": [
                            {
                                "question": "Which do you want me to do?",
                                "header": "Next move",
                                "multiSelect": False,
                                "options": [
                                    {"label": "Fix the guard first", "description": "..."},
                                    {"label": "Finish now", "description": "..."},
                                ],
                            }
                        ]
                    },
                    "caller": {"type": "direct"},
                }
            ]
        },
    }


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


def stop_hook_feedback(reason="KEEP GOING — THIS IS A NUDGE, NOT A WALL."):
    """How a blocked reply comes back into the transcript. Measured 2026-09-01.

    Plain string content, no `origin` stamp, `isMeta` true. That last field is
    the only thing distinguishing it from a person typing.
    """
    return {
        "type": "user",
        "isMeta": True,
        "message": {"content": f"Stop hook feedback: {reason}"},
    }


def tool_result_error(call_id="toolu_ran", text="2 failed, 40 passed"):
    """A tool call whose result came back an error — e.g. a failing test run.

        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "toolu_x",
             "is_error": true, "content": "<the failure>"}]}}
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


# ---------------------------------------------------------------------- harness


def decide(tmp_path, records, *, plan=OUTSTANDING_PLAN, session=None):
    """Run the guard over `records` and return its decision ({} means allowed).

    Each tmp_path gets its own state file, its own plan file AND its own session
    id. The guard keeps a running tally on disk, so a shared path would make
    these tests order-dependent on one another and let a test run reach into a
    live session open on this machine. Pass `session` explicitly to make several
    calls share one tally on purpose, which is the only way to exercise the
    ceiling at all.

    `plan=None` points the guard at a path that does not exist, which is the
    "no written plan" case rather than the "plan is finished" one.
    """
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    plan_file = tmp_path / "shared-tracker-plan.md"
    if plan is None:
        plan_file = tmp_path / "no-such-plan.md"
    else:
        plan_file.write_text(plan)

    payload = {
        "hook_event_name": "Stop",
        "transcript_path": str(transcript),
        "session_id": session or f"test-{tmp_path.name}",
    }
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **os.environ,
            "ONDOWAY_PROCEED_STATE": str(tmp_path / "state.json"),
            "ONDOWAY_PROCEED_PLAN": str(plan_file),
            # The sibling guards' escape hatch must not be set, or every call
            # here would allow and the suite would prove nothing.
            "CLAUDE_NO_EXCUSES_JUDGE": "",
        },
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else {}


def blocked(decision):
    return decision.get("decision") == "block"


def reason(decision):
    return decision.get("reason", "")


# A turn that did real work and then stopped, with no question on the table.
STALLED = [human(), assistant_text(), bash_call("uv run pytest tests/test_x.py"), assistant_text()]


# ------------------------------------------------------- the arm: a stall is blocked


def test_a_stall_with_phases_outstanding_is_blocked(tmp_path):
    """Plan owes phases, tools were used, no question asked."""
    decision = decide(tmp_path, STALLED)
    assert blocked(decision)
    assert "KEEP GOING" in reason(decision)


def test_asking_a_real_question_is_the_sanctioned_way_to_stop(tmp_path):
    """`AskUserQuestion` is the ONLY sanctioned stop — the "show questions" half."""
    records = [human(), assistant_text(), bash_call(), ask_user_question()]
    assert decide(tmp_path, records) == {}


def test_a_finished_plan_is_not_a_stall(tmp_path):
    """Every phase heading says DONE, so there is nothing to carry on into."""
    assert decide(tmp_path, STALLED, plan=FINISHED_PLAN) == {}


def test_no_plan_file_means_no_opinion(tmp_path):
    """This guard only governs a run that has a written plan."""
    assert decide(tmp_path, STALLED, plan=None) == {}


def test_a_turn_that_used_no_tools_is_not_a_stall(tmp_path):
    """A turn that only answered a question has nothing to carry on FROM."""
    records = [human("what does P1 do?"), assistant_text("It builds the track command.")]
    assert decide(tmp_path, records) == {}


def test_an_advisor_only_turn_is_not_a_stall(tmp_path):
    """The advisor records as `server_tool_use`, which is deliberately not a tool.

    The sibling advisor gate forces a consult into every single turn, so counting
    `server_tool_use` would mean no turn is ever tool-free and the allowance
    above could never fire in practice — the guard would block plain answers.
    """
    records = [human("what does P1 do?"), advisor_call(), advisor_result(), assistant_text()]
    assert decide(tmp_path, records) == {}


# ------------------------------------------------- the block is a NUDGE, not a wall


def test_the_block_names_the_outstanding_phases(tmp_path):
    text = reason(decide(tmp_path, STALLED))
    for label in ("P1", "P2", "P3", "P4"):
        assert label in text, f"{label} is outstanding and must be named"
    assert "P0" not in text, "P0 says DONE and must not be listed as owed"


def test_the_block_says_to_keep_working_in_the_same_turn(tmp_path):
    """Not a wall: the expected response is to carry on, not to redo or re-verify."""
    text = reason(decide(tmp_path, STALLED))
    assert "NUDGE, NOT A WALL" in text
    assert "THIS SAME TURN" in text
    assert "redo, re-verify or re-report" in text


def test_the_block_demands_the_tool_not_a_question_in_prose(tmp_path):
    text = reason(decide(tmp_path, STALLED))
    assert "AskUserQuestion" in text
    assert "A question written in prose is not a question." in text
    assert "options" in text


# ------------------------------------------------- the ceiling, so a report gets out
#
# This guard's own conditions get MORE true the more its nudge is obeyed:
# "phases outstanding" cannot be cleared inside one turn, and "the turn used
# tools" becomes true the instant the nudge is followed. Without a ceiling it
# would block every reply for the rest of a multi-phase build — the
# unsatisfiable boundary this project has already shipped twice.


def test_three_blocks_in_one_turn_stand_the_guard_down(tmp_path):
    for attempt in range(3):
        assert blocked(decide(tmp_path, STALLED, session="wedged")), attempt
    decision = decide(tmp_path, STALLED, session="wedged")
    assert not blocked(decision)
    assert "PROCEED GUARD STOOD DOWN" in decision.get("systemMessage", "")


def test_the_owner_speaking_starts_the_tally_again(tmp_path):
    """A new ask is new ground, not the self-feeding condition the ceiling is for."""
    for _ in range(3):
        assert blocked(decide(tmp_path, STALLED, session="spoken"))
    spoke_again = [*STALLED, human("now do P2"), bash_call(), assistant_text()]
    assert blocked(decide(tmp_path, spoke_again, session="spoken"))


def test_a_sanctioned_stop_clears_the_tally(tmp_path):
    """Ordinary correct behaviour must never accumulate toward the ceiling."""
    good = [human(), bash_call(), ask_user_question()]
    assert blocked(decide(tmp_path, STALLED, session="mixed"))
    assert blocked(decide(tmp_path, STALLED, session="mixed"))
    assert decide(tmp_path, good, session="mixed") == {}
    # Tally cleared: the next two blocks must not trip a ceiling of three.
    assert blocked(decide(tmp_path, STALLED, session="mixed"))
    assert blocked(decide(tmp_path, STALLED, session="mixed"))


# --------------------------- the guard must not read its OWN output as a new turn
#
# The sibling guard deadlocked by counting a tool call it had itself REFUSED as a
# destructive act that had run — a boundary check reading its own output as
# input, ledger class 17b. The equivalent hole here runs the other way: if this
# guard's own block feedback counted as a person typing, it would become the new
# turn boundary. The turn after it has no tools in it yet, which this guard
# ALLOWS — so firing once would disarm it for the rest of the session.


def test_the_guards_own_block_feedback_does_not_start_a_new_turn(tmp_path):
    """Measured shape, not assumed: isMeta is the only thing marking it machine-written."""
    records = [*STALLED, stop_hook_feedback(), bash_call(), assistant_text()]
    decision = decide(tmp_path, records, session="feedback")
    assert blocked(decision), (
        "the guard's own feedback is an isMeta record and must not open a fresh "
        "turn; if it did, one block would disarm the guard for good"
    )


def test_block_feedback_alone_does_not_become_a_tool_free_turn(tmp_path):
    """The exact disarm: feedback, then a text-only reply, must still block.

    Were the feedback treated as human, the turn after it would be text-only,
    the tool-free allowance would fire, and the reply would sail through.
    """
    records = [*STALLED, stop_hook_feedback(), assistant_text("As I was saying.")]
    assert blocked(decide(tmp_path, records, session="disarm"))


def test_a_real_message_after_block_feedback_still_ends_the_turn(tmp_path):
    """So the fix above cannot become a blanket exemption for `user` records."""
    records = [*STALLED, stop_hook_feedback(), human("stop, do this instead")]
    assert decide(tmp_path, records, session="spoke-after") == {}


# --------------------------------------------- a failing command is still working


def test_a_failed_tool_call_still_counts_as_work(tmp_path):
    """The most common stall shape there is: run the tests, they fail, stop and ask.

    `pytest` exiting non-zero comes back as a `tool_result` with `is_error`. The
    sibling guard excludes errored calls from its DESTRUCTIVE tally, correctly —
    a command that was refused changed nothing. This guard asks a different
    question: was the turn working? A failing test run certainly was, and
    excluding it here would wave through precisely the stall to catch.
    """
    records = [
        human(),
        bash_call_with_id("uv run pytest tests/test_x.py", "toolu_failed"),
        tool_result_error("toolu_failed"),
        assistant_text("Two tests fail."),
    ]
    assert blocked(decide(tmp_path, records, session="failing-run"))


# ------------------------------------------------------- reading the plan's phases


def test_a_phase_marked_abandoned_is_not_read_as_done(tmp_path):
    """ABANDONED contains DONE — in capitals — so a substring test retires it.

    A-B-A-N-D-O-N-E-D: `DONE` sits at index 4. This test failed when the guard
    asked `"DONE" in heading`, and being case-sensitive rescued nothing, because
    the letters are already capitals. A phase the owner explicitly gave up on was
    read as finished and the guard went silent on it — and a guard that stops
    firing looks exactly like a satisfied one. The check compares WORDS now.
    """
    plan = "## The phases\n\n### P0 — DONE\n\n### P3 — ABANDONED dashboard approach\n"
    decision = decide(tmp_path, STALLED, plan=plan)
    assert blocked(decision)
    assert "ABANDONED dashboard approach" in reason(decision)


def test_done_is_recognised_whatever_its_casing_and_punctuation(tmp_path):
    """Word matching makes case-folding safe, so a heading may say so any way.

    `**Done**`, `(done)` and `DONE.` all mean the phase is finished. None of them
    is reachable by the substring bug above, because none of those words is a
    fragment of a longer one.
    """
    plan = (
        "## The phases\n\n"
        "### P0 — **Done** 2026-09-01.\n\n"
        "### P1 — (done)\n\n"
        "### P2 — DONE.\n"
    )
    assert decide(tmp_path, STALLED, plan=plan) == {}


def test_a_heading_that_is_not_a_phase_is_ignored(tmp_path):
    """`Plan`, `Phase notes` and prose headings start with P but name no phase."""
    plan = (
        "# Shared tracker\n\n"
        "## Plan\n\n"
        "## Phase notes\n\n"
        "## Problems\n\n"
        "### P0 — DONE 2026-09-01.\n"
    )
    assert decide(tmp_path, STALLED, plan=plan) == {}


def test_two_headings_for_one_phase_are_judged_separately(tmp_path):
    """Copied from the real plan as it stood at 15:10 on 2026-09-01.

    The file carries a status heading and a standing design heading per phase.
    Collapsing them by label — "P2 is finished if any P2 heading says DONE" —
    was tried against this exact shape and marked P2 finished on the strength of
    `engine side DONE`, while the same heading says the front half is in
    progress. The guard would have gone silent on the one live phase. Judging
    each heading on its own over-lists instead, which is noise the ceiling
    bounds.
    """
    plan = (
        "## The five phases\n\n"
        "### P1 — DONE 2026-09-01. Uncommitted; the owner commits.\n\n"
        "### P1 — what was built\n\n"
        "### P2 — engine side DONE 2026-09-01. Front half in progress.\n\n"
        "### P2 — the full design\n"
    )
    decision = decide(tmp_path, STALLED, plan=plan)
    assert blocked(decision)
    assert "P2 — the full design" in reason(decision), "the live phase must be named"


def test_a_phase_at_another_heading_level_still_counts(tmp_path):
    """Missing a demoted phase would make the guard go quiet — the one bad direction."""
    plan = "# Shared tracker\n\n### P0 — DONE\n\n## P9 — the late addition\n"
    decision = decide(tmp_path, STALLED, plan=plan)
    assert blocked(decision)
    assert "P9 — the late addition" in reason(decision)


# ---------------------------------------------------------------- the guard's edges


def test_a_non_stop_event_is_never_touched(tmp_path):
    """Registered on Stop only; anything else passes straight through."""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in STALLED) + "\n")
    plan_file = tmp_path / "plan.md"
    plan_file.write_text(OUTSTANDING_PLAN)
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "transcript_path": str(transcript),
                "session_id": "other-event",
            }
        ),
        capture_output=True,
        text=True,
        timeout=60,
        env={
            **os.environ,
            "ONDOWAY_PROCEED_STATE": str(tmp_path / "state.json"),
            "ONDOWAY_PROCEED_PLAN": str(plan_file),
            "CLAUDE_NO_EXCUSES_JUDGE": "",
        },
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == ""


def test_a_transcript_with_no_human_record_is_allowed(tmp_path):
    """Nothing has been asked yet, so there is no turn to judge."""
    assert decide(tmp_path, [assistant_text(), bash_call()]) == {}


def test_the_guard_never_exits_non_zero(tmp_path):
    """A guard that crashes is a guard that is switched off.

    Garbage on stdin must still exit 0 and print nothing.
    """
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input="not json at all",
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "ONDOWAY_PROCEED_STATE": str(tmp_path / "state.json")},
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == ""
