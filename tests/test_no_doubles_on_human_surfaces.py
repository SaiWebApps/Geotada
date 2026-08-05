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


def test_the_app_shows_what_degraded_rather_than_dropping_it() -> None:
    """A degraded tour must SAY so on the phone, not look like a clean one.

    The third door of the same defect this file guards. When the walking-
    directions service is unreachable the backend still builds the tour, but its
    walking times are estimates rather than measured routes, and it labels that
    on the wire (``degradations``, each row carrying the plain-English ``human``
    sentence — ``src/tour/degradations.py:44-67``). The phone used to drop the
    field on parse, so the traveller read estimated times as if a real route had
    been measured. That is a stand-in reaching a human surface, which is exactly
    what this file exists to stop.

    The register matters as much as the presence. ``human`` is written for a
    person and names no service, module or exception; ``kind``, ``component``,
    ``error_type`` and ``error_message`` are for an operator. Rendering either of
    the latter to a tourist is its own defect, so this guard checks the page shows
    only the first.

    Plain substring parsing, per this file's docstring, and every absence check
    below is preceded by a proof that the sweep read the right file.

    UNDO TEST: change the wire key in ``mobile/lib/models/trip.dart`` from
    ``json['degradations']`` to any other name -> RED at assertion 2. Or delete
    the ``_DegradationCard`` line from the itinerary page -> RED at assertion 4.
    """
    model = (MOBILE_LIB / "models" / "trip.dart").read_text(encoding="utf-8")
    page = (MOBILE_LIB / "pages" / "trip_itinerary_page.dart").read_text(encoding="utf-8")
    service = (MOBILE_LIB / "services" / "trip_service.dart").read_text(encoding="utf-8")

    # 1. Non-vacuity: prove each file is the one we think it is before asserting
    #    that anything is present or absent in it. A moved file would otherwise
    #    make every check below pass against the wrong text.
    assert "class GeneratedTrip" in model, (
        "GeneratedTrip is no longer declared in mobile/lib/models/trip.dart — the "
        "model moved and this guard is reading the wrong file"
    )
    assert "class TripItineraryPage" in page, (
        "TripItineraryPage is no longer declared in "
        "mobile/lib/pages/trip_itinerary_page.dart — the page moved and this "
        "guard is reading the wrong file"
    )
    assert "GeneratedTrip.fromJson" in service, (
        "mobile/lib/services/trip_service.dart no longer parses through "
        "GeneratedTrip.fromJson — the app gained a second parse path and this "
        "guard no longer covers it"
    )

    # 2. The wire key is READ, not dropped.
    assert "json['degradations']" in model, (
        "mobile/lib/models/trip.dart does not read the response's degradations "
        "field, so a tour built on estimated walking times reaches the traveller "
        "looking exactly like one built on measured routes"
    )

    # 3. The parsed value is KEPT.
    assert "degradationNotices" in model, (
        "mobile/lib/models/trip.dart parses the degradations field but stores "
        "nothing — a value read and discarded is the same silence"
    )

    # 4. The page RENDERS it. A parsed-but-unrendered field fails this step.
    assert "degradationNotices" in page, (
        "mobile/lib/pages/trip_itinerary_page.dart never reads the trip's "
        "degradation notices, so nothing the backend reported reaches the screen"
    )
    assert "_DegradationCard" in page, (
        "mobile/lib/pages/trip_itinerary_page.dart has no _DegradationCard "
        "widget, so there is nothing on the itinerary for the traveller to read"
    )

    # 5. The traveller reads the HUMAN register and only that one.
    assert "row['human']" in model, (
        "mobile/lib/models/trip.dart does not take the human sentence off each "
        "degradation row; every other field on that row is written for an "
        "operator, not a tourist"
    )
    operator_only = [
        field for field in ("error_type", "error_message", "component") if field in page
    ]
    assert not operator_only, (
        f"the itinerary page names operator-facing degradation fields "
        f"{operator_only}. A traveller must never be shown an exception class, "
        f"an exception message or the name of the code that failed — "
        f"src/tour/degradations.py reserves those for the operator and gives the "
        f"traveller `human`."
    )

    # 6. The notices arrive by the ordinary parse path, not a private second one.
    assert "GeneratedTrip.fromJson" in service, (
        "mobile/lib/services/trip_service.dart must reach the notices through the "
        "same model parse every other trip field uses"
    )
