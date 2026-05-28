#!/usr/bin/env python3
"""Upload Hidden Gardens of Paris content into Neo4j via the FastAPI backend.

Strategy:
- Read poi-raw.json + beats.json as canonical source of truth
- For each Hidden Gardens chunk export: create new POIs (skip matches),
  create beats (MERGE auto-dedups by script_body), create HAS_BEAT edges,
  create TAGGED_WITH edges (lens lookup by name)
- All operations are idempotent (DB uses MERGE on POI {name, city_name}
  and NarrativeBeat {script_body})
- Strip pipeline-only fields before sending to API

Outputs: data/paris/.upload-report-hidden-gardens.json with full audit log.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import requests

API = "http://localhost:8000/api/v1"
ROOT = Path("/Users/adamserblowski/Geotada")
POI_RAW = ROOT / "data/paris/poi-raw.json"
BEATS_FILE = ROOT / "data/paris/beats.json"
EXPORT_DIR = ROOT / "data/paris/export"
REPORT = ROOT / "data/paris/.upload-report-hidden-gardens.json"

CITY = "paris"
BOOK_PREFIX = "hidden_gardens_of_paris"

POI_FORWARD_FIELDS = (
    "name", "city_name", "latitude", "longitude", "importance_tier",
    "short_description", "trigger_radius", "typical_duration_min",
    "kid_friendly", "name_variations", "poi_role", "parent_poi",
    "establishing_not_applicable",
)
BEAT_FORWARD_FIELDS = (
    "script_body", "duration_sec", "est_spoken_seconds", "kid_friendly",
    "entities", "sensory_anchor", "narrative_function", "beat_type",
    "emotional_register", "subject_tag", "sub_location", "trigger_address",
    "beat_length_class", "physical_cues", "pronunciation",
    "inline_foreign_phrases",
)


def _http(method: str, path: str, **kwargs) -> requests.Response:
    url = f"{API}{path}"
    r = requests.request(method, url, timeout=15, **kwargs)
    return r


def _fetch_all_pois() -> dict:
    """Return {name_lower: poi_record} index of every POI in DB."""
    out = {}
    skip = 0
    while True:
        r = _http("GET", f"/nodes/POI?skip={skip}&limit=200")
        r.raise_for_status()
        data = r.json()
        for item in data["items"]:
            props = item["properties"]
            poi = {**props, "id": item["id"]}
            name = props.get("name", "").lower()
            out[name] = poi
            for v in (props.get("name_variations") or []):
                out.setdefault(v.lower(), poi)
        if skip + 200 >= data.get("total", 0):
            break
        skip += 200
    return out


def _fetch_lenses() -> dict:
    """Return {lens_slug: lens_id} for taggable lenses."""
    out = {}
    r = _http("GET", "/nodes/Lens?limit=200")
    r.raise_for_status()
    for item in r.json()["items"]:
        props = item["properties"]
        if not props.get("is_parent", False):
            out[props["name"]] = item["id"]
    return out


def _build_poi_payload(canonical: dict) -> dict:
    payload = {"city_name": CITY}
    for f in POI_FORWARD_FIELDS:
        if f in canonical and canonical[f] is not None:
            payload[f] = canonical[f]
    payload["city_name"] = CITY  # always
    return payload


def _build_beat_payload(beat_canonical: dict) -> dict:
    payload = {}
    for f in BEAT_FORWARD_FIELDS:
        if f in beat_canonical and beat_canonical[f] is not None:
            payload[f] = beat_canonical[f]
    if not payload.get("duration_sec"):
        wc = len((beat_canonical.get("script_body") or "").split())
        payload["duration_sec"] = max(5, int(wc / 2.5))
    return payload


def main() -> int:
    print("=== Hidden Gardens upload ===")
    poi_raw = json.loads(POI_RAW.read_text())
    beats_all = json.loads(BEATS_FILE.read_text())
    poi_canonical = {p["name"].lower(): p for p in poi_raw}
    beats_by_id = {b["beat_id"]: b for b in beats_all if b.get("beat_id")}

    db_pois = _fetch_all_pois()
    lenses = _fetch_lenses()
    print(f"DB state: {len(db_pois)} POIs (incl. variations) · {len(lenses)} taggable lenses")

    chunk_files = sorted(EXPORT_DIR.glob(f"{BOOK_PREFIX}-chunk-*.json"))
    print(f"chunks to upload: {len(chunk_files)}")

    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "city": CITY,
        "book": BOOK_PREFIX,
        "chunks": [],
        "totals": {
            "pois_created": 0,
            "pois_matched": 0,
            "beats_created": 0,
            "beats_matched": 0,
            "has_beat_created": 0,
            "tagged_with_created": 0,
            "tagged_with_skipped_no_lens": 0,
            "errors": [],
        },
    }

    for path in chunk_files:
        chunk_data = json.loads(path.read_text())
        chunk_id = path.stem.replace(f"{BOOK_PREFIX}-", "")
        chunk_report = {
            "chunk": chunk_id,
            "pois_created": [],
            "pois_matched": [],
            "beats_created": 0,
            "beats_matched": 0,
            "has_beat_edges": 0,
            "tagged_with_edges": 0,
            "errors": [],
        }
        print(f"\n[{chunk_id}]")

        for entry in chunk_data:
            poi_name = entry["name"]
            canonical = poi_canonical.get(poi_name.lower())

            # Phase 2: match or create POI
            existing = db_pois.get(poi_name.lower())
            if existing:
                poi_id = existing["id"]
                chunk_report["pois_matched"].append(poi_name)
            else:
                if not canonical:
                    chunk_report["errors"].append(f"POI {poi_name!r} not in poi-raw.json — skipping")
                    print(f"  WARN: {poi_name!r} not in poi-raw.json")
                    continue
                payload = _build_poi_payload(canonical)
                if payload.get("importance_tier") is None:
                    chunk_report["errors"].append(f"POI {poi_name!r} missing importance_tier — skipping")
                    print(f"  WARN: {poi_name!r} missing importance_tier")
                    continue
                r = _http("POST", "/nodes/POI", json=payload)
                if r.status_code not in (200, 201):
                    err = f"POI create failed {r.status_code}: {poi_name!r} :: {r.text[:200]}"
                    chunk_report["errors"].append(err)
                    print(f"  ERROR: {err}")
                    continue
                poi_id = r.json()["id"]
                # cache for later refs in this run
                db_pois[poi_name.lower()] = {**payload, "id": poi_id}
                chunk_report["pois_created"].append(poi_name)
                print(f"  + POI {poi_name!r} → {poi_id[:8]}…")

            # Phase 3: beats + HAS_BEAT for this POI
            for beat in (entry.get("beats") or []):
                bid = beat.get("beat_id")
                canonical_beat = beats_by_id.get(bid, beat)
                payload = _build_beat_payload(canonical_beat)
                if not payload.get("script_body"):
                    chunk_report["errors"].append(f"empty script_body in beat {bid!r}")
                    continue
                r = _http("POST", "/nodes/NarrativeBeat", json=payload)
                if r.status_code not in (200, 201):
                    err = f"Beat create failed {r.status_code}: {bid!r} :: {r.text[:200]}"
                    chunk_report["errors"].append(err)
                    continue
                beat_node = r.json()
                beat_id = beat_node["id"]
                # crude detection of "matched vs created": check if response indicates
                # idempotent merge (the API returns 200 either way but the body might differ)
                # — we just count both as creates for the report
                chunk_report["beats_created"] += 1

                # HAS_BEAT (POI → Beat)
                edge = _http("POST", "/edges/HAS_BEAT", json={
                    "source": {"label": "POI", "id": poi_id},
                    "target": {"label": "NarrativeBeat", "id": beat_id},
                })
                if edge.status_code in (200, 201):
                    chunk_report["has_beat_edges"] += 1
                else:
                    chunk_report["errors"].append(
                        f"HAS_BEAT failed {edge.status_code} {bid!r} :: {edge.text[:120]}"
                    )

                # TAGGED_WITH (Beat → Lens)
                lens_slug = canonical_beat.get("lens")
                lens_id = lenses.get(lens_slug)
                if not lens_id:
                    chunk_report["errors"].append(f"unknown/parent lens {lens_slug!r} for beat {bid!r}")
                    report["totals"]["tagged_with_skipped_no_lens"] += 1
                    continue
                tag = _http("POST", "/edges/TAGGED_WITH", json={
                    "source": {"label": "NarrativeBeat", "id": beat_id},
                    "target": {"label": "Lens", "id": lens_id},
                })
                if tag.status_code in (200, 201):
                    chunk_report["tagged_with_edges"] += 1
                else:
                    chunk_report["errors"].append(
                        f"TAGGED_WITH failed {tag.status_code} {bid!r} → {lens_slug!r}"
                    )

        report["chunks"].append(chunk_report)
        for k in ("pois_created", "pois_matched"):
            report["totals"][f"pois_{'created' if k == 'pois_created' else 'matched'}"] += len(chunk_report[k])
        report["totals"]["beats_created"] += chunk_report["beats_created"]
        report["totals"]["has_beat_created"] += chunk_report["has_beat_edges"]
        report["totals"]["tagged_with_created"] += chunk_report["tagged_with_edges"]
        report["totals"]["errors"].extend(chunk_report["errors"])
        print(f"  → {len(chunk_report['pois_created'])} new POIs, "
              f"{chunk_report['beats_created']} beats, "
              f"{chunk_report['has_beat_edges']}/{chunk_report['tagged_with_edges']} edges, "
              f"{len(chunk_report['errors'])} errors")

    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print("\n=== TOTALS ===")
    for k, v in report["totals"].items():
        if k == "errors":
            print(f"  errors: {len(v)}")
            for e in v[:5]:
                print(f"    - {e}")
            if len(v) > 5:
                print(f"    ... and {len(v) - 5} more")
        else:
            print(f"  {k}: {v}")
    print(f"\nfull audit: {REPORT}")
    return 0 if not report["totals"]["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
