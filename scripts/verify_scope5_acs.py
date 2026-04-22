"""Verify AC-2, AC-6, AC-9 for the Scope 5 single-chunk validation gate.

AC-2: Single-chunk validation run satisfies —
  (a) zero within-run beat_id collisions
  (b) 100% of beats match existing POI or emit new_poi: true
  (c) sub-POI geocode round-trip: within 10m, differs from parent by ≥15m,
      confidence ≥70%                          (RUN post-poi-geocode only)
  (d) zero preservation-boundary fields modified on existing POIs
  (e) every new sub-POI has non-empty source_passage

AC-6: Every poi_role: stop POI has ≥1 establishing beat OR
      establishing_not_applicable=true AND importance_tier ≤ 2.

AC-9: Every new sub-POI carries parent_poi + valid poi_role + source_passage.

Usage:
    .venv/bin/python scripts/verify_scope5_acs.py \\
        --beats data/paris/beats.json \\
        --pois-pre data/paris/_snapshots/poi-raw.pre.json \\
        --pois-post data/paris/poi-raw.json \\
        --city paris

--pois-pre is the snapshot taken BEFORE the extraction run. Required for AC-2d.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a script without PYTHONPATH hacks
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PRESERVED_FIELDS = [
    "importance_tier",
    "latitude",
    "longitude",
    "name_variations",
]  # fields that must not be modified on pre-existing POIs per AC-2d / AC-3


def check_ac2a(beats: list[dict]) -> tuple[bool, list[str]]:
    """Zero within-run beat_id collisions."""
    seen: dict[str, int] = {}
    errors = []
    for i, b in enumerate(beats):
        bid = b.get("beat_id")
        if not bid:
            errors.append(f"beat[{i}]: missing beat_id")
            continue
        if bid in seen:
            errors.append(f"collision: {bid} at indices {seen[bid]} and {i}")
        else:
            seen[bid] = i
    return (not errors, errors)


def check_ac2b(beats: list[dict], pois: list[dict]) -> tuple[bool, list[str]]:
    """100% of beats match existing POI or flag new_poi: true."""
    poi_names = {p["name"] for p in pois}
    orphans = []
    for b in beats:
        poi_name = b.get("poi_name")
        if poi_name in poi_names:
            continue
        if b.get("new_poi") is True:
            continue
        orphans.append(f"{b.get('beat_id','?')}: poi_name='{poi_name}' not in POI list and not flagged new_poi")
    return (not orphans, orphans)


def check_ac2d(
    pois_pre: list[dict], pois_post: list[dict]
) -> tuple[bool, list[str]]:
    """Pre-existing POIs preserve their immutable fields."""
    pre_by_name = {p["name"]: p for p in pois_pre}
    post_by_name = {p["name"]: p for p in pois_post}

    errors = []
    for name, p_pre in pre_by_name.items():
        p_post = post_by_name.get(name)
        if p_post is None:
            errors.append(f"{name}: pre-existing POI dropped post-run")
            continue
        for f in PRESERVED_FIELDS:
            if p_pre.get(f) != p_post.get(f):
                errors.append(
                    f"{name}: preservation field '{f}' changed from "
                    f"{p_pre.get(f)!r} to {p_post.get(f)!r}"
                )
    return (not errors, errors)


def check_ac2e_ac9(pois_post: list[dict]) -> tuple[bool, list[str]]:
    """Every new sub-POI (parent_poi set) has non-empty source_passage and
    a valid poi_role. Uses Pydantic validation."""
    from src.api.models.nodes import POICreate

    errors = []
    sub_pois = [p for p in pois_post if p.get("parent_poi")]
    for p in sub_pois:
        try:
            POICreate(**{k: v for k, v in p.items() if k in POICreate.model_fields})
        except Exception as e:
            errors.append(f"{p.get('name','?')}: Pydantic validation failed — {e}")
        # Double-check source_passage explicitly
        if not (p.get("source_passage") or "").strip():
            errors.append(f"{p.get('name','?')}: source_passage empty or missing")
        if p.get("poi_role") not in ("stop", "setting", "walk_by_only"):
            errors.append(f"{p.get('name','?')}: poi_role '{p.get('poi_role')}' invalid")
    return (not errors, errors, len(sub_pois))


def check_ac6(
    beats: list[dict], pois: list[dict]
) -> tuple[bool, list[str]]:
    """Every poi_role: stop POI has ≥1 establishing beat OR
    establishing_not_applicable=true AND importance_tier ≤ 2.

    Data-file proxy for the Cypher check in the spec (which runs post-upload).
    """
    beats_by_poi: dict[str, list[dict]] = {}
    for b in beats:
        beats_by_poi.setdefault(b["poi_name"], []).append(b)

    errors = []
    for p in pois:
        if p.get("poi_role") != "stop":
            continue
        name = p["name"]
        tier = p.get("importance_tier", 0)
        poi_beats = beats_by_poi.get(name, [])
        has_establishing = any(
            b.get("narrative_function") == "establishing" for b in poi_beats
        )
        ena = p.get("establishing_not_applicable") is True
        if has_establishing:
            continue
        if ena and tier <= 2:
            continue
        if ena and tier >= 3:
            errors.append(
                f"{name}: tier {tier} stop has establishing_not_applicable=true — "
                f"forbidden for tier ≥ 3 (AC-6 auto-flag restricted to tier ≤ 2)"
            )
            continue
        errors.append(
            f"{name}: tier {tier} stop has no establishing beat and is not "
            f"establishing_not_applicable (AC-6 violation)"
        )
    return (not errors, errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--beats", required=True)
    parser.add_argument("--pois-post", required=True, help="POI file after the run")
    parser.add_argument(
        "--pois-pre",
        required=False,
        help="POI file snapshot taken before the run (for AC-2d)",
    )
    parser.add_argument("--city", required=True, help="city slug, e.g. paris")
    args = parser.parse_args()

    beats = json.loads(Path(args.beats).read_text())
    pois_post = json.loads(Path(args.pois_post).read_text())

    all_pass = True

    print(f"=== AC-2a: within-run beat_id uniqueness ({len(beats)} beats) ===")
    ok, errors = check_ac2a(beats)
    if ok:
        print("  PASS")
    else:
        all_pass = False
        print("  FAIL")
        for e in errors[:10]:
            print(f"    {e}")

    print(f"\n=== AC-2b: orphan check (all beats match POI or flag new_poi) ===")
    ok, errors = check_ac2b(beats, pois_post)
    if ok:
        print("  PASS")
    else:
        all_pass = False
        print("  FAIL")
        for e in errors[:10]:
            print(f"    {e}")

    if args.pois_pre:
        print(f"\n=== AC-2d: preservation boundaries on pre-existing POIs ===")
        pois_pre = json.loads(Path(args.pois_pre).read_text())
        ok, errors = check_ac2d(pois_pre, pois_post)
        if ok:
            print(f"  PASS ({len(pois_pre)} pre-existing POIs preserved)")
        else:
            all_pass = False
            print("  FAIL")
            for e in errors[:10]:
                print(f"    {e}")
    else:
        print("\n[INFO] --pois-pre not supplied; AC-2d skipped.")

    print(f"\n=== AC-2e + AC-9: sub-POI source_passage + Pydantic ===")
    ok, errors, count = check_ac2e_ac9(pois_post)
    if count == 0:
        print("  (no sub-POIs emitted in this run)")
    elif ok:
        print(f"  PASS ({count} sub-POIs all valid)")
    else:
        all_pass = False
        print(f"  FAIL ({count} sub-POIs, {len(errors)} invalid)")
        for e in errors[:10]:
            print(f"    {e}")

    print(f"\n=== AC-6: establishing-beat coverage on poi_role: stop POIs ===")
    ok, errors = check_ac6(beats, pois_post)
    if ok:
        print("  PASS")
    else:
        all_pass = False
        print(f"  FAIL ({len(errors)} violators)")
        for e in errors[:15]:
            print(f"    {e}")

    print("\n[INFO] AC-2c (sub-POI geocode round-trip) requires /poi-geocode")
    print("       invocation + a separate check script; run after geocoding.")

    print("\n" + ("ALL DATA-LEVEL CHECKS PASSED" if all_pass else "FAILURES FOUND"))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
