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

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .compose_gate import build_full_verifier, compose_and_verify
from .contract import BeatRef, BeatSequence, Route, Script, Sentence, ValidationReport
from .generation import GLUE_NAV, GLUE_REFLECTION, _sum_audio
from .reflection import reflection_slots
from .verify import FaithfulnessChecker, _visited_claims

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
    """Deterministic offline default: stitched sentences + one verbatim
    key-claims reflection per (non-empty) slot, inserted immediately after
    the slot's transit opening and before its anchor beats. Records calls."""

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
  first-timer would ask, then answer it from the beats.
- The requested lenses set your register and diction (a dial on the one
  voice), never a reason to invent content.

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
  — every number, date, name, and event — must appear in that slot's
  visited_claims. Details from the script or beats sections DO NOT COUNT,
  even when true. Recombine the listed claims; add nothing.
- Keep every sentence's stop_idx (reflections use their slot's stop_idx).
- Keep the stop ORDER and overall structure; improve flow, transitions, and
  storytelling within it."""

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
        f"STITCHED SCRIPT:\n{json.dumps(stitched, ensure_ascii=False)}",
        f"BEATS (id -> key_claims + corpus text):\n{json.dumps(beats, ensure_ascii=False)}",
        "REFLECTION SLOTS (each reflection must be fully supported by its own "
        f"visited_claims list ALONE — nothing from elsewhere in this prompt):\n"
        f"{json.dumps(slots, ensure_ascii=False)}",
    ]
    if attempt > 1 and prev_report is not None:
        failures = {
            "untraceable": [s.text for s in prev_report.untraceable_sentences],
            "forbidden_or_invented": [
                [s.text, code] for s, code in prev_report.forbidden_phrase_hits
            ],
            "unfaithful": [[s.text, code] for s, code in prev_report.faithfulness_failures],
        }
        parts.append(
            "PREVIOUS ATTEMPT FAILED VERIFICATION — fix exactly these problems "
            f"(this is the single allowed recompose):\n{json.dumps(failures, ensure_ascii=False)}"
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
            b.text for b in (getattr(response, "content", []) or []) if b.type == "text"
        )
        data = json.loads(text)
        return tuple(
            Sentence(
                text=s["text"],
                source_id=s["source_id"],
                source_type=s["source_type"],
                stop_idx=s["stop_idx"],
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
) -> Script:
    """Fire-once compose behind the M7 gate (Step 4.4).

    One compose; on a failing merged VERIFY report, EXACTLY one bounded
    recompose steered by that report; still failing → the flavour is refused
    (``ComposeVerificationError`` propagates). The returned Script carries the
    PASSING report and a ``total_audio_seconds`` recomputed for the composed
    sentence stream. Checker/chunks default to the offline no-ops so the
    caller decides where the real teeth are wired (live gate / prod)."""
    request = build_compose_request(stitched, beat_sequence, route)
    verify = build_full_verifier(
        beat_sequence,
        request.beats_by_id,
        chunk_text_by_slug=chunk_text_by_slug,
        faithfulness_checker=faithfulness_checker,
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

    return compose_and_verify(compose, verify)


__all__ = [
    "COMPOSE_MODEL",
    "AnthropicComposeClient",
    "ComposeClient",
    "ComposeRequest",
    "MockComposeClient",
    "build_compose_request",
    "compose_script",
]
