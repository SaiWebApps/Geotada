#!/usr/bin/env python3
"""Generate WITHIN-edge staging file for Paris from local data files.

Reads:
- data/paris/areas.json (34 Areas with polygons)
- data/paris/poi-raw.json (303 POIs with lat/lng)
- data/paris/boundaries/*.json (OSM polygons)

Writes:
- data/paris/within_edges.json with shape:
    {
      "poi_to_area": [{"poi_name", "area_name", "area_type"}, ...],
      "area_to_area": [{"child_name", "child_type", "parent_name", "parent_type"}, ...]
    }

Validates: every POI in ≥1 Area (except Vincennes), no cycles, parent integrity.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PARIS = Path(__file__).resolve().parent.parent / "data" / "paris"
BOUNDARIES = PARIS / "boundaries"


def point_in_poly(lat: float, lng: float, poly: list[list[float]]) -> bool:
    """Ray-cast point-in-polygon. poly is list of [lat, lng] pairs."""
    if not poly:
        return False
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        yi, xi = poly[i][0], poly[i][1]
        yj, xj = poly[j][0], poly[j][1]
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def load_area_polygons() -> list[dict]:
    """Return [{name, area_type, parent_area, polygon}, ...] for all Areas."""
    areas = json.load(open(PARIS / "areas.json"))
    result = []
    for a in areas:
        if a.get("manual_boundary"):
            poly = a["manual_boundary"]
        elif a.get("osm_relation_id"):
            cf = BOUNDARIES / f"{a['osm_relation_id']}.json"
            if not cf.exists():
                print(f"  ERROR: missing boundary file for {a['name']} ({cf})")
                sys.exit(1)
            poly = json.load(open(cf))
        else:
            print(f"  ERROR: no boundary source for {a['name']}")
            sys.exit(1)
        result.append({
            "name": a["name"],
            "area_type": a["area_type"],
            "parent_area": a.get("parent_area"),
            "polygon": poly,
        })
    return result


def detect_cycles(parents: dict[str, str | None]) -> list[list[str]]:
    """Return list of cycles in the parent_area chain."""
    cycles = []
    for start in parents:
        seen = []
        node = start
        while node is not None:
            if node in seen:
                cycles.append(seen[seen.index(node):] + [node])
                break
            seen.append(node)
            node = parents.get(node)
    return cycles


def main():
    print("=== Generating WITHIN edges (POI→Area + Area→Area) ===\n")

    areas = load_area_polygons()
    pois = json.load(open(PARIS / "poi-raw.json"))
    print(f"Loaded {len(pois)} POIs, {len(areas)} Areas")

    # 1. POI→Area edges (point-in-polygon, multi-Area allowed)
    poi_to_area = []
    orphans = []
    for p in pois:
        lat, lng = p.get("latitude"), p.get("longitude")
        if lat is None:
            orphans.append(p["name"])
            continue
        matched = []
        for a in areas:
            if point_in_poly(lat, lng, a["polygon"]):
                matched.append(a)
        if matched:
            for a in matched:
                poi_to_area.append({
                    "poi_name": p["name"],
                    "area_name": a["name"],
                    "area_type": a["area_type"],
                })
        else:
            orphans.append(p["name"])

    # 2. Area→Area edges (parent_area chain)
    area_to_area = []
    parents = {a["name"]: a["parent_area"] for a in areas}
    type_lookup = {a["name"]: a["area_type"] for a in areas}
    for a in areas:
        if a["parent_area"]:
            if a["parent_area"] not in parents:
                print(f"  ERROR: {a['name']} -> {a['parent_area']} (parent not in roster)")
                sys.exit(1)
            area_to_area.append({
                "child_name": a["name"],
                "child_type": a["area_type"],
                "parent_name": a["parent_area"],
                "parent_type": type_lookup[a["parent_area"]],
            })

    # 3. Validation
    print("\n--- Validation ---")
    print(f"POI→Area edges:  {len(poi_to_area)}")
    print(f"Area→Area edges: {len(area_to_area)}")
    print(f"Orphan POIs:     {len(orphans)}")
    for n in orphans:
        print(f"  - {n}")

    # Every Area except Paris has exactly one parent
    no_parent = [a["name"] for a in areas if a["parent_area"] is None]
    print(f"\nAreas without parent (should be just 'Paris'): {no_parent}")
    if no_parent != ["Paris"]:
        print(f"  ERROR: expected ['Paris'], got {no_parent}")
        sys.exit(1)

    cycles = detect_cycles(parents)
    if cycles:
        print(f"  ERROR: cycle detected: {cycles}")
        sys.exit(1)
    print("Cycle check: PASS")

    # Le Marais POI count post-expansion
    marais_count = sum(1 for e in poi_to_area if e["area_name"] == "Le Marais")
    print(f"\nLe Marais POI membership: {marais_count}")
    if marais_count < 40:
        print(f"  WARNING: expected ≥40, got {marais_count}")

    # Tier-5 anchor membership spot-check
    print("\n--- Tier-5 anchor membership spot-check ---")
    tier5 = ["Notre-Dame Cathedral", "Eiffel Tower", "Louvre Museum",
             "Place des Vosges", "Sacre-Coeur Basilica", "Conciergerie",
             "Arc de Triomphe", "Sainte-Chapelle"]
    by_poi = {}
    for e in poi_to_area:
        by_poi.setdefault(e["poi_name"], []).append(e["area_name"])
    for t in tier5:
        membership = by_poi.get(t, [])
        marker = "✓" if membership else "✗"
        print(f"  {marker} {t}: {membership}")

    # Write staging file
    out_path = PARIS / "within_edges.json"
    payload = {
        "_meta": {
            "generated_by": "scripts/generate_within_edges.py",
            "city_name": "Paris",
            "total_pois": len(pois),
            "total_areas": len(areas),
            "poi_to_area_count": len(poi_to_area),
            "area_to_area_count": len(area_to_area),
            "orphans": orphans,
        },
        "poi_to_area": sorted(poi_to_area, key=lambda x: (x["poi_name"], x["area_name"])),
        "area_to_area": sorted(area_to_area, key=lambda x: (x["child_name"], x["parent_name"])),
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"\nWrote {out_path}")
    print(f"Done — {len(poi_to_area)} POI→Area + {len(area_to_area)} Area→Area edges")


if __name__ == "__main__":
    main()
