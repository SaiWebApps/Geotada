"""Unit tests for trip generation business logic — no Neo4j required.

Tests: Golden Ratio algorithm, scheduling with POI visit durations, dedup, edge cases.
"""

from __future__ import annotations

from src.api.crud.trips import apply_golden_ratio, compute_schedule


def _make_candidate(
    poi_id: str,
    beat_id: str,
    importance_tier: int,
    duration_sec: int = 180,
    typical_duration_min: int = 30,
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
        "typical_duration_min": typical_duration_min,
        "importance_tier": importance_tier,
        "lat": 48.858 + hash(poi_id) % 100 * 0.001,
        "lng": 2.294 + hash(poi_id) % 100 * 0.001,
    }


class TestApplyGoldenRatio:
    """Test the golden ratio selection algorithm."""

    def test_golden_ratio_selects_anchors_first(self):
        """Anchors (tier 5) appear before flavour in the selection."""
        candidates = [
            _make_candidate("p1", "b1", importance_tier=5),
            _make_candidate("p2", "b2", importance_tier=3),
            _make_candidate("p3", "b3", importance_tier=2),
            _make_candidate("p4", "b4", importance_tier=4),
            _make_candidate("p5", "b5", importance_tier=5),
        ]
        result = apply_golden_ratio(candidates, max_stops=5, duration_min=None)
        anchor_positions = [i for i, s in enumerate(result) if s["importance_tier"] == 5]
        flavour_positions = [i for i, s in enumerate(result) if s["importance_tier"] < 5]
        assert len(anchor_positions) > 0
        assert max(anchor_positions) < min(flavour_positions)

    def test_golden_ratio_twenty_percent_anchors(self):
        """With 10 max_stops, ~2 anchors are selected (round(10*0.2)=2)."""
        anchors = [_make_candidate(f"a{i}", f"ba{i}", importance_tier=5) for i in range(5)]
        flavour = [_make_candidate(f"f{i}", f"bf{i}", importance_tier=3) for i in range(10)]
        candidates = anchors + flavour
        result = apply_golden_ratio(candidates, max_stops=10, duration_min=None)
        anchor_count = sum(1 for s in result if s["importance_tier"] == 5)
        assert anchor_count == 2
        assert len(result) == 10

    def test_golden_ratio_respects_max_stops(self):
        """Output never exceeds max_stops."""
        candidates = [_make_candidate(f"p{i}", f"b{i}", importance_tier=3) for i in range(20)]
        result = apply_golden_ratio(candidates, max_stops=5, duration_min=None)
        assert len(result) <= 5

    def test_golden_ratio_respects_duration_budget_using_poi_duration(self):
        """Duration budget trims using POI typical_duration_min, not beat audio length."""
        # Each POI takes 45 min to visit. Budget = 100 min → 2 stops max (90 min ≤ 100).
        candidates = [
            _make_candidate(
                f"p{i}", f"b{i}", importance_tier=3, duration_sec=60, typical_duration_min=45
            )
            for i in range(10)
        ]
        result = apply_golden_ratio(candidates, max_stops=10, duration_min=100)
        total_visit = sum(s["typical_duration_min"] for s in result)
        assert total_visit <= 100
        assert len(result) == 2

    def test_golden_ratio_budget_ignores_beat_audio_length(self):
        """Even if beat audio is short (60s), POI visit duration (45 min) drives the budget."""
        candidates = [
            _make_candidate(
                "p1", "b1", importance_tier=3, duration_sec=60, typical_duration_min=45
            ),
            _make_candidate(
                "p2", "b2", importance_tier=3, duration_sec=60, typical_duration_min=45
            ),
        ]
        # Budget = 50 min. Only 1 stop fits (45 ≤ 50, but 45+45=90 > 50).
        result = apply_golden_ratio(candidates, max_stops=10, duration_min=50)
        assert len(result) == 1

    def test_golden_ratio_deduplicates_by_poi(self):
        """If multiple beats exist for the same POI, only the best one is kept."""
        candidates = [
            _make_candidate("same_poi", "beat_low", importance_tier=2),
            _make_candidate("same_poi", "beat_high", importance_tier=4),
            _make_candidate("other_poi", "beat_other", importance_tier=3),
        ]
        result = apply_golden_ratio(candidates, max_stops=10, duration_min=None)
        poi_ids = [s["poi_id"] for s in result]
        assert len(poi_ids) == len(set(poi_ids))
        same_poi_entry = next(s for s in result if s["poi_id"] == "same_poi")
        assert same_poi_entry["importance_tier"] == 4

    def test_golden_ratio_empty_input(self):
        """Empty candidates list returns empty result."""
        result = apply_golden_ratio([], max_stops=10, duration_min=None)
        assert result == []


class TestComputeSchedule:
    """Test sequential time scheduling logic using POI visit durations."""

    def test_schedule_uses_poi_visit_duration_not_beat_audio(self):
        """Stops are scheduled by typical_duration_min, not duration_sec."""
        stops = [
            _make_candidate(
                "p1", "b1", importance_tier=5, duration_sec=120, typical_duration_min=90
            ),  # 2 min audio, 90 min visit
            _make_candidate(
                "p2", "b2", importance_tier=3, duration_sec=45, typical_duration_min=30
            ),  # 45s audio, 30 min visit
        ]
        result = compute_schedule(stops, start_time="09:00")
        assert result[0]["start_time"] == "09:00"
        assert result[0]["duration_min"] == 90
        assert result[1]["start_time"] == "10:30"
        assert result[1]["duration_min"] == 30

    def test_schedule_sequential_times(self):
        """Stops get sequential start times based on POI visit duration."""
        stops = [
            _make_candidate("p1", "b1", importance_tier=5, typical_duration_min=30),
            _make_candidate("p2", "b2", importance_tier=3, typical_duration_min=15),
            _make_candidate("p3", "b3", importance_tier=2, typical_duration_min=10),
        ]
        result = compute_schedule(stops, start_time="09:00")
        assert result[0]["start_time"] == "09:00"
        assert result[0]["duration_min"] == 30
        assert result[1]["start_time"] == "09:30"
        assert result[1]["duration_min"] == 15
        assert result[2]["start_time"] == "09:45"
        assert result[2]["duration_min"] == 10

    def test_schedule_respects_start_time(self):
        """Custom start time is used for the first stop."""
        stops = [
            _make_candidate("p1", "b1", importance_tier=3, typical_duration_min=60),
            _make_candidate("p2", "b2", importance_tier=3, typical_duration_min=30),
        ]
        result = compute_schedule(stops, start_time="14:30")
        assert result[0]["start_time"] == "14:30"
        assert result[0]["sort_order"] == 1
        assert result[1]["start_time"] == "15:30"
        assert result[1]["sort_order"] == 2

    def test_schedule_defaults_to_30_min_when_no_typical_duration(self):
        """If typical_duration_min is missing, defaults to 30 minutes."""
        stop = {
            "poi_id": "p1",
            "poi_name": "Test",
            "beat_id": "b1",
            "lens_name": "a",
            "lens_display": "A",
            "duration_sec": 60,
            "importance_tier": 3,
            "lat": 48.85,
            "lng": 2.34,
        }
        result = compute_schedule([stop], start_time="09:00")
        assert result[0]["duration_min"] == 30

    def test_schedule_realistic_paris_day(self):
        """A realistic Paris day trip produces sensible schedule times."""
        stops = [
            _make_candidate("eiffel", "b1", importance_tier=5, typical_duration_min=90),
            _make_candidate("cafe_flore", "b2", importance_tier=3, typical_duration_min=30),
            _make_candidate("notre_dame", "b3", importance_tier=5, typical_duration_min=60),
            _make_candidate("shakespeare", "b4", importance_tier=3, typical_duration_min=45),
        ]
        result = compute_schedule(stops, start_time="09:00")

        # Eiffel Tower: 09:00 - 10:30 (90 min)
        assert result[0]["start_time"] == "09:00"
        assert result[0]["duration_min"] == 90
        # Café de Flore: 10:30 - 11:00 (30 min)
        assert result[1]["start_time"] == "10:30"
        assert result[1]["duration_min"] == 30
        # Notre-Dame: 11:00 - 12:00 (60 min)
        assert result[2]["start_time"] == "11:00"
        assert result[2]["duration_min"] == 60
        # Shakespeare and Company: 12:00 - 12:45 (45 min)
        assert result[3]["start_time"] == "12:00"
        assert result[3]["duration_min"] == 45

        total = sum(s["duration_min"] for s in result)
        assert total == 225  # 3h 45m — realistic half-day
