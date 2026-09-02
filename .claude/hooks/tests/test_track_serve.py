"""Tests for `track serve` — the agent dashboard.

WHAT THIS PAGE IS FOR. The owner watching agents build software, and one question:
is this run progressing or spinning? It is the third of three views in this repo
and it shares data with neither. `make workbench` serves the tour editor on port
8000; `make dashboard` serves the Neo4j graph on 8080; this serves agent state.
None can answer another's question, which is why it does not extend `src/server.py`.

ORGANISED BY STORY, NEVER BY STEP. Owner ruling 2026-09-01: "Organize in state
machines and divide by feature / story, to clarify the connection to bigger
picture." A step id tells the owner nothing about what is being built or why. The
rendering these tests hold it to is `.claude/ledger/dashboard-mockup.html`, which
the owner approved.

READ-ONLY, and that is a property worth testing. No agent writes to this page. If
serving could mutate the database, the dashboard would become another surface an
agent could use to make itself look finished.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
TRACK = REPO / ".claude" / "ledger" / "track.py"


def track(*args: str, db: Path, expect_ok: bool = True) -> dict:
    result = subprocess.run(
        [sys.executable, str(TRACK), *args, "--db", str(db)],
        capture_output=True, text=True, cwd=str(REPO), check=False,
    )
    if expect_ok and result.returncode != 0:
        raise AssertionError(f"track {' '.join(args)} exited {result.returncode}\n"
                             f"{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout) if result.stdout.strip() else {}


@pytest.fixture
def served(tmp_path: Path):
    """A running server over a database with one feature and two stories.

    Port 0 so the OS picks a free one — a fixed port would collide with a sibling
    test run, and `track serve` must never be able to take the tour editor's 8000
    or the graph dashboard's 8080 by accident.
    """
    db = tmp_path / "tracker.db"
    track("init", db=db)
    track("feature-add", "--slug", "walking-a-tour",
          "--title", "Walking a tour on the phone",
          "--for-whom", "a tourist in a city they do not know", "--tier", "2", db=db)
    track("story-add", "--feature", "walking-a-tour", "--id", "S-1",
          "--text", "I walk up to a statue and it just starts talking to me.",
          "--said-by", "Nadia, walking with a six-year-old", db=db)
    track("story-add", "--feature", "walking-a-tour", "--id", "S-2",
          "--text", "I paused for coffee and it carried on from the same sentence.",
          "--said-by", "Priya, a slow afternoon", db=db)
    track("issue-add", "--story", "S-1", "--id", "1", "--name", "Arrival starts audio",
          "--test-command", "true", "--files", "mobile/lib/x.dart", db=db)
    track("step-status", "--id", "1", "--status", "completed", db=db)

    proc = subprocess.Popen(
        [sys.executable, str(TRACK), "serve", "--db", str(db), "--port", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REPO),
    )
    # The server prints the port it actually bound, so the test never guesses.
    line = proc.stdout.readline().strip()
    try:
        port = int(json.loads(line)["port"])
    except Exception as exc:  # pragma: no cover - startup failure path
        proc.kill()
        raise AssertionError(f"serve did not announce a port; printed {line!r}") from exc

    yield f"http://127.0.0.1:{port}", db
    proc.terminate()
    proc.wait(timeout=10)


def get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def test_the_page_leads_with_the_feature_in_plain_words(served) -> None:
    base, _ = served
    status, body = get(base + "/")
    assert status == 200
    assert "Walking a tour on the phone" in body
    assert "a tourist in a city they do not know" in body


def test_every_story_appears_in_the_users_own_words(served) -> None:
    base, _ = served
    _, body = get(base + "/")
    assert "I walk up to a statue and it just starts talking to me." in body
    assert "I paused for coffee and it carried on from the same sentence." in body


def test_a_story_carries_its_own_state_machine(served) -> None:
    """One machine per story, in the owner's role names — not one global diagram
    of the machinery, which is identical every run and says nothing about today."""
    base, _ = served
    _, body = get(base + "/")
    for state in ("PM", "Planner", "QA", "Implementer", "Verifier", "Done"):
        assert state in body
    assert body.count("data-story-machine") == 2, "one machine per story, no more, no fewer"


def test_no_step_id_is_used_as_a_heading(served) -> None:
    """The owner's complaint about the first mockup: rows were step ids with no
    story attached, which told them nothing about what was being built."""
    base, _ = served
    _, body = get(base + "/")
    assert "data-story-machine" in body
    assert body.index("Walking a tour on the phone") < body.index("data-story-machine")


def test_the_json_endpoint_serves_what_the_page_renders(served) -> None:
    base, _ = served
    status, body = get(base + "/api/state")
    assert status == 200
    payload = json.loads(body)
    assert payload["features"][0]["slug"] == "walking-a-tour"
    assert {s["id"] for s in payload["stories"]} == {"S-1", "S-2"}
    assert payload["health"]["progress"] == 100


def test_the_event_log_is_served_newest_first(served) -> None:
    base, _ = served
    _, body = get(base + "/api/state")
    events = json.loads(body)["events"]
    assert events, "the log is what draws the state machine; an empty one is a bug"
    assert [e["id"] for e in events] == sorted((e["id"] for e in events), reverse=True)


def test_serving_never_writes(served) -> None:
    """A dashboard that can mutate the database is one more surface an agent could
    use to look finished."""
    base, db = served
    before = Path(db).read_bytes()
    for path in ("/", "/api/state", "/api/state"):
        get(base + path)
    assert Path(db).read_bytes() == before


def test_a_post_is_refused(served) -> None:
    base, _ = served
    request = urllib.request.Request(base + "/api/state", data=b"{}", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # pragma: no cover
            assert response.status >= 400
    except urllib.error.HTTPError as err:
        assert err.code in (400, 405, 501)


def test_an_unknown_path_is_not_the_dashboard(served) -> None:
    base, _ = served
    status, _ = get(base + "/../../etc/passwd")
    assert status != 200


def test_the_page_says_it_is_read_only(served) -> None:
    base, _ = served
    _, body = get(base + "/")
    assert "Read-only" in body


def test_a_replan_is_named_on_the_page_by_its_story(served) -> None:
    """A stuck machine must name its story; that story names its feature. That is
    the whole bigger-picture link."""
    base, db = served
    track("story-state", "--id", "S-2", "--state", "Implementer", db=db)
    track("story-state", "--id", "S-2", "--state", "Verifier", db=db)
    track("story-state", "--id", "S-2", "--state", "Implementer",
          "--sent-back", "--why", "same failure", db=db)
    track("story-state", "--id", "S-2", "--state", "Verifier", db=db)
    track("story-state", "--id", "S-2", "--state", "Implementer",
          "--sent-back", "--why", "same failure again", db=db)

    _, body = get(base + "/")
    assert "S-2" in body
    _, api = get(base + "/api/state")
    health = json.loads(api)["health"]
    assert health["replan_required"] is True
    assert health["story"] == "S-2"


def test_it_refuses_the_ports_that_belong_to_other_views(tmp_path: Path) -> None:
    """8000 is the tour editor's API, 8080 the graph dashboard, 7687/7688 the
    databases. Binding one of those would take a running service down."""
    db = tmp_path / "tracker.db"
    track("init", db=db)
    for port in ("8000", "8001", "8080", "7687", "7688"):
        result = subprocess.run(
            [sys.executable, str(TRACK), "serve", "--db", str(db), "--port", port],
            capture_output=True, text=True, cwd=str(REPO), check=False, timeout=30,
        )
        assert result.returncode != 0, f"serve agreed to bind {port}"


def test_an_empty_database_still_renders(tmp_path: Path) -> None:
    """Before the PM has written anything. A dashboard that crashes on an empty
    plan is a dashboard nobody opens at the start of a run."""
    db = tmp_path / "tracker.db"
    track("init", db=db)
    proc = subprocess.Popen(
        [sys.executable, str(TRACK), "serve", "--db", str(db), "--port", "0"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(REPO),
    )
    try:
        port = int(json.loads(proc.stdout.readline().strip())["port"])
        status, body = get(f"http://127.0.0.1:{port}/")
        assert status == 200
        assert "Nothing planned yet" in body
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_the_database_is_opened_read_only(served) -> None:
    """Belt as well as braces: even a bug in a handler cannot write."""
    _, db = served
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        assert conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0] == 2
