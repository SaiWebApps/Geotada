"""Payload tests for .claude/hooks/truth-gate.py.

The guard is a Stop hook: it runs two judges (advisor and verifier, on two
different models) over the reply's own text and blocks unless both come back
clean. It never actually spawns a real `claude -p` model call in these
tests — the ONLY faked thing is the `claude` binary itself, resolved via
`ONDOWAY_TRUTH_GATE_CLAUDE`. Everything downstream of that — the real
subprocess spawn, the real timeout, the real JSON-brace-slice parsing, the
real ceiling bookkeeping — runs exactly as it would in production. A canned-
verdict shortcut that skipped the subprocess entirely would leave that code
untested, which is this project's own "guard that reports green while
guarding nothing" failure (advisor-consult-guard.py's `server_tool_use`
postmortem).

THE FAKE BINARY BRANCHES ON --model, because the real hook always calls TWO
different models (`fable` for the advisor, `claude-sonnet-5` for the
verifier) with the SAME `ONDOWAY_TRUTH_GATE_CLAUDE` binary. It reads
`FAKE_CLAUDE_<TAG>_RESPONSE` / `_MODE` / `_HANG_SECONDS` / `_LIE_IF_CONTAINS`
env vars, where `<TAG>` is the model name upper-cased with `-`/`.` turned to
`_` — `FABLE` for the advisor, `CLAUDE_SONNET_5` for the verifier. This
assumes the real CLI always receives `-p <prompt>` and `--model <name>` as
separate argv tokens, which is what no-flinch.py's own subprocess call does;
if a future CLI version ever required the prompt positionally instead, this
fake would need updating even though nothing here would fail to compile.

THE 10957632 REGRESSION IS A REAL, VERIFIED COMMIT, not an invented fixture.
Read directly off this repository: `git show -s 10957632` on
2026-08-31 gives commit 109576326d58f2462771adc600a2f0deb04ab36d, message
"chore(cleanup): sweep 513 dead files nothing builds, tests, or ships reads",
body stating "Every path was checked before it went, not after." The owner's
own words, the same day, after being told a push removed 720 files and asked
whether he wanted any back: "No, I meant to delete these. Stop fucking
catastrophizing." The fixtures below use that exact commit id and message.

Record shapes match the sibling guards' own measured fixtures:

    human       {"type": "user", "origin": {"kind": "human"},
                 "message": {"content": "<a string>"}}
    reply text  {"type": "assistant",
                 "message": {"id": "<msg id>", "content": [
                    {"type": "text", "text": "..."}]}}
    bash call   {"type": "assistant", "message": {"id": "<msg id>", "content": [
                    {"type": "tool_use", "id": "<call id>", "name": "Bash",
                     "input": {"command": "..."}}]}}
    tool result {"type": "user", "message": {"content": [
                    {"type": "tool_result", "tool_use_id": "<call id>",
                     "content": "...", "is_error": <bool, only when true>}]}}
    block echo  {"type": "user", "isMeta": true,
                 "message": {"content": "<this gate's own previous reason>"}}
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / ".claude" / "hooks" / "truth-gate.py"

ADVISOR_TAG = "FABLE"
VERIFIER_TAG = "CLAUDE_SONNET_5"

REAL_COMMIT = "10957632"
REAL_COMMIT_MESSAGE = "chore(cleanup): sweep 513 dead files nothing builds, tests, or ships reads"


# ------------------------------------------------------------- the fake claude


FAKE_CLAUDE_SOURCE = """#!/usr/bin/env python3
import json, os, sys, time

args = sys.argv[1:]
model = None
prompt = None
for i, a in enumerate(args):
    if a == "--model" and i + 1 < len(args):
        model = args[i + 1]
    if a == "-p" and i + 1 < len(args):
        prompt = args[i + 1]

def tag(m):
    return (m or "unknown").upper().replace("-", "_").replace(".", "_")

def getenv(suffix, default=None):
    return os.environ.get("FAKE_CLAUDE_" + tag(model) + "_" + suffix, default)

mode = getenv("MODE", "")
if mode == "fail":
    sys.stderr.write("fake claude: simulated failure\\n")
    sys.exit(1)
if mode == "hang":
    started = time.time()
    time.sleep(float(getenv("HANG_SECONDS", "5")))
    ended = time.time()
    # When asked, record WHEN this judge ran, so a test can ask whether two
    # judges overlapped instead of timing the whole hook and guessing. One
    # short append per process; both judges write to the same file.
    timeline = os.environ.get("FAKE_CLAUDE_TIMELINE")
    if timeline:
        with open(timeline, "a") as fh:
            fh.write("%s %.6f %.6f\\n" % (tag(model), started, ended))
    sys.exit(0)
if mode == "badjson":
    print("not json at all, sorry")
    sys.exit(0)

marker = getenv("LIE_IF_CONTAINS")
if marker and prompt and marker in prompt:
    print(json.dumps({"statements": [
        {"statement": marker, "verdict": "LIE", "reason": "fake: marker present",
         "alarms_about_change": False}
    ]}))
    sys.exit(0)

canned = getenv("RESPONSE")
if canned:
    print(canned)
    sys.exit(0)

print(json.dumps({"statements": []}))
"""


def fake_claude(tmp_path):
    path = tmp_path / "fake_claude.py"
    if not path.exists():
        path.write_text(FAKE_CLAUDE_SOURCE)
        path.chmod(0o755)
    return path


def judge_env(tag, *, response=None, mode=None, hang_seconds=None, lie_if_contains=None):
    prefix = f"FAKE_CLAUDE_{tag}_"
    out = {}
    if response is not None:
        out[prefix + "RESPONSE"] = response
    if mode is not None:
        out[prefix + "MODE"] = mode
    if hang_seconds is not None:
        out[prefix + "HANG_SECONDS"] = str(hang_seconds)
    if lie_if_contains is not None:
        out[prefix + "LIE_IF_CONTAINS"] = lie_if_contains
    return out


def clean_statement(statement, alarms=False):
    return json.dumps(
        {"statements": [{"statement": statement, "verdict": "TRUTH", "reason": "checked",
                          "alarms_about_change": alarms}]}
    )


# ---------------------------------------------------------------- record shapes


def human(text="do the thing"):
    return {"type": "user", "origin": {"kind": "human"}, "message": {"content": text}}


def assistant_text(text, message_id="msg_reply"):
    return {"type": "assistant", "message": {"id": message_id, "content": [{"type": "text", "text": text}]}}


def bash_call(command, call_id="toolu_bash", message_id="msg_bash"):
    return {
        "type": "assistant",
        "message": {
            "id": message_id,
            "content": [{"type": "tool_use", "id": call_id, "name": "Bash", "input": {"command": command}}],
        },
    }


def tool_result(call_id, text="ok", is_error=False):
    block = {"type": "tool_result", "tool_use_id": call_id, "content": text}
    if is_error:
        block["is_error"] = True
    return {"type": "user", "message": {"content": [block]}}


def block_echo(text="TRUTH GATE — BLOCKED.\n\nfix it"):
    """How this gate's OWN previous refusal lands back in the transcript:
    harness feedback, isMeta, never the person speaking again."""
    return {"type": "user", "isMeta": True, "message": {"content": text}}


# ---------------------------------------------------------------------- harness


def decide(tmp_path, records, *, session=None, extra_env=None, claude_binary=None, judge_timeout="10"):
    """Run the guard over `records` and return its decision ({} means allowed)."""
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    payload = {
        "hook_event_name": "Stop",
        "transcript_path": str(transcript),
        "session_id": session or f"test-{tmp_path.name}",
    }
    binary = claude_binary if claude_binary is not None else str(fake_claude(tmp_path))
    env = {
        **os.environ,
        "ONDOWAY_TRUTH_GATE_STATE": str(tmp_path / "state.json"),
        "ONDOWAY_TRUTH_GATE_CLAUDE": binary,
        "ONDOWAY_TRUTH_GATE_TIMEOUT": judge_timeout,
    }
    env.update(extra_env or {})
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else {}


def blocked(decision):
    return decision.get("decision") == "block"


def reason(decision):
    return decision.get("reason", "")


# ------------------------------------------------------------------- the basics


def test_a_clean_reply_is_allowed(tmp_path):
    records = [human(), assistant_text("The tests pass and nothing else changed.")]
    assert decide(tmp_path, records) == {}


def test_an_empty_reply_never_invokes_the_judges(tmp_path):
    """No text at all to judge — proven by pointing at a binary that would
    fail if it were ever invoked."""
    records = [human(), bash_call("ls")]
    decision = decide(tmp_path, records, claude_binary=str(tmp_path / "does-not-exist"))
    assert decision == {}


# --------------------------------------------------------------- LIE / verdicts


def test_an_advisor_lie_blocks(tmp_path):
    statement = "4 of 9 shards passed"
    records = [human(), assistant_text(f"Status: {statement}.")]
    env = judge_env(
        ADVISOR_TAG,
        response=json.dumps(
            {"statements": [{"statement": statement, "verdict": "LIE",
                              "reason": "actually 3 of 9 passed", "alarms_about_change": False}]}
        ),
    )
    decision = decide(tmp_path, records, extra_env=env)
    assert blocked(decision)
    assert "[ADVISOR]" in reason(decision)
    assert statement in reason(decision)
    assert "fix the statement or delete it, then say it again" in reason(decision)


def test_a_verifier_catch_blocks_even_when_the_advisor_is_clean(tmp_path):
    statement = "88 commits ahead of main"
    records = [human(), assistant_text(f"This branch is {statement}.")]
    env = judge_env(
        VERIFIER_TAG,
        response=json.dumps(
            {"statements": [{"statement": statement, "verdict": "LIE",
                              "reason": "git rev-list --count says 90", "alarms_about_change": False}]}
        ),
    )
    decision = decide(tmp_path, records, extra_env=env)
    assert blocked(decision)
    assert "[VERIFIER]" in reason(decision)


def test_a_lie_verdict_never_stands_down(tmp_path):
    """No ceiling on a genuine lie — the owner's own words: keep repeating
    until the advisor says TRUTH."""
    records = [human(), assistant_text("A persistently false claim.")]
    env = judge_env(
        ADVISOR_TAG,
        response=json.dumps(
            {"statements": [{"statement": "a persistently false claim", "verdict": "LIE",
                              "reason": "checked and confirmed false", "alarms_about_change": False}]}
        ),
    )
    for _ in range(5):
        decision = decide(tmp_path, records, session="persistent-lie", extra_env=env)
        assert blocked(decision)


# ----------------------------------------------------------------- infra failures


def test_a_judge_that_exits_nonzero_is_an_infra_failure(tmp_path):
    records = [human(), assistant_text("Anything at all.")]
    decision = decide(tmp_path, records, extra_env=judge_env(ADVISOR_TAG, mode="fail"))
    assert blocked(decision)
    assert "COULD NOT REACH A VERDICT" in reason(decision)


def test_a_judge_that_hangs_past_the_timeout_is_an_infra_failure(tmp_path):
    records = [human(), assistant_text("Anything at all.")]
    decision = decide(
        tmp_path, records,
        extra_env=judge_env(ADVISOR_TAG, mode="hang", hang_seconds=3),
        judge_timeout="1",
    )
    assert blocked(decision)
    assert "timed out" in reason(decision)


def test_a_judge_returning_non_json_is_an_infra_failure(tmp_path):
    records = [human(), assistant_text("Anything at all.")]
    decision = decide(tmp_path, records, extra_env=judge_env(ADVISOR_TAG, mode="badjson"))
    assert blocked(decision)
    assert "COULD NOT REACH A VERDICT" in reason(decision)


def test_a_missing_claude_binary_is_an_infra_failure_not_a_crash(tmp_path):
    records = [human(), assistant_text("Anything at all.")]
    decision = decide(tmp_path, records, claude_binary=str(tmp_path / "no-such-binary"))
    assert blocked(decision)
    assert "COULD NOT REACH A VERDICT" in reason(decision)


def test_missing_alarms_about_change_is_an_infra_failure(tmp_path):
    """The field the owner called out as mattering most must not be silently
    defaulted when a judge omits it."""
    records = [human(), assistant_text("A plain statement.")]
    env = judge_env(
        ADVISOR_TAG,
        response=json.dumps(
            {"statements": [{"statement": "a plain statement", "verdict": "TRUTH", "reason": "checked"}]}
        ),
    )
    decision = decide(tmp_path, records, extra_env=env)
    assert blocked(decision)
    assert "COULD NOT REACH A VERDICT" in reason(decision)
    assert "alarms_about_change" in reason(decision)


def test_the_infra_ceiling_stands_down_after_three_failures(tmp_path):
    records = [human(), assistant_text("Anything at all.")]
    env = judge_env(ADVISOR_TAG, mode="fail")
    for attempt in range(3):
        assert blocked(decide(tmp_path, records, session="wedged", extra_env=env)), attempt
    decision = decide(tmp_path, records, session="wedged", extra_env=env)
    assert not blocked(decision)
    assert "TRUTH GATE STOOD DOWN" in decision.get("systemMessage", "")


def test_the_ceiling_stands_down_on_repeated_real_timeouts(tmp_path):
    """The coordinator's exact concern, on the TIMEOUT path specifically, not
    just the generic scripted-failure path above: does the gate DEGRADE
    rather than wedge open when both judges genuinely time out, repeatedly,
    the way they did in real use (both judges hitting the full 240s on a
    reply that told them to re-run a multi-minute test suite)?"""
    records = [human(), assistant_text("Anything at all.")]
    env = {
        **judge_env(ADVISOR_TAG, mode="hang", hang_seconds=3),
        **judge_env(VERIFIER_TAG, mode="hang", hang_seconds=3),
    }
    for attempt in range(3):
        decision = decide(tmp_path, records, session="timeout-wedge", extra_env=env, judge_timeout="1")
        assert blocked(decision), attempt
        assert "timed out" in reason(decision)
    decision = decide(tmp_path, records, session="timeout-wedge", extra_env=env, judge_timeout="1")
    assert not blocked(decision), "three real timeouts in a row must stand the arm down, not wedge it"
    assert "TRUTH GATE STOOD DOWN" in decision.get("systemMessage", "")


def test_a_clean_run_after_infra_failures_clears_the_ceiling(tmp_path):
    records = [human(), assistant_text("Anything at all.")]
    failing = judge_env(ADVISOR_TAG, mode="fail")
    assert blocked(decide(tmp_path, records, session="mixed", extra_env=failing))
    assert blocked(decide(tmp_path, records, session="mixed", extra_env=failing))
    assert decide(tmp_path, records, session="mixed") == {}  # a clean run in between
    assert blocked(decide(tmp_path, records, session="mixed", extra_env=failing))
    assert blocked(decide(tmp_path, records, session="mixed", extra_env=failing))


# ----------------------------------------------------- the R1/R2 self-wedge fix


def test_a_blocked_replys_lie_is_not_rejudged_after_a_clean_revision(tmp_path):
    """The reasoned-through design fix: R1's already-fixed statement must not
    haunt R2 forever just because both sit in the same turn."""
    marker = "the shard count is 4 of 9"
    records = [
        human(),
        assistant_text(f"Status update: {marker}.", message_id="msg_r1"),
        block_echo(),
        assistant_text("Corrected status: the shard count is 3 of 9.", message_id="msg_r2"),
    ]
    decision = decide(tmp_path, records, extra_env=judge_env(ADVISOR_TAG, lie_if_contains=marker))
    assert decision == {}, "R1's marker text leaked into what was judged for R2"


def test_an_unfixed_lie_alone_is_still_caught(tmp_path):
    """Companion to the test above: the marker mechanism itself must work
    when there is no revision to exonerate."""
    marker = "the shard count is 4 of 9"
    records = [human(), assistant_text(f"Status update: {marker}.", message_id="msg_only")]
    decision = decide(tmp_path, records, extra_env=judge_env(ADVISOR_TAG, lie_if_contains=marker))
    assert blocked(decision)


# ---------------------------------------------------------- FALSE-ALARM verdict


def test_the_10957632_regression_is_a_false_alarm(tmp_path):
    """The exact incident this arm exists for, using the real, verified
    commit — see module docstring."""
    statement = "513 of 720 deleted files were removed -- do you want any of them back?"
    records = [
        human(),
        bash_call(f"git -C {REPO} log --oneline -1 {REAL_COMMIT}", call_id="toolu_hist"),
        tool_result("toolu_hist", f"{REAL_COMMIT} {REAL_COMMIT_MESSAGE}"),
        assistant_text(statement),
    ]
    env = judge_env(
        ADVISOR_TAG,
        response=json.dumps(
            {
                "statements": [
                    {
                        "statement": statement,
                        "verdict": "FALSE-ALARM",
                        "reason": f"commit {REAL_COMMIT} '{REAL_COMMIT_MESSAGE}' states the sweep was deliberate",
                        "alarms_about_change": True,
                    }
                ]
            }
        ),
    )
    decision = decide(tmp_path, records, extra_env=env)
    assert blocked(decision)
    assert REAL_COMMIT in reason(decision)
    assert "delete the alarm or restate it as a fact with no question attached" in reason(decision)


def test_false_alarm_with_a_space_normalizes_correctly(tmp_path):
    statement = "513 files were deleted -- should they be restored?"
    records = [
        human(),
        bash_call(f"git -C {REPO} show {REAL_COMMIT}", call_id="toolu_h"),
        tool_result("toolu_h", REAL_COMMIT_MESSAGE),
        assistant_text(statement),
    ]
    env = judge_env(
        ADVISOR_TAG,
        response=json.dumps(
            {"statements": [{"statement": statement, "verdict": "FALSE ALARM",
                              "reason": f"commit {REAL_COMMIT} shows intent", "alarms_about_change": True}]}
        ),
    )
    decision = decide(tmp_path, records, extra_env=env)
    assert blocked(decision)
    assert "delete the alarm or restate it as a fact with no question attached" in reason(decision)


# ---------------------------------------------------- the mechanical pre-check


def test_no_history_lookup_overrides_an_alarm_to_lie(tmp_path):
    """The structural backstop: a TRUE, sourced-sounding alarm with no git
    log/show/blame anywhere in the turn is forced to LIE regardless of what
    the judge said."""
    statement = "720 files were removed -- do you want any of them back?"
    records = [human(), assistant_text(statement)]
    env = judge_env(
        ADVISOR_TAG,
        response=json.dumps(
            {"statements": [{"statement": statement, "verdict": "TRUTH",
                              "reason": "the count is accurate", "alarms_about_change": True}]}
        ),
    )
    decision = decide(tmp_path, records, extra_env=env)
    assert blocked(decision)
    assert "read the commit that made this change, then decide whether it is news" in reason(decision)
    assert "(was: the count is accurate)" in reason(decision)


def test_the_dash_c_form_of_git_log_counts_as_a_lookup(tmp_path):
    """This environment resets cwd between Bash calls, so `git -C <path> log`
    is the NORMAL way agents here run git — a substring match on the phrase
    "git log" would miss it and re-block a satisfied remedy forever."""
    statement = "513 files were removed as part of a deliberate cleanup."
    records = [
        human(),
        bash_call(f"git -C {REPO} log -1 -- some/file", call_id="toolu_x"),
        tool_result("toolu_x", "commit abc123 chore: cleanup"),
        assistant_text(statement),
    ]
    env = judge_env(
        ADVISOR_TAG,
        response=json.dumps(
            {"statements": [{"statement": statement, "verdict": "TRUTH",
                              "reason": "matches commit abc123", "alarms_about_change": True}]}
        ),
    )
    decision = decide(tmp_path, records, extra_env=env)
    assert decision == {}, "a -C form history lookup must count, and TRUTH must not be overridden"


def test_git_diff_does_not_count_as_a_history_lookup(tmp_path):
    """diff/status show WHAT changed, never WHY -- the tool the motivating
    incident almost certainly used to produce its count in the first place."""
    statement = "720 files were removed -- want them back?"
    records = [
        human(),
        bash_call(f"git -C {REPO} diff --stat HEAD~1", call_id="toolu_y"),
        tool_result("toolu_y", "720 files changed"),
        assistant_text(statement),
    ]
    env = judge_env(
        ADVISOR_TAG,
        response=json.dumps(
            {"statements": [{"statement": statement, "verdict": "TRUTH",
                              "reason": "the count is accurate", "alarms_about_change": True}]}
        ),
    )
    decision = decide(tmp_path, records, extra_env=env)
    assert blocked(decision)
    assert "read the commit that made this change, then decide whether it is news" in reason(decision)


def test_a_refused_git_log_call_does_not_count_as_a_lookup(tmp_path):
    statement = "720 files were removed -- want them back?"
    records = [
        human(),
        bash_call(f"git -C {REPO} log -1 -- some/file", call_id="toolu_refused"),
        tool_result("toolu_refused", "NO CONSULT, NO ACTION.", is_error=True),
        assistant_text(statement),
    ]
    env = judge_env(
        ADVISOR_TAG,
        response=json.dumps(
            {"statements": [{"statement": statement, "verdict": "TRUTH",
                              "reason": "the count is accurate", "alarms_about_change": True}]}
        ),
    )
    decision = decide(tmp_path, records, extra_env=env)
    assert blocked(decision)


def test_a_neutral_statement_with_no_alarm_flag_is_never_overridden(tmp_path):
    """The override only ever touches statements the judge itself flagged."""
    records = [human(), assistant_text("The function returns an integer.")]
    env = judge_env(ADVISOR_TAG, response=clean_statement("the function returns an integer", alarms=False))
    assert decide(tmp_path, records, extra_env=env) == {}


# --------------------------------------------------------- shared bypass / misc


def test_the_shared_bypass_stands_down_immediately(tmp_path):
    records = [human(), assistant_text("Anything at all.")]
    decision = decide(
        tmp_path, records,
        claude_binary=str(tmp_path / "does-not-exist"),
        extra_env={"CLAUDE_NO_EXCUSES_JUDGE": "1"},
    )
    assert decision == {}


def test_malformed_stdin_allows(tmp_path):
    for raw_text in ("null", "42", '"a string"', "[]", "not json at all"):
        env = {
            **os.environ,
            "ONDOWAY_TRUTH_GATE_CLAUDE": str(tmp_path / "does-not-exist"),
            "ONDOWAY_TRUTH_GATE_STATE": str(tmp_path / "state.json"),
        }
        done = subprocess.run(
            [sys.executable, str(GUARD)], input=raw_text,
            capture_output=True, text=True, timeout=30, env=env,
        )
        assert done.returncode == 0, f"{raw_text!r}: {done.stderr}"
        assert not done.stdout.strip(), f"{raw_text!r}: should allow silently"


def test_a_missing_transcript_path_allows(tmp_path):
    env = {
        **os.environ,
        "ONDOWAY_TRUTH_GATE_CLAUDE": str(tmp_path / "does-not-exist"),
        "ONDOWAY_TRUTH_GATE_STATE": str(tmp_path / "state.json"),
    }
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"hook_event_name": "Stop", "session_id": "s"}),
        capture_output=True, text=True, timeout=30, env=env,
    )
    assert done.returncode == 0, done.stderr
    assert not done.stdout.strip()


def test_the_two_judges_run_in_parallel_not_sequentially(tmp_path):
    """The two judges' RUNNING PERIODS overlap — asked of them directly.

    This measured the hook's total wall clock against a 2.5s ceiling until
    2026-08-31, and failed that day at 2.81s inside a full-suite run while
    three background agents were working, then passed at 1.84s when run alone
    minutes later. Same code, same machine, opposite verdicts: the assertion
    was measuring the machine's load as much as the gate's behaviour.

    Widening the ceiling would have been worse than leaving it. Two 1.5s
    judges run back to back take 3.0s, so any threshold loose enough to
    survive a busy machine stops being able to tell sequential from parallel
    at all — the one thing the test is named for.

    So each fake judge now records its own start and end, and the assertion is
    that the two intervals INTERSECT. Two processes that genuinely run at the
    same time overlap under any load; two that run one after the other never
    do, however fast or slow the machine is. The absolute ceiling below stays
    only as a crash guard against a hang, generous enough that it can never be
    the thing that fails.
    """
    records = [human(), assistant_text("Anything at all.")]
    timeline = tmp_path / "judge-timeline.txt"
    env = {
        **judge_env(ADVISOR_TAG, mode="hang", hang_seconds=1.5),
        **judge_env(VERIFIER_TAG, mode="hang", hang_seconds=1.5),
        "FAKE_CLAUDE_TIMELINE": str(timeline),
    }
    start = time.time()
    decide(tmp_path, records, extra_env=env, judge_timeout="10")
    elapsed = time.time() - start

    assert timeline.exists(), "neither judge ran"
    spans = {}
    for line in timeline.read_text().splitlines():
        if not line.strip():
            continue
        tag, began, ended = line.split()
        spans[tag] = (float(began), float(ended))
    assert set(spans) == {ADVISOR_TAG, VERIFIER_TAG}, f"judges that ran: {sorted(spans)}"

    advisor_began, advisor_ended = spans[ADVISOR_TAG]
    verifier_began, verifier_ended = spans[VERIFIER_TAG]
    overlap = min(advisor_ended, verifier_ended) - max(advisor_began, verifier_began)
    assert overlap > 0, (
        "the judges did not run at the same time — "
        f"advisor {advisor_began:.3f}..{advisor_ended:.3f}, "
        f"verifier {verifier_began:.3f}..{verifier_ended:.3f}"
    )
    # A crash guard, not a performance bar: 10s is the judge timeout itself, so
    # only a genuine hang reaches it.
    assert elapsed < 10, f"the hook took {elapsed:.2f}s, which is a hang"
