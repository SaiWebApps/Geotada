"""LIVE proof of the AUTHOR ENGINE end-to-end: for each stop, write fresh from the facts,
then the semantic fact-check-and-repair loop restores dropped facts / strips invented ones.
Shows each stop's final narration + convergence (attempts, fell-back?) + the fact-check
verdict (should be clean) + an independent facts-kept %, so we can compare against the
author-ONLY run that dropped facts (Palais 44%, Notre-Dame 50%). Output-bounded. NO graph
writes.

Gated: --live AND ONDOWAY_DEMO_APPROVE=1.

Usage: ONDOWAY_DEMO_APPROVE=1 uv run python scripts/author_tour.py \
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
from src.tour.content_budget import partition_poi_content
from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import generate, split_sentences
from src.tour.narration_quality import craft_score
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route

load_dotenv()

_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_PROPER = re.compile(r"\b([A-Z][a-zà-ÿ]+(?:\s+(?:de|la|le|du|des|of|the)?\s*[A-Z][a-zà-ÿ]+)+)\b")


def _distinctive(text: str) -> set[str]:
    return {t for t in (set(_YEAR.findall(text)) | {m.strip() for m in _PROPER.findall(text)})
            if len(t) > 3}


def _retention(source: set[str], out: str) -> float:
    return 1.0 if not source else sum(1 for t in source if t in out) / len(source)


def _wide_facts(plan, wide_budget: int, narrow: tuple[str, ...]) -> tuple[str, ...] | None:
    """Widen-retry fact window: re-partition the PRE-CAP plan at ``wide_budget`` and
    re-derive facts from the wider core's key_claims (same derivation as ``_facts_for``).
    Returns None unless the wider set adds >= 2 facts absent from the narrow set — the
    money guard: identical facts would fail identically, so nothing is spent."""
    from src.tour.content_budget import partition_poi_content

    cb = partition_poi_content(plan, core_seconds_budget=wide_budget)
    core_ids = set(cb.core_ids)
    facts, seen = [], set()
    for b in plan.beats:
        if b.id not in core_ids:
            continue
        for it in list(b.key_claims) or [p.strip() for p in split_sentences(b.script_body or "")]:
            if it and it not in seen:
                seen.add(it)
                facts.append(it)
    new = [f for f in facts if f not in set(narrow)]
    return tuple(facts) if len(new) >= 2 else None


def _corpus_facts_for(
    poi, snap, route, lenses: list[str], narrow: tuple[str, ...], cap: int = 40
) -> tuple[str, ...]:
    """FULL-CORPUS fact list for one POI: every ACTIVE beat (``select_poi_beats_full``,
    apply_cap=False) — NOT ``plans[i]`` (built by plain ``select_poi_beats``, which already
    applies the per-tier R1 ceiling) and NOT the further core-seconds-budget cap applied
    into ``capped``. This is the FULL-CORPUS RECHECK primitive (Phase-C tour-killer fix):
    a claim tier-capped OR budget-capped out of the tour window can still be grounded here.

    Seeded with ``narrow`` (this stop's tour-window facts) FIRST, so ``corpus ⊇ narrow``
    holds BY CONSTRUCTION: ``select_poi_beats_full``'s own docstring says the capped plan is
    a prefix for the flat strategy but a SCORE-SELECTED SUBSET for the spatial strategies, so
    under a spatial strategy a narrow-window beat can sit past index ``cap`` in the full plan
    and get truncated out of the recheck corpus otherwise — a conservative failure (a
    rescuable claim fails to rescue) but a real yield loss the seeding removes for free.

    Capped to ``cap`` facts (JUDGE DILUTION mitigation, forecast risk #1): the faithfulness
    judge was calibrated on tour-window-sized fact lists (~28 items); an unbounded full-POI
    corpus is 3-10x larger and risks diluting the judge's attention. The cap floats up to
    ``len(narrow)`` if the narrow window alone exceeds it, so seeding never truncates the
    very facts it exists to guarantee. Reads the ALREADY-LOADED snapshot/route — no extra DB
    round-trip, no spend."""
    from src.tour.beat_select import select_poi_beats_full

    raw_beats = list(snap.beats_for(poi.id)) + list(route.demoted_beats.get(poi.id, ()))
    full = select_poi_beats_full(poi, raw_beats, interest_lenses=lenses)
    facts: list[str] = list(dict.fromkeys(narrow))  # seed FIRST, de-duped, order-preserved
    seen: set[str] = set(facts)
    effective_cap = max(cap, len(facts))
    for b in full.beats:
        for it in (list(b.key_claims) or [p.strip() for p in split_sentences(b.script_body or "")]):
            if it and it not in seen:
                seen.add(it)
                facts.append(it)
                if len(facts) >= effective_cap:
                    return tuple(facts)
    return tuple(facts)


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
    ap.add_argument("--stop", default="", help="if set, only this POI (substring) — cheap validation")
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
    lens = lenses[0] if lenses else "general"

    print(f"{args.city.upper()} — {len(route.pois)} stops, {args.duration}min, {lenses or 'none'}")
    if not args.live:
        print("[DRY RUN] --live + ONDOWAY_DEMO_APPROVE=1 to spend (~$2, output-bounded).")
        return 0
    if os.getenv("ONDOWAY_DEMO_APPROVE") != "1":
        print("REFUSED: --live needs ONDOWAY_DEMO_APPROVE=1.", file=sys.stderr)
        return 3

    from src.tour.author import LLMDrafter, author_compose_stop
    from src.tour.compose import COMPOSE_MODEL
    from src.tour.factcheck import (
        HaikuClaimDecomposer,
        HaikuCoverageJudge,
        HaikuFaithfulnessJudge,
        SemanticFactChecker,
    )

    drafter = LLMDrafter(COMPOSE_MODEL)
    checker = SemanticFactChecker(
        entailer=HaikuFaithfulnessJudge(),  # calibrated faithfulness (accepts recombination)
        decomposer=HaikuClaimDecomposer(),
        coverage_judge=HaikuCoverageJudge(),
    )

    for stop_idx, poi in enumerate(route.pois):
        if args.stop and args.stop.lower() not in poi.name.lower():
            continue
        facts = tuple(_facts_for(stop_idx, stitched, beats_by_id))
        stitch = " ".join(
            s.text for s in stitched.script if s.stop_idx == stop_idx and s.source_type == "beat")
        src_toks = _distinctive(stitch)
        trace: list = []
        res = author_compose_stop(facts, poi.name, lens, drafter=drafter, checker=checker,
                                  stitch_fallback=stitch, max_repairs=3, trace=trace,
                                  widen=lambda i=stop_idx, f=facts: _wide_facts(
                                      plans[i], args.core_seconds * 2, f),
                                  corpus_facts=lambda p=poi, f=facts: _corpus_facts_for(
                                      p, snap, route, ti.lenses, f),
                                  excise=True)
        if res.widened:
            print("  [widen retry] narrow loop failed; wider fact window converged")
        if res.rescued:
            print(f"  [corpus rescue] {len(res.rescued)} claim(s) grounded in the POI corpus "
                  "outside the fact window:")
            for c in res.rescued:
                print(f"       RESCUED: {c}")
        if res.excised:
            print(f"  [excision] dropped {len(res.excised)} sentence(s) carrying a true "
                  "invention; kept the rest of the authored prose:")
            for e in res.excised:
                print(f"       EXCISED: {e}")
        if res.grounded_fallback and res.rescued_not_served:
            print(f"  [PARTIAL RESCUE, STILL FELL BACK] the corpus grounded "
                  f"{len(res.rescued_not_served)} claim(s) below, but the stop still fell "
                  "back to the stitch (the residual invention could not be safely excised):")
            for c in res.rescued_not_served:
                print(f"       RESCUED-BUT-DROPPED: {c}")
        tag = "GROUNDED-STITCH FALLBACK" if res.grounded_fallback else f"converged in {res.attempts}"
        print(f"\n{'#'*74}\nSTOP {stop_idx} — {poi.name}  [{tag}]")
        print(f"  facts kept: {_retention(src_toks, res.text)*100:.0f}%  |  "
              f"craft {craft_score(res.text):.2f}  |  "
              f"fact-check: {len(res.result.unsupported_claims)} unsupported, "
              f"{len(res.result.missing_facts)} missing")
        # Convergence trajectory — WHY the author draft passed/failed at each attempt.
        for i, (draft, verdict) in enumerate(trace):
            print(f"  -- author attempt {i}: {len(verdict.unsupported_claims)} unsupported, "
                  f"{len(verdict.missing_facts)} missing  ({len(draft)} chars) --")
            for c in verdict.unsupported_claims:
                print(f"       UNSUPPORTED: {c}")
            for m in verdict.missing_facts:
                print(f"       MISSING: {m}")
            print(f"       DRAFT: {draft[:400]}{'...' if len(draft) > 400 else ''}")
        if res.grounded_fallback:
            print("\n  [author never reached 0/0 — served grounded stitch]")
        print(f"{'#'*74}\n{res.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
