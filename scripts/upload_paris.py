"""Bulk upload Paris data to Neo4j (local or Aura).

Reads from:
  - data/paris/poi-raw.json   (239 POIs with gravity/geocoding metadata)
  - data/paris/beats.json     (430 beats with fact-checking metadata)

Creates:
  - Schema constraints and indexes
  - Lens nodes (MVP + any additional lenses referenced by beats)
  - POI nodes with spatial points
  - NarrativeBeat nodes with full script bodies
  - HAS_BEAT relationships (POI → Beat)
  - TAGGED_WITH relationships (Beat → Lens)

Usage:
    make upload-paris
    # or directly:
    python scripts/upload_paris.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from src.connection import abort_on_connection_error, create_driver, get_database
from src.schema.constraints import apply_all
from src.seed.lenses import seed_lenses

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "paris"
POI_FILE = DATA_DIR / "poi-raw.json"
BEATS_FILE = DATA_DIR / "beats.json"


def _load_json(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def _ensure_lenses(session, lens_slugs: set[str]) -> int:
    """Create any lens nodes that don't already exist. Returns count created."""
    created = 0
    for slug in sorted(lens_slugs):
        display = slug.replace("_", " ").title()
        result = session.run(
            """
            MERGE (l:Lens {name: $name})
            ON CREATE SET
                l.id = randomUUID(),
                l.display_label = $display_label,
                l.is_parent = false
            RETURN l.id AS id
            """,
            name=slug,
            display_label=display,
        )
        result.consume()
        created += 1
    return created


def _upload_pois(session, pois: list[dict]) -> dict[str, int]:
    """Upload POI nodes with spatial points. Returns stats."""
    created = 0
    skipped = 0
    for poi in pois:
        lat = poi.get("latitude")
        lon = poi.get("longitude")
        if lat is None or lon is None:
            skipped += 1
            continue

        name_variations = poi.get("name_variations") or []
        if isinstance(name_variations, str):
            name_variations = [name_variations]

        session.run(
            """
            MERGE (p:POI {name: $name})
            ON CREATE SET p.id = randomUUID()
            SET p.short_description   = $short_description,
                p.location            = point({latitude: $lat, longitude: $lon, srid: 4326}),
                p.importance_tier     = $importance_tier,
                p.trigger_radius      = $trigger_radius,
                p.kid_friendly        = $kid_friendly,
                p.name_variations     = $name_variations
            """,
            name=poi["name"],
            short_description=poi.get("short_description", ""),
            lat=float(lat),
            lon=float(lon),
            importance_tier=poi.get("importance_tier", 1),
            trigger_radius=poi.get("trigger_radius", 10),
            kid_friendly=poi.get("kid_friendly", "yes"),
            name_variations=name_variations,
        )
        created += 1
    return {"created": created, "skipped": skipped}


def _upload_beats(session, beats: list[dict]) -> dict[str, int]:
    """Upload NarrativeBeat nodes and link to POIs + Lenses. Returns stats."""
    linked = 0
    orphaned = 0
    tagged = 0

    for beat in beats:
        poi_name = beat.get("poi_name", "")
        lens = beat.get("lens", "")
        script_body = beat.get("script_body", "")
        beat_id = beat.get("beat_id", "")

        if not poi_name or not script_body:
            orphaned += 1
            continue

        word_count = len(script_body.split())
        duration_sec = beat.get("duration_sec") or max(30, int(word_count / 2.5))
        kid_friendly = beat.get("kid_friendly", "yes")
        confidence = beat.get("confidence", "")
        fact_status = ""
        if isinstance(beat.get("fact_check"), dict):
            fact_status = beat["fact_check"].get("status", "")

        result = session.run(
            """
            MATCH (p:POI {name: $poi_name})
            MERGE (b:NarrativeBeat {beat_id: $beat_id})
            ON CREATE SET b.id = randomUUID()
            SET b.script_body    = $script_body,
                b.duration_sec   = $duration_sec,
                b.kid_friendly   = $kid_friendly,
                b.confidence     = $confidence,
                b.fact_status    = $fact_status,
                b.version        = 1,
                b.active_status  = 'active',
                b.audio_url      = ''
            MERGE (p)-[:HAS_BEAT]->(b)
            RETURN p.name AS poi
            """,
            poi_name=poi_name,
            beat_id=beat_id,
            script_body=script_body,
            duration_sec=duration_sec,
            kid_friendly=kid_friendly,
            confidence=confidence,
            fact_status=fact_status,
        )
        record = result.single()
        if record:
            linked += 1
        else:
            orphaned += 1
            continue

        if lens:
            session.run(
                """
                MATCH (b:NarrativeBeat {beat_id: $beat_id})
                MATCH (l:Lens {name: $lens})
                MERGE (b)-[:TAGGED_WITH]->(l)
                """,
                beat_id=beat_id,
                lens=lens,
            )
            tagged += 1

    return {"linked": linked, "orphaned": orphaned, "tagged": tagged}


@abort_on_connection_error
def main() -> None:
    db = get_database()
    db_label = f"cloud ({db})" if db else "local"
    print(f"\n{'='*60}")
    print(f"  PARIS DATA UPLOAD → Neo4j [{db_label}]")
    print(f"{'='*60}\n")

    pois = _load_json(POI_FILE)
    beats = _load_json(BEATS_FILE)
    print(f"  Source: {len(pois)} POIs, {len(beats)} beats\n")

    beat_lenses = {b["lens"] for b in beats if b.get("lens")}
    print(f"  Lenses referenced by beats: {len(beat_lenses)}")

    driver = create_driver()
    try:
        with driver.session(database=db) as session:
            # 1. Schema
            print("\n  [1/5] Applying schema constraints & indexes...")
            t0 = time.time()
        apply_all(driver)
        print(f"         Done ({time.time()-t0:.1f}s)")

        with driver.session(database=db) as session:
            # 2. Lenses
            print("  [2/5] Seeding lenses...")
            t0 = time.time()
            seed_lenses(driver)
            lens_count = _ensure_lenses(session, beat_lenses)
            print(f"         {lens_count} lenses ensured ({time.time()-t0:.1f}s)")

            # 3. POIs
            print(f"  [3/5] Uploading {len(pois)} POIs...")
            t0 = time.time()
            poi_stats = _upload_pois(session, pois)
            print(f"         {poi_stats['created']} created, {poi_stats['skipped']} skipped ({time.time()-t0:.1f}s)")

            # 4. Beats + relationships
            print(f"  [4/5] Uploading {len(beats)} beats + linking...")
            t0 = time.time()
            beat_stats = _upload_beats(session, beats)
            print(f"         {beat_stats['linked']} linked, {beat_stats['orphaned']} orphaned, {beat_stats['tagged']} tagged ({time.time()-t0:.1f}s)")

            # 5. Summary
            print("  [5/5] Verifying counts...")
            nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            poi_count = session.run("MATCH (n:POI) RETURN count(n) AS c").single()["c"]
            beat_count = session.run("MATCH (n:NarrativeBeat) RETURN count(n) AS c").single()["c"]
            lens_count = session.run("MATCH (n:Lens) RETURN count(n) AS c").single()["c"]

        print(f"\n{'='*60}")
        print(f"  UPLOAD COMPLETE")
        print(f"  Nodes: {nodes} ({poi_count} POIs, {beat_count} beats, {lens_count} lenses)")
        print(f"  Relationships: {rels}")
        print(f"{'='*60}\n")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
