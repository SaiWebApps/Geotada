"""Grey-zone hard-boundary tests (walls 1, 2, 5).

These lock the STRUCTURAL guarantees that keep shadow-library (Anna's Archive /
WeLib) copyrighted text out of the pipeline:

- Wall 2 (network): src/onboard/fetch.py's allowlist rejects every non
  license-clean host, including lookalikes.
- Wall 1 (type):   DiscoveryPointer has no text field and forbids extras.
- Wall 5 (repo):   no committed data/*/beats.json attribution references a
  shadow-library domain.

Pure — no Neo4j, no network. Run with:
    make test-file FILE=tests/test_onboard_boundary.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.onboard.fetch import (
    INGEST_DOMAIN_ALLOWLIST,
    IngestDomainError,
    assert_ingestable,
    is_ingest_host_allowed,
)
from src.onboard.models import DiscoveryPointer

# ---------------------------------------------------------------------------
# Wall 2 — network allowlist
# ---------------------------------------------------------------------------

BLOCKED_URLS = [
    "https://annas-archive.org/md5/abc123",
    "https://welib.org/book/42",
    "https://welib.se/read/99",
    "http://libgen.is/index.php?req=paris",
    "https://example.com/x",
    # Lookalike: a shadow host that merely SUFFIXES an allowed brand must fail.
    "https://wikipedia.org.evil.com/paris",
]

ALLOWED_URLS = [
    "https://en.wikipedia.org/wiki/Paris",
    "https://en.wikivoyage.org/wiki/Paris",
    "https://query.wikidata.org/sparql?query=SELECT",
    "https://overpass-api.de/api/interpreter",
    "https://www.gutenberg.org/ebooks/1",
    "https://archive.org/advancedsearch.php",
    "https://gutendex.com/books",
]


@pytest.mark.parametrize("url", BLOCKED_URLS)
def test_assert_ingestable_rejects_non_allowlisted(url: str) -> None:
    assert is_ingest_host_allowed(url) is False
    with pytest.raises(IngestDomainError):
        assert_ingestable(url)


@pytest.mark.parametrize("url", ALLOWED_URLS)
def test_assert_ingestable_allows_license_clean(url: str) -> None:
    assert is_ingest_host_allowed(url) is True
    assert_ingestable(url)  # must NOT raise


def test_lookalike_suffix_is_rejected() -> None:
    """Two distinct lookalike shapes must both be rejected — one genuinely
    discriminates between the naive and the correct impl:

    - ``notwikipedia.org`` ends with the bare brand ``wikipedia.org``, so a naive
      ``host.endswith(d)`` would WRONGLY allow it; the dotted-suffix rule
      (``host == d or host.endswith("." + d)``) correctly rejects it. This case
      is RED under the naive bug and GREEN under the fix — it is the real test.
    - ``wikipedia.org.evil.com`` is a different registrable domain that only
      prefixes the brand; it is rejected under BOTH impls (``endswith(d)`` is
      False), so it does not discriminate — kept as an extra guard."""
    # The discriminator: naive endswith(d) allows it, dotted-suffix rejects it.
    assert is_ingest_host_allowed("https://notwikipedia.org/x") is False
    with pytest.raises(IngestDomainError):
        assert_ingestable("https://notwikipedia.org/x")
    # Non-discriminating guard: a different-registrable-domain lookalike.
    assert is_ingest_host_allowed("https://wikipedia.org.evil.com/x") is False
    with pytest.raises(IngestDomainError):
        assert_ingestable("https://wikipedia.org.evil.com/x")


def test_shadow_domains_are_not_on_the_allowlist() -> None:
    for shadow in ("annas-archive.org", "welib.org", "welib.se", "libgen.is"):
        assert shadow not in INGEST_DOMAIN_ALLOWLIST


def test_missing_host_is_rejected() -> None:
    assert is_ingest_host_allowed("not-a-url") is False
    assert is_ingest_host_allowed("") is False


def test_allowlisted_host_with_port_is_allowed() -> None:
    assert is_ingest_host_allowed("https://en.wikipedia.org:443/wiki/Paris") is True


# ---------------------------------------------------------------------------
# Wall 1 — DiscoveryPointer is metadata-only (no text field, extras forbidden)
# ---------------------------------------------------------------------------

TEXT_BEARING_FIELDS = ["text", "content", "body", "full_text"]


@pytest.mark.parametrize("field", TEXT_BEARING_FIELDS)
def test_discovery_pointer_has_no_text_field(field: str) -> None:
    assert field not in DiscoveryPointer.model_fields


@pytest.mark.parametrize("field", TEXT_BEARING_FIELDS)
def test_discovery_pointer_rejects_text_via_kwargs(field: str) -> None:
    with pytest.raises(ValidationError):
        DiscoveryPointer(
            source="annas_archive",
            title="Some Book",
            source_url="https://annas-archive.org/md5/abc",
            **{field: "copyrighted body text"},
        )


def test_discovery_pointer_valid_metadata_constructs() -> None:
    p = DiscoveryPointer(
        source="annas_archive",
        title="Around and About London",
        author="Someone",
        year=1901,
        format="epub",
        source_url="https://annas-archive.org/md5/abc",
    )
    assert p.title == "Around and About London"
    # Sanity: the instance genuinely has no text-bearing attribute.
    for field in TEXT_BEARING_FIELDS:
        assert not hasattr(p, field)


# ---------------------------------------------------------------------------
# Wall 5 — no committed beats.json attribution references a shadow library
# ---------------------------------------------------------------------------

# Shadow-library brand tokens. Matched only as word-bounded / domain-ish tokens
# (\b on both sides), NOT as bare substrings: `welib` matches `welib.se` and
# `www.welib.com` but NOT the `welib` inside `jewelibrary` (there the leading `w`
# is preceded by a word char, so there is no boundary and no match). This keeps
# the all-leaves scan from false-positiving on ordinary long narration text.
_SHADOW_BRANDS = ("annas-archive", "libgen", "z-lib", "zlibrary", "welib")
_SHADOW_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(b) for b in _SHADOW_BRANDS) + r")\b",
    re.IGNORECASE,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _shadow_hits_in_beat(beat: dict) -> list[str]:
    """Every string leaf anywhere in `beat` (ALL keys, ALL nesting) that
    references a shadow-library brand as a word-bounded / domain-ish token.

    Walking every leaf — not a hand-picked subset of attribution keys — is what
    makes the scan non-evadable: a shadow ref hidden under `source_passage`,
    `_meta`, `fact_check`, `provenance_note`, or any other key is still caught."""
    hits: list[str] = []

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, str) and _SHADOW_RE.search(obj):
            hits.append(obj)

    walk(beat)
    return hits


def test_scan_catches_shadow_ref_in_any_key() -> None:
    """A shadow ref hidden under ANY real key (not just source_url/*url*) must be
    caught: the scan walks every string leaf, so it is not evadable by relocating
    the ref to an unexpected key."""
    beat = {
        "beat_id": "b1",
        "source_chunk_slug": "libgen-md5-abc",
        "source_passage": "see annas-archive.org for the scan",
        "_meta": {"ingest_source": "welib.se"},
        "fact_check": {"notes": "cross-checked against a libgen scan"},
        "provenance_note": "acquired via annas-archive",
    }
    hits = _shadow_hits_in_beat(beat)
    assert len(hits) == 5, hits
    joined = " ".join(hits).lower()
    for token in ("libgen-md5-abc", "annas-archive.org", "welib.se"):
        assert token in joined


def test_scan_does_not_false_positive_on_ordinary_words() -> None:
    """Ordinary words that merely CONTAIN a brand as a substring (e.g.
    'jewelibrary') must NOT be flagged — the match is word-bounded / domain-ish."""
    beat = {
        "beat_id": "b2",
        "title": "a jewelibrary in Paris",
        "body": "the public library",
        "note": "calibrate the genre",
    }
    assert _shadow_hits_in_beat(beat) == []


def _beats_files() -> list[Path]:
    return sorted((_REPO_ROOT / "data").glob("*/beats.json"))


def test_beats_files_exist() -> None:
    # Guards against a silently-empty scan (glob matching nothing → vacuous pass).
    assert _beats_files(), "no data/*/beats.json found — scan would be vacuous"


@pytest.mark.parametrize("beats_path", _beats_files(), ids=lambda p: p.parent.name)
def test_no_beat_attribution_references_shadow_library(beats_path: Path) -> None:
    beats = json.loads(beats_path.read_text())
    offenders: list[str] = []
    for beat in beats:
        for value in _shadow_hits_in_beat(beat):
            offenders.append(f"{beat.get('beat_id', '?')}: {value!r}")
    assert not offenders, (
        f"{beats_path} has beats attributing a shadow-library source: {offenders[:5]}"
    )
