"""COMPOSE — the fire-once LLM narration composer (Phase 4; spec §4/§5/§6).

The deterministic stitcher (``generation.generate``) stays the offline/test
baseline. COMPOSE rewrites its Script into the single-narrator story —
LOCKED voice: one warm, second-person narrator; the newcomer's curiosity is
captured as STRUCTURE (raise the question, answer from the beats); lens is a
register/diction dial, never a second voice
(specs/2026-06-14-compose-narrator/00-narrator-voice-decision.md) — and adds
reflections on the placed slots (reflection.py). Every sentence stays
source-attributed; ``compose_gate`` + VERIFY gate the output fail-closed.

``MockComposeClient`` is the everywhere-default (make test is offline): it
returns the stitched sentences unchanged and inserts one verbatim
key-claims reflection per slot — deterministic, attributable, entailable.
"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .claim_dedup import candidate_duplicate_pairs, claims_realized_by, verify_claim_coverage
from .compose_gate import (
    ComposeVerificationError,
    _bad_stops,
    build_full_verifier,
    compose_and_verify,
    drop_failing_sentences,
    repair_composed,
    repair_composed_surgical,
)
from .contract import (
    BeatRef,
    BeatSequence,
    Route,
    Script,
    Sentence,
    StopVerifyStatus,
    ValidationReport,
)
from .generation import GLUE_NAV, GLUE_REFLECTION, _sum_audio
from .reflection import reflection_slots
from .verify import (
    FaithfulnessChecker,
    MockFaithfulnessChecker,
    _visited_claims,
    verify_faithfulness,
)

# narrative_function values that mark a beat as transit-class — mirrors
# generation._TRANSIT_NARRATIVE_FUNCTIONS (the transit stage is the only
# legitimate emitter of these, and a reflection lands right after them).
_TRANSIT_FUNCTIONS: frozenset[str] = frozenset({"transition", "transit", "navigation"})


class ComposeRequest(BaseModel):
    """Everything one compose attempt needs, precomputed and immutable.

    ``visited_claims_by_slot`` maps each reflection slot (stop_idx) to the
    ordered union of key_claims of beats cited STRICTLY before that stop —
    the only facts a reflection may synthesize (VERIFY enforces this
    fail-closed, Step 4.2). Slots with an empty union are omitted here:
    an unverifiable reflection is never composed in the first place.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    stitched: Script
    beats_by_id: dict[str, BeatRef] = Field(default_factory=dict)
    slots: tuple[int, ...] = ()
    visited_claims_by_slot: dict[int, tuple[str, ...]] = Field(default_factory=dict)
    duplicate_pairs: tuple[tuple[int, str, str], ...] = ()
    # Per-chapter compose only: the ordered stop names of the WHOLE tour, so a
    # single-stop rewrite still knows where it sits (cohesion) without re-writing
    # the other stops. Empty for a whole-tour compose.
    tour_context: tuple[str, ...] = ()


def build_compose_request(
    stitched: Script,
    beat_sequence: BeatSequence,
    route: Route,
) -> ComposeRequest:
    """Precompute the compose inputs: reflection slots + per-slot claims.

    Slots whose visited-claims union is empty are DROPPED (fail-closed at
    compose time — the VERIFY side of the same rule is Step 4.2).
    """
    beats_by_id = {b.id: b for plan in beat_sequence.poi_beats for b in plan.beats}
    slots = reflection_slots(route, beat_sequence)
    claims_by_slot: dict[int, tuple[str, ...]] = {}
    kept: list[int] = []
    for slot in slots:
        claims = _visited_claims(stitched, beats_by_id, slot)
        if claims:
            kept.append(slot)
            claims_by_slot[slot] = claims
    return ComposeRequest(
        stitched=stitched,
        beats_by_id=beats_by_id,
        slots=tuple(kept),
        visited_claims_by_slot=claims_by_slot,
        duplicate_pairs=candidate_duplicate_pairs(stitched),
    )


class ComposeClient(Protocol):
    """One compose attempt: the full sentence stream, source-attributed.

    ``attempt`` is 1-based; ``prev_report`` carries the failing
    ValidationReport on the single bounded recompose (attempt 2) so the
    composer can steer away from the prior failure.
    """

    def compose(
        self,
        request: ComposeRequest,
        attempt: int,
        prev_report: ValidationReport | None,
    ) -> tuple[Sentence, ...]: ...


def _is_transit_sentence(sentence: Sentence, beats_by_id: dict[str, BeatRef]) -> bool:
    """True for the leg-opening sentences of a stop: the GLUE_NAV line or a
    corpus transit beat's sentences. A reflection lands right after these."""
    if sentence.source_type == "glue":
        return sentence.source_id == GLUE_NAV
    if sentence.source_type == "beat":
        beat = beats_by_id.get(sentence.source_id)
        return beat is not None and (beat.narrative_function or "").lower() in _TRANSIT_FUNCTIONS
    return False


def _reflection_text(claims: tuple[str, ...]) -> str:
    """Deterministic, verbatim-from-claims reflection (Mock only).

    Quoting the claims verbatim keeps the sentence entailable by a strict
    checker and its proper nouns/years inside the canonical context (4.2).
    """
    quoted = "; ".join(claims[:2])
    return f"Worth holding onto from what you've seen so far: {quoted}."


class MockComposeClient:
    """TEST DOUBLE ONLY — never wired into a product path.

    The product composer (``api.dependencies.get_compose_client``) is ALWAYS the
    real Opus ``AnthropicComposeClient``; a customer is never served this stitcher
    passthrough as the narrator. This class exists so the hermetic ``make test``
    bar stays offline + $0: ``tests/conftest.py`` patches ``AnthropicComposeClient``
    to THIS for every non-``live`` test, and unit tests inject it directly.

    Deterministic offline behaviour: stitched sentences + one verbatim key-claims
    reflection per (non-empty) slot, inserted immediately after the slot's transit
    opening and before its anchor beats. Records calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, ValidationReport | None]] = []

    def compose(
        self,
        request: ComposeRequest,
        attempt: int,
        prev_report: ValidationReport | None,
    ) -> tuple[Sentence, ...]:
        self.calls.append((attempt, prev_report))
        pending = dict(request.visited_claims_by_slot)
        out: list[Sentence] = []
        sentences = list(request.stitched.script)
        for i, sentence in enumerate(sentences):
            out.append(sentence)
            slot = sentence.stop_idx
            if slot not in pending:
                continue
            if not _is_transit_sentence(sentence, request.beats_by_id):
                continue
            nxt = sentences[i + 1] if i + 1 < len(sentences) else None
            if nxt is not None and nxt.stop_idx == slot and _is_transit_sentence(
                nxt, request.beats_by_id
            ):
                continue  # still inside the transit run
            out.append(
                Sentence(
                    text=_reflection_text(pending.pop(slot)),
                    source_id=GLUE_REFLECTION,
                    source_type="glue",
                    stop_idx=slot,
                )
            )
        return tuple(out)


# ---------------------------------------------------------------------------
# Real fire-once Anthropic compose (Step 4.5) — NOT exercised by `make test`.
# ---------------------------------------------------------------------------

COMPOSE_MODEL = "claude-opus-4-8"
# Streaming ceiling: adaptive-thinking tokens count against max_tokens, and a
# full tour's rewritten sentence list is large — 16K truncated a real 45-min
# Paris compose mid-JSON (live gate, 2026-07-02). Stream + 64K per the SDK
# guidance; a max_tokens stop is raised as a hard error, never parsed.
COMPOSE_MAX_OUTPUT_TOKENS = 64000

# The LOCKED narrator voice (specs/2026-06-14-compose-narrator/): ONE warm,
# second-person narrator; the newcomer's curiosity captured as STRUCTURE;
# lens = a register/diction dial on the one voice. Grounding is enforced by
# VERIFY, but the prompt states the rules so attempt 1 usually passes.
_COMPOSE_SYSTEM = """\
You are the narrator of a GPS-triggered walking audio tour. Rewrite the given
stitched script into one continuous story a walker hears through earphones.

VOICE (locked — do not deviate):
- ONE warm, second-person narrator — a knowing friend walking with the
  listener. Never a host pair, never an interviewer, never a second voice.
- Capture the newcomer's curiosity as STRUCTURE: raise the question a
  first-timer would ask, then answer it from the beats — at SOME stops, not
  every one (a device used everywhere becomes a tic).
- The requested lenses set your register and diction (a dial on the one
  voice), never a reason to invent content.

CRAFT — sound like a person, not a machine. Human and machine narration differ
most in STRUCTURE and stance, not word-polish; these rules target the measured
tells that make generated prose feel generated:
- Do NOT state the meaning, lesson, or theme of a place. End on the fact, the
  image, or the open question and let the listener draw the conclusion. Never
  write "a testament to…", "a reminder that…", "stands as a symbol of…",
  "speaks to the enduring…", or any sentence whose job is to tell the walker
  what to think or feel.
- Name things. Use the specific person, book, street, and date the beats give
  you; never soften a real name into a vague gesture ("a famous writer").
- State feelings plainly when the beats state them ("Parisians were furious").
  Never convert a feeling into a bodily or weather metaphor ("a chill hung in
  the air", "the stones seem to whisper"), and add NO sensory detail the beats
  do not contain.
- Speak TO the walker; an occasional aside about the walk itself is welcome
  ("you'll see why in a minute", "look up as you pass").
- VARY the shape of the stops. Do not open every stop the same way, and do not
  give every stop the same weight or arc — a minor stop can be a single sharp
  sentence; a major one earns a fuller telling.
- FUSE REPEATS BOLDLY. Guidebook sources overlap heavily, so a stop often tells
  the same event, person, date, or place TWICE in different words — the single
  most common flaw in this material, and it makes the guide sound broken. Before
  you finalize each stop, re-read it and hunt for any fact stated more than once
  (even when the wording differs completely — "renamed to honour the first
  département to pay taxes" and "Napoleon gave naming rights to the district that
  paid first" are the SAME fact). Merge each repeat into ONE richer telling that
  keeps every distinct particular from both versions, and drop the redundant one.
  Carrying over EVERY year, date, number, and proper noun from both sentences is
  non-negotiable — fuse the wording, never lose a fact (dropping a date is the
  most common fusion error). A downstream check rejects any fusion that loses a
  fact, so fuse without fear; when in doubt whether two sentences are the same
  fact, they usually are.
- CITE EVERY BEAT YOU MERGE. When the two sentences you fuse come from DIFFERENT
  beats (different source_id), the merged sentence MUST keep one source_id as its
  primary AND list the OTHER merged beat id(s) in its "also_cites" field. This is
  mandatory: the faithfulness check entails a fused sentence against the UNION of
  its cited beats, so a cross-beat merge with only one source_id is rejected even
  though every fact is true. A sentence from a single beat leaves also_cites empty.
- The CANDIDATE DUPLICATE PAIRS list (when present) flags same-stop sentences a
  cheap pre-scan found similar; treat each as "probably the same fact — fuse
  unless they are genuinely distinct." It is a hint, not exhaustive: also fuse
  repeats it missed.
- Within a stop you may reorder sentences so events flow sensibly (usually
  oldest to newest), or open on what's in front of the walker and step back in
  time. Never move content between stops.

GROUNDING (violations are rejected by an automated verifier):
- Output the FULL sentence list. Every sentence carries source attribution.
- A sentence with source_type "beat" keeps its source_id and may only restate
  what that beat's key claims support — never add names, dates, or facts.
- Glue sentences (source_type "glue") use ONLY these source_id labels:
  GLUE_NAV, GLUE_STAGING, GLUE_PACING, GLUE_CALLBACK, GLUE_CLOSING,
  GLUE_REFLECTION, ARITH, SYNTHESIZED_OPENER. Glue may not introduce proper
  nouns or years that no cited beat carries.
- Never use the words "imagine", "picture this", "envision", "visualize".
- Reflections: at each given slot, add sentences with source_id
  GLUE_REFLECTION and that slot's stop_idx, placed right after the slot's
  transit opening. Slots not listed get NO reflection. HARD CONSTRAINT (an
  automated entailment gate checks each reflection sentence against that
  slot's visited_claims list ALONE): every factual assertion in a reflection
  — every number, date, name, time, and event — must appear in that slot's
  visited_claims. Do NOT add a precise time of day, a figure, or any detail you
  happen to know but the list does not carry, even if it is true. Details from
  the script or beats sections DO NOT COUNT. Recombine the listed claims; add
  nothing.
- Keep every sentence's stop_idx (reflections use their slot's stop_idx).
- Keep the stop ORDER; improve flow, transitions, dynamics, and storytelling
  within it, following the CRAFT rules above."""

_COMPOSE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source_id": {"type": "string"},
                    "source_type": {"type": "string", "enum": ["beat", "glue"]},
                    "stop_idx": {"type": "integer"},
                    "also_cites": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "When THIS sentence fuses a fact stated by more than one "
                            "beat, list the OTHER beats' ids here (source_id is the "
                            "primary). Omit or [] for a plain single-beat sentence."
                        ),
                    },
                },
                "required": ["text", "source_id", "source_type", "stop_idx"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sentences"],
    "additionalProperties": False,
}


def _compose_user_prompt(
    request: ComposeRequest, attempt: int, prev_report: ValidationReport | None
) -> str:
    """Render one compose attempt's user message (deterministic, testable)."""
    import json

    stitched = [
        {
            "text": s.text,
            "source_id": s.source_id,
            "source_type": s.source_type,
            "stop_idx": s.stop_idx,
        }
        for s in request.stitched.script
    ]
    beats = {
        bid: {
            "key_claims": list(b.key_claims),
            "script_body": b.script_body or "",
        }
        for bid, b in request.beats_by_id.items()
    }
    slots = [
        {"stop_idx": slot, "visited_claims": list(request.visited_claims_by_slot[slot])}
        for slot in request.slots
    ]
    parts = [
        f"LENSES (register dial): {request.stitched.inputs.lenses or 'none — neutral register'}",
    ]
    if request.tour_context:
        here = {s.stop_idx for s in request.stitched.script}
        parts.append(
            "TOUR CONTEXT — you are composing ONLY the stop(s) in STITCHED SCRIPT "
            f"below (stop index {sorted(here)}). The whole walk, in order, is: "
            f"{json.dumps(list(request.tour_context), ensure_ascii=False)}. Keep this "
            "stop coherent with that arc; do NOT write the other stops."
        )
    parts += [
        f"STITCHED SCRIPT:\n{json.dumps(stitched, ensure_ascii=False)}",
        f"BEATS (id -> key_claims + corpus text):\n{json.dumps(beats, ensure_ascii=False)}",
        "REFLECTION SLOTS (each reflection must be fully supported by its own "
        f"visited_claims list ALONE — nothing from elsewhere in this prompt):\n"
        f"{json.dumps(slots, ensure_ascii=False)}",
    ]
    if request.duplicate_pairs:
        dupes = [
            {"stop_idx": stop_idx, "a": a, "b": b}
            for stop_idx, a, b in request.duplicate_pairs
        ]
        parts.append(
            "CANDIDATE DUPLICATE PAIRS (same-stop sentences a pre-scan found "
            "similar — probably the same fact; fuse each into one telling unless "
            "genuinely distinct, and also fuse repeats not listed here):\n"
            f"{json.dumps(dupes, ensure_ascii=False)}"
        )
    if attempt > 1 and prev_report is not None:
        failures = {
            "untraceable": [s.text for s in prev_report.untraceable_sentences],
            "forbidden_or_invented": [
                [s.text, code] for s, code in prev_report.forbidden_phrase_hits
            ],
            "unfaithful": [[s.text, code] for s, code in prev_report.faithfulness_failures],
            # Facts the previous attempt DROPPED (usually a date or number lost while
            # fusing a repeat). Each MUST reappear — it was in the stitched script.
            "dropped_facts_you_must_restore": [
                claim for _bid, claim in prev_report.coverage_failures
            ],
        }
        parts.append(
            "PREVIOUS ATTEMPT FAILED VERIFICATION — fix exactly these problems "
            "(this is the single allowed recompose). For dropped_facts_you_must_restore, "
            "weave each fact back in (fuse it into the sentence that now covers that "
            "topic; do not re-introduce the repetition):\n"
            f"{json.dumps(failures, ensure_ascii=False)}"
        )
    return "\n\n".join(parts)


class AnthropicComposeClient:
    """Fire-once real compose: ONE messages.create per attempt, structured
    output via output_config.format (guaranteed-valid JSON), adaptive
    thinking. The anthropic import is deferred (HaikuGlueClient pattern) so
    unit tests never need the SDK; ``make test`` never constructs this."""

    def __init__(self, model: str = COMPOSE_MODEL, *, client: object | None = None):
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0
        if client is None:
            import anthropic

            client = anthropic.Anthropic()
        self._client = client

    def compose(
        self,
        request: ComposeRequest,
        attempt: int,
        prev_report: ValidationReport | None,
    ) -> tuple[Sentence, ...]:
        import json

        with self._client.messages.stream(  # type: ignore[attr-defined]
            model=self.model,
            max_tokens=COMPOSE_MAX_OUTPUT_TOKENS,
            thinking={"type": "adaptive"},
            system=_COMPOSE_SYSTEM,
            output_config={"format": {"type": "json_schema", "schema": _COMPOSE_OUTPUT_SCHEMA}},
            messages=[
                {"role": "user", "content": _compose_user_prompt(request, attempt, prev_report)}
            ],
        ) as stream:
            response = stream.get_final_message()
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise ValueError(
                "compose output truncated at max_tokens="
                f"{COMPOSE_MAX_OUTPUT_TOKENS} — the sentence list is incomplete"
            )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        text = next(
            (b.text for b in (getattr(response, "content", []) or []) if b.type == "text"),
            None,
        )
        if text is None:
            raise ValueError(
                "compose response carried no text block "
                f"(stop_reason={getattr(response, 'stop_reason', None)!r}) — nothing to parse"
            )
        data = json.loads(text)
        return tuple(
            Sentence(
                text=s["text"],
                source_id=s["source_id"],
                source_type=s["source_type"],
                stop_idx=s["stop_idx"],
                # Only beat sentences carry fused citations; ignore any stray
                # also_cites the model attaches to glue.
                also_cites=(
                    tuple(s.get("also_cites") or ())
                    if s["source_type"] == "beat"
                    else ()
                ),
            )
            for s in data["sentences"]
        )


def compose_script(
    stitched: Script,
    beat_sequence: BeatSequence,
    route: Route,
    *,
    client: ComposeClient,
    faithfulness_checker: FaithfulnessChecker | None = None,
    chunk_text_by_slug: dict[str, str] | None = None,
    repair: bool = False,
) -> Script:
    """Fire-once compose behind the M7 gate (Step 4.4).

    One compose; on a failing merged VERIFY report, EXACTLY one bounded
    recompose steered by that report. Then, iff ``repair`` is set, a per-stop
    graceful repair reverts only the stops that still failed to their grounded
    stitched narration and serves the result (the workbench opts in — it must
    always show SOMETHING good; the persisted ``/compose`` path leaves ``repair``
    off so a genuine refusal stays a refusal the editor can act on). Still
    failing → the flavour is refused (``ComposeVerificationError`` propagates).
    The returned Script carries the PASSING report and a ``total_audio_seconds``
    recomputed for the composed sentence stream. Checker/chunks default to the
    offline no-ops so the caller decides where the real teeth are wired."""
    request = build_compose_request(stitched, beat_sequence, route)
    # Coverage baseline: the claims the pre-compose stitch actually voiced. The
    # gate then blocks any compose (however bold its fusion) that drops one — the
    # safety net that lets the prompt say "fuse without fear".
    expected_claim_ids = claims_realized_by(stitched, request.beats_by_id)
    verify = build_full_verifier(
        beat_sequence,
        request.beats_by_id,
        chunk_text_by_slug=chunk_text_by_slug,
        faithfulness_checker=faithfulness_checker,
        expected_claim_ids=expected_claim_ids,
    )

    def compose(attempt: int, prev: ValidationReport | None) -> Script:
        sentences = client.compose(request, attempt, prev)
        return stitched.model_copy(
            update={
                "script": tuple(sentences),
                "total_audio_seconds": _sum_audio(sentences, beat_sequence),
                "validation": ValidationReport(),
            }
        )

    repair_fn = (
        (lambda comp, rep: repair_composed(comp, stitched, rep)) if repair else None
    )
    return compose_and_verify(compose, verify, repair=repair_fn)


_PER_CHAPTER_MAX_WORKERS = 6


def _report_for_stop(
    report: ValidationReport, stop_idx: int, beat_stop: dict[str, int]
) -> ValidationReport:
    """The subset of a whole-tour report pertaining to one stop — the failure
    feedback a per-stop recompose needs."""
    return ValidationReport(
        untraceable_sentences=tuple(
            s for s in report.untraceable_sentences if s.stop_idx == stop_idx
        ),
        forbidden_phrase_hits=tuple(
            (s, c) for s, c in report.forbidden_phrase_hits if s.stop_idx == stop_idx
        ),
        faithfulness_failures=tuple(
            (s, c) for s, c in report.faithfulness_failures if s.stop_idx == stop_idx
        ),
        coverage_failures=tuple(
            (bid, cl) for bid, cl in report.coverage_failures if beat_stop.get(bid) == stop_idx
        ),
    )


def _per_stop_verify_report(
    served: Script,
    beat_stop: dict[str, int],
    reverted_stops: set[int],
    partial_by_stop: dict[int, tuple[str, ...]],
    *reports: ValidationReport | None,
) -> tuple[StopVerifyStatus, ...]:
    """Diagnostic: one entry per stop marking whether it kept its composed
    narration (``composed``), kept it except for a surgically-restored beat
    (``partially_reverted``, ``restored_beats`` naming which), or was rolled back
    whole to the stitch (``reverted_to_stitched``), plus — from the failing
    report(s) that drove the gate — which VERIFY categories fired against that stop.

    ``reverted_stops`` and ``partial_by_stop`` are computed STRUCTURALLY by the
    caller (the exact sets the repair whole-reverted / surgically spliced), never
    inferred from text: the Mock composer is an identity passthrough, so a
    composed-but-unchanged stop is byte-identical to the stitch yet was NOT
    reverted. Pure, off the hot path.
    """
    faith: dict[int, list[str]] = defaultdict(list)
    cov: dict[int, list[str]] = defaultdict(list)
    forb: dict[int, list[str]] = defaultdict(list)
    untr: dict[int, list[str]] = defaultdict(list)
    for report in reports:
        if report is None:
            continue
        for s, reason in report.faithfulness_failures:
            faith[s.stop_idx].append(f"{s.source_id}: {reason}")
        for bid, claim in report.coverage_failures:
            k = beat_stop.get(bid)
            if k is not None:
                cov[k].append(f"{bid}: {claim}")
        for s, code in report.forbidden_phrase_hits:
            forb[s.stop_idx].append(code)
        for s in report.untraceable_sentences:
            untr[s.stop_idx].append(s.source_id)

    def _status(k: int) -> str:
        if k in reverted_stops:
            return "reverted_to_stitched"
        if k in partial_by_stop:
            return "partially_reverted"
        return "composed"

    stops = sorted({s.stop_idx for s in served.script} | reverted_stops | set(partial_by_stop))
    out: list[StopVerifyStatus] = []
    for k in stops:
        out.append(
            StopVerifyStatus(
                stop_idx=k,
                status=_status(k),
                restored_beats=tuple(partial_by_stop.get(k, ())),
                faithfulness=tuple(faith.get(k, ())),
                coverage=tuple(cov.get(k, ())),
                forbidden=tuple(forb.get(k, ())),
                untraceable=tuple(untr.get(k, ())),
            )
        )
    return tuple(out)


def compose_script_per_chapter(
    stitched: Script,
    beat_sequence: BeatSequence,
    route: Route,
    *,
    client: ComposeClient,
    faithfulness_checker: FaithfulnessChecker | None = None,
    chunk_text_by_slug: dict[str, str] | None = None,
    max_workers: int = _PER_CHAPTER_MAX_WORKERS,
    candidates: int = 1,
) -> Script:
    """Compose each stop in its OWN focused call, in PARALLEL, then verify the
    assembled tour and repair only what still fails.

    Whole-tour compose juggles ~150 sentences: it drops facts on the big stops
    (so they revert to stitched and the repetition survives) and is slow (~19
    min). Composing one stop at a time keeps the model's attention on that stop's
    repeats — it fuses them without dropping facts — and parallelizes across stops
    (~1 min). Reflections are still VERIFIED on the assembled whole (each sees the
    earlier stops' visited claims), and a stop that still fails after its own
    bounded recompose reverts to the grounded stitch. Same gates, same guarantees
    — just per-stop scope and concurrency.

    ``candidates`` > 1 turns on BEST-OF-N: each stop is composed that many times
    (in parallel, sampling diversity from the LLM) and the candidate with the
    fewest LOCAL faithfulness + coverage failures is kept — extra lottery tickets
    for the big, dense stops whose single fusion trips the gate and reverts."""
    beats_by_id = {b.id: b for plan in beat_sequence.poi_beats for b in plan.beats}
    beat_stop = {s.source_id: s.stop_idx for s in stitched.script if s.source_type == "beat"}
    tour_context = tuple(p.name for p in route.pois)
    all_slots = reflection_slots(route, beat_sequence)
    visited = {slot: _visited_claims(stitched, beats_by_id, slot) for slot in all_slots}

    stops = sorted({s.stop_idx for s in stitched.script})
    by_stop: dict[int, list[Sentence]] = defaultdict(list)
    for s in stitched.script:
        by_stop[s.stop_idx].append(s)

    def _request_for(stop_idx: int) -> ComposeRequest:
        stop_sents = by_stop[stop_idx]
        mini = stitched.model_copy(update={"script": tuple(stop_sents)})
        stop_beats = {
            s.source_id: beats_by_id[s.source_id]
            for s in stop_sents
            if s.source_type == "beat" and s.source_id in beats_by_id
        }
        return ComposeRequest(
            stitched=mini,
            beats_by_id=stop_beats,
            slots=tuple(slot for slot in all_slots if slot == stop_idx),
            visited_claims_by_slot={k: v for k, v in visited.items() if k == stop_idx},
            duplicate_pairs=candidate_duplicate_pairs(mini),
            tour_context=tour_context,
        )

    def _compose_stop(stop_idx: int, attempt: int, prev: ValidationReport | None) -> list[Sentence]:
        # Client errors propagate (matching whole-tour compose_script): a systemic
        # failure — auth, billing, rate limit — must SURFACE, not be silently
        # reverted to stitched and mislabelled a partial compose. Bad compose
        # OUTPUT (not a client error) is what the VERIFY + repair path handles.
        return list(client.compose(_request_for(stop_idx), attempt, prev))

    checker = faithfulness_checker or MockFaithfulnessChecker()
    composed_by_stop: dict[int, list[Sentence]] = {}

    def _local_penalty(stop_idx: int, cand: list[Sentence]) -> int:
        """Beat-faithfulness + coverage failures of ONE stop's candidate — the
        signal best-of-N ranks on. Reflections are cross-stop (judged on the
        assembled whole later), so they are excluded here."""
        stop_beats = {
            s.source_id: beats_by_id[s.source_id]
            for s in by_stop[stop_idx]
            if s.source_type == "beat" and s.source_id in beats_by_id
        }
        mini = stitched.model_copy(update={"script": tuple(by_stop[stop_idx])})
        expected = claims_realized_by(mini, stop_beats)
        beat_only = mini.model_copy(
            update={"script": tuple(s for s in cand if s.source_type == "beat")}
        )
        faith = verify_faithfulness(beat_only, stop_beats, checker)
        cov = verify_claim_coverage(
            mini.model_copy(update={"script": tuple(cand)}), expected, stop_beats
        )
        return len(faith) + len(cov)

    def _run(targets: list[int], attempt: int, prev_of):
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(targets)))) as pool:
            results = pool.map(lambda i: _compose_stop(i, attempt, prev_of(i)), targets)
        for stop_idx, sents in zip(targets, results, strict=True):
            composed_by_stop[stop_idx] = sents

    def _run_best_of_n(targets: list[int]):
        """Attempt 1 with best-of-N: compose every (stop, candidate) pair in one
        parallel wave, then keep each stop's lowest-penalty candidate."""
        n = max(1, candidates)
        jobs = [(i, k) for i in targets for k in range(n)]
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(jobs)))) as pool:
            gen = list(pool.map(lambda job: (job[0], _compose_stop(job[0], 1, None)), jobs))
        cands: dict[int, list[list[Sentence]]] = defaultdict(list)
        for stop_idx, sents in gen:
            cands[stop_idx].append(sents)
        for stop_idx in targets:
            cs = cands[stop_idx]
            composed_by_stop[stop_idx] = (
                cs[0] if len(cs) == 1 else min(cs, key=lambda c: _local_penalty(stop_idx, c))
            )

    def _assemble() -> Script:
        out: list[Sentence] = []
        for stop_idx in stops:
            out.extend(composed_by_stop[stop_idx])
        return stitched.model_copy(
            update={
                "script": tuple(out),
                "total_audio_seconds": _sum_audio(out, beat_sequence),
                "validation": ValidationReport(),
            }
        )

    verify = build_full_verifier(
        beat_sequence,
        beats_by_id,
        chunk_text_by_slug=chunk_text_by_slug,
        faithfulness_checker=faithfulness_checker,
        expected_claim_ids=claims_realized_by(stitched, beats_by_id),
    )

    def _served(
        script: Script,
        passing: ValidationReport,
        reverted: set[int],
        partial: dict[int, tuple[str, ...]],
        *fail_reports: ValidationReport | None,
    ) -> Script:
        """Attach the passing report AND the per-stop verify_report diagnostic
        (which stops whole-reverted, which were surgically-repaired, + the failing
        report(s) that drove the gate) to the served Script — additive, so no
        existing behavior changes."""
        return script.model_copy(
            update={
                "validation": passing,
                "verify_report": _per_stop_verify_report(
                    script, beat_stop, reverted, partial, *fail_reports
                ),
            }
        )

    _run_best_of_n(stops)  # attempt 1: best-of-N per stop, all in parallel
    composed = _assemble()
    report = verify(composed)
    if report.passed:
        return _served(composed, report, set(), {})  # every stop composed clean

    bad = sorted(_bad_stops(report, stitched))
    if bad:  # attempt 2: recompose ONLY the failed stops, each with its own feedback
        _run(bad, 2, lambda i: _report_for_stop(report, i, beat_stop))
        composed = _assemble()
        report = verify(composed)
        if report.passed:
            return _served(composed, report, set(), {})

    # Granular repair first: drop just the failing sentences (a stop whose only
    # fault is an embellished reflection keeps all its fused beat prose).
    trimmed = drop_failing_sentences(composed, report)
    tr_report = verify(trimmed)
    if tr_report.passed:
        # No revert — only individual sentences were dropped; every stop keeps its
        # (possibly trimmed) composed narration.
        return _served(trimmed, tr_report, set(), {}, report)

    # Surgical repair: for each stop whose trimmed compose left a beat's claim
    # uncovered (a dropped fusion), splice back ONLY that beat's grounded stitched
    # sentence(s) IN PLACE — keeping the stop's other AI-voiced sentences. A stop
    # whose every beat was restored is marked reverted (accurate), the rest
    # partially_reverted.
    surgical, restored, fully = repair_composed_surgical(composed, stitched, report, tr_report)
    surg_report = verify(surgical)
    if surg_report.passed:
        partial = {k: v for k, v in restored.items() if k not in fully}
        return _served(surgical, surg_report, fully, partial, report, tr_report)

    # Safety net: any stop a surgical splice still could not verify falls back to a
    # whole-stop revert to the grounded stitch.
    reverted = _bad_stops(surg_report, stitched) | fully
    repaired = repair_composed(surgical, stitched, surg_report)
    rep_report = verify(repaired)
    if rep_report.passed:
        partial = {k: v for k, v in restored.items() if k not in reverted}
        return _served(repaired, rep_report, reverted, partial, report, tr_report)
    raise ComposeVerificationError(rep_report, 2)


__all__ = [
    "COMPOSE_MODEL",
    "AnthropicComposeClient",
    "ComposeClient",
    "ComposeRequest",
    "MockComposeClient",
    "build_compose_request",
    "compose_script",
    "compose_script_per_chapter",
]
