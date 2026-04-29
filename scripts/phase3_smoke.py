"""Phase 3 smoke run + cost / latency telemetry.

End-to-end PdV 60-min round-trip:
  Neo4j → load corpus → select_route → select_poi_beats →
  generate(beat_sequence, route, input, glue_client=Haiku) →
  validate_script.

Reports:
  - first 200 sentences of script with source attribution
  - validation summary
  - actual Haiku token consumption + USD cost (one run)
  - median + p95 wall-clock over 5 generation runs (mocked LLM,
    deterministic) AND one live-Haiku run for cost.

Invoke:
    python -m scripts.phase3_smoke

Requires ``ANTHROPIC_API_KEY`` env var for the live-Haiku step. Pass
``--mock-only`` to skip the network call and only report timing
against the deterministic mock.
"""

from __future__ import annotations

import argparse
import statistics
import time

from src.connection import create_driver
from src.tour.beat_select import select_poi_beats
from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import GLUE_LABELS, generate
from src.tour.glue_client import HaikuGlueClient, MockGlueClient, load_glue_prompt
from src.tour.selection import load_paris_corpus, select_route

# Haiku 4.5 pricing (per 1M tokens), 2026 list. Treat as approximate;
# the smoke prints raw token counts so the user can re-cost later.
HAIKU_INPUT_USD_PER_MTOK = 1.00
HAIKU_OUTPUT_USD_PER_MTOK = 5.00


def _build_beat_sequence(route, snapshot, lenses=None) -> BeatSequence:
    plans = []
    for poi in route.pois:
        beats = snapshot.beats_for(poi.id)
        plan = select_poi_beats(poi, beats, interest_lenses=lenses)
        plans.append(plan)
    return BeatSequence(poi_beats=tuple(plans))


def _summarise_script(script, n: int = 200) -> str:
    lines = [
        f"city_slug:              {script.city_slug}",
        f"generated_at:           {script.generated_at}",
        f"total_audio_seconds:    {script.total_audio_seconds}  ({script.total_audio_seconds/60:.1f} min)",
        f"total_walking_seconds:  {script.total_walking_seconds}  ({script.total_walking_seconds/60:.1f} min)",
        f"total_walk_distance_m:  {script.total_walk_distance_m}",
        f"total_planned_seconds:  {script.total_planned_seconds}",
        f"selected_pois:          {len(script.selected_pois)}",
        f"sentences:              {len(script.script)}",
        f"validation.passed:      {script.validation.passed}",
        f"untraceable count:      {len(script.validation.untraceable_sentences)}",
        f"forbidden_phrase hits:  {len(script.validation.forbidden_phrase_hits)}",
        "",
        "selected_pois:",
    ]
    for poi in script.selected_pois:
        lines.append(
            f"  - {poi.name:40s}  tier={poi.tier}  "
            f"area={poi.area}  beats={len(poi.beat_ids)}"
        )
    lines.append("")
    lines.append(f"first {min(n, len(script.script))} sentences:")
    for idx, sent in enumerate(script.script[:n], 1):
        attribution = (
            f"BEAT:{sent.source_id[:8]}…"
            if sent.source_type == "beat"
            else f"{sent.source_id}"
        )
        truncated = sent.text if len(sent.text) <= 200 else sent.text[:197] + "..."
        lines.append(f"  [{idx:3d}] (stop {sent.stop_idx}, {attribution}) {truncated}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mock-only",
        action="store_true",
        help="Skip the live Haiku call; report only mocked-LLM latency.",
    )
    parser.add_argument(
        "--lenses",
        type=str,
        default="",
        help="Comma-separated child lenses for interest bias.",
    )
    args = parser.parse_args()

    driver = create_driver()
    try:
        print("Loading Paris corpus from Neo4j...")
        t0 = time.perf_counter()
        snapshot = load_paris_corpus(driver, city_slug="paris")
        load_ms = (time.perf_counter() - t0) * 1000
        n_beats = sum(len(b) for b in snapshot.beats_by_poi.values())
        print(f"  loaded {len(snapshot.pois)} POIs, {n_beats} beats in {load_ms:.0f} ms")

        lenses = [s.strip() for s in args.lenses.split(",") if s.strip()] or None
        run = TourInput(
            start=(48.8555, 2.3656),
            duration_min=60,
            city_slug="paris",
            round_trip=True,
            start_label="Place des Vosges centroid",
            lenses=lenses,
        )

        print("\nSelecting route...")
        route = select_route(run, snapshot)
        print(f"  spine_area={route.spine_area}, {len(route.pois)} POIs")
        for i, p in enumerate(route.pois, 1):
            print(f"    {i:2d}. {p.name:40s} tier={p.tier} beats={p.beat_count}")

        print("\nSelecting beats per POI...")
        beat_sequence = _build_beat_sequence(route, snapshot)
        for plan in beat_sequence.poi_beats:
            print(
                f"  - {plan.poi_name:40s} strategy={plan.ordering_strategy} "
                f"beats={len(plan.beats)}"
            )

        # ----- 5 mocked generations for wall-clock median/p95 -----
        print("\nGenerating (mock LLM ×5) for latency measurement...")
        durations: list[float] = []
        last_script = None
        for _ in range(5):
            t = time.perf_counter()
            last_script = generate(beat_sequence, route, run, glue_client=MockGlueClient())
            durations.append((time.perf_counter() - t) * 1000)
        med = statistics.median(durations)
        p95 = sorted(durations)[int(len(durations) * 0.95) - 1]
        print(f"  median={med:.1f} ms  p95={p95:.1f} ms  min={min(durations):.1f}  max={max(durations):.1f}")
        print(f"  GATE: <30s wall-clock per tour → "
              f"{'PASS' if max(durations) < 30_000 else 'FAIL'}")

        assert last_script is not None
        print("\n" + _summarise_script(last_script, n=200))

        # ----- count expected Haiku invocations + token estimate -----
        glue_calls = []
        class _CountingMock:
            def stitch(self, category, context, request):
                glue_calls.append((category, context, request))
                return "Walk to the next stop."
        generate(beat_sequence, route, run, glue_client=_CountingMock())
        prompt_template = load_glue_prompt()
        # Rough char→token approximation (Anthropic guidance: ~4 chars/token).
        def _estimate_tokens(text: str) -> int:
            return max(1, len(text) // 4)
        proj_in = 0
        proj_out_max = 0
        for cat, ctx, req in glue_calls:
            rendered = (
                prompt_template.replace("{{CATEGORY}}", cat)
                .replace("{{CONTEXT}}", ctx or "(no surrounding context)")
                .replace("{{REQUEST}}", req or "(no specific request)")
            )
            proj_in += _estimate_tokens(rendered)
            proj_out_max += 150
        proj_usd_max = (
            proj_in / 1_000_000 * HAIKU_INPUT_USD_PER_MTOK
            + proj_out_max / 1_000_000 * HAIKU_OUTPUT_USD_PER_MTOK
        )
        print(f"\nProjected Haiku invocations: {len(glue_calls)}")
        for i, (cat, _, _) in enumerate(glue_calls, 1):
            print(f"  [{i}] {cat}")
        print(f"  estimated input toks (≈4ch/tok): {proj_in}")
        print(f"  max output toks (150/call):      {proj_out_max}")
        print(f"  upper-bound USD:                  ${proj_usd_max:.5f}")

        # ----- one live Haiku run for cost telemetry -----
        if not args.mock_only:
            print("\nLive Haiku run (cost telemetry)...")
            client = HaikuGlueClient()
            t = time.perf_counter()
            live_script = generate(beat_sequence, route, run, glue_client=client)
            live_ms = (time.perf_counter() - t) * 1000
            in_tok = client.input_tokens
            out_tok = client.output_tokens
            usd = (in_tok / 1_000_000) * HAIKU_INPUT_USD_PER_MTOK + \
                  (out_tok / 1_000_000) * HAIKU_OUTPUT_USD_PER_MTOK
            print(f"  wall-clock:        {live_ms:.0f} ms")
            print(f"  haiku input toks:  {in_tok}")
            print(f"  haiku output toks: {out_tok}")
            print(f"  estimated USD:     ${usd:.5f}")
            print(f"  GATE: <$0.01 per tour → {'PASS' if usd < 0.01 else 'FAIL'}")
            print(f"  validation.passed: {live_script.validation.passed}")

        return 0
    finally:
        driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
