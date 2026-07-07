"""Regression tests for upload_hidden_gardens idempotency.

Defect (2026-07-06): the API now keys NarrativeBeat on its own `id` (not on
script_body), and there is no uniqueness constraint on beat_id or script_body.
A naive re-POST of identical narration therefore silently creates a SECOND
NarrativeBeat node with the same script_body plus a duplicate
POI-[:HAS_BEAT]->beat edge, so the tour engine sees duplicate beats. The
script's docstring falsely claimed idempotency via a server-side MERGE on
script_body that no longer exists.

The fix makes the script idempotent client-side: it pre-fetches every existing
beat, indexes them by the API's canonical normalized-script_body hash, and
REUSES the existing beat id (skipping the POST) when the same narration is
already present. These tests exercise the pure resolve/index helpers so they
run without a live DB or API.
"""

from __future__ import annotations

from scripts.upload_hidden_gardens import _resolve_beat_id
from src.api.models.nodes import _normalized_script_body_hash


def _make_recorder():
    """Return (post_fn, calls) where post_fn assigns a fresh id per call."""
    calls: list[dict] = []

    def post_fn(payload: dict) -> dict:
        calls.append(payload)
        return {"id": f"new-beat-{len(calls)}"}

    return post_fn, calls


def test_rerun_reuses_existing_beat_and_skips_post():
    """RED without the fix: an identical-narration beat already in the DB must
    be reused (no POST), not duplicated.

    Pre-fix behaviour POSTed unconditionally, creating a second node for the
    same script_body — the exact duplication the defect describes.
    """
    body = "The garden was planted in 1612 behind the old wall."
    existing = {_normalized_script_body_hash(body): "existing-beat-id"}
    post_fn, calls = _make_recorder()

    beat_id, created = _resolve_beat_id(existing, {"script_body": body}, post_fn)

    assert beat_id == "existing-beat-id"
    assert created is False
    assert calls == [], "must not POST a beat that already exists in the DB"


def test_normalization_dedups_whitespace_and_case_variants():
    """A body that differs only by casing/whitespace hashes to the same key,
    so it dedups onto the existing beat exactly as the API's MERGE-on-id path
    would if it recomputed the same canonical hash."""
    canonical = "A Fact.  Another   fact."
    variant = "  a fact. another fact.  "
    existing = {_normalized_script_body_hash(canonical): "existing-beat-id"}
    post_fn, calls = _make_recorder()

    beat_id, created = _resolve_beat_id(existing, {"script_body": variant}, post_fn)

    assert beat_id == "existing-beat-id"
    assert created is False
    assert calls == []


def test_new_beat_is_posted_once_and_indexed():
    """A genuinely new beat is POSTed exactly once and recorded in the index so
    a later identical beat in the SAME run also dedups (no second POST)."""
    body = "A brand new beat never seen before."
    index: dict[str, str] = {}
    post_fn, calls = _make_recorder()

    first_id, first_created = _resolve_beat_id(index, {"script_body": body}, post_fn)
    assert first_created is True
    assert first_id == "new-beat-1"
    assert len(calls) == 1

    # Same narration again within one run must reuse, not re-POST.
    second_id, second_created = _resolve_beat_id(index, {"script_body": body}, post_fn)
    assert second_created is False
    assert second_id == "new-beat-1"
    assert len(calls) == 1, "identical body within the run must not POST twice"
