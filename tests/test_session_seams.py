"""Phase 5 — the two SEAMS of the living session (design §4.6; plan S5.9/S5.10).

The 2026-08-18 amendment to the plan (phase4-ledger.md "TEST CULL"): each seam is
BEHAVIOURAL wherever a behavioural check can exist, and a source scan ONLY where the
invariant is about the source itself — and says so in its docstring. The one-engine
moulds this file replaces (`test_tour_one_engine.py`, `_mentions`, the tombstones)
were retired with the cull; the shape kept here from them is what made them honest:
NON-VACUITY FIRST (the files exist and are the ones we mean), a git-index check (a
file that vanished from the tree is not "clean"), and an anti-over-deletion clause
naming what must SURVIVE.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
MOBILE_LIB = ROOT / "mobile" / "lib"
MOBILE_TEST = ROOT / "mobile" / "test"

#: The ONE Dart method that changes the current plan; its only decision input is a
#: server contingency id (design §4.6; plan S5.9 — "the phone SELECTS, it never
#: DECIDES").
THE_ONE_SELECTOR = "bool applyContingency(String contingencyId)"

#: Vocabulary of a second replan brain. Any of these under mobile/ is a defect: the
#: phone holds "no scoring, no candidate pool, no policy" (§4.6). Matched as whole
#: words / identifiers, case-insensitive on the words, exact on the identifiers.
BANNED_BRAIN_WORDS: tuple[str, ...] = (
    r"\bcandidate(s)?\b",
    r"\bbestAlternate\b",
    r"\b_bestAlternate\b",
    r"\bchooseBest\w*\b",
    r"\bpickBest\w*\b",
    r"\bbestOf\w*\b",
    r"\brank(ed|ing)?\b",
    r"\bscore(d|s|Stop|Entry|Route)?\b",
    r"\bpoi_score\b",
    r"\binsertionCost\w*\b",
    r"\bheldKarp\b",
    r"\bHeld-Karp\b",
    r"\bgreedy\b",
    r"\bplan(Route|Day|Tour)\b",
    r"\breplan(Route|Day|Tour)\b",
    r"\bselectRoute\b",
    r"\bcontingencyFor\w*\b",
    r"\btieBreak\w*\b",
)

#: What must SURVIVE under mobile/lib — the anti-over-deletion clause: the phone's
#: arithmetic (§4.6's one permitted computation), the prefetch door (§4.7), and the
#: session vocabulary this phase adds. An over-eager sweep that deleted these would
#: pass the ban and fail here.
SURVIVING_MOBILE_NEIGHBOURS: tuple[str, ...] = (
    "haversineDistance",
    "prefetchAudio",
    "prefetchSessionAudio",
    "matchContingency",
    "holdSession",
    "SessionPlan",
    "SessionContingency",
    "fetchSession",
    "replanSession",
)


def _dart_files() -> list[pathlib.Path]:
    return sorted([*MOBILE_LIB.rglob("*.dart"), *MOBILE_TEST.rglob("*.dart")])


def _tracked() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files", "--", "mobile/lib", "mobile/test"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return set(out)


def test_the_replan_brain_is_only_on_the_server():
    """SEAM 1 (plan S5.9; design §4.6 "One replan brain — the phone SELECTS, it never
    DECIDES"). The invariant is an ABSENCE of code — no scoring, ranking, candidate
    pool or plan construction anywhere under mobile/ — which cannot be proven
    behaviourally, so this half is a source scan and says so. The BEHAVIOURAL half
    of the seam lives in mobile/test/services/session_selection_test.dart: the
    first matching entry in server order is selected, exactly one method changes the
    plan on a server id, the question's default holds until answered, alternates
    prefetch through the existing cache door.

    Non-vacuity first: the Dart tree exists, is tracked, and carries the session
    vocabulary. Then the ban. Then the positive clause: exactly ONE Dart method
    changes the current plan and its only decision input is a server contingency
    id. RED by mutation: add a local `_bestAlternate()` to the playback service.
    """
    files = _dart_files()
    assert len(files) >= 20, f"the Dart tree is not where this seam expects it ({len(files)})"
    tracked = _tracked()
    playback = MOBILE_LIB / "services" / "tour_playback_service.dart"
    for must in (
        "services/tour_playback_service.dart",
        "services/trip_service.dart",
        "models/trip.dart",
        "services/audio_service.dart",
    ):
        assert (MOBILE_LIB / must).exists(), f"{must} vanished from mobile/lib"
        assert f"mobile/lib/{must}" in tracked, f"{must} is not in the git index"

    corpus = {p: p.read_text(encoding="utf-8") for p in files}
    lib_text = "\n".join(t for p, t in corpus.items() if MOBILE_LIB in p.parents)

    # NON-VACUITY: the things that must survive are present.
    for name in SURVIVING_MOBILE_NEIGHBOURS:
        assert name in lib_text, f"{name!r} is missing from mobile/lib — the sweep over-deleted"

    # THE BAN: no second brain's vocabulary anywhere under mobile/.
    hits: list[str] = []
    for path, text in corpus.items():
        for pattern in BANNED_BRAIN_WORDS:
            for m in re.finditer(pattern, text, flags=re.IGNORECASE):
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{path.relative_to(ROOT)}:{line}: {m.group(0)!r}")
    assert not hits, "a replan brain is growing in the app:\n  " + "\n  ".join(hits[:20])

    # THE POSITIVE CLAUSE: exactly ONE method changes the current plan, keyed on a
    # server contingency id, and the working stop list is assigned only by the
    # tour lifecycle and that method's re-ordering.
    play_src = corpus[playback]
    assert play_src.count(THE_ONE_SELECTOR) == 1, "the one selector is not exactly one"
    assignments = re.findall(r"^\s*_stops = .*$", play_src, flags=re.MULTILINE)
    assert len(assignments) == 3, (
        "the working stop list is assigned only in startTour, stopTour and the "
        f"selector's re-ordering; found {len(assignments)}: {assignments}"
    )


def _body_of(source: str, signature: str) -> str:
    """The text of one Dart/Python method from its signature to the next member
    at the same indentation — enough for an is-it-in-there scan."""
    start = source.index(signature)
    indent = source[: start].rsplit("\n", 1)[-1]
    rest = source[start + len(signature) :]
    end = re.search(rf"\n{indent}(?:[A-Za-z@/]|\}})", rest)
    return rest if end is None else rest[: end.start()]


def test_the_session_clock_is_checked_against_the_server():
    """SEAM 2 (plan S5.10; design §4.6 — the silent-divergence bug the one-brain
    rule exists to prevent). Exactly ONE re-timing expression each side; the
    reconnect path COMPARES them; a divergence beyond `retime_tolerance_seconds`
    is REPORTED (a row on the degradations channel on the server, a line for the
    screen on the phone) and never silently corrected — no assignment from the
    server's clock back into the local one, and none the other way.

    The BEHAVIOURAL halves live where behaviour can be run: on the server,
    tests/test_trip_api.py::TestLivingSession::test_a_phone_clock_that_diverges_is_reported_never_corrected
    (live corpus: the row appears, the reply keeps the server's clock) and
    tests/test_tour_session.py (the one expression prices narration at the learned
    rate; the finish is its view); on the phone,
    mobile/test/services/session_arithmetic_test.dart ("REPORTED, never corrected":
    the notice appears, the phone's re-timing is unchanged). What ONLY a source
    read can assert is the ONE-ness and the ABSENCE — one `stop_clocks`, one
    `retimeRemaining`, no second running clock, and no assignment inside either
    compare — so that half is a scan and says so. RED by mutation: correct the
    phone from the server inside `_compareClockWithServer` (an assignment) -> RED;
    a second walk-less clock in the CRUD adapter -> RED.
    """
    src_dir = ROOT / "src"
    py = {p: p.read_text(encoding="utf-8") for p in sorted(src_dir.rglob("*.py"))}
    contingency = src_dir / "tour" / "contingency.py"
    routes = src_dir / "api" / "routes" / "trips.py"
    crud = src_dir / "api" / "crud" / "trips.py"
    for must in (contingency, routes, crud):
        assert must.exists(), f"{must} vanished"

    # ONE server expression, and everything that spells a clock is a view of it.
    definitions = [p for p, t in py.items() if "def stop_clocks(" in t]
    assert definitions == [contingency], definitions
    assert py[contingency].count("def stop_clocks(") == 1
    finish = _body_of(py[contingency], "def finish_clock(")
    assert "stop_clocks(" in finish and "total_walk_seconds + sum(" not in finish, (
        "finish_clock must be a VIEW of stop_clocks, not a second sum"
    )
    for view in ("def _wire_clocks(", "def _session_promises("):
        assert "stop_clocks(" in _body_of(py[routes], view), f"{view} does not read the one clock"
    # The CRUD adapter's walk-less running clock is gone (S5.10): it writes what
    # it is handed.
    adapter = _body_of(py[crud], "def route_script_to_stops(")
    assert "current_minute" not in adapter and "current_hour" not in adapter, (
        "a second, walk-less clock is back in the adapter"
    )
    assert "clocks.get(sp.id" in adapter

    # The server COMPARES and REPORTS, and assigns nothing.
    report = _body_of(py[routes], "def _report_phone_clock(")
    assert "clock_divergence_seconds(" in report and "record(" in report
    assert "SESSION_CLOCK_DIVERGENCE" in report
    assert re.search(r"session_plan\.stops\[[^\]]*\]\s*=", report) is None, (
        "the server adopted the phone's clock"
    )
    assert re.search(r"^\s*(?:first|session_plan)\.\w+\s*=", report, re.M) is None
    assert "_report_phone_clock(" in _body_of(py[routes], "def replan_trip_session(")

    # ONE phone expression, COMPARED on every held version, REPORTED, no assignment.
    playback = (MOBILE_LIB / "services" / "tour_playback_service.dart").read_text(encoding="utf-8")
    assert playback.count("List<StopEta> retimeRemaining()") == 1
    assert playback.count("kHaversineCorrection / paceMps") == 1, (
        "the walk arithmetic must be spelled once (the one _walkSeconds helper)"
    )
    assert playback.count("int _walkSeconds(double meters)") == 1
    assert playback.count("_walkSeconds(") >= 3  # its definition and its two readers
    assert playback.count("void _compareClockWithServer(SessionPlan session)") == 1
    hold = _body_of(playback, "void holdSession(SessionPlan session)")
    assert "_compareClockWithServer(session);" in hold
    compare = _body_of(playback, "void _compareClockWithServer(SessionPlan session)")
    assert "retimeRemaining()" in compare and "_serverClockFor(" in compare
    assert "_clockNotices.add(" in compare and "retimeToleranceSeconds" in compare
    assert re.search(r"^\s*_\w+\s*=[^=]", compare, re.M) is None, (
        "the compare assigns into the phone's state — the server is correcting the phone:\n"
        + compare
    )
    assert re.search(r"^\s*_\w+\s*[-+*/]=", compare, re.M) is None
    # The behavioural halves are where the docstring says.
    arithmetic = MOBILE_TEST / "services" / "session_arithmetic_test.dart"
    assert arithmetic.exists()
    assert "REPORTED, never corrected" in arithmetic.read_text(encoding="utf-8")
    api_test = (ROOT / "tests" / "test_trip_api.py").read_text(encoding="utf-8")
    assert "def test_a_phone_clock_that_diverges_is_reported_never_corrected(" in api_test
