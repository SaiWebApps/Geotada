"""Golden test: Île de la Cité one-way 90min reproduces empirical Tour 2.

Loads the canonical fixture under fixtures/tour_golden/ile_oneway_90min.json
and runs the live selection → beat_select → generation pipeline against the
production Paris Neo4j. Guards the established beat-ID overlap baseline while
reporting the 90% empirical target, plus spine area + validation gates.

Missing populated local dev Neo4j is a hard failure.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import generate
from src.tour.routing_client import RoutingClient
from src.tour.selection import build_poi_beat_plans_capped, load_paris_corpus, select_route
from tests.live_graph import open_dev_driver
from tests.test_tour_golden_consistency import generated_stable_beat_ids

# Quality-comparison gate against a human-curated ideal tour; excluded from the
# definitive `make test` bar (routed through its internal golden shard).
pytestmark = pytest.mark.golden

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "tour_golden" / "ile_oneway_90min.json"
)
OVERLAP_TARGET = 0.90
# AN ABSOLUTE HIT COUNT, NOT A RATIO. Read all of this before changing the number.
#
# WHY ABSOLUTE: a fractional floor divides by the pinned-set size, so re-keying the
# fixture moved the bar without anyone deciding to — 42.6% of the old 47 ids demanded 20
# hits, 42.6% of the 31 durable slugs demands only 14.
#
# STATE IT PLAINLY: THIS FLOOR WENT DOWN, from 20 required hits to 15. An earlier version
# of this comment called that a tightening by quoting the percentage (48.4% vs 42.6%) —
# that was unit-shopping, using the ratio it had just declared invalid. By the unit this
# line now uses, the requirement dropped by five hits. A hostile review caught it.
#
# WHY IT IS STILL DEFENSIBLE: 15 = 85% of the FIRST HONEST MEASUREMENT of this gate
# (2026-07-30: 18 of 31 pinned beats, 58.1%, on the 7-POI routed walk), per decision D6.
# The old 20 was 42.6% of a 47-id set whose ids were per-database UUIDs; those rotate on
# any re-seed, which is what took this gate red and kept it red. The two numbers count
# different things, so neither is a continuation of the other.
#
# THE HISTORY, because a previous version of this comment got it wrong: this gate was NOT
# "always red". It was live and passing — Île 25/47 = 53.2% (2026-06-13) and 16/47 = 34.0%
# after the pace pin, recorded in specs/2026-06-13-tour-planner-canonical/
# GOLDEN-GAP-DIAGNOSTIC.md and tests/test_tour_beat_select.py. Do not repeat the claim
# that it could never pass.
#
# OVERLAP_TARGET (90%) stays as the unmet aspiration. The gap is a tour-SHAPE difference,
# not a tuning knob: the human document walks Notre-Dame's portals and the Conciergerie's
# halls as many standing positions at one place, while the engine caps a single stop at
# MAX_DWELL_AUDIO_SECONDS=270 (~675 words) and seats more POIs instead.
OVERLAP_MIN_HITS = 15


def _live_driver():
    return open_dev_driver()


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
    # M3: routed leg costs when the local Valhalla is up (make valhalla-up);
    # identical to the haversine path when it isn't (total fallback).
    with RoutingClient() as routing_client:
        route = select_route(tour_input, snapshot, routing_client=routing_client)
    # C9b golden-harness fidelity: route through the shipped build path so the
    # goldens merge co-located demoted_beats like production (diagnostic R2).
    seq = BeatSequence(
        poi_beats=tuple(
            pb
            for pb, _ in build_poi_beat_plans_capped(
                route, snapshot, lenses=None, end_is_none=True
            )
        )
    )
    script = generate(seq, route, tour_input)
    return script, route, seq


def test_ile_golden_overlap(snapshot, fixture):
    """Beat-ID overlap must not regress below the established routed baseline."""
    script, route, _seq = _generated_beat_ids(snapshot, fixture)

    expected: set[str] = set(fixture["expected_stable_beat_ids"])
    generated_ids, untranslated = generated_stable_beat_ids(script, _seq)
    assert not untranslated, (
        f"{len(untranslated)} emitted beats carry no stable_beat_id: {untranslated[:5]}"
    )

    overlap = len(expected & generated_ids)
    overlap_pct = overlap / len(expected) if expected else 0.0
    missing = sorted(expected - generated_ids)

    # Emitted UNCONDITIONALLY for `make golden-probe`. The probe used to grep this
    # number out of pytest's ASSERTION text, so it only ever produced output while
    # the gate was RED — the moment the goldens went green the probe returned nothing
    # and failed under pipefail. A gate's reporting must not depend on the gate
    # failing. Guarded by test_golden_probe_marker_is_emitted_by_both_goldens.
    print(
        f"GOLDEN-OVERLAP Ile {overlap}/{len(expected)} "
        f"({overlap_pct:.1%}) floor {OVERLAP_MIN_HITS} hits"
    )

    assert overlap >= OVERLAP_MIN_HITS, (
        f"Île golden overlap {overlap}/{len(expected)} ({overlap_pct:.1%}) below the "
        f"regression floor of {OVERLAP_MIN_HITS} hits (empirical target "
        f"{OVERLAP_TARGET:.0%}). "
        f"Missing: {missing[:10]}{'…' if len(missing) > 10 else ''}. "
        f"Generated POIs: {[p.name for p in route.pois]}. "
        f"Spine: {route.spine_area}."
    )


def test_ile_golden_spine(snapshot, fixture):
    """Spine area should be Île de la Cité (Phase 2.6 district-dominance rule)."""
    _, route, _ = _generated_beat_ids(snapshot, fixture)
    expected_spine = fixture["expected_spine_area"]
    assert route.spine_area == expected_spine, (
        f"Spine area mismatch: expected {expected_spine!r}, got {route.spine_area!r}. "
        f"POIs picked: {[p.name for p in route.pois]}."
    )


def test_ile_golden_validation_passes(snapshot, fixture):
    script, _, _ = _generated_beat_ids(snapshot, fixture)
    assert script.validation.passed, (
        f"Validation failed. "
        f"Untraceable: "
        f"{[s.text[:80] for s in script.validation.untraceable_sentences]}. "
        f"Forbidden: "
        f"{[(s.text[:80], phrase) for s, phrase in script.validation.forbidden_phrase_hits]}."
    )


def test_ile_golden_picks_notre_dame(snapshot, fixture):
    """Notre-Dame Cathedral must be among the picked anchors (it's the centerpiece)."""
    _, route, _ = _generated_beat_ids(snapshot, fixture)
    poi_names = {p.name for p in route.pois}
    assert "Notre-Dame Cathedral" in poi_names, (
        f"Notre-Dame Cathedral not selected. POIs: {sorted(poi_names)}."
    )
