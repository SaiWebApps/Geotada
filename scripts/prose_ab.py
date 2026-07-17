"""Cheap single-stop A/B for the STILTED-PROSE / transitions problem: recompose ONE stop
with the current prompt vs a FLOW-fixed prompt, so we can SEE whether the fix helps on
the exact stop the user flagged — ~2 Opus calls (~$0.20), hard output-bounded. Same
in-memory decomposition + core cap as demo_full_tour; NO graph writes.

Gated: --live AND ONDOWAY_DEMO_APPROVE=1, else it prints the plan only ($0).

Usage: ONDOWAY_DEMO_APPROVE=1 uv run python scripts/prose_ab.py \
    --city paris --start 48.852966,2.349902 --duration 45 --lenses dark_history \
    --core-seconds 90 --stop "Palais" --live
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

import src.tour.compose as C
from src.connection import create_driver
from src.tour.beat_select import select_poi_beats
from src.tour.claim_dedup import candidate_duplicate_pairs
from src.tour.compose import ComposeRequest
from src.tour.content_budget import partition_poi_content
from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import generate
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route

load_dotenv()

# The FLOW fix: connect facts causally instead of listing closed declaratives.
_FLOW_BLOCK = """

MAKE IT FLOW — connect, don't list. A stop is ONE story, not a row of facts. Each
sentence hands off to the next: state a fact, then let its consequence, or the question
it raises, pull the listener forward. WEAVE background INTO the sentence it explains —
never drop it as its own closed statement ("Jean was captive in England." "Marcel wanted
power." -> "With the king held captive in England, the throne stood weak — and that was
the opening Marcel saw."). Prefer causal and temporal joins (so, which is why, by then,
and that is when) over a full stop between two related facts. Vary the cadence: a longer
sentence that carries the story, then a short one that lands the point — never a run of
equal, closed declaratives. This OVERRIDES "one idea per sentence" when the ideas are
causally linked; keep each sentence sayable in one breath, but let it carry a linked
cause and effect rather than a bare fact."""


def _stop_text(sents) -> str:
    return " ".join(s.text for s in sents)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--duration", type=int, default=45)
    ap.add_argument("--lenses", default="")
    ap.add_argument("--core-seconds", type=int, default=90)
    ap.add_argument("--stop", required=True, help="substring of the POI name to A/B")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    C.COMPOSE_MAX_OUTPUT_TOKENS = 12000  # hard per-call bound

    lat, lng = (float(x) for x in args.start.split(","))
    lenses = [x for x in args.lenses.split(",") if x]
    ti = TourInput(start=(lat, lng), duration_min=args.duration, city_slug=args.city, lenses=lenses)
    driver = create_driver()
    try:
        snap = load_paris_corpus(driver, city_slug=args.city)
    finally:
        driver.close()
    with RoutingClient() as rc:
        route = select_route(ti, snap, routing_client=rc)
    plans = []
    for poi in route.pois:
        beats = list(snap.beats_for(poi.id)) + list(route.demoted_beats.get(poi.id, ()))
        plans.append(select_poi_beats(poi, beats, interest_lenses=ti.lenses))
    # core cap
    capped = []
    for pb in plans:
        cb = partition_poi_content(pb, core_seconds_budget=args.core_seconds)
        core = tuple(b for b in pb.beats if b.id in set(cb.core_ids))
        capped.append(pb.model_copy(update={"beats": core or pb.beats[:1]}))
    seq = BeatSequence(poi_beats=tuple(capped))
    stitched = generate(seq, route, ti)

    # locate the target stop
    beats_by_id = {b.id: b for pb in seq.poi_beats for b in pb.beats}
    target = None
    for i, poi in enumerate(route.pois):
        if args.stop.lower() in poi.name.lower():
            target = i
            break
    if target is None:
        print(f"stop matching {args.stop!r} not found in {[p.name for p in route.pois]}", file=sys.stderr)
        return 2
    tour_context = tuple(p.name for p in route.pois)
    stop_sents = [s for s in stitched.script if s.stop_idx == target]
    mini = stitched.model_copy(update={"script": tuple(stop_sents)})
    stop_beats = {s.source_id: beats_by_id[s.source_id] for s in stop_sents
                  if s.source_type == "beat" and s.source_id in beats_by_id}
    request = ComposeRequest(stitched=mini, beats_by_id=stop_beats,
                             duplicate_pairs=candidate_duplicate_pairs(mini), tour_context=tour_context)

    print(f"A/B stop: {route.pois[target].name} ({len(stop_beats)} beats)")
    if not args.live:
        print("[DRY RUN] --live + ONDOWAY_DEMO_APPROVE=1 to spend (~2 Opus calls, ~$0.20).")
        return 0
    if os.getenv("ONDOWAY_DEMO_APPROVE") != "1":
        print("REFUSED: --live needs ONDOWAY_DEMO_APPROVE=1.", file=sys.stderr)
        return 3

    from src.tour.compose import AnthropicComposeClient
    client = AnthropicComposeClient()
    a = client.compose(request, 1, None)  # CURRENT prompt
    orig = C._COMPOSE_SYSTEM
    C._COMPOSE_SYSTEM = orig + _FLOW_BLOCK  # + FLOW fix
    try:
        b = client.compose(request, 1, None)
    finally:
        C._COMPOSE_SYSTEM = orig

    print(f"\n{'='*72}\nA — CURRENT prompt (the stilted version)\n{'='*72}\n{_stop_text(a)}")
    print(f"\n{'='*72}\nB — with the FLOW fix\n{'='*72}\n{_stop_text(b)}")
    print(f"\ntokens in/out: {client.input_tokens}/{client.output_tokens}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
