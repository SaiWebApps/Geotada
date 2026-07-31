"""A1 — the authoring primitives live in ``src/tour/authoring.py``, byte-identical.

Track A deletes ``src/tour/compose.py`` as a file (step A8).  Before that can happen,
the primitives that the SURVIVING callers need — the frozen physical authoring policy
(model / max_tokens / system prompt / output schema), the ``ComposeRequest`` input type,
the per-stop request rebuild and the pure certification finalizer — have to move out of
it into a module that survives.  This file guards that move.

Two things must hold, and they pull in opposite directions:

1. **Nothing changed.**  ``premium_authoring_policy_sha256()`` hashes the moved constants
   directly, and that hash is baked into committed certification data
   (``data/certification/tour-batch-v1/plan.json``).  A stray whitespace edit while
   moving the prompt would silently invalidate every recorded candidate.  So the hash is
   pinned to the value measured on the live tree BEFORE the move.

2. **The callers moved with it.**  ``premium_tour.py`` and friends must now import from
   ``src.tour.authoring``, not from ``src.tour.compose`` — otherwise the missed importer
   only explodes at A8, when the file it points at disappears.

Structure is read with ``ast`` (real parse of the real tree), never a text match.
"""

from __future__ import annotations

import ast
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

COMPOSE_MODULE = "src.tour.compose"
AUTHORING_MODULE = "src.tour.authoring"

#: The exact names ``premium_tour.py`` needs from the extracted module (D4: "premium_tour.py
#: imports 12 names from compose.py").
PREMIUM_MOVED_NAMES = frozenset(
    {
        "_COMPOSE_OUTPUT_SCHEMA",
        "_COMPOSE_SYSTEM",
        "CERTIFICATION_COMPOSE_MAX_OUTPUT_TOKENS",
        "COMPOSE_MODEL",
        "CertificationComposition",
        "CompletedCertificationComposeUnit",
        "ComposeRequest",
        "_certification_compose_requests",
        "_sentences_from_json",
        "candidate_compose_request_envelope",
        "compose_input_sha256",
        "finalize_certification_composition",
    }
)

#: Measured on the live tree at HEAD c8ec3969, BEFORE the extraction, by importing
#: ``premium_authoring_policy_sha256`` from ``src.tour.premium_tour`` and calling it.
#: The same value appears in committed certification plan data, so it is not free to drift.
PRE_MOVE_AUTHORING_POLICY_SHA256 = (
    "ed5f149e8d9be1dbff74f83f650db115a92cc4a38fa02f16f0f0fa29725611fd"
)

#: AC-2 (as amended 2026-07-30) clause one: the three importers the ENDPOINT CUTOVER owns —
#: ``compose.py`` itself and the two API modules that still drive the whole-tour composer.
#: Each is mapped to the Track A step that removes its edge, because "still imports compose"
#: is only true of them for part of the run: A3 cuts the route over to the per-stop seam, and
#: A8 deletes ``compose.py`` and ``get_compose_client`` together.  Before that step runs the
#: edge MUST still be there (A1 may not quietly do a later step's work); after it has run the
#: edge's absence is the plan working, not a regression.  The upper bound below never
#: loosens: none of the three may be replaced by some other surviving importer.
PINNED_COMPOSE_IMPORTERS: dict[str, str] = {
    "src/tour/compose.py": "A8",  # deleted as a file
    "src/api/dependencies.py": "A8",  # get_compose_client dies with it
    "src/api/routes/trips.py": "A3",  # the /trips/{id}/compose engine cutover
}

#: AC-2 (as amended) clause two, VERBATIM: the twelve importers the ledger already schedules
#: for deletion in a named later Track A step.  A1 deliberately leaves these edges alone —
#: its job is to catch a module that SURVIVES Track A and was missed, not to pre-delete
#: another step's work.  For ``tests/conftest.py`` it is the compose-client arm (:91-115)
#: that goes, not the file (D6/AC-9).
#:
#: This list is not invented here.  Every entry is named in AC-2's own text, and
#: :func:`test_later_step_allowlist_matches_the_ledger` re-derives it from ``state.json`` on
#: every run: each file must appear in the ``files_allowed`` of the step claimed to delete
#: it.  If the ledger and this list ever disagree, the test fails rather than the allowlist
#: silently absorbing a genuinely missed extraction — which is exactly how an allowlist
#: turns into a fudge.
COMPOSE_IMPORTERS_DELETED_BY_A_LATER_STEP: dict[str, str] = {
    "scripts/author_tour.py": "A6",  # author-engine track
    "tools/compose_snapshot.py": "A7",  # compose scoreboard
    "tests/test_compose_quality_eval.py": "A7",  # compose scoreboard
    "tests/conftest.py": "A8",  # the compose-client arm (:91-115) only
    "tests/test_tour_compose.py": "A8",  # compose.py's own tests
    "tests/test_tour_compose_live.py": "A8",
    "tests/test_compose_corrector_optin.py": "A8",
    "tests/test_compose_omission_detection.py": "A8",
    "tests/test_compose_provider.py": "A8",
    "tests/test_compose_repair_dedup.py": "A8",
    "tests/test_compose_revert_asymmetry.py": "A8",
    "tests/test_openai_compose.py": "A8",
}

#: The ledger this step is executing.  Read at test time so the allowlist above cannot drift
#: away from the plan it claims to quote.
LEDGER_STATE = REPO_ROOT / "specs" / "2026-07-29-one-true-tour-algorithm" / "state.json"

SCANNED_ROOTS = ("src", "scripts", "tests", "tools")


def _package_of(path: pathlib.Path) -> str:
    """The dotted package a module lives in, for resolving relative imports."""
    return ".".join(path.relative_to(REPO_ROOT).parts[:-1])


def _imported_modules(tree: ast.AST, package: str) -> dict[str, list[ast.ImportFrom | ast.Import]]:
    """Every absolute module name this file imports, mapped to the nodes that import it."""
    found: dict[str, list[ast.ImportFrom | ast.Import]] = {}
    package_parts = package.split(".") if package else []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - node.level + 1]
                module = ".".join([*base, node.module] if node.module else base)
            else:
                module = node.module or ""
            found.setdefault(module, []).append(node)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.setdefault(alias.name, []).append(node)
    return found


def _parse(relative_path: str) -> tuple[ast.Module, str]:
    path = REPO_ROOT / relative_path
    return ast.parse(path.read_text(encoding="utf-8")), _package_of(path)


def _python_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in SCANNED_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        files.extend(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


def _completed_step_ids() -> frozenset[str]:
    """The Track A step ids the ledger records as already run.

    A pinned import edge is only *required* to still exist until the step that removes it
    has run, so this is what separates "an earlier step overreached into a later one's
    work" from "that later step did its job".  Read strictly (``step["status"]``, no
    ``.get`` fallback): a renamed field must fail loudly, not silently mark everything
    done and switch the lower bound off.

    When the spec folder is gone Track A is over (2026-07-27 owner ruling) and every step
    counts as run; the pin then collapses to its upper-bound half, which
    :func:`test_later_step_allowlist_matches_the_ledger` independently backs up.
    """
    if not LEDGER_STATE.exists():
        return frozenset(PINNED_COMPOSE_IMPORTERS.values())
    ledger = json.loads(LEDGER_STATE.read_text(encoding="utf-8"))
    return frozenset(step["id"] for step in ledger["steps"] if step["status"] == "completed")


def test_premium_imports_authoring_not_compose() -> None:
    """THE A1 GATE. ``premium_tour.py`` gets its primitives from ``authoring``.

    RED before the extraction (``src.tour.authoring`` does not exist and premium_tour
    imports all twelve names from ``src.tour.compose``); GREEN after it.
    """
    tree, package = _parse("src/tour/premium_tour.py")
    imports = _imported_modules(tree, package)

    assert COMPOSE_MODULE not in imports, (
        "src/tour/premium_tour.py still imports "
        f"{COMPOSE_MODULE}; the authoring primitives were supposed to move to "
        f"{AUTHORING_MODULE}, which survives the deletion of compose.py at step A8."
    )
    assert AUTHORING_MODULE in imports, (
        f"src/tour/premium_tour.py imports nothing from {AUTHORING_MODULE}; the "
        "extraction did not happen."
    )

    imported_names = {
        alias.name
        for node in imports[AUTHORING_MODULE]
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    missing = PREMIUM_MOVED_NAMES - imported_names
    assert not missing, (
        f"src/tour/premium_tour.py does not import {sorted(missing)} from "
        f"{AUTHORING_MODULE}. All twelve moved names must come from the extracted module."
    )


def test_authoring_module_exports_the_moved_names() -> None:
    """The names are really there and really importable — not just an edited import line."""
    from src.tour import authoring

    missing = sorted(name for name in PREMIUM_MOVED_NAMES if not hasattr(authoring, name))
    assert not missing, f"src/tour/authoring.py is missing {missing}"


def test_authoring_policy_hash_is_byte_identical_after_the_move() -> None:
    """AC-2's byte-identity half: the frozen physical policy did not drift in transit."""
    from src.tour.premium_tour import premium_authoring_policy_sha256

    assert premium_authoring_policy_sha256() == PRE_MOVE_AUTHORING_POLICY_SHA256, (
        "the authoring policy hash changed during the extraction. The model, max_tokens, "
        "system prompt or output schema was edited, not just moved — and that hash is "
        "recorded in committed certification candidate data. Restore the bytes exactly."
    )


def test_remaining_compose_importers_are_pinned() -> None:
    """AC-2's importer half: a missed extraction fails HERE at A1, not at A8.

    Any module still importing ``src.tour.compose`` must either be one of the three
    survivors A2/A3 cut over, or be one of the twelve AC-2 names as dying in a later
    Track A step.
    """
    importers: set[str] = set()
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if COMPOSE_MODULE in _imported_modules(tree, _package_of(path)):
            importers.add(path.relative_to(REPO_ROOT).as_posix())

    unaccounted = (
        importers
        - set(PINNED_COMPOSE_IMPORTERS)
        - set(COMPOSE_IMPORTERS_DELETED_BY_A_LATER_STEP)
    )
    assert not unaccounted, (
        f"{sorted(unaccounted)} still import {COMPOSE_MODULE} but survive Track A. "
        "Repoint them at src.tour.authoring, or this breaks at A8 when compose.py is "
        "deleted."
    )

    done = _completed_step_ids()
    still_missing = sorted(
        name
        for name, step in PINNED_COMPOSE_IMPORTERS.items()
        if name not in importers and step not in done
    )
    assert not still_missing, (
        f"{still_missing} no longer import {COMPOSE_MODULE}, and the Track A step that owns "
        f"cutting each one over has not run yet. That is more than the current step was "
        "asked to do. Re-check the pin before widening it."
    )


def test_later_step_allowlist_matches_the_ledger() -> None:
    """The allowlist above is the LEDGER's deletion schedule, not this test's invention.

    An allowlist nobody checks is how a gate quietly stops gating: a genuinely missed
    extraction gets "explained" by adding a line to it.  So every entry is re-derived from
    ``state.json`` — the file must appear in the ``files_allowed`` of the very step claimed
    to remove it.  Disagreement fails here.
    """
    if not LEDGER_STATE.exists():
        # Track A finished and its spec folder was cleaned up (2026-07-27 owner ruling).
        # Then every allowlisted file must actually be GONE and the pin collapses to AC-2's
        # original three-importers-only form — stricter than the amended one, not weaker.
        # tests/conftest.py is excluded: D6/AC-9 delete an ARM of it, never the file.
        survivors = sorted(
            name
            for name in COMPOSE_IMPORTERS_DELETED_BY_A_LATER_STEP
            if name != "tests/conftest.py" and (REPO_ROOT / name).exists()
        )
        assert not survivors, (
            f"{survivors} were scheduled for deletion during Track A and the ledger at "
            f"{LEDGER_STATE} is gone, so Track A is over — but they still exist. Either "
            "the deletion steps did not run or the allowlist is now hiding real importers."
        )
        return

    ledger = json.loads(LEDGER_STATE.read_text(encoding="utf-8"))
    # ``files`` is the ledger's own key for a step's file scope. Read it strictly: a
    # ``.get(..., ())`` fallback would turn a renamed field into a silent all-pass, which
    # is the same failure mode this test exists to prevent.
    scoped_files = {step["id"]: set(step["files"]) for step in ledger["steps"]}

    # Both halves of the pin name a step: the twelve that are DELETED by a later step, and
    # the three whose compose edge is CUT OVER by a named step (which is what lets the
    # lower bound above stand down once that step has run). Neither may name a step whose
    # scope does not actually include the file.
    unbacked = sorted(
        (name, step)
        for name, step in (
            *COMPOSE_IMPORTERS_DELETED_BY_A_LATER_STEP.items(),
            *PINNED_COMPOSE_IMPORTERS.items(),
        )
        if name not in scoped_files[step]
    )
    assert not unbacked, (
        f"{unbacked} are allowlisted here as 'deleted by a later step', but that step's "
        "`files` scope in the ledger does not list them. The allowlist is asserting a "
        "deletion the plan never promised — that is a fudge, not an exemption."
    )
