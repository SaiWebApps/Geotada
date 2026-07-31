"""No test double may reach a surface a human looks at.

The workbench and the mobile app are both production-facing. The standing rule
is that neither may ever resolve a stand-in: a silent WAV, a canned transition,
a sentence sliced out of Wikipedia and labelled "drafted", a verifier that
approves everything. The owner judges the product by looking at these surfaces,
so a fake there does not merely mislead him — it invalidates every conclusion he
draws while it is present.

The doubles themselves are NOT the defect and are not removed: the hermetic
``make test`` suite needs them to stay $0 and offline. What must not exist is a
DOOR — a default, an env var, a config profile, a request field or an import —
through which one is reachable outside a test interpreter.

These are the two doors that no other test watches:

1. The app is a separate build. Nothing in ``src/`` can stop ``mobile/lib`` from
   importing a double out of ``mobile/test``; only this does.
2. ``register_provider()`` is the single sanctioned way to make the unregistered
   ``MockTTSProvider`` resolvable. It is safe ONLY while its caller set is
   exactly ``tests/``. One call from ``src/`` or ``scripts/`` silently re-arms
   every fake path the rest of this work closed.

Cheap, hermetic and $0. No regex — the project bans it for parsing because a
pattern that matches nothing returns a plausible empty result and an "absence"
assertion over an empty result passes vacuously. Every check below proves it
found something before it asserts anything is missing.
"""

from __future__ import annotations

import ast
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
MOBILE_LIB = REPO / "mobile" / "lib"
MOBILE_TEST = REPO / "mobile" / "test"


def _dart_files(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(p for p in root.rglob("*.dart") if p.is_file())


def _import_targets(source: str) -> list[str]:
    """Every quoted path in an ``import``/``export`` directive, by plain parsing.

    Dart directives are one per logical line and terminate at ``;``. We take the
    single- or double-quoted span inside each, which is the whole grammar we
    need — no regex, and an unparseable line simply yields nothing rather than a
    confident wrong answer.
    """
    targets: list[str] = []
    for raw in source.splitlines():
        line = raw.strip()
        if not (line.startswith("import ") or line.startswith("export ")):
            continue
        for quote in ("'", '"'):
            first = line.find(quote)
            if first == -1:
                continue
            second = line.find(quote, first + 1)
            if second != -1:
                targets.append(line[first + 1 : second])
                break
    return targets


def test_the_shipped_app_never_imports_from_its_test_tree() -> None:
    """``mobile/lib`` must not reach into ``mobile/test`` for anything.

    The app's doubles (``MockClient``, ``FakeLocationService``, the stub audio
    services) all live under ``mobile/test``, which is correct — that is what
    keeps ``make flutter-test`` hermetic. This is the guard that keeps them
    there. A single ``import '../../test/...'`` in a shipped file would put a
    fake in front of a tourist, and nothing else in the suite would notice.

    ``mobile/lib/services/providers.dart`` is the legitimate opposite of this:
    it declares the SEAM (an interface a test can implement), which is how you
    get testability without shipping a double.

    UNDO TEST: add ``import '../../test/services/mocks/mock_audio_service.dart';``
    to any file under ``mobile/lib`` -> RED, and the message names the file.
    """
    lib_files = _dart_files(MOBILE_LIB)
    test_files = _dart_files(MOBILE_TEST)

    # Non-vacuity: both trees must actually exist, or the sweep proves nothing.
    assert lib_files, f"no .dart files found under {MOBILE_LIB} — guard is vacuous"
    assert test_files, f"no .dart files found under {MOBILE_TEST} — guard is vacuous"

    offenders: dict[str, list[str]] = {}
    for path in lib_files:
        bad = [
            target
            for target in _import_targets(path.read_text(encoding="utf-8"))
            if "test/" in target or target.startswith("test/") or "/mocks/" in target
        ]
        if bad:
            offenders[str(path.relative_to(REPO))] = bad

    assert not offenders, (
        f"these shipped app files import out of the test tree: {offenders}. "
        f"Everything under mobile/test is a double; importing one into "
        f"mobile/lib ships a fake to a tourist."
    )


def _calls_to(func_name: str, roots: list[pathlib.Path]) -> dict[str, int]:
    """Count calls to ``func_name`` per file, via ``ast`` — never text matching.

    Catches both ``register_provider(...)`` and ``module.register_provider(...)``
    because it reads the call's callee, not the spelling of the line.
    """
    hits: dict[str, int] = {}
    for root in roots:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in paths:
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            count = 0
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                callee = node.func
                name = (
                    callee.id
                    if isinstance(callee, ast.Name)
                    else callee.attr
                    if isinstance(callee, ast.Attribute)
                    else None
                )
                if name == func_name:
                    count += 1
            if count:
                hits[str(path.relative_to(REPO))] = count
    return hits


def test_the_fake_tts_provider_has_no_server_side_registrar() -> None:
    """``register_provider()`` may be called from ``tests/`` and nowhere else.

    ``MockTTSProvider`` is defined but deliberately absent from ``_PROVIDERS``,
    so no env var, config profile, request body or deploy manifest can resolve
    it. ``register_provider()`` is the one door left open, and it is safe only
    while every caller runs inside a pytest interpreter. A call added under
    ``src/`` or ``scripts/`` would put the silent WAV back in
    ``GET /audio/providers`` — which is exactly the list the workbench dropdown
    is built from — and re-open ``POST /audio/preview {"provider": "mock"}``.

    UNDO TEST: call ``register_provider("mock", MockTTSProvider)`` anywhere under
    ``src/`` -> RED naming the file.
    """
    # Non-vacuity FIRST: prove the detector finds the one caller we know exists.
    # Without this, a broken walker would report "no callers" and pass.
    known = _calls_to("register_provider", [REPO / "tests"])
    assert known, (
        "the ast walk found no register_provider call under tests/, but "
        "tests/conftest.py is known to make one — the detector is broken, so a "
        "clean result from it would prove nothing"
    )

    server_side = _calls_to("register_provider", [REPO / "src", REPO / "scripts"])
    assert not server_side, (
        f"register_provider is called from server-side code: {server_side}. That "
        f"is the one door through which the unregistered silent-WAV provider "
        f"becomes resolvable, and a uvicorn process must never open it — the "
        f"workbench dropdown is built from that registry."
    )
