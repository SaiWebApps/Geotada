"""Source-traceability + forbidden-phrase validation — §3.5/§3.6.

Runs after ``generate(...)`` and produces a ``ValidationReport``. The
caller (skill orchestrator, CLI, or test harness) treats a non-empty
report as a hard failure — these checks are the gate between
generation and TTS per phase-1-design rule 8.

Two independent checks:

1. **Source-traceability.** Every Sentence must satisfy one of:
   - ``source_type == 'beat'`` and ``source_id`` is a known beat ID in
     the BeatSequence; OR
   - ``source_type in {'glue','arith'}`` and ``source_id`` is a member
     of ``generation.GLUE_LABELS``.
   Anything else lands in ``untraceable_sentences``.

2. **Forbidden-phrase scan.** Glue sentences may not contain
   "imagine" / "picture this" / "envision" / "visualize" (rule 32 +
   feedback_tour_tone_default). Glue sentences may not introduce a
   proper noun or 4-digit year that does not appear in any cited
   beat's ``script_body`` from the same Script.

Beat-cited sentences are NOT scanned for forbidden words — the corpus
itself is canonical, and editorial review caught those at extraction
time. Validation guards against runtime invention only.
"""

from __future__ import annotations

import re

from .contract import BeatSequence, Script, Sentence, ValidationReport
from .generation import FORBIDDEN_PHRASES, GLUE_LABELS

# Capitalized tokens past the first word are candidate proper nouns.
# Limited to 3+ letters so single-letter "I" and "A" don't trip it. The
# accent class admits the diacritics that show up in French names.
_CAP_TOKEN_RE = re.compile(r"\b[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'\-]{2,}\b")
_YEAR_RE = re.compile(r"\b1[0-9]{3}\b|\b20[0-2][0-9]\b")

# Common English/French sentence-starter words that shouldn't count as
# proper nouns when they appear capitalized at the head of a sentence.
_SENTENCE_HEAD_WORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "but",
        "or",
        "so",
        "for",
        "yet",
        "this",
        "that",
        "these",
        "those",
        "here",
        "there",
        "you",
        "your",
        "we",
        "our",
        "i",
        "walk",
        "stand",
        "step",
        "find",
        "look",
        "turn",
        "press",
        "now",
        "next",
        "then",
        "settle",
        "take",
        "stop",
        "end",
        "cross",
        "exit",
        "le",
        "la",
        "les",
        "un",
        "une",
        "des",
        "du",
        "de",
        "you've",
        "we've",
        "let's",
    }
)


def validate_script(script: Script, beat_sequence: BeatSequence) -> ValidationReport:
    """Run both gates and return the report."""
    traceability = validate_source_traceability(script, beat_sequence)
    forbidden = _forbidden_phrase_hits(script, beat_sequence)
    return traceability.model_copy(
        update={"forbidden_phrase_hits": tuple(forbidden)}
    )


def validate_source_traceability(
    script: Script,
    beat_sequence: BeatSequence,
    *,
    allowed_derived_source_ids: frozenset[str] | None = None,
) -> ValidationReport:
    """Structural provenance only; semantic FACT review owns prose meaning."""
    return ValidationReport(
        untraceable_sentences=tuple(
            _untraceable_sentences(
                script,
                beat_sequence,
                allowed_derived_source_ids=allowed_derived_source_ids,
            )
        )
    )


# ---------------------------------------------------------------------------
# Source-traceability
# ---------------------------------------------------------------------------


def _untraceable_sentences(
    script: Script,
    beat_sequence: BeatSequence,
    *,
    allowed_derived_source_ids: frozenset[str] | None = None,
) -> list[Sentence]:
    # Track B (B.4): the known-id set derives from poi_beats + vignette_beats
    # INTERNALLY — a walk-past one-liner is beat-cited against a vignette
    # beat, which is not a POIBeats entry. The signature does not change.
    known_beat_ids = {b.id for plan in beat_sequence.poi_beats for b in plan.beats}
    known_beat_ids |= {b.id for beats in beat_sequence.vignette_beats.values() for b in beats}
    derived_source_ids = (
        GLUE_LABELS
        if allowed_derived_source_ids is None
        else allowed_derived_source_ids
    )
    out: list[Sentence] = []
    for sentence in script.script:
        if sentence.source_type == "beat":
            # Multi-beat citation: the primary AND every fused (also_cites) id
            # must trace to a real beat.
            if any(bid not in known_beat_ids for bid in sentence.cited_beat_ids):
                out.append(sentence)
        elif sentence.source_type in ("glue", "arith"):
            if sentence.source_id not in derived_source_ids:
                out.append(sentence)
        else:
            out.append(sentence)
    return out


# ---------------------------------------------------------------------------
# Forbidden-phrase scan
# ---------------------------------------------------------------------------


def _forbidden_phrase_hits(
    script: Script, beat_sequence: BeatSequence
) -> list[tuple[Sentence, str]]:
    out: list[tuple[Sentence, str]] = []
    cited_text = _cited_beat_corpus_text(script, beat_sequence)
    cited_proper_nouns = _proper_nouns_in(cited_text)
    cited_years = set(_YEAR_RE.findall(cited_text))

    for sentence in script.script:
        if sentence.source_type == "beat":
            continue  # corpus is canonical; only scan glue
        lower = sentence.text.lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase in lower:
                out.append((sentence, f"forbidden_phrase:{phrase}"))

        # Proper-noun + year leakage in glue.
        for token in _proper_nouns_in(sentence.text, drop_first_word=True):
            if token.lower() in _SENTENCE_HEAD_WORDS:
                continue
            if token in cited_proper_nouns:
                continue
            out.append((sentence, f"new_proper_noun:{token}"))
        for year in _YEAR_RE.findall(sentence.text):
            if year in cited_years:
                continue
            out.append((sentence, f"new_year:{year}"))
    return out


def _cited_beat_corpus_text(script: Script, beat_sequence: BeatSequence) -> str:
    cited_ids: set[str] = {s.source_id for s in script.script if s.source_type == "beat"}
    chunks: list[str] = []
    for plan in beat_sequence.poi_beats:
        chunks.append(plan.poi_name)  # the POI's own name is canonical context
        for beat in plan.beats:
            if beat.id in cited_ids:
                if beat.script_body:
                    chunks.append(beat.script_body)
                # Phase 4 (Step 4.2): key_claims are corpus-derived facts a
                # reflection legitimately quotes; their proper nouns/years are
                # canonical context, same class as cues/pronunciation.
                chunks.extend(beat.key_claims)
            # Phase 7.5: physical_cues + pronunciation are corpus-derived
            # facts that can surface in the synthesized cold-open. Include
            # them in canonical context so glue-validation doesn't flag
            # cue proper nouns ("Café Ma Bourgogne") as runtime invention.
            for cue in beat.physical_cues:
                if cue.cue:
                    chunks.append(cue.cue)
            if beat.pronunciation:
                chunks.append(beat.pronunciation)
    # Track B (B.4): cited vignette beats are corpus text too — their
    # script_body/key_claims join the canonical context exactly like
    # anchor-beat text (the walk-past one-liner is beat-cited, and glue may
    # legitimately reference facts the corpus already voiced).
    for beats in beat_sequence.vignette_beats.values():
        for beat in beats:
            if beat.id in cited_ids:
                if beat.script_body:
                    chunks.append(beat.script_body)
                chunks.extend(beat.key_claims)
    # Phase 7.5: Area names that surface in the synthesized opener
    # ("the Marais", "the Île de la Cité") are canonical context too.
    for poi in script.selected_pois:
        if poi.area:
            chunks.append(poi.area)
    return "\n".join(chunks)


def _proper_nouns_in(text: str, *, drop_first_word: bool = False) -> set[str]:
    """Return the set of capitalized multi-letter tokens.

    When ``drop_first_word=True``, the first word of every sentence is
    excluded so that mere sentence-start capitalization doesn't read as
    a proper noun.
    """
    if not text:
        return set()
    if not drop_first_word:
        return set(_CAP_TOKEN_RE.findall(text))

    out: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        tokens = _CAP_TOKEN_RE.findall(sentence)
        if not tokens:
            continue
        # Skip the first capitalized token (sentence-start position).
        # Any token after the first that is also capitalized is a real
        # candidate proper noun — even if the sentence is short.
        first_match = _CAP_TOKEN_RE.search(sentence)
        if first_match is None:
            continue
        first_span_end = first_match.end()
        rest = sentence[first_span_end:]
        out.update(_CAP_TOKEN_RE.findall(rest))
    return out


__all__ = ["validate_script"]
