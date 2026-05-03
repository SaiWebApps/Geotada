"""Trip generation routes — create optimized itineraries from profile preferences."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import Session

from src.api.crud.trips import (
    apply_golden_ratio,
    compute_schedule,
    create_trip_with_stops,
    find_candidate_pois,
    find_matching_beats,
    list_trips_for_profile,
)
from src.api.dependencies import get_session
from src.api.models.trips import (
    GeneratedStop,
    TripGenerateRequest,
    TripGenerateResponse,
)

router = APIRouter(tags=["trips"])


@router.post("/trips/generate", response_model=TripGenerateResponse, status_code=201)
def generate_trip(
    body: TripGenerateRequest,
    session: Session = Depends(get_session),
):
    """Generate an optimized trip itinerary based on profile lens preferences.

    Finds POIs within radius, matches to beats the user prefers, applies
    golden-ratio selection (~20% anchors), schedules stops, and persists
    the Trip graph structure.
    """
    # Verify profile exists
    profile_check = session.run(
        "MATCH (p:Profile {id: $pid}) RETURN p.id AS id",
        pid=body.profile_id,
    ).single()
    if profile_check is None:
        raise HTTPException(404, f"Profile '{body.profile_id}' not found")

    # Step 1: Find candidate POIs within radius
    pois = find_candidate_pois(
        session,
        center_lat=body.center_lat,
        center_lng=body.center_lng,
        radius_m=body.radius_m,
        kid_friendly_only=body.kid_friendly_only,
    )
    if not pois:
        raise HTTPException(422, "No POIs found within the specified radius and filters")

    # Step 2: Find beats matching profile's lens preferences
    poi_ids = [p["id"] for p in pois]
    beats = find_matching_beats(session, poi_ids, body.profile_id)
    if not beats:
        raise HTTPException(
            422,
            "No narrative beats match the profile's lens preferences for POIs in this area",
        )

    # Step 3: Apply golden ratio selection
    selected = apply_golden_ratio(beats, body.max_stops, body.duration_min)

    # Step 4: Compute schedule
    scheduled = compute_schedule(selected, body.start_time)

    # Step 5: Generate trip name if not provided
    trip_name = body.trip_name or f"Trip ({body.start_date})"

    # Step 6: Persist to Neo4j
    result = create_trip_with_stops(
        session,
        trip_name=trip_name,
        profile_id=body.profile_id,
        start_date=body.start_date,
        end_date=body.end_date,
        stops=scheduled,
    )

    # Build response
    stops_out = [GeneratedStop(**s) for s in scheduled]
    total_duration = sum(s["duration_min"] for s in scheduled)
    anchor_count = sum(1 for s in scheduled if s["importance_tier"] == 5)
    flavour_count = len(scheduled) - anchor_count

    return TripGenerateResponse(
        trip_id=result["trip_id"],
        trip_name=result["trip_name"],
        profile_id=body.profile_id,
        total_stops=len(scheduled),
        total_duration_min=total_duration,
        anchor_count=anchor_count,
        flavour_count=flavour_count,
        stops=stops_out,
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
