"""Payload tests for .claude/hooks/advisor-consult-guard.py.

The guard has two arms. The Stop arm refuses to let a turn END without an
advisor consult in it — and, on any model that is not Fable, without a closing
consult AFTER the turn's last action with a written report in front of it. The
PreToolUse arm refuses to let a tool RUN until the turn contains a consult, a
visible plan after it and a look at the code before it, and refuses a second
destructive command on a single piece of advice.

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

The shapes below were measured (session 710b5e6a on 2026-08-29, session a798c91b
on 2026-09-01):

    human      {"type": "user", "origin": {"kind": "human"},
                "message": {"content": "<a string, not a list>"}}
    text       {"type": "assistant", "message": {"model": "claude-opus-5",
                "content": [{"type": "text", "text": "..."}]}}
    narration  {"type": "assistant", "message": {"model": "claude-fable-5-1",
                "content": [{"type": "thinking", "thinking": "<one paragraph>",
                             "signature": "CAQSjRQKEQgRGAI4AUIJbmFycmF0aW9u..."}]}}
    advisor    {"type": "assistant", "message": {"content": [
                   {"type": "server_tool_use", "id": "srvtoolu_...", "name": "advisor",
                    "input": {}}]}}
    result     {"type": "assistant", "message": {"content": [
                   {"type": "advisor_tool_result", "tool_use_id": "srvtoolu_...",
                    "content": {"type": "advisor_redacted_result",
                                "encrypted_content": "..."}}]}}
    tool call  {"type": "assistant", "message": {"content": [
                   {"type": "tool_use", "id": "toolu_...", "name": "Bash",
                    "input": {...}}]}}
    result     {"type": "user", "message": {"content": [
                   {"type": "tool_result", "tool_use_id": "toolu_...",
                    "content": "...", "is_error": <true only when refused/failed>}]}}

THE GATED CALL'S OWN RECORD IS ON DISK WHEN THE GUARD JUDGES. The guard waits
for it — the payload's ``tool_use_id`` — before reading anything, so every
PreToolUse fixture here ends with that record, exactly as the real file does once
it has caught up. ``landed=False`` is the file that never catches up.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# Beside the hook it tests, not in the product's tests/ tree — the subject is
# agent supervision, not Ondoway, so it must never run inside `make test`.
REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / ".claude" / "hooks" / "advisor-consult-guard.py"

FABLE = "claude-fable-5-1"
OPUS = "claude-opus-5"

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

#: A closing report of the same shape — what ran and what it showed.
A_REPORT = (
    "Report against the plan: the file was read in full, the failing test was "
    "written and went red, the change was made, the test went green, the linter "
    "passed, and the suite ran once at the end with every test passing."
)

#: The first 96 characters of a real narration block's signature, read off
#: session a798c91b's transcript on 2026-09-01. The guard decodes only this
#: prefix; the block's kind sits in its first bytes.
NARRATION_SIGNATURE = (
    "CAQSjRQKEQgRGAI4AUIJbmFycmF0aW9uEgxVNbJmeGWYGr3Ypz4aDJ9hjtKy2uyZO/q7pSIwrHaRZ+f53op03qFYO3yVQpFL"
)
#: The same prefix of a real PRIVATE thinking block's signature, same session.
THINKING_SIGNATURE = (
    "CAQSowYKEAgRGAI4AUIIdGhpbmtpbmcSDGyo8IreOcrYiEsSshoMQ9DkSO4jnFT3kcSAIjB6tmuPRZadGT1NHaXCaGknJ++I"
)

#: A real narration block's text from the same record: the harness's rendering
#: of a printed plan of about 1,500 characters.
A_NARRATED_PLAN = (
    "I'll follow the advisor's plan step by step, starting by locating this "
    "session's transcript and replaying the three Edit refusals to pinpoint "
    "the real cause behind the guard's failure."
)


# ---------------------------------------------------------------- record shapes


def human(text="do the thing"):
    return {"type": "user", "origin": {"kind": "human"}, "message": {"content": text}}


def assistant(blocks, model=FABLE):
    message = {"content": blocks}
    if model is not None:
        message["model"] = model
    return {"type": "assistant", "message": message}


def assistant_text(text, model=FABLE):
    return assistant([{"type": "text", "text": text}], model)


def narration(text=A_NARRATED_PLAN, model=FABLE):
    return assistant(
        [{"type": "thinking", "thinking": text, "signature": NARRATION_SIGNATURE}], model
    )


def private_thinking(text, model=FABLE, signature=THINKING_SIGNATURE):
    block = {"type": "thinking", "thinking": text}
    if signature is not None:
        block["signature"] = signature
    return assistant([block], model)


def advisor_call(model=FABLE):
    return assistant(
        [{"type": "server_tool_use", "id": "srvtoolu_x", "name": "advisor", "input": {}}],
        model,
    )


def advisor_result(model=FABLE):
    return assistant(
        [
            {
                "type": "advisor_tool_result",
                "tool_use_id": "srvtoolu_x",
                "content": {"type": "advisor_redacted_result", "encrypted_content": "Escl"},
            }
        ],
        model,
    )


def tool_call(name, tool_input, call_id="toolu_x", model=FABLE):
    return assistant(
        [{"type": "tool_use", "id": call_id, "name": name, "input": tool_input}], model
    )


def bash_call(command, call_id="toolu_x", model=FABLE):
    return tool_call("Bash", {"command": command}, call_id, model)


def grounding_call(name="mcp__codegraph__codegraph_explore", model=FABLE):
    """A look at the real code — what the advisor must be able to see.

    The advisor has no tools: it forwards this conversation and reads nothing
    else, so a consult with none of these before it produces advice about
    software in general. Every fixture below whose subject is a DIFFERENT arm
    carries one of these, so those tests keep measuring the arm they are named
    for instead of failing on this one.
    """
    return tool_call(name, {"query": "x"}, "toolu_look", model)


def tool_result(call_id, text="ok", is_error=False):
    """How a call's result comes back. `is_error: true` is a refusal or a
    failure; a clean result is the proof that the call actually ran."""
    block = {"type": "tool_result", "tool_use_id": call_id, "content": text}
    if is_error:
        block["is_error"] = True
    return {"type": "user", "message": {"content": [block]}}


def ran(records, call_id):
    """The call `call_id` in `records`, followed by its clean result."""
    return [*records, tool_result(call_id)]


def gated_call(tool, command, call_id):
    """The record of the call the guard is judging — on disk by the time it does."""
    return tool_call(tool, {"command": command}, call_id)


# ---------------------------------------------------------------------- harness


def write_transcript(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


#: An ACT, not a look. Since the 2026-09-02 redesign a read-only shell command
#: (`ls -la`, `git status`) is never gated, so the default gated command has to
#: be something that runs code.
AN_ACT = "uv run pytest tests/test_x.py"


def run_guard(payload, wait="0.3", tmp_path=None, doctor=None):
    env = {**os.environ, "ONDOWAY_ADVISOR_LAG_WAIT": wait}
    if tmp_path is not None:
        # Private state and doctor report per test, never the live session's.
        env["ONDOWAY_STATE_DIR"] = str(tmp_path / "state")
        env["ONDOWAY_LOCAL_SETTINGS"] = str(tmp_path / "state" / "settings.local.json")
        doctor_path = tmp_path / "state" / "doctor.json"
        doctor_path.parent.mkdir(parents=True, exist_ok=True)
        if doctor is not None:
            doctor_path.write_text(json.dumps(doctor))
        elif not doctor_path.exists():
            doctor_path.write_text(json.dumps({"advisor": {"supported": "yes"}}))
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else {}


def decide(
    tmp_path,
    records,
    *,
    tool="Bash",
    command=AN_ACT,
    event="PreToolUse",
    tool_use_id="toolu_gated",
    landed=True,
    wait="0.3",
    payload_extra=None,
    tool_input=None,
    doctor=None,
):
    """Run the guard over `records` and return its decision ({} means allowed).

    For a PreToolUse event the gated call's own record is appended to the
    transcript unless `landed=False`, because that is the file the guard sees
    once it has caught up. The lag wait is short by default so the never-lands
    fixtures finish in a fraction of a second.
    """
    transcript = tmp_path / "session.jsonl"
    rows = list(records)
    tool_input = tool_input if tool_input is not None else {"command": command}
    if event == "PreToolUse" and landed:
        rows.append(tool_call(tool, tool_input, tool_use_id))
    write_transcript(transcript, rows)
    payload = {
        "hook_event_name": event,
        "tool_name": tool,
        "tool_input": tool_input,
        "transcript_path": str(transcript),
        "session_id": f"test-{tmp_path.name}",
    }
    if tool_use_id is not None:
        payload["tool_use_id"] = tool_use_id
    payload.update(payload_extra or {})
    return run_guard(payload, wait, tmp_path=tmp_path, doctor=doctor)


def denied(decision):
    return decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def blocked(decision):
    return decision.get("decision") == "block"


def reason(decision):
    out = decision.get("hookSpecificOutput", {})
    return out.get("permissionDecisionReason") or decision.get("reason", "")


def consulted_turn(model=FABLE):
    """The shape every allowed action rests on: a look, a consult, a plan."""
    return [
        human(),
        grounding_call(model=model),
        advisor_call(model),
        advisor_result(model),
        assistant_text(A_PRINTED_PLAN, model),
    ]


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
    records = [*consulted_turn(), human("second ask")]
    assert denied(decide(tmp_path, records))


def test_a_consult_with_the_plan_printed_lets_the_tool_run(tmp_path):
    assert not denied(decide(tmp_path, consulted_turn()))


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
    records = [human(), grounding_call(), advisor_call(), advisor_result()]
    decision = decide(tmp_path, records)
    assert denied(decision)
    assert "THE PLAN WAS NOT PRINTED." in reason(decision)


def test_a_bare_acknowledgement_is_not_a_printed_plan(tmp_path):
    records = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        assistant_text("Consulting now."),
    ]
    decision = decide(tmp_path, records)
    assert denied(decision)
    assert "THE PLAN WAS NOT PRINTED." in reason(decision)


def test_text_printed_before_the_consult_does_not_count(tmp_path):
    """Otherwise any long preamble would pay for a consult that came after it."""
    records = [
        human(),
        grounding_call(),
        assistant_text(A_PRINTED_PLAN),
        advisor_call(),
        advisor_result(),
    ]
    assert denied(decide(tmp_path, records))


# ------------------------------------ the plan on Fable is a narration block
#
# MEASURED 2026-09-01, session a798c91b, Claude Fable 5.1 through claude-desktop:
# every visible line after a turn's first one is stored as a `thinking` block
# whose server signature names the kind "narration" — ten of them ran 184 to
# 617 characters, and the shortest stood in for a printed plan of about 1,500.
# Not one mid-turn `text` block after the first. A check that counted only
# text blocks refused every action for the rest of the turn, and a ceiling was
# invented to escape it. Opus 5 sessions store hundreds of mid-turn text blocks
# and no narration, so both channels have to count.


def test_a_narration_block_after_the_consult_is_a_printed_plan(tmp_path):
    records = [human(), grounding_call(), advisor_call(), advisor_result(), narration()]
    assert not denied(decide(tmp_path, records))


def test_private_thinking_after_the_consult_is_not_a_printed_plan(tmp_path):
    """The owner never sees private thinking, so it cannot be the plan they
    were shown — however long it runs."""
    records = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        private_thinking(A_PRINTED_PLAN * 3),
    ]
    decision = decide(tmp_path, records)
    assert denied(decision)
    assert "THE PLAN WAS NOT PRINTED." in reason(decision)


def test_a_thinking_block_with_no_signature_is_not_a_printed_plan(tmp_path):
    """No signature, no kind to read: treated as private, which refuses."""
    records = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        private_thinking(A_PRINTED_PLAN * 3, signature=None),
    ]
    assert denied(decide(tmp_path, records))


def test_a_one_line_narration_IS_a_printed_plan(tmp_path):
    """MEASURED 2026-09-02 on this project's own transcript: a seven-step
    numbered plan of about a thousand characters was stored by the harness as a
    narration block of 147 characters, and the old floor of 150 refused it as
    "not printed". The narration's length belongs to the harness, not to the
    session, so its PRESENCE is the check now. Text blocks keep the floor."""
    records = [
        human(),
        grounding_call(),
        advisor_call(),
        advisor_result(),
        narration("Consulting the advisor now."),
    ]
    assert not denied(decide(tmp_path, records))


# ------------------------------------------- arm: a look is never an act
#
# REDESIGNED 2026-09-02. The first refusal of a compliant turn was `ls -la` as
# "NO CONSULT, NO ACTION". Gating the Bash TOOL gated every look made through
# it, and a session that cannot look is pushed toward looking some other way.
# bashclass.py now classifies the COMMAND: read-only programs with read-only
# arguments and no redirection pass; everything else is an act.


def test_a_read_only_shell_command_needs_no_consult(tmp_path):
    for command in (
        "ls -la",
        "git status --porcelain",
        "git -C /tmp log --oneline -5 | head",
        "grep -n foo src/x.py",
        "cat a.txt 2>&1 | tail -3",
        "for f in a b; do wc -l $f; done",
        "find . -name '*.py' | sort",
        "python3 --version",
        "make -n lint",
    ):
        assert not denied(decide(tmp_path, [human()], command=command)), command


def test_a_shell_command_that_acts_is_gated(tmp_path):
    for command in (
        "python3 -c 'open(\"x\",\"w\").write(\"1\")'",
        "python3 scripts/thing.py",
        "uv run pytest tests/test_x.py",
        "make lint",
        "echo hi > out.txt",
        "cat in.txt | tee out.txt",
        "find . -name '*.pyc' -delete",
        "ls && rm -rf build",
        "sed -i '' s/a/b/ file.py",
        "curl https://example.com",
        "xargs rm < list.txt",
    ):
        decision = decide(tmp_path, [human()], command=command)
        assert denied(decision), command
        assert "NO CONSULT, NO ACTION." in reason(decision), command


# ------------------------------------------- arm: read it before you change it
#
# CLAUDE.md rule 5 as a STATE TRANSITION rather than a tool spelling: a file
# that exists may be modified only after it was opened in full with Read,
# whether the modification comes through Edit, Write, or a shell redirection.
# This replaces the old "grounded BEFORE the consult" arm, which fought the
# prompt-submit context (look first, then consult) and refused a Read that
# came one call late.


def read_call(path, call_id="toolu_read", limit=None, offset=None):
    data = {"file_path": str(path)}
    if limit is not None:
        data["limit"] = limit
    if offset is not None:
        data["offset"] = offset
    return tool_call("Read", data, call_id)


def existing_file(tmp_path, lines=40):
    target = tmp_path / "existing.py"
    target.write_text("\n".join(f"line {n}" for n in range(1, lines + 1)) + "\n")
    return target


def test_editing_a_file_never_read_is_refused(tmp_path):
    target = existing_file(tmp_path)
    decision = decide(
        tmp_path, consulted_turn(), tool="Edit",
        tool_input={"file_path": str(target), "old_string": "line 1", "new_string": "x"},
    )
    assert denied(decision)
    assert "READ IT BEFORE YOU CHANGE IT." in reason(decision)


def test_editing_a_file_read_in_full_is_allowed(tmp_path):
    target = existing_file(tmp_path)
    records = [*consulted_turn(), read_call(target)]
    decision = decide(
        tmp_path, records, tool="Edit",
        tool_input={"file_path": str(target), "old_string": "line 1", "new_string": "x"},
    )
    assert not denied(decision)


def test_a_read_from_an_earlier_turn_still_counts(tmp_path):
    """The rule is about the SESSION having opened the file, not this turn."""
    target = existing_file(tmp_path)
    records = [human("first"), read_call(target), *consulted_turn()]
    decision = decide(
        tmp_path, records, tool="Write",
        tool_input={"file_path": str(target), "content": "new"},
    )
    assert not denied(decision)


def test_an_excerpt_read_does_not_count(tmp_path):
    """`limit` that stops short of the end is an excerpt, which is the exact
    thing rule 5 exists to stop."""
    target = existing_file(tmp_path, lines=400)
    records = [*consulted_turn(), read_call(target, limit=100)]
    decision = decide(
        tmp_path, records, tool="Write",
        tool_input={"file_path": str(target), "content": "new"},
    )
    assert denied(decision)
    assert "READ IT BEFORE YOU CHANGE IT." in reason(decision)


def test_a_limited_read_that_reaches_the_end_counts(tmp_path):
    target = existing_file(tmp_path, lines=40)
    records = [*consulted_turn(), read_call(target, limit=30, offset=10)]
    decision = decide(
        tmp_path, records, tool="Write",
        tool_input={"file_path": str(target), "content": "new"},
    )
    assert not denied(decision)


def test_writing_a_new_file_needs_no_read(tmp_path):
    decision = decide(
        tmp_path, consulted_turn(), tool="Write",
        tool_input={"file_path": str(tmp_path / "brand-new.py"), "content": "x"},
    )
    assert not denied(decision)


def test_a_heredoc_over_an_unread_file_is_refused(tmp_path):
    """`cat > file <<EOF` was the shell's way around the Edit tool's own
    read-first check. It is held to the same rule."""
    target = existing_file(tmp_path)
    decision = decide(
        tmp_path, consulted_turn(), command=f"cat > {target} <<'EOF'\nnew\nEOF",
    )
    assert denied(decision)
    assert "READ IT BEFORE YOU CHANGE IT." in reason(decision)


def test_a_redirect_into_a_new_file_is_allowed(tmp_path):
    decision = decide(
        tmp_path, consulted_turn(), command=f"echo hi > {tmp_path / 'fresh.txt'}",
    )
    assert not denied(decision)


def test_tee_over_an_unread_file_is_refused(tmp_path):
    target = existing_file(tmp_path)
    decision = decide(tmp_path, consulted_turn(), command=f"echo hi | tee {target}")
    assert denied(decision)
    assert "READ IT BEFORE YOU CHANGE IT." in reason(decision)


def test_the_rule_holds_even_before_a_consult_is_checked_for_looks(tmp_path):
    """A read-only command that ALSO redirects into an existing file is not a
    look: the redirect makes it an act, and the act needs the read."""
    target = existing_file(tmp_path)
    decision = decide(tmp_path, [human()], command=f"ls > {target}")
    assert denied(decision)


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


def test_the_grounding_tools_are_never_themselves_blocked_nor_waited_on(tmp_path):
    """Otherwise the rule would be unsatisfiable by the remedy it prints.

    A guard that cannot be satisfied by its own instructions is the class-17
    failure this project has already shipped twice: the only way past becomes the
    escape token, which trains the habit of waving guards through.

    And a look must not pay the lag wait either: the exemption is checked before
    the guard waits for anything, proven here by a record that never lands and a
    wait long enough that paying it would show.
    """
    for name in ("Read", "Grep", "Glob", "mcp__codegraph__codegraph_explore"):
        started = time.monotonic()
        decision = decide(tmp_path, [human()], tool=name, landed=False, wait="5")
        assert not denied(decision), f"{name} must stay exempt"
        assert time.monotonic() - started < 2, f"{name} waited for the transcript"


def test_acting_tools_are_still_gated_with_no_consult(tmp_path):
    """The exemption is for LOOKING. Changing things still needs the full gate."""
    for name in ("Bash", "Write", "Edit", "Agent"):
        assert denied(decide(tmp_path, [human()], tool=name)), f"{name} must stay gated"


# ------------------------------------------ arm: one consult per destructive act


def test_a_second_destructive_command_on_one_consult_is_refused(tmp_path):
    """The exact shape of the sweep that deleted a file the suite reads."""
    records = ran(
        [*consulted_turn(), bash_call("git rm -r --cached tests/reports", "toolu_first")],
        "toolu_first",
    )
    decision = decide(tmp_path, records, command="rm -rf specs/2026-08-06-tour-time-model")
    assert denied(decision)
    assert "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT." in reason(decision)


def test_the_first_destructive_command_after_a_consult_is_allowed(tmp_path):
    """The gated call's own record is on disk, and it must not count itself as
    the destructive act that already ran on this consult."""
    decision = decide(tmp_path, consulted_turn(), command="git rm -r --cached tests/reports")
    assert not denied(decision)


def test_a_fresh_consult_re_arms_the_next_destructive_command(tmp_path):
    """Consult, delete, consult again, delete again — that sequence is the point."""
    records = [
        *ran(
            [*consulted_turn(), bash_call("git rm -r --cached tests/reports", "toolu_first")],
            "toolu_first",
        ),
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
    ]
    assert not denied(decide(tmp_path, records, command="rm -rf graphify-out"))


def test_a_harmless_command_after_a_destructive_one_is_not_taxed(tmp_path):
    """A guard that fires on ordinary work gets deleted, and then guards nothing."""
    records = ran(
        [*consulted_turn(), bash_call("git rm -r --cached tests/reports", "toolu_first")],
        "toolu_first",
    )
    assert not denied(decide(tmp_path, records, command="git status --porcelain"))


# ------------------------------- the arm must not count its OWN refusals as acts


def test_a_refused_destructive_command_does_not_count_as_one(tmp_path):
    """The deadlock this guard walked into on 2026-08-31.

    A refused `git commit` is still a `tool_use` record. Counting it made the
    refusal itself the reason for the next refusal: three consecutive attempts,
    each preceded by a correct fresh consult and a printed plan, each blocked by
    the previous block. There was no way out except editing the guard — which is
    class 17b of the ledger, a boundary check reading its own output as input.
    """
    records = [
        *consulted_turn(),
        bash_call("git commit --no-edit", "toolu_refused"),
        tool_result("toolu_refused", "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT.", True),
    ]
    assert not denied(decide(tmp_path, records, command="git commit --no-edit")), (
        "a command this guard REFUSED never ran, so it cannot be the destructive "
        "act that forces the next consult"
    )


def test_a_destructive_command_that_actually_RAN_still_counts(tmp_path):
    """The other direction, so the fix above cannot become a blanket exemption.
    A command that ran has a clean result in the turn — that is what "ran" means."""
    records = ran(
        [*consulted_turn(), bash_call("git rm -r --cached tests/reports", "toolu_ran")],
        "toolu_ran",
    )
    decision = decide(tmp_path, records, command="rm -rf specs/old")
    assert denied(decision)
    assert "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT." in reason(decision)


def test_two_destructive_calls_in_one_message_do_not_refuse_each_other(tmp_path):
    """The guard waits for the whole batch to land, so a sibling call issued in
    the same message is on disk with no result yet. It has not happened, and
    must not be read as the act that already ran on this consult."""
    records = [*consulted_turn(), bash_call("git commit --no-edit", "toolu_sibling")]
    assert not denied(decide(tmp_path, records, command="git push origin main"))


# ------------------------------------------ the transcript file lags the call
#
# MEASURED 2026-09-01, session a798c91b. Claude Code appends every block of an
# assistant message in one batch after the message completes, and the hook can
# run first: a Bash call's own record was stamped 22:13:21.918Z, the hook ran at
# 22:13:21.95Z and saw a file with no consult in it — the consult, its result and
# the plan were all in the same unlanded batch. Later the file held 392 records
# from 22:26:41Z until past 22:31Z while calls kept coming. So the guard waits
# for the record of the very call it is gating, and never stands down.


def test_the_guard_waits_for_the_gated_call_to_land(tmp_path):
    """The remedy is performed, the file is behind, and the guard waits for it."""
    transcript = tmp_path / "session.jsonl"
    write_transcript(transcript, [human(), grounding_call()])
    batch = [
        advisor_call(),
        advisor_result(),
        assistant_text(A_PRINTED_PLAN),
        gated_call("Bash", "ls -la", "toolu_late"),
    ]

    def land_later():
        time.sleep(0.4)
        with transcript.open("a") as handle:
            for record in batch:
                handle.write(json.dumps(record) + "\n")

    threading.Thread(target=land_later).start()
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
        "transcript_path": str(transcript),
        "session_id": "late",
        "tool_use_id": "toolu_late",
    }
    assert not denied(run_guard(payload, wait="5"))


def test_a_call_whose_record_never_lands_is_refused_and_says_so(tmp_path):
    """The verdict is about the file as it stood, and the refusal says exactly
    that, so the session retries instead of re-doing a remedy already done."""
    decision = decide(tmp_path, [human()], landed=False)
    assert denied(decision)
    assert "NO CONSULT, NO ACTION." in reason(decision)
    assert "THE TRANSCRIPT FILE HAD NOT CAUGHT UP" in reason(decision)


def test_a_refusal_carries_no_caught_up_note_when_the_file_is_current(tmp_path):
    decision = decide(tmp_path, [human()])
    assert denied(decision)
    assert "THE TRANSCRIPT FILE HAD NOT CAUGHT UP" not in reason(decision)


def test_refusals_never_stand_down_when_the_advisor_exists(tmp_path):
    """Owner ruling, 2026-09-01: "You must consult the advisor. Always." On a
    machine whose doctor report says the advisor tool exists, no number of
    refusals releases the gate."""
    for attempt in range(8):
        assert denied(decide(tmp_path, [human()], landed=False)), attempt
        assert denied(decide(tmp_path, [human()])), attempt


def test_a_consulting_session_is_never_released_even_when_the_doctor_cannot_tell(tmp_path):
    """One advisor record anywhere in the window proves the tool exists."""
    unknown = {"advisor": {"supported": "unknown"}}
    records = [human("earlier"), advisor_call(), advisor_result(), human("now")]
    for attempt in range(12):
        assert denied(decide(tmp_path, records, doctor=unknown)), attempt


def test_a_never_consulting_session_on_an_unknown_machine_is_released_late_and_loudly(tmp_path):
    """The co-founder case: a harness with no advisor tool, no CLI for the
    doctor to ask, and a gate whose only remedy is impossible. After
    RELEASE_AFTER_DENIALS refusals in one turn the gate lets the turn through
    with a diagnosis, and the next release costs twice as many."""
    unknown = {"advisor": {"supported": "unknown"}}
    first = [{**human(), "uuid": "turn-one"}]
    denials = 0
    released_at = None
    for attempt in range(1, 8):
        decision = decide(tmp_path, first, doctor=unknown)
        if denied(decision):
            denials += 1
        else:
            released_at = attempt
            assert "ADVISOR GATE RELEASED" in decision.get("systemMessage", "")
            break
    assert released_at == 6, (denials, released_at)
    # The re-arm: a new human message (its own uuid) resets the count, and the
    # threshold has doubled, so ten refusals in a row are all still refusals.
    again = [{**human("second ask"), "uuid": "turn-two"}]
    for attempt in range(10):
        assert denied(decide(tmp_path, again, doctor=unknown)), attempt


def test_a_machine_whose_harness_provably_lacks_the_advisor_is_disarmed_loudly(tmp_path):
    no = {"advisor": {"supported": "no", "why": "the harness does not know `claude-fable-5-1`"}}
    decision = decide(tmp_path, [human()], doctor=no)
    assert not denied(decision)
    assert "ADVISOR GATE DISARMED ON THIS MACHINE" in decision.get("systemMessage", "")


def advisor_error(model=FABLE):
    """A consult that came back as an error — the harness's own block type,
    read off the 2.1.259 binary's strings on 2026-09-02."""
    return assistant(
        [{"type": "advisor_tool_result_error", "tool_use_id": "srvtoolu_x",
          "content": {"error": "rate_limit_error", "message": "Fable quota exhausted"}}],
        model,
    )


def test_a_failed_consult_still_counts_and_routes_to_opus(tmp_path):
    """An error is the session having asked; it is not punished. The router
    flips the local advisorModel to opus and the guard says so."""
    records = [human(), grounding_call(), advisor_call(), advisor_error(),
               assistant_text(A_PRINTED_PLAN)]
    # As SessionStart leaves it: the router has decided fable and written it.
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "advisor-router.json").write_text(json.dumps({"model": "fable"}))
    (state / "settings.local.json").write_text(json.dumps({"advisorModel": "fable"}))
    decision = decide(tmp_path, records)
    assert not denied(decision)
    assert "routed to `opus`" in decision.get("systemMessage", "")
    local = json.loads((tmp_path / "state" / "settings.local.json").read_text())
    assert local["advisorModel"] == "opus"


def test_a_session_that_rewrites_its_own_advisor_model_is_overruled(tmp_path):
    """The working agent does not choose the advisor. A hand edit of
    settings.local.json is reset to the router's decision on the next act."""
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "advisor-router.json").write_text(json.dumps({"model": "fable"}))
    (state / "settings.local.json").write_text(json.dumps({"advisorModel": "sonnet"}))
    decision = decide(tmp_path, consulted_turn())
    assert not denied(decision)
    assert "ADVISOR MODEL RESET to `fable`" in decision.get("systemMessage", "")
    local = json.loads((state / "settings.local.json").read_text())
    assert local["advisorModel"] == "fable"


def test_an_empty_file_that_never_catches_up_is_refused_not_waved_through(tmp_path):
    """A brand-new session whose first records have not landed has asked for
    nothing the guard can see, and that is a refusal, not a pass."""
    decision = decide(tmp_path, [], landed=False)
    assert denied(decision)
    assert "THE TRANSCRIPT FILE HAD NOT CAUGHT UP" in reason(decision)


def test_a_turn_that_outgrew_the_window_is_judged_on_the_window(tmp_path):
    """No human record in view means the whole window is the turn: a consult
    must appear somewhere in it."""
    assert not denied(decide(tmp_path, consulted_turn()[1:]))
    assert denied(decide(tmp_path, [grounding_call()]))


def test_without_a_tool_use_id_the_file_is_judged_as_it_stands(tmp_path):
    """An older harness that stamps no id gets no wait — and no pass."""
    started = time.monotonic()
    decision = decide(tmp_path, [human()], tool_use_id=None, landed=False, wait="5")
    assert denied(decision)
    assert time.monotonic() - started < 2


# ------------------------------------------- spawned agents cannot consult
#
# MEASURED 2026-09-01: a subagent's PreToolUse payload carries
# `"agent_id": "a7a21be1cd7843808", "agent_type": "claude"` and names the MAIN
# session's transcript. The advisor is a server tool of the main session, so no
# subagent could ever satisfy this arm; the Agent call that spawned it was gated
# instead.


def test_a_spawned_agents_call_is_not_held_to_the_consult(tmp_path):
    stamp = {"agent_id": "a7a21be1cd7843808", "agent_type": "claude"}
    assert not denied(decide(tmp_path, [human()], payload_extra=stamp))


def test_either_agent_stamp_alone_is_enough(tmp_path):
    for stamp in ({"agent_id": "a7a21be1cd7843808"}, {"agent_type": "qa"}):
        assert not denied(decide(tmp_path, [human()], payload_extra=stamp)), stamp


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
    assert not denied(decide(tmp_path, [*consulted_turn(), compaction_summary()]))


def test_a_real_message_after_a_compaction_summary_still_ends_the_turn(tmp_path):
    """So the fix above cannot become a blanket exemption for `user` records."""
    records = [*consulted_turn(), compaction_summary(), human("second ask")]
    assert denied(decide(tmp_path, records))


def test_an_unfamiliar_user_record_still_counts_as_human(tmp_path):
    """The fail-loud default is untouched: the fix keys on a POSITIVE marker.

    A shape carrying neither `isCompactSummary` nor an origin stamp is exactly
    the case the default exists for — an unfamiliar record costs one extra
    consult rather than silently disarming the guard.
    """
    records = [
        *consulted_turn(),
        {"type": "user", "message": {"content": "[Request interrupted by user]"}},
    ]
    assert denied(decide(tmp_path, records))


# ------------------------------------------------------------- the Stop arm holds


def test_the_stop_arm_still_refuses_a_reply_with_no_consult(tmp_path):
    decision = decide(tmp_path, [human()], event="Stop")
    assert blocked(decision)
    assert "NO CONSULT, NO REPLY." in reason(decision)


def test_the_stop_arm_is_satisfied_by_a_consult(tmp_path):
    records = [human(), advisor_call(), advisor_result()]
    assert decide(tmp_path, records, event="Stop") == {}


def test_the_stop_arm_never_stands_down(tmp_path):
    """An earlier version let the fifth unconsulted reply through, in case the
    advisor was down. The owner's ruling leaves no such case."""
    for attempt in range(6):
        assert blocked(decide(tmp_path, [human()], event="Stop")), attempt


# ---------------------------------- the closing consult, off Fable
#
# OWNER RULING, 2026-09-01, for Opus or anything that is not Fable: "FORCE the
# model to ALWAYS check in with the advisor and then show the advisor that it
# listened. It should be blocked and should choke on itself until the advisor is
# happy." The advisor's answer is stored encrypted (every advisor result in this
# project's transcripts is an `advisor_redacted_result`), so what is enforced is
# the order of events: the last consult comes after the last action, with a
# report of the work written in front of it.


def opus_work():
    """A consulted, planned, executed turn on Opus — with the action's clean
    result, because a call that ran has one."""
    return ran(
        [*consulted_turn(OPUS), bash_call("uv run pytest tests/test_x.py", "toolu_work", OPUS)],
        "toolu_work",
    )


def test_off_fable_a_reply_after_an_action_needs_a_closing_consult(tmp_path):
    decision = decide(tmp_path, [*opus_work(), assistant_text("Done.", OPUS)], event="Stop")
    assert blocked(decision)
    assert "SHOW THE ADVISOR WHAT YOU DID." in reason(decision)


def test_off_fable_a_report_then_a_closing_consult_lets_the_reply_through(tmp_path):
    records = [
        *opus_work(),
        assistant_text(A_REPORT, OPUS),
        advisor_call(OPUS),
        advisor_result(OPUS),
        assistant_text("Done.", OPUS),
    ]
    assert decide(tmp_path, records, event="Stop") == {}


def test_off_fable_a_closing_consult_with_no_report_is_refused(tmp_path):
    records = [*opus_work(), advisor_call(OPUS), advisor_result(OPUS), assistant_text("Done.", OPUS)]
    decision = decide(tmp_path, records, event="Stop")
    assert blocked(decision)
    assert "THE ADVISOR WAS NOT SHOWN A REPORT." in reason(decision)


def test_off_fable_an_action_after_the_closing_consult_reopens_it(tmp_path):
    """"Fix this" from the advisor is an action, and an action needs showing."""
    records = ran(
        [
            *opus_work(),
            assistant_text(A_REPORT, OPUS),
            advisor_call(OPUS),
            advisor_result(OPUS),
            bash_call("uv run pytest tests/test_x.py", "toolu_fix", OPUS),
        ],
        "toolu_fix",
    )
    decision = decide(tmp_path, [*records, assistant_text("Fixed.", OPUS)], event="Stop")
    assert blocked(decision)
    assert "SHOW THE ADVISOR WHAT YOU DID." in reason(decision)


def test_off_fable_a_refused_action_is_not_the_last_action(tmp_path):
    """A call the guard itself refused changed nothing, so it needs no showing."""
    records = [
        *consulted_turn(OPUS),
        bash_call("git push", "toolu_refused", OPUS),
        tool_result("toolu_refused", "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT.", True),
        assistant_text("Held off.", OPUS),
    ]
    assert decide(tmp_path, records, event="Stop") == {}


def test_off_fable_a_turn_that_only_looked_needs_no_closing_consult(tmp_path):
    records = [*consulted_turn(OPUS), assistant_text("Here is the answer.", OPUS)]
    assert decide(tmp_path, records, event="Stop") == {}


def test_on_fable_the_closing_consult_is_not_demanded(tmp_path):
    records = ran(
        [*consulted_turn(), bash_call("uv run pytest tests/test_x.py", "toolu_work")],
        "toolu_work",
    )
    assert decide(tmp_path, [*records, assistant_text("Done.")], event="Stop") == {}


def test_a_session_with_no_readable_model_is_held_to_the_stricter_rule(tmp_path):
    records = ran(
        [*consulted_turn(None), bash_call("uv run pytest tests/test_x.py", "toolu_work", None)],
        "toolu_work",
    )
    decision = decide(tmp_path, [*records, assistant_text("Done.", None)], event="Stop")
    assert blocked(decision)
    assert "SHOW THE ADVISOR WHAT YOU DID." in reason(decision)


def test_a_synthetic_stub_does_not_change_the_sessions_model(tmp_path):
    """Read off the survey of 2026-09-01: the harness writes an assistant record
    with model "<synthetic>" in place of an answer when the API errors. A Fable
    session whose newest record is that stub is still a Fable session."""
    records = ran(
        [*consulted_turn(), bash_call("uv run pytest tests/test_x.py", "toolu_work")],
        "toolu_work",
    )
    records += [assistant_text("Done.", model="<synthetic>")]
    assert decide(tmp_path, records, event="Stop") == {}
