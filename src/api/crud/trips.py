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
               coalesce(l.display_label, l.name) AS lens_display,
               coalesce(beat.duration_sec, 180) AS duration_sec,
               coalesce(poi.typical_duration_min,
                   CASE WHEN coalesce(poi.importance_tier, 3) >= 5 THEN 60
                        WHEN coalesce(poi.importance_tier, 3) >= 4 THEN 45
                        ELSE 30 END
               ) AS typical_duration_min,
               coalesce(poi.importance_tier, 3) AS importance_tier,
               poi.location.latitude AS lat,
               poi.location.longitude AS lng,
               beat.script_body AS script_body,
               beat.audio_url AS audio_url,
               beat.duration_sec AS audio_duration_sec
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

    # Trim to duration budget if provided (using POI visit duration, not beat audio length)
    if duration_min is not None:
        trimmed: list[dict[str, Any]] = []
        total_min = 0
        for stop in selected:
            stop_dur = stop.get("typical_duration_min", 30)
            if total_min + stop_dur <= duration_min:
                trimmed.append(stop)
                total_min += stop_dur
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
        duration_min = stop.get("typical_duration_min", 30)
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
                "script_body": stop.get("script_body"),
                "audio_url": stop.get("audio_url"),
                "audio_duration_sec": stop.get("audio_duration_sec"),
            }
        )

        # Advance clock by POI visit duration
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


def list_trips_for_profile(
    session: Session,
    profile_id: str,
) -> list[dict[str, Any]]:
    """Return all trips for a profile with their stops.

    For each trip, collects stops via HAS_STOP → ItineraryItem → AT_POI → POI,
    PLAYS_BEAT → Beat → TAGGED_WITH → Lens. Returns trip data + ordered stops.
    """
    # First verify profile exists
    check = session.run(
        "MATCH (p:Profile {id: $pid}) RETURN p.id AS id",
        pid=profile_id,
    ).single()
    if check is None:
        return None  # type: ignore[return-value]

    # Get all trips for this profile
    trips_query = """
        MATCH (p:Profile {id: $pid})-[:IS_CAPTAIN_OF]->(t:Trip)
        RETURN t.id AS trip_id,
               t.name AS trip_name,
               t.start_date AS start_date,
               t.end_date AS end_date,
               t.status AS status
        ORDER BY t.created_at DESC
    """
    trip_records = session.run(trips_query, pid=profile_id)
    trips = [dict(r) for r in trip_records]

    results: list[dict[str, Any]] = []
    for trip in trips:
        # Get stops for each trip
        stops_query = """
            MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(item:ItineraryItem)
            MATCH (item)-[:AT_POI]->(poi:POI)
            MATCH (item)-[:PLAYS_BEAT]->(beat:NarrativeBeat)-[:TAGGED_WITH]->(lens:Lens)
            RETURN item.sort_order AS sort_order,
                   poi.id AS poi_id,
                   poi.name AS poi_name,
                   poi.location.latitude AS lat,
                   poi.location.longitude AS lng,
                   beat.id AS beat_id,
                   lens.name AS lens_name,
                   coalesce(lens.display_label, lens.name) AS lens_display,
                   item.duration_min AS duration_min,
                   coalesce(poi.importance_tier, 3) AS importance_tier,
                   CASE WHEN item.start_time IS NOT NULL
                        THEN substring(toString(item.start_time), 0, 5)
                        ELSE '09:00' END AS start_time,
                   beat.script_body AS script_body,
                   beat.audio_url AS audio_url,
                   beat.duration_sec AS audio_duration_sec
            ORDER BY item.sort_order
        """
        stop_records = session.run(stops_query, tid=trip["trip_id"])
        stops = [dict(r) for r in stop_records]

        total_duration = sum(s["duration_min"] for s in stops)
        anchor_count = sum(1 for s in stops if s["importance_tier"] == 5)
        flavour_count = len(stops) - anchor_count

        results.append(
            {
                "trip_id": trip["trip_id"],
                "trip_name": trip["trip_name"],
                "profile_id": profile_id,
                "total_stops": len(stops),
                "total_duration_min": total_duration,
                "anchor_count": anchor_count,
                "flavour_count": flavour_count,
                "stops": stops,
            }
        )

    return results
