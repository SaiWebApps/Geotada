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
import math
import sys
import time
import uuid
from pathlib import Path

from src.connection import create_driver
from src.tour.beat_select import select_vignette_beats
from src.tour.compose_gate import build_full_verifier
from src.tour.contract import BeatSequence, TourInput
from src.tour.density import TourabilityRefusedError, assess_snapshot
from src.tour.generation import generate
from src.tour.glue_client import HaikuGlueClient, MockGlueClient
from src.tour.render_md import render_markdown
from src.tour.routing import haversine_m
from src.tour.routing_client import RoutingClient
from src.tour.selection import (
    VALHALLA_MAX_CONTOUR_MINUTES,
    CertificationPlanningInfeasibleError,
    build_poi_beat_plans_capped,
    load_paris_corpus,
    reach_envelope_searched,
    select_route,
)

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
                return (
                    (float(record["lat"]), float(record["lng"])),
                    f"{record['area_name']} (centroid)",
                )

    raise SystemExit(
        f"\u2717 Could not resolve start point: {start_arg!r}. "
        f"Pass coordinates as 'lat,lng', an exact POI name, or an Area name."
    )


def _build_beat_sequence(route, snapshot, lenses) -> BeatSequence:
    capped = build_poi_beat_plans_capped(route, snapshot, lenses=lenses, end_is_none=True)
    # Render the walk-past vignettes too (Track B + filler-stub demotions):
    # select_route already populated route.vignettes; without this the CLI
    # markdown silently drops every walk-by one-liner, including a thin stop that
    # the governor demoted from a dedicated stop to a vignette. Mirrors the
    # /trips API build sites so the CLI tour matches what the app voices.
    vignette_beats = select_vignette_beats(route.vignettes, snapshot.beats_by_poi, lenses=lenses)
    return BeatSequence(
        poi_beats=tuple(pb for pb, _ in capped),
        vignette_beats=vignette_beats,
        overflow_by_poi={pb.poi_id: ov for pb, ov in capped if ov},
    )


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


def _perp_distance_m(
    lat: float, lng: float, a: tuple[float, float], b: tuple[float, float]
) -> float:
    """Perpendicular distance from a point to the straight A->B line, in metres.

    Equirectangular projection, which is exact enough across a city: the error
    over 10 km is under a metre, and this number is read to the nearest 10 m.
    Clamped to the segment, so a stop beyond either end measures to that end
    rather than to an imaginary extension of the line.
    """
    lat0 = math.radians((a[0] + b[0]) / 2.0)
    to_x = 111_320.0 * math.cos(lat0)
    to_y = 110_540.0
    ax, ay = a[1] * to_x, a[0] * to_y
    bx, by = b[1] * to_x, b[0] * to_y
    px, py = lng * to_x, lat * to_y
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / span))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _print_breakdown(
    *,
    tour_input: TourInput,
    wall_clock_s: float,
    route=None,
    script=None,
    best_elapsed_s: int | None = None,
) -> None:
    """The seven numbers, printed on BOTH the success and the refusal paths.

    ONE printer for both, deliberately, so the two can never drift into reporting
    different things. Four of the seven need a route that a refusal never
    produced; those say so in words rather than printing a zero, because a zero
    reads as a measurement and "no route exists" is not one.

    The reach radius comes from ``reach_envelope_searched`` -- the SAME function
    the planner uses -- so this reports the circle actually searched. Deriving it
    here from the requested duration would print ~4,444 m at 300 minutes while the
    fixed-destination planner searched ~12,259 m, and the harness built to expose
    that bug would have hidden it.
    """
    radius_m, iso_minutes = reach_envelope_searched(tour_input)
    absent = "— no route was produced, so this cannot be measured"

    print("  ── breakdown ──────────────────────────────────────────────")
    if route is not None and script is not None:
        walk_s = route.total_walk_seconds
        dwell_s = sum(p.dwell_seconds for p in script.selected_pois)
        legs = [
            int(t.leg_seconds) if getattr(t, "leg_seconds", None) is not None else t.walk_seconds
            for t in route.transits
        ]
        longest = max(legs) if legs else 0
        print(f"  walk:               {walk_s:6d} s ({walk_s // 60} min)")
        print(f"  dwell:              {dwell_s:6d} s ({dwell_s // 60} min)")
        print(f"  total (walk+dwell): {walk_s + dwell_s:6d} s ({(walk_s + dwell_s) // 60} min)")
        print(f"  longest leg:        {longest:6d} s ({longest // 60} min)")
        if tour_input.end is not None:
            worst = max(
                (
                    (_perp_distance_m(p.lat, p.lng, tour_input.start, tour_input.end), p.name)
                    for p in script.selected_pois
                ),
                default=(0.0, "—"),
            )
            print(f"  furthest off A→B:   {worst[0]:6.0f} m  ({worst[1]})")
        else:
            worst_open = max(
                (
                    (haversine_m(tour_input.start[0], tour_input.start[1], p.lat, p.lng), p.name)
                    for p in script.selected_pois
                ),
                default=(0.0, "—"),
            )
            print(
                f"  furthest off A→B:   {worst_open[0]:6.0f} m  ({worst_open[1]}) "
                "— measured from the start; this walk has no B"
            )
    else:
        best = "unknown" if best_elapsed_s is None else f"{best_elapsed_s} s"
        print(f"  walk:               {absent}")
        print(f"  dwell:              {absent}")
        print(
            f"  total (walk+dwell): {best} — the best bounded route the planner "
            "reached, which it then refused"
        )
        print(f"  longest leg:        {absent}")
        print(f"  furthest off A→B:   {absent}")
    # NAME WHICH MECHANISM WAS OPERATIVE, or this line is worse than no line.
    # `radius_m` is the analytic FALLBACK circle. The planner's primary admission
    # test is the Valhalla road polygon, used whenever the contour it asks for is
    # within the engine's limit. Reporting the circle without saying which of the
    # two applied invites a phase to record a shrink that never happened: clamping
    # the contour makes the polygon available again, so the circle can fall while
    # the region the planner actually admits GROWS.
    if iso_minutes > VALHALLA_MAX_CONTOUR_MINUTES:
        note = (
            f"isochrone {iso_minutes} min REFUSED (>{VALHALLA_MAX_CONTOUR_MINUTES} "
            "max), so this circle IS the reach test"
        )
    else:
        note = (
            f"isochrone {iso_minutes} min accepted, so the ROAD POLYGON is the reach "
            "test and this circle is only its fallback"
        )
    print(f"  reach radius:       {radius_m:6.0f} m circle — {note}")
    print(f"  wall clock:         {wall_clock_s:6.2f} s")
    # CLOCK EXCLUSIONS — printed on every DATED run, including when empty, so a
    # Monday and a Tuesday breakdown keep the same shape and read side by side
    # (D1 demo). Omitted entirely on a dateless run, which is what keeps that
    # output byte-identical to the pre-clock harness. Reads the field
    # defensively: the section lands (printing "none") before Route learns to
    # record exclusions in S1.6, and lists them once it has.
    if tour_input.start_datetime is not None:
        exclusions = getattr(route, "clock_exclusions", ()) if route is not None else ()
        print("  clock exclusions:")
        if exclusions:
            for excl in exclusions:
                print(f"    • {excl.name} — {excl.reason}")
        else:
            print("    none")
    print("  ───────────────────────────────────────────────────────────")


def _print_refusal(
    a,
    *,
    header: str,
    duration_min: int,
    round_trip: bool,
) -> None:
    """Structured stdout for a refusal — a Phase 6 RED density refusal OR an empty
    delivery (density passed but no stop survived selection, e.g. a lensed thin
    area where every reachable POI fell to a walk-by).

    Includes fill_ratio + anchor count, max_supportable_duration, and
    one_way_alternative_destination when applicable. Prints actionable
    next steps so the harness's caller (the skill) can relay them.
    """
    print(header)
    print(f"  fill_ratio:        {a.fill_ratio:.2f} (target ≥ 1.0)")
    print(f"  anchor_candidates: {a.anchor_candidate_count} (target ≥ 4)")
    print(f"  cluster_compactness: {a.cluster_compactness:.2f} (target ≤ 0.6)")
    print(f"  reachable_pois:    {a.reachable_poi_count}")
    print(f"  reachable_beats:   {a.reachable_beat_count}")
    print(f"  walk_radius_m:     {a.walk_radius_m:.0f}")
    print()
    print("  Recommendations:")
    if a.max_supportable_duration_min and a.max_supportable_duration_min < duration_min:
        print(
            f"    • Try a {a.max_supportable_duration_min}-min "
            f"{'round-trip' if round_trip else 'one-way'} instead "
            f"(corpus capacity supports this length)."
        )
    if round_trip and a.one_way_alternative_destination:
        print(
            f"    • Try one-way ending at {a.one_way_alternative_destination!r} "
            f"(denser corpus reachable on a one-way path)."
        )
    if not (
        (a.max_supportable_duration_min and a.max_supportable_duration_min < duration_min)
        or (round_trip and a.one_way_alternative_destination)
    ):
        print(
            "    • Try a different starting area; this start point is too sparse "
            "for the requested duration. Consult "
            "`data/{city}/tourability_summary.md` for nearest GREEN starts."
        )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", required=True, help="'lat,lng' or POI/Area name")
    parser.add_argument(
        "--end",
        default=None,
        help=(
            "'lat,lng' or POI/Area name for a fixed destination B. Omit for an open "
            "walk. Mutually exclusive with --round-trip."
        ),
    )
    parser.add_argument("--duration", type=int, required=True, help="Minutes")
    parser.add_argument("--lenses", default="", help="Comma-separated child lenses")
    parser.add_argument("--round-trip", action="store_true")
    parser.add_argument("--theme", default="", help="Optional theme hint")
    parser.add_argument("--city-slug", default="paris")
    # THE PLANNER'S CLOCK (redesign §2.2/§2.3). No --date = dateless planning,
    # byte-identical to before the clock existed — which is also what keeps the
    # W1.1 before-picture comparable to a post-clock dateless run.
    parser.add_argument(
        "--date",
        default=None,
        help="Walk date, YYYY-MM-DD. Omit for dateless planning (today's behaviour).",
    )
    parser.add_argument(
        "--time",
        default="09:00",
        help="Walk start time, HH:MM (used only with --date; default 09:00).",
    )
    parser.add_argument(
        "--end-hardness",
        choices=["wall", "firm", "open"],
        default="firm",
        help="How hard the end is: wall keeps visible slack, firm is today's "
        "behaviour, open never pads toward the requested length.",
    )
    parser.add_argument(
        "--haiku",
        action="store_true",
        help="Use real Haiku for glue (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--canned",
        action="store_true",
        help=(
            "Use the deterministic MockGlueClient for glue: transitions are fixed "
            "strings, not written by a model. Free, and must be asked for."
        ),
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
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    # WHO WRITES THE TRANSITIONS — decided here, before any work, because a
    # refusal that arrives after selection and routing has already spent the
    # user's time. Fails closed like get_provider / get_drafter /
    # build_full_verifier: MockGlueClient used to be the SILENT default, so a
    # tour the owner read could be part fixed-string prose under a
    # "validation: PASS" header with nothing naming it.
    if args.haiku and args.canned:
        parser.error(
            "--haiku and --canned contradict: one uses a real model for the "
            "transitions and the other uses fixed strings. Pass exactly one."
        )
    if not (args.haiku or args.canned):
        parser.error(
            "refusing to write a tour without saying who wrote the transitions. "
            "Pass --haiku for real Haiku glue (spends money), or --canned for "
            "the deterministic fixed-string glue (free). There is no default: "
            "canned transitions presented as a finished tour is the defect this "
            "replaces."
        )

    project_root = Path(__file__).resolve().parent.parent
    out_dir = (
        Path(args.output_dir)
        if args.output_dir
        else project_root / "data" / args.city_slug / "tours"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    driver = create_driver()
    try:
        start_coords, start_label = _resolve_start(driver, args.start, args.city_slug)
        # Resolved through the SAME resolver as --start so a name, a substring and a
        # bare "lat,lng" all behave identically at both ends. The label is discarded:
        # TourInput carries start_label and has no end_label field.
        end_coords: tuple[float, float] | None = None
        if args.end:
            end_coords, _ = _resolve_start(driver, args.end, args.city_slug)
        snapshot = load_paris_corpus(driver, city_slug=args.city_slug)

        lenses = [s.strip() for s in args.lenses.split(",") if s.strip()] or None
        tour_input = TourInput(
            start=start_coords,
            duration_min=args.duration,
            city_slug=args.city_slug,
            round_trip=bool(args.round_trip),
            end=end_coords,
            lenses=lenses,
            theme_hint=args.theme.strip() or None,
            start_label=start_label,
            start_datetime=f"{args.date}T{args.time}" if args.date else None,
            end_hardness=args.end_hardness,
        )

        t_select = time.perf_counter()
        try:
            # M3: routed leg costs when the local Valhalla is up; total
            # haversine fallback (sticky-degraded after one refusal) when not.
            with RoutingClient() as routing_client:
                route = select_route(tour_input, snapshot, routing_client=routing_client)
        except TourabilityRefusedError as exc:
            rt = bool(args.round_trip)
            _print_refusal(
                exc.assessment,
                header=(
                    f"\u2717 TOURABILITY REFUSED (RED) \u2014 {start_label} "
                    f"{args.duration}-min {'round-trip' if rt else 'one-way'}"
                ),
                duration_min=args.duration,
                round_trip=rt,
            )
            return 3
        except CertificationPlanningInfeasibleError as exc:
            # CAUGHT, not allowed to escape. Until this clause existed, a request
            # that merely did not fit its certification band ended the run in a
            # Python traceback — the harness printed none of the numbers that
            # explain WHY, and the one command meant to demonstrate the reported
            # bug produced a stack trace instead of evidence. Everything printed
            # here already lives on the exception (src/tour/selection.py:456-487);
            # nothing is recomputed, so this cannot disagree with the planner.
            rt = bool(args.round_trip)
            lo, hi = exc.minimum_elapsed_seconds, exc.maximum_elapsed_seconds
            best = exc.best_elapsed_seconds
            print(
                f"✗ CERTIFICATION PLANNING INFEASIBLE — {start_label} "
                f"{args.duration}-min {'round-trip' if rt else 'one-way'}"
            )
            print(f"  message:     {exc}")
            print(f"  policy:      {exc.policy_id}")
            print(f"  reason:      {exc.reason}")
            print(f"  required:    {lo}-{hi}s ({lo // 60}-{hi // 60} min)")
            print(
                "  best found:  "
                + ("none" if best is None else f"{best}s ({best // 60} min)")
            )
            if exc.gap_minutes is not None:
                print(f"  gap:         {exc.gap_minutes} min")
            print()
            print("  Alternatives:")
            if not exc.alternatives:
                print("    • none offered by the planner")
            for alt in exc.alternatives:
                if alt.kind == "closer_b" and alt.poi_id:
                    print(
                        f"    • closer_b: end at {alt.poi_id} "
                        f"({alt.lat:.5f}, {alt.lng:.5f}) at {alt.duration_min} min"
                    )
                elif alt.kind == "extend":
                    print(
                        f"    • extend: keep this destination, ask for "
                        f"{alt.duration_min} min"
                    )
                elif alt.kind == "loop":
                    print(
                        f"    • loop: drop the destination, walk {alt.duration_min} "
                        f"min from the start"
                    )
                else:
                    print(
                        f"    • {alt.kind}: {alt.duration_min} min, "
                        f"drop_end={alt.drop_end}"
                    )
            print()
            _print_breakdown(
                tour_input=tour_input,
                wall_clock_s=time.perf_counter() - t_select,
                best_elapsed_s=exc.best_elapsed_seconds,
            )
            return 3
        t_select = time.perf_counter() - t_select

        if not route.pois:
            # Density passed but no stop survived selection \u2014 e.g. a lensed thin
            # area where every reachable POI fell to a walk-by. Route through the
            # SAME structured refusal (actionable alternatives) instead of a bare
            # "no POIs reachable". Reuse the attached assessment, else recompute.
            rt = bool(args.round_trip)
            assessment = route.tourability or assess_snapshot(tour_input, snapshot)
            lens_note = " for your interest" if lenses else ""
            _print_refusal(
                assessment,
                header=(
                    f"\u2717 EMPTY TOUR \u2014 {start_label} {args.duration}-min "
                    f"{'round-trip' if rt else 'one-way'}: no stop survived "
                    f"selection (every reachable POI fell to a walk-by{lens_note})."
                ),
                duration_min=args.duration,
                round_trip=rt,
            )
            return 3

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
            # CANNED GLUE, and it must be ASKED FOR. Every transition sentence in
            # the tour this prints comes from MockGlueClient's fixed table
            # (src/tour/glue_client.py), not from a model. This used to be the
            # silent default, so a tour the owner read could be part canned prose
            # under a "validation: PASS" header with nothing naming it — the same
            # shape of lie as reporting a faithfulness pass that never ran.
            #
            # Reached only with an explicit --canned; the guard after
            # parse_args() has already refused the no-flag case. The summary
            # below still prints which implementation produced the prose.
            t_gen = time.perf_counter()
            script = generate(beat_sequence, route, tour_input, glue_client=MockGlueClient())
            t_gen = time.perf_counter() - t_gen
            # Project cost upper bound from a one-shot counting pass.
            in_tok, out_tok, cost_usd = _project_cost_upper_bound(
                beat_sequence, route, tour_input
            )
            cost_kind = "projected"

        # VERIFY the deterministic stitch (traceability + forbidden + rapidfuzz
        # provenance + faithfulness) and attach the merged report. There is no
        # recompose ladder here any more: this harness renders the $0 stitch, and
        # the whole-tour composer it used to re-run died with compose.py. A failing
        # report is reported and exits 1 rather than re-rolling the same
        # deterministic stitch. Chunk text isn't loaded here, so provenance is a
        # no-op until the corpus backfills source_passage.
        #
        # FAITHFULNESS IS NOT CHECKED HERE, and that is now stated rather than
        # implied. This call used to pass no checker at all, and the gate quietly
        # substituted the trusting Mock — so the "validation: PASS" line below
        # announced a pass on a check that never ran, on the very script the
        # owner reads. The opt-out is explicit, and the printed summary says
        # UNVERIFIED. Wiring the real Haiku checker here is a deliberate spend
        # decision, not something this harness should do by default.
        beats_by_id = {b.id: b for plan in beat_sequence.poi_beats for b in plan.beats}
        verify = build_full_verifier(
            beat_sequence,
            beats_by_id,
            allow_unverified_faithfulness=True,
            spine_area=route.spine_area,
        )
        script = script.model_copy(update={"validation": verify(script)})

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
                tourability=route.tourability,
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
        _print_breakdown(
            tour_input=tour_input,
            wall_clock_s=wall_clock,
            route=route,
            script=script,
        )
        print(
            f"  validation:  {'PASS' if passed else 'FAIL'} "
            f"(untraceable={len(script.validation.untraceable_sentences)}, "
            f"forbidden={len(script.validation.forbidden_phrase_hits)})"
        )
        # Say plainly which checks actually ran, and what wrote the prose. "PASS"
        # above covers traceability and forbidden phrases; it has never covered
        # faithfulness on this path, and printing only PASS is what made an
        # unverified tour read as verified. The same applies to the transitions:
        # without --haiku they are canned strings, and a reader judging the tour
        # deserves to know which sentences no model wrote.
        print(
            "  faithfulness: "
            + (
                "CHECKED"
                if script.validation.faithfulness_checked
                else "NOT CHECKED — no entailment pass ran on this tour"
            )
        )
        print(
            "  glue:        "
            + (
                "REAL (Haiku)"
                if args.haiku
                else "CANNED — transitions are fixed strings from MockGlueClient, "
                "not written by a model; pass --haiku for real ones"
            )
        )
        if route.tourability is not None and route.tourability.status == "YELLOW":
            tb = route.tourability
            hints: list[str] = []
            if tb.max_supportable_duration_min:
                hints.append(f"consider {tb.max_supportable_duration_min}-min")
            if tb.round_trip and tb.one_way_alternative_destination:
                hints.append(
                    f"or one-way ending at {tb.one_way_alternative_destination!r}"
                )
            hint_str = "; ".join(hints) if hints else "thin tour"
            print(
                f"  tourability: YELLOW — fill_ratio={tb.fill_ratio:.2f} ({hint_str})"
            )
        else:
            print("  tourability: GREEN")

        return 0 if passed else 1
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
