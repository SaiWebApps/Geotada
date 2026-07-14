"""Step-4 DRAFT: turn each POI's pinned Wikipedia lead into one establishing beat.

Two drafters, one wall between free and paid:

- ``MockBeatDrafter`` is free and deterministic. It sets ``source_passage`` to a
  VERBATIM contiguous span of ``extract.text`` (a literal slice, never a
  paraphrase), so the emitted beat is a normalized substring of the pinned
  ``wikipedia/{poi_slug}-rev-{revid}.txt`` file ``write_city`` wrote from the
  SAME text — i.e. it passes ``scripts/validate_beats.validate`` unchanged.
- ``AnthropicBeatDrafter`` spends real API credits, so it can NEVER run without
  an explicit ``confirm=True``: ``draft_all`` raises ``CostNotConfirmed`` (which
  carries the dollar estimate) BEFORE any client is constructed or any call is
  made. Its ``source_passage`` is ALSO the mechanical verbatim slice — only the
  narration prose (``script_body``) comes from the model, and only from the
  pinned ``extract.text`` (never WebFetch/memory) — so a paid beat can no more be
  grounded in reconstructed memory than a mock one.

The emitted beat dict mirrors a real ``data/*/beats.json`` wikipedia beat and is
built from the FROZEN ``WikiExtract`` and the shared ``slugify`` / ``hash_body``
helpers in ``scripts/beat_builder.py`` (imported, never re-implemented). It
carries NO ``fact_check`` block: an absent status is allowed by validate, whereas
a "verified" status would (rightly) trip the verification-freshness gate.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime
from typing import Any

from scripts.beat_builder import hash_body, slugify
from src.onboard.assemble import WikiExtract

MODEL = "claude-opus-4-8"

# Provider selection. Default is the free, deterministic mock; "anthropic" opts
# into paid drafting (still gated behind confirm=True in draft_all).
ONBOARD_PROVIDER = os.getenv("ONBOARD_PROVIDER", "mock")

# Cost model for claude-opus-4-8: $5 / 1M input tokens, $25 / 1M output tokens.
_INPUT_TOKENS_PER_BEAT = 1200
_OUTPUT_TOKENS_PER_BEAT = 350
_INPUT_USD_PER_TOKEN = 5.0 / 1e6
_OUTPUT_USD_PER_TOKEN = 25.0 / 1e6

# Longest verbatim span we quote as source_passage; we always cut at a sentence
# boundary at/under this many characters so the passage stays a clean substring.
_MAX_PASSAGE_CHARS = 500

_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


# ---------------------------------------------------------------------------
# Verbatim-span helpers (shared by both drafters).
# ---------------------------------------------------------------------------
def _verbatim_span(text: str) -> str:
    """A contiguous, VERBATIM slice of ``text`` ending at a sentence boundary at
    or under ~500 chars — a literal substring of the pinned revision file, never
    a paraphrase, so it grounds against ``wikipedia/{slug}-rev-{revid}.txt``."""
    text = text.strip()
    if len(text) <= _MAX_PASSAGE_CHARS:
        return text
    window = text[:_MAX_PASSAGE_CHARS]
    cut = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if cut == -1:
        cut = window.rfind(" ")  # no sentence end — fall back to a word boundary
    if cut == -1:
        return window
    return text[: cut + 1].strip()


def _paraphrase(span: str) -> str:
    """Simulate a drafter that RECONSTRUCTS from memory instead of quoting: a
    fabricated lead-in on every sentence so the passage is no longer a verbatim
    substring of the pinned file. Used only by the mock's paraphrase mode (the
    undo test); the grounding gate needs ≥2 ungrounded fragments to fire, so a
    single-word edit could not exercise it — the whole passage must drift."""
    parts = [p for p in _SENTENCE_END_RE.split(span.strip()) if p]
    return " ".join(f"Reportedly, {p}" for p in parts)


def _lead_line(poi_name: str, span: str) -> str:
    """A short, non-empty lead derived from the span. Includes ``poi_name`` so
    the body hash is unique across POIs even if two share an opening sentence."""
    first = span.split(". ")[0].strip().rstrip(".")
    return f"{poi_name}: {first}."


def _build_beat(poi_name: str, extract: WikiExtract, script_body: str, source_passage: str) -> dict:
    """Assemble one establishing wikipedia beat matching a real ``beats.json``
    row and accepted unchanged by ``scripts/validate_beats.validate``.

    Keyed off the POI: ``topic_slug`` (and thus the identity tuple) and
    ``script_body_hash`` are unique per distinct POI. ``book_slug="wikipedia"``
    arms the grounding gate; ``source_chunk_slug`` is the pinned filename stem
    ``write_city`` produces. No ``fact_check`` block (absent status is allowed)."""
    poi_slug = slugify(poi_name)
    body = script_body.strip()
    return {
        "beat_id": f"{poi_slug}_wikipedia_lead",
        "poi_name": poi_name,
        "parent_poi": None,
        "lens": "history",
        "topic_slug": f"{poi_slug}_lead",
        "book_slug": "wikipedia",
        "source_chunk_slug": f"{poi_slug}-rev-{extract.revid}",
        "script_body": body,
        "script_body_hash": hash_body(body),
        "beat_length_class": "mid",
        "duration_sec": 30,
        "kid_friendly": "yes",
        "entities": [],
        "physical_cues": [],
        "inline_foreign_phrases": [],
        "key_claims": [],
        "sensory_anchor": False,
        "narrative_function": "establishing",
        "beat_type": "establishing",
        "emotional_register": "neutral",
        "source_passage": source_passage.strip(),
        "source_attribution": {
            "source_type": "wikipedia",
            "book_title": "Wikipedia",
            "article_title": extract.article_title,
            "url": extract.url,
            "revision_id": extract.revid,
            "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "section": "Lead",
        },
    }


# ---------------------------------------------------------------------------
# Drafters.
# ---------------------------------------------------------------------------
class MockBeatDrafter:
    """Free, deterministic drafter. ``source_passage`` is a verbatim slice of the
    pinned text; ``script_body`` is a short lead derived from it. With
    ``paraphrase=True`` it instead emits a memory-style paraphrase (used only to
    prove the grounding gate bites)."""

    def __init__(self, *, paraphrase: bool = False) -> None:
        self._paraphrase = paraphrase

    def draft(self, poi_name: str, extract: WikiExtract) -> dict:
        span = _verbatim_span(extract.text)
        source_passage = _paraphrase(span) if self._paraphrase else span
        return _build_beat(poi_name, extract, _lead_line(poi_name, span), source_passage)


class AnthropicBeatDrafter:
    """Paid drafter. The model writes only ``script_body`` and only from the
    pinned ``extract.text``; ``source_passage`` remains the mechanical verbatim
    slice, so a paid beat cannot be grounded in reconstructed memory. The client
    is constructed lazily so ``draft_all(confirm=False)`` never builds one."""

    def __init__(self, *, client: Any = None) -> None:
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            import anthropic  # imported lazily — never at draft_all's confirm gate

            self._client = anthropic.Anthropic()
        return self._client

    def draft(self, poi_name: str, extract: WikiExtract) -> dict:
        span = _verbatim_span(extract.text)
        message = self._get_client().messages.create(
            model=MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": _draft_prompt(poi_name, span)}],
        )
        script_body = _response_text(message) or _lead_line(poi_name, span)
        return _build_beat(poi_name, extract, script_body, span)


def _draft_prompt(poi_name: str, source_span: str) -> str:
    return (
        "Write a single short establishing narration line for an audio walking "
        f"tour stop at {poi_name}. Use ONLY the facts in the source text below; "
        "do not add anything from memory.\n\nSOURCE:\n" + source_span
    )


def _response_text(message: Any) -> str:
    blocks = getattr(message, "content", None) or []
    return " ".join(getattr(b, "text", "") for b in blocks if getattr(b, "text", "")).strip()


def get_drafter() -> MockBeatDrafter | AnthropicBeatDrafter:
    """The configured drafter. Default (and any non-"anthropic" value) is the
    free mock; "anthropic" selects the paid drafter."""
    if os.getenv("ONBOARD_PROVIDER", ONBOARD_PROVIDER) == "anthropic":
        return AnthropicBeatDrafter()
    return MockBeatDrafter()


# ---------------------------------------------------------------------------
# Cost estimate + confirmation gate.
# ---------------------------------------------------------------------------
def estimate_cost(n: int) -> dict:
    """Dollar estimate for drafting ``n`` beats on claude-opus-4-8, assuming
    ~1200 input + ~350 output tokens per beat."""
    est_usd = n * (
        _INPUT_TOKENS_PER_BEAT * _INPUT_USD_PER_TOKEN
        + _OUTPUT_TOKENS_PER_BEAT * _OUTPUT_USD_PER_TOKEN
    )
    return {
        "model": MODEL,
        "beats": n,
        "est_input_tokens": n * _INPUT_TOKENS_PER_BEAT,
        "est_output_tokens": n * _OUTPUT_TOKENS_PER_BEAT,
        "est_usd": round(est_usd, 4),
    }


class CostNotConfirmed(Exception):  # noqa: N818 — public name is the caller/test contract
    """Raised when a paid (anthropic) draft run is requested without
    ``confirm=True``. Carries the cost ``estimate`` so the caller can show it and
    re-invoke with ``confirm=True``."""

    def __init__(self, estimate: dict) -> None:
        self.estimate = estimate
        super().__init__(
            f"anthropic beat drafting for {estimate['beats']} beat(s) would cost "
            f"~${estimate['est_usd']} — pass confirm=True to proceed."
        )


def draft_all(
    pois: list[dict],
    extracts_by_slug: dict[str, WikiExtract],
    *,
    confirm: bool = False,
    drafter: MockBeatDrafter | AnthropicBeatDrafter | None = None,
) -> list[dict]:
    """Draft one establishing beat per POI that has a matching extract (by
    ``slugify(poi_name)``). The mock is free; a paid ``AnthropicBeatDrafter``
    with ``confirm=False`` raises ``CostNotConfirmed`` BEFORE any client is built
    or any call is made."""
    drafter = drafter or get_drafter()
    if isinstance(drafter, AnthropicBeatDrafter) and not confirm:
        raise CostNotConfirmed(estimate_cost(len(pois)))
    beats: list[dict] = []
    for poi in pois:
        extract = extracts_by_slug.get(slugify(poi["name"]))
        if extract is None:
            continue
        beats.append(drafter.draft(poi["name"], extract))
    return beats
