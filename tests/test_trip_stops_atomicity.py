"""Atomicity regression tests for the trip-persistence crud layer.

Both writes are documented as single transactions. Before the fix they were
per-statement autocommit, so a mid-loop ValueError (a stop citing a beat the
corpus no longer has) left permanent damage:

- ``replace_trip_stops`` had already committed the DETACH DELETE, so the trip
  lost its ORIGINAL itinerary and kept only a partial new one.
- ``create_trip_with_stops`` had already committed the Trip node plus every
  item before the failure, so the profile kept a phantom trip with a silently
  truncated stop list.

Undo-test: revert the ``session.execute_write`` wrappers in
``src/api/crud/trips.py`` back to ``session.run`` and both tests go RED.
"""

from __future__ import annotations

import pytest

from src.api.crud.trips import create_trip_with_stops, replace_trip_stops
from src.connection import create_driver, get_database
from src.schema.constraints import apply_all
from src.seed.runner import seed_all
from tests.conftest import _assert_test_port, needs_neo4j


@pytest.fixture(scope="module")
def seeded_driver():
    _assert_test_port()
    d = create_driver()
    with d.session(database=get_database()) as s:
        s.run("MATCH (n) DETACH DELETE n")
    apply_all(d)
    seed_all(d)
    yield d
    d.close()


@pytest.fixture(scope="module")
def profile_id(seeded_driver):
    with seeded_driver.session(database=get_database()) as s:
        return s.run("MATCH (p:Profile {display_name: 'Mom'}) RETURN p.id AS id").single()["id"]


def _real_stops(driver, limit: int = 2) -> list[dict]:
    """Adapter-shaped stop dicts over POIs that really have beats."""
    with driver.session(database=get_database()) as s:
        records = s.run(
            """
            MATCH (poi:POI)-[:HAS_BEAT]->(b:NarrativeBeat)
            WITH poi, collect(b.id) AS beat_ids
            RETURN poi.id AS poi_id, beat_ids
            ORDER BY poi.id
            LIMIT $limit
            """,
            limit=limit,
        ).data()
    assert len(records) >= limit, "toy seed must provide POIs with beats"
    return [
        {
            "sort_order": idx + 1,
            "poi_id": r["poi_id"],
            "beat_ids": r["beat_ids"],
            "primary_beat_id": r["beat_ids"][0],
            "lens_name": None,
            "duration_min": 30,
            "start_time": "09:00",
        }
        for idx, r in enumerate(records)
    ]


def _item_ids(driver, trip_id: str) -> list[str]:
    with driver.session(database=get_database()) as s:
        return [
            r["id"]
            for r in s.run(
                "MATCH (:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) "
                "RETURN i.id AS id ORDER BY i.sort_order",
                tid=trip_id,
            )
        ]


@needs_neo4j
class TestReplaceTripStopsIsAtomic:
    def test_failed_replace_leaves_the_original_itinerary_intact(self, seeded_driver, profile_id):
        """A stop citing a nonexistent beat must NOT destroy the existing stops."""
        stops = _real_stops(seeded_driver, limit=1)
        with seeded_driver.session(database=get_database()) as s:
            trip = create_trip_with_stops(
                s,
                trip_name="Atomic Replace Trip",
                profile_id=profile_id,
                start_date="2026-05-01",
                end_date="2026-05-02",
                stops=stops,
            )
        trip_id = trip["trip_id"]
        original_items = _item_ids(seeded_driver, trip_id)
        assert len(original_items) == 1

        bad = _real_stops(seeded_driver, limit=1)
        bad[0]["beat_ids"] = ["beat-that-does-not-exist"]
        bad[0]["primary_beat_id"] = "beat-that-does-not-exist"

        with seeded_driver.session(database=get_database()) as s, pytest.raises(ValueError):
            replace_trip_stops(s, trip_id, bad)

        # The DETACH DELETE must have rolled back with the failed CREATE.
        assert _item_ids(seeded_driver, trip_id) == original_items


@needs_neo4j
class TestCreateTripWithStopsIsAtomic:
    def test_failed_create_leaves_no_phantom_trip(self, seeded_driver, profile_id):
        """A mid-loop failure must roll back the Trip node and the earlier items."""
        stops = _real_stops(seeded_driver, limit=2)
        stops[1]["beat_ids"] = ["beat-that-does-not-exist"]
        stops[1]["primary_beat_id"] = "beat-that-does-not-exist"

        with seeded_driver.session(database=get_database()) as s, pytest.raises(ValueError):
            create_trip_with_stops(
                s,
                trip_name="Phantom Trip",
                profile_id=profile_id,
                start_date="2026-05-01",
                end_date="2026-05-02",
                stops=stops,
            )

        with seeded_driver.session(database=get_database()) as s:
            trips = s.run(
                "MATCH (t:Trip {name: 'Phantom Trip'}) RETURN count(t) AS n"
            ).single()["n"]
            orphan_items = s.run(
                "MATCH (i:ItineraryItem) WHERE NOT (:Trip)-[:HAS_STOP]->(i) RETURN count(i) AS n"
            ).single()["n"]
        assert trips == 0, "the partial Trip node must not survive the failure"
        assert orphan_items == 0
