"""Phase 2.6 — Latin Quarter polygon overshoot fix.

Tightens the Latin Quarter polygon so it stops engulfing the southern
half of Île de la Cité (Notre-Dame, Crypte, Mémorial Déportation). The
fix in `data/paris/areas.json` is the canonical source; this script
propagates it to the live Neo4j graph:

1. Updates the `Latin Quarter` Area's boundary WKT to the new 6-vertex
   shape (NE step-down so the polygon respects the Seine's south bank).
2. Deletes the three now-incorrect (POI)-[:WITHIN]->(:Area {Latin Quarter})
   edges (Notre-Dame Cathedral, Crypte Archéologique, Mémorial Déportation).
3. Verifies the spot-check from the Areas-closeout report.

Idempotent: re-running is a no-op once the boundary and edges are correct.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.connection import create_driver
from src.utils.spatial import coords_to_wkt

LEAKED_POIS = (
    "Notre-Dame Cathedral",
    "Crypte Archeologique de l'Ile de la Cite",
    "Memorial des Martyrs de la Deportation",
)


def _latin_quarter_polygon() -> list[tuple[float, float]]:
    src = Path("data/paris/areas.json")
    for a in json.loads(src.read_text()):
        if a["name"] == "Latin Quarter":
            return [tuple(p) for p in a["manual_boundary"]]
    raise RuntimeError("Latin Quarter not found in areas.json")


def main() -> int:
    coords = _latin_quarter_polygon()
    new_wkt = coords_to_wkt(coords)
    print(f"New WKT: {new_wkt}")

    driver = create_driver()
    try:
        with driver.session() as session:
            # 1. Update boundary on the Latin Quarter Area node.
            session.run(
                "MATCH (a:Area {name: 'Latin Quarter', city_name: 'Paris'}) "
                "SET a.boundary = $wkt",
                wkt=new_wkt,
            )
            print("  Updated Latin Quarter boundary on Area node.")

            # 2. Delete the leaked WITHIN edges.
            for poi_name in LEAKED_POIS:
                r = session.run(
                    "MATCH (p:POI {city_name: 'paris', name: $poi})"
                    "-[r:WITHIN]->(a:Area {name: 'Latin Quarter'}) "
                    "DELETE r RETURN count(r) AS deleted",
                    poi=poi_name,
                ).single()
                deleted = r["deleted"] if r else 0
                print(f"  {poi_name}: deleted {deleted} WITHIN edge(s).")

            # 3. Spot-check.
            print("\n--- Spot-check after fix ---")
            for poi_name in (*LEAKED_POIS, "Sainte-Chapelle", "The Sorbonne"):
                r = session.run(
                    "MATCH (p:POI {city_name: 'paris', name: $poi})"
                    "-[:WITHIN]->(a:Area) RETURN collect(a.name) AS areas",
                    poi=poi_name,
                ).single()
                areas = r["areas"] if r else []
                print(f"  {poi_name}: {sorted(areas)}")
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
