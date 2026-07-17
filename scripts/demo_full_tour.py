"""DEMO: generate a real tour and (behind a spend gate) compose it with the hook
opener + in-memory single-fact decomposition, then print BEFORE vs AFTER.

$0 dry run (default): generate the stitched tour, print each stop's opener (the raw
"X is a ... in ..." label), count keyless beats, and print a spend estimate. No API.

--live (requires ONDOWAY_DEMO_APPROVE=1): decompose each KEYLESS selected beat into
atomic grounded key_claims (Haiku) IN MEMORY — no graph write — so the coverage gate
catches any dropped fact; then compose per-chapter with the live Opus hook prompt
(candidates=1) and print the composed openers + full tour + coverage + token cost.

Usage:
  uv run python scripts/demo_full_tour.py --city london --start 51.5081,-0.1281 --duration 40
  ONDOWAY_DEMO_APPROVE=1 uv run python scripts/demo_full_tour.py --city london \
      --start 51.5081,-0.1281 --duration 40 --lenses hidden_history --live
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv
from rapidfuzz import fuzz

import src.tour.compose as _compose_mod
from src.connection import create_driver
from src.tour.beat_select import select_poi_beats
from src.tour.claim_dedup import claims_realized_by, verify_claim_coverage
from src.tour.compose import compose_script_per_chapter
from src.tour.content_budget import partition_poi_content
from src.tour.compose_gate import ComposeVerificationError
from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import generate
from src.tour.render_md import stop_narration_text
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route

load_dotenv()

_DECOMP_SYSTEM = (
    "You split a walking-tour beat's body into its ATOMIC factual claims. Each claim "
    "states EXACTLY ONE fact (one date, one person, one measure, one relationship). "
    "Invent nothing; add no fact absent from the body. For each claim also return "
    "`quote`: the verbatim span of the body that supports it. Prefer one claim per "
    "independent fact; a sentence carrying two facts becomes two claims. Keep a compound "
    "fact that cannot be split without loss as one claim. Do not split a claim below "
    "about four content words."
)
_DECOMP_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"claim": {"type": "string"}, "quote": {"type": "string"}},
                "required": ["claim", "quote"],
            },
        }
    },
    "required": ["claims"],
}


def _stop_beat_openers(script) -> dict[int, str]:
    """The FIRST beat-authored sentence of each stop — the actual dwell opener (the
    label pre-compose, the hook post-compose), skipping nav/glue/reflection lines."""
    out: dict[int, str] = {}
    for s in script.script:
        if s.source_type == "beat" and s.stop_idx not in out:
            out[s.stop_idx] = s.text
    return out


def _keyless_beats(seq: BeatSequence) -> list:
    return [b for pb in seq.poi_beats for b in pb.beats if not b.key_claims]


def _decompose_beat(beat, anthropic_client, checker) -> tuple[str, ...]:
    """Haiku: atomic grounded claims for one keyless beat. Grounding: quote in body
    (rapidfuzz partial_ratio >= 88) AND entails(quote -> claim). Drop failures."""
    body = beat.script_body or ""
    if not body:
        return ()
    resp = anthropic_client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=_DECOMP_SYSTEM,
        output_config={"format": {"type": "json_schema", "schema": _DECOMP_SCHEMA}},
        messages=[{"role": "user", "content": f"POI: {beat.poi_id}\nBODY: {body}"}],
    )
    text = next((b.text for b in (resp.content or []) if b.type == "text"), None)
    if not text:
        return ()
    out: list[str] = []
    for c in json.loads(text).get("claims", []):
        claim, quote = c.get("claim", "").strip(), c.get("quote", "").strip()
        if not claim or not quote:
            continue
        if fuzz.partial_ratio(quote, body) < 88:  # quote must be in the body
            continue
        if not checker.entails((quote,), claim):  # claim must not overstate its quote
            continue
        out.append(claim)
    return tuple(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    ap.add_argument("--start", required=True, help="lat,lng")
    ap.add_argument("--duration", type=int, default=40)
    ap.add_argument("--lenses", default="")
    ap.add_argument("--round-trip", action="store_true")
    ap.add_argument("--core-seconds", type=int, default=0,
                    help="if >0, cap each stop to its CORE beats (content_budget) — tight + cheap")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

    # HARD spend safeguard: bound output tokens PER compose call (default 64k) so a stop
    # can never balloon to the runaway that cost $11 last time. 12k is ~5x below the
    # default, roomy for a tight ~225-word stop's text+thinking, and caps a call at
    # ~$0.9 worst-case.
    _compose_mod.COMPOSE_MAX_OUTPUT_TOKENS = 12000

    lat, lng = (float(x) for x in args.start.split(","))
    lenses = [x for x in args.lenses.split(",") if x]
    tour_input = TourInput(
        start=(lat, lng), duration_min=args.duration, city_slug=args.city, lenses=lenses,
        round_trip=args.round_trip,
    )

    driver = create_driver()
    try:
        snapshot = load_paris_corpus(driver, city_slug=args.city)
    finally:
        driver.close()
    with RoutingClient() as rc:
        route = select_route(tour_input, snapshot, routing_client=rc)
    if not route.pois:
        print(f"NO ROUTE from {args.start} in {args.city}", file=sys.stderr)
        return 2

    plans = []
    for poi in route.pois:
        beats = list(snapshot.beats_for(poi.id)) + list(route.demoted_beats.get(poi.id, ()))
        plans.append(select_poi_beats(poi, beats, interest_lenses=tour_input.lenses))
    # CORE CAP: trim each stop to its content_budget CORE beats (the hook + best story
    # within the budget) so stops are listenable (~150-225 words) and cheap to compose.
    # Overflow beats would go to the tap / walk-away (not composed in this demo).
    if args.core_seconds > 0:
        capped = []
        dropped = 0
        for pb in plans:
            cb = partition_poi_content(pb, core_seconds_budget=args.core_seconds)
            core = tuple(b for b in pb.beats if b.id in set(cb.core_ids))
            dropped += len(pb.beats) - len(core)
            capped.append(pb.model_copy(update={"beats": core or pb.beats[:1]}))
        plans = capped
        print(f"CORE CAP: trimmed {dropped} overflow beats to the tap "
              f"(core={args.core_seconds}s ~{args.core_seconds*150//60}w/stop)")

    seq = BeatSequence(poi_beats=tuple(plans))
    stitched = generate(seq, route, tour_input)
    before = _stop_beat_openers(stitched)

    print(f"\n{'='*70}\n{args.city.upper()} — {len(route.pois)} stops, {args.duration} min"
          f"  (start {args.start}, lenses={lenses or 'none'})\n{'='*70}")
    print("\n### BEFORE (stitched — the raw first beat sentence per stop) ###")
    for idx in sorted(before):
        print(f"  [{idx}] {before[idx][:120]}")

    keyless = _keyless_beats(seq)
    print(f"\nkeyless beats in this tour: {len(keyless)} / "
          f"{sum(len(pb.beats) for pb in seq.poi_beats)} selected")
    if not args.live:
        n_stops = len(route.pois)
        print(f"\n[DRY RUN — no spend] Estimate to compose live: ~{len(keyless)} Haiku "
              f"decomposition calls (~${len(keyless)*0.0015:.2f}) + {n_stops}-stop Opus "
              f"compose candidates=1 (~${n_stops*0.09:.2f}) + Haiku faithfulness. "
              f"Re-run with --live and ONDOWAY_DEMO_APPROVE=1 to spend.")
        return 0

    if os.getenv("ONDOWAY_DEMO_APPROVE") != "1":
        print("\nREFUSED: --live requires ONDOWAY_DEMO_APPROVE=1 in the environment.",
              file=sys.stderr)
        return 3

    # ---- LIVE: decompose keyless beats in-memory, then compose with the hook prompt ----
    import anthropic

    from src.tour.compose import AnthropicComposeClient
    from src.tour.verify import HaikuFaithfulnessChecker

    raw = anthropic.Anthropic()
    checker = HaikuFaithfulnessChecker()
    decomposed = 0
    new_plans = []
    for pb in seq.poi_beats:
        beats = []
        for b in pb.beats:
            if not b.key_claims:
                kc = _decompose_beat(b, raw, checker)
                if kc:
                    b = b.model_copy(update={"key_claims": kc})
                    decomposed += 1
            beats.append(b)
        new_plans.append(pb.model_copy(update={"beats": tuple(beats)}))
    seq = BeatSequence(
        poi_beats=tuple(new_plans),
        vignette_beats=seq.vignette_beats,
        overflow_by_poi=seq.overflow_by_poi,
    )
    print(f"\ndecomposed {decomposed} keyless beats into atomic key_claims (in memory).")

    beats_by_id = {b.id: b for pb in seq.poi_beats for b in pb.beats}
    expected = claims_realized_by(stitched, beats_by_id)

    client = AnthropicComposeClient()
    try:
        composed = compose_script_per_chapter(
            stitched, seq, route, client=client, faithfulness_checker=checker, candidates=1
        )
    except ComposeVerificationError as exc:
        print(f"\nCOMPOSE REFUSED after {exc.attempts} attempts: {exc.report}", file=sys.stderr)
        return 4

    after = stop_narration_text(composed)
    after_openers = _stop_beat_openers(composed)
    coverage_fail = verify_claim_coverage(composed, expected, beats_by_id)

    print("\n### BEFORE vs AFTER — the dwell-stop opener ###")
    for idx in sorted(before):
        print(f"  [{idx}] BEFORE: {before[idx][:110]}")
        print(f"  [{idx}] AFTER : {after_openers.get(idx, '(no beat sentence)')[:110]}\n")

    print(f"\n{'='*70}\nFULL COMPOSED {args.city.upper()} TOUR\n{'='*70}")
    for idx in sorted(after):
        print(f"\n--- STOP {idx} ---\n{after[idx]}")

    print(f"\n{'='*70}\ncoverage failures (facts dropped): {len(coverage_fail)}"
          f"{'' if not coverage_fail else ' -> ' + str(coverage_fail[:5])}")
    print(f"compose tokens in/out: {client.input_tokens}/{client.output_tokens}; "
          f"decomp+faithfulness Haiku calls: {checker.calls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
