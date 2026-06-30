"""Trip generation routes — run the tour engine (src/tour) and persist itineraries."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import Driver, Session

from src.api.crud.trips import (
    create_trip_with_stops,
    list_trips_for_profile,
    route_script_to_stops,
)
from src.api.dependencies import get_driver, get_session
from src.api.models.trips import (
    GeneratedStop,
    TripGenerateRequest,
    TripGenerateResponse,
    TripPreviewRequest,
    TripPreviewResponse,
    TripPreviewStop,
)
from src.tour.beat_select import select_poi_beats
from src.tour.contract import BeatSequence, TourInput
from src.tour.density import TourabilityRefusedError
from src.tour.generation import generate
from src.tour.options import build_route_option
from src.tour.render_md import stop_narration_text
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_k_routes, select_route

router = APIRouter(tags=["trips"])

# TourInput.duration_min is required; the request field is optional for
# back-compat with pre-engine clients that never sent it.
DEFAULT_DURATION_MIN = 60


def _end_point(end_lat: float | None, end_lng: float | None) -> tuple[float, float] | None:
    """Fixed-destination (lat, lng) B for TourInput.end, or None when unset.

    Both coordinates must be present to form an endpoint; a lone end_lat or
    end_lng is treated as no endpoint (TourInput.end stays None — the
    end=None identity path is unchanged).
    """
    if end_lat is None or end_lng is None:
        return None
    return (end_lat, end_lng)


def _refusal_detail(exc: TourabilityRefusedError) -> dict:
    """Structured 422 body from a Step-2.2 feasibility/density refusal.

    Shape (mirrors the FeasibilityAlternative NamedTuple from src/tour/density.py):
        {reason, gap_minutes, alternatives: [{kind, duration_min, drop_end,
                                              poi_id, lat, lng}, ...]}
    gap_minutes is None for plain density-RED refusals (no fixed destination);
    alternatives is [] there too. For a fixed-destination overshoot it carries
    the routed-leg gap and the loop/extend/closer_b alternatives (closer_b
    includes its target poi_id/lat/lng).
    """
    return {
        "reason": str(exc),
        "gap_minutes": exc.gap_minutes,
        "alternatives": [
            {
                "kind": alt.kind,
                "duration_min": alt.duration_min,
                "drop_end": alt.drop_end,
                "poi_id": alt.poi_id,
                "lat": alt.lat,
                "lng": alt.lng,
            }
            for alt in exc.alternatives
        ],
    }


def _resolve_lenses(session: Session, body: TripGenerateRequest) -> list[str] | None:
    """Lens precedence: request -> profile PREFERS_LENS -> None (engine unbiased).

    Profile lens names are sorted so the engine input is deterministic
    regardless of edge-traversal order. A computed per-city default starter
    set is a future feature (see ondoway-lens-defaults-spec.md); until it
    exists, a no-lens profile runs the engine without lens bias.
    """
    if body.lenses:
        return body.lenses
    records = session.run(
        "MATCH (p:Profile {id: $pid})-[:PREFERS_LENS]->(l:Lens) RETURN l.name AS name",
        pid=body.profile_id,
    )
    names = sorted(r["name"] for r in records)
    return names or None


def _lens_display_map(session: Session, lens_names: set[str]) -> dict[str, str]:
    """Map lens name -> display_label (falling back to the name) for the given lenses."""
    if not lens_names:
        return {}
    records = session.run(
        "MATCH (l:Lens) WHERE l.name IN $names "
        "RETURN l.name AS name, coalesce(l.display_label, l.name) AS display",
        names=sorted(lens_names),
    )
    return {r["name"]: r["display"] for r in records}


def _primary_beat_audio(session: Session, beat_ids: list[str]) -> dict[str, dict]:
    """Per primary beat: script_body/audio_url/audio_duration_sec for the response.

    Mirrors what list_trips_for_profile reads for a stop's primary beat, so the
    generate response keeps the pre-engine contract (mobile skips audio
    generation when audio_url is already populated).
    """
    ids = [b for b in beat_ids if b]
    if not ids:
        return {}
    records = session.run(
        "MATCH (b:NarrativeBeat) WHERE b.id IN $ids "
        "RETURN b.id AS id, b.script_body AS script_body, b.audio_url AS audio_url, "
        "b.duration_sec AS audio_duration_sec",
        ids=ids,
    )
    return {
        r["id"]: {
            "script_body": r["script_body"],
            "audio_url": r["audio_url"],
            "audio_duration_sec": r["audio_duration_sec"],
        }
        for r in records
    }


@router.post("/trips/generate", response_model=TripGenerateResponse, status_code=201)
def generate_trip(
    body: TripGenerateRequest,
    session: Session = Depends(get_session),
    driver: Driver = Depends(get_driver),
):
    """Generate a trip by running the tour engine end to end.

    Pipeline: load_paris_corpus -> select_route (density gate: RED refusal
    -> 422) -> select_poi_beats per route POI -> generate (deterministic
    mock glue) -> route_script_to_stops -> persist Trip + ItineraryItems.

    M0b scope notes:
    - `radius_m`, `max_stops`, and `kid_friendly_only` are accepted for
      request back-compat but are inert: the engine derives its own walk
      radius and stop count from `duration_min`.
    - The Script's narration (sentence stream) is not persisted or returned;
      it belongs to the COMPOSE/audio milestone. The validation report that
      `generate` attaches is non-blocking here for the same reason.
    """
    profile_check = session.run(
        "MATCH (p:Profile {id: $pid}) RETURN p.id AS id",
        pid=body.profile_id,
    ).single()
    if profile_check is None:
        raise HTTPException(404, f"Profile '{body.profile_id}' not found")

    lenses = _resolve_lenses(session, body)

    tour_input = TourInput(
        start=(body.center_lat, body.center_lng),
        duration_min=body.duration_min or DEFAULT_DURATION_MIN,
        city_slug="paris",
        lenses=lenses,
        round_trip=body.round_trip,
        end=_end_point(body.end_lat, body.end_lng),
    )

    snapshot = load_paris_corpus(driver, city_slug=tour_input.city_slug)
    try:
        # M2/M3: the client supplies routed leg costs + polylines when the
        # local Valhalla container is up; with it down every call falls back
        # to haversine instantly. M6: up to 3 diverse flavours; flavours[0]
        # is the trip that persists.
        with RoutingClient() as routing_client:
            flavours = select_k_routes(tour_input, snapshot, 3, routing_client=routing_client)
        route = flavours[0]
    except TourabilityRefusedError as exc:
        raise HTTPException(422, _refusal_detail(exc)) from exc

    # A non-RED assessment can still yield an empty route (e.g. YELLOW by fill
    # ratio with no tier-3+ anchor candidates). Refuse before persisting —
    # never create a zero-stop Trip.
    if not route.pois:
        raise HTTPException(
            422,
            "No tourable POIs reachable from this start for the requested duration.",
        )

    # Per flavour: beat plan (merging beats demoted into a host POI — same
    # sequence as scripts/tour_build.py) and Script. scripts[0] drives the
    # persisted trip; every flavour becomes a RouteOption.
    scripts = []
    for flavour in flavours:
        plans = []
        for poi in flavour.pois:
            beats = list(snapshot.beats_for(poi.id))
            beats.extend(flavour.demoted_beats.get(poi.id, ()))
            plans.append(select_poi_beats(poi, beats, interest_lenses=lenses))
        scripts.append(generate(BeatSequence(poi_beats=tuple(plans)), flavour, tour_input))
    script = scripts[0]

    beats_by_id = {ref.id: ref for refs in snapshot.beats_by_poi.values() for ref in refs}
    stops = route_script_to_stops(script.selected_pois, beats_by_id, body.start_time, script=script)

    trip_name = body.trip_name or f"Trip ({body.start_date})"
    result = create_trip_with_stops(
        session,
        trip_name=trip_name,
        profile_id=body.profile_id,
        start_date=body.start_date,
        end_date=body.end_date,
        stops=stops,
    )

    display_map = _lens_display_map(session, {s["lens_name"] for s in stops if s["lens_name"]})
    audio_by_beat = _primary_beat_audio(session, [s["primary_beat_id"] for s in stops])
    # Walking leg INTO each stop (transits[i] arrives at pois[i]); response-only
    # in M2 — not persisted on ItineraryItem until routing runs in production.
    polyline_by_poi = {t.to_poi_id: t.polyline for t in route.transits if t.to_poi_id}
    stops_out = [
        GeneratedStop(
            sort_order=s["sort_order"],
            poi_id=s["poi_id"],
            poi_name=s["poi_name"],
            lat=s["lat"],
            lng=s["lng"],
            beat_id=s["primary_beat_id"],
            beat_ids=s["beat_ids"],
            lens_name=s["lens_name"],
            lens_display=display_map.get(s["lens_name"]) if s["lens_name"] else None,
            duration_min=s["duration_min"],
            importance_tier=s["importance_tier"],
            start_time=s["start_time"],
            dwell_seconds=s["dwell_seconds"],
            transit_polyline=polyline_by_poi.get(s["poi_id"]),
            **audio_by_beat.get(s["primary_beat_id"], {}),
        )
        for s in stops
    ]
    total_duration = sum(s["duration_min"] for s in stops)
    anchor_count = sum(1 for s in stops if s["importance_tier"] == 5)

    options = [
        build_route_option(
            flavour, fl_script, beats_by_id, route_id=f"{result['trip_id']}-opt{i + 1}"
        )
        for i, (flavour, fl_script) in enumerate(zip(flavours, scripts, strict=True))
    ]

    return TripGenerateResponse(
        trip_id=result["trip_id"],
        trip_name=result["trip_name"],
        profile_id=body.profile_id,
        total_stops=len(stops),
        total_duration_min=total_duration,
        anchor_count=anchor_count,
        flavour_count=len(stops) - anchor_count,
        lens_coverage=script.lens_coverage,
        stops=stops_out,
        options=options,
    )


@router.post("/trips/preview", response_model=TripPreviewResponse)
def preview_trip(
    body: TripPreviewRequest,
    driver: Driver = Depends(get_driver),
):
    """Web-first preview (Phase 1.5): run the engine and return per-stop narration
    WITHOUT a profile and WITHOUT persisting a Trip/ItineraryItem.

    Lets a web surface (the preview page; later the workbench) show the assembled
    story fast. Audio is fetched per stop by the client via POST /audio/preview on
    each stop's narration text. RED density / no reachable POIs -> 422.
    """
    tour_input = TourInput(
        start=(body.center_lat, body.center_lng),
        duration_min=body.duration_min or DEFAULT_DURATION_MIN,
        city_slug="paris",
        lenses=body.lenses or None,
        round_trip=body.round_trip,
        end=_end_point(body.end_lat, body.end_lng),
    )
    snapshot = load_paris_corpus(driver, city_slug=tour_input.city_slug)
    try:
        with RoutingClient() as routing_client:
            route = select_route(tour_input, snapshot, routing_client=routing_client)
    except TourabilityRefusedError as exc:
        raise HTTPException(422, _refusal_detail(exc)) from exc

    if not route.pois:
        raise HTTPException(
            422,
            "No tourable POIs reachable from this start for the requested duration.",
        )

    plans = []
    for poi in route.pois:
        beats = list(snapshot.beats_for(poi.id))
        beats.extend(route.demoted_beats.get(poi.id, ()))
        plans.append(select_poi_beats(poi, beats, interest_lenses=tour_input.lenses))
    script = generate(BeatSequence(poi_beats=tuple(plans)), route, tour_input)
    per_stop = stop_narration_text(script)

    stops = [
        TripPreviewStop(
            sort_order=i + 1,
            poi_name=sp.name,
            lat=sp.lat,
            lng=sp.lng,
            narration=per_stop.get(i, ""),
            minutes=round(sp.dwell_seconds / 60),
            # Phase 3 spotlight model (spec s7). Default band/spotlight until
            # Step 3.5 wires the spotlight effect into selection.
            band="dwell",
            spotlight=0.0,
        )
        for i, sp in enumerate(script.selected_pois)
    ]
    return TripPreviewResponse(
        spine_area=route.spine_area,
        total_audio_min=round(script.total_audio_seconds / 60),
        stops=stops,
        # Per-corridor lens coverage note ships later in Phase 3 (REACH).
        lens_coverage_note=None,
    )


@router.get("/trips", response_model=list[TripGenerateResponse])
def list_trips(
    profile_id: str = Query(..., description="Profile ID to list trips for"),
    session: Session = Depends(get_session),
):
    """List all saved trips for a profile, including their stops."""
    result = list_trips_for_profile(session, profile_id)
    if result is None:
        raise HTTPException(404, f"Profile '{profile_id}' not found")

    return [
        TripGenerateResponse(
            trip_id=t["trip_id"],
            trip_name=t["trip_name"],
            profile_id=t["profile_id"],
            total_stops=t["total_stops"],
            total_duration_min=t["total_duration_min"],
            anchor_count=t["anchor_count"],
            flavour_count=t["flavour_count"],
            stops=[GeneratedStop(**s) for s in t["stops"]],
        )
        for t in result
    ]
