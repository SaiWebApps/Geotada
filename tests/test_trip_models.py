"""Unit tests for trip generation Pydantic models — no Neo4j required.

Tests: T1 (9 unit tests)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.api.models.trips import GeneratedStop, TripGenerateRequest, TripGenerateResponse


class TestTripGenerateRequest:
    """Validate TripGenerateRequest model constraints."""

    # Acceptance Criterion: AC1 — POST /api/v1/trips/generate returns 201
    def test_trip_generate_request_valid_minimal(self):
        """T1: Minimal valid request with only required fields."""
        req = TripGenerateRequest(
            profile_id="prof-123",
            center_lat=48.858,
            center_lng=2.294,
            start_date="2026-05-01",
            end_date="2026-05-03",
        )
        assert req.profile_id == "prof-123"
        assert req.center_lat == 48.858
        assert req.center_lng == 2.294
        assert req.start_date == "2026-05-01"

    # Acceptance Criterion: AC1 — POST /api/v1/trips/generate returns 201
    def test_trip_generate_request_valid_all_fields(self):
        """T1: Request with all optional fields explicitly set."""
        req = TripGenerateRequest(
            profile_id="prof-456",
            center_lat=48.854,
            center_lng=2.332,
            radius_m=5000,
            max_stops=15,
            duration_min=120,
            start_date="2026-06-01",
            end_date="2026-06-05",
            start_time="10:30",
            kid_friendly_only=True,
            trip_name="My Paris Trip",
        )
        assert req.radius_m == 5000
        assert req.max_stops == 15
        assert req.duration_min == 120
        assert req.start_time == "10:30"
        assert req.kid_friendly_only is True
        assert req.trip_name == "My Paris Trip"

    # Acceptance Criterion: AC1 — POST /api/v1/trips/generate returns 201
    def test_trip_generate_request_lat_out_of_range(self):
        """T1: Latitude > 90 must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TripGenerateRequest(
                profile_id="p",
                center_lat=91.0,
                center_lng=2.0,
                start_date="2026-05-01",
                end_date="2026-05-03",
            )
        assert "center_lat" in str(exc_info.value)

    # Acceptance Criterion: AC1 — POST /api/v1/trips/generate returns 201
    def test_trip_generate_request_lng_out_of_range(self):
        """T1: Longitude > 180 must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TripGenerateRequest(
                profile_id="p",
                center_lat=48.0,
                center_lng=181.0,
                start_date="2026-05-01",
                end_date="2026-05-03",
            )
        assert "center_lng" in str(exc_info.value)

    # Acceptance Criterion: AC1 — POST /api/v1/trips/generate returns 201
    def test_trip_generate_request_radius_too_large(self):
        """T1: radius_m > 10000 must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TripGenerateRequest(
                profile_id="p",
                center_lat=48.0,
                center_lng=2.0,
                radius_m=10001,
                start_date="2026-05-01",
                end_date="2026-05-03",
            )
        assert "radius_m" in str(exc_info.value)

    # Acceptance Criterion: AC1 — POST /api/v1/trips/generate returns 201
    def test_trip_generate_request_max_stops_capped(self):
        """T1: max_stops > 30 must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TripGenerateRequest(
                profile_id="p",
                center_lat=48.0,
                center_lng=2.0,
                max_stops=31,
                start_date="2026-05-01",
                end_date="2026-05-03",
            )
        assert "max_stops" in str(exc_info.value)

    # Acceptance Criterion: AC1 — POST /api/v1/trips/generate returns 201
    def test_trip_generate_request_defaults(self):
        """T1: Defaults are applied correctly when optional fields omitted."""
        req = TripGenerateRequest(
            profile_id="p",
            center_lat=0.0,
            center_lng=0.0,
            start_date="2026-01-01",
            end_date="2026-01-02",
        )
        assert req.radius_m == 3000
        assert req.max_stops == 10
        assert req.duration_min is None
        assert req.start_time == "09:00"
        assert req.kid_friendly_only is False
        assert req.trip_name is None


class TestGeneratedStop:
    """Validate GeneratedStop model."""

    # Acceptance Criterion: AC2 — Each stop has required fields
    def test_generated_stop_model(self):
        """T1: GeneratedStop can be constructed with all required fields."""
        stop = GeneratedStop(
            sort_order=1,
            poi_id="poi-abc",
            poi_name="Eiffel Tower",
            lat=48.858,
            lng=2.294,
            beat_id="beat-xyz",
            lens_name="hidden_history",
            lens_display="Hidden History",
            duration_min=5,
            importance_tier=5,
            start_time="09:00",
        )
        assert stop.sort_order == 1
        assert stop.poi_id == "poi-abc"
        assert stop.poi_name == "Eiffel Tower"
        assert stop.lat == 48.858
        assert stop.lng == 2.294
        assert stop.beat_id == "beat-xyz"
        assert stop.lens_name == "hidden_history"
        assert stop.lens_display == "Hidden History"
        assert stop.duration_min == 5
        assert stop.importance_tier == 5
        assert stop.start_time == "09:00"
        # New optional fields default to None
        assert stop.script_body is None
        assert stop.audio_url is None
        assert stop.audio_duration_sec is None

    def test_generated_stop_with_audio_fields(self):
        """T1: GeneratedStop accepts optional script_body, audio_url, audio_duration_sec."""
        stop = GeneratedStop(
            sort_order=2,
            poi_id="poi-def",
            poi_name="Notre-Dame",
            lat=48.853,
            lng=2.349,
            beat_id="beat-456",
            lens_name="architecture",
            lens_display="Architecture",
            duration_min=10,
            importance_tier=5,
            start_time="10:30",
            script_body="The flying buttresses of Notre-Dame...",
            audio_url="https://cdn.ondoway.com/beats/notre_dame/beat-456.mp3",
            audio_duration_sec=185.5,
        )
        assert stop.script_body == "The flying buttresses of Notre-Dame..."
        assert stop.audio_url == "https://cdn.ondoway.com/beats/notre_dame/beat-456.mp3"
        assert stop.audio_duration_sec == 185.5

    def test_generated_stop_serializes_null_audio_fields(self):
        """T1: JSON serialization includes null audio fields when not provided."""
        stop = GeneratedStop(
            sort_order=1,
            poi_id="poi-1",
            poi_name="Test",
            lat=48.0,
            lng=2.0,
            beat_id="b-1",
            lens_name="history",
            lens_display="History",
            duration_min=5,
            importance_tier=3,
            start_time="09:00",
        )
        data = stop.model_dump()
        assert "script_body" in data
        assert "audio_url" in data
        assert "audio_duration_sec" in data
        assert data["script_body"] is None
        assert data["audio_url"] is None
        assert data["audio_duration_sec"] is None


class TestTripGenerateResponse:
    """Validate TripGenerateResponse model."""

    # Acceptance Criterion: AC1 — Response has trip_id, trip_name, profile_id, etc.
    def test_trip_generate_response_model(self):
        """T1: TripGenerateResponse can be constructed with all required fields."""
        stop = GeneratedStop(
            sort_order=1,
            poi_id="poi-1",
            poi_name="Test POI",
            lat=48.0,
            lng=2.0,
            beat_id="beat-1",
            lens_name="history",
            lens_display="History",
            duration_min=3,
            importance_tier=5,
            start_time="09:00",
        )
        resp = TripGenerateResponse(
            trip_id="trip-001",
            trip_name="My Trip",
            profile_id="prof-1",
            total_stops=1,
            total_duration_min=3,
            anchor_count=1,
            flavour_count=0,
            stops=[stop],
        )
        assert resp.trip_id == "trip-001"
        assert resp.trip_name == "My Trip"
        assert resp.profile_id == "prof-1"
        assert resp.total_stops == 1
        assert resp.total_duration_min == 3
        assert resp.anchor_count == 1
        assert resp.flavour_count == 0
        assert len(resp.stops) == 1
        assert resp.stops[0].poi_id == "poi-1"
