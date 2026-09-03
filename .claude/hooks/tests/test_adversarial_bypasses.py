"""Attacks on the enforcement architecture, run against the REAL hooks.

Every test here is one row of the adversarial table the 2026-09-02 review
demanded: an attack, the defence expected, and — the part that matters — proof
that a LEGITIMATE path stayed open beside the refusal. A hook that fires is not
a hook that works; a hook that fires AND leaves the intended path cheap is.

Payloads are driven through `run.sh` where the machine environment is the
thing under attack, and straight through the guard everywhere else, with a
private state directory and doctor report per test so nothing here touches the
live session.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
HOOKS = REPO / ".claude" / "hooks"
GUARD = HOOKS / "advisor-consult-guard.py"
RUN_SH = HOOKS / "run.sh"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_advisor_consult_guard import (  # noqa: E402
    A_PRINTED_PLAN,
    advisor_call,
    advisor_result,
    assistant_text,
    consulted_turn,
    denied,
    human,
    reason,
    tool_call,
    write_transcript,
)


def _env(tmp_path, doctor=None, **extra):
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "doctor.json").write_text(json.dumps(doctor or {"advisor": {"supported": "yes"}}))
    env = {**os.environ, "ONDOWAY_ADVISOR_LAG_WAIT": "0.2",
           "ONDOWAY_STATE_DIR": str(state),
           "ONDOWAY_LOCAL_SETTINGS": str(state / "settings.local.json")}
    env.update(extra)
    return env


def guard(tmp_path, records, tool, tool_input, *, doctor=None, event="PreToolUse"):
    transcript = tmp_path / "session.jsonl"
    rows = list(records)
    if event == "PreToolUse":
        rows.append(tool_call(tool, tool_input, "toolu_attack"))
    write_transcript(transcript, rows)
    payload = {"hook_event_name": event, "tool_name": tool, "tool_input": tool_input,
               "transcript_path": str(transcript), "session_id": f"attack-{tmp_path.name}",
               "tool_use_id": "toolu_attack"}
    done = subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=60,
                          env=_env(tmp_path, doctor))
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else {}


def bash(tmp_path, records, command, **kw):
    return guard(tmp_path, records, "Bash", {"command": command}, **kw)


def existing(tmp_path, name="target.py", lines=30):
    path = tmp_path / name
    path.write_text("\n".join(f"line {n}" for n in range(1, lines + 1)) + "\n")
    return path


def read_call(path):
    return tool_call("Read", {"file_path": str(path)}, "toolu_read")


# ------------------------------------------------ attack: reinvent a blocked tool


def test_attack_hand_rolled_grep_in_python_is_an_act_and_needs_the_consult(tmp_path):
    """The old system gated `grep` by name; a python one-liner was the bypass.
    Now the CAPABILITY is classified: `python3 -c` runs code, so it is an act
    and waits for the consult — while the real `grep` is a look and is free."""
    attack = "python3 -c \"import sys;[print(l) for l in open('x.py') if 'foo' in l]\""
    assert denied(bash(tmp_path, [human()], attack))
    assert not denied(bash(tmp_path, [human()], "grep -n foo x.py"))  # the intended path
    assert not denied(bash(tmp_path, consulted_turn(), attack))  # after consulting: fine


def test_attack_awk_sed_perl_as_a_search_are_looks_and_never_gated(tmp_path):
    """Recreating a search with a stream tool is not a bypass of anything —
    reading is free. The gate is on CHANGING things."""
    for command in ("awk '/foo/' x.py", "sed -n '/foo/p' x.py", "perl -ne 'print if /foo/' x.py"):
        assert not denied(bash(tmp_path, [human()], command)), command


# ------------------------------------------------ attack: modify without reading


def test_attack_cat_is_not_a_reading_credential_for_an_edit(tmp_path):
    """`cat` the file, then Edit it: the shell excerpt does not count. Only a
    full Read does — and after one, the same Edit is allowed."""
    target = existing(tmp_path)
    records = [*consulted_turn(),
               tool_call("Bash", {"command": f"cat {target}"}, "toolu_cat")]
    edit = {"file_path": str(target), "old_string": "line 1", "new_string": "x"}
    decision = guard(tmp_path, records, "Edit", edit)
    assert denied(decision) and "READ IT BEFORE YOU CHANGE IT." in reason(decision)
    assert not denied(guard(tmp_path, [*records, read_call(target)], "Edit", edit))


def test_attack_rewrite_through_a_heredoc_python_or_tee(tmp_path):
    target = existing(tmp_path)
    for command in (
        f"cat > {target} <<'EOF'\nnew\nEOF",
        f"printf 'x' > {target}",
        f"printf 'x' >> {target}",
        f"echo x | tee {target}",
        f"echo x | tee -a {target}",
    ):
        decision = bash(tmp_path, consulted_turn(), command)
        assert denied(decision), command
        assert "READ IT BEFORE YOU CHANGE IT." in reason(decision), command
    # Legitimate: the same commands after a Read.
    for command in (f"printf 'x' > {target}", f"echo x | tee {target}"):
        assert not denied(bash(tmp_path, [*consulted_turn(), read_call(target)], command))


def test_attack_path_tricks_resolve_to_the_same_file(tmp_path):
    target = existing(tmp_path)
    link = tmp_path / "alias.py"
    link.symlink_to(target)
    dotted = tmp_path / "sub" / ".." / target.name
    (tmp_path / "sub").mkdir()
    for spelling in (link, dotted):
        decision = guard(tmp_path, consulted_turn(), "Write",
                         {"file_path": str(spelling), "content": "x"})
        assert denied(decision), spelling
    # A Read through one spelling licenses a Write through another.
    decision = guard(tmp_path, [*consulted_turn(), read_call(link)], "Write",
                     {"file_path": str(dotted), "content": "x"})
    assert not denied(decision)


def test_attack_excerpt_read_then_write(tmp_path):
    target = existing(tmp_path, lines=500)
    partial = tool_call("Read", {"file_path": str(target), "limit": 50}, "toolu_partial")
    decision = guard(tmp_path, [*consulted_turn(), partial], "Write",
                     {"file_path": str(target), "content": "x"})
    assert denied(decision)


# ------------------------------------------------ attack: postpone the advisor


def test_attack_implement_first_consult_later(tmp_path):
    """Every act before the consult is refused; the refusal escalates on the
    third; the consult unlocks the same act unchanged."""
    records = [human(), read_call(tmp_path / "x.py")]
    messages = []
    for _ in range(3):
        decision = bash(tmp_path, records, "make lint")
        assert denied(decision)
        messages.append(reason(decision))
    assert "refusal 3 in this turn" in messages[-1]
    assert "The ONLY call that will be accepted next is `advisor()`" in messages[-1]
    unlocked = [*records, advisor_call(), advisor_result(), assistant_text(A_PRINTED_PLAN)]
    assert not denied(bash(tmp_path, unlocked, "make lint"))


def test_attack_claim_a_consult_in_prose_without_making_one(tmp_path):
    records = [human(), assistant_text("Consulting the advisor now. " + A_PRINTED_PLAN)]
    decision = bash(tmp_path, records, "make lint")
    assert denied(decision) and "NO CONSULT, NO ACTION." in reason(decision)


def test_attack_a_consult_from_the_previous_turn(tmp_path):
    records = [*consulted_turn(), human("next thing")]
    assert denied(bash(tmp_path, records, "make lint"))


def test_attack_consult_silently_and_act(tmp_path):
    records = [human(), advisor_call(), advisor_result()]
    decision = bash(tmp_path, records, "make lint")
    assert denied(decision) and "THE PLAN WAS NOT PRINTED." in reason(decision)


def test_attack_delegate_the_act_to_an_agent_without_consulting(tmp_path):
    decision = guard(tmp_path, [human()], "Agent",
                     {"subagent_type": "general-purpose", "prompt": "delete build/"})
    assert denied(decision)


def test_attack_pick_a_different_advisor_model_by_editing_settings(tmp_path):
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "advisor-router.json").write_text(json.dumps({"model": "fable"}))
    (state / "settings.local.json").write_text(json.dumps({"advisorModel": "haiku"}))
    decision = bash(tmp_path, consulted_turn(), "make lint")
    assert not denied(decision)
    assert "ADVISOR MODEL RESET to `fable`" in decision.get("systemMessage", "")
    assert json.loads((state / "settings.local.json").read_text())["advisorModel"] == "fable"


# ------------------------------------------------ attack: decompose destruction


def test_attack_split_a_sweep_into_find_delete_and_git_rm(tmp_path):
    first = [*consulted_turn(),
             tool_call("Bash", {"command": "git rm -r --cached build"}, "toolu_first"),
             {"type": "user", "message": {"content": [
                 {"type": "tool_result", "tool_use_id": "toolu_first", "content": "ok"}]}}]
    decision = bash(tmp_path, first, "find . -name '*.pyc' -delete")
    assert denied(decision) and "A DESTRUCTIVE ACTION NEEDS ITS OWN CONSULT." in reason(decision)


def test_attack_hide_a_marker_in_a_heredoc_is_not_destructive(tmp_path):
    """The other direction: a commit MESSAGE that says "rm -rf" is data, and
    must not tax the next command as a second destructive act."""
    first = [*consulted_turn(),
             tool_call("Bash", {"command": "cat <<'MSG'\nwe did rm -rf of nothing\nMSG"},
                       "toolu_first"),
             {"type": "user", "message": {"content": [
                 {"type": "tool_result", "tool_use_id": "toolu_first", "content": "ok"}]}}]
    assert not denied(bash(tmp_path, first, "git rm --cached x"))


# ------------------------------------------------ attack: the machine itself


def _settings_command(hook):
    return (
        'ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "${CLAUDE_PROJECT_DIR:-.}"); '
        f'sh "$ROOT/.claude/hooks/run.sh" {hook}'
    )


def test_env_project_dir_unset_from_a_subdirectory_still_finds_the_hook(tmp_path):
    """The lockout shape: no CLAUDE_PROJECT_DIR, cwd a subdirectory. The old
    command became `python3 /.claude/hooks/x.py` and exit 2 = block everything."""
    env = {k: v for k, v in _env(tmp_path).items() if k != "CLAUDE_PROJECT_DIR"}
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": "ls"}, "transcript_path": "/nonexistent",
               "session_id": "env"}
    done = subprocess.run(["bash", "-c", _settings_command("advisor-consult-guard.py")],
                          input=json.dumps(payload), capture_output=True, text=True,
                          cwd=str(REPO / ".claude" / "hooks"), env=env, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "can't open file" not in done.stderr


def test_env_no_python_disarms_loudly_instead_of_blocking(tmp_path):
    bare = tmp_path / "bin"
    bare.mkdir()
    for name in ("sh", "cat", "dirname", "pwd", "printf", "command", "git"):
        real = subprocess.run(["which", name], capture_output=True, text=True).stdout.strip()
        if real:
            (bare / name).symlink_to(real)
    env = {"PATH": str(bare), "HOME": str(tmp_path)}
    done = subprocess.run(["sh", str(RUN_SH), "advisor-consult-guard.py"], input="{}",
                          capture_output=True, text=True, env=env, timeout=60)
    assert done.returncode == 0, done.stderr
    assert "ONDOWAY HOOKS DISARMED" in done.stdout
    assert "python3" in done.stdout


def test_env_harness_without_the_advisor_tool_is_disarmed_with_the_fix_named(tmp_path):
    doctor = {"advisor": {"supported": "no",
                          "why": "the harness does not know `claude-fable-5-1`"}}
    decision = bash(tmp_path, [human()], "make lint", doctor=doctor)
    assert not denied(decision)
    assert "ADVISOR GATE DISARMED ON THIS MACHINE" in decision.get("systemMessage", "")
    assert "claude-fable-5-1" in decision.get("systemMessage", "")


def test_env_fable_quota_exhausted_routes_to_opus_and_the_consult_still_counts(tmp_path):
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "advisor-router.json").write_text(json.dumps({"model": "fable"}))
    (state / "settings.local.json").write_text(json.dumps({"advisorModel": "fable"}))
    error = {"type": "assistant", "message": {"content": [
        {"type": "advisor_tool_result_error", "tool_use_id": "srvtoolu_x",
         "content": {"error": "rate_limit_error"}}]}}
    records = [human(), advisor_call(), error, assistant_text(A_PRINTED_PLAN)]
    decision = bash(tmp_path, records, "make lint")
    assert not denied(decision)
    assert "routed to `opus`" in decision.get("systemMessage", "")
    assert json.loads((state / "settings.local.json").read_text())["advisorModel"] == "opus"
    assert json.loads((state / "advisor-router.json").read_text())["fable_failed_at"]


def test_env_quota_state_unknown_defaults_to_fable_explicitly(tmp_path):
    """The defined behaviour for 'cannot determine': fable, and say so."""
    env = _env(tmp_path)
    done = subprocess.run([sys.executable, str(HOOKS / "advisor-router.py")],
                          input=json.dumps({"hook_event_name": "SessionStart"}),
                          capture_output=True, text=True, env=env, timeout=60)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert "routed to `fable`" in out["hookSpecificOutput"]["additionalContext"]
    local = json.loads((tmp_path / "state" / "settings.local.json").read_text())
    assert local["advisorModel"] == "fable"


def test_env_harness_that_lacks_fable_in_its_catalog_routes_to_opus(tmp_path):
    env = _env(tmp_path, doctor={"advisor": {"supported": "yes"}, "fable_in_catalog": "no"})
    done = subprocess.run([sys.executable, str(HOOKS / "advisor-router.py")],
                          input="{}", capture_output=True, text=True, env=env, timeout=60)
    assert "routed to `opus`" in done.stdout, done.stdout


def test_env_ledger_guard_names_this_checkout_not_a_hardcoded_one(tmp_path):
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": "make lint"}, "session_id": "ledger"}
    done = subprocess.run([sys.executable, str(HOOKS / "ledger-guard.py")],
                          input=json.dumps(payload), capture_output=True, text=True,
                          env=_env(tmp_path), timeout=60)
    text = done.stdout
    assert f"make -C {REPO} " in text
    assert "{root}" not in text


# ------------------------------------------------ progress, not activity


def test_looks_are_never_taxed_so_a_compliant_turn_pays_nothing_to_look(tmp_path):
    for command in ("ls -la", "git status", "git log -3 | cat", "wc -l x.py",
                    "find . -name '*.py' | head", "cat x 2>&1 | tail -5"):
        assert not denied(bash(tmp_path, [human()], command)), command


def test_the_only_way_out_of_refusals_is_the_named_remedy(tmp_path):
    """Ten refusals, ten different spellings of an act, and the gate is
    unchanged — no ceiling, no stand-down, on a machine whose advisor exists."""
    spellings = ["make lint", "uv run pytest x", "python3 x.py", "node x.js",
                 "echo 1 > y", "git commit -m x", "npm test", "cargo build",
                 "bash ./x.sh", "sh -c 'ls'"]
    for command in spellings:
        assert denied(bash(tmp_path, [human()], command)), command
