"""Trip generation routes — run the tour engine (src/tour) and persist itineraries."""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import Driver, Session

from src.api.crud.trips import (
    create_trip_with_stops,
    get_trip_compose_inputs,
    list_trips_for_profile,
    mark_trip_composed,
    replace_trip_stops,
    route_script_to_stops,
)
from src.api.dependencies import (
    get_compose_client,
    get_driver,
    get_faithfulness_checker,
    get_session,
)
from src.api.models.trips import (
    GeneratedStop,
    TripComposeRequest,
    TripComposeResponse,
    TripGenerateRequest,
    TripGenerateResponse,
    TripPreviewRequest,
    TripPreviewResponse,
    TripPreviewStop,
    TripPreviewTourability,
)
from src.tour.beat_select import select_poi_beats, select_vignette_beats
from src.tour.compose import ComposeClient, ComposeRequest, compose_script
from src.tour.compose_gate import ComposeVerificationError
from src.tour.contract import (
    BeatSequence,
    Route,
    Sentence,
    TourabilityAssessment,
    TourInput,
    ValidationReport,
)
from src.tour.density import TourabilityRefusedError
from src.tour.generation import generate, split_sentences
from src.tour.options import build_route_option
from src.tour.render_md import stop_narration_text
from src.tour.routing import summarise_route
from src.tour.routing_client import RoutingClient
from src.tour.selection import (
    build_poi_beat_plans,
    load_paris_corpus,
    pick_spine_area,
    select_k_routes,
    select_route,
    select_vignettes,
)
from src.tour.verify import FaithfulnessChecker

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
    # persisted trip; every flavour becomes a RouteOption. Track B: each
    # flavour's walk-past vignettes get ONE voiceable beat and the stitcher
    # voices the one-liner inside the leg narration.
    scripts = []
    for flavour in flavours:
        plans = build_poi_beat_plans(flavour, snapshot, lenses=lenses)
        vignette_beats = select_vignette_beats(
            flavour.vignettes, snapshot.beats_by_poi, lenses=lenses
        )
        scripts.append(
            generate(
                BeatSequence(poi_beats=tuple(plans), vignette_beats=vignette_beats),
                flavour,
                tour_input,
            )
        )
    script = scripts[0]

    beats_by_id = {ref.id: ref for refs in snapshot.beats_by_poi.values() for ref in refs}
    stops = route_script_to_stops(script.selected_pois, beats_by_id, body.start_time, script=script)

    # Step 4.6: persist the RESOLVED engine input + every flavour's ordered
    # poi ids so /compose rebuilds the user's PICK without re-running
    # selection (corpus/routing drift must never swap the picked route).
    tour_input_json = json.dumps(
        {
            "start": list(tour_input.start),
            "end": list(tour_input.end) if tour_input.end else None,
            "duration_min": tour_input.duration_min,
            "city_slug": tour_input.city_slug,
            "lenses": tour_input.lenses,
            "round_trip": tour_input.round_trip,
            "start_time": body.start_time,
        }
    )
    options_json = json.dumps([[p.id for p in flavour.pois] for flavour in flavours])

    trip_name = body.trip_name or f"Trip ({body.start_date})"
    result = create_trip_with_stops(
        session,
        trip_name=trip_name,
        profile_id=body.profile_id,
        start_date=body.start_date,
        end_date=body.end_date,
        stops=stops,
        tour_input_json=tour_input_json,
        options_json=options_json,
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
            flavour,
            fl_script,
            beats_by_id,
            route_id=f"{result['trip_id']}-opt{i + 1}",
            snapshot=snapshot,
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


class _CountingComposeClient:
    """Records the attempts consumed so the response can report them —
    the gate's fire-once/recompose-once flow stays inside compose_script."""

    def __init__(self, inner: ComposeClient):
        self.inner = inner
        self.attempts = 0

    def compose(
        self, request: ComposeRequest, attempt: int, prev_report: ValidationReport | None
    ) -> tuple[Sentence, ...]:
        self.attempts = attempt
        return self.inner.compose(request, attempt, prev_report)


@router.post("/trips/{trip_id}/compose", response_model=TripComposeResponse)
def compose_trip(
    trip_id: str,
    body: TripComposeRequest,
    session: Session = Depends(get_session),
    driver: Driver = Depends(get_driver),
    compose_client: ComposeClient = Depends(get_compose_client),
    faithfulness_checker: FaithfulnessChecker | None = Depends(get_faithfulness_checker),
):
    """Second step of the preview/compose split (Phase 4 Step 4.7, spec §5).

    Rebuilds the user's PICK from the poi ids persisted at generate time —
    NEVER re-running selection, so corpus/routing drift cannot swap the
    route — then runs the fire-once compose behind the M7 VERIFY gate and
    re-persists the trip's stops with the composed narration (fresh item
    ids, no audio fields). NO TTS here: /audio/generate-trip-stops voices
    the narration afterwards, which by then has passed the gate. A refused
    flavour is a structured 422; the trip is left untouched so the client
    can offer another flavour.
    """
    inputs = get_trip_compose_inputs(session, trip_id)
    if inputs is None:
        raise HTTPException(404, f"Trip '{trip_id}' not found")
    if inputs["composed_route_id"]:
        raise HTTPException(
            409,
            {"reason": "already_composed", "composed_route_id": inputs["composed_route_id"]},
        )
    tour_input_dict, options = inputs["tour_input"], inputs["options"]
    if not tour_input_dict or not options:
        raise HTTPException(
            409,
            {"reason": "missing_compose_inputs", "detail": "trip predates the compose split"},
        )

    match = re.fullmatch(re.escape(trip_id) + r"-opt(\d+)", body.route_id)
    option_n = int(match.group(1)) if match else 0
    if not (1 <= option_n <= len(options)):
        raise HTTPException(404, f"Unknown route_id '{body.route_id}' for trip '{trip_id}'")
    poi_ids = options[option_n - 1]

    tour_input = TourInput(
        start=tuple(tour_input_dict["start"]),
        duration_min=tour_input_dict["duration_min"],
        city_slug=tour_input_dict["city_slug"],
        lenses=tour_input_dict["lenses"],
        round_trip=tour_input_dict["round_trip"],
        end=tuple(tour_input_dict["end"]) if tour_input_dict.get("end") else None,
    )

    snapshot = load_paris_corpus(driver, city_slug=tour_input.city_slug)
    pois_by_id = {p.id: p for p in snapshot.pois}
    missing = [pid for pid in poi_ids if pid not in pois_by_id]
    if missing:
        raise HTTPException(409, {"reason": "corpus_changed", "missing_poi_ids": missing})
    picked = [pois_by_id[pid] for pid in poi_ids]

    spine = pick_spine_area(tour_input.start[0], tour_input.start[1], picked, snapshot)
    with RoutingClient() as routing_client:
        route = summarise_route(
            picked,
            start_lat=tour_input.start[0],
            start_lng=tour_input.start[1],
            round_trip=tour_input.round_trip,
            duration_min=tour_input.duration_min,
            spine_area=spine,
            routing_client=routing_client,
        )

    # Track B: re-tag walk-past vignettes on the rebuilt route (pure fn over
    # the same stop set) so the composed narration voices the one-liners too.
    interest = frozenset(s.lower() for s in (tour_input.lenses or []))
    route = route.model_copy(
        update={"vignettes": select_vignettes(route, snapshot, interest or None)}
    )
    plans = [
        select_poi_beats(poi, list(snapshot.beats_for(poi.id)), interest_lenses=tour_input.lenses)
        for poi in picked
    ]
    vignette_beats = select_vignette_beats(
        route.vignettes, snapshot.beats_by_poi, lenses=tour_input.lenses
    )
    seq = BeatSequence(poi_beats=tuple(plans), vignette_beats=vignette_beats)
    stitched = generate(seq, route, tour_input)

    counting = _CountingComposeClient(compose_client)
    try:
        composed = compose_script(
            stitched, seq, route, client=counting, faithfulness_checker=faithfulness_checker
        )
    except ComposeVerificationError as exc:
        raise HTTPException(
            422,
            {
                "reason": "compose_verification_failed",
                "attempts": exc.attempts,
                "untraceable": len(exc.report.untraceable_sentences),
                "forbidden": len(exc.report.forbidden_phrase_hits),
                "provenance": len(exc.report.provenance_failures),
                "faithfulness": len(exc.report.faithfulness_failures),
            },
        ) from exc

    beats_by_id = {ref.id: ref for refs in snapshot.beats_by_poi.values() for ref in refs}
    stops = route_script_to_stops(
        composed.selected_pois, beats_by_id, tour_input_dict.get("start_time"), script=composed
    )
    item_ids = replace_trip_stops(session, trip_id, stops)
    mark_trip_composed(session, trip_id, body.route_id)

    display_map = _lens_display_map(session, {s["lens_name"] for s in stops if s["lens_name"]})
    stops_out = [
        GeneratedStop(
            sort_order=s["sort_order"],
            stop_id=item_ids[i],
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
            narration=s.get("narration"),
            dwell_seconds=s["dwell_seconds"],
        )
        for i, s in enumerate(stops)
    ]
    return TripComposeResponse(
        trip_id=trip_id,
        route_id=body.route_id,
        attempts=counting.attempts,
        stops=stops_out,
    )


def _preview_stops(script, route: Route, vignette_beats, snapshot) -> list[TripPreviewStop]:
    """Interleave walk-past vignette stops into the preview stop list.

    The vignette on leg ``i`` (the walk INTO dwell stop ``i``) sits right
    BEFORE that dwell stop, mirroring build_route_option's interleave. Its
    card carries the same one-liner the leg narration voices (first sentence
    of its chosen beat) with minutes=0; the dwell stop's narration already
    contains that line inside its leg text.
    """
    from src.tour.selection import spotlight

    lenses_fs = frozenset(script.inputs.lenses or ())
    per_stop = stop_narration_text(script)
    one_liner_by_poi: dict[str, str] = {}
    for beats in vignette_beats.values():
        for beat in beats:
            sentences = split_sentences(beat.script_body or "")
            if sentences:
                one_liner_by_poi[beat.poi_id] = sentences[0]

    out: list[TripPreviewStop] = []
    for i, sp in enumerate(script.selected_pois):
        for poi in route.vignettes.get(i, ()):
            if poi.id not in one_liner_by_poi:
                continue  # no voiceable beat -> not voiced, not shown
            out.append(
                TripPreviewStop(
                    sort_order=len(out) + 1,
                    poi_name=poi.name,
                    lat=poi.lat,
                    lng=poi.lng,
                    narration=one_liner_by_poi[poi.id],
                    minutes=0,
                    band="vignette",
                    spotlight=spotlight(poi, lenses=lenses_fs or None, snapshot=snapshot),
                )
            )
        out.append(
            TripPreviewStop(
                sort_order=len(out) + 1,
                poi_name=sp.name,
                lat=sp.lat,
                lng=sp.lng,
                narration=per_stop.get(i, ""),
                minutes=round(sp.dwell_seconds / 60),
                band="dwell",
                spotlight=0.0,
            )
        )
    return out


def _tourability_payload(
    assessment: TourabilityAssessment | None,
) -> TripPreviewTourability | None:
    """Map the engine's YELLOW assessment onto the preview wire model.

    The engine attaches the assessment only for YELLOW (GREEN carries None,
    RED raised long before a 200). Dropping it here is what made thin-area
    single-stop tours look like silent bugs (hostile-panel finding,
    2026-07-02) — the Phase 6 contract is "generate but WARN"."""
    if assessment is None:
        return None
    return TripPreviewTourability(
        status=assessment.status,  # GREEN (delivered_thin) or YELLOW; RED raised earlier
        delivered_thin=assessment.delivered_thin,
        fill_ratio=round(assessment.fill_ratio, 2),
        anchor_candidates=assessment.anchor_candidate_count,
        reachable_poi_count=assessment.reachable_poi_count,
        max_supportable_duration_min=assessment.max_supportable_duration_min,
        one_way_alternative_destination=assessment.one_way_alternative_destination,
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

    plans = build_poi_beat_plans(route, snapshot, lenses=tour_input.lenses)
    vignette_beats = select_vignette_beats(
        route.vignettes, snapshot.beats_by_poi, lenses=tour_input.lenses
    )
    script = generate(
        BeatSequence(poi_beats=tuple(plans), vignette_beats=vignette_beats),
        route,
        tour_input,
    )

    stops = _preview_stops(script, route, vignette_beats, snapshot)
    return TripPreviewResponse(
        spine_area=route.spine_area,
        total_audio_min=round(script.total_audio_seconds / 60),
        stops=stops,
        # Per-corridor lens coverage note ships later in Phase 3 (REACH).
        lens_coverage_note=None,
        tourability=_tourability_payload(route.tourability),
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
