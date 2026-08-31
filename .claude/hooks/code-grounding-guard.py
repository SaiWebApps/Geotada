#!/usr/bin/env python3
"""No agent advises, verifies or acts from memory of a codebase it never opened.

TWO ARMS, one file, because they are two halves of one rule.

  UserPromptSubmit  Run `codegraph sync` so the index every agent reads from is
                    current, and say so in the context the turn starts with.
  PreToolUse        A shadow (the verifier) is refused unless its prompt carries
                    this session's transcript path, so it can read the advisor's
                    printed plan and check the work against THAT, not merely
                    against the implementer's account of it.

WHY THIS EXISTS, measured rather than assumed. The `advisor` tool takes no
arguments: it forwards the conversation and nothing else. The reviewer behind it
has NO TOOLS — it cannot sync an index, open a file, or query the graph. So an
instruction to "consult the code" reaches something structurally unable to obey,
and the only channel it has is what already sits in the transcript.

On 2026-08-31 that gap cost the owner directly. Asked to prove with screenshots
that a browser had run the test suite, the advisor designed a scheme from general
knowledge — attach over the DevTools protocol and photograph the browser's own
version page — while `tests/test_workbench_ui.py` sat in the repository with a
`_take_screenshot` helper and 36 call sites driving the real product through
Playwright. The advisor could not have known: that file had never been mentioned
in the conversation. The implementer executed it anyway, and the owner's verdict
on the result was "means nothing".

So the fix cannot be an instruction. It has to put the codebase INTO the channel
the advisor actually reads, and refuse to let anything be acted on otherwise:

  * this hook keeps the index fresh (measured 0.29s, and its first run found
    three files the index had already gone stale on);
  * the injected context here, plus the grounding requirement in
    advisor-consult-guard.py, put real symbols in front of the advisor BEFORE it
    is asked anything;
  * every agent definition under .claude/agents/ carries the same requirement,
    because "all agents must be aware of the code" is not satisfied by grounding
    one of them.

NO PATTERN MATCHING. Both arms compare structure — a tool name, a subagent type,
a substring the payload itself supplies — because a word list catches only the
spellings someone thought of, and fails silently on the rest.

FAILS OPEN, deliberately. A missing binary, a sync error or a malformed payload
warns and allows. This guard exists to stop ungrounded work, and a guard that
wedges the session when its own dependency breaks is a guard that gets deleted —
which costs every case it was built for.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

#: `codegraph sync` on this repo: 0.29s measured 2026-08-31, on an index that had
#: drifted by three files. The timeout is two orders of magnitude above that
#: because the cost of waiting is a pause and the cost of blocking is the owner's
#: session; it is a backstop against a hung daemon, not a budget.
SYNC_TIMEOUT_SECONDS = 60

#: The verifier. Named by the subagent type the Agent tool is called with — read
#: off a real record in this project's own transcript, not assumed:
#:   {"type":"tool_use","name":"Agent","input":{"subagent_type":"shadow", ...}}
VERIFIER_SUBAGENT = "shadow"


def allow():
    sys.exit(0)


def deny(reason):
    """Refuse the call. Always exit 0 — the decision travels in the printed JSON.
    A hook that crashes is a hook that is switched off."""
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                },
                "systemMessage": reason,
            }
        )
    )
    sys.exit(0)


def add_context(text):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": text,
                }
            }
        )
    )
    sys.exit(0)


def repo_root(payload):
    """The project directory, from the payload or this file's own location."""
    given = payload.get("cwd") or ""
    if given and (Path(given) / ".codegraph").is_dir():
        return Path(given)
    return Path(__file__).resolve().parent.parent.parent


def handle_user_prompt_submit(payload):
    """Refresh the index the whole turn will reason from."""
    root = repo_root(payload)
    if not (root / ".codegraph").is_dir():
        allow()  # not an indexed repo; nothing to sync and nothing to say

    binary = shutil.which("codegraph")
    if not binary:
        add_context(
            "CodeGraph index NOT synced: the `codegraph` binary is not on PATH. "
            "Every claim about this codebase in this turn must be grounded by "
            "reading the actual files, because the index may be stale."
        )

    try:
        result = subprocess.run(
            [binary, "sync"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=SYNC_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # a hung daemon, a killed process, anything
        add_context(
            f"CodeGraph sync did not complete ({type(exc).__name__}). The index may "
            "be stale — ground claims by reading files rather than trusting it."
        )

    if result.returncode != 0:
        add_context(
            f"CodeGraph sync exited {result.returncode}. The index may be stale — "
            "ground claims by reading files rather than trusting it."
        )

    add_context(
        "CodeGraph index synced for this turn.\n\n"
        "GROUNDING COMES BEFORE ADVICE, NOT AFTER IT. The `advisor` tool forwards "
        "this conversation and nothing else — the reviewer behind it has no tools "
        "and cannot open a file, so it knows only what is already written here. "
        "Look at the real code FIRST (codegraph_explore, or Read on the files in "
        "question), THEN consult, so the advice is about this repository rather "
        "than about software in general. Measured 2026-08-31: advice given without "
        "that step invented a screenshot mechanism from scratch while "
        "tests/test_workbench_ui.py already did the job in-repo."
    )


def handle_pre_tool_use(payload):
    """The verifier must be able to read the plan it is checking the work against."""
    if (payload.get("tool_name") or "") != "Agent":
        allow()

    tool_input = payload.get("tool_input") or {}
    if (tool_input.get("subagent_type") or "") != VERIFIER_SUBAGENT:
        allow()

    transcript = payload.get("transcript_path") or ""
    if not transcript:
        allow()  # nothing to require; never block on our own missing input

    prompt = tool_input.get("prompt")
    if isinstance(prompt, str) and transcript in prompt:
        allow()

    deny(
        "THE VERIFIER CANNOT CHECK WORK AGAINST A PLAN IT CANNOT READ.\n\n"
        "This shadow's prompt does not contain the session transcript path, so it "
        "can only check the claims it is handed — and those are written by the "
        "same turn that did the work. That is how a turn stays inside its own "
        "account of itself: every number can be true while the work still went "
        "somewhere the advisor never sanctioned.\n\n"
        "Put this path in the prompt, and tell the shadow to read it, find the "
        "LAST advisor plan in this turn, and reject work that falls outside it:\n\n"
        f"    {transcript}\n\n"
        "The advisor decides what should happen; the shadow decides whether that "
        "is what did happen. Neither job works if the two never see the same plan."
    )


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    event = payload.get("hook_event_name") or ""
    if event == "UserPromptSubmit":
        handle_user_prompt_submit(payload)
    elif event == "PreToolUse":
        handle_pre_tool_use(payload)
    allow()


if __name__ == "__main__":
    main()
