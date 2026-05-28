#!/usr/bin/env python3
"""Phase B aggregator for the hidden-gardens-of-paris batch.

Reads data/paris/.batch-results/*.json (the per-chunk agent outputs), applies
the Phase B fixup pass (subject_tag truncation, beat_length_class re-classing,
schema cleanup, beat_id collision check), and writes:

  - data/paris/export/hidden-gardens-of-paris-<chunk_id>.json (one per chunk)
  - appended POIs to data/paris/poi-raw.json (no importance_tier — gravity-pass
    assigns those)
  - appended beats to data/paris/beats.json
  - per-chunk entries in data/paris/book-log.json

Idempotent: skips POIs whose name already exists in poi-raw.json (case-
insensitive), skips beats whose beat_id already exists in beats.json.
"""
from __future__ import annotations
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Users/adamserblowski/Geotada")
BATCH = ROOT / "data/paris/.batch-results"
EXPORT = ROOT / "data/paris/export"
POI_RAW = ROOT / "data/paris/poi-raw.json"
BEATS = ROOT / "data/paris/beats.json"
BOOK_LOG = ROOT / "data/paris/book-log.json"

VALID_BEAT_TYPES = {
    "anecdote", "character_story", "event", "architectural_detail",
    "sensory_observation", "factoid", "establishing", "stop_orientation",
    "transit", "sidebar",
}
VALID_LENGTH_CLASSES = {"anchor", "mid", "seasoning", "micro"}
LENGTH_RANGES = {  # (min_words, max_words) — asymmetric per spec
    "micro": (0, 19),
    "seasoning": (20, 79),
    "mid": (80, 199),
    "anchor": (200, 400),
}
BOOK_SLUG = "hidden_gardens_of_paris"
BOOK_TITLE = "Hidden Gardens of Paris"
BOOK_AUTHOR = "Susan Cahill"


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _classify_length(word_count: int) -> str:
    if word_count < 20:
        return "micro"
    if word_count < 80:
        return "seasoning"
    if word_count < 200:
        return "mid"
    return "anchor"


def _truncate_subject_tag(tag: str) -> str:
    """Subject_tag must be ≤3 space-separated words. Kebab-hyphenated French
    proper nouns count as one word."""
    if not tag:
        return tag
    words = tag.split()
    if len(words) <= 3:
        return tag
    return " ".join(words[:3])


def _normalize_beat(beat: dict, fixup: dict) -> dict:
    """Apply Phase B fixups in-place. Returns the same beat for chaining."""
    # subject_tag truncation
    orig_tag = beat.get("subject_tag", "")
    fixed_tag = _truncate_subject_tag(orig_tag)
    if fixed_tag != orig_tag:
        beat["subject_tag"] = fixed_tag
        fixup.setdefault("subject_tag_fixed", 0)
        fixup["subject_tag_fixed"] += 1

    # beat_length_class re-class from script_body word count
    body = beat.get("script_body", "")
    wc = _word_count(body)
    actual_class = _classify_length(wc)
    declared = beat.get("beat_length_class")
    if declared not in VALID_LENGTH_CLASSES or declared != actual_class:
        beat["beat_length_class"] = actual_class
        fixup.setdefault("beat_length_class_reclassed", 0)
        fixup["beat_length_class_reclassed"] += 1
    beat["_word_count"] = wc

    # beat_type validation — fall back to 'factoid' if invalid (rare)
    bt = beat.get("beat_type")
    if bt not in VALID_BEAT_TYPES:
        # Common Sonnet hallucinations: lens slugs as beat_type, etc.
        # Map known patterns or default to anecdote
        if bt in {"anecdote", "character_story"}:
            pass  # already handled
        else:
            beat["beat_type"] = "factoid"
            beat.setdefault("_meta", {})["beat_type_fixup_from"] = bt
            fixup.setdefault("beat_type_corrected", 0)
            fixup["beat_type_corrected"] += 1

    # Tier-3+ empty physical_cues with non-null trigger_address → review queue
    # (we don't have tier yet, so just flag empty cues + trigger_address)
    if beat.get("trigger_address") and not (beat.get("physical_cues") or []):
        beat.setdefault("_review_flags", []).append("trigger_address_without_physical_cues")
        fixup.setdefault("trigger_address_no_cues_flagged", 0)
        fixup["trigger_address_no_cues_flagged"] += 1

    # _meta.prompt_version
    beat.setdefault("_meta", {})
    beat["_meta"].setdefault("prompt_version", "unified_v2")
    beat["_meta"].setdefault("city_name", "paris")

    return beat


def _normalize_poi(poi: dict) -> dict:
    """Coerce POI shape across the various agent schemas. Result is the canonical
    shape used by poi-raw.json (no importance_tier)."""
    name = poi.get("name") or poi.get("poi_name")
    if not name:
        return None  # skip
    is_new = bool(poi.get("is_new") or poi.get("new_poi"))
    matched = poi.get("matched_existing")
    match_status = poi.get("match_status") or poi.get("match_type")
    if match_status in ("existing", "matched") or matched not in (None, ""):
        is_new = False
    if match_status in ("new", "new_poi"):
        is_new = True

    return {
        "name": name,
        "is_new": is_new,
        "matched_existing": matched,
        "short_description": poi.get("short_description"),
        "name_variations": poi.get("name_variations") or [],
        "kid_friendly": poi.get("kid_friendly", "yes"),
        "latitude": poi.get("latitude"),
        "longitude": poi.get("longitude"),
        "trigger_radius": poi.get("trigger_radius") or 10,
        "geocode_source": poi.get("geocode_source"),
        "geocode_confidence": poi.get("geocode_confidence"),
        "gravity_reasoning": poi.get("gravity_reasoning") or poi.get("notes") or poi.get("pipeline_note"),
    }


def main() -> int:
    EXPORT.mkdir(parents=True, exist_ok=True)
    poi_raw = json.loads(POI_RAW.read_text())
    beats_data = json.loads(BEATS.read_text())
    book_log = json.loads(BOOK_LOG.read_text()) if BOOK_LOG.exists() else []

    existing_poi_names = {p["name"].casefold() for p in poi_raw}
    existing_beat_ids = {b.get("beat_id") for b in beats_data if b.get("beat_id")}

    fixup_total: dict = defaultdict(int)
    new_pois_added: list[dict] = []
    new_beats_added: list[dict] = []
    book_log_entries: list[dict] = []

    chunk_files = sorted(BATCH.glob("chunk-*.json"))
    for path in chunk_files:
        obj = json.loads(path.read_text())
        chunk_id = obj.get("chunk_id") or path.stem
        pois = obj.get("pois") or []
        beats = obj.get("beats") or []
        rq = obj.get("review_queue") or []

        # Phase B fixup
        chunk_fixup = defaultdict(int)
        for b in beats:
            _normalize_beat(b, chunk_fixup)
        for k, v in chunk_fixup.items():
            fixup_total[k] += v

        # Build per-chunk export shape: POIs with nested beats
        normalized_pois = [_normalize_poi(p) for p in pois]
        normalized_pois = [p for p in normalized_pois if p]

        beats_by_poi = defaultdict(list)
        for b in beats:
            beats_by_poi[b.get("poi_name", "UNKNOWN")].append(b)

        export_entries = []
        for p in normalized_pois:
            export_entries.append({
                "poi": p,
                "beats": beats_by_poi.get(p["name"], []),
            })
        # Beats whose poi_name doesn't match any POI in this chunk's pois list
        # (sometimes a beat references a POI that's in a different chunk)
        unmatched_beats = []
        poi_names_in_chunk = {p["name"] for p in normalized_pois}
        for poi_name, blist in beats_by_poi.items():
            if poi_name not in poi_names_in_chunk:
                unmatched_beats.extend(blist)

        export_payload = {
            "chunk_id": chunk_id,
            "book_slug": BOOK_SLUG,
            "book_title": BOOK_TITLE,
            "author": BOOK_AUTHOR,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "pois": export_entries,
            "orphan_beats": unmatched_beats,  # beats whose poi_name appears in another chunk
            "review_queue": rq,
            "phase_b_fixup": dict(chunk_fixup),
        }
        export_path = EXPORT / f"{BOOK_SLUG}-{chunk_id}.json"
        export_path.write_text(json.dumps(export_payload, indent=2, ensure_ascii=False))

        # Append new POIs to poi-raw.json
        chunk_new_pois = 0
        for p in normalized_pois:
            if not p["is_new"]:
                continue
            if p["name"].casefold() in existing_poi_names:
                continue
            poi_record = {
                "name": p["name"],
                "name_variations": p["name_variations"],
                "short_description": p["short_description"],
                "kid_friendly": p["kid_friendly"],
                "latitude": p["latitude"],
                "longitude": p["longitude"],
                "trigger_radius": p["trigger_radius"],
                "_pipeline": {
                    "source_chunk": chunk_id,
                    "source_book": BOOK_SLUG,
                    "geocode_source": p["geocode_source"],
                    "geocode_confidence": p["geocode_confidence"],
                    "gravity_reasoning": p["gravity_reasoning"],
                    "added_at": datetime.now(timezone.utc).isoformat(),
                },
                "_meta": {
                    "prompt_version": "unified_v2",
                    "city_name": "paris",
                },
            }
            poi_raw.append(poi_record)
            existing_poi_names.add(p["name"].casefold())
            new_pois_added.append(poi_record)
            chunk_new_pois += 1

        # Append new beats to beats.json (skip dupes)
        chunk_new_beats = 0
        for b in beats:
            bid = b.get("beat_id")
            if not bid or bid in existing_beat_ids:
                continue
            beats_data.append(b)
            existing_beat_ids.add(bid)
            new_beats_added.append(b)
            chunk_new_beats += 1

        # book-log entry
        book_log_entries.append({
            "book_slug": BOOK_SLUG,
            "chunk_id": chunk_id,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "beats_extracted": len(beats),
            "beats_committed": chunk_new_beats,
            "pois_touched": len(normalized_pois),
            "pois_created": chunk_new_pois,
            "review_queue_items": len(rq),
            "phase_b_fixup": dict(chunk_fixup),
            "model": "sonnet",
        })

    # Persist
    POI_RAW.write_text(json.dumps(poi_raw, indent=2, ensure_ascii=False))
    BEATS.write_text(json.dumps(beats_data, indent=2, ensure_ascii=False))

    # book-log.json shape: {city, books_processed: [{book_title, author, chunks_processed: [...]}]}
    if not isinstance(book_log, dict):
        book_log = {"city": "Paris", "books_processed": []}
    book_log.setdefault("books_processed", [])
    target = next(
        (b for b in book_log["books_processed"] if b.get("book_title") == BOOK_TITLE),
        None,
    )
    if target is None:
        target = {
            "book_title": BOOK_TITLE,
            "author": BOOK_AUTHOR,
            "book_slug": BOOK_SLUG,
            "chunks_processed": [],
        }
        book_log["books_processed"].append(target)
    target.setdefault("chunks_processed", [])
    existing_chunks = {c.get("chunk") for c in target["chunks_processed"]}
    for entry in book_log_entries:
        # canonicalize entry to match the existing schema
        if entry["chunk_id"] in existing_chunks:
            continue
        target["chunks_processed"].append({
            "chunk": entry["chunk_id"],
            "processed_at": entry["processed_at"],
            "beats_extracted": entry["beats_extracted"],
            "beats_committed": entry["beats_committed"],
            "pois_touched": entry["pois_touched"],
            "pois_created": entry["pois_created"],
            "review_queue_items": entry["review_queue_items"],
            "phase_b_fixup": entry["phase_b_fixup"],
            "model": entry["model"],
        })
        existing_chunks.add(entry["chunk_id"])
    BOOK_LOG.write_text(json.dumps(book_log, indent=2, ensure_ascii=False))

    print(f"=== Phase B complete ===")
    print(f"chunks processed: {len(chunk_files)}")
    print(f"new POIs added: {len(new_pois_added)}")
    print(f"new beats added: {len(new_beats_added)}")
    print(f"phase_b_fixup totals: {dict(fixup_total)}")
    print(f"export files written: {len(chunk_files)} -> {EXPORT}/")
    print(f"poi-raw.json: {len(poi_raw)} POIs (was {len(poi_raw) - len(new_pois_added)})")
    print(f"beats.json: {len(beats_data)} beats (was {len(beats_data) - len(new_beats_added)})")
    print(f"book-log.json: +{len(book_log_entries)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
