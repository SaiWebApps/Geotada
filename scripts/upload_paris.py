"""Bulk upload a city's data to Neo4j (local or Aura).

City-parameterized: pass a city slug (default ``paris``). Reads from
``data/{city_slug}/poi-raw.json`` and ``data/{city_slug}/beats.json`` and
rejects POIs outside the city's bbox in ``CITY_BBOX`` (the out-of-city geofence
guard). Add a new city by adding its bbox to ``CITY_BBOX``.

Creates:
  - Schema constraints and indexes
  - Lens nodes (MVP + any additional lenses referenced by beats)
  - POI nodes with spatial points
  - NarrativeBeat nodes with full script bodies
  - HAS_BEAT relationships (POI → Beat)
  - TAGGED_WITH relationships (Beat → Lens)

Usage:
    make upload-paris                 # Paris (default)
    make upload CITY=new_york         # any city in CITY_BBOX
    # or directly:
    python -m scripts.upload_paris new_york
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from src.api.models.nodes import canonical_name_key
from src.connection import abort_on_connection_error, create_driver, get_database
from src.schema.constraints import apply_all
from src.seed.lenses import seed_lenses

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _assert_upload_target_allowed(allow_cloud: bool) -> None:
    """Refuse an upload against a non-local (Aura) target unless --allow-cloud.

    The upload path plain-SETs live fields (e.g. ``beat.audio_url = ''``), so an
    accidental run while ``.env`` is in cloud mode overwrites production. This
    fires BEFORE any driver is created, so it protects even when Aura is
    unreachable/paused. A deliberate cloud upload is still possible by typing
    ``--allow-cloud`` explicitly.
    """
    if allow_cloud:
        return
    uri = os.getenv("NEO4J_URI", "")
    host = urlparse(uri).hostname or ""
    if host not in _LOCAL_HOSTS:
        raise SystemExit(
            f"REFUSING to upload against non-local NEO4J_URI={uri!r} (host={host!r}). "
            f"This path overwrites live fields (audio_url='' etc.). Run `make use-local` "
            f"first, or pass --allow-cloud to deliberately target Aura."
        )


REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = Path(__file__).resolve().parent / "validate_beats.py"

# Generous per-city bounding boxes (city + inner edges): reject gross coordinate
# errors (a Boston POI, (0,0), or out-of-city leaks) without clipping legitimate
# edge POIs. (min_lat, max_lat, min_lon, max_lon)
CITY_BBOX: dict[str, tuple[float, float, float, float]] = {
    "paris": (48.70, 49.00, 2.10, 2.60),
    "new_york": (40.45, 40.93, -74.28, -73.68),
}
PARIS_BBOX = CITY_BBOX["paris"]  # back-compat default


def _city_paths(city_slug: str) -> tuple[Path, Path]:
    data_dir = REPO_ROOT / "data" / city_slug
    return data_dir / "poi-raw.json", data_dir / "beats.json"

# fact_check.status values that must never reach the live database.
_BLOCKED_STATUSES = {"disputed"}


def _load_json(path: Path) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def _in_city_bounds(lat: float, lon: float, bbox: tuple = PARIS_BBOX) -> bool:
    return bbox[0] <= lat <= bbox[1] and bbox[2] <= lon <= bbox[3]


def _beat_blocked(beat: dict) -> bool:
    """True if a beat must NOT be uploaded — currently: missing essentials or a
    `disputed` fact-check status. (Note: this does NOT require `verified`;
    uploading unverified beats is a launch-policy decision left to the operator.)"""
    if not beat.get("poi_name") or not beat.get("script_body"):
        return True
    return (beat.get("fact_check") or {}).get("status") in _BLOCKED_STATUSES


def _assert_beats_valid(beats_path: Path) -> None:
    """Run the full validate_beats gate before any DB write (AC-9). Aborts the
    upload if the beats file fails — so grounding, verification-freshness,
    uniqueness, and status checks all gate the upload, not just extraction."""
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(beats_path)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Refusing to upload: validate_beats rejected the beats file.\n"
            + (result.stdout or "")
            + (result.stderr or "")
        )


def _ensure_lenses(session, lens_slugs: set[str]) -> int:
    """Create any lens nodes that don't already exist. Returns count created."""
    params = [
        {"name": slug, "display_label": slug.replace("_", " ").title()}
        for slug in sorted(lens_slugs)
    ]
    result = session.run(
        """
        UNWIND $lenses AS lens
        MERGE (l:Lens {name: lens.name})
        ON CREATE SET
            l.id = randomUUID(),
            l.display_label = lens.display_label,
            l.is_parent = false
        RETURN count(l) AS total
        """,
        lenses=params,
    )
    return result.single()["total"]


def _upload_pois(session, pois: list[dict], city_name: str, bbox: tuple) -> dict[str, int]:
    """Upload POI nodes with spatial points via batched UNWIND. Returns stats."""
    params = []
    skipped = 0
    out_of_bounds = 0
    for poi in pois:
        lat = poi.get("latitude")
        lon = poi.get("longitude")
        if lat is None or lon is None:
            skipped += 1
            continue
        if not _in_city_bounds(float(lat), float(lon), bbox):
            # Coordinate hygiene: never upload a POI outside the city geofence
            # (catches the Boston-POI class, (0,0), and stray coords).
            print(f"         ! skipping out-of-bounds POI {poi.get('name')!r} @ ({lat}, {lon})")
            out_of_bounds += 1
            continue

        name_variations = poi.get("name_variations") or []
        if isinstance(name_variations, str):
            name_variations = [name_variations]

        params.append({
            "name": poi["name"],
            # Canonical dedup key (defect 3), computed identically to create_node
            # so a later API create/edit MERGEs onto this node instead of forking.
            "name_key": canonical_name_key(poi["name"]),
            "city_name": city_name,
            "short_description": poi.get("short_description", ""),
            "lat": float(lat),
            "lon": float(lon),
            "importance_tier": poi.get("importance_tier", 1),
            "trigger_radius": poi.get("trigger_radius", 10),
            "kid_friendly": poi.get("kid_friendly", "yes"),
            "name_variations": name_variations,
            "poi_role": poi.get("poi_role"),
        })

    result = session.run(
        """
        UNWIND $pois AS poi
        MERGE (p:POI {name_key: poi.name_key, city_name: poi.city_name})
        ON CREATE SET p.id = randomUUID()
        SET p.name                = poi.name,
            p.short_description   = poi.short_description,
            p.location            = point({latitude: poi.lat, longitude: poi.lon, srid: 4326}),
            p.importance_tier     = poi.importance_tier,
            p.trigger_radius      = poi.trigger_radius,
            p.kid_friendly        = poi.kid_friendly,
            p.name_variations     = poi.name_variations,
            p.poi_role            = poi.poi_role
        RETURN count(p) AS total
        """,
        pois=params,
    )
    created = result.single()["total"]
    return {"created": created, "skipped": skipped, "out_of_bounds": out_of_bounds}


def _provenance_fields(beat: dict) -> dict:
    """The three VERIFY provenance/faithfulness fields (M7 / Phase 4 Step 4.0).

    Normalized so absence stays absent: `SET x = null` in Neo4j REMOVES the
    property, so a beat without provenance never gains a null-valued key.
    """
    passage = (beat.get("source_passage") or "").strip() or None
    chunk_slug = (beat.get("source_chunk_slug") or "").strip() or None
    claims = [s.strip() for s in (beat.get("key_claims") or []) if isinstance(s, str) and s.strip()]
    return {
        "source_passage": passage,
        "source_chunk_slug": chunk_slug,
        "key_claims": claims or None,
    }


def _backfill_provenance(session, beats: list[dict]) -> dict[str, int]:
    """Set ONLY the three provenance fields on existing beats (match by beat_id).

    The full upload path plain-SETs fields like ``beat.audio_url = ''``, so
    re-running it against a live graph is destructive. Backfilling provenance
    onto an already-uploaded graph must therefore never go through it.
    """
    params = []
    for beat in beats:
        beat_id = beat.get("beat_id", "")
        if not beat_id:
            continue
        fields = _provenance_fields(beat)
        if not any(fields.values()):
            continue
        params.append({"beat_id": beat_id, **fields})
    result = session.run(
        """
        UNWIND $beats AS b
        MATCH (beat:NarrativeBeat {beat_id: b.beat_id})
        SET beat.source_passage    = b.source_passage,
            beat.source_chunk_slug = b.source_chunk_slug,
            beat.key_claims        = b.key_claims
        RETURN count(beat) AS updated
        """,
        beats=params,
    )
    updated = result.single()["updated"]
    return {"updated": updated, "candidates": len(params)}


def _upload_beats(session, beats: list[dict]) -> dict[str, int]:
    """Upload NarrativeBeat nodes and link to POIs + Lenses via batched UNWIND."""
    params = []
    pre_skipped = 0
    blocked = 0
    no_beat_id = 0

    for beat in beats:
        poi_name = beat.get("poi_name", "")
        script_body = beat.get("script_body", "")
        beat_id = beat.get("beat_id", "")

        if not beat_id:
            # MERGE (beat:NarrativeBeat {beat_id: ""}) has no uniqueness
            # constraint behind it, so a second empty-beat_id beat would MATCH
            # the first node and SET-overwrite it — silently collapsing distinct
            # beats into one. Refuse rather than corrupt: an empty beat_id is a
            # data defect the validate_beats gate should have caught upstream.
            no_beat_id += 1
            continue
        if not poi_name or not script_body:
            pre_skipped += 1
            continue
        if (beat.get("fact_check") or {}).get("status") in _BLOCKED_STATUSES:
            blocked += 1  # disputed beats never go live
            continue

        word_count = len(script_body.split())
        duration_sec = beat.get("duration_sec") or max(30, int(word_count / 2.5))
        kid_friendly = beat.get("kid_friendly", "yes")
        confidence = beat.get("confidence", "")
        fact_status = ""
        if isinstance(beat.get("fact_check"), dict):
            fact_status = beat["fact_check"].get("status", "")

        # Neo4j cannot store list[dict]; JSON-encode physical_cues (matches the engine's
        # _decode_physical_cues and the API's _encode_complex_props). entities is list[str]
        # and stores natively. Both are read back by src/tour/selection.py.
        raw_cues = beat.get("physical_cues")
        _cues_ok = (
            isinstance(raw_cues, list)
            and raw_cues
            and all(isinstance(c, dict) for c in raw_cues)
        )
        physical_cues = json.dumps(raw_cues) if _cues_ok else None

        params.append({
            "poi_name": poi_name,
            "beat_id": beat_id,
            "script_body": script_body,
            "duration_sec": duration_sec,
            "kid_friendly": kid_friendly,
            "confidence": confidence,
            "fact_status": fact_status,
            "lens": beat.get("lens", ""),
            "sub_location": beat.get("sub_location"),
            "trigger_address": beat.get("trigger_address"),
            "narrative_function": beat.get("narrative_function"),
            "beat_type": beat.get("beat_type"),
            "emotional_register": beat.get("emotional_register"),
            "beat_length_class": beat.get("beat_length_class"),
            "est_spoken_seconds": beat.get("est_spoken_seconds"),
            "entities": beat.get("entities") or [],
            "subject_tag": beat.get("subject_tag"),
            "physical_cues": physical_cues,
            "pronunciation": beat.get("pronunciation"),
            **_provenance_fields(beat),
        })

    result = session.run(
        """
        UNWIND $beats AS b
        OPTIONAL MATCH (p:POI {name: b.poi_name})
        WITH b, p WHERE p IS NOT NULL
        MERGE (beat:NarrativeBeat {beat_id: b.beat_id})
        ON CREATE SET beat.id = randomUUID()
        SET beat.script_body    = b.script_body,
            beat.duration_sec   = b.duration_sec,
            beat.kid_friendly   = b.kid_friendly,
            beat.confidence     = b.confidence,
            beat.fact_status    = b.fact_status,
            beat.version        = 1,
            beat.active_status  = 'active',
            beat.audio_url      = '',
            beat.sub_location       = b.sub_location,
            beat.trigger_address    = b.trigger_address,
            beat.narrative_function = b.narrative_function,
            beat.beat_type          = b.beat_type,
            beat.emotional_register = b.emotional_register,
            beat.beat_length_class  = b.beat_length_class,
            beat.est_spoken_seconds = b.est_spoken_seconds,
            beat.entities           = b.entities,
            beat.subject_tag        = b.subject_tag,
            beat.physical_cues      = b.physical_cues,
            beat.pronunciation      = b.pronunciation,
            beat.source_passage     = b.source_passage,
            beat.source_chunk_slug  = b.source_chunk_slug,
            beat.key_claims         = b.key_claims
        MERGE (p)-[:HAS_BEAT]->(beat)
        RETURN count(beat) AS linked
        """,
        beats=params,
    )
    linked = result.single()["linked"]
    orphaned = len(params) - linked + pre_skipped

    taggable = [b for b in params if b["lens"]]
    if taggable:
        tag_result = session.run(
            """
            UNWIND $beats AS b
            MATCH (beat:NarrativeBeat {beat_id: b.beat_id})
            MATCH (l:Lens {name: b.lens})
            MERGE (beat)-[:TAGGED_WITH]->(l)
            RETURN count(*) AS tagged
            """,
            beats=taggable,
        )
        tagged = tag_result.single()["tagged"]
    else:
        tagged = 0

    return {
        "linked": linked,
        "orphaned": orphaned,
        "tagged": tagged,
        "blocked": blocked,
        "no_beat_id": no_beat_id,
    }


@abort_on_connection_error
def main() -> None:
    allow_cloud = "--allow-cloud" in sys.argv
    # Guard BEFORE any driver/session is opened: an accidental cloud-mode run
    # must not reach create_driver() (protects even when Aura is paused).
    _assert_upload_target_allowed(allow_cloud)

    # First non-flag arg is the city slug (flags like --allow-cloud/--provenance-only
    # must never be misread as a city).
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    city_slug = positional[0] if positional else "paris"
    if city_slug not in CITY_BBOX:
        sys.exit(
            f"Unknown city '{city_slug}'. Known: {', '.join(sorted(CITY_BBOX))}. "
            f"Add its bbox to CITY_BBOX in {Path(__file__).name}."
        )
    poi_file, beats_file = _city_paths(city_slug)
    bbox = CITY_BBOX[city_slug]

    db = get_database()
    db_label = f"cloud ({db})" if db else "local"
    provenance_only = "--provenance-only" in sys.argv
    mode = "PROVENANCE BACKFILL" if provenance_only else f"{city_slug.upper()} DATA UPLOAD"
    print(f"\n{'='*60}")
    print(f"  {mode} → Neo4j [{db_label}]")
    print(f"{'='*60}\n")

    # AC-9: every integrity gate (grounding, verification-freshness, uniqueness,
    # status vocab) must pass before we touch the database. Fail fast, pre-connect.
    print("  [0/5] Validating beats (validate_beats gate)...")
    _assert_beats_valid(beats_file)
    print("         OK")

    if provenance_only:
        # Step 4.0 backfill: ONLY the three provenance fields, matched by
        # beat_id. Never the full upload path (it plain-SETs audio_url='').
        beats = _load_json(beats_file)
        driver = create_driver()
        try:
            with driver.session(database=db) as session:
                print(f"  Backfilling provenance onto {len(beats)} source beats...")
                stats = _backfill_provenance(session, beats)
                kc = session.run(
                    "MATCH (b:NarrativeBeat) WHERE b.key_claims IS NOT NULL "
                    "RETURN count(b) AS c"
                ).single()["c"]
                total = session.run(
                    "MATCH (b:NarrativeBeat) RETURN count(b) AS c"
                ).single()["c"]
            print(
                f"  {stats['updated']} updated of {stats['candidates']} candidates; "
                f"{kc}/{total} beats in the graph now carry key_claims"
            )
        finally:
            driver.close()
        return

    pois = _load_json(poi_file)
    beats = _load_json(beats_file)
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
            poi_stats = _upload_pois(session, pois, city_slug, bbox)
            print(
                f"         {poi_stats['created']} created, {poi_stats['skipped']} skipped "
                f"(null coords), {poi_stats['out_of_bounds']} skipped (out of bounds) "
                f"({time.time()-t0:.1f}s)"
            )

            # 4. Beats + relationships
            print(f"  [4/5] Uploading {len(beats)} beats + linking...")
            t0 = time.time()
            beat_stats = _upload_beats(session, beats)
            print(
                f"         {beat_stats['linked']} linked, {beat_stats['orphaned']} orphaned, "
                f"{beat_stats['tagged']} tagged, {beat_stats['blocked']} blocked (disputed), "
                f"{beat_stats['no_beat_id']} skipped (no beat_id) "
                f"({time.time()-t0:.1f}s)"
            )

            # 5. Summary
            print("  [5/5] Verifying counts...")
            nodes = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
            rels = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
            poi_count = session.run("MATCH (n:POI) RETURN count(n) AS c").single()["c"]
            beat_count = session.run("MATCH (n:NarrativeBeat) RETURN count(n) AS c").single()["c"]
            lens_count = session.run("MATCH (n:Lens) RETURN count(n) AS c").single()["c"]

        print(f"\n{'='*60}")
        print("  UPLOAD COMPLETE")
        print(f"  Nodes: {nodes} ({poi_count} POIs, {beat_count} beats, {lens_count} lenses)")
        print(f"  Relationships: {rels}")
        print(f"{'='*60}\n")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
