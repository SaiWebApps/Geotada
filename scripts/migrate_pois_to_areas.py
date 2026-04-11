#!/usr/bin/env python3
"""Migrate 7 misclassified POI nodes to Area nodes, preserving all beats.

Transfers HAS_BEAT and TAGGED_WITH edges, creates corridor Area nodes where
needed, splits Les Halles into Area + Forum des Halles POI, and verifies
zero beat loss.

Prerequisites:
    - Neo4j running with data from Scopes 1-2
    - API running: make api

Usage:
    python scripts/migrate_pois_to_areas.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.connection import get_driver

API_BASE = "http://localhost:8000/api/v1"

# Mapping: POI name -> (target Area name, area_type, parent arrondissement)
# Islands and Les Halles already have Area nodes from Scope 2.
# Corridors need new Area nodes.
MIGRATIONS = [
    {
        "poi_name": "Ile de la Cite",
        "area_name": "Île de la Cité",
        "area_exists": True,
    },
    {
        "poi_name": "Ile Saint-Louis",
        "area_name": "Île Saint-Louis",
        "area_exists": True,
    },
    {
        "poi_name": "Les Halles",
        "area_name": "Les Halles",
        "area_exists": True,
    },
    {
        "poi_name": "Rue Mouffetard",
        "area_name": "Rue Mouffetard",
        "area_exists": False,
        "area_type": "corridor",
        "parent_arr": "5th Arrondissement",
        "boundary": "POLYGON((2.3488 48.8412, 2.3508 48.8412, 2.3508 48.8445, 2.3488 48.8445, 2.3488 48.8412))",
    },
    {
        "poi_name": "Rue Visconti",
        "area_name": "Rue Visconti",
        "area_exists": False,
        "area_type": "corridor",
        "parent_arr": "6th Arrondissement",
        "boundary": "POLYGON((2.3348 48.8554, 2.3378 48.8554, 2.3378 48.8568, 2.3348 48.8568, 2.3348 48.8554))",
    },
    {
        "poi_name": "Rue Chanoinesse",
        "area_name": "Rue Chanoinesse",
        "area_exists": False,
        "area_type": "corridor",
        "parent_arr": "4th Arrondissement",
        "boundary": "POLYGON((2.3488 48.8522, 2.3515 48.8522, 2.3515 48.8538, 2.3488 48.8538, 2.3488 48.8522))",
    },
    {
        "poi_name": "Grands Boulevards",
        "area_name": "Grands Boulevards",
        "area_exists": False,
        "area_type": "corridor",
        "parent_arr": "2nd Arrondissement",
        "boundary": "POLYGON((2.3400 48.8695, 2.3470 48.8695, 2.3470 48.8730, 2.3400 48.8730, 2.3400 48.8695))",
    },
]


def get_total_beat_count(driver) -> int:
    with driver.session() as s:
        return s.run("MATCH (b:NarrativeBeat) RETURN count(b) AS cnt").single()["cnt"]


def get_poi_beats(driver, poi_name: str) -> list[dict]:
    """Get all beats for a POI, with their IDs and lens tag info."""
    with driver.session() as s:
        return s.run(
            """
            MATCH (p:POI {name: $name})-[r:HAS_BEAT]->(b:NarrativeBeat)
            RETURN b.id AS beat_id, r.sort_order AS sort_order
            """,
            name=poi_name,
        ).data()


def find_area_id(driver, area_name: str) -> str | None:
    with driver.session() as s:
        r = s.run(
            "MATCH (a:Area {name: $name}) RETURN a.id AS id",
            name=area_name,
        ).single()
        return r["id"] if r else None


def find_arrondissement_id(driver, arr_name: str) -> str | None:
    with driver.session() as s:
        r = s.run(
            "MATCH (a:Area {name: $name, area_type: 'district'}) RETURN a.id AS id",
            name=arr_name,
        ).single()
        return r["id"] if r else None


def create_corridor_area(poi_name: str, migration: dict, driver) -> str:
    """Create a corridor Area node via the API. Returns the new Area's ID."""
    # Get POI coordinates to use as centroid
    with driver.session() as s:
        poi = s.run(
            "MATCH (p:POI {name: $name}) RETURN p.location.latitude AS lat, p.location.longitude AS lng",
            name=poi_name,
        ).single()

    payload = {
        "name": migration["area_name"],
        "area_type": migration["area_type"],
        "city_name": "Paris",
        "boundary": migration["boundary"],
        "centroid_lat": poi["lat"],
        "centroid_lng": poi["lng"],
        "short_description": "",
    }
    resp = requests.post(f"{API_BASE}/nodes/Area", json=payload, timeout=30)
    resp.raise_for_status()
    area_id = resp.json()["id"]
    print(f"    Created corridor Area: {migration['area_name']} (id={area_id})")
    return area_id


def create_forum_des_halles_poi() -> str:
    """Create the Forum des Halles POI node. Returns its ID."""
    payload = {
        "name": "Forum des Halles",
        "latitude": 48.8620,
        "longitude": 2.3469,
        "importance_tier": 3,
        "short_description": "Modern shopping and transit complex on the site of the historic central market",
    }
    resp = requests.post(f"{API_BASE}/nodes/POI", json=payload, timeout=30)
    resp.raise_for_status()
    poi_id = resp.json()["id"]
    print(f"    Created POI: Forum des Halles (id={poi_id})")
    return poi_id


def create_within_edge(source_label: str, source_id: str, target_id: str):
    """Create a WITHIN edge via the API (MERGE = idempotent)."""
    payload = {
        "source": {"label": source_label, "id": source_id},
        "target": {"label": "Area", "id": target_id},
        "properties": {},
    }
    resp = requests.post(f"{API_BASE}/edges/WITHIN", json=payload, timeout=30)
    resp.raise_for_status()


def migrate_single_poi(driver, migration: dict):
    """Migrate one POI to an Area within a single Neo4j transaction."""
    poi_name = migration["poi_name"]
    area_name = migration["area_name"]

    # Step 1: Get beats from the POI
    beats = get_poi_beats(driver, poi_name)
    if not beats:
        print(f"  [{poi_name}] No beats found — skipping beat transfer")

    # Step 2: Find or create the target Area
    if migration["area_exists"]:
        area_id = find_area_id(driver, area_name)
        if not area_id:
            raise RuntimeError(f"Area '{area_name}' not found but marked as existing")
        print(f"    Found existing Area: {area_name} (id={area_id})")
    else:
        area_id = create_corridor_area(poi_name, migration, driver)

    # Step 3: Migrate beats and delete POI in a single transaction
    with driver.session() as s:
        with s.begin_transaction() as tx:
            # Create HAS_BEAT edges from Area to each beat (MERGE for safety)
            for beat in beats:
                tx.run(
                    """
                    MATCH (a:Area {id: $area_id}), (b:NarrativeBeat {id: $beat_id})
                    MERGE (a)-[r:HAS_BEAT]->(b)
                    SET r.id = coalesce(r.id, randomUUID()),
                        r.created_at = coalesce(r.created_at, datetime()),
                        r.sort_order = $sort_order
                    """,
                    area_id=area_id,
                    beat_id=beat["beat_id"],
                    sort_order=beat["sort_order"],
                )

            # Verify Area now has the expected beats
            count = tx.run(
                "MATCH (a:Area {id: $area_id})-[:HAS_BEAT]->(b) RETURN count(b) AS cnt",
                area_id=area_id,
            ).single()["cnt"]
            if count < len(beats):
                raise RuntimeError(
                    f"Beat count mismatch after transfer: expected {len(beats)}, got {count}"
                )

            # DETACH DELETE the old POI (removes old HAS_BEAT edges;
            # Beat→Lens TAGGED_WITH edges are unaffected)
            tx.run(
                "MATCH (p:POI {name: $name}) DETACH DELETE p",
                name=poi_name,
            )

            # Verify beats still have TAGGED_WITH edges
            orphaned_tags = tx.run(
                """
                MATCH (a:Area {id: $area_id})-[:HAS_BEAT]->(b:NarrativeBeat)
                WHERE NOT (b)-[:TAGGED_WITH]->()
                RETURN b.id
                """,
                area_id=area_id,
            ).data()
            if orphaned_tags:
                print(f"    WARNING: {len(orphaned_tags)} beats lost TAGGED_WITH edges")

            tx.commit()

    print(f"    Transferred {len(beats)} beats, deleted POI '{poi_name}'")
    return area_id


def main():
    driver = None
    try:
        driver = get_driver().__enter__()

        # Baseline
        baseline = get_total_beat_count(driver)
        print("=" * 70)
        print("POI-to-Area Migration")
        print("=" * 70)
        print(f"  Total beat baseline: {baseline}")
        print()

        area_ids = {}  # area_name -> area_id (for WITHIN edges later)

        # Phase 1: Migrate each POI
        for migration in MIGRATIONS:
            poi_name = migration["poi_name"]
            print(f"  [{poi_name}]")
            try:
                # Special handling for Les Halles: create Forum des Halles POI first
                if poi_name == "Les Halles":
                    forum_id = create_forum_des_halles_poi()
                    # All beats are historical — they all go to the Area (no beats for Forum)

                area_id = migrate_single_poi(driver, migration)
                area_ids[migration["area_name"]] = area_id
                print(f"    OK")
            except Exception as e:
                print(f"    FAILED: {e}")
                continue
            print()

        # Phase 2: Create WITHIN edges for corridor Areas
        print("-" * 70)
        print("Creating WITHIN edges for migrated Areas")
        print("-" * 70)
        for migration in MIGRATIONS:
            area_name = migration["area_name"]
            area_id = area_ids.get(area_name)
            if not area_id:
                continue

            # Check if WITHIN edge already exists
            with driver.session() as s:
                existing = s.run(
                    "MATCH (a:Area {id: $id})-[:WITHIN]->(:Area) RETURN count(*) AS cnt",
                    id=area_id,
                ).single()["cnt"]

            if existing > 0:
                print(f"  [SKIP] {area_name} — already has WITHIN edge")
                continue

            # Find parent arrondissement
            parent_arr = migration.get("parent_arr")
            if not parent_arr:
                # Islands and Les Halles should have WITHIN from Scope 2
                print(f"  [SKIP] {area_name} — no parent_arr defined (should exist from Scope 2)")
                continue

            parent_id = find_arrondissement_id(driver, parent_arr)
            if not parent_id:
                print(f"  [FAIL] {area_name} — parent '{parent_arr}' not found")
                continue

            try:
                create_within_edge("Area", area_id, parent_id)
                print(f"  [OK] {area_name} → {parent_arr}")
            except Exception as e:
                print(f"  [FAIL] {area_name} → {parent_arr}: {e}")

        # Phase 3: Verification
        print()
        print("=" * 70)
        print("Verification")
        print("=" * 70)

        post_count = get_total_beat_count(driver)
        print(f"  Beat count: {baseline} (before) → {post_count} (after)")
        if post_count != baseline:
            print(f"  FAIL — beat count changed by {post_count - baseline}!")
        else:
            print(f"  PASS — zero beat loss")

        # Orphaned beats check
        with driver.session() as s:
            orphans = s.run(
                "MATCH (b:NarrativeBeat) WHERE NOT ()-[:HAS_BEAT]->(b) RETURN count(b) AS cnt"
            ).single()["cnt"]
        print(f"  Orphaned beats: {orphans}")
        if orphans > 0:
            print(f"  FAIL — {orphans} beats have no parent!")
        else:
            print(f"  PASS — no orphaned beats")

        # Migrated POIs should not exist
        with driver.session() as s:
            remaining = s.run(
                """
                MATCH (n:POI)
                WHERE n.name IN $names
                RETURN n.name
                """,
                names=[m["poi_name"] for m in MIGRATIONS],
            ).data()
        if remaining:
            print(f"  FAIL — still POI nodes: {[r['n.name'] for r in remaining]}")
        else:
            print(f"  PASS — all migrated POIs deleted")

        # Forum des Halles exists
        with driver.session() as s:
            forum = s.run(
                "MATCH (p:POI {name: 'Forum des Halles'}) RETURN p.id"
            ).single()
        if forum:
            print(f"  PASS — Forum des Halles POI exists")
        else:
            print(f"  FAIL — Forum des Halles POI not found")

    finally:
        if driver:
            driver.close()


if __name__ == "__main__":
    main()
