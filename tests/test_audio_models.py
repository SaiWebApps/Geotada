"""Unit tests for audio Pydantic models — validation constraints.

Tests that Field(min_length, max_length) constraints on audio request
models are enforced correctly.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

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


def _declared_tts_registry() -> dict[str, str]:
    """The provider registry ``src/audio/provider.py`` DECLARES, read from source.

    Structural and name-free, mirroring ``_declared_audio_registry`` in
    ``tests/test_workbench_ui.py``: find the module-level dict literal whose keys
    are string constants and whose values are classes defined in that same
    module. Read from SOURCE rather than imported, because ``tests/conftest.py``
    calls ``register_provider("mock", ...)`` at import time — so the in-process
    registry of a pytest interpreter is deliberately NOT the set a server
    serves, and it is the server's set these defaults must satisfy.
    """
    import ast
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "src" / "audio" / "provider.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    found: dict[str, str] = {}
    for node in tree.body:
        if not (
            (isinstance(node, ast.AnnAssign) and node.value is not None)
            or isinstance(node, ast.Assign)
        ):
            continue
        value = node.value
        if not isinstance(value, ast.Dict) or not value.keys:
            continue
        if not all(isinstance(k, ast.Constant) and isinstance(k.value, str) for k in value.keys):
            continue
        if not all(isinstance(v, ast.Name) and v.id in classes for v in value.values):
            continue
        found.update({k.value: v.id for k, v in zip(value.keys, value.values, strict=True)})
    assert found, (
        "found no name->class registry in src/audio/provider.py; this derivation "
        "is broken, so comparing model defaults against it would prove nothing"
    )
    return found


def test_no_request_model_defaults_to_an_unserved_provider() -> None:
    """No API request model may name a provider the server cannot serve.

    A default is the contract a client gets when it omits the field. Four models
    here defaulted to ``"mock"`` — a provider deliberately absent from
    ``_PROVIDERS``, so any body omitting ``provider`` asked the server for an
    implementation it refuses to resolve (400), and before the fake was
    deregistered it asked for a silent WAV instead.

    The mobile app escapes this only by accident: it sends a NULL body when both
    provider and voice_id are omitted, so the field never materialises. The
    moment it sends ``{"voice_id": ...}`` it inherits the default.

    ``None`` is the correct default — ``get_provider(None)`` falls through to the
    ``TTS_PROVIDER`` pin (``render.yaml`` in production, ``scripts/workbench.sh``
    locally, ``tests/conftest.py`` in the bar).

    UNDO TEST: set any of these back to ``provider: str = "mock"`` -> RED.
    """
    import src.api.models.audio as audio_models

    served = _declared_tts_registry()
    checked: dict[str, object] = {}
    for name in dir(audio_models):
        obj = getattr(audio_models, name)
        if not (isinstance(obj, type) and issubclass(obj, BaseModel)):
            continue
        field = obj.model_fields.get("provider")
        if field is None or field.is_required():
            continue
        checked[f"{obj.__name__}.provider"] = field.default

    # Non-vacuity: if the walk found nothing, the assertion below is empty.
    assert checked, (
        "found no request model with a defaulted 'provider' field, so this "
        "guard would pass no matter what src/api/models/audio.py declares"
    )

    offenders = {
        where: default
        for where, default in checked.items()
        if default is not None and default not in served
    }
    assert not offenders, (
        f"these API request models default 'provider' to something the server "
        f"does not serve: {offenders}. The server serves {sorted(served)}. A "
        f"default is what a client gets when it omits the field, so naming a "
        f"fake here makes the fake the published contract."
    )
