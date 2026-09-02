"""Payload tests for .claude/hooks/pre-shadow-check.py.

The guard is a PreToolUse hook on `Agent`, awake only when the spawn names the
shadow. It asks four questions of the turn's own work before the expensive
verifier starts, numbered here as the sections below number them: do this
turn's `path:NN` citations still resolve (1), is every number in the shadow's
prompt present in a tool result from this turn (2), if the engine was edited is
its guard still green (3), and is every COMMIT ID in that prompt present in a
CLEAN tool result from this turn (4).

Check 4 arrived 2026-09-02 and its section is at the foot of this file. Check 2
cannot stand in for it. `_quantity_of` reads a token as a quantity only when it
begins with a digit AND every letter in it sits after the last digit, so the
ordinary hash shapes are invisible to it. Driven, not reasoned about:

    c0f77e1a    check 2 sees nothing        check 4 catches it
    7a5b01c8    check 2 sees nothing        check 4 catches it
    deadbeef    check 2 sees nothing        check 4 catches it
    1234567a    check 2 reads 1234567       check 4 catches it too
    12345678    check 2 reads 12345678      check 4 ignores it

Two shapes are therefore NOT covered by check 4 alone, and neither costs
anything: a digits-then-letters hash is seen by both arms, and an all-digit
hash is just a large integer, which is what check 2 is for. An earlier draft of
this paragraph claimed the all-digit case was the only exception; a verifier
drove `1234567a` and disproved it.

EVERY RECORD SHAPE HERE WAS COPIED FROM test_advisor_consult_guard.py, which
measured them off this project's real transcripts (session 710b5e6a on
2026-08-29, session a798c91b on 2026-09-01). Not one is invented. That guard's
docstring records why: its own first version looked for
``{"type": "tool_use", "name": "advisor"}`` when the advisor actually records as
``server_tool_use``, so it blocked every reply — and all thirteen of its tests
passed, because they were built from the same assumed shape. A fixture invented
alongside the code it tests proves only that the two agree with each other.

    human      {"type": "user", "origin": {"kind": "human"},
                "message": {"content": "<a string, not a list>"}}
    text       {"type": "assistant", "message": {"model": "claude-opus-5",
                "content": [{"type": "text", "text": "..."}]}}
    tool call  {"type": "assistant", "message": {"content": [
                   {"type": "tool_use", "id": "toolu_...", "name": "Write",
                    "input": {...}}]}}
    result     {"type": "user", "message": {"content": [
                   {"type": "tool_result", "tool_use_id": "toolu_...",
                    "content": "...", "is_error": <true only when refused/failed>}]}}

The project root and the ceiling's state directory are both redirected into
tmp_path, so no test reads or writes the real repository.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / ".claude" / "hooks" / "pre-shadow-check.py"

OPUS = "claude-opus-5"


# ---------------------------------------------------------------- record shapes


def human(text="do the thing"):
    return {"type": "user", "origin": {"kind": "human"}, "message": {"content": text}}


def assistant(blocks, model=OPUS):
    return {"type": "assistant", "message": {"model": model, "content": blocks}}


def assistant_text(text, model=OPUS):
    return assistant([{"type": "text", "text": text}], model)


def tool_call(name, tool_input, call_id="toolu_x", model=OPUS):
    return assistant(
        [{"type": "tool_use", "id": call_id, "name": name, "input": tool_input}], model
    )


def tool_result(call_id, text="ok", is_error=False):
    """How a call's result comes back. `is_error: true` is a refusal or a
    failure; a clean result is the proof that the call actually ran."""
    block = {"type": "tool_result", "tool_use_id": call_id, "content": text}
    if is_error:
        block["is_error"] = True
    return {"type": "user", "message": {"content": [block]}}


def wrote(path, call_id, evidence="ok"):
    """A Write that RAN: the call, then its clean result."""
    return [
        tool_call("Write", {"file_path": str(path), "content": "x"}, call_id),
        tool_result(call_id, evidence),
    ]


# ---------------------------------------------------------------------- harness


def run_guard(payload, state_dir, root):
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=180,
        env={
            **os.environ,
            "ONDOWAY_SHADOW_STATE_DIR": str(state_dir),
            "CLAUDE_PROJECT_DIR": str(root),
        },
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else {}


def decide(
    tmp_path,
    records,
    *,
    prompt="Verify the turn.",
    subagent_type="shadow",
    tool="Agent",
    root=None,
    session="s1",
):
    """Run the guard over `records` and return its decision ({} means allowed)."""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {
            "subagent_type": subagent_type,
            "prompt": prompt,
            "description": "verify",
        },
        "transcript_path": str(transcript),
        "session_id": session,
        "tool_use_id": "toolu_gated",
    }
    return run_guard(payload, tmp_path / "state", root or (tmp_path / "root"))


def denied(decision):
    return decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def reason(decision):
    out = decision.get("hookSpecificOutput", {})
    return out.get("permissionDecisionReason") or decision.get("systemMessage", "")


def make_root(tmp_path):
    root = tmp_path / "root"
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    return root


# ------------------------------------------------------ check 1: citations resolve
#
# The failure it removes, measured 2026-09-01: about twenty `path:NN` citations
# in one turn stopped resolving because a 113-line insertion in the session's own
# edit pushed every line below it down. The shadow spent its whole run finding
# that out.


def test_a_citation_past_the_end_of_the_file_is_refused(tmp_path):
    root = make_root(tmp_path)
    (root / "engine.py").write_text("one\ntwo\nthree\n")
    report = root / "report.md"
    report.write_text("The bug is at engine.py:214, in the loop.\n")

    decision = decide(tmp_path, [human(), *wrote(report, "toolu_md")], root=root)
    assert denied(decision)
    assert "BROKEN CITATIONS" in reason(decision)
    assert "engine.py:214" in reason(decision)
    assert "that file has 4 lines" in reason(decision)


def test_a_citation_that_still_resolves_is_not_refused(tmp_path):
    root = make_root(tmp_path)
    (root / "engine.py").write_text("one\ntwo\nthree\n")
    report = root / "report.md"
    report.write_text("The bug is at engine.py:2, in the loop.\n")

    assert not denied(decide(tmp_path, [human(), *wrote(report, "toolu_md")], root=root))


def test_a_citation_with_a_sentence_ending_period_is_still_read(tmp_path):
    """The exact hole that silently disarmed citation-guard.py's pattern on
    2026-08-29: `provider.py:222.` stopped being a citation and the arm went
    quiet. Tokens are trimmed rather than matched, so the period is punctuation."""
    root = make_root(tmp_path)
    (root / "provider.py").write_text("one\n")
    report = root / "report.md"
    report.write_text("It is wrong in provider.py:222.\n")

    decision = decide(tmp_path, [human(), *wrote(report, "toolu_md")], root=root)
    assert denied(decision)
    assert "provider.py:222" in reason(decision)


def test_a_refused_write_is_not_a_file_this_turn_wrote(tmp_path):
    """The guard must not count its own output as input — class 17b of the
    failures ledger, the self-deadlock the advisor guard walked into on
    2026-08-31 by reading a `git commit` it had itself refused as one that ran.
    A Write that came back an error put nothing on disk."""
    root = make_root(tmp_path)
    report = root / "report.md"
    report.write_text("Broken citation at engine.py:999.\n")
    records = [
        human(),
        tool_call("Write", {"file_path": str(report), "content": "x"}, "toolu_refused"),
        tool_result("toolu_refused", "denied by a hook", is_error=True),
    ]
    assert not denied(decide(tmp_path, records, root=root))


# ------------------------------------------------- check 2: numbers are sourced
#
# The failures it removes, measured 2026-09-01: a stale test count, "four
# refused" when the transcript held nine, "three coding rules" when the file has
# seven. Every one of them a figure restated from memory rather than re-derived.


def test_a_number_in_no_tool_result_is_refused(tmp_path):
    root = make_root(tmp_path)
    records = [human(), assistant_text("Ran the suite."), tool_result("toolu_run", "12 passed")]
    decision = decide(
        tmp_path, records, prompt="Verify that 47 tests passed after the change.", root=root
    )
    assert denied(decision)
    assert "UNSOURCED NUMBERS" in reason(decision)
    assert "47" in reason(decision)


def test_a_number_present_in_a_tool_result_is_allowed(tmp_path):
    root = make_root(tmp_path)
    records = [human(), tool_result("toolu_run", "47 passed in 3.21s")]
    assert not denied(
        decide(tmp_path, records, prompt="Verify that 47 tests passed.", root=root)
    )


def test_small_numbers_and_years_assert_nothing(tmp_path):
    """A guard that fires on ordinary prose is a guard that gets deleted."""
    root = make_root(tmp_path)
    records = [human(), tool_result("toolu_run", "ok")]
    prompt = "Check the 3 files changed on 2026-09-01 against the 2 claims made."
    assert not denied(decide(tmp_path, records, prompt=prompt, root=root))


def test_a_prefix_of_a_bigger_number_does_not_source_it(tmp_path):
    """21 is not proven by 210: the evidence is searched for the digits as
    written, so a number that merely looks similar cannot pay for a claim."""
    root = make_root(tmp_path)
    records = [human(), tool_result("toolu_run", "210 files scanned")]
    decision = decide(tmp_path, records, prompt="The shadow ran 21 times.", root=root)
    assert denied(decision)
    assert "21" in reason(decision)


def test_a_citation_line_number_in_the_prompt_is_not_an_unsourced_claim(tmp_path):
    """Check 1 already resolves those against the files. A line number is a
    location, not a quantity, and must not be refused twice."""
    root = make_root(tmp_path)
    records = [human(), tool_result("toolu_run", "ok")]
    prompt = "Confirm the fix at engine.py:214 is the one described."
    assert not denied(decide(tmp_path, records, prompt=prompt, root=root))


# -------------------------------------------- check 3: the engine guard is fresh
#
# The failure it removes: "the engine is green" when the guard was never re-run
# after the edit. The guard is hermetic node over one file, so running it here
# costs seconds against the shadow's mean of 386.


def test_editing_the_engine_without_a_green_guard_is_refused(tmp_path):
    root = make_root(tmp_path)
    engine = root / ".claude" / "team-engine.js"
    engine.write_text("// changed\n")
    (root / ".claude" / "team-engine.test.js").write_text(
        "console.error('assertion failed: plan step count');\nprocess.exit(1);\n"
    )
    records = [human(), *wrote(engine, "toolu_engine")]
    decision = decide(tmp_path, records, root=root)
    assert denied(decision)
    assert "THE ENGINE GUARD IS NOT GREEN." in reason(decision)
    assert "assertion failed" in reason(decision)


def test_editing_the_engine_with_a_green_guard_is_allowed(tmp_path):
    root = make_root(tmp_path)
    engine = root / ".claude" / "team-engine.js"
    engine.write_text("// changed\n")
    (root / ".claude" / "team-engine.test.js").write_text("process.exit(0);\n")
    assert not denied(decide(tmp_path, [human(), *wrote(engine, "toolu_engine")], root=root))


def test_a_turn_that_did_not_touch_the_engine_never_runs_its_guard(tmp_path):
    """A red engine guard is not this turn's problem when this turn did not
    touch the engine."""
    root = make_root(tmp_path)
    (root / ".claude" / "team-engine.test.js").write_text("process.exit(1);\n")
    records = [human(), *wrote(root / "notes.txt", "toolu_other")]
    assert not denied(decide(tmp_path, records, root=root))


# --------------------------------------------------------------- clean, and asleep


def test_a_clean_turn_lets_the_shadow_spawn(tmp_path):
    root = make_root(tmp_path)
    (root / "engine.py").write_text("one\ntwo\nthree\n")
    report = root / "report.md"
    report.write_text("Fixed at engine.py:2. The suite reported 47 passing.\n")
    records = [human(), *wrote(report, "toolu_md", "47 passed in 3.21s")]
    assert decide(tmp_path, records, prompt="Verify 47 passing.", root=root) == {}


def test_a_turn_with_no_writes_at_all_is_clean(tmp_path):
    assert decide(tmp_path, [human(), assistant_text("Read three files.")]) == {}


def test_a_spawn_that_is_not_the_shadow_is_not_checked(tmp_path):
    """The guard is scoped to one agent type. Every other spawn goes through
    untouched, however broken the turn is."""
    root = make_root(tmp_path)
    report = root / "report.md"
    report.write_text("Broken at engine.py:999.\n")
    records = [human(), *wrote(report, "toolu_md")]
    for other in ("qa", "judge", "skeptic", "general-purpose"):
        decision = decide(tmp_path, records, subagent_type=other, root=root, session=other)
        assert decision == {}, other


def test_a_tool_that_is_not_agent_is_not_checked(tmp_path):
    root = make_root(tmp_path)
    report = root / "report.md"
    report.write_text("Broken at engine.py:999.\n")
    records = [human(), *wrote(report, "toolu_md")]
    assert decide(tmp_path, records, tool="Bash", root=root) == {}


# --------------------------------------------------------------------- ceiling
#
# A guard that cannot be satisfied wedges the session, and this project has
# shipped that failure twice. Three refusals in one turn and this one stands
# down and lets the shadow judge the work itself.


def test_it_stands_down_after_three_refusals_in_one_turn(tmp_path):
    root = make_root(tmp_path)
    report = root / "report.md"
    report.write_text("Broken at engine.py:999.\n")
    records = [human(), *wrote(report, "toolu_md")]

    for attempt in range(3):
        assert denied(decide(tmp_path, records, root=root)), attempt

    fourth = decide(tmp_path, records, root=root)
    assert not denied(fourth)
    assert "PRE-SHADOW CHECK STOOD DOWN." in reason(fourth)


def test_a_new_human_message_re_arms_the_ceiling(tmp_path):
    """The tally is per TURN. New words from the owner are new work to check,
    so the stand-down does not carry into them."""
    root = make_root(tmp_path)
    report = root / "report.md"
    report.write_text("Broken at engine.py:999.\n")
    records = [human(), *wrote(report, "toolu_md")]

    for _ in range(4):
        decide(tmp_path, records, root=root)

    next_turn = [
        {"type": "user", "origin": {"kind": "human"}, "message": {"content": "again"},
         "uuid": "second-ask"},
        *wrote(report, "toolu_md2"),
    ]
    assert denied(decide(tmp_path, [*records, *next_turn], root=root))


# ------------------------------------------------------- numbers inside tokens
#
# These five reach INTO the hook rather than driving it as a subprocess: the
# unit under test is one pure function over two strings, and a payload round
# trip would only obscure which half was wrong.

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location(
    "pre_shadow_check", Path(__file__).resolve().parents[1] / "pre-shadow-check.py")
check = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(check)


def test_a_uuid_in_the_transcript_path_is_not_a_claim():
    """The guard's own first live firing, 2026-09-02.

    A shadow prompt MUST carry the session transcript path, and that path holds
    a uuid. Walked character by character it yields three numbers no tool result
    could ever source, in a path that cannot be removed. The guard refused a
    spawn it had made impossible to satisfy — the unsatisfiable-boundary failure
    its own docstring says this project has shipped twice before.
    """
    prompt = (
        "SESSION TRANSCRIPT: /Users/x/.claude/projects/-Users-x-git-ondoway/"
        "1d64ca6b-bc57-436b-ae8b-ac6bad8eecaf.jsonl\nVerify the three fixes."
    )
    assert check.unsourced_numbers(prompt, "no numbers here at all") == []


def test_a_number_inside_an_identifier_is_not_a_claim():
    for text in ("sha256 of the output", "commit 9525b4a5 landed",
                 "read .claude/team-engine.test.js"):
        assert check.unsourced_numbers(text, "") == []


def test_a_bare_number_is_still_a_claim():
    assert check.unsourced_numbers("329 passed", "") == ["329"]


def test_a_bare_number_present_in_the_evidence_passes():
    assert check.unsourced_numbers("329 passed", "the run printed 329 passed") == []


def test_a_number_written_with_separators_is_still_a_claim():
    assert check.unsourced_numbers("5,070 insertions", "") == ["5070"]


def test_a_figure_with_a_unit_or_a_prefix_is_still_a_claim():
    """The over-correction, caught by a verifier on 2026-09-02.

    The first fix for the uuid case demanded the whole token be digits, which
    silently stopped counting every ordinary spelling of a figure — including
    three this guard's own docstring uses. A report saying "61% of the time"
    is asserting 61 exactly as much as one saying "61 percent".
    """
    for text, want in (
        ("61% of the time", ["61"]),
        ("21.9 minutes median", ["21"]),
        ("386s mean", ["386"]),
        ("334ms latency", ["334"]),
        ("n=512 samples", ["512"]),
        ("#512 filed", ["512"]),
        ("$4200 spent", ["4200"]),
        ("512/600 files", ["512", "600"]),
    ):
        assert check.unsourced_numbers(text, "") == want, text


# ------------------------------------------------ check 4: commit ids are sourced
#
# The failure it removes, measured 2026-09-02 in this guard's own session. Three
# shadow runs were spent, ~400 seconds each, and every one rejected on the same
# shape: a commit id written into the shadow's prompt that no command in that turn
# had produced. `HEAD is c0f77e1a` was stated while HEAD was already two commits
# further on, because a parallel session was committing into the same worktree.
#
# Check 2 cannot see these. `_quantity_of` requires the token to START with a
# digit and carry no letters between digit runs, so `c0f77e1a` (leading letter)
# and `7a5b01c8` (letters between digits) are both rejected as identifiers before
# any freshness question is asked.


def test_a_commit_id_in_no_tool_result_is_refused(tmp_path):
    """The exact rejection of 2026-09-02: HEAD restated from memory."""
    root = make_root(tmp_path)
    records = [human(), tool_result("toolu_run", "nothing to report")]
    decision = decide(tmp_path, records, prompt="Verify HEAD is c0f77e1a.", root=root)
    assert denied(decision)
    assert "UNSOURCED COMMIT IDS" in reason(decision)
    assert "c0f77e1a" in reason(decision)


def test_a_commit_id_a_command_produced_this_turn_is_allowed(tmp_path):
    root = make_root(tmp_path)
    records = [human(), tool_result("toolu_run", "c0f77e1a40b17ef chore: sweep")]
    assert not denied(
        decide(tmp_path, records, prompt="Verify HEAD is c0f77e1a.", root=root)
    )


def test_a_full_id_the_evidence_only_abbreviated_is_allowed(tmp_path):
    """git prints short hashes. Expanding what was seen is not a stale claim."""
    root = make_root(tmp_path)
    records = [human(), tool_result("toolu_run", "On 7a5b01c8 feat(guards): three fixes")]
    prompt = "Verify origin/main is 7a5b01c8a4bb9eabd4ec0d9ef5f8f64f218c8fa2."
    assert not denied(decide(tmp_path, records, prompt=prompt, root=root))


def test_an_id_only_in_a_refused_calls_output_is_still_unsourced(tmp_path):
    """Class 17b of the failures ledger — a boundary check reading its own
    output as input. This guard's own denial quotes the id back, and that
    denial lands as an errored tool_result. Counting it would make the second
    attempt pass on the strength of the first refusal."""
    root = make_root(tmp_path)
    records = [
        human(),
        tool_result("toolu_denied", "UNSOURCED COMMIT IDS (1): c0f77e1a", is_error=True),
    ]
    decision = decide(tmp_path, records, prompt="Verify HEAD is c0f77e1a.", root=root)
    assert denied(decision)
    assert "c0f77e1a" in reason(decision)


def test_an_agent_id_the_shadow_itself_returned_is_sourced(tmp_path):
    """A real shadow result ends with `agentId: a27ba936ffef8287a`, which is
    17 hex characters and reads exactly like a short commit id. Quoting it back
    in the next prompt must not be refused — it came from a tool result."""
    root = make_root(tmp_path)
    evidence = "VERDICT: CONFIRMED\nagentId: a27ba936ffef8287a"
    records = [human(), tool_result("toolu_shadow", evidence)]
    prompt = "Continue from agent a27ba936ffef8287a."
    assert not denied(decide(tmp_path, records, prompt=prompt, root=root))


def test_the_session_transcript_uuid_is_not_a_commit_id(tmp_path):
    """Every shadow prompt must carry the transcript path, and that path holds
    a uuid. Its hyphens keep it out of hex, so it is never extracted — the same
    unsatisfiable-boundary trap check 2 fell into on this guard's first firing."""
    root = make_root(tmp_path)
    records = [human(), tool_result("toolu_run", "ok")]
    prompt = (
        "SESSION TRANSCRIPT: /Users/x/.claude/projects/-Users-x-git-ondoway/"
        "3a897d67-31dc-4c44-b1c8-cff25af0f76d.jsonl\nVerify the fix."
    )
    assert not denied(decide(tmp_path, records, prompt=prompt, root=root))


def test_an_ordinary_word_is_not_a_commit_id():
    """Seven-plus letters that all happen to be hex: `deadbeef`, `decade`,
    `facade`. The first is a real hex word and IS treated as an id; the guard
    accepts that cost because the remedy is to run a command. What must not
    happen is a normal English word being read as one."""
    for text in ("the facade of it", "a decade later", "added and deleted"):
        assert check.unsourced_shas(text, "") == [], text


def test_a_commit_id_is_reported_once_however_often_it_is_repeated():
    prompt = "c0f77e1a landed, then c0f77e1a was pushed, and c0f77e1a is HEAD."
    assert check.unsourced_shas(prompt, "") == ["c0f77e1a"]


def test_punctuation_around_an_id_is_not_part_of_it():
    """`(c0f77e1a)` and `c0f77e1a.` are the same id as `c0f77e1a`."""
    for text in ("HEAD is (c0f77e1a)", "HEAD is c0f77e1a.", "HEAD is `c0f77e1a`"):
        assert check.unsourced_shas(text, "") == ["c0f77e1a"], text


def test_a_sibling_guard_that_exits_on_import_does_not_kill_this_one(tmp_path):
    """Found by a verifier on 2026-09-02, which DROVE the case instead of
    reading it: importing a module runs its top level, so a sibling guard
    calling sys.exit() there raises SystemExit — and `except Exception` lets
    that straight through, killing this hook with a non-zero exit and no JSON
    on stdout. The borrow must survive it and disarm its own arm instead.

    Driven against a COPY of the hooks directory so the real freshness-gate.py
    is untouched.
    """
    fake = tmp_path / "hooks"
    fake.mkdir()
    (fake / "freshness-gate.py").write_text("import sys\nsys.exit(3)\n")
    (fake / "pre-shadow-check.py").write_text(GUARD.read_text(encoding="utf-8"))

    root = make_root(tmp_path)
    transcript = tmp_path / "session.jsonl"
    records = [human(), tool_result("toolu_run", "nothing to report")]
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": {
            "subagent_type": "shadow",
            "prompt": "Verify HEAD is c0f77e1a.",
            "description": "verify",
        },
        "transcript_path": str(transcript),
        "session_id": "exiting-sibling",
        "tool_use_id": "toolu_gated",
    }
    done = subprocess.run(
        [sys.executable, str(fake / "pre-shadow-check.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=180,
        env={
            **os.environ,
            "ONDOWAY_SHADOW_STATE_DIR": str(tmp_path / "state"),
            "CLAUDE_PROJECT_DIR": str(root),
        },
    )
    assert done.returncode == 0, (done.returncode, done.stderr)
    decision = json.loads(done.stdout) if done.stdout.strip() else {}
    assert not denied(decision)
    assert "commit-id arm is OFF" in reason(decision)
