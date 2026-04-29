"""End-to-end /tour-build CLI harness.

Resolves a named or coordinate start point against Paris Neo4j, runs
``selection → beat_select → generation → validation``, writes the
JSON Script + Markdown render to ``data/{city_slug}/tours/{id}.json``
+ ``.md``, and prints a one-line summary.

Defaults to the deterministic ``MockGlueClient`` so this works without
``ANTHROPIC_API_KEY``. Pass ``--haiku`` to switch on the real Haiku
glue stitch (requires the env var).

Exit codes:
- 0 — validation passed
- 1 — validation failed (untraceable sentence(s) or forbidden phrase hit)
- 2 — input/resolution error (e.g. unknown start name, no POIs reachable)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

from src.connection import create_driver
from src.tour.beat_select import select_poi_beats
from src.tour.contract import BeatSequence, Script, TourInput
from src.tour.generation import generate
from src.tour.glue_client import HaikuGlueClient, MockGlueClient
from src.tour.render_md import render_markdown
from src.tour.selection import load_paris_corpus, select_route

HAIKU_INPUT_USD_PER_MTOK = 1.00  # 2026 Haiku 4.5 list (per 1M tokens)
HAIKU_OUTPUT_USD_PER_MTOK = 5.00


def _resolve_start(driver, start_arg: str, city_slug: str) -> tuple[tuple[float, float], str]:
    """Coordinate string or POI/Area name → (lat, lng) + display label.

    Tries (in order):
    1. ``"lat,lng"`` literal.
    2. POI exact name (case-insensitive).
    3. POI substring match (case-insensitive contains).
    4. Area exact name → use the centroid of POIs WITHIN that area.
    """
    if "," in start_arg:
        try:
            lat_s, lng_s = start_arg.split(",", 1)
            return (float(lat_s.strip()), float(lng_s.strip())), start_arg
        except ValueError:
            pass

    # Build a list of name candidates to try, full name first then
    # progressively shorter leading-word slices ("Pont Neuf metro" →
    # "Pont Neuf metro", "Pont Neuf", "Pont"). Stops at 1 word.
    tokens = start_arg.split()
    candidates: list[str] = []
    for n_words in range(len(tokens), 0, -1):
        candidates.append(" ".join(tokens[:n_words]))

    with driver.session() as session:
        for cand in candidates:
            record = session.run(
                "MATCH (p:POI {city_name: $city}) "
                "WHERE toLower(p.name) = toLower($name) "
                "RETURN p.name AS name, p.location.y AS lat, p.location.x AS lng "
                "LIMIT 1",
                city=city_slug,
                name=cand,
            ).single()
            if record:
                return (float(record["lat"]), float(record["lng"])), record["name"]

        for cand in candidates:
            record = session.run(
                "MATCH (p:POI {city_name: $city}) "
                "WHERE toLower(p.name) CONTAINS toLower($needle) "
                "WITH p ORDER BY p.importance_tier DESC, p.name "
                "RETURN p.name AS name, p.location.y AS lat, p.location.x AS lng "
                "LIMIT 1",
                city=city_slug,
                needle=cand,
            ).single()
            if record:
                return (float(record["lat"]), float(record["lng"])), record["name"]

        for cand in candidates:
            record = session.run(
                "MATCH (p:POI {city_name: $city})-[:WITHIN]->(a:Area) "
                "WHERE toLower(a.name) = toLower($name) AND p.location IS NOT NULL "
                "RETURN avg(p.location.y) AS lat, avg(p.location.x) AS lng, "
                "       a.name AS area_name "
                "LIMIT 1",
                city=city_slug,
                name=cand,
            ).single()
            if record and record["lat"] is not None:
                return (float(record["lat"]), float(record["lng"])), f"{record['area_name']} (centroid)"

    raise SystemExit(
        f"\u2717 Could not resolve start point: {start_arg!r}. "
        f"Pass coordinates as 'lat,lng', an exact POI name, or an Area name."
    )


def _build_beat_sequence(route, snapshot, lenses) -> BeatSequence:
    plans = []
    for poi in route.pois:
        beats = snapshot.beats_for(poi.id)
        plan = select_poi_beats(poi, beats, interest_lenses=lenses)
        plans.append(plan)
    return BeatSequence(poi_beats=tuple(plans))


def _generated_id(start_label: str, duration_min: int) -> str:
    safe = "".join(ch if ch.isalnum() else "-" for ch in start_label.lower())
    safe = "-".join(p for p in safe.split("-") if p)
    suffix = uuid.uuid4().hex[:6]
    return f"{safe[:40]}-{duration_min}min-{suffix}"


def _project_cost_upper_bound(
    beat_sequence: BeatSequence, route, tour_input: TourInput
) -> tuple[int, int, float]:
    """Approx Haiku cost ceiling without making a network call.

    Counts glue invocations the same way generation.py would, multiplies
    by max output tokens (150) and Haiku list price; estimates input
    tokens from the rendered prompt template (~4 chars per token).
    """
    from src.tour.glue_client import load_glue_prompt

    template = load_glue_prompt()
    glue_calls: list[tuple[str, str, str]] = []

    class _Counting:
        def stitch(self, category, context, request):
            glue_calls.append((category, context, request))
            return "Walk to the next stop."

    generate(beat_sequence, route, tour_input, glue_client=_Counting())

    proj_in = 0
    proj_out_max = 150 * len(glue_calls)
    for cat, ctx, req in glue_calls:
        rendered = (
            template.replace("{{CATEGORY}}", cat)
            .replace("{{CONTEXT}}", ctx or "(no surrounding context)")
            .replace("{{REQUEST}}", req or "(no specific request)")
        )
        proj_in += max(1, len(rendered) // 4)
    usd = (
        proj_in / 1_000_000 * HAIKU_INPUT_USD_PER_MTOK
        + proj_out_max / 1_000_000 * HAIKU_OUTPUT_USD_PER_MTOK
    )
    return proj_in, proj_out_max, usd


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", required=True, help="'lat,lng' or POI/Area name")
    parser.add_argument("--duration", type=int, required=True, help="Minutes")
    parser.add_argument("--lenses", default="", help="Comma-separated child lenses")
    parser.add_argument("--round-trip", action="store_true")
    parser.add_argument("--theme", default="", help="Optional theme hint")
    parser.add_argument("--city-slug", default="paris")
    parser.add_argument(
        "--haiku",
        action="store_true",
        help="Use real Haiku for glue (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output dir (default: data/{city_slug}/tours/)",
    )
    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="JSON only (skip the markdown render).",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_dir = Path(args.output_dir) if args.output_dir else project_root / "data" / args.city_slug / "tours"
    out_dir.mkdir(parents=True, exist_ok=True)

    driver = create_driver()
    try:
        start_coords, start_label = _resolve_start(driver, args.start, args.city_slug)
        snapshot = load_paris_corpus(driver, city_slug=args.city_slug)

        lenses = [s.strip() for s in args.lenses.split(",") if s.strip()] or None
        tour_input = TourInput(
            start=start_coords,
            duration_min=args.duration,
            city_slug=args.city_slug,
            round_trip=bool(args.round_trip),
            lenses=lenses,
            theme_hint=args.theme.strip() or None,
            start_label=start_label,
        )

        t_select = time.perf_counter()
        route = select_route(tour_input, snapshot)
        t_select = time.perf_counter() - t_select

        if not route.pois:
            raise SystemExit(
                f"\u2717 No POIs reachable from {start_label} within "
                f"{args.duration}-min envelope."
            )

        t_beats = time.perf_counter()
        beat_sequence = _build_beat_sequence(route, snapshot, lenses)
        t_beats = time.perf_counter() - t_beats

        if args.haiku:
            client = HaikuGlueClient()
            t_gen = time.perf_counter()
            script = generate(beat_sequence, route, tour_input, glue_client=client)
            t_gen = time.perf_counter() - t_gen
            in_tok = client.input_tokens
            out_tok = client.output_tokens
            cost_usd = (
                in_tok / 1_000_000 * HAIKU_INPUT_USD_PER_MTOK
                + out_tok / 1_000_000 * HAIKU_OUTPUT_USD_PER_MTOK
            )
            cost_kind = "measured"
        else:
            t_gen = time.perf_counter()
            script = generate(beat_sequence, route, tour_input, glue_client=MockGlueClient())
            t_gen = time.perf_counter() - t_gen
            # Project cost upper bound from a one-shot counting pass.
            in_tok, out_tok, cost_usd = _project_cost_upper_bound(
                beat_sequence, route, tour_input
            )
            cost_kind = "projected"

        wall_clock = t_select + t_beats + t_gen

        gen_id = _generated_id(start_label, args.duration)
        json_path = out_dir / f"{gen_id}.json"
        md_path = out_dir / f"{gen_id}.md"

        json_path.write_text(json.dumps(script.model_dump(mode="json"), indent=2) + "\n")
        if not args.no_markdown:
            md = render_markdown(
                script,
                cost_usd=cost_usd,
                haiku_input_tokens=in_tok,
                haiku_output_tokens=out_tok,
                wall_clock_seconds=wall_clock,
                beat_sequence=beat_sequence,
            )
            md_path.write_text(md)

        # ----- summary -----
        passed = script.validation.passed
        print(f"\u2713 generated_id={gen_id}")
        print(f"  json:        {json_path}")
        if not args.no_markdown:
            print(f"  markdown:    {md_path}")
        print(f"  start:       {start_label} ({start_coords[0]:.5f}, {start_coords[1]:.5f})")
        print(f"  spine:       {route.spine_area}")
        print(f"  POIs:        {len(route.pois)}  → {[p.name for p in route.pois]}")
        print(
            f"  walk:        {script.total_walking_seconds // 60} min "
            f"({script.total_walk_distance_m} m)"
        )
        print(f"  audio:       {script.total_audio_seconds // 60} min")
        print(
            f"  planned:     {script.total_planned_seconds // 60} min "
            f"(err-short of {args.duration})"
        )
        print(f"  cost:        ${cost_usd:.5f} ({cost_kind}: {in_tok} in + {out_tok} out)")
        print(f"  wall_clock:  {wall_clock:.2f} s")
        print(
            f"  validation:  {'PASS' if passed else 'FAIL'} "
            f"(untraceable={len(script.validation.untraceable_sentences)}, "
            f"forbidden={len(script.validation.forbidden_phrase_hits)})"
        )

        return 0 if passed else 1
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
