"""Semantic CLAIM-REPETITION detection for assembled tour narration.

THE DEFECT. A stop seats beats from several source books that each restate the same
historical fact in completely different words. Measured on
``data/paris/tours/pont-neuf-60min-5afc2e.md``, Henri IV's nickname is glossed FOUR
times at one stop, from four different beats:

    "named for Henri IV, the lusty gallant on horseback"
    "Vert-Galant - meaning a green or lusty gentleman - is a reference to the king's
     legendary amorous exploits"
    "The nickname Vert-Galant - the Green Gallant - honours the king's famously
     amorous career"
    "Henri IV's early amorous adventures had earned him the affectionate nickname of
     le Vert Galant"

WHY THE EXISTING LEXICAL PASS CANNOT SEE IT. ``claim_dedup.py`` matches canonical-token
signatures; a 4-gram Jaccard detector at threshold 0.18 finds **ZERO** duplicate pairs
across all 107 narration sentences of that tour. Lexical overlap is ~0 while semantic
overlap is ~100%. Word-matching for a MEANING-level question is a banned shortcut in this
project (CLAUDE.md), and rightly so: it is unfixable by tuning, because the signal simply
is not in the words.

THE DESIGN - two stages that must never be blurred:

STAGE 1, CANDIDATE GENERATION (``generate_candidates``) - $0, deterministic, no LLM.
    Pairs are proposed from STRUCTURE, not from meaning: two sentences that reference the
    same salient ENTITY are a candidate pair. Entity references come from the corpus
    itself (``BeatRef.entities``, backfilled by the extraction pipeline), optionally
    augmented by surface mentions of those same known entity strings. This stage is
    deliberately RECALL-ORIENTED and over-generates - a candidate is a QUESTION for the
    judge ("do these two say the same thing?"), never an answer. Over-generating costs a
    judge call; under-generating loses a real duplicate forever, so generosity is correct.

STAGE 2, SEMANTIC ADJUDICATION (``RedundancyJudge``) - the verdict, and the ONLY thing
    that decides redundancy. A model judges whether the pair asserts the SAME FACT.
    Mirrors the established ``factcheck.py`` shape: a narrow injectable Protocol,
    ``HaikuRedundancyJudge`` with temperature=0 and a 5-token cap for the live path, and a
    deferred ``anthropic`` import so this module imports with no network and no API key.

Nothing here decides policy. ``RepetitionReport`` is a RICH, reportable result - every
candidate pair, the judge's verdict on each, per-stop summaries, and the transitive
clusters of mutually-redundant sentences - so a caller can render a review, pick which
occurrence to keep, or gate. Not wired into the production pipeline.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol

from .contract import BeatRef
from .generation import split_sentences
from .verify import FAITHFULNESS_MODEL

_MAX_WORKERS = 8


# --------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class NarrationSentence:
    """One spoken sentence of assembled narration, carrying the STRUCTURAL provenance
    stage 1 keys off. ``entities`` are the source beat's corpus-declared entities - not
    anything parsed out of the prose."""

    text: str
    stop_id: str = ""
    beat_id: str = ""
    entities: tuple[str, ...] = ()
    index: int = -1


def sentences_from_beats(
    beats: Iterable[BeatRef], *, stop_id: str = ""
) -> tuple[NarrationSentence, ...]:
    """Explode beats into per-sentence records, each inheriting its beat's declared
    entities. Convenience for callers holding a ``BeatSequence``; the detector itself
    accepts any ``NarrationSentence`` sequence. ``index`` is assigned in stream order."""
    out: list[NarrationSentence] = []
    for beat in beats:
        for sent in split_sentences(beat.script_body or ""):
            text = sent.strip()
            if not text:
                continue
            out.append(
                NarrationSentence(
                    text=text,
                    stop_id=stop_id or beat.poi_id,
                    beat_id=beat.id,
                    entities=tuple(beat.entities),
                    index=len(out),
                )
            )
    return tuple(out)


# --------------------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------------------


SHARED_ENTITY = "shared_entity"
SPARSE_ENTITIES = "sparse_entities"


@dataclass(frozen=True)
class CandidatePair:
    """A stage-1 proposal: these two sentences MIGHT restate the same fact. Carries no
    verdict. ``a`` is always the earlier index. ``reason`` records WHY it was proposed -
    ``SHARED_ENTITY`` (they name the same salient entity) or ``SPARSE_ENTITIES`` (at least
    one side is under-described in the corpus, so it is paired defensively)."""

    a: int
    b: int
    shared_entities: tuple[str, ...]
    stop_id: str = ""
    reason: str = SHARED_ENTITY

    @property
    def key(self) -> tuple[int, int]:
        return (self.a, self.b)


@dataclass(frozen=True)
class PairVerdict:
    """A stage-2 adjudication of one candidate pair. ``redundant`` is the judge's word,
    never the candidate generator's."""

    pair: CandidatePair
    redundant: bool
    a_text: str = ""
    b_text: str = ""


@dataclass(frozen=True)
class StopRedundancy:
    """Per-stop summary. ``clusters`` are transitive groups of mutually-redundant sentence
    indices (the four Vert-Galant sentences form ONE cluster of four, not six pairs), which
    is what a reporting caller actually wants: 'this fact is told 4 times here'."""

    stop_id: str
    sentence_count: int
    candidate_count: int
    redundant_pairs: tuple[PairVerdict, ...] = ()
    clusters: tuple[tuple[int, ...], ...] = ()

    @property
    def repeated_sentence_count(self) -> int:
        """Sentences that are a REPEAT of an earlier one (cluster size minus the first
        telling). The number of sentences a caller could drop without losing a fact."""
        return sum(len(c) - 1 for c in self.clusters)

    @property
    def redundancy_ratio(self) -> float:
        if not self.sentence_count:
            return 0.0
        return self.repeated_sentence_count / self.sentence_count


@dataclass(frozen=True)
class RepetitionReport:
    """The full, reportable result: everything stage 1 proposed, everything stage 2 ruled,
    and the per-stop rollup. Deterministically ordered throughout."""

    sentences: tuple[NarrationSentence, ...] = ()
    candidates: tuple[CandidatePair, ...] = ()
    verdicts: tuple[PairVerdict, ...] = ()
    stops: tuple[StopRedundancy, ...] = ()
    judge_calls: int = 0

    @property
    def redundant_pairs(self) -> tuple[PairVerdict, ...]:
        return tuple(v for v in self.verdicts if v.redundant)

    @property
    def clusters(self) -> tuple[tuple[int, ...], ...]:
        out: list[tuple[int, ...]] = []
        for stop in self.stops:
            out.extend(stop.clusters)
        return tuple(sorted(out))

    def passed(self) -> bool:
        """No adjudicated repetition anywhere. Advisory - callers decide policy."""
        return not self.redundant_pairs


# --------------------------------------------------------------------------------------
# Stage 2 - the semantic judge (the only thing that rules on MEANING)
# --------------------------------------------------------------------------------------


class RedundancyJudge(Protocol):
    """Do these two narration sentences assert the SAME underlying FACT - such that a
    listener hearing both learns nothing new the second time? Narrow by design so callers
    inject either ``HaikuRedundancyJudge`` or an offline stub."""

    def same_fact(self, a: str, b: str) -> bool: ...


# Prompt shape mirrors factcheck.py's judges: all instruction in the user turn, one-word
# verdict, so a 5-token cap at temperature=0 is enough. The distinction it must hold is
# SAME FACT vs MERELY SAME SUBJECT - the failure mode of a mechanical entity matcher.
_REDUNDANCY_JUDGE_USER = (
    "You are a strict REPETITION judge for spoken audio-tour narration. You are given TWO"
    " sentences from the same tour. Decide ONE thing: do they assert the SAME underlying "
    "FACT, so that a listener who already heard the first learns NOTHING NEW from the sec"
    "ond?\n\nAnswer YES when both sentences deliver the same essential payload - the same "
    "who / what / when / where and the same relationship among them - even if the wording"
    " shares no words at all. Completely different phrasing is still YES when the fact is "
    "the same: an epithet glossed as \"the lusty gallant\" and the same epithet glossed as"
    " \"a reference to the king's amorous exploits\" are the SAME FACT. A restatement that"
    " merely adds colour, a translation of the same name, or a retelling from a different "
    "book is still the SAME FACT.\n\nAnswer NO when the second sentence delivers a fact th"
    "e first did not. In particular, answer NO whenever the two sentences are merely ABOUT"
    " THE SAME SUBJECT but assert DIFFERENT things about it - a different event, date, num"
    "ber, cause, consequence, or relationship. Two sentences about one person, one buildin"
    "g, or one bridge are NOT redundant just because they share that subject: \"Henri IV s"
    "igned the Edict of Nantes in 1598\" and \"Henri IV was stabbed by Ravaillac\" are DIF"
    "FERENT facts. Answer NO if either sentence carries a specific - a name, date, number,"
    " or asserted relationship - that the other never conveys in any form.\n\nJudge only w"
    "hat the two sentences actually say; never fill a gap with outside knowledge.\n\nSENTE"
    "NCE A:\n{a}\n\nSENTENCE B:\n{b}\n\nDo A and B assert the SAME fact? Output EXACTLY on"
    "e word - YES or NO - and nothing else.\nAnswer (YES or NO):"
)


class HaikuRedundancyJudge:
    """Real Haiku redundancy judgement (deterministic: temp=0, 5-token cap). Defers the
    ``anthropic`` import so this module imports with no SDK, no network and no API key;
    the client is only constructed on the live path. Mirrors ``HaikuFaithfulnessJudge``."""

    def __init__(self, model: str = FAITHFULNESS_MODEL, *, client: object = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.calls = 0

    def same_fact(self, a: str, b: str) -> bool:
        if not a.strip() or not b.strip():
            return False
        self.calls += 1
        resp = self._client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=5,
            temperature=0,  # deterministic: a pair's verdict must not flip between a
            # detection run and the post-repair re-check, or a repair loop never
            # converges (same rationale as factcheck.py's judges).
            messages=[{"role": "user", "content": _REDUNDANCY_JUDGE_USER.format(a=a, b=b)}],
        )
        text = "".join(
            getattr(b_, "text", "") for b_ in (getattr(resp, "content", []) or [])
        ).strip().upper()
        return text.startswith("YES")


# --------------------------------------------------------------------------------------
# Stage 1 - candidate generation from STRUCTURE ($0, deterministic, no LLM)
# --------------------------------------------------------------------------------------


def normalize_entity(name: str) -> str:
    """Fold an entity NAME to a comparison key: accents stripped, lowercased, punctuation
    to spaces, whitespace collapsed, and proper-noun SPELLING variants folded.

    This canonicalizes an IDENTIFIER's surface form ("Vert-Galant", "vert galant",
    "Vert Galant" -> one key); it makes no claim about meaning. The variant fold exists
    because the real corpus spells one referent two ways - 'Henri IV' in beat 1fbeb1b3 and
    'Henry IV' in the Pont Neuf beats - and exact string intersection silently loses every
    pair across that split. Folding a token's final ``y`` to ``i`` unifies the Henri/Henry
    class. This is deliberately STRUCTURAL (orthography only); semantic entity resolution
    is NOT attempted here - deciding that two differently-named things are the same thing
    is the judge's job, not the candidate generator's.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    folded = "".join(ch if ch.isalnum() else " " for ch in stripped.lower())
    return " ".join(_fold_spelling_variant(tok) for tok in folded.split())


def _fold_spelling_variant(token: str) -> str:
    """Orthographic variant fold for a single token. Final ``y`` -> ``i`` (Henry/Henri,
    Mary/Marie-class endings). Guarded to tokens long enough that the fold cannot collapse
    unrelated short words."""
    if len(token) > 3 and token.endswith("y"):
        return f"{token[:-1]}i"
    return token


def _mentions(text: str, entity_key: str) -> bool:
    """Does the normalized sentence contain the normalized entity as a whole-token run?
    A recall aid for stage 1 only, over a CLOSED vocabulary of corpus-declared entity
    names - it answers 'is this entity referenced here?', never 'do these mean the same?'.
    """
    if not entity_key:
        return False
    haystack = f" {normalize_entity(text)} "
    return f" {entity_key} " in haystack


def _entity_keys_for(
    sentence: NarrationSentence, vocabulary: Sequence[tuple[str, str]], *, surface: bool
) -> frozenset[str]:
    keys = {normalize_entity(e) for e in sentence.entities if normalize_entity(e)}
    if surface:
        for key, _display in vocabulary:
            if key not in keys and _mentions(sentence.text, key):
                keys.add(key)
    return frozenset(keys)


def generate_candidates(
    sentences: Sequence[NarrationSentence],
    *,
    min_shared_entities: int = 1,
    cross_stop: bool = False,
    surface_mentions: bool = True,
    max_entity_frequency: float = 1.0,
    pair_sparse: bool = True,
    sparse_entity_floor: int = 1,
) -> tuple[CandidatePair, ...]:
    """STAGE 1. Propose sentence pairs that share a salient entity. Deterministic, $0.

    RECALL IS PREFERRED OVER PRECISION HERE, by design: the semantic judge is the actual
    filter, and a judge call costs ~$0.0005, while a pair never proposed is a duplicate
    lost forever. Two measured recall gaps are handled explicitly:

    - SPARSE ENTITIES (``pair_sparse``). A beat whose corpus ``entities`` list is empty can
      never intersect with anything and is therefore invisible. Measured miss: beat
      4cb9c5a0 ("Pont Neuf means New Bridge, but ironically it is the oldest",
      ``entities=[]``) vs beat 1fbeb1b3 ("...despite its name...Paris's oldest surviving
      bridge") - a real duplicate that entity intersection alone cannot see. When either
      side has fewer than ``sparse_entity_floor`` entity keys, the pair is proposed anyway,
      tagged ``SPARSE_ENTITIES``. Set ``pair_sparse=False`` to disable (costs recall).
    - SPELLING DRIFT. 'Henri IV' and 'Henry IV' are one referent split across two spellings
      in the real corpus; ``normalize_entity`` folds them before intersecting.

    The one optional damper is ``max_entity_frequency`` - an entity appearing in more than
    that fraction of a stop's sentences (e.g. the stop's own name) is too generic to be
    SALIENT and would pair everything with everything; it is skipped for pairing but a
    pair sharing some OTHER entity is still produced. Default 1.0 keeps every entity.

    Returns pairs sorted by (a, b), with ``a < b`` in stream order.
    """
    ordered = _with_indices(sentences)
    vocabulary = _vocabulary(ordered)
    keys_by_index = {
        s.index: _entity_keys_for(s, vocabulary, surface=surface_mentions) for s in ordered
    }

    groups: dict[str, list[NarrationSentence]] = {}
    if cross_stop:
        groups["*"] = list(ordered)
    else:
        for sent in ordered:
            groups.setdefault(sent.stop_id, []).append(sent)

    found: dict[tuple[int, int], tuple[set[str], str, str]] = {}
    for group_id, members in groups.items():
        if len(members) < 2:
            continue
        blocked = _over_frequent(members, keys_by_index, max_entity_frequency)
        for i, first in enumerate(members):
            for second in members[i + 1 :]:
                shared = (keys_by_index[first.index] & keys_by_index[second.index]) - blocked
                if len(shared) >= max(1, min_shared_entities):
                    reason = SHARED_ENTITY
                elif pair_sparse and _is_sparse(
                    keys_by_index, first, second, sparse_entity_floor
                ):
                    reason = SPARSE_ENTITIES  # GAP 1: an entity-less beat stays visible
                else:
                    continue
                lo, hi = sorted((first.index, second.index))
                stop_id = first.stop_id if not cross_stop else group_id
                slot = found.setdefault((lo, hi), (set(), stop_id, reason))
                slot[0].update(shared)

    display = dict(vocabulary)
    return tuple(
        CandidatePair(
            a=lo,
            b=hi,
            shared_entities=tuple(sorted(display.get(k, k) for k in shared)),
            stop_id=stop_id if not cross_stop else "",
            reason=reason,
        )
        for (lo, hi), (shared, stop_id, reason) in sorted(found.items())
    )


def _is_sparse(
    keys_by_index: dict[int, frozenset[str]],
    first: NarrationSentence,
    second: NarrationSentence,
    floor: int,
) -> bool:
    """Is EITHER side under-described by the corpus? Such a sentence can never intersect,
    so it is paired defensively rather than left invisible to the judge."""
    return (
        len(keys_by_index[first.index]) < floor or len(keys_by_index[second.index]) < floor
    )


def _with_indices(sentences: Sequence[NarrationSentence]) -> tuple[NarrationSentence, ...]:
    """Assign stream indices to any sentence that came in without one, so results are
    addressable and ordering is total."""
    out: list[NarrationSentence] = []
    for position, sent in enumerate(sentences):
        out.append(sent if sent.index >= 0 else _replace_index(sent, position))
    return tuple(out)


def _replace_index(sentence: NarrationSentence, index: int) -> NarrationSentence:
    return NarrationSentence(
        text=sentence.text,
        stop_id=sentence.stop_id,
        beat_id=sentence.beat_id,
        entities=sentence.entities,
        index=index,
    )


def _vocabulary(sentences: Sequence[NarrationSentence]) -> tuple[tuple[str, str], ...]:
    """The closed set of corpus-declared entity names, as (key, display), sorted."""
    seen: dict[str, str] = {}
    for sent in sentences:
        for raw in sent.entities:
            key = normalize_entity(raw)
            if key and key not in seen:
                seen[key] = raw
    return tuple(sorted(seen.items()))


def _over_frequent(
    members: Sequence[NarrationSentence],
    keys_by_index: dict[int, frozenset[str]],
    threshold: float,
) -> frozenset[str]:
    if threshold >= 1.0 or len(members) < 2:
        return frozenset()
    counts: dict[str, int] = {}
    for sent in members:
        for key in keys_by_index[sent.index]:
            counts[key] = counts.get(key, 0) + 1
    limit = threshold * len(members)
    return frozenset(k for k, n in counts.items() if n > limit)


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------


def detect_claim_repetition(
    sentences: Sequence[NarrationSentence],
    judge: RedundancyJudge,
    *,
    min_shared_entities: int = 1,
    cross_stop: bool = False,
    surface_mentions: bool = True,
    max_entity_frequency: float = 1.0,
    pair_sparse: bool = True,
    sparse_entity_floor: int = 1,
) -> RepetitionReport:
    """Run stage 1 then stage 2 and return the full report.

    Pure orchestration - all MEANING-level intelligence is in the injected ``judge``, so
    this is fully testable offline with a deterministic stub. Judge calls for independent
    pairs run concurrently; results are re-sorted so output order never depends on
    scheduling.
    """
    ordered = _with_indices(sentences)
    candidates = generate_candidates(
        ordered,
        min_shared_entities=min_shared_entities,
        cross_stop=cross_stop,
        surface_mentions=surface_mentions,
        max_entity_frequency=max_entity_frequency,
        pair_sparse=pair_sparse,
        sparse_entity_floor=sparse_entity_floor,
    )
    by_index = {s.index: s for s in ordered}

    verdicts: tuple[PairVerdict, ...] = ()
    if candidates:

        def _run(pair: CandidatePair) -> PairVerdict:
            a_text = by_index[pair.a].text
            b_text = by_index[pair.b].text
            return PairVerdict(
                pair=pair,
                redundant=bool(judge.same_fact(a_text, b_text)),
                a_text=a_text,
                b_text=b_text,
            )

        workers = max(1, min(_MAX_WORKERS, len(candidates)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            verdicts = tuple(sorted(pool.map(_run, candidates), key=lambda v: v.pair.key))

    return RepetitionReport(
        sentences=ordered,
        candidates=candidates,
        verdicts=verdicts,
        stops=_summarize(ordered, candidates, verdicts, cross_stop=cross_stop),
        judge_calls=len(candidates),
    )


def _summarize(
    sentences: Sequence[NarrationSentence],
    candidates: Sequence[CandidatePair],
    verdicts: Sequence[PairVerdict],
    *,
    cross_stop: bool,
) -> tuple[StopRedundancy, ...]:
    stop_of = {s.index: ("*" if cross_stop else s.stop_id) for s in sentences}
    counts: dict[str, int] = {}
    for sent in sentences:
        key = stop_of[sent.index]
        counts[key] = counts.get(key, 0) + 1

    cand_by_stop: dict[str, int] = {}
    for cand in candidates:
        key = stop_of[cand.a]
        cand_by_stop[key] = cand_by_stop.get(key, 0) + 1

    red_by_stop: dict[str, list[PairVerdict]] = {}
    for verdict in verdicts:
        if verdict.redundant:
            red_by_stop.setdefault(stop_of[verdict.pair.a], []).append(verdict)

    out: list[StopRedundancy] = []
    for stop_id in sorted(counts):
        redundant = tuple(sorted(red_by_stop.get(stop_id, []), key=lambda v: v.pair.key))
        out.append(
            StopRedundancy(
                stop_id=stop_id,
                sentence_count=counts[stop_id],
                candidate_count=cand_by_stop.get(stop_id, 0),
                redundant_pairs=redundant,
                clusters=cluster_pairs(v.pair.key for v in redundant),
            )
        )
    return tuple(out)


def cluster_pairs(pairs: Iterable[tuple[int, int]]) -> tuple[tuple[int, ...], ...]:
    """Transitive closure over redundant pairs -> groups telling one fact. Union-find, so
    the four Vert-Galant sentences collapse to a single cluster of four. Sorted."""
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    for a, b in pairs:
        union(a, b)

    groups: dict[int, list[int]] = {}
    for node in parent:
        groups.setdefault(find(node), []).append(node)
    return tuple(sorted(tuple(sorted(g)) for g in groups.values() if len(g) > 1))


# --------------------------------------------------------------------------------------
# Lexical baseline - DIAGNOSTIC ONLY, never a detector
# --------------------------------------------------------------------------------------


def four_gram_jaccard(a: str, b: str) -> float:
    """Word-4-gram Jaccard similarity. Present ONLY as the measured BASELINE this module
    exists to replace: on the Pont-Neuf tour it scores ~0 on sentences that are 100%
    semantically redundant, which is why a lexical redundancy gate is rejected outright
    (CLAUDE.md: no lexical shortcuts for meaning-level work). Never call this to decide
    redundancy - it is here so tests can prove the gap it leaves."""
    grams_a, grams_b = _four_grams(a), _four_grams(b)
    if not grams_a or not grams_b:
        return 0.0
    return len(grams_a & grams_b) / len(grams_a | grams_b)


def _four_grams(text: str) -> frozenset[tuple[str, ...]]:
    tokens = normalize_entity(text).split()
    if len(tokens) < 4:
        return frozenset()
    return frozenset(tuple(tokens[i : i + 4]) for i in range(len(tokens) - 3))


@dataclass(frozen=True)
class LexicalBaseline:
    """What a 4-gram Jaccard detector would find at ``threshold`` - for the report that
    justifies this module's existence."""

    threshold: float = 0.18
    pairs: tuple[tuple[int, int, float], ...] = field(default_factory=tuple)

    @property
    def found(self) -> int:
        return len(self.pairs)


def lexical_baseline_pairs(
    sentences: Sequence[NarrationSentence], *, threshold: float = 0.18
) -> LexicalBaseline:
    """Run the rejected lexical detector over the same input, for comparison only."""
    ordered = _with_indices(sentences)
    hits: list[tuple[int, int, float]] = []
    for i, first in enumerate(ordered):
        for second in ordered[i + 1 :]:
            score = four_gram_jaccard(first.text, second.text)
            if score >= threshold:
                hits.append((first.index, second.index, score))
    return LexicalBaseline(threshold=threshold, pairs=tuple(sorted(hits)))


__all__ = [
    "SHARED_ENTITY",
    "SPARSE_ENTITIES",
    "CandidatePair",
    "HaikuRedundancyJudge",
    "LexicalBaseline",
    "NarrationSentence",
    "PairVerdict",
    "RedundancyJudge",
    "RepetitionReport",
    "StopRedundancy",
    "cluster_pairs",
    "detect_claim_repetition",
    "four_gram_jaccard",
    "generate_candidates",
    "lexical_baseline_pairs",
    "normalize_entity",
    "sentences_from_beats",
]
