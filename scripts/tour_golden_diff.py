"""Diagnostic CLI: side-by-side overlap report against a golden fixture.

Runs the full selection → beat_select pipeline against the live Paris
Neo4j and prints a per-POI diff against fixtures/tour_golden/<fixture>.json.

NOT a test dependency — useful when iterating on calibration knobs to see
exactly which beats land where.

Usage:
    python scripts/tour_golden_diff.py pdv_round_trip_60min
    python scripts/tour_golden_diff.py ile_oneway_90min
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.connection import create_driver
from src.tour.beat_select import select_poi_beats
from src.tour.contract import TourInput
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route


FIXTURE_DIR = ROOT / "fixtures" / "tour_golden"


def main(name: str) -> int:
    fixture_path = FIXTURE_DIR / f"{name}.json"
    if not fixture_path.exists():
        candidates = sorted(p.stem for p in FIXTURE_DIR.glob("*.json"))
        print(f"Fixture not found: {fixture_path}")
        print(f"Available: {candidates}")
        return 2

    fixture = json.loads(fixture_path.read_text())
    inp = fixture["input"]
    expected = set(fixture["expected_beat_ids"])

    driver = create_driver()
    snapshot = load_paris_corpus(driver, city_slug=inp["city_slug"])

    tour_input = TourInput(
        start=tuple(inp["start"]),
        duration_min=inp["duration_min"],
        city_slug=inp["city_slug"],
        round_trip=inp["round_trip"],
        lenses=inp.get("lenses"),
        theme_hint=inp.get("theme_hint"),
        start_label=inp.get("start_label"),
    )

    # M3: routed leg costs when the local Valhalla is up (make valhalla-up);
    # identical to the haversine path when it isn't (total fallback).
    with RoutingClient() as routing_client:
        route = select_route(tour_input, snapshot, routing_client=routing_client)
    print("=" * 80)
    print(f"FIXTURE: {name}")
    print(f"Input: start={tour_input.start} duration={tour_input.duration_min}min "
          f"round_trip={tour_input.round_trip}")
    print(f"Spine: {route.spine_area} (expected {fixture.get('expected_spine_area')!r})")
    print(f"POIs picked: {[p.name for p in route.pois]}")
    print(f"Expected POIs: {fixture.get('expected_pois')}")
    print()

    generated_ids: set[str] = set()
    print("Per-POI breakdown:")
    for poi in route.pois:
        plan = select_poi_beats(poi, snapshot.beats_for(poi.id))
        for b in plan.beats:
            generated_ids.add(b.id)
        n_in_fix = sum(1 for b in plan.beats if b.id in expected)
        print(f"  {poi.name} (t{poi.tier}): "
              f"strategy={plan.ordering_strategy}, "
              f"beats={len(plan.beats)} (fixture-hits={n_in_fix})")

    overlap = len(expected & generated_ids)
    overlap_pct = overlap / len(expected) if expected else 0.0
    missing = sorted(expected - generated_ids)
    extra = sorted(generated_ids - expected)

    print()
    print(f"Overlap: {overlap}/{len(expected)} = {overlap_pct:.1%}")
    if missing:
        print(f"Missing fixture beats ({len(missing)}):")
        with driver.session() as s:
            for bid in missing[:25]:
                rec = s.run(
                    "MATCH (p:POI)-[:HAS_BEAT]->(b:NarrativeBeat {id: $bid}) "
                    "RETURN p.name AS poi, b.sub_location AS sub, "
                    "b.narrative_function AS nf, b.script_body AS body",
                    bid=bid,
                ).data()
                if rec:
                    r = rec[0]
                    body = (r.get("body") or "")[:60].replace("\n", " ")
                    print(f"  {bid[:8]} | {r['poi']:35s} | "
                          f"sub={(r.get('sub') or '')[:25]:25s} | "
                          f"nf={(r.get('nf') or '')[:14]:14s} | {body!r}")
        if len(missing) > 25:
            print(f"  … {len(missing) - 25} more")
    if extra:
        print(f"Extra generated beats not in fixture: {len(extra)} (omitted; not penalized)")

    driver.close()
    return 0 if overlap_pct >= 0.90 else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
