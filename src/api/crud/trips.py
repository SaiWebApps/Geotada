"""Business logic for trip generation — POI search, beat matching, and scheduling."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from src.tour.options import dominant_lens
from src.tour.render_md import stop_narration_text

if TYPE_CHECKING:
    from neo4j import Session

    from src.tour.contract import BeatRef, Script, ScriptPOI


def route_script_to_stops(
    selected_pois: list[ScriptPOI] | tuple[ScriptPOI, ...],
    beats_by_id: dict[str, BeatRef],
    start_time: str,
    *,
    script: Script | None = None,
    extra_by_poi: dict[str, tuple[str, ...]] | None = None,
) -> list[dict[str, Any]]:
    """Adapt the engine's ordered ScriptPOIs into the stop dicts create_trip_with_stops expects.

    Pure function — no DB, no engine run. Each ScriptPOI becomes one stop in route
    order; ALL of its beats are kept (`beat_ids`) with `primary_beat_id` = the first
    (so single-beat read paths still work); the per-stop lens is the dominant lens of
    its beats (computed, not fabricated); the clock advances by each stop's
    `dwell_seconds`. See specs/2026-06-12-tour-algorithm-decision/M0b-DESIGN.md.

    Phase 1 (Step 1.2): when ``script`` is passed, each stop also carries its
    ``narration`` — the stitched per-stop text (cold-open, transit glue, beats,
    closing) from ``stop_narration_text``, the text Phase 1 hands to TTS. Omitted
    (``""``) when no script is given, so existing callers stay back-compatible.
    """
    parts = start_time.split(":")
    current_hour, current_minute = int(parts[0]), int(parts[1])
    narration_by_stop = stop_narration_text(script) if script is not None else {}
    extras = extra_by_poi or {}

    stops: list[dict[str, Any]] = []
    for idx, sp in enumerate(selected_pois):
        beat_ids = list(sp.beat_ids)
        duration_min = max(1, round(sp.dwell_seconds / 60)) if sp.dwell_seconds else 1
        time_str = f"{current_hour:02d}:{current_minute:02d}"

        stops.append(
            {
                "sort_order": idx + 1,
                "poi_id": sp.id,
                "poi_name": sp.name,
                "lat": sp.lat,
                "lng": sp.lng,
                "beat_ids": beat_ids,
                "extra_beat_ids": list(extras.get(sp.id, ())),
                "primary_beat_id": beat_ids[0] if beat_ids else None,
                "lens_name": dominant_lens(sp.beat_ids, beats_by_id),
                "duration_min": duration_min,
                "importance_tier": sp.tier,
                "start_time": time_str,
                "area": sp.area,
                "dwell_seconds": sp.dwell_seconds,
                "narration": narration_by_stop.get(idx, ""),
            }
        )

        current_minute += duration_min
        current_hour += current_minute // 60
        current_minute %= 60

    return stops


def create_trip_with_stops(
    session: Session,
    trip_name: str,
    profile_id: str,
    start_date: str,
    end_date: str,
    stops: list[dict[str, Any]],
    tour_input_json: str | None = None,
    options_json: str | None = None,
) -> dict[str, Any]:
    """Create Trip node and ItineraryItem nodes in a single transaction.

    Creates:
    - Trip node with UUID, name, dates, status='planning'
    - Profile -[:IS_CAPTAIN_OF]-> Trip
    - For each stop: ItineraryItem with HAS_STOP, ASSIGNED_TO, AT_POI, and one
      PLAYS_BEAT edge per beat in the stop's `beat_ids`. The item stores
      `beat_ids` (engine narration order), `primary_beat_id` (= beat_ids[0],
      for single-beat read paths), the stop's dominant `lens_name` (nullable),
      and the stitched per-stop `narration` (Phase 1, Step 1.2; nullable — a
      null/absent value is simply not stored). See
      specs/2026-06-12-tour-algorithm-decision/M0b-DESIGN.md.

    Phase 4 (Step 4.6): ``tour_input_json`` (the RESOLVED engine input incl.
    lenses + start_time) and ``options_json`` (per flavour, the ORDERED poi id
    list; index+1 = the option number in ``route_id``) persist on the Trip so
    POST /trips/{id}/compose can rebuild the user's PICK without re-running
    selection — corpus/routing drift between generate and compose must never
    swap the picked route. Nulls are simply not stored.
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
            tour_input_json: $tour_input_json,
            options_json: $options_json,
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
        tour_input_json=tour_input_json,
        options_json=options_json,
    )

    _create_itinerary_items(session, trip_id, profile_id, stops)

    return {"trip_id": trip_id, "trip_name": trip_name}


def _create_itinerary_items(
    session: Session,
    trip_id: str,
    profile_id: str,
    stops: list[dict[str, Any]],
) -> list[str]:
    """Create one ItineraryItem (+ edges) per stop; item ids in stop order.

    A null $lens_name is simply not stored (Cypher drops null map entries).
    """
    item_query = """
        MATCH (trip:Trip {id: $trip_id})
        MATCH (poi:POI {id: $poi_id})
        MATCH (profile:Profile {id: $profile_id})
        CREATE (item:ItineraryItem {
            id: $item_id,
            sort_order: $sort_order,
            duration_min: $duration_min,
            start_time: $start_time,
            beat_ids: $beat_ids,
            extra_beat_ids: $extra_beat_ids,
            primary_beat_id: $primary_beat_id,
            lens_name: $lens_name,
            narration: $narration,
            extra_narration: $extra_narration,
            created_at: datetime()
        })
        CREATE (trip)-[:HAS_STOP]->(item)
        CREATE (item)-[:ASSIGNED_TO]->(profile)
        CREATE (item)-[:AT_POI]->(poi)
        WITH item
        UNWIND $beat_ids AS bid
        MATCH (beat:NarrativeBeat {id: bid})
        CREATE (item)-[:PLAYS_BEAT]->(beat)
        RETURN count(beat) AS edges
    """
    item_ids: list[str] = []
    for stop in stops:
        item_id = str(uuid.uuid4())
        record = session.run(
            item_query,
            trip_id=trip_id,
            poi_id=stop["poi_id"],
            profile_id=profile_id,
            item_id=item_id,
            sort_order=stop["sort_order"],
            duration_min=stop["duration_min"],
            start_time=stop["start_time"],
            beat_ids=stop["beat_ids"],
            extra_beat_ids=stop.get("extra_beat_ids", []),
            primary_beat_id=stop["primary_beat_id"],
            lens_name=stop["lens_name"],
            narration=stop.get("narration"),
            extra_narration=stop.get("extra_narration"),
        ).single()
        # The mid-query MATCH silently drops absent beat ids; fail loudly
        # rather than persist an item whose stored beat_ids cite beats it
        # has no PLAYS_BEAT edge to (corpus changed mid-request?).
        edges = record["edges"] if record else 0
        if edges != len(stop["beat_ids"]):
            raise ValueError(
                f"Stop {stop['poi_id']!r}: created {edges} PLAYS_BEAT edges "
                f"for {len(stop['beat_ids'])} beat_ids — beats missing from graph"
            )
        item_ids.append(item_id)
    return item_ids


def replace_trip_stops(
    session: Session, trip_id: str, stops: list[dict[str, Any]]
) -> list[str]:
    """Delete a trip's ItineraryItems and recreate them from ``stops``.

    /compose persists the picked flavour through this: item ids are FRESH
    (clients rebuild their stop lists from the response) and the new items
    carry no audio fields, so stale per-stop audio of the pre-compose
    narration can never be served as composed. Returns the new item ids in
    stop order.
    """
    record = session.run(
        "MATCH (p:Profile)-[:IS_CAPTAIN_OF]->(t:Trip {id: $tid}) RETURN p.id AS pid",
        tid=trip_id,
    ).single()
    if record is None:
        raise ValueError(f"Trip {trip_id!r} not found (or has no captain profile)")
    session.run(
        "MATCH (:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) DETACH DELETE i",
        tid=trip_id,
    )
    return _create_itinerary_items(session, trip_id, record["pid"], stops)


def mark_trip_composed(session: Session, trip_id: str, route_id: str) -> None:
    """Record the composed pick — a second /compose on the trip is a 409."""
    session.run(
        "MATCH (t:Trip {id: $tid}) SET t.composed_route_id = $rid",
        tid=trip_id,
        rid=route_id,
    )


def get_trip_compose_inputs(session: Session, trip_id: str) -> dict[str, Any] | None:
    """The persisted Phase-4 compose inputs for a trip; None if no such trip.

    Returns ``{"tour_input": dict | None, "options": list[list[str]] | None,
    "composed_route_id": str | None}`` parsed from the JSON properties Step
    4.6 writes at generate time. Pre-Phase-4 trips read as None fields —
    /compose refuses those rather than re-running selection.
    """
    record = session.run(
        "MATCH (t:Trip {id: $tid}) "
        "RETURN t.tour_input_json AS ti, t.options_json AS oj, "
        "       t.composed_route_id AS composed",
        tid=trip_id,
    ).single()
    if record is None:
        return None
    return {
        "tour_input": json.loads(record["ti"]) if record["ti"] else None,
        "options": json.loads(record["oj"]) if record["oj"] else None,
        "composed_route_id": record["composed"],
    }


def list_trips_for_profile(
    session: Session,
    profile_id: str,
) -> list[dict[str, Any]]:
    """Return all trips for a profile with their stops.

    For each trip, collects stops via HAS_STOP → ItineraryItem → AT_POI → POI.
    One row per item: its PLAYS_BEAT beats are collected, with stored
    `beat_ids`/`primary_beat_id`/`lens_name` item properties taking precedence
    and edge-derived values as the fallback for legacy single-beat items
    (e.g. seeded trips) that predate M0b's multi-beat persistence.
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
            MATCH (item)-[:PLAYS_BEAT]->(beat:NarrativeBeat)
            OPTIONAL MATCH (beat)-[:TAGGED_WITH]->(bl:Lens)
            WITH item, poi, beat, min(bl.name) AS beat_lens
            WITH item, poi, collect({id: beat.id, script_body: beat.script_body,
                                     audio_url: beat.audio_url,
                                     duration_sec: beat.duration_sec,
                                     lens: beat_lens}) AS beats
            WITH item, poi, beats,
                 coalesce(item.primary_beat_id, beats[0].id) AS primary_id
            WITH item, poi, beats, primary_id,
                 [b IN beats WHERE b.id = primary_id][0] AS pb
            WITH item, poi, beats, primary_id, pb,
                 coalesce(item.lens_name, pb.lens) AS lens_name
            OPTIONAL MATCH (lens:Lens {name: lens_name})
            RETURN item.sort_order AS sort_order,
                   item.id AS stop_id,
                   poi.id AS poi_id,
                   poi.name AS poi_name,
                   poi.location.latitude AS lat,
                   poi.location.longitude AS lng,
                   primary_id AS beat_id,
                   coalesce(item.beat_ids, [b IN beats | b.id]) AS beat_ids,
                   coalesce(item.extra_beat_ids, []) AS extra_beat_ids,
                   item.extra_narration AS extra_narration,
                   lens_name AS lens_name,
                   CASE WHEN lens IS NOT NULL
                        THEN coalesce(lens.display_label, lens.name)
                        ELSE lens_name END AS lens_display,
                   item.duration_min AS duration_min,
                   coalesce(poi.importance_tier, 3) AS importance_tier,
                   CASE WHEN item.start_time IS NOT NULL
                        THEN substring(toString(item.start_time), 0, 5)
                        ELSE '09:00' END AS start_time,
                   pb.script_body AS script_body,
                   item.narration AS narration,
                   coalesce(item.audio_url, pb.audio_url) AS audio_url,
                   coalesce(item.audio_duration_sec, pb.duration_sec) AS audio_duration_sec
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
