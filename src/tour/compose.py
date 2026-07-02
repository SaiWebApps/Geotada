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

from .contract import BeatRef, BeatSequence, Route, Script, Sentence, ValidationReport
from .generation import GLUE_NAV, GLUE_REFLECTION
from .reflection import reflection_slots
from .verify import _visited_claims

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


__all__ = [
    "ComposeClient",
    "ComposeRequest",
    "MockComposeClient",
    "build_compose_request",
]
