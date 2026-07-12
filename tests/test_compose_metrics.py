"""Unit proof for the deterministic compose scoreboard (src/tour/compose_metrics).

Every metric is proven adversarially: a GOOD composed Script is clean, and a
minimally-REGRESSED twin (one dropped date, one lost claim, one em dash, ...)
trips exactly that detector. No LLM, no network — pure functions.
"""

from __future__ import annotations

from src.tour.compose_metrics import (
    compute_compose_metrics,
    metric_regressions,
    quality_violations,
)
from src.tour.contract import (
    BeatRef,
    BeatSequence,
    POIBeats,
    Script,
    ScriptPOI,
    Sentence,
    TourInput,
    ValidationReport,
)
from src.tour.generation import GLUE_CLOSING, GLUE_NAV

# Two beats at two stops, each carrying a dated key_claim.
B0 = BeatRef(
    id="b0", poi_id="p0", script_body="Henri IV built the square, completed in 1612.",
    key_claims=("Henri IV built the square, completed in 1612.",),
)
B1 = BeatRef(
    id="b1", poi_id="p1", script_body="Hugo moved to the square in 1832.",
    key_claims=("Hugo moved to the square in 1832.",),
)
SEQ = BeatSequence(poi_beats=(
    POIBeats(poi_id="p0", poi_name="Place des Vosges",
             ordering_strategy="trigger_address", beats=(B0,)),
    POIBeats(poi_id="p1", poi_name="Maison de Hugo",
             ordering_strategy="trigger_address", beats=(B1,)),
))
BEATS = {"b0": B0, "b1": B1}


def _beat(text: str, sid: str, stop: int) -> Sentence:
    return Sentence(text=text, source_id=sid, source_type="beat", stop_idx=stop)


def _glue(text: str, label: str, stop: int) -> Sentence:
    return Sentence(text=text, source_id=label, source_type="glue", stop_idx=stop)


def _script(sentences: list[Sentence]) -> Script:
    return Script(
        city_slug="paris", generated_at="2026-07-12T00:00:00Z",
        inputs=TourInput(start=(48.85, 2.36), duration_min=60, city_slug="paris"),
        total_audio_seconds=0, total_walking_seconds=0, total_walk_distance_m=0,
        total_planned_seconds=0,
        selected_pois=(
            ScriptPOI(id="p0", name="Place des Vosges", tier=5, lat=48.85, lng=2.36),
            ScriptPOI(id="p1", name="Maison de Hugo", tier=4, lat=48.86, lng=2.37),
        ),
        lens_coverage={}, script=tuple(sentences), validation=ValidationReport(),
    )


# A grounded stitch: both facts voiced, guidance to stop 1, a closing sign-off.
STITCHED = _script([
    _beat("Henri IV built the square, completed in 1612.", "b0", 0),
    _glue("From here, walk two minutes east to the Maison de Victor Hugo.", GLUE_NAV, 1),
    _beat("Hugo moved to the square in 1832.", "b1", 1),
    _glue("That's our walk — thank you for spending it with me.", GLUE_CLOSING, 1),
])

# A GOOD compose: reworded, every fact + date + guidance + sign-off intact.
GOOD = _script([
    _beat("Henri the Fourth raised this square, finished in 1612.", "b0", 0),
    _glue("From here, walk two minutes east to the Maison de Victor Hugo.", GLUE_NAV, 1),
    _beat("Victor Hugo made his home on the square in 1832.", "b1", 1),
    _glue("That's our walk, and thank you for spending it with me.", GLUE_CLOSING, 1),
])


def _metrics(composed: Script, **kw):
    return compute_compose_metrics(STITCHED, composed, SEQ, BEATS, **kw)


def test_good_compose_has_no_violations():
    assert quality_violations(_metrics(GOOD)) == []


def test_dropped_date_is_caught():
    # Same prose, but 1612 silently vanishes — passes coverage (>0.34 tokens
    # survive) yet is a real lost fact.
    bad = _script([
        _beat("Henri the Fourth raised this square long ago.", "b0", 0),
        _glue("From here, walk two minutes east to the Maison de Victor Hugo.", GLUE_NAV, 1),
        _beat("Victor Hugo made his home on the square in 1832.", "b1", 1),
        _glue("That's our walk, and thank you.", GLUE_CLOSING, 1),
    ])
    m = _metrics(bad)
    assert m.dropped_numerals == {0: ("1612",)}
    assert any("dropped numerals" in v for v in quality_violations(m))


def test_lost_claim_is_caught():
    # Stop 1's whole fact is gone (beat sentence replaced by empty filler).
    bad = _script([
        _beat("Henri the Fourth raised this square, finished in 1612.", "b0", 0),
        _glue("From here, walk two minutes east to the Maison de Victor Hugo.", GLUE_NAV, 1),
        _beat("A handsome building stands here.", "b1", 1),
        _glue("That's our walk, thank you.", GLUE_CLOSING, 1),
    ])
    m = _metrics(bad)
    assert m.coverage_loss and m.coverage_loss[0][0] == "b1"
    assert any("key_claim" in v for v in quality_violations(m))


def test_em_dash_is_caught():
    bad = _script([
        _beat("Henri the Fourth raised this square — finished in 1612.", "b0", 0),
        _glue("From here, walk east to the Maison de Victor Hugo.", GLUE_NAV, 1),
        _beat("Victor Hugo made his home here in 1832.", "b1", 1),
        _glue("That's our walk, thank you.", GLUE_CLOSING, 1),
    ])
    m = _metrics(bad)
    assert m.em_dash_sentences == 1
    assert any("em dash" in v for v in quality_violations(m))


def test_missing_guidance_is_a_regression_vs_golden():
    # Stop 1 has no GLUE_NAV: the tourist is never walked there. Guidance is a
    # RELATIVE signal (a golden legitimately has some vignettes), so it flags as
    # a regression against the good golden, not as an absolute invariant.
    bad = _script([
        _beat("Henri the Fourth raised this square, finished in 1612.", "b0", 0),
        _beat("Victor Hugo made his home here in 1832.", "b1", 1),
        _glue("That's our walk, thank you.", GLUE_CLOSING, 1),
    ])
    good_m = _metrics(GOOD)
    bad_m = _metrics(bad)
    assert good_m.missing_guidance_stops == ()
    assert bad_m.missing_guidance_stops == (1,)
    assert any("no guidance" in v for v in metric_regressions(bad_m, good_m))


def test_no_closing_is_caught():
    bad = _script([
        _beat("Henri the Fourth raised this square, finished in 1612.", "b0", 0),
        _glue("From here, walk east to the Maison de Victor Hugo.", GLUE_NAV, 1),
        _beat("Victor Hugo made his home here in 1832.", "b1", 1),
    ])
    m = _metrics(bad)
    assert not m.has_closing
    assert any("sign-off" in v for v in quality_violations(m))


def test_worsened_repetition_is_caught():
    # Compose bolts a near-duplicate of the b0 fact into stop 0 (more dup pairs
    # than the stitch had).
    bad = _script([
        _beat("Henri the Fourth raised this square, finished in 1612.", "b0", 0),
        _beat("Henri the Fourth built this very square, done in 1612.", "b0", 0),
        _glue("From here, walk east to the Maison de Victor Hugo.", GLUE_NAV, 1),
        _beat("Victor Hugo made his home here in 1832.", "b1", 1),
        _glue("That's our walk, thank you.", GLUE_CLOSING, 1),
    ])
    m = _metrics(bad)
    assert m.composed_dupe_pairs > m.stitched_dupe_pairs
    assert any("WORSENED repetition" in v for v in quality_violations(m))


def test_reverted_stops_come_from_the_report_not_text():
    bad_sentence = Sentence(text="x", source_id="b1", source_type="beat", stop_idx=1)
    report = ValidationReport(faithfulness_failures=((bad_sentence, "bad"),))
    m = _metrics(GOOD, report=report)
    assert m.reverted_stops == (1,)
    # No report -> revert tracking simply off (not a false zero from text match).
    assert _metrics(GOOD).reverted_stops == ()


def test_metric_regressions_flags_each_contextual_signal():
    # Compare the comparison layer directly on constructed metrics so it does not
    # depend on _sum_audio internals (real beats carry spoken-second estimates;
    # hand fixtures do not). A golden with none of these problems...
    golden = _metrics(GOOD)
    assert metric_regressions(golden, golden) == []  # not a regression vs itself

    thinned = golden.model_copy(update={"audio_seconds_composed": 40})
    rich_golden = golden.model_copy(update={"audio_seconds_composed": 100})
    assert any("thinned" in v for v in metric_regressions(thinned, rich_golden))

    more_dupes = golden.model_copy(update={"composed_dupe_pairs": 3})
    assert any("duplicate pairs" in v for v in metric_regressions(more_dupes, golden))

    more_reverts = golden.model_copy(update={"reverted_stops": (0, 1)})
    assert any("reverted stops" in v for v in metric_regressions(more_reverts, golden))

    unguided = golden.model_copy(update={"missing_guidance_stops": (2,)})
    assert any("no guidance" in v for v in metric_regressions(unguided, golden))

    samey = golden.model_copy(update={"opener_overlaps": ((1, 0, 0.8),)})
    assert any("samey openers" in v for v in metric_regressions(samey, golden))
