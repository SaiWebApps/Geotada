"""Unit tests for API models — no Neo4j required."""

import pytest
from pydantic import ValidationError

from src.api.models.nodes import (
    CREATE_MODELS,
    NodeLabel,
    NodeListResponse,
    NodeResponse,
    POICreate,
)

# ── NodeLabel enum ──


class TestNodeLabel:
    def test_has_seven_labels(self):
        assert len(NodeLabel) == 7

    def test_all_expected_labels_present(self):
        expected = {
            "User",
            "Profile",
            "Lens",
            "Trip",
            "ItineraryItem",
            "POI",
            "NarrativeBeat",
        }
        assert {label.value for label in NodeLabel} == expected

    def test_labels_are_string_values(self):
        for label in NodeLabel:
            assert isinstance(label.value, str)


# ── NodeResponse ──


class TestNodeResponse:
    def test_can_construct_with_required_fields(self):
        resp = NodeResponse(
            id="abc-123",
            labels=["User"],
            properties={"email": "test@example.com"},
        )
        assert resp.id == "abc-123"
        assert resp.labels == ["User"]
        assert resp.properties["email"] == "test@example.com"

    def test_properties_can_be_empty(self):
        resp = NodeResponse(id="x", labels=["Lens"], properties={})
        assert resp.properties == {}


# ── NodeListResponse ──


class TestNodeListResponse:
    def test_can_construct_empty_list(self):
        resp = NodeListResponse(items=[], total=0, skip=0, limit=50)
        assert resp.items == []
        assert resp.total == 0

    def test_can_construct_with_items(self):
        item = NodeResponse(id="1", labels=["User"], properties={"email": "a@b.com"})
        resp = NodeListResponse(items=[item], total=1, skip=0, limit=50)
        assert len(resp.items) == 1
        assert resp.items[0].id == "1"


# ── CREATE_MODELS mapping ──


class TestCreateModels:
    def test_every_label_has_a_create_model(self):
        for label in NodeLabel:
            assert label in CREATE_MODELS, f"Missing create model for {label.value}"

    def test_user_create_requires_email(self):
        model = CREATE_MODELS[NodeLabel.User]
        instance = model(email="test@example.com")
        assert instance.email == "test@example.com"

    def test_poi_create_requires_lat_lng(self):
        model = CREATE_MODELS[NodeLabel.POI]
        instance = model(name="Test POI", latitude=48.8, longitude=2.3)
        assert instance.latitude == 48.8
        assert instance.longitude == 2.3

    def test_lens_create_requires_name_and_label(self):
        model = CREATE_MODELS[NodeLabel.Lens]
        instance = model(name="test_lens", display_label="Test Lens")
        assert instance.name == "test_lens"
        assert instance.display_label == "Test Lens"


# ── POI coordinate validation ──


class TestPOICoordinateValidation:
    """Test POICreate field_validators for latitude and longitude ranges."""

    def _make_poi(self, *, latitude: float = 48.8, longitude: float = 2.3) -> POICreate:
        return POICreate(name="Test", latitude=latitude, longitude=longitude)

    def test_latitude_above_90_rejected(self):
        with pytest.raises(ValidationError, match="latitude must be between"):
            self._make_poi(latitude=90.1)

    def test_latitude_below_neg90_rejected(self):
        with pytest.raises(ValidationError, match="latitude must be between"):
            self._make_poi(latitude=-90.1)

    def test_longitude_above_180_rejected(self):
        with pytest.raises(ValidationError, match="longitude must be between"):
            self._make_poi(longitude=180.1)

    def test_longitude_below_neg180_rejected(self):
        with pytest.raises(ValidationError, match="longitude must be between"):
            self._make_poi(longitude=-180.1)

    def test_boundary_latitude_90_accepted(self):
        poi = self._make_poi(latitude=90.0)
        assert poi.latitude == 90.0

    def test_boundary_latitude_neg90_accepted(self):
        poi = self._make_poi(latitude=-90.0)
        assert poi.latitude == -90.0

    def test_boundary_longitude_180_accepted(self):
        poi = self._make_poi(longitude=180.0)
        assert poi.longitude == 180.0

    def test_boundary_longitude_neg180_accepted(self):
        poi = self._make_poi(longitude=-180.0)
        assert poi.longitude == -180.0
