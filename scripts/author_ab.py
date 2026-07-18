"""Architecture A/B on ONE stop: the current COMPOSE (fuse the stitched beats) vs an
AUTHOR-ENGINE pass (Spec-Mirror: plan the arc, write the stop FRESH from the facts, then
fact-check). Answers "advanced author engine vs compose?" with evidence, cheaply (~$0.20,
2 Opus calls, output-bounded). NO graph writes.

Gated: --live AND ONDOWAY_DEMO_APPROVE=1.

Usage: ONDOWAY_DEMO_APPROVE=1 uv run python scripts/author_ab.py \
    --city paris --start 48.852966,2.349902 --duration 45 --lenses dark_history \
    --core-seconds 90 --stop Palais --live
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
from src.tour.claim_dedup import candidate_duplicate_pairs
from src.tour.compose import ComposeRequest
from src.tour.content_budget import partition_poi_content
from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import generate, split_sentences
from src.tour.narration_quality import craft_score
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route

load_dotenv()

_AUTHOR_SYSTEM = (
    "You are a master audio walking-tour writer. Write ONE dwell-stop of narration for a "
    "walker standing at {poi} ({lens} lens).\n"
    "First, silently PLAN the arc: choose the single strongest hook to open on, and order "
    "the material so tension BUILDS to a payoff — the worst turn or reversal comes late, "
    "not buried in the middle.\n"
    "Then WRITE it as flowing spoken prose:\n"
    "- Open on a MOMENT (a person acting, a conflict, a surprising claim) — never a label "
    "or a founding date.\n"
    "- CONNECT facts causally; each sentence hands off to the next (so, which is why, by "
    "then). Do NOT list closed declaratives.\n"
    "- Vary rhythm HARD: at least one sentence under 8 words as percussion AND one longer "
    "line; never three of the same shape in a row.\n"
    "- SAY EACH FACT ONCE. Render dark material plainly, no euphemism, then move on.\n"
    "- ~150 words, second person, warm, heard once.\n"
    "STRICT GROUNDING: use ONLY the facts below; invent nothing; keep every fact. Return "
    "ONLY the narration."
)

_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_PROPER = re.compile(r"\b([A-Z][a-zà-ÿ]+(?:\s+(?:de|la|le|du|des|of|the)?\s*[A-Z][a-zà-ÿ]+)+)\b")


def _distinctive(text: str) -> set[str]:
    toks = set(_YEAR.findall(text)) | {m.strip() for m in _PROPER.findall(text)}
    return {t for t in toks if len(t) > 3}


def _retention(source: set[str], out: str) -> float:
    return 1.0 if not source else sum(1 for t in source if t in out) / len(source)


def _stop_text(sents) -> str:
    return " ".join(s.text for s in sents)


def _facts_from(stop_sents, beats_by_id) -> list[str]:
    """The stop's grounded facts: each beat's key_claims if present, else its body
    sentences — the SPEC the author writes from."""
    facts: list[str] = []
    seen = set()
    for s in stop_sents:
        if s.source_type != "beat":
            continue
        b = beats_by_id.get(s.source_id)
        if not b:
            continue
        items = list(b.key_claims) or [p.strip() for p in split_sentences(b.script_body or "")]
        for it in items:
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
    ap.add_argument("--stop", required=True)
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

    target = next((i for i, p in enumerate(route.pois) if args.stop.lower() in p.name.lower()), None)
    if target is None:
        print(f"stop {args.stop!r} not in {[p.name for p in route.pois]}", file=sys.stderr)
        return 2
    poi_name = route.pois[target].name
    stop_sents = [s for s in stitched.script if s.stop_idx == target]
    mini = stitched.model_copy(update={"script": tuple(stop_sents)})
    stop_beats = {s.source_id: beats_by_id[s.source_id] for s in stop_sents
                  if s.source_type == "beat" and s.source_id in beats_by_id}
    request = ComposeRequest(stitched=mini, beats_by_id=stop_beats,
                             duplicate_pairs=candidate_duplicate_pairs(mini),
                             tour_context=tuple(p.name for p in route.pois))
    facts = _facts_from(stop_sents, beats_by_id)
    source_toks = _distinctive(_stop_text(stop_sents))

    print(f"A/B stop: {poi_name} ({len(stop_beats)} beats, {len(facts)} facts)")
    if not args.live:
        print("[DRY RUN] --live + ONDOWAY_DEMO_APPROVE=1 to spend (~$0.20).")
        return 0
    if os.getenv("ONDOWAY_DEMO_APPROVE") != "1":
        print("REFUSED: --live needs ONDOWAY_DEMO_APPROVE=1.", file=sys.stderr)
        return 3

    import anthropic

    from src.tour.compose import COMPOSE_MODEL, AnthropicComposeClient

    a = _stop_text(AnthropicComposeClient().compose(request, 1, None))  # A: fuse-beats compose

    raw = anthropic.Anthropic()
    sys_prompt = _AUTHOR_SYSTEM.format(poi=poi_name, lens=(lenses[0] if lenses else "general"))
    resp = raw.messages.create(
        model=COMPOSE_MODEL, max_tokens=2000, thinking={"type": "adaptive"},
        system=sys_prompt,
        messages=[{"role": "user", "content": "FACTS:\n- " + "\n- ".join(facts)}],
    )
    b = next((blk.text for blk in resp.content if blk.type == "text"), "")

    for name, txt in [("A — COMPOSE (fuse the stitched beats)", a),
                      ("B — AUTHOR ENGINE (plan -> write fresh from facts -> fact-check)", b)]:
        print(f"\n{'='*72}\n{name}\n  facts kept: {_retention(source_toks, txt)*100:.0f}%"
              f"  |  craft_score: {craft_score(txt):.2f}\n{'='*72}\n{txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
