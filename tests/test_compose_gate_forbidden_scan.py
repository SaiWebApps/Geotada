"""CHARACTERIZATION TEST for a known-open defect — read this before "fixing" a failure here.

THE DEFECT (open as of 2026-07-27, HEAD a882af1)
-------------------------------------------------
``build_full_verifier`` (src/tour/compose_gate.py:314) defaults ``base_validator`` to
``validate_script``, which is source-traceability PLUS the forbidden-phrase scan
(``_forbidden_phrase_hits``, src/tour/validation.py:164) — the check that catches the
writer inventing a proper noun or a year in a glue sentence.

``finalize_certification_composition`` overrides that default at src/tour/compose.py:975
with ``validate_authorized_sources``, which returns ``validate_source_traceability`` ONLY.
So the forbidden-phrase scan never runs in the certification path, and every downstream
consumer of ``forbidden_phrase_hits`` reads 0 BY CONSTRUCTION rather than by measurement —
including ``render_md.py:309``, which prints "(gate: 0)", and
``src/api/routes/trips.py:793``, which puts the count on an API response.

Full write-up: Docs/bug-reports/2026-07-27-preview-failure-observability-salvage.md §1.

WHY THESE TESTS ARE GREEN AND NOT RED
--------------------------------------
They pin the CURRENT, WRONG behaviour on purpose, so the defect is executable rather than
buried in a document. A red test would just be a broken build that someone silences.

**When the gate is fixed, ``test_certification_validator_delegates_only_to_traceability``
WILL FAIL. That failure is the success signal.** Delete this file at that point — do not
"repair" the assertion to keep it green.

WHY THAT TEST READS THE SOURCE TREE RATHER THAN CALLING THE FUNCTION
---------------------------------------------------------------------
The validator in question is a CLOSURE (``validate_authorized_sources``) defined inside
``finalize_certification_composition``, so it cannot be imported and called directly, and
reaching it at runtime means constructing a fully-consistent set of completed compose units
(matching request hashes, payload hashes and envelopes) — i.e. replicating a compose run.

A first draft of this file asserted on ``validate_source_traceability`` directly instead.
A judge caught that this is worthless: the natural fix is to edit the CLOSURE BODY, which
leaves ``validate_source_traceability`` untouched, so that test would have stayed GREEN
straight through the fix and left the repo asserting a closed defect was open.

So the closure is inspected STRUCTURALLY with ``ast`` (the house-approved way to read real
structure — never a pattern match): parse the real function, find the nested validator,
and assert its body is nothing but a delegation to ``validate_source_traceability``. Any
genuine fix — adding the scan, switching to ``validate_script``, wrapping the result —
changes that body and turns this red.
"""

from __future__ import annotations

import ast
import datetime as _dt
import inspect
import textwrap

from src.tour.compose import finalize_certification_composition
from src.tour.compose_gate import build_full_verifier
from src.tour.contract import (
    BeatRef,
    BeatSequence,
    POIBeats,
    Script,
    ScriptPOI,
    Sentence,
    TourInput,
    ValidationReport,
)
from src.tour.generation import GLUE_PACING
from src.tour.validation import validate_script, validate_source_traceability

#: The nested validator the certification path substitutes for ``validate_script``.
CERT_VALIDATOR_NAME = "validate_authorized_sources"

#: A proper noun and a year that appear NOWHERE in the cited corpus text below.
INVENTED_NAME = "Fontainebleau"
INVENTED_YEAR = "1743"


def _sequence() -> BeatSequence:
    return BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id="p1",
                poi_name="Place des Vosges",
                ordering_strategy="trigger_address",
                beats=(
                    BeatRef(
                        id="b1",
                        poi_id="p1",
                        word_count=9,
                        script_body="The square was completed in 1612 under Henri IV.",
                    ),
                ),
            ),
        )
    )


def _script_with_invented_glue() -> Script:
    """One sourced beat sentence, plus a glue sentence inventing a name and a year."""
    return Script(
        city_slug="paris",
        generated_at=_dt.datetime(2026, 7, 27, tzinfo=_dt.UTC).isoformat(),
        inputs=TourInput(
            start=(48.8555, 2.3656), duration_min=60, city_slug="paris", round_trip=True
        ),
        total_audio_seconds=0,
        total_walking_seconds=0,
        total_walk_distance_m=0,
        total_planned_seconds=0,
        selected_pois=(
            ScriptPOI(
                id="p1", name="Place des Vosges", tier=5, lat=48.85, lng=2.36, area="Le Marais"
            ),
        ),
        lens_coverage={},
        script=(
            Sentence(
                text="The square was completed in 1612 under Henri IV.",
                source_id="b1",
                source_type="beat",
                stop_idx=0,
            ),
            Sentence(
                text=f"The court had moved from {INVENTED_NAME} by {INVENTED_YEAR}.",
                source_id=GLUE_PACING,
                source_type="glue",
                stop_idx=0,
            ),
        ),
        validation=ValidationReport(),
    )


def test_the_forbidden_phrase_scan_does_catch_invented_content() -> None:
    """Control. The scan itself works — the defect is that one path does not call it."""
    script = _script_with_invented_glue()
    report = validate_script(script, _sequence())

    codes = {code for _sentence, code in report.forbidden_phrase_hits}
    assert f"new_proper_noun:{INVENTED_NAME}" in codes, (
        f"the scan should flag an invented proper noun; got {sorted(codes)}"
    )
    assert f"new_year:{INVENTED_YEAR}" in codes, (
        f"the scan should flag an invented year; got {sorted(codes)}"
    )


def _certification_validator_ast() -> ast.FunctionDef:
    """The REAL nested validator from ``finalize_certification_composition``'s source."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(finalize_certification_composition)))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == CERT_VALIDATOR_NAME:
            return node
    raise AssertionError(
        f"{CERT_VALIDATOR_NAME} no longer exists inside "
        "finalize_certification_composition. The certification path was restructured — "
        "re-verify by hand whether the forbidden-phrase scan now runs there, then either "
        "delete this file (fixed) or re-anchor these tests (still broken)."
    )


def test_certification_path_installs_its_own_validator() -> None:
    """The override itself: the certification path does not use the default verifier."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(finalize_certification_composition)))
    overrides = [
        kw.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "build_full_verifier"
        for kw in node.keywords
        if kw.arg == "base_validator" and isinstance(kw.value, ast.Name)
    ]
    assert overrides == [CERT_VALIDATOR_NAME], (
        "the certification path's base_validator override changed to "
        f"{overrides!r}. If it now passes validate_script (or nothing), the defect is "
        "fixed — delete this file. But an EMPTY list may instead mean the call site was "
        "refactored to a module-qualified form (compose_gate.build_full_verifier(...)), "
        "which this AST walk matches by bare name only. Check which before concluding "
        "anything."
    )


def test_certification_validator_delegates_only_to_traceability() -> None:
    """THE DEFECT. Pins current wrong behaviour — read the module docstring before editing.

    The installed validator's whole body is a single ``return
    validate_source_traceability(...)``. That call cannot see forbidden phrases, invented
    proper nouns or invented years — only ``validate_script`` adds that scan, and the
    certification path replaced it.

    WHEN THE GATE IS FIXED THIS TEST FAILS. That is the alarm. Delete the file.
    """
    body = _certification_validator_ast().body
    statements = [node for node in body if not isinstance(node, ast.Expr)]  # drop docstring

    delegates_only = (
        len(statements) == 1
        and isinstance(statements[0], ast.Return)
        and isinstance(statements[0].value, ast.Call)
        and getattr(statements[0].value.func, "id", None) == "validate_source_traceability"
    )
    assert delegates_only, (
        "GOOD NEWS, PROBABLY: the certification-path validator is no longer a bare "
        "delegation to validate_source_traceability. If it now runs the forbidden-phrase "
        "scan, the defect in "
        "Docs/bug-reports/2026-07-27-preview-failure-observability-salvage.md §1 is fixed "
        "— delete this whole test file rather than adjusting this assertion."
    )


def test_that_delegation_is_why_invented_content_survives() -> None:
    """Ties the structure above to the consequence: same script, opposite verdicts."""
    script, sequence = _script_with_invented_glue(), _sequence()

    assert validate_script(script, sequence).forbidden_phrase_hits != ()
    assert validate_source_traceability(script, sequence).forbidden_phrase_hits == ()


def test_the_default_verifier_still_runs_the_full_scan() -> None:
    """The default is not the problem; only the certification override is.

    Guards against a 'fix' that removes the scan from ``build_full_verifier``'s default
    instead of adding it to the certification path — that would make the two paths agree
    by making both of them blind.
    """
    default = inspect.signature(build_full_verifier).parameters["base_validator"].default
    assert default is validate_script, (
        "build_full_verifier's base_validator default must stay validate_script (the "
        f"full scan); it is now {default!r}. Making both paths blind is not a fix."
    )
