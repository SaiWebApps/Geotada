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
import unicodedata

from .contract import BeatSequence, Script, Sentence, ValidationReport
from .generation import (
    FORBIDDEN_PHRASES,
    FORWARD_PROMISE_PHRASES,
    FORWARD_SIGHT_PHRASES,
    GLUE_LABELS,
    GLUE_NAV,
)

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


def validate_script(
    script: Script,
    beat_sequence: BeatSequence,
    *,
    spine_area: str | None = None,
) -> ValidationReport:
    """Run both gates and return the report."""
    traceability = validate_source_traceability(script, beat_sequence)
    forbidden = _forbidden_phrase_hits(script, beat_sequence, spine_area=spine_area)
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
    script: Script,
    beat_sequence: BeatSequence,
    *,
    spine_area: str | None = None,
) -> list[tuple[Sentence, str]]:
    out: list[tuple[Sentence, str]] = []
    cited_text = _cited_beat_corpus_text(script, beat_sequence)
    cited_proper_nouns = _proper_nouns_in(cited_text)
    # THE TOUR'S OWN PLACE VOCABULARY IS NOT AN INVENTION. This scan exists to
    # catch glue asserting a fact the corpus never gave it — a name, a date, a
    # claim the walker cannot check. The names of the stops the engine SEATED, and
    # of the areas they sit in, are corpus records the engine chose the route from;
    # they are the one vocabulary glue is entitled to use.
    #
    # Without this, the synthesized opener fails whenever the spine area's name
    # happens not to appear inside a cited beat's body — "You're starting in
    # Opéra-Garnier" was flagged on the 300-minute Rue Royale tour purely because
    # the beats about its stops never spell the neighbourhood out. That is a
    # validation FAILURE on a correct tour, which is worse than no check: it
    # teaches whoever reads the report to ignore it.
    for stop in script.selected_pois:
        cited_proper_nouns |= _proper_nouns_in(stop.name)
        if stop.area:
            cited_proper_nouns |= _proper_nouns_in(stop.area)
    # The SPINE is the neighbourhood the walk starts in, and it is not always one
    # any stop belongs to — a Rue Royale tour starts in Opéra-Garnier and its first
    # stop is already in the 1st. The opener's whole job is to say where the walker
    # is standing, so it has to be allowed to name that, and the name is the
    # engine's own choice from the corpus rather than anything glue made up.
    if spine_area:
        cited_proper_nouns |= _proper_nouns_in(spine_area)
    # THE CITY'S OWN NAME AND DEMONYM ARE THE WALK'S VOCABULARY (Phase 6 W6.12,
    # measured: "the height of Parisian luxury" in an authored close was refused as
    # new_proper_noun:Parisian, three attempts, the day dead). The tour's own city
    # can never be an invention.
    cited_proper_nouns |= _city_vocabulary(script.city_slug)
    cited_years = set(_YEAR_RE.findall(cited_text))

    # Phase 6 S6.5 (W6.2 R4): the names of stops LATER than each stop index — a
    # "you'll see"-class phrase is a promise only when it points past the stop.
    stop_names = [poi.name for poi in script.selected_pois]

    def _names_a_later_stop(text: str, stop_idx: int) -> bool:
        folded = _fold(text).lower()
        return any(
            _fold(name).lower() in folded
            for name in stop_names[stop_idx + 1 :]
            if name
        )

    for sentence in script.script:
        if sentence.source_type == "beat":
            continue  # corpus is canonical; only scan glue
        lower = sentence.text.lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase in lower:
                out.append((sentence, f"forbidden_phrase:{phrase}"))

        # Phase 6 S6.5 (W6.2 R4, LOCKED 8/11): a stop's text may NAME its neighbour
        # as a fact but never PROMISE it — the session may trade the next stop away.
        # GLUE_NAV is the map speaking ("Next, walk to X" is its job) and is exempt.
        if sentence.source_id != GLUE_NAV:
            for phrase in FORWARD_PROMISE_PHRASES:
                if phrase in lower:
                    out.append((sentence, f"forward_promise:{phrase}"))
            for phrase in FORWARD_SIGHT_PHRASES:
                if phrase in lower and _names_a_later_stop(sentence.text, sentence.stop_idx):
                    out.append((sentence, f"forward_promise:{phrase}"))

        # Proper-noun + year leakage in glue. GLUE_NAV is exempt from the
        # proper-noun half (Phase 6 W6.12, measured: "Walk northwest along the
        # Seine" was refused as new_proper_noun:Seine): the nav line is the MAP
        # speaking — its nouns are places by nature, exactly as the
        # forward-promise scan already treats it. Years and the phrase list
        # still apply to it; story glue keeps the full scan.
        if sentence.source_id == GLUE_NAV:
            for year in _YEAR_RE.findall(sentence.text):
                if year not in cited_years:
                    out.append((sentence, f"new_year:{year}"))
            continue
        for token in _proper_nouns_in(sentence.text, drop_first_word=True):
            if token.lower() in _SENTENCE_HEAD_WORDS:
                continue
            if _name_is_licensed(token, cited_proper_nouns):
                continue
            out.append((sentence, f"new_proper_noun:{token}"))
        for year in _YEAR_RE.findall(sentence.text):
            if year in cited_years:
                continue
            out.append((sentence, f"new_year:{year}"))
    return out


#: The city's own name and demonym, licensed for glue in every tour of that city.
#: Keyed by city_slug; an unknown slug licenses its title-cased form alone.
_CITY_VOCABULARY: dict[str, tuple[str, ...]] = {
    "paris": ("Paris", "Parisian", "Parisians"),
    "london": ("London", "Londoner", "Londoners"),
    "new_york": ("New", "York", "Yorker", "Yorkers"),
}


def _city_vocabulary(city_slug: str | None) -> set[str]:
    if not city_slug:
        return set()
    return set(
        _CITY_VOCABULARY.get(
            city_slug.lower(), (city_slug.replace("_", " ").title(),)
        )
    )


# The possessive, plural and plural-possessive endings the composer writes onto a
# name — "Ravaillac's knife", "Ravaillac\u2019s" (the curly apostrophe), "the Ravaillacs'"
# (the tokenizer drops a trailing bare apostrophe, so that one arrives as "Ravaillacs").
_POSSESSIVE_ENDINGS: tuple[str, ...] = ("'s", "\u2019s", "s'", "s\u2019", "s", "'", "\u2019")


def _fold(name: str) -> str:
    """A name without its diacritics — "André" and "Andre" are one name."""
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", name) if not unicodedata.combining(ch)
    )


def _name_is_licensed(token: str, licensed: set[str]) -> bool:
    """Is ``token`` a name the cited corpus carries — in ANY orthographic form?

    An INFLECTED or RE-ACCENTED form of a licensed name is the same name, not a new
    one: the tokenizer (``_CAP_TOKEN_RE``) keeps an apostrophe-s inside the token, so
    "Ravaillac's" was compared against a set holding "Ravaillac" and refused as an
    invention; "André" was refused against a corpus that spells "Andre". Measured
    2026-08-19 (Phase 6 W6.1): Fiona & Dev's compose was refused over the wire, every
    attempt, for "…died under Francis Ravaillac's knife" and "André Maurois ranks
    him…" — reflections drawing on a voiced beat's own key claims. Fold diacritics,
    strip the possessive/plural endings, compare again; a genuinely different name
    ("François" for a corpus that says "Francis") still fails — that is a rename, and
    the prompt's own rule is to use the name the beats give.
    """
    if token in licensed:
        return True
    folded = {_fold(name) for name in licensed}
    candidates = [token]
    for ending in _POSSESSIVE_ENDINGS:
        if token.endswith(ending) and len(token) > len(ending) + 2:
            bare = token[: -len(ending)]
            candidates.append(bare)
            if ending in ("s'", "s\u2019"):
                candidates.append(f"{bare}s")
    # A HYPHENATED COMPOUND whose capitalised head is licensed is that name in
    # adjectival dress, not a new one (Phase 6 W6.12, measured on Camille's day:
    # "From a Roman-style arch for Napoleon…" was refused as
    # new_proper_noun:Roman-style against a corpus that says "Roman" freely).
    if "-" in token:
        candidates.extend(part for part in token.split("-") if part and part[0].isupper())
    return any(c in licensed or _fold(c) in folded for c in candidates)


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
