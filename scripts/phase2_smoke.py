"""Phase 2 smoke runs and performance timing.

Runs `select_route` against the live Paris corpus for the two §6 gate
inputs and reports a Route summary, plus median + p95 timing over 10
iterations.

Invoke from repo root:
    python -m scripts.phase2_smoke
"""

from __future__ import annotations

import statistics
import time

from src.connection import create_driver
from src.tour.contract import TourInput
from src.tour.selection import load_paris_corpus, select_route


def _format_route(route, label: str) -> str:
    lines = [f"\n=== {label} ==="]
    lines.append(f"  spine_area:           {route.spine_area}")
    lines.append(f"  selected_pois:        {len(route.pois)}")
    for i, poi in enumerate(route.pois, 1):
        lines.append(
            f"    {i:2d}. {poi.name:40s}  tier={poi.tier}  "
            f"areas={list(poi.areas)[:3]}  beats={poi.beat_count}"
        )
    lines.append(f"  total_walk_distance_m: {route.total_walk_distance_m:.0f}")
    lines.append(f"  total_walk_seconds:   {route.total_walk_seconds}  ({route.total_walk_seconds/60:.1f} min)")
    lines.append(f"  audio_budget_seconds: {route.audio_budget_seconds}  ({route.audio_budget_seconds/60:.1f} min)")
    lines.append(f"  err_short_total:      {route.err_short_total_seconds}s")
    lines.append(f"  target_audio:         {route.target_audio_seconds}s")
    lines.append(f"  transits:             {len(route.transits)}")
    return "\n".join(lines)


def main() -> int:
    print("Connecting to Neo4j and loading Paris corpus...")
    driver = create_driver()
    try:
        t0 = time.perf_counter()
        snapshot = load_paris_corpus(driver, city_slug="paris")
        load_ms = (time.perf_counter() - t0) * 1000
        print(f"  loaded {len(snapshot.pois)} POIs and {sum(len(b) for b in snapshot.beats_by_poi.values())} beats in {load_ms:.0f} ms")

        # ---- Smoke run 1: PdV round-trip 60min ----
        run_a = TourInput(
            start=(48.8555, 2.3656),  # Place des Vosges centroid
            duration_min=60,
            city_slug="paris",
            round_trip=True,
            start_label="Place des Vosges centroid",
        )
        route_a = select_route(run_a, snapshot)
        print(_format_route(route_a, "Smoke A — PdV centroid, 60 min, round-trip"))
        names_a = [p.name for p in route_a.pois]
        gate_a = "Place des Vosges" in names_a
        print(f"  GATE: PdV in route → {gate_a}")

        # ---- Smoke run 2: Pont Neuf metro 90min one-way ----
        run_b = TourInput(
            start=(48.85675, 2.341033),  # Pont Neuf POI as proxy for the metro
            duration_min=90,
            city_slug="paris",
            round_trip=False,
            start_label="Pont Neuf metro",
        )
        route_b = select_route(run_b, snapshot)
        print(_format_route(route_b, "Smoke B — Pont Neuf metro, 90 min, one-way"))
        names_b = [p.name for p in route_b.pois]
        areas_b: set[str] = set()
        for p in route_b.pois:
            areas_b.update(p.areas)
        gate_b_pn = "Pont Neuf" in names_b
        gate_b_ile = "Île de la Cité" in areas_b
        last = route_b.pois[-1].name if route_b.pois else "—"
        print(
            f"  GATE: Pont Neuf in route → {gate_b_pn}; "
            f"crosses Île de la Cité → {gate_b_ile}; "
            f"final stop = {last}"
        )

        # ---- Performance: 10 runs of select_route on a fresh snapshot ----
        print("\n=== Performance: 10 × select_route (snapshot pre-loaded) ===")
        timings_a: list[float] = []
        timings_b: list[float] = []
        for _ in range(10):
            t = time.perf_counter()
            select_route(run_a, snapshot)
            timings_a.append((time.perf_counter() - t) * 1000)
            t = time.perf_counter()
            select_route(run_b, snapshot)
            timings_b.append((time.perf_counter() - t) * 1000)

        for label, timings in (("Smoke A", timings_a), ("Smoke B", timings_b)):
            med = statistics.median(timings)
            p95 = sorted(timings)[int(len(timings) * 0.95) - 1]
            mn = min(timings)
            mx = max(timings)
            print(
                f"  {label}:  median={med:.1f} ms  p95={p95:.1f} ms  min={mn:.1f}  max={mx:.1f}"
            )
            print(f"    < 500ms gate: {'PASS' if mx < 500 else 'FAIL'}")

        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
