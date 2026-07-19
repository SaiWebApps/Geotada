"""Pins the mechanical FLOOR of the tour quality standard.

Standard: ``specs/2026-07-19-tour-quality-standard/01-standard.md`` §4 (the checks)
and §5 (threshold provenance). Module under test: ``src/tour/quality_rubric.py``.

Every test here is a DISCRIMINATOR: delete the check it names from
``quality_rubric.py`` and the test must go RED. Each docstring states the defect it
guards and the exact UNDO that reddens it.

Hermetic: no Neo4j, no network, no LLM. Fixtures are the real pydantic contracts.
"""

from __future__ import annotations

import pytest

from src.tour.contract import (
    POI,
    BeatRef,
    Route,
    Script,
    ScriptPOI,
    Sentence,
    TourInput,
    ValidationReport,
)
from src.tour.quality_rubric import (
    BALANCE_MAX_SHARE,
    GORGE_MAX_WORDS_PER_STOP,
    STARVE_MIN_BEATS,
    STARVE_MIN_WORDS_PER_BEAT,
    Severity,
    score_tour,
)

# ---------------------------------------------------------------------------
# Helpers — house style mirrors tests/test_tour_selection.py (_poi / _snap).
# ---------------------------------------------------------------------------


def _words(n: int, *, prefix: str) -> str:
    """``n`` GLOBALLY-unique words, so a length fixture never trips C5 by accident."""
    return " ".join(f"{prefix}{i}" for i in range(n))


_POI_SEQ: dict[str, int] = {}


def _coords(pid: str) -> tuple[float, float]:
    """Distinct, geographically PLAUSIBLE coords per POI id.

    C12 flags ADJACENT stops closer than MIN_STOP_SEPARATION_M (100 m), so fixtures
    must place POIs at real walking separations — otherwise every multi-stop fixture
    trips C12 at 0 m and the test is measuring the fixture, not the check. ~0.003 deg
    of latitude is ~333 m, comfortably a real leg. Deterministic per id (first-seen
    order), so a given fixture always yields the same geometry.
    """
    idx = _POI_SEQ.setdefault(pid, len(_POI_SEQ))
    return 48.85 + idx * 0.003, 2.35


def _spoi(pid: str, *, tier: int = 5, name: str | None = None) -> ScriptPOI:
    lat, lng = _coords(pid)
    return ScriptPOI(id=pid, name=name or pid, tier=tier, lat=lat, lng=lng)


def _poi(pid: str, *, tier: int = 5, name: str | None = None) -> POI:
    lat, lng = _coords(pid)
    return POI(
        id=pid,
        name=name or pid,
        tier=tier,
        poi_role="stop",
        lat=lat,
        lng=lng,
    )


def _beats(poi_id: str, n: int) -> list[BeatRef]:
    """``n`` real BeatRefs — the rubric only measures len(), but the corpus map is
    typed as beats, so the fixture uses the real model rather than a stand-in."""
    return [BeatRef(id=f"{poi_id}-b{i}", poi_id=poi_id) for i in range(n)]


def _sentence(text: str, stop_idx: int, *, source_type: str = "beat") -> Sentence:
    return Sentence(
        text=text,
        source_id=f"src-{stop_idx}-{abs(hash(text)) % 10_000}",
        source_type=source_type,
        stop_idx=stop_idx,
    )


def _script(
    sentences: list[Sentence],
    pois: list[ScriptPOI],
    *,
    # Default ABOVE the C3-thin floor (0.8 x 0.83 x 0.60 x 60 min = 23.9 min) so a
    # fixture aimed at some OTHER check does not trip C3 as a side effect. A test
    # about C3 passes a deliberately low value.
    total_audio_seconds: int = 1800,
) -> Script:
    return Script(
        city_slug="paris",
        generated_at="2026-07-19T00:00:00Z",
        inputs=TourInput(start=(48.85, 2.35), duration_min=60, city_slug="paris"),
        total_audio_seconds=total_audio_seconds,
        total_walking_seconds=300,
        total_walk_distance_m=400,
        total_planned_seconds=900,
        selected_pois=tuple(pois),
        lens_coverage={},
        script=tuple(sentences),
        validation=ValidationReport(),
    )


def _route(
    pois: list[POI] | None = None,
    *,
    vignettes: dict[int, tuple[POI, ...]] | None = None,
) -> Route:
    return Route(
        pois=tuple(pois or ()),
        transits=(),
        total_walk_distance_m=400.0,
        total_walk_seconds=300,
        vignettes=vignettes or {},
    )


def _checks(report) -> list[str]:
    return [f.check for f in report.findings]


# ---------------------------------------------------------------------------
# C1 — starvation (BLOCKER). The Sainte-Chapelle defect.
# ---------------------------------------------------------------------------


def test_c1_starved_fires_on_the_measured_sainte_chapelle_case() -> None:
    """GUARDS: a rich POI reduced to a one-liner (standard §4 C1, §3 P7).

    The REAL measured case, §5: on the Ile de la Cite 60-min tour, Sainte-Chapelle
    (tier 5, 12 corpus beats) rendered as 9 words = 0.75 words/beat, against a floor
    of 12 x 12 = 144. UNDO: delete the ``if available >= STARVE_MIN_BEATS`` block in
    ``score_tour`` (or raise STARVE_MIN_WORDS_PER_BEAT's effect by making the
    comparison ``words < 0``) and this goes RED.
    """
    poi = _spoi("sainte-chapelle", tier=5, name="Sainte-Chapelle")
    nine_words = "Sainte-Chapelle stands here with its famous windows above you"
    assert len(nine_words.split()) == 9

    report = score_tour(
        _script([_sentence(nine_words, 0)], [poi]),
        _route([_poi("sainte-chapelle", tier=5)]),
        {"sainte-chapelle": _beats("sainte-chapelle", 12)},
    )

    starved = [f for f in report.findings if f.check == "C1-starved"]
    assert len(starved) == 1, _checks(report)
    assert starved[0].severity is Severity.BLOCKER
    assert starved[0].poi_name == "Sainte-Chapelle"
    assert starved[0].stop_idx == 0
    # The floor it was measured against is the standard's, not an ad-hoc number.
    assert f"{STARVE_MIN_WORDS_PER_BEAT * 12:.0f}" in starved[0].message
    assert not report.passed


def test_c1_does_not_fire_for_a_legitimately_thin_poi() -> None:
    """GUARDS: false positives on genuinely thin POIs (standard §5: the thin POIs
    around Sainte-Chapelle had 3 beats and were correctly short).

    3 corpus beats is below STARVE_MIN_BEATS=5, so a short render is an editorial
    outcome, not starvation. UNDO: lower STARVE_MIN_BEATS to 1 (or drop the
    ``available >= STARVE_MIN_BEATS`` guard) and this goes RED.
    """
    assert STARVE_MIN_BEATS == 5  # the fixture's 3 beats must stay under the bar

    poi = _spoi("palais-de-justice", tier=4, name="Palais de Justice")
    report = score_tour(
        _script([_sentence(_words(20, prefix="p"), 0)], [poi]),
        _route([_poi("palais-de-justice", tier=4)]),
        {"palais-de-justice": _beats("palais-de-justice", 3)},
    )

    assert "C1-starved" not in _checks(report)
    assert report.passed


# ---------------------------------------------------------------------------
# C8 — gorging (BLOCKER). The Notre-Dame defect.
# ---------------------------------------------------------------------------


def test_c8_gorged_fires_on_the_measured_over_cap_stop() -> None:
    """GUARDS: an unbroken wall of narration at one stop (standard §4 C8).

    The REAL measured shape, §5: Notre-Dame rendered ~1022-1038 words in a single
    stop, over even the walking-tour ADAPTATION of the museum sector's 250-word
    station ceiling (750 words ~ 5 min at 150 wpm). UNDO: delete the
    ``if words > GORGE_MAX_WORDS_PER_STOP`` block and this goes RED.
    """
    poi = _spoi("notre-dame", tier=5, name="Notre-Dame")
    report = score_tour(
        _script([_sentence(_words(1038, prefix="n"), 0)], [poi]),
        _route([_poi("notre-dame", tier=5)]),
        {"notre-dame": _beats("notre-dame", 59)},  # 1038 > 59*12, so C1 stays silent
    )

    gorged = [f for f in report.findings if f.check == "C8-gorged"]
    assert len(gorged) == 1, _checks(report)
    assert gorged[0].severity is Severity.BLOCKER
    assert gorged[0].poi_name == "Notre-Dame"
    assert "1038" in gorged[0].message
    assert "C1-starved" not in _checks(report)
    assert not report.passed


def test_c8_does_not_fire_at_exactly_the_cap() -> None:
    """GUARDS: the C8 boundary — the cap is inclusive (``>``, not ``>=``).

    A stop of exactly GORGE_MAX_WORDS_PER_STOP words is at budget, not over it.
    UNDO: change the comparison to ``words >= GORGE_MAX_WORDS_PER_STOP`` and this
    goes RED (an off-by-one that would reject a legal 5-minute anchor).
    """
    poi = _spoi("notre-dame", tier=5, name="Notre-Dame")
    at_cap = _words(GORGE_MAX_WORDS_PER_STOP, prefix="c")
    assert len(at_cap.split()) == GORGE_MAX_WORDS_PER_STOP

    report = score_tour(
        _script([_sentence(at_cap, 0)], [poi]),
        _route([_poi("notre-dame", tier=5)]),
        {"notre-dame": _beats("notre-dame", 59)},
    )

    assert "C8-gorged" not in _checks(report)
    assert report.passed


# ---------------------------------------------------------------------------
# C2 — tier inversion (BLOCKER).
# ---------------------------------------------------------------------------


def test_c2_tier_inversion_fires_when_a_rich_tier5_poi_is_only_a_vignette() -> None:
    """GUARDS: the headline POI demoted to a walk-past line while a lesser POI gets
    the full stop (standard §4 C2).

    Fixture: tier-5 Sainte-Chapelle with 12 beats sits in ``route.vignettes`` while
    tier-4 Palais de Justice is the anchor. UNDO: delete the ``for vig in
    vignette_pois`` loop and this goes RED.
    """
    anchor = _spoi("palais-de-justice", tier=4, name="Palais de Justice")
    vignette = _poi("sainte-chapelle", tier=5, name="Sainte-Chapelle")

    report = score_tour(
        _script([_sentence(_words(200, prefix="a"), 0)], [anchor]),
        _route([_poi("palais-de-justice", tier=4)], vignettes={0: (vignette,)}),
        {"sainte-chapelle": _beats("sainte-chapelle", 12)},
    )

    inversions = [f for f in report.findings if f.check == "C2-tier-inversion"]
    assert len(inversions) == 1, _checks(report)
    assert inversions[0].severity is Severity.BLOCKER
    assert inversions[0].poi_name == "Sainte-Chapelle"
    assert not report.passed


def test_c2_does_not_fire_when_the_vignette_is_also_an_anchor() -> None:
    """GUARDS: false positive on a POI that is BOTH an anchor and listed as a
    vignette on its own approach leg — it did get a full stop, so it is no inversion.

    UNDO: delete the ``if vig.id in anchor_ids: continue`` line and this goes RED.
    """
    anchor = _spoi("sainte-chapelle", tier=5, name="Sainte-Chapelle")
    other = _spoi("palais-de-justice", tier=4, name="Palais de Justice")
    vignette = _poi("sainte-chapelle", tier=5, name="Sainte-Chapelle")

    report = score_tour(
        _script(
            [_sentence(_words(200, prefix="a"), 0), _sentence(_words(200, prefix="b"), 1)],
            [anchor, other],
        ),
        _route(
            [_poi("sainte-chapelle", tier=5), _poi("palais-de-justice", tier=4)],
            vignettes={0: (vignette,)},
        ),
        {"sainte-chapelle": _beats("sainte-chapelle", 12)},
    )

    assert "C2-tier-inversion" not in _checks(report)


# ---------------------------------------------------------------------------
# C5 — verbatim repetition (BLOCKER).
# ---------------------------------------------------------------------------


def test_c5_verbatim_repeat_fires_on_a_repeated_sentence() -> None:
    """GUARDS: the same sentence spoken twice in one tour (standard §4 C5, §2 S5,
    §3 P3 "say it once").

    Case-and-whitespace normalised, so a re-cased echo still counts. UNDO: delete the
    C5 loop (or the ``if key in seen`` branch) and this goes RED.
    """
    line = "The rose windows were assembled here in the thirteenth century"
    assert len(line.split()) >= 5

    report = score_tour(
        _script(
            [
                _sentence(line, 0),
                _sentence(_words(30, prefix="x"), 0),
                _sentence("  the ROSE windows were assembled here in the  thirteenth century ", 1),
            ],
            [_spoi("a", tier=3), _spoi("b", tier=3)],
        ),
        _route([_poi("a", tier=3), _poi("b", tier=3)]),
        {},
    )

    repeats = [f for f in report.findings if f.check == "C5-verbatim-repeat"]
    assert len(repeats) == 1, _checks(report)
    assert repeats[0].severity is Severity.BLOCKER
    assert repeats[0].stop_idx == 1
    assert "also at stop 0" in repeats[0].message
    assert not report.passed


def test_c5_does_not_fire_on_short_glue_lines_that_legitimately_recur() -> None:
    """GUARDS: false positives on navigational glue. "Walk on." / "Turn left here."
    recur by design across a tour and must not blocker-fail it.

    The module exempts keys under 5 words. UNDO: delete the
    ``if len(key.split()) < 5: continue`` guard and this goes RED — every tour with
    repeated nav glue would be refused.
    """
    report = score_tour(
        _script(
            [
                _sentence("Walk on.", 0, source_type="glue"),
                _sentence(_words(30, prefix="y"), 0),
                _sentence("Walk on.", 1, source_type="glue"),
                _sentence("Turn left here.", 1, source_type="glue"),
                _sentence(_words(30, prefix="z"), 1),
                _sentence("Turn left here.", 2, source_type="glue"),
                _sentence(_words(30, prefix="w"), 2),
            ],
            [_spoi("a", tier=3), _spoi("b", tier=3), _spoi("c", tier=3)],
        ),
        _route([_poi("a", tier=3), _poi("b", tier=3), _poi("c", tier=3)]),
        {},
    )

    assert "C5-verbatim-repeat" not in _checks(report)
    assert report.passed


# ---------------------------------------------------------------------------
# C6 — empty stop (BLOCKER).
# ---------------------------------------------------------------------------


def test_c6_empty_stop_fires_on_a_stop_with_zero_words() -> None:
    """GUARDS: a stop the tourist walks to and hears nothing at (standard §4 C6).

    UNDO: delete the ``if words == 0`` loop and this goes RED.
    """
    report = score_tour(
        _script(
            [_sentence(_words(40, prefix="e"), 0), _sentence("", 1)],
            [_spoi("a", tier=3), _spoi("b", tier=3)],
        ),
        _route([_poi("a", tier=3), _poi("b", tier=3)]),
        {},
    )

    empties = [f for f in report.findings if f.check == "C6-empty-stop"]
    assert len(empties) == 1, _checks(report)
    assert empties[0].severity is Severity.BLOCKER
    assert empties[0].stop_idx == 1
    assert not report.passed


# ---------------------------------------------------------------------------
# Verdict semantics — passed is driven by BLOCKERs only.
# ---------------------------------------------------------------------------


def test_passed_is_false_with_a_blocker_and_true_with_only_warnings() -> None:
    """GUARDS: the serve/regenerate decision itself (standard §4 severity column,
    §7 "a BLOCKER verdict regenerates the script").

    A WARN must never refuse a tour, and a BLOCKER must always refuse it. UNDO:
    change ``RubricReport.passed`` to ``not self.findings`` and the WARN half goes
    RED; change it to ``True`` and the BLOCKER half goes RED.
    """
    # BLOCKER half — an empty third stop. The two full stops split 50/50 so C4 stays
    # silent and this half isolates the BLOCKER path.
    blocking = score_tour(
        _script(
            [
                _sentence(_words(40, prefix="q"), 0),
                _sentence(_words(40, prefix="k"), 1),
                _sentence("", 2),
            ],
            [_spoi("a", tier=3), _spoi("b", tier=3), _spoi("c", tier=3)],
        ),
        _route([_poi("a", tier=3), _poi("b", tier=3), _poi("c", tier=3)]),
        {},
    )
    assert blocking.blockers and not blocking.warnings
    assert blocking.passed is False
    assert blocking.summary().startswith("FAIL")

    # WARN half — a lopsided but otherwise legal tour.
    warning = score_tour(
        _script(
            [_sentence(_words(200, prefix="r"), 0), _sentence(_words(20, prefix="s"), 1)],
            [_spoi("a", tier=3), _spoi("b", tier=3)],
        ),
        _route([_poi("a", tier=3), _poi("b", tier=3)]),
        {},
    )
    assert warning.warnings and not warning.blockers
    assert warning.passed is True
    assert warning.summary().startswith("PASS")


def test_c4_imbalance_is_a_warn_and_does_not_flip_passed() -> None:
    """GUARDS: severity misclassification of C4 (standard §4: C4 is WARN, surfaced to
    the editor, NOT a regeneration trigger).

    200/20 words = 91% in one stop, over BALANCE_MAX_SHARE=0.60. UNDO: change C4's
    severity to ``Severity.BLOCKER`` and this goes RED. Deleting the C4 block
    entirely also reddens it (the finding disappears).
    """
    assert BALANCE_MAX_SHARE == 0.60

    report = score_tour(
        _script(
            [_sentence(_words(200, prefix="t"), 0), _sentence(_words(20, prefix="u"), 1)],
            [_spoi("a", tier=3), _spoi("b", tier=3)],
        ),
        _route([_poi("a", tier=3), _poi("b", tier=3)]),
        {},
    )

    imbalances = [f for f in report.findings if f.check == "C4-imbalance"]
    assert len(imbalances) == 1, _checks(report)
    assert imbalances[0].severity is Severity.WARN
    assert imbalances[0].stop_idx == 0
    assert report.blockers == []
    assert report.passed is True


def test_c4_imbalance_does_not_fire_on_a_single_stop_tour() -> None:
    """GUARDS: false positive on a one-stop tour, where one stop necessarily holds
    100% of the words and an imbalance warning would be noise.

    UNDO: delete the ``and len(words_by_stop) > 1`` clause and this goes RED.
    """
    report = score_tour(
        _script([_sentence(_words(200, prefix="v"), 0)], [_spoi("a", tier=3)]),
        _route([_poi("a", tier=3)]),
        {},
    )

    assert "C4-imbalance" not in _checks(report)
    assert report.passed


# ---------------------------------------------------------------------------
# Stats — the numbers the workbench surfaces.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("audio_seconds,expected_minutes", [(600, 10.0), (930, 15.5)])
def test_stats_report_word_and_audio_totals(audio_seconds: int, expected_minutes: float) -> None:
    """GUARDS: the report's stats block, which the editor reads to triage a WARN.

    UNDO: drop ``total_words`` from ``report.stats`` (or stop summing per-stop words)
    and this goes RED.
    """
    report = score_tour(
        _script(
            [_sentence(_words(40, prefix="g"), 0), _sentence(_words(60, prefix="h"), 1)],
            [_spoi("a", tier=3), _spoi("b", tier=3)],
            total_audio_seconds=audio_seconds,
        ),
        _route([_poi("a", tier=3), _poi("b", tier=3)]),
        {},
    )

    assert report.stats["total_words"] == 100
    assert report.stats["n_stops"] == 2
    assert report.stats["words_by_stop"] == {0: 40, 1: 60}
    assert report.stats["audio_minutes"] == expected_minutes
