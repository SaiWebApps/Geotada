"""Pins ``src/tour/spatial_check.py`` — the geometry-only WARN check for spatial claims
("look down X toward Y") that ``SemanticFactChecker`` cannot see (it entails propositions,
never the directional instruction wrapped around one).

Every test here is a DISCRIMINATOR: delete the behaviour it names and the test must go
RED. The headline tests (marked HEADLINE below) reproduce the real NYC failure directly
against ``data/new_york/poi-raw.json`` — no synthetic coordinates for the motivating case.

Hermetic: no Neo4j, no network, no LLM. Pure functions + real on-disk corpus JSON only.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from src.tour.contract import Route, Script, ScriptPOI, Sentence, TourInput, ValidationReport
from src.tour.routing import haversine_m
from src.tour.spatial_check import (
    AXIS_TOLERANCE_DEG,
    MAX_PLAUSIBLE_POINT_DISTANCE_M,
    MIN_STOP_TARGET_DISTANCE_M,
    ConservativeRegexExtractor,
    SpatialClaim,
    Verdict,
    _axis_deviation_deg,
    bearing_deg,
    check_script_spatial_claims,
    check_spatial_claim,
    resolve_poi_coords,
    resolve_street_axis_deg,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_NYC_POIS = json.loads((_REPO_ROOT / "data" / "new_york" / "poi-raw.json").read_text())


def _poi(name: str, lat: float, lng: float, *, variations: list[str] | None = None) -> dict:
    return {"name": name, "latitude": lat, "longitude": lng, "name_variations": variations or []}


# ---------------------------------------------------------------------------
# bearing_deg — pure geometry, cardinal sanity
# ---------------------------------------------------------------------------


def test_bearing_deg_due_north_is_zero() -> None:
    assert bearing_deg(40.0, -74.0, 41.0, -74.0) == pytest.approx(0.0, abs=1e-6)


def test_bearing_deg_due_east_is_ninety() -> None:
    # At a real latitude the east-west meridian convergence is tiny but nonzero;
    # abs=0.5 keeps this a sanity check on due-EAST, not an exact-projection test.
    assert bearing_deg(40.0, -74.0, 40.0, -73.9) == pytest.approx(90.0, abs=0.5)


def test_bearing_deg_due_south_is_180() -> None:
    assert bearing_deg(41.0, -74.0, 40.0, -74.0) == pytest.approx(180.0, abs=1e-6)


def test_bearing_deg_due_west_is_270() -> None:
    assert bearing_deg(40.0, -73.9, 40.0, -74.0) == pytest.approx(270.0, abs=0.5)


def test_bearing_deg_same_point_is_defined_not_nan() -> None:
    # atan2(0, 0) is a well-defined 0.0 in Python/math — this pins that it doesn't
    # raise or return NaN for a degenerate (zero-distance) pair.
    result = bearing_deg(40.7, -74.0, 40.7, -74.0)
    assert result == 0.0


# ---------------------------------------------------------------------------
# _axis_deviation_deg — undirected axis-line comparison
# ---------------------------------------------------------------------------


def test_axis_deviation_zero_when_bearing_equals_axis() -> None:
    assert _axis_deviation_deg(102.0, 102.0) == pytest.approx(0.0)


def test_axis_deviation_zero_for_the_opposite_ray() -> None:
    # A street can be walked either way — 282 is "down the same street" as 102.
    assert _axis_deviation_deg(282.0, 102.0) == pytest.approx(0.0)


def test_axis_deviation_is_90_at_perpendicular() -> None:
    assert _axis_deviation_deg(12.0, 102.0) == pytest.approx(90.0)


def test_axis_deviation_wraps_around_0_360_boundary() -> None:
    assert _axis_deviation_deg(2.0, 358.0) == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# resolve_poi_coords — exact-match resolution, UNKNOWN on no match
# ---------------------------------------------------------------------------


def test_resolve_poi_coords_matches_on_name() -> None:
    pois = [_poi("Wall Street", 40.706877, -74.011265)]
    assert resolve_poi_coords(pois, "wall street") == (40.706877, -74.011265)


def test_resolve_poi_coords_matches_on_name_variation() -> None:
    pois = [_poi("Singer Building", 40.72437, -73.9982, variations=["Little Singer Building"])]
    assert resolve_poi_coords(pois, "Little Singer Building") == (40.72437, -73.9982)


def test_resolve_poi_coords_is_none_when_nothing_matches() -> None:
    """UNKNOWN, not a violation: a missing target must resolve to None, never a guess."""
    pois = [_poi("Wall Street", 40.706877, -74.011265)]
    assert resolve_poi_coords(pois, "1 Liberty Plaza") is None


def test_resolve_poi_coords_does_not_fuzzy_match() -> None:
    """No partial/substring matching — a near-miss name must stay UNKNOWN rather than
    silently resolving to the wrong POI (a false accusation risk)."""
    pois = [_poi("Wall Street", 40.706877, -74.011265)]
    assert resolve_poi_coords(pois, "Wall") is None


# ---------------------------------------------------------------------------
# resolve_street_axis_deg — derives a street's axis from real addressed POIs
# ---------------------------------------------------------------------------


def test_resolve_street_axis_from_two_addressed_pois() -> None:
    pois = [
        _poi("Wall Street", 40.706877, -74.011265),
        _poi("1 Wall Street", 40.70722, -74.01167),
        _poi("40 Wall Street", 40.7069, -74.0097),
    ]
    axis = resolve_street_axis_deg(pois, "Wall Street")
    assert axis == pytest.approx(102.09, abs=0.5)


def test_resolve_street_axis_is_none_with_fewer_than_two_addressed_pois() -> None:
    """Only ONE addressed POI ('1 Wall Street') besides the street's own generic
    point — not enough to derive a real axis."""
    pois = [_poi("Wall Street", 40.706877, -74.011265), _poi("1 Wall Street", 40.70722, -74.01167)]
    assert resolve_street_axis_deg(pois, "Wall Street") is None


def test_resolve_street_axis_rejects_pois_closer_than_the_baseline() -> None:
    """Two addressed POIs a metre apart give a numerically noisy bearing — must
    return None (UNKNOWN) rather than an unstable axis. UNDO: dropping the
    AXIS_MIN_BASELINE_M guard makes this assert an axis exists instead."""
    pois = [
        _poi("Wall Street", 40.706877, -74.011265),
        _poi("1 Wall Street", 40.70722, -74.01167),
        _poi("2 Wall Street", 40.707221, -74.011671),  # ~0.1m from "1 Wall Street"
    ]
    assert resolve_street_axis_deg(pois, "Wall Street") is None


def test_resolve_street_axis_is_none_when_street_unresolvable() -> None:
    pois = [_poi("Wall Street", 40.706877, -74.011265)]
    assert resolve_street_axis_deg(pois, "Nonexistent Street") is None


# ---------------------------------------------------------------------------
# ConservativeRegexExtractor — narrow, high-confidence pattern only
# ---------------------------------------------------------------------------


def test_extractor_fires_on_the_real_wall_street_sentence() -> None:
    claims = ConservativeRegexExtractor().extract(
        "Look down Wall Street toward 1 Liberty Plaza."
    )
    assert len(claims) == 1
    assert claims[0].target_name == "1 Liberty Plaza"
    assert claims[0].reference_name == "Wall Street"


def test_extractor_fires_without_the_leading_look() -> None:
    claims = ConservativeRegexExtractor().extract("Walk down Wall Street toward 40 Wall Street.")
    assert len(claims) == 1
    assert claims[0].target_name == "40 Wall Street"


@pytest.mark.parametrize(
    "sentence",
    [
        "The building on your left was built in 1908.",
        "This is one of the oldest streets in Manhattan.",
        "On the far side of the square stands a statue.",
        "Turn to your right and you will see the church.",
        "The tower rising ahead was completed in 1930.",
    ],
)
def test_extractor_recall_is_low_by_design_and_stays_silent_on_other_phrasings(
    sentence: str,
) -> None:
    """Documents the deliberate scope limit: these are all real spatial-cue shapes
    this extractor does NOT attempt — a missed cue is acceptable; a wrong extraction
    that feeds a bad name into the resolver is not."""
    assert ConservativeRegexExtractor().extract(sentence) == []


# ---------------------------------------------------------------------------
# check_spatial_claim — the geometry core
# ---------------------------------------------------------------------------


def test_check_spatial_claim_is_unknown_when_target_unresolvable() -> None:
    pois = [_poi("Wall Street", 40.706877, -74.011265)]
    claim = SpatialClaim(
        sentence="s",
        target_name="1 Liberty Plaza",
        stated_direction="d",
        reference_name="Wall Street",
    )
    result = check_spatial_claim(claim, 40.706877, -74.011265, pois)
    assert result.verdict is Verdict.UNKNOWN


def test_check_spatial_claim_is_unknown_when_axis_unresolvable() -> None:
    pois = [_poi("Wall Street", 40.706877, -74.011265), _poi("Target", 40.71, -74.011265)]
    claim = SpatialClaim(
        sentence="s", target_name="Target", stated_direction="d", reference_name="Wall Street"
    )
    result = check_spatial_claim(claim, 40.706877, -74.011265, pois)
    assert result.verdict is Verdict.UNKNOWN


def test_check_spatial_claim_flags_a_target_beyond_the_distance_bound() -> None:
    """The 'target 3km away behind buildings is not just ahead' motivating case,
    with no axis reference at all (a bare 'toward' claim)."""
    far_lat = 40.706877 + (MAX_PLAUSIBLE_POINT_DISTANCE_M * 3 / 111_000)  # ~3km north
    pois = [_poi("Wall Street", 40.706877, -74.011265), _poi("Far Tower", far_lat, -74.011265)]
    claim = SpatialClaim(sentence="s", target_name="Far Tower", stated_direction="toward")
    result = check_spatial_claim(claim, 40.706877, -74.011265, pois)
    assert result.verdict is Verdict.IMPLAUSIBLE
    assert "too far" in result.reason


def test_check_spatial_claim_passes_a_bare_toward_claim_within_distance() -> None:
    pois = [_poi("Wall Street", 40.706877, -74.011265), _poi("Near Thing", 40.7075, -74.011265)]
    claim = SpatialClaim(sentence="s", target_name="Near Thing", stated_direction="toward")
    result = check_spatial_claim(claim, 40.706877, -74.011265, pois)
    assert result.verdict is Verdict.PLAUSIBLE


def test_undo_check_spatial_claim_axis_tolerance_reddens_when_removed() -> None:
    """MUTATION-VERIFIED discriminator for the axis-deviation branch: a target 90
    degrees off axis must be IMPLAUSIBLE. If the ``deviation > AXIS_TOLERANCE_DEG``
    branch is deleted (falls through to PLAUSIBLE), this test goes RED."""
    pois = [
        _poi("Wall Street", 40.706877, -74.011265),
        _poi("1 Wall Street", 40.70722, -74.01167),
        _poi("40 Wall Street", 40.7069, -74.0097),
        _poi("Due North Thing", 40.71, -74.011265),  # bearing ~0 deg, axis ~102/282
    ]
    claim = SpatialClaim(
        sentence="s",
        target_name="Due North Thing",
        stated_direction="down Wall Street toward",
        reference_name="Wall Street",
    )
    result = check_spatial_claim(claim, 40.706877, -74.011265, pois)
    assert result.verdict is Verdict.IMPLAUSIBLE
    assert result.axis_deg is not None
    assert _axis_deviation_deg(result.bearing_to_target_deg, result.axis_deg) > AXIS_TOLERANCE_DEG


# ---------------------------------------------------------------------------
# HEADLINE — the real NYC case, real data/new_york/poi-raw.json coordinates
# ---------------------------------------------------------------------------


def test_headline_real_wall_street_axis_matches_the_reported_103_283() -> None:
    """MEASURED against the real corpus. The task's reported figure: Wall Street's
    axis runs ~103/283 degrees. Computed here from two REAL addressed POIs in
    data/new_york/poi-raw.json ('1 Wall Street' and '40 Wall Street') — not
    invented, not adjusted to fit."""
    axis = resolve_street_axis_deg(_NYC_POIS, "Wall Street")
    assert axis is not None
    assert axis == pytest.approx(102.1, abs=1.0)


def test_headline_literal_1_liberty_plaza_is_not_a_poi_in_new_york_corpus() -> None:
    """HONEST FINDING, stated per the task's own instruction: 'if the real
    coordinates do not reproduce the figure above, SAY SO.' data/new_york/poi-raw.json
    has NO POI named or aliased '1 Liberty Plaza' (the demolished Singer Building at
    that address was never given its own POI entry — the only 'Singer Building' POI
    in this corpus is the unrelated 'Little Singer Building' in SoHo, ~1.9 km away).
    The resolver's honest, correct behaviour on the REAL corpus is UNKNOWN — not a
    violation. This is the seam the task asked to be surfaced, not hidden."""
    assert resolve_poi_coords(_NYC_POIS, "1 Liberty Plaza") is None
    wall = resolve_poi_coords(_NYC_POIS, "Wall Street")
    claim = SpatialClaim(
        sentence="Look down Wall Street toward 1 Liberty Plaza.",
        target_name="1 Liberty Plaza",
        stated_direction="down Wall Street toward",
        reference_name="Wall Street",
    )
    result = check_spatial_claim(claim, *wall, _NYC_POIS)
    assert result.verdict is Verdict.UNKNOWN  # MUST NOT be reported as a violation


def test_headline_wall_street_toward_zuccotti_park_reproduces_the_near_north_mismatch() -> None:
    """HEADLINE. Since '1 Liberty Plaza' itself is not a resolvable POI (see the test
    above), this proves the geometry core on the closest real, resolvable stand-in:
    'Zuccotti Park' (formerly Liberty Plaza Park — the plaza '1 Liberty Plaza' the
    building takes its address from), at real poi-raw.json coordinates 261 m from the
    real 'Wall Street' POI, bearing ~0 degrees (due north) — the same "nearly due
    north" character as the task's reported 345 degrees, and ~78 degrees off Wall
    Street's real ~102/282 axis (comfortably past AXIS_TOLERANCE_DEG=40). The exact
    reported '345' figure could not be reproduced (this repo's Wall Street stop point
    is not necessarily the exact coordinate the live tour run narrated from), but the
    conclusion — a claimed 'down Wall Street' cue pointing roughly PERPENDICULAR to
    Wall Street's real axis — reproduces cleanly on real, unmodified corpus data.
    """
    wall = resolve_poi_coords(_NYC_POIS, "Wall Street")
    zuccotti = resolve_poi_coords(_NYC_POIS, "Zuccotti Park")
    assert wall is not None and zuccotti is not None

    bearing = bearing_deg(*wall, *zuccotti)
    axis = resolve_street_axis_deg(_NYC_POIS, "Wall Street")
    assert bearing == pytest.approx(0.33, abs=0.5)  # near-due-north, MEASURED
    assert axis == pytest.approx(102.1, abs=0.5)  # MEASURED
    assert _axis_deviation_deg(bearing, axis) == pytest.approx(78.2, abs=1.0)

    claim = SpatialClaim(
        sentence="Look down Wall Street toward 1 Liberty Plaza.",
        target_name="Zuccotti Park",
        stated_direction="down Wall Street toward",
        reference_name="Wall Street",
    )
    result = check_spatial_claim(claim, *wall, _NYC_POIS)
    assert result.verdict is Verdict.IMPLAUSIBLE


def test_headline_a_genuinely_correct_wall_street_cue_does_not_flag() -> None:
    """HEADLINE (negative control). '40 Wall Street' really is addressed on Wall
    Street and its real bearing from the 'Wall Street' POI (~89 degrees) sits close
    to the street's own real axis (~102 degrees) — this must NOT be flagged."""
    wall = resolve_poi_coords(_NYC_POIS, "Wall Street")
    assert wall is not None
    claim = SpatialClaim(
        sentence="Look down Wall Street toward 40 Wall Street.",
        target_name="40 Wall Street",
        stated_direction="down Wall Street toward",
        reference_name="Wall Street",
    )
    result = check_spatial_claim(claim, *wall, _NYC_POIS)
    assert result.verdict is Verdict.PLAUSIBLE


# ---------------------------------------------------------------------------
# DEFECT 1 — a real long-sightline avenue cue must NOT be flagged on distance alone
# ---------------------------------------------------------------------------


def test_defect1_long_correct_avenue_sightline_is_not_flagged_on_distance_alone() -> None:
    """HEADLINE / MUTATION-VERIFIED. Real, public Manhattan coordinates: Washington
    Square Arch (Fifth Avenue's southern end) is ~2.19 km from the Empire State
    Building (350 Fifth Avenue) — comfortably past MAX_PLAUSIBLE_POINT_DISTANCE_M —
    yet the real bearing is only ~4 degrees off Fifth Avenue's own real axis (derived
    from two genuinely addressed Fifth Avenue POIs). This is exactly the shape the
    hostile shadow reproduced: 'Look up Fifth Avenue toward the Empire State
    Building' is a CORRECT, natural cue down a long avenue, not a violation.

    UNDO: reintroducing the old `if distance_m > MAX_PLAUSIBLE_POINT_DISTANCE_M`
    short-circuit BEFORE axis resolution turns this RED (IMPLAUSIBLE instead of
    PLAUSIBLE), which is the exact false accusation the shadow found.
    """
    washington_sq_arch = (40.7308, -73.9973)
    flatiron_175_fifth = (40.7411, -73.9897)
    empire_state = (40.7484, -73.9857)

    pois = [
        _poi("Fifth Avenue", *washington_sq_arch),
        _poi("175 Fifth Avenue", *flatiron_175_fifth),
        _poi(
            "350 Fifth Avenue", *empire_state, variations=["Empire State Building"]
        ),
    ]

    distance_m = MAX_PLAUSIBLE_POINT_DISTANCE_M  # sanity anchor for the assertion below
    claim = SpatialClaim(
        sentence="Look up Fifth Avenue toward the Empire State Building.",
        target_name="Empire State Building",
        stated_direction="up Fifth Avenue toward",
        reference_name="Fifth Avenue",
    )
    result = check_spatial_claim(claim, *washington_sq_arch, pois)
    assert result.distance_m is not None and result.distance_m > distance_m * 2, (
        "test setup must exercise a target well past the distance cap"
    )
    assert result.verdict is Verdict.PLAUSIBLE
    assert "within axis tolerance" in result.reason


def test_defect1_axis_mismatch_still_flags_regardless_of_distance() -> None:
    """Negative control for the DEFECT 1 fix: removing the distance short-circuit must
    not also remove the ability to catch a genuine axis mismatch — the axis-confirmed
    IMPLAUSIBLE path must still fire even though this target is also past the old
    distance cap (proves the fix narrows the false-positive, it doesn't gut the check)."""
    washington_sq_arch = (40.7308, -73.9973)
    flatiron_175_fifth = (40.7411, -73.9897)
    empire_state = (40.7484, -73.9857)
    # A real target far off Fifth Avenue's axis (due east of the stop, not up the avenue).
    far_off_axis_target = (40.7309, -73.9700)

    pois = [
        _poi("Fifth Avenue", *washington_sq_arch),
        _poi("175 Fifth Avenue", *flatiron_175_fifth),
        _poi("350 Fifth Avenue", *empire_state),
        _poi("Off Axis Tower", *far_off_axis_target),
    ]
    claim = SpatialClaim(
        sentence="s",
        target_name="Off Axis Tower",
        stated_direction="up Fifth Avenue toward",
        reference_name="Fifth Avenue",
    )
    result = check_spatial_claim(claim, *washington_sq_arch, pois)
    assert result.verdict is Verdict.IMPLAUSIBLE


# ---------------------------------------------------------------------------
# DEFECT 2 — a minimum stop->target distance floor guards the judged bearing
# ---------------------------------------------------------------------------


def test_defect2_point_blank_target_is_unknown_not_confidently_judged() -> None:
    """MUTATION-VERIFIED. A stop and target a few metres apart (well under
    MIN_STOP_TARGET_DISTANCE_M) give a numerically unstable bearing — the axis check
    must refuse to judge it rather than confidently emitting PLAUSIBLE/IMPLAUSIBLE.
    UNDO: dropping the ``distance_m < MIN_STOP_TARGET_DISTANCE_M`` guard makes this
    fall through to a confident (and unstable) axis verdict instead of UNKNOWN."""
    stop = (40.706877, -74.011265)
    point_blank_target = (40.706880, -74.011268)  # ~0.4 m away
    assert haversine_m(*stop, *point_blank_target) < MIN_STOP_TARGET_DISTANCE_M, (
        "test setup must place the target inside the floor"
    )

    pois = [
        _poi("Wall Street", *stop),
        _poi("1 Wall Street", 40.70722, -74.01167),
        _poi("40 Wall Street", 40.7069, -74.0097),
        _poi("Point Blank Thing", *point_blank_target),
    ]
    claim = SpatialClaim(
        sentence="s",
        target_name="Point Blank Thing",
        stated_direction="down Wall Street toward",
        reference_name="Wall Street",
    )
    result = check_spatial_claim(claim, *stop, pois)
    assert result.verdict is Verdict.UNKNOWN
    assert "unstable" in result.reason


def test_defect2_geocode_confidence_field_is_actually_read_in_axis_resolution() -> None:
    """MUTATION-VERIFIED. A candidate street-axis sibling flagged LOW geocode
    confidence in the corpus's own ``_pipeline.geocode_confidence`` field must not
    seed an axis — this is the field the AXIS_MIN_BASELINE_M docstring cites but the
    pre-fix code never read. UNDO: dropping the geocode_confidence filter in
    ``resolve_street_axis_deg`` makes this resolve an axis instead of ``None``."""
    pois = [
        _poi("Wall Street", 40.706877, -74.011265),
        {
            "name": "1 Wall Street",
            "latitude": 40.70722,
            "longitude": -74.01167,
            "name_variations": [],
            "_pipeline": {"geocode_confidence": "LOW"},
        },
        {
            "name": "40 Wall Street",
            "latitude": 40.7069,
            "longitude": -74.0097,
            "name_variations": [],
            "_pipeline": {"geocode_confidence": "LOW"},
        },
    ]
    assert resolve_street_axis_deg(pois, "Wall Street") is None


def test_defect2_high_confidence_siblings_still_resolve_an_axis() -> None:
    """Positive control for the above: the same two POIs with HIGH confidence must
    still resolve the axis — proves the LOW-confidence filter is targeted, not a
    blanket regression that breaks every corpus entry carrying the field at all."""
    pois = [
        _poi("Wall Street", 40.706877, -74.011265),
        {
            "name": "1 Wall Street",
            "latitude": 40.70722,
            "longitude": -74.01167,
            "name_variations": [],
            "_pipeline": {"geocode_confidence": "HIGH"},
        },
        {
            "name": "40 Wall Street",
            "latitude": 40.7069,
            "longitude": -74.0097,
            "name_variations": [],
            "_pipeline": {"geocode_confidence": "HIGH"},
        },
    ]
    axis = resolve_street_axis_deg(pois, "Wall Street")
    assert axis == pytest.approx(102.09, abs=0.5)


# ---------------------------------------------------------------------------
# DEFECT 3 — the endswith-suffix axis heuristic must reject non-street siblings
# ---------------------------------------------------------------------------


def test_defect3_real_bogus_club_axis_is_now_rejected() -> None:
    """HEADLINE / MUTATION-VERIFIED. Reproduces the shadow's exact finding against
    the real, unmodified ``data/new_york/poi-raw.json``: 12 unrelated private clubs
    across Manhattan (Salmagundi Club, National Arts Club, Metropolitan Club, ...)
    all end with the word "Club" and, pre-fix, manufactured a spurious ~38.6 degree
    axis with no real street behind any of them. UNDO: reverting the leading-house-
    number requirement in ``resolve_street_axis_deg`` reproduces the bogus axis."""
    axis = resolve_street_axis_deg(_NYC_POIS, "Club")
    assert axis is None


def test_defect3_endswith_match_without_a_house_number_is_rejected() -> None:
    """Minimal, synthetic discriminator for the same mechanism: two POIs that share a
    name SUFFIX with the queried street but carry no leading house number must not
    seed an axis, even though they clear the distance baseline."""
    pois = [
        _poi("Study Club", 40.706877, -74.011265),
        _poi("Painters Club", 40.71, -74.02),  # >1km away, no real street relation
    ]
    assert resolve_street_axis_deg(pois, "Club") is None


def test_defect3_implausibly_spread_addressed_matches_are_rejected() -> None:
    """Even WITH a leading house number on both sides, siblings spread far beyond any
    real single street (here, ~9 km apart across a city) must not seed an axis —
    the MAX_AXIS_SPREAD_M guard. UNDO: removing that guard resolves an axis instead
    of ``None`` for this synthetic same-name-coincidence case."""
    pois = [
        _poi("Main Street", 40.706877, -74.011265),
        _poi("1 Main Street", 40.71, -74.011265),  # ~350 m away — fine on its own
        _poi("500 Main Street", 40.79, -74.011265),  # ~9.3 km away — implausible spread
    ]
    assert resolve_street_axis_deg(pois, "Main Street") is None


# ---------------------------------------------------------------------------
# DEFECT 4 — prefer the axis pair nearest the stop over the furthest-apart pair
# ---------------------------------------------------------------------------


def test_defect4_prefers_the_local_pair_over_the_furthest_apart_pair() -> None:
    """MUTATION-VERIFIED. A synthetic curving street: the citywide-furthest addressed
    pair gives one axis, but the LOCAL pair nearest the stop gives a materially
    different one (a real curving street bends). With a stop injected, the nearest
    pair must win. UNDO: reverting to unconditional furthest-apart selection changes
    the result back to the far-pair axis."""
    p1 = (40.7000, -74.0000)  # '1 Curve Street' — far south end
    p2 = (40.7010, -74.0100)  # '50 Curve Street' — mid-bend
    p3 = (40.7020, -74.0102)  # '90 Curve Street' — north end, near the stop
    stop = (40.7021, -74.0101)

    pois = [
        _poi("Curve Street", 40.7015, -74.0090),  # generic point, excluded (no house #)
        _poi("1 Curve Street", *p1),
        _poi("50 Curve Street", *p2),
        _poi("90 Curve Street", *p3),
    ]

    far_pair_axis = resolve_street_axis_deg(pois, "Curve Street")
    near_pair_axis = resolve_street_axis_deg(
        pois, "Curve Street", stop_lat=stop[0], stop_lng=stop[1]
    )

    assert far_pair_axis == pytest.approx(104.5, abs=0.5)
    assert near_pair_axis == pytest.approx(171.4, abs=0.5)
    assert abs(far_pair_axis - near_pair_axis) > 30, "test setup must actually diverge"


# ---------------------------------------------------------------------------
# check_script_spatial_claims — Script-level wiring, WARN-shaped findings
# ---------------------------------------------------------------------------


def _sentence(text: str, stop_idx: int) -> Sentence:
    return Sentence(text=text, source_id=f"b-{stop_idx}", source_type="beat", stop_idx=stop_idx)


def _script_with_wall_street_stop(sentence_text: str) -> Script:
    wall = resolve_poi_coords(_NYC_POIS, "Wall Street")
    assert wall is not None
    lat, lng = wall
    return Script(
        city_slug="new_york",
        generated_at="2026-07-19T00:00:00Z",
        inputs=TourInput(start=(lat, lng), duration_min=60, city_slug="new_york"),
        total_audio_seconds=1800,
        total_walking_seconds=300,
        total_walk_distance_m=400,
        total_planned_seconds=900,
        selected_pois=(ScriptPOI(id="wall-street", name="Wall Street", tier=5, lat=lat, lng=lng),),
        lens_coverage={},
        script=(_sentence(sentence_text, 0),),
        validation=ValidationReport(),
    )


def test_check_script_spatial_claims_flags_the_real_case_via_city_pois_injection() -> None:
    """Same claim as the headline test, run through the Script-level entry point with
    a real corpus stand-in target injected via ``city_pois=`` (the documented test
    seam) — proves the wiring end to end without touching disk."""
    script = _script_with_wall_street_stop("Look down Wall Street toward Zuccotti Park.")
    findings = check_script_spatial_claims(script, city_pois=_NYC_POIS)
    assert len(findings) == 1
    assert findings[0].check == "S1-unverified-direction"
    assert findings[0].stop_idx == 0
    assert findings[0].poi_name == "Wall Street"


def test_check_script_spatial_claims_stays_silent_on_the_correct_cue() -> None:
    script = _script_with_wall_street_stop("Look down Wall Street toward 40 Wall Street.")
    findings = check_script_spatial_claims(script, city_pois=_NYC_POIS)
    assert findings == []


def test_check_script_spatial_claims_stays_silent_when_target_unresolvable() -> None:
    """The literal, real-corpus case: '1 Liberty Plaza' is UNKNOWN, not a violation —
    the wiring must never turn an UNKNOWN verdict into a finding."""
    script = _script_with_wall_street_stop("Look down Wall Street toward 1 Liberty Plaza.")
    findings = check_script_spatial_claims(script, city_pois=_NYC_POIS)
    assert findings == []


def test_check_script_spatial_claims_loads_the_real_city_corpus_when_not_injected() -> None:
    """No ``city_pois=`` override — exercises the real on-disk loader against the
    real data/new_york/poi-raw.json, end to end."""
    script = _script_with_wall_street_stop("Look down Wall Street toward Zuccotti Park.")
    findings = check_script_spatial_claims(script)
    assert len(findings) == 1
    assert findings[0].check == "S1-unverified-direction"


# ---------------------------------------------------------------------------
# quality_rubric wiring — additive, WARN, never flips `passed`
# ---------------------------------------------------------------------------


def test_deliberately_not_wired_into_quality_rubric() -> None:
    """DECISION GUARD. spatial_check is built and tested but MUST NOT be called from
    score_tour. It was wired on 2026-07-19 and unwired the same day, on measurement.

    The hole it targets is real — SemanticFactChecker entails PROPOSITIONS and never
    sees the directional instruction wrapped around one, so a geometrically false cue
    passes fact-check 0-unsupported. But the module as built emits FALSE ACCUSATIONS on
    real shipped data. Reproduced end-to-end against unmodified data/new_york/poi-raw.json
    with the shipped ConservativeRegexExtractor:

        "Look down Wall Street toward Trinity Church."  ->  IMPLAUSIBLE

    That cue is CORRECT. Trinity Church stands at the head of Wall Street and is its
    single most recognisable sightline; the check rejects it because the street axis is
    derived by matching POIs whose names merely END WITH "Wall Street".

    A missed cue costs nothing. A false accusation tells an editor a true sentence is
    wrong -- and the standard explicitly REWARDS concrete look-cues (C10/G1), so this
    check would fight the property we are trying to increase. Precision must be ~100% on
    real look-cues before wiring at ANY severity, including WARN.

    Also unresolved: street-axis resolution succeeds for 2 of 13 addressed NYC candidates
    (one spurious), and data/{city}/poi-raw.json is not shipped in the production image,
    so it would degrade to all-UNKNOWN in prod regardless.

    See [[founding-case-efficacy-rule]]: the founding case (a false look-cue) was never
    measured as PRECISION over all real look-cues, which is exactly how the Trinity
    Church regression survived a full build-and-repair cycle.
    """
    import src.tour.quality_rubric as quality_rubric

    src = inspect.getsource(quality_rubric)
    assert "check_script_spatial_claims(" not in src, (
        "spatial_check must not be called from quality_rubric until its precision on "
        "real look-cues is measured at ~100% -- it currently false-accuses a correct "
        "Wall Street / Trinity Church cue"
    )

    script = _script_with_wall_street_stop("Look down Wall Street toward Zuccotti Park.")
    route = Route(pois=(), transits=(), total_walk_distance_m=400.0, total_walk_seconds=300)
    report = quality_rubric.score_tour(script, route, beats_by_poi={})
    assert not [f for f in report.findings if f.check.startswith("S1-")]
