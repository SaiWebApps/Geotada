"""Packaged hashes for the frozen Premium authoring authorities.

The source documents remain reviewable under ``specs/``.  Runtime code imports
only these pins because production images deliberately exclude the specs tree.
The packaged copy here is what runs; the specs copy is a document. (The test that
pinned the two together was retired 2026-08-18 with the other spec-artefact pins.)
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
    reference_manifest_sha256="dfb7cc205422473dad2e3c168c471aa5c4060c73c2cc450be0665ead6db98378",
    calibration_manifest_sha256="d4548864786d11ec44a00c2bfd753cc9d42909bdda511c819f144efe1646f56a",
)


__all__ = ["PREMIUM_AUTHORITIES", "PremiumAuthorityHashes"]
