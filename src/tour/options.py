"""RouteOption assembly — the §2.8 output contract, one per flavour (M6).

Pure functions over engine outputs (Route + Script + the snapshot's beat
refs). The API layer wraps these into responses; M7 fills stop_audio and
the grounded why_this_works.

Phase 3 Step 3.4: populate the spotlight model on the output. Each stop
carries its computed ``spotlight`` score (s3.1) and its collapsed output
``band`` ("dwell" vs "vignette"); the option carries a per-corridor
``lens_coverage_note`` (s3.1) when lenses were requested. This is ANNOTATION
ONLY -- which stops are selected and their ORDER are decided upstream in
select_route by the existing gates, so the Step-2.0d identity baseline is
untouched. Selected (on-corridor) stops score at proximity 1.0 (detour 0),
so spotlight == gravity x lens_relevance, always strictly positive.
"""

from __future__ import annotations

from .contract import POI, BeatRef, Route, RouteOption, RouteOptionStop, Script
from .selection import (
    LENS_FLOOR,
    CorpusSnapshot,
    band_for_spotlight,
    gravity,
    is_dwell_band,
    lens_relevance,
    require_materialized_snapshot,
    spotlight,
)


def dominant_lens(beat_ids: tuple[str, ...], beats_by_id: dict[str, BeatRef]) -> str | None:
    """The most common lens across a stop's beats, or None if no beat is lensed.

    Computed from the beats themselves (BeatRef.lenses) — never fabricated.
    Ties break deterministically by lens name so the result is stable across
    runs. (Moved from the API adapter in M6 so the engine and API share it.)
    """
    counts: dict[str, int] = {}
    for bid in beat_ids:
        ref = beats_by_id.get(bid)
        if ref is None:
            continue
        for lens in ref.lenses:
            counts[lens] = counts.get(lens, 0) + 1
    if not counts:
        return None
    return sorted(counts, key=lambda lname: (-counts[lname], lname))[0]


def build_route_option(
    route: Route,
    script: Script,
    beats_by_id: dict[str, BeatRef],
    *,
    route_id: str,
    snapshot: CorpusSnapshot,
) -> RouteOption:
    """Assemble one flavour's RouteOption from its Route + Script.

    eta_seconds is the honest routed estimate: per-leg routed time when the
    leg was routed (leg_seconds), the pace-corrected haversine otherwise,
    plus every stop's dwell.

    Step 3.4 (s3.1/s7): each stop is annotated with its ``spotlight`` score and
    collapsed output ``band``, and the option carries a per-corridor
    ``lens_coverage_note``. ANNOTATION ONLY -- the stop set and order come from
    select_route's gates upstream; this only describes them. ``snapshot``
    supplies each POI's tier (gravity) and beat lenses (lens_relevance);
    ``script.inputs.lenses`` is the requested genre. Selected stops are
    on-corridor, so proximity is the on-path default (detour 0 -> 1.0) and
    spotlight == gravity x lens_relevance, which is strictly positive.

    Track B (Step B.3): ``route.vignettes`` (leg_idx -> walk-past POIs, leg i
    = the walk INTO stop i) are interleaved as ``band="vignette"`` stops right
    after their leg-origin stop — the vignette on leg i sits between stop i-1
    and stop i (a leg-0 vignette would precede stop 0; a round trip's closing
    leg, index len(stops), would follow the last stop). Dwell stops, their
    order, and eta_seconds are unchanged: a vignette is a walk-past one-liner
    (minutes=0), not a stop with dwell time.
    """
    require_materialized_snapshot(snapshot, operation="route-option assembly")
    roles = {p.id: p.poi_role for p in route.pois}
    pois_by_id: dict[str, POI] = {p.id: p for p in route.pois}
    lenses_fs = frozenset(script.inputs.lenses or ())
    dwell_stops = [
        _build_stop(
            sp,
            poi=pois_by_id.get(sp.id),
            role=roles.get(sp.id, "stop"),
            beats_by_id=beats_by_id,
            lenses=lenses_fs,
            snapshot=snapshot,
        )
        for sp in script.selected_pois
    ]
    interleaved: list[RouteOptionStop] = []
    for i, stop in enumerate(dwell_stops):
        interleaved.extend(
            _vignette_stop(vp, lenses=lenses_fs, snapshot=snapshot)
            for vp in route.vignettes.get(i, ())
        )
        interleaved.append(stop)
    interleaved.extend(
        _vignette_stop(vp, lenses=lenses_fs, snapshot=snapshot)
        for vp in route.vignettes.get(len(dwell_stops), ())
    )
    stops = tuple(interleaved)
    eta_seconds = sum(
        (t.leg_seconds if t.leg_seconds is not None else t.walk_seconds) for t in route.transits
    ) + sum(sp.dwell_seconds for sp in script.selected_pois)

    return RouteOption(
        route_id=route_id,
        stops=stops,
        route_polyline=route.route_polyline,
        eta_seconds=eta_seconds,
        lens_summary=dict(script.lens_coverage),
        flow_score=route.flow_score,
        backtrack_ratio=route.backtrack_ratio,
        degraded=route.reach.degraded if route.reach is not None else False,
        lens_coverage_note=_lens_coverage_note(route.pois, lenses=lenses_fs, snapshot=snapshot),
    )


def _build_stop(
    sp,
    *,
    poi: POI | None,
    role: str,
    beats_by_id: dict[str, BeatRef],
    lenses: frozenset[str],
    snapshot: CorpusSnapshot,
) -> RouteOptionStop:
    """One RouteOptionStop with its Step 3.4 spotlight + band annotation.

    Falls back to gravity-only scoring (no lens dimming) when the POI is not in
    ``route.pois`` -- e.g. a synthesized fixed-end B sentinel that carries no
    beats. The sentinel still gets a positive spotlight from its tier so the
    "every selected stop has a band" invariant holds.
    """
    if poi is not None:
        score = spotlight(poi, lenses=lenses, snapshot=snapshot)
        tier = poi.tier
    else:
        # No corpus POI behind this stop (sentinel). Score on tier alone with a
        # uniform lens factor -- no beats means no lens dimming to apply.
        tier = sp.tier
        score = gravity(tier)
    band = "dwell" if is_dwell_band(band_for_spotlight(score, tier=tier)) else "vignette"
    return RouteOptionStop(
        poi_id=sp.id,
        name=sp.name,
        lat=sp.lat,
        lng=sp.lng,
        lens=dominant_lens(sp.beat_ids, beats_by_id),
        visit_or_walk_past=("walk_past" if role == "walk_by_only" else "visit"),
        minutes=round(sp.dwell_seconds / 60),
        band=band,
        spotlight=score,
    )


def _vignette_stop(
    poi: POI,
    *,
    lenses: frozenset[str],
    snapshot: CorpusSnapshot,
) -> RouteOptionStop:
    """One walk-past vignette as a RouteOptionStop (Track B Step B.3).

    ``band="vignette"``, ``visit_or_walk_past="walk_past"``, ``minutes=0`` —
    a one-liner as you pass, never dwell time. ``spotlight`` is the POI's
    on-path score (the same call select_vignettes banded it with) and
    ``lens`` the dominant lens of its own beats from the snapshot.
    """
    beats = {b.id: b for b in snapshot.beats_for(poi.id)}
    return RouteOptionStop(
        poi_id=poi.id,
        name=poi.name,
        lat=poi.lat,
        lng=poi.lng,
        lens=dominant_lens(tuple(beats), beats),
        visit_or_walk_past="walk_past",
        minutes=0,
        band="vignette",
        spotlight=spotlight(poi, lenses=lenses, snapshot=snapshot),
    )


def _lens_coverage_note(
    pois: tuple[POI, ...],
    *,
    lenses: frozenset[str],
    snapshot: CorpusSnapshot,
) -> str | None:
    """Per-corridor lens density (s3.1): how many route POIs speak to the lens.

    Returns None when no lens was requested (nothing to surface). Otherwise
    counts the route POIs whose beats hit the requested lenses -- a hit is any
    ``lens_relevance`` above the floor (a direct or one-hop match; a miss sits
    at LENS_FLOOR). The note states "N of M places on this route speak to the
    chosen lens(es)" so the user can judge whether to broaden the genre before
    composing (s3.1: REACH measures and surfaces coverage, never silently ships
    an off-tone tour).
    """
    if not lenses:
        return None
    total = len(pois)
    if total == 0:
        return "No places on this route speak to the chosen lens(es)."
    hits = sum(
        1 for p in pois if lens_relevance(p, lenses=lenses, snapshot=snapshot) > LENS_FLOOR
    )
    return f"{hits} of {total} places on this route speak to the chosen lens(es)."
