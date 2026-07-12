"""Deterministic quality scoreboard for a composed tour (backlog: sustainable
compose regression system).

Every metric is a PURE, FREE, deterministic function over the (stitched,
composed) Script pair — NO LLM, NO network — so it runs inside the normal
``make test`` bar at zero cost on anyone's API key. Each number maps to a
concrete failure class a human tester reported from the workbench.

Two layers, kept separate so this stays measurement, not a weighted score:

* :func:`quality_violations` — ABSOLUTE invariants a good tour must ALWAYS
  satisfy, independent of any baseline: no silently dropped date/number, no
  lost key_claim, no fusion that WORSENED repetition, no within-stop exact
  repeat, no em dash (TTS), and a real sign-off. Any hit is unambiguously bad.
* :func:`metric_regressions` — RELATIVE signals judged against a committed
  golden: a NEW unguided stop, MORE samey openers, MORE reverted stops, MORE
  duplicate pairs, or audio thinned past a floor. These are contextual (a tour
  legitimately has some vignettes / openers), so only a change-for-the-worse
  vs the recorded-good baseline counts.

NOT covered here (stated so nothing reads as implied coverage): cross-stop
*narrative thread* and *semantic-paraphrase* repetition (near-zero lexical
overlap) need a judge, not a deterministic count — they live in the
Fable-subagent rubric, not this module.
"""

from __future__ import annotations

import re
from itertools import pairwise

from pydantic import BaseModel

from .claim_dedup import (
    _canonicalize_dates,
    _overlap,
    _signature,
    candidate_duplicate_pairs,
    claims_realized_by,
    suppress_exact_repeats,
    verify_claim_coverage,
)
from .compose_gate import _bad_stops
from .contract import BeatRef, BeatSequence, Script, Sentence, ValidationReport
from .generation import GLUE_CLOSING, GLUE_NAV, _sum_audio

_HAS_DIGIT = re.compile(r"\d")
# The em dash (U+2014) and its longer/var cousins that mangle TTS prosody.
_EM_DASHES = ("—", "―", "⸺", "⸻")


def _numeral_tokens(text: str) -> set[str]:
    """Year/number tokens in a sentence, dates folded to century form first so
    "300 BC" and "the 3rd century BC" count as the SAME token, not two."""
    canon = _canonicalize_dates(text.lower())
    return {t for t in re.findall(r"[a-z0-9]+", canon) if _HAS_DIGIT.search(t)}


def _beat_sentences_by_stop(script: Script) -> dict[int, list[Sentence]]:
    out: dict[int, list[Sentence]] = {}
    for s in script.script:
        if s.source_type == "beat":
            out.setdefault(s.stop_idx, []).append(s)
    return out


def _first_sentence_by_stop(script: Script) -> list[tuple[int, Sentence]]:
    """The FIRST sentence of each stop, in stop order — a stop's opener."""
    seen: dict[int, Sentence] = {}
    for s in script.script:
        seen.setdefault(s.stop_idx, s)
    return [(idx, seen[idx]) for idx in sorted(seen)]


class ComposeMetrics(BaseModel):
    """A frozen, comparable snapshot of a composed tour's deterministic signals."""

    composed_dupe_pairs: int
    stitched_dupe_pairs: int
    dropped_numerals: dict[int, tuple[str, ...]]  # stop_idx -> numeral tokens lost
    coverage_loss: tuple[tuple[str, str], ...]  # (beat_id, claim_text)
    composed_exact_repeats: int
    audio_seconds_stitched: int
    audio_seconds_composed: int
    reverted_stops: tuple[int, ...]
    opener_overlaps: tuple[tuple[int, int, float], ...]  # (stop_idx, prev_idx, overlap)
    missing_guidance_stops: tuple[int, ...]
    em_dash_sentences: int
    has_closing: bool

    @property
    def audio_delta(self) -> int:
        """Spoken seconds lost (positive) or gained by compose vs the stitch."""
        return self.audio_seconds_stitched - self.audio_seconds_composed


def compute_compose_metrics(
    stitched: Script,
    composed: Script,
    beat_sequence: BeatSequence,
    beats_by_id: dict[str, BeatRef],
    *,
    report: ValidationReport | None = None,
    opener_overlap_min: float = 0.6,
) -> ComposeMetrics:
    """Measure ``composed`` against its pre-compose ``stitched`` baseline.

    ``report`` (the merged VERIFY report the gate produced for ``composed``)
    yields the TRUE reverted-stop set via ``_bad_stops`` — text equality would
    conflate a repair-revert with the model legitimately echoing a one-line
    stop. Omit it and the field is empty (revert tracking simply off).
    """
    st_beats = _beat_sentences_by_stop(stitched)
    co_beats = _beat_sentences_by_stop(composed)

    dropped: dict[int, tuple[str, ...]] = {}
    for stop_idx, st_sents in st_beats.items():
        st_nums: set[str] = set()
        for s in st_sents:
            st_nums |= _numeral_tokens(s.text)
        co_nums: set[str] = set()
        for s in co_beats.get(stop_idx, []):
            co_nums |= _numeral_tokens(s.text)
        gone = st_nums - co_nums
        if gone:
            dropped[stop_idx] = tuple(sorted(gone))

    expected = claims_realized_by(stitched, beats_by_id)
    coverage_loss = verify_claim_coverage(composed, expected, beats_by_id)

    exact_left = suppress_exact_repeats(list(composed.script), beat_sequence)
    composed_exact_repeats = len(composed.script) - len(exact_left)

    # Adjacent-stop opener overlap: does stop N open the same way as stop N-1?
    openers = _first_sentence_by_stop(composed)
    overlaps: list[tuple[int, int, float]] = []
    for (p_idx, p_s), (idx, s) in pairwise(openers):
        ov = _overlap(_signature(p_s.text), _signature(s.text))
        if ov >= opener_overlap_min:
            overlaps.append((idx, p_idx, round(ov, 3)))

    # Every CONTENT stop after the first must be one the tourist is guided TO.
    content_stops = sorted({s.stop_idx for s in composed.script if s.source_type == "beat"})
    nav_stops = {s.stop_idx for s in composed.script if s.source_id == GLUE_NAV}
    missing_guidance = tuple(idx for idx in content_stops[1:] if idx not in nav_stops)

    em_dash = sum(1 for s in composed.script if any(d in s.text for d in _EM_DASHES))
    has_closing = any(s.source_id == GLUE_CLOSING for s in composed.script)
    reverted = tuple(sorted(_bad_stops(report, stitched))) if report is not None else ()

    return ComposeMetrics(
        composed_dupe_pairs=len(candidate_duplicate_pairs(composed)),
        stitched_dupe_pairs=len(candidate_duplicate_pairs(stitched)),
        dropped_numerals=dropped,
        coverage_loss=coverage_loss,
        composed_exact_repeats=composed_exact_repeats,
        audio_seconds_stitched=_sum_audio(stitched.script, beat_sequence),
        audio_seconds_composed=_sum_audio(composed.script, beat_sequence),
        reverted_stops=reverted,
        opener_overlaps=tuple(overlaps),
        missing_guidance_stops=missing_guidance,
        em_dash_sentences=em_dash,
        has_closing=has_closing,
    )


def quality_violations(m: ComposeMetrics, *, require_closing: bool = True) -> list[str]:
    """ABSOLUTE invariants a good composed tour must satisfy. Empty == clean.

    These flip a golden RED with no baseline needed — a dropped date, a lost
    fact, worsened repetition, a within-stop exact repeat, an em dash, or a
    missing sign-off is wrong in any tour.
    """
    out: list[str] = []
    if m.dropped_numerals:
        out.append(f"dropped numerals/dates at stops {dict(m.dropped_numerals)}")
    if m.coverage_loss:
        out.append(f"{len(m.coverage_loss)} key_claim(s) voiced in stitch but lost in compose")
    if m.composed_dupe_pairs > m.stitched_dupe_pairs:
        out.append(
            f"compose WORSENED repetition: {m.composed_dupe_pairs} dup pairs vs "
            f"{m.stitched_dupe_pairs} in stitch"
        )
    if m.composed_exact_repeats:
        out.append(f"{m.composed_exact_repeats} exact-repeat sentence(s) within a stop")
    if m.em_dash_sentences:
        out.append(f"{m.em_dash_sentences} sentence(s) contain an em dash (TTS hazard)")
    if require_closing and not m.has_closing:
        out.append("tour has no GLUE_CLOSING sign-off (ends on a whimper)")
    return out


def metric_regressions(
    current: ComposeMetrics,
    golden: ComposeMetrics,
    *,
    audio_ratio_floor: float = 0.9,
) -> list[str]:
    """RELATIVE regressions of ``current`` against a committed-good ``golden``.

    Contextual signals (a tour legitimately has some vignettes, openers,
    reverts) where only a change-for-the-worse is a regression: a stop that LOST
    its guidance, MORE samey openers, MORE reverted stops, MORE duplicate pairs,
    or audio thinned below ``audio_ratio_floor`` of the golden. Empty == no
    regression.
    """
    out: list[str] = []
    new_unguided = set(current.missing_guidance_stops) - set(golden.missing_guidance_stops)
    if new_unguided:
        out.append(f"stops newly reached with no guidance: {sorted(new_unguided)}")
    if len(current.opener_overlaps) > len(golden.opener_overlaps):
        out.append(
            f"more samey openers than golden: {len(current.opener_overlaps)} "
            f"vs {len(golden.opener_overlaps)}"
        )
    if len(current.reverted_stops) > len(golden.reverted_stops):
        out.append(
            f"more reverted stops than golden: {len(current.reverted_stops)} "
            f"vs {len(golden.reverted_stops)}"
        )
    if current.composed_dupe_pairs > golden.composed_dupe_pairs:
        out.append(
            f"more duplicate pairs than golden: {current.composed_dupe_pairs} "
            f"vs {golden.composed_dupe_pairs}"
        )
    if (
        golden.audio_seconds_composed > 0
        and current.audio_seconds_composed < golden.audio_seconds_composed * audio_ratio_floor
    ):
        out.append(
            f"audio thinned vs golden: {current.audio_seconds_composed}s "
            f"< {audio_ratio_floor:.0%} of {golden.audio_seconds_composed}s"
        )
    return out


__all__ = [
    "ComposeMetrics",
    "compute_compose_metrics",
    "metric_regressions",
    "quality_violations",
]
