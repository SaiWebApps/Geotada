#!/usr/bin/env python3
"""Upload POI→Area WITHIN edges + the 2 Marais Area-attached beats.

Phase A-4 follow-up to scripts/create_paris_areas.py (which handles Areas + Area→Area).

Reads:
- data/paris/within_edges.json (POI→Area edges from staging)
- data/paris/beats.json (the 2 Marais Area-attached beats, poi_name='Marais')

Writes to Neo4j via REST API.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

PROJECT = Path(__file__).resolve().parent.parent
PARIS = PROJECT / "data" / "paris"
API = "http://localhost:8000/api/v1"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def fetch_all(label: str) -> list[dict]:
    items = []
    skip = 0
    while True:
        r = requests.get(f"{API}/nodes/{label}?skip={skip}&limit=200", timeout=30)
        r.raise_for_status()
        d = r.json()
        items.extend(d["items"])
        if skip + 200 >= d["total"]:
            break
        skip += 200
    return items


def post_edge(rel_type: str, source_label: str, source_id: str,
              target_label: str, target_id: str) -> bool:
    r = requests.post(
        f"{API}/edges/{rel_type}",
        json={
            "source": {"label": source_label, "id": source_id},
            "target": {"label": target_label, "id": target_id},
            "properties": {},
        },
        timeout=30,
    )
    return r.status_code in (200, 201)


# ----------------------------------------------------------------------
# 1. POI→Area WITHIN edges
# ----------------------------------------------------------------------

def upload_poi_to_area():
    print("=== Uploading POI→Area WITHIN edges ===\n")
    staging = json.load(open(PARIS / "within_edges.json"))

    pois_by_name = {}
    for p in fetch_all("POI"):
        # Build by name; multi-city safe via city_name filter
        if p["properties"].get("city_name") in ("paris", "Paris"):
            pois_by_name[p["properties"]["name"]] = p["id"]

    areas_by_key = {}
    for a in fetch_all("Area"):
        key = (a["properties"]["name"], a["properties"]["area_type"])
        areas_by_key[key] = a["id"]

    print(f"Resolved {len(pois_by_name)} POIs, {len(areas_by_key)} Areas in Neo4j")

    edges = staging["poi_to_area"]
    posted = 0
    failed = 0
    missing_poi = set()
    missing_area = set()
    for e in edges:
        poi_id = pois_by_name.get(e["poi_name"])
        area_id = areas_by_key.get((e["area_name"], e["area_type"]))
        if not poi_id:
            missing_poi.add(e["poi_name"]); failed += 1; continue
        if not area_id:
            missing_area.add((e["area_name"], e["area_type"])); failed += 1; continue
        if post_edge("WITHIN", "POI", poi_id, "Area", area_id):
            posted += 1
        else:
            failed += 1
            print(f"  FAILED edge: {e['poi_name']} -> {e['area_name']}")

    print(f"\nPOI→Area edges posted: {posted}/{len(edges)}")
    print(f"  Failed: {failed}")
    if missing_poi:
        print(f"  POIs not in Neo4j: {len(missing_poi)}")
        for n in sorted(missing_poi):
            print(f"    - {n}")
    if missing_area:
        print(f"  Areas not in Neo4j: {missing_area}")
    return posted, failed


# ----------------------------------------------------------------------
# 2. The 2 Marais Area-attached beats
# ----------------------------------------------------------------------

def upload_marais_area_beats():
    print("\n=== Uploading Marais Area-attached beats ===\n")
    beats_all = json.load(open(PARIS / "beats.json"))
    marais_beats = [b for b in beats_all if b.get("poi_name") == "Marais"]
    print(f"Found {len(marais_beats)} beats with poi_name='Marais' in beats.json")

    # Find Le Marais Area
    areas = fetch_all("Area")
    le_marais = next(
        (a for a in areas
         if a["properties"]["name"] == "Le Marais"
         and a["properties"]["area_type"] == "neighborhood"),
        None,
    )
    if not le_marais:
        print("ERROR: Le Marais Area not in Neo4j"); sys.exit(1)
    le_marais_id = le_marais["id"]

    # Lens lookup
    lenses = fetch_all("Lens")
    lens_by_name = {l["properties"]["name"]: l["id"] for l in lenses}

    # Allowed NarrativeBeat fields per upload.md "FORWARD" list
    forward_keys = {
        "script_body", "duration_sec", "est_spoken_seconds", "kid_friendly",
        "entities", "sensory_anchor", "narrative_function", "beat_type",
        "emotional_register", "subject_tag", "sub_location", "trigger_address",
        "beat_length_class", "physical_cues", "pronunciation",
        "inline_foreign_phrases",
    }

    results = []
    for beat in marais_beats:
        bid = beat["beat_id"]
        payload = {k: beat[k] for k in forward_keys if k in beat and beat[k] is not None}
        # script_body is required
        if "script_body" not in payload:
            print(f"  SKIP {bid}: no script_body"); continue
        # Coerce lens-required fields
        if "kid_friendly" not in payload:
            payload["kid_friendly"] = "yes"

        # MERGE NarrativeBeat
        r = requests.post(f"{API}/nodes/NarrativeBeat", json=payload, timeout=30)
        if r.status_code not in (200, 201):
            print(f"  FAILED beat create: {bid} -> {r.status_code} {r.text[:200]}")
            continue
        beat_node = r.json()
        beat_id = beat_node["id"]

        # HAS_BEAT: Area -> NarrativeBeat
        has_beat_ok = post_edge("HAS_BEAT", "Area", le_marais_id, "NarrativeBeat", beat_id)

        # TAGGED_WITH: NarrativeBeat -> Lens
        lens_name = beat.get("lens")
        lens_id = lens_by_name.get(lens_name)
        tagged_ok = False
        if lens_id:
            tagged_ok = post_edge("TAGGED_WITH", "NarrativeBeat", beat_id, "Lens", lens_id)
        else:
            print(f"  WARNING: lens '{lens_name}' not found")

        print(f"  ✓ {bid}: beat={beat_id[:8]}.. HAS_BEAT={'OK' if has_beat_ok else 'FAIL'} "
              f"TAGGED_WITH={'OK' if tagged_ok else 'FAIL'} (lens={lens_name})")
        results.append({"beat_id": bid, "neo4j_id": beat_id,
                        "has_beat": has_beat_ok, "tagged_with": tagged_ok})

    return results


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main():
    posted, failed = upload_poi_to_area()
    marais_results = upload_marais_area_beats()
    print(f"\n=== DONE ===")
    print(f"POI→Area edges: {posted} posted, {failed} failed")
    print(f"Marais Area beats attached: {len(marais_results)}/{len(marais_results)}")


if __name__ == "__main__":
    main()
