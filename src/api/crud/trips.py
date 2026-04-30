"""Business logic for trip generation — POI search, beat matching, and scheduling."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import Session


def find_candidate_pois(
    session: Session,
    center_lat: float,
    center_lng: float,
    radius_m: int,
    kid_friendly_only: bool,
) -> list[dict[str, Any]]:
    """Find POIs within radius of center point using Neo4j spatial functions.

    Returns list of dicts with keys: id, name, lat, lng, importance_tier,
    trigger_radius, kid_friendly.
    """
    kid_filter = "AND n.kid_friendly = true" if kid_friendly_only else ""
    query = f"""
        WITH point({{latitude: $lat, longitude: $lng, srid: 4326}}) AS center
        MATCH (n:POI)
        WHERE n.location IS NOT NULL
          AND point.distance(n.location, center) <= $radius
          {kid_filter}
        RETURN n.id AS id,
               n.name AS name,
               n.location.latitude AS lat,
               n.location.longitude AS lng,
               coalesce(n.importance_tier, 3) AS importance_tier,
               coalesce(n.trigger_radius, 50) AS trigger_radius,
               coalesce(n.kid_friendly, false) AS kid_friendly
        ORDER BY point.distance(n.location, center)
    """
    result = session.run(query, lat=center_lat, lng=center_lng, radius=radius_m)
    return [dict(record) for record in result]


def find_matching_beats(
    session: Session,
    poi_ids: list[str],
    profile_id: str,
) -> list[dict[str, Any]]:
    """Find active NarrativeBeats for candidate POIs that match the profile's lens preferences.

    Returns list of dicts with keys: beat_id, poi_id, poi_name, lens_name,
    lens_display, duration_sec, importance_tier, lat, lng.
    """
    query = """
        MATCH (profile:Profile {id: $profile_id})-[:PREFERS_LENS]->(lens:Lens)
        WITH collect(lens) AS preferred_lenses
        UNWIND $poi_ids AS pid
        MATCH (poi:POI {id: pid})-[:HAS_BEAT]->(beat:NarrativeBeat)-[:TAGGED_WITH]->(l:Lens)
        WHERE l IN preferred_lenses
          AND coalesce(beat.status, 'active') <> 'inactive'
        RETURN beat.id AS beat_id,
               poi.id AS poi_id,
               poi.name AS poi_name,
               l.name AS lens_name,
               coalesce(l.display_name, l.name) AS lens_display,
               coalesce(beat.duration_sec, 180) AS duration_sec,
               coalesce(poi.importance_tier, 3) AS importance_tier,
               poi.location.latitude AS lat,
               poi.location.longitude AS lng
    """
    result = session.run(query, profile_id=profile_id, poi_ids=poi_ids)
    return [dict(record) for record in result]


def apply_golden_ratio(
    candidates: list[dict[str, Any]],
    max_stops: int,
    duration_min: int | None,
) -> list[dict[str, Any]]:
    """Apply golden ratio selection: ~20% anchors (gravity 5), rest flavour (1-4).

    Pure Python function — no DB calls.
    Deduplicates by POI (picks highest-gravity beat if multiple).
    Trims to duration budget if provided.
    Caps at max_stops.
    """
    # Deduplicate: keep highest importance_tier beat per POI
    best_per_poi: dict[str, dict[str, Any]] = {}
    for c in candidates:
        poi_id = c["poi_id"]
        if (
            poi_id not in best_per_poi
            or c["importance_tier"] > best_per_poi[poi_id]["importance_tier"]
        ):
            best_per_poi[poi_id] = c

    unique = list(best_per_poi.values())

    # Split into anchors (tier 5) and flavour (tier 1-4)
    anchors = sorted(
        [c for c in unique if c["importance_tier"] == 5],
        key=lambda x: x["importance_tier"],
        reverse=True,
    )
    flavour = sorted(
        [c for c in unique if c["importance_tier"] < 5],
        key=lambda x: x["importance_tier"],
        reverse=True,
    )

    # Target ~20% anchors
    target_anchor_count = max(1, round(max_stops * 0.2))
    selected_anchors = anchors[:target_anchor_count]
    remaining_slots = max_stops - len(selected_anchors)
    selected_flavour = flavour[:remaining_slots]

    selected = selected_anchors + selected_flavour

    # Trim to duration budget if provided
    if duration_min is not None:
        trimmed: list[dict[str, Any]] = []
        total_sec = 0
        budget_sec = duration_min * 60
        for stop in selected:
            stop_dur = stop.get("duration_sec", 180)
            if total_sec + stop_dur <= budget_sec:
                trimmed.append(stop)
                total_sec += stop_dur
            else:
                break
        selected = trimmed

    return selected[:max_stops]


def compute_schedule(
    stops: list[dict[str, Any]],
    start_time: str,
) -> list[dict[str, Any]]:
    """Assign sequential start_time to each stop based on duration.

    Pure Python function. Returns stops enriched with sort_order, duration_min,
    and start_time fields.
    """
    parts = start_time.split(":")
    current_hour = int(parts[0])
    current_minute = int(parts[1])

    scheduled: list[dict[str, Any]] = []
    for idx, stop in enumerate(stops):
        duration_sec = stop.get("duration_sec", 180)
        duration_min = max(1, duration_sec // 60)
        time_str = f"{current_hour:02d}:{current_minute:02d}"

        scheduled.append(
            {
                "sort_order": idx + 1,
                "poi_id": stop["poi_id"],
                "poi_name": stop["poi_name"],
                "lat": stop["lat"],
                "lng": stop["lng"],
                "beat_id": stop["beat_id"],
                "lens_name": stop["lens_name"],
                "lens_display": stop["lens_display"],
                "duration_min": duration_min,
                "importance_tier": stop["importance_tier"],
                "start_time": time_str,
            }
        )

        # Advance clock
        current_minute += duration_min
        current_hour += current_minute // 60
        current_minute = current_minute % 60

    return scheduled


def create_trip_with_stops(
    session: Session,
    trip_name: str,
    profile_id: str,
    start_date: str,
    end_date: str,
    stops: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create Trip node and ItineraryItem nodes in a single transaction.

    Creates:
    - Trip node with UUID, name, dates, status='planning'
    - Profile -[:IS_CAPTAIN_OF]-> Trip
    - For each stop: ItineraryItem with HAS_STOP, ASSIGNED_TO, AT_POI, PLAYS_BEAT
    """
    trip_id = str(uuid.uuid4())

    # Build the Cypher for creating the trip and linking to profile
    create_query = """
        MATCH (profile:Profile {id: $profile_id})
        CREATE (trip:Trip {
            id: $trip_id,
            name: $trip_name,
            start_date: $start_date,
            end_date: $end_date,
            status: 'planning',
            created_at: datetime()
        })
        MERGE (profile)-[:IS_CAPTAIN_OF]->(trip)
        RETURN trip.id AS trip_id
    """
    session.run(
        create_query,
        trip_id=trip_id,
        trip_name=trip_name,
        profile_id=profile_id,
        start_date=start_date,
        end_date=end_date,
    )

    # Create each itinerary item
    item_query = """
        MATCH (trip:Trip {id: $trip_id})
        MATCH (poi:POI {id: $poi_id})
        MATCH (beat:NarrativeBeat {id: $beat_id})
        MATCH (profile:Profile {id: $profile_id})
        CREATE (item:ItineraryItem {
            id: $item_id,
            sort_order: $sort_order,
            duration_min: $duration_min,
            start_time: $start_time,
            created_at: datetime()
        })
        CREATE (trip)-[:HAS_STOP]->(item)
        CREATE (item)-[:ASSIGNED_TO]->(profile)
        CREATE (item)-[:AT_POI]->(poi)
        CREATE (item)-[:PLAYS_BEAT]->(beat)
    """
    for stop in stops:
        session.run(
            item_query,
            trip_id=trip_id,
            poi_id=stop["poi_id"],
            beat_id=stop["beat_id"],
            profile_id=profile_id,
            item_id=str(uuid.uuid4()),
            sort_order=stop["sort_order"],
            duration_min=stop["duration_min"],
            start_time=stop["start_time"],
        )

    return {"trip_id": trip_id, "trip_name": trip_name}
