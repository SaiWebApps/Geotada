"""Phase B for /pipeline-batch — collect agent results, sanitize, dedup, write.

Built for the v2 6-book batch (Pariswalks remaining + Rough Guide + Frommer's
+ Rick Steves + Hazan + AAP-13-20). Designed to be safe under Opus output
(stricter JSON than Sonnet) but resilient to either.

Per-wave usage:
    .venv/bin/python scripts/pipeline_phase_b.py \
        --wave 1 \
        --result-dir /tmp/wave_1_results \
        --commit-message "Wave 1 (Pariswalks 1-3,5-7 + Rough Guide 01-09)"

Each result file is the raw JSON-with-prose output from one agent. The script:
  1. Tolerantly parses (demjson3 fallback + regex unescape repair)
  2. Sanitizes each beat (subject_tag truncation, length-class re-class,
     inline_foreign_phrase consistency, façade-cue fallback for trigger_address)
  3. Validates each beat through Pydantic NarrativeBeatCreate
  4. Drops failed beats into a review queue rather than committing them
  5. Cross-chunk dedup by beat_id and (poi_name, lens, topic_slug)
  6. Appends to data/paris/beats.json + book-log.json + poi-raw.json
  7. Writes per-chunk export files
  8. Updates .pipeline-state.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import beats_io  # noqa: E402

CITY = "paris"
NOW_ISO = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash(body: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", body.lower().strip()).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------
# 1. TOLERANT JSON PARSING
# ----------------------------------------------------------------------

def _extract_json_fence(text: str) -> str:
    """Pull the JSON code fence out of agent prose-prefixed output."""
    m = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1)
    # No fence — try to find the outermost {...}
    m = re.search(r"\{[\s\S]+\}", text)
    return m.group(0) if m else text


def _try_parse(json_text: str) -> dict:
    """Parse JSON, falling back to tolerant repair on common Sonnet/Opus glitches."""
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        pass

    # Try demjson3
    try:
        import demjson3  # type: ignore
        return demjson3.decode(json_text)
    except Exception:
        pass

    # Last-ditch: regex repair of unescaped quotes inside ("...") patterns
    repaired = re.sub(r'\("([^"\n]+)"\)', r'(\\"\1\\")', json_text)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"could not parse agent JSON after repair attempts: {e}") from e


def parse_agent_result(path: Path) -> dict:
    """Read an agent-result JSON file and return the parsed payload.

    The file may be the raw tool-result envelope (a list with a 'text' field)
    or just the JSON payload directly.
    """
    raw = path.read_text(encoding="utf-8")

    # If it looks like a tool-result envelope, drill in
    try:
        envelope = json.loads(raw)
        if isinstance(envelope, list) and envelope and isinstance(envelope[0], dict) and "text" in envelope[0]:
            text = envelope[0]["text"]
            return _try_parse(_extract_json_fence(text))
    except json.JSONDecodeError:
        pass

    return _try_parse(_extract_json_fence(raw))


# ----------------------------------------------------------------------
# 2. SANITIZERS
# ----------------------------------------------------------------------

LENGTH_RANGES = {"anchor": (200, 400), "mid": (80, 200), "seasoning": (20, 80), "micro": (0, 20)}


def _reclass_by_wordcount(wc: int) -> str:
    if wc < 20:
        return "micro"
    if wc <= 80:
        return "seasoning"
    if wc <= 200:
        return "mid"
    return "anchor"


def _truncate_subject_tag(tag: str) -> str:
    """Bring subject_tag inside the 1–3 word, 1–32 char Pydantic constraint."""
    if not tag:
        return ""
    tag = tag.strip()
    words = tag.split()
    if len(words) <= 3 and 1 <= len(tag) <= 32:
        return tag
    if len(words) > 3:
        # If tag includes hyphens already, keep as one kebab word; else take first 3
        if "-" in tag.replace(" ", ""):
            return tag.replace(" ", "-")[:32]
        # Drop common French articles
        stop = {"de", "la", "le", "les", "du", "des", "l", "d", "of", "the", "and", "a"}
        kept = [w for w in words if w.lower() not in stop]
        if 1 <= len(kept) <= 3:
            tag = " ".join(kept)
        else:
            tag = " ".join(words[:3])
    if len(tag) > 32:
        tag = tag[:32].rsplit(" ", 1)[0] or tag[:32]
    return tag


def sanitize_beat(beat: dict, chunk_slug: str | None = None) -> dict:
    """Apply v2 conformance fix-ups in place. Returns the modified dict."""
    # Required fields with sane defaults
    body = (beat.get("script_body") or "").strip()
    beat["script_body"] = body
    beat["script_body_hash"] = _hash(body)
    wc = len(body.split())
    beat["beat_length_class"] = _reclass_by_wordcount(wc)
    beat["duration_sec"] = round(wc / 2.5)
    beat["subject_tag"] = _truncate_subject_tag(beat.get("subject_tag", "") or "")

    # inline_foreign_phrases consistency: drop entries whose phrase isn't in body
    raw_phrases = beat.get("inline_foreign_phrases") or []
    beat["inline_foreign_phrases"] = [
        p for p in raw_phrases if isinstance(p, dict) and p.get("phrase") and p["phrase"] in body
    ]

    # Façade-cue fallback for trigger_address with empty cues (Fix 2 enforcement)
    if beat.get("trigger_address") and not (beat.get("physical_cues") or []):
        beat["physical_cues"] = [
            {"cue": f"Façade of {beat['trigger_address']}", "direction": "here", "feature_type": "architectural_detail"}
        ]

    # Default sub_location/trigger_address/pronunciation to None if missing
    beat.setdefault("sub_location", None)
    beat.setdefault("trigger_address", None)
    beat.setdefault("pronunciation", None)

    # Provenance fields
    if chunk_slug:
        beat.setdefault("source_chunk_slug", chunk_slug)
    beat.setdefault("city_name", CITY)
    meta = beat.setdefault("_meta", {})
    meta.setdefault("prompt_version", "unified_v2")
    meta.setdefault("generated_at", NOW_ISO)
    meta.setdefault("city_name", CITY)

    return beat


# ----------------------------------------------------------------------
# 3. PYDANTIC VALIDATION
# ----------------------------------------------------------------------

def validate_through_pydantic(beats: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (valid_beats, rejected_with_error) tuple."""
    from src.api.models.nodes import NarrativeBeatCreate
    from pydantic import ValidationError

    valid: list[dict] = []
    rejected: list[dict] = []
    for b in beats:
        # Build the kwargs Pydantic expects (a subset of full beat dict)
        kw = {
            "script_body": b.get("script_body", ""),
            "duration_sec": b.get("duration_sec", 60),
            "kid_friendly": b.get("kid_friendly", "yes"),
            "entities": b.get("entities") or [],
            "sensory_anchor": b.get("sensory_anchor"),
            "narrative_function": b.get("narrative_function", "") or "",
            "beat_type": b.get("beat_type", "") or "",
            "emotional_register": b.get("emotional_register", "") or "",
            "subject_tag": b.get("subject_tag", "") or "",
            "physical_cues": b.get("physical_cues") or [],
            "script_body_hash": b.get("script_body_hash", "") or "",
            "book_slug": b.get("book_slug", "") or "",
            "topic_slug": b.get("topic_slug", "") or "",
            "city_name": b.get("city_name", "") or "",
            "source_chunk_slug": b.get("source_chunk_slug", "") or "",
            "sub_location": b.get("sub_location"),
            "trigger_address": b.get("trigger_address"),
            "beat_length_class": b.get("beat_length_class", "") or "",
            "inline_foreign_phrases": b.get("inline_foreign_phrases") or [],
            "pronunciation": b.get("pronunciation"),
        }
        try:
            NarrativeBeatCreate(**kw)
            valid.append(b)
        except ValidationError as e:
            rejected.append({"beat_id": b.get("beat_id", "?"), "error": str(e).splitlines()[0:3], "beat": b})
    return valid, rejected


# ----------------------------------------------------------------------
# 4. CROSS-CHUNK DEDUP
# ----------------------------------------------------------------------

def cross_chunk_dedup(beats: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return (deduped_beats, dedup_review_items)."""
    seen_ids: dict[str, dict] = {}
    seen_identity: dict[tuple, dict] = {}
    seen_hash: dict[str, dict] = {}
    deduped: list[dict] = []
    review: list[dict] = []

    for b in beats:
        bid = b.get("beat_id", "")
        identity = (
            b.get("city_name", ""),
            b.get("poi_name", ""),
            b.get("lens", ""),
            b.get("book_slug", ""),
            b.get("topic_slug", ""),
        )
        h = b.get("script_body_hash", "")
        # legacy_unknown wildcard for identity tuple
        if "legacy_unknown" in identity:
            identity = None

        if bid and bid in seen_ids:
            review.append({"type": "DEDUP_BEAT_ID", "winner": seen_ids[bid].get("beat_id"), "loser": bid})
            continue
        if h and h in seen_hash:
            review.append({"type": "DEDUP_HASH", "winner": seen_hash[h].get("beat_id"), "loser": bid})
            continue
        if identity and identity in seen_identity:
            review.append({"type": "DEDUP_IDENTITY", "tuple": list(identity), "winner": seen_identity[identity].get("beat_id"), "loser": bid})
            continue

        seen_ids[bid] = b
        seen_hash[h] = b
        if identity:
            seen_identity[identity] = b
        deduped.append(b)

    return deduped, review


# ----------------------------------------------------------------------
# 5. PER-CHUNK EXPORT FILES
# ----------------------------------------------------------------------

def write_export_file(chunk_payload: dict, beats: list[dict]) -> Path:
    """Write data/paris/export/{book_slug}-{chunk_slug}.json."""
    book_slug = chunk_payload.get("book_slug", "unknown_book")
    chunk_id = chunk_payload.get("chunk_id", "unknown_chunk")
    pois = chunk_payload.get("pois", []) or []

    poi_to_beats: dict[str, list[dict]] = defaultdict(list)
    for b in beats:
        poi_to_beats[b.get("poi_name", "")].append(b)

    poi_entries = []
    for p in pois:
        name = p.get("name", "")
        poi_entries.append({**p, "beats": poi_to_beats.get(name, [])})

    out_path = Path("data") / CITY / "export" / f"{book_slug}-{chunk_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"pois": poi_entries}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out_path


# ----------------------------------------------------------------------
# 6. POI APPEND
# ----------------------------------------------------------------------

def append_new_pois(payloads: list[dict]) -> list[dict]:
    """Append new POIs (is_new == true) to data/paris/poi-raw.json. Skip dupes by name."""
    poi_path = Path("data") / CITY / "poi-raw.json"
    existing = json.load(poi_path.open())
    existing_names = {p["name"].lower(): p for p in existing}

    appended: list[dict] = []
    for payload in payloads:
        for p in payload.get("pois", []) or []:
            if not p.get("is_new"):
                continue
            name = p.get("name", "").strip()
            if not name or name.lower() in existing_names:
                continue
            # Build the POI record per poi-raw.json convention. Tier intentionally
            # omitted — /poi-gravity scores it later.
            poi_record = {
                "name": name,
                "city_name": CITY,
                "short_description": p.get("short_description", "") or "",
                "latitude": p.get("latitude") or 0.0,
                "longitude": p.get("longitude") or 0.0,
                "trigger_radius": p.get("trigger_radius", 10),
                "kid_friendly": p.get("kid_friendly", "yes"),
                "name_variations": p.get("name_variations", []) or [],
                "_pipeline": {
                    "geocode_source": p.get("geocode_source", ""),
                    "geocode_confidence": p.get("geocode_confidence", ""),
                    "gravity_reasoning": p.get("gravity_reasoning", ""),
                    "added_at": NOW_ISO,
                },
                "_meta": {"prompt_version": "unified_v2", "generated_at": NOW_ISO, "city_name": CITY},
            }
            existing.append(poi_record)
            existing_names[name.lower()] = poi_record
            appended.append(poi_record)

    if appended:
        poi_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return appended


# ----------------------------------------------------------------------
# 7. MAIN
# ----------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wave", type=int, required=True)
    ap.add_argument("--result-dir", type=Path, required=True)
    ap.add_argument("--commit-message-prefix", default="")
    args = ap.parse_args()

    print(f"=== Phase B for Wave {args.wave} ===")

    if not args.result_dir.exists():
        print(f"result-dir does not exist: {args.result_dir}", file=sys.stderr)
        return 2

    # Parse all agent results
    payloads: list[dict] = []
    parse_errors: list[tuple[str, str]] = []
    for f in sorted(args.result_dir.glob("*.json")):
        try:
            payload = parse_agent_result(f)
            payloads.append(payload)
        except Exception as e:
            parse_errors.append((f.name, str(e)))

    print(f"  parsed: {len(payloads)} payloads; parse errors: {len(parse_errors)}")
    for name, err in parse_errors:
        print(f"    PARSE FAIL {name}: {err}")

    if not payloads:
        return 1

    # Collect + sanitize all beats
    all_beats: list[dict] = []
    chunk_slug_per_beat: dict[str, str] = {}
    for payload in payloads:
        chunk_slug = payload.get("chunk_id") or payload.get("chunk_slug") or ""
        for b in payload.get("beats", []) or []:
            sanitize_beat(b, chunk_slug=chunk_slug)
            all_beats.append(b)

    print(f"  sanitized beats: {len(all_beats)}")

    # Pydantic validation
    valid, rejected = validate_through_pydantic(all_beats)
    print(f"  pydantic valid: {len(valid)}; rejected: {len(rejected)}")

    # Cross-chunk dedup
    deduped, dedup_review = cross_chunk_dedup(valid)
    print(f"  after dedup: {len(deduped)}; dedup review items: {len(dedup_review)}")

    # Append new POIs
    new_pois = append_new_pois(payloads)
    print(f"  new POIs appended: {len(new_pois)}")

    # Build export files
    export_files: list[Path] = []
    for payload in payloads:
        chunk_id = payload.get("chunk_id") or ""
        chunk_beats = [b for b in deduped if b.get("source_chunk_slug") == chunk_id]
        out = write_export_file(payload, chunk_beats)
        export_files.append(out)
    print(f"  export files written: {len(export_files)}")

    # Append beats + book-log via beats_io.commit
    beats_path = Path("data") / CITY / "beats.json"
    log_path = Path("data") / CITY / "book-log.json"
    existing_beats = json.load(beats_path.open())
    log = json.load(log_path.open())

    # Build book-log entries — group by book_slug
    by_book: dict[str, list[dict]] = defaultdict(list)
    for payload in payloads:
        by_book[payload.get("book_slug", "unknown")].append(payload)

    for book_slug, payloads_for_book in by_book.items():
        # Find or create the book entry
        book_entry = None
        for be in log["books_processed"]:
            if (
                be.get("book_slug") == book_slug
                or (book_slug == "rough_guide_paris" and be.get("book_title") == "The Rough Guide to Paris")
                or (book_slug == "pariswalks" and be.get("book_title") == "Pariswalks")
                or (book_slug == "frommers_24_great_walks" and "Frommer" in (be.get("book_title") or ""))
                or (book_slug == "rick_steves_paris" and "Rick Steves" in (be.get("book_title") or ""))
                or (book_slug == "a_walk_through_paris" and "Walk Through Paris" in (be.get("book_title") or ""))
                or (book_slug == "around_and_about_paris_13_20" and "13 to 20" in (be.get("book_title") or ""))
            ):
                book_entry = be
                break
        if book_entry is None:
            book_entry = {
                "book_title": "PLACEHOLDER",  # caller can rename
                "book_slug": book_slug,
                "author": payloads_for_book[0].get("author", ""),
                "chunks_processed": [],
            }
            log.setdefault("books_processed", []).append(book_entry)
            book_entry["book_slug"] = book_slug

        for payload in payloads_for_book:
            chunk_id = payload.get("chunk_id") or ""
            chunk_beats = [b for b in deduped if b.get("source_chunk_slug") == chunk_id]
            pois_touched = sorted({b.get("poi_name", "") for b in chunk_beats if b.get("poi_name")})
            new_poi_names = [p["name"] for p in (payload.get("pois") or []) if p.get("is_new")]
            book_entry.setdefault("chunks_processed", []).append({
                "chunk": chunk_id,
                "processed_at": NOW_ISO,
                "beats_extracted": len(chunk_beats),
                "pois_touched": pois_touched,
                "new_pois_flagged": new_poi_names,
                "pois_mentioned_no_content": [],
            })

    # Atomic commit
    final_beats = existing_beats + deduped
    print(f"  committing {len(existing_beats)} + {len(deduped)} = {len(final_beats)} beats")
    beats_io.commit(final_beats, log, beats_path=beats_path, log_path=log_path)
    print(f"  ✓ committed")

    # Per-wave review queue file
    review_dir = Path(f"/tmp/wave_{args.wave}_review")
    review_dir.mkdir(exist_ok=True)
    if rejected:
        (review_dir / "pydantic_rejected.json").write_text(json.dumps(rejected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if dedup_review:
        (review_dir / "dedup_review.json").write_text(json.dumps(dedup_review, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if parse_errors:
        (review_dir / "parse_errors.json").write_text(json.dumps([{"file": n, "error": e} for n, e in parse_errors], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Summary
    print()
    print("--- WAVE B SUMMARY ---")
    print(f"  parsed payloads: {len(payloads)}")
    print(f"  sanitized beats: {len(all_beats)}")
    print(f"  pydantic valid: {len(valid)}")
    print(f"  pydantic rejected: {len(rejected)}")
    print(f"  cross-chunk dedup deduped: {len(deduped)}")
    print(f"  cross-chunk dedup review: {len(dedup_review)}")
    print(f"  new POIs appended: {len(new_pois)}")
    print(f"  export files: {len(export_files)}")
    print(f"  review dir: {review_dir}")

    # Distributions for the diagnostic
    cls = Counter(b.get("beat_length_class") for b in deduped)
    print(f"  length-class: {dict(cls)}")
    btypes = Counter(b.get("beat_type") for b in deduped)
    print(f"  beat_type: {dict(btypes)}")
    print(f"  trigger_address count: {sum(1 for b in deduped if b.get('trigger_address'))}")
    print(f"  sub_location count: {sum(1 for b in deduped if b.get('sub_location'))}")
    print(f"  inline_foreign_phrases entries: {sum(len(b.get('inline_foreign_phrases') or []) for b in deduped)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
