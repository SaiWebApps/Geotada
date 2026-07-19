"""The AUTHOR ENGINE — write a stop's narration FRESH from its grounded facts (flow-first),
then a SEMANTIC fact-check-and-repair loop restores any dropped fact and strips any
invented one. Flow *and* fidelity.

The compose engine fuses stitched beat-sentences (fact-first, but stilted and repetitive);
the author engine writes like a person from the facts (far better prose — proven in the
side-by-side) but drops facts on its own. This loop closes that gap:

    draft  = drafter.write(facts)                      # flowing prose from the facts
    loop (bounded):
        result = checker.check(draft, facts)           # SEMANTIC: unsupported + missing
        if result.passed(): serve draft
        draft = drafter.rewrite(facts, draft, result)  # restore dropped, strip invented
    floor: grounded stitch (fact-complete)             # guarantees termination + fidelity

The check is the semantic ``SemanticFactChecker`` (bidirectional entailment) — NO lexical
shortcuts. Termination is guaranteed: the ladder ends at the grounded stitch, which is
fact-complete and corpus-verbatim, so it trivially passes.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from .contract import BeatSequence, Route, Script, Sentence, ValidationReport
from .factcheck import FactCheckResult, SemanticFactChecker
from .generation import split_sentences
from .narration_quality import craft_score


@dataclass(frozen=True)
class StopContext:
    """Cross-stop narrative context threaded into ONE stop's draft/rewrite prompt so the
    author can bridge from the previous stop and pull toward the next — WITHOUT ever
    licensing a new invented fact (see ``_THREADING_ADDENDUM``). Built by
    ``author_compose_script``'s serial (``thread=True``) walk; ``None`` (the default
    everywhere else, incl. the production API path) reproduces today's byte-identical
    isolated-stop prompt.

    ``prev_summary`` is a single sentence describing what the PREVIOUS content-bearing stop
    actually SERVED (the converged author prose OR the grounded stitch it fell back to —
    never a discarded draft). It is PROMPT-ONLY: it must NEVER be admitted into the
    fact-checker's source facts, or unverified narration would become uncheckable
    "evidence" for the next stop's claims (see ``test_prev_summary_is_never_admitted_as_a_
    source_fact``).

    Every field here is actually READ by ``_threading_addendum`` (``prev_summary`` gates and
    fills the bridge clause; ``next_poi``'s TRUTHINESS gates the pull clause, though its
    literal name is never spliced into the prompt — see ``_threading_addendum``'s docstring;
    ``position`` selects the branch). There is no ``prev_poi`` or ``tour_theme`` field: an
    earlier draft carried both but never read either in the addendum, and a hostile verifier
    flagged that as dead surface with tests manufacturing false coverage — removed rather
    than wired to a use that would only duplicate ``prev_summary``'s existing gating."""

    prev_summary: str = ""
    next_poi: str = ""
    position: str = "middle"  # "opening" | "middle" | "finale"


class Drafter(Protocol):
    """Writes a stop's narration from its facts, and rewrites it against a repair signal.
    The intelligence (the LLM) lives here; the loop below is pure orchestration.

    ``context`` (keyword-only, defaults ``None``): optional cross-stop narrative context
    (see ``StopContext``). Callers MUST pass it only when non-``None`` (never
    ``context=None`` explicitly) so drafters written before threading existed — which take
    no ``context`` parameter at all — keep working unmodified."""

    def write(
        self, facts: tuple[str, ...], poi: str, lens: str, *, context: StopContext | None = None
    ) -> str: ...

    def rewrite(
        self,
        facts: tuple[str, ...],
        draft: str,
        result: FactCheckResult,
        poi: str,
        lens: str,
        *,
        context: StopContext | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class AuthorResult:
    text: str
    result: FactCheckResult  # the fact-check verdict on ``text`` (the SERVED text, always)
    attempts: int  # how many draft/rewrite rounds ran
    grounded_fallback: bool  # True iff we fell back to the grounded stitch
    widened: bool = False  # True iff the served text came from the widened-fact retry
    rescued: tuple[str, ...] = ()  # claims flagged unsupported by the window, grounded by
    # the FULL POI corpus and served anyway (a windowing artifact, not an invention)
    excised: tuple[str, ...] = ()  # sentences SURGICALLY DROPPED from the served text
    # because they carried a claim entailed by nothing (a true invention)
    rescued_not_served: tuple[str, ...] = ()  # claims the corpus GROUNDED during a rescue
    # attempt (narrow or widened) that nonetheless still fell back to the stitch (no excise
    # rung configured, or excision itself aborted) — auditability only, never behavior: without
    # this an operator sees a bare GROUNDED-STITCH FALLBACK and cannot tell a corpus rescue
    # fired at all (only ``rescued``, which is empty whenever nothing was ultimately SERVED
    # under the rescued banner, was previously visible).
    threaded: bool = False  # True iff a StopContext was passed to this call (attributes a
    # live regression to the threading track even when it still fell back — mirrors
    # ``widened``'s shape but answers "was this attempt made under threading", not "did it win")


def author_compose_stop(
    facts: tuple[str, ...],
    poi: str,
    lens: str,
    *,
    drafter: Drafter,
    checker: SemanticFactChecker,
    stitch_fallback: str,
    max_repairs: int = 2,
    trace: list[tuple[str, FactCheckResult]] | None = None,
    widen: Callable[[], tuple[str, ...] | None] | None = None,
    wide_max_repairs: int = 1,
    corpus_facts: Callable[[], tuple[str, ...]] | None = None,
    excise: bool = False,
    min_keep_ratio: float = 0.6,
    context: StopContext | None = None,
) -> AuthorResult:
    """Draft the stop, then repair against the semantic fact-check until it is faithful and
    complete, bounded by ``max_repairs``. If repair is exhausted, fall back to the grounded
    ``stitch_fallback`` (fact-complete corpus text) so a stop NEVER ships a dropped or
    invented fact — the author's flow is preferred, fidelity is guaranteed.

    ``trace`` (optional out-param): if provided, each author attempt is appended as
    ``(draft_text, verdict)`` in order — so a caller can see WHY the loop fell back (which
    claims stayed unsupported / which facts stayed missing on the final author draft),
    instead of only the grounded-stitch floor's verdict. Diagnostic only; no behavior change.

    Each repair rewrites from the BEST draft seen so far (fewest unsupported+missing), not
    the last — a rewrite that makes things worse (a new mis-attribution, or an empty/collapsed
    draft) is DISCARDED rather than fed forward, so the loop cannot thrash a good draft into a
    worse one. An empty rewrite is treated as a total miss and never adopted.

    ``widen`` (optional): called ONCE, only when the narrow loop fails to converge, and
    ALWAYS BEFORE either rescue rung below gets a chance to run (ordering fixed 2026-07-18;
    see the RATIONALE paragraph after ``excise`` for why this order is load-bearing). If it
    returns a wider fact tuple, the draft/repair loop runs one more bounded round
    (``wide_max_repairs``) on those facts; the widened prose is served ONLY if it fully
    passes, else the ORIGINAL narrow ``stitch_fallback`` is served (never a wider stitch).
    Rationale + live evidence (Phase C, specs/2026-07-18-tour-qa-campaign/PHASE-C-RESULTS.md):
    fragmentary narrow facts make the author invent bridging connectives the checker rejects;
    widening put the bridge in the facts and converted 3 of 4 retried fallbacks to authored
    first-attempt at the same zero-fabrication bar (Big Ben craft 0.08 -> 2.42). One
    dense-multi-entity stop (Conciergerie) regressed under widening — the retry is bounded
    (~1.5x Opus on fallback stops only) so that case costs a little and changes nothing.

    ``corpus_facts`` (optional, both OFF by default so every existing caller — including the
    production path, ``author_compose_script``, which passes neither — is byte-identical):
    called ONLY when the best draft's residual failures are UNSUPPORTED-only (a genuine
    MISSING fact is a real drop no corpus recheck can repair, so it is never called then),
    and ONLY after ``widen`` has already had its turn and failed to fully converge. If it
    returns a non-empty POI FULL-CORPUS fact tuple, every still-unsupported claim is
    RE-TESTED against it (``checker.unsupported_against``, the STRICT entailer — never the
    paraphrase-tolerant coverage judge). A claim entailed by the wider corpus was only
    unsupported because the tour-window trimmed away its source beat (a windowing
    artifact, not an invention) and is served; a claim entailed by NOTHING stays a true
    invention. Fully rescued -> serve the draft AS-IS (no cut, no craft gate — see the
    ``excise`` paragraph's CRAFT FLOOR note), verdict recomputed clean.

    ``excise`` (optional, OFF by default): when claims survive the corpus recheck (or no
    ``corpus_facts`` was given at all) and the failures are still unsupported-only, try
    dropping ONLY the sentence(s) that carry them (``_excise``) rather than discarding the
    whole stop. Surgical excision serves the remainder ONLY if every sentence carrying an
    unsupported claim was locatable, the surviving prose clears the ``min_keep_ratio``
    collapse floor, and the remainder independently re-passes the fact-check: the COVERAGE
    direction against the NARROW ``facts`` (a dropped fact is still a drop, unrelaxed), and
    the FAITHFULNESS direction's residual unsupported claims are given one more chance
    through the SAME full-POI ``corpus`` the rescue rung already fetched
    (``checker.unsupported_against``) — a claim the corpus grounds is not a fresh invention
    just because the excised remainder's re-decomposition surfaced it again. Without this,
    a rescued claim whose sentence survives excision (because only the OTHER, truly-invented
    sentence was dropped) gets re-flagged unsupported against the narrow facts alone and the
    whole draft wrongly falls through to the stitch — the exact mixed Vert-Galant shape
    (one windowed-out true claim + one real invention) the whole track exists for. This
    never relaxes the anti-hallucination guarantee: a claim only ever survives via entailment
    against facts the POI's own corpus actually states, never a guess.
    CRAFT FLOOR: ``_excise`` gates a SURGICALLY-CUT remainder on ``craft_score(remainder) >=
    craft_score(stitch_fallback)`` — dropping a sentence can strand its neighbor (dangling
    anaphora), so a fact-clean-but-mutilated remainder must still beat the stitch it would
    replace. The plain corpus-RESCUE path (no cut at all — the draft ships verbatim) applies
    NO such gate: nothing was mutilated, so there is no register-crash risk to guard against,
    and the whole premise of the author engine is that its unmutilated prose already beats
    the mechanical stitch (see ``test_rescue_path_has_no_craft_floor_by_design_unlike_excise``).
    RATIONALE for widen-before-rescue: the same recheck+excise ladder is applied to the
    widened draft first if ``widen`` fully failed to converge, and ONLY THEN — if that also
    fails — is a narrow-draft rescue/excise attempted, since widening is the more expensive
    rung and must not be preempted by a narrow rescue that would ship lower-craft prose
    (Phase-C measured widened prose at 2.29-2.42 craft; see
    ``test_widen_fires_before_any_rescue_attempt_even_when_the_narrow_rescue_would_succeed``).

    ``AuthorResult.rescued_not_served`` (auditability, not a behavior change): whenever a
    rescue attempt (narrow or widened) grounds SOME claims against the corpus but the stop
    still falls back (no excise rung configured, or excision itself aborted), those grounded
    claims are surfaced here even though nothing was ultimately served under the ``rescued``
    banner — so an operator reading the harness output can tell the rescue rung fired at
    all, instead of seeing a bare GROUNDED-STITCH FALLBACK.

    ``context`` (optional): cross-stop ``StopContext`` forwarded to BOTH the narrow loop and
    the widened retry, so a widened-but-threaded stop still opens/bridges/pulls correctly.
    Threading buys ZERO leniency from the fact-check: the checker still runs against exactly
    ``facts`` (or ``wide_facts``) regardless of ``context``."""
    threaded = context is not None
    best_draft, best_result, attempts = _author_loop(
        facts, poi, lens, drafter=drafter, checker=checker, max_repairs=max_repairs, trace=trace,
        context=context,
    )
    if best_result.passed():
        return AuthorResult(
            text=best_draft, result=best_result, attempts=attempts, grounded_fallback=False,
            threaded=threaded,
        )

    rescued_not_served: tuple[str, ...] = ()

    # WIDEN FIRST: the more expensive but higher-craft rung must get its chance to converge
    # before either rescue rung below is even attempted — a narrow rescue that WOULD succeed
    # must never preempt it (the 8cc2fb6 regression this reordering fixes).
    widened_draft: str | None = None
    widened_result: FactCheckResult | None = None
    widened_facts: tuple[str, ...] = ()
    if widen is not None:
        wide_facts = widen()
        if wide_facts:
            wide_draft, wide_result, wide_attempts = _author_loop(
                wide_facts,
                poi,
                lens,
                drafter=drafter,
                checker=checker,
                max_repairs=wide_max_repairs,
                trace=trace,
                context=context,
            )
            attempts += wide_attempts
            if wide_result.passed():
                return AuthorResult(
                    text=wide_draft,
                    result=wide_result,
                    attempts=attempts,
                    grounded_fallback=False,
                    widened=True,
                    threaded=threaded,
                )
            widened_draft, widened_result, widened_facts = wide_draft, wide_result, wide_facts

    if widened_draft is not None:
        served, partial = _rescue_or_excise(
            widened_draft, widened_result, widened_facts, checker=checker,
            corpus_facts=corpus_facts, excise=excise, min_keep_ratio=min_keep_ratio,
            stitch_fallback=stitch_fallback,
        )
        rescued_not_served = partial
        if served is not None:
            text, result, rescued, excised = served
            return AuthorResult(
                text=text, result=result, attempts=attempts, grounded_fallback=False,
                widened=True, rescued=rescued, excised=excised, threaded=threaded,
            )

    # NARROW rescue/excise: only reached once widen (if configured) has already failed to
    # fully converge AND its own rescue/excise attempt (if any) also failed to serve.
    served, partial = _rescue_or_excise(
        best_draft, best_result, facts, checker=checker, corpus_facts=corpus_facts,
        excise=excise, min_keep_ratio=min_keep_ratio, stitch_fallback=stitch_fallback,
    )
    rescued_not_served = rescued_not_served + tuple(
        c for c in partial if c not in rescued_not_served
    )
    if served is not None:
        text, result, rescued, excised = served
        return AuthorResult(
            text=text, result=result, attempts=attempts, grounded_fallback=False,
            rescued=rescued, excised=excised, threaded=threaded,
        )
    # Deterministic floor: the grounded stitch is fact-complete and corpus-verbatim, so it
    # passes the check trivially — fidelity guaranteed even when the author won't converge.
    floor = checker.check(stitch_fallback, facts)
    return AuthorResult(
        text=stitch_fallback, result=floor, attempts=attempts + 1, grounded_fallback=True,
        rescued_not_served=rescued_not_served,
        threaded=threaded,
    )


def _rescue_or_excise(
    draft: str,
    result: FactCheckResult,
    facts: tuple[str, ...],
    *,
    checker: SemanticFactChecker,
    corpus_facts: Callable[[], tuple[str, ...]] | None,
    excise: bool,
    min_keep_ratio: float,
    stitch_fallback: str,
) -> tuple[tuple[str, FactCheckResult, tuple[str, ...], tuple[str, ...]] | None, tuple[str, ...]]:
    """Try to serve a FAILED draft via full-corpus RECHECK and/or surgical EXCISION,
    cheapest-and-least-lossy rung first. Returns ``(served, rescued_even_if_not_served)``:
    ``served`` is ``(served_text, served_result, rescued_claims, excised_sentences)`` on
    success, else ``None`` (caller falls through to the next rung / the grounded-stitch
    floor). ``rescued_even_if_not_served`` is populated whenever the corpus grounds ANY
    claim during THIS attempt — regardless of whether the attempt ultimately served —
    purely for the caller's ``AuthorResult.rescued_not_served`` auditability field; it never
    affects control flow. A no-op — returns ``(None, ())`` immediately, with NO extra
    checker calls — when neither ``corpus_facts`` nor ``excise`` is supplied, so every
    existing caller stays byte-identical.

    Guard: a genuine MISSING fact is a real drop the corpus recheck cannot repair (the
    corpus can only ADD support for an unsupported claim, never supply a fact the draft
    never stated), so this never runs — and ``corpus_facts`` is never even called — when
    ``result.missing_facts`` is non-empty; a coverage failure always falls through."""
    if corpus_facts is None and not excise:
        return None, ()
    if result.missing_facts or not result.unsupported_claims:
        return None, ()
    still = result.unsupported_claims
    rescued: tuple[str, ...] = ()
    corpus: tuple[str, ...] = ()
    if corpus_facts is not None:
        corpus = corpus_facts()
        if corpus:
            still = checker.unsupported_against(result.unsupported_claims, corpus)
            rescued = tuple(c for c in result.unsupported_claims if c not in still)
    if not still:
        return (draft, FactCheckResult((), ()), rescued, ()), rescued
    if excise:
        excised_out = _excise(
            draft, still, facts, checker=checker, min_keep_ratio=min_keep_ratio,
            stitch_fallback=stitch_fallback, corpus=corpus,
        )
        if excised_out is not None:
            text, res, dropped = excised_out
            return (text, res, rescued, dropped), rescued
    return None, rescued


def _excise(
    draft: str,
    unsupported: tuple[str, ...],
    facts: tuple[str, ...],
    *,
    checker: SemanticFactChecker,
    min_keep_ratio: float,
    stitch_fallback: str,
    corpus: tuple[str, ...] = (),
) -> tuple[str, FactCheckResult, tuple[str, ...]] | None:
    """SURGICAL EXCISION: drop ONLY the sentence(s) carrying ``unsupported`` claims, keep
    the rest of the authored prose VERBATIM, and re-check the remainder — COVERAGE against
    the NARROW ``facts`` (unrelaxed: a dropped fact is still a drop), FAITHFULNESS with one
    extra chance through the full-POI ``corpus`` (if given) for any claim the remainder's
    re-decomposition still flags unsupported. That second chance is NOT a relaxation: a
    claim only survives it by being entailed by facts the POI's OWN corpus actually states
    (``checker.unsupported_against``, the same strict entailer, never a guess) — it exists
    because dropping the invented sentence leaves the REST of the draft intact, including
    any sentence carrying a claim the corpus rescue already grounded (windowed out of
    ``facts`` but true), which the narrow-only recheck would otherwise re-flag and wrongly
    discard the whole excision for (the Vert-Galant shape: one windowed-out true claim next
    to one real invention). Returns ``(remainder_text, passed_result, dropped_sentences)``
    on success; ``None`` on any of four ABORT conditions (caller falls through to the
    grounded stitch):
      1. a claim maps to ZERO sentences (``checker.locate``) — we cannot prove where the
         invention lives, so we must not guess (the banned fuzzy/substring-match repair);
      2. the surviving text breaches the COLLAPSE FLOOR — fewer than
         ``ceil(min_keep_ratio * n)`` sentences, or fewer than 2 absolute. Phase-C authored
         stops run 5-12 sentences (~150 words); below the floor the survivor is a fragment,
         not a stop;
      3. the remainder still fails the fact-check — either a genuine COVERAGE drop (a
         required fact rode along with the invention: the Ravaillac shape, one sentence
         welds an invented modifier to a load-bearing fact) or a FAITHFULNESS residual the
         corpus does not ground either (a second, un-rescuable invention);
      4. the remainder's deterministic craft score is WORSE than the stitch it would
         replace — a grounded-but-mutilated remainder (dangling anaphora: a dropped
         sentence can strand the next one, e.g. "But their blood soaked his clothes...")
         passes every fact gate yet still delivers the exact register-crash the stitch
         fallback exists to avoid, so serving it would be a net loss. (Only the SURGICALLY
         CUT remainder is gated this way — the plain corpus-rescue rung, which ships the
         draft unmutilated, is deliberately exempt; see ``author_compose_stop``'s
         ``excise`` docstring paragraph, CRAFT FLOOR note.)"""
    sents = [s for s in (p.strip() for p in split_sentences(draft)) if s]
    if not sents:
        return None
    located = checker.locate(unsupported, tuple(sents))
    drop_idxs: set[int] = set()
    for claim in unsupported:
        idxs = located.get(claim, ())
        if not idxs:
            return None  # unlocatable -> cannot safely excise -> stitch
        drop_idxs.update(idxs)
    kept = [s for i, s in enumerate(sents) if i not in drop_idxs]
    dropped = tuple(s for i, s in enumerate(sents) if i in drop_idxs)
    if len(kept) < 2 or len(kept) < math.ceil(min_keep_ratio * len(sents)):
        return None  # collapse floor breached -> stitch
    remainder = " ".join(kept)
    result = checker.check(remainder, facts)
    if result.missing_facts:
        return None  # a required fact rode along with the invention -> stitch (unrelaxed)
    if result.unsupported_claims:
        residual = (
            checker.unsupported_against(result.unsupported_claims, corpus)
            if corpus else result.unsupported_claims
        )
        if residual:
            return None  # a genuine invention the corpus does not ground either -> stitch
        # every claim the narrow recheck flagged is corpus-grounded (a rescued claim's
        # sentence surviving alongside the excised one) -> treat the remainder as clean.
        result = FactCheckResult((), result.missing_facts)
    if craft_score(remainder) < craft_score(stitch_fallback):
        return None  # grounded but worse-crafted than the stitch it would replace -> stitch
    return remainder, result, dropped


def _draft_write(drafter: Drafter, facts, poi: str, lens: str, context: StopContext | None) -> str:
    """Calls ``drafter.write`` WITHOUT a ``context`` kwarg when ``context`` is ``None`` — so
    drafters written before threading existed (no ``context`` parameter at all, e.g. the
    pre-threading test fakes) never see an unexpected keyword argument and keep working
    unmodified."""
    if context is not None:
        return drafter.write(facts, poi, lens, context=context)
    return drafter.write(facts, poi, lens)


def _draft_rewrite(
    drafter: Drafter, facts, draft: str, result: FactCheckResult, poi: str, lens: str,
    context: StopContext | None,
) -> str:
    """The ``rewrite`` mirror of ``_draft_write`` — same no-kwarg-unless-present rule."""
    if context is not None:
        return drafter.rewrite(facts, draft, result, poi, lens, context=context)
    return drafter.rewrite(facts, draft, result, poi, lens)


def _author_loop(
    facts: tuple[str, ...],
    poi: str,
    lens: str,
    *,
    drafter: Drafter,
    checker: SemanticFactChecker,
    max_repairs: int,
    trace: list[tuple[str, FactCheckResult]] | None,
    context: StopContext | None = None,
) -> tuple[str, FactCheckResult, int]:
    """One draft + bounded repair pass; returns (best_draft, best_result, attempts)."""
    draft = _draft_write(drafter, facts, poi, lens, context)
    result = checker.check(draft, facts)
    if trace is not None:
        trace.append((draft, result))
    best_draft, best_result = draft, result
    attempts = 1
    while not best_result.passed() and attempts <= max_repairs:
        cand = _draft_rewrite(drafter, facts, best_draft, best_result, poi, lens, context)
        if cand.strip():
            cand_result = checker.check(cand, facts)
            if trace is not None:
                trace.append((cand, cand_result))
            if _failure_count(cand_result) < _failure_count(best_result):
                best_draft, best_result = cand, cand_result
        elif trace is not None:
            # empty/collapsed rewrite: record it (conveys nothing -> all facts missing) but
            # never adopt it; the next repair retries from the best draft, not this ruin.
            trace.append((cand, FactCheckResult((), facts)))
        attempts += 1
    return best_draft, best_result, attempts


def _failure_count(result: FactCheckResult) -> int:
    """Total fact-check failures (unsupported + missing); 0 == faithful and complete."""
    return len(result.unsupported_claims) + len(result.missing_facts)


def _facts_for_stop(
    stop_idx: int, stitched: Script, beats_by_id: dict
) -> tuple[str, ...]:
    """The grounded facts of one stop: each cited beat's key_claims (or, keyless, its body
    sentences), order-preserved + deduped. Same derivation the author scripts use."""
    facts: list[str] = []
    seen: set[str] = set()
    for s in stitched.script:
        if s.stop_idx != stop_idx or s.source_type != "beat":
            continue
        b = beats_by_id.get(s.source_id)
        if not b:
            continue
        items = list(getattr(b, "key_claims", ()) or ()) or [
            p.strip() for p in split_sentences(getattr(b, "script_body", "") or "")
        ]
        for it in items:
            if it and it not in seen:
                seen.add(it)
                facts.append(it)
    return tuple(facts)


def _served_text(sents: list[Sentence]) -> str:
    """The narration a stop actually SERVED (author prose or the grounded stitch — whichever
    ``_author_stop`` emitted), joined in order. Glue/transition sentences are excluded: only
    the beat-cited content is "what the stop said" for threading purposes."""
    return " ".join(s.text for s in sents if s.source_type == "beat")


def _one_sentence_summary(text: str) -> str:
    """The one-sentence summary threaded forward as ``StopContext.prev_summary``.

    Structural rule (no meaning-inference): the LAST sentence of the served text, via the
    same ``split_sentences`` splitter used throughout this module. This deliberately departs
    from "the stop's first sentence" — live evidence (specs/2026-07-18-tour-qa-campaign/
    PHASE-C-RESULTS.md) shows ``_AUTHOR_SYSTEM`` instructs the drafter to open on a
    contentless MOMENT and build tension to a late payoff, so authored OPENERS are routinely
    zero-content ("Listen for hooves.") while CLOSERS are consistently callback-grade ("The
    kings never came back to the island."). The first sentence would hand the next stop
    nothing to bridge from; the last is what the walker actually just heard."""
    sents = [s.strip() for s in split_sentences(text) if s.strip()]
    return sents[-1] if sents else ""


def author_compose_script(
    stitched: Script,
    beat_sequence: BeatSequence,
    route: Route,
    *,
    lens: str,
    drafter: Drafter,
    checker: SemanticFactChecker,
    max_repairs: int = 3,
    max_workers: int = 6,
    thread: bool = False,
) -> tuple[Script, dict[int, bool]]:
    """Author-engine counterpart to ``compose_script_per_chapter``: write each dwell stop
    FRESH from its grounded facts (fact-check-and-repair, grounded-stitch floor), then
    reassemble into the same ``Script`` shape the endpoint already returns.

    Per stop, the beat sentences are REPLACED by the author prose (each sentence cited to
    the UNION of that stop's beats, so ``source_type='beat'`` + traceability hold); non-beat
    sentences (glue / transitions / reflections) are preserved in place. A stop that will not
    converge serves its grounded stitch (``author_compose_stop``'s floor), so a served stop
    is ALWAYS either 0-unsupported/0-missing author prose or the exact stitch — never a
    non-converged draft. Returns ``(script, grounded_fallback_by_stop)``. The intelligence
    (Opus drafter + calibrated checker) is injected, so this is fully testable offline.

    ``thread`` (default ``False``, byte-identical to today when unset — the production API
    path never sets it): when ``True``, stops are authored SERIALLY in ascending order
    (never via the ``ThreadPoolExecutor`` below) so each stop's ``StopContext`` can carry the
    PREVIOUS content-bearing stop's one-sentence summary, and the NEXT content-bearing stop's
    POI (used only to GATE the pull instruction — its literal name is never spliced into the
    prompt, see ``_threading_addendum``) + this stop's narrative ``position``
    ("opening"/"middle"/"finale", with a single content stop labelled "finale" since it is
    the last thing the walker hears). Glue/vignette-only stops (no beat sentences) are
    transparent to threading: they neither receive nor interrupt the prev/next chain.
    ``position``/``next_poi`` are computed over the stops that will actually be AUTHORED
    (those with beat content), never over the raw ``sorted(by_stop)`` keys, so a glue/
    orientation stop at index 0 does not steal the "opening" label from the first real stop.
    Threading is strictly a PROMPT addition — the fact-check contract is unchanged, so a
    threaded bridge that invents a connective fact still fails and still falls back (see
    ``test_threaded_bridge_that_invents_still_falls_back``)."""
    beats_by_id = {b.id: b for plan in beat_sequence.poi_beats for b in plan.beats}
    poi_name_by_stop = {i: p.name for i, p in enumerate(route.pois)}
    by_stop: dict[int, list[Sentence]] = defaultdict(list)
    for s in stitched.script:
        by_stop[s.stop_idx].append(s)
    stops = sorted(by_stop)
    # Stops that will actually be AUTHORED/served-with-content (have beat sentences) — the
    # ONLY stops eligible for a narrative position or a prev/next link. Glue/vignette-only
    # stops (author.py's own "nothing to author" case below) are invisible to threading.
    content_stops = [i for i in stops if any(s.source_type == "beat" for s in by_stop[i])]

    def _author_stop(
        stop_idx: int, context: StopContext | None = None
    ) -> tuple[int, list[Sentence], bool]:
        stop_sents = by_stop[stop_idx]
        beat_sents = [s for s in stop_sents if s.source_type == "beat"]
        if not beat_sents:
            return stop_idx, list(stop_sents), False  # vignette/glue-only: nothing to author
        facts = _facts_for_stop(stop_idx, stitched, beats_by_id)
        stitch = " ".join(s.text for s in beat_sents)
        if not facts:  # keyless + bodiless -> nothing to write from; keep the grounded stitch
            return stop_idx, list(stop_sents), True
        poi = poi_name_by_stop.get(stop_idx, "this stop")
        res = author_compose_stop(
            facts, poi, lens, drafter=drafter, checker=checker,
            stitch_fallback=stitch, max_repairs=max_repairs, context=context,
        )
        if res.grounded_fallback:
            return stop_idx, list(stop_sents), True  # keep the stitch sentences verbatim
        cited = tuple(dict.fromkeys(s.source_id for s in beat_sents))  # union, order-preserved
        primary, also = cited[0], cited[1:]
        author_sents = [
            Sentence(text=t.strip(), source_id=primary, source_type="beat",
                     stop_idx=stop_idx, also_cites=also)
            for t in split_sentences(res.text) if t.strip()
        ]
        if not author_sents:  # defensive: never emit an empty stop
            return stop_idx, list(stop_sents), True
        out: list[Sentence] = []
        inserted = False
        for s in stop_sents:  # replace the run of beat sentences; keep glue in place
            if s.source_type == "beat":
                if not inserted:
                    out.extend(author_sents)
                    inserted = True
            else:
                out.append(s)
        return stop_idx, out, False

    if thread:
        results: list[tuple[int, list[Sentence], bool]] = []
        prev_summary = ""
        for stop_idx in stops:
            ctx: StopContext | None = None
            if stop_idx in content_stops:
                i = content_stops.index(stop_idx)
                # Finale is checked FIRST: a tour with exactly one content stop has
                # i == 0 == len(content_stops) - 1, and it is the LAST thing the walker
                # hears, so it must get the closing instruction, not "opening".
                if i == len(content_stops) - 1:
                    position = "finale"
                elif i == 0:
                    position = "opening"
                else:
                    position = "middle"
                next_poi = (
                    poi_name_by_stop.get(content_stops[i + 1], "")
                    if i + 1 < len(content_stops)
                    else ""
                )
                ctx = StopContext(
                    prev_summary=prev_summary, next_poi=next_poi, position=position,
                )
            stop_idx_out, sents, fb = _author_stop(stop_idx, ctx)
            results.append((stop_idx_out, sents, fb))
            if stop_idx in content_stops:  # only content stops update the chain
                prev_summary = _one_sentence_summary(_served_text(sents))
    else:
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(stops)))) as pool:
            results = list(pool.map(_author_stop, stops))
    out_by_stop = {i: sents for i, sents, _ in results}
    fell_back = {i: fb for i, _, fb in results}
    out: list[Sentence] = []
    for stop_idx in stops:
        out.extend(out_by_stop[stop_idx])
    script = stitched.model_copy(update={"script": tuple(out), "validation": ValidationReport()})
    return script, fell_back


# --- the drafter prompts (the author voice + the repair instruction) ---
_AUTHOR_SYSTEM = (
    "You are a master audio walking-tour writer. Write ONE dwell-stop of narration for a "
    "walker standing at {poi} ({lens} lens).\n"
    "First, silently PLAN the arc: choose the strongest hook to open on, and order the "
    "material so tension BUILDS to a payoff late, not buried in the middle.\n"
    "Then WRITE flowing spoken prose: open on a MOMENT (never a label/date); CONNECT facts "
    "causally, each sentence handing off to the next (never a list of closed declaratives); "
    "vary rhythm HARD (a sentence under 8 words AND a longer line; never 3 of the same shape "
    "in a row); SAY EACH FACT ONCE; render dark material plainly, then move on. ~150 words, "
    "second person, warm, heard once.\n"
    "STRICT GROUNDING — this is non-negotiable and a fact-checker will verify it: use ONLY "
    "the facts below and keep EVERY one. Add NO name, date, number, material, place, or "
    "detail that is not in the facts — not even a plausible one (do NOT call a bell "
    "'bronze' or a figure someone's 'sister' unless the facts say so). Your vividness comes "
    "from RHYTHM, STRUCTURE, and how you CONNECT the facts — never from inventing detail. "
    "Rephrasing a fact is welcome; adding a new fact is forbidden.\n"
    "KEEP EACH FACT ON ITS OWN SUBJECT — this stop is {poi}, and it may contain or sit near "
    "other named things (a tower, a hall, a person). A fact the facts state about ONE subject "
    "must land on THAT subject: never let a property slide onto a different entity just "
    "because you named it in the last breath. If a fact is about {poi}, name {poi} (or a "
    "pronoun a listener cannot mishear); if it is about the tower, name the tower. A "
    "fact-checker will reject 'the tower is the oldest prison' when the facts say the PLACE "
    "is. When two things could be confused, name the one you mean. Return ONLY the narration."
)
_REWRITE_SYSTEM = (
    "You are revising ONE audio walking-tour stop at {poi} ({lens} lens). Keep the flow and "
    "voice of the draft, but FIX exactly the problems listed below and change nothing else:\n"
    "1. RESTORE every DROPPED fact below — weave each into the sentence that covers its "
    "topic; do not tack them on as a list, and do not repeat anything already said.\n"
    "2. FIX every UNSUPPORTED statement below. Each is unsupported for ONE of two reasons — "
    "diagnose which, then fix it that way (do NOT just delete a fact you can re-attach):\n"
    "   (a) ADDED DETAIL the facts do not contain (an invented material, name, number, date, "
    "or claim) — CUT that detail, or rephrase to say only what the facts say.\n"
    "   (b) MIS-ATTRIBUTION — the detail IS in the facts, but you attached it to the WRONG "
    "subject (e.g. you credited a property to place/person X when the facts credit it to Y, "
    "though both appear in the facts). Do NOT delete the fact: RE-ATTACH it by NAMING the "
    "exact subject the facts name (write the place's name, not 'the tower' or 'it'), so no "
    "listener and no fact-checker can mistake which one you mean.\n"
    "Add NOTHING new — no plausible-sounding detail, no inference beyond the facts — and "
    "never STRENGTHEN a fact's scope (if the facts say 'one of the oldest', do not write 'the "
    "oldest').\n"
    "CRITICAL: the revised narration must STILL CONTAIN EVERY SOURCE FACT and be about the "
    "same length as the draft or longer. NEVER shorten it or drop a fact to make a flag go "
    "away — fix the flagged sentence in place. Returning a short or empty narration fails.\n"
    "Keep it flowing, second person; vividness from rhythm, not new facts. Return ONLY the "
    "revised narration."
)
# Appended (formatted) to either system prompt above ONLY when a StopContext is present —
# a context=None call (every existing caller, incl. the production API path) formats
# neither prompt with this text, so the no-context prompts stay byte-identical.
#
# KILLER-DEFECT FIX (hostile-verifier must-fix #1): an earlier draft of this addendum
# instructed the drafter to "open on a brief bridge OR CALLBACK to" the previous stop's
# content, and separately told it to "call back to something THIS TOUR ALREADY SAID" — both
# invite a flat declarative restatement of the previous/next stop's content, which
# factcheck.py's decomposer extracts as an ordinary checkable claim and its
# _FAITHFULNESS_JUDGE_USER TEST 3 rejects outright (it names an entity / detail absent from
# THIS stop's FACTS). That is the exact fallback disaster the author engine exists to avoid:
# an instruction that itself licenses the thing the checker is documented to reject.
#
# The fix constrains a bridge/pull to ONLY the forms _DECOMPOSE_SYSTEM's own EXCLUDE list
# names (second-person address, rhetorical question, sensory/imaginative framing) — forms
# that structurally carry no checkable proposition, by the decomposer's own contract — and
# explicitly forbids naming any entity (a place, e.g. the next POI) that is not in THIS
# stop's FACTS. Restated three ways on purpose, with the ambiguous "callback to what was
# said" phrasing dropped entirely. The checker is still the backstop of last resort (see
# test_threaded_bridge_that_invents_still_falls_back): a drafter that ignores this
# instruction anyway still gets caught and falls back, never smuggled through.
_THREADING_ADDENDUM = (
    "\n\nCROSS-STOP CONTINUITY: this narration is the {position} stop of a walking tour — "
    "it will be heard right after the previous stop and right before the next, not read as "
    "a stand-alone essay.\n"
    "{bridge_clause}{pull_clause}"
    "Any bridge or pull must be RHETORICAL ONLY: a second-person address, a question, or "
    "sensory/imaginative framing — the exact forms a fact-checker's claim-decomposer already "
    "excludes from checking, and nothing else. It must NEVER assert a new fact: never "
    "restate, describe, or name ANY detail (a place, a date, an appearance, a reason, a "
    "relationship) about the previous or next stop as a flat declarative statement — even a "
    "detail this tour narrated earlier is not in THIS stop's FACTS, and the fact-checker "
    "gates every sentence of this stop against exactly those FACTS, nothing more. If a "
    "bridge or pull cannot be phrased as a question, a second-person address, or sensory "
    "framing, leave it out and move straight into this stop's own material."
)


def _threading_addendum(context: StopContext) -> str:
    """Builds the ``_THREADING_ADDENDUM`` fill-ins from ``context``. Pure string assembly —
    no meaning-inference. The bridge clause surfaces ``prev_summary`` to the model as
    CONTEXT ONLY (never to be repeated as a stated fact); the pull clause NEVER splices
    ``next_poi``'s literal name into the prompt text (only its truthiness gates which clause
    applies) — naming it would itself be the licensed-invention defect this addendum exists
    to prevent."""
    bridge_clause = (
        "For context only (never to be repeated as a stated fact), the previous stop just "
        f'left the walker with this: "{context.prev_summary}" Gesture at that moment '
        "rhetorically — a second-person nod or a question — before moving into this stop's "
        "own material; never restate, describe, or assert it as a declarative sentence.\n"
        if context.prev_summary
        else ""
    )
    if context.position == "finale":
        pull_clause = (
            "This is the FINAL stop of the tour — give it an actual close, not another "
            "opener.\n"
        )
    elif context.next_poi:
        pull_clause = (
            "Before you finish, plant a forward pull — a question or a second-person "
            "gesture toward what's still ahead — never naming or describing the next stop, "
            "just building anticipation.\n"
        )
    else:
        pull_clause = ""
    return _THREADING_ADDENDUM.format(
        position=context.position, bridge_clause=bridge_clause, pull_clause=pull_clause
    )


class LLMDrafter:
    """Real author drafter (Opus by default). Defers the anthropic import so unit tests
    never need the SDK; only constructed on the live path."""

    def __init__(self, model: str, *, client: object = None, max_tokens: int = 4000) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.max_tokens = max_tokens
        self.calls = 0

    def _once(self, system: str, user: str, *, thinking: dict | None) -> str:
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        # DETERMINISM (2026-07-18). All three Haiku judges pin temperature=0 — factcheck.py
        # says why: "a claim's verdict must not flip between runs". The DRAFTER did not, so
        # it ran at the API default and wrote different prose every run, which crossed the
        # fact-check threshold differently, which made whole STOPS converge or fall back at
        # random. Measured: the same NYC tour authored 35 minutes apart swapped which stops
        # fell back (Castle Clinton + Wall Street vs Battery Park + Bowling Green), and the
        # same for Paris. That instability read as "the fix moved the failure" all evening.
        # Extended thinking rejects temperature, so it is set only on the no-thinking rung.
        if thinking is None:
            kwargs["temperature"] = 0
        else:
            kwargs["thinking"] = thinking
        resp = self._client.messages.create(**kwargs)  # type: ignore[attr-defined]
        return "".join(
            getattr(b, "text", "") for b in (getattr(resp, "content", []) or []) if b.type == "text"
        ).strip()

    def _call(self, system: str, user: str) -> str:
        self.calls += 1
        # Adaptive thinking can consume the entire token budget on a hard stop/repair and
        # return NO text (the empty-collapse that stranded Hôtel-Dieu). If that happens, retry
        # once WITHOUT extended thinking so the model spends its budget on prose instead.
        text = self._once(system, user, thinking={"type": "adaptive"})
        if not text:
            text = self._once(system, user, thinking=None)
        return text

    def write(
        self, facts: tuple[str, ...], poi: str, lens: str, *, context: StopContext | None = None
    ) -> str:
        system = _AUTHOR_SYSTEM.format(poi=poi, lens=lens)
        if context is not None:
            system += _threading_addendum(context)
        return self._call(system, "FACTS:\n- " + "\n- ".join(facts))

    def rewrite(
        self,
        facts: tuple[str, ...],
        draft: str,
        result: FactCheckResult,
        poi: str,
        lens: str,
        *,
        context: StopContext | None = None,
    ) -> str:
        user = (
            "SOURCE FACTS (the only allowed material):\n- " + "\n- ".join(facts)
            + "\n\nDROPPED FACTS you must restore:\n- "
            + ("\n- ".join(result.missing_facts) or "(none)")
            + "\n\nUNSUPPORTED statements you must remove or fix:\n- "
            + ("\n- ".join(result.unsupported_claims) or "(none)")
            + "\n\nDRAFT to revise:\n" + draft
        )
        system = _REWRITE_SYSTEM.format(poi=poi, lens=lens)
        if context is not None:
            system += _threading_addendum(context)
        return self._call(system, user)


__all__ = [
    "AuthorResult",
    "Drafter",
    "LLMDrafter",
    "StopContext",
    "author_compose_script",
    "author_compose_stop",
]
