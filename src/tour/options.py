"""RouteOption assembly — the §2.8 output contract, one per flavour (M6).

Pure functions over engine outputs (Route + Script + the snapshot's beat
refs). The API layer wraps these into responses; M7 fills stop_audio and
the grounded why_this_works.
"""

from __future__ import annotations

from .contract import BeatRef, Route, RouteOption, RouteOptionStop, Script


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
) -> RouteOption:
    """Assemble one flavour's RouteOption from its Route + Script.

    eta_seconds is the honest routed estimate: per-leg routed time when the
    leg was routed (leg_seconds), the pace-corrected haversine otherwise,
    plus every stop's dwell.
    """
    roles = {p.id: p.poi_role for p in route.pois}
    stops = tuple(
        RouteOptionStop(
            poi_id=sp.id,
            name=sp.name,
            lat=sp.lat,
            lng=sp.lng,
            lens=dominant_lens(sp.beat_ids, beats_by_id),
            visit_or_walk_past=(
                "walk_past" if roles.get(sp.id, "stop") == "walk_by_only" else "visit"
            ),
            minutes=round(sp.dwell_seconds / 60),
        )
        for sp in script.selected_pois
    )
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
    )
