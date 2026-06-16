#!/usr/bin/env python3
"""Generate WITHIN-edge staging file for a city from local data files.

City-parameterized (multi-city safe). Reads:
- data/{slug}/areas.json (Areas with polygons)
- data/{slug}/poi-raw.json (POIs with lat/lng)
- data/{slug}/boundaries/*.json (OSM polygons, list of [lat, lng])

Writes:
- data/{slug}/within_edges.json with shape:
    {
      "poi_to_area": [{"poi_name", "area_name", "area_type"}, ...],
      "area_to_area": [{"child_name", "child_type", "parent_name", "parent_type"}, ...]
    }

Validates: every POI in >=1 Area, exactly one root Area (parent_area is null),
the parent chain is acyclic, and every parent_area is in the roster.

Usage:
    python scripts/generate_within_edges.py --slug new_york
    python scripts/generate_within_edges.py            # defaults to paris
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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


def load_area_polygons(city_dir: Path) -> list[dict]:
    """Return [{name, area_type, parent_area, polygon}, ...] for all Areas."""
    boundaries = city_dir / "boundaries"
    areas = json.load(open(city_dir / "areas.json"))
    result = []
    for a in areas:
        if a.get("manual_boundary"):
            poly = a["manual_boundary"]
        elif a.get("osm_relation_id"):
            cf = boundaries / f"{a['osm_relation_id']}.json"
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default="paris", help="city slug (default: paris)")
    args = parser.parse_args()

    city_dir = ROOT / "data" / args.slug
    print(f"=== Generating WITHIN edges for '{args.slug}' (POI->Area + Area->Area) ===\n")

    areas = load_area_polygons(city_dir)
    pois = json.load(open(city_dir / "poi-raw.json"))
    print(f"Loaded {len(pois)} POIs, {len(areas)} Areas")

    # 1. POI->Area edges (point-in-polygon, multi-Area allowed)
    poi_to_area = []
    orphans = []
    for p in pois:
        lat, lng = p.get("latitude"), p.get("longitude")
        if lat is None:
            orphans.append(p["name"])
            continue
        matched = [a for a in areas if point_in_poly(lat, lng, a["polygon"])]
        if matched:
            for a in matched:
                poi_to_area.append({
                    "poi_name": p["name"],
                    "area_name": a["name"],
                    "area_type": a["area_type"],
                })
        else:
            orphans.append(p["name"])

    # 2. Area->Area edges (parent_area chain)
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
    print(f"POI->Area edges:  {len(poi_to_area)}")
    print(f"Area->Area edges: {len(area_to_area)}")
    print(f"Orphan POIs:     {len(orphans)}")
    for n in orphans:
        print(f"  - {n}")

    # Exactly one root Area (parent_area is null)
    roots = [a["name"] for a in areas if a["parent_area"] is None]
    print(f"\nRoot Areas (parent_area=null): {roots}")
    if len(roots) != 1:
        print(f"  ERROR: expected exactly one root, got {roots}")
        sys.exit(1)

    cycles = detect_cycles(parents)
    if cycles:
        print(f"  ERROR: cycle detected: {cycles}")
        sys.exit(1)
    print("Cycle check: PASS")

    # Write staging file
    out_path = city_dir / "within_edges.json"
    payload = {
        "_meta": {
            "generated_by": "scripts/generate_within_edges.py",
            "city_name": args.slug,
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
    print(f"Done -- {len(poi_to_area)} POI->Area + {len(area_to_area)} Area->Area edges")


if __name__ == "__main__":
    main()
