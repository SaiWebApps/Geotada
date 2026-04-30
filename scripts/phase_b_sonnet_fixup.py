#!/usr/bin/env python3
"""Phase B Sonnet output fixup pass.

Per the campaign brief (2026-04-25 handoff), Sonnet extraction at v2 quality is
acceptable for non-anchor (filler) waves *only* if a fixup pass recovers the
known regressions:
  - subject_tag often exceeds the ≤3-word constraint
  - beat_length_class self-classification is unreliable (~48% consistency)
  - JSON output sometimes has unescaped quotes inside source_passage
  - Tier-3+ beats sometimes ship with empty physical_cues despite the source
    passage citing visible features

This script:
  1. Reads agent transcript files (Claude Code JSONL) OR pre-extracted JSON
  2. Tolerantly parses the JSON (json -> demjson3 -> regex fallback)
  3. Applies automated fixups (subject_tag, beat_length_class, script_body_hash)
  4. Pydantic-validates each beat against `NarrativeBeatCreate`
  5. Routes:
     - Auto-fixable beats   -> <out>/fixed/<chunk>.json
     - Validation failures  -> <out>/review/<chunk>.json (NOT silently dropped)
     - Empty-cue suspects   -> <out>/review/<chunk>.json (do NOT auto-fix
                               — auto-filling cues would be invention)
  6. Produces a per-chunk + per-wave summary report

Usage:
    phase_b_sonnet_fixup.py
        --transcripts <path1> <path2> ...
        --or-json     <path1> <path2> ...
        --out         /tmp/ondoway-probe/wave1
        --poi-raw     data/paris/poi-raw.json

Centralized in the orchestrator (main conversation), not in agent prompts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path("/Users/adamserblowski/Ondoway")
sys.path.insert(0, str(PROJECT_ROOT))

# Pydantic validator
from src.api.models.nodes import NarrativeBeatCreate  # noqa: E402
from pydantic import ValidationError  # noqa: E402

try:
    import demjson3  # type: ignore
except ImportError:
    demjson3 = None


# ── Length-class ranges (per unified-beat-extract.md §B5) ──
LENGTH_RANGES = {
    "anchor":   (200, 400),
    "mid":       (80, 200),
    "seasoning": (20,  80),
    "micro":     ( 0,  20),
}


# ── Visible-feature keyword set for empty-cue review flagging ──
# Conservative set — high-confidence indicators that the source cites something
# the listener can see/touch at the POI. Used to flag tier-3+ beats where the
# extractor produced empty physical_cues despite the source clearly mentioning
# a visible feature.
VISIBLE_FEATURE_KEYWORDS = {
    "façade", "facade", "tower", "spire", "statue", "plaque", "stained glass",
    "rose window", "altar", "interior", "vault", "courtyard", "garden",
    "fountain", "bridge", "arch", "portal", "cell", "chapel", "cloister",
    "balcony", "window", "door", "wall", "roof", "ceiling", "column", "pillar",
    "carved", "monument", "pavement", "frieze", "sculpture", "tympanum",
    "buttress", "dome", "nave", "choir", "transept", "crypt", "gargoyle",
    "inscription", "memorial", "tomb", "courtyard", "stairs", "staircase",
    "cobblestone", "mosaic", "fresco", "mural", "obelisk",
}


def normalize_for_hash(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().strip())


def script_body_hash(body: str) -> str:
    return hashlib.sha256(normalize_for_hash(body).encode("utf-8")).hexdigest()


# ────────────────────────────────────────────────────────────
# JSON parsing (tolerant)
# ────────────────────────────────────────────────────────────


def _extract_code_fence(text: str) -> str | None:
    m = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"```\s*\n(\{.*?\})\s*\n```", text, re.DOTALL)
    if m:
        return m.group(1)
    return None


def parse_tolerantly(raw: str) -> tuple[Any | None, str]:
    """Parse JSON tolerantly. Return (parsed, parser_used) or (None, error)."""
    try:
        return json.loads(raw), "json"
    except json.JSONDecodeError as e1:
        if demjson3 is not None:
            try:
                return demjson3.decode(raw), "demjson3"
            except Exception as e2:
                pass
        # Last resort: try to clean obvious unescaped-quote patterns inside
        # source_passage strings. Common Sonnet failure: nested quotes in
        # historic guidebook text not properly escaped.
        try:
            cleaned = _heuristic_json_cleanup(raw)
            return json.loads(cleaned), "json+heuristic"
        except Exception:
            return None, f"all parsers failed: json={e1.msg} (line {e1.lineno})"


def _heuristic_json_cleanup(raw: str) -> str:
    # Replace smart quotes with straight quotes inside string values
    # (not perfect; only helps when smart quotes inside source_passage are
    # the issue)
    out = raw.replace("\u2018", "'").replace("\u2019", "'")
    out = out.replace("\u201c", '"').replace("\u201d", '"')
    return out


# ────────────────────────────────────────────────────────────
# Transcript reading
# ────────────────────────────────────────────────────────────


def read_transcript_last_assistant_text(path: Path) -> str | None:
    last = None
    with path.open() as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = ev.get("message") or ev.get("content") or {}
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content")
                if role == "assistant" and isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            last = c.get("text", "")
    return last


def load_chunk_payload(path: Path) -> tuple[dict | None, str]:
    """Return (payload_dict, parser_or_error)."""
    if path.suffix == ".output" or "/tasks/" in str(path):
        text = read_transcript_last_assistant_text(path)
        if not text:
            return None, "no assistant text in transcript"
        fence = _extract_code_fence(text)
        if not fence:
            return None, "no JSON code fence in last assistant message"
    else:
        # Treat as already-extracted JSON
        return json.loads(path.read_text()), "preparsed"
    parsed, status = parse_tolerantly(fence)
    return parsed, status


# ────────────────────────────────────────────────────────────
# Fixups
# ────────────────────────────────────────────────────────────


def fix_subject_tag(tag: str) -> tuple[str, list[str]]:
    """Coerce subject_tag to <=3 space-separated words, <=32 chars.

    Strategy: if it has >3 space-separated words, kebab-hyphenate the
    overflow (replace spaces with hyphens) so the result still has <=3
    space-separated tokens. If still over 32 chars, truncate at word boundary.
    Returns (fixed_tag, applied_changes).
    """
    notes: list[str] = []
    if not tag:
        return tag, notes
    raw = tag.strip()
    # Lowercase unless contains hyphenated proper-noun look (heuristic skip)
    if not any(c.isupper() for c in raw):
        pass  # already lowercase
    words = raw.split()
    if len(words) > 3:
        # Take first 3 word-tokens; kebab-join the rest into the third
        head = words[:2]
        tail = "-".join(words[2:])
        new_words = head + [tail]
        raw = " ".join(new_words)
        notes.append(f"kebab-hyphenated tail (was {len(words)} words)")
    if len(raw) > 32:
        # Truncate at word boundary
        truncated = raw[:32]
        if " " in truncated:
            truncated = truncated.rsplit(" ", 1)[0]
        notes.append(f"truncated to 32 chars (was {len(raw)})")
        raw = truncated
    if len(raw) > 32 or len(raw) < 1:
        # Last-resort hard truncate
        raw = raw[:32] or "untagged"
        notes.append("hard-truncated/defaulted")
    return raw, notes


def word_count(s: str) -> int:
    return len(s.split())


def fix_beat_length_class(beat: dict) -> tuple[str, list[str]]:
    notes: list[str] = []
    body = beat.get("script_body", "")
    declared = beat.get("beat_length_class", "")
    actual_words = word_count(body)
    correct = None
    for cls, (lo, hi) in LENGTH_RANGES.items():
        if lo <= actual_words < hi or (cls == "anchor" and actual_words >= lo and actual_words <= hi):
            # Strict: micro=[0,20), seasoning=[20,80), mid=[80,200), anchor=[200,400]
            if cls == "anchor" and actual_words > 400:
                continue
            if cls == "micro" and actual_words >= 20:
                continue
            correct = cls
            break
    if correct is None:
        # Word count above anchor-max (>400). Per B5 asymmetric rule, NOT
        # auto-truncating; flag for review instead. Also keep original class.
        notes.append(f"word_count={actual_words} > 400 (above anchor max); NOT re-classed")
        return declared, notes
    if declared != correct:
        notes.append(f"re-classed from {declared!r} to {correct!r} (word_count={actual_words})")
    return correct, notes


# ────────────────────────────────────────────────────────────
# Tier lookup + visible-feature heuristic
# ────────────────────────────────────────────────────────────


def load_poi_tiers(poi_raw_path: Path) -> dict[str, int | None]:
    pois = json.loads(poi_raw_path.read_text())
    out: dict[str, int | None] = {}
    for p in pois:
        out[p["name"].lower()] = p.get("importance_tier")
    return out


def cites_visible_feature(text: str) -> list[str]:
    text_low = text.lower()
    hits = []
    for kw in VISIBLE_FEATURE_KEYWORDS:
        if kw in text_low:
            hits.append(kw)
    return hits


# ────────────────────────────────────────────────────────────
# Per-chunk processing
# ────────────────────────────────────────────────────────────


def fix_one_chunk(payload: dict, poi_tiers: dict[str, int | None]) -> dict:
    """Apply fixups to a chunk's beats; return a result dict with categories."""
    chunk_id = payload.get("chunk_id", "?")
    raw_beats = payload.get("beats", [])
    fixed_beats: list[dict] = []
    review_items: list[dict] = []
    fixup_summary = {
        "subject_tag_fixed": 0,
        "beat_length_class_reclassed": 0,
        "script_body_hash_filled": 0,
        "validation_failed": 0,
        "empty_cue_review_flagged": 0,
        "anchor_overlength_flagged": 0,
    }

    for b in raw_beats:
        change_log: list[str] = []

        # Fix subject_tag
        old_tag = b.get("subject_tag", "")
        new_tag, st_notes = fix_subject_tag(old_tag)
        if new_tag != old_tag:
            b["subject_tag"] = new_tag
            fixup_summary["subject_tag_fixed"] += 1
            change_log.extend([f"subject_tag: {n}" for n in st_notes])

        # Fix beat_length_class
        new_cls, lc_notes = fix_beat_length_class(b)
        if new_cls != b.get("beat_length_class", ""):
            b["beat_length_class"] = new_cls
            fixup_summary["beat_length_class_reclassed"] += 1
        if any("> 400" in n for n in lc_notes):
            fixup_summary["anchor_overlength_flagged"] += 1
            review_items.append({
                "type": "ANCHOR_OVERLENGTH",
                "beat_id": b.get("beat_id"),
                "issue": lc_notes[0],
                "recommendation": "Source likely contains a multi-paragraph anchor essay. Consider splitting into two anchor beats at natural transition.",
            })
        change_log.extend([f"beat_length_class: {n}" for n in lc_notes])

        # Fill script_body_hash
        if not b.get("script_body_hash"):
            b["script_body_hash"] = script_body_hash(b.get("script_body", ""))
            fixup_summary["script_body_hash_filled"] += 1

        # Empty-cue review check (no auto-fix)
        physical_cues = b.get("physical_cues") or []
        poi_lower = (b.get("poi_name", "") or "").lower()
        tier = poi_tiers.get(poi_lower)
        # Tier-3+ rule. Treat unknown tier as tier-3+ (conservative: catch new POIs)
        is_tier_3_plus = tier is None or tier >= 3
        if is_tier_3_plus and not physical_cues:
            source_passage = b.get("source_passage", "") or ""
            visible_hits = cites_visible_feature(source_passage)
            if visible_hits:
                fixup_summary["empty_cue_review_flagged"] += 1
                review_items.append({
                    "type": "EMPTY_CUES_WITH_VISIBLE_FEATURE",
                    "beat_id": b.get("beat_id"),
                    "poi_name": b.get("poi_name"),
                    "tier": tier,
                    "visible_keywords_in_source": visible_hits[:5],
                    "source_passage_excerpt": source_passage[:200],
                    "recommendation": "Source mentions visible feature(s); cue array empty. Manual review — DO NOT auto-fill (would be invention).",
                })

        # Pydantic validation
        try:
            NarrativeBeatCreate(**{k: v for k, v in b.items() if k != "_meta"
                                   and k != "source_passage_verified"
                                   and k != "key_claims"
                                   and k != "source_attribution"})
            # Validation passed — keep change log on the beat for traceability
            if change_log:
                b.setdefault("_fixup_notes", []).extend(change_log)
            fixed_beats.append(b)
        except ValidationError as ve:
            fixup_summary["validation_failed"] += 1
            review_items.append({
                "type": "PYDANTIC_VALIDATION_FAIL",
                "beat_id": b.get("beat_id", "<missing>"),
                "errors": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e.get("type")} for e in ve.errors()],
                "fixup_attempted": change_log,
                "recommendation": "Manual fix or re-extract this single beat. Not silently dropped per campaign brief.",
            })

    # Pull existing agent-flagged review_queue items into ours
    for item in payload.get("review_queue", []) or []:
        if isinstance(item, dict):
            item_with_origin = dict(item)
            item_with_origin["from"] = "agent_review_queue"
            review_items.append(item_with_origin)

    return {
        "chunk_id": chunk_id,
        "model": payload.get("model", "unknown"),
        "pois_flagged_new": [p for p in (payload.get("pois") or []) if p.get("is_new")],
        "fixed_beats": fixed_beats,
        "review_items": review_items,
        "fixup_summary": fixup_summary,
        "agent_summary": payload.get("summary", {}),
    }


# ────────────────────────────────────────────────────────────
# Main
# ────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--transcripts", nargs="*", default=[])
    ap.add_argument("--or-json", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--poi-raw", default=str(PROJECT_ROOT / "data" / "paris" / "poi-raw.json"))
    args = ap.parse_args()

    out_dir = Path(args.out)
    (out_dir / "fixed").mkdir(parents=True, exist_ok=True)
    (out_dir / "review").mkdir(parents=True, exist_ok=True)

    poi_tiers = load_poi_tiers(Path(args.poi_raw))

    inputs = [Path(p) for p in args.transcripts] + [Path(p) for p in args.or_json]
    if not inputs:
        print("no inputs", file=sys.stderr)
        return 2

    wave_summary = {"chunks_ok": 0, "chunks_unparseable": 0, "total_beats_fixed": 0, "total_review_items": 0,
                    "by_chunk": []}
    for p in inputs:
        payload, parser = load_chunk_payload(p)
        if payload is None:
            wave_summary["chunks_unparseable"] += 1
            wave_summary["by_chunk"].append({"input": str(p), "status": "unparseable", "detail": parser})
            print(f"UNPARSEABLE {p}: {parser}", file=sys.stderr)
            continue

        result = fix_one_chunk(payload, poi_tiers)
        chunk_id = result["chunk_id"].replace("/", "_")
        fixed_path = out_dir / "fixed" / f"{chunk_id}.json"
        review_path = out_dir / "review" / f"{chunk_id}.json"
        fixed_path.write_text(json.dumps({
            "chunk_id": result["chunk_id"],
            "model": result["model"],
            "beats": result["fixed_beats"],
            "pois_flagged_new": result["pois_flagged_new"],
        }, indent=2, ensure_ascii=False))
        review_path.write_text(json.dumps({
            "chunk_id": result["chunk_id"],
            "review_items": result["review_items"],
            "fixup_summary": result["fixup_summary"],
            "agent_summary": result["agent_summary"],
        }, indent=2, ensure_ascii=False))

        wave_summary["chunks_ok"] += 1
        wave_summary["total_beats_fixed"] += len(result["fixed_beats"])
        wave_summary["total_review_items"] += len(result["review_items"])
        wave_summary["by_chunk"].append({
            "input": str(p),
            "status": "ok",
            "parser": parser,
            "chunk_id": result["chunk_id"],
            "beats_fixed": len(result["fixed_beats"]),
            "review_items": len(result["review_items"]),
            "new_pois_flagged": len(result["pois_flagged_new"]),
            "fixup_summary": result["fixup_summary"],
        })
        print(f"OK {result['chunk_id']}: {len(result['fixed_beats'])} beats fixed, "
              f"{len(result['review_items'])} review items, "
              f"{len(result['pois_flagged_new'])} new POIs flagged "
              f"(fixups: {result['fixup_summary']})")

    summary_path = out_dir / "wave_summary.json"
    summary_path.write_text(json.dumps(wave_summary, indent=2, ensure_ascii=False))
    print(f"\nwave summary: {wave_summary['chunks_ok']} ok, "
          f"{wave_summary['chunks_unparseable']} unparseable, "
          f"{wave_summary['total_beats_fixed']} beats, "
          f"{wave_summary['total_review_items']} review items")
    print(f"wrote {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
