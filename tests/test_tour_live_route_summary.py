"""Replayable checks over the real database/Valhalla route selected for the live tour."""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = (
    ROOT / "specs/2026-07-21-tour-certification/live-route-summary.json"
)
COMPARISON_PATH = (
    ROOT
    / "specs/2026-07-21-tour-certification/live-route-gold-comparison.json"
)


def _summary() -> dict:
    return json.loads(SUMMARY_PATH.read_bytes())


def _comparison() -> dict:
    return json.loads(COMPARISON_PATH.read_bytes())


def test_live_route_has_the_captured_ordered_database_pois() -> None:
    summary = _summary()

    assert [poi["name"] for poi in summary["pois"]] == [
        "Pont Neuf",
        "Square du Vert-Galant",
        "Conciergerie",
        "Sainte-Chapelle",
        "Square Jean XXIII",
        "Notre-Dame Cathedral",
        "Shakespeare and Company",
        "The Sorbonne",
    ]


def test_live_route_coordinates_are_finite_and_geographically_valid() -> None:
    for poi in _summary()["pois"]:
        assert math.isfinite(poi["lat"]) and -90 <= poi["lat"] <= 90
        assert math.isfinite(poi["lng"]) and -180 <= poi["lng"] <= 180


def test_every_live_route_leg_has_a_successful_valhalla_receipt() -> None:
    summary = _summary()
    legs = summary["legs"]

    assert len(legs) == len(summary["pois"])
    assert [leg["index"] for leg in legs] == list(range(len(legs)))
    assert all(leg["source"] == "valhalla" for leg in legs)
    assert all(len(leg["request_sha256"]) == 64 for leg in legs)
    assert all(len(leg["response_sha256"]) == 64 for leg in legs)
    assert all(leg["seconds"] > 0 and leg["distance_m"] > 0 for leg in legs)


def test_live_route_totals_equal_the_exact_leg_sums() -> None:
    summary = _summary()

    assert sum(leg["seconds"] for leg in summary["legs"]) == 3423
    assert sum(leg["distance_m"] for leg in summary["legs"]) == 2743.0
    assert summary["total_walk_seconds"] == 3423
    assert summary["total_walk_distance_m"] == 2743.0
    assert summary["planned_source_narration_seconds"] == 1732
    assert summary["planned_additional_dwell_seconds"] == 0
    assert summary["planned_elapsed_seconds"] == 5155
    assert summary["planning_status"] == "pre_authoring_capacity_only"
    assert (
        summary["minimum_elapsed_seconds"]
        <= summary["planned_elapsed_seconds"]
        <= summary["maximum_elapsed_seconds"]
    )


def test_every_gold_route_difference_has_an_explicit_justification() -> None:
    comparison = _comparison()

    assert comparison["comparison_role"] == "read_only_audit_evidence"
    assert comparison["algorithmic_allow_or_deny_rule"] is False
    assert comparison["candidate_route_sha256"] == _summary()["route_sha256"]
    assert comparison["differences"]
    assert all(
        item["item"] and item["kind"] and item["justification"]
        for item in comparison["differences"]
    )
