"""The per-sentence CORRECT-LOOP — correct-don't-reject compose (Scope 3,
specs/2026-07-13-compose-correct-dont-reject, commit 1).

Replaces the per-chapter drop/revert repair ladder: every sentence a verified
whole-tour report flags is CORRECTED (trim → rewrite, ≤2 LLM attempts,
per-tour budget) or FLOORED (its owning beats' verbatim post-dedup stitch
sentences splice in, composer-chosen position) — never silently dropped, and
a stop is never shotgun-reverted. Binding contract: 02-spec.md Outputs 1-3 +
Glue/Vignettes + Constraints; 04b D2c (mechanical trim acceptance), D2d
(affirm → floor, telemetry only), BL-R7 (glue correction-before-drop).

The Scope-2 verify-layer primitives are WIRED here, never reimplemented:
``pregate_violations`` (fail-closed, zero-LLM, runs BEFORE any entailment
verdict), ``passes_sentence_unit_shortcut``, ``is_valid_trim`` (a trim is a
pure order-preserving deletion of flagged tokens), and
``route_flagged_sentence`` (under-cited → floor, NEVER correction-stripped —
the fact-preserving rule).

Deterministic termination: the floor is LLM-free and always reachable; a
correction-call failure or an exhausted budget degrades to the floor; the
seated-beat invariant sweep runs LAST so every beat in the stop's compose
request owns ≥1 shipped sentence.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Literal, Protocol

from .contract import (
    BeatRef,
    BeatSequence,
    Script,
    Sentence,
    StopCorrectionCounts,
    ValidationReport,
)
from .generation import FORBIDDEN_PHRASES, GLUE_LABELS, _sum_audio
from .validation import (
    _SENTENCE_HEAD_WORDS,
    _YEAR_RE,
    _cited_beat_corpus_text,
    _proper_nouns_in,
    validate_script,
)
from .verify import (
    FaithfulnessChecker,
    _normalize_for_verbatim,
    passes_sentence_unit_shortcut,
)
from .verify_gate import (
    _canonicalize,
    _word_tokens,
    is_valid_trim,
    pregate_violations,
    route_flagged_sentence,
    salient_tokens,
)

# Concurrency for per-sentence correction ladders (independent LLM calls) —
# the compose.py _run/ThreadPoolExecutor pattern.
_CORRECT_MAX_WORKERS = 6

CorrectionMode = Literal["trim", "rewrite", "glue"]


@dataclass(frozen=True)
class CorrectionRequest:
    """One correction attempt, fully rendered by the loop (deterministic).

    ``flagged_tokens`` are the pre-gate violation tokens (the material a TRIM
    must remove — 04b D2c); ``cited_bodies`` is the constraint source the
    rewrite must stay inside; ``stop_context`` is the stop's sentence stream
    so a rewrite keeps its slot in the flow.
    """

    mode: CorrectionMode
    sentence_text: str
    flagged_tokens: tuple[str, ...]
    cited_bodies: tuple[str, ...]
    stop_context: tuple[str, ...]
    stop_idx: int
    attempt: int = 1


class CorrectionClient(Protocol):
    """One LLM correction attempt. Raising = a correction-call failure — the
    loop degrades that sentence to the floor (AC-11c), never errors out."""

    def correct(self, request: CorrectionRequest) -> str: ...


class MockCorrectionClient:
    """Offline default for harnesses: affirms (returns the input unchanged),
    which routes every flagged sentence to the deterministic floor. Records
    calls so budgets are assertable."""

    def __init__(self) -> None:
        self.calls: list[CorrectionRequest] = []

    def correct(self, request: CorrectionRequest) -> str:
        self.calls.append(request)
        return request.sentence_text


class GatedFaithfulnessChecker:
    """Wraps a FaithfulnessChecker so the deterministic pre-gate runs BEFORE
    every entailment verdict: any salient-class token of the sentence absent
    from the support union fails closed with ZERO LLM calls (02-spec
    Never-fabricate layer 1). Wired into the per-chapter verify + best-of-N
    penalty; the whole-tour path is untouched until Scope 5.

    Order note: verify's verbatim shortcut runs before ``entails`` is ever
    called, so the effective order is shortcut → pre-gate → entailment. This
    is outcome-identical to the battery's pre-gate → shortcut → entailment: a
    complete sentence-unit run of a cited body cannot carry a token absent
    from that body's union.
    """

    def __init__(self, inner: FaithfulnessChecker):
        self.inner = inner

    def entails(self, support: tuple[str, ...], sentence_text: str) -> bool:
        if pregate_violations(sentence_text, tuple(support)):
            return False  # fail closed — no LLM verdict for a pre-gate violation
        return self.inner.entails(support, sentence_text)


def count_pregate_flagged(
    sentences: list[Sentence], beats_by_id: dict[str, BeatRef]
) -> int:
    """Number of beat-cited sentences with ≥1 pre-gate violation against their
    declared citations' bodies — the FIRST best-of-N ranking key (a
    deterministic fabrication signal, never an LLM verdict alone)."""
    flagged = 0
    for s in sentences:
        if s.source_type != "beat":
            continue
        bodies = tuple(
            b.script_body
            for b in (beats_by_id.get(bid) for bid in s.cited_beat_ids)
            if b is not None and b.script_body
        )
        if pregate_violations(s.text, bodies):
            flagged += 1
    return flagged


# ---------------------------------------------------------------------------
# Real Anthropic correction client — NOT exercised by `make test`.
# ---------------------------------------------------------------------------

CORRECTION_MODEL = "claude-opus-4-8"
_CORRECTION_MAX_TOKENS = 1000

_TRIM_PROMPT = """\
One sentence of a walking-tour narration contains material not supported by its sources.

FLAGGED UNSUPPORTED TOKENS (the material to remove): {tokens}

SENTENCE:
{sentence}

Remove ONLY the unsupported material. Do not rephrase, reorder, or add anything;
keep every other word verbatim. Return ONLY the trimmed sentence — no preamble,
no quotation marks, no commentary."""

_REWRITE_PROMPT = """\
One sentence of the composed walking-tour stop below failed its grounding check.

STOP CONTEXT (the composed stop, in order — the flagged sentence is marked >>> <<<):
{context}

SOURCE TEXT (the flagged sentence's cited beats' corpus text — your rewrite must be
fully supported by THIS text and nothing else; no other names, dates, numbers, or facts):
{sources}

Rewrite ONLY the flagged sentence so it keeps the narrator voice, still fits its slot in
the stop's flow, and is fully supported by the SOURCE TEXT alone. Return ONLY the
rewritten sentence — no preamble, no quotation marks, no commentary."""

_GLUE_PROMPT = """\
One connective (glue) sentence of the walking-tour stop below failed validation: glue may
not contain the words "imagine", "picture this", "envision" or "visualize", and may not
introduce any proper noun or year the tour's cited corpus text does not already carry.

STOP CONTEXT (the flagged sentence is marked >>> <<<):
{context}

Rewrite ONLY the flagged glue sentence as a short, fact-free transition in the same warm
second-person narrator voice — no names, no dates, no new facts. Return ONLY the
rewritten sentence — no preamble, no quotation marks, no commentary."""


class AnthropicCorrectionClient:
    """Real Opus correction attempts (trim / narrator-voice rewrite / glue).

    Deferred anthropic import (HaikuGlueClient pattern) so unit tests never
    need the SDK; ``make test`` never constructs this. No temperature param —
    Opus 4.7+ rejects it (matches the compose client)."""

    def __init__(self, model: str = CORRECTION_MODEL, *, client: object | None = None):
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0
        if client is None:
            from src.tour.anthropic_client import compose_client

            client = compose_client()
        self._client = client

    def _render(self, request: CorrectionRequest) -> str:
        context = "\n".join(
            f">>> {line} <<<" if line == request.sentence_text else line
            for line in request.stop_context
        )
        if request.mode == "trim":
            return _TRIM_PROMPT.format(
                tokens=", ".join(request.flagged_tokens), sentence=request.sentence_text
            )
        if request.mode == "glue":
            return _GLUE_PROMPT.format(context=context)
        return _REWRITE_PROMPT.format(
            context=context, sources="\n\n".join(request.cited_bodies)
        )

    def correct(self, request: CorrectionRequest) -> str:
        response = self._client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=_CORRECTION_MAX_TOKENS,
            messages=[{"role": "user", "content": self._render(request)}],
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        return (
            "".join(
                b.text
                for b in (getattr(response, "content", []) or [])
                if getattr(b, "type", "") == "text"
            )
            .strip()
            .strip('"')
            .strip()
        )


# ---------------------------------------------------------------------------
# The correct-loop
# ---------------------------------------------------------------------------


class _Budget:
    """Thread-safe per-tour correction-call budget (2 x stop_count)."""

    def __init__(self, limit: int):
        self.limit = max(0, limit)
        self.used = 0
        self._lock = threading.Lock()

    def acquire(self) -> bool:
        with self._lock:
            if self.used >= self.limit:
                return False
            self.used += 1
            return True


@dataclass
class _Counters:
    glue_dropped: int = 0
    affirm_reject: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def bump_glue(self) -> None:
        with self._lock:
            self.glue_dropped += 1

    def bump_affirm(self) -> None:
        with self._lock:
            self.affirm_reject += 1


@dataclass(frozen=True)
class _Outcome:
    kind: Literal["corrected", "floor", "glue_corrected", "glue_floor", "drop"]
    text: str = ""
    floor_beats: frozenset[str] = frozenset()


def _sentence_key(s: Sentence) -> tuple[int, str, str]:
    return (s.stop_idx, s.source_id, s.text)


def _is_affirm(original: str, corrected: str) -> bool:
    """04b D2d: a correction returning ~identical text (whitespace/case fold)
    is an AFFIRM — floor + telemetry, no escalation ship-path."""
    return _normalize_for_verbatim(corrected) == _normalize_for_verbatim(original)


def _bodies(beats: list[BeatRef]) -> tuple[str, ...]:
    return tuple(b.script_body for b in beats if b.script_body)


def strip_bodyless_citations(script: Script, beats_by_id: dict[str, BeatRef]) -> Script:
    """Remove KNOWN-but-bodyless beat ids from beat sentences' ``also_cites``
    BEFORE verify (02-spec Vignettes: bodyless citations stripped pre-verify)
    — a bodyless citation adds nothing to entail against and would otherwise
    poison the support derivation. Unknown ids are kept: traceability's job.
    A bodyless PRIMARY citation stays (source_id semantics) and fails closed
    via verify's no_support backstop → the loop floors it."""
    out: list[Sentence] = []
    changed = False
    for s in script.script:
        if s.source_type != "beat" or not s.also_cites:
            out.append(s)
            continue
        kept = tuple(
            bid
            for bid in s.also_cites
            if bid not in beats_by_id or beats_by_id[bid].script_body
        )
        if kept == s.also_cites:
            out.append(s)
        else:
            changed = True
            out.append(s.model_copy(update={"also_cites": kept}))
    return script.model_copy(update={"script": tuple(out)}) if changed else script


def _glue_scan_ok(text: str, corpus_nouns: set[str], corpus_years: set[str]) -> bool:
    """validation's glue rules on ONE sentence: no forbidden phrase, no proper
    noun or year the script's cited corpus text does not already carry."""
    lower = text.lower()
    if any(phrase in lower for phrase in FORBIDDEN_PHRASES):
        return False
    for token in _proper_nouns_in(text, drop_first_word=True):
        if token.lower() in _SENTENCE_HEAD_WORDS:
            continue
        if token not in corpus_nouns:
            return False
    return all(year in corpus_years for year in _YEAR_RE.findall(text))


def correct_script(
    composed: Script,
    report: ValidationReport,
    *,
    stitched: Script,
    beat_sequence: BeatSequence,
    beats_by_id: dict[str, BeatRef],
    vignette_beat_ids: frozenset[str] = frozenset(),
    checker: FaithfulnessChecker,
    correction_client: CorrectionClient | None = None,
    budget: int,
) -> Script:
    """Correct or floor every sentence ``report`` flags, sweep the seated-beat
    invariant LAST, recompute audio LAST, and emit per-stop
    verified/corrected/floored counts + ``glue_dropped``/``affirm_reject`` on
    the returned Script's ValidationReport.

    ``beats_by_id`` is the SUPPORT map (anchors + vignette beats);
    ``stitched`` supplies the verbatim post-dedup floor material;
    ``correction_client=None`` runs the loop fully deterministic — flagged
    correctable sentences floor without an LLM attempt (the offline default;
    production injects a real client). ``checker`` is the RAW checker — the
    loop runs the pre-gate itself before any entailment re-entry.
    """
    # --- floor material: verbatim post-dedup stitch, per (stop, beat) -------
    stitch_blocks: dict[tuple[int, str], list[Sentence]] = defaultdict(list)
    stitched_beat_order: dict[int, list[str]] = defaultdict(list)
    stitched_glue: dict[tuple[int, str], list[Sentence]] = defaultdict(list)
    for s in stitched.script:
        if s.source_type == "beat":
            key = (s.stop_idx, s.source_id)
            if s.source_id not in stitched_beat_order[s.stop_idx]:
                stitched_beat_order[s.stop_idx].append(s.source_id)
            stitch_blocks[key].append(s)
        else:
            stitched_glue[(s.stop_idx, s.source_id)].append(s)

    # --- stop unions (verify-parity: ANCHOR beats cited at the stop) --------
    stop_union: dict[int, list[BeatRef]] = defaultdict(list)
    seen_union: dict[int, set[str]] = defaultdict(set)
    stop_context: dict[int, list[str]] = defaultdict(list)
    for s in composed.script:
        stop_context[s.stop_idx].append(s.text)
        if s.source_type != "beat":
            continue
        for bid in s.cited_beat_ids:
            if (
                bid in beats_by_id
                and bid not in vignette_beat_ids
                and bid not in seen_union[s.stop_idx]
            ):
                seen_union[s.stop_idx].add(bid)
                stop_union[s.stop_idx].append(beats_by_id[bid])

    # --- the flagged set (faithfulness + forbidden + untraceable) -----------
    flagged: dict[tuple[int, str, str], Sentence] = {}
    for sentence, _reason in report.faithfulness_failures:
        flagged.setdefault(_sentence_key(sentence), sentence)
    for sentence, _code in report.forbidden_phrase_hits:
        flagged.setdefault(_sentence_key(sentence), sentence)
    for sentence in report.untraceable_sentences:
        flagged.setdefault(_sentence_key(sentence), sentence)

    budget_box = _Budget(budget)
    counters = _Counters()
    corpus_text = _cited_beat_corpus_text(composed, beat_sequence)
    corpus_nouns = _proper_nouns_in(corpus_text)
    corpus_years = set(_YEAR_RE.findall(corpus_text))

    def _call(request: CorrectionRequest) -> str | None:
        """One budgeted correction call; None = no budget / call failure —
        both degrade to the floor (deterministic termination)."""
        if correction_client is None or not budget_box.acquire():
            return None
        try:
            return correction_client.correct(request)
        except Exception:
            return None  # correction-call failure degrades to the floor (AC-11c)

    def _passes_beat_gate(text: str, cited: list[BeatRef]) -> bool:
        """Full per-sentence re-entry: pre-gate → shortcut → entailment, plus
        the forbidden-phrase scan (every attempt re-enters the gate)."""
        bodies = _bodies(cited)
        if not bodies:
            return False
        lower = text.lower()
        if any(phrase in lower for phrase in FORBIDDEN_PHRASES):
            return False
        if pregate_violations(text, bodies):
            return False
        if passes_sentence_unit_shortcut(text, cited):
            return True
        return bool(checker.entails(bodies, text))

    def _resolve_beat(s: Sentence) -> _Outcome:
        cited = [beats_by_id[bid] for bid in s.cited_beat_ids if bid in beats_by_id]
        if not cited:
            return _Outcome("drop")  # fully untraceable — nothing to ground or floor
        cited_ids = frozenset(b.id for b in cited)
        declared_bodies = _bodies(cited)
        if not declared_bodies:
            # no_support fail-closed class: floor whatever stitch its beats own.
            return _Outcome("floor", floor_beats=cited_ids)
        is_vignette_cited = any(bid in vignette_beat_ids for bid in s.cited_beat_ids)
        union_beats = [] if is_vignette_cited else stop_union.get(s.stop_idx, [])
        union_bodies = _bodies(union_beats)
        if route_flagged_sentence(s.text, declared_bodies, union_bodies) == "under_cited":
            # Fact-preserving rule: under-cited routes STRAIGHT to the floor of
            # the stop-union beats owning the uncovered tokens — never trimmed.
            uncovered = {
                v.split(":", 1)[1] for v in pregate_violations(s.text, declared_bodies)
            }
            owners = frozenset(
                b.id
                for b in union_beats
                if b.script_body
                and uncovered & _word_tokens(_canonicalize(b.script_body))
            )
            return _Outcome("floor", floor_beats=owners or cited_ids)

        # Correctable: ≤2 attempts — TRIM first when the failure is separable
        # unsourced garnish (pre-gate violations vs the declared bodies), else
        # narrator-voice rewrites. Exhaustion/affirm/failure → floor ALL cited
        # beats (fusion ownership — AC-5).
        floor = _Outcome("floor", floor_beats=cited_ids)
        violations = pregate_violations(s.text, declared_bodies)
        tokens = tuple(dict.fromkeys(v.split(":", 1)[1] for v in violations))
        context = tuple(stop_context.get(s.stop_idx, ()))

        def _attempt(mode: CorrectionMode, attempt: int) -> str | None:
            return _call(
                CorrectionRequest(
                    mode=mode,
                    sentence_text=s.text,
                    flagged_tokens=tokens,
                    cited_bodies=declared_bodies,
                    stop_context=context,
                    stop_idx=s.stop_idx,
                    attempt=attempt,
                )
            )

        if tokens:
            out = _attempt("trim", 1)
            if out is None:
                return floor
            if _is_affirm(s.text, out):
                counters.bump_affirm()
                return floor
            if is_valid_trim(s.text, out, frozenset(tokens)):
                if _passes_beat_gate(out, cited):
                    return _Outcome("corrected", text=out)
                out2 = _attempt("rewrite", 2)
                if out2 is None:
                    return floor
                if _is_affirm(s.text, out2):
                    counters.bump_affirm()
                    return floor
                if _passes_beat_gate(out2, cited):
                    return _Outcome("corrected", text=out2)
                return floor
            # NOT a trim (04b D2c): the same output counts as the attempt-2
            # full rewrite — re-enter the gate, no extra call.
            if _passes_beat_gate(out, cited):
                return _Outcome("corrected", text=out)
            return floor

        out = _attempt("rewrite", 1)
        if out is None:
            return floor
        if _is_affirm(s.text, out):
            counters.bump_affirm()
            return floor
        if _passes_beat_gate(out, cited):
            return _Outcome("corrected", text=out)
        out2 = _attempt("rewrite", 2)
        if out2 is None:
            return floor
        if _is_affirm(s.text, out2):
            counters.bump_affirm()
            return floor
        if _passes_beat_gate(out2, cited):
            return _Outcome("corrected", text=out2)
        return floor

    def _resolve_glue(s: Sentence) -> _Outcome:
        """04b BL-R7: ONE correction attempt BEFORE any drop; still-failing
        composed glue floors to the stitched glue of the same (stop_idx,
        source_id); composer-ADDED glue with no stitched counterpart drops
        after its failed attempt; every drop increments glue_dropped. (An old
        persisted script's GLUE_REFLECTION is ordinary glue on this ladder —
        the reflection machinery was retired in Scope 3 commit 2.)"""
        traceable = s.source_id in GLUE_LABELS
        if traceable:
            out = _call(
                CorrectionRequest(
                    mode="glue",
                    sentence_text=s.text,
                    flagged_tokens=(),
                    cited_bodies=(),
                    stop_context=tuple(stop_context.get(s.stop_idx, ())),
                    stop_idx=s.stop_idx,
                )
            )
            if out is not None and _glue_scan_ok(out, corpus_nouns, corpus_years):
                return _Outcome("glue_corrected", text=out)
        if traceable and stitched_glue.get((s.stop_idx, s.source_id)):
            return _Outcome("glue_floor")
        counters.bump_glue()
        return _Outcome("drop")

    def _resolve(s: Sentence) -> _Outcome:
        if s.source_type == "beat":
            return _resolve_beat(s)
        return _resolve_glue(s)

    outcomes: dict[tuple[int, str, str], _Outcome] = {}
    if flagged:
        keys = list(flagged)
        workers = max(1, min(_CORRECT_MAX_WORKERS, len(keys)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = pool.map(lambda k: _resolve(flagged[k]), keys)
        outcomes = dict(zip(keys, results, strict=True))

    # --- assembly (deterministic, script order) ------------------------------
    floored_by_stop: dict[int, set[str]] = defaultdict(set)
    for key, outcome in outcomes.items():
        if outcome.kind == "floor":
            floored_by_stop[key[0]] |= outcome.floor_beats

    stop_order: list[int] = []
    out_by_stop: dict[int, list[Sentence]] = defaultdict(list)
    inserted: set[tuple[int, str]] = set()
    verified: dict[int, int] = defaultdict(int)
    corrected_n: dict[int, int] = defaultdict(int)
    floored_n: dict[int, int] = defaultdict(int)
    # Scope 45 telemetry: spoken-audio seconds of the stitch blocks floored in
    # (flag floors + seated-beat invariant), so the editorial queue can rank how
    # much of a stop degraded to raw stitch.
    floored_secs: dict[int, int] = defaultdict(int)

    body_tokens_cache: dict[str, frozenset[str]] = {}

    def _body_tokens(bid: str) -> frozenset[str]:
        """A beat's coverage universe — the same parity semantics as
        ``_populate_also_cites`` (pre-gate word-token membership)."""
        if bid not in body_tokens_cache:
            beat = beats_by_id.get(bid)
            body_tokens_cache[bid] = (
                _word_tokens(_canonicalize(beat.script_body))
                if beat is not None and beat.script_body
                else frozenset()
            )
        return body_tokens_cache[bid]

    def _honest_also_cites(s: Sentence, corrected_text: str) -> tuple[str, ...]:
        """Citation-honesty rule (skeptic blocker, 2026-07-17): a shipped
        CORRECTION re-derives ``also_cites`` from the corrected TEXT —
        ``_populate_also_cites``'s BL-V2 semantics in reverse. ``source_id``
        is always kept; an ``also_cites`` bid is retained ONLY if its body
        still justifies ≥1 pre-gate salient token of the corrected text that
        the other retained citations' bodies do not cover. A stripped citation
        may leave the beat unowned — the seated-beat invariant (which runs
        LAST) then floors its stitch block in, the fact-preserving outcome.
        Safe-direction asymmetry: over-stripping only costs a redundant floor;
        under-stripping loses facts — so a corrected text with NO salient
        tokens strips ALL also_cites."""
        if not s.also_cites:
            return s.also_cites
        sal = salient_tokens(corrected_text)
        if not sal:
            return ()
        covered = set(_body_tokens(s.source_id))
        uncovered = {t for t in sal if t not in covered}
        kept: list[str] = []
        for bid in s.also_cites:
            supplied = uncovered & _body_tokens(bid)
            if supplied:  # this beat still justifies an uncovered salient token
                kept.append(bid)
                uncovered -= supplied
        return tuple(kept)

    def _insert_blocks(stop_idx: int, beat_ids: frozenset[str] | set[str]) -> None:
        """Floor the given beats' stitch blocks at the current position, in
        stitched order, once each."""
        for bid in stitched_beat_order.get(stop_idx, []):
            if bid not in beat_ids or (stop_idx, bid) in inserted:
                continue
            block = stitch_blocks.get((stop_idx, bid), [])
            if not block:
                continue
            inserted.add((stop_idx, bid))
            out_by_stop[stop_idx].extend(block)
            floored_n[stop_idx] += 1
            floored_secs[stop_idx] += _sum_audio(tuple(block), beat_sequence)

    for s in composed.script:
        stop_idx = s.stop_idx
        if stop_idx not in stop_order:
            stop_order.append(stop_idx)
        outcome = outcomes.get(_sentence_key(s))
        if s.source_type == "beat":
            cited = set(s.cited_beat_ids)
            floor_set = floored_by_stop.get(stop_idx, set())
            if outcome is None:
                if cited and cited <= floor_set:
                    # Collateral subset rule: a floor replaces only sentences
                    # whose FULL citation set ⊆ the floored-beat set.
                    _insert_blocks(stop_idx, cited)
                else:
                    out_by_stop[stop_idx].append(s)
                    verified[stop_idx] += 1
            elif outcome.kind == "corrected":
                out_by_stop[stop_idx].append(
                    s.model_copy(
                        update={
                            "text": outcome.text,
                            "also_cites": _honest_also_cites(s, outcome.text),
                        }
                    )
                )
                corrected_n[stop_idx] += 1
            elif outcome.kind == "floor":
                _insert_blocks(stop_idx, outcome.floor_beats)
            # "drop": untraceable — vanishes; the invariant restores real beats.
        else:
            if outcome is None:
                out_by_stop[stop_idx].append(s)
            elif outcome.kind == "glue_corrected":
                out_by_stop[stop_idx].append(s.model_copy(update={"text": outcome.text}))
            elif outcome.kind == "glue_floor":
                out_by_stop[stop_idx].extend(stitched_glue[(stop_idx, s.source_id)])
            # "drop": counted in glue_dropped by the resolver.

    # --- seated-beat invariant sweep (LAST): every beat in the stop's compose
    # request owns ≥1 shipped sentence (source_id or also_cites); an unowned
    # beat's stitch block floors in adjacent to its POI's block. -------------
    for stop_idx in stitched_beat_order:
        if stop_idx not in stop_order:
            stop_order.append(stop_idx)
    for stop_idx in stop_order:
        shipped = out_by_stop[stop_idx]
        owned: set[str] = set()
        for s in shipped:
            if s.source_type == "beat":
                owned.update(s.cited_beat_ids)
        for bid in stitched_beat_order.get(stop_idx, []):
            if bid in owned or (stop_idx, bid) in inserted:
                continue
            block = stitch_blocks.get((stop_idx, bid), [])
            if not block:
                continue
            poi_id = beats_by_id[bid].poi_id if bid in beats_by_id else None
            insert_at = 0 if bid in vignette_beat_ids else len(shipped)
            for i, s in enumerate(shipped):
                if s.source_type != "beat":
                    continue
                cited_beat = beats_by_id.get(s.source_id)
                if cited_beat is not None and cited_beat.poi_id == poi_id:
                    insert_at = i + 1  # adjacent: after its POI's block
            shipped[insert_at:insert_at] = block
            inserted.add((stop_idx, bid))
            owned.add(bid)
            floored_n[stop_idx] += 1
            floored_secs[stop_idx] += _sum_audio(tuple(block), beat_sequence)

    final_sentences = tuple(s for stop_idx in stop_order for s in out_by_stop[stop_idx])
    counts = {
        stop_idx: StopCorrectionCounts(
            verified=verified.get(stop_idx, 0),
            corrected=corrected_n.get(stop_idx, 0),
            floored=floored_n.get(stop_idx, 0),
            floored_audio_seconds=floored_secs.get(stop_idx, 0),
        )
        for stop_idx in stop_order
    }
    telemetry = {
        # Stored as a TUPLE of (stop_idx, counts) pairs, not a dict: ValidationReport
        # is frozen=True and a dict field breaks hash(). See contract.py.
        "stop_correction_counts": tuple(sorted(counts.items())),
        "glue_dropped": counters.glue_dropped,
        "affirm_reject": counters.affirm_reject,
        "corrections_spent": budget_box.used,
    }

    if final_sentences == composed.script:
        # Nothing changed (clean tour, or an uncorrectable non-sentence failure
        # like provenance): keep the original report, add the telemetry.
        return composed.model_copy(
            update={"validation": report.model_copy(update=telemetry)}
        )

    # Recompute _sum_audio LAST, over the final shipped stream.
    final_script = composed.model_copy(
        update={
            "script": final_sentences,
            "total_audio_seconds": _sum_audio(final_sentences, beat_sequence),
        }
    )
    # Re-verify the affected checks deterministically: traceability + forbidden
    # on the final stream. Faithfulness needs no re-run — every shipped beat
    # sentence either passed the original verify, re-entered the full gate as a
    # correction, or is verbatim post-dedup stitch (shortcut-trivial). Coverage
    # is retired on this path; provenance is beat-level, carried through.
    base = validate_script(final_script, beat_sequence)
    final_report = base.model_copy(
        update={
            "provenance_failures": report.provenance_failures,
            "faithfulness_failures": (),
            "coverage_failures": (),
            **telemetry,
        }
    )
    return final_script.model_copy(update={"validation": final_report})


__all__ = [
    "CORRECTION_MODEL",
    "AnthropicCorrectionClient",
    "CorrectionClient",
    "CorrectionMode",
    "CorrectionRequest",
    "GatedFaithfulnessChecker",
    "MockCorrectionClient",
    "correct_script",
    "count_pregate_flagged",
    "strip_bodyless_citations",
]
