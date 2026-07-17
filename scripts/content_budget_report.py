"""$0 OFFLINE report: partition every POI's beats into content tiers over the REAL
corpus (data/{city}/beats.json) and print the split — the empirical answer to
"is a dense stop's overflow cut, or relocatable?".

No graph, no LLM, no network. Reads the committed beats.json, approximates the
cold-open -> body -> closer ordering by narrative_function, partitions with
`partition_poi_content`, and reports per-dense-POI + corpus-wide the share of
OVERFLOW words that go to each tier (CORE stays; the rest is CUT / WALK-AWAY /
CALLBACK / OPTIONAL).

Usage: uv run python scripts/content_budget_report.py [--city paris] [--core-seconds 90]
       [--leg-seconds 120] [--top 12]
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from src.tour.content_budget import is_ledger_beat, partition_poi_content
from src.tour.contract import POIBeats
from src.tour.contract import BeatRef as BR
from src.tour.routing import beat_spoken_seconds

# Approximate the emitted arc: openers first, body, then closers/threads.
_NF_RANK = {
    "establishing": 0, "scene_setter": 1, "hook": 2,
    "climax": 3, "deepen": 4, "factoid": 5,
    "callback": 6, "transition": 7, None: 8,
}


def _beat(d: dict) -> BR:
    body = d.get("script_body") or ""
    return BR.model_construct(
        id=d.get("beat_id", ""),
        poi_id=d.get("poi_name", ""),  # beats.json keys the POI by name, not id
        script_body=body,
        word_count=len(body.split()),  # no word_count field in beats.json — derive it
        est_spoken_seconds=d.get("est_spoken_seconds") or 0,
        beat_type=d.get("beat_type"),
        narrative_function=d.get("narrative_function"),
        key_claims=tuple(d.get("key_claims") or ()),
    )


def _words(beat: BR) -> int:
    return beat.word_count or len((beat.script_body or "").split())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="paris")
    ap.add_argument("--core-seconds", type=int, default=90)  # ~225 words, between the 2- and 5-min caps
    ap.add_argument("--leg-seconds", type=int, default=120)  # a representative ~2-min walk-away leg
    ap.add_argument("--top", type=int, default=12)
    args = ap.parse_args()

    beats = json.loads(Path(f"data/{args.city}/beats.json").read_text())
    by_poi: dict[str, list[BR]] = defaultdict(list)
    for d in beats:
        by_poi[d.get("poi_name", "")].append(_beat(d))

    tier_words = defaultdict(int)   # tier -> total words across all POIs
    tier_beats = defaultdict(int)
    overflow_words = 0             # words in any tier other than CORE
    per_poi_rows = []
    for poi_id, bs in by_poi.items():
        bs = sorted(bs, key=lambda b: (_NF_RANK.get(b.narrative_function, 8), b.id))
        plan = POIBeats(poi_id=poi_id, poi_name=poi_id, ordering_strategy="narrative_function",
                        beats=tuple(bs))
        cb = partition_poi_content(plan, core_seconds_budget=args.core_seconds,
                                   leg_walk_seconds=args.leg_seconds)
        wmap = {b.id: _words(b) for b in bs}
        tiers = {"CORE": cb.core_ids, "WALK-AWAY": cb.walkaway_ids, "CALLBACK": cb.callback_ids,
                 "OPTIONAL": cb.optional_ids, "CUT": cb.cut_ids}
        for t, ids in tiers.items():
            w = sum(wmap[i] for i in ids)
            tier_words[t] += w
            tier_beats[t] += len(ids)
            if t != "CORE":
                overflow_words += w
        total_secs = sum(beat_spoken_seconds(b) for b in bs)
        if len(bs) > len(cb.core_ids):  # this POI overflows the core
            per_poi_rows.append((poi_id, len(bs), sum(wmap.values()), total_secs, cb, wmap))

    per_poi_rows.sort(key=lambda r: r[2], reverse=True)
    print(f"\n{'='*72}\n{args.city.upper()} content-budget partition  "
          f"(core={args.core_seconds}s ~{args.core_seconds*150//60}w, leg={args.leg_seconds}s)"
          f"\n{'='*72}")
    print(f"{len(by_poi)} POIs, {len(beats)} beats.  "
          f"Ledger-flagged beats (would CUT): {sum(1 for d in beats if is_ledger_beat(_beat(d)))}")

    print(f"\n--- Top {args.top} densest POIs (that overflow a {args.core_seconds}s core) ---")
    for poi_id, n, w, secs, cb, wmap in per_poi_rows[: args.top]:
        parts = [
            f"CORE {len(cb.core_ids)}", f"walk {len(cb.walkaway_ids)}",
            f"callbk {len(cb.callback_ids)}", f"tap {len(cb.optional_ids)}",
            f"CUT {len(cb.cut_ids)}",
        ]
        print(f"  {poi_id[:34]:34} {n:3} beats / {w:5}w / {secs//60}m{secs%60:02d}s  ->  "
              + "  ".join(parts))

    print(f"\n{'='*72}\nCORPUS-WIDE OVERFLOW SPLIT (the cut-vs-relocate answer)\n{'='*72}")
    print(f"CORE (stays at stop): {tier_words['CORE']:,}w in {tier_beats['CORE']} beats")
    print(f"OVERFLOW total: {overflow_words:,}w in "
          f"{sum(tier_beats[t] for t in tier_words if t!='CORE')} beats. Of that overflow:")
    for t in ("CUT", "OPTIONAL", "WALK-AWAY", "CALLBACK"):
        pct = 100.0 * tier_words[t] / overflow_words if overflow_words else 0.0
        print(f"  {t:10}: {pct:5.1f}%  ({tier_words[t]:,}w, {tier_beats[t]} beats)")
    print("\nReading: CUT = clear ledger/number-dumps that don't survive one listen; "
          "OPTIONAL = opt-in 'tap for more' (already built); WALK-AWAY/CALLBACK = the two "
          "bounded relocation channels the research endorses (STORY on the leg / a thread).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
