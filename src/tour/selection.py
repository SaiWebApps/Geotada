"""POI selection — §3.2 of phase-1-design.

Two entry points:

- ``load_paris_corpus(driver, ...)`` — pulls a CorpusSnapshot of POIs +
  beat metadata from Neo4j. City-scoped per CLAUDE.md guardrails. The
  city_slug used at the call site is mandatory; this is the only
  Neo4j-aware function in tour/. All POIs/Beats arrive frozen.
- ``select_route(input, snapshot)`` — pure function. Computes the route
  envelope, picks the spine area, scores each POI, and runs a
  routing-aware greedy until budget is exhausted (§3.2 cap = 12 outer
  anchors per Q5 clarification). Returns a Route.

The Cypher query is the only place where Neo4j-specific assumptions
live. Keep it deliberate and well-commented.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .contract import POI, BeatRef, PhysicalCue, Route, TourabilityAssessment, TourInput
from .density import TourabilityRefused, assess as assess_tourability
from .routing import (
    HAVERSINE_CORRECTION,
    PACE_KMH,
    compute_dwell_seconds,
    envelope_radius_m,
    haversine_m,
    insertion_cost_seconds,
    pace_corrected_walk_seconds,
    summarise_route,
    target_audio_seconds,
    walk_budget_seconds,
)

# §3.2 score weights / caps. Calibrated against golden tests on 2026-04-29.
INTEREST_BIAS_MAX: float = 2.0
INTEREST_BIAS_BASE: float = 1.0
INTEREST_BIAS_SCALE: float = 0.5

AREA_ALIGNMENT_SPINE: float = 1.0
AREA_ALIGNMENT_ADJACENT: float = 0.5
AREA_ALIGNMENT_OTHER: float = 0.2

POI_ROLE_MULTIPLIER: dict[str, float] = {
    "stop": 1.0,
    "setting": 0.7,
    "walk_by_only": 0.0,
}

ANCHOR_TIERS: frozenset[int] = frozenset({3, 4, 5})

# §5 Q5 (Phase 2 calibration, 2026-04-27):
#   max_anchors = max(1, duration_min // ANCHOR_CAP_DIVISOR)
#   bounded above by HARD_ANCHOR_CAP. Calibrated against the empirical Île
#   walk (90 min → 9 anchors).
ANCHOR_CAP_DIVISOR: int = 10
HARD_ANCHOR_CAP: int = 12  # outer anchors only — internal vignettes don't count

# Spine selection: pick the most-populated non-city Area within this many
# metres of the start point, weighted by tier among the candidate POIs.
SPINE_RADIUS_M: float = 800.0

# Areas that are city-scope (excluded from spine choice) or de-prioritised.
EXCLUDED_AREA_TYPES: frozenset[str] = frozenset({"city"})

# Phase 2.6 calibration: a neighborhood/island/corridor Area beats a
# district Area unless the district has at least SPINE_DISTRICT_DOMINANCE
# times the (tier-weighted) vote count of the smaller Area. This makes
# "Île de la Cité" the spine for a Pont Neuf start instead of "1st
# Arrondissement", because districts naturally accumulate more votes
# (every district contains everything inside it). The 5%-tolerance rule
# from Phase 2.5 was too weak to overcome that vote bias.
SPINE_DISTRICT_DOMINANCE: float = 2.0
SPECIFIC_AREA_TYPES: frozenset[str] = frozenset({"neighborhood", "island", "corridor"})
DISTRICT_AREA_TYPES: frozenset[str] = frozenset({"district"})
SPINE_AREA_TYPE_PRIORITY: tuple[str, ...] = (
    "neighborhood",
    "island",
    "corridor",
    "district",
    "city",
)

# Phase 7.5 (Fix 3, 2026-04-29) — same-physical-location POI demotion.
# After the greedy + endpoint-pull + fill pass, two selected POIs sometimes
# sit at the same address (e.g. Musée Victor Hugo at 6 PdV vs Place des
# Vosges no. 6). The user walks past the same building twice as separate
# stops. Demote the smaller-tier of any such pair into the larger; merge
# its beats into the host POI's pool so content isn't lost.
#
# Threshold is the v3 schema geofence radius (100 m) — the same distance
# the runtime uses to decide two coordinates point at "the same physical
# place". The Phase 7.5 spec called for 15 m, but live Paris corpus
# coordinates show PdV (centroid 48.8555,2.3656) sits ~85 m from
# Musée Victor Hugo's pin (48.8548,2.3661); a 15 m gate would never
# catch the headline case the spec was written to fix. The name-token
# overlap signal (`_has_cross_poi_address_overlap`) remains the
# semantic guard — adjacent-but-unrelated POIs (e.g. ND vs Crypte
# Archéologique) don't carry beats referencing each other's distinctive
# tokens, so they don't trigger demotion.
DEMOTION_PROXIMITY_M: float = 100.0

# Demotion is restricted to anchor-tier (≥4) POIs. The empirical Île
# walk treats Square du Vert-Galant (tier 3, ~80 m from Pont Neuf) as
# its own pause stop; merging tier-3 pauses into nearby tier-5 anchors
# would drop deliberate Pariswalks-style stops. Pavillon du Roi /
# Hôtel de Coulanges-style cases cited by the spec are all anchor-tier
# POIs, so this guard preserves the headline behaviour while
# protecting empirical pause-stop semantics.
DEMOTION_MIN_TIER: int = 4
# Common topographic / generic prefix tokens that don't make a POI
# distinctive when grepping addresses for cross-POI overlap. "Musee
# Victor Hugo" → distinctive token "hugo" (not "musee" / "victor"
# alone — Victor is a personal name, but the tokens we care about are
# the unambiguously POI-specific ones).
_NAME_GENERIC_TOKENS: frozenset[str] = frozenset(
    {
        "the", "of", "and", "or",
        "de", "des", "du", "le", "la", "les", "et",
        "place", "rue", "boulevard", "avenue", "quai", "pont", "musee", "musée",
        "hotel", "hôtel", "cathedral", "cathedrale", "cathédrale", "church",
        "saint", "sainte", "st", "ste",
        "square", "garden", "jardin", "park", "parc", "tower", "tour",
        "victor",  # ambiguous given name; a tour with two "Victor X" POIs in it should already be co-located before this fires
    }
)
_NAME_TOKEN_MIN_LEN: int = 4


# Phase 7 (2026-04-29) fill pass — target_audio is a floor, not a soft stop.
# After the main greedy + endpoint-pull, if delivered audio is still well
# below target, run a relaxed-cost-efficiency second pass that adds
# anchors until the audio floor is met or walk budget is nearly spent.
# Concorde 180-min one-way Phase 6 case: 5 anchors selected, 25-min audio
# proxy, 89-min target, 41/60-min walk used. Greedy stalls because
# `score / extra_cost` no longer favours additions. Phase 7 fill pass
# adds higher-walk-cost candidates because being below the audio floor
# matters more than route efficiency at that point.
FILL_PASS_AUDIO_FLOOR_FRAC: float = 0.8
FILL_PASS_WALK_BUDGET_FRAC: float = 0.95


# Endpoint-pull (Q1, one-way only): after greedy completes, force-include
# the highest-scoring un-selected POI in the far half of the reachable
# envelope as the final stop. The "far half" is anything beyond this
# fraction of max_radius from start.
ENDPOINT_PULL_FAR_FRACTION: float = 0.5
# Try the top-K far candidates by score; accept the first that fits
# walk-budget + anchor-cap with ≤ ENDPOINT_PULL_MAX_DROPS drops. Without
# this, a single highest-score candidate that busts budget would silently
# abandon the pull even when the next-best far candidate would fit.
ENDPOINT_PULL_CANDIDATE_TOP_K: int = 5
# Greedy reserves this fraction of the walk budget for endpoint-pull on
# one-way routes. Without reservation the greedy can use 98% of the
# budget on tight neighborhood clusters, leaving no room for a
# far-envelope closing stop and silently abandoning the pull.
ENDPOINT_PULL_RESERVED_BUDGET_FRACTION: float = 0.25


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusSnapshot:
    """All inputs `select_route` needs in pure-function form."""

    pois: tuple[POI, ...]
    beats_by_poi: dict[str, tuple[BeatRef, ...]]
    area_types: dict[str, str]  # area_name → area_type (district/neighborhood/...)
    adjacent_areas: dict[str, frozenset[str]]  # area_name → directly-adjacent area names

    def beats_for(self, poi_id: str) -> tuple[BeatRef, ...]:
        return self.beats_by_poi.get(poi_id, ())


# ---------------------------------------------------------------------------
# Neo4j loader
# ---------------------------------------------------------------------------


# Cypher pulls every active beat for every city POI in one shot. POIs
# carry their Area memberships as a list; beats carry only what selection
# and ordering need.
LOAD_PARIS_POIS_CYPHER = """
MATCH (p:POI {city_name: $city_slug})
OPTIONAL MATCH (p)-[:WITHIN]->(a:Area)
WITH p, collect(DISTINCT a.name) AS area_names
WHERE p.location IS NOT NULL
RETURN
  p.id            AS id,
  p.name          AS name,
  p.importance_tier AS tier,
  p.poi_role      AS poi_role,
  p.location.y    AS lat,
  p.location.x    AS lng,
  area_names      AS areas
"""

LOAD_PARIS_BEATS_CYPHER = """
MATCH (p:POI {city_name: $city_slug})-[:HAS_BEAT]->(b:NarrativeBeat)
WHERE b.active_status = 'active'
OPTIONAL MATCH (b)-[:TAGGED_WITH]->(l:Lens)
WITH p, b, collect(DISTINCT l.name) AS lens_names
RETURN
  b.id                  AS id,
  p.id                  AS poi_id,
  b.sub_location        AS sub_location,
  b.trigger_address     AS trigger_address,
  b.narrative_function  AS narrative_function,
  b.beat_type           AS beat_type,
  b.emotional_register  AS emotional_register,
  b.beat_length_class   AS beat_length_class,
  b.est_spoken_seconds  AS est_spoken_seconds,
  b.script_body         AS script_body,
  b.entities            AS entities,
  b.subject_tag         AS subject_tag,
  b.active_status       AS active_status,
  b.physical_cues       AS physical_cues,
  b.pronunciation       AS pronunciation,
  lens_names            AS lenses
"""

LOAD_AREA_TYPES_CYPHER = """
MATCH (a:Area)
RETURN a.name AS name, a.area_type AS area_type, a.city_name AS city_name
"""

# Two areas are "adjacent" when at least one POI is in both.
LOAD_AREA_ADJACENCY_CYPHER = """
MATCH (p:POI {city_name: $city_slug})-[:WITHIN]->(a:Area)
WITH p, collect(DISTINCT a.name) AS area_names
UNWIND area_names AS a1
UNWIND area_names AS a2
WITH a1, a2 WHERE a1 < a2
RETURN a1, a2, count(*) AS shared_pois
"""


def load_paris_corpus(driver, *, city_slug: str = "paris") -> CorpusSnapshot:
    """Pull a CorpusSnapshot for one city from Neo4j."""
    with driver.session() as session:
        poi_records = session.run(LOAD_PARIS_POIS_CYPHER, city_slug=city_slug).data()
        beat_records = session.run(LOAD_PARIS_BEATS_CYPHER, city_slug=city_slug).data()
        area_records = session.run(LOAD_AREA_TYPES_CYPHER).data()
        adj_records = session.run(LOAD_AREA_ADJACENCY_CYPHER, city_slug=city_slug).data()

    return _snapshot_from_records(poi_records, beat_records, area_records, adj_records)


def _snapshot_from_records(
    poi_records: list[dict],
    beat_records: list[dict],
    area_records: list[dict],
    adj_records: list[dict],
) -> CorpusSnapshot:
    pois: list[POI] = []
    beats_by_poi_acc: dict[str, list[BeatRef]] = {}

    for r in beat_records:
        body = r.get("script_body")
        ref = BeatRef(
            id=r["id"],
            poi_id=r["poi_id"],
            sub_location=_clean(r.get("sub_location")),
            trigger_address=_clean(r.get("trigger_address")),
            narrative_function=_clean(r.get("narrative_function")),
            beat_type=_clean(r.get("beat_type")),
            emotional_register=_clean(r.get("emotional_register")),
            beat_length_class=_clean(r.get("beat_length_class")),
            est_spoken_seconds=int(r.get("est_spoken_seconds") or 0),
            word_count=_count_words(body),
            entities=tuple(r.get("entities") or ()),
            subject_tag=_clean(r.get("subject_tag")),
            lenses=tuple(s for s in (r.get("lenses") or ()) if s),
            active_status=r.get("active_status") or "active",
            script_body=body if isinstance(body, str) and body.strip() else None,
            physical_cues=_decode_physical_cues(r.get("physical_cues")),
            pronunciation=_clean(r.get("pronunciation")),
        )
        beats_by_poi_acc.setdefault(ref.poi_id, []).append(ref)

    for r in poi_records:
        pid = r["id"]
        beats = beats_by_poi_acc.get(pid, [])
        beat_count = len(beats)
        # matching_lens_beat_count is computed lazily per-input, since the
        # interest set is request-scoped. Default to 0 here.
        pois.append(
            POI(
                id=pid,
                name=r["name"],
                tier=int(r.get("tier") or 1),
                poi_role=r.get("poi_role") or "stop",
                lat=float(r["lat"]),
                lng=float(r["lng"]),
                areas=tuple(a for a in (r.get("areas") or ()) if a),
                beat_count=beat_count,
                matching_lens_beat_count=0,
            )
        )

    area_types = {r["name"]: (r.get("area_type") or "") for r in area_records}

    adjacency: dict[str, set[str]] = {}
    for r in adj_records:
        a1 = r["a1"]
        a2 = r["a2"]
        if not a1 or not a2:
            continue
        adjacency.setdefault(a1, set()).add(a2)
        adjacency.setdefault(a2, set()).add(a1)
    adjacent_areas = {k: frozenset(v) for k, v in adjacency.items()}

    return CorpusSnapshot(
        pois=tuple(pois),
        beats_by_poi={k: tuple(v) for k, v in beats_by_poi_acc.items()},
        area_types=area_types,
        adjacent_areas=adjacent_areas,
    )


def _clean(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    return v


def _count_words(s) -> int:
    if not isinstance(s, str):
        return 0
    return sum(1 for token in s.split() if token)


def _decode_physical_cues(raw) -> tuple[PhysicalCue, ...]:
    """Decode the JSON-encoded physical_cues string back to PhysicalCue tuple.

    Neo4j stores list[dict] as JSON-encoded strings (see
    src/api/crud/nodes.py::_encode_complex_props). This loader reads the
    raw value back into structured tuples so beat_select / generation
    can reason about cues without re-querying.

    Tolerates legacy list[str] beats (Vallois pre-migration shape) by
    wrapping bare strings in a default cue dict.
    """
    if raw is None:
        return ()
    if isinstance(raw, str):
        if not raw.strip():
            return ()
        try:
            decoded = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return ()
    else:
        decoded = raw
    if not isinstance(decoded, list):
        return ()
    cues: list[PhysicalCue] = []
    for item in decoded:
        if isinstance(item, dict):
            cue_text = item.get("cue") or ""
            if not cue_text:
                continue
            cues.append(
                PhysicalCue(
                    cue=cue_text,
                    direction=item.get("direction"),
                    feature_type=item.get("feature_type"),
                )
            )
        elif isinstance(item, str) and item.strip():
            cues.append(PhysicalCue(cue=item.strip()))
    return tuple(cues)


# ---------------------------------------------------------------------------
# Selection (pure)
# ---------------------------------------------------------------------------


def select_route(input: TourInput, snapshot: CorpusSnapshot) -> Route:
    """Compute the spine, score POIs, run greedy selection. Returns a Route.

    Phase 6 added two guards before the greedy:

    1. **Density gate** (§3.7) — call ``density.assess(input)``. RED
       raises ``TourabilityRefused``; YELLOW attaches the assessment to
       ``Route.tourability`` for the harness to surface.
    2. **Zero-beat-POI exclusion** — POIs with no active beats are
       removed from the candidate pool before scoring. This was the
       Phase 5 Petit Palais bug: a tier-4 POI with 0 beats was selected
       as an anchor purely because it sat on the route corridor.
    """
    start_lat, start_lng = input.start
    interest = frozenset((input.lenses or []))

    # Phase 6 density gate. RED → refuse; YELLOW → continue but
    # attach the assessment so the harness can warn.
    assessment = assess_tourability(input, snapshot.pois, snapshot.beats_by_poi)
    if assessment.status == "RED":
        raise TourabilityRefused(assessment)

    # Step 1: envelope filter. Phase 6 also drops 0-active-beat POIs.
    radius_m = envelope_radius_m(input.duration_min, round_trip=input.round_trip)
    candidates: list[POI] = []
    for poi in snapshot.pois:
        if poi.poi_role == "walk_by_only":
            continue  # walk-bys are handled separately (Phase 3 enrichment)
        if poi.tier not in ANCHOR_TIERS:
            continue
        if haversine_m(start_lat, start_lng, poi.lat, poi.lng) > radius_m:
            continue
        if not _has_active_beats(poi, snapshot):
            continue  # Phase 6: zero-beat POIs are excluded as anchors.
        candidates.append(_with_interest_count(poi, snapshot, interest))

    if not candidates:
        empty = summarise_route(
            (),
            start_lat=start_lat,
            start_lng=start_lng,
            round_trip=input.round_trip,
            duration_min=input.duration_min,
            spine_area=None,
        )
        return _attach_tourability_if_yellow(empty, assessment)

    # Step 2: spine.
    spine = pick_spine_area(start_lat, start_lng, candidates, snapshot)

    # Step 3: greedy with insertion cost.
    walk_budget = walk_budget_seconds(input.duration_min)
    audio_budget = target_audio_seconds(input.duration_min)
    max_anchors = min(HARD_ANCHOR_CAP, max(1, input.duration_min // ANCHOR_CAP_DIVISOR))

    # Reserve some walk budget for the endpoint-pull post-step on one-way
    # routes — otherwise the greedy fills 98% of the budget on tight
    # clusters and silently abandons the pull.
    if input.round_trip:
        greedy_walk_budget = walk_budget
    else:
        greedy_walk_budget = int(walk_budget * (1.0 - ENDPOINT_PULL_RESERVED_BUDGET_FRACTION))

    selected: list[POI] = []
    consumed_walk = 0
    consumed_audio = 0

    remaining = list(candidates)

    while remaining and len(selected) < max_anchors:
        best_candidate: POI | None = None
        best_extra: int = 0
        best_idx: int = 0
        best_value: float = -math.inf

        for cand in remaining:
            extra, idx = insertion_cost_seconds(
                cand,
                selected,
                start_lat=start_lat,
                start_lng=start_lng,
                round_trip=input.round_trip,
            )
            if consumed_walk + extra > greedy_walk_budget:
                continue
            base = poi_score(cand, spine, interest, snapshot)
            # +1s smoothing prevents division-by-zero on co-located POIs.
            # Phase 7.5: clamp the denominator floor at 1.0 — integer
            # rounding inside ``insertion_cost_seconds`` can yield extra=-1
            # when a candidate sits between two waypoints, which the bare
            # ``extra + 1.0`` would resolve to a divide-by-zero.
            value = base / max(1.0, extra + 1.0)
            if value > best_value:
                best_value = value
                best_candidate = cand
                best_extra = extra
                best_idx = idx

        if best_candidate is None:
            break

        # Insert at the best position.
        selected.insert(best_idx, best_candidate)
        consumed_walk += best_extra
        consumed_audio += compute_dwell_seconds(best_candidate.tier)
        remaining.remove(best_candidate)

        if consumed_audio >= audio_budget:
            break

    # Step 4: endpoint-pull (one-way only). Force-include a far-envelope POI
    # as the closing anchor so traverses (e.g. Pont Neuf → Île east tip)
    # don't truncate near the start. Re-orders the route end-to-end via
    # insertion-cost optimisation; respects HARD_ANCHOR_CAP and walk budget.
    if not input.round_trip and selected:
        far_radius_min = radius_m * ENDPOINT_PULL_FAR_FRACTION
        already = {p.id for p in selected}
        far_candidates = [
            c
            for c in candidates
            if c.id not in already
            and haversine_m(start_lat, start_lng, c.lat, c.lng) >= far_radius_min
        ]
        if far_candidates:
            ranked_far = sorted(
                far_candidates,
                key=lambda c: (-poi_score(c, spine, interest, snapshot), c.id),
            )[:ENDPOINT_PULL_CANDIDATE_TOP_K]
            for cand in ranked_far:
                pulled = _apply_endpoint_pull(
                    selected,
                    cand,
                    spine=spine,
                    interest=interest,
                    snapshot=snapshot,
                    start_lat=start_lat,
                    start_lng=start_lng,
                    walk_budget=walk_budget,
                    hard_anchor_cap=HARD_ANCHOR_CAP,
                )
                if pulled is not selected and pulled[-1].id == cand.id:
                    selected = pulled
                    break

    # Phase 7 fill pass — target_audio is a floor. Greedy +
    # endpoint-pull may emit a route well below the audio target when
    # cost-efficient additions run out. Add anchors with a relaxed
    # cost-efficiency threshold until target is met or walk budget is
    # nearly spent. See FILL_PASS_* constants for thresholds.
    selected = _apply_fill_pass(
        selected,
        candidates,
        spine=spine,
        interest=interest,
        snapshot=snapshot,
        start_lat=start_lat,
        start_lng=start_lng,
        round_trip=input.round_trip,
        walk_budget=walk_budget,
        audio_budget=audio_budget,
        hard_anchor_cap=HARD_ANCHOR_CAP,
    )

    # Phase 7.5 Fix 3: detect co-located POI pairs in the final selection
    # and demote the smaller-tier of each pair. Demoted POI beats are
    # merged into the host's pool by the harness via Route.demoted_beats.
    selected, demoted_beats = apply_co_located_demotion(selected, snapshot)

    route = summarise_route(
        selected,
        start_lat=start_lat,
        start_lng=start_lng,
        round_trip=input.round_trip,
        duration_min=input.duration_min,
        spine_area=spine,
    )
    if demoted_beats:
        route = route.model_copy(update={"demoted_beats": demoted_beats})
    return _attach_tourability_if_yellow(route, assessment)


def apply_co_located_demotion(
    selected: list[POI],
    snapshot: CorpusSnapshot,
) -> tuple[list[POI], dict[str, tuple[BeatRef, ...]]]:
    """Return (selected_minus_demoted, host_id → demoted_beats).

    A pair (A, B) of selected POIs qualifies for demotion when
    ``haversine(A, B) ≤ DEMOTION_PROXIMITY_M`` AND at least one beat at
    one POI carries a ``trigger_address`` or ``sub_location`` mentioning
    a distinctive token of the other POI's name. Smaller tier loses;
    on a tie, fewer beats loses; final tie-break is alphabetical id so
    the outcome is deterministic.

    The Tour 1 case: Musée Victor Hugo (tier 4) sits at the same
    physical address as Place des Vosges no. 6 (tier 5). PdV carries a
    beat with sub_location ``hugo-museum-no-6`` whose tokens overlap
    Hugo museum's distinctive ``hugo`` token. Hugo museum demotes;
    its 2 beats merge into PdV's pool.

    No-op when the route is empty or no pair qualifies.
    """
    if len(selected) < 2:
        return list(selected), {}

    demoted_to_host: dict[str, str] = {}
    for i in range(len(selected)):
        a = selected[i]
        if a.id in demoted_to_host:
            continue
        for j in range(i + 1, len(selected)):
            b = selected[j]
            if b.id in demoted_to_host or a.id in demoted_to_host:
                continue
            # Both POIs must be anchor-tier; pause-tier (≤3) POIs are
            # deliberate empirical-walk stops and must not collapse.
            if a.tier < DEMOTION_MIN_TIER or b.tier < DEMOTION_MIN_TIER:
                continue
            distance = haversine_m(a.lat, a.lng, b.lat, b.lng)
            if distance > DEMOTION_PROXIMITY_M:
                continue
            if not _has_cross_poi_address_overlap(a, b, snapshot):
                continue
            host, demote = _pick_demotion_host(a, b)
            demoted_to_host[demote.id] = host.id

    if not demoted_to_host:
        return list(selected), {}

    new_selected = [p for p in selected if p.id not in demoted_to_host]
    demoted_beats: dict[str, tuple[BeatRef, ...]] = {}
    for demoted_id, host_id in demoted_to_host.items():
        beats = snapshot.beats_for(demoted_id)
        merged = demoted_beats.get(host_id, ()) + tuple(beats)
        demoted_beats[host_id] = merged
    return new_selected, demoted_beats


def _pick_demotion_host(a: POI, b: POI) -> tuple[POI, POI]:
    """Return (host, demoted) given a co-located pair.

    Larger tier hosts; on tie, more-beats hosts; final tie-break is
    alphabetical id (low → host) so the choice is deterministic.
    """
    if a.tier != b.tier:
        return (a, b) if a.tier > b.tier else (b, a)
    if a.beat_count != b.beat_count:
        return (a, b) if a.beat_count > b.beat_count else (b, a)
    return (a, b) if a.id < b.id else (b, a)


def _has_cross_poi_address_overlap(
    a: POI, b: POI, snapshot: CorpusSnapshot
) -> bool:
    """True iff a beat at one POI mentions a distinctive token of the other.

    Looks at ``trigger_address`` and ``sub_location`` (case-insensitive
    substring) on every beat at A and B. Distinctive tokens are name
    fragments ≥ 4 chars that aren't generic topographic prefixes
    ("place", "rue", "musee" etc.) — see ``_NAME_GENERIC_TOKENS``.
    """
    a_tokens = _distinctive_name_tokens(a.name)
    b_tokens = _distinctive_name_tokens(b.name)
    if not a_tokens and not b_tokens:
        return False

    def _beat_address_text(beat: BeatRef) -> str:
        return f"{beat.trigger_address or ''} {beat.sub_location or ''}".lower()

    for beat in snapshot.beats_for(a.id):
        text = _beat_address_text(beat)
        if any(tok in text for tok in b_tokens):
            return True
    for beat in snapshot.beats_for(b.id):
        text = _beat_address_text(beat)
        if any(tok in text for tok in a_tokens):
            return True
    return False


def _distinctive_name_tokens(name: str) -> set[str]:
    """Lowercase name tokens ≥ 4 chars excluding generic topographic words."""
    if not name:
        return set()
    tokens = re.findall(r"[a-zà-öø-ÿ]+", name.lower())
    return {
        t for t in tokens
        if len(t) >= _NAME_TOKEN_MIN_LEN and t not in _NAME_GENERIC_TOKENS
    }


def _apply_fill_pass(
    selected: list[POI],
    candidates: list[POI],
    *,
    spine: str | None,
    interest: frozenset[str],
    snapshot: CorpusSnapshot,
    start_lat: float,
    start_lng: float,
    round_trip: bool,
    walk_budget: int,
    audio_budget: int,
    hard_anchor_cap: int,
) -> list[POI]:
    """Phase 7: fill until audio floor is met or walk budget hits 95%.

    Score-first ranking (not score / cost) so we keep adding genuinely
    rich anchors at the price of a higher walk cost. Stops when:
      - delivered audio (sum of dwell-seconds proxy) ≥ ``FILL_PASS_AUDIO_FLOOR_FRAC × audio_budget``;
      - cumulative walk would exceed ``FILL_PASS_WALK_BUDGET_FRAC × walk_budget``;
      - route hits ``hard_anchor_cap``;
      - no remaining candidate fits.

    Insertions go through ``insertion_cost_seconds`` so the route stays
    geometrically sane. The post-endpoint-pull last-anchor (one-way
    routes) is preserved by clamping insertion idx to interior positions
    when the route already has ≥2 stops on a one-way path.
    """
    if not selected or not candidates:
        return selected

    floor_audio = audio_budget * FILL_PASS_AUDIO_FLOOR_FRAC
    walk_cap = int(walk_budget * FILL_PASS_WALK_BUDGET_FRAC)

    consumed_audio = sum(compute_dwell_seconds(p.tier) for p in selected)
    if consumed_audio >= floor_audio:
        return selected  # already met; no fill needed

    consumed_walk = _full_route_walk_seconds(
        selected, start_lat=start_lat, start_lng=start_lng, round_trip=round_trip
    )
    if consumed_walk >= walk_cap:
        return selected  # walk already saturated; no slack to fill

    selected_ids = {p.id for p in selected}
    pool = [c for c in candidates if c.id not in selected_ids]
    pool.sort(key=lambda c: (-poi_score(c, spine, interest, snapshot), c.id))

    # On a one-way path with ≥2 stops, treat the last anchor as the
    # endpoint (placed by endpoint-pull) and never insert after it.
    preserve_endpoint = (not round_trip) and len(selected) >= 2

    for cand in pool:
        if len(selected) >= hard_anchor_cap:
            break
        if consumed_audio >= floor_audio:
            break
        extra, idx = insertion_cost_seconds(
            cand,
            selected,
            start_lat=start_lat,
            start_lng=start_lng,
            round_trip=round_trip,
        )
        if preserve_endpoint and idx >= len(selected):
            # Best position was after the endpoint; clamp to just before it
            # and recompute extra for that constrained position.
            idx = len(selected) - 1
            extra = _insertion_extra_at_index(
                cand,
                selected,
                idx,
                start_lat=start_lat,
                start_lng=start_lng,
                round_trip=round_trip,
            )
        if consumed_walk + extra > walk_cap:
            continue
        selected = selected[:idx] + [cand] + selected[idx:]
        consumed_walk += extra
        consumed_audio += compute_dwell_seconds(cand.tier)

    return selected


def _insertion_extra_at_index(
    cand: POI,
    selected: list[POI],
    idx: int,
    *,
    start_lat: float,
    start_lng: float,
    round_trip: bool,
) -> int:
    """Walk-time delta from inserting `cand` at exactly position `idx`."""
    base_coords: list[tuple[float, float]] = [(start_lat, start_lng), *((p.lat, p.lng) for p in selected)]
    if round_trip:
        base_coords.append((start_lat, start_lng))
    base = 0
    for (lat1, lng1), (lat2, lng2) in zip(base_coords, base_coords[1:]):
        base += pace_corrected_walk_seconds(haversine_m(lat1, lng1, lat2, lng2))
    new_pois = selected[:idx] + [cand] + selected[idx:]
    new_coords: list[tuple[float, float]] = [(start_lat, start_lng), *((p.lat, p.lng) for p in new_pois)]
    if round_trip:
        new_coords.append((start_lat, start_lng))
    new_total = 0
    for (lat1, lng1), (lat2, lng2) in zip(new_coords, new_coords[1:]):
        new_total += pace_corrected_walk_seconds(haversine_m(lat1, lng1, lat2, lng2))
    return new_total - base


def _full_route_walk_seconds(
    pois: list[POI], *, start_lat: float, start_lng: float, round_trip: bool
) -> int:
    coords: list[tuple[float, float]] = [(start_lat, start_lng)]
    coords.extend((p.lat, p.lng) for p in pois)
    if round_trip:
        coords.append((start_lat, start_lng))
    total = 0
    for (lat1, lng1), (lat2, lng2) in zip(coords, coords[1:]):
        total += pace_corrected_walk_seconds(haversine_m(lat1, lng1, lat2, lng2))
    return total


# Endpoint-pull will drop at most this many incumbents to make room for
# the far-envelope endpoint. Larger values can collapse the route to one
# anchor (the endpoint alone); two preserves the spine-anchor cluster
# while still letting one weak incumbent give way for an east-tip pick.
ENDPOINT_PULL_MAX_DROPS: int = 2


def _apply_endpoint_pull(
    selected: list[POI],
    endpoint: POI,
    *,
    spine: str | None,
    interest: frozenset[str],
    snapshot: CorpusSnapshot,
    start_lat: float,
    start_lng: float,
    walk_budget: int,
    hard_anchor_cap: int,
) -> list[POI]:
    """Insert `endpoint` as the closing stop, dropping at most
    ENDPOINT_PULL_MAX_DROPS weak incumbents to fit walk-budget +
    anchor-cap. If the endpoint can't be made to fit within those drops,
    return the input unchanged (greedy result wins).
    """
    incumbents = list(selected)
    drops_used = 0
    while True:
        if len(incumbents) + 1 > hard_anchor_cap and incumbents and drops_used < ENDPOINT_PULL_MAX_DROPS:
            incumbents = _drop_weakest(incumbents, spine, interest, snapshot)
            drops_used += 1
            continue

        if len(incumbents) + 1 > hard_anchor_cap:
            return list(selected)  # endpoint won't fit under cap with allowed drops

        candidate_route = _reorder_with_endpoint(
            incumbents, endpoint, start_lat=start_lat, start_lng=start_lng
        )
        walk = _route_walk_seconds(
            candidate_route, start_lat=start_lat, start_lng=start_lng
        )
        if walk <= walk_budget:
            return candidate_route
        if not incumbents or drops_used >= ENDPOINT_PULL_MAX_DROPS:
            return list(selected)  # bounded drops exhausted; abandon pull
        incumbents = _drop_weakest(incumbents, spine, interest, snapshot)
        drops_used += 1


def _drop_weakest(
    pois: list[POI],
    spine: str | None,
    interest: frozenset[str],
    snapshot: CorpusSnapshot,
) -> list[POI]:
    weakest = min(pois, key=lambda p: (poi_score(p, spine, interest, snapshot), p.id))
    return [p for p in pois if p.id != weakest.id]


def _route_walk_seconds(
    pois: list[POI], *, start_lat: float, start_lng: float
) -> int:
    coords = [(start_lat, start_lng), *((p.lat, p.lng) for p in pois)]
    total = 0
    from .routing import pace_corrected_walk_seconds

    for (lat1, lng1), (lat2, lng2) in zip(coords, coords[1:]):
        total += pace_corrected_walk_seconds(haversine_m(lat1, lng1, lat2, lng2))
    return total


def _reorder_with_endpoint(
    selected: list[POI],
    endpoint: POI,
    *,
    start_lat: float,
    start_lng: float,
) -> list[POI]:
    """Place `endpoint` last and order the remainder via best-insertion."""
    interior: list[POI] = []
    pool = list(selected)
    while pool:
        best: POI | None = None
        best_extra: int = 0
        best_idx: int = 0
        for cand in pool:
            extra, idx = insertion_cost_seconds(
                cand,
                interior + [endpoint],
                start_lat=start_lat,
                start_lng=start_lng,
                round_trip=False,
            )
            if best is None or extra < best_extra:
                best = cand
                best_extra = extra
                best_idx = idx
        assert best is not None
        # Never insert *after* the endpoint. interior + [endpoint] has
        # len(interior) + 1 slots; idx == len(interior) means "before
        # endpoint", which is fine. idx > len(interior) is impossible
        # because insertion_cost_seconds bounds idx by len of `ordered`.
        if best_idx > len(interior):
            best_idx = len(interior)
        interior.insert(best_idx, best)
        pool.remove(best)
    return interior + [endpoint]


# ---------------------------------------------------------------------------
# Spine selection
# ---------------------------------------------------------------------------


def pick_spine_area(
    start_lat: float,
    start_lng: float,
    candidates: Iterable[POI],
    snapshot: CorpusSnapshot,
) -> str | None:
    """Most-populous non-city Area among POIs within SPINE_RADIUS_M.

    Tier-weighted: each candidate POI casts `tier` votes for each of its
    Areas. **Phase 2.6 rule:** if the top-scoring Area is a district,
    promote a competing neighborhood/island/corridor whose votes are at
    least `(top / SPINE_DISTRICT_DOMINANCE)` — i.e., the district must be
    ≥2× the more-specific area to keep the spine. Districts naturally
    accumulate more votes (every district contains everything inside
    it), so without this lift districts always win and the algorithm
    can never pick "Île de la Cité" near Pont Neuf.

    Among multiple specific Areas the highest score wins; among true
    score ties, fall back to SPINE_AREA_TYPE_PRIORITY then alphabetical.

    Falls back to the closest candidate's most-specific non-city Area
    when no POIs are within SPINE_RADIUS_M.
    """
    nearby: list[POI] = []
    for poi in candidates:
        if haversine_m(start_lat, start_lng, poi.lat, poi.lng) <= SPINE_RADIUS_M:
            nearby.append(poi)

    if not nearby:
        sorted_by_dist = sorted(
            candidates,
            key=lambda p: haversine_m(start_lat, start_lng, p.lat, p.lng),
        )
        for poi in sorted_by_dist:
            ranked = _rank_areas_by_specificity(poi.areas, snapshot)
            if ranked:
                return ranked[0]
        return None

    votes: Counter[str] = Counter()
    for poi in nearby:
        for area in poi.areas:
            if _is_excluded(area, snapshot):
                continue
            votes[area] += poi.tier

    if not votes:
        return None

    leader = max(votes, key=lambda a: (votes[a], -_type_rank(a, snapshot), a))
    leader_type = snapshot.area_types.get(leader, "")

    # If the leader is a district, see whether a more-specific Area is
    # close enough (≥ leader / SPINE_DISTRICT_DOMINANCE) to win.
    if leader_type in DISTRICT_AREA_TYPES:
        threshold = votes[leader] / SPINE_DISTRICT_DOMINANCE
        contenders = [
            a
            for a in votes
            if snapshot.area_types.get(a, "") in SPECIFIC_AREA_TYPES
            and votes[a] >= threshold
        ]
        if contenders:
            return max(contenders, key=lambda a: (votes[a], -_type_rank(a, snapshot), a))

    # Fall through: literal top-scorer. Ties broken by area_type priority
    # then alphabetically (deterministic).
    return min(votes.keys(), key=lambda a: _spine_tiebreak_key(a, votes, snapshot))


def _type_rank(area: str, snapshot: CorpusSnapshot) -> int:
    area_type = snapshot.area_types.get(area, "")
    return (
        SPINE_AREA_TYPE_PRIORITY.index(area_type)
        if area_type in SPINE_AREA_TYPE_PRIORITY
        else len(SPINE_AREA_TYPE_PRIORITY)
    )


def _spine_tiebreak_key(area: str, votes: Counter[str], snapshot: CorpusSnapshot) -> tuple:
    """Smaller is better: (-vote_count, type_rank, vote_count, name).

    Used only when the 2× district lift hasn't already chosen a winner —
    e.g., among multiple specific Areas with identical scores.
    """
    return (-votes[area], _type_rank(area, snapshot), votes[area], area)


def _rank_areas_by_specificity(areas: tuple[str, ...], snapshot: CorpusSnapshot) -> list[str]:
    """Order a POI's Areas from most-specific to least, dropping city-typed."""
    ranked = []
    for a in areas:
        if _is_excluded(a, snapshot):
            continue
        area_type = snapshot.area_types.get(a, "")
        rank = (
            SPINE_AREA_TYPE_PRIORITY.index(area_type)
            if area_type in SPINE_AREA_TYPE_PRIORITY
            else len(SPINE_AREA_TYPE_PRIORITY)
        )
        ranked.append((rank, a))
    ranked.sort()
    return [a for _, a in ranked]


def _is_excluded(area: str, snapshot: CorpusSnapshot) -> bool:
    area_type = snapshot.area_types.get(area, "")
    return area_type in EXCLUDED_AREA_TYPES


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def poi_score(
    poi: POI,
    spine_area: str | None,
    interest: frozenset[str],
    snapshot: CorpusSnapshot,
) -> float:
    """The §3.2 per-POI score."""
    importance = float(poi.tier)
    richness = math.log1p(max(0, poi.beat_count))
    bias = _interest_bias(poi, interest)
    alignment = _area_alignment(poi, spine_area, snapshot)
    role_mult = POI_ROLE_MULTIPLIER.get(poi.poi_role, 0.0)
    return importance * richness * bias * alignment * role_mult


def _interest_bias(poi: POI, interest: frozenset[str]) -> float:
    if not interest or poi.beat_count == 0:
        return INTEREST_BIAS_BASE
    fraction = poi.matching_lens_beat_count / poi.beat_count
    bias = INTEREST_BIAS_BASE + INTEREST_BIAS_SCALE * fraction
    return min(bias, INTEREST_BIAS_MAX)


def _area_alignment(poi: POI, spine_area: str | None, snapshot: CorpusSnapshot) -> float:
    if spine_area is None:
        return AREA_ALIGNMENT_OTHER  # neutral
    if spine_area in poi.areas:
        return AREA_ALIGNMENT_SPINE
    adjacent = snapshot.adjacent_areas.get(spine_area, frozenset())
    if any(a in adjacent for a in poi.areas):
        return AREA_ALIGNMENT_ADJACENT
    return AREA_ALIGNMENT_OTHER


def _with_interest_count(
    poi: POI, snapshot: CorpusSnapshot, interest: frozenset[str]
) -> POI:
    if not interest:
        return poi
    matching = 0
    interest_low = {s.lower() for s in interest}
    for beat in snapshot.beats_for(poi.id):
        if any(lens.lower() in interest_low for lens in beat.lenses):
            matching += 1
    return poi.model_copy(update={"matching_lens_beat_count": matching})


def _has_active_beats(poi: POI, snapshot: CorpusSnapshot) -> bool:
    """True iff the POI has at least one active beat in the snapshot.

    Phase 5 Tour 4 selected Petit Palais (tier 4) as a stop with zero
    beats because routing-aware scoring liked the corridor geometry.
    The fix: filter the candidate pool by beat count before scoring.
    """
    for beat in snapshot.beats_for(poi.id):
        if (beat.active_status or "active") == "active":
            return True
    return False


def _attach_tourability_if_yellow(
    route: Route, assessment: TourabilityAssessment
) -> Route:
    """Attach the YELLOW assessment to the Route for skill-side surfacing.

    GREEN tours don't need to carry the assessment — the absence of a
    ``tourability`` field on the Route signals "fully GREEN, no
    warning needed". RED tours never reach this code path (we raised
    earlier).
    """
    if assessment.status == "YELLOW":
        return route.model_copy(update={"tourability": assessment})
    return route


__all__ = [
    "CorpusSnapshot",
    "load_paris_corpus",
    "select_route",
    "pick_spine_area",
    "poi_score",
    "PACE_KMH",
    "HAVERSINE_CORRECTION",
]
