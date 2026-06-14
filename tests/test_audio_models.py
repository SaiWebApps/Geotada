"""Unit tests for audio Pydantic models — validation constraints.

Tests that Field(min_length, max_length) constraints on audio request
models are enforced correctly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.api.models.audio import (
    AudioPreviewRequest,
    CompareRequest,
    EvalRequest,
)


class TestAudioPreviewRequestValidation:
    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            AudioPreviewRequest(text="")

    def test_max_length_exceeded(self):
        # Cap raised to 20000 (long per-stop narration is chunked by the provider).
        with pytest.raises(ValidationError):
            AudioPreviewRequest(text="x" * 20001)

    def test_valid_text_accepted(self):
        req = AudioPreviewRequest(text="Hello world")
        assert req.text == "Hello world"

    def test_max_length_boundary_accepted(self):
        req = AudioPreviewRequest(text="x" * 20000)
        assert len(req.text) == 20000

    def test_single_char_accepted(self):
        req = AudioPreviewRequest(text="A")
        assert req.text == "A"


class TestCompareRequestValidation:
    def test_empty_providers_rejected(self):
        with pytest.raises(ValidationError):
            CompareRequest(text="Hello", providers=[])

    def test_too_many_providers_rejected(self):
        with pytest.raises(ValidationError):
            CompareRequest(text="Hello", providers=["a", "b", "c", "d", "e", "f"])

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            CompareRequest(text="", providers=["mock"])

    def test_valid_request_accepted(self):
        req = CompareRequest(text="Hello", providers=["mock"])
        assert req.text == "Hello"
        assert req.providers == ["mock"]

    def test_max_providers_boundary_accepted(self):
        req = CompareRequest(text="Hello", providers=["a", "b", "c", "d", "e"])
        assert len(req.providers) == 5


class TestEvalRequestValidation:
    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            EvalRequest(text="")

    def test_max_length_exceeded(self):
        with pytest.raises(ValidationError):
            EvalRequest(text="x" * 5001)

    def test_valid_request_accepted(self):
        req = EvalRequest(text="Hello world", provider="mock")
        assert req.text == "Hello world"
        assert req.provider == "mock"
