"""SPATIAL CLAIM CHECK — geometry the fact-checker cannot see.

THE HOLE this exists to close (found by an opus tour-adversary on a live NYC tour,
independently verified against this repo's own data — see ``check_script_spatial_claims``
docstring and ``tests/test_spatial_check.py`` for the full real-coordinate reproduction):
a re-authored Wall Street stop opened "Look down Wall Street toward 1 Liberty Plaza."
Wall Street runs roughly east-west; the target the sentence points at sits roughly due
north of the stop. The walker is aimed down a street the target is not on. The sentence
passed fact-check 0-unsupported / 0-missing, because ``SemanticFactChecker`` entails
PROPOSITIONS ("the Singer Building once stood on that site") against source facts — the
directional instruction wrapped around the proposition is not a proposition at all, so no
existing gate ever looks at it.

THE SEAM, stated honestly: identifying WHICH SPAN of narration is a spatial instruction,
and WHAT it names as a target, is a MEANING-level extraction problem — the kind this repo
otherwise bans lexical shortcuts for (see ``feedback-no-lexical-shortcuts``). This module
does not pretend otherwise. ``ConservativeRegexExtractor`` below is a deliberately narrow,
low-recall placeholder for that seam, documented as such, wired behind the ``SpatialClaim
Extractor`` Protocol so a model-based extractor can replace it later without touching the
geometry core.

Once a claim is EXTRACTED, though, verifying it is pure arithmetic: a bearing between two
coordinates is deterministic, computable math, not interpretation. That is the part this
module verifies with confidence, and the part that is unit-tested exhaustively.

Two layers, mirroring ``quality_rubric.py``:
* Geometry core (``bearing_deg``, ``check_spatial_claim``) — pure, deterministic, exhaustively
  tested, no I/O.
* Corpus resolution (``resolve_poi_coords``, ``resolve_street_axis_deg``, the poi-raw.json
  loader) — touches ``data/{city_slug}/poi-raw.json``, the canonical POI source of truth.
  A target that does not resolve is UNKNOWN, never a violation: silence beats a false
  accusation.

NOT WIRED INTO ANY GATE. ``check_script_spatial_claims`` is exercised only by
``tests/test_spatial_check.py``; ``quality_rubric.score_tour`` deliberately does NOT call
it, and a test greps this module's name out of that module's source to keep it that way.
It was wired on 2026-07-19 and UNWIRED the same day on measurement. This docstring
claimed the opposite until 2026-07-30 — a conservative extractor plus a brand-new
geometry check has not earned any severity yet, let alone blocker.

HONEST STATUS, post 2026-07-19 hostile-review repair (see ``resolve_street_axis_deg``'s
docstring for the exact numbers): a false-accusation bug (distance short-circuiting before
axis resolution) and an unsound axis-resolution heuristic (a bare name-suffix match
manufacturing a bogus axis from unrelated POIs) are both fixed and regression-tested
against real corpus coordinates. Separately, scanning EVERY sentence of all 94 real
generated tour transcripts in ``data/{paris,london}/tours/*.md`` (9,642 sentences) with
the fixed code produced ZERO axis-claim extractions — the conservative extractor's
low recall means this check has not yet fired on any real shipped narration at all. Its
real-world value today is unproven both ways: no false accusations shipped, but also no
real narration it has caught anything genuinely wrong in yet. This module also has ZERO
coverage in the deployed production API (see the corpus-loading section below) — today
it earns real coverage only locally, in the workbench, and in this file's own tests.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from src.tour.contract import Script
from src.tour.routing import haversine_m

# ── provenance-tracked thresholds ───────────────────────────────────────────
# Same voice as quality_rubric.py:34-39 — every constant states its KIND.
#   MEASURED  — derived from a real, reproducible computation on the live NYC graph
#   JUDGEMENT — chosen by us; documented with the reasoning, not tuned to make a test pass

#: JUDGEMENT. Two addressed POIs on a named street must be at least this far apart before
#: their bearing is trusted as the street's axis — below this, GPS rounding and the corpus's
#: own geocode noise (poi-raw.json's own ``geocode_confidence`` field shows some entries are
#: web-search-derived, not surveyed) dominate the computed angle. 30 m is a single building
#: frontage; two POIs closer than that are not giving the street a meaningful direction.
#: The ``geocode_confidence`` field cited above IS read — ``resolve_street_axis_deg`` drops
#: any candidate sibling whose ``_pipeline.geocode_confidence`` is ``"LOW"`` before it ever
#: reaches this baseline check (see DEFECT 2/3 fix, 2026-07-19).
AXIS_MIN_BASELINE_M: float = 30.0

#: JUDGEMENT, same reasoning as ``AXIS_MIN_BASELINE_M`` applied to the OTHER leg of the
#: geometry: the stop -> target bearing that ``AXIS_TOLERANCE_DEG`` actually judges. Before
#: this floor existed, a stop and target a few metres apart (well within ordinary geocode
#: noise) produced a wildly unstable bearing that was then judged with full 40-degree
#: confidence — the docstring above already blamed geocode noise for exactly this failure
#: mode but nothing enforced it on this leg. 30 m matches the axis-pair floor: a single
#: building frontage is not enough separation to trust a bearing.
MIN_STOP_TARGET_DISTANCE_M: float = 30.0

#: JUDGEMENT, anchored on a MEASURED false positive: the real New York corpus's own POIs
#: whose names merely END WITH "Club" (12 unrelated private clubs scattered across
#: Manhattan — Salmagundi, National Arts, Metropolitan, Union, etc.) span several km and
#: previously manufactured a spurious ~38.6 degree "axis" with no real street behind it.
#: A genuine single named street's addressed buildings cluster tightly (the real Wall
#: Street pair above is ~204 m apart); 2 km is generous headroom for a real short/medium
#: street while still catching a citywide same-suffix coincidence like the Club case.
MAX_AXIS_SPREAD_M: float = 2_000.0

#: JUDGEMENT, anchored on MEASURED data (see the module docstring and the headline test).
#: On the real NYC corpus, the two addressed "Wall Street" POIs give an axis of ~102/282
#: degrees; the real "Zuccotti Park" stand-in for the reported target bears ~0 degrees from
#: the "Wall Street" stop — a ~78 degree deviation from the axis LINE (undirected, so the
#: max possible deviation is 90). The correct "down Wall Street toward 40 Wall Street" case
#: measures ~13 degrees off axis. 40 degrees sits cleanly between the two MEASURED cases:
#: comfortably clears real streets' gentle curves and this corpus's own geocode noise,
#: while still catching a genuine 90-degree-scale wrong-direction claim.
AXIS_TOLERANCE_DEG: float = 40.0

#: JUDGEMENT. Derived from the motivating failure mode ("a target 3 km away behind
#: buildings is not 'just ahead'") rather than tuned on a measured case: pick a bound well
#: under 3 km. The extractor this bound sits behind only fires on an explicit "down/along/up
#: <street> toward <target>" pattern (a stop-to-stop, walking-scale relationship in this
#: corpus), so 1 km is generous headroom for a real distant landmark call-out while still
#: catching the reported failure class by an order of magnitude.
#:
#: DEFECT 1 fix (2026-07-19): this bound is used ONLY for a bare "toward X" claim that
#: carries no street/axis reference at all — there is nothing else checkable for that
#: shape. It plays NO role once an axis reference is present: a long, CORRECT sightline
#: down a real street/avenue routinely exceeds 1 km ("Look up Fifth Avenue toward the
#: Empire State Building" is ~2.2 km and dead on-axis) and must not be flagged on distance
#: alone. See ``check_spatial_claim`` and the Fifth-Avenue regression test.
MAX_PLAUSIBLE_POINT_DISTANCE_M: float = 1_000.0


class Verdict(StrEnum):
    """UNKNOWN is a valid, honest result and MUST NOT be treated as a violation —
    silence beats a false accusation when the corpus cannot resolve a name."""

    PLAUSIBLE = "plausible"
    IMPLAUSIBLE = "implausible"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SpatialClaim:
    """One extracted spatial instruction. ``target_name`` is what the claim points at;
    ``reference_name`` is the axis it is claimed relative to (e.g. the street name in
    "down Wall Street toward X"), or ``None`` when the claim carries no axis reference
    (a bare "toward X" / "just ahead of X"), in which case only the distance/visibility
    bound is checkable — there is no facing direction to compare against."""

    sentence: str
    target_name: str
    stated_direction: str
    reference_name: str | None = None


class SpatialClaimExtractor(Protocol):
    """Whatever turns narration text into ``SpatialClaim``s. The seam a model-based
    extractor plugs into later; ``ConservativeRegexExtractor`` is the v1 placeholder."""

    def extract(self, sentence: str) -> list[SpatialClaim]: ...


# Fires ONLY on "(look) down/along/up <Street> toward/to/at <Target>" — the exact shape
# of the reported failure. Deliberately does not attempt "on your left", "across the
# square", "the tower rising ahead", or any other spatial phrasing: recall is LOW BY
# DESIGN. A missed cue is silently unchecked (acceptable); this pattern's job is only to
# never mis-extract, since a wrong extraction of target/street feeds bad names into the
# resolver and produces a nonsense verdict where UNKNOWN would have been honest.
_AXIS_CLAIM_RE = re.compile(
    r"\b(?:look(?:ing)?\s+)?(?:down|along|up)\s+"
    r"(?P<street>[A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*){0,4})\s+"
    r"(?:toward|towards|to|at)\s+"
    r"(?P<target>(?:\d+[\w-]*\s+)?[A-Z][\w&'.,-]*(?:\s+[A-Z][\w&'.,-]*){0,5})"
    r"(?=[.,;:!?]|$)"
)


class ConservativeRegexExtractor:
    """v1 placeholder extractor. Low recall BY DESIGN (see module + regex docstrings):
    only the unambiguous "down/along/up <street> toward <target>" shape fires. Everything
    else — "on your left", "across the square", implicit look-cues — is silently unchecked
    rather than guessed at. A missed cue is acceptable; a false accusation is not."""

    def extract(self, sentence: str) -> list[SpatialClaim]:
        claims = []
        for m in _AXIS_CLAIM_RE.finditer(sentence):
            street = m.group("street").strip()
            target = m.group("target").strip().rstrip(".,;:")
            if not street or not target:
                continue
            claims.append(
                SpatialClaim(
                    sentence=sentence,
                    target_name=target,
                    stated_direction=m.group(0),
                    reference_name=street,
                )
            )
        return claims


# ── geometry core — pure, deterministic ─────────────────────────────────────


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, in degrees, [0, 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lng2 - lng1)
    x = math.sin(dlmb) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def _angular_diff_deg(a: float, b: float) -> float:
    """Smallest angle between two bearings, [0, 180]."""
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def _axis_deviation_deg(bearing: float, axis_deg: float) -> float:
    """How far ``bearing`` sits off an undirected axis LINE (``axis_deg`` mod 180 — a
    street can be walked either way), [0, 90]."""
    return min(_angular_diff_deg(bearing, axis_deg), _angular_diff_deg(bearing, axis_deg + 180.0))


def _normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


# DEFECT 3 fix: an ``endswith(street_name)`` match is not enough to call a POI "addressed
# on" that street — see ``resolve_street_axis_deg``. A genuine addressed building name
# carries a leading house number ("40 Wall Street"); a bare name that merely ends in the
# same words ("Salmagundi Club" ending in "club") does not.
_ADDRESSED_HOUSE_NUMBER_RE = re.compile(r"^\d+[\w-]*\s")


def _geocode_confidence(poi: dict) -> str | None:
    """Reads poi-raw.json's own ``_pipeline.geocode_confidence`` (HIGH/MEDIUM/LOW). This
    field is cited in ``AXIS_MIN_BASELINE_M``'s docstring as a reason to distrust noisy
    entries; ``resolve_street_axis_deg`` is where it is actually read and enforced."""
    pipeline = poi.get("_pipeline")
    if not isinstance(pipeline, dict):
        return None
    return pipeline.get("geocode_confidence")


def resolve_poi_coords(city_pois, name: str) -> tuple[float, float] | None:
    """Resolve a target name to (lat, lng) against a city's POI roster (poi-raw.json
    shape: dicts with ``name``/``name_variations``/``latitude``/``longitude``).
    Exact match only (case/whitespace-normalized) — no fuzzy matching, so a resolved
    target is always a real, unambiguous corpus POI. Returns ``None`` — UNKNOWN, not a
    violation — when nothing matches."""
    needle = _normalize_name(name)
    if not needle:
        return None
    for poi in city_pois:
        candidates = [poi.get("name", "")]
        candidates.extend(poi.get("name_variations") or [])
        if any(c and _normalize_name(c) == needle for c in candidates):
            lat, lng = poi.get("latitude"), poi.get("longitude")
            if lat is None or lng is None:
                return None
            return float(lat), float(lng)
    return None


def resolve_street_axis_deg(
    city_pois,
    street_name: str,
    *,
    stop_lat: float | None = None,
    stop_lng: float | None = None,
) -> float | None:
    """Approximate a named street's axis (degrees, mod 180 — undirected) from real
    corpus POIs, since poi-raw.json has no street-geometry field, only POI points.

    SEAM (JUDGEMENT): uses the corpus's own address-naming convention — POIs named
    like "1 Wall Street" / "40 Wall Street" carry the street name as a suffix. A
    candidate must (a) carry a leading house number, not just a shared name suffix
    (DEFECT 3: an ``endswith`` match alone let 12 unrelated "...Club" POIs scattered
    across Manhattan manufacture a bogus ~38.6 degree "Club" axis — none of them is
    actually addressed on a street called "Club"), and (b) not be a ``LOW``
    ``geocode_confidence`` entry (DEFECT 2: an unsurveyed, web-search-derived point must
    not seed an axis). Requires >=2 surviving matches, at least ``AXIS_MIN_BASELINE_M``
    apart; a candidate whose surviving matches span more than ``MAX_AXIS_SPREAD_M`` is
    rejected outright as an implausible same-name-suffix coincidence rather than one
    real street (DEFECT 3). Returns ``None`` (UNKNOWN) whenever the corpus does not
    carry enough genuine addressed POIs on that street — no axis is invented.

    MEASURED coverage (2026-07-19, post-fix, this repo's shipped corpora, own-named
    street-like POIs — i.e. a POI whose OWN name ends in a street/avenue-type suffix):
    New York resolves 1/31 (only "Wall Street" — the pre-fix 2/13 included a bogus
    "Club" axis manufactured from 12 unrelated private clubs, now correctly rejected);
    Paris 0/1; London 0/8. Real coverage is genuinely poor — most named streets in
    these corpora have 0 or 1 addressed POI carrying a real house number, so most axis
    lookups are honestly UNKNOWN, never a false PLAUSIBLE/IMPLAUSIBLE. Separately
    measured: running the full check (extractor + this resolver) over every sentence
    in all 94 real generated tour transcripts in ``data/{paris,london}/tours/*.md``
    (9,642 sentences) produced ZERO axis-claim extractions at all — the conservative
    extractor's low recall means this check has not yet fired on any real shipped
    narration, for better (no false accusations shipped) and worse (no real-world
    coverage proof beyond the corpus-coordinate regression tests). See
    ``tests/test_spatial_check.py`` for the exact reproduction of the pre-fix "Club"
    false positive and its post-fix rejection.

    ``stop_lat``/``stop_lng`` (DEFECT 4, optional): when given, the pair of matches
    NEAREST the stop is preferred over the single furthest-apart pair — for a curving
    street this tracks the local axis at the stop rather than maximizing chord error
    against a distant, differently-angled segment. Omitted (both ``None``, e.g. direct
    unit-test callers with no stop in scope) falls back to the original furthest-apart
    selection for numerical stability.
    """
    needle = _normalize_name(street_name)
    if not needle:
        return None
    matches: list[tuple[float, float]] = []
    for poi in city_pois:
        name = poi.get("name", "")
        normalized = _normalize_name(name)
        if not normalized or normalized == needle:
            continue  # the street's own point is not an addressed building ON it
        if not normalized.endswith(needle):
            continue
        if not _ADDRESSED_HOUSE_NUMBER_RE.match(normalized):
            continue  # DEFECT 3: shares a name suffix but carries no house number
        if _geocode_confidence(poi) == "LOW":
            continue  # DEFECT 2: unsurveyed/low-confidence geocode — do not seed an axis
        lat, lng = poi.get("latitude"), poi.get("longitude")
        if lat is not None and lng is not None:
            matches.append((float(lat), float(lng)))
    if len(matches) < 2:
        return None

    valid_pairs: list[tuple[float, tuple[float, float], tuple[float, float]]] = []
    for i in range(len(matches)):
        for j in range(i + 1, len(matches)):
            d = haversine_m(*matches[i], *matches[j])
            if d >= AXIS_MIN_BASELINE_M:
                valid_pairs.append((d, matches[i], matches[j]))
    if not valid_pairs:
        return None

    # DEFECT 3: a genuine single street's addressed POIs cluster; POIs that only
    # coincidentally share a name suffix across unrelated locations do not.
    if max(d for d, _, _ in valid_pairs) > MAX_AXIS_SPREAD_M:
        return None

    if stop_lat is not None and stop_lng is not None:
        # DEFECT 4: prefer the LOCAL pair (both members close to the stop) over the
        # citywide-furthest pair — the average of both members' distance to the stop,
        # not just the single closest point, so a pair sharing one near point but
        # reaching far past the stop is not mistaken for "the local segment".
        def _dist_to_stop(
            pair: tuple[float, tuple[float, float], tuple[float, float]],
        ) -> float:
            _, p1, p2 = pair
            return (
                haversine_m(stop_lat, stop_lng, *p1) + haversine_m(stop_lat, stop_lng, *p2)
            ) / 2.0

        _, (lat1, lng1), (lat2, lng2) = min(valid_pairs, key=_dist_to_stop)
    else:
        # No stop in scope — fall back to the original furthest-apart-for-numerical-
        # stability selection.
        _, (lat1, lng1), (lat2, lng2) = max(valid_pairs, key=lambda t: t[0])

    return bearing_deg(lat1, lng1, lat2, lng2) % 180.0


@dataclass(frozen=True)
class SpatialCheckResult:
    verdict: Verdict
    reason: str
    bearing_to_target_deg: float | None = None
    axis_deg: float | None = None
    distance_m: float | None = None


def check_spatial_claim(
    claim: SpatialClaim, stop_lat: float, stop_lng: float, city_pois
) -> SpatialCheckResult:
    """Is ``claim`` geometrically plausible, standing at (stop_lat, stop_lng)?

    UNKNOWN whenever the target (or, for an axis claim, the axis) does not resolve
    from ``city_pois`` — never reported as a violation by the caller. See module
    docstring for the seam this sits behind (extraction is meaning-level; everything
    from here down is arithmetic on resolved coordinates).

    DEFECT 1 fix (2026-07-19): when the claim names a street/avenue to look "down",
    the distance bound (``MAX_PLAUSIBLE_POINT_DISTANCE_M``) plays NO role — a long,
    correct sightline down a real boulevard ("Look up Fifth Avenue toward the Empire
    State Building", ~2.2 km away and dead on-axis) is exactly what a good look-cue
    uses, not a defect. For an axis claim, only a CONFIRMED axis mismatch (or an
    axis that fails to resolve at all, UNKNOWN) can produce a verdict. The distance
    bound is reserved for the OTHER case: a bare "toward X" with no street/axis
    reference at all, where distance is the only thing there is to check.
    """
    target = resolve_poi_coords(city_pois, claim.target_name)
    if target is None:
        return SpatialCheckResult(
            Verdict.UNKNOWN,
            f"target {claim.target_name!r} not found in the corpus — cannot verify",
        )
    t_lat, t_lng = target
    distance_m = haversine_m(stop_lat, stop_lng, t_lat, t_lng)
    bearing = bearing_deg(stop_lat, stop_lng, t_lat, t_lng)

    if not claim.reference_name:
        # No axis to check at all — the walking-scale distance bound is the only
        # thing checkable for a bare "toward X" claim.
        if distance_m > MAX_PLAUSIBLE_POINT_DISTANCE_M:
            return SpatialCheckResult(
                Verdict.IMPLAUSIBLE,
                (
                    f"{claim.target_name} is {distance_m:.0f} m away (cap "
                    f"{MAX_PLAUSIBLE_POINT_DISTANCE_M:.0f} m) — too far for a walking-tour "
                    "look-cue regardless of stated direction"
                ),
                bearing_to_target_deg=bearing,
                distance_m=distance_m,
            )
        return SpatialCheckResult(
            Verdict.PLAUSIBLE,
            "no axis claim; within the distance bound",
            bearing_to_target_deg=bearing,
            distance_m=distance_m,
        )

    # An axis claim ("down/along/up <street> toward <target>") — DEFECT 1: distance
    # alone must never accuse here; only the axis comparison below can.
    if distance_m < MIN_STOP_TARGET_DISTANCE_M:
        # DEFECT 2: at point-blank range the stop->target bearing itself is unstable
        # (ordinary geocode noise dominates a few-metre baseline) — the 40-degree
        # axis tolerance would be judging a number that is not trustworthy.
        return SpatialCheckResult(
            Verdict.UNKNOWN,
            (
                f"target {claim.target_name!r} is only {distance_m:.0f} m from the stop "
                f"(floor {MIN_STOP_TARGET_DISTANCE_M:.0f} m) — bearing too unstable to "
                "judge against an axis"
            ),
            bearing_to_target_deg=bearing,
            distance_m=distance_m,
        )

    axis = resolve_street_axis_deg(
        city_pois, claim.reference_name, stop_lat=stop_lat, stop_lng=stop_lng
    )
    if axis is None:
        return SpatialCheckResult(
            Verdict.UNKNOWN,
            (
                f"axis of {claim.reference_name!r} not resolvable from the corpus "
                "(need >=2 genuinely addressed POIs on it) — cannot verify"
            ),
            bearing_to_target_deg=bearing,
            distance_m=distance_m,
        )
    deviation = _axis_deviation_deg(bearing, axis)
    if deviation > AXIS_TOLERANCE_DEG:
        return SpatialCheckResult(
            Verdict.IMPLAUSIBLE,
            (
                f"{claim.target_name} bears {bearing:.0f}° from the stop, "
                f"{deviation:.0f}° off {claim.reference_name}'s own axis "
                f"({axis:.0f}/{(axis + 180.0) % 360.0:.0f}°) — not "
                f"'down {claim.reference_name}'"
            ),
            bearing_to_target_deg=bearing,
            axis_deg=axis,
            distance_m=distance_m,
        )
    return SpatialCheckResult(
        Verdict.PLAUSIBLE,
        "within axis tolerance",
        bearing_to_target_deg=bearing,
        axis_deg=axis,
        distance_m=distance_m,
    )


# ── corpus loading — data/{city_slug}/poi-raw.json is the source of truth ──
# NOTE (honest limitation): the production Dockerfile ships src/ and frontend/ only,
# never data/ (see src/city_registry.py's own docstring) — so in the deployed prod
# container this loader finds nothing and every claim resolves UNKNOWN, which is the
# fail-safe direction (never a false accusation), not a crash. This check earns real
# coverage locally, in the workbench, and in tests, where data/ is present; it is not
# yet a live prod guarantee. Flagging this honestly rather than papering over it.

_REPO_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=8)
def _load_city_pois_cached(city_slug: str) -> tuple[dict, ...]:
    path = _REPO_ROOT / "data" / city_slug / "poi-raw.json"
    if not path.exists():
        return ()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return ()
    return tuple(data) if isinstance(data, list) else ()


@dataclass(frozen=True)
class SpatialFinding:
    """Mirrors quality_rubric.Finding's shape (not the same class — spatial_check
    stays import-independent of quality_rubric to avoid a circular import; the wiring
    in quality_rubric.py converts these into real ``Finding`` objects)."""

    check: str
    message: str
    stop_idx: int | None
    poi_name: str | None


def check_script_spatial_claims(
    script: Script,
    *,
    extractor: SpatialClaimExtractor | None = None,
    city_pois=None,
) -> list[SpatialFinding]:
    """Run the spatial check over every sentence in a composed ``Script``.

    Only IMPLAUSIBLE claims produce a finding — PLAUSIBLE and UNKNOWN are both
    silent, per the "silence beats a false accusation" rule. Nothing in the
    shipped gate calls this: ``quality_rubric.score_tour`` does NOT wire these in
    at any severity (see the module docstring). Findings surface only to a caller
    that asks for them directly, which today means the tests.

    ``city_pois`` is an injection seam for tests; production wiring omits it and
    loads ``data/{script.city_slug}/poi-raw.json`` via the cached loader.
    """
    extractor = extractor or ConservativeRegexExtractor()
    pois = city_pois if city_pois is not None else _load_city_pois_cached(script.city_slug)
    stop_lookup = {i: (p.lat, p.lng, p.name) for i, p in enumerate(script.selected_pois)}

    findings: list[SpatialFinding] = []
    for sentence in script.script:
        stop = stop_lookup.get(sentence.stop_idx)
        if stop is None:
            continue
        lat, lng, poi_name = stop
        for claim in extractor.extract(sentence.text):
            result = check_spatial_claim(claim, lat, lng, pois)
            if result.verdict is Verdict.IMPLAUSIBLE:
                findings.append(
                    SpatialFinding(
                        check="S1-unverified-direction",
                        message=f"{claim.sentence!r} — {result.reason}",
                        stop_idx=sentence.stop_idx,
                        poi_name=poi_name,
                    )
                )
    return findings
