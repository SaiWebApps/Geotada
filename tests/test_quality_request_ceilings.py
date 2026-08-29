"""The review envelopes' output ceilings — per-model and per-candidate-count.

The judge's pre-commit consult (2026-08-29) named the unguarded failure mode this
file closes: nothing pinned the ceilings, so reverting the `_output_ceiling`
wiring would ship the two-candidate blind review against the flat 16K ceiling —
recreating the measured paid truncation (Sonnet 5 burned the full 16K and stopped
at `max_tokens` on the exact calibration request Opus finished in 6,363 output
tokens; under zero retries that spend is paid-and-lost). Hermetic: envelopes are
built, never sent.
"""

from __future__ import annotations

from src.tour.quality_requests import (
    ENJOY_MAX_OUTPUT_TOKENS,
    _output_ceiling,
    calibration_request_envelope,
)


def test_dense_output_models_get_double_the_ceiling() -> None:
    """Sonnet 5 tokenizes ~30% denser and its adaptive thinking spends against the
    same max_tokens, measured 2026-08-28 as a mid-JSON truncation at the flat
    ceiling. UNDO: return ``base`` unconditionally -> RED."""
    assert _output_ceiling("claude-opus-4-8", 16_000) == 16_000
    assert _output_ceiling("claude-sonnet-5", 16_000) == 32_000
    assert _output_ceiling("claude-sonnet-5", 64_000) == 128_000


def test_calibration_envelope_carries_the_per_model_ceiling() -> None:
    """The sealed request itself must carry the right ceiling — the constant alone
    proves nothing if the envelope builder stops calling it. The Opus envelope
    stays byte-stable at 16K (a paid calibration receipt reseeds only against an
    identical envelope); Sonnet's doubles. UNDO: hardcode
    ``max_tokens=ENJOY_MAX_OUTPUT_TOKENS`` in ``calibration_request_envelope``
    -> the Sonnet half goes RED."""
    _, opus = calibration_request_envelope((), (), model="claude-opus-4-8")
    _, sonnet = calibration_request_envelope((), (), model="claude-sonnet-5")
    assert opus["max_tokens"] == ENJOY_MAX_OUTPUT_TOKENS == 16_000
    assert sonnet["max_tokens"] == 32_000
