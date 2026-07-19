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
from src.tour.routing import AUDIO_FRACTION, ERR_SHORT

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

#: CITED (adapted). Museum practice caps a station at 250 words (~2 min). A walking-tour
#: anchor with a 5-min dwell is not a museum station, so we adapt to 750 words ≈ 5 min
#: at 150 wpm. The standard states plainly that this is an adaptation, not a citation.
GORGE_MAX_WORDS_PER_STOP: int = 750

#: CITED. Nubart / Musa Guide: keep sentences to 10-15 words for the ear.
MAX_SENTENCE_WORDS: float = 15.0

#: CITED. 130-150 words per minute of spoken narration.
WORDS_PER_MINUTE: float = 150.0

#: JUDGEMENT. No single stop should hold more than this share of the tour's words.
BALANCE_MAX_SHARE: float = 0.60

#: JUDGEMENT, from a MEASURED absurdity. An acceptance pass on a real Île de la Cité
#: tour found Palais de Justice and Conciergerie seated as SEPARATE stops **17 metres
#: apart** — the same building complex — where the second stop opens by saying "the
#: Conciergerie is one of the few remaining vestiges of the old medieval Palais de
#: Justice", i.e. describing the spot the listener stood on seconds earlier. Two stops
#: that close are one stop.
#:
#: RECALIBRATED from 100 m to 50 m on evidence: at 100 m this also flagged
#: Sainte-Chapelle at 86 m from the Conciergerie, and that is a FALSE POSITIVE —
#: Sainte-Chapelle is a genuinely distinct attraction, and 86 m is a real (if short)
#: walk in a dense historic quarter. 50 m is roughly 40 seconds at 4 km/h: below that
#: the listener has not meaningfully moved. Chosen to separate the two MEASURED cases
#: (17 m = defect, 86 m = legitimate), not to make a check pass.
MIN_STOP_SEPARATION_M: float = 50.0

#: JUDGEMENT. Ceiling on the C1 starvation floor, as a share of the gorge cap, so C1
#: and C8 can never demand contradictory things for a beat-rich POI. See the comment
#: at the C1 check for the Notre-Dame arithmetic that forced this.
STARVE_FLOOR_MAX_SHARE_OF_CAP: float = 0.5

#: INHERITED from src/tour/selection.py FILL_PASS_AUDIO_FLOOR_FRAC. Not a new number:
#: the engine's own fill pass already treats 0.8 of the audio target as the floor.
AUDIO_FLOOR_FRAC: float = 0.8


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
    for sentence in script.script:
        words_by_stop[sentence.stop_idx] = words_by_stop.get(sentence.stop_idx, 0) + _words(
            sentence.text
        )

    total_words = sum(words_by_stop.values())
    report.stats = {
        "total_words": total_words,
        "n_stops": len(words_by_stop),
        "audio_minutes": round(script.total_audio_seconds / 60, 1),
        "words_by_stop": dict(sorted(words_by_stop.items())),
    }

    # ── C3: thin tour — delivered audio against the engine's own target ─────
    # INHERITED thresholds, not new ones: the engine plans to ERR_SHORT (0.83) of the
    # requested duration and targets AUDIO_FRACTION (0.60) of that as spoken audio;
    # its own fill pass treats FILL_PASS_AUDIO_FLOOR_FRAC (0.8) of that target as the
    # floor. A tour under the floor is one the tourist walks in silence — the very
    # defect that made a 60-min request deliver 13.3 min. Without this the rubric
    # BLESSES a starved tour, which it did on a 2-stop / 9.4-min run.
    duration_min = getattr(script.inputs, "duration_min", 0) or 0
    if duration_min:
        target_s = duration_min * ERR_SHORT * AUDIO_FRACTION * 60
        floor_s = target_s * AUDIO_FLOOR_FRAC
        report.stats["audio_target_min"] = round(target_s / 60, 1)
        report.stats["audio_floor_min"] = round(floor_s / 60, 1)
        if script.total_audio_seconds < floor_s:
            report.findings.append(
                Finding(
                    check="C3-thin",
                    severity=Severity.BLOCKER,
                    message=(
                        f"{script.total_audio_seconds / 60:.1f} min of audio for a "
                        f"{duration_min}-min request (floor {floor_s / 60:.1f} min, "
                        f"target {target_s / 60:.1f} min) — the tourist walks in silence"
                    ),
                )
            )

    # ── C6: no empty stop ───────────────────────────────────────────────────
    for stop_idx, words in sorted(words_by_stop.items()):
        if words == 0:
            report.findings.append(
                Finding(
                    check="C6-empty-stop",
                    severity=Severity.BLOCKER,
                    message="stop rendered zero words",
                    stop_idx=stop_idx,
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

    # ── C12: two anchors too close to be separate stops ─────────────────────
    # Consecutive anchors only: a tour legitimately revisits an area, but two
    # ADJACENT stops within MIN_STOP_SEPARATION_M are the same place told twice.
    pois = list(script.selected_pois)
    for i in range(len(pois) - 1):
        a, b = pois[i], pois[i + 1]
        metres = _haversine_m(a.lat, a.lng, b.lat, b.lng)
        if metres < MIN_STOP_SEPARATION_M:
            report.findings.append(
                Finding(
                    check="C12-stops-too-close",
                    severity=Severity.BLOCKER,
                    message=(
                        f"{metres:.0f} m from the previous stop ({a.name}) — too close to "
                        f"be a separate stop; the listener has not moved"
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

    return report
