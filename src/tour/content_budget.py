"""Content budget — a PURE, offline classifier that partitions a POI's beats by WHERE
each is best heard: CORE (at the stop), WALK-AWAY (the following leg), CALLBACK (a later
thin stop), OPTIONAL (tap-for-more), or CUT (does not survive one listen).

This exists to MEASURE the cut-vs-relocate question on the real corpus, not to change
emitted tours. The research (specs/2026-07-16-tour-craft/CONTENT-REDISTRIBUTION.md) is
blunt: pros overwhelmingly CUT overflow rather than relocate it, and no source names
moving raw FACTS between stops. Two bounded channels survive because a GPS tour can't
delete a stop the tourist stands at: a bounded amount of STORY rides the walk-away, and
a narrative REFERENCE seeds a callback. Everything else is CUT (ledgers/dumps) or parked
in the opt-in tap. This module classifies; a later, money-gated slice would compose.

Pure: no I/O, no LLM, no network. Deterministic. Beat-seconds via the engine's single
source of truth (``routing.beat_spoken_seconds``) so it speaks the same audio-clock units
as selection/generation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .contract import BeatRef, POIBeats
from .routing import beat_spoken_seconds

# --- CUT detector: "does not survive one listen" (currency/price DUMP or measure STACK) ---
# Deliberately CONSERVATIVE — high precision, low recall. Years/dates are NARRATIVE
# anchors ("built in 1163", "between 1829 and 1835") and are NEVER counted; a single
# meaningful number never fires. A beat is flagged only on a clear MULTI-token dump — the
# Conciergerie tariff ("27 livres 12 sous … 22 livres 10 sous"), a spec stack ("237 feet
# long, 182 feet wide, 135 feet tall"), a statistics pile ("10 million bricks, 60,000 tons
# of steel, 6400 windows"). The design bias is to DEMOTE-to-tap, not cut, so a beat whose
# one great fact is a number survives (design risk #7).
_LEDGER_CURRENCY = re.compile(
    r"\b\d[\d,]*\s*(?:livres?|sous|crowns?|pounds?|francs?|écus|shillings?|pence)\b"
    r"|[£$€]\s?\d",
    re.IGNORECASE,
)
_LEDGER_MEASURE = re.compile(
    r"\b\d[\d,]*[\s-]?(?:foot|feet|metres?|meters?|tonnes?|tons?|acres?|inches|yards?)\b",
    re.IGNORECASE,
)
_LEDGER_CURRENCY_MIN = 3
_LEDGER_MEASURE_MIN = 3

# A callback moves a narrative THREAD, not facts — a character/anecdote reference.
_CALLBACK_TYPES = frozenset({"character_story", "anecdote"})


def is_ledger_beat(beat: BeatRef) -> bool:
    """True iff the beat is a currency/price DUMP or measurement STACK that does not
    survive one listen — a hard-CUT candidate. Conservative: dates/years never count, and
    a single number never fires (needs >= 3 currency or >= 3 measurement tokens)."""
    body = beat.script_body or ""
    return (
        len(_LEDGER_CURRENCY.findall(body)) >= _LEDGER_CURRENCY_MIN
        or len(_LEDGER_MEASURE.findall(body)) >= _LEDGER_MEASURE_MIN
    )


def leg_word_budget(leg_walk_seconds: int) -> int:
    """Words that fit the walk-away leg at ~150 wpm (VoiceMap: words = walk_time x wpm).
    The audio must END before the next GPS trigger, so this is a HARD ceiling."""
    return max(0, int(leg_walk_seconds * 150 / 60))


@dataclass(frozen=True)
class ContentBudget:
    """A TOTAL, DISJOINT partition of a POI's beats by where each is best heard.
    Every beat id in ``plan.beats`` appears in exactly one tuple."""

    core_ids: tuple[str, ...]
    walkaway_ids: tuple[str, ...]
    callback_ids: tuple[str, ...]
    optional_ids: tuple[str, ...]
    cut_ids: tuple[str, ...]

    def all_ids(self) -> tuple[str, ...]:
        return (
            *self.core_ids,
            *self.walkaway_ids,
            *self.callback_ids,
            *self.optional_ids,
            *self.cut_ids,
        )


def partition_poi_content(
    plan: POIBeats,
    core_seconds_budget: int,
    leg_walk_seconds: int | None = None,
    interest_lenses: tuple[str, ...] | list[str] | None = None,
) -> ContentBudget:
    """Partition a POI's ORDERED beats into content tiers. Pure; no I/O, no LLM.

    Order of assignment: CUT first (ledger/dump beats), then CORE (the ordered prefix of
    the rest that fits ``core_seconds_budget`` — the first non-cut beat is ALWAYS kept, so
    a stop always speaks), then the remainder competes for WALK-AWAY (fills the following
    leg's audio budget in order), then ONE CALLBACK candidate (a character/anecdote thread
    for a later thin stop), and the rest is OPTIONAL (the opt-in tap). Total + disjoint.
    """
    cut: list[str] = []
    core: list[str] = []
    remainder: list[BeatRef] = []
    consumed = 0
    candidates = [b for b in plan.beats if not is_ledger_beat(b)]
    cut = [b.id for b in plan.beats if is_ledger_beat(b)]

    # LENS-AWARE CORE (opt-in; ``interest_lenses`` absent == byte-identical legacy order).
    # The core fill is greedy first-fit on the ORDERED beats, so which beats survive into
    # the spoken window was decided purely by what happened to FIT the seconds budget —
    # blind to what the tourist actually asked for. Live consequence (2026-07-18, three
    # independent generations): a dark_history tour of Place des Vosges seated a
    # parks_gardens bench beat and two social_change beats, while the POI's own
    # dark_history beats — Victor Hugo on "the blow of Montgomery's lance", the duelling
    # ground, Richelieu's ban — sat outside the window and could never be voiced. Hostile
    # panel verdict: "a tourist who picked dark history would feel misled at the one stop
    # that mattered most" (specs/2026-07-18-tour-qa-campaign/PHASE-C-RESULTS.md).
    # The FIRST beat keeps its position regardless: it is the stop's orientation/staging
    # ("Find a bench near the children's play area..."), which every stop needs and which
    # the lens filter must not evict.
    if interest_lenses:
        order = {str(x).lower(): i for i, x in enumerate(interest_lenses)}

        def _lens_rank(b: BeatRef) -> int:
            """Best (lowest) position of this beat's lenses in the REQUESTED order, so a
            two-lens ask seats its PRIMARY lens first. Off-lens beats sort last."""
            ranks = [
                order[x]
                for x in (str(y).lower() for y in (getattr(b, "lenses", None) or ()))
                if x in order
            ]
            return min(ranks) if ranks else len(order)

        if candidates:
            head, tail = candidates[:1], candidates[1:]
            # Stable sort within each rank: on-lens beats keep their relative order, so this
            # re-PRIORITISES the window without re-ordering arbitrarily.
            candidates = head + sorted(tail, key=_lens_rank)

    for b in candidates:
        secs = beat_spoken_seconds(b)
        if core and consumed + secs > core_seconds_budget:
            remainder.append(b)
        else:
            core.append(b.id)
            consumed += secs

    # WALK-AWAY: fill the following leg's audio budget with remaining STORY beats, in order.
    # A hard ceiling — content that doesn't fit the leg drops to the tap, never overruns the
    # next GPS trigger (Detour's skip-when-fast).
    walkaway: list[str] = []
    rest: list[BeatRef] = []
    consumed_w = 0
    leg_budget = leg_walk_seconds or 0
    for b in remainder:
        secs = beat_spoken_seconds(b)
        if leg_budget and consumed_w + secs <= leg_budget:
            walkaway.append(b.id)
            consumed_w += secs
        else:
            rest.append(b)

    # CALLBACK: exactly one narrative-reference candidate (a character/anecdote thread).
    callback: list[str] = []
    optional: list[str] = []
    taken = False
    for b in rest:
        if not taken and (b.beat_type in _CALLBACK_TYPES or b.narrative_function == "callback"):
            callback.append(b.id)
            taken = True
        else:
            optional.append(b.id)

    return ContentBudget(
        core_ids=tuple(core),
        walkaway_ids=tuple(walkaway),
        callback_ids=tuple(callback),
        optional_ids=tuple(optional),
        cut_ids=tuple(cut),
    )


__all__ = ["ContentBudget", "is_ledger_beat", "leg_word_budget", "partition_poi_content"]
