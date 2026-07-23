"""The packaged runtime authority pins must equal their reviewable sources."""

from __future__ import annotations

import hashlib
from pathlib import Path

from src.tour.premium_authorities import PREMIUM_AUTHORITIES

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "specs" / "2026-07-21-tour-certification"


def _sha256(name: str) -> str:
    return hashlib.sha256((SPEC / name).read_bytes()).hexdigest()


def test_packaged_premium_authorities_match_reviewed_sources() -> None:
    assert PREMIUM_AUTHORITIES.contract_sha256 == _sha256("contract.json")
    assert PREMIUM_AUTHORITIES.reference_manifest_sha256 == _sha256(
        "investigation-reference-manifest.json"
    )
    assert PREMIUM_AUTHORITIES.calibration_manifest_sha256 == _sha256("calibration-manifest.json")
