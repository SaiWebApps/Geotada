#!/usr/bin/env python3
"""Phase 2 of /poi-gravity --rescore: compute composites, apply forced
distribution, write back to poi-raw.json, sync exports.

Inputs:
  - data/paris/poi-raw.json — 367 POIs, mix of (a) existing complete audits,
    (b) new POIs no tier, (c) tier-1 POIs with zero-composite audit blocks
  - data/paris/.gravity-research-signals.json — fresh signals from the
    background research agent for ~112 POIs (a JSON object: {name: signals})

Outputs:
  - data/paris/poi-raw.json (in place) with importance_tier + gravity_audit on every POI
  - data/paris/export/*.json with importance_tier synced
  - data/paris/.gravity-rescore-distribution.json — distribution audit
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path("/Users/adamserblowski/Geotada")
POI_RAW = ROOT / "data/paris/poi-raw.json"
SIGNALS = ROOT / "data/paris/.gravity-research-signals.json"
EXPORT_DIR = ROOT / "data/paris/export"
DISTRIBUTION_OUT = ROOT / "data/paris/.gravity-rescore-distribution.json"

# Forced distribution targets (per spec Phase 2 Step 2)
TIER_TARGETS = [
    (5, 0.12),  # top 12%
    (4, 0.17),  # next 17%
    (3, 0.28),  # next 28%
    (2, 0.22),  # next 22%
    (1, 0.21),  # bottom 21%
]

TRENDS_SCORE = {"dominant": 100, "high": 80, "moderate": 60, "low": 35, "minimal": 15}
WIKI_SCORE = {"extensive": 100, "moderate": 66, "stub": 33, "none": 0}
GUIDE_SCORE = {"UBIQUITOUS": 100, "COMMON": 75, "RARE": 35, "ABSENT": 10}


def _percentile(values: list[float | None], v: float | None) -> float | None:
    """Percentile rank (0-100) of v among non-None values. None values get None back."""
    if v is None:
        return None
    non_null = sorted([x for x in values if x is not None])
    if not non_null:
        return None
    # rank: count of values strictly less than v + half ties
    less = sum(1 for x in non_null if x < v)
    equal = sum(1 for x in non_null if x == v)
    rank = less + 0.5 * equal
    return 100.0 * rank / len(non_null)


def _composite(audit: dict, visitors_pop: list, reviews_pop: list) -> float:
    """Compute weighted composite score (0-100) from audit signals."""
    s_vis = _percentile(visitors_pop, audit.get("official_visitors"))
    s_rev = _percentile(reviews_pop, audit.get("google_review_count"))
    s_trends = TRENDS_SCORE.get(audit.get("google_trends"))
    s_wiki = WIKI_SCORE.get(audit.get("wikipedia_depth"))
    s_guide = GUIDE_SCORE.get(audit.get("guidebook_presence"))

    weighted_sum = 0.0
    weight_total = 0.0
    for value, weight in [(s_vis, 3), (s_rev, 3), (s_trends, 3), (s_wiki, 1), (s_guide, 1)]:
        if value is not None:
            weighted_sum += value * weight
            weight_total += weight

    if weight_total == 0:
        return 0.0
    return weighted_sum / weight_total


def _merge_audit(existing: dict, fresh: dict | None) -> dict:
    """Merge fresh research signals into the existing audit block. Fresh values
    replace existing where present; existing values are kept where fresh is None."""
    out = dict(existing or {})
    if not fresh:
        return out
    for k in ("official_visitors", "google_review_count", "google_trends",
              "wikipedia_depth", "guidebook_presence", "evidence"):
        v = fresh.get(k)
        if v is not None and v != "":
            out[k] = v
    return out


def main() -> int:
    poi_raw = json.loads(POI_RAW.read_text())
    signals = json.loads(SIGNALS.read_text()) if SIGNALS.exists() else {}
    print(f"loaded {len(poi_raw)} POIs and signals for {len(signals)} POIs")

    # Pass 1: merge fresh signals into each POI's gravity_audit
    by_name = {p["name"]: p for p in poi_raw}
    for name, fresh in signals.items():
        poi = by_name.get(name)
        if not poi:
            print(f"WARN: signals for unknown POI: {name!r}")
            continue
        pipeline = poi.setdefault("_pipeline", {})
        existing_audit = pipeline.get("gravity_audit") or {}
        merged = _merge_audit(existing_audit, fresh)
        pipeline["gravity_audit"] = merged

    # Pass 2: build populations of visitor counts and review counts (for
    # percentile ranking) — drawn from ALL POIs that have these signals
    visitors_pop = [
        ((p.get("_pipeline") or {}).get("gravity_audit") or {}).get("official_visitors")
        for p in poi_raw
    ]
    reviews_pop = [
        ((p.get("_pipeline") or {}).get("gravity_audit") or {}).get("google_review_count")
        for p in poi_raw
    ]
    print(f"visitors_pop: {sum(1 for x in visitors_pop if x is not None)} non-null")
    print(f"reviews_pop: {sum(1 for x in reviews_pop if x is not None)} non-null")

    # Pass 3: compute composite for every POI
    for poi in poi_raw:
        audit = (poi.get("_pipeline") or {}).get("gravity_audit") or {}
        comp = _composite(audit, visitors_pop, reviews_pop)
        audit["raw_composite"] = round(comp, 2)
        poi.setdefault("_pipeline", {})["gravity_audit"] = audit

    # Pass 4: sort + apply forced distribution
    sorted_pois = sorted(
        poi_raw,
        key=lambda p: (
            (p.get("_pipeline") or {}).get("gravity_audit", {}).get("raw_composite", 0),
            # tiebreaker: prior_assigned_gravity (residual signal)
            p.get("importance_tier") or 0,
        ),
        reverse=True,
    )
    n = len(sorted_pois)
    cumulative = 0
    tier_assignments = []
    for tier, pct in TIER_TARGETS:
        slice_size = int(round(n * pct))
        if tier == TIER_TARGETS[-1][0]:
            slice_size = n - cumulative  # last tier absorbs remainder
        tier_assignments.append((tier, cumulative, cumulative + slice_size))
        cumulative += slice_size

    distribution = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    transitions = {}
    now_iso = datetime.now(timezone.utc).isoformat()

    for tier, lo, hi in tier_assignments:
        for poi in sorted_pois[lo:hi]:
            old_tier = poi.get("importance_tier")
            audit = poi["_pipeline"]["gravity_audit"]
            audit["assigned_gravity"] = tier
            audit.setdefault("reasoning",
                             f"composite={audit['raw_composite']:.1f}, "
                             f"signals: visitors={audit.get('official_visitors')}, "
                             f"reviews={audit.get('google_review_count')}, "
                             f"trends={audit.get('google_trends')!r}, "
                             f"wiki={audit.get('wikipedia_depth')!r}, "
                             f"guidebook={audit.get('guidebook_presence')!r}")
            poi["importance_tier"] = tier
            distribution[tier] += 1
            if old_tier and old_tier != tier:
                key = f"T{old_tier}_to_T{tier}"
                transitions[key] = transitions.get(key, 0) + 1
            poi["_pipeline"]["gravity_audit"]["formula_version"] = (
                "poi_gravity_v2_smart_resume_2026_05_01_hidden_gardens_batch"
            )
            poi["_pipeline"]["gravity_audit"]["scored_at"] = now_iso

    # Pass 5: write poi-raw.json back (preserve original POI order)
    POI_RAW.write_text(json.dumps(poi_raw, indent=2, ensure_ascii=False))
    print(f"\nwrote {POI_RAW}")
    print(f"distribution: {distribution}")

    # Sanity check: anchor POIs should be tier 5
    ANCHORS = [
        "Notre-Dame Cathedral", "Eiffel Tower", "Louvre Museum",
        "Place des Vosges", "Sacre-Coeur Basilica", "Conciergerie",
        "Sainte-Chapelle", "Arc de Triomphe", "Pantheon",
    ]
    print("\nanchor check:")
    for name in ANCHORS:
        poi = by_name.get(name)
        if not poi:
            print(f"  {name}: NOT FOUND in poi-raw")
            continue
        print(f"  {name}: tier {poi.get('importance_tier')}")

    # Sync exports
    canonical = {p["name"].lower(): p for p in poi_raw}
    fields = ("importance_tier", "trigger_radius", "latitude", "longitude")
    fixes = 0
    files_changed = 0
    for export_file in sorted(EXPORT_DIR.glob("*.json")):
        data = json.loads(export_file.read_text())
        if not isinstance(data, list):
            continue
        changed = False
        for poi in data:
            c = canonical.get(poi.get("name", "").lower())
            if not c:
                continue
            for f in fields:
                cv = c.get(f)
                if cv is not None and poi.get(f) != cv:
                    poi[f] = cv
                    fixes += 1
                    changed = True
        if changed:
            export_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            files_changed += 1
    print(f"\nsynced {fixes} fields across {files_changed} export files")

    # Distribution audit log
    DISTRIBUTION_OUT.write_text(json.dumps({
        "rescore_at": now_iso,
        "formula_version": "poi_gravity_v2_smart_resume_2026_05_01_hidden_gardens_batch",
        "n_total": n,
        "distribution": distribution,
        "tier_targets": {t: f"{p:.0%}" for t, p in TIER_TARGETS},
        "transitions": transitions,
        "fresh_signals_applied": len(signals),
        "export_files_synced": files_changed,
        "export_field_fixes": fixes,
    }, indent=2))
    print(f"\ndistribution audit: {DISTRIBUTION_OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
