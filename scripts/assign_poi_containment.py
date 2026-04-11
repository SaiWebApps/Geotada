#!/usr/bin/env python3
"""Assign every Paris POI to its containing Area(s) via WITHIN edges.

For each POI, tests point-in-polygon against all Area boundaries and creates
WITHIN edges for every match. A POI can be in multiple Areas (e.g., Notre-Dame
is in Ile de la Cite AND 4th Arrondissement AND Paris).

Uses MERGE for idempotent re-runs.

Prerequisites:
    - Neo4j running with Areas from Scopes 1-3
    - API running: make api

Usage:
    python scripts/assign_poi_containment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.connection import get_driver
from src.utils.spatial import point_in_polygon

API_BASE = "http://localhost:8000/api/v1"
# Buffer for polygon simplification artifacts (~83m at Paris latitude)
BUFFER_DEG = 0.00075


def fetch_pois(session) -> list[dict]:
    """Fetch all POIs with their location coordinates."""
    result = session.run(
        "MATCH (p:POI) "
        "WHERE p.location IS NOT NULL "
        "RETURN p.id AS id, p.name AS name, p.location AS location "
        "ORDER BY p.name"
    ).data()
    pois = []
    for row in result:
        loc = row["location"]
        pois.append({
            "id": row["id"],
            "name": row["name"],
            "lat": loc.latitude,
            "lng": loc.longitude,
        })
    return pois


def fetch_areas(session) -> list[dict]:
    """Fetch all Areas with their boundaries."""
    result = session.run(
        "MATCH (a:Area) "
        "WHERE a.boundary IS NOT NULL "
        "RETURN a.id AS id, a.name AS name, a.area_type AS area_type, "
        "a.boundary AS boundary "
        "ORDER BY a.name"
    ).data()
    return result


def create_within_edge(poi_id: str, area_id: str) -> bool:
    """Create a WITHIN edge from POI to Area via the REST API."""
    resp = requests.post(
        f"{API_BASE}/edges/WITHIN",
        json={
            "source": {"label": "POI", "id": poi_id},
            "target": {"label": "Area", "id": area_id},
            "properties": {},
        },
        timeout=10,
    )
    return resp.status_code in (200, 201)


def main():
    print("=== POI Containment Assignment ===\n")

    with get_driver() as driver:
        with driver.session() as session:
            pois = fetch_pois(session)
            areas = fetch_areas(session)

    print(f"Loaded {len(pois)} POIs, {len(areas)} Areas\n")

    if not areas:
        print("ERROR: No Areas with boundaries found. Run Scope 2 first.")
        sys.exit(1)

    edges_created = 0
    orphans = []

    for poi in pois:
        matches = []
        for area in areas:
            if point_in_polygon(poi["lat"], poi["lng"], area["boundary"], buffer_deg=BUFFER_DEG):
                matches.append(area)

        if matches:
            area_names = []
            for area in matches:
                ok = create_within_edge(poi["id"], area["id"])
                if ok:
                    edges_created += 1
                    area_names.append(f'{area["name"]} ({area["area_type"]})')
                else:
                    print(f"  WARNING: Failed to create WITHIN edge: "
                          f"{poi['name']} -> {area['name']}")
            print(f"  {poi['name']} -> {', '.join(area_names)}")
        else:
            orphans.append(poi["name"])

    print(f"\n--- Summary ---")
    print(f"WITHIN edges created/confirmed: {edges_created}")
    print(f"POIs with 0 matches (orphans): {len(orphans)}")

    if orphans:
        print(f"\nOrphans:")
        for name in orphans:
            print(f"  - {name}")

    print("\nDone.")


if __name__ == "__main__":
    main()
