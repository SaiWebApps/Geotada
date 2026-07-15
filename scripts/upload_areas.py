#!/usr/bin/env python3
"""Upload a city's Area hierarchy + WITHIN edges to Neo4j via the REST API.

City-parameterized (multi-city safe). Does, idempotently (all MERGE-based):
  1. Area nodes        <- data/{slug}/areas.json (boundary from OSM cache or manual_boundary)
  2. Area->Area WITHIN <- areas.json parent_area chain
  3. POI->Area WITHIN  <- data/{slug}/within_edges.json (poi_to_area)

Prereqs: API running (make api) and the city's POIs already uploaded (make upload CITY=...).

Usage:
    python scripts/upload_areas.py --slug new_york
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import Polygon

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.city_registry import onboard_data_root
from src.utils.spatial import coords_to_wkt, fetch_osm_boundary, simplify_polygon

API = "http://localhost:8000/api/v1"


def _city_data_dir(slug: str) -> Path:
    """The city's corpus dir under the hermetic-aware data root
    (``$ONBOARD_DATA_ROOT`` when set, else ``<repo>/data``). Unset → the prior
    ``<repo>/data/{slug}`` exactly, so real deploys are byte-identical."""
    return onboard_data_root() / slug


def get_boundary(area: dict, slug: str) -> list[tuple[float, float]]:
    """Boundary coords as (lat, lng) — from manual_boundary or the OSM cache."""
    if area.get("manual_boundary"):
        coords = [tuple(c) for c in area["manual_boundary"]]
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        return coords
    osm_id = area.get("osm_relation_id")
    if not osm_id:
        raise ValueError(f"No boundary source for {area['name']}")
    return fetch_osm_boundary(osm_id, city_slug=slug)


def compute_centroid(coords: list[tuple[float, float]]) -> tuple[float, float]:
    poly = Polygon([(lng, lat) for lat, lng in coords])
    c = poly.centroid
    return (c.y, c.x)


def post_edge(rel_type: str, src_label: str, src_id: str, tgt_label: str, tgt_id: str) -> bool:
    r = requests.post(
        f"{API}/edges/{rel_type}",
        json={
            "source": {"label": src_label, "id": src_id},
            "target": {"label": tgt_label, "id": tgt_id},
            "properties": {},
        },
        timeout=30,
    )
    return r.status_code in (200, 201)


def fetch_all(label: str) -> list[dict]:
    items, skip = [], 0
    while True:
        r = requests.get(f"{API}/nodes/{label}?skip={skip}&limit=200", timeout=30)
        r.raise_for_status()
        d = r.json()
        items.extend(d["items"])
        if skip + 200 >= d["total"]:
            break
        skip += 200
    return items


def upload_areas(areas: list[dict], slug: str) -> dict[str, str]:
    """Create Area nodes; return {name: id}."""
    type_order = {"city": 0, "borough": 1, "district": 1, "neighborhood": 2,
                  "island": 2, "corridor": 2}
    areas = sorted(areas, key=lambda a: type_order.get(a["area_type"], 3))

    created: dict[str, str] = {}
    print("=== Area nodes ===")
    for area in areas:
        name = area["name"]
        try:
            coords = get_boundary(area, slug)
            simplified = simplify_polygon(coords)
            wkt = coords_to_wkt(simplified)
            centroid = compute_centroid(simplified)
            payload = {
                "name": name,
                "area_type": area["area_type"],
                "city_name": area["city_name"],
                "boundary": wkt,
                "centroid_lat": centroid[0],
                "centroid_lng": centroid[1],
                "short_description": "",
            }
            r = requests.post(f"{API}/nodes/Area", json=payload, timeout=30)
            r.raise_for_status()
            created[name] = r.json()["id"]
            print(f"  [OK] {name} ({area['area_type']}) — {len(simplified) - 1} vertices")
            if area.get("osm_relation_id") and not area.get("manual_boundary"):
                time.sleep(1)
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
    return created


def upload_area_to_area(areas: list[dict], created: dict[str, str]) -> int:
    print("\n=== Area->Area WITHIN edges ===")
    n = 0
    for area in areas:
        parent = area.get("parent_area")
        if not parent:
            continue
        cid, pid = created.get(area["name"]), created.get(parent)
        if not cid or not pid:
            print(f"  [SKIP] {area['name']} -> {parent} (missing node)")
            continue
        if post_edge("WITHIN", "Area", cid, "Area", pid):
            n += 1
            print(f"  [OK] {area['name']} -> {parent}")
        else:
            print(f"  [FAIL] {area['name']} -> {parent}")
    return n


def upload_poi_to_area(slug: str, city_name: str, created: dict[str, str]) -> tuple[int, int]:
    print("\n=== POI->Area WITHIN edges ===")
    with open(_city_data_dir(slug) / "within_edges.json") as f:
        staging = json.load(f)
    pois_by_name = {
        p["properties"]["name"]: p["id"]
        for p in fetch_all("POI")
        if p["properties"].get("city_name") == city_name
    }
    # Resolve Areas by name (created this run) or by querying.
    areas_by_name = dict(created)
    if not areas_by_name:
        for a in fetch_all("Area"):
            if a["properties"].get("city_name") == city_name:
                areas_by_name[a["properties"]["name"]] = a["id"]
    print(f"Resolved {len(pois_by_name)} POIs, {len(areas_by_name)} Areas")

    posted = failed = 0
    missing_poi, missing_area = set(), set()
    for e in staging["poi_to_area"]:
        poi_id = pois_by_name.get(e["poi_name"])
        area_id = areas_by_name.get(e["area_name"])
        if not poi_id:
            missing_poi.add(e["poi_name"])
            failed += 1
            continue
        if not area_id:
            missing_area.add(e["area_name"])
            failed += 1
            continue
        if post_edge("WITHIN", "POI", poi_id, "Area", area_id):
            posted += 1
        else:
            failed += 1
    print(f"POI->Area edges posted: {posted}/{len(staging['poi_to_area'])} (failed {failed})")
    if missing_poi:
        print(f"  POIs not in Neo4j ({len(missing_poi)}): {sorted(missing_poi)[:10]}")
    if missing_area:
        print(f"  Areas not in Neo4j: {sorted(missing_area)}")
    return posted, failed


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", required=True, help="city slug, e.g. new_york")
    args = ap.parse_args()

    with open(_city_data_dir(args.slug) / "areas.json") as f:
        areas = json.load(f)
    city_name = areas[0]["city_name"]
    print(f"Uploading {len(areas)} Areas for '{args.slug}' (city_name={city_name})\n")

    created = upload_areas(areas, args.slug)
    a2a = upload_area_to_area(areas, created)
    posted, failed = upload_poi_to_area(args.slug, city_name, created)

    print("\n=== DONE ===")
    print(f"Area nodes:      {len(created)}/{len(areas)}")
    print(f"Area->Area:      {a2a}")
    print(f"POI->Area:       {posted} posted, {failed} failed")


if __name__ == "__main__":
    main()
