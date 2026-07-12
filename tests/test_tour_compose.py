"""Phase 4 Step 4.3 — ComposeRequest + MockComposeClient.

The stitched Script comes from the REAL generate() (MockGlueClient), so the
mock composer is exercised against actual stitcher shapes: cold-open, GLUE_NAV
transits, corpus transit beats, anchor blocks.
"""

from __future__ import annotations

import pytest

from src.tour.compose import MockComposeClient, build_compose_request, compose_script
from src.tour.compose_gate import ComposeVerificationError, build_full_verifier
from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    POIBeats,
    Route,
    Sentence,
    TourInput,
    TransitSegment,
)
from src.tour.generation import GLUE_NAV, GLUE_REFLECTION, generate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _poi(pid: str) -> POI:
    return POI(id=pid, name=pid, tier=5, poi_role="stop", lat=48.85, lng=2.36)


def _claim_beat(bid: str, poi_id: str, claim: str | None, **kwargs) -> BeatRef:
    """A beat whose script_body IS its key claim — so a strict verbatim
    checker can entail both the beat sentence and a reflection quoting it."""
    body = kwargs.pop("body", claim or "A plain fact with no claim.")
    return BeatRef(
        id=bid,
        poi_id=poi_id,
        script_body=body,
        word_count=len(body.split()),
        key_claims=(claim,) if claim else (),
        **kwargs,
    )


def _route(walks: list[int]) -> Route:
    pois = tuple(_poi(f"p{i}") for i in range(len(walks)))
    transits = tuple(
        TransitSegment(
            from_poi_id=None if i == 0 else pois[i - 1].id,
            to_poi_id=p.id,
            distance_m=100.0,
            walk_seconds=walks[i],
        )
        for i, p in enumerate(pois)
    )
    return Route(
        pois=pois,
        transits=transits,
        total_walk_distance_m=100.0 * len(pois),
        total_walk_seconds=sum(walks),
    )


def _seq(stops: list[list[BeatRef]]) -> BeatSequence:
    return BeatSequence(
        poi_beats=tuple(
            POIBeats(
                poi_id=f"p{i}",
                poi_name=f"p{i}",
                ordering_strategy="sub_location",
                beats=tuple(beats),
            )
            for i, beats in enumerate(stops)
        )
    )


def _input() -> TourInput:
    return TourInput(start=(48.85, 2.36), duration_min=60, city_slug="paris")


CLAIM_A = "Henri IV completed the square in 1612"
CLAIM_B = "Victor Hugo lived at number 6"


def _five_stop_setup() -> tuple:
    """5 stops; legs into 1 and 3 are long -> slots (1, 3). Claims at stops
    0 (A) and 1 (B); stops 2-4 claimless."""
    seq = _seq(
        [
            [_claim_beat("b0", "p0", CLAIM_A)],
            [_claim_beat("b1", "p1", CLAIM_B)],
            [_claim_beat("b2", "p2", None)],
            [_claim_beat("b3", "p3", None)],
            [_claim_beat("b4", "p4", None)],
        ]
    )
    route = _route([10, 400, 10, 400, 10])
    stitched = generate(seq, route, _input())
    assert stitched.validation.passed  # sanity: the baseline is clean
    return seq, route, stitched


# ---------------------------------------------------------------------------
# build_compose_request
# ---------------------------------------------------------------------------


def test_request_computes_slots_and_visited_claim_unions():
    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    assert request.slots == (1, 3)
    assert request.visited_claims_by_slot[1] == (CLAIM_A,)
    assert request.visited_claims_by_slot[3] == (CLAIM_A, CLAIM_B)


def test_empty_union_slot_is_dropped_fail_closed():
    # Only eligible leg is into stop 1, but stop 0 carries NO claims.
    seq = _seq(
        [
            [_claim_beat("b0", "p0", None)],
            [_claim_beat("b1", "p1", None)],
        ]
    )
    route = _route([10, 400])
    stitched = generate(seq, route, _input())
    request = build_compose_request(stitched, seq, route)
    assert request.slots == ()
    composed = MockComposeClient().compose(request, 1, None)
    assert composed == stitched.script  # nothing added, nothing lost


# ---------------------------------------------------------------------------
# MockComposeClient
# ---------------------------------------------------------------------------


def test_mock_preserves_every_stitched_sentence_in_order():
    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    composed = MockComposeClient().compose(request, 1, None)
    without_reflections = tuple(s for s in composed if s.source_id != GLUE_REFLECTION)
    assert without_reflections == stitched.script


def test_mock_inserts_one_reflection_per_slot_after_the_transit_glue():
    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    composed = list(MockComposeClient().compose(request, 1, None))

    reflections = [s for s in composed if s.source_id == GLUE_REFLECTION]
    assert [s.stop_idx for s in reflections] == [1, 3]
    for r in reflections:
        i = composed.index(r)
        before, after = composed[i - 1], composed[i + 1]
        # Right after the leg's GLUE_NAV line...
        assert before.source_id == GLUE_NAV and before.stop_idx == r.stop_idx
        # ...and before the stop's anchor beats.
        assert after.source_type == "beat" and after.stop_idx == r.stop_idx
    # The slot-1 reflection quotes the visited claim verbatim.
    assert CLAIM_A in reflections[0].text


def test_mock_inserts_after_a_corpus_transit_beat_run():
    """When the leg's opener is a corpus transit BEAT (not glue), the
    reflection lands after its sentences, before the anchor block."""
    transit = _claim_beat(
        "t1",
        "p1",
        None,
        body="Leave p0 and follow the quay toward p1.",
        narrative_function="transition",
        trigger_address="from p0",
    )
    seq = _seq(
        [
            [_claim_beat("b0", "p0", CLAIM_A)],
            [transit, _claim_beat("b1", "p1", None)],
        ]
    )
    route = _route([10, 400])
    stitched = generate(seq, route, _input())
    request = build_compose_request(stitched, seq, route)
    composed = list(MockComposeClient().compose(request, 1, None))

    (reflection,) = [s for s in composed if s.source_id == GLUE_REFLECTION]
    i = composed.index(reflection)
    assert composed[i - 1].source_id == "t1"  # the transit beat's last sentence
    assert composed[i + 1].source_id == "b1"  # the anchor block follows


def test_composed_script_passes_the_full_verifier_with_a_strict_checker():
    """End-to-end tooth: validate_script + provenance + a STRICT verbatim
    entailment checker all pass on the mock-composed output."""

    class StrictVerbatimChecker:
        def entails(self, key_claims, sentence_text):
            return any(c in sentence_text for c in key_claims)

    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    composed = MockComposeClient().compose(request, 1, None)
    script = stitched.model_copy(update={"script": composed})

    verify = build_full_verifier(
        seq, request.beats_by_id, faithfulness_checker=StrictVerbatimChecker()
    )
    report = verify(script)
    assert report.passed, (
        report.untraceable_sentences,
        report.forbidden_phrase_hits,
        report.faithfulness_failures,
    )


def test_mock_records_attempt_and_prev_report():
    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    client = MockComposeClient()
    client.compose(request, 1, None)
    marker = stitched.validation
    client.compose(request, 2, marker)
    assert client.calls == [(1, None), (2, marker)]


# ---------------------------------------------------------------------------
# compose_script (Step 4.4) — fire-once behind the M7 gate
# ---------------------------------------------------------------------------


class _FailNTimesClient:
    """Emits a fabricated (untraceable) sentence for the first ``n`` attempts,
    then delegates to the honest mock."""

    def __init__(self, n: int):
        self.n = n
        self.mock = MockComposeClient()
        self.calls: list[tuple[int, object]] = []

    def compose(self, request, attempt, prev_report):
        self.calls.append((attempt, prev_report))
        if attempt <= self.n:
            fabricated = Sentence(
                text="A fact from nowhere.",
                source_id="not-a-real-beat",
                source_type="beat",
                stop_idx=0,
            )
            return (*request.stitched.script, fabricated)
        return self.mock.compose(request, attempt, prev_report)


def test_compose_script_fires_exactly_once_when_clean():
    seq, route, stitched = _five_stop_setup()
    client = MockComposeClient()
    composed = compose_script(stitched, seq, route, client=client)
    assert len(client.calls) == 1
    assert composed.validation.passed
    reflections = [s for s in composed.script if s.source_id == GLUE_REFLECTION]
    assert len(reflections) == 2
    # Audio total re-estimated for the composed stream: +4s per glue reflection.
    assert composed.total_audio_seconds == stitched.total_audio_seconds + 4 * len(reflections)


def test_compose_script_recomposes_once_steered_by_the_failing_report():
    seq, route, stitched = _five_stop_setup()
    client = _FailNTimesClient(1)
    composed = compose_script(stitched, seq, route, client=client)
    assert [a for a, _ in client.calls] == [1, 2]
    first_prev, second_prev = client.calls[0][1], client.calls[1][1]
    assert first_prev is None
    # The recompose sees WHY attempt 1 failed: the fabricated sentence.
    assert second_prev is not None
    assert any(s.source_id == "not-a-real-beat" for s in second_prev.untraceable_sentences)
    assert composed.validation.passed


def test_compose_script_blocks_after_the_bounded_recompose():
    seq, route, stitched = _five_stop_setup()
    client = _FailNTimesClient(2)
    with pytest.raises(ComposeVerificationError) as exc:
        compose_script(stitched, seq, route, client=client)
    assert exc.value.attempts == 2
    assert len(client.calls) == 2  # never a third attempt


# ---------------------------------------------------------------------------
# AnthropicComposeClient (Step 4.5) — offline, fake SDK client injected
# ---------------------------------------------------------------------------


class _FakeBlock:
    def __init__(self, type_: str, text: str = ""):
        self.type = type_
        self.text = text


class _FakeResponse:
    def __init__(self, payload: str, stop_reason: str = "end_turn"):
        self.content = [_FakeBlock("thinking"), _FakeBlock("text", payload)]
        self.usage = type("U", (), {"input_tokens": 120, "output_tokens": 45})()
        self.stop_reason = stop_reason


class _FakeStream:
    """Mimics client.messages.stream(...) — a context manager whose
    get_final_message() returns the accumulated response."""

    def __init__(self, response: _FakeResponse):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._response


class _FakeMessages:
    def __init__(self, payload: str, stop_reason: str = "end_turn"):
        self.payload = payload
        self.stop_reason = stop_reason
        self.calls: list[dict] = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeStream(_FakeResponse(self.payload, self.stop_reason))


class _FakeSDKClient:
    def __init__(self, payload: str, stop_reason: str = "end_turn"):
        self.messages = _FakeMessages(payload, stop_reason)


def _anthropic_client_setup():
    import json

    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    payload = json.dumps(
        {
            "sentences": [
                {"text": "A fact.", "source_id": "b0", "source_type": "beat", "stop_idx": 0},
            ]
        }
    )
    fake = _FakeSDKClient(payload)
    from src.tour.compose import AnthropicComposeClient

    return request, fake, AnthropicComposeClient(client=fake)


def test_anthropic_client_request_shape_and_parsing():
    request, fake, client = _anthropic_client_setup()
    sentences = client.compose(request, 1, None)

    assert sentences == (
        Sentence(text="A fact.", source_id="b0", source_type="beat", stop_idx=0),
    )
    assert client.input_tokens == 120 and client.output_tokens == 45

    (call,) = fake.messages.calls
    assert call["model"] == "claude-opus-4-8"
    assert call["thinking"] == {"type": "adaptive"}
    # Structured output: guaranteed-valid JSON against a strict schema.
    schema = call["output_config"]["format"]["schema"]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["sentences"]["items"]["additionalProperties"] is False
    # No sampling params on Opus 4.7+ (they 400).
    assert "temperature" not in call and "top_p" not in call and "top_k" not in call
    # The LOCKED single-narrator voice + grounding rules ride the system prompt.
    assert "ONE warm, second-person narrator" in call["system"]
    assert "GLUE_REFLECTION" in call["system"]
    # The user prompt carries the stitched script, key claims, and slots.
    user = call["messages"][0]["content"]
    assert CLAIM_A in user and CLAIM_B in user
    assert "REFLECTION SLOTS" in user and '"stop_idx": 3' in user


def test_anthropic_client_recompose_prompt_carries_the_failure():
    request, fake, client = _anthropic_client_setup()
    fabricated = Sentence(
        text="A fact from nowhere.", source_id="ghost", source_type="beat", stop_idx=0
    )
    prev = request.stitched.validation.model_copy(
        update={"untraceable_sentences": (fabricated,)}
    )
    client.compose(request, 2, prev)
    user = fake.messages.calls[-1]["messages"][0]["content"]
    assert "PREVIOUS ATTEMPT FAILED" in user
    assert "A fact from nowhere." in user


def test_anthropic_client_injected_client_needs_no_sdk_construction():
    """With an injected client the constructor performs no anthropic import
    (the deferred-import branch is only for the real path)."""
    _, fake, client = _anthropic_client_setup()
    assert client._client is fake


def test_anthropic_client_raises_on_max_tokens_truncation():
    """A max_tokens stop means the sentence list is incomplete — hard error,
    never fed to json.loads (a real 45-min tour hit this at 16K, live gate)."""
    seq, route, stitched = _five_stop_setup()
    request = build_compose_request(stitched, seq, route)
    fake = _FakeSDKClient('{"sentences":[{"text":"cut off mid', stop_reason="max_tokens")
    from src.tour.compose import AnthropicComposeClient

    client = AnthropicComposeClient(client=fake)
    with pytest.raises(ValueError, match="truncated at max_tokens"):
        client.compose(request, 1, None)


def test_anthropic_client_raises_helpful_error_when_no_text_block():
    """Audit-found robustness gap: a terminal response with no text block (a
    refusal / thinking-only turn) must raise a clear ValueError, not a bare
    StopIteration from an exhausted generator."""
    import pytest

    request, fake, client = _anthropic_client_setup()

    class _NoTextResponse:
        def __init__(self):
            self.content = [_FakeBlock("thinking")]  # no "text" block at all
            self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 0})()
            self.stop_reason = "refusal"

    class _NoTextStream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return _NoTextResponse()

    fake.messages.stream = lambda **kw: _NoTextStream()
    with pytest.raises(ValueError, match="no text block"):
        client.compose(request, 1, None)


def test_compose_system_prompt_carries_the_anti_tell_craft_rules():
    """Prompt v2 encodes the StoryScope-measured AI tells to suppress (the
    Fable-5 advisor's P0 craft), so attempt 1 leans human, not machine."""
    from src.tour.compose import _COMPOSE_SYSTEM
    s = _COMPOSE_SYSTEM.lower()
    assert "a testament to" in s and "stands as a symbol of" in s  # moralizing ban
    assert "never convert a feeling" in s                          # embodied-emotion ban
    assert "name things" in s                                      # explicit-naming push
    assert "vary the shape of the stops" in s                      # anti-uniformity
    assert "same fact in different words" in s                     # in-stop dedup
    assert "precise time of day" in s                              # reflection embellishment guard
