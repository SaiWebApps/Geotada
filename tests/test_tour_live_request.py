"""The approved live-tour request cannot drift between routing and authoring."""

import json
from pathlib import Path

from src.tour.contract import TourInput

ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH = (
    ROOT / "specs/2026-07-21-tour-certification/live-tour-request.json"
)


def test_live_tour_request_is_the_frozen_one_way_ninety_minute_start() -> None:
    request = TourInput.model_validate(json.loads(REQUEST_PATH.read_bytes()))

    assert request.start == (48.8568, 2.3414)
    assert request.duration_min == 90
    assert request.round_trip is False
    assert request.end is None
