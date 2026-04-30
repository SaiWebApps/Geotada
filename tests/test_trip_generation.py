"""Unit tests for trip generation business logic — no Neo4j required.

Tests: T2 (8 unit tests for Golden Ratio algorithm, scheduling, dedup, edge cases)
"""

from __future__ import annotations

from src.api.crud.trips import apply_golden_ratio, compute_schedule


def _make_candidate(
    poi_id: str,
    beat_id: str,
    importance_tier: int,
    duration_sec: int = 180,
    lens_name: str = "hidden_history",
) -> dict:
    """Helper to build a candidate dict matching the find_matching_beats output shape."""
    return {
        "poi_id": poi_id,
        "poi_name": f"POI {poi_id}",
        "beat_id": beat_id,
        "lens_name": lens_name,
        "lens_display": lens_name.replace("_", " ").title(),
        "duration_sec": duration_sec,
        "importance_tier": importance_tier,
        "lat": 48.858 + hash(poi_id) % 100 * 0.001,
        "lng": 2.294 + hash(poi_id) % 100 * 0.001,
    }


class TestApplyGoldenRatio:
    """Test the golden ratio selection algorithm."""

    # Acceptance Criterion: AC3 — Golden Ratio: ~20% anchors (gravity 5), ~80% flavour
    def test_golden_ratio_selects_anchors_first(self):
        """T2: Anchors (tier 5) appear before flavour in the selection."""
        candidates = [
            _make_candidate("p1", "b1", importance_tier=5),
            _make_candidate("p2", "b2", importance_tier=3),
            _make_candidate("p3", "b3", importance_tier=2),
            _make_candidate("p4", "b4", importance_tier=4),
            _make_candidate("p5", "b5", importance_tier=5),
        ]
        result = apply_golden_ratio(candidates, max_stops=5, duration_min=None)
        # First items should be anchors (tier 5)
        anchor_positions = [i for i, s in enumerate(result) if s["importance_tier"] == 5]
        flavour_positions = [i for i, s in enumerate(result) if s["importance_tier"] < 5]
        assert len(anchor_positions) > 0
        # All anchors come before all flavour stops
        assert max(anchor_positions) < min(flavour_positions)

    # Acceptance Criterion: AC3 — Golden Ratio: ~20% anchors (gravity 5), ~80% flavour
    def test_golden_ratio_twenty_percent_anchors(self):
        """T2: With 10 max_stops, ~2 anchors are selected (round(10*0.2)=2)."""
        # 5 anchors and 10 flavour candidates — enough supply
        anchors = [_make_candidate(f"a{i}", f"ba{i}", importance_tier=5) for i in range(5)]
        flavour = [_make_candidate(f"f{i}", f"bf{i}", importance_tier=3) for i in range(10)]
        candidates = anchors + flavour
        result = apply_golden_ratio(candidates, max_stops=10, duration_min=None)
        anchor_count = sum(1 for s in result if s["importance_tier"] == 5)
        # round(10 * 0.2) = 2
        assert anchor_count == 2
        assert len(result) == 10

    # Acceptance Criterion: AC3 — Golden Ratio: ~20% anchors (gravity 5), ~80% flavour
    def test_golden_ratio_respects_max_stops(self):
        """T2: Output never exceeds max_stops."""
        candidates = [_make_candidate(f"p{i}", f"b{i}", importance_tier=3) for i in range(20)]
        result = apply_golden_ratio(candidates, max_stops=5, duration_min=None)
        assert len(result) <= 5

    # Acceptance Criterion: AC5 — If duration_min provided, total doesn't exceed it
    def test_golden_ratio_respects_duration_budget(self):
        """T2: Duration budget trims stops that would exceed the total."""
        # Each candidate is 5 minutes (300 sec). Budget = 12 minutes → 2 stops max.
        candidates = [
            _make_candidate(f"p{i}", f"b{i}", importance_tier=3, duration_sec=300)
            for i in range(10)
        ]
        result = apply_golden_ratio(candidates, max_stops=10, duration_min=12)
        total_sec = sum(s["duration_sec"] for s in result)
        assert total_sec <= 12 * 60
        assert len(result) == 2

    # Acceptance Criterion: AC4 — No duplicate POIs in stops
    def test_golden_ratio_deduplicates_by_poi(self):
        """T2: If multiple beats exist for the same POI, only the best one is kept."""
        candidates = [
            _make_candidate("same_poi", "beat_low", importance_tier=2),
            _make_candidate("same_poi", "beat_high", importance_tier=4),
            _make_candidate("other_poi", "beat_other", importance_tier=3),
        ]
        result = apply_golden_ratio(candidates, max_stops=10, duration_min=None)
        poi_ids = [s["poi_id"] for s in result]
        # No duplicate POIs
        assert len(poi_ids) == len(set(poi_ids))
        # The higher-tier beat was kept
        same_poi_entry = next(s for s in result if s["poi_id"] == "same_poi")
        assert same_poi_entry["importance_tier"] == 4

    # Acceptance Criterion: AC3 — Golden Ratio edge case: empty input
    def test_golden_ratio_empty_input(self):
        """T2: Empty candidates list returns empty result."""
        result = apply_golden_ratio([], max_stops=10, duration_min=None)
        assert result == []


class TestComputeSchedule:
    """Test sequential time scheduling logic."""

    # Acceptance Criterion: AC2 — Each stop has start_time
    def test_compute_schedule_sequential_times(self):
        """T2: Stops get sequential start times based on duration."""
        stops = [
            _make_candidate("p1", "b1", importance_tier=5, duration_sec=1800),  # 30 min
            _make_candidate("p2", "b2", importance_tier=3, duration_sec=900),  # 15 min
            _make_candidate("p3", "b3", importance_tier=2, duration_sec=600),  # 10 min
        ]
        result = compute_schedule(stops, start_time="09:00")
        assert result[0]["start_time"] == "09:00"
        assert result[0]["duration_min"] == 30
        assert result[1]["start_time"] == "09:30"
        assert result[1]["duration_min"] == 15
        assert result[2]["start_time"] == "09:45"
        assert result[2]["duration_min"] == 10

    # Acceptance Criterion: AC2 — Each stop has start_time
    def test_compute_schedule_respects_start_time(self):
        """T2: Custom start time is used for the first stop."""
        stops = [
            _make_candidate("p1", "b1", importance_tier=3, duration_sec=3600),  # 60 min
            _make_candidate("p2", "b2", importance_tier=3, duration_sec=1800),  # 30 min
        ]
        result = compute_schedule(stops, start_time="14:30")
        assert result[0]["start_time"] == "14:30"
        assert result[0]["sort_order"] == 1
        assert result[1]["start_time"] == "15:30"
        assert result[1]["sort_order"] == 2
