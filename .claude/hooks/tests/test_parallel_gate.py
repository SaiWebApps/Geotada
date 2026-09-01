"""Payload tests for .claude/hooks/parallel-gate.py.

The guard is a PreToolUse hook: it either lets a `run_in_background: true`
`Agent`/`Bash` call through or denies it as the avoidable second half of a
pair that should have been one message. Four conditions gate the denial — see
the guard's own module docstring — and every one of them gets a test that
must deny and a test that must not, because a starved condition looks exactly
like a satisfied one until something measures it.

THE MESSAGE-ID EVIDENCE IS MEASURED, not invented. Read directly off this
project's own session transcript, 2026-08-31 (session
0e1421c4-69ff-4adf-ab04-810cb7af3436): a `thinking` block and the `tool_use`
block that followed it in one turn shared `message.id`
`msg_011CebcSpTpmJEvR7XxrcUVN`; the NEXT tool call's own leading `thinking`
block carried a different id, `msg_011CebcTcp7pYsAq74s9UYku`. The fixtures
below use short synthetic ids (`msg_1`, `msg_2`, ...) for readability, but the
property under test — same id within one inference, different id across two —
is the measured one.

The noise-record fixture (`last-prompt`, `attachment`, `agent-name`,
`bridge-session`) is not invented either: those are the exact non-`user`/
non-`assistant` top-level types this project's real transcripts carry as
harness bookkeeping, interleaved with the records that matter.

Record shapes otherwise follow the sibling guards' own measured fixtures:

    human       {"type": "user", "origin": {"kind": "human"},
                 "message": {"content": "<a string>"}}
    assistant   {"type": "assistant",
                 "message": {"id": "<msg id>", "content": [<one block>]}}
    tool_use    {"type": "tool_use", "id": "<call id>", "name": "...",
                 "input": {...}}
    tool_result {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "<call id>",
                     "content": "...", "is_error": <bool, only when true>}]}}
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
GUARD = REPO / ".claude" / "hooks" / "parallel-gate.py"


# ---------------------------------------------------------------- record shapes


def human(text="do the thing"):
    return {"type": "user", "origin": {"kind": "human"}, "message": {"content": text}}


def assistant_block(block, message_id):
    return {"type": "assistant", "message": {"id": message_id, "content": [block]}}


def thinking(message_id="msg_2"):
    return assistant_block({"type": "thinking", "thinking": "hmm"}, message_id)


def tool_use(name, call_id, message_id, **input_fields):
    return assistant_block(
        {"type": "tool_use", "id": call_id, "name": name, "input": input_fields},
        message_id,
    )


def bg_spawn(name="Agent", call_id="toolu_bg", message_id="msg_1", **extra_input):
    fields = {"run_in_background": True, "description": "x", "prompt": "y"}
    fields.update(extra_input)
    if name == "Bash":
        fields.pop("description", None)
        fields.pop("prompt", None)
        fields.setdefault("command", "sleep 100")
    return tool_use(name, call_id, message_id, **fields)


def tool_result(call_id, text="ok", is_error=False):
    block = {"type": "tool_result", "tool_use_id": call_id, "content": text}
    if is_error:
        block["is_error"] = True
    return {"type": "user", "message": {"content": [block]}}


def launched(call_id):
    return tool_result(call_id, "Async agent launched successfully.")


def refused(call_id, text="NO CONSULT, NO ACTION."):
    return tool_result(call_id, text, is_error=True)


def noise(kind):
    """A harness bookkeeping row — measured shape, see module docstring."""
    return {"type": kind}


# ---------------------------------------------------------------------- harness


def decide(tmp_path, records, *, tool="Agent", tool_input=None, session=None):
    """Run the guard over `records` and return its decision ({} means allowed)."""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": tool_input if tool_input is not None else {"run_in_background": True},
        "transcript_path": str(transcript),
        "session_id": session or f"test-{tmp_path.name}",
    }
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "ONDOWAY_PARALLEL_GATE_STATE": str(tmp_path / "state.json")},
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else {}


def raw(tmp_path, stdin_text, *, env_extra=None):
    """Run the guard over a raw stdin payload, bypassing `decide`'s JSON shape."""
    env = {**os.environ, "ONDOWAY_PARALLEL_GATE_STATE": str(tmp_path / "state.json")}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def denied(decision):
    return decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"


def reason(decision):
    out = decision.get("hookSpecificOutput", {})
    return out.get("permissionDecisionReason") or ""


# ------------------------------------------------------------- condition 1: scope


def test_a_solo_background_spawn_with_no_prior_is_allowed(tmp_path):
    assert not denied(decide(tmp_path, [human()]))


def test_a_foreground_call_is_never_gated_even_with_an_unreadable_transcript(tmp_path):
    """Bailing before the transcript is read: a nonexistent path must not matter."""
    done = raw(
        tmp_path,
        json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Agent",
                "tool_input": {"run_in_background": False},
                "transcript_path": str(tmp_path / "does-not-exist.jsonl"),
                "session_id": "s",
            }
        ),
    )
    assert done.returncode == 0, done.stderr
    assert not done.stdout.strip(), "a bare allow prints nothing"


def test_unrelated_tools_are_never_gated(tmp_path):
    done = raw(
        tmp_path,
        json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Read",
                "tool_input": {"file_path": "/x"},
                "transcript_path": str(tmp_path / "does-not-exist.jsonl"),
                "session_id": "s",
            }
        ),
    )
    assert done.returncode == 0, done.stderr
    assert not done.stdout.strip()


def test_run_in_background_omitted_is_out_of_scope(tmp_path):
    """Deliberate: omitted is not inferred as background, only `True` is."""
    records = [human(), bg_spawn(call_id="toolu_prior"), launched("toolu_prior"), thinking()]
    decision = decide(tmp_path, records, tool_input={"description": "x", "prompt": "y"})
    assert not denied(decision)


def test_run_in_background_false_is_out_of_scope(tmp_path):
    records = [human(), bg_spawn(call_id="toolu_prior"), launched("toolu_prior"), thinking()]
    decision = decide(tmp_path, records, tool_input={"run_in_background": False})
    assert not denied(decision)


# --------------------------------------------------------- the pattern itself


def test_two_background_spawns_in_separate_messages_with_nothing_between_is_denied(tmp_path):
    records = [human(), bg_spawn(call_id="toolu_prior"), launched("toolu_prior"), thinking()]
    decision = decide(tmp_path, records)
    assert denied(decision)
    assert "batch them into one message" in reason(decision)


def test_a_bash_background_spawn_is_covered_too(tmp_path):
    records = [
        human(),
        bg_spawn(name="Bash", call_id="toolu_prior", command="sleep 100"),
        launched("toolu_prior"),
        thinking(),
    ]
    decision = decide(
        tmp_path, records, tool="Bash", tool_input={"command": "sleep 200", "run_in_background": True}
    )
    assert denied(decision)


# ---------------------------------------------------- condition 4: same inference


def test_two_background_spawns_sharing_one_message_id_is_allowed(tmp_path):
    """The batched case: a record after P shares P's OWN message id."""
    records = [
        human(),
        bg_spawn(call_id="toolu_prior", message_id="msg_1"),
        launched("toolu_prior"),
        thinking(message_id="msg_1"),  # same id as P — one inference, not two
    ]
    assert not denied(decide(tmp_path, records))


def test_nothing_at_all_after_the_prior_spawn_is_allowed(tmp_path):
    """No evidence of a new inference at all — the safe, can't-tell direction."""
    records = [human(), bg_spawn(call_id="toolu_prior"), launched("toolu_prior")]
    assert not denied(decide(tmp_path, records))


# -------------------------------------------------- condition 3: real work between


def test_real_work_between_two_spawns_is_allowed(tmp_path):
    records = [
        human(),
        bg_spawn(call_id="toolu_prior", message_id="msg_1"),
        launched("toolu_prior"),
        tool_use("Read", "toolu_read", "msg_2", file_path="/x"),
        tool_result("toolu_read", "file contents"),
    ]
    assert not denied(decide(tmp_path, records))


def test_the_most_recent_spawn_is_compared_against_not_the_first(tmp_path):
    """Real work followed the FIRST spawn, but nothing followed the SECOND —
    the current call must be judged against the second, not exonerated by the
    first's history."""
    records = [
        human(),
        bg_spawn(call_id="toolu_A", message_id="msg_1"),
        launched("toolu_A"),
        tool_use("Read", "toolu_read", "msg_2", file_path="/x"),
        tool_result("toolu_read", "ok"),
        bg_spawn(call_id="toolu_B", message_id="msg_3"),
        launched("toolu_B"),
        thinking(message_id="msg_4"),
    ]
    assert denied(decide(tmp_path, records))


# ---------------------------------------------------- condition 2: refused spawns


def test_a_refused_prior_spawn_does_not_count(tmp_path):
    records = [human(), bg_spawn(call_id="toolu_refused"), refused("toolu_refused"), thinking()]
    decision = decide(tmp_path, records)
    assert not denied(decision), "a refused spawn never ran and is not a valid prior"


def test_denying_once_lets_the_retry_through(tmp_path):
    """The self-clearing mechanism the module docstring describes: this
    gate's own denial writes an is_error tool_result for the SECOND call,
    which is itself 'a tool_result after P that is not P's own' — so the
    retry no longer sees 'nothing else completed' and is judged fresh."""
    records = [
        human(),
        bg_spawn(call_id="toolu_prior", message_id="msg_1"),
        launched("toolu_prior"),
        thinking(message_id="msg_2"),
        bg_spawn(call_id="toolu_denied", message_id="msg_2"),
        refused("toolu_denied"),  # this gate's own earlier denial, now on disk
    ]
    decision = decide(tmp_path, records)
    assert not denied(decision), "the retry must not be denied a second time"


# ------------------------------------------------------------------ turn scoping


def test_a_new_human_turn_resets_the_comparison(tmp_path):
    records = [
        human("first ask"),
        bg_spawn(call_id="toolu_prior", message_id="msg_1"),
        launched("toolu_prior"),
        human("second ask"),
        thinking(message_id="msg_2"),
    ]
    decision = decide(tmp_path, records)
    assert not denied(decision), "a spawn from an earlier turn must not tax this one"


# --------------------------------------------------------------------- the ceiling


DENY_SHAPE = [human(), bg_spawn(call_id="toolu_prior"), launched("toolu_prior"), thinking()]


def test_the_ceiling_stands_the_arm_down_after_three_denials(tmp_path):
    for attempt in range(3):
        assert denied(decide(tmp_path, DENY_SHAPE, session="wedged")), attempt
    decision = decide(tmp_path, DENY_SHAPE, session="wedged")
    assert not denied(decision)
    assert "PARALLEL GATE STOOD DOWN" in decision.get("systemMessage", "")


def test_an_allowed_call_clears_the_tally(tmp_path):
    allow_shape = [human(), bg_spawn(call_id="toolu_prior"), launched("toolu_prior")]
    assert denied(decide(tmp_path, DENY_SHAPE, session="mixed"))
    assert denied(decide(tmp_path, DENY_SHAPE, session="mixed"))
    assert not denied(decide(tmp_path, allow_shape, session="mixed"))
    # tally cleared: two more denials must not trip a ceiling of three
    assert denied(decide(tmp_path, DENY_SHAPE, session="mixed"))
    assert denied(decide(tmp_path, DENY_SHAPE, session="mixed"))


# -------------------------------------------------------------- noise and malformity


def test_unknown_noise_record_types_are_ignored(tmp_path):
    records = [
        human(),
        noise("last-prompt"),
        bg_spawn(call_id="toolu_prior"),
        noise("attachment"),
        launched("toolu_prior"),
        noise("agent-name"),
        thinking(),
        noise("bridge-session"),
    ]
    decision = decide(tmp_path, records)
    assert denied(decision), "noise records must not hide the real pattern"


def test_a_malformed_payload_does_not_crash(tmp_path):
    for text in ("null", "42", '"a string"', "[]", "not json at all"):
        done = raw(tmp_path, text)
        assert done.returncode == 0, f"{text!r}: {done.stderr}"
        assert not done.stdout.strip(), f"{text!r}: should allow silently"


def test_missing_tool_input_does_not_crash(tmp_path):
    done = raw(
        tmp_path,
        json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Agent",
                "transcript_path": str(tmp_path / "does-not-exist.jsonl"),
                "session_id": "s",
            }
        ),
    )
    assert done.returncode == 0, done.stderr
    assert not done.stdout.strip()


# ------------------------------------------------------------ the shared bypass


def test_a_judge_subprocess_tool_call_is_never_gated(tmp_path):
    """CLAUDE_NO_EXCUSES_JUDGE is the shared convention across this project's
    guards (see truth-gate.py): a judge subprocess spawned by a sibling guard
    must never be second-guessed by this one."""
    decision_records = DENY_SHAPE
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in decision_records) + "\n")
    done = raw(
        tmp_path,
        json.dumps(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Agent",
                "tool_input": {"run_in_background": True},
                "transcript_path": str(transcript),
                "session_id": "s",
            }
        ),
        env_extra={"CLAUDE_NO_EXCUSES_JUDGE": "1"},
    )
    assert done.returncode == 0, done.stderr
    assert not done.stdout.strip()
