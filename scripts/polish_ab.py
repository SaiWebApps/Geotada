"""Multi-model POLISH A/B: compose ONE stop with Claude (the flow+escalation prompt),
then have a SECOND model rewrite it for flow/escalation while keeping every fact — so
you can judge whether a ChatGPT/Gemini editor pass beats Claude alone. Cheap (~$0.15),
one stop, hard output-bounded. NO graph writes.

Reports, per version, a fact-retention check: what fraction of the source's distinctive
tokens (years + multi-word proper nouns) still appear — a rough "did the polish drop a
fact?" signal (the real risk of any rewrite pass).

Gated: --live AND ONDOWAY_DEMO_APPROVE=1. Gemini runs only if `google.genai` is
installed AND GEMINI_API_KEY is set (else it's skipped with a note).

Usage: ONDOWAY_DEMO_APPROVE=1 uv run python scripts/polish_ab.py \
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
from src.tour.generation import generate
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route

load_dotenv()

_POLISH_SYSTEM = (
    "You are an expert audio walking-tour editor. Rewrite the narration below so it "
    "FLOWS and BUILDS: connect facts causally (don't list closed declaratives), weave "
    "background into the sentence it explains, and let tension rise toward a payoff near "
    "the end rather than sitting at a flat, even pitch. Warm, spoken, second person; heard "
    "once, so short varied sentences. STRICT: keep EVERY fact — every name, date, number, "
    "place, and event that appears — and ADD nothing not already present; invent no fact. "
    "Do not state the moral or over-explain why it matters. Return ONLY the rewritten "
    "narration, no preamble."
)

# distinctive source tokens = years + multi-word Capitalized proper nouns
_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_PROPER = re.compile(r"\b([A-Z][a-zà-ÿ]+(?:\s+(?:de|la|le|du|des|of|the)?\s*[A-Z][a-zà-ÿ]+)+)\b")


def _distinctive(text: str) -> set[str]:
    toks = set(_YEAR.findall(text))
    toks |= {m.strip() for m in _PROPER.findall(text)}
    return {t for t in toks if len(t) > 3}


def _retention(source_toks: set[str], out: str) -> float:
    if not source_toks:
        return 1.0
    kept = sum(1 for t in source_toks if t in out)
    return kept / len(source_toks)


def _stop_text(sents) -> str:
    return " ".join(s.text for s in sents)


def _chatgpt_polish(text: str) -> str:
    from openai import OpenAI

    client = OpenAI()
    r = client.chat.completions.create(
        model=os.getenv("OPENAI_COMPOSE_MODEL", "gpt-4o"),
        messages=[{"role": "system", "content": _POLISH_SYSTEM}, {"role": "user", "content": text}],
        max_tokens=1200,
    )
    return r.choices[0].message.content or ""


def _gemini_polish(text: str) -> str | None:
    if not os.getenv("GEMINI_API_KEY"):
        return None
    try:
        from google import genai
    except Exception:
        return None
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    r = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=f"{_POLISH_SYSTEM}\n\n---\n{text}",
    )
    return getattr(r, "text", None)


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
    stop_sents = [s for s in stitched.script if s.stop_idx == target]
    mini = stitched.model_copy(update={"script": tuple(stop_sents)})
    stop_beats = {s.source_id: beats_by_id[s.source_id] for s in stop_sents
                  if s.source_type == "beat" and s.source_id in beats_by_id}
    request = ComposeRequest(stitched=mini, beats_by_id=stop_beats,
                             duplicate_pairs=candidate_duplicate_pairs(mini),
                             tour_context=tuple(p.name for p in route.pois))
    source_toks = _distinctive(_stop_text(stop_sents))

    print(f"A/B stop: {route.pois[target].name} ({len(stop_beats)} beats, "
          f"{len(source_toks)} distinctive source tokens)")
    if not args.live:
        print("[DRY RUN] --live + ONDOWAY_DEMO_APPROVE=1 to spend (~$0.15).")
        return 0
    if os.getenv("ONDOWAY_DEMO_APPROVE") != "1":
        print("REFUSED: --live needs ONDOWAY_DEMO_APPROVE=1.", file=sys.stderr)
        return 3

    from src.tour.compose import AnthropicComposeClient

    base = _stop_text(AnthropicComposeClient().compose(request, 1, None))
    versions = [("Claude (flow+escalation)", base)]
    versions.append(("Claude -> ChatGPT polish", _chatgpt_polish(base)))
    gem = _gemini_polish(base)
    versions.append(("Claude -> Gemini polish", gem if gem else "[SKIPPED: set GEMINI_API_KEY + `uv add google-genai`]"))

    for name, txt in versions:
        ret = _retention(source_toks, txt) if txt and not txt.startswith("[SKIPPED") else None
        tag = f"  (facts kept: {ret*100:.0f}%)" if ret is not None else ""
        print(f"\n{'='*72}\n{name}{tag}\n{'='*72}\n{txt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
