"""Step 1.1 — stop_narration_text: group a Script's sentences into per-stop text.

Pure-function unit tests (no DB, no audio). Verifies that the narration the
engine already produces (cold-open + transit glue + beats + closing) can be
grouped per stop and joined in order — the text Phase 1 will hand to TTS.
"""

from __future__ import annotations

import datetime as _dt

from src.tour.contract import Script, ScriptPOI, Sentence, TourInput, ValidationReport
from src.tour.render_md import stop_narration_text


def _script(sentences: list[Sentence]) -> Script:
    return Script(
        city_slug="paris",
        generated_at=_dt.datetime(2026, 6, 13, tzinfo=_dt.UTC).isoformat(),
        inputs=TourInput(start=(48.8555, 2.3656), duration_min=60, city_slug="paris"),
        total_audio_seconds=0,
        total_walking_seconds=0,
        total_walk_distance_m=0,
        total_planned_seconds=0,
        selected_pois=(
            ScriptPOI(id="p1", name="Place des Vosges", tier=5, lat=48.85, lng=2.36),
        ),
        lens_coverage={},
        script=tuple(sentences),
        validation=ValidationReport(),
    )


def test_groups_by_stop_and_joins_in_order_including_glue() -> None:
    script = _script(
        [
            Sentence(text="s0a", source_id="b1", source_type="beat", stop_idx=0),
            Sentence(text="s0b", source_id="GLUE_NAV", source_type="glue", stop_idx=0),
            Sentence(text="s1a", source_id="b2", source_type="beat", stop_idx=1),
        ]
    )
    assert stop_narration_text(script) == {0: "s0a s0b", 1: "s1a"}


def test_empty_script_returns_empty_dict() -> None:
    assert stop_narration_text(_script([])) == {}


def test_single_stop_single_sentence() -> None:
    script = _script(
        [Sentence(text="only", source_id="b1", source_type="beat", stop_idx=0)]
    )
    assert stop_narration_text(script) == {0: "only"}


def _yellow_assessment(on_lens_fill_ratio):
    from src.tour.contract import TourabilityAssessment

    return TourabilityAssessment(
        status="YELLOW", walk_radius_m=369.0, fill_ratio=0.57,
        audio_capacity_seconds=1000, target_audio_seconds=1793,
        reachable_poi_count=3, reachable_beat_count=10, anchor_candidate_count=2,
        cluster_compactness=0.5, duration_min=60, round_trip=True,
        on_lens_fill_ratio=on_lens_fill_ratio,
    )


def test_yellow_banner_discloses_lens_specific_fill():
    from src.tour.render_md import _yellow_banner

    # Same overall 57% fill, but the on-lens fill (20%) is disclosed for the interest.
    banner = _yellow_banner(_yellow_assessment(0.20), ["dark_history"])
    assert "57% audio fill" in banner
    assert "dark_history" in banner
    assert "20%" in banner


def test_yellow_banner_no_lens_line_without_lenses():
    from src.tour.render_md import _yellow_banner

    banner = _yellow_banner(_yellow_assessment(None), None)
    assert "57% audio fill" in banner
    assert "for your interest" not in banner.lower()
