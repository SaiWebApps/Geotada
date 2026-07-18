"""FULL-TOUR side-by-side: compose (fuse the stitched beats, fact-gated) vs the author
engine (plan -> write fresh from the facts) for EVERY stop. Shows both per stop with
facts-kept + craft_score, so the architecture tradeoff is visible across a whole walk.
Live, output-bounded. NO graph writes.

Gated: --live AND ONDOWAY_DEMO_APPROVE=1.

Usage: ONDOWAY_DEMO_APPROVE=1 uv run python scripts/tour_ab.py \
    --city paris --start 48.852966,2.349902 --duration 45 --lenses dark_history \
    --core-seconds 90 --live
"""

from __future__ import annotations

import argparse
import os
import re
import sys

from dotenv import load_dotenv

import src.tour.compose as C
from src.connection import create_driver
from src.tour.beat_select import select_poi_beats
from src.tour.compose import compose_script_per_chapter
from src.tour.compose_gate import ComposeVerificationError
from src.tour.content_budget import partition_poi_content
from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import generate, split_sentences
from src.tour.narration_quality import craft_score
from src.tour.render_md import stop_narration_text
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route

load_dotenv()

_AUTHOR_SYSTEM = (
    "You are a master audio walking-tour writer. Write ONE dwell-stop of narration for a "
    "walker standing at {poi} ({lens} lens).\n"
    "First, silently PLAN the arc: choose the strongest hook to open on, and order the "
    "material so tension BUILDS to a payoff late, not buried in the middle.\n"
    "Then WRITE flowing spoken prose: open on a MOMENT (never a label/date); CONNECT facts "
    "causally, each sentence handing off to the next (never a list of closed declaratives); "
    "vary rhythm HARD (a sentence under 8 words AND a longer line; never 3 of the same shape "
    "in a row); SAY EACH FACT ONCE; render dark material plainly, then move on. ~150 words, "
    "second person, warm, heard once.\n"
    "STRICT GROUNDING: use ONLY the facts below; invent nothing; keep every fact. Return "
    "ONLY the narration."
)

_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_PROPER = re.compile(r"\b([A-Z][a-zà-ÿ]+(?:\s+(?:de|la|le|du|des|of|the)?\s*[A-Z][a-zà-ÿ]+)+)\b")


def _distinctive(text: str) -> set[str]:
    return {t for t in (set(_YEAR.findall(text)) | {m.strip() for m in _PROPER.findall(text)})
            if len(t) > 3}


def _retention(source: set[str], out: str) -> float:
    return 1.0 if not source else sum(1 for t in source if t in out) / len(source)


def _facts_for(stop_idx, stitched, beats_by_id) -> list[str]:
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
    return facts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--duration", type=int, default=45)
    ap.add_argument("--lenses", default="")
    ap.add_argument("--core-seconds", type=int, default=90)
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    C.COMPOSE_MAX_OUTPUT_TOKENS = 12000

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
    poi_names = {i: p.name for i, p in enumerate(route.pois)}

    print(f"{args.city.upper()} — {len(route.pois)} stops, {args.duration}min, {lenses or 'no lens'}")
    if not args.live:
        print("[DRY RUN] --live + ONDOWAY_DEMO_APPROVE=1 to spend (~$4, output-bounded).")
        return 0
    if os.getenv("ONDOWAY_DEMO_APPROVE") != "1":
        print("REFUSED: --live needs ONDOWAY_DEMO_APPROVE=1.", file=sys.stderr)
        return 3

    import anthropic

    from src.tour.compose import COMPOSE_MODEL, AnthropicComposeClient
    from src.tour.verify import HaikuFaithfulnessChecker

    # A — the fact-gated compose (whole tour)
    try:
        composed = compose_script_per_chapter(
            stitched, seq, route, client=AnthropicComposeClient(),
            faithfulness_checker=HaikuFaithfulnessChecker(), candidates=1,
        )
    except ComposeVerificationError as exc:
        print(f"compose refused: {exc.report}", file=sys.stderr)
        return 4
    compose_by_stop = stop_narration_text(composed)

    # B — the author engine, per stop
    raw = anthropic.Anthropic()
    for stop_idx in sorted(poi_names):
        poi = poi_names[stop_idx]
        facts = _facts_for(stop_idx, stitched, beats_by_id)
        src_toks = _distinctive(" ".join(
            s.text for s in stitched.script if s.stop_idx == stop_idx and s.source_type == "beat"))
        resp = raw.messages.create(
            model=COMPOSE_MODEL, max_tokens=2000, thinking={"type": "adaptive"},
            system=_AUTHOR_SYSTEM.format(poi=poi, lens=(lenses[0] if lenses else "general")),
            messages=[{"role": "user", "content": "FACTS:\n- " + "\n- ".join(facts)}],
        )
        author = next((b.text for b in resp.content if b.type == "text"), "")
        a = compose_by_stop.get(stop_idx, "")
        print(f"\n{'#'*74}\nSTOP {stop_idx} — {poi}\n{'#'*74}")
        print(f"\n--- A · COMPOSE  (facts {_retention(src_toks, a)*100:.0f}%, "
              f"craft {craft_score(a):.2f}) ---\n{a}")
        print(f"\n--- B · AUTHOR ENGINE  (facts {_retention(src_toks, author)*100:.0f}%, "
              f"craft {craft_score(author):.2f}) ---\n{author}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
