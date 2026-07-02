"""VERIFY with teeth (§2.6, M7) — provenance + faithfulness checks.

Two INDEPENDENT checks layered on top of validation.validate_script's
traceability + forbidden-phrase gates (rapidfuzz alone is not faithfulness):

1. **Provenance** (deterministic, ``rapidfuzz``): each beat's verbatim
   ``source_passage`` must fuzzy-match the source chunk it was extracted
   from, above ``PROVENANCE_MATCH_THRESHOLD``. Catches a beat whose stored
   passage drifted from (or never existed in) its cited chunk.

2. **Faithfulness** (one entailment call per stop): every beat-cited
   sentence must follow from that beat's ``key_claims``. Pluggable
   ``FaithfulnessChecker`` — ``MockFaithfulnessChecker`` (default, offline,
   trusts the corpus) keeps ``make test`` free; ``HaikuFaithfulnessChecker``
   runs the real entailment in dev/CI/prod.

Both write to ``ValidationReport`` (the Script is never mutated). A beat
that lacks ``source_passage``/``key_claims`` is SKIPPED, not failed — the
corpus extraction pipeline backfills these; until then these checks are
no-ops and the traceability/forbidden gates still apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from rapidfuzz import fuzz

from .contract import BeatRef, BeatSequence, Script, Sentence
from .generation import GLUE_REFLECTION

# A verbatim passage present in its chunk scores ~100 (partial_ratio is
# substring-tolerant); 88 leaves headroom for whitespace/punctuation drift
# while still catching a fabricated or wrong-chunk passage (which scores low).
PROVENANCE_MATCH_THRESHOLD: float = 88.0


def verify_provenance(
    beat_sequence: BeatSequence,
    chunk_text_by_slug: dict[str, str],
    *,
    threshold: float = PROVENANCE_MATCH_THRESHOLD,
) -> list[tuple[str, float]]:
    """(beat_id, score) for every provenanced beat that fails its chunk match.

    Beats with no ``source_passage``/``source_chunk_slug`` are skipped. A beat
    citing a slug absent from ``chunk_text_by_slug`` fails at score 0.0 — it
    claims provenance we cannot confirm.
    """
    failures: list[tuple[str, float]] = []
    for plan in beat_sequence.poi_beats:
        for beat in plan.beats:
            if not beat.source_passage or not beat.source_chunk_slug:
                continue
            chunk = chunk_text_by_slug.get(beat.source_chunk_slug)
            if not chunk:
                failures.append((beat.id, 0.0))
                continue
            score = fuzz.partial_ratio(beat.source_passage, chunk)
            if score < threshold:
                failures.append((beat.id, score))
    return failures


class FaithfulnessChecker(Protocol):
    """Does ``sentence_text`` follow from ``key_claims``? (entailment)"""

    def entails(self, key_claims: tuple[str, ...], sentence_text: str) -> bool: ...


class MockFaithfulnessChecker:
    """Offline default: trusts the corpus (every beat-cited sentence entails).

    Tests inject a stub to exercise failures; production wires the Haiku
    checker. Records calls so the gate's call-count can be asserted.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def entails(self, key_claims: tuple[str, ...], sentence_text: str) -> bool:
        self.calls.append((key_claims, sentence_text))
        return True


FAITHFULNESS_MODEL = "claude-haiku-4-5-20251001"
_ENTAILMENT_PROMPT = (
    "You are a strict fact-checker. Given a list of KEY CLAIMS and one "
    "SENTENCE, answer with exactly 'YES' if the sentence is fully supported "
    "by the claims, or 'NO' if it adds, contradicts, or overstates anything.\n\n"
    "KEY CLAIMS:\n{claims}\n\nSENTENCE:\n{sentence}\n\nAnswer (YES or NO):"
)


@dataclass
class HaikuFaithfulnessChecker:
    """Real one-call-per-sentence entailment via Anthropic Haiku (dev/CI/prod).

    Mirrors HaikuGlueClient: defers the anthropic import so unit tests never
    need the SDK, and only runs when wired in explicitly (Mock is the
    default everywhere else). NOT exercised by ``make test`` — its live
    behavior needs ANTHROPIC_API_KEY (set on the Render service).
    """

    model: str = FAITHFULNESS_MODEL
    max_output_tokens: int = 5
    calls: int = 0
    _client: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        import anthropic

        self._client = anthropic.Anthropic()

    def entails(self, key_claims: tuple[str, ...], sentence_text: str) -> bool:
        self.calls += 1
        rendered = _ENTAILMENT_PROMPT.format(
            claims="\n".join(f"- {c}" for c in key_claims), sentence=sentence_text
        )
        response = self._client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=self.max_output_tokens,
            messages=[{"role": "user", "content": rendered}],
        )
        text = "".join(
            getattr(b, "text", "") for b in (getattr(response, "content", []) or [])
        ).strip().upper()
        # Conservative: only an explicit YES passes; anything else fails closed.
        return text.startswith("YES")


def _visited_claims(
    script: Script,
    beats_by_id: dict[str, BeatRef],
    before_stop_idx: int,
) -> tuple[str, ...]:
    """Order-preserving, deduped union of key_claims of beats cited at
    stop_idx STRICTLY below ``before_stop_idx`` — what the walker has already
    heard when a reflection on the leg into that stop is spoken."""
    seen_claims: set[str] = set()
    seen_beats: set[str] = set()
    out: list[str] = []
    for s in script.script:
        if s.source_type != "beat" or s.stop_idx >= before_stop_idx:
            continue
        if s.source_id in seen_beats:
            continue
        seen_beats.add(s.source_id)
        beat = beats_by_id.get(s.source_id)
        if beat is None:
            continue
        for claim in beat.key_claims:
            if claim not in seen_claims:
                seen_claims.add(claim)
                out.append(claim)
    return tuple(out)


def verify_faithfulness(
    script: Script,
    beats_by_id: dict[str, BeatRef],
    checker: FaithfulnessChecker,
) -> list[tuple[Sentence, str]]:
    """(sentence, reason) for each beat-cited sentence not entailed by its
    beat's ``key_claims``. Sentences whose beat has no ``key_claims`` are
    skipped (nothing to entail against yet).

    Phase 4 (Step 4.2) — reflections are FAIL-CLOSED, unlike other glue: a
    ``GLUE_REFLECTION`` sentence must entail from the union of key_claims of
    beats cited STRICTLY BEFORE its stop (what the walker has already heard);
    an empty union is itself a failure — an unverifiable reflection never
    ships."""
    failures: list[tuple[Sentence, str]] = []
    for sentence in script.script:
        if sentence.source_type == "glue" and sentence.source_id == GLUE_REFLECTION:
            claims = _visited_claims(script, beats_by_id, sentence.stop_idx)
            if not claims:
                failures.append((sentence, "unverifiable_reflection:no_visited_claims"))
                continue
            if not checker.entails(claims, sentence.text):
                failures.append((sentence, "unfaithful_reflection"))
            continue
        if sentence.source_type != "beat":
            continue
        beat = beats_by_id.get(sentence.source_id)
        if beat is None or not beat.key_claims:
            continue
        if not checker.entails(beat.key_claims, sentence.text):
            failures.append((sentence, f"unfaithful:{sentence.source_id}"))
    return failures
