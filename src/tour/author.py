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

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from .contract import BeatSequence, Route, Script, Sentence, ValidationReport
from .factcheck import FactCheckResult, SemanticFactChecker
from .generation import split_sentences


class Drafter(Protocol):
    """Writes a stop's narration from its facts, and rewrites it against a repair signal.
    The intelligence (the LLM) lives here; the loop below is pure orchestration."""

    def write(self, facts: tuple[str, ...], poi: str, lens: str) -> str: ...

    def rewrite(
        self, facts: tuple[str, ...], draft: str, result: FactCheckResult, poi: str, lens: str
    ) -> str: ...


@dataclass(frozen=True)
class AuthorResult:
    text: str
    result: FactCheckResult  # the fact-check verdict on ``text``
    attempts: int  # how many draft/rewrite rounds ran
    grounded_fallback: bool  # True iff we fell back to the grounded stitch


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
    worse one. An empty rewrite is treated as a total miss and never adopted."""
    draft = drafter.write(facts, poi, lens)
    result = checker.check(draft, facts)
    if trace is not None:
        trace.append((draft, result))
    best_draft, best_result = draft, result
    attempts = 1
    while not best_result.passed() and attempts <= max_repairs:
        cand = drafter.rewrite(facts, best_draft, best_result, poi, lens)
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
    if best_result.passed():
        return AuthorResult(
            text=best_draft, result=best_result, attempts=attempts, grounded_fallback=False
        )
    # Deterministic floor: the grounded stitch is fact-complete and corpus-verbatim, so it
    # passes the check trivially — fidelity guaranteed even when the author won't converge.
    floor = checker.check(stitch_fallback, facts)
    return AuthorResult(
        text=stitch_fallback, result=floor, attempts=attempts + 1, grounded_fallback=True
    )


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
    (Opus drafter + calibrated checker) is injected, so this is fully testable offline."""
    beats_by_id = {b.id: b for plan in beat_sequence.poi_beats for b in plan.beats}
    poi_name_by_stop = {i: p.name for i, p in enumerate(route.pois)}
    by_stop: dict[int, list[Sentence]] = defaultdict(list)
    for s in stitched.script:
        by_stop[s.stop_idx].append(s)
    stops = sorted(by_stop)

    def _author_stop(stop_idx: int) -> tuple[int, list[Sentence], bool]:
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
            stitch_fallback=stitch, max_repairs=max_repairs,
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
        if thinking is not None:
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

    def write(self, facts: tuple[str, ...], poi: str, lens: str) -> str:
        return self._call(
            _AUTHOR_SYSTEM.format(poi=poi, lens=lens), "FACTS:\n- " + "\n- ".join(facts)
        )

    def rewrite(
        self, facts: tuple[str, ...], draft: str, result: FactCheckResult, poi: str, lens: str
    ) -> str:
        user = (
            "SOURCE FACTS (the only allowed material):\n- " + "\n- ".join(facts)
            + "\n\nDROPPED FACTS you must restore:\n- "
            + ("\n- ".join(result.missing_facts) or "(none)")
            + "\n\nUNSUPPORTED statements you must remove or fix:\n- "
            + ("\n- ".join(result.unsupported_claims) or "(none)")
            + "\n\nDRAFT to revise:\n" + draft
        )
        return self._call(_REWRITE_SYSTEM.format(poi=poi, lens=lens), user)


__all__ = [
    "AuthorResult",
    "Drafter",
    "LLMDrafter",
    "author_compose_script",
    "author_compose_stop",
]
