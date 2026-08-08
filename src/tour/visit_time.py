"""How long a visitor spends AT a place — the third hand on the tour clock.

Time at a stop is min(what the place absorbs, what this visitor's interest
justifies, the party's ceiling). All three arguments matter: Camille
(historic_arch) spends 33 minutes in the Cour Carrée where Théo (dark_history)
spends 8, and a chocolate museum is 90 minutes for one visitor and a walk-past
for the next. See docs/personas/.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .contract import POI

if TYPE_CHECKING:
    # CorpusSnapshot lives in selection.py, NOT contract.py — and it is imported
    # only for the annotation, because step 3B.8 has selection importing the
    # combining rule back out of this module. A real import both ways is a cycle.
    # Same shape as src/tour/density.py, which solved this first.
    from .selection import CorpusSnapshot

#: A one-hop lens match unlocks this fraction of the gap between the outside and
#: inside capacities. Mirrors LENS_ADJACENCY_ONE_HOP = 0.6 rather than inventing
#: a second scale.
ONE_HOP_VISIT_FRACTION: float = 0.6


def visit_seconds(
    poi: POI,
    interest: frozenset[str],
    snapshot: CorpusSnapshot | None,
    *,
    party_ceiling_seconds: int | None = None,
) -> int:
    """Seconds this visitor spends AT this place.

    ``snapshot`` may be None ONLY when no interest was declared, because that is
    the one case the lens graph is never consulted for. Callers without a corpus
    — density's legacy diagnostic form is the only one — must pass an empty
    interest rather than a snapshot of None with lenses, which would otherwise
    silently price every place as a lens miss.
    """
    from .selection import _lens_relation  # single source of truth for the hop model

    if snapshot is None and interest:
        raise ValueError(
            "visit_seconds needs a CorpusSnapshot to price a declared interest; "
            "pass an empty interest instead of guessing a lens relation"
        )

    outside = poi.typical_duration_min * 60
    inside = poi.visit_seconds_inside
    if inside is None or inside <= outside:
        value = outside
    else:
        relation = _lens_relation(poi, interest, snapshot)
        if relation == "direct":
            value = inside
        # "no_lens" is DELIBERATELY not "direct" here, unlike _lens_adjacency at
        # selection.py:3405-3418. Uniform 1.0 is right for SELECTION — do not
        # penalise someone for not choosing. Giving them the maximum interior at
        # every place is wrong for DWELL: it hands a family with a five-year-old
        # a 45-minute cathedral. Same classifier, two questions, two answers.
        elif relation in ("one_hop", "no_lens"):
            value = round(outside + (inside - outside) * ONE_HOP_VISIT_FRACTION)
        else:
            value = outside
    if party_ceiling_seconds is not None:
        value = min(value, party_ceiling_seconds)
    return value


def stop_seconds(visit_seconds: int, audio_seconds: int) -> int:
    """The one rule for how long a stop lasts.

    Each caller supplies its own audio number — the greedy has no Route during
    insertion and must price through the governor allowance, while the final
    gate and generation price through ``build_poi_beat_plans_capped``, and the
    density gate prices an uncapped pool. THE COMBINING is what must not fork;
    the audio sources legitimately differ and saying otherwise would be a lie.

    A stop is never shorter than what it says — the tour cannot cut its own
    narration off mid-sentence — and never shorter than what the place and the
    visitor jointly justify. So it is the longer of the two, and a long silence
    inside it is CORRECT: Camille stands twenty minutes at Concorde for four
    minutes of audio (docs/personas/01-architecture-pilgrim.md, step 5).

    Defined here rather than at the final gate because the density gate needs it
    first, and a second copy written at the second use is exactly the defect
    this phase exists to remove.
    """
    return max(visit_seconds, audio_seconds)


def served_elapsed_seconds(walk_seconds: int, dwell_seconds: int) -> int:
    """How long this tour takes — THE ONE COMPOSITION.

    A two-term sum barely looks worth a function, and that is precisely why it
    grew two spellings: the planner's final band gate composed it in selection.py
    and the rubric's C7 composed it again in quality_rubric.py. Two expressions of
    one quantity agree until one of them is edited, and then a tour is certified at
    one length and judged at another.

    The DWELL each caller passes legitimately differs and must not be forced to
    match: the planner has a corpus and no Script, so it prices stops through
    ``selection.served_dwell_seconds``; the rubric has the Script generation
    actually produced and reads ``dwell_seconds`` straight off its stops. Those are
    two honest views of the same tour at two moments. THE COMBINING is what forks,
    so the combining is what lives here.

    Walking is the whole walk, never a share of it: narration heard on the move is
    free (product ruling 2026-07-19) because it happens inside a walk this sum
    already counts.
    """
    return walk_seconds + dwell_seconds
