"""Fetch a city/area boundary polygon from OSM Overpass and cache it.

City-parameterized companion to ``src.utils.spatial.fetch_osm_boundary`` (whose
cache dir is hardcoded to Paris). Writes ``data/{slug}/boundaries/{relation}.json``
as a list of [lat, lng] pairs — the same on-disk format the rest of the pipeline
reads.

Usage:
    python -m scripts.fetch_city_boundary --slug new_york --relation 175905
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

from src.utils.spatial import _extract_outer_coords

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "Ondoway-pipeline/1.0 (serblowa@gmail.com)"}


def fetch_boundary(relation_id: int) -> list[tuple[float, float]]:
    """Fetch outer-ring coordinates (lat, lng) for an OSM relation."""
    query = f"""
    [out:json][timeout:60];
    relation({relation_id});
    out geom;
    """
    resp = None
    for attempt in range(4):
        resp = requests.post(OVERPASS_URL, data={"data": query}, headers=HEADERS, timeout=90)
        if resp.status_code in (429, 504):
            wait = 10 * (2**attempt)
            print(f"  Overpass {resp.status_code}, retrying in {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break
    else:
        resp.raise_for_status()

    coords = _extract_outer_coords(resp.json())
    if not coords:
        raise ValueError(f"No outer boundary found for OSM relation {relation_id}")
    return coords


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", required=True, help="city slug, e.g. new_york")
    parser.add_argument("--relation", required=True, type=int, help="OSM relation id")
    parser.add_argument(
        "--force", action="store_true", help="re-fetch even if the cache file exists"
    )
    args = parser.parse_args()

    out_dir = Path("data") / args.slug / "boundaries"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_file = out_dir / f"{args.relation}.json"

    if cache_file.exists() and not args.force:
        print(f"Cache hit: {cache_file} (use --force to re-fetch)")
        return

    coords = fetch_boundary(args.relation)
    with open(cache_file, "w") as f:
        json.dump(coords, f)

    lats = [c[0] for c in coords]
    lngs = [c[1] for c in coords]
    print(f"Wrote {len(coords)} vertices to {cache_file}")
    print(f"  bbox: lat [{min(lats):.5f}, {max(lats):.5f}]  lng [{min(lngs):.5f}, {max(lngs):.5f}]")


if __name__ == "__main__":
    main()
