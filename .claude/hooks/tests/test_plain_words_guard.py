"""Payload tests for .claude/hooks/plain-words-guard.py.

THE TWO THAT MATTER are at the top, and they are not invented examples. They are
the two replies the owner actually reacted to on 2026-09-02:

  * the one they stopped on and answered "What?" — this gate MUST block it;
  * the one they read without objecting — this gate MUST let it through.

The rejected one is verbatim. The accepted one is ABRIDGED — its opening
paragraphs, not the whole reply — and that is worth stating rather than
implying, because an abridged sample is a weaker guarantee than a full one. A
verifier fed the complete reply through the guard on 2026-09-02 and it was
allowed, so the shorter sample here is not hiding a failure; it is just less
evidence than the docstring first claimed.

If either of those goes the wrong way, the rule the gate enforces is not the
rule the owner asked for, and no amount of synthetic passing cases would tell
you that. Everything below them exists to pin the edges.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from breaking_cases import story_of, texts_of

REPO = Path(__file__).resolve().parents[3]
GUARD = REPO / ".claude" / "hooks" / "plain-words-guard.py"


# ── the two real replies ─────────────────────────────────────────────────────

#: What the owner stopped on. Their reply was one word: "What?"
THE_REJECTED_REPLY = (
    "The Vallois campaign is campaign_status: deferred since 2026-04-24 — the "
    "owner pivoted to /pipeline-batch. It and its command go; git keeps them "
    "recoverable. Applying the remaining fixes."
)

#: What they read next and did not object to.
THE_ACCEPTED_REPLY = """You're right, that was gibberish. Here it is in plain words.

Back in April you started a job: re-reading a Paris guidebook and pulling story
facts out of it, one chunk at a time. 22 chunks total.

5 got done. Then you switched to a better method and stopped.

A small file kept score — "5 done, 17 not started." That file lived in the folder
you told me to delete.

So the score file goes with the folder. The command that reads it is then
useless, so it goes too.

Nothing is lost. Git remembers every file it has ever held."""


def transcript(tmp_path, reply, owner_said="Carry on."):
    """A two-record transcript: the owner speaks, then the reply is drafted."""
    path = tmp_path / "transcript.jsonl"
    records = [
        {
            "type": "user",
            "uuid": "owner-1",
            "message": {"content": owner_said},
        },
        {
            "type": "assistant",
            "uuid": "reply-1",
            "message": {"content": [{"type": "text", "text": reply}]},
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in records))
    return path


#: Bumped per call so every `decide` gets its OWN ceiling tally. Sharing one
#: state file made a six-payload loop stand the gate down after the third and
#: report the fourth as a pass — the test lying about the code, not the code
#: failing. The ceiling test below keeps one state file on purpose; it is the
#: only test that wants the tally to carry.
_CALL = [0]


def decide(tmp_path, reply, owner_said="Carry on."):
    """Run the gate over one reply. {} means it let the reply through."""
    _CALL[0] += 1
    state = tmp_path / f"state-{_CALL[0]}.json"
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({
            "transcript_path": str(transcript(tmp_path, reply, owner_said)),
            "session_id": "test-session",
        }),
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(Path.home()),
            "ONDOWAY_PLAIN_WORDS_STATE": str(state),
        },
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout) if done.stdout.strip() else {}


def blocked(decision):
    return decision.get("decision") == "block"


def why(decision):
    return decision.get("reason", "")


# ── the load-bearing pair ────────────────────────────────────────────────────


def test_the_sentence_the_owner_could_not_read_is_refused(tmp_path):
    """The exact sentence that produced "What?". If this passes, the gate is wrong."""
    decision = decide(tmp_path, THE_REJECTED_REPLY)
    assert blocked(decision), "the gate let through the sentence it was built for"
    assert "campaign_status" in why(decision), "name the word that broke it"
    assert "/pipeline-batch" in why(decision)


def test_the_plain_rewrite_the_owner_accepted_goes_through(tmp_path):
    """The matched half. Without it, "block everything" would pass the test above.

    This is the assertion that keeps the gate usable. A guard that refuses the
    good reply as well as the bad one gets switched off within a day, and then
    it guards nothing.
    """
    assert not blocked(decide(tmp_path, THE_ACCEPTED_REPLY))


# ── check 1: a code word used as English ─────────────────────────────────────


def test_a_bare_file_name_is_refused(tmp_path):
    assert blocked(decide(tmp_path, "I changed selection.py and it works now."))


def test_the_same_file_name_in_backticks_is_fine(tmp_path):
    """Backticks are the author admitting it is a name. That is the sanctioned form."""
    assert not blocked(decide(
        tmp_path,
        "I changed `selection.py`, the file that picks which places you visit.",
    ))


def test_a_bare_slash_command_is_refused(tmp_path):
    assert blocked(decide(tmp_path, "Then I ran /pipeline-batch on the new chunks."))


def test_a_bare_flag_is_refused(tmp_path):
    assert blocked(decide(tmp_path, "Pass --live to make it call the real service."))


def test_snake_case_and_camel_case_are_both_caught(tmp_path):
    assert blocked(decide(tmp_path, "The value of max_stops was ignored."))
    assert blocked(decide(tmp_path, "It calls loadParisCorpus before anything else."))


def test_a_command_inside_a_fenced_block_is_never_judged(tmp_path):
    """Commands stay exact — that is the owner's own standing rule."""
    reply = (
        "Run this to see the walk on your phone:\n\n"
        "```bash\n"
        "make flutter-ios ARGS=--profile\n"
        "```\n\n"
        "It builds the app and opens it."
    )
    assert not blocked(decide(tmp_path, reply))


def test_brand_names_that_look_like_code_are_left_alone(tmp_path):
    reply = "The build goes to TestFlight, so iOS and macOS both get it from GitHub."
    assert not blocked(decide(tmp_path, reply))


def test_quoting_the_owners_own_words_back_is_allowed(tmp_path):
    """They wrote it; answering them must be possible."""
    owner = "Why does it say campaign_status: deferred?"
    reply = "Why does it say campaign_status: deferred?\n\nBecause the job was paused."
    assert not blocked(decide(tmp_path, reply, owner_said=owner))


# ── check 2: too many named things ───────────────────────────────────────────


def test_a_reply_that_names_a_handful_of_files_is_fine(tmp_path):
    reply = (
        "I touched `one.py`, the reader.\n"
        "And `two.py`, the writer.\n"
        "And `three.py`, the checker."
    )
    assert not blocked(decide(tmp_path, reply))


def test_a_reply_that_names_fifteen_files_is_a_wall(tmp_path):
    names = " ".join(f"`file{n}.py`" for n in "abcdefghijklmno")
    decision = decide(tmp_path, f"I changed these: {names}")
    assert blocked(decision)
    assert "TOO MANY NAMED THINGS" in why(decision)


def test_grounded_citations_are_never_counted_against_the_reply(tmp_path):
    """The collision a judge caught before this gate was committed.

    `citation-guard.py` runs one slot above this gate and exists to DEMAND
    `file:line` citations. The first draft counted them, capped at five, and so
    refused a seven-citation reply that the other guard was simultaneously
    refusing for being ungrounded. A reply caught between two wired guards can
    satisfy neither, which is how a guard stack stops being usable.
    """
    cites = " ".join(f"`src/tour/mod{n}.py:{n}0`" for n in range(1, 10))
    reply = f"Here is where each one lives. {cites} That is all of them."
    assert not blocked(decide(tmp_path, reply))


# ── check 3: sentence length ─────────────────────────────────────────────────


def test_one_very_long_sentence_is_refused(tmp_path):
    long_one = (
        "I went through the whole thing and found that the reason it was not "
        "working is that the part which reads the file was looking in the old "
        "place rather than the new place where everything actually lives now."
    )
    decision = decide(tmp_path, long_one)
    assert blocked(decision)
    assert "SENTENCE TOO LONG" in why(decision)


def test_short_sentences_pass_however_many_there_are(tmp_path):
    reply = (
        "It was looking in the wrong place.\n"
        "The files moved last week.\n"
        "I pointed it at the new place.\n"
        "It works now."
    )
    assert not blocked(decide(tmp_path, reply))


#: One sentence, well past the limit. Reused below in every marker shape.
A_LONG_SENTENCE = (
    "The reader now looks in the new place rather than the old one, which is "
    "why it finally stopped failing, and it will go on working after the very "
    "next change as well because a fresh test now checks the whole thing every "
    "single time anybody runs it."
)


def test_a_long_sentence_cannot_escape_by_wearing_a_bullet(tmp_path):
    """Four markers, four bypasses, all closed.

    The first draft skipped any line opening with one of these. Bulleted prose
    is this repository's most common reply shape, so skipping them was skipping
    most of the coverage — a judge put the same 49-word sentence through all
    four and it passed every time.
    """
    for marker in ["- ", "* ", "> ", "# ", "1. ", "3) "]:
        decision = decide(tmp_path, marker + A_LONG_SENTENCE)
        assert blocked(decision), f"a long sentence escaped behind {marker!r}"
        assert "SENTENCE TOO LONG" in why(decision)


def test_a_short_bulleted_line_is_still_fine(tmp_path):
    """The marker is stripped, not punished. Ordinary lists must still pass."""
    reply = (
        "Here is what changed:\n\n"
        "- The reader looks in the new place.\n"
        "- A test checks it every time.\n"
        "1. Nothing else moved."
    )
    assert not blocked(decide(tmp_path, reply))


def test_a_table_row_carries_no_sentence(tmp_path):
    """A table is furniture. Measuring its rows as prose would fire on summaries."""
    reply = (
        "| what | where | why it matters to you and to the next person who "
        "reads it and has to work out what on earth was going on here |\n"
        "| --- | --- | --- |"
    )
    assert not blocked(decide(tmp_path, reply))


# ── it must never break the session ──────────────────────────────────────────


def test_every_recorded_web_address_reaches_the_owner(tmp_path):
    """The corpus, fed one entry at a time. See breaking_cases.py for why.

    On 2026-09-02 this gate called `http://127.0.0.1:8010` a filename dropped
    into prose, because the path check below it fires on a slash and a dot and
    every web address has both. The owner's ruling was that banning the one
    shape is the wrong fix, so the whole recorded list is checked here.
    """
    for address in texts_of("web address"):
        decision = decide(tmp_path, f"The dashboard is up. Open it at {address} to watch.")
        assert not blocked(decision), (
            f"{address!r} was refused.\n{story_of(address)}\n"
            f"gate said: {why(decision)}"
        )


def test_a_bare_file_path_in_prose_is_still_refused(tmp_path):
    """The matched half. Exempting addresses must not exempt paths.

    A fix that let through anything with a slash and a dot would pass every
    address AND every bare path, and this gate's first check would be dead
    while still reporting success.
    """
    assert blocked(decide(tmp_path, "I changed src/tour/validation.py and it works now."))


def test_a_malformed_payload_never_blocks(tmp_path):
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input="not json at all",
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
        timeout=60,
    )
    assert done.returncode == 0
    assert not done.stdout.strip()


def test_a_missing_transcript_never_blocks(tmp_path):
    done = subprocess.run(
        [sys.executable, str(GUARD)],
        input=json.dumps({"transcript_path": str(tmp_path / "nope.jsonl")}),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(Path.home())},
        timeout=60,
    )
    assert done.returncode == 0
    assert not done.stdout.strip()


def test_it_stands_down_rather_than_wedge_the_session(tmp_path):
    """Three refusals in a row on one turn, then it steps aside and says so."""
    state = tmp_path / "state.json"

    def run_once():
        done = subprocess.run(
            [sys.executable, str(GUARD)],
            input=json.dumps({
                "transcript_path": str(transcript(tmp_path, THE_REJECTED_REPLY)),
                "session_id": "wedge-test",
            }),
            capture_output=True,
            text=True,
            env={
                "PATH": "/usr/bin:/bin",
                "HOME": str(Path.home()),
                "ONDOWAY_PLAIN_WORDS_STATE": str(state),
            },
            timeout=60,
        )
        assert done.returncode == 0
        return json.loads(done.stdout) if done.stdout.strip() else {}

    assert blocked(run_once())
    assert blocked(run_once())
    assert blocked(run_once())
    stood_down = run_once()
    assert not blocked(stood_down)
    assert "STOOD DOWN" in stood_down.get("systemMessage", "")
