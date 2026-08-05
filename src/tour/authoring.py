"""AUTHORING — the physical authoring primitives shared by every narration caller.

Extracted BYTE-IDENTICALLY out of ``compose.py`` (step A1 of the one-true-tour-algorithm
ledger).  ``compose.py`` — the whole-tour composer — is deleted later in Track A; these
pieces are the parts of it that survive, because they are what the per-stop authoring
path, the Premium blueprint builder and the certification replay all actually need:

* the frozen physical policy (``COMPOSE_MODEL``, the max-token ceiling, ``_COMPOSE_SYSTEM``
  and ``_COMPOSE_OUTPUT_SCHEMA``) that ``premium_authoring_policy_sha256()`` hashes,
* ``ComposeRequest`` — one stop's precomputed, immutable authoring input,
* the request rendering/hashing/envelope helpers and the response parser,
* ``_certification_compose_requests`` + ``finalize_certification_composition``, the pure
  replay boundary that verifies already-completed per-stop responses.

NOTHING here was edited during the move.  The policy hash is baked into committed
certification candidate data, so a whitespace change is a data-invalidating change;
``tests/test_tour_authoring_extraction.py`` pins it to its pre-move value.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from .artifact import CompositionTrace, sentences_payload_sha256
from .candidate_authoring import (
    AuthoringStopRequest,
)
from .claim_dedup import (
    claims_realized_by,
    suppress_exact_repeats,
    suppress_repeated_claims,
    suppress_same_beat_near_duplicates,
)
from .compose_gate import ComposeVerificationError, build_full_verifier
from .contract import (
    BeatRef,
    BeatSequence,
    Route,
    Script,
    Sentence,
    ValidationReport,
)
from .generation import GLUE_REFLECTION, _sum_audio
from .reflection import reflection_slots
from .validation import validate_script, validate_source_traceability
from .verify import FaithfulnessChecker, _visited_claims


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


class CertificationComposition(BaseModel):
    """The exact final script plus its physical compose response lineage."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    script: Script
    composition_trace: tuple[CompositionTrace, ...]


class CompletedCertificationComposeUnit(BaseModel):
    """One physical compose response, ready for deterministic replay.

    The durable workflow owns these values; the pure finalizer below never calls
    a provider and never invents request/response lineage.  The parsed-payload
    hash separately binds the structured sentence stream to the physical
    response record.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    unit_id: str = Field(..., pattern=r"^stop:[0-9]+$")
    stop_index: int = Field(..., ge=0)
    model: str = Field(..., min_length=1)
    authorized_request: ComposeRequest
    authoring_request: AuthoringStopRequest
    parsed_provider_sentences: tuple[Sentence, ...] = Field(..., min_length=1)
    request_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    response_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    parsed_payload_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")


COMPOSE_MODEL = "claude-opus-4-8"
# Streaming ceiling: adaptive-thinking tokens count against max_tokens, and a
# full tour's rewritten sentence list is large — 16K truncated a real 45-min
# Paris compose mid-JSON (live gate, 2026-07-02). Stream + 64K per the SDK
# guidance; a max_tokens stop is raised as a hard error, never parsed.
COMPOSE_MAX_OUTPUT_TOKENS = 64000
# Certification preserves the branch-proven adaptive-thinking allowance. The
# frozen full-call-plan preflight—not a smaller hidden ceiling—controls spend.
CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS = COMPOSE_MAX_OUTPUT_TOKENS

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

CRAFT, WHAT TO DO — build a story, not a recital. Write each stop the way a
friend who loves this city would tell it on the walk: curious, specific,
grounded in real stakes. Correctness with no person and no reason to care is
the exact failure testers named ("like reading Wikipedia aloud").
- OPEN ON A MOMENT. Start the tour, and each major stop, where something is
  happening — a person acting, a conflict, a surprising claim the beats carry —
  never on a label, a founding date, or a scene-description. The opener
  (SYNTHESIZED_OPENER) should make a first-timer want to keep walking.
- LEAD WITH THE STAKES. Facts are the material, not the point. Open on who
  wanted what, what was at risk, what changed — then hang the names, dates, and
  numbers off that spine. A stop that is only names and dates has failed even
  when every fact is present and nothing repeats.
- FAVOUR THE ONE PERSON. When a stop carries both aggregate history and a single
  named individual the beats give you, lead with that one person's story; prefer
  one concrete thing the walker can see now over abstract significance. (Still
  voice every beat — this is emphasis and order, never omission.)
- WRITE FOR THE EAR — it is heard once, never re-read. Vary the rhythm HARD:
  within a stop, land at least one very short sentence (under eight words) as
  percussion AND let at least one run longer to carry the story; never three
  sentences in a row of the same shape or length. Use contractions and active
  verbs. Avoid parenthetical asides, colons, and clauses stacked past what the ear
  can hold in one breath.
- SAY IT ONCE. State each fact a single time. If two beats carry the same fact,
  voice it ONCE and move on — restating the same point in new words ("prisoners
  were tortured here" then "you could hear the tortured prisoners' screams") is
  padding; cut the repeat. Explain a name or term once, not twice.
- MAKE IT FLOW — connect, don't list. A stop is ONE story, not a row of facts.
  Each sentence hands off to the next: state a fact, then let its consequence, or
  the question it raises, pull the listener forward. WEAVE background INTO the
  sentence it explains — never drop it as its own closed statement ("The king was
  a captive in England." "Marcel wanted power." -> "With the king held captive,
  the throne stood weak — and that was the opening Marcel saw."). Prefer causal and
  temporal joins (so, which is why, by then, and that is when) over a full stop
  between two related facts. This OVERRIDES "one idea per sentence" whenever the
  ideas are causally linked — keep each sentence sayable in one breath, but let it
  carry a linked cause and effect, not a bare fact.
- BUILD, DON'T FLATTEN. After the hook, keep raising the stakes or the open
  question through the body toward a payoff near the end — never settle into a
  level-pitch list where every beat lands at the same weight. Order what you can so
  the tension deepens: the worst turn, the reversal, the twist comes LATE, not
  buried in the middle. Flat, evenly-weighted event escalation is the measured tell
  of this model specifically — fight it.
- HOLD THE COMPLEXITY, don't tidy it away. Where the history is genuinely messy — a
  figure who is both villain and victim, accounts that disagree, a question left
  open — keep that tension rather than smoothing it into one neat, single-track
  answer. Real stories carry ambiguity; flattening everything into tidy resolution
  reads as machine-made. (Never invent ambiguity the beats don't support.)
- DON'T FLINCH on the dark material. When the beats carry violence, cruelty, or
  death, render it plainly and precisely rather than hiding the documented event
  behind vague language or hurrying past it. Let it land, then move on.
  (Match the beats — invent no horror they don't state.)
- BUILD MOMENTUM. Sometimes plant a question or a tension at one stop and pay it
  off at the NEXT one, so the walk builds instead of resetting at each POI — the
  answer need not land in the same stop. (Keep the stop order; never move content
  between stops; a glue plant introduces no name or year no cited beat carries.)
- SIZE THE STOP TO THE WALK. Roughly 110-170 words for a standing single-idea
  stop, more for a dense multi-beat one but hard-capped near 750 words (five
  minutes); a minor stop can be one sharp sentence. Trim over-description and
  anything the walker can already see — cut by IDEA, never by truncation and
  never a fact.

CRAFT — sound like a person, not a machine. Human and machine narration differ
most in STRUCTURE and stance, not word-polish; these rules target the measured
tells that make generated prose feel generated:
- Do NOT state the meaning, lesson, or theme of a place. End on the fact, the
  image, or the open question and let the listener draw the conclusion. Avoid
  hollow significance inflation whose only job is to tell the walker what to
  think or feel.
- Name things. Use the specific person, book, street, and date the beats give
  you; never soften a real name into a vague gesture ("a famous writer").
- State feelings plainly when the beats state them. Do not replace sourced
  emotion with an invented bodily, weather, or object-personification metaphor,
  and add no sensory detail the beats do not contain.
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
  non-negotiable — fuse the wording, never lose a fact. Fuse only propositions
  that are actually equivalent; factual review judges their meaning, not shared
  wording.
- CITE EVERY BEAT YOU MERGE. When the two sentences you fuse come from DIFFERENT
  beats (different source_id), the merged sentence MUST keep one source_id as its
  primary AND list the OTHER merged beat id(s) in its "also_cites" field. This is
  mandatory: the faithfulness check entails a fused sentence against the UNION of
  its cited beats, so a cross-beat merge with only one source_id is rejected even
  though every fact is true. A sentence from a single beat leaves also_cites empty.
- ON A DENSE STOP, DE-DUPLICATE BY MEANING BEFORE YOU WRITE. A stop that seats many
  beats often has SEVERAL of them asserting the SAME fact with NO shared words —
  "built to house the relics", "raised to shelter the Crown of Thorns", and
  "commissioned to hold the Passion" are ONE fact, not three. Read every beat's
  key_claims first, GROUP the beats that make the same claim, and voice each
  grouped fact EXACTLY ONCE — the richest telling, keeping every distinct particular
  — with the other beats in ``also_cites``. Never re-tell one fact a second (or
  third) time in "fresh words": a stop that tells one story three ways is the single
  biggest reason these tours sound stilted and broken. Preserve every distinct
  proposition while fusing by meaning.
- Within a stop you may reorder sentences so events flow sensibly (usually
  oldest to newest), or open on what's in front of the walker and step back in
  time. Never move content between stops.

GROUNDING (violations are rejected by an automated verifier):
- Output the FULL sentence list. Every sentence carries source attribution.
- A sentence with source_type "beat" keeps its source_id and may only restate
  what that beat's key claims support — never add names, dates, or facts.
- A glue sentence must keep a source_id supplied in this stop's STITCHED SCRIPT.
  A requested reflection must use the source_id supplied in its REFLECTION SLOT.
  Never invent a source identity. Glue may not introduce proper nouns or years
  that no cited beat carries.
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
        {
            "stop_idx": slot,
            "source_id": GLUE_REFLECTION,
            "visited_claims": list(request.visited_claims_by_slot[slot]),
        }
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
            {"stop_idx": stop_idx, "a": a, "b": b} for stop_idx, a, b in request.duplicate_pairs
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


def compose_input_sha256(request: ComposeRequest) -> str:
    """Canonical hash of the exact typed input before provider-envelope metadata."""

    payload = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def candidate_compose_request_envelope(
    request: ComposeRequest,
    authoring_request: AuthoringStopRequest,
    *,
    model: str = COMPOSE_MODEL,
) -> tuple[str, dict[str, object]]:
    """Build one adaptive, 64K, candidate-bound physical authoring request."""

    stops = {sentence.stop_idx for sentence in request.stitched.script}
    if stops != {authoring_request.stop_index}:
        raise ValueError("authoring request stop differs from its compose input")
    if compose_input_sha256(request) != authoring_request.compose_input_sha256:
        raise ValueError("authoring request is bound to different compose input")
    binding = json.dumps(
        {
            "candidate_id": authoring_request.candidate.candidate_id,
            "request_id": authoring_request.request_id,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    user = _compose_user_prompt(request, 1, None) + "\n\nAUTHORING BINDING:\n" + binding
    sdk_request: dict[str, object] = {
        "model": model,
        "max_tokens": CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS,
        "thinking": {"type": "adaptive"},
        "system": _COMPOSE_SYSTEM,
        "output_config": {"format": {"type": "json_schema", "schema": _COMPOSE_OUTPUT_SCHEMA}},
        "messages": [{"role": "user", "content": user}],
    }
    return (
        json.dumps(
            sdk_request,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ),
        sdk_request,
    )


def _sentences_from_json(sentences: list[dict], request: ComposeRequest) -> tuple[Sentence, ...]:
    """Build ``Sentence`` objects from a compose response's JSON, COERCING each BEAT
    sentence's ``stop_idx`` to its beat's TRUE stitched stop.

    The model echoes ``stop_idx`` in its output; trusting that value verbatim let a
    mis-tagged beat sentence be bucketed into the wrong stop by the compose gate — a
    silent mis-placement / empty-stop / mis-repair class (a stop could ship with zero
    narration while the lenient tour-wide coverage gate still passed). A beat's home stop
    is unambiguous from the stitch, so we take it from ``beat_stop[source_id]`` and ignore
    the model's echo. Non-beat glue/reflection sentences (no source beat) keep their given
    slot ``stop_idx``; an unknown ``source_id`` (a hallucinated beat) is left as-given for
    the traceability gate to reject."""
    beat_stop = {
        s.source_id: s.stop_idx for s in request.stitched.script if s.source_type == "beat"
    }
    out: list[Sentence] = []
    for s in sentences:
        stype = s["source_type"]
        sid = s["source_id"]
        stop_idx = beat_stop.get(sid, s["stop_idx"]) if stype == "beat" else s["stop_idx"]
        out.append(
            Sentence(
                text=s["text"],
                source_id=sid,
                source_type=stype,
                stop_idx=stop_idx,
                # Only beat sentences carry fused citations; ignore any stray also_cites
                # the model attaches to glue.
                also_cites=(tuple(s.get("also_cites") or ()) if stype == "beat" else ()),
            )
        )
    return tuple(out)


def _certification_compose_requests(
    stitched: Script,
    beat_sequence: BeatSequence,
    route: Route,
) -> tuple[dict[str, BeatRef], list[int], dict[int, ComposeRequest]]:
    """Rebuild the canonical per-stop requests from the grounded source."""
    beats_by_id = {beat.id: beat for plan in beat_sequence.poi_beats for beat in plan.beats}
    tour_context = tuple(poi.name for poi in route.pois)
    by_stop: dict[int, list[Sentence]] = defaultdict(list)
    for sentence in stitched.script:
        by_stop[sentence.stop_idx].append(sentence)
    stops = sorted(by_stop)
    # The UPPER bound was deleted 2026-08-04 (OWNER RULING 5): duration alone
    # decides how many stops a route has, and refusing to author one the same
    # engine had already planned was a limit with no reason behind it. The LOWER
    # bound stays: ``requests`` below is keyed by stop index, so an empty stitch
    # would silently yield an empty authoring plan that a caller would then
    # "author" for zero stops and persist as a tour.
    if not stops:
        raise ValueError("authoring requires at least one stop")
    all_slots = tuple(
        slot
        for slot in reflection_slots(route, beat_sequence)
        if _visited_claims(stitched, beats_by_id, slot)
    )
    visited = {slot: _visited_claims(stitched, beats_by_id, slot) for slot in all_slots}

    requests: dict[int, ComposeRequest] = {}
    for stop_index in stops:
        stop_sentences = by_stop[stop_index]
        mini = stitched.model_copy(update={"script": tuple(stop_sentences)})
        stop_beats = {
            sentence.source_id: beats_by_id[sentence.source_id]
            for sentence in stop_sentences
            if sentence.source_type == "beat" and sentence.source_id in beats_by_id
        }
        requests[stop_index] = ComposeRequest(
            stitched=mini,
            beats_by_id=stop_beats,
            slots=tuple(slot for slot in all_slots if slot == stop_index),
            visited_claims_by_slot={
                index: claims for index, claims in visited.items() if index == stop_index
            },
            duplicate_pairs=(),
            tour_context=tour_context,
        )
    return beats_by_id, stops, requests


def _dedup_composed(sentences: list[Sentence], beat_sequence: BeatSequence) -> list[Sentence]:
    """The composed-path de-dup, ported byte-for-byte from ``compose.py`` (one-true-
    tour-algorithm ledger, step A5): collapse a fact voiced twice in the ASSEMBLED
    sentence stream — cross-beat claim repeat (the Île de la Cité three-source-book
    case, now most often cross-STOP since each stop is authored independently),
    same-stop byte-identical, and same-beat near-verbatim. Coverage-safe BY
    CONSTRUCTION: it keeps the FIRST telling / any sentence carrying a novel claim
    and never empties a beat, so a script that covered every claim before still
    does (a dropped twin's fact stays voiced by its survivor). Run inside
    ``finalize_certification_composition`` — the ONE finalizer both the persisted
    ``/trips/{id}/compose`` path (``author_prebuilt_route``) and ``/trips/preview``
    (``premium_tour.finalize_premium_composition``) call — so neither surface ships
    a duplicate the other suppresses. Always run BEFORE verify (with the
    pre-compose coverage baseline, when the caller enables it), so a drop that
    would unexpectedly lose a fact fails closed rather than shipping silently."""
    out = suppress_repeated_claims(sentences, beat_sequence, include_same_beat=True)
    out = suppress_exact_repeats(out, beat_sequence)
    out = suppress_same_beat_near_duplicates(out)
    return out


def finalize_certification_composition(
    stitched: Script,
    beat_sequence: BeatSequence,
    route: Route,
    *,
    completed_units: tuple[CompletedCertificationComposeUnit, ...],
    model: str = COMPOSE_MODEL,
    chunk_text_by_slug: dict[str, str] | None = None,
    faithfulness_checker: FaithfulnessChecker | None = None,
    enforce_claim_coverage: bool = False,
    scan_glue_for_invention: bool = False,
) -> CertificationComposition:
    """Purely verify and finalize already-completed per-stop compose responses.

    This is the durable replay boundary: it reconstructs every authorized request
    from the grounded source, rejects incomplete or alternate response sets, binds
    each parsed payload to its recorded hash, then runs VERIFY without editing the
    provider-authored text. Unlike the Basic Tour/live availability path, certification never
    splices or reverts to the grounded source.  It performs no provider calls and
    needs no in-memory call ledger.

    THE THREE GATE KNOBS, and why they are knobs (ledger decision D3).  This
    finalizer was written for the CERTIFICATION replay, whose judgement of prose is
    SEMANTIC: it validates structure only and lets factual review own meaning, so its
    defaults are the trusting offline entailment stub, no coverage baseline and no
    lexical scan.  The persisted ``POST /trips/{id}/compose`` path is the opposite
    case — it writes an unreviewed tour into Neo4j — and the whole-tour composer it
    replaced ran all three.  Rather than re-gate certification (a NEW check, which
    this ledger forbids) each is injectable and defaults OFF:

    * ``faithfulness_checker`` — the real entailment checker; ``None`` keeps the
      trusting ``MockFaithfulnessChecker``.
    * ``enforce_claim_coverage`` — derive the coverage baseline from the PRE-compose
      stitch, so a bold fusion may merge or reword a fact but never DELETE one.
    * ``scan_glue_for_invention`` — add ``validate_script``'s other half (the
      forbidden-phrase / invented-proper-noun / invented-year scan over glue) on top
      of the authorized-sources traceability below.  Structural traceability cannot
      see invention, so without this the count on the compose 422 reads 0 by
      construction rather than by measurement.
    """
    beats_by_id, stops, requests = _certification_compose_requests(stitched, beat_sequence, route)
    units_by_stop: dict[int, CompletedCertificationComposeUnit] = {}
    for unit in completed_units:
        if unit.unit_id != f"stop:{unit.stop_index}":
            raise ValueError("completed compose unit differs from its stop index")
        if unit.model != model:
            raise ValueError("completed compose unit used an unauthorized model")
        request_stops = {sentence.stop_idx for sentence in unit.authorized_request.stitched.script}
        if request_stops != {unit.stop_index}:
            raise ValueError("completed compose request spans a different stop")
        if unit.stop_index in units_by_stop:
            raise ValueError("completed compose response repeats a stop")
        units_by_stop[unit.stop_index] = unit
    if set(units_by_stop) != set(stops):
        raise ValueError("completed compose responses differ from candidate stops")

    composed_by_stop: dict[int, tuple[Sentence, ...]] = {}
    for stop_index in stops:
        unit = units_by_stop[stop_index]
        expected_request = requests[stop_index]
        if unit.authorized_request != expected_request:
            raise ValueError("completed compose request differs from grounded source")
        if unit.authoring_request.stop_index != stop_index:
            raise ValueError("completed authoring request differs from its stop")
        envelope, _ = candidate_compose_request_envelope(
            unit.authorized_request,
            unit.authoring_request,
            model=model,
        )
        expected_request_sha256 = hashlib.sha256(envelope.encode("utf-8")).hexdigest()
        if unit.request_sha256 != expected_request_sha256:
            raise ValueError("completed compose request hash is inconsistent")
        expected_payload_sha256 = sentences_payload_sha256(unit.parsed_provider_sentences)
        if unit.parsed_payload_sha256 != expected_payload_sha256:
            raise ValueError("completed compose parsed payload hash is inconsistent")
        composed_by_stop[stop_index] = unit.parsed_provider_sentences

    composed_sentences = _dedup_composed(
        [sentence for stop_index in stops for sentence in composed_by_stop[stop_index]],
        beat_sequence,
    )
    # ``composed_by_stop`` STAYS the raw provider payload. It is deliberately NOT
    # rebound to the post-dedup grouping.
    #
    # An earlier version of this port did rebind it, reasoning that the raw payload
    # "stays attested regardless" via ``response_sha256``. That was wrong twice over,
    # and a judge consult caught it:
    #   1. It made the fail-closed guard in ``finish`` a tautology. ``final_sentences``
    #      is a stop_idx filter over ``final_script.script``, which IS
    #      ``composed_sentences``; comparing it to the same filter over the same list
    #      can never differ, so a real provenance check silently became dead code.
    #   2. ``CompositionTrace.source_sentences`` / ``source_payload_sha256`` are what a
    #      replay reads as "what the provider returned". Recording post-dedup text there
    #      under ``derivation="provider_response"``, while ``response_sha256`` names the
    #      untouched body, makes the certification artifact claim bytes the provider
    #      never sent — on any tour where de-dup dropped a sentence.
    #
    # De-dup can only DROP sentences, never rewrite or reorder one, so the honest
    # relationship is SUBSEQUENCE: each stop's final text must appear in that stop's raw
    # provider output, in order. ``CompositionTrace`` is already built for exactly this —
    # ``source_sentence_indexes`` must be monotonic, unique and in range, one per final
    # sentence — so ``finish`` below proves the subsequence and records which raw
    # sentences survived, instead of asserting an identity that de-dup makes impossible.
    composed = stitched.model_copy(
        update={
            "script": tuple(composed_sentences),
            "total_audio_seconds": _sum_audio(composed_sentences, beat_sequence),
            "validation": ValidationReport(),
        }
    )
    authorized_derived_source_ids = frozenset(
        sentence.source_id
        for request in requests.values()
        for sentence in request.stitched.script
        if sentence.source_type != "beat"
    ) | ({GLUE_REFLECTION} if any(request.slots for request in requests.values()) else set())

    def validate_authorized_sources(script: Script, sequence: BeatSequence) -> ValidationReport:
        report = validate_source_traceability(
            script,
            sequence,
            allowed_derived_source_ids=frozenset(authorized_derived_source_ids),
        )
        if not scan_glue_for_invention:
            return report
        # Full ``validate_script`` parity. Only the forbidden-phrase half is taken
        # from it: its traceability half does not know THIS run's authorized derived
        # source ids, so it would reject legitimately-authorized glue.
        return report.model_copy(
            update={
                "forbidden_phrase_hits": validate_script(script, sequence).forbidden_phrase_hits
            }
        )

    verifier = build_full_verifier(
        beat_sequence,
        beats_by_id,
        chunk_text_by_slug=chunk_text_by_slug,
        faithfulness_checker=faithfulness_checker,
        # This function's public signature keeps ``faithfulness_checker=None``
        # (pinned by tests/test_tour_authoring_gates.py), and the offline
        # certification-replay path genuinely runs without one. The gate no
        # longer substitutes a trusting checker behind our back, so state the
        # intent here instead: no checker means the faithfulness pass is SKIPPED,
        # and the report it returns says so via ``faithfulness_checked=False``.
        # The live API never takes this branch — src/api/dependencies.py always
        # injects the real Haiku checker.
        allow_unverified_faithfulness=faithfulness_checker is None,
        # The baseline is what the PRE-compose stitch actually voiced — not every
        # key_claim — so the gate blocks deletion without demanding a beat's prose
        # voice claims it never voiced.
        expected_claim_ids=(
            claims_realized_by(stitched, beats_by_id) if enforce_claim_coverage else None
        ),
        base_validator=validate_authorized_sources,
    )
    report = verifier(composed)

    def finish(final_script: Script) -> CertificationComposition:
        traces: list[CompositionTrace] = []
        attested: set[int] = set()
        for stop_index in stops:
            unit = units_by_stop[stop_index]
            sentence_indexes = tuple(
                index
                for index, sentence in enumerate(final_script.script)
                if sentence.stop_idx == stop_index
            )
            final_sentences = tuple(final_script.script[index] for index in sentence_indexes)
            source_sentences = composed_by_stop[stop_index]  # the RAW provider payload
            stitched_source = requests[stop_index].stitched.script
            if not final_sentences:
                raise ValueError(
                    f"stop {stop_index} has no composed text left after de-dup — the "
                    "provider response cannot be attested by an empty trace"
                )
            # PROVE the subsequence, and record WHICH raw sentences survived de-dup.
            # De-dup may only drop, so every final sentence must appear in this stop's
            # raw provider output, in order. A sentence that does not — e.g. a glue or
            # reflection line whose stop_idx was mis-echoed by the provider and so
            # re-attributed to a neighbouring stop — raises here instead of shipping
            # inside a trace that says the provider authored it.
            surviving: list[int] = []
            cursor = 0
            for sentence in final_sentences:
                while cursor < len(source_sentences) and source_sentences[cursor] != sentence:
                    cursor += 1
                if cursor >= len(source_sentences):
                    raise ValueError(
                        f"stop {stop_index} composed text is not a subsequence of the "
                        "provider response — a sentence is attributed to a stop the "
                        "provider did not author it for"
                    )
                surviving.append(cursor)
                cursor += 1
            source_indexes = tuple(surviving)
            traces.append(
                CompositionTrace(
                    unit_id=unit.unit_id,
                    stop_index=stop_index,
                    request_sha256=unit.request_sha256,
                    response_sha256=unit.response_sha256,
                    derivation="provider_response",
                    authorized_source_sentences=stitched_source,
                    source_sentences=source_sentences,
                    source_payload_sha256=sentences_payload_sha256(source_sentences),
                    source_sentence_indexes=source_indexes,
                    sentence_indexes=sentence_indexes,
                    sentence_sha256s=tuple(
                        hashlib.sha256(final_script.script[index].text.encode("utf-8")).hexdigest()
                        for index in sentence_indexes
                    ),
                )
            )
            attested.update(sentence_indexes)
        # No sentence may ship unattested. Grouping by stop_idx silently skips any
        # sentence whose stop_idx falls outside `stops`, which would put narration in
        # composed.script that no CompositionTrace covers at all.
        if attested != set(range(len(final_script.script))):
            unattested = sorted(set(range(len(final_script.script))) - attested)
            raise ValueError(
                f"composed script carries {len(unattested)} sentence(s) attested by no "
                f"composition trace (indexes {unattested[:5]}) — their stop_idx falls "
                "outside the authored stop set"
            )
        return CertificationComposition(script=final_script, composition_trace=tuple(traces))

    if report.passed:
        return finish(composed.model_copy(update={"validation": report}))
    raise ComposeVerificationError(report, 1)


__all__ = [
    "CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS",
    "COMPOSE_MAX_OUTPUT_TOKENS",
    "COMPOSE_MODEL",
    "CertificationComposition",
    "CompletedCertificationComposeUnit",
    "ComposeRequest",
    "candidate_compose_request_envelope",
    "compose_input_sha256",
    "finalize_certification_composition",
]
