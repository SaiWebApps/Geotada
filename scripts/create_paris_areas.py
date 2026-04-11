#!/usr/bin/env python3
"""Create Paris area hierarchy in Neo4j via the REST API.

Reads data/paris/areas.json, fetches/loads boundary polygons, creates Area nodes,
and wires the WITHIN hierarchy.

Usage:
    # Start API first: make api
    python scripts/create_paris_areas.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import Polygon

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.spatial import (
    coords_to_wkt,
    fetch_osm_boundary,
    simplify_polygon,
)

API_BASE = "http://localhost:8000/api/v1"
AREAS_FILE = Path("data/paris/areas.json")


def load_areas() -> list[dict]:
    with open(AREAS_FILE) as f:
        return json.load(f)


def get_boundary(area: dict) -> list[tuple[float, float]]:
    """Get boundary coordinates — from OSM or manual definition."""
    if area.get("manual_boundary"):
        coords = [tuple(c) for c in area["manual_boundary"]]
        # Ensure closed
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        return coords

    osm_id = area.get("osm_relation_id")
    if not osm_id:
        raise ValueError(f"No boundary source for {area['name']}")

    return fetch_osm_boundary(osm_id)


def compute_centroid(coords: list[tuple[float, float]]) -> tuple[float, float]:
    """Compute centroid of a polygon. Returns (lat, lng)."""
    # Shapely uses (x=lng, y=lat)
    shapely_coords = [(lng, lat) for lat, lng in coords]
    poly = Polygon(shapely_coords)
    centroid = poly.centroid
    return (centroid.y, centroid.x)  # (lat, lng)


def create_area_node(area: dict, wkt_boundary: str, centroid: tuple[float, float]) -> dict:
    """Create an Area node via the API. Returns the response dict."""
    payload = {
        "name": area["name"],
        "area_type": area["area_type"],
        "city_name": area["city_name"],
        "boundary": wkt_boundary,
        "centroid_lat": centroid[0],
        "centroid_lng": centroid[1],
        "short_description": "",
    }
    resp = requests.post(
        f"{API_BASE}/nodes/Area",
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def create_within_edge(source_label: str, source_id: str, target_id: str) -> dict:
    """Create a WITHIN edge via the API."""
    payload = {
        "source": {"label": source_label, "id": source_id},
        "target": {"label": "Area", "id": target_id},
        "properties": {},
    }
    resp = requests.post(
        f"{API_BASE}/edges/WITHIN",
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def find_area_id(name: str, created_areas: dict[str, str]) -> str | None:
    """Look up area ID from our created areas map."""
    return created_areas.get(name)


def main():
    areas = load_areas()

    # Sort: city first, then districts, then sub-areas
    type_order = {"city": 0, "district": 1, "neighborhood": 2, "island": 2, "corridor": 2}
    areas.sort(key=lambda a: type_order.get(a["area_type"], 3))

    created_areas: dict[str, str] = {}  # name -> id
    results = []

    print("=" * 70)
    print("Creating Paris Area Hierarchy")
    print("=" * 70)
    print()

    # Phase 1: Create all Area nodes
    for area in areas:
        name = area["name"]
        try:
            raw_coords = get_boundary(area)
            simplified = simplify_polygon(raw_coords)
            wkt_boundary = coords_to_wkt(simplified)
            centroid = compute_centroid(simplified)
            vertex_count = len(simplified) - 1  # exclude closing vertex

            resp = create_area_node(area, wkt_boundary, centroid)
            area_id = resp["id"]
            created_areas[name] = area_id

            results.append({
                "name": name,
                "type": area["area_type"],
                "vertices": vertex_count,
                "parent": area.get("parent_area", "-"),
                "id": area_id,
                "status": "CREATED",
            })
            print(f"  [OK] {name} ({area['area_type']}) — {vertex_count} vertices")

            # Rate limit for OSM Overpass
            if area.get("osm_relation_id") and not area.get("manual_boundary"):
                time.sleep(5)

        except Exception as e:
            results.append({
                "name": name,
                "type": area["area_type"],
                "vertices": 0,
                "parent": area.get("parent_area", "-"),
                "id": None,
                "status": f"FAILED: {e}",
            })
            print(f"  [FAIL] {name}: {e}")

    print()
    print("-" * 70)
    print("Creating WITHIN edges")
    print("-" * 70)

    # Phase 2: Create WITHIN edges
    edge_count = 0
    for area in areas:
        parent_name = area.get("parent_area")
        if not parent_name:
            continue

        child_name = area["name"]
        child_id = created_areas.get(child_name)
        parent_id = created_areas.get(parent_name)

        if not child_id:
            print(f"  [SKIP] {child_name} — not created")
            continue
        if not parent_id:
            print(f"  [SKIP] {child_name} → {parent_name} — parent not created")
            continue

        try:
            create_within_edge("Area", child_id, parent_id)
            edge_count += 1
            print(f"  [OK] {child_name} → {parent_name}")
        except Exception as e:
            print(f"  [FAIL] {child_name} → {parent_name}: {e}")

    # Summary
    print()
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"{'Name':<30} {'Type':<15} {'Vertices':>8}  {'Parent':<25} {'Status'}")
    print("-" * 100)
    for r in results:
        print(f"{r['name']:<30} {r['type']:<15} {r['vertices']:>8}  {r['parent'] or '-':<25} {r['status']}")
    print()
    print(f"Areas created: {sum(1 for r in results if r['status'] == 'CREATED')}/{len(results)}")
    print(f"WITHIN edges: {edge_count}")


if __name__ == "__main__":
    main()
