"""Trip generation routes — run the tour engine (src/tour) and persist itineraries."""

from __future__ import annotations

import json
import os
import re
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import Driver, Session
from pydantic import ValidationError

from src.api.crud.trips import (
    create_trip_with_stops,
    get_trip_compose_inputs,
    list_trips_for_profile,
    mark_trip_composed,
    replace_trip_stops,
    route_script_to_stops,
)
from src.api.dependencies import (
    get_claim_repetition_judge,
    get_compose_client,
    get_correction_client,
    get_driver,
    get_faithfulness_checker,
    get_omission_checker,
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
from src.tour.beat_select import select_vignette_beats

# check_tour_repetition / repetition_findings are deliberately NOT imported: the G4
# check is dark (see the long comment at its call site in preview_trip). RedundancyJudge
# is still imported for the Depends() signature, which stays so re-enabling is one line.
from src.tour.claim_repetition import RedundancyJudge
from src.tour.compose import (
    ComposeClient,
    ComposeRequest,
    compose_provider_name,
    compose_script,
    compose_script_per_chapter,
    keyless_affected_stops,
)
from src.tour.compose_gate import ComposeVerificationError
from src.tour.contract import (
    BeatSequence,
    Route,
    Script,
    Sentence,
    TourabilityAssessment,
    TourInput,
    ValidationReport,
)
from src.tour.density import TourabilityRefusedError
from src.tour.generation import generate, is_walk_concurrent, vignette_one_liner_text
from src.tour.narration_quality import score_narration
from src.tour.options import build_route_option
from src.tour.quality_rubric import score_tour
from src.tour.routing import summarise_route
from src.tour.routing_client import RoutingClient
from src.tour.selection import (
    build_poi_beat_plans_capped,
    build_poi_extra_beats,
    build_poi_extra_narration,
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


def _build_tour_input(**kwargs) -> TourInput:
    """Construct TourInput, mapping its contract ValidationError to a 422.

    TourInput's model_validator (e.g. _end_round_trip_mutex: end + round_trip
    are mutually exclusive, src/tour/contract.py) raises a pydantic
    ValidationError on a contradictory request. Unhandled, that surfaces as an
    opaque HTTP 500 with a stack trace (app.py registers no ValidationError
    handler). It is a CLIENT error, so translate it to a 422 with the field
    messages the caller needs to correct the request.
    """
    try:
        return TourInput(**kwargs)
    except ValidationError as exc:
        raise HTTPException(
            422,
            {
                "reason": "invalid_tour_input",
                "errors": [
                    {"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()
                ],
            },
        ) from exc


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

    tour_input = _build_tour_input(
        start=(body.center_lat, body.center_lng),
        duration_min=body.duration_min or DEFAULT_DURATION_MIN,
        city_slug=body.city_slug,
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
        # C9 governor v4 seam: caps a dominating stop, overflow -> keep-exploring.
        capped = build_poi_beat_plans_capped(
            flavour, snapshot, lenses=lenses, end_is_none=tour_input.end is None
        )
        plans = tuple(pb for pb, _ in capped)
        overflow_by_poi = {pb.poi_id: ov for pb, ov in capped if ov}
        vignette_beats = select_vignette_beats(
            flavour.vignettes, snapshot.beats_by_poi, lenses=lenses
        )
        scripts.append(
            generate(
                BeatSequence(
                    poi_beats=tuple(plans),
                    vignette_beats=vignette_beats,
                    overflow_by_poi=overflow_by_poi,
                ),
                flavour,
                tour_input,
            )
        )
    script = scripts[0]

    beats_by_id = {ref.id: ref for refs in snapshot.beats_by_poi.values() for ref in refs}
    # KE1: per-stop "keep exploring" extras (un-voiced beats), computed from the
    # SAME merged pool the voiced plan used so they are exactly full-minus-voiced.
    extra_by_poi = build_poi_extra_beats(
        flavours[0],
        snapshot,
        {sp.id: sp.beat_ids for sp in script.selected_pois},
        lenses=lenses,
    )
    stops = route_script_to_stops(
        script.selected_pois, beats_by_id, body.start_time, script=script, extra_by_poi=extra_by_poi
    )

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
    # Per-flavour ordered poi ids PLUS the C9 exempt-anchor identity, so /compose
    # restores the SAME exempt set the greedy used (Held-Karp reorders pois, and
    # the compose-rebuilt route has no greedy locals). Legacy trips stored a bare
    # id list; the compose reader treats those as fail-open (uncapped).
    options_json = json.dumps(
        [
            {
                "poi_ids": [p.id for p in flavour.pois],
                "start_anchor_poi_id": flavour.start_anchor_poi_id,
                "fixed_end_poi_id": flavour.fixed_end_poi_id,
            }
            for flavour in flavours
        ]
    )

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
            extra_beat_ids=s["extra_beat_ids"],
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
    """Records the attempts consumed so the response can report them — the gate's
    fire-once/recompose-once flow stays inside the composer.

    The composer runs one call PER STOP in PARALLEL, so this is written from many
    threads at once. Report the MAX attempt any stop needed (the worst-case round
    trips the gate cost us); a plain last-writer-wins assignment would report an
    arbitrary stop's counter instead. The lock keeps the read-compare-write atomic.
    """

    def __init__(self, inner: ComposeClient):
        self.inner = inner
        self.attempts = 0
        self._lock = threading.Lock()

    def compose(
        self, request: ComposeRequest, attempt: int, prev_report: ValidationReport | None
    ) -> tuple[Sentence, ...]:
        with self._lock:
            self.attempts = max(self.attempts, attempt)
        return self.inner.compose(request, attempt, prev_report)


@router.post("/trips/{trip_id}/compose", response_model=TripComposeResponse)
def compose_trip(
    trip_id: str,
    body: TripComposeRequest,
    session: Session = Depends(get_session),
    driver: Driver = Depends(get_driver),
    compose_client: ComposeClient = Depends(get_compose_client),
    faithfulness_checker: FaithfulnessChecker | None = Depends(get_faithfulness_checker),
    correction_client=Depends(get_correction_client),
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
    entry = options[option_n - 1]
    if isinstance(entry, dict):  # C9f-i per-flavour format: {poi_ids, anchor ids}
        poi_ids = entry["poi_ids"]
        anchor_restore = {
            k: entry[k]
            for k in ("start_anchor_poi_id", "fixed_end_poi_id")
            if entry.get(k) is not None
        }
    else:  # legacy bare id list (trips generated pre-C9f): fail open (uncapped).
        poi_ids = entry
        anchor_restore = {}

    tour_input = _build_tour_input(
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
    # C9f-i: restore the exempt-anchor identity persisted at generate time onto the
    # summarise_route-rebuilt route, so C9f-ii's cap exempts the SAME start-anchor /
    # fixed-end here as it did at generate. Empty for legacy trips -> fail open.
    if anchor_restore:
        route = route.model_copy(update=anchor_restore)
    # C9f-i: compose goes through the SAME shared governor seam as
    # generate/preview (unifies the choke point; the anchor-id restore above lets
    # the cap exempt the marquee at compose too). v4 caps a dominating stop and
    # surfaces its overflow.
    capped = build_poi_beat_plans_capped(
        route, snapshot, lenses=tour_input.lenses, end_is_none=tour_input.end is None
    )
    plans = tuple(pb for pb, _ in capped)
    overflow_by_poi = {pb.poi_id: ov for pb, ov in capped if ov}
    vignette_beats = select_vignette_beats(
        route.vignettes, snapshot.beats_by_poi, lenses=tour_input.lenses
    )
    seq = BeatSequence(
        poi_beats=tuple(plans), vignette_beats=vignette_beats, overflow_by_poi=overflow_by_poi
    )
    stitched = generate(seq, route, tour_input)

    # KNOWN DIVERGENCE (2026-07-19), deliberate and scoped — see
    # specs/2026-07-19-tour-quality-standard/01-standard.md §"Remaining divergence".
    # The WORKBENCH (/trips/preview) runs compose_script_per_chapter with best-of-2 +
    # the corrector. This APP path still runs whole-tour compose_script, so the two
    # surfaces do not narrate identically yet.
    #
    # It was unified and then deliberately reverted, because unifying changes a
    # PERSISTENCE contract, not just prose: whole-tour compose RAISES on verification
    # failure -> HTTP 422 -> the trip is left UNMUTATED and another flavour can be
    # tried. Per-chapter never refuses; it floors to grounded stitch and returns 200,
    # so replace_trip_stops + mark_trip_composed would run on degraded content, and
    # TripComposeResponse carries no compose_status for the app to notice. Closing
    # that gap needs a decided contract (add compose_status, and/or refuse on total
    # degradation), not a silent swap. Tracked, not forgotten.
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
    # KE2: recompute the keep-exploring extras HERE (never trust generate-time
    # values) from the composed script's voiced beats, the SAME way generate does
    # (build_poi_extra_beats over the rebuilt route), so extra_beat_ids stays
    # exactly full-minus-voiced. The extras are curated corpus beats — faithful by
    # construction — so their narration is stitched DETERMINISTICALLY from their
    # script_bodies (build_poi_extra_narration), NOT re-composed through the LLM
    # VERIFY gate: there is nothing freely-composed to entail. The stops carry BOTH
    # extra_beat_ids (via route_script_to_stops) and extra_narration, keyed by poi.
    extra_by_poi = build_poi_extra_beats(
        route,
        snapshot,
        {sp.id: sp.beat_ids for sp in composed.selected_pois},
        lenses=tour_input.lenses,
    )
    extra_narration_by_poi = build_poi_extra_narration(extra_by_poi, snapshot)
    stops = route_script_to_stops(
        composed.selected_pois,
        beats_by_id,
        tour_input_dict.get("start_time"),
        script=composed,
        extra_by_poi=extra_by_poi,
    )
    for stop in stops:
        stop["extra_narration"] = extra_narration_by_poi.get(stop["poi_id"])
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
            extra_beat_ids=s["extra_beat_ids"],
            lens_name=s["lens_name"],
            lens_display=display_map.get(s["lens_name"]) if s["lens_name"] else None,
            duration_min=s["duration_min"],
            importance_tier=s["importance_tier"],
            start_time=s["start_time"],
            narration=s.get("narration"),
            extra_narration=s.get("extra_narration"),
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


def _preview_stops(
    script, route: Route, vignette_beats, snapshot, overflow_by_poi
) -> list[TripPreviewStop]:
    """Interleave walk-past vignette stops into the preview stop list.

    The vignette on leg ``i`` (the walk INTO dwell stop ``i``) sits right
    BEFORE that dwell stop, mirroring build_route_option's interleave. Its
    card carries the same one-liner the leg narration voices (first sentence
    of its chosen beat) with minutes=0; the dwell stop's narration already
    contains that line inside its leg text.

    KE9: a DWELL stop gets ``has_deeper_dive=True`` iff its poi_id is a key of
    ``overflow_by_poi`` with a non-empty overflow — the C9 governor capped some
    of that stop's beats out into the "keep exploring here" extras. Vignette
    (walk-past) stops never have deeper-dive. Pure and deterministic.
    """
    from src.audio.tts_normalize import normalize_dashes_for_reading
    from src.tour.selection import spotlight

    lenses_fs = frozenset(script.inputs.lenses or ())
    # The vignette one-liner is voiced by its own interleaved card (below); strip it
    # from the dwell stop's narration so the workbench doesn't double-voice it (the
    # "bleed"). _build_transit folds the one-liner in at the arrival dwell stop_idx as
    # a vignette-beat sentence, so drop sentences sourced from a vignette beat.
    vignette_beat_ids = {b.id for beats in vignette_beats.values() for b in beats}
    # SPLIT WALK-CONCURRENT NARRATION OUT OF THE DWELL CARD (2026-07-19).
    #
    # Navigation lines and reflections are spoken WHILE THE TOURIST WALKS the leg
    # INTO stop i, but they carry stop_idx == i, so they were concatenated into that
    # stop's narration. The editor therefore saw one undifferentiated blob and could
    # not tell what the tourist hears on the walk versus standing at the stop, could
    # not play the walk content on its own, and could not see how much of a long
    # walk was filled at all.
    #
    # That mattered because the walks are where the tour is emptiest. MEASURED on
    # the live Paris graph, 2026-07-19, on the CURRENT code (an earlier revision of
    # this comment quoted 1650 s / 959 s / 61%, measured while a since-reverted
    # selection experiment was applied; those figures were stale and are corrected
    # here — re-derive rather than carry a number forward):
    #
    #   60-min Ile de la Cite / dark_history: 1096 s walking, 710 s spoken.
    #       60% of elapsed time is silence; 4 leg cards carry 54 words = 22 s,
    #       filling 2.0% of the walking.
    #   60-min Le Marais / social_change:     1148 s walking, 345 s spoken.
    #       76% silence; 1 leg card carries 14 words = 6 s, filling 0.5%.
    #
    # ``is_walk_concurrent`` is the SHARED predicate (src/tour/generation.py) that
    # quality_rubric's C7/C7b time model also uses, so a sentence shown on a leg
    # card is exactly a sentence the rubric scored as costing no elapsed time.
    _dwell_sents: dict[int, list[str]] = {}
    _leg_sents: dict[int, list[str]] = {}
    for s in script.script:
        if s.source_type == "beat" and s.source_id in vignette_beat_ids:
            continue  # voiced by its own interleaved vignette card, below
        if is_walk_concurrent(s, vignette_beat_ids):
            _leg_sents.setdefault(s.stop_idx, []).append(s.text)
        else:
            _dwell_sents.setdefault(s.stop_idx, []).append(s.text)
    # Display-normalize dashes so the workbench text reads the way the audio
    # sounds (comma pause, not a dangling em-dash the tourist complained about).
    per_stop = {idx: normalize_dashes_for_reading(" ".join(t)) for idx, t in _dwell_sents.items()}
    per_leg = {idx: normalize_dashes_for_reading(" ".join(t)) for idx, t in _leg_sents.items()}
    # Walk seconds of the leg ARRIVING at stop i — shown on the leg card so the
    # editor can see the walk against the narration that fills it. A leg with 600 s
    # of walking and 20 s of narration is the defect made visible.
    _leg_walk_s: dict[int, int] = {}
    for i, t in enumerate(route.transits):
        _leg_walk_s[i] = int(t.leg_seconds if t.leg_seconds is not None else t.walk_seconds)
    # Voice the walk-past one-liner via the SAME helper the audio/script path uses
    # (generation.vignette_one_liner_text) so the workbench text never diverges from
    # what the tourist hears — clause-capped when the beat's first sentence is a long
    # run-on, keeping the POI's own name in the shortened line.
    # Vignette beats belong to WALK-PAST POIs (route.vignettes), NOT the seated
    # route.pois — the cap's name guard needs THOSE names or it falls back to the
    # full run-on. Cover both.
    _poi_name_by_id = {p.id: p.name for p in route.pois}
    for _pois in route.vignettes.values():
        for _p in _pois:
            _poi_name_by_id.setdefault(_p.id, _p.name)
    one_liner_by_poi: dict[str, str] = {}
    for beats in vignette_beats.values():
        for beat in beats:
            text = vignette_one_liner_text(beat.script_body, _poi_name_by_id.get(beat.poi_id, ""))
            if text:
                one_liner_by_poi[beat.poi_id] = normalize_dashes_for_reading(text)

    out: list[TripPreviewStop] = []
    for i, sp in enumerate(script.selected_pois):
        # The LEG into this stop, before anything that happens at it. Emitted only
        # when there is something to hear: a leg with no narration is silence, and
        # an empty card would imply content that does not exist.
        leg_text = per_leg.get(i, "").strip()
        if leg_text:
            out.append(
                TripPreviewStop(
                    sort_order=len(out) + 1,
                    poi_name=f"Walk to {sp.name}",
                    lat=sp.lat,
                    lng=sp.lng,
                    narration=leg_text,
                    minutes=round(_leg_walk_s.get(i, 0) / 60),
                    band="leg",
                    spotlight=0.0,
                )
            )
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
                has_deeper_dive=bool(overflow_by_poi.get(sp.id)),
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
        on_lens_fill_ratio=(
            round(assessment.on_lens_fill_ratio, 2)
            if assessment.on_lens_fill_ratio is not None
            else None
        ),
        anchor_candidates=assessment.anchor_candidate_count,
        reachable_poi_count=assessment.reachable_poi_count,
        max_supportable_duration_min=assessment.max_supportable_duration_min,
        one_way_alternative_destination=assessment.one_way_alternative_destination,
    )


def _compose_status(stitched: Script, composed: Script) -> str:
    """'composed' (fully AI-voiced) or 'composed_partial' when the graceful
    per-stop repair reverted at least one stop to the grounded stitch."""

    def _by_stop(s: Script) -> dict[int, tuple[str, ...]]:
        out: dict[int, list[str]] = {}
        for sent in s.script:
            out.setdefault(sent.stop_idx, []).append(sent.text)
        return {k: tuple(v) for k, v in out.items()}

    st, co = _by_stop(stitched), _by_stop(composed)
    reverted = any(co.get(k) == v for k, v in st.items())
    return "composed_partial" if reverted else "composed"


@router.post("/trips/preview", response_model=TripPreviewResponse)
def preview_trip(
    body: TripPreviewRequest,
    driver: Driver = Depends(get_driver),
    compose_client: ComposeClient = Depends(get_compose_client),
    faithfulness_checker: FaithfulnessChecker | None = Depends(get_faithfulness_checker),
    correction_client=Depends(get_correction_client),
    claim_repetition_judge: RedundancyJudge = Depends(get_claim_repetition_judge),
    omission_checker=Depends(get_omission_checker),
):
    """Web-first preview (Phase 1.5): run the engine and return per-stop narration
    WITHOUT a profile and WITHOUT persisting a Trip/ItineraryItem.

    Lets a web surface (the preview page; later the workbench) show the assembled
    story fast. Audio is fetched per stop by the client via POST /audio/preview on
    each stop's narration text. RED density / no reachable POIs -> 422.
    """
    tour_input = _build_tour_input(
        start=(body.center_lat, body.center_lng),
        duration_min=body.duration_min or DEFAULT_DURATION_MIN,
        city_slug=body.city_slug,
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

    capped = build_poi_beat_plans_capped(
        route, snapshot, lenses=tour_input.lenses, end_is_none=tour_input.end is None
    )
    plans = tuple(pb for pb, _ in capped)
    overflow_by_poi = {pb.poi_id: ov for pb, ov in capped if ov}
    vignette_beats = select_vignette_beats(
        route.vignettes, snapshot.beats_by_poi, lenses=tour_input.lenses
    )
    seq = BeatSequence(
        poi_beats=tuple(plans),
        vignette_beats=vignette_beats,
        overflow_by_poi=overflow_by_poi,
    )
    script = generate(seq, route, tour_input)

    # THE ONE ALGORITHM. No flags, no tiers, no per-request narrator choice: every
    # preview runs the same pipeline — Opus composes each stop, the faithfulness gate
    # verifies, and the correct-don't-reject corrector repairs (trim -> rewrite) before
    # anything is allowed to degrade to raw stitch. The grounded stitch is the FLOOR
    # (what a refused/unrepairable stop falls back to), never a selectable mode. The
    # hermetic test suite stubs the client offline so `make test` never spends.
    compose_status = "stitched"
    provider = compose_provider_name(os.getenv("COMPOSE_PROVIDER"))
    narration_quality = None
    omitted_facts: list = []
    omission_stops_checked = 0
    try:
        # Per-chapter: one focused (parallel) call per stop, so the big
        # repetitive stops fuse without dropping facts (whole-tour compose
        # reverted them) and the tour composes in ~1 min, not ~19.
        # Always on: the corrector is part of the algorithm, not an option.
        #
        # omission_checker/omission_findings: the ADVISORY coverage-direction pass
        # (opt-in ONLY at this preview call site — never the persisted /compose
        # path). The production coverage gate this ladder already runs cannot see
        # a dropped fact (its overlap COEFFICIENT reads 1.000 once compose
        # deletes material — measured on a real London beat, CLAUDE.md
        # 2026-07-19). This runs the calibrated CoverageJudge on the SERVED
        # script, scoped internally to keyless-beat stops (the blind spot's
        # proven-worst corpus, 100% of London) — a keyed-corpus preview with no
        # keyless beat in view spends nothing extra. Read-only: it never affects
        # compose_status/script above; findings are appended to omitted_facts and
        # surfaced next to the rubric's, below.
        composed = compose_script_per_chapter(
            script,
            seq,
            route,
            client=compose_client,
            faithfulness_checker=faithfulness_checker,
            candidates=2,  # best-of-2: extra tickets for the big, dense stops
            correction_client=correction_client,
            omission_checker=omission_checker,
            omission_findings=omitted_facts,
        )
    except ComposeVerificationError:
        compose_status = "refused"  # unrepairable — keep the grounded stitch
    else:
        compose_status = _compose_status(script, composed)
        script = composed
        # Objective quality signals on the composed narration, so tour quality is
        # MEASURED, not a matter of taste. Score the FULL spoken text (composed
        # glue/closers/reflections included — that is where moralizing closers
        # concentrate, the highest-weighted tell).
        narration = " ".join(s.text for s in script.script)
        q = score_narration(narration)
        narration_quality = {
            "stilted_score": q.stilted_score,
            "engagement_score": q.engagement_score,
            # reliable=False => the composites are noise (short sample); the UI
            # must flag this and lean on tells_per_100w instead of the deltas.
            "reliable": q.reliable,
            "n_words": q.n_words,
            "burstiness": q.burstiness,
            "mean_sentence_words": q.mean_sentence_words,
            "long_sentence_rate": q.long_sentence_rate,
            "second_person_per_100w": q.second_person_rate,
            "look_prompt_rate": q.look_prompt_rate,
            "tells_per_100w": q.per_100w,
        }
        # Bookkeeping only (no judge calls): how many stops the omission pass
        # above actually looked at, for the "stats" transparency field below.
        beats_by_id = {b.id: b for plan in seq.poi_beats for b in plan.beats}
        omission_stops_checked = len(keyless_affected_stops(script, beats_by_id))

    # THE QUALITY RUBRIC — runs on EVERY tour, deterministic and $0. The mechanical
    # floor of specs/2026-07-19-tour-quality-standard/01-standard.md: it catches the
    # two failures the corpus-vs-render comparison can prove (a rich POI STARVED to a
    # line, a stop GORGED past the listenable cap) plus repeats, empty stops and
    # imbalance. Surfaced to the editor rather than silently swallowed — a tour that
    # breaches the standard is visible in the workbench with the exact check and stop.
    rubric = score_tour(script, route, snapshot.beats_by_poi, beat_sequence=seq)

    # G4 — an ADVISORY, UNCALIBRATED semantic check (standard §4): does any two
    # narration sentences, ANYWHERE in the tour, restate the same underlying fact in
    # new words — exactly the gap a lexical/regex pass cannot see (see
    # claim_repetition.py's docstring for the measured Vert-Galant defect a 4-gram
    # Jaccard detector missed at 0 hits). Report-only, same as the omission checker
    # below: the (now-removed) failure-ledger entry FL-2026-111 recorded that
    # HaikuRedundancyJudge "has never executed against a live model" — still true:
    # every test in tests/test_claim_repetition.py injects a hand-labelled stub, none
    # construct the real class with client=None — and warned verbatim "an unproven
    # judge silently gating narration would suppress real facts". So
    # this NEVER folds into `quality["passed"]` until a labelled bake-off closes that
    # entry. Findings surface in the separate `quality["g4"]` block below, severity
    # WARN, for an editor to see without a non-deterministic judge flipping the
    # tour's verdict.
    #
    # Skipped entirely on the "refused" path: `script` there is still the raw,
    # never-composed stitch (compose_script_per_chapter raised
    # ComposeVerificationError and the grounded stitch was kept as the floor) —
    # spending the full judge-call budget scoring a script nobody will ever compose
    # again is pure waste, not a check on anything the tourist will hear.
    # DELIBERATELY NOT RUN as of 2026-07-19. It was wired earlier the same day and
    # unwired on measurement, before ever billing a real preview.
    #
    # Two independent reasons, both measured, either one sufficient:
    #
    # 1. IT DOES NOT DETECT THE DEFECT IT EXISTS FOR. The cost cap forced a sampling
    #    strategy over ~1100 candidate pairs per tour. Prefix truncation spent the
    #    whole budget on stop 0 (0 of 327 pairs with a-stop >= 1 were ever judged);
    #    the round-robin stratification that fixed that breadth destroyed
    #    within-bucket depth instead. Measured on the very tour
    #    claim_repetition.py's docstring cites as its founding case
    #    (data/paris/tours/pont-neuf-60min-5afc2e.json, where "Vert-Galant" is
    #    glossed FOUR times in different words): at MAX_CANDIDATE_PAIRS=200 the
    #    stratified sample recovers **0 of the 15 Vert-Galant edges**. A check that
    #    reports "no repetition found" on the canonical repetition tour is worse
    #    than no check — it tells an editor the tour is clean.
    #
    # 2. THE JUDGE IS UNCALIBRATED. HaikuRedundancyJudge has never executed against
    #    a live model; all 32 tests inject a hand-labelled stub. The (now-removed)
    #    failure-ledger entry FL-2026-111 warned verbatim: "an unproven judge
    #    silently gating narration would suppress real facts."
    #
    # Cost of leaving it on: the cap is a FLOOR, not a ceiling — every real tour
    # yields >1100 candidates, so this bills ~200 Haiku calls (~$0.10) on EVERY
    # preview for the recall measured above.
    #
    # To re-enable: (a) fix the sampler so it recovers the Vert-Galant edges at a
    # defensible budget, and (b) run the labelled bake-off that closes FL-2026-111
    # (~$0.006/tour, the pattern in scripts/coverage_calibrate.py). Until BOTH are
    # done this stays dark. The module, its tests, and the response shape below all
    # remain so re-enabling is a one-line change.
    repetition = None
    g4_findings: tuple = ()

    stops = _preview_stops(script, route, vignette_beats, snapshot, overflow_by_poi)
    return TripPreviewResponse(
        spine_area=route.spine_area,
        total_audio_min=round(script.total_audio_seconds / 60),
        stops=stops,
        # Per-corridor lens coverage note ships later in Phase 3 (REACH).
        lens_coverage_note=None,
        tourability=_tourability_payload(route.tourability),
        compose_status=compose_status,
        provider=provider,
        narration_quality=narration_quality,
        quality={
            # THE DETERMINISTIC, $0 rubric ALONE decides pass/fail. G4's redundancy
            # judge is uncalibrated (formerly tracked as failure-ledger entry
            # FL-2026-111, now removed — see the check_tour_repetition docstring) and
            # must never flip this verdict — see the `g4` block below for its
            # findings, kept strictly advisory.
            "passed": rubric.passed,
            "summary": rubric.summary(),
            "blockers": [
                {
                    "check": f.check,
                    "message": f.message,
                    "stop_idx": f.stop_idx,
                    "poi_name": f.poi_name,
                }
                for f in rubric.blockers
            ],
            "warnings": [
                {
                    "check": f.check,
                    "message": f.message,
                    "stop_idx": f.stop_idx,
                    "poi_name": f.poi_name,
                }
                for f in rubric.warnings
            ]
            + [
                {
                    "check": "coverage_omission",
                    "message": f"beat {f.beat_id}: possibly dropped fact — {f.fact}",
                    "stop_idx": f.stop_idx,
                    "poi_name": None,
                }
                for f in omitted_facts
            ],
            "stats": {
                **rubric.stats,
                # ADVISORY ONLY — never folded into "passed". omission_stops_checked
                # is the KEYLESS-beat stop count the coverage judge actually ran on
                # (0 on a fully-keyed corpus preview, where this feature spends
                # nothing); omission_findings is how many it flagged as possibly
                # dropped, for the workbench to point the editor at.
                "omission_stops_checked": omission_stops_checked,
                "omission_findings": len(omitted_facts),
            },
            # G4 — SEPARATE, clearly-labelled ADVISORY block (standard §4). Severity
            # is always WARN here, never BLOCKER: `calibrated=False` documents WHY
            # (see the module docstring above — HaikuRedundancyJudge has never executed
            # against a live model) so a consumer of
            # this response cannot mistake it for a proven gate. `judge_calls` /
            # `candidates_dropped` are 0 on the refused path (skipped — see above),
            # never on any composed/stitched preview (every real tour measured
            # exceeds MAX_CANDIDATE_PAIRS, so the cap is a FLAT ~$0.10 cost, not a
            # ceiling — see claim_repetition.MAX_CANDIDATE_PAIRS).
            "g4": {
                "severity": "WARN",
                "calibrated": False,
                "findings": [
                    {
                        "check": f.check,
                        "message": f.message,
                        "stop_idx": f.stop_idx,
                        "poi_name": None,
                    }
                    for f in g4_findings
                ],
                "judge_calls": repetition.judge_calls if repetition is not None else 0,
                "candidates_dropped": (
                    repetition.candidates_dropped if repetition is not None else 0
                ),
            },
        },
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
