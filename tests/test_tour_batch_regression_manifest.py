"""Frozen-input proof for the 4 Paris + 4 New York tour experiment."""

from pathlib import Path

import pytest

from src.tour.batch_regression_manifest import (
    FrozenTourBatchManifest,
    load_frozen_tour_batch,
)

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT / "specs" / "2026-07-22-tour-batch-regression" / "requests.v1.json"
)


def test_frozen_manifest_has_unique_four_plus_four_requests() -> None:
    manifest = load_frozen_tour_batch(MANIFEST_PATH)

    assert len(manifest.cases) == 8
    assert len({case.request_sha256 for case in manifest.cases}) == 8
    assert [case.tour_input.city_slug for case in manifest.cases].count("paris") == 4
    assert [case.tour_input.city_slug for case in manifest.cases].count("new_york") == 4


def test_each_city_covers_open_round_trip_and_fixed_end() -> None:
    manifest = load_frozen_tour_batch(MANIFEST_PATH)

    for city_slug in ("paris", "new_york"):
        assert {
            case.route_mode
            for case in manifest.cases
            if case.tour_input.city_slug == city_slug
        } == {"open", "round_trip", "fixed_end"}



def test_duplicate_or_unbalanced_batches_fail_closed() -> None:
    manifest = load_frozen_tour_batch(MANIFEST_PATH)
    values = manifest.model_dump(mode="json", exclude_computed_fields=True)
    values["cases"][-1] = values["cases"][0]

    with pytest.raises(ValueError):
        FrozenTourBatchManifest.model_validate(values)
