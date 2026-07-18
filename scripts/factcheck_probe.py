"""Cheap ($0.04) calibration probe for the SemanticFactChecker: run it on one real stop's
GROUNDED STITCH (control — expect near-empty: the stitch is fact-complete + corpus-verbatim)
and on the same stitch with one fact-bearing sentence REMOVED (expect that fact flagged
missing). Prints the DETAILED verdicts so we can see whether it false-flags or catches real
drops. NO graph writes. Gated: --live + ONDOWAY_DEMO_APPROVE=1.

Usage: ONDOWAY_DEMO_APPROVE=1 uv run python scripts/factcheck_probe.py \
    --city paris --start 48.852966,2.349902 --duration 45 --lenses dark_history \
    --core-seconds 90 --stop Palais --live
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from src.connection import create_driver
from src.tour.beat_select import select_poi_beats
from src.tour.content_budget import partition_poi_content
from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import generate, split_sentences
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route


def _facts_for(stop_idx, stitched, beats_by_id):
    facts, seen = [], set()
    for s in stitched.script:
        if s.stop_idx != stop_idx or s.source_type != "beat":
            continue
        b = beats_by_id.get(s.source_id)
        if not b:
            continue
        for it in (list(b.key_claims) or [p.strip() for p in split_sentences(b.script_body or "")]):
            if it and it not in seen:
                seen.add(it)
                facts.append(it)
    return tuple(facts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--duration", type=int, default=45)
    ap.add_argument("--lenses", default="")
    ap.add_argument("--core-seconds", type=int, default=90)
    ap.add_argument("--stop", required=True)
    ap.add_argument("--text", default="", help="check THIS narration against the stop's facts")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()

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
    capped = []
    for pb in plans:
        cb = partition_poi_content(pb, core_seconds_budget=args.core_seconds)
        core = tuple(b for b in pb.beats if b.id in set(cb.core_ids))
        capped.append(pb.model_copy(update={"beats": core or pb.beats[:1]}))
    seq = BeatSequence(poi_beats=tuple(capped))
    stitched = generate(seq, route, ti)
    beats_by_id = {b.id: b for pb in seq.poi_beats for b in pb.beats}

    target = next((i for i, p in enumerate(route.pois) if args.stop.lower() in p.name.lower()), None)
    if target is None:
        print(f"stop {args.stop!r} not in {[p.name for p in route.pois]}", file=sys.stderr)
        return 2
    facts = _facts_for(target, stitched, beats_by_id)
    beat_sents = [s.text for s in stitched.script if s.stop_idx == target and s.source_type == "beat"]
    stitch = " ".join(beat_sents)

    print(f"STOP: {route.pois[target].name}  ({len(facts)} source facts, {len(beat_sents)} stitch sentences)")
    if not args.live:
        print("[DRY RUN] --live + ONDOWAY_DEMO_APPROVE=1 to spend (~$0.04).")
        return 0
    if os.getenv("ONDOWAY_DEMO_APPROVE") != "1":
        print("REFUSED: --live needs ONDOWAY_DEMO_APPROVE=1.", file=sys.stderr)
        return 3

    from src.tour.factcheck import HaikuClaimDecomposer, SemanticFactChecker
    from src.tour.verify import HaikuFaithfulnessChecker

    checker = SemanticFactChecker(entailer=HaikuFaithfulnessChecker(), decomposer=HaikuClaimDecomposer())

    def _report(label, text):
        r = checker.check(text, facts)
        print(f"\n=== {label} ===")
        print(f"  unsupported_claims ({len(r.unsupported_claims)}):")
        for c in r.unsupported_claims:
            print(f"     - {c}")
        print(f"  missing_facts ({len(r.missing_facts)}):")
        for f in r.missing_facts:
            print(f"     - {f}")

    if args.text:
        _report("PROVIDED NARRATION (author prose)", args.text)
        return 0
    _report("CONTROL: grounded stitch (expect ~empty)", stitch)
    if len(beat_sents) >= 2:
        dropped_sent = beat_sents[len(beat_sents) // 2]
        dropped = " ".join(s for s in beat_sents if s != dropped_sent)
        print(f"\n[dropped sentence]: {dropped_sent}")
        _report("DROP: stitch minus one sentence (expect its fact flagged missing)", dropped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
