"""Guards the paid-provider shard and the definitive test executor."""

from __future__ import annotations

import ast
import runpy
import urllib.request
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]


def test_audio_functional_module_is_marked_live() -> None:
    """The real OpenAI TTS/Whisper suite must run only in the live shard.

    Regression case: the module documented itself as live but lacked a pytest
    marker. On any machine with ``OPENAI_API_KEY`` set, the hermetic local shard
    silently made paid calls. Parse the file instead of importing it because its
    collection-time reachability probe itself uses the network.
    """
    path = REPO / "tests" / "test_audio_functional.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    has_live_marker = any(
        isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets
        )
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "live"
        and isinstance(node.value.value, ast.Attribute)
        and node.value.value.attr == "mark"
        and isinstance(node.value.value.value, ast.Name)
        and node.value.value.value.id == "pytest"
        for node in tree.body
    )

    assert has_live_marker, (
        "tests/test_audio_functional.py makes real paid OpenAI calls and must set "
        "module-level `pytestmark = pytest.mark.live` so `make test` routes it "
        "through `test-live`"
    )


def test_audio_functional_collection_never_probes_the_network(
    monkeypatch,
) -> None:
    """A configured credential must not turn collection into a real API call."""
    path = REPO / "tests" / "test_audio_functional.py"
    monkeypatch.setenv("OPENAI_API_KEY", "canary-must-never-leave-the-process")

    def _forbidden(*_args, **_kwargs):
        raise AssertionError("network attempted while collecting paid tests")

    monkeypatch.setattr(urllib.request, "build_opener", _forbidden)
    monkeypatch.setattr(httpx, "get", _forbidden)
    runpy.run_path(str(path), run_name="__paid_collection_probe__")


def test_default_conftest_scrubs_paid_keys_before_importing_the_api() -> None:
    """Collection-time imports cannot reload real keys from root ``.env``."""
    source = (REPO / "tests" / "conftest.py").read_text(encoding="utf-8")
    scrub = source.index('os.environ[_paid_key] = ""')
    api_import = source.index("from src.api.app import create_app")

    assert scrub < api_import
    for key in (
        "ANTHROPIC_API_KEY",
        "ELEVENLABS_API_KEY",
        "OPENAI_API_KEY",
        "RESEND_API_KEY",
    ):
        assert f'"{key}"' in source[:api_import]


def test_makefile_live_targets_enable_live_collection() -> None:
    source = (REPO / "Makefile").read_text(encoding="utf-8")
    functional = source.split("test-functional:", 1)[1].split("\n\n", 1)[0]
    live = source.split("test-live:", 1)[1].split("\n\n", 1)[0]
    audio_gate = source.split("tour-audio-gate:", 1)[1].split("\n\n", 1)[0]
    compose_gate = source.split("tour-compose-gate:", 1)[1].split("\n\n", 1)[0]

    for target in (functional, live, audio_gate, compose_gate):
        assert "ONDOWAY_LIVE_TESTS=1" in target
        assert "-o addopts=" in target
        assert "-m live" in target
    assert "ONDOWAY_ENABLE_PAID_LLM_CALLS=1" in live
    assert "ONDOWAY_ENABLE_PAID_LLM_CALLS=1" in compose_gate


def test_make_test_is_the_only_exhaustive_executor() -> None:
    source = (REPO / "Makefile").read_text(encoding="utf-8")
    test_target = source.split("\ntest:", 1)[1].split("\n\naudit:", 1)[0]

    shards = (
        "test-local",
        "flutter-test",
        "test-workbench",
        "test-golden",
        "tour-grade",
        "tour-invariants",
        "test-live",
        "test-cloud",
    )
    for shard in shards:
        invocation = f"@$(MAKE) --no-print-directory {shard}"
        assert test_target.count(invocation) == 1
