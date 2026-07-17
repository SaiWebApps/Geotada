"""The content-budget partition (src/tour/content_budget.py) — a pure, offline classifier
that sorts a POI's beats into core/walk-away/callback/optional/cut. $0, no LLM, no graph.

The invariants that matter: the partition is TOTAL and DISJOINT (no beat lost, none in two
tiers), the CUT detector fires only on real ledger/number DUMPS (not date-dense narrative),
CORE respects its budget and always speaks, and walk-away is bounded by the leg.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.tour.content_budget import (
    is_ledger_beat,
    leg_word_budget,
    partition_poi_content,
)
from src.tour.contract import BeatRef, POIBeats

_DATA = Path(__file__).resolve().parent.parent / "data"


def _beat(bid: str, body: str, *, secs: int = 30, btype: str | None = None,
          nf: str | None = None) -> BeatRef:
    return BeatRef.model_construct(
        id=bid, poi_id="p", script_body=body, word_count=len(body.split()),
        est_spoken_seconds=secs, beat_type=btype, narrative_function=nf, key_claims=(),
    )


def _plan(*beats: BeatRef) -> POIBeats:
    return POIBeats(poi_id="p", poi_name="P", ordering_strategy="narrative_function",
                    beats=tuple(beats))


# ---- CUT detector: fires on real dumps, NOT on date-dense narrative ----

def test_ledger_detector_flags_a_real_currency_dump():
    """The Conciergerie tariff — a currency DUMP that does not survive one listen."""
    assert is_ledger_beat(_beat("t", (
        "Even during the Terror, the Conciergerie ran a tariff. A wealthy prisoner could "
        "rent a bed for 27 livres 12 sous the first month, 22 livres 10 sous after that, "
        "eventually dropped to 15."
    )))


def test_ledger_detector_flags_a_measurement_stack():
    assert is_ledger_beat(_beat("m",
        "Each anchorage measures 237 feet long, 182 feet wide, and 135 feet tall."))


def test_ledger_detector_does_not_flag_date_dense_narrative():
    """The forecaster's finding: years/dates are NARRATIVE anchors, never ledger tokens.
    A single meaningful number never fires. UNDO: count years as ledger tokens -> these
    flag -> RED (over-cutting real story)."""
    for body in [
        "Delacroix lived at number 13 between 1829 and 1835, in a studio off the quai.",
        "The spire collapsed in a great storm in 1860.",
        "In 2018 the Louvre set a record: 10.2 million visitors in one year.",
    ]:
        assert not is_ledger_beat(_beat("x", body)), body


# ---- partition: total, disjoint, budgeted ----

def test_partition_is_total_and_disjoint():
    beats = [_beat(f"b{i}", "A grounded story sentence about the place and its people.",
                   secs=40) for i in range(8)]
    plan = _plan(*beats)
    cb = partition_poi_content(plan, core_seconds_budget=90, leg_walk_seconds=120)
    ids = list(cb.all_ids())
    assert sorted(ids) == sorted(b.id for b in beats)  # TOTAL: every beat placed
    assert len(ids) == len(set(ids))  # DISJOINT: none in two tiers


def test_core_respects_budget_but_always_speaks():
    """CORE holds the ordered prefix within the seconds budget; the first non-cut beat is
    always kept even if it alone exceeds the budget (a stop must speak)."""
    beats = [_beat("big", "One long opening story.", secs=200),
             _beat("b2", "A second story.", secs=60)]
    cb = partition_poi_content(_plan(*beats), core_seconds_budget=90, leg_walk_seconds=0)
    assert cb.core_ids == ("big",)  # first kept despite overshoot
    assert "b2" in cb.optional_ids  # the rest overflows (no leg budget)


def test_walkaway_is_bounded_by_the_leg():
    beats = [_beat("core", "Opener.", secs=80)] + [
        _beat(f"o{i}", "Overflow story.", secs=60) for i in range(6)]
    short = partition_poi_content(_plan(*beats), core_seconds_budget=90, leg_walk_seconds=60)
    long = partition_poi_content(_plan(*beats), core_seconds_budget=90, leg_walk_seconds=300)
    assert len(long.walkaway_ids) > len(short.walkaway_ids)  # longer leg admits more
    assert len(short.walkaway_ids) <= 1  # a 60s leg holds ~one 60s beat


def test_leg_word_budget_matches_voicemap_formula():
    assert leg_word_budget(120) == 300  # 120s * 150wpm / 60 = 300 words


# ---- real-corpus invariants (no compose, $0) ----

def test_partition_is_total_over_the_real_paris_corpus():
    """Run the partition over EVERY real Paris POI and assert it never loses or
    double-counts a beat — the property the report depends on."""
    from collections import defaultdict

    by_poi: dict[str, list[BeatRef]] = defaultdict(list)
    for d in json.loads((_DATA / "paris" / "beats.json").read_text()):
        body = d.get("script_body") or ""
        by_poi[d.get("poi_name", "")].append(BeatRef.model_construct(
            id=d.get("beat_id", ""), poi_id=d.get("poi_name", ""), script_body=body,
            word_count=len(body.split()), est_spoken_seconds=d.get("est_spoken_seconds") or 0,
            beat_type=d.get("beat_type"), narrative_function=d.get("narrative_function"),
            key_claims=(),
        ))
    for poi, beats in by_poi.items():
        cb = partition_poi_content(_plan(*beats), core_seconds_budget=90, leg_walk_seconds=120)
        placed = list(cb.all_ids())
        assert sorted(placed) == sorted(b.id for b in beats), poi  # total
        assert len(placed) == len(set(placed)), poi  # disjoint
