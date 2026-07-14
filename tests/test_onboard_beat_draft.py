"""Unit tests for src/onboard/beat_draft.py (Step 4 of new-city onboarding).

Pure — no Neo4j, no network, $0. Run with:
    make test-file FILE=tests/test_onboard_beat_draft.py

The load-bearing guarantee is that a MOCK-drafted beat is byte-for-byte
acceptable to the same commit-time gate a real Wikipedia beat must pass
(``scripts/validate_beats.validate``): its ``source_passage`` is a VERBATIM
slice of the pinned revision text, so it grounds; its identity tuple and body
hash are unique per POI; and the paid provider cannot spend a cent without an
explicit ``confirm=True``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import validate_beats
from scripts.beat_builder import hash_body, slugify
from src.onboard.assemble import WikiExtract
from src.onboard.beat_draft import (
    AnthropicBeatDrafter,
    CostNotConfirmed,
    MockBeatDrafter,
    draft_all,
    estimate_cost,
)

# ---------------------------------------------------------------------------
# Fixtures — real multi-sentence Wikipedia-lead text (≥4 sentences each, so the
# grounding gate has ≥2 fragments and the paraphrase undo can actually trip it).
# ---------------------------------------------------------------------------


def _extracts() -> list[WikiExtract]:
    return [
        WikiExtract(
            poi_name="Brooklyn Bridge",
            revid="111",
            text=(
                "The Brooklyn Bridge is a hybrid cable-stayed suspension bridge in New "
                "York City, spanning the East River between the boroughs of Manhattan "
                "and Brooklyn. Opened on May 24, 1883, it was the first fixed crossing "
                "of the East River. It was also the longest suspension bridge in the "
                "world at the time of its opening, with a main span of 1,595.5 feet. "
                "The bridge was designed by John Augustus Roebling."
            ),
            article_title="Brooklyn Bridge",
            url="https://en.wikipedia.org/wiki/Brooklyn_Bridge?oldid=111",
        ),
        WikiExtract(
            poi_name="Central Park",
            revid="222",
            text=(
                "Central Park is an urban park in New York City located between the "
                "Upper West Side and Upper East Side of Manhattan. It is the fifth-largest "
                "park in the city, covering 843 acres. Central Park is the most visited "
                "urban park in the United States, with an estimated 42 million visitors "
                "annually. It is also one of the most filmed locations in the world."
            ),
            article_title="Central Park",
            url="https://en.wikipedia.org/wiki/Central_Park?oldid=222",
        ),
        WikiExtract(
            poi_name="Empire State Building",
            revid="333",
            text=(
                "The Empire State Building is a 102-story Art Deco skyscraper in the "
                "Midtown South neighborhood of Manhattan in New York City. The building "
                "was designed by Shreve, Lamb and Harmon and built from 1930 to 1931. "
                "Its name is derived from Empire State, the nickname of the state of New "
                "York. The building stood as the world's tallest for nearly 40 years."
            ),
            article_title="Empire State Building",
            url="https://en.wikipedia.org/wiki/Empire_State_Building?oldid=333",
        ),
    ]


def _pois() -> list[dict]:
    return [{"name": e.poi_name} for e in _extracts()]


def _by_slug(extracts: list[WikiExtract]) -> dict[str, WikiExtract]:
    return {slugify(e.poi_name): e for e in extracts}


def _write_corpus(root: Path, slug: str, extracts: list[WikiExtract], beats: list[dict]) -> Path:
    """Mirror ``assemble.write_city``'s on-disk layout for one city:
    ``data/{slug}/wikipedia/{poi_slug}-rev-{revid}.txt`` (verbatim pinned text)
    plus ``data/{slug}/beats.json``. Returns the beats.json path."""
    city_dir = root / "data" / slug
    wiki_dir = city_dir / "wikipedia"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    for ext in extracts:
        poi_slug = slugify(ext.poi_name)
        (wiki_dir / f"{poi_slug}-rev-{ext.revid}.txt").write_text(ext.text, encoding="utf-8")
    beats_path = city_dir / "beats.json"
    beats_path.write_text(json.dumps(beats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return beats_path


# ---------------------------------------------------------------------------
# 1. Mock beats pass validate_beats unchanged (grounding gate).
# ---------------------------------------------------------------------------


def test_mock_beats_pass_validate_beats(tmp_path: Path) -> None:
    extracts = _extracts()
    beats = draft_all(_pois(), _by_slug(extracts), drafter=MockBeatDrafter())
    assert len(beats) == len(extracts)
    beats_path = _write_corpus(tmp_path, "testville", extracts, beats)
    errors = validate_beats.validate(beats_path)
    assert errors == [], errors


def test_paraphrased_source_passage_fails_grounding(tmp_path: Path) -> None:
    """UNDO: a drafter that PARAPHRASES source_passage (not a verbatim slice of
    the pinned text) is a memory-reconstruction and must trip the Wikipedia
    grounding gate. (The gate fires only when ≥2 fragments are ungrounded, so a
    single-word edit cannot exercise it — the whole passage drifts, which is
    exactly the failure the gate exists to catch.)"""
    extracts = _extracts()
    beats = draft_all(_pois(), _by_slug(extracts), drafter=MockBeatDrafter(paraphrase=True))
    beats_path = _write_corpus(tmp_path, "testville", extracts, beats)
    errors = validate_beats.validate(beats_path)
    assert any("WIKIPEDIA_UNGROUNDED" in e for e in errors), errors


# ---------------------------------------------------------------------------
# 2. Identity tuple + body hash unique across POIs.
# ---------------------------------------------------------------------------


def test_identity_and_hash_unique_across_pois(tmp_path: Path) -> None:
    extracts = _extracts()
    beats = draft_all(_pois(), _by_slug(extracts), drafter=MockBeatDrafter())
    beats_path = _write_corpus(tmp_path, "testville", extracts, beats)
    errors = validate_beats.validate(beats_path)
    assert not [e for e in errors if "IDENTITY_COLLISION" in e or "HASH_COLLISION" in e], errors


def test_identity_check_catches_same_topic_slug(tmp_path: Path) -> None:
    """UNDO: a second beat for the SAME poi with a UNIQUE topic_slug is fine;
    forcing its topic_slug equal to another beat's collapses the identity tuple
    and validate must flag IDENTITY_COLLISION."""
    extracts = _extracts()
    beats = draft_all(_pois(), _by_slug(extracts), drafter=MockBeatDrafter())
    dup = dict(beats[0])
    dup["beat_id"] = beats[0]["beat_id"] + "_dup"
    dup["script_body"] = beats[0]["script_body"] + " A second establishing line."
    dup["script_body_hash"] = hash_body(dup["script_body"])  # keep hashes distinct
    dup["topic_slug"] = beats[0]["topic_slug"] + "_alt"  # UNIQUE topic → no collision

    ok_path = _write_corpus(tmp_path / "ok", "testville", extracts, [*beats, dup])
    ok_errors = validate_beats.validate(ok_path)
    assert not any("IDENTITY_COLLISION" in e for e in ok_errors), ok_errors

    dup["topic_slug"] = beats[0]["topic_slug"]  # same poi + same topic → collision
    bad_path = _write_corpus(tmp_path / "bad", "testville", extracts, [*beats, dup])
    bad_errors = validate_beats.validate(bad_path)
    assert any("IDENTITY_COLLISION" in e for e in bad_errors), bad_errors


# ---------------------------------------------------------------------------
# 3. Live (paid) provider cannot spend without confirm=True.
# ---------------------------------------------------------------------------


class _CountingMessages:
    """A stand-in for ``anthropic.Anthropic().messages`` that counts calls and
    never touches the network."""

    def __init__(self) -> None:
        self.calls = 0
        self.models: list[str] = []

    def create(self, *, model: str, **_kwargs: object) -> SimpleNamespace:
        self.calls += 1
        self.models.append(model)
        # Distinct per call, as a real model's per-POI narration would be — so the
        # emitted bodies don't hash-collide (script_body is not grounded; only
        # the mechanically-sliced source_passage is).
        return SimpleNamespace(content=[SimpleNamespace(text=f"Narration {self.calls}.")])


class _CountingClient:
    def __init__(self) -> None:
        self.messages = _CountingMessages()


def test_live_provider_without_confirm_makes_zero_calls() -> None:
    fake = _CountingClient()
    pois = _pois()
    drafter = AnthropicBeatDrafter(client=fake)
    with pytest.raises(CostNotConfirmed) as exc:
        draft_all(pois, _by_slug(_extracts()), confirm=False, drafter=drafter)
    assert fake.messages.calls == 0
    assert exc.value.estimate["beats"] == len(pois)
    assert exc.value.estimate["est_usd"] > 0


def test_live_provider_with_confirm_drafts_each_poi(tmp_path: Path) -> None:
    fake = _CountingClient()
    extracts = _extracts()
    pois = _pois()
    drafter = AnthropicBeatDrafter(client=fake)
    beats = draft_all(pois, _by_slug(extracts), confirm=True, drafter=drafter)
    assert fake.messages.calls == len(pois)
    assert fake.messages.models == ["claude-opus-4-8"] * len(pois)
    assert len(beats) == len(pois)
    # Even the paid path grounds source_passage in the pinned text (never memory).
    beats_path = _write_corpus(tmp_path, "testville", extracts, beats)
    assert validate_beats.validate(beats_path) == []


# ---------------------------------------------------------------------------
# 4. Cost estimate scales linearly and is positive.
# ---------------------------------------------------------------------------


def test_estimate_cost_scales_and_is_positive() -> None:
    one = estimate_cost(1)
    two = estimate_cost(2)
    assert one["model"] == "claude-opus-4-8"
    assert one["est_usd"] > 0
    assert one["est_input_tokens"] == 1200
    assert one["est_output_tokens"] == 350
    assert two["beats"] == 2
    assert two["est_usd"] == pytest.approx(2 * one["est_usd"], rel=0.01)
