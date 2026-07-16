"""Unit tests for the REAL ``OpenAIComposeClient`` translation logic — the request
it builds and the response it parses — exercised against a FAKE OpenAI SDK object
at the network boundary only.

This is NOT the banned 'mock composer' (``MockComposeClient`` returns the stitcher
passthrough and must never reach the product): here the client's REAL code runs on
every line; only the paid HTTP call is faked, so ``make test`` verifies the plumbing
at $0. Writing QUALITY is judged separately by a real, live Opus-vs-ChatGPT
compare with a printed cost estimate — never here, never by a mock.
"""

from __future__ import annotations

import json

import pytest

from src.tour.compose import (
    _COMPOSE_SYSTEM,
    _OPENAI_COMPOSE_OUTPUT_SCHEMA,
    OpenAIComposeClient,
    build_compose_request,
)
from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    POIBeats,
    Route,
    TourInput,
    TransitSegment,
)
from src.tour.generation import generate


def _request():
    poi = POI(id="p0", name="p0", tier=5, poi_role="stop", lat=48.85, lng=2.36)
    beat = BeatRef(
        id="b0",
        poi_id="p0",
        script_body="Henri IV finished the square in 1612.",
        word_count=7,
        key_claims=("Henri IV finished the square in 1612",),
    )
    seq = BeatSequence(
        poi_beats=(
            POIBeats(poi_id="p0", poi_name="p0", ordering_strategy="sub_location", beats=(beat,)),
        )
    )
    route = Route(
        pois=(poi,),
        transits=(
            TransitSegment(from_poi_id=None, to_poi_id="p0", distance_m=100.0, walk_seconds=10),
        ),
        total_walk_distance_m=100.0,
        total_walk_seconds=10,
    )
    stitched = generate(
        seq, route, TourInput(start=(48.85, 2.36), duration_min=90, city_slug="paris")
    )
    return build_compose_request(stitched, seq, route)


class _FakeUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content, finish_reason="stop"):
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason


class _FakeResponse:
    def __init__(self, content, finish_reason="stop", usage=None):
        self.choices = [_FakeChoice(content, finish_reason)]
        self.usage = usage if usage is not None else _FakeUsage(11, 22)


class _FakeCompletions:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


class _FakeChat:
    def __init__(self, response):
        self.completions = _FakeCompletions(response)


class _FakeOpenAI:
    """A stand-in for ``openai.OpenAI()`` — only the ``chat.completions.create``
    surface the client touches. The client's real request-building and
    response-parsing run against it; no network, no billing."""

    def __init__(self, response):
        self.chat = _FakeChat(response)


def _payload(sentences):
    return json.dumps({"sentences": sentences})


def test_openai_client_parses_response_into_sentences():
    payload = _payload(
        [
            {
                "text": "You're standing in the square.",
                "source_id": "GLUE_STAGING",
                "source_type": "glue",
                "stop_idx": 0,
                "also_cites": ["should_be_ignored_on_glue"],
            },
            {
                "text": "Henri IV finished it in 1612.",
                "source_id": "b0",
                "source_type": "beat",
                "stop_idx": 0,
                "also_cites": ["bX"],
            },
        ]
    )
    client = OpenAIComposeClient(model="gpt-4o", client=_FakeOpenAI(_FakeResponse(payload)))
    out = client.compose(_request(), 1, None)
    assert [s.text for s in out] == [
        "You're standing in the square.",
        "Henri IV finished it in 1612.",
    ]
    glue, beat = out
    assert glue.source_type == "glue" and glue.also_cites == ()  # dropped on glue
    assert beat.source_type == "beat" and beat.also_cites == ("bX",)  # kept on beat


def test_openai_client_sends_system_prompt_strict_schema_and_model():
    fake = _FakeOpenAI(_FakeResponse(_payload([])))
    OpenAIComposeClient(model="gpt-4o", client=fake).compose(_request(), 1, None)
    kw = fake.chat.completions.calls[0]
    assert kw["model"] == "gpt-4o"
    assert kw["messages"][0] == {"role": "system", "content": _COMPOSE_SYSTEM}
    assert kw["messages"][1]["role"] == "user"
    assert "STITCHED SCRIPT" in kw["messages"][1]["content"]  # same user prompt as Opus
    rf = kw["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"] is _OPENAI_COMPOSE_OUTPUT_SCHEMA


def test_openai_client_tracks_token_usage_for_cost():
    fake = _FakeOpenAI(_FakeResponse(_payload([]), usage=_FakeUsage(111, 222)))
    client = OpenAIComposeClient(client=fake)
    client.compose(_request(), 1, None)
    assert client.input_tokens == 111
    assert client.output_tokens == 222


def test_openai_client_raises_on_truncation():
    fake = _FakeOpenAI(_FakeResponse(_payload([]), finish_reason="length"))
    with pytest.raises(ValueError, match="truncated"):
        OpenAIComposeClient(client=fake).compose(_request(), 1, None)


def test_openai_client_raises_on_empty_content():
    fake = _FakeOpenAI(_FakeResponse(None))
    with pytest.raises(ValueError, match="no content"):
        OpenAIComposeClient(client=fake).compose(_request(), 1, None)


def test_openai_strict_schema_requires_also_cites():
    """OpenAI strict structured output requires EVERY property in ``required`` — the
    Anthropic schema left ``also_cites`` optional, which OpenAI would reject."""
    items = _OPENAI_COMPOSE_OUTPUT_SCHEMA["properties"]["sentences"]["items"]
    assert "also_cites" in items["required"]
    assert items["additionalProperties"] is False
