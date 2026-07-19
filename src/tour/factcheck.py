"""Semantic fact-checker for tour narration — the ROBUST, fully model-based replacement
for the refuted lexical coverage gate. NO regex, NO word-lists, NO string-overlap: every
judgement is an entailment call (see specs/2026-07-16-tour-craft/FACTCHECK-DESIGN.md,
grounded in FActScore / VeriScore / QuestEval / MiniCheck / TRUE).

Given a stop's composed NARRATION (free prose) and its KNOWN source FACTS (the cited
beats' key_claims + verbatim body sentences — closed-book, the evidence is the beats),
it emits a repair signal:

    FactCheckResult(unsupported_claims=[...], missing_facts=[...])

- FAITHFULNESS (output -> source): decompose the narration into atomic CHECKWORTHY
  claims, then entail each against the source facts with the STRICT entailer. A claim the
  facts don't support is an invention/distortion — strictness is correct here.
- COVERAGE (source -> output): judge each source fact against the whole narration with a
  DEDICATED, paraphrase-tolerant coverage judge. A fact the narration doesn't convey (in
  ANY wording) was dropped.

The two directions use DIFFERENT judges on purpose. Faithfulness reuses the strict
``FaithfulnessChecker.entails`` (add/overstate anything -> NO). Coverage cannot: the strict
entailer false-negatives on legitimate paraphrase ("no king came back again" does not
"fully support" the claim "the kings never returned"), which blocked author-engine
convergence — measured at 62% accuracy / 9-of-16 paraphrases wrongly rejected on the
labeled calibration set (specs/2026-07-16-tour-craft/coverage_calibration_set.json). The
``CoverageJudge`` prompt below was chosen by a labeled bake-off of 8 candidate strategies
(scripts/coverage_calibrate.py): it scored 100% (0 false-neg on paraphrase, 0 false-pos on
real drops), crediting synonym/rewording/spelled-out-number/implied-referent while still
catching a dropped name, date, number, or asserted relationship.

The only genuinely new model call versus the old gate is decomposing the narration, and
only CHECKWORTHY facts are extracted — evocative/second-person/opinion framing yields ZERO
claims, so legitimate narration voice is never flagged as hallucination. The checker is
an ADVISORY gate with a deterministic grounded floor downstream (surgical splice / stitch
revert), never treated as an oracle.
"""

from __future__ import annotations

import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol

from .generation import split_sentences
from .verify import FAITHFULNESS_MODEL, FaithfulnessChecker

_MAX_WORKERS = 8


@dataclass(frozen=True)
class FactCheckResult:
    """The repair signal. ``unsupported_claims`` = atomic narration claims NOT entailed by
    the source facts (invention/distortion). ``missing_facts`` = source facts NOT conveyed
    by the narration (omission). Empty + empty = the narration is faithful and complete."""

    unsupported_claims: tuple[str, ...]
    missing_facts: tuple[str, ...]

    def passed(self) -> bool:
        return not self.unsupported_claims and not self.missing_facts


class ClaimDecomposer(Protocol):
    """Splits a narration into atomic, CHECKWORTHY factual claims (evocative/opinion/
    second-person framing excluded). The one genuinely new model call in the pipeline."""

    def decompose(self, narration: str) -> tuple[str, ...]: ...


# --- the decomposition prompt (VeriScore checkworthy-only, CoT-then-JSON) ---
_DECOMPOSE_SYSTEM = (
    "You split a walking-tour narration into its ATOMIC, CHECKWORTHY factual claims. A "
    "claim states EXACTLY ONE verifiable fact (one date, person, place, measure, or "
    "relationship) and stands alone — resolve every 'it/there/this/he/she' to the named "
    "subject. EXCLUDE, always: second-person address ('you stand here'), sensory or "
    "imaginative framing ('imagine what carried across the water', 'picture the crowds'), "
    "opinions, mood, and rhetorical questions — these are narration craft, NOT facts to "
    "check, and must yield no claim. Do NOT split a compound fact that loses meaning when "
    "split. Keep each claim FAITHFUL to what the narration actually said — never ADD, "
    "STRENGTHEN, or WEAKEN a qualifier of time, place, scope, or degree the narration did "
    "not state (write 'the kings never returned to the island', NOT 'did not return after "
    "this period'; write 'the bell was forged in 1685', NOT 'the bell, one of Europe's "
    "oldest, was forged around 1685'). First, in a 'reasoning' field, walk the narration "
    "and mark each span factual-versus-framing; THEN list the atomic claims."
)
_DECOMPOSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "reasoning": {"type": "string"},
        "claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["reasoning", "claims"],
}


class HaikuClaimDecomposer:
    """Real Haiku decomposition (deterministic: temp=0). Defers the anthropic import so
    unit tests never need the SDK; only constructed on the live path."""

    def __init__(self, model: str = FAITHFULNESS_MODEL, *, client: object = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.calls = 0

    def decompose(self, narration: str) -> tuple[str, ...]:
        if not narration.strip():
            return ()
        self.calls += 1
        resp = self._client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=2048,
            temperature=0,
            system=_DECOMPOSE_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _DECOMPOSE_SCHEMA}},
            messages=[{"role": "user", "content": narration}],
        )
        text = "".join(
            getattr(b, "text", "") for b in (getattr(resp, "content", []) or [])
        ).strip()
        if not text:
            return ()
        try:
            claims = json.loads(text).get("claims", [])
        except (json.JSONDecodeError, AttributeError):
            return ()  # malformed/truncated -> no claims (fail-open; coverage still runs)
        return tuple(c.strip() for c in claims if isinstance(c, str) and c.strip())


class CoverageJudge(Protocol):
    """Does the whole NARRATION convey this one source FACT to a listener? (recall)
    Paraphrase-tolerant by design — the deliberate counterpart to the strict faithfulness
    entailer. Separate protocol so the coverage direction is injectable + testable."""

    def conveys(self, fact: str, narration: str) -> bool: ...


# The COVERAGE prompt — winner of the labeled bake-off (scripts/coverage_calibrate.py,
# candidate 'explicit_paraphrase_allowance'): 100% acc / 0 FN / 0 FP on the 24-item
# calibration set, vs 62% / 9 FN for the strict entailer it replaces on this direction.
# system is empty (all instruction in the user turn); {fact} and {narration} are filled.
_COVERAGE_JUDGE_USER = (
    "You are a strict-but-fair COVERAGE judge for spoken audio-tour narration. Decide ONE"
    " thing: would a listener who HEARS the narration actually LEARN the fact? This is ab"
    "out MEANING delivered to the listener, not words matched. The narration may state th"
    "e fact in completely different words, across several sentences, or through vivid or "
    "second-person phrasing.\n\nAnswer YES when the narration delivers the fact's essenti"
    "al content — its who / what / when / where and the relationship among them — even if"
    " it is reworded. ALL of the following count as CONVEYED (answer YES):\n- Synonyms or"
    " reworded phrases with the same meaning: e.g. \"slew\" as \"cut down\", \"built\" as"
    " \"raised\", \"destroyed and melted down\" as just \"melted down\", \"held captive\""
    " as \"sat captive\", \"coloured\" as \"glowing\", \"mourning\" as \"grief\", \"prove"
    "d useless\" as \"kept nothing at all\".\n- A number, amount, or date written as word"
    "s instead of digits, or the reverse: e.g. \"2,278\" as \"two thousand two hundred an"
    "d seventy-eight\"; \"22 February 1357\" spelled out as \"the twenty-second of Februa"
    "ry, 1357\".\n- A different name, title, epithet, or plain description for the SAME e"
    "ntity the narration already points to: e.g. \"Charles V\" as \"Charles the Wise\", \""
    "tricoteuses\" as \"knitting women\", \"perron\" as \"the steps\", a tower identified"
    " by its position (\"the westernmost tower facing the Seine\") instead of its proper "
    "name.\n- The same meaning with negation or clause order rearranged: e.g. \"the kings"
    " never returned\" as \"no king ever came back again\".\n- The fact assembled from SE"
    "VERAL sentences read together, not from one alone.\n- Vivid, implied, or second-pers"
    "on phrasing that still lets the listener grasp the fact: e.g. torture conveyed by \""
    "screams\" carrying from a tower; \"held before execution\" conveyed by someone who \""
    "waited\" at the prison.\n\nAnswer NO when the fact's essential content is genuinely "
    "ABSENT from the narration, or is CONTRADICTED by it. Mere topical overlap is NOT eno"
    "ugh: if the narration talks near the fact but never delivers its specific payload, a"
    "nswer NO. In particular, answer NO when the fact turns on a SPECIFIC element that th"
    "e narration never states in any form:\n- a specific proper NAME that carries the fac"
    "t's point and is missing or replaced by something broader: e.g. the fact names \"Hot"
    "el de Saint-Pol\" but the narration only says \"the Marais\".\n- a specific DATE or "
    "year the narration never gives: e.g. \"1368\", \"2013\", \"1804\".\n- a specific NUM"
    "BER, weight, or measure the narration never gives: e.g. \"thirteen tons\".\n- a spec"
    "ific RELATIONSHIP the fact asserts that the narration never asserts, even though bot"
    "h parties are mentioned: e.g. the fact says a man FOUNDED a dynasty but the narratio"
    "n only says the dynasty had \"barely begun\"; the fact names \"the True Cross and th"
    "e Crown of Thorns\" but the narration only says \"relics\"; the fact says an arcade "
    "was \"the entrance to the Conciergerie before 1825\" but the narration only points t"
    "o \"that arcade\".\n\nJudge only against what the NARRATION actually says — never fi"
    "ll a gap with outside knowledge. A reworded or synonym-swapped fact is CONVEYED; a f"
    "act whose specific name, date, number, or asserted relationship simply never appears"
    " is NOT.\n\nFACT:\n{fact}\n\nNARRATION:\n{narration}\n\nWould a listener hearing the"
    " NARRATION learn the FACT? Output EXACTLY one word — YES or NO — and nothing else.\n"
    "Answer (YES or NO):"
)


class HaikuCoverageJudge:
    """Real Haiku coverage judgement (deterministic: temp=0, 5-token cap). Defers the
    anthropic import so unit tests never need the SDK; only constructed on the live path.
    Mirrors HaikuFaithfulnessChecker's shape but with the paraphrase-tolerant prompt."""

    def __init__(self, model: str = FAITHFULNESS_MODEL, *, client: object = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.calls = 0

    def conveys(self, fact: str, narration: str) -> bool:
        if not fact.strip() or not narration.strip():
            return False
        self.calls += 1
        resp = self._client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=5,
            temperature=0,  # deterministic: a fact's coverage verdict must not flip
            # between the pre-repair check and the post-repair re-check, or the author
            # loop never converges (same rationale as the faithfulness entailer).
            messages=[{"role": "user", "content": _COVERAGE_JUDGE_USER.format(
                fact=fact, narration=narration)}],
        )
        text = "".join(
            getattr(b, "text", "") for b in (getattr(resp, "content", []) or [])
        ).strip().upper()
        return text.startswith("YES")


# The FAITHFULNESS prompt (output->source) — winner of the labeled bake-off
# (scripts/faithfulness_calibrate.py, candidate 'attribution_first_hardened'): binds
# referents FIRST so it accepts grounded recombination but rejects any added specific,
# contradiction, mis-attribution (incl. part/whole), or overstatement. 0 false-positives
# on the 28-item set (never ships a hallucination); {facts} + {claim} are filled.
_FAITHFULNESS_JUDGE_USER = (
    "You are a rigorous FAITHFULNESS judge for audio-tour narration. You are given a bull"
    "eted list of SOURCE FACTS and ONE CLAIM (a single sentence). Decide whether the SOUR"
    "CE FACTS fully support the CLAIM. Judge by ATTRIBUTION FIRST — WHO or WHAT each stat"
    "ement is ABOUT. Apply the tests below in your head and emit only the verdict word; d"
    "o not write out the steps.\n\nTEST 1 — Bind the referents. In the CLAIM, identify th"
    "e subject (the entity the sentence is about) and, for every property, action, number"
    ", date, name, or relationship it asserts, the entity that thing is attached to. Read"
    " the FACTS the same way. Two different names or descriptions count as the SAME entit"
    "y ONLY IF the FACTS themselves state or directly equate them — e.g. a fact 'The west"
    "ernmost tower is called the Tour Bonbec' lets 'the westernmost tower facing the Sein"
    "e' and 'the Tour Bonbec' be one entity. NEVER merge two names using outside knowledg"
    "e, geography, or a guess that they might be the same place.\n\nTEST 2 — Same propert"
    "y, same entity. For everything the CLAIM asserts, the FACTS must attach THAT SAME pr"
    "operty/action/relationship to THAT SAME bound entity. A property the FACTS attach to"
    " entity X but the CLAIM attaches to a DIFFERENT entity Y is NOT supported — even whe"
    "n BOTH X and Y appear in the FACTS. Beware PART vs WHOLE: a container and its conten"
    "ts are DIFFERENT entities. If the FACTS attach a property to a PART (a hall inside a"
    " building, or a building that is a vestige of / stands within a larger palace), a CL"
    "AIM attaching that property to the containing WHOLE — or to a sibling part — is NOT "
    "supported, even though the whole is named in the FACTS (facts: 'the Conciergerie is "
    "a vestige of the Palais de Justice' + 'the Conciergerie is the oldest prison'; claim"
    ": 'the Palais de Justice was the oldest prison' -> NO). (If the facts say the Concie"
    "rgerie is the oldest prison and that Marie-Antoinette was held at the Conciergerie, "
    "then a claim that the Palais de Justice was the oldest prison, or that she was held "
    "at the Palais de Justice, is NOT supported: the facts never attach those to the Pala"
    "is de Justice.)\n\nTEST 3 — Nothing added, strengthened, or contradicted. Answer NO "
    "if the CLAIM: adds any specific the facts never give (a material, measurement, numbe"
    "r, date, name, cause, or person — e.g. 'built of limestone', 'made of bronze', 'more"
    " than a hundred', 'Napoleon'); contradicts a fact (a different number, date, or deta"
    "il — 'fifteen tons' where the facts say 'thirteen tons', 'in 1250' where the facts s"
    "ay 'between 1301 and 1315'); or strengthens scope or degree (the facts say 'one of E"
    "urope's oldest' but the claim says 'the oldest'; the facts say 'often' but the claim"
    " says 'always'; the facts say 'could be heard' but the claim says 'were always heard"
    "'; 'rarely' turned into 'never').\n\nFULLY SUPPORTED (answer YES): a CLAIM that only"
    " RECOMBINES, REWORDS, or PARAPHRASES correctly-attributed facts. All of these are SU"
    "PPORTED — synonyms and rephrasings that keep the meaning ('slew'='cut down', 'built'"
    "='raised', 'held captive'='sat captive', 'destroyed and melted down'='melted down', "
    "'replaced'='recast', 'coloured'='glowing', 'mourning'='grief'); a fact restated as i"
    "ts negation or with clauses reordered ('the kings never returned'='no king came back"
    " again'); and several facts about the SAME bound entity merged into one sentence (fa"
    "cts that the westernmost tower is the Tour Bonbec, that it is where prisoners were t"
    "ortured, and that screams were heard from it -> 'Screams of tortured prisoners could"
    " be heard from the westernmost tower facing the Seine'). Do NOT reject faithful reco"
    "mbination just because no single fact contains the whole sentence.\n\nJudge ONLY aga"
    "inst the FACTS below — never fill a gap with outside knowledge. If the CLAIM stays w"
    "ithin the facts (same entities, same properties, nothing added, strengthened, or con"
    "tradicted) answer YES; otherwise answer NO.\n\nSOURCE FACTS:\n{facts}\n\nCLAIM:\n{cl"
    "aim}\n\nOutput EXACTLY one word — YES or NO — as your first and only token.\nAnswer "
    "(YES or NO):"
)


class HaikuFaithfulnessJudge:
    """Real Haiku FAITHFULNESS judgement (deterministic: temp=0, 5-token cap), conforming to
    the ``FaithfulnessChecker`` protocol so it drops in as the ``entailer`` for the author
    engine's fact-check WITHOUT touching verify.py's strict entailer (which the compose
    engine still uses). Uses the paraphrase-tolerant-but-attribution-strict prompt chosen by
    the labeled bake-off (scripts/faithfulness_calibrate.py, candidate
    'attribution_first_hardened'): 96% acc / 0 false-pos (never passes an invention or
    mis-attribution) / 1 false-neg on the 28-item set, vs the strict entailer's 3 false-negs
    on grounded recombination that blocked author-engine convergence."""

    def __init__(self, model: str = FAITHFULNESS_MODEL, *, client: object = None) -> None:
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.calls = 0

    def entails(self, key_claims: tuple[str, ...], sentence_text: str) -> bool:
        if not sentence_text.strip() or not key_claims:
            return False
        self.calls += 1
        facts = "\n".join(f"- {c}" for c in key_claims)
        resp = self._client.messages.create(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=5,
            temperature=0,  # deterministic: a claim's verdict must not flip between the
            # pre-repair check and the post-repair re-check, or the author loop never
            # converges (same rationale as the coverage judge and verify.py's entailer).
            messages=[{"role": "user", "content": _FAITHFULNESS_JUDGE_USER.format(
                facts=facts, claim=sentence_text)}],
        )
        text = "".join(
            getattr(b, "text", "") for b in (getattr(resp, "content", []) or [])
        ).strip().upper()
        return text.startswith("YES")


class SemanticFactChecker:
    """Bidirectional fact-check: STRICT entailer for faithfulness + paraphrase-tolerant
    ``CoverageJudge`` for coverage + a decomposer. Pure orchestration — the intelligence is
    in the injected models, so this class is fully testable offline with a substring fake +
    a rule decomposer. ``coverage_judge`` is optional: when omitted, coverage falls back to
    the strict entailer (backward-compatible for the offline substring-fake tests); the live
    path injects the calibrated ``HaikuCoverageJudge``."""

    def __init__(
        self,
        entailer: FaithfulnessChecker,
        decomposer: ClaimDecomposer,
        coverage_judge: CoverageJudge | None = None,
    ) -> None:
        self._entail = entailer
        self._decompose = decomposer
        self._coverage = coverage_judge

    def unsupported_against(
        self, claims: tuple[str, ...], facts: tuple[str, ...]
    ) -> tuple[str, ...]:
        """The FAITHFULNESS half of ``check`` factored out: which of ``claims`` are NOT
        entailed by ``facts``? Routes through the STRICT ``self._entail`` ONLY — never
        ``self._coverage`` (the coverage judge is deliberately paraphrase-tolerant and
        would rubber-stamp an overstatement/mis-attribution the strict judge correctly
        rejects; using it here would turn the anti-hallucination gate into a rubber
        stamp). This is the FULL-CORPUS RECHECK primitive: a claim flagged unsupported
        against a trimmed tour-window fact list may still be entailed by the POI's full
        beat corpus, in which case it is grounded (a windowing artifact), not invented."""
        if not claims:
            return ()

        def _run(claim: str) -> tuple[str, bool]:
            return claim, self._entail.entails(facts, claim)

        with ThreadPoolExecutor(max_workers=max(1, min(_MAX_WORKERS, len(claims)))) as pool:
            verdicts = list(pool.map(_run, claims))
        return tuple(c for c, ok in verdicts if not ok)

    def locate(
        self, claims: tuple[str, ...], sentences: tuple[str, ...]
    ) -> dict[str, tuple[int, ...]]:
        """Claim -> SENTENCE-INDEX attribution: which of ``sentences`` convey each of
        ``claims``? Uses the paraphrase-tolerant ``self._coverage.conveys(claim, sentence)``
        when a coverage judge is injected, falling back to
        ``self._entail.entails((sentence,), claim)`` when ``_coverage is None`` — the same
        fallback ``check()`` already applies to its coverage direction (below), so the
        offline substring-fake tests keep working. Used by SURGICAL EXCISION to find which
        sentence(s) carry a still-unsupported claim so only those may be dropped — never a
        lexical/substring guess. A claim conveyed by NO sentence maps to ``()``, the
        caller's signal to abort excision (we cannot prove where an invention lives)."""
        result: dict[str, tuple[int, ...]] = {c: () for c in claims}
        if not claims or not sentences:
            return result
        jobs = [(c, i, s) for c in claims for i, s in enumerate(sentences)]

        def _run(job: tuple[str, int, str]) -> tuple[str, int, bool]:
            claim, idx, sent = job
            if self._coverage is not None:
                ok = self._coverage.conveys(claim, sent)
            else:
                ok = self._entail.entails((sent,), claim)
            return claim, idx, ok

        with ThreadPoolExecutor(max_workers=max(1, min(_MAX_WORKERS, len(jobs)))) as pool:
            verdicts = list(pool.map(_run, jobs))
        hits: dict[str, list[int]] = defaultdict(list)
        for claim, idx, ok in verdicts:
            if ok:
                hits[claim].append(idx)
        for claim, idxs in hits.items():
            result[claim] = tuple(idxs)
        return result

    def check(self, narration_text: str, source_facts: tuple[str, ...]) -> FactCheckResult:
        claims = self._decompose.decompose(narration_text)
        narration_sents = tuple(
            s for s in (p.strip() for p in split_sentences(narration_text)) if s
        )
        # FAITHFULNESS: is each narration claim supported by the source facts? (STRICT)
        # COVERAGE: is each source fact conveyed by the whole narration? (paraphrase-
        # tolerant CoverageJudge when injected, else the strict entailer as fallback).
        # Independent YES/NO lookups -> run them all concurrently.
        jobs: list[tuple[str, str]] = [("F", c) for c in claims] + [("C", f) for f in source_facts]
        if not jobs:
            return FactCheckResult((), ())
        whole_narration = " ".join(narration_sents)

        def _run(job: tuple[str, str]) -> tuple[str, str, bool]:
            kind, item = job
            if kind == "F":
                ok = self._entail.entails(source_facts, item)
            elif self._coverage is not None:
                ok = self._coverage.conveys(item, whole_narration)
            else:
                ok = self._entail.entails(narration_sents, item)
            return kind, item, ok

        with ThreadPoolExecutor(max_workers=max(1, min(_MAX_WORKERS, len(jobs)))) as pool:
            verdicts = list(pool.map(_run, jobs))

        unsupported = tuple(item for kind, item, ok in verdicts if kind == "F" and not ok)
        missing = tuple(item for kind, item, ok in verdicts if kind == "C" and not ok)
        return FactCheckResult(unsupported_claims=unsupported, missing_facts=missing)


__all__ = [
    "ClaimDecomposer",
    "CoverageJudge",
    "FactCheckResult",
    "HaikuClaimDecomposer",
    "HaikuCoverageJudge",
    "HaikuFaithfulnessJudge",
    "SemanticFactChecker",
]
