"""M8 GRADE—rubric checks plus the live regression gate.

The grade shard owns this entire file. It runs the pure rubric checks and the
real dev-graph gate together, with no marker deselections.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tour.grade import GRADE_BASELINE, grade_tour

pytestmark = pytest.mark.grade

# ---------------------------------------------------------------------------
# Pure rubric (runs in the default bar)
# ---------------------------------------------------------------------------

_FIXTURE = {
    "expected_pois": ["A", "B", "C", "D"],
    "expected_beat_ids": ["b1", "b2", "b3", "b4", "b5"],
    "expected_spine_area": "Le Marais",
}


def test_perfect_tour_scores_one():
    g = grade_tour(
        generated_poi_names=["A", "B", "C", "D"],
        generated_beat_ids=["b1", "b2", "b3", "b4", "b5"],
        generated_spine_area="Le Marais",
        validation_passed=True,
        fixture=_FIXTURE,
    )
    assert g.score == pytest.approx(1.0)
    assert g.passed


def test_axes_weight_as_documented():
    # All POIs, half the beats, right spine, valid:
    # 0.4*1 + 0.3*0.4 + 0.2*1 + 0.1*1 = 0.82
    g = grade_tour(
        generated_poi_names=["A", "B", "C", "D"],
        generated_beat_ids=["b1", "b2"],  # 2/5 = 0.4 overlap
        generated_spine_area="Le Marais",
        validation_passed=True,
        fixture=_FIXTURE,
    )
    assert g.poi_recall == pytest.approx(1.0)
    assert g.beat_overlap == pytest.approx(0.4)
    assert g.score == pytest.approx(0.82)


def test_lost_pois_and_beats_fail_baseline():
    # Wrong POIs entirely, no beats: 0.4*0 + 0.3*0 + 0.2*1 + 0.1*1 = 0.30
    g = grade_tour(
        generated_poi_names=["X", "Y"],
        generated_beat_ids=[],
        generated_spine_area="Le Marais",
        validation_passed=True,
        fixture=_FIXTURE,
    )
    assert g.score == pytest.approx(0.30)
    assert not g.passed
    assert g.score < GRADE_BASELINE


def test_wrong_spine_and_failed_validation_dock_their_weights():
    g = grade_tour(
        generated_poi_names=["A", "B", "C", "D"],
        generated_beat_ids=["b1", "b2", "b3", "b4", "b5"],
        generated_spine_area="Wrong Area",
        validation_passed=False,
        fixture=_FIXTURE,
    )
    # 0.4 + 0.3 + 0 + 0 = 0.70
    assert g.score == pytest.approx(0.70)
    assert g.spine_match == 0.0
    assert g.validation == 0.0


def test_empty_expectations_recall_is_one():
    g = grade_tour(
        generated_poi_names=[],
        generated_beat_ids=[],
        generated_spine_area=None,
        validation_passed=True,
        fixture={"expected_pois": [], "expected_beat_ids": [], "expected_spine_area": None},
    )
    assert g.poi_recall == 1.0 and g.beat_overlap == 1.0


# ---------------------------------------------------------------------------
# Live regression gate (marked grade; excluded from make test)
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "tour_golden"
_GOLDENS = ["ile_oneway_90min", "pdv_round_trip_60min"]


def _live_graded(fixture: dict):
    """Run the real pipeline for a fixture's input and grade it. Skips (→ fails
    under conftest) only handled by the caller via the live driver helper."""
    from src.tour.beat_select import select_poi_beats
    from src.tour.contract import BeatSequence, TourInput
    from src.tour.generation import generate
    from src.tour.routing_client import RoutingClient
    from src.tour.selection import select_route

    inp = fixture["input"]
    tour_input = TourInput(
        start=tuple(inp["start"]), duration_min=inp["duration_min"],
        city_slug=inp["city_slug"], round_trip=inp["round_trip"], lenses=inp.get("lenses"),
    )
    snapshot = _SNAPSHOT
    with RoutingClient() as rc:
        route = select_route(tour_input, snapshot, routing_client=rc)
    plans = [select_poi_beats(p, snapshot.beats_for(p.id)) for p in route.pois]
    script = generate(BeatSequence(poi_beats=tuple(plans)), route, tour_input)
    gen_beats = [s.source_id for s in script.script if s.source_type == "beat"]
    return route, grade_tour(
        generated_poi_names=[p.name for p in route.pois],
        generated_beat_ids=gen_beats,
        generated_spine_area=route.spine_area,
        validation_passed=script.validation.passed,
        fixture=fixture,
    )


_SNAPSHOT = None  # module-level cache set by the fixture below


@pytest.fixture(scope="module", autouse=True)
def _live_snapshot():
    """Load the live Paris corpus once; skip the grade tests if it's down."""
    global _SNAPSHOT
    from src.tour.selection import load_paris_corpus
    from tests.live_graph import open_dev_driver

    d = open_dev_driver()
    if d is None:
        pytest.skip("live dev Neo4j unreachable — start it with `make db-up`")
    _SNAPSHOT = load_paris_corpus(d, city_slug="paris")
    d.close()
    yield


@pytest.mark.parametrize("name", _GOLDENS)
def test_live_golden_clears_grade_baseline(name):
    fixture = json.loads((_FIXTURE_DIR / f"{name}.json").read_text())
    _route, g = _live_graded(fixture)
    assert g.passed, f"{name} regressed: {g.breakdown()}"


def test_broken_golden_drops_below_baseline():
    """PROVE: corrupt a golden's expectations and the SAME live output grades
    below baseline — the gate genuinely catches a regression, not a tautology."""
    fixture = json.loads((_FIXTURE_DIR / "ile_oneway_90min.json").read_text())
    _route, real = _live_graded(fixture)
    assert real.passed  # sanity: real output passes

    broken = dict(fixture)
    broken["expected_pois"] = ["Eiffel Tower", "Sacre-Coeur", "Louvre", "Arc de Triomphe"]
    broken["expected_beat_ids"] = ["nonexistent-1", "nonexistent-2", "nonexistent-3"]
    broken["expected_spine_area"] = "Montmartre"
    _route2, broken_grade = _live_graded(broken)
    assert not broken_grade.passed, f"broken golden should fail: {broken_grade.breakdown()}"
    assert broken_grade.score < GRADE_BASELINE
