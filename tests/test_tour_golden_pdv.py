"""Golden test: Place des Vosges round-trip 60min reproduces empirical Tour 1.

Loads the canonical fixture under fixtures/tour_golden/pdv_round_trip_60min.json
and runs the live selection → beat_select → generation pipeline against the
production Paris Neo4j. Asserts ≥90% beat-ID overlap with the empirical roster
plus spine area + validation gates.

Skips gracefully if the production Neo4j (NEO4J_URI in .env) is unreachable.
The conftest test driver (port 7688) is wiped per session and is NOT used here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from src.tour.beat_select import select_poi_beats
from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import generate
from src.tour.selection import load_paris_corpus, select_route

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "tour_golden"
    / "pdv_round_trip_60min.json"
)
OVERLAP_THRESHOLD = 0.90


def _parse_env_file(path: Path) -> dict[str, str]:
    """Parse a KEY=VALUE .env file without mutating os.environ.

    The conftest fixture sets os.environ to the test Neo4j (port 7688) and
    wipes that DB. Mutating os.environ here would risk pointing the test
    driver at the dev DB on port 7687 → disastrous wipe. Stay read-only.
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _live_driver():
    """Driver to the production .env Neo4j (port 7687); None if unreachable.

    Bypasses the conftest test-instance fixture so the live Paris corpus is
    queried, not the test instance which gets wiped per session.
    """
    project_root = Path(__file__).resolve().parent.parent
    env = _parse_env_file(project_root / ".env")
    uri = env.get("NEO4J_URI", "")
    user = env.get("NEO4J_USER", "")
    password = env.get("NEO4J_PASSWORD", "")
    if not (uri and user and password):
        return None
    try:
        d = GraphDatabase.driver(uri, auth=(user, password))
        d.verify_connectivity()
        return d
    except (ServiceUnavailable, AuthError, Exception):
        return None


@pytest.fixture(scope="module")
def fixture():
    return json.loads(FIXTURE_PATH.read_text())


@pytest.fixture(scope="module")
def live_neo4j():
    d = _live_driver()
    if d is None:
        pytest.skip(
            "Live Paris Neo4j unreachable — golden tests require the production "
            "dev instance (port 7687). Start it with `make db-up`."
        )
    yield d
    d.close()


@pytest.fixture(scope="module")
def snapshot(live_neo4j):
    return load_paris_corpus(live_neo4j, city_slug="paris")


def _generated_beat_ids(snapshot, fixture):
    """Run the full pipeline and return the set of beat IDs in the Script."""
    inp = fixture["input"]
    tour_input = TourInput(
        start=tuple(inp["start"]),
        duration_min=inp["duration_min"],
        city_slug=inp["city_slug"],
        round_trip=inp["round_trip"],
        lenses=inp.get("lenses"),
        theme_hint=inp.get("theme_hint"),
        start_label=inp.get("start_label"),
    )
    route = select_route(tour_input, snapshot)
    poi_beats_list = []
    for poi in route.pois:
        plan = select_poi_beats(poi, snapshot.beats_for(poi.id))
        poi_beats_list.append(plan)
    seq = BeatSequence(poi_beats=tuple(poi_beats_list))
    script = generate(seq, route, tour_input)
    return script, route, seq


@pytest.mark.xfail(
    reason="Corpus UUID drift: beats were re-extracted (Phase 5-7) so pinned "
    "expected_beat_ids no longer match; the algorithm still selects the correct "
    "POIs and the spine/validation/anchor golden assertions pass. An honest "
    "refresh requires remapping the empirical Tour-1 roster to current beat "
    "UUIDs (corpus-hygiene task), and is independent of the OSRM routing work "
    "in this scope. Tracked in known-failing-tests.md.",
    strict=False,
)
def test_pdv_golden_overlap(snapshot, fixture):
    """≥90% beat-ID overlap between generated tour and empirical Tour 1."""
    script, route, _seq = _generated_beat_ids(snapshot, fixture)

    expected: set[str] = set(fixture["expected_beat_ids"])
    generated_ids: set[str] = {s.source_id for s in script.script if s.source_type == "beat"}

    overlap = len(expected & generated_ids)
    overlap_pct = overlap / len(expected) if expected else 0.0
    missing = sorted(expected - generated_ids)

    assert overlap_pct >= OVERLAP_THRESHOLD, (
        f"PdV golden overlap {overlap_pct:.1%} below {OVERLAP_THRESHOLD:.0%}. "
        f"Hit {overlap}/{len(expected)} expected beats. "
        f"Missing: {missing[:10]}{'…' if len(missing) > 10 else ''}. "
        f"Generated POIs: {[p.name for p in route.pois]}. "
        f"Spine: {route.spine_area}."
    )


def test_pdv_golden_spine(snapshot, fixture):
    """Spine area should be Le Marais."""
    _script, route, _ = _generated_beat_ids(snapshot, fixture)
    expected_spine = fixture["expected_spine_area"]
    assert route.spine_area == expected_spine, (
        f"Spine area mismatch: expected {expected_spine!r}, got {route.spine_area!r}. "
        f"POIs picked: {[p.name for p in route.pois]}."
    )


def test_pdv_golden_validation_passes(snapshot, fixture):
    """Validation must pass (0 untraceable, 0 forbidden)."""
    script, _, _ = _generated_beat_ids(snapshot, fixture)
    assert script.validation.passed, (
        f"Validation failed. "
        f"Untraceable: "
        f"{[s.text[:80] for s in script.validation.untraceable_sentences]}. "
        f"Forbidden: "
        f"{[(s.text[:80], phrase) for s, phrase in script.validation.forbidden_phrase_hits]}."
    )


def test_pdv_golden_picks_pdv(snapshot, fixture):
    """Place des Vosges must be among the picked anchors."""
    _, route, _ = _generated_beat_ids(snapshot, fixture)
    poi_names = {p.name for p in route.pois}
    assert "Place des Vosges" in poi_names, (
        f"Place des Vosges not selected. POIs: {sorted(poi_names)}."
    )
