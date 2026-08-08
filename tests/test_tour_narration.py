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
        dwell_capacity_seconds=1000, target_dwell_seconds=1793,
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


def _surplus_fill_assessment(anchor_candidate_count: int = 2, cluster_compactness: float = 0.5):
    """YELLOW where fill is already at/above target — the Louvre 45-min repro.

    fill_ratio=1.00 (100% fill) but anchor_candidate_count=2 is below
    GREEN_ANCHOR_CANDIDATES_MIN (4), so density._status returns YELLOW via
    the yellow_by_surplus_fill clause, not because fill is low.
    """
    from src.tour.contract import TourabilityAssessment

    return TourabilityAssessment(
        status="YELLOW", walk_radius_m=369.0, fill_ratio=1.00,
        dwell_capacity_seconds=1793, target_dwell_seconds=1793,
        reachable_poi_count=2, reachable_beat_count=11,
        anchor_candidate_count=anchor_candidate_count,
        cluster_compactness=cluster_compactness, duration_min=45, round_trip=True,
    )


def test_yellow_banner_near_green_fill_does_not_claim_below_70_80_bar():
    """D9 follow-up: fill between the empirical 70-80% bar and GREEN (e.g. 99%)
    must not claim "ran below the empirical 70-80% bar" (still false at 99%),
    but should disclose the near-miss honestly. Live repro: the same Louvre
    45-min tour at fill_ratio=0.99 post-corpus-edit."""
    from src.tour.render_md import _yellow_banner

    a = _surplus_fill_assessment()
    if hasattr(a, "__dict__"):
        a = a.__class__(**{**a.__dict__, "fill_ratio": 0.99})
    else:
        a = a._replace(fill_ratio=0.99)
    banner = _yellow_banner(a, None)
    assert "ran below the empirical" not in banner
    assert "99%" in banner


def test_yellow_banner_surplus_fill_does_not_claim_below_bar():
    """D9: fill=100% YELLOW-for-anchor-scarcity must not claim below-bar fill.

    Live repro (specs/2026-07-18-tour-qa-campaign/REPORT.md, artifact
    48-8606-2-3376-45min-b8ed0a.md): a Louvre 45-min round-trip rendered
    "100% audio fill" alongside "ran below the empirical 70-80% audio-fill
    bar" — self-contradictory. The banner must state the TRUE limiting
    factor (thin anchor pool) instead.
    """
    from src.tour.render_md import _yellow_banner

    banner = _yellow_banner(_surplus_fill_assessment(), None)
    assert "100% audio fill" in banner
    assert "ran below the empirical" not in banner
    assert "substantial stop" in banner


def test_yellow_banner_spread_out_cluster_states_layout_reason():
    """D9: surplus fill + spread-out (not thin-anchor) cluster also gets an honest reason."""
    from src.tour.render_md import _yellow_banner

    banner = _yellow_banner(
        _surplus_fill_assessment(anchor_candidate_count=5, cluster_compactness=0.9), None
    )
    assert "ran below the empirical" not in banner
    assert "spread out" in banner


def test_yellow_banner_genuine_low_fill_keeps_below_bar_message():
    """D9 regression: genuinely low fill (0.5 <= fill < 1.0) must keep the below-bar line."""
    from src.tour.render_md import _yellow_banner

    banner = _yellow_banner(_yellow_assessment(None), None)
    assert "ran below the empirical" in banner
