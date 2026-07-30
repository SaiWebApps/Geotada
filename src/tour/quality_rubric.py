"""THE TOUR QUALITY RUBRIC — the mechanical floor that runs on every tour.

Full standard, gold examples and threshold provenance:
``specs/2026-07-19-tour-quality-standard/01-standard.md``. Read it before changing a
number here; every threshold there is either MEASURED, INHERITED from the engine, or
CITED to professional audio-guide practice, and says which.

Two layers, per the standard:

* **FLOOR (this module)** — deterministic, $0, runs on every tour. A BLOCKER result
  means the tour is not fit to serve and the caller regenerates.
* **GATE (elsewhere)** — semantic, model-judged. Meaning-level properties a counter
  can never see. Per ``feedback-no-lexical-shortcuts``, word-matching for MEANING is a
  banned shortcut in this project: narrative quality is judged semantically or not at
  all. This module therefore checks only STRUCTURE — counts, ratios, budgets — and
  deliberately makes no claim about whether the prose is good.

The two failures this exists to catch, both measured on the live Paris graph:

* **STARVATION** — Sainte-Chapelle (tier 5, 12 beats in corpus) rendered as 9 words.
* **GORGING** — Notre-Dame rendered 1022 words in one stop, over even the walking-tour
  adaptation of the museum sector's 250-words-per-station ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from src.tour.contract import BeatSequence, Route, Script
from src.tour.generation import (
    _END_B_SENTINEL_PREFIX,
    SPOKEN_WPM,
    is_walk_concurrent,
)
from src.tour.narration_quality import score_narration

# ── thresholds ──────────────────────────────────────────────────────────────
# Provenance for every value is in the standard, §5. Summary of KIND:
#   MEASURED  — derived from a real $0 engine run on the live Paris graph
#   INHERITED — already a constant elsewhere in the engine; not a new number
#   CITED     — professional audio-guide practice, with a URL in the standard
#   JUDGEMENT — chosen by us; the standard says so explicitly and shows the data

#: JUDGEMENT. A POI with at least this many corpus beats is "rich" — starving it is a
#: defect rather than an editorial choice. Sainte-Chapelle had 12; the thin POIs
#: around it had 3.
STARVE_MIN_BEATS: int = 5

#: JUDGEMENT, anchored on MEASURED data. Healthy stops ran ~17 and ~40 words/beat.
#: Deliberately permissive: this catches 9-words-for-12-beats (0.75), not terseness.
STARVE_MIN_WORDS_PER_BEAT: float = 12.0

#: MEASURED 2026-07-26, superseding the earlier CITED-adapted 750. Museum practice caps
#: a station at 250 words (~2 min); a walking-tour anchor with a 5-min dwell is not a
#: museum station, so the number was adapted rather than cited — but it was adapted by
#: reasoning, not measurement, and it was WRONG. Widest-stop population across the eight
#: authored tours in data/certification/tour-batch-v1/:
#:     661 / 662 / 664 / 673 / 679 / 757 / 761 / 808
#: At 750 this check BLOCKED three tours this project itself certified
#: (nyc-lower-manhattan-90, paris-marais-loop-60, paris-ile-open-90). 850 clears the
#: real ceiling (808) at 1.05x while still catching the defect it exists for — the
#: measured Notre-Dame wall of 1022-1038 words — at 1.20x.
#: Guarded by test_c8_clears_the_widest_stop_in_the_certification_corpus.
GORGE_MAX_WORDS_PER_STOP: int = 850

#: JUDGEMENT, anchored on a MEASUREMENT of the gold text. Was 15.0, CITED to Nubart /
#: Musa Guide ("keep sentences to 10-15 words for the ear"). That citation describes
#: MUSEUM STATION copy, and it does not survive contact with this project's own north
#: star: the owner's hand-written gold (standard §1) measures `mean_sentence_words`
#: **19.11** and so FAILED its own bar at 15, as did every one of 191 saved tours.
#:
#: WHAT THIS RETUNE DID AND DID NOT FIX. It moved the STOP-level pass rate from 0/38 to
#: 6/38, and it admits the gold. At TOUR level the rate barely moves — 9/9 of cohort A
#: and 176/182 of cohort B still trip C9 — because one over-long stop flags a whole tour.
#: So "a check that never passes discriminates nothing" is only half-answered here: the
#: cap is no longer unreachable, but most real tours genuinely do ramble. Do not read a
#: 100% tour-level rate in the scorer output as evidence the retune failed.
#:
#: The check itself is SOUND and was nearly deleted by mistake. C9 fires PER STOP;
#: aggregating whole-tour compresses machine figures toward the gold and hides the
#: ordering. Measured per stop across the post-audio-fix cohort: gold 19.11 against 38
#: machine stops at min 16.9 / median 23.2 / max 34.3. The gold reads shorter than 34 of
#: 38 — C9 ranks the hand-written text above machine output correctly. Only the constant
#: was wrong.
#:
#: THE RULE FOR THE NUMBER: the smallest round number strictly above the anchor. Not
#: 19.11 itself — `score_narration` rounds to 2dp, so `19.11 > 19.11` is False by nothing
#: at all, and one word added to a 509-word passage flips it. Margin is needed for a
#: second reason too: the gold's mean is taken over 27 sentences while a real stop's is
#: taken over 5-6, so the cap judges a noisier statistic than the one it was calibrated
#: on. Nothing hinges on the exact choice — 19.5 fails 33 of 38 machine stops, 20 fails
#: 32, 21 fails 31 — so the rule matters more than the value.
#: Guarded by test_c9_cap_admits_the_owners_own_gold_text — the calibration, executable.
MAX_SENTENCE_WORDS: float = 20.0

#: CITED. 130-150 words per minute of spoken narration.
WORDS_PER_MINUTE: float = 150.0

#: JUDGEMENT. No single stop should hold more than this share of the tour's words.
BALANCE_MAX_SHARE: float = 0.60

#: JUDGEMENT, from a MEASURED absurdity, and demoted to WARN by a SECOND measurement.
#: An acceptance pass on a real Île de la Cité tour found Palais de Justice and
#: Conciergerie seated as SEPARATE stops **17 metres apart** — the same building
#: complex — where the second stop opens by saying "the Conciergerie is one of the
#: few remaining vestiges of the old medieval Palais de Justice", i.e. describing the
#: spot the listener stood on seconds earlier. That is a real defect this constant
#: was written to catch.
#:
#: RECALIBRATED from 100 m to 50 m on evidence: at 100 m this also flagged
#: Sainte-Chapelle at 86 m from the Conciergerie, and that is a FALSE POSITIVE —
#: Sainte-Chapelle is a genuinely distinct attraction, and 86 m is a real (if short)
#: walk in a dense historic quarter.
#:
#: THEN, at 50 m, MEASURED across the full real corpora (2026-07-19,
#: ``tests/test_tour_selection.py::test_selection_does_not_filter_close_but_distinct_pois``):
#: Paris' 370 POIs give 48 pairs under 50 m, New York's 402 give 46. They are NOT one
#: population. True duplicates (corpus geocoding defects — the same place entered
#: twice, e.g. NYSE/Wall Street, Place/Square des Abbesses, Flatiron
#: District/Building) cluster at 0.0-1.7 m. Genuinely distinct, walkable landmarks
#: start at ~8 m: Panthéon <-> Bibliothèque Sainte-Geneviève (14.9 m), Place de la
#: Concorde <-> Jeu de Paume (14.3 m), Galignani <-> Angelina (11.8 m), and — the
#: decisive case — Hôtel Le Meurice <-> Angelina at **8.4 m**. Le Meurice and
#: Galignani are the two POIs the product owner's own gold text narrates as
#: consecutive stops (standard §1: "At number 224, the English bookshop
#: Galignani... Le Meurice... at 228"). No distance threshold separates "one
#: building told twice" from "two neighbours on one street" — 8.4 m (a real
#: distinction) sits well inside the 17 m defect case this constant was calibrated
#: on. A companion guard that filtered ``select_route`` on this same distance was
#: tried and REVERTED for exactly this reason (see the refutation test above,
#: [[stop-separation-guard-refuted]]); this check is demoted from BLOCKER to WARN
#: for the identical reason — refusing to SERVE a tour containing the gold-standard
#: stop is a worse defect than the one this constant was built to catch. The real
#: tool for "the same place told twice" is semantic, not geometric: G4 (repetition of
#: the same FACT anywhere in the tour, standard §4). C12 stays as a WARN surfaced to
#: the editor — a short gap is still worth a human glance — but never blocks serving.
MIN_STOP_SEPARATION_M: float = 50.0

#: JUDGEMENT. Ceiling on the C1 starvation floor, as a share of the gorge cap, so C1
#: and C8 can never demand contradictory things for a beat-rich POI. See the comment
#: at the C1 check for the Notre-Dame arithmetic that forced this.
STARVE_FLOOR_MAX_SHARE_OF_CAP: float = 0.5

#: MEASURED 2026-07-26. The minimum share of the REQUESTED duration that must arrive as
#: spoken audio. Replaces the old derivation
#: ``ERR_SHORT(0.83) x AUDIO_FRACTION(0.60) x AUDIO_FLOOR_FRAC(0.8) = 0.398``, which was
#: self-referential (it inherited the PLANNER's aim as the SERVING verdict) and wrong.
#:
#: routing.py declares WALK_FRACTION 0.40 + AUDIO_FRACTION 0.60 = 1.00 — a DISJOINT
#: walk-XOR-listen model, i.e. the tourist stands still for 60% of the hour. The product
#: ruling of 2026-07-19 ("audio overlaps the walking… it costs no time", commit 4cbb94c)
#: retired that model, and C7/C7b were updated for it. C3 was not. 0.398 is a fossil.
#:
#: MEASURED audio/duration on the eight tracked certified tours:
#:     0.227 nyc-lower-manhattan-90   <- worst tour this project ACCEPTED
#:     0.249 nyc-central-park-open-90
#:     0.277 paris-marais-loop-60
#:     0.286 nyc-grand-central-times-square-60
#:     0.311 nyc-village-loop-60
#:     0.343 paris-ile-open-90
#:     0.426 paris-pont-neuf-notre-dame-60
#:     ----
#:     0.056 paris-west-axis-90       <- genuinely starved: 2 stops, 5.0 min for 90 min
#: At 0.398, SEVEN of the eight were BLOCKED. The check was also inverted in practice:
#: a verbose ONE-STOP tour passed while an 11-stop tour did not.
#:
#: 0.19 is the geometric midpoint of the two poles it must separate — the documented
#: starved run (9.4 min for 60 min = 0.157) and the worst accepted tour (0.227) — giving
#: a symmetric 1.21x block margin and 1.19x pass margin. It is NOT a target: the engine
#: still AIMS at AUDIO_FRACTION; this is the floor below which a tour is not deliverable.
#: Guarded from both sides by
#: test_c3_clears_the_certification_corpus_and_still_blocks_the_starved_tour.
MIN_AUDIO_FRAC_OF_REQUESTED: float = 0.19

#: INHERITED. The engine composes at most eight stops — premium_tour.py (``max_stops=8``)
#: and routing.py ("certification planning supports one to eight stops"). Named here so
#: the C3 floor can be capped by what a tour may PHYSICALLY hold; see
#: ``c3_audio_floor_seconds``.
MAX_COMPOSED_STOPS: int = 8

#: MEASURED, 2026-07-19, over every real composed tour in ``data/*/tours/`` — 195 tour
#: files: **paris 191, london 4. ``data/new_york/tours/`` DOES NOT EXIST** and
#: contributed nothing, so this is a Paris-dominated sample (paris 485 of 501
#: stop/tour samples with a nonzero tour mean), not a three-city one. An earlier
#: revision of this comment claimed "paris, london, new_york — 487 samples"; that
#: was wrong on both counts and was caught by an adversarial re-read rather than by
#: the author. The distribution below reproduces exactly — only the stated evidence
#: base was inflated. §4 gives no absolute "dates per 100 words" ceiling for C11
#: (unlike C1/C8), so C11 flags a stop RELATIVE to
#: the tour's own mean year_density rather than an invented absolute cut. The
#: multiple is anchored on the real distribution of (stop_density / tour_mean)
#: across every measured stop: median 0.97, p90 1.67, p95 2.00, max 3.11. 3.4% of
#: samples exceed a 2.0x multiple, i.e. this sits at roughly the p95 of real
#: tours — a genuine outlier cut, not noise, without being so tight it fires on the
#: routine spread every tour has. This was a one-off measurement (not a standing
#: regression test — the corpus in ``data/*/tours/`` will drift), reproducible by
#: running ``score_narration`` per stop over every ``data/{city}/tours/*.json`` and
#: taking each stop's ``per_100w["year_density"]`` against its tour's own mean.
#: Revisit if a future corpus's distribution shifts (see standard §8's own
#: admission that external audio-guide research is "in flight").
OUTLIER_YEAR_DENSITY_MULTIPLE: float = 2.0


class Severity(StrEnum):
    """BLOCKER regenerates the tour. WARN surfaces to the editor."""

    BLOCKER = "blocker"
    WARN = "warn"


@dataclass(frozen=True)
class Finding:
    check: str
    severity: Severity
    message: str
    stop_idx: int | None = None
    poi_name: str | None = None
    #: Structured numbers a check needed to derive its own verdict and that a later
    #: consumer (``compose_fixable``) needs again — e.g. C1's per-POI floor. Kept
    #: separate from ``message`` (prose for a human) so downstream code never has to
    #: parse a sentence to recover a number score_tour already computed exactly.
    context: dict | None = None


@dataclass
class RubricReport:
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.BLOCKER]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity is Severity.WARN]

    @property
    def passed(self) -> bool:
        """False => do not serve this tour; regenerate."""
        return not self.blockers

    def summary(self) -> str:
        if self.passed and not self.warnings:
            return "PASS — no findings"
        head = "PASS" if self.passed else "FAIL"
        return (
            f"{head} — {len(self.blockers)} blocker(s), {len(self.warnings)} warning(s): "
            + "; ".join(f"{f.check}:{f.message}" for f in self.findings[:6])
        )


def c3_audio_floor_seconds(duration_min: int) -> float:
    """The C3 thinness floor, in seconds of spoken audio, for a requested duration.

    Two terms, and the ``min`` is the load-bearing half:

    1. ``MIN_AUDIO_FRAC_OF_REQUESTED`` — MEASURED against the tracked certified tours.
    2. A CAP at what a tour may physically contain:
       ``MAX_COMPOSED_STOPS x GORGE_MAX_WORDS_PER_STOP x STARVE_FLOOR_MAX_SHARE_OF_CAP``.

    Term 1 alone is LINEAR in duration while capacity is CONSTANT, so an uncapped floor
    becomes physically unsatisfiable on long tours: ``TourInput`` accepts up to 600 min,
    where the old 0.398 floor demanded ~35 800 words from a tour that may hold at most
    ``8 x 850 = 6800``. No choice of fraction fixes that — only the cap does. This is
    exactly the contradiction ``STARVE_FLOOR_MAX_SHARE_OF_CAP`` already exists to
    prevent between C1 and C8; C3 needed the same treatment.

    Exposed (rather than inlined in ``score_tour``) so the satisfiability claim is
    directly testable at every offered duration — see
    ``test_c3_floor_never_demands_more_words_than_c8_allows_at_any_offered_duration``.
    """
    linear_s = MIN_AUDIO_FRAC_OF_REQUESTED * duration_min * 60
    capacity_words = (
        MAX_COMPOSED_STOPS * GORGE_MAX_WORDS_PER_STOP * STARVE_FLOOR_MAX_SHARE_OF_CAP
    )
    capacity_s = capacity_words / WORDS_PER_MINUTE * 60
    return min(linear_s, capacity_s)


def _words(text: str) -> int:
    return len(text.split())


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle metres. Local copy so the rubric imports nothing from the
    selection engine it is meant to judge independently."""
    import math

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 6_371_000.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _concurrent_audio_seconds(script: Script, beat_sequence: BeatSequence | None) -> int:
    """Seconds of narration the tourist hears WHILE WALKING, not while standing.

    Per the 2026-07-19 product ruling ("Audio overlaps the walking. It is a part of
    the tour experience.") this audio costs no elapsed time — it is spoken during a
    leg the tourist is walking anyway. C7 must therefore exclude it from the time
    budget, and C7b bounds it by the walk it rides on.

    Identified from what the engine already records, with no new Sentence field:

    * ``GLUE_NAV`` — the leg's navigation line, spoken on the move.
    * ``GLUE_REFLECTION`` — placed by ``reflection.py`` on a long WALKING leg by
      definition; that is the whole point of the placement rule.
    * vignette beat sentences — walk-past one-liners voiced inside the leg
      (``generation._vignette_one_liners``), identified via
      ``beat_sequence.vignette_beats``.

    Everything else — anchor beat sentences, the cold open, staging, closing — is
    spoken at a stop with the tourist standing still, and stays in the time budget.

    Without a ``beat_sequence`` the vignette ids are unknown; those sentences then
    count as stationary, which is the CONSERVATIVE direction (it can only make C7
    stricter, never wrongly pass a tour).
    """
    vignette_ids: set[str] = set()
    if beat_sequence is not None:
        vignette_ids = {
            b.id for beats in beat_sequence.vignette_beats.values() for b in beats
        }
    words = sum(
        _words(s.text) for s in script.script if is_walk_concurrent(s, vignette_ids)
    )
    return round(words / SPOKEN_WPM * 60)


def score_tour(
    script: Script,
    route: Route,
    beats_by_poi: dict[str, list],
    *,
    beat_sequence: BeatSequence | None = None,
) -> RubricReport:
    """Score a generated tour against the mechanical floor of the quality standard.

    ``beats_by_poi`` is the corpus map (``CorpusSnapshot.beats_by_poi``) — the full set
    of beats AVAILABLE for each POI, which is what makes the starvation check possible:
    it compares what was rendered against what the corpus could have supported.
    """
    report = RubricReport()

    words_by_stop: dict[int, int] = {}
    texts_by_stop: dict[int, list[str]] = {}
    for sentence in script.script:
        words_by_stop[sentence.stop_idx] = words_by_stop.get(sentence.stop_idx, 0) + _words(
            sentence.text
        )
        texts_by_stop.setdefault(sentence.stop_idx, []).append(sentence.text)

    total_words = sum(words_by_stop.values())
    report.stats = {
        "total_words": total_words,
        # The stop count is the ROSTER's, not the rendered sentences'. Counting
        # ``words_by_stop`` UNDER-REPORTS whenever a stop rendered nothing at all —
        # the exact tour C6 exists to catch — so the editor saw "2 stops" for a
        # 3-stop tour with one silent stop and had no signal anything was missing.
        "n_stops": len(script.selected_pois),
        "audio_minutes": round(script.total_audio_seconds / 60, 1),
        "words_by_stop": dict(sorted(words_by_stop.items())),
    }

    # ── C3: thin tour — delivered audio against a MEASURED floor ────────────
    # The floor is MIN_AUDIO_FRAC_OF_REQUESTED, calibrated against the tracked
    # certification batch (see that constant for the full population). It is CAPPED by
    # what a tour may physically hold, so C3 can never demand what C8 forbids — the
    # same construction, and the same reason, as C1's cap at the starvation check.
    # Without C3 the rubric BLESSES a starved tour, which it did on a 2-stop/9.4-min run.
    duration_min = getattr(script.inputs, "duration_min", 0) or 0
    if duration_min:
        floor_s = c3_audio_floor_seconds(duration_min)
        report.stats["audio_floor_min"] = round(floor_s / 60, 1)
        if script.total_audio_seconds < floor_s:
            report.findings.append(
                Finding(
                    check="C3-thin",
                    severity=Severity.BLOCKER,
                    message=(
                        f"{script.total_audio_seconds / 60:.1f} min of audio for a "
                        f"{duration_min}-min request (floor {floor_s / 60:.1f} min) — "
                        f"the tourist walks in silence"
                    ),
                )
            )

    # ── C7: time-budget overrun — walk + STATIONARY listening vs the engine's total ─
    # INHERITED ceiling, nothing new computed. routing.py:94-95 defines
    # err_short_total_seconds(duration) = duration_min * ERR_SHORT * 60, and
    # summarise_route (routing.py:290-299) stamps it onto the Route, so this reads
    # the field straight off ``route``. Skipped when the Route carries no total
    # (the field's own unset sentinel, 0 — e.g. a Route built directly in a test).
    #
    # AUDIO SPOKEN WHILE WALKING IS FREE (product ruling, 2026-07-19: "Audio
    # overlaps the walking. It is a part of the tour experience.").
    #
    # This check previously added ALL audio to ALL walking. That models a tourist
    # who walks in silence and then stands in silence to listen — which is not what
    # the product is. Under that model, filling a walk with narration APPEARS to
    # consume the time budget even though it costs the tourist no extra minutes, so
    # leg content could never be scored fairly however much of it was added.
    #
    # CORRECTION (2026-07-19). An earlier revision of this comment justified the
    # change with a worked example — "1650s walk + 1434s audio = 3084s against a
    # 2988s ceiling", i.e. a claim that closing C3 necessarily tripped C7, BLOCKER
    # for BLOCKER. THAT ARITHMETIC WAS WRONG and is removed rather than quietly
    # corrected. The 1650s was measured on the Île de la Cité tour while an
    # unrelated selection-side experiment was applied; that experiment was reverted
    # (it moved frozen route geometry) and the figure was carried across anyway. The
    # real walk on this route is 1087s, so the sum is 2521s against 2988s — 467s of
    # HEADROOM. No such deadlock occurred on any measured tour; an adversarial
    # review caught this, not the author.
    #
    # The change rests on the PRODUCT RULING alone, which needs no arithmetic:
    # narration heard while walking is part of the tour experience and does not cost
    # the tourist extra minutes. That is a statement about what the product IS.
    #
    # The correct model has two kinds of listening:
    #   * STATIONARY — the tourist stands at a stop and listens. This ADDS to
    #     elapsed time and is what C7 must count.
    #   * CONCURRENT — the tourist listens WHILE walking a leg. This costs no
    #     elapsed time at all; it is bounded by the leg's own duration (C7b below).
    #
    # Concurrent audio is identified from what the engine already records, with no
    # new field: navigation glue and reflections are spoken on the move by
    # construction (reflection.py places a reflection on a LONG WALKING LEG), and a
    # vignette is a walk-past one-liner (generation._vignette_one_liners). Anchor
    # beat sentences at a stop are stationary.
    concurrent_s = _concurrent_audio_seconds(script, beat_sequence)
    stationary_s = max(0, script.total_audio_seconds - concurrent_s)
    report.stats["audio_concurrent_s"] = concurrent_s
    report.stats["audio_stationary_s"] = stationary_s

    if route.err_short_total_seconds > 0:
        actual_total_s = route.total_walk_seconds + stationary_s
        report.stats["time_budget_actual_s"] = actual_total_s
        report.stats["time_budget_ceiling_s"] = route.err_short_total_seconds
        # The ceiling percentage is DERIVED FROM THE ROUTE, never from a planning
        # constant. This message used to interpolate ERR_SHORT (83%) as a literal, but
        # the premium/certification lane plans at a nominal fraction of 1.00, so on
        # every premium tour the sentence said "83% of the requested duration" while
        # the arithmetic above correctly used the route's own stamped total. The number
        # a reader is shown must be the one the check actually measured against.
        ceiling_note = (
            f" ({route.err_short_total_seconds / (duration_min * 60):.0%} of the "
            f"requested duration)"
            if duration_min
            else ""
        )
        if actual_total_s > route.err_short_total_seconds:
            report.findings.append(
                Finding(
                    check="C7-time-budget",
                    severity=Severity.BLOCKER,
                    message=(
                        f"{actual_total_s}s of walking+standing exceeds the "
                        f"{route.err_short_total_seconds}s err-short budget "
                        f"({route.total_walk_seconds}s walk + "
                        f"{stationary_s}s stationary listening; {concurrent_s}s more is "
                        f"spoken while walking and costs no time) — over the engine's own "
                        f"err-short planning ceiling{ceiling_note}, not necessarily over "
                        f"the requested duration itself"
                    ),
                )
            )

    # ── C7b: leg audio may not outrun the leg ──────────────────────────────────
    # Concurrent audio is free only while the tourist is still walking. Narration
    # that outlasts its leg either cuts off on arrival or holds the tourist on the
    # pavement — so the free-airtime budget is the walk itself.
    #
    # THE TWO WALK MEASURES DISAGREE, so take the SMALLER. ``route.total_walk_seconds``
    # and ``sum(transits.leg_seconds)`` are not the same number: measured across six
    # real Paris tours they differ by -119s to +499s (ile_arch_60: 736 vs 1115;
    # ile_dark_120: 2166 vs 2665), because leg_seconds carries routed road-network
    # values while total_walk_seconds is the pace-corrected haversine the budget math
    # uses (see routing.py's TransitSegment note). C7 uses total_walk_seconds because
    # that is the currency the err-short ceiling is denominated in.
    #
    # C7b is a BLOCKER about whether narration FITS a walk, so it must never
    # overstate the airtime available: the min of the two is the honest bound. An
    # adversarial review caught the two checks silently reasoning about different
    # walks.
    leg_seconds_total = sum(
        int(t.leg_seconds if t.leg_seconds is not None else t.walk_seconds)
        for t in route.transits
    )
    total_leg_walk_s = (
        min(leg_seconds_total, route.total_walk_seconds)
        if route.total_walk_seconds > 0
        else leg_seconds_total
    )
    report.stats["leg_walk_capacity_s"] = total_leg_walk_s
    if concurrent_s > total_leg_walk_s > 0:
        report.findings.append(
            Finding(
                check="C7b-leg-audio-overruns-walk",
                severity=Severity.BLOCKER,
                message=(
                    f"{concurrent_s}s of walk-concurrent narration exceeds the "
                    f"{total_leg_walk_s}s the tourist actually spends walking — leg "
                    f"content would cut off on arrival or hold them on the pavement"
                ),
            )
        )

    # ── C6: no empty stop ───────────────────────────────────────────────────
    # DRIVEN FROM THE STOP ROSTER, not from the rendered sentences. Iterating
    # ``words_by_stop`` made this check UNREACHABLE for the exact condition it
    # names: a stop that rendered NO Sentence at all has no key in that dict, so
    # the ``words == 0`` branch could only ever fire on a Sentence whose text was
    # literally empty. A tour routing the walker to a stop where they hear nothing
    # scored PASS and was served. C1 does not cover it either (it skips POIs with
    # fewer than STARVE_MIN_BEATS corpus beats).
    #
    # ALIGNMENT ASSUMPTION (shared with C1/C8 below, and stated here rather than
    # left implicit): ``stop_idx`` indexes ``script.selected_pois`` POSITIONALLY.
    # That holds because both the roster (generation._script_pois, built by walking
    # ``route.pois`` in order) and every Sentence's ``stop_idx`` are derived from
    # the same ordered Route. It is NOT keyed on beat_sequence.poi_beats, which is a
    # lookup BY POI ID inside that walk and may legitimately not cover every POI.
    #
    # The pinned-endpoint sentinel (``_END_B_SENTINEL_PREFIX``, generation.py:891)
    # is skipped: it is a materialised destination with no POI of its own and is
    # content-free BY DESIGN, so silence there is not a defect.
    #
    # A roster entry with NO SEATED PLAN (``beat_sequence.poi_beats`` has no entry
    # for it, so ``ScriptPOI.beat_ids`` is empty) is deliberately NOT skipped. It is
    # tempting to treat it as "nothing was seated, so nothing could be said", but
    # that is the WORST instance of this very defect: the tourist is still routed
    # there and still hears nothing. It also carries no false-positive risk, because
    # such a stop normally still receives its arrival/navigation glue line (attached
    # at ITS stop_idx by ``generation._build_transit``) and so never reaches zero
    # words. Only a genuinely silent stop fires.
    for stop_idx, poi in enumerate(script.selected_pois):
        if poi.id.startswith(_END_B_SENTINEL_PREFIX):
            continue
        if words_by_stop.get(stop_idx, 0) == 0:
            report.findings.append(
                Finding(
                    check="C6-empty-stop",
                    severity=Severity.BLOCKER,
                    message="stop rendered zero words",
                    stop_idx=stop_idx,
                    poi_name=poi.name,
                )
            )

    # ── C1 starvation / C8 gorging, per anchor ──────────────────────────────
    # ScriptPOI carries the POI roster in stop order; stop_idx indexes it.
    for stop_idx, poi in enumerate(script.selected_pois):
        words = words_by_stop.get(stop_idx, 0)
        available = len(beats_by_poi.get(poi.id, ()))

        if available >= STARVE_MIN_BEATS:
            # The floor is CAPPED so C1 and C8 cannot demand contradictory things. A
            # linear floor is unsatisfiable for a beat-rich POI: Notre-Dame has 59
            # corpus beats, so 59*12 = 708 words, against a 750-word gorge cap — a
            # 42-word window, and govern_poi_beats cuts on WHOLE beats so the render
            # jumps 594 -> 709 and can land outside it. Starvation means "a rich POI
            # was reduced to a line", NOT "the stop failed to exhaust the corpus": a
            # 59-beat POI legitimately renders a SELECTION. Capping the floor at half
            # the gorge limit keeps the check meaningful where it matters (12 beats ->
            # 144-word floor still catches Sainte-Chapelle's 9 words) while never
            # contradicting C8.
            floor = min(
                STARVE_MIN_WORDS_PER_BEAT * available,
                GORGE_MAX_WORDS_PER_STOP * STARVE_FLOOR_MAX_SHARE_OF_CAP,
            )
            if words < floor:
                report.findings.append(
                    Finding(
                        check="C1-starved",
                        severity=Severity.BLOCKER,
                        message=(
                            f"{words} words rendered for a POI with {available} corpus "
                            f"beats (floor {floor:.0f}); the material exists and was not used"
                        ),
                        stop_idx=stop_idx,
                        poi_name=poi.name,
                        context={"floor": floor},
                    )
                )

        if words > GORGE_MAX_WORDS_PER_STOP:
            report.findings.append(
                Finding(
                    check="C8-gorged",
                    severity=Severity.BLOCKER,
                    message=(
                        f"{words} words in one stop (cap {GORGE_MAX_WORDS_PER_STOP}, "
                        f"~{words / WORDS_PER_MINUTE:.1f} min of unbroken narration)"
                    ),
                    stop_idx=stop_idx,
                    poi_name=poi.name,
                )
            )

    # ── C2: tier inversion — a tier-5 POI reduced to a walk-past one-liner ──
    anchor_ids = {p.id for p in script.selected_pois}
    vignette_pois = [v for group in (route.vignettes or {}).values() for v in group]
    anchor_tiers = [p.tier for p in script.selected_pois]
    lowest_anchor_tier = min(anchor_tiers) if anchor_tiers else 5
    for vig in vignette_pois:
        if vig.id in anchor_ids:
            continue
        available = len(beats_by_poi.get(vig.id, ()))
        if vig.tier > lowest_anchor_tier and available >= STARVE_MIN_BEATS:
            report.findings.append(
                Finding(
                    check="C2-tier-inversion",
                    severity=Severity.BLOCKER,
                    message=(
                        f"tier-{vig.tier} POI with {available} beats is a walk-past "
                        f"vignette while a tier-{lowest_anchor_tier} POI is a full stop"
                    ),
                    poi_name=vig.name,
                )
            )

    # ── C4: stop balance ────────────────────────────────────────────────────
    if total_words and words_by_stop:
        top_idx, top_words = max(words_by_stop.items(), key=lambda kv: kv[1])
        share = top_words / total_words
        if share > BALANCE_MAX_SHARE and len(words_by_stop) > 1:
            report.findings.append(
                Finding(
                    check="C4-imbalance",
                    severity=Severity.WARN,
                    message=f"one stop holds {share:.0%} of the tour's words",
                    stop_idx=top_idx,
                )
            )

    # ── C12: two adjacent anchors close enough to deserve a human glance ────
    # WARN, not BLOCKER — see MIN_STOP_SEPARATION_M's provenance comment above.
    # Consecutive anchors only: a tour legitimately revisits an area. Distance ALONE
    # cannot tell "the same place told twice" (17 m Palais de Justice/Conciergerie,
    # a real defect) apart from "two neighbouring, genuinely distinct landmarks"
    # (8.4 m Hôtel Le Meurice/Angelina — the product owner's OWN gold-text stops,
    # standard §1). A BLOCKER here refuses to serve the gold-standard tour, which is
    # worse than the defect this check exists to catch. It stays WARN so an editor
    # sees a short gap without the tour being refused; the check that actually
    # distinguishes the two cases is semantic, G4 (same fact repeated anywhere in
    # the tour), not geometric.
    pois = list(script.selected_pois)
    for i in range(len(pois) - 1):
        a, b = pois[i], pois[i + 1]
        metres = _haversine_m(a.lat, a.lng, b.lat, b.lng)
        if metres < MIN_STOP_SEPARATION_M:
            report.findings.append(
                Finding(
                    check="C12-stops-too-close",
                    severity=Severity.WARN,
                    message=(
                        f"{metres:.0f} m from the previous stop ({a.name}) — close enough "
                        f"that an editor should confirm these are two distinct stops, not "
                        f"one place told twice"
                    ),
                    stop_idx=i + 1,
                    poi_name=b.name,
                )
            )

    # ── C5: verbatim repetition ─────────────────────────────────────────────
    seen: dict[str, int] = {}
    for sentence in script.script:
        key = " ".join(sentence.text.lower().split())
        if len(key.split()) < 5:  # short glue lines legitimately recur
            continue
        if key in seen:
            report.findings.append(
                Finding(
                    check="C5-verbatim-repeat",
                    severity=Severity.BLOCKER,
                    message=f"sentence repeated (also at stop {seen[key]}): {sentence.text[:70]}…",
                    stop_idx=sentence.stop_idx,
                )
            )
        else:
            seen[key] = sentence.stop_idx

    # ── C9/C11: narration-quality reuse, per stop (C10 deleted 2026-07-27) ──
    # REUSE narration_quality.score_narration — the standard (§5/§6) says the rubric
    # reuses those metrics and, until now, imported nothing from that module. No new
    # lexical logic is added below; only score_narration's own numbers are read.
    stop_year_densities: dict[int, float] = {}
    for stop_idx, texts in sorted(texts_by_stop.items()):
        stop_text = " ".join(texts)
        if not stop_text.strip():
            continue  # C6 already reports the empty stop; nothing to score here
        nq = score_narration(stop_text)

        # C9: sentence length for the ear. The cap is a JUDGEMENT anchored on the gold
        # text's own measured 19.11 (see MAX_SENTENCE_WORDS), NOT on the Nubart 10-15
        # museum-copy range it used to cite — the gold failed that range. WARN — a long
        # mean is a craft smell surfaced to the editor, not grounds to refuse serving.
        if nq.mean_sentence_words > MAX_SENTENCE_WORDS:
            report.findings.append(
                Finding(
                    check="C9-long-sentences",
                    severity=Severity.WARN,
                    message=(
                        f"mean sentence length {nq.mean_sentence_words:.1f} words "
                        f"(cap {MAX_SENTENCE_WORDS:.0f})"
                    ),
                    stop_idx=stop_idx,
                )
            )

        # C10 (opens with a look-cue) WAS HERE. DELETED 2026-07-27, and NOT replaced —
        # opener quality is currently UNCHECKED. See
        # tests/...::test_openers_are_unchecked_since_c10_was_deleted, which pins the gap.
        #
        # It asked a MEANING question with a word list. narration_quality._LOOK_INITIAL
        # is a regex matching 18 sentence-initial verbs (look|notice|spot|glance|watch|
        # turn|cross|walk|stop|pause|head|carry on|step|face|find). The owner's own gold
        # text opens "Here, at the corner of rue de Castiglione and rue de Rivoli, stands
        # the Hotel Le Meurice" — the clearest instance of orientation-before-history in
        # the whole standard, and the sentence S1 was derived FROM — and C10 rated it
        # "a bare fact, not a look-cue". It fired on 100% of 191 saved tours and on the
        # north star itself, so it separated nothing.
        #
        # It cannot be fixed by extending the word list; that is the same shortcut with
        # more words. The standard specifies the replacement — G1, judged semantically —
        # and the honest state is that G1 does not exist yet.

        stop_year_densities[stop_idx] = nq.per_100w["year_density"]

    # C11: date density for the ear. WARN, RELATIVE to the tour's own mean — see
    # OUTLIER_YEAR_DENSITY_MULTIPLE for why there is no absolute cut (§5 has no
    # provenance row for one). Always reports the per-stop densities either way.
    if len(stop_year_densities) > 1:
        report.stats["year_density_by_stop"] = dict(sorted(stop_year_densities.items()))
        mean_density = sum(stop_year_densities.values()) / len(stop_year_densities)
        if mean_density > 0:
            # C11 IS REPORT-ONLY. It records the outliers as a stat and emits NO
            # Finding. Ruled 2026-07-30 on measurement, not taste: C11 fired on
            # 100% of the human-vetted reference tours (5 of 25 Place des Vosges
            # positions, 6 of 29 Ile) and on only 8-11% of machine tours. A check
            # that accuses the hand-written text this project calls its north star,
            # while passing the output it is meant to police, is pointing the wrong
            # way — and the multiple needed to admit the references (3.82 PdV /
            # 4.19 Ile) sits ABOVE the machine maximum ratio of 3.11, so no
            # threshold exists that clears the humans and still bites. Deleting it
            # would throw away a real signal; emitting it as a WARN spends reader
            # attention on noise. So the densities stay visible in
            # `stats["year_density_outliers"]` for anyone diagnosing a date-list
            # stop, and nothing is blocked or warned. Pinned by
            # test_c11_reports_a_stat_but_emits_no_finding.
            outlier_threshold = mean_density * OUTLIER_YEAR_DENSITY_MULTIPLE
            report.stats["year_density_outliers"] = {
                stop_idx: round(density, 1)
                for stop_idx, density in sorted(stop_year_densities.items())
                if density > outlier_threshold
            }

    # ── S1: spatial claim geometry — DELIBERATELY NOT WIRED ─────────────────
    # `src/tour/spatial_check.py` exists and is tested, but it is NOT called here.
    # It was wired on 2026-07-19 and UNWIRED the same day, on measurement.
    #
    # The hole it targets is real: SemanticFactChecker entails PROPOSITIONS against
    # source facts and never sees the directional instruction wrapped around one
    # ("look down X toward Y"), so a cue can be geometrically false and still pass
    # fact-check 0-unsupported. But the module as built emits FALSE ACCUSATIONS on
    # real shipped data. Reproduced end-to-end by an adversarial reviewer against
    # unmodified `data/new_york/poi-raw.json` with the shipped extractor:
    #
    #     "Look down Wall Street toward Trinity Church."  ->  IMPLAUSIBLE
    #
    # That cue is correct. Trinity Church stands at the head of Wall Street and is
    # its single most recognisable sightline; the check rejects it because the
    # church bears 330 deg while the street axis (derived by matching POIs whose
    # names merely END WITH "Wall Street") reads 47 deg off.
    #
    # A missed cue costs nothing. A false accusation actively degrades the tour --
    # it tells an editor a true sentence is wrong, and the standard explicitly
    # rewards concrete look-cues (G1 — C10, its lexical proxy, was deleted
    # 2026-07-27 and G1 is not built), so this check would fight the very
    # property we are trying to increase. Precision must be ~100% on real data
    # before this is wired at ANY severity, including WARN.
    #
    # Also unresolved: street-axis resolution succeeds for only 2 of 13 addressed
    # NYC candidates (one of those spurious), and `data/{city}/poi-raw.json` is not
    # shipped in the production image, so the check would degrade to all-UNKNOWN in
    # prod regardless. Fix the extractor's precision first; then re-wire as WARN.

    return report


# ── compose_fixable: is a BLOCKER worth another compose pass? ───────────────
#
# The standard's naive §7 reading — "a BLOCKER regenerates the script" — treats
# BLOCKER as one predicate. It is two: (a) may this tour be SERVED (score_tour's
# ``passed``, unchanged, never touched by anything below), and (b) is looping the
# COMPOSE step for one stop worth the money. This module answers (b). A defect
# that is upstream of compose (selection picked the wrong POI, chose a bad route,
# or the audio-seconds formula structurally cannot move) will reproduce IDENTICALLY
# on a recompose — that is spend with zero chance of convergence, and for C1 it is
# actively worse than doing nothing (an under-seated stop pushed to "write more"
# invites fabrication that the entailment gate then rejects, floors to stitch, and
# ends up terser than before). ``compose_fixable`` exists so the caller can spend
# only where a recompose can plausibly change the outcome.


@dataclass(frozen=True)
class StopMaterial:
    """What the composer actually had to work with for ONE stop."""

    seated_body_words: int  # words in the beats SEATED for this stop
    composed_words: int  # words the composer actually rendered


def compose_fixable(finding: Finding, material: StopMaterial | None) -> bool:
    """True => a targeted re-compose of this stop could plausibly fix it.
    False => the defect is upstream (selection/route); recomposing burns
    money and cannot converge.

    This is a SEPARATE predicate from "is the tour servable" (``RubricReport.passed``
    / a finding's ``severity``). A BLOCKER always means do-not-serve; this function
    answers the different question of whether looping compose for the stop is worth
    the spend. See the standard's §7 amendment for why these must not be conflated.

    Fails CLOSED throughout: any severity other than BLOCKER, any unrecognised check
    id, or a check missing the structured data it needs (``material`` and, for C1,
    ``finding.context["floor"]``) all return False. This function never guesses.
    """
    if finding.severity is not Severity.BLOCKER:
        # Never loop on a WARN — nothing here is worth another compose pass over a
        # finding that only ever surfaces to the editor.
        return False

    check = finding.check

    if check == "C6-empty-stop":
        # The model emitted nothing for this stop. Always a compose-side failure —
        # there is no selection/route explanation for zero output.
        return True

    if check == "C5-verbatim-repeat":
        # Same-STOP exact dupes already die inside compose, in _dedup_composed
        # (compose.py:1061, via suppress_exact_repeats) before a script is ever
        # scored. A survivor reaching the rubric is therefore a CROSS-stop repeat —
        # only a recompose of the offending stop(s) removes it.
        return True

    if check == "C8-gorged":
        # Fixable ONLY if the COMPOSER is the one who inflated the stop past what
        # selection actually seated for it (composed_words > seated_body_words).
        # If composed_words <= seated_body_words, the overshoot is selection's
        # doing: beat_select.py:260-288 (govern_poi_beats) always keeps the first
        # seated beat even when it alone blows the per-stop allowance ("the FIRST
        # beat is always kept... the ratified bounded one-beat overshoot",
        # beat_select.py:269-271). Trimming that in compose drops a claim, the
        # coverage gate flags it, repair_composed_surgical (compose_gate.py:125,
        # spliced back in compose.py's serve path around line 1170) puts the
        # stitch back verbatim, and the stop gorges again on the next attempt — a
        # PROVEN oscillation. Never loop-eligible in that branch.
        return material is not None and material.composed_words > material.seated_body_words

    if check == "C1-starved":
        # Mirror of C8. Fixable ONLY if what was SEATED for this stop already met
        # the SAME per-POI floor score_tour computed when it raised this finding
        # (carried in finding.context["floor"] — compose_fixable's signature is
        # fixed to (finding, material), so that per-POI number, which depends on
        # the corpus's full beat count for the POI, has no other channel here).
        # seated_body_words >= floor means the COMPOSER under-used material it
        # actually had — a recompose can plausibly do better with no new risk.
        # If seated_body_words < floor, the rest of the POI's beats are sitting in
        # overflow_by_poi, never seated for this stop; telling compose to "write
        # more" invites fabrication, the entailment gate rejects it, and the stop
        # floors to stitch — strictly WORSE than the terse original. Fails closed
        # (False) if the floor was never recorded, rather than guessing.
        if material is None or finding.context is None:
            return False
        floor = finding.context.get("floor")
        if floor is None:
            return False
        return material.seated_body_words >= floor

    if check == "C3-thin":
        # PROVEN unfixable, for the BODY of the stop. generation.py:1203-1207 computes
        # the beat-derived share of total_audio_seconds from SEATED beats scaled by the
        # voiced-word fraction, min(1.0, voiced/body) — more composed BODY words can
        # only push that ratio TOWARD 1.0, never past it, so a recompose cannot close a
        # C3 gap by writing more of the beat text. This is NOT literally zero extra
        # audio, though: generation.py:1208 adds ``glue_count * 4`` seconds on top of
        # the beat total — more glue sentences (navigation/transition lines) DO add a
        # few real seconds, uncapped by the voiced/body ratio. That is also a
        # reward-hacking vector worth naming: a composer under pressure to hit a C3
        # floor could pad glue count rather than write more substance, and this check
        # would not catch it. The conclusion still holds — a targeted stop recompose
        # cannot close a C3 gap by any amount that matters — so C3 stays BLOCKER for
        # the SERVING verdict; it is merely loop-INELIGIBLE. These are different
        # predicates — see the module-level comment above.
        return False

    if check in ("C2-tier-inversion", "C12-stops-too-close"):
        # Route/selection defects, kept fail-closed here regardless of severity. C2
        # needs a different tiering/selection decision. C12 is WARN (see
        # MIN_STOP_SEPARATION_M's provenance comment — distance alone cannot tell a
        # duplicate from a genuinely close, distinct landmark), so the severity guard
        # above already returns False for it in practice; even if a future caller
        # somehow raised a C12 finding at BLOCKER, fixing it needs a stop dropped or
        # merged. Neither is something a stop-level recompose can do — the POIs and
        # their positions don't change.
        return False

    if check == "C7-time-budget":
        # Selection/budget: the walk+listening total is a routing/selection
        # quantity. Recomposing a stop's TEXT does not change
        # route.total_walk_seconds, and (per C3, generation.py:1207) it barely
        # moves total_audio_seconds either — no recompose closes an over-budget gap.
        return False

    # Unknown check id: fail CLOSED. Never spend money looping on something this
    # classifier has no positive evidence about.
    return False


__all__ = [
    "Finding",
    "RubricReport",
    "Severity",
    "StopMaterial",
    "compose_fixable",
    "score_tour",
]
