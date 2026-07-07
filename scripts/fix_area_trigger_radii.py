"""Correct trigger_radius for physical-extent POIs that were modelled as undersized
points (see scripts/survey_area_candidates.py).

Radius is derived from the feature's REAL extent (OSM/Nominatim bounding box), not
guessed: radius = clamp(round(half_diagonal, 10), current..MAX). We only ever
INCREASE a radius — an existing larger value is left untouched. Each feature's pin
must already be near the OSM match (proximity sanity check) or it is skipped.

Dry-run by default. Pass --apply to write poi-raw.json (with a timestamped backup)
and an audit log to data/{city}/.area-radius-fix.json.

Usage:
    uv run python scripts/fix_area_trigger_radii.py --city new_york
    uv run python scripts/fix_area_trigger_radii.py --city new_york --apply
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

MAX_RADIUS = 500  # a "setting frame" cap; interiors are covered by child POIs
PROXIMITY_M = 800  # OSM match must be within this of the existing pin
# OSM types we accept as genuine physical extents (guards against transit/building hits)
EXTENT_TYPES = {
    "park",
    "garden",
    "nature_reserve",
    "cemetery",
    "recreation_ground",
    "common",
    "square",
    "pedestrian",
    "island",
    "beach",
    "grassland",
    "wood",
    "water",
    "bridge",
    "marketplace",
    "commercial",
}
HEADERS = {"User-Agent": "Ondoway-pipeline/1.0 (serblowa@gmail.com)"}


def nominatim(query: str) -> dict | None:
    url = (
        "https://nominatim.openstreetmap.org/search?"
        + urllib.parse.urlencode({"q": query, "format": "json", "limit": 1})
    )
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
    return data[0] if data else None


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def half_diagonal_m(bbox: list[str]) -> float:
    s, n, w, e = (float(x) for x in bbox)  # south, north, west, east
    midlat = (s + n) / 2
    h = (n - s) * 111000
    wm = (e - w) * 111000 * math.cos(math.radians(midlat))
    return math.hypot(h, wm) / 2


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="new_york")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    ap.add_argument(
        "--city-query", default="New York", help="appended to each POI name for the OSM query"
    )
    args = ap.parse_args()

    base = Path("data") / args.city
    cand_path = base / ".area-candidates.json"
    if not cand_path.exists():
        raise SystemExit(f"{cand_path} missing — run survey_area_candidates.py --json first")

    # Consider EVERY flagged extent, not just the survey's heuristic tiers — the
    # survey's tier depends on a per-city size table, but the real arbiter is the
    # live OSM extent fetched below (only-increase keeps already-correct radii safe).
    candidates = json.loads(cand_path.read_text())["candidates"]
    targets = {c["name"] for c in candidates}

    pois = json.loads((base / "poi-raw.json").read_text())
    by_name = {p["name"]: p for p in pois}

    changes, skipped = [], []
    for name in sorted(targets):
        p = by_name.get(name)
        if p is None or p.get("latitude") is None:
            skipped.append((name, "no POI / no coords"))
            continue
        if p.get("poi_role") == "walk_by_only":
            # Walk-by seasoning is intentionally small (silence-budget); don't inflate.
            skipped.append((name, "walk_by_only — left small by design"))
            continue
        try:
            m = nominatim(f"{name}, {args.city_query}")
        except Exception as exc:
            skipped.append((name, f"fetch error: {exc}"))
            time.sleep(1.1)
            continue
        time.sleep(1.1)  # Nominatim: max 1 req/s
        if not m or "boundingbox" not in m:
            skipped.append((name, "no OSM match"))
            continue
        dist = haversine_m(p["latitude"], p["longitude"], float(m["lat"]), float(m["lon"]))
        if dist > PROXIMITY_M:
            skipped.append((name, f"OSM match {round(dist)}m away — wrong feature?"))
            continue
        if m.get("type") not in EXTENT_TYPES and m.get("class") not in {"leisure", "natural"}:
            skipped.append((name, f"OSM type={m.get('type')} not an extent"))
            continue
        cur = p.get("trigger_radius") or 0
        proposed = min(round(half_diagonal_m(m["boundingbox"]) / 10) * 10, MAX_RADIUS)
        new = max(cur, proposed)
        if new == cur:
            skipped.append((name, f"already >= proposed ({cur}m >= {proposed}m)"))
            continue
        changes.append(
            {
                "name": name,
                "old_radius": cur,
                "new_radius": new,
                "osm_type": m.get("type"),
                "osm_match_dist_m": round(dist),
                "source": "OSM/Nominatim boundingbox",
                "osm_url": f"https://www.openstreetmap.org/{m.get('osm_type')}/{m.get('osm_id')}",
            }
        )

    print(f"\n=== trigger_radius corrections — {args.city} ===")
    print(f"{'old':>5} {'->':^4} {'new':>5}   osm_type        name")
    for c in changes:
        print(
            f"{c['old_radius']:>4}m  ->  {c['new_radius']:>4}m   "
            f"{(c['osm_type'] or '-'):<14}  {c['name']}"
        )
    print(f"\n{len(changes)} to change, {len(skipped)} skipped.")
    if skipped:
        print("--- skipped ---")
        for name, why in skipped:
            print(f"   {name}: {why}")

    if not args.apply:
        print("\n(dry-run — pass --apply to write)")
        return

    stamp = "20260616"
    backup = base / f"poi-raw.bak-arearadius-{stamp}.json"
    backup.write_text((base / "poi-raw.json").read_text())
    for c in changes:
        by_name[c["name"]]["trigger_radius"] = c["new_radius"]
    (base / "poi-raw.json").write_text(json.dumps(pois, indent=2, ensure_ascii=False))
    (base / ".area-radius-fix.json").write_text(
        json.dumps({"city": args.city, "changes": changes, "skipped": skipped}, indent=2)
    )
    print(f"\nApplied {len(changes)} changes. Backup: {backup.name}")


if __name__ == "__main__":
    main()
