"""Survey a city's POIs for ones that are physical extents (parks, squares, bridges,
cemeteries, gardens, islands, piers...) modelled as undersized points.

Read-only. Produces a ranked report grouped into three action tiers:

  Tier 1 (PROMOTE)   geometry is wrong for a centroid+radius (large or linear);
                     should become a polygon-backed Area node.
  Tier 2 (RESIZE)    right model (setting point), trigger_radius too small.
  Tier 3 (KEEP)      genuinely point-like; leave as-is.

Usage:
    uv run python scripts/survey_area_candidates.py --city new_york
    uv run python scripts/survey_area_candidates.py --city new_york \
        --json data/new_york/.area-candidates.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Name tokens that denote a physical footprint you move through / across.
EXTENT_RE = re.compile(
    r"\b(Park|Square|Garden|Gardens|Cemetery|Bridge|Island|Yards|High Line|Market|"
    r"Meadow|Pier|Plaza|Campus|Beach|Common|Mall|Esplanade|Promenade|Reservoir|"
    r"Terminal|Greenmarket|Waterfront)\b"
)

# Curated real-world half-extents (metres, centroid -> farthest edge) for the
# high-value features. Source: OSM relation bounding boxes, rounded. Used to
# quantify the mismatch; absence just means "unmeasured, classify by tokens".
REAL_HALF_EXTENT_M = {
    "Hudson River Park": 2000,
    "Riverside Park": 1900,
    "Flushing Meadows Corona Park": 1600,
    "Central Park": 1600,
    "Coney Island": 1200,
    "The High Line": 1100,
    "Green-Wood Cemetery": 900,
    "Brooklyn Bridge": 800,
    "Prospect Park": 800,
    "Brooklyn Bridge Park": 700,
    "New York Botanical Garden": 650,
    "Governors Island": 600,
    "Inwood Hill Park": 500,
    "Brooklyn Botanic Garden": 350,
    "Hudson Yards": 300,
    "Battery Park": 250,
    "Domino Park": 250,
    "Washington Square Park": 150,
    "Tompkins Square Park": 150,
    "Bryant Park": 150,
    "Sheep Meadow": 150,
    "Marcus Garvey Park": 150,
    "Rockefeller Center": 150,
    "Madison Square Park": 150,
    "Fort Greene Park": 150,
    "McCarren Park": 150,
    "Sunset Park": 150,
    "Conservatory Garden": 100,
    "Grand Central Terminal": 100,
    "Chelsea Market": 80,
    "Little Island": 80,
    "Gramercy Park": 50,
}

# Linear features: a centroid+radius is geometrically wrong regardless of size.
LINEAR_RE = re.compile(r"\b(High Line|Bridge|Promenade|Esplanade|Greenway)\b")

# Tier-1 promotion threshold: real extent this large can't be a point.
PROMOTE_REAL_M = 400
# Tier-2 resize threshold: features whose real extent exceeds current radius by this.
RESIZE_RATIO = 1.4


def classify(name: str, radius: int, real: int | None) -> tuple[str, str, int | None]:
    """Return (tier, action, suggested_radius)."""
    linear = bool(LINEAR_RE.search(name))
    if linear or (real is not None and real >= PROMOTE_REAL_M):
        why = "linear feature" if linear else f"~{real}m extent"
        return "1-PROMOTE", f"polygon Area node ({why}); radius can't represent it", None
    if real is not None:
        if real > radius * RESIZE_RATIO:
            return "2-RESIZE", f"bump trigger_radius {radius}m -> ~{real}m", real
        return "3-KEEP", "radius matches extent", radius
    # Unmeasured: token-based guess. Parks/beaches with a tiny radius are suspect.
    big_token = re.search(r"\b(Park|Beach|Cemetery|Island|Reservoir|Meadow)\b", name)
    if big_token and radius < 75:
        return "2-RESIZE?", f"likely under-sized ({radius}m) — verify extent", None
    return "3-KEEP", "point-like or unmeasured", radius


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="new_york")
    ap.add_argument("--json", help="optional path to also write machine-readable results")
    args = ap.parse_args()

    base = Path("data") / args.city
    pois = json.loads((base / "poi-raw.json").read_text())
    area_names = {a["name"] for a in json.loads((base / "areas.json").read_text())}

    rows = []
    for p in pois:
        name = p["name"]
        if name in area_names:
            continue  # already dual-modelled as an Area node
        if not (EXTENT_RE.search(name) or name in REAL_HALF_EXTENT_M):
            continue
        radius = p.get("trigger_radius") or 0
        real = REAL_HALF_EXTENT_M.get(name)
        tier, action, suggested = classify(name, radius, real)
        ratio = round(real / radius, 1) if (real and radius) else None
        rows.append(
            {
                "name": name,
                "tier": tier,
                "poi_role": p.get("poi_role"),
                "importance_tier": p.get("importance_tier"),
                "trigger_radius": radius,
                "real_half_extent_m": real,
                "mismatch_x": ratio,
                "suggested_radius": suggested,
                "action": action,
            }
        )

    def sort_key(r):
        return (r["tier"], -(r["mismatch_x"] or 0), -(r["real_half_extent_m"] or 0))

    rows.sort(key=sort_key)

    by_tier: dict[str, list] = {}
    for r in rows:
        by_tier.setdefault(r["tier"], []).append(r)

    print(f"\nArea-candidate survey — {args.city}  ({len(rows)} physical-extent POIs flagged)\n")
    for tier in sorted(by_tier):
        group = by_tier[tier]
        print(f"── Tier {tier}  ({len(group)}) " + "─" * 40)
        print(f"   {'curr':>5} {'real':>6} {'off':>6}  {'role':<9} t  name")
        for r in group:
            real = f"{r['real_half_extent_m']}m" if r["real_half_extent_m"] else "   ?"
            off = f"{r['mismatch_x']}x" if r["mismatch_x"] else "  ?"
            print(
                f"   {r['trigger_radius']:>4}m {real:>6} {off:>6}  "
                f"{(r['poi_role'] or '-'):<9} {r['importance_tier']}  {r['name']}"
            )
            print(f"        → {r['action']}")
        print()

    if args.json:
        out = Path(args.json)
        out.write_text(json.dumps({"city": args.city, "candidates": rows}, indent=2))
        print(f"Wrote {len(rows)} candidates to {out}")


if __name__ == "__main__":
    main()
