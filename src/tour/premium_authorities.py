"""Packaged hashes for the frozen Premium authoring authorities.

The source documents remain reviewable under ``specs/``.  Runtime code imports
only these pins because production images deliberately exclude the specs tree.
``tests/test_premium_authorities.py`` prevents either copy from drifting.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PremiumAuthorityHashes:
    contract_sha256: str
    reference_manifest_sha256: str
    calibration_manifest_sha256: str


PREMIUM_AUTHORITIES = PremiumAuthorityHashes(
    contract_sha256="a7250bada7cb09ad9a47e159b9a89f6385046555dbd3e5d99ccf31d581f3a82d",
    reference_manifest_sha256="0baecbe2a8a8841958f51c908d4833a1850540589c1e91becdc1d597dfc28da1",
    calibration_manifest_sha256="d4548864786d11ec44a00c2bfd753cc9d42909bdda511c819f144efe1646f56a",
)


__all__ = ["PREMIUM_AUTHORITIES", "PremiumAuthorityHashes"]
