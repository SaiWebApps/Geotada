"""The workbench preview must send what it means and reject what it cannot honour.

THREE MEASURED DEFECTS (2026-07-19), all of which made "tour preview" look broken
to a human pressing the button:

1. ``city_slug`` was never sent by ``generateTourPreview`` (``frontend/review.html``),
   so ``TripPreviewRequest``'s default of "paris" applied to EVERY preview. A
   London or New York workbench session previewed the PARIS corpus from a
   London/NY start, found nothing reachable, and 422'd.

2. An unknown lens string was silently ignored. ``_lens_relation``
   (``selection.py:2451-2477``) classifies every POI as a "miss" for an
   unrecognised lens, so ``lens_relevance`` returns the uniform ``LENS_FLOOR``
   (0.25). A uniform MULTIPLICATIVE factor leaves relative ranking identical to
   passing no lens, so a typo produced the un-lensed tour with no signal at all.

3. The lens input offered its vocabulary only as a ``placeholder`` — which is not
   a value — so the default request sent NO lenses.

These tests are cheap, hermetic and $0.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from pydantic import ValidationError

from src.api.models.trips import TripPreviewRequest
from src.schema.definitions import TAGGABLE_LENSES

REPO = pathlib.Path(__file__).resolve().parents[1]
REVIEW_HTML = REPO / "frontend" / "review.html"


# --------------------------------------------------------------------------
# 1. city_slug is actually sent
# --------------------------------------------------------------------------


def test_preview_fetch_sends_city_slug() -> None:
    """UNDO TEST: delete the ``city_slug:`` line from the preview fetch body and
    this goes RED. Without it every city previews Paris."""
    html = REVIEW_HTML.read_text()
    body = re.search(
        r"fetch\(`\$\{API_BASE\}/trips/preview`.*?\}\),", html, re.S
    )
    assert body, "could not locate the /trips/preview fetch call in review.html"
    assert "city_slug:" in body.group(0), (
        "generateTourPreview does not send city_slug — every preview silently "
        "falls back to TripPreviewRequest's 'paris' default, so a London/NY "
        "workbench session previews the wrong corpus and 422s."
    )


def test_preview_city_slug_uses_the_canonical_city_variable() -> None:
    """It must send the same key the rest of the page uses, not a fresh guess."""
    html = REVIEW_HTML.read_text()
    body = re.search(r"fetch\(`\$\{API_BASE\}/trips/preview`.*?\}\),", html, re.S)
    assert body and re.search(r"city_slug:\s*cityName", body.group(0)), (
        "city_slug must come from cityName, the canonical key every other "
        "workbench fetch already sends."
    )


# --------------------------------------------------------------------------
# 2. unknown lenses are rejected loudly
# --------------------------------------------------------------------------


def _req(**kw: object) -> TripPreviewRequest:
    base = {"center_lat": 48.8546, "center_lng": 2.3477}
    base.update(kw)
    return TripPreviewRequest(**base)  # type: ignore[arg-type]


def test_every_taggable_lens_is_accepted() -> None:
    for lens in TAGGABLE_LENSES:
        assert _req(lenses=[lens]).lenses == [lens]


def test_unknown_lens_is_rejected_not_silently_ignored() -> None:
    """UNDO TEST: remove ``validate_lenses`` and this goes RED.

    Before the validator this request was ACCEPTED and produced the un-lensed
    tour — the exact silent failure being guarded against.
    """
    with pytest.raises(ValidationError) as exc:
        _req(lenses=["dark_histry"])  # a plausible typo
    assert "Unknown lens" in str(exc.value)


def test_rejection_names_the_valid_vocabulary() -> None:
    """An error a human can act on names what they should have typed."""
    with pytest.raises(ValidationError) as exc:
        _req(lenses=["not_a_lens"])
    msg = str(exc.value)
    assert "dark_history" in msg and "historic_arch" in msg


def test_one_bad_lens_among_good_ones_still_rejects() -> None:
    with pytest.raises(ValidationError):
        _req(lenses=["dark_history", "totally_made_up"])


def test_blank_and_none_lenses_remain_permissive() -> None:
    """An absent lens is a legitimate request (the un-lensed tour), unchanged."""
    assert _req(lenses=None).lenses is None
    assert _req(lenses=[]).lenses is None
    assert _req(lenses=["  ", ""]).lenses is None
    assert _req(lenses=["  dark_history  "]).lenses == ["dark_history"]


# --------------------------------------------------------------------------
# 3. the UI offers the real vocabulary
# --------------------------------------------------------------------------


def test_lens_datalist_matches_the_canonical_vocabulary_exactly() -> None:
    """The picker must not drift from TAGGABLE_LENSES in either direction.

    An option the server rejects is a trap; a valid lens missing from the list is
    invisible to the editor.
    """
    html = REVIEW_HTML.read_text()
    block = re.search(r'<datalist id="tourLensOptions">(.*?)</datalist>', html, re.S)
    assert block, "the lens datalist is missing from review.html"
    offered = set(re.findall(r'value="([^"]+)"', block.group(1)))
    canonical = set(TAGGABLE_LENSES)
    assert offered == canonical, (
        f"lens picker drifted from TAGGABLE_LENSES. "
        f"offered-but-invalid={sorted(offered - canonical)}, "
        f"valid-but-missing={sorted(canonical - offered)}"
    )


def test_lens_input_is_wired_to_the_datalist() -> None:
    html = REVIEW_HTML.read_text()
    tag = re.search(r'<input[^>]*id="tourLenses"[^>]*>', html)
    assert tag, "the #tourLenses input is missing"
    assert 'list="tourLensOptions"' in tag.group(0), (
        "#tourLenses is not bound to the datalist, so the vocabulary stays "
        "invisible and typos stay easy."
    )
