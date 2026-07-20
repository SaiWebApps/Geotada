"""Phase 4 Step 4.3 — ComposeRequest + MockComposeClient.

The stitched Script comes from the REAL generate() (MockGlueClient), so the
mock composer is exercised against actual stitcher shapes: cold-open, GLUE_NAV
transits, corpus transit beats, anchor blocks.
"""

from __future__ import annotations

import pytest

from src.tour.compose import (
    MockComposeClient,
    build_compose_request,
    compose_script,
    compose_script_per_chapter,
)
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
from src.tour.generation import GLUE_NAV, GLUE_REFLECTION, SPOKEN_WPM, generate

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
    # THE GUARANTEE: the composed stream's audio total grows by exactly what the
    # added reflections SAY. Until 2026-07-19 this asserted a flat "+4s per glue
    # reflection" — the founding defect of the audio-clock rewrite. These
    # reflections are real sentences ("Worth holding onto from what you've seen so
    # far: Henri IV completed the square in 1612."), so crediting them 4s each made
    # walk-leg narration invisible to the tour's own clock. Now they are credited
    # their real spoken length at SPOKEN_WPM.
    added_words = sum(len(s.text.split()) for s in reflections)
    assert composed.total_audio_seconds == (
        stitched.total_audio_seconds + round(added_words / SPOKEN_WPM * 60)
    )
    assert composed.total_audio_seconds > stitched.total_audio_seconds + 4 * len(reflections), (
        "real reflections must be worth more than the old flat 4s-per-glue estimate"
    )


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
# Per-chapter compose: one focused (parallel) call per stop, whole-tour verify,
# per-stop recompose, per-stop repair.
# ---------------------------------------------------------------------------


class _FailStop2Client:
    """Honest mock everywhere except it fabricates an untraceable sentence
    whenever the mini-request is for stop 2 (persistently — never recovers)."""

    def __init__(self):
        self.mock = MockComposeClient()
        self.stops_seen: list[frozenset[int]] = []

    def compose(self, request, attempt, prev_report):
        idxs = frozenset(s.stop_idx for s in request.stitched.script)
        self.stops_seen.append(idxs)
        base = tuple(self.mock.compose(request, attempt, prev_report))
        if 2 in idxs:
            return (*base, Sentence(text="Nope.", source_id="ghost",
                                    source_type="beat", stop_idx=2))
        return base


def test_per_chapter_composes_each_stop_alone_and_serves():
    seq, route, stitched = _five_stop_setup()
    client = _FailStop2Client()
    composed = compose_script_per_chapter(stitched, seq, route, client=client)
    assert composed.validation.passed  # served via per-stop repair, not refused
    # EVERY request was a single stop — the defining per-chapter property.
    assert client.stops_seen and all(len(idxs) == 1 for idxs in client.stops_seen)


def test_per_chapter_reverts_only_the_failed_stop_and_keeps_facts():
    seq, route, stitched = _five_stop_setup()
    client = _FailStop2Client()
    composed = compose_script_per_chapter(stitched, seq, route, client=client)
    # the bad stop's fabrication is gone (stop 2 reverted to its grounded stitch)
    assert not any(s.source_id == "ghost" for s in composed.script)
    # stop 2 was RETRIED (its own recompose) before being reverted
    assert client.stops_seen.count(frozenset({2})) >= 2
    # reflections still land at the two slots, verified on the assembled whole
    assert len([s for s in composed.script if s.source_id == GLUE_REFLECTION]) == 2
    # every stitched beat sentence survives (mock is identity on the good stops)
    st = {s.text for s in stitched.script if s.source_type == "beat"}
    assert st <= {s.text for s in composed.script if s.source_type == "beat"}


def test_per_chapter_verify_report_is_populated_per_stop():
    """The compose result carries a per-stop verify_report: one entry per stop,
    each marked composed or reverted_to_stitched. On the clean path every stop is
    composed and its reason tuples are empty."""
    seq, route, stitched = _five_stop_setup()
    composed = compose_script_per_chapter(stitched, seq, route, client=MockComposeClient())
    stops = sorted({s.stop_idx for s in stitched.script})
    assert [r.stop_idx for r in composed.verify_report] == stops
    assert all(r.status == "composed" for r in composed.verify_report)
    assert all(
        not (r.faithfulness or r.coverage or r.forbidden or r.untraceable)
        for r in composed.verify_report
    )


def test_per_chapter_verify_report_flags_the_reverted_stop_with_its_reason():
    """A stop that reverts to the stitch (its fact-carrying rewrite failed
    entailment, and dropping it left the claim uncovered) is marked
    reverted_to_stitched AND carries the exact faithfulness + coverage reasons —
    the diagnostic that pinpoints WHY a stop lost its AI voice, without re-running."""
    # Every stop carries a claim; short legs -> no reflection slots, so the test
    # isolates the beat-paraphrase revert path (stop 1 is the target).
    seq = _seq(
        [
            [_claim_beat("b0", "p0", CLAIM_A)],
            [_claim_beat("b1", "p1", CLAIM_B)],
            [_claim_beat("b2", "p2", "Napoleon crowned himself emperor in 1804")],
        ]
    )
    route = _route([10, 10, 10])
    stitched = generate(seq, route, _input())

    class _ParaphraseStop1Client:
        """Identity everywhere except stop 1, whose beat sentence it paraphrases
        away from a claim substring — a bold-but-faithful reword a STRICT checker
        over-rejects. Dropping it uncovers stop 1's claim, forcing a whole revert."""

        def compose(self, request, attempt, prev_report):
            stop = next(iter({s.stop_idx for s in request.stitched.script}))
            out = []
            for s in request.stitched.script:
                if stop == 1 and s.source_type == "beat":
                    out.append(s.model_copy(update={"text": "A totally reworded telling."}))
                else:
                    out.append(s)
            return tuple(out)

    class _StrictSubstringChecker:  # entails only a near-verbatim claim quote
        def entails(self, key_claims, sentence_text):
            return any(c in sentence_text for c in key_claims)

    composed = compose_script_per_chapter(
        stitched, seq, route, client=_ParaphraseStop1Client(),
        faithfulness_checker=_StrictSubstringChecker(),
    )
    by_stop = {r.stop_idx: r for r in composed.verify_report}
    assert by_stop[1].status == "reverted_to_stitched"
    # the exact gate reasons that flattened stop 1 are surfaced
    assert by_stop[1].faithfulness  # the paraphrase failed entailment
    assert by_stop[1].coverage      # dropping it left the claim uncovered
    # every other stop kept its composed narration
    assert all(by_stop[k].status == "composed" for k in by_stop if k != 1)


def test_per_chapter_propagates_a_systemic_client_error():
    """A client error (auth / billing / rate-limit) must SURFACE, not be silently
    reverted to stitched and mislabelled a partial compose."""
    seq, route, stitched = _five_stop_setup()

    class _BoomClient:
        def compose(self, request, attempt, prev_report):
            raise RuntimeError("credit balance too low")

    with pytest.raises(RuntimeError, match="credit balance"):
        compose_script_per_chapter(stitched, seq, route, client=_BoomClient())


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
    assert "fuse repeats boldly" in s                              # in-stop dedup mandate
    assert "fuse without fear" in s                                # coverage-gate reassurance
    assert "precise time of day" in s                              # reflection embellishment guard


def test_best_of_n_picks_the_cleaner_candidate_per_stop():
    """candidates=2 composes each stop twice and keeps the lower-penalty one:
    stop 0's first candidate embellishes (an entailment failure), its second is
    clean, so the clean one is kept and the tour serves."""
    import threading

    seq, route, stitched = _five_stop_setup()

    class _AliensChecker:  # entails anything that does NOT smuggle in 'ALIENS'
        def entails(self, key_claims, sentence_text):
            return "ALIENS" not in sentence_text

    class _BestOfClient:
        def __init__(self):
            self._lock = threading.Lock()
            self._n: dict[int, int] = {}
            self.calls = 0

        def compose(self, request, attempt, prev_report):
            stop = next(iter({s.stop_idx for s in request.stitched.script}))
            with self._lock:
                self.calls += 1
                k = self._n.get(stop, 0)
                self._n[stop] = k + 1
            base = list(request.stitched.script)
            if stop == 0 and k == 0:  # first candidate at stop 0 embellishes its BEAT sentences
                base = [
                    s.model_copy(update={"text": s.text + " ALIENS"})
                    if s.source_type == "beat"
                    else s
                    for s in base
                ]
            return tuple(base)

    client = _BestOfClient()
    composed = compose_script_per_chapter(
        stitched, seq, route, client=client, faithfulness_checker=_AliensChecker(), candidates=2
    )
    assert composed.validation.passed
    assert not any("ALIENS" in s.text for s in composed.script)  # the bad candidate was dropped
    assert client.calls == 2 * len({s.stop_idx for s in stitched.script})  # best-of-2, every stop


# ---------------------------------------------------------------------------
# Empty reflection slots must be dropped on BOTH compose paths
# ---------------------------------------------------------------------------


def test_per_chapter_drops_empty_claim_slots_like_the_whole_tour_path() -> None:
    """The per-chapter composer (the WORKBENCH path) must fail closed on a slot
    whose visited beats carry no key_claims — exactly as build_compose_request
    already did for the whole-tour path.

    A reflection is instructed to be supported by its slot's claim list ALONE. With
    an empty list that instruction is unsatisfiable: the composer writes nothing, or
    writes something unsupported that VERIFY rejects. Either way the slot is a
    guaranteed loss that costs an Opus call to discover.

    MEASURED on the live Paris graph: 1 of 10 slots across six representative tours,
    and the one it hit was the tour with a 10 min 56 s unbroken silence — the tour
    most in need of leg content had its only slot guaranteed to fail. London's
    corpus is 100% keyless, so there it is every slot.

    UNDO TEST: restore ``all_slots = reflection_slots(route, beat_sequence)`` in
    compose_script_per_chapter and this goes RED.
    """
    # Both stops CLAIMLESS -> the leg into stop 1 is an eligible slot by walk
    # deficit, but its visited-claims union is empty.
    seq = _seq(
        [
            [_claim_beat("b0", "p0", None)],
            [_claim_beat("b1", "p1", None)],
        ]
    )
    route = _route([10, 400])
    stitched = generate(seq, route, _input())

    # The slot IS placed (the walk deficit qualifies it) ...
    from src.tour.reflection import reflection_slots

    assert reflection_slots(route, seq) == (1,), "fixture must produce an eligible slot"

    # ... but it must never be HANDED TO THE COMPOSER.
    #
    # Asserting on the composed OUTPUT is not a real test here: MockComposeClient
    # renders a reflection from its claim tuple, so an empty tuple yields no
    # sentence either way and the assertion passes with the fix reverted. (That
    # exact fake guard was written first and caught by its own undo test.) The
    # observable seam is the ComposeRequest the client actually receives.
    seen: list[tuple[int, ...]] = []

    class _SpyClient:
        def __init__(self) -> None:
            self._inner = MockComposeClient()

        def compose(self, request, attempt, prev_report):
            seen.append(request.slots)
            return self._inner.compose(request, attempt, prev_report)

    compose_script_per_chapter(stitched, seq, route, client=_SpyClient())

    assert seen, "the composer must have been called at least once"
    assert all(s == () for s in seen), (
        f"an empty-claim slot was handed to the composer: requested slots {seen}. "
        "It must be dropped fail-closed, as build_compose_request already does."
    )


def test_per_chapter_still_composes_slots_that_do_have_claims() -> None:
    """The fix must drop ONLY empty slots — a claim-bearing slot still reflects."""
    seq, route, stitched = _five_stop_setup()
    composed = compose_script_per_chapter(stitched, seq, route, client=MockComposeClient())
    reflections = [s for s in composed.script if s.source_id == GLUE_REFLECTION]
    assert len(reflections) >= 1, "claim-bearing slots must still produce reflections"
    assert any(CLAIM_A in r.text for r in reflections)
