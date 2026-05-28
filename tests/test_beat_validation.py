"""Tests for the dedup data hygiene foundation:

1. Pydantic NarrativeBeatCreate hash auto-compute and reject-mismatch.
2. CLI scripts/validate_beats.py hash + identity-tuple checks, including
   the legacy_unknown wildcard semantics.
3. BP-9 — validator is single-file-path scoped (city isolation).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.api.models.nodes import NarrativeBeatCreate, _normalized_script_body_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = REPO_ROOT / "scripts" / "validate_beats.py"
FIXTURE_PARIS = REPO_ROOT / "tests" / "fixtures" / "beats_multi_chunk.json"
FIXTURE_LONDON = REPO_ROOT / "tests" / "fixtures" / "beats_london_min.json"


def run_validator(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


# ── Pydantic field validation ──


def test_hash_auto_computed():
    """AC-4 — empty hash gets filled with SHA-256 of normalized body."""
    beat = NarrativeBeatCreate(script_body="Hello world")
    assert beat.script_body_hash == hashlib.sha256(b"hello world").hexdigest()


def test_hash_present_correct_accepted():
    """AC-4 — caller-provided hash that matches normalized body is accepted."""
    body = "Some Body Here"
    correct = _normalized_script_body_hash(body)
    beat = NarrativeBeatCreate(script_body=body, script_body_hash=correct)
    assert beat.script_body_hash == correct


def test_hash_present_wrong_rejected():
    """AC-4 — caller-provided hash that doesn't match body raises."""
    with pytest.raises(ValidationError):
        NarrativeBeatCreate(script_body="Foo", script_body_hash="bogus")


def test_normalized_hash_collapses_whitespace_and_case():
    """Whitespace runs collapse, case is folded."""
    a = _normalized_script_body_hash("  Hello   WORLD\n")
    b = _normalized_script_body_hash("hello world")
    assert a == b


# ── CLI validator: happy paths ──


def test_baseline_fixture_passes():
    """The hand-crafted multi-chunk fixture is valid as-shipped."""
    result = run_validator(FIXTURE_PARIS)
    assert result.returncode == 0, result.stdout + result.stderr


def test_validator_legacy_unknown_wildcard():
    """AC-12 — two beats with `legacy_unknown` book_slug at the same
    POI/lens do NOT trigger an identity collision (wildcard semantics)."""
    # The baseline fixture already has two `Pont Neuf / hidden_history /
    # legacy_unknown / legacy_unknown` beats with different bodies. They
    # must pass.
    result = run_validator(FIXTURE_PARIS)
    assert result.returncode == 0, result.stdout + result.stderr


# ── CLI validator: failure modes ──


def test_validator_hash_collision(tmp_path):
    """AC-5 — two beats sharing script_body_hash → exit 1."""
    beats = json.loads(FIXTURE_PARIS.read_text())
    # Make beat 4 carry beat 1's body + hash but a distinct identity
    # tuple (different lens) so we trigger ONLY hash collision.
    beats[3]["script_body"] = beats[0]["script_body"]
    beats[3]["script_body_hash"] = beats[0]["script_body_hash"]
    beats[3]["lens"] = "different_lens"
    target = tmp_path / "beats.json"
    target.write_text(json.dumps(beats))
    result = run_validator(target)
    assert result.returncode == 1
    assert "HASH_COLLISION" in result.stdout


def test_validator_identity_collision(tmp_path):
    """AC-3 — two beats sharing the full identity tuple → exit 1."""
    beats = json.loads(FIXTURE_PARIS.read_text())
    # Clone beat 1 with a different body (and recomputed hash) but same
    # identity tuple. Only identity should trip.
    duplicate = json.loads(json.dumps(beats[0]))
    duplicate["beat_id"] = duplicate["beat_id"] + "_dup"
    duplicate["script_body"] = "A different body that says nothing about Philippe-Auguste."
    normalized = re.sub(r"\s+", " ", duplicate["script_body"].lower().strip())
    duplicate["script_body_hash"] = hashlib.sha256(normalized.encode()).hexdigest()
    beats.append(duplicate)
    target = tmp_path / "beats.json"
    target.write_text(json.dumps(beats))
    result = run_validator(target)
    assert result.returncode == 1
    assert "IDENTITY_COLLISION" in result.stdout


def test_validator_missing_hash_flagged(tmp_path):
    """A beat with no script_body_hash field is flagged (HASH_MISSING)."""
    beats = json.loads(FIXTURE_PARIS.read_text())
    del beats[0]["script_body_hash"]
    target = tmp_path / "beats.json"
    target.write_text(json.dumps(beats))
    result = run_validator(target)
    assert result.returncode == 1
    assert "HASH_MISSING" in result.stdout


def test_validator_unreadable_file_returns_2(tmp_path):
    """Operator-error exit code 2 is distinct from data-integrity exit 1."""
    target = tmp_path / "does_not_exist.json"
    result = run_validator(target)
    assert result.returncode == 2


def test_validator_not_a_list_returns_2(tmp_path):
    target = tmp_path / "object.json"
    target.write_text(json.dumps({"not": "a list"}))
    result = run_validator(target)
    assert result.returncode == 2


# ── BP-9: city isolation ──


def test_validator_city_isolated(tmp_path):
    """BP-9 — sequentially validating Paris and London fixtures must leave
    each independent. Neither sees the other's data even though both files
    sit in the same fixtures directory."""
    # Run both back-to-back from a fresh subprocess so any module-level
    # cache pollution would surface.
    paris_copy = tmp_path / "paris.json"
    london_copy = tmp_path / "london.json"
    shutil.copy(FIXTURE_PARIS, paris_copy)
    shutil.copy(FIXTURE_LONDON, london_copy)
    paris_result = run_validator(paris_copy)
    london_result = run_validator(london_copy)
    assert paris_result.returncode == 0, paris_result.stdout + paris_result.stderr
    assert london_result.returncode == 0, london_result.stdout + london_result.stderr
    # And the order doesn't matter:
    london_first = run_validator(london_copy)
    paris_second = run_validator(paris_copy)
    assert london_first.returncode == 0
    assert paris_second.returncode == 0


# ── commit-time Wikipedia source-grounding gate ──


def _wiki_beat(chunk: str, source_passage: str) -> dict:
    return {
        "beat_id": "paris_test_poi_historic_arch_wikipedia_t",
        "city_name": "paris",
        "poi_name": "Test POI",
        "lens": "historic_arch",
        "book_slug": "wikipedia",
        "topic_slug": "t",
        "source_chunk_slug": chunk,
        "script_body_hash": "deadbeef",
        "source_passage": source_passage,
    }


def test_validator_wikipedia_grounded_passes(tmp_path):
    """A Wikipedia beat whose source_passage is in the pinned .txt passes."""
    chunk = "test_poi-rev-123"
    (tmp_path / "wikipedia").mkdir()
    text = "The arch was built in 1806. It stands at the Place du Carrousel near the Louvre."
    (tmp_path / "wikipedia" / f"{chunk}.txt").write_text(text)
    target = tmp_path / "beats.json"
    target.write_text(json.dumps([_wiki_beat(chunk, text)]))
    result = run_validator(target)
    assert result.returncode == 0, result.stdout + result.stderr


def test_validator_wikipedia_ungrounded_fails(tmp_path):
    """A source_passage absent from the pinned .txt is blocked at commit."""
    chunk = "test_poi-rev-123"
    (tmp_path / "wikipedia").mkdir()
    (tmp_path / "wikipedia" / f"{chunk}.txt").write_text(
        "The monument is built of marble. It stands in a public square."
    )
    passage = (
        "The arch is three times the size of its sibling. The statues were carved "
        "by Ramey and Cartellier. The horses came from Berlin."
    )
    target = tmp_path / "beats.json"
    target.write_text(json.dumps([_wiki_beat(chunk, passage)]))
    result = run_validator(target)
    assert result.returncode == 1
    assert "WIKIPEDIA_UNGROUNDED" in result.stdout


def test_validator_wikipedia_missing_source_fails(tmp_path):
    """A Wikipedia beat whose pinned .txt is absent cannot be committed."""
    target = tmp_path / "beats.json"
    target.write_text(json.dumps([_wiki_beat("absent-rev-9", "Some claim here that has words.")]))
    result = run_validator(target)
    assert result.returncode == 1
    assert "WIKIPEDIA_MISSING_SOURCE" in result.stdout
