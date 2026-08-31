"""Payload tests for .claude/hooks/citation-guard.py.

The guard is a Stop hook: it reads a transcript and either lets the reply stand
or blocks it. These tests feed it real stdin payloads over synthetic transcripts
and assert the decision, because the guard's own history is a history of arms
that went SILENTLY dead — a pattern that did not expect a sentence-ending period,
a prefilter that knew `flaky` but not `flake`. A starved arm looks exactly like a
satisfied one, so every arm gets a payload that must block and a payload that
must not.

CASE ONE IS THE OWNER'S 2026-08-29 RULING. A reply asserted, from a commit
message rather than the code, that the workbench "signs in with a real identity
and calls the same phone endpoints" — and the guard stayed silent, because the
sentence named no path outside backticks. The owner: "It should ALWAYS fire. It
should NEVER EVER stop firing just because of how you write." That exact reply is
`test_the_2026_08_29_escape_is_closed`.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

# These tests live BESIDE the hook they test, not in the product's tests/ tree.
# The subject here is agent supervision, not Ondoway: it must never run inside
# `make test`, which is the bar that answers "does the product work". Same
# precedent as .claude/team-engine.test.js. Three levels up from
# .claude/hooks/tests/ is the repository root.
REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / ".claude" / "hooks" / "citation-guard.py"

# A real tracked product file with a real symbol in it, used as the thing a reply
# names or cites. Derived, not invented: the doors walk in
# test_surfaces_share_one_engine.py reports plan_premium_full_telling here.
PRODUCT_FILE = "src/tour/premium_tour.py"
PRODUCT_SYMBOL = "plan_premium_full_telling"


def defining_line(relative, symbol):
    """The line `symbol` is defined on, parsed out rather than written down.

    Hardcoding it would make this file a second place the codebase's shape is
    recorded, and the first edit above that line would make the test a liar.
    """
    tree = ast.parse((REPO / relative).read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
            return node.lineno
    raise AssertionError(f"{symbol} is no longer defined in {relative}")


PRODUCT_LINE = defining_line(PRODUCT_FILE, PRODUCT_SYMBOL)


# ------------------------------------------------------------------ transcripts


def human(text):
    return {"type": "user", "message": {"content": text}}


def assistant(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def tool_call(name, tool_input):
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]},
    }


def tool_result(text="ok"):
    return {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": text}]},
    }


def decide(tmp_path, records, session):
    """Run the guard over `records` and return its decision dict ({} = allowed)."""
    transcript = tmp_path / f"{session}.jsonl"
    transcript.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    result = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"transcript_path": str(transcript), "session_id": session}),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


def blocked(decision):
    return decision.get("decision") == "block"


# ------------------------------------------------------------------- arm 3 / the ruling


def test_the_2026_08_29_escape_is_closed(tmp_path):
    """The exact reply that slipped through, verbatim in shape.

    It names three product functions, every one of them inside backticks, and
    cites no line. Under the old guard this was silent: arm 2 asked only about
    PATHS named OUTSIDE backticks, and this reply named none.
    """
    reply = (
        "The work you described is already done and merged.\n\n"
        "All three gaps are closed:\n"
        f"| `{PRODUCT_SYMBOL}` | yes | yes |\n"
        "| `build_poi_extra_beats` | yes | yes |\n"
        "| `build_poi_extra_narration` | yes | yes |\n\n"
        "The workbench does not have its own copy of the full telling. It signs "
        "in with a real identity and calls the same phone endpoints, in the "
        "phone order, with the phone payloads."
    )
    decision = decide(tmp_path, [human("is it done?"), assistant(reply)], "escape")
    assert blocked(decision), "the owner's ruling: naming the code must always fire"
    assert PRODUCT_SYMBOL in decision["reason"]
    assert PRODUCT_FILE in decision["reason"]


def test_touching_product_code_obliges_a_citation_whatever_the_wording(tmp_path):
    """Arm 3. The reply names nothing at all; the TURN opened a product file."""
    records = [
        human("check the workbench"),
        tool_call("Read", {"file_path": str(REPO / PRODUCT_FILE)}),
        tool_result(),
        assistant("Everything the tourist reaches, the editor reaches too. Done."),
    ]
    decision = decide(tmp_path, records, "arm3-read")
    assert blocked(decision), "a guard you can silence by rephrasing is not a guard"
    assert "cites no line" in decision["reason"]


def test_a_bash_command_naming_product_code_also_obliges_a_citation(tmp_path):
    records = [
        human("what changed?"),
        tool_call("Bash", {"command": f"wc -l {REPO}/{PRODUCT_FILE}"}),
        tool_result("1272"),
        assistant("That file is about as long as I expected. Nothing to worry about."),
    ]
    assert blocked(decide(tmp_path, records, "arm3-bash"))


def test_the_workbench_page_is_product_code_too(tmp_path):
    """frontend/ was the first rewrite's own blind spot.

    The false sentence this guard was rebuilt for is a claim about
    frontend/review.html — and that file sat outside every trigger, because
    PRODUCT_ROOTS named only src/ and mobile/lib/. CLAUDE.md rule 1 binds the two
    surfaces equally; so must this.
    """
    records = [
        human("does the editor run the tourist's path?"),
        tool_call("Read", {"file_path": str(REPO / "frontend/review.html")}),
        tool_result(),
        assistant(
            "It signs in with a real identity and calls the same phone endpoints, "
            "in the phone order, with the phone payloads."
        ),
    ]
    assert blocked(decide(tmp_path, records, "frontend-root"))


def test_a_background_notification_does_not_end_the_turn(tmp_path):
    """A finished job must not silence arm 3 for the reply after it.

    Verified against this project's transcript, 2026-08-29: a task notification
    is stored as `type: "user"` with plain string content and no tool_result —
    the exact shape of a typed message. Counting it as the person speaking would
    drop every product Read before it out of the turn, so a reply landing just
    after a build finished would owe nothing. That is the same "stops firing"
    class as the wording escape, reached by timing instead.
    """
    notification = {
        "type": "user",
        "message": {"content": "<task-notification>\n<task-id>b3uuq0jw2</task-id>\n"
                               "<status>completed</status>\n</task-notification>"},
    }
    records = [
        human("check the planner"),
        tool_call("Read", {"file_path": str(REPO / PRODUCT_FILE)}),
        tool_result(),
        notification,
        assistant("All good — the tourist's path and the editor's now agree."),
    ]
    assert blocked(decide(tmp_path, records, "notification-boundary"))


def test_arm_three_is_scoped_to_this_turn_not_the_whole_session(tmp_path):
    """A product Read in an EARLIER turn must not tax every later reply.

    Without this scoping the guard would demand a citation forever after the
    first product file it ever saw, which is the noise the ledger records as
    fatal to a guard.
    """
    records = [
        human("read the planner"),
        tool_call("Read", {"file_path": str(REPO / PRODUCT_FILE)}),
        tool_result(),
        assistant("Read it."),
        human("now just run the suite"),
        tool_call("Bash", {"command": "make -C /Users/x/ondoway test"}),
        tool_result("389 passed"),
        assistant("389 passed, 0 failed. Nothing needed from you."),
    ]
    assert not blocked(decide(tmp_path, records, "arm3-scope"))


# ------------------------------------------------------------------- arm 2 / symbols


def test_naming_a_symbol_is_satisfied_by_citing_its_defining_file(tmp_path):
    records = [
        human("is the full telling reached?"),
        tool_call("Read", {"file_path": str(REPO / PRODUCT_FILE)}),
        tool_result(),
        assistant(
            f"The workbench reaches `{PRODUCT_SYMBOL}`, which is defined at "
            f"{PRODUCT_FILE}:{PRODUCT_LINE} and entered from the compose route."
        ),
    ]
    assert not blocked(decide(tmp_path, records, "arm2-proven"))


def test_citing_the_wrong_file_does_not_prove_the_symbol(tmp_path):
    """A citation elsewhere is not a citation into the file that defines it."""
    other = "src/tour/options.py"
    records = [
        human("is the full telling reached?"),
        tool_call("Read", {"file_path": str(REPO / other)}),
        tool_result(),
        assistant(f"The workbench reaches `{PRODUCT_SYMBOL}`; see {other}:1."),
    ]
    decision = decide(tmp_path, records, "arm2-wrong-file")
    assert blocked(decision)
    assert PRODUCT_FILE in decision["reason"]


def test_an_ordinary_english_word_that_is_also_a_symbol_never_fires(tmp_path):
    """src/ defines `generate`, `gravity` and `spotlight`.

    Ordinary prose using those words is not a code claim, and a guard that blocks
    it gets deleted — taking the arms that work with it.
    """
    records = [
        human("what did you do?"),
        assistant(
            "I asked it to generate the trip, watched the gravity of the day "
            "settle, and put the spotlight on the second stop. It reads well."
        ),
    ]
    assert not blocked(decide(tmp_path, records, "arm2-english"))


# ------------------------------------------------------------------------- arm 1


def test_a_citation_to_a_file_never_opened_is_refused(tmp_path):
    records = [
        human("where is it?"),
        assistant(f"It happens at {PRODUCT_FILE}:12, as you would expect."),
    ]
    decision = decide(tmp_path, records, "arm1-unread")
    assert blocked(decision)
    assert "never opened" in decision["reason"]


def test_a_line_past_the_end_of_the_file_is_refused(tmp_path):
    records = [
        human("where is it?"),
        tool_call("Read", {"file_path": str(REPO / PRODUCT_FILE)}),
        tool_result(),
        assistant(f"It happens at {PRODUCT_FILE}:999999."),
    ]
    decision = decide(tmp_path, records, "arm1-overrun")
    assert blocked(decision)
    assert "outside it" in decision["reason"]


# -------------------------------------------------------------------- no false alarms


def test_an_honest_suite_report_is_allowed(tmp_path):
    records = [
        human("run the suite"),
        tool_call("Bash", {"command": "make -C /Users/x/ondoway test"}),
        tool_result("389 passed"),
        assistant("389 passed, 0 failed, in 4m12s. Nothing needed from you."),
    ]
    assert not blocked(decide(tmp_path, records, "clean-suite"))


def test_a_test_file_named_without_a_line_is_allowed(tmp_path):
    """tests/ is not product code; a run report names its files legitimately."""
    records = [
        human("which test?"),
        assistant("tests/test_surfaces_share_one_engine.py is the one that walks both."),
    ]
    assert not blocked(decide(tmp_path, records, "clean-tests"))
