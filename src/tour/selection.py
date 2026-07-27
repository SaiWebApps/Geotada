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

import itertools
import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import InitVar, dataclass
from dataclasses import field as dataclass_field
from types import MappingProxyType
from typing import TYPE_CHECKING

from shapely.errors import ShapelyError as _ShapelyError
from shapely.geometry import Point as _ShapelyPoint
from shapely.geometry import shape as _shapely_shape
from shapely.prepared import prep as _shapely_prep

from .beat_select import (
    _find_closing_friendly_index,
    extra_beat_ids,
    govern_poi_beats,
    select_poi_beats,
)
from .contract import (
    POI,
    BeatRef,
    PhysicalCue,
    POIBeats,
    ReachVerdict,
    Route,
    TourabilityAssessment,
    TourInput,
)
from .corpus_places import CorpusMaterializationPlan, CorpusPlaceManifest
from .density import FeasibilityAlternative, TourabilityRefusedError
from .density import assess_snapshot as assess_tourability
from .ordering import held_karp_open
from .routing import (
    EARTH_RADIUS_M,
    HAVERSINE_CORRECTION,
    LEGACY_ROUTE_PLANNING_POLICY,
    PACE_KMH,
    TIMEBOX_MATERIALITY_TOLERANCE_SECONDS,
    WALK_FRACTION,
    LegSecondsFn,
    RoutePlanningBudget,
    RoutePlanningPolicy,
    default_leg_seconds,
    envelope_radius_m,
    haversine_m,
    insertion_cost_seconds,
    planned_audio_seconds,
    route_planning_budget,
    smallest_duration_min_for_walk_seconds,
    summarise_route,
    within_planning_timebox,
)
from .routing import (
    target_audio_seconds as target_audio_seconds,
)

if TYPE_CHECKING:
    from .routing_client import RoutingClient


# Capability token held by the one validating converter.  It is not a security
# boundary against malicious Python code; it prevents ordinary constructors,
# fixtures, and future refactors from accidentally blessing a raw snapshot as
# materialized merely because its fields have the right shape.
_MATERIALIZED_SNAPSHOT_TOKEN = object()

# §3 lens_adjacency hop model (ALGORITHM-SPEC.md, M3): a requested lens scores
# a POI 1.0 on a direct beat-lens hit, 0.6 when a beat lens is one
# IS_PARENT_OF hop away (parent OR child), and 0.0 on a miss — a thematic
# FILTER, not a bias (supersedes the old rule-41 "bias not filter" and the
# INTEREST_BIAS_* constants it came with). With no lenses requested the
# factor is uniform 1.0 and selection degrades to importance x richness x
# alignment x role.
LENS_ADJACENCY_DIRECT: float = 1.0
LENS_ADJACENCY_ONE_HOP: float = 0.6
LENS_ADJACENCY_MISS: float = 0.0

# §3 spotlight model (ALGORITHM-SPEC.md, Phase 3). Lens is genre/tone, not a
# gate: every corridor POI is eligible and a continuous spotlight score
# allocates dwell. spotlight = gravity(tier) x lens_relevance x proximity.
#
# Crucially distinct from the legacy _lens_adjacency above, whose MISS=0.0
# makes lens a HARD FILTER (the current select_route gate). lens_relevance
# below shares the SAME direct/1-hop/miss CLASSIFICATION but maps a miss to a
# POSITIVE FLOOR (LENS_FLOOR) — a miss DIMS, it never zeroes. This is purely
# additive (Step 3.1): select_route's selection is untouched until Step 3.5.
#
# LENS_FLOOR (=0.25): lens_relevance on a thematic miss. A landmark on the
# user's path still clears the floor on gravity → at least a brief mention;
# "the only silence is low-gravity AND off-genre" (§3).
LENS_FLOOR: float = 0.25
LENS_RELEVANCE_DIRECT: float = 1.0  # direct lens hit
LENS_RELEVANCE_ONE_HOP: float = 0.6  # parent/child 1-hop via lens_neighbors
LENS_RELEVANCE_NO_LENS: float = 1.0  # no lenses requested → uniform

# proximity(poi, route) — the on-path bonus. 1.0 when the POI sits on the A-B
# line (zero marginal detour) and decays as the routed detour off that line
# grows. Exponential decay exp(-detour_seconds / PROXIMITY_DECAY_SECONDS):
#   - 1.0 at detour 0 (perfectly on-path),
#   - strictly monotonically decreasing in detour,
#   - ALWAYS > 0 (never zeroes) — so proximity alone can never silence a POI,
#     preserving the §3 invariant that the ONLY silence is low-gravity AND
#     off-genre (and keeping the multiplicative objective's factors ≥ 0, §9.5).
# PROXIMITY_DECAY_SECONDS is the e-folding constant: at this many seconds of
# marginal detour the proximity factor falls to 1/e (~0.368). 600s (10 min)
# means a POI a 10-min detour off the direct line keeps ~37% of its on-path
# weight — a gentle dimming, not a cliff.
PROXIMITY_DECAY_SECONDS: float = 600.0

# §3 band classifier (ALGORITHM-SPEC.md, Phase 3 Step 3.2). The continuous
# spotlight score maps to one of five output bands:
#   headline | full | short | vignette | silent
# The output-facing collapse is dwell (headline/full/short) vs vignette;
# "silent" means excluded for this user. The thresholds below are INITIAL,
# principled anchors -- they are refined in the Step 3.5 golden re-baseline,
# NOT frozen here.
#
# Anchoring (on-path, proximity == 1.0, so spotlight == gravity x lens):
#   - tier-1 off-genre miss  = 1 x 0.25 = 0.25  (canonical SILENT case)
#   - tier-5 off-genre miss  = 5 x 0.25 = 1.25  (high-gravity landmark; must
#                                                 clear to at least VIGNETTE)
#   - tier-1 1-hop           = 1 x 0.6  = 0.60
#   - tier-3 direct hit      = 3 x 1.0  = 3.0
#   - tier-5 direct hit      = 5 x 1.0  = 5.0   (canonical HEADLINE case)
# Thresholds are lower-inclusive cut points on the spotlight score:
# Calibrated at the Step 3.5 golden re-baseline: the DWELL floor (short) sits at
# tier-3 gravity (gravity(t)=float(t)) so a no-lens tour's dwell pool matches the
# prior ANCHOR_TIERS={3,4,5} anchors (which the human-ideal goldens were built on)
# -- tier-1/2 no-lens POIs fall to vignette instead of crowding out the golden
# anchors. Lens dimming still demotes off-genre POIs on lensed tours; the
# two-track (dwell/vignette) output stands.
BAND_THRESHOLD_HEADLINE: float = 5.0  # >= 5.0 -> headline (tier-5, or lens-lifted)
BAND_THRESHOLD_FULL: float = 4.0  # >= 4.0 -> full stop (tier-4+)
BAND_THRESHOLD_SHORT: float = 3.0  # >= 3.0 -> short stop; the DWELL floor (~ tier-3 anchor)
BAND_THRESHOLD_VIGNETTE: float = 0.5  # >= 0.5 -> walk-past vignette; below -> silent
#
# The §3 silence invariant is structural, NOT a pure score threshold: silence
# requires BOTH a lens miss AND low gravity. A high-gravity landmark
# (tier >= BAND_LANDMARK_TIER) is NEVER silent -- lens alone can dim it to a
# vignette but never to silence ("the only silence is low-gravity AND
# off-genre"). This guard floors such a POI at VIGNETTE even if a large
# proximity detour would otherwise push its score below the silent cut.
BAND_LANDMARK_TIER: int = 4

# Filler-stub demotion (2026-07-04, user-agent ratified). The dwell/vignette band
# decision (band_for_spotlight) is score-driven (gravity x lens x proximity) and
# NEVER looks at how much a stop will actually SPEAK. So a low-tier POI with one
# 56s beat still becomes a full DWELL stop — a "walked here for one sentence"
# anticlimax the tourists flagged (Crypte 56s, Hotel de la Monnaie 44s). A DWELL
# stop that would emit fewer than this many voiced seconds is demoted to a
# walk-by vignette instead — EXCEPT a landmark (tier >= BAND_LANDMARK_TIER), which
# never vanishes to a one-liner (a thin landmark discloses, per the density gate).
# Measured on FULL emitted audio (select_poi_beats keeps every beat; the lens only
# re-orders), so a stop thin FOR a lens but rich overall (e.g. the Pantheon, ~40s
# on-lens but ~275s total) is correctly KEPT.
MIN_DWELL_AUDIO_SECONDS: int = 90

# Absolute per-stop audio CEILING (C9h, 2026-07-16). No single stop may voice more
# than this many seconds of continuous narration — the 10-minute "wall, not a walk"
# monologue an acceptance review flagged as the top reason tours feel stilted.
# The terminal stop keeps a closing-friendly beat by swapping lower-priority
# kept beats back into overflow; it does not receive an over-cap exception.
# Applied to EVERY stop (the marquee included) on BOTH open-walk and A→B routes, as
# min(existing governor cap, this). It is a WHOLE-BEAT cap via govern_poi_beats:
# trimmed beats become keep-exploring overflow (never dropped), and compose
# recomputes its coverage baseline on the capped stitch, so NO fact is lost. Well
# above MIN_DWELL_AUDIO_SECONDS so a capped stop never demotes to a vignette.
# Tunable: raise to let a star dominate longer; lower for tighter stops.
# DERIVED, not chosen (2026-07-19). This ceiling and the quality standard's per-stop
# WORD cap were written independently and silently drifted: at 420 s, and with
# routing.beat_spoken_seconds converting at 150 wpm, this permitted 420*150/60 = 1050
# words in a single stop -- 40% above the published 750-word cap
# (src/tour/quality_rubric.py GORGE_MAX_WORDS_PER_STOP, sourced in
# specs/2026-07-19-tour-quality-standard/01-standard.md from museum-sector practice).
# Notre-Dame's MEASURED 1038-word stop was therefore the ceiling WORKING AS CONFIGURED,
# not a cap failure. Tied to the word cap so the two can no longer drift:
#     750 words / 150 wpm = 5.0 min = 300 s
# MINUS a MEASURED glue reserve: the ceiling caps BEAT audio, but a rendered stop also
# carries generation glue (arrival line, look-cue, closer). Measured per-stop glue on
# the Ile de la Cite tour: 2 / 65 / 16 / 12 / 73 words. Budgeting the worst case
# (~75 words = 30 s) keeps the RENDERED stop inside the cap instead of landing at 765.
MAX_DWELL_AUDIO_SECONDS: int = 270

# The five band labels, ordered loudest -> quietest. "silent" means excluded.
BAND_HEADLINE: str = "headline"
BAND_FULL: str = "full"
BAND_SHORT: str = "short"
BAND_VIGNETTE: str = "vignette"
BAND_SILENT: str = "silent"

# Output-facing collapse: the dwell bands (a real stop) vs the vignette band
# (one line as you pass). "silent" is neither -- it is excluded.
DWELL_BANDS: frozenset[str] = frozenset({BAND_HEADLINE, BAND_FULL, BAND_SHORT})

# Track B (Step B.1) — walk-past vignettes along the legs. A vignette-band POI
# within this perpendicular distance of a leg's straight segment is close
# enough to voice as a one-liner without any detour (locked deferred
# clarification: 50 m).
VIGNETTE_MAX_DETOUR_M: float = 50.0
# At most this many vignettes per leg — more one-liners than this on a single
# walk crowds the transit narration (locked deferred clarification: 2).
VIGNETTE_MAX_PER_LEG: int = 2

# §2.2 k-flavours (M6): diversity re-runs multiply already-used POIs' scores
# by DIVERSITY_PENALTY; a candidate flavour whose stop set shares
# >= JACCARD_OVERLAP_MAX (Jaccard) with any kept flavour is rejected.
DIVERSITY_PENALTY: float = 0.3
JACCARD_OVERLAP_MAX: float = 0.60

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
# Outer anchors only — internal vignettes don't count. Raised 12→15 (2026-07-11)
# to give long requests (150-400 min) denser coverage of nearby POIs instead of
# overstuffing 12 stops (the thin-tour complaint). 15 keeps the EXACT Held-Karp
# order solver comfortably under its 1s guard (~249ms measured; 2^15·15^2 ≈ 7.4M
# transitions). Do NOT exceed 16 (the outer timing edge). Tours ≤120 min are
# unaffected (max_anchors = duration//10 stays ≤12), so the calibration goldens
# do not move.
HARD_ANCHOR_CAP: int = 15  # outer anchors only — internal vignettes don't count

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
        "the",
        "of",
        "and",
        "or",
        "de",
        "des",
        "du",
        "le",
        "la",
        "les",
        "et",
        "place",
        "rue",
        "boulevard",
        "avenue",
        "quai",
        "pont",
        "musee",
        "musée",
        "hotel",
        "hôtel",
        "cathedral",
        "cathedrale",
        "cathédrale",
        "church",
        "saint",
        "sainte",
        "st",
        "ste",
        "square",
        "garden",
        "jardin",
        "park",
        "parc",
        "tower",
        "tour",
        "victor",  # ambiguous given name; co-located before this fires
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
# #21 under-fill rescue: while below the stop floor, admit a further stop whose
# MARGINAL walk cost is proportional to the audio it delivers — walk-seconds per
# audio-second. A rich nearby stop the greedy couldn't fit is worth the detour; a
# far, thin stop is a walk-slog (25 min walking for 3 min audio) and stays OUT.
# Tuned on the live routed corpus, which shows a clean gap: rich stops the fix
# SHOULD add rate 3.2-4.2 (Pantheon 3.47, Louvre Museum 3.2-3.3, Palais-Royal
# 4.19), thin slogs rate >=5.0 (Pont des Arts 5.0, thin streets 5.7-16). 4.5 sits
# squarely in the gap. (A marginal ratio is used, not a total-walk cap: the
# fill-pass insertion cost is a PRE-Held-Karp overestimate, so a total-walk
# threshold wrongly rejects good stops once the route is re-optimised.)
RESCUE_MAX_WALK_PER_AUDIO: float = 4.5
# The rescue lifts a tour to at least this many stops (the reported failure was a
# 60-min tour seating only ONE). Kept modest so two far-ish rich stops can't
# accumulate into a walk-heavy route — a 1->2 stop lift is the fix; a rich dense
# area already seats more via the greedy, and this never fires there.
RESCUE_STOP_FLOOR: int = 2
# C11a: a GREEN-density route whose DELIVERED audio is below this fraction of the
# audio target is disclosed as thin (delivered_thin). ~0.5 flags the pool-vs-
# delivered gap (e.g. a 90-min request delivering ~7 min) while leaving genuinely
# rich tours (Ile ~0.68 of target) unflagged.
GREEN_THIN_DELIVERY_FRAC: float = 0.5
# C9 governor v4 (domination-gated share-of-DELIVERED, 2026-07-04). The cap acts
# ONLY on a genuine DOMINATING OUTLIER — a non-exempt stop whose emitted audio
# both exceeds GOVERNOR_SHARE_OF_DELIVERED of the tour's total delivered audio AND
# exceeds GOVERNOR_DOMINATION_FACTOR x the MEAN of the OTHER non-exempt stops (so
# it is drowning its peers, e.g. the UC5 'Ile de la Cite' encyclopedia-dump; the
# mean-of-others gate means two co-dominators can't shield each other). Balanced
# tours (every stop near its fair share) are NEVER capped — the panel proved an
# always-on share cap over-trims them. EXEMPT (may dominate): the marquee (the
# highest-tier delivered stop, ties -> highest-audio) and the fixed destination /
# pulled endpoint. Importance-based exemption fixes the v3 bug where the greedy's
# nearest proximity-seed (often a thin courtyard) held the exemption while the
# real star was capped. See C9F-GOVERNOR-V3-SHARE.md + the panel refutation.
GOVERNOR_SHARE_OF_DELIVERED: float = 1.0 / 3.0
GOVERNOR_DOMINATION_FACTOR: float = 1.5


class CertificationPlanningInfeasibleError(Exception):
    """No eligible bounded stop set can satisfy a frozen certification band."""

    def __init__(
        self,
        *,
        policy_id: str,
        minimum_elapsed_seconds: int,
        maximum_elapsed_seconds: int,
        best_elapsed_seconds: int | None,
        reason: str,
    ) -> None:
        self.policy_id = policy_id
        self.minimum_elapsed_seconds = minimum_elapsed_seconds
        self.maximum_elapsed_seconds = maximum_elapsed_seconds
        self.best_elapsed_seconds = best_elapsed_seconds
        self.reason = reason
        best = "none" if best_elapsed_seconds is None else str(best_elapsed_seconds)
        super().__init__(
            f"Certification planning infeasible under {policy_id}: {reason}; "
            f"required {minimum_elapsed_seconds}-{maximum_elapsed_seconds}s, "
            f"best eligible bounded route {best}s."
        )


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


# Step 2.4 (2026-06-30) — fixed-destination B-materialization (HYBRID).
# When the request carries a fixed end B, ORDER must pin a concrete POI as
# the last stop. If a selected (already in-corridor) POI sits within this
# many metres of B, snap B onto it — the user's "end here" is satisfied by
# walking to that real anchor. Otherwise synthesize a sentinel POI at B's
# exact coordinate and add it to the selected set so Held-Karp can pin it.
# Geometric haversine proximity (like DEMOTION_PROXIMITY_M) is the right
# metric here: this is a "the destination *is* this place" judgment, not a
# routed-detour budget question (the corridor gate already enforced that).
B_SNAP_PROXIMITY_M: float = 150.0
# poi_role / tier for a synthesized B sentinel. role 'stop' marks it a
# plain ordered stop (not an anchor the greedy would have scored); a
# neutral mid tier keeps it from skewing any tier-weighted pass that might
# see it downstream — it carries no beats, so it contributes no audio.
B_SENTINEL_POI_ROLE: str = "stop"
B_SENTINEL_TIER: int = 3


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CorpusSnapshot:
    """All inputs `select_route` needs in pure-function form."""

    pois: tuple[POI, ...]
    beats_by_poi: Mapping[str, tuple[BeatRef, ...]]
    area_types: Mapping[str, str]  # area_name → area_type (district/neighborhood/...)
    adjacent_areas: Mapping[str, frozenset[str]]  # area_name → directly-adjacent area names
    # M3: lens hierarchy for the §3 lens_adjacency hop model. Lowercased lens
    # name → its IS_PARENT_OF neighbors one hop away, BOTH directions (parent
    # and children). Empty when a fixture doesn't care about lens hops.
    lens_neighbors: Mapping[str, frozenset[str]] = dataclass_field(default_factory=dict)
    place_manifest: CorpusPlaceManifest | None = None

    def beats_for(self, poi_id: str) -> tuple[BeatRef, ...]:
        if self.place_manifest is not None and not isinstance(
            self, MaterializedCorpusSnapshot
        ):
            raise ValueError("typed corpus place evidence has not been materialized")
        return self.beats_by_poi.get(poi_id, ())


@dataclass(frozen=True)
class MaterializedCorpusSnapshot(CorpusSnapshot):
    """Deep-immutable, manifest-validated input admitted to typed selection.

    The distinct type is intentional: carrying a manifest is not sufficient.
    Only :func:`place_materialization.materialize_corpus_snapshot` may convert
    source rows into this selection-ready form after sentence coverage,
    provenance, canonical identities, and playback contexts have been checked.
    """

    materialization_plan: CorpusMaterializationPlan | None = None
    snapshot_sha256: str = ""
    _validation_token: InitVar[object | None] = None

    def __post_init__(self, _validation_token: object | None) -> None:
        mappings = (
            self.beats_by_poi,
            self.area_types,
            self.adjacent_areas,
            self.lens_neighbors,
        )
        if any(not isinstance(value, MappingProxyType) for value in mappings):
            raise ValueError("materialized corpus mappings must be deep-immutable")
        if self.place_manifest is None or self.materialization_plan is None:
            raise ValueError("materialized corpus requires its manifest and decision plan")
        if _validation_token is not _MATERIALIZED_SNAPSHOT_TOKEN:
            raise ValueError("only the validated materializer may construct this snapshot")
        if (
            self.materialization_plan.source_manifest_sha256
            != self.place_manifest.manifest_sha256
        ):
            raise ValueError("materialization plan is bound to a different manifest")
        if not re.fullmatch(r"[0-9a-f]{64}", self.snapshot_sha256):
            raise ValueError("materialized corpus requires a canonical snapshot hash")


def require_materialized_snapshot(
    snapshot: CorpusSnapshot, *, operation: str
) -> None:
    """Validate one typed snapshot at a public post-selection boundary."""

    if snapshot.place_manifest is None:
        return
    if not isinstance(snapshot, MaterializedCorpusSnapshot):
        raise ValueError(f"typed corpus must be materialized before {operation}")
    from .place_materialization import validate_materialized_corpus_snapshot

    validate_materialized_corpus_snapshot(snapshot)


def _place_identity_key(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    ).casefold()


def is_container_identity_poi(poi: POI) -> bool:
    """Whether this POI *is* one of its own containing areas — a neighbourhood or
    district standing in as if it were a findable place.

    Measured on the live Paris graph (2026-07-26): exactly ONE POI qualifies —
    ``Les Halles``, which exists both as an Area and as a tier-5 POI with
    ``poi_role='setting'``. A tourist told to "go to Les Halles" while standing in
    Les Halles has been given no destination.
    """

    return _place_identity_key(poi.name) in {_place_identity_key(area) for area in poi.areas}


def route_has_container_identity_stop(route: Route) -> bool:
    """Return whether a neighborhood or area was used as a fictional stop."""

    return any(is_container_identity_poi(poi) for poi in route.pois)


def choose_discrete_route(routes: list[Route]) -> Route:
    """Choose the first ranked route whose stops are findable identities."""

    for route in routes:
        if not route_has_container_identity_stop(route):
            return route
    raise ValueError("bounded candidates contain no route with all-discrete stops")


# ---------------------------------------------------------------------------
# Neo4j loader
# ---------------------------------------------------------------------------


# Cypher pulls every active beat for every city POI in one shot. POIs
# carry their Area memberships as a list; beats carry only what selection
# and ordering need. ORDER BY p.id because Cypher row order is otherwise
# unspecified — snapshot.pois must be identical across two loads of the
# same graph or greedy tie-breaks drift between runs.
LOAD_PARIS_POIS_CYPHER = """
MATCH (p:POI {city_name: $city_slug})
OPTIONAL MATCH (p)-[:WITHIN]->(a:Area)
WITH p, collect(DISTINCT a.name) AS area_names
WHERE p.location IS NOT NULL
RETURN
  p.id            AS id,
  p.canonical_place_id AS canonical_place_id,
  p.name          AS name,
  p.aliases       AS aliases,
  p.coordinate_provenance AS coordinate_provenance,
  p.importance_tier AS tier,
  p.poi_role      AS poi_role,
  p.location.y    AS lat,
  p.location.x    AS lng,
  area_names      AS areas
ORDER BY p.id
"""

LOAD_PARIS_BEATS_CYPHER = """
MATCH (p:POI {city_name: $city_slug})-[:HAS_BEAT]->(b:NarrativeBeat)
WHERE b.active_status = 'active'
OPTIONAL MATCH (b)-[:TAGGED_WITH]->(l:Lens)
WITH p, b, collect(DISTINCT l.name) AS lens_names
RETURN
  b.id                  AS id,
  b.beat_id             AS stable_beat_id,
  b.place_plan_id       AS place_plan_id,
  p.id                  AS poi_id,
  b.sub_location        AS sub_location,
  b.trigger_address     AS trigger_address,
  b.narrative_function  AS narrative_function,
  b.beat_type           AS beat_type,
  b.emotional_register  AS emotional_register,
  b.beat_length_class   AS beat_length_class,
  b.est_spoken_seconds  AS est_spoken_seconds,
  b.script_body         AS script_body,
  b.audio_url           AS audio_url,
  b.entities            AS entities,
  b.subject_tag         AS subject_tag,
  b.active_status       AS active_status,
  b.physical_cues       AS physical_cues,
  b.pronunciation       AS pronunciation,
  b.source_passage      AS source_passage,
  b.source_chunk_slug   AS source_chunk_slug,
  b.key_claims          AS key_claims,
  lens_names            AS lenses
ORDER BY coalesce(b.beat_id, b.id)
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

# Lens hierarchy for the §3 lens_adjacency hop model. Lens nodes are global
# (not city-scoped) by design — the taxonomy is shared across cities.
LOAD_LENS_HIERARCHY_CYPHER = """
MATCH (parent:Lens)-[:IS_PARENT_OF]->(child:Lens)
RETURN parent.name AS parent, child.name AS child
"""


def load_paris_corpus(driver, *, city_slug: str = "paris") -> CorpusSnapshot:
    """Pull a CorpusSnapshot for one city from Neo4j."""
    with driver.session() as session:
        poi_records = session.run(LOAD_PARIS_POIS_CYPHER, city_slug=city_slug).data()
        beat_records = session.run(LOAD_PARIS_BEATS_CYPHER, city_slug=city_slug).data()
        area_records = session.run(LOAD_AREA_TYPES_CYPHER).data()
        adj_records = session.run(LOAD_AREA_ADJACENCY_CYPHER, city_slug=city_slug).data()
        lens_records = session.run(LOAD_LENS_HIERARCHY_CYPHER).data()

    return _snapshot_from_records(
        poi_records, beat_records, area_records, adj_records, lens_records
    )


def _lens_neighbor_map(lens_records: list[dict]) -> dict[str, frozenset[str]]:
    """Symmetric 1-hop IS_PARENT_OF neighborhood, lowercased both ways."""
    acc: dict[str, set[str]] = {}
    for r in lens_records:
        parent = (r.get("parent") or "").strip().lower()
        child = (r.get("child") or "").strip().lower()
        if not parent or not child:
            continue
        acc.setdefault(parent, set()).add(child)
        acc.setdefault(child, set()).add(parent)
    return {k: frozenset(v) for k, v in acc.items()}


# src/seed/narratives.py:95 stamps every seeded beat with this audio prefix.
# A seeded beat that was later adopted into the corpus carries a real
# ``beat_id``; the un-adopted twin left behind by re-seeding does not, and
# is invisible to db_parity.py:113 and prune_orphan_pois.py:48 (both filter
# ``beat_id IS NOT NULL``). Excluding it here is the only thing keeping
# placeholder audio out of a tour.
_PLACEHOLDER_AUDIO_PREFIX = "s3://ondoway-audio/placeholder/"


def _is_unadopted_placeholder_beat(record: dict) -> bool:
    """True for a seed-artifact beat: no stable beat_id AND placeholder audio.

    The conjunction is deliberate. Real corpus beats awaiting TTS still point
    at the placeholder prefix, and hermetic callers legitimately omit
    ``stable_beat_id``; neither half alone may exclude a beat.
    """
    if _clean(record.get("stable_beat_id")) is not None:
        return False
    audio_url = record.get("audio_url")
    return isinstance(audio_url, str) and audio_url.startswith(_PLACEHOLDER_AUDIO_PREFIX)


def _snapshot_from_records(
    poi_records: list[dict],
    beat_records: list[dict],
    area_records: list[dict],
    adj_records: list[dict],
    lens_records: list[dict] | None = None,
    place_manifest: CorpusPlaceManifest | None = None,
) -> CorpusSnapshot:
    pois: list[POI] = []
    beats_by_poi_acc: dict[str, list[BeatRef]] = {}

    for r in beat_records:
        if _is_unadopted_placeholder_beat(r):
            continue
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
            lenses=tuple(sorted(s for s in (r.get("lenses") or ()) if s)),
            active_status=r.get("active_status") or "active",
            script_body=body if isinstance(body, str) and body.strip() else None,
            physical_cues=_decode_physical_cues(r.get("physical_cues")),
            pronunciation=_clean(r.get("pronunciation")),
            source_passage=_clean(r.get("source_passage")),
            source_chunk_slug=_clean(r.get("source_chunk_slug")),
            key_claims=tuple(s.strip() for s in (r.get("key_claims") or ()) if s and s.strip()),
            stable_beat_id=_clean(r.get("stable_beat_id")),
            place_plan_id=_clean(r.get("place_plan_id")),
        )
        beats_by_poi_acc.setdefault(ref.poi_id, []).append(ref)

    for r in poi_records:
        pid = r["id"]
        beats = beats_by_poi_acc.get(pid, [])
        beat_count = len(beats)
        # matching_lens_beat_count is legacy: the M3 lens_adjacency hop model
        # scans beat lenses directly, so nothing computes it any more. The
        # contract field stays (spec §5: every existing field preserved).
        pois.append(
            POI(
                id=pid,
                name=r["name"],
                tier=int(r.get("tier") or 1),
                poi_role=r.get("poi_role") or "stop",
                lat=float(r["lat"]),
                lng=float(r["lng"]),
                areas=tuple(sorted(a for a in (r.get("areas") or ()) if a)),
                beat_count=beat_count,
                matching_lens_beat_count=0,
                canonical_place_id=_clean(r.get("canonical_place_id")),
                aliases=tuple(
                    sorted(
                        {
                            alias.strip()
                            for alias in (r.get("aliases") or ())
                            if isinstance(alias, str) and alias.strip()
                        },
                        key=lambda value: (value.casefold(), value),
                    )
                ),
                coordinate_provenance=_decode_coordinate_provenance(
                    r.get("coordinate_provenance")
                ),
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
        lens_neighbors=_lens_neighbor_map(lens_records or []),
        place_manifest=place_manifest,
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


def _decode_coordinate_provenance(raw):
    """Decode a D1 coordinate evidence object; missing legacy data stays None.

    A present but malformed value is rejected rather than downgraded to
    untrusted coordinates.  D2 will persist this canonical JSON shape.
    """

    if raw is None or raw == "":
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("coordinate_provenance is not JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("coordinate_provenance must be an object")
    from .corpus_places import CoordinateProvenance

    return CoordinateProvenance.model_validate(raw)


# ---------------------------------------------------------------------------
# Step 2.2b — closer_b geometry (bearing + ±45° wedge)
# ---------------------------------------------------------------------------

# Half-angle of the directional wedge around the A→B bearing. A candidate B'
# counts as "in the same direction" when its A→B' bearing lies within ±45° of
# the A→B bearing — a 90°-wide cone pointing at the originally-requested B.
CLOSER_B_WEDGE_HALF_ANGLE_DEG: float = 45.0


def bearing(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compass bearing in degrees [0, 360) from (lat1,lng1) toward (lat2,lng2).

    Euclidean (equirectangular) bearing: longitude differences are scaled by
    cos(mean latitude) so a degree of longitude is weighted like the local
    east-west distance. 0° = due north, 90° = due east. Adequate for the
    short, in-city A→B' separations the wedge test compares — we never need
    great-circle bearing precision here, only relative direction.
    """
    mean_lat_rad = math.radians((lat1 + lat2) / 2.0)
    dx = (lng2 - lng1) * math.cos(mean_lat_rad)  # east component
    dy = lat2 - lat1  # north component
    # atan2(east, north) gives a clockwise-from-north compass bearing.
    return math.degrees(math.atan2(dx, dy)) % 360.0


def _angular_diff_deg(a: float, b: float) -> float:
    """Smallest absolute difference between two bearings, in [0, 180]."""
    diff = abs(a - b) % 360.0
    return diff if diff <= 180.0 else 360.0 - diff


def in_wedge(
    origin_lat: float,
    origin_lng: float,
    axis_lat: float,
    axis_lng: float,
    target_lat: float,
    target_lng: float,
    *,
    half_angle_deg: float = CLOSER_B_WEDGE_HALF_ANGLE_DEG,
) -> bool:
    """True iff ``target`` lies inside the ±half_angle wedge around the
    origin→axis bearing.

    The wedge is centred on the bearing from ``origin`` to ``axis`` (the A→B
    direction). ``target`` (a candidate B') is inside when the angular gap
    between its origin→target bearing and the axis bearing is ≤ ``half_angle``.
    """
    axis_bearing = bearing(origin_lat, origin_lng, axis_lat, axis_lng)
    target_bearing = bearing(origin_lat, origin_lng, target_lat, target_lng)
    return _angular_diff_deg(axis_bearing, target_bearing) <= half_angle_deg


def _closer_b_alternative(
    *,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    duration_min: int,
    interest: frozenset[str],
    snapshot: CorpusSnapshot,
    leg_cost_fn: LegSecondsFn,
    walk_budget: int | None = None,
) -> FeasibilityAlternative | None:
    """Build the Step 2.2b 'closer_b' alternative, or None when none fits.

    Scans the LANDMARK-tier POIs (``poi_role`` in the eligible roles, ``tier``
    in ``ANCHOR_TIERS``, >=1 active beat) and keeps those whose routed A->B'
    leg fits inside the walk budget — using the very divisor the caller passes
    (``leg_fn or default_leg_seconds``), never straight-line haversine.

    NOTE (Step 3.5 model switch): a suggested DESTINATION B' is intentionally
    still restricted to ``ANCHOR_TIERS`` — "end your walk here" should point at
    a real landmark, never a tier-1 footnote. So this pool is deliberately
    NARROWER than select_route's now-gateless corridor candidate pool; the two
    are no longer identical. The ranking uses ``poi_score``, whose lens factor
    is now the floored ``lens_relevance``, so a lens-miss landmark ranks below a
    lens-hit one rather than tying at zero.

    Among the in-budget anchors:
    - If any lie inside the ±45° wedge around the A→B bearing, pick the highest
      ``poi_score`` (tie-break ascending ``id``) inside the wedge.
    - Otherwise (empty wedge), fall back to the highest ``poi_score`` (tie-break
      ascending ``id``) in-budget anchor regardless of bearing.

    Returns None when no anchor is reachable inside the walk budget, so the
    refusal omits closer_b entirely in that case. ``spine`` is None at this
    pre-selection point, so ``poi_score`` evaluates with neutral area
    alignment (the rank still reflects tier x richness x lens fit x role).
    """
    budget = (
        route_planning_budget(duration_min).walk_budget_seconds
        if walk_budget is None
        else walk_budget
    )

    in_budget: list[POI] = []
    for poi in snapshot.pois:
        if poi.poi_role not in POI_ROLE_MULTIPLIER or POI_ROLE_MULTIPLIER[poi.poi_role] <= 0.0:
            continue
        if poi.tier not in ANCHOR_TIERS:
            continue
        if not _has_active_beats(poi, snapshot):
            continue
        t_ab_prime = leg_cost_fn(start_lat, start_lng, poi.lat, poi.lng)
        if t_ab_prime <= budget:
            in_budget.append(poi)

    if not in_budget:
        return None

    def _rank_key(p: POI) -> tuple[float, str]:
        # Highest poi_score first (negate), ascending id as the deterministic
        # tie-break — mirrors every other selection ranking in this module.
        return (-poi_score(p, None, interest, snapshot), p.id)

    in_wedge_anchors = [
        p
        for p in in_budget
        if in_wedge(start_lat, start_lng, end_lat, end_lng, p.lat, p.lng)
    ]
    pool = in_wedge_anchors if in_wedge_anchors else in_budget
    target = min(pool, key=_rank_key)
    return FeasibilityAlternative(
        kind="closer_b",
        duration_min=duration_min,
        drop_end=True,
        poi_id=target.id,
        lat=target.lat,
        lng=target.lng,
    )


# ---------------------------------------------------------------------------
# Step 2.4 — fixed-destination B-materialization (HYBRID)
# ---------------------------------------------------------------------------


def _materialize_fixed_end_b(
    selected: list[POI],
    *,
    end_lat: float,
    end_lng: float,
) -> tuple[list[POI], POI]:
    """Resolve a fixed end B to a concrete POI inside ``selected`` for ORDER.

    HYBRID rule (locked):
    - If a selected POI sits within ``B_SNAP_PROXIMITY_M`` of B, snap B onto
      the nearest such POI (ties broken by ascending id for determinism) and
      return it unchanged — ``selected`` is returned as-is.
    - Otherwise synthesize a sentinel POI at B's *exact* coordinate
      (``poi_role='stop'``, neutral tier, no beats) and return a new list
      with the sentinel appended, so Held-Karp can pin it as ``fixed_end``.

    All members of ``selected`` are already in-corridor on the fixed-end path
    (the §2.3 corridor gate filtered the candidate pool), so the snap pool is
    exactly ``selected``. The returned POI is guaranteed present in the
    returned list — the precondition ``held_karp_open(fixed_end=...)`` enforces.
    """
    nearest: POI | None = None
    nearest_dist = float("inf")
    for poi in selected:
        d = haversine_m(end_lat, end_lng, poi.lat, poi.lng)
        # Strictly-closer keeps the first-seen on a tie; the explicit id
        # tie-break below makes the choice independent of list order.
        if d < nearest_dist or (d == nearest_dist and nearest is not None and poi.id < nearest.id):
            nearest_dist = d
            nearest = poi

    if nearest is not None and nearest_dist <= B_SNAP_PROXIMITY_M:
        return selected, nearest

    sentinel = POI(
        id=f"__end_b__{end_lat:.6f}_{end_lng:.6f}",
        name="Destination",
        tier=B_SENTINEL_TIER,
        poi_role=B_SENTINEL_POI_ROLE,
        lat=end_lat,
        lng=end_lng,
    )
    return [*selected, sentinel], sentinel


# ---------------------------------------------------------------------------
# Selection (pure)
# ---------------------------------------------------------------------------


def build_poi_beat_plans(
    route: Route, snapshot: CorpusSnapshot, *, lenses: Iterable[str] | None
) -> tuple[POIBeats, ...]:
    """Ordered per-POI beat plans for a route, with each co-located demoted
    sibling's beats merged into its host (the single source shared by
    ``/trips/generate``, ``/trips/{id}/compose``, ``scripts/tour_build.py`` and
    the golden harnesses). Vignette handling + ``BeatSequence`` construction stay
    at the call sites (they differ per surface). C9b: an identity refactor of the
    three production loops that already merged ``demoted_beats``; the golden
    harnesses are routed through it too so they measure the shipped pipeline.
    """
    require_materialized_snapshot(snapshot, operation="beat planning")
    plans: list[POIBeats] = []
    for poi in route.pois:
        beats = list(snapshot.beats_for(poi.id))
        beats.extend(route.demoted_beats.get(poi.id, ()))
        plans.append(select_poi_beats(poi, beats, interest_lenses=lenses))
    return tuple(plans)


def build_poi_extra_beats(
    route: Route,
    snapshot: CorpusSnapshot,
    voiced_by_poi: dict[str, tuple[str, ...]],
    *,
    lenses: Iterable[str] | None,
) -> dict[str, tuple[str, ...]]:
    """KE1: per-POI "keep exploring here" extras — the un-voiced beats of each stop.

    Uses the SAME merged beat pool (``snapshot.beats_for`` + ``demoted_beats``) as
    :func:`build_poi_beat_plans`, so the extras are exactly the uncapped plan minus
    what the tour voiced, in priority order. POIs with no extras are omitted.
    """
    require_materialized_snapshot(snapshot, operation="extra-beat planning")
    out: dict[str, tuple[str, ...]] = {}
    for poi in route.pois:
        beats = list(snapshot.beats_for(poi.id))
        beats.extend(route.demoted_beats.get(poi.id, ()))
        extras = extra_beat_ids(poi, beats, voiced_by_poi.get(poi.id, ()), interest_lenses=lenses)
        if extras:
            out[poi.id] = extras
    return out


def build_poi_extra_narration(
    extra_by_poi: dict[str, tuple[str, ...]],
    snapshot: CorpusSnapshot,
) -> dict[str, str]:
    """KE2: per-POI "keep exploring here" narration — DETERMINISTIC, no LLM.

    The extras are CURATED CORPUS beats (each carries a real ``script_body``), so
    they are faithful by construction — unlike the freely-composed main narration
    they need NO LLM entailment / VERIFY gate. We therefore stitch them the same
    way the main narration voices its beat portion (``generation._beat_to_sentences``
    -> ``split_sentences``), joining sentence texts with a single space — the exact
    join ``stop_narration_text`` uses for the per-stop audio the /audio path voices.

    ``extra_by_poi`` maps poi_id -> ORDERED extra beat ids (the output of
    :func:`build_poi_extra_beats`); the join preserves that priority order, so
    extra_beat_ids and extra_narration are consistent by construction. A POI's
    resolvable extras with empty/absent bodies contribute nothing; a POI whose
    extras yield no text at all is omitted (no empty-string narration is stored).
    """
    require_materialized_snapshot(snapshot, operation="extra narration")
    from .generation import split_sentences  # local import: avoid a module cycle

    beats_by_id = {
        ref.id: (poi_id, ref)
        for poi_id, refs in snapshot.beats_by_poi.items()
        for ref in refs
    }
    out: dict[str, str] = {}
    for poi_id, beat_ids in extra_by_poi.items():
        sentences: list[str] = []
        for bid in beat_ids:
            resolved = beats_by_id.get(bid)
            if resolved is None:
                continue
            actual_poi_id, ref = resolved
            if actual_poi_id != poi_id or not ref.script_body:
                continue
            sentences.extend(split_sentences(ref.script_body))
        narration = " ".join(sentences)
        if narration:
            out[poi_id] = narration
    return out


def _domination_caps(is_exempt: list[bool], audio: list[int]) -> list[int | None]:
    """Per-stop second-caps for the v4 domination-gated governor.

    Exempt stops → ``None`` (uncapped). A non-exempt stop is capped ONLY when it is
    a genuine DOMINATING OUTLIER: it exceeds ``GOVERNOR_SHARE_OF_DELIVERED`` of the
    total delivered audio AND exceeds ``GOVERNOR_DOMINATION_FACTOR`` x the MEAN of
    the OTHER non-exempt stops (it is drowning its peers). Comparing to the mean of
    the others — not the next-largest — closes the pairwise-shielding gap where two
    co-dominators would each hide behind the other. A dominator is capped to the
    share ceiling; capping lowers the total, so we re-check to a fixed point. A
    balanced tour, where no stop dwarfs the mean of its peers, is NEVER capped —
    the whole point of the v4 redesign. A cluster of 3+ NEAR-EQUAL rich stops
    converges to a balanced delivery (only the single largest, if any, trims)
    rather than each being cut. Needs ≥2 non-exempt stops for "domination" to mean
    anything.
    """
    n = len(audio)
    caps: list[int | None] = [None if is_exempt[i] else audio[i] for i in range(n)]
    non_exempt = [i for i in range(n) if caps[i] is not None]
    if len(non_exempt) < 2:
        return caps  # need a dominator + at least one drowned peer
    # Cap the largest current dominator to the ceiling, then re-evaluate. A
    # "dominator" is over the ⅓ ceiling AND exceeds the factor x the MEAN of the
    # OTHER non-exempt stops — compared to the peers it is drowning, not to the
    # next-largest (so two co-dominators can't shield each other, the panel gap).
    # Terminates: each cap strictly lowers the (integer) delivered total, which is
    # bounded below by 0, so the loop runs a finite number of passes.
    while True:
        total = sum(audio[i] if caps[i] is None else caps[i] for i in range(n))
        ceiling = int(GOVERNOR_SHARE_OF_DELIVERED * total)
        target: int | None = None
        for i in non_exempt:
            if caps[i] <= ceiling:
                continue
            others = [caps[j] for j in non_exempt if j != i]
            mean_others = sum(others) / len(others)
            if caps[i] <= GOVERNOR_DOMINATION_FACTOR * max(1.0, mean_others):
                continue  # balanced — not a drowning outlier
            if target is None or caps[i] > caps[target]:
                target = i
        if target is None:
            break
        caps[target] = ceiling
    return caps


def _is_filler_stub(poi: POI, snapshot: CorpusSnapshot, lenses: Iterable[str] | None) -> bool:
    """A dwell-eligible POI too THIN to justify a dedicated stop — demote it to a
    walk-by vignette (the "walked here for one sentence" anticlimax).

    True iff the POI would be a DWELL stop (on-path dwell band) that is NOT a
    landmark (tier < BAND_LANDMARK_TIER) AND whose full emitted audio is under
    ``MIN_DWELL_AUDIO_SECONDS``. The dwell-band guard matters: a silent or already-
    vignette POI is NOT a filler-stub (it was never going to be a dedicated stop),
    so this must not re-promote a silent POI into a walk-by. Shared by the dwell-
    pool filter (keeps it out of the greedy) and :func:`select_vignettes` (routes
    it to a walk-by), so /trips/generate and /trips/compose agree by construction.
    """
    if poi.tier >= BAND_LANDMARK_TIER:
        return False
    score = spotlight(poi, lenses=lenses or None, snapshot=snapshot)
    if not is_dwell_band(band_for_spotlight(score, tier=poi.tier)):
        return False  # vignette/silent already — not a would-be dwell stop
    return planned_capped_audio_seconds(poi, snapshot, lenses, None) < MIN_DWELL_AUDIO_SECONDS


def build_poi_beat_plans_capped(
    route: Route,
    snapshot: CorpusSnapshot,
    *,
    lenses: Iterable[str] | None,
    end_is_none: bool = False,
) -> tuple[tuple[POIBeats, tuple[str, ...]], ...]:
    """C9 governor v4 — the shared EMISSION choke point: ``(kept, overflow_ids)``
    per POI, in route order. All six build sites (generate, compose, preview,
    tour_build, the two golden harnesses) go through here so the cap lives in ONE
    place.

    Two caps compose (whichever is tighter wins per stop):
    1. The v4 DOMINATION governor (:func:`_domination_caps`) — relative, runs only
       on ``end_is_none`` (round-trip / open-walk); caps a single dominating outlier
       and EXEMPTS the MARQUEE (highest-tier delivered stop, ties -> highest audio)
       and ``route.fixed_end_poi_id``.
    2. The absolute ``MAX_DWELL_AUDIO_SECONDS`` CEILING (C9h) — no stop, marquee
       included, may voice more than this on EITHER route type, so no spot becomes a
       10-minute monologue. The marquee may still dominate, but only up to the
       ceiling.

    Both are WHOLE-BEAT caps via :func:`govern_poi_beats`: trimmed beats are returned
    as keep-exploring overflow (never silently dropped), so no fact is lost.
    """
    plans = build_poi_beat_plans(route, snapshot, lenses=lenses)
    if not plans:
        return ()
    if end_is_none:
        audio = [planned_audio_seconds(plan.beats) for plan in plans]
        exempt_ids: set[str] = set()
        if route.fixed_end_poi_id is not None:
            exempt_ids.add(route.fixed_end_poi_id)
        # The marquee: highest-tier stop, ties -> highest audio. Always a real POI in
        # the delivered route (never a dangling / demoted id).
        marquee = max(range(len(plans)), key=lambda i: (route.pois[i].tier, audio[i]))
        exempt_ids.add(route.pois[marquee].id)
        is_exempt = [poi.id in exempt_ids for poi in route.pois]
        dom_caps = _domination_caps(is_exempt, audio)
    else:
        # A→B: no relative domination governor, but the absolute ceiling still binds.
        dom_caps = [None] * len(plans)
    # Apply the absolute ceiling to EVERY stop: min(domination cap, MAX). A None
    # (exempt / uncapped-by-domination) stop is capped to the MAX; a domination-capped
    # stop keeps the tighter of the two.
    final_caps = [
        MAX_DWELL_AUDIO_SECONDS if c is None else min(c, MAX_DWELL_AUDIO_SECONDS)
        for c in dom_caps
    ]
    capped = [
        govern_poi_beats(plan, cap) for plan, cap in zip(plans, final_caps, strict=True)
    ]
    # Protect the last NARRATED stop's closing-friendly beat from the cap. The closing
    # glue fires after the last beat of the last stop WITH content, and
    # reorder_final_stop_for_closing (which runs later, in generate) can only reorder
    # beats the cap KEPT — so if the cap trimmed the callback/climax, the tour ends
    # mid-fact. Skip a beatless fixed-end (A→B) sentinel and protect the real terminal.
    for i in range(len(capped) - 1, -1, -1):
        if capped[i][0].beats:
            capped[i] = _keep_final_closing_beat(
                capped[i], plans[i], allowance_seconds=final_caps[i]
            )
            break
    return tuple(capped)


def _keep_final_closing_beat(
    capped: tuple[POIBeats, tuple[str, ...]],
    full_plan: POIBeats,
    *,
    allowance_seconds: int = MAX_DWELL_AUDIO_SECONDS,
) -> tuple[POIBeats, tuple[str, ...]]:
    """If the per-stop cap trimmed the FINAL stop's closing-friendly beat
    (callback > climax > longest, per ``_find_closing_friendly_index``), fit it
    inside the SAME allowance by returning the lowest-priority kept tail beats
    to overflow.  This closes on a real ending without the former one-beat cap
    leak.  Overflow is rebuilt in full-plan order, so every displaced source
    fact remains available through keep-exploring.

    No-op when nothing was trimmed, the closing beat already survived, or the
    closing beat alone exceeds the allowance (no whole-beat plan can satisfy
    both constraints in that malformed-corpus case)."""
    kept, overflow = capped
    if not overflow:
        return capped
    idx = _find_closing_friendly_index(full_plan.beats)
    if idx is None:
        return capped
    closing = full_plan.beats[idx]
    if any(b.id == closing.id for b in kept.beats):
        return capped
    if closing.id not in overflow or planned_audio_seconds((closing,)) > allowance_seconds:
        return capped

    # govern_poi_beats kept a priority prefix.  Remove from its tail first, so
    # the cold-open/head is displaced only if it is the sole way to fit the
    # closing beat.  At least the closing remains because it fits by itself.
    fitted = list(kept.beats)
    while fitted and planned_audio_seconds((*fitted, closing)) > allowance_seconds:
        fitted.pop()
    fitted.append(closing)
    fitted_ids = {beat.id for beat in fitted}
    new_kept = kept.model_copy(update={"beats": tuple(fitted)})
    new_overflow = tuple(beat.id for beat in full_plan.beats if beat.id not in fitted_ids)
    return new_kept, new_overflow


def planned_capped_audio_seconds(
    poi: POI,
    snapshot: CorpusSnapshot,
    lenses: Iterable[str] | None,
    allowance: int | None,
) -> int:
    """Voiced seconds a POI's plan CONSUMES under the C9 governor: the capped
    (allowance-truncated) beats for an incidental stop, or the full uncapped plan
    for an exempt anchor (``allowance is None``). This is selection's FLOOR-LESS
    audio currency — no tier floor; tier dwell survives only as C8's reported
    minute floor. Pure per (poi, lenses, allowance); memoize at the call site.
    """
    plan = select_poi_beats(poi, snapshot.beats_for(poi.id), interest_lenses=lenses)
    kept, _overflow = govern_poi_beats(plan, allowance)
    return planned_audio_seconds(kept.beats)


def select_route(
    input: TourInput,
    snapshot: CorpusSnapshot,
    *,
    routing_client: RoutingClient | None = None,
    score_penalty: dict[str, float] | None = None,
    planning_policy: RoutePlanningPolicy = LEGACY_ROUTE_PLANNING_POLICY,
) -> Route:
    """Compute the spine, score POIs, run greedy selection. Returns a Route.

    M2: ``routing_client`` only enriches the final Route's transits with
    routed leg_seconds/polylines (via summarise_route) — selection scoring
    stays on haversine until M3.

    M6: ``score_penalty`` (poi_id → multiplicative factor) is the diversity
    knob select_k_routes uses for flavour re-runs; leave None for normal
    single-route selection.

    Phase 6 added two guards before the greedy:

    1. **Density gate** (§3.7) — call ``density.assess_snapshot(input, snapshot)``. RED
       raises ``TourabilityRefusedError``; YELLOW attaches the assessment to
       ``Route.tourability`` for the harness to surface.
    2. **Zero-beat-POI exclusion** — POIs with no active beats are
       removed from the candidate pool before scoring. This was the
       Phase 5 Petit Palais bug: a tier-4 POI with 0 beats was selected
       as an anchor purely because it sat on the route corridor.
    """
    if snapshot.place_manifest is not None and not isinstance(
        snapshot, MaterializedCorpusSnapshot
    ):
        raise ValueError(
            "typed corpus must be validated by materialize_corpus_snapshot "
            "before density or selection"
        )
    start_lat, start_lng = input.start
    interest = frozenset(input.lenses or [])
    planning_budget = route_planning_budget(input.duration_min, planning_policy)
    certification_fixed_end = input.end is not None and not planning_policy.is_legacy
    certification_total_ceiling = (
        planning_budget.maximum_elapsed_seconds + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
    )
    # M3: the §3 divisor — routed leg times when a client is given (memoized;
    # the greedy re-evaluates the same coordinate pairs many times), else the
    # pace-corrected haversine.
    leg_fn = _memoized_leg_fn(routing_client) if routing_client is not None else None

    # Phase 6 density gate. Start-circle RED refuses open/round-trip requests.
    # Fixed-end requests defer to the routed A→B corridor checks below.
    assessment = assess_tourability(input, snapshot)
    if assessment.status == "RED" and input.end is None:
        raise TourabilityRefusedError(assessment)

    # Step 2.2a: fixed-destination feasibility. When a fixed end B exists, the
    # routed A→B leg alone must fit inside the walk budget — otherwise no
    # in-budget tour can reach B and the greedy would silently emit a route
    # that never gets there. Compute the routed leg time with the SAME divisor
    # the greedy uses (leg_fn when a routing client is given, else the
    # pace-corrected haversine) — NEVER a straight-line haversine, which would
    # admit across-the-river endpoints no bridge serves. Raise BEFORE the
    # greedy so it propagates on the first flavour through select_k_routes,
    # exactly like RED density. (end is None for open/loop walks — they never
    # enter this branch, so the Step-2.0d invariance baseline is untouched.)
    if input.end is not None:
        leg_cost_fn = leg_fn or default_leg_seconds
        t_ab = leg_cost_fn(start_lat, start_lng, input.end[0], input.end[1])
        budget = planning_budget.walk_budget_seconds
        reachability_ceiling = (
            budget
            if planning_policy.is_legacy
            else planning_budget.maximum_elapsed_seconds
            + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
        )
        if t_ab > reachability_ceiling:
            overshoot_s = t_ab - reachability_ceiling
            gap_minutes = math.ceil(overshoot_s / 60)
            suggested_duration = 1
            if planning_policy.is_legacy:
                suggested_duration = smallest_duration_min_for_walk_seconds(
                    t_ab, planning_policy
                )
            else:
                while (
                    route_planning_budget(
                        suggested_duration, planning_policy
                    ).maximum_elapsed_seconds
                    + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
                    < t_ab
                ):
                    suggested_duration += 1
            alternatives = (
                # Drop B and loop from A at the requested duration.
                FeasibilityAlternative(
                    kind="loop", duration_min=input.duration_min, drop_end=True
                ),
                # Keep B but extend to the smallest duration whose active-time
                # ceiling covers the routed A→B leg.
                FeasibilityAlternative(
                    kind="extend",
                    duration_min=suggested_duration,
                    drop_end=False,
                ),
            )
            # Step 2.2b: when at least one anchor is reachable inside the walk
            # budget, also offer a 'closer_b' pointing at a nearer destination
            # B' — preferring an anchor in the A→B direction (±45° wedge),
            # falling back to the highest-scoring in-budget anchor otherwise.
            # Omitted entirely when no anchor fits the budget.
            closer_b = _closer_b_alternative(
                start_lat=start_lat,
                start_lng=start_lng,
                end_lat=input.end[0],
                end_lng=input.end[1],
                duration_min=input.duration_min,
                interest=interest,
                snapshot=snapshot,
                leg_cost_fn=leg_cost_fn,
                walk_budget=budget,
            )
            if closer_b is not None:
                alternatives = (*alternatives, closer_b)
            raise TourabilityRefusedError(
                assessment,
                (
                    f"Destination unreachable in {input.duration_min} min: routed A→B "
                    f"leg {t_ab}s exceeds reachability ceiling "
                    f"{reachability_ceiling}s by {gap_minutes} min."
                ),
                gap_minutes=gap_minutes,
                alternatives=alternatives,
            )

    # Step 1: REACH (§2.1, M5) — Valhalla walking isochrone replaces the
    # analytic radius (a straight-line circle admits across-the-river POIs no
    # bridge serves). Falls back to the exact haversine envelope when the
    # isochrone is unavailable. Phase 6 also drops 0-active-beat POIs.
    if certification_fixed_end:
        reach_walk_minutes = certification_total_ceiling / 60.0
        radius_m = (
            reach_walk_minutes * PACE_KMH * 1000.0
        ) / 60.0 / HAVERSINE_CORRECTION
        iso_minutes = max(1, math.ceil(reach_walk_minutes))
    else:
        radius_m = envelope_radius_m(
            input.duration_min,
            round_trip=input.round_trip,
            planning_policy=planning_policy,
        )
        iso_minutes = _isochrone_walk_minutes(
            input.duration_min,
            round_trip=input.round_trip,
            walk_minutes=planning_budget.walk_envelope_minutes,
        )
    reach_contains, reach_degraded = _reach_predicate(
        (start_lat, start_lng), radius_m, iso_minutes, routing_client
    )
    # Step 2.3: corridor (time-ellipse) reach filter for fixed-destination
    # walks. When a fixed end B exists, an anchor only earns candidacy if the
    # routed detour through it — A→poi→B — still fits inside the walk budget:
    # ``t(A, poi) + t(poi, B) <= walk_budget_seconds(duration_min)``. This is
    # the two-focus (A, B) ellipse whose string length is the walk budget,
    # measured with the SAME divisor the greedy uses (``leg_fn or
    # default_leg_seconds``) — NEVER straight-line haversine, which would admit
    # across-the-river anchors no bridge serves. ``end is None`` for open/loop
    # walks: ``corridor_admits`` is None and the gate is skipped entirely, so
    # the candidate pool on that path is LITERALLY unchanged (Step-2.0d
    # identity baseline holds).
    corridor_admits = None
    if input.end is not None:
        corridor_leg_fn = leg_fn or default_leg_seconds
        end_lat, end_lng = input.end
        corridor_budget = planning_budget.walk_budget_seconds

        def corridor_admits(lat: float, lng: float) -> bool:
            t_a_poi = corridor_leg_fn(start_lat, start_lng, lat, lng)
            t_poi_b = corridor_leg_fn(lat, lng, end_lat, end_lng)
            return t_a_poi + t_poi_b <= corridor_budget

    # Phase 3 re-baseline (Step 3.5): THE MODEL SWITCH. The hard tier gate
    # (poi.tier not in ANCHOR_TIERS), the walk_by_only exclusion, and the
    # lens-miss exclusion are GONE. Every corridor POI with active beats is now
    # ELIGIBLE; the continuous spotlight score + band decide
    # dwell/vignette/silent. This produces the s3 two-track output:
    #   - silent  : excluded for this user. The ONLY silence is low-gravity AND
    #               off-genre -- per band_for_spotlight that fires solely when a
    #               POI is BOTH below the lens floor (a thematic miss) AND
    #               low-gravity (tier < BAND_LANDMARK_TIER). Lens alone, gravity
    #               alone, or a detour alone never silences a landmark.
    #   - vignette: eligible but not a dwell stop (a tier-low or off-genre POI,
    #               or any walk_by_only POI -- role multiplier 0.0 zeroes its
    #               poi_score so it can never out-rank a real stop). Surfaced as
    #               an on-path one-liner by a downstream step (RouteOptionStop
    #               band="vignette"), NOT inserted into the dwell route here.
    #   - dwell   : a real stop (headline/full/short) -- the greedy/endpoint-
    #               pull/fill draw the ordered route from these.
    # The band is measured on-path (marginal_detour_seconds=0): a detour is an
    # ordering cost, not an eligibility test, and band_for_spotlight already
    # floors any landmark (tier >= BAND_LANDMARK_TIER) at vignette regardless
    # of detour. ``candidates`` below is the DWELL pool the greedy consumes;
    # vignette/silent POIs are deliberately kept out of it so dwell-minute
    # allocation is unchanged in spirit -- gate removal WIDENS which POIs can
    # earn a dwell stop (every tier, every lens), it does not make the route
    # stop everywhere.
    reachable_count = 0
    candidates: list[POI] = []
    # Fixed-end POIs that fail ONLY the ordinary walking-allocation ellipse.
    # They stay out of greedy/ordinary fill, but the elapsed-time rescue may
    # consider them using the exact A→selected→candidate→B routed total.
    corridor_rescue_candidates: list[POI] = []
    filler_stubs: list[tuple[int, POI]] = []  # (audio, poi) for the never-empty guard
    for poi in snapshot.pois:
        in_reach = reach_contains(poi.lat, poi.lng)
        if in_reach:
            reachable_count += 1
        if not in_reach:
            continue
        if not _has_active_beats(poi, snapshot):
            continue  # Phase 6: zero-beat POIs carry no audio -> nothing to say.
        on_path_band = band_for_spotlight(
            spotlight(poi, lenses=interest or None, snapshot=snapshot),
            tier=poi.tier,
        )
        # A LANDMARK (tier >= BAND_LANDMARK_TIER) that a LENS dimmed to vignette
        # stays a DWELL stop — a landmark thin FOR your interest DISCLOSES (via the
        # density/tourability gate), it never vanishes. Without this floor, a
        # lensed thin-area start (e.g. The Sorbonne under dark_history, spotlight
        # 4.0 -> 1.0) collapses every reachable POI to vignette and empties the
        # whole tour, silently dropping a major landmark. band_for_spotlight never
        # takes a landmark below vignette, so this catches exactly the dimmed case.
        lens_dimmed_landmark = poi.tier >= BAND_LANDMARK_TIER and on_path_band == BAND_VIGNETTE
        if (
            not is_dwell_band(on_path_band)
            and not lens_dimmed_landmark
            and not poi.requires_dwell
        ):
            # silent -> excluded entirely; a NON-landmark vignette -> a walk-by, not
            # a dwell stop. Either way it does not enter the greedy's dwell pool.
            continue
        if POI_ROLE_MULTIPLIER.get(poi.poi_role, 0.0) <= 0.0:
            # walk_by_only (and any zero-weight role): an on-path vignette, never
            # a dwell anchor. Its poi_score is 0, so admitting it would let the
            # greedy insert a content-less stop (0 > -inf) -- keep it out of the
            # dwell pool explicitly.
            continue
        if is_container_identity_poi(poi):
            # A POI that IS one of its own areas is not a destination. It was already
            # rejected downstream by choose_discrete_route -- but only AFTER routing,
            # and that guard kills the WHOLE route, so a single such POI in every
            # bounded candidate refused the tour outright with
            # "bounded candidates contain no route with all-discrete stops".
            #
            # That is a genuine contradiction between two live rules:
            # ELIGIBLE_POI_ROLES (density.py) admits poi_role='setting' as stoppable,
            # while choose_discrete_route rejects a setting whose name matches its
            # area. MEASURED 2026-07-26: `Les Halles` is the only Paris POI that is
            # both, and it alone made the 90-min Ile de la Cite preview return 422.
            # Excluding it from the DWELL POOL resolves the contradiction at the
            # right layer -- it stays available as a walk-past vignette, which is
            # what a neighbourhood actually is.
            continue
        if not poi.requires_dwell and _is_filler_stub(poi, snapshot, interest or None):
            # Too thin for a dedicated stop — keep it OUT of the greedy's dwell
            # pool so it surfaces as a walk-by vignette (select_vignettes applies
            # the SAME predicate). Held for the never-empty guard below.
            filler_stubs.append(
                (planned_capped_audio_seconds(poi, snapshot, interest or None, None), poi)
            )
            continue
        if corridor_admits is not None and not corridor_admits(poi.lat, poi.lng):
            # Outside the ordinary walk-allocation ellipse is no longer silent
            # deletion.  The candidate may be useful when the tour is underfilled,
            # but only the elapsed rescue can admit it after pricing the full pinned-B
            # route plus emitted audio against the existing total-time ceiling.
            corridor_rescue_candidates.append(poi)
            continue
        candidates.append(poi)

    certification_candidates = sorted(
        {
            poi.id: poi
            for poi in [*candidates, *corridor_rescue_candidates]
        }.values(),
        key=lambda poi: poi.id,
    )

    # Never empty the tour: if EVERY dwell-eligible POI was a thin filler-stub,
    # keep the richest one as a real stop (a one-stop tour beats a zero-stop tour;
    # the density gate already surfaces thinness). Landmarks are never filler, so
    # this only fires in genuinely thin low-tier areas.
    if not candidates and filler_stubs:
        candidates.append(max(filler_stubs, key=lambda pair: pair[0])[1])

    reach = ReachVerdict(
        mode=(
            "standard"
            if assessment.status == "GREEN"
            else "redirect"
            if assessment.one_way_alternative_destination
            else "ambient"
        ),
        degraded=reach_degraded,
        walk_minutes=iso_minutes,
        reachable_poi_count=reachable_count,
        alternative_destination=assessment.one_way_alternative_destination,
    )

    if not candidates and not (certification_fixed_end and certification_candidates):
        # REACH (the authoritative walkable-POI check) found nothing seatable.
        # The haversine density pre-check can be optimistic at an edge/waterfront
        # start (e.g. on the Brooklyn Bridge: POIs across the East River are
        # inside the straight-line envelope but NOT inside the walking
        # isochrone). Returning a silent 0-stop Route here shipped an empty
        # "tour" for ANY such start in ANY city. Refuse cleanly with the
        # assessment's alternatives, exactly like the density-RED path.
        raise TourabilityRefusedError(
            assessment,
            f"No POIs are reachable on foot within a {input.duration_min}-min walk "
            f"of this start — try a longer duration or a start nearer the density.",
        )

    # Step 2: spine.
    spine = pick_spine_area(start_lat, start_lng, candidates, snapshot)

    # Step 3: greedy with insertion cost.
    walk_budget = planning_budget.walk_budget_seconds
    audio_budget = planning_budget.audio_target_seconds
    max_anchors = min(HARD_ANCHOR_CAP, max(1, input.duration_min // ANCHOR_CAP_DIVISOR))
    if planning_budget.max_stops is not None:
        # A coordinate-only B can materialize as one additional sentinel.  Reserve
        # that slot up front; the bounded repair may use it for a real destination
        # POI when B snaps to one of the selected stops.
        reserved_for_b = 1 if input.end is not None else 0
        max_anchors = min(
            max_anchors,
            max(1, planning_budget.max_stops - reserved_for_b),
        )

    # Reserve some walk budget for the endpoint-pull post-step on one-way
    # routes — otherwise the greedy fills 98% of the budget on tight
    # clusters and silently abandons the pull.
    if certification_fixed_end:
        greedy_walk_budget = certification_total_ceiling
    elif input.round_trip:
        greedy_walk_budget = walk_budget
    else:
        greedy_walk_budget = int(walk_budget * (1.0 - ENDPOINT_PULL_RESERVED_BUDGET_FRACTION))

    selected: list[POI] = []
    # A fixed destination is part of the route from the first planning decision,
    # even when no corpus POI represents it.  Greedy insertion deltas therefore
    # spend the remaining A→B allocation rather than starting from a fictional
    # zero-length open walk.
    consumed_walk = (
        (leg_fn or default_leg_seconds)(start_lat, start_lng, input.end[0], input.end[1])
        if input.end is not None
        else 0
    )
    consumed_audio = 0

    remaining = list(
        certification_candidates
        if certification_fixed_end and not candidates
        else candidates
    )

    # C9 governor (SCOPED to round-trip / open-walk, end is None; A->B keeps the
    # Phase-2 currency + corridor discipline — see _capped_audio): floor-less
    # capped-audio currency. The first-seated POI is the START-ANCHOR
    # (positional, decision 3) and is exempt (allowance None => full accounting);
    # every other stop is capped to the per-stop allowance. The audio break is
    # SUPPRESSED until the route reaches the min(3, d//10) stop floor, so a
    # beat-rich anchor can never collapse the tour to one stop (the abandoned
    # >=2 hard-ceiling refutation).
    allowance = audio_budget // max(1, min(3, input.duration_min // 10))
    count_floor = min(3, input.duration_min // 10)
    exempt_anchor_id: str | None = None
    _capped_memo: dict[tuple[str, bool], int] = {}

    def _capped_audio(cand: POI, *, exempt: bool) -> int:
        key = (cand.id, exempt)
        cached = _capped_memo.get(key)
        if cached is None:
            # Fixed-end A→B emission skips the relative domination governor but
            # still applies the absolute per-stop ceiling.  Selection must count
            # that same capped beat plan: tier dwell proxies can over-credit a
            # thin landmark (for example 300 planned seconds for 125 seconds of
            # material), making both the greedy and fill pass stop while the
            # shipped tour remains below its audio floor.
            if input.end is not None:
                stop_allowance = MAX_DWELL_AUDIO_SECONDS
            else:
                stop_allowance = None if exempt else allowance
            # An EXEMPT anchor is exempt from the GOVERNOR allowance, not from the
            # absolute MAX_DWELL_AUDIO_SECONDS ceiling — build_poi_beat_plans_capped
            # applies that ceiling to every stop including the marquee. Crediting the
            # greedy with UNCAPPED audio made the planner believe a marquee filled far
            # more of the audio target than the tour actually delivers, so it stopped
            # adding stops early — which is why tightening the ceiling alone SHORTENS
            # a tour instead of spreading it over more stops.
            cached = planned_capped_audio_seconds(
                cand, snapshot, interest, stop_allowance
            )
            _capped_memo[key] = cached
        return cached

    while remaining and len(selected) < max_anchors:
        best_candidate: POI | None = None
        best_extra: int = 0
        best_idx: int = 0
        best_value: float = -math.inf

        for cand in remaining:
            if input.end is not None:
                extra, idx = _insertion_cost_with_fixed_end(
                    cand,
                    selected,
                    start_lat=start_lat,
                    start_lng=start_lng,
                    fixed_end=input.end,
                    leg_seconds_fn=leg_fn,
                )
            else:
                extra, idx = insertion_cost_seconds(
                    cand,
                    selected,
                    start_lat=start_lat,
                    start_lng=start_lng,
                    round_trip=input.round_trip,
                    leg_seconds_fn=leg_fn,
                )
            if consumed_walk + extra > greedy_walk_budget:
                continue
            base = poi_score(cand, spine, interest, snapshot, penalty=score_penalty)
            # +1s smoothing prevents division-by-zero on co-located POIs.
            # Phase 7.5: clamp the denominator floor at 1.0 — integer
            # rounding inside ``insertion_cost_seconds`` can yield extra=-1
            # when a candidate sits between two waypoints, which the bare
            # ``extra + 1.0`` would resolve to a divide-by-zero.
            value = base / max(1.0, extra + 1.0)
            # Exact-value ties break on id (matching every other selection
            # path) so the pick never depends on candidate iteration order.
            if value > best_value or (
                value == best_value
                and best_candidate is not None
                and cand.id < best_candidate.id
            ):
                best_value = value
                best_candidate = cand
                best_extra = extra
                best_idx = idx

        if best_candidate is None:
            break

        # Insert at the best position.
        selected.insert(best_idx, best_candidate)
        consumed_walk += best_extra
        # Start-anchor exemption applies ONLY to round-trip / open-walk (end is
        # None): there the first-seated POI is genuinely the start-anchor and may
        # dominate (decision 3). For A->B the first-seated is an INCIDENTAL
        # corridor POI — exempting it would starve the real destination B (which
        # is materialized post-greedy and exempt at EMISSION), so A->B caps every
        # corridor stop.
        if input.end is None and exempt_anchor_id is None:
            exempt_anchor_id = best_candidate.id
        consumed_audio += _capped_audio(
            best_candidate, exempt=best_candidate.id == exempt_anchor_id
        )
        remaining.remove(best_candidate)

        if consumed_audio >= audio_budget and (
            input.end is not None or len(selected) >= count_floor
        ):
            break

    # Step 4: endpoint-pull (one-way only). Force-include a far-envelope POI
    # as the closing anchor so traverses (e.g. Pont Neuf → Île east tip)
    # don't truncate near the start. Re-orders the route end-to-end via
    # insertion-cost optimisation; respects HARD_ANCHOR_CAP and walk budget.
    pulled_endpoint_id: str | None = None
    if input.end is None and not input.round_trip and selected:
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
                key=lambda c: (
                    -poi_score(c, spine, interest, snapshot, penalty=score_penalty),
                    c.id,
                ),
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
                    hard_anchor_cap=planning_budget.max_stops or HARD_ANCHOR_CAP,
                    leg_seconds_fn=leg_fn,
                    score_penalty=score_penalty,
                )
                if pulled is not selected and pulled[-1].id == cand.id:
                    selected = pulled
                    pulled_endpoint_id = cand.id
                    break

    # Phase 7 fill pass — target_audio is a floor. Greedy +
    # endpoint-pull may emit a route well below the audio target when
    # cost-efficient additions run out. Add anchors with a relaxed
    # cost-efficiency threshold until target is met or walk budget is
    # nearly spent. See FILL_PASS_* constants for thresholds.
    rescue_added_ids: list[str] = []
    selected = _apply_fill_pass(
        selected,
        candidates,
        spine=spine,
        interest=interest,
        snapshot=snapshot,
        start_lat=start_lat,
        start_lng=start_lng,
        leg_seconds_fn=leg_fn,
        score_penalty=score_penalty,
        round_trip=input.round_trip,
        walk_budget=walk_budget,
        audio_budget=audio_budget,
        hard_anchor_cap=planning_budget.max_stops or HARD_ANCHOR_CAP,
        capped_audio_fn=_capped_audio,
        exempt_anchor_id=exempt_anchor_id,
        rescue_floor=RESCUE_STOP_FLOOR,
        fixed_end=input.end,
        rescue_candidates=(
            corridor_rescue_candidates
            if planning_policy.is_legacy or certification_fixed_end
            else []
        ),
        rescue_added_ids=rescue_added_ids,
    )

    # A rescue is allowed to trade walking-allocation seconds for useful audio,
    # but never to breach the existing total elapsed ceiling.  Recompute an exact
    # pinned-B Held-Karp route with the shipped capped beat plans and roll back the
    # lowest-value rescue additions deterministically until it fits.  Ordinary
    # greedy/fill selections are untouched; they already obey their tighter walk
    # budgets.
    if input.end is not None and rescue_added_ids:
        elapsed_ceiling = planning_budget.maximum_elapsed_seconds
        rescue_ids = set(rescue_added_ids)
        while True:
            trial_selected, trial_end = _materialize_fixed_end_b(
                selected, end_lat=input.end[0], end_lng=input.end[1]
            )
            trial_selected = held_karp_open(
                trial_selected,
                fixed_start=(start_lat, start_lng),
                fixed_end=trial_end,
                routed_cost_fn=leg_fn,
            )
            trial_route = summarise_route(
                trial_selected,
                start_lat=start_lat,
                start_lng=start_lng,
                round_trip=False,
                duration_min=input.duration_min,
                spine_area=spine,
                routing_client=routing_client,
                planning_policy=planning_policy,
            ).model_copy(update={"fixed_end_poi_id": trial_end.id})
            trial_audio = sum(
                planned_audio_seconds(plan.beats)
                for plan, _ in build_poi_beat_plans_capped(
                    trial_route, snapshot, lenses=interest or None, end_is_none=False
                )
            )
            if trial_route.total_walk_seconds + trial_audio <= elapsed_ceiling:
                break
            removable = [poi for poi in selected if poi.id in rescue_ids]
            if not removable:
                break
            drop = min(
                removable,
                key=lambda poi: (
                    poi_score(poi, spine, interest, snapshot, penalty=score_penalty),
                    poi.id,
                ),
            )
            selected = [poi for poi in selected if poi.id != drop.id]
            rescue_ids.remove(drop.id)

    if not planning_policy.is_legacy:
        selected = _apply_certification_timebox_repair(
            selected,
            certification_candidates if certification_fixed_end else candidates,
            input=input,
            snapshot=snapshot,
            spine=spine,
            interest=interest,
            score_penalty=score_penalty,
            leg_seconds_fn=leg_fn,
            planning_policy=planning_policy,
            planning_budget=planning_budget,
        )

    # Phase 7.5 Fix 3: detect co-located POI pairs in the final selection
    # and demote the smaller-tier of each pair. Demoted POI beats are
    # merged into the host's pool by the harness via Route.demoted_beats.
    selected, demoted_beats = apply_co_located_demotion(selected, snapshot)
    # Belt-and-suspenders against a place loaded twice (same display NAME, distinct
    # id): every dedup path above keys on POI id, and apply_co_located_demotion's
    # tier>=4 + cross-address-token gate can skip a bare same-name twin, so an
    # id-distinct twin would otherwise surface as two adjacent stops (the workbench
    # duplicate-stop bug — the beat-starved copy reads "Walk to the next stop."). Fold
    # twins by NAME here; the dropped twin's beats merge into the survivor. On a clean
    # corpus (globally unique names) this is a strict no-op.
    selected, twin_beats = collapse_name_twins(selected, snapshot)
    for host_id, beats in twin_beats.items():
        demoted_beats[host_id] = demoted_beats.get(host_id, ()) + beats

    # M4 ORDER: exact Held-Karp pass over the final set — the greedy's
    # insertion order is a by-product of selection, not an optimum. A pulled
    # endpoint stays pinned last (if demotion didn't absorb it); round trips
    # optimize the closed tour.
    #
    # Step 2.4: when the request carries a fixed end B, materialize B (HYBRID:
    # snap to the nearest in-corridor selected POI within ~150m, else
    # synthesize a sentinel at B's exact coord and add it to ``selected``) and
    # pin it as ``fixed_end`` so the route literally ends at B. This SUPERSEDES
    # the endpoint-pull-derived fixed_end on the fixed-end path. The end-is-None
    # branch is LITERALLY unchanged (Step-2.0d identity baseline holds).
    fixed_end = None
    if input.end is not None and selected:
        selected, fixed_end = _materialize_fixed_end_b(
            selected, end_lat=input.end[0], end_lng=input.end[1]
        )
    elif pulled_endpoint_id is not None and not input.round_trip:
        fixed_end = next((p for p in selected if p.id == pulled_endpoint_id), None)
    selected = held_karp_open(
        selected,
        fixed_start=(start_lat, start_lng),
        fixed_end=fixed_end,
        round_trip=input.round_trip,
        routed_cost_fn=leg_fn,
    )

    # Never ship a silent 0-stop tour. Even when REACH found candidates, the
    # greedy can seat NONE of them (every reachable anchor's round-trip insertion
    # cost exceeds a tight walk budget — e.g. a short tour from an isolated start),
    # or demotion/collapse can fold the selection to empty. In any city that is an
    # honest refusal, not a served empty route: surface the assessment's
    # alternatives (extend the duration, move the start) like the density-RED path.
    # (A→B has already materialized its pinned end B above, so a fixed-destination
    # tour is never empty here.)
    if not selected:
        raise TourabilityRefusedError(
            assessment,
            f"No POIs could be seated within a {input.duration_min}-min walk of this "
            f"start — try a longer duration or a start nearer the density.",
        )
    route = summarise_route(
        selected,
        start_lat=start_lat,
        start_lng=start_lng,
        round_trip=input.round_trip,
        duration_min=input.duration_min,
        spine_area=spine,
        routing_client=routing_client,
        planning_policy=planning_policy,
    )
    if demoted_beats:
        route = route.model_copy(update={"demoted_beats": demoted_beats})
    route = route.model_copy(update={"reach": reach})
    # C9 governor exempt identity — record which POIs are EXEMPT from the per-stop
    # audio cap so compose and the golden harnesses (which lack the greedy locals,
    # and where pois[0] is NOT the start-anchor after Held-Karp) read the SAME
    # exempt set the greedy used. Additive metadata only; pois/transits/beats are
    # untouched (identity baseline holds bit-for-bit). None on A→B / empty routes.
    # Only persist an anchor id that is ACTUALLY in the final route: the greedy's
    # first-seated exempt_anchor_id can be dropped afterward by co-located demotion
    # (folded into its host), which would otherwise leave start_anchor_poi_id
    # dangling on a POI the route no longer contains. (v4's governor exempts the
    # marquee, computed in-wrapper, so this field is advisory — but keep it
    # consistent for the persisted options_json contract.)
    route_poi_ids = {p.id for p in route.pois}
    anchor_update: dict[str, str | None] = {}
    if exempt_anchor_id is not None and exempt_anchor_id in route_poi_ids:
        anchor_update["start_anchor_poi_id"] = exempt_anchor_id
    if fixed_end is not None and fixed_end.id in route_poi_ids:
        anchor_update["fixed_end_poi_id"] = fixed_end.id
    if anchor_update:
        route = route.model_copy(update=anchor_update)
    if not planning_policy.is_legacy or input.end is not None:
        # Last-line invariant: after materialization, demotion, exact ordering,
        # and final-closing governance, a certification route of ANY shape must
        # remain inside the same frozen band used by repair.  Legacy keeps its
        # historical fixed-end-only over-ceiling guard byte-for-byte below.
        final_audio = sum(
            planned_audio_seconds(plan.beats)
            for plan, _ in build_poi_beat_plans_capped(
                route,
                snapshot,
                lenses=interest or None,
                end_is_none=input.end is None,
            )
        )
        elapsed_ceiling = planning_budget.maximum_elapsed_seconds
        final_elapsed = route.total_walk_seconds + final_audio
        if not planning_policy.is_legacy and not within_planning_timebox(
            final_elapsed, planning_budget
        ):
            raise CertificationPlanningInfeasibleError(
                policy_id=planning_policy.policy_id,
                minimum_elapsed_seconds=planning_budget.minimum_elapsed_seconds,
                maximum_elapsed_seconds=elapsed_ceiling,
                best_elapsed_seconds=final_elapsed,
                reason="post-selection transforms moved the exact route outside the band",
            )
        if planning_policy.is_legacy and final_elapsed > elapsed_ceiling:
            raise TourabilityRefusedError(
                assessment,
                (
                    "Fixed-destination route exceeds the elapsed-time ceiling after "
                    f"final routing: {route.total_walk_seconds}s walk + "
                    f"{final_audio}s capped audio = {final_elapsed}s > "
                    f"{elapsed_ceiling}s."
                ),
            )
    # Track B (Step B.2): attach walk-past vignettes AFTER ordering — the leg
    # geometry is final only now. Additive metadata: ``pois``/``transits`` are
    # untouched (the identity baseline holds bit-for-bit).
    # The snapshot-aware density boundary already performed the one full
    # manifest/materialization validation for this route.  Use the private
    # implementation here so vignette selection stays O(corpus), not another
    # full replay validation.  External callers use the guarded public wrapper.
    vignettes = _select_vignettes_validated(route, snapshot, lenses=interest or None)
    if vignettes:
        route = route.model_copy(update={"vignettes": vignettes})
    # C11a: a GREEN-density pool can still DELIVER thin — audio far under the
    # request (few reachable/affordable dwell POIs, or beat-thin ones) or a
    # single dominating stop. Flag it so the surface discloses "honest but thin"
    # instead of silently reading fully-GREEN. (The engine-side answer to the
    # 2026-07-02 pool-vs-delivered gap; replaces the client-side thin heuristic.)
    if assessment.status == "GREEN":
        # v4: measure the UNCAPPED available content, NOT the governor-capped
        # emission. The governor only moves a dominating stop's overflow into
        # keep-exploring extras (still available to the walker on demand), so a
        # capped tour is not "thin" — its content is all there. Measuring capped
        # audio would flip a healthy tour to a spurious thin banner when the
        # governor fires (the panel's bug-5). This is the original C11a currency.
        delivered_audio = sum(
            planned_capped_audio_seconds(p, snapshot, interest or None, None)
            for p in route.pois
        )
        if (
            delivered_audio < GREEN_THIN_DELIVERY_FRAC * assessment.target_audio_seconds
            or len(route.pois) < 2
        ):
            assessment = assessment.model_copy(update={"delivered_thin": True})
    return _attach_tourability_if_yellow(route, assessment)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def select_k_routes(
    input: TourInput,
    snapshot: CorpusSnapshot,
    k: int = 3,
    *,
    routing_client: RoutingClient | None = None,
    planning_policy: RoutePlanningPolicy = LEGACY_ROUTE_PLANNING_POLICY,
) -> list[Route]:
    """§2.2 k flavours (M6): up to ``k`` distinct stop sets, each
    independently ordered (M4) and routed (M2/M3).

    select_route is the k=1 delegate. Each additional flavour re-runs the
    greedy with every already-used POI's score multiplied by
    DIVERSITY_PENALTY; a candidate whose stop set shares
    >= JACCARD_OVERLAP_MAX (Jaccard) with any kept flavour receives one bounded
    stricter rerun in which already-used POIs score zero. If that result still
    overlaps, the search ends. RED density raises TourabilityRefusedError on the
    first run, exactly like select_route.
    """
    if k < 1:
        return []
    first = select_route(
        input,
        snapshot,
        routing_client=routing_client,
        planning_policy=planning_policy,
    )
    flavours = [first]
    if not first.pois:
        return flavours  # empty route: nothing to diversify against

    strict_exclusion = False
    while len(flavours) < k:
        used = {p.id for f in flavours for p in f.pois}
        penalty = dict.fromkeys(used, 0.0 if strict_exclusion else DIVERSITY_PENALTY)
        try:
            cand = select_route(
                input,
                snapshot,
                routing_client=routing_client,
                score_penalty=penalty,
                planning_policy=planning_policy,
            )
        except CertificationPlanningInfeasibleError:
            # Flavours after the first are optional product choices. A penalty
            # can make an alternate unable to satisfy certification even when
            # the unpenalized primary is valid; preserve that primary instead
            # of turning optional diversity into a total-tour refusal.
            break
        if not cand.pois:
            break
        cand_ids = {p.id for p in cand.pois}
        overlaps = any(
            _jaccard(cand_ids, {p.id for p in f.pois}) >= JACCARD_OVERLAP_MAX
            for f in flavours
        )
        if overlaps and not strict_exclusion:
            strict_exclusion = True
            continue
        if overlaps:
            break
        flavours.append(cand)
        strict_exclusion = False
    return flavours


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
            # A materialized off-site story is valid only at its canonical
            # destination.  Post-selection demotion must never move it back to
            # an address/name-derived host.
            if a.requires_dwell or b.requires_dwell:
                continue
            if (
                a.canonical_place_id is not None
                and b.canonical_place_id is not None
                and a.canonical_place_id != b.canonical_place_id
            ):
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
        # Fold beats into the ULTIMATE survivor, never an intermediate host that is
        # itself demoted (a 3-way chain would otherwise orphan a POI's whole content:
        # nothing ever reads demoted_beats for a POI that left the route).
        survivor_id = _resolve_demotion_host(host_id, demoted_to_host)
        beats = snapshot.beats_for(demoted_id)
        demoted_beats[survivor_id] = demoted_beats.get(survivor_id, ()) + tuple(beats)
    return new_selected, demoted_beats


def _resolve_demotion_host(host_id: str, demoted_to_host: dict[str, str]) -> str:
    """Follow a co-located demotion host-chain to its ultimate survivor — a host that
    is not itself demoted. With 3+ co-located POIs the pairwise picks can chain
    (A→B, B→C), so A's beats must land on C, not on the demoted intermediate B.
    Cycle-safe via ``seen`` (``_pick_demotion_host`` is antisymmetric, so cycles
    cannot form) — kept for parity with ``_resolve_twin_host``."""
    seen: set[str] = set()
    while host_id in demoted_to_host and host_id not in seen:
        seen.add(host_id)
        host_id = demoted_to_host[host_id]
    return host_id


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


def _has_cross_poi_address_overlap(a: POI, b: POI, snapshot: CorpusSnapshot) -> bool:
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
    return {t for t in tokens if len(t) >= _NAME_TOKEN_MIN_LEN and t not in _NAME_GENERIC_TOKENS}


# Two selected POIs sharing a display name within this radius are one place loaded
# twice (a data twin), not two distinct places — the corpus keeps names globally
# unique, so this only ever fires on duplicated data.
NAME_TWIN_PROXIMITY_M = 250.0


def _pick_twin_host(a: POI, b: POI) -> tuple[POI, POI]:
    """(host, dropped) for a same-name twin pair — keep the richer / higher-tier /
    lower-id one so the choice is deterministic and content is preserved."""
    if a.beat_count != b.beat_count:
        return (a, b) if a.beat_count > b.beat_count else (b, a)
    if a.tier != b.tier:
        return (a, b) if a.tier > b.tier else (b, a)
    return (a, b) if a.id < b.id else (b, a)


def _resolve_twin_host(host_id: str, dropped_to_host: dict[str, str]) -> str:
    """Follow a twin host-chain to its ultimate survivor — a host that is not itself
    dropped. With 3+ same-name twins the pairwise picks can chain (A→C, C→B), so a
    dropped twin's beats must land on B, not the dropped intermediate C. Cycle-safe
    via ``seen`` (``_pick_twin_host`` is antisymmetric, so cycles cannot form)."""
    seen: set[str] = set()
    while host_id in dropped_to_host and host_id not in seen:
        seen.add(host_id)
        host_id = dropped_to_host[host_id]
    return host_id


def collapse_name_twins(
    selected: list[POI],
    snapshot: CorpusSnapshot,
) -> tuple[list[POI], dict[str, tuple[BeatRef, ...]]]:
    """Collapse selected POIs that share a display NAME into one (name-keyed dedup).

    Returns ``(selected_minus_twins, host_id -> merged_twin_beats)``. Two POIs are
    twins when their names match (case-insensitive, trimmed) and they sit within
    ``NAME_TWIN_PROXIMITY_M``. This catches a place loaded twice (same name, distinct
    id) that id-based dedup and the tier-/address-gated co-located demotion both miss.
    The dropped twin's beats fold into the survivor so no content is lost.

    No-op when the route is empty or every selected name is unique — the clean-corpus
    case — so a well-formed tour is never perturbed.
    """
    if len(selected) < 2:
        return list(selected), {}

    def _norm(name: str) -> str:
        return (name or "").strip().casefold()

    dropped_to_host: dict[str, str] = {}
    for i in range(len(selected)):
        a = selected[i]
        if a.id in dropped_to_host:
            continue
        for j in range(i + 1, len(selected)):
            b = selected[j]
            if b.id in dropped_to_host:
                continue
            if a.requires_dwell or b.requires_dwell:
                continue
            # A shared display name is not identity.  Once both records carry
            # canonical IDs, only equal IDs may collapse; nearby distinct
            # places remain separate.
            if (
                a.canonical_place_id is not None
                and b.canonical_place_id is not None
                and a.canonical_place_id != b.canonical_place_id
            ):
                continue
            if _norm(a.name) != _norm(b.name):
                continue
            if haversine_m(a.lat, a.lng, b.lat, b.lng) > NAME_TWIN_PROXIMITY_M:
                continue
            host, drop = _pick_twin_host(a, b)
            dropped_to_host[drop.id] = host.id

    if not dropped_to_host:
        return list(selected), {}

    new_selected = [p for p in selected if p.id not in dropped_to_host]
    merged: dict[str, tuple[BeatRef, ...]] = {}
    for drop_id, host_id in dropped_to_host.items():
        # Fold beats into the ULTIMATE survivor, never an intermediate host that is
        # itself dropped (a 3-way chain would otherwise orphan a twin's beats).
        survivor_id = _resolve_twin_host(host_id, dropped_to_host)
        merged[survivor_id] = merged.get(survivor_id, ()) + tuple(snapshot.beats_for(drop_id))
    return new_selected, merged


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
    capped_audio_fn: Callable[..., int],
    exempt_anchor_id: str | None,
    rescue_floor: int = 0,
    leg_seconds_fn: LegSecondsFn | None = None,
    score_penalty: dict[str, float] | None = None,
    fixed_end: tuple[float, float] | None = None,
    rescue_candidates: list[POI] | None = None,
    rescue_added_ids: list[str] | None = None,
) -> list[POI]:
    """Phase 7: fill until audio floor is met or walk budget hits 95%.

    Score-first ranking (not score / cost) so we keep adding genuinely
    rich anchors at the price of a higher walk cost. Stops when:
      - delivered audio (dwell-seconds proxy)
        >= ``FILL_PASS_AUDIO_FLOOR_FRAC x audio_budget``;
      - cumulative walk would exceed
        ``FILL_PASS_WALK_BUDGET_FRAC x walk_budget``;
      - route hits ``hard_anchor_cap``;
      - no remaining candidate fits.

    Insertions go through ``insertion_cost_seconds`` so the route stays
    geometrically sane. The post-endpoint-pull last-anchor (one-way
    routes) is preserved by clamping insertion idx to interior positions
    when the route already has ≥2 stops on a one-way path.

    #21 UNDER-FILL RESCUE: in a thin area the greedy can seat only one stop
    because a second stop's round-trip detour busts ``walk_budget`` — even
    though the tour massively under-delivers AUDIO (e.g. a 60-min Latin Quarter
    loop seating only Sorbonne: 6 min audio, 15 min walk). While the route is
    BELOW ``count_floor`` stops, a further stop is admitted when its MARGINAL
    walk cost is proportional to the audio it delivers (``extra <=
    RESCUE_MAX_WALK_PER_AUDIO x cand_audio``): a rich nearby stop is seated, a
    far/thin walk-slog is not. A tour that ALREADY meets the audio floor returns
    early (below), so an audio-rich few-stop tour (e.g. the PdV golden, whose
    beat-heavy stops clear the floor) is never expanded — only the genuine
    under-fill is; and a multi-stop tour (Île, ≥ rescue_floor) is never touched.
    """
    if not selected or not candidates:
        return selected

    floor_audio = audio_budget * FILL_PASS_AUDIO_FLOOR_FRAC
    walk_cap = int(walk_budget * FILL_PASS_WALK_BUDGET_FRAC)

    consumed_audio = sum(
        capped_audio_fn(p, exempt=p.id == exempt_anchor_id) for p in selected
    )
    if consumed_audio >= floor_audio:
        return selected  # already met; no fill needed

    consumed_walk = _full_route_walk_seconds(
        selected,
        start_lat=start_lat,
        start_lng=start_lng,
        round_trip=round_trip,
        leg_seconds_fn=leg_seconds_fn,
        fixed_end=fixed_end,
    )

    selected_ids = {p.id for p in selected}
    pool = [c for c in candidates if c.id not in selected_ids]
    pool.sort(key=lambda c: (-poi_score(c, spine, interest, snapshot, penalty=score_penalty), c.id))

    def _insertion(cand: POI, sel: list[POI]) -> tuple[int, int]:
        if fixed_end is not None:
            return _insertion_cost_with_fixed_end(
                cand,
                sel,
                start_lat=start_lat,
                start_lng=start_lng,
                fixed_end=fixed_end,
                leg_seconds_fn=leg_seconds_fn,
            )
        extra, idx = insertion_cost_seconds(
            cand, sel, start_lat=start_lat, start_lng=start_lng,
            round_trip=round_trip, leg_seconds_fn=leg_seconds_fn,
        )
        # One-way with ≥2 stops: never insert after the endpoint-pulled last anchor.
        if (not round_trip) and len(sel) >= 2 and idx >= len(sel):
            idx = len(sel) - 1
            extra = _insertion_extra_at_index(
                cand, sel, idx, start_lat=start_lat, start_lng=start_lng,
                round_trip=round_trip, leg_seconds_fn=leg_seconds_fn,
            )
        return extra, idx

    # Phase 1 — the original within-walk_cap fill (unchanged): add rich anchors
    # while there is genuine walk slack. This alone reaches the stop floor for
    # any area where a nearby second stop fits the budget.
    if consumed_walk < walk_cap:
        for cand in pool:
            if len(selected) >= hard_anchor_cap or consumed_audio >= floor_audio:
                break
            extra, idx = _insertion(cand, selected)
            if consumed_walk + extra > walk_cap:
                continue
            selected = [*selected[:idx], cand, *selected[idx:]]
            consumed_walk += extra
            consumed_audio += capped_audio_fn(cand, exempt=False)

    # Phase 2 — #21 under-fill rescue: ONLY if Phase 1 could not reach the stop
    # floor (a thin area where every next stop's detour busts walk_cap). Lift to
    # RESCUE_STOP_FLOOR by seating a stop whose MARGINAL walk is proportional to
    # the audio it delivers (rich nearby stop in, far/thin walk-slog out). Runs on
    # top of Phase 1, so it never displaces a within-budget stop Phase 1 chose.
    move_ceiling = walk_budget / WALK_FRACTION if WALK_FRACTION else float("inf")
    if rescue_floor > 0 and (len(selected) < rescue_floor or consumed_audio < floor_audio):
        seated = {p.id for p in selected}
        rescue_pool_by_id = {cand.id: cand for cand in pool}
        for cand in rescue_candidates or ():
            rescue_pool_by_id.setdefault(cand.id, cand)
        rescue_pool = sorted(
            rescue_pool_by_id.values(),
            key=lambda cand: (
                -poi_score(cand, spine, interest, snapshot, penalty=score_penalty),
                cand.id,
            ),
        )
        for cand in rescue_pool:
            if cand.id in seated or len(selected) >= hard_anchor_cap:
                continue
            if len(selected) >= rescue_floor and consumed_audio >= floor_audio:
                break
            # LENS FIDELITY. A landmark the lens DIMMED to vignette is kept in the
            # pool by the lens_dimmed_landmark floor so it never vanishes from the
            # tour — but it belongs as a walk-past MENTION, not a dwell stop. The
            # rescue must not promote it: asking for dark_history and being made to
            # stand in front of an off-genre POI is exactly the failure the band
            # logic exists to prevent.
            if interest and not is_dwell_band(
                band_for_spotlight(
                    poi_score(cand, spine, interest, snapshot, penalty=score_penalty),
                    tier=cand.tier,
                )
            ):
                continue
            extra, idx = _insertion(cand, selected)
            cand_audio = capped_audio_fn(cand, exempt=False)
            if extra > RESCUE_MAX_WALK_PER_AUDIO * cand_audio:
                continue
            # MOVE CEILING: walking + listening is the tourist's real elapsed time.
            # Cap it at the engine's own err-short total, or filling to the audio
            # floor produces a route needing 67.7 min for a 60-min request.
            if consumed_walk + extra + consumed_audio + cand_audio > move_ceiling:
                continue
            selected = [*selected[:idx], cand, *selected[idx:]]
            consumed_walk += extra
            consumed_audio += cand_audio
            seated.add(cand.id)
            if rescue_added_ids is not None:
                rescue_added_ids.append(cand.id)

    return selected


def _isochrone_walk_minutes(
    duration_min: int,
    *,
    round_trip: bool,
    walk_minutes: float | None = None,
) -> int:
    """The walking-time contour REACH asks Valhalla for.

    Mirrors envelope_radius_m's derivation: the err-short walk budget in
    minutes, halved for round trips (out-and-back reach).
    """
    walk_min = (
        route_planning_budget(duration_min).walk_envelope_minutes
        if walk_minutes is None
        else walk_minutes
    )
    return max(1, round(walk_min / 2.0 if round_trip else walk_min))


# A real pedestrian isochrone covers a meaningful slice of the walk envelope; a
# real Paris 30-min iso is ~5 km² (≈2x the haversine circle), while a tile-less
# Valhalla returns a degenerate ~0.03 km² near-point. Require the iso to cover at
# least this fraction of the haversine-envelope circle, else it is degenerate and
# REACH falls back to the analytic envelope. 0.25 sits ~7x below a real iso and
# ~20x above a degenerate one — a wide, safe margin.
ISO_MIN_AREA_FRACTION: float = 0.25


def _reach_predicate(
    start: tuple[float, float],
    radius_m: float,
    iso_minutes: int,
    routing_client: RoutingClient | None,
):
    """(contains(lat, lng), degraded) — the REACH membership test (§2.1).

    Primary: point-in-polygon against the Valhalla walking isochrone
    (prepared shapely geometry; GeoJSON rings are (lng, lat)). Fallback —
    no client, isochrone refused, or unparseable geometry — is the exact
    pre-M5 haversine envelope with ``degraded=True``.
    """
    if routing_client is not None:
        iso = routing_client.isochrone(start[0], start[1], iso_minutes)
        if iso is not None:
            try:
                geoms = [
                    _shapely_shape(f["geometry"])
                    for f in iso.get("features", ())
                    if f.get("geometry")
                ]
                if geoms:
                    union = geoms[0]
                    for g in geoms[1:]:
                        union = union.union(g)
                    # Reject a DEGENERATE isochrone. Valhalla with no tiles for
                    # the region (e.g. New York on a Paris-only tileset) can't
                    # snap the origin to an edge and returns a near-point polygon
                    # (~0.03 km² vs the ~5 km² of a real 30-min walk). Trusting it
                    # collapses REACH to the handful of co-located start POIs, so
                    # the greedy seats 1 stop. Fall through to the haversine
                    # envelope when the polygon is implausibly small for the walk.
                    lng_km = 111.0 * math.cos(math.radians(start[0]))
                    iso_area_km2 = union.area * 111.0 * lng_km
                    envelope_area_km2 = math.pi * (radius_m / 1000.0) ** 2
                    if iso_area_km2 >= ISO_MIN_AREA_FRACTION * envelope_area_km2:
                        prepared = _shapely_prep(union)
                        return (
                            lambda lat, lng: bool(prepared.covers(_ShapelyPoint(lng, lat))),
                            False,
                        )
            except (KeyError, TypeError, ValueError, _ShapelyError):
                # Malformed GeoJSON, or shapely GEOS errors on degenerate/
                # self-intersecting isochrone rings (GEOSException derives
                # ShapelyError, not ValueError — pre-2026-07-02 it escaped
                # as a 500) → analytic fallback below.
                pass

    start_lat, start_lng = start
    return (
        lambda lat, lng: haversine_m(start_lat, start_lng, lat, lng) <= radius_m,
        True,
    )


def _memoized_leg_fn(client: RoutingClient) -> LegSecondsFn:
    """Memoized routed leg times for the §3 divisor.

    The greedy, endpoint-pull, and fill pass re-evaluate the same coordinate
    pairs many times per request; with a live Valhalla each unique pair costs
    one HTTP roundtrip, so cache per select_route call. (The client itself
    sticky-degrades to pure math after the first transport failure.)
    """
    cache: dict[tuple[float, float, float, float], int] = {}

    def leg_fn(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
        key = (lat1, lng1, lat2, lng2)
        if key not in cache:
            cache[key] = client.leg_seconds(lat1, lng1, lat2, lng2)
        return cache[key]

    return leg_fn


def _insertion_extra_at_index(
    cand: POI,
    selected: list[POI],
    idx: int,
    *,
    start_lat: float,
    start_lng: float,
    round_trip: bool,
    leg_seconds_fn: LegSecondsFn | None = None,
    fixed_end: tuple[float, float] | None = None,
) -> int:
    """Walk-time delta from inserting `cand` at exactly position `idx`."""
    fn = leg_seconds_fn or default_leg_seconds
    base_coords: list[tuple[float, float]] = [
        (start_lat, start_lng),
        *((p.lat, p.lng) for p in selected),
    ]
    if fixed_end is not None:
        base_coords.append(fixed_end)
    elif round_trip:
        base_coords.append((start_lat, start_lng))
    base = 0
    for (lat1, lng1), (lat2, lng2) in itertools.pairwise(base_coords):
        base += fn(lat1, lng1, lat2, lng2)
    new_pois = [*selected[:idx], cand, *selected[idx:]]
    new_coords: list[tuple[float, float]] = [
        (start_lat, start_lng),
        *((p.lat, p.lng) for p in new_pois),
    ]
    if fixed_end is not None:
        new_coords.append(fixed_end)
    elif round_trip:
        new_coords.append((start_lat, start_lng))
    new_total = 0
    for (lat1, lng1), (lat2, lng2) in itertools.pairwise(new_coords):
        new_total += fn(lat1, lng1, lat2, lng2)
    return new_total - base


def _insertion_cost_with_fixed_end(
    cand: POI,
    selected: list[POI],
    *,
    start_lat: float,
    start_lng: float,
    fixed_end: tuple[float, float],
    leg_seconds_fn: LegSecondsFn | None = None,
) -> tuple[int, int]:
    """Cheapest insertion delta in the pinned chain A→selected→B.

    Unlike the open-walk helper, B contributes to the base route even when it
    has no corpus POI.  Equal deltas keep the earliest insertion index, making
    the result independent of candidate iteration order.
    """
    best_extra = math.inf
    best_idx = 0
    for idx in range(len(selected) + 1):
        extra = _insertion_extra_at_index(
            cand,
            selected,
            idx,
            start_lat=start_lat,
            start_lng=start_lng,
            round_trip=False,
            leg_seconds_fn=leg_seconds_fn,
            fixed_end=fixed_end,
        )
        if extra < best_extra:
            best_extra = extra
            best_idx = idx
    return int(best_extra), best_idx


def _full_route_walk_seconds(
    pois: list[POI],
    *,
    start_lat: float,
    start_lng: float,
    round_trip: bool,
    leg_seconds_fn: LegSecondsFn | None = None,
    fixed_end: tuple[float, float] | None = None,
) -> int:
    fn = leg_seconds_fn or default_leg_seconds
    coords: list[tuple[float, float]] = [(start_lat, start_lng)]
    coords.extend((p.lat, p.lng) for p in pois)
    if fixed_end is not None:
        coords.append(fixed_end)
    elif round_trip:
        coords.append((start_lat, start_lng))
    total = 0
    for (lat1, lng1), (lat2, lng2) in itertools.pairwise(coords):
        total += fn(lat1, lng1, lat2, lng2)
    return total


@dataclass(frozen=True)
class _CertificationRouteTrial:
    selected: tuple[POI, ...]
    ordered: tuple[POI, ...]
    walk_seconds: int
    audio_seconds: int

    @property
    def elapsed_seconds(self) -> int:
        return self.walk_seconds + self.audio_seconds


def _certification_route_trial(
    selected: list[POI],
    *,
    input: TourInput,
    snapshot: CorpusSnapshot,
    interest: frozenset[str],
    leg_seconds_fn: LegSecondsFn | None,
    planning_budget: RoutePlanningBudget,
) -> _CertificationRouteTrial | None:
    """Price one stop set in the exact routed/capped certification currency."""

    if not selected and input.end is None:
        return None
    materialized = list(selected)
    fixed_end: POI | None = None
    if input.end is not None:
        materialized, fixed_end = _materialize_fixed_end_b(
            materialized, end_lat=input.end[0], end_lng=input.end[1]
        )
    if planning_budget.max_stops is None or len(materialized) > planning_budget.max_stops:
        return None
    ordered = held_karp_open(
        materialized,
        fixed_start=input.start,
        fixed_end=fixed_end,
        round_trip=input.round_trip,
        routed_cost_fn=leg_seconds_fn,
    )
    walk_seconds = _full_route_walk_seconds(
        ordered,
        start_lat=input.start[0],
        start_lng=input.start[1],
        round_trip=input.round_trip,
        leg_seconds_fn=leg_seconds_fn,
    )
    route = Route(
        pois=tuple(ordered),
        transits=(),
        total_walk_distance_m=0.0,
        total_walk_seconds=walk_seconds,
        fixed_end_poi_id=fixed_end.id if fixed_end is not None else None,
    )
    audio_seconds = sum(
        planned_audio_seconds(plan.beats)
        for plan, _ in build_poi_beat_plans_capped(
            route,
            snapshot,
            lenses=interest or None,
            end_is_none=input.end is None,
        )
    )
    return _CertificationRouteTrial(
        selected=tuple(selected),
        ordered=tuple(ordered),
        walk_seconds=walk_seconds,
        audio_seconds=audio_seconds,
    )


def _apply_certification_timebox_repair(
    selected: list[POI],
    candidates: list[POI],
    *,
    input: TourInput,
    snapshot: CorpusSnapshot,
    spine: str | None,
    interest: frozenset[str],
    score_penalty: dict[str, float] | None,
    leg_seconds_fn: LegSecondsFn | None,
    planning_policy: RoutePlanningPolicy,
    planning_budget: RoutePlanningBudget,
) -> list[POI]:
    """Bounded add/exchange repair for one frozen certification policy.

    Only the already-eligible ordinary candidate pool is considered, so the
    pass cannot waive lens, role, REACH, or fixed-B corridor rules.  Each trial
    is exactly ordered and priced with routed walk plus the same whole-beat cap
    emission uses.  Structural glue and observations are deliberately absent:
    neither is a legitimate source of duration padding.
    """

    if planning_budget.max_stops is None:
        raise ValueError("certification repair requires an authorized stop cap")

    base = _certification_route_trial(
        selected,
        input=input,
        snapshot=snapshot,
        interest=interest,
        leg_seconds_fn=leg_seconds_fn,
        planning_budget=planning_budget,
    )
    preferred_trials: list[_CertificationRouteTrial] = []
    last_resort_trials: list[_CertificationRouteTrial] = []
    observed: list[int] = []

    def consider(
        trial_selected: list[POI],
        *,
        added: POI | None = None,
        reference_walk_seconds: int | None = None,
    ) -> None:
        trial = _certification_route_trial(
            trial_selected,
            input=input,
            snapshot=snapshot,
            interest=interest,
            leg_seconds_fn=leg_seconds_fn,
            planning_budget=planning_budget,
        )
        if trial is None:
            return
        observed.append(trial.elapsed_seconds)
        if trial.elapsed_seconds > (
            planning_budget.maximum_elapsed_seconds
            + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
        ):
            return
        ratio_exceeded = False
        if added is not None and reference_walk_seconds is not None:
            # Price the candidate against the route *without that candidate*.
            # For an exchange, comparing against the original incumbent route
            # can hide a pure walk-slog whenever the removed incumbent was an
            # even larger detour.
            marginal_walk = max(0, trial.walk_seconds - reference_walk_seconds)
            added_audio = planned_capped_audio_seconds(
                added,
                snapshot,
                interest or None,
                MAX_DWELL_AUDIO_SECONDS,
            )
            ratio_exceeded = (
                marginal_walk > RESCUE_MAX_WALK_PER_AUDIO * max(1, added_audio)
            )
        if within_planning_timebox(trial.elapsed_seconds, planning_budget):
            target = last_resort_trials if ratio_exceeded else preferred_trials
            target.append(trial)

    consider(list(selected))
    selected_ids = {poi.id for poi in selected}
    pool = sorted(
        (candidate for candidate in candidates if candidate.id not in selected_ids),
        key=lambda poi: (
            -poi_score(poi, spine, interest, snapshot, penalty=score_penalty),
            poi.id,
        ),
    )
    if base is not None and len(base.ordered) < planning_budget.max_stops:
        for candidate in pool:
            consider(
                [*selected, candidate],
                added=candidate,
                reference_walk_seconds=base.walk_seconds,
            )
    for incumbent in sorted(selected, key=lambda poi: poi.id):
        retained = [poi for poi in selected if poi.id != incumbent.id]
        retained_trial = _certification_route_trial(
            retained,
            input=input,
            snapshot=snapshot,
            interest=interest,
            leg_seconds_fn=leg_seconds_fn,
            planning_budget=planning_budget,
        )
        reference_walk_seconds = (
            retained_trial.walk_seconds if retained_trial is not None else 0
        )
        for candidate in pool:
            consider(
                [*retained, candidate],
                added=candidate,
                reference_walk_seconds=reference_walk_seconds,
            )

    eligible_trials = preferred_trials or last_resort_trials
    if not eligible_trials:
        bounded = [
            value
            for value in observed
            if value
            <= planning_budget.maximum_elapsed_seconds
            + TIMEBOX_MATERIALITY_TOLERANCE_SECONDS
        ]
        best = max(bounded) if bounded else (min(observed) if observed else None)
        raise CertificationPlanningInfeasibleError(
            policy_id=planning_policy.policy_id,
            minimum_elapsed_seconds=planning_budget.minimum_elapsed_seconds,
            maximum_elapsed_seconds=planning_budget.maximum_elapsed_seconds,
            best_elapsed_seconds=best,
            reason="no eligible non-slog add or one-for-one exchange reaches the TIME band",
        )

    def rank(trial: _CertificationRouteTrial) -> tuple[float, float, tuple[str, ...]]:
        score = sum(
            poi_score(poi, spine, interest, snapshot, penalty=score_penalty)
            for poi in trial.selected
        )
        return (
            abs(planning_budget.nominal_elapsed_seconds - trial.elapsed_seconds),
            -score,
            tuple(sorted(poi.id for poi in trial.selected)),
        )

    return list(min(eligible_trials, key=rank).selected)


# Endpoint-pull will drop at most this many incumbents to make room for
# the far-envelope endpoint. Larger values can collapse the route to one
# anchor (the endpoint alone); two preserves the spine-anchor cluster
# while still letting one weak incumbent give way for an east-tip pick.
# NOTE: the drop count alone does NOT preserve the cluster when the
# greedy could only seat <= MAX_DROPS incumbents (structural for 60-min
# one-way tours, whose greedy sees only 75% of the walk budget) — that
# is the 2026-07-02 Rue Cler collapse, where a 39-beat far anchor
# evicted the entire route. _apply_endpoint_pull therefore also refuses
# to drop the last incumbent: a route consisting solely of the pulled
# endpoint is not a tour.
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
    leg_seconds_fn: LegSecondsFn | None = None,
    score_penalty: dict[str, float] | None = None,
) -> list[POI]:
    """Insert `endpoint` as the closing stop, dropping at most
    ENDPOINT_PULL_MAX_DROPS weak incumbents to fit walk-budget +
    anchor-cap. If the endpoint can't be made to fit within those drops,
    return the input unchanged (greedy result wins).
    """
    incumbents = list(selected)
    drops_used = 0
    while True:
        if (
            len(incumbents) + 1 > hard_anchor_cap
            and incumbents
            and drops_used < ENDPOINT_PULL_MAX_DROPS
        ):
            incumbents = _drop_weakest(incumbents, spine, interest, snapshot, score_penalty)
            drops_used += 1
            continue

        if len(incumbents) + 1 > hard_anchor_cap:
            return list(selected)  # endpoint won't fit under cap with allowed drops

        # M4: order the trial route exactly (replaces the greedy
        # best-insertion `_reorder_with_endpoint`), endpoint pinned last.
        candidate_route = held_karp_open(
            [*incumbents, endpoint],
            fixed_start=(start_lat, start_lng),
            fixed_end=endpoint,
            routed_cost_fn=leg_seconds_fn,
        )
        walk = _route_walk_seconds(
            candidate_route,
            start_lat=start_lat,
            start_lng=start_lng,
            leg_seconds_fn=leg_seconds_fn,
        )
        if walk <= walk_budget:
            return candidate_route
        if len(incumbents) <= 1 or drops_used >= ENDPOINT_PULL_MAX_DROPS:
            # Bounded drops exhausted — or the next drop would evict the
            # LAST incumbent, leaving [endpoint] alone. A one-stop route
            # of just the pulled endpoint is a collapse, not a tour
            # (2026-07-02 Rue Cler regression): abandon the pull and let
            # the greedy result stand.
            return list(selected)
        incumbents = _drop_weakest(incumbents, spine, interest, snapshot, score_penalty)
        drops_used += 1


def _drop_weakest(
    pois: list[POI],
    spine: str | None,
    interest: frozenset[str],
    snapshot: CorpusSnapshot,
    score_penalty: dict[str, float] | None = None,
) -> list[POI]:
    weakest = min(
        pois, key=lambda p: (poi_score(p, spine, interest, snapshot, penalty=score_penalty), p.id)
    )
    return [p for p in pois if p.id != weakest.id]


def _route_walk_seconds(
    pois: list[POI],
    *,
    start_lat: float,
    start_lng: float,
    leg_seconds_fn: LegSecondsFn | None = None,
) -> int:
    fn = leg_seconds_fn or default_leg_seconds
    coords = [(start_lat, start_lng), *((p.lat, p.lng) for p in pois)]
    total = 0
    for (lat1, lng1), (lat2, lng2) in itertools.pairwise(coords):
        total += fn(lat1, lng1, lat2, lng2)
    return total


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
    ≥2x the more-specific area to keep the spine. Districts naturally
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
            if snapshot.area_types.get(a, "") in SPECIFIC_AREA_TYPES and votes[a] >= threshold
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

    Used only when the 2x district lift hasn't already chosen a winner —
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
    *,
    penalty: dict[str, float] | None = None,
) -> float:
    """The §3 per-POI score: importance x richness x lens_relevance x alignment x role.

    M6: ``penalty`` (poi_id → factor) is the k-flavours diversity knob —
    POIs already used by kept flavours score lower on re-runs.

    Phase 3 re-baseline (Step 3.5): the lens factor is now the POSITIVE-floored
    ``lens_relevance`` (miss -> LENS_FLOOR = 0.25), NOT the legacy hard-filter
    ``_lens_adjacency`` (miss -> 0.0). This is the second half of the model
    switch: with the candidate-pool lens gate removed, a lens-miss POI is
    eligible, so its score must DIM rather than ZERO -- otherwise the greedy
    would still never pick it and a tier-5 off-genre landmark would silently
    drop out (violating "lens alone never silences a landmark", s3). The
    objective stays strictly multiplicative (s9.5); only the lens factor's
    miss value changed from 0.0 to a positive floor. With no lenses requested
    both functions return 1.0, so the unlensed objective is byte-identical.
    """
    importance = float(poi.tier)
    richness = math.log1p(max(0, poi.beat_count))
    relevance = lens_relevance(poi, lenses=interest or None, snapshot=snapshot)
    alignment = _area_alignment(poi, spine_area, snapshot)
    role_mult = POI_ROLE_MULTIPLIER.get(poi.poi_role, 0.0)
    diversity = penalty.get(poi.id, 1.0) if penalty else 1.0
    return importance * richness * relevance * alignment * role_mult * diversity


def _lens_adjacency(poi: POI, interest: frozenset[str], snapshot: CorpusSnapshot) -> float:
    """§3 hop model over the POI's active beat lenses (M3, replaces _interest_bias).

    1.0 when any beat lens directly matches a requested lens; 0.6 when any
    beat lens is one IS_PARENT_OF hop from a requested lens (parent or
    child); 0.0 otherwise. No requested lenses → uniform 1.0 so selection
    degrades gracefully to importance x richness x alignment x role.
    """
    relation = _lens_relation(poi, interest, snapshot)
    if relation == "no_lens" or relation == "direct":
        return LENS_ADJACENCY_DIRECT
    if relation == "one_hop":
        return LENS_ADJACENCY_ONE_HOP
    return LENS_ADJACENCY_MISS


def _lens_relation(
    poi: POI, interest: frozenset[str], snapshot: CorpusSnapshot
) -> str:
    """Classify a POI's relation to the requested lenses (shared §3 logic).

    Returns one of ``"no_lens"`` (no lenses requested), ``"direct"`` (a beat
    lens directly matches a requested lens), ``"one_hop"`` (a beat lens is one
    IS_PARENT_OF hop — parent OR child — from a requested lens), or
    ``"miss"`` (neither). This is the single source of truth for the
    direct/1-hop/miss decision: both the legacy ``_lens_adjacency`` (hard
    filter, miss → 0.0) and the new ``lens_relevance`` (spotlight floor,
    miss → LENS_FLOOR) map these labels onto their own weights, so the two
    can never drift apart on classification.
    """
    if not interest:
        return "no_lens"
    interest_low = {s.lower() for s in interest}
    neighbors: set[str] = set()
    for lens in interest_low:
        neighbors |= snapshot.lens_neighbors.get(lens, frozenset())
    one_hop = False
    for beat in snapshot.beats_for(poi.id):
        for lens in beat.lenses:
            lens_low = lens.lower()
            if lens_low in interest_low:
                return "direct"
            if lens_low in neighbors:
                one_hop = True
    return "one_hop" if one_hop else "miss"


# ---------------------------------------------------------------------------
# §3 spotlight model (Phase 3) — pure scoring, ADDITIVE (no selection change)
# ---------------------------------------------------------------------------


def gravity(tier: int) -> float:
    """Gravity ∝ importance_tier (1..5) — the §3 'how much it pulls' factor.

    Monotonic (strictly increasing) in tier, reusing the SAME linear tier
    weighting ``poi_score`` already applies (``importance = float(poi.tier)``)
    so the spotlight stays consistent with the existing objective. A tier-5
    landmark pulls 5x a tier-1 footnote. Always > 0 for valid tiers (1..5).
    """
    return float(tier)


def lens_relevance(
    poi: POI, *, lenses: frozenset[str] | None, snapshot: CorpusSnapshot
) -> float:
    """§3 lens_relevance — a POSITIVE-FLOORED genre factor (never a gate).

    - 1.0 on a direct lens hit,
    - 0.6 on a parent/child 1-hop via ``snapshot.lens_neighbors``,
    - LENS_FLOOR (0.25) on a miss — a miss DIMS, it never zeroes,
    - 1.0 (uniform) when ``lenses`` is None/empty.

    Shares its direct/1-hop/miss classification with ``_lens_adjacency`` via
    ``_lens_relation`` — the ONLY difference is the miss maps to LENS_FLOOR
    here instead of 0.0. Because the floor is strictly positive, lens alone
    can never silence a POI; only the combined spotlight (low gravity AND a
    miss) can drop one below an output band (§3).
    """
    interest = lenses or frozenset()
    relation = _lens_relation(poi, interest, snapshot)
    if relation == "no_lens":
        return LENS_RELEVANCE_NO_LENS
    if relation == "direct":
        return LENS_RELEVANCE_DIRECT
    if relation == "one_hop":
        return LENS_RELEVANCE_ONE_HOP
    return LENS_FLOOR


def proximity(marginal_detour_seconds: float = 0.0) -> float:
    """§3 proximity — the on-path bonus, decaying with marginal detour.

    1.0 when the POI is exactly on the A-B line (``marginal_detour_seconds``
    == 0) and exponentially decaying as the routed detour off that line grows:
    ``exp(-marginal_detour_seconds / PROXIMITY_DECAY_SECONDS)``. The decay is
    strictly monotonically decreasing in detour and ALWAYS > 0, so proximity
    alone never zeroes a POI (preserving the §3 silence invariant). Negative
    detours (a POI that shortens the route — rare, from integer routing
    rounding) are clamped to 0 so proximity caps at 1.0.
    """
    detour = max(0.0, marginal_detour_seconds)
    return math.exp(-detour / PROXIMITY_DECAY_SECONDS)


def spotlight(
    poi: POI,
    *,
    lenses: frozenset[str] | None,
    snapshot: CorpusSnapshot,
    marginal_detour_seconds: float = 0.0,
) -> float:
    """§3 continuous spotlight score = gravity x lens_relevance x proximity.

    PURE and ADDITIVE — this Step 3.1 function does NOT touch select_route's
    selection (the tier/lens gates stay until Step 3.5). It scores how much of
    the user's time and audio a POI earns; downstream steps map the score onto
    output bands (headline / full / short / vignette / silent).

    All three factors are ≥ 0 (the §9.5 multiplicative-objective invariant),
    and gravity is > 0 for any valid tier while lens_relevance is ≥ LENS_FLOOR
    > 0 and proximity is > 0 — so the spotlight of any real POI is strictly
    positive. A lens miss merely DIMS it (xLENS_FLOOR); the silence band is a
    downstream threshold decision, not a zero here.
    """
    return (
        gravity(poi.tier)
        * lens_relevance(poi, lenses=lenses, snapshot=snapshot)
        * proximity(marginal_detour_seconds)
    )


def band_for_spotlight(spotlight_score: float, *, tier: int) -> str:
    """§3 band classifier — map a spotlight score (+ POI tier) to an output band.

    Returns one of ``"headline"`` | ``"full"`` | ``"short"`` | ``"vignette"`` |
    ``"silent"``. The dwell bands (headline/full/short) are a real stop; the
    vignette band is one line as you pass; ``"silent"`` means excluded for this
    user. Use ``is_dwell_band`` / ``DWELL_BANDS`` for the output-facing collapse.

    PURE and ADDITIVE — this does NOT touch select_route's selection (the
    tier/lens gates stay until Step 3.5). Thresholds are INITIAL anchors
    (BAND_THRESHOLD_*), refined in the Step 3.5 golden re-baseline.

    The §3 silence invariant is encoded STRUCTURALLY, not as a bare score
    threshold: silence requires BOTH a lens miss AND low gravity. A high-gravity
    landmark (``tier >= BAND_LANDMARK_TIER``) is therefore floored at
    ``vignette`` even if a large proximity detour drove its score below the
    silent cut -- "lens alone never silences a landmark on the user's path"
    (and a detour alone never does either). Only a genuinely low-gravity,
    off-genre POI (low tier whose score fell below BAND_THRESHOLD_VIGNETTE)
    goes silent.
    """
    if spotlight_score >= BAND_THRESHOLD_HEADLINE:
        return BAND_HEADLINE
    if spotlight_score >= BAND_THRESHOLD_FULL:
        return BAND_FULL
    if spotlight_score >= BAND_THRESHOLD_SHORT:
        return BAND_SHORT
    if spotlight_score >= BAND_THRESHOLD_VIGNETTE:
        return BAND_VIGNETTE
    # Below the vignette cut. A high-gravity landmark never goes silent on
    # score alone -- floor it at vignette (the §3 invariant). Only a
    # low-gravity POI that also missed on lens (the joint condition that
    # produced this low score) is truly silent.
    if tier >= BAND_LANDMARK_TIER:
        return BAND_VIGNETTE
    return BAND_SILENT


def is_dwell_band(band: str) -> bool:
    """Output-facing collapse: True for a dwell stop (headline/full/short).

    ``vignette`` is a walk-past line (not a dwell stop); ``silent`` is
    excluded. Both return False.
    """
    return band in DWELL_BANDS


# ---------------------------------------------------------------------------
# Track B (Step B.1) — walk-past vignette selection along the legs
# ---------------------------------------------------------------------------


def _point_to_segment_m(
    lat: float, lng: float, a_lat: float, a_lng: float, b_lat: float, b_lng: float
) -> float:
    """Perpendicular distance (m) from a point to the A→B straight segment.

    Local equirectangular projection around the segment's mean latitude —
    accurate to well under a metre at the sub-kilometre scales a walking leg
    spans, and fully deterministic. Points beyond the segment's endpoints
    measure to the nearest endpoint (it is a SEGMENT, not an infinite line).
    """
    lat0 = math.radians((a_lat + b_lat) / 2.0)
    kx = math.cos(lat0) * EARTH_RADIUS_M
    ky = EARTH_RADIUS_M

    ax, ay = math.radians(a_lng) * kx, math.radians(a_lat) * ky
    bx, by = math.radians(b_lng) * kx, math.radians(b_lat) * ky
    px, py = math.radians(lng) * kx, math.radians(lat) * ky

    dx, dy = bx - ax, by - ay
    seg_len_sq = dx * dx + dy * dy
    if seg_len_sq <= 0.0:
        return math.hypot(px - ax, py - ay)  # degenerate (co-located) leg
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def select_vignettes(
    route: Route,
    snapshot: CorpusSnapshot,
    lenses: frozenset[str] | None = None,
) -> dict[int, tuple[POI, ...]]:
    """Guarded external boundary for walk-past vignette selection."""

    require_materialized_snapshot(snapshot, operation="vignette selection")
    return _select_vignettes_validated(route, snapshot, lenses)


def _select_vignettes_validated(
    route: Route,
    snapshot: CorpusSnapshot,
    lenses: frozenset[str] | None = None,
) -> dict[int, tuple[POI, ...]]:
    """Track B Step B.1 — pure walk-past vignette selection along the legs.

    Returns ``leg_idx → vignette POIs`` where leg ``i`` is the walk INTO stop
    ``i``, matching ``route.transits`` indexing. Locked rules (Track B,
    IMPLEMENTATION-PLAN deferred clarifications):

    - eligible iff the POI's on-path band is exactly ``vignette``
      (``band_for_spotlight(spotlight(...), tier=poi.tier)``); dwell-band
      POIs are real-stop material, silent POIs stay excluded;
    - within ``VIGNETTE_MAX_DETOUR_M`` (perpendicular) of the leg's straight
      segment;
    - never a dwell stop of this route;
    - deduped across legs — the first (earliest) leg that EMITS a POI wins; a
      candidate merely cut by the cap on an earlier leg stays available;
    - capped at ``VIGNETTE_MAX_PER_LEG`` per leg;
    - deterministic order: spotlight descending, then id.

    One engine invariant joins the locked rules: a POI with no active beats
    has nothing to voice (the Phase 6 zero-beat rule that keeps such POIs out
    of the dwell pool), so it never becomes a vignette either — the band
    tagging in ``select_route`` only ever fires on active-beat POIs.

    Only legs BETWEEN two route POIs are considered: the Route contract does
    not carry the start coordinate, so leg 0 (start → first stop) and a round
    trip's closing leg (last stop → start) have no computable geometry here
    and never yield vignettes.
    """
    pois = route.pois
    if len(pois) < 2:
        return {}
    dwell_ids = {p.id for p in pois}

    scored: list[tuple[float, POI]] = []
    for poi in snapshot.pois:
        if poi.id in dwell_ids:
            continue
        if not poi.vignette_eligible or poi.requires_dwell:
            continue
        if not _has_active_beats(poi, snapshot):
            continue
        score = spotlight(poi, lenses=lenses or None, snapshot=snapshot)
        # Vignette-band POIs are walk-bys by score; ALSO route a demoted
        # filler-stub here (a dwell-band POI too thin for a dedicated stop — the
        # same predicate the dwell-pool filter used, so generate/compose agree).
        if band_for_spotlight(score, tier=poi.tier) != BAND_VIGNETTE and not _is_filler_stub(
            poi, snapshot, lenses
        ):
            continue
        scored.append((score, poi))
    if not scored:
        return {}
    # Deterministic candidate ranking: spotlight desc, then id.
    scored.sort(key=lambda pair: (-pair[0], pair[1].id))

    out: dict[int, tuple[POI, ...]] = {}
    assigned: set[str] = set()
    for leg_idx in range(1, len(pois)):
        a, b = pois[leg_idx - 1], pois[leg_idx]
        picked: list[POI] = []
        for _score, poi in scored:
            if len(picked) >= VIGNETTE_MAX_PER_LEG:
                break
            if poi.id in assigned:
                continue
            dist = _point_to_segment_m(poi.lat, poi.lng, a.lat, a.lng, b.lat, b.lng)
            if dist > VIGNETTE_MAX_DETOUR_M:
                continue
            picked.append(poi)
        if picked:
            out[leg_idx] = tuple(picked)
            assigned.update(p.id for p in picked)
    return out


def _area_alignment(poi: POI, spine_area: str | None, snapshot: CorpusSnapshot) -> float:
    if spine_area is None:
        return AREA_ALIGNMENT_OTHER  # neutral
    if spine_area in poi.areas:
        return AREA_ALIGNMENT_SPINE
    adjacent = snapshot.adjacent_areas.get(spine_area, frozenset())
    if any(a in adjacent for a in poi.areas):
        return AREA_ALIGNMENT_ADJACENT
    return AREA_ALIGNMENT_OTHER




def _has_active_beats(poi: POI, snapshot: CorpusSnapshot) -> bool:
    """True iff the POI has at least one active beat in the snapshot.

    Phase 5 Tour 4 selected Petit Palais (tier 4) as a stop with zero
    beats because routing-aware scoring liked the corridor geometry.
    The fix: filter the candidate pool by beat count before scoring.
    """
    return any((beat.active_status or "active") == "active" for beat in snapshot.beats_for(poi.id))


def _attach_tourability_if_yellow(route: Route, assessment: TourabilityAssessment) -> Route:
    """Attach the assessment to the Route for surface-side disclosure.

    Attached when YELLOW, OR (C11a) when GREEN-but-delivered-thin. A fully-GREEN
    route that delivers richly carries NO tourability field — its absence signals
    "no warning needed". RED tours never reach this code path (raised earlier).
    """
    if assessment.status == "YELLOW" or assessment.delivered_thin:
        return route.model_copy(update={"tourability": assessment})
    return route


__all__ = [
    "CLOSER_B_WEDGE_HALF_ANGLE_DEG",
    "HAVERSINE_CORRECTION",
    "LENS_FLOOR",
    "PACE_KMH",
    "PROXIMITY_DECAY_SECONDS",
    "VIGNETTE_MAX_DETOUR_M",
    "VIGNETTE_MAX_PER_LEG",
    "CorpusSnapshot",
    "MaterializedCorpusSnapshot",
    "bearing",
    "gravity",
    "in_wedge",
    "lens_relevance",
    "load_paris_corpus",
    "pick_spine_area",
    "poi_score",
    "proximity",
    "require_materialized_snapshot",
    "select_route",
    "select_vignettes",
    "spotlight",
]
