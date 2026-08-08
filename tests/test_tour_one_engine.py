"""AC-1 / AC-9 / AC-10 (partial) — the ONE-ENGINE boundary, one node id per Track A step.

Track A's D6 deletes the old narration tracks in a fixed order, and this file grows one
pinned node id per step so each deletion has an executable proof rather than a claim:

- ``test_author_engine_track_is_gone`` (A6) — the never-shipped author-engine track
  (``src/tour/author.py``, ``content_budget.py``, ``tour_consistency.py``,
  ``scripts/author_tour.py``).
- ``test_compose_scoreboard_is_gone`` (A7) — the compose-metrics scoreboard.
- ``test_whole_tour_composer_is_gone`` (A8) — ``src/tour/compose.py`` and
  ``src/tour/factcheck.py``, the reduced ``compose_gate`` surface, the conftest money-guard
  arms that fed them, and AC-1's ``compose_script`` boundary clause.

The one-engine boundary AC-1 describes has two halves, and they come true at different
steps: A8 removes the ``compose_script``/``compose_script_per_chapter`` import edge, and
A9 removes the last non-premium narration-provider construction in ``src/``. Per CF-4 the
step that lands SECOND must assert both, so A9's node id owns the second half.

Structure is read with ``ast`` and ``subprocess`` (``git ls-files``), never a text/regex
match.

NONE OF THIS IS AC-1/AC-9 MET ON ITS OWN. Carry-forward CF-4 in this ledger's
``state.json`` maps every AC-1 and AC-9 clause to the step (A7/A8/A9/A10) that owns it.
Read it before adding the next node id to this file.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

#: The author-engine track this step deletes (D6). ``src/tour/factcheck.py`` is
#: deliberately absent — it waits for A8.
DELETED_FILES = (
    "src/tour/author.py",
    "src/tour/content_budget.py",
    "src/tour/tour_consistency.py",
    "scripts/author_tour.py",
    "tests/test_author.py",
    "tests/test_content_budget.py",
    "tests/test_tour_consistency.py",
)

#: Dotted module names a surviving file must never import once the track is gone.
DELETED_MODULES = frozenset(
    {
        "src.tour.author",
        "src.tour.content_budget",
        "src.tour.tour_consistency",
    }
)

SCANNED_ROOTS = ("src", "scripts", "tests", "tools")

#: The autouse money-guard fixture in ``tests/conftest.py``.
MONEY_GUARD_FIXTURE = "_money_guard_no_live_compose"

#: Every ``(module, attribute)`` the money-guard fixture must swap for an offline stub —
#: the CURRENT truth, shared by the A6 and A8 node ids below so there is exactly one place
#: to update when a step removes an arm. Read STRUCTURALLY from conftest's AST, not by
#: looking for the class name in the source text: a substring check stays green when the
#: arming ``monkeypatch.setattr`` is deleted but the name survives in a comment, which is
#: exactly how a money-guard silently disarms. Equality (not containment) is deliberate —
#: it fails both on a disarmed guard and on an unreviewed new billing client.
#:
#: A6 removed the two author-engine arms (``src.tour.author.LLMDrafter``,
#: ``src.tour.tour_consistency.HaikuCrossStopJudge``). A8 removed the two compose-client
#: rows and the three ``factcheck`` judge rows (AC-9 (a) and (c)) — the whole-tour composer
#: and ``get_omission_checker`` that built them are gone. A9 removed the last two rows
#: (``src.tour.compose_correct.AnthropicCorrectionClient``,
#: ``src.tour.claim_repetition.HaikuRedundancyJudge``) together with the corrector and the
#: dark G4, so the pair below is the WHOLE set of billing clients the tree can still build.
EXPECTED_MONEY_GUARD_ARMS = frozenset(
    {
        # AC-9: this premium-executor + faithfulness pair must survive Track A untouched.
        ("src.tour.premium_tour", "AnthropicPremiumExecutor"),
        ("src.tour.verify", "HaikuFaithfulnessChecker"),
    }
)


def _package_of(path: pathlib.Path) -> str:
    return ".".join(path.relative_to(REPO_ROOT).parts[:-1])


def _imported_modules(tree: ast.AST, package: str) -> set[str]:
    """Every absolute module name a file imports (relative imports resolved)."""
    found: set[str] = set()
    package_parts = package.split(".") if package else []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - node.level + 1]
                module = ".".join([*base, node.module] if node.module else base)
            else:
                module = node.module or ""
            found.add(module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
    return found


def _python_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for root in SCANNED_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        files.extend(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(files)


def _tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return set(out.stdout.splitlines())


def _money_guard_armed_pairs(conftest_tree: ast.AST) -> set[tuple[str, str]]:
    """The ``(module, attribute)`` pairs the money-guard fixture actually arms.

    Structural: it collects the ``monkeypatch.setattr(<alias>, <name>, ...)`` CALLS
    inside the fixture body, resolves ``<alias>`` through the fixture's own
    ``import x as alias`` statements, and resolves a non-constant ``<name>`` through the
    enclosing ``for <name> in ("A", "B")`` loop that binds it. Nothing here matches text,
    so a class name mentioned only in a comment or docstring cannot keep it green.
    """
    fixture = next(
        node
        for node in ast.walk(conftest_tree)
        if isinstance(node, ast.FunctionDef) and node.name == MONEY_GUARD_FIXTURE
    )

    aliases: dict[str, str] = {}
    for node in ast.walk(fixture):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name

    # `for _judge_name in ("HaikuCoverageJudge", "HaikuFaithfulnessJudge"):` — the loop
    # variable is the setattr target for each literal in the iterable.
    loop_bound: dict[str, tuple[str, ...]] = {}
    for node in ast.walk(fixture):
        if not (isinstance(node, ast.For) and isinstance(node.target, ast.Name)):
            continue
        if not isinstance(node.iter, (ast.Tuple, ast.List)):
            continue
        elts = node.iter.elts
        if elts and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in elts):
            loop_bound[node.target.id] = tuple(e.value for e in elts)

    pairs: set[tuple[str, str]] = set()
    for node in ast.walk(fixture):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "setattr":
            continue
        owner = node.func.value
        if not (isinstance(owner, ast.Name) and owner.id == "monkeypatch"):
            continue
        target, attr = node.args[0], node.args[1]
        module = aliases.get(target.id, target.id) if isinstance(target, ast.Name) else "<expr>"
        if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
            pairs.add((module, attr.value))
        elif isinstance(attr, ast.Name) and attr.id in loop_bound:
            pairs.update((module, value) for value in loop_bound[attr.id])
        else:
            pairs.add((module, "<unresolved>"))
    return pairs


def test_author_engine_track_is_gone() -> None:
    # 1. Every file the step names is gone from disk AND from git's index (a file left
    #    untracked-but-present would still break the "deleted" claim).
    tracked = _tracked_files()
    on_disk = [f for f in DELETED_FILES if (REPO_ROOT / f).exists()]
    still_tracked = [f for f in DELETED_FILES if f in tracked]
    assert not on_disk, f"{on_disk} still exist on disk; A6 must delete them."
    assert not still_tracked, f"{still_tracked} are still tracked by git; `git rm` them."

    # 2. No surviving file (src/, scripts/, tests/, tools/) imports the deleted modules —
    #    a missed importer would explode at collection/runtime rather than being caught here.
    offenders: dict[str, set[str]] = {}
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = _imported_modules(tree, _package_of(path))
        hit = imported & DELETED_MODULES
        if hit:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = hit
    assert not offenders, (
        f"{offenders} still import a module A6 deleted; repoint or delete the importer."
    )

    # 3. tests/conftest.py's money-guard fixture: the author + cross-stop-consistency arms
    #    are gone (no more `src.tour.author` / `src.tour.tour_consistency` import), and the
    #    arms A6 did not own are exactly the current live set.
    conftest_tree = ast.parse((REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    conftest_imports = _imported_modules(conftest_tree, "tests")
    assert "src.tour.author" not in conftest_imports
    assert "src.tour.tour_consistency" not in conftest_imports

    # The surviving arms, checked by what the fixture ARMS rather than by what its text
    # mentions: exactly these (module, attribute) pairs, no more and no fewer.
    armed = _money_guard_armed_pairs(conftest_tree)
    assert armed == set(EXPECTED_MONEY_GUARD_ARMS), (
        "tests/conftest.py's money-guard armed set drifted. "
        f"disarmed={sorted(set(EXPECTED_MONEY_GUARD_ARMS) - armed)} "
        f"unexpected={sorted(armed - set(EXPECTED_MONEY_GUARD_ARMS))}"
    )


# ---- A7 — the compose scoreboard is deleted (CF-4's A7 row) ----------------------------
#
# D6: "compose scoreboard (compose_metrics + its eval + tools/compose_snapshot.py +
# craft_score) at A7 BEFORE compose_gate's _bad_stops dies." ``src/tour/narration_quality.py``
# is deliberately NOT in the deletion list below: ``craft_score`` still has a real production
# caller (``src/tour/compose.py:84``) that survives until compose.py itself is deleted as a
# file at A8 (D6) — deleting the symbol now would explode compose.py's import at collection
# time for every one of its many importers, which is exactly the "suite stops collecting"
# failure D6's ordering exists to avoid. CF-4 (A6 judge ruling) enumerates A7's actual AC-1
# obligation as exactly these three paths; the two test files below are the "its eval" D6
# names and are additionally pinned by AC-2's amendment
# (``COMPOSE_IMPORTERS_DELETED_BY_A_LATER_STEP`` in tests/test_tour_authoring_extraction.py).

#: The compose scoreboard this step deletes as files.
SCOREBOARD_DELETED_FILES = (
    "src/tour/compose_metrics.py",
    "tests/test_compose_metrics.py",
    "tests/test_compose_quality_eval.py",
    "tools/compose_snapshot.py",
    ".claude/commands/report-tour-issue.md",
)

#: Dotted module names a surviving file must never import once the scoreboard is gone.
SCOREBOARD_DELETED_MODULES = frozenset(
    {
        "src.tour.compose_metrics",
        "tools.compose_snapshot",
    }
)


def test_compose_scoreboard_is_gone() -> None:
    # 1. Every file this step names is gone from disk AND from git's index (a file left
    #    untracked-but-present would still break the "deleted" claim).
    tracked = _tracked_files()
    on_disk = [f for f in SCOREBOARD_DELETED_FILES if (REPO_ROOT / f).exists()]
    still_tracked = [f for f in SCOREBOARD_DELETED_FILES if f in tracked]
    assert not on_disk, f"{on_disk} still exist on disk; A7 must delete them."
    assert not still_tracked, f"{still_tracked} are still tracked by git; `git rm` them."

    # 2. No surviving file (src/, scripts/, tests/, tools/) imports the deleted modules — a
    #    missed importer would explode at collection/runtime rather than being caught here.
    offenders: dict[str, set[str]] = {}
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = _imported_modules(tree, _package_of(path))
        hit = imported & SCOREBOARD_DELETED_MODULES
        if hit:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = hit
    assert not offenders, (
        f"{offenders} still import a module A7 deleted; repoint or delete the importer."
    )


# ---- unify-tour-algorithm step 4 — the SECOND authoring seam is deleted ----------------
#
# Deliberately placed next to ``test_compose_scoreboard_is_gone`` rather than at the end of
# the file: concurrent lanes of the same ledger also add a ``test_*_is_gone`` here, and three
# additions at one end-of-file is the classic both-added merge conflict.

#: The second authoring seam, deleted in this step. Every name must vanish from the
#: whole tree, not merely from ``src/`` — three test modules imported them at module
#: scope, so a half-done deletion collect-errors the suite rather than failing cleanly.
DELETED_SEAM_NAMES = frozenset(
    {
        "PrebuiltRouteComposeUnit",
        "PrebuiltRouteAuthoringPlan",
        "PrebuiltRouteExecutor",
        "prebuilt_route_sha256",
        "plan_prebuilt_route_authoring",
        "author_prebuilt_route",
    }
)

#: The five already-shared helpers the deletion must NOT take with it (AC-11).
SURVIVING_AUTHORING_HELPERS = frozenset(
    {
        "_certification_compose_requests",
        "candidate_compose_request_envelope",
        "compose_input_sha256",
        "_sentences_from_json",
        "finalize_certification_composition",
    }
)


def test_the_second_authoring_seam_is_gone() -> None:
    """AC-1 / AC-9 / AC-11 / AC-22 — one Block-2 seam, and the tree knows it.

    UNDO: re-add ``def author_prebuilt_route(...)`` to ``src/tour/authoring.py`` and
    clause 1 goes RED; re-add its ``__all__`` entry and clause 3 goes RED; rename any of
    the five shared helpers and clause 2 goes RED; restore any single call in the three
    re-pointed test modules and clause 4 goes RED, naming the file; add a planner import
    to a Block-2 function body and clause 5 goes RED.
    """
    authoring = REPO_ROOT / "src" / "tour" / "authoring.py"
    tree = ast.parse(authoring.read_text(encoding="utf-8"), filename=str(authoring))

    # 1. The six symbols are not DEFINED in authoring.py any more.
    defined = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.ClassDef)
    }
    assert not defined & DELETED_SEAM_NAMES, sorted(defined & DELETED_SEAM_NAMES)

    # 2. The five shared helpers survive.
    assert defined >= SURVIVING_AUTHORING_HELPERS, sorted(
        SURVIVING_AUTHORING_HELPERS - defined
    )

    # 3. __all__ carries neither them nor AUTHORING_MAX_STOPS.
    exported = {
        elt.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "__all__"
        for elt in node.value.elts
        if isinstance(elt, ast.Constant)
    }
    assert exported, "authoring.py lost its __all__ entirely"
    assert not exported & DELETED_SEAM_NAMES
    assert "AUTHORING_MAX_STOPS" not in exported

    # 4. REPOSITORY-WIDE: no file under src/ scripts/ tests/ tools/ still names any
    #    of them — as an import, a call, or a bare reference. This is the clause that
    #    binds the test re-points: an un-re-pointed test module is a hit here.
    offenders: dict[str, set[str]] = {}
    for path in _python_files():
        if path.name == "test_tour_one_engine.py":
            continue  # this file names them as data, on purpose
        file_tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        named = (
            {node.id for node in ast.walk(file_tree) if isinstance(node, ast.Name)}
            | {
                alias.name
                for node in ast.walk(file_tree)
                if isinstance(node, ast.ImportFrom)
                for alias in node.names
            }
            | {node.attr for node in ast.walk(file_tree) if isinstance(node, ast.Attribute)}
        )
        hit = named & DELETED_SEAM_NAMES
        if hit:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = hit
    assert not offenders, (
        "the second authoring seam still has live references, so the deletion is "
        f"half-done and the suite will collect-error: {offenders}"
    )

    # 5. The AUTHOR block cannot reach a planner — the function-scoped guard, run
    #    from here too so the deletion and the prohibition share one node id.
    from tests.test_tour_authoring_from_route import (
        _assert_the_seam_cannot_reach_the_planner,
    )

    _assert_the_seam_cannot_reach_the_planner()


# ---- unify-tour-algorithm — ONE planner, ONE interleave, and no private preview --------
#
# The owner's question, 2026-08-04: "prove to me that the app and the workbench
# ultimately invoke the exact same tour logic code end-to-end. No duplicate, no separate
# modules with the logic."
#
# ``tests/test_workbench_matches_the_app.py`` answers the RUNTIME half by breaking one
# shared object and requiring both HTTP surfaces to break. That is the load-bearing
# proof, but it can only speak about paths a request actually takes: a second
# implementation that no live handler reaches today is invisible to it, and is exactly
# what the next refactor picks up by mistake. This node id answers the STRUCTURAL half —
# there is only one such implementation in the tree at all — by reading the syntax tree.

#: The two primitives that turn one request into the K route options a person chooses
#: between. Naming them is not an allowlist: everything asserted below (who calls them,
#: from where, and whether that set has one member) is derived from the tree.
K_OPTION_PRIMITIVES = frozenset({"select_k_routes", "choose_discrete_route"})

#: The one callable allowed to produce them, as ``(repo-relative file, function)``.
THE_ONE_PLANNER = ("src/tour/premium_tour.py", "plan_premium_options")

#: The output contract the interleave assembles. Constructing either of these IS
#: interleaving a route into cards, whatever the surrounding function is called.
INTERLEAVE_TYPES = frozenset({"RouteOption", "RouteOptionStop"})
CONTRACT_MODULE = "src.tour.contract"
THE_ONE_INTERLEAVE_MODULE = "src/tour/options.py"
THE_ONE_INTERLEAVE = "build_route_option"

#: The private preview interleave deleted on 2026-08-04 (AC-17). It lived in the API
#: layer and had already drifted from the shared builder: it split walk-concurrent
#: narration onto its own card and the shared builder did not, so the workbench and the
#: phone disagreed about what a "stop" is.
DELETED_PREVIEW_INTERLEAVE = "_preview_stops"


def _called_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _call_sites(tree: ast.AST, wanted: frozenset[str]) -> dict[str, set[str]]:
    """``callee -> {enclosing function}`` for every call to a wanted name.

    A call made at import time is reported under ``"<module scope>"`` rather than
    dropped: a second planner run while the module loads is still a second planner.
    """
    found: dict[str, set[str]] = {}

    def _descend(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                _descend(child, child.name)
                continue
            if isinstance(child, ast.Call):
                name = _called_name(child.func)
                if name in wanted:
                    found.setdefault(name, set()).add(scope)
            _descend(child, scope)

    _descend(tree, "<module scope>")
    return found


def _local_names_for(tree: ast.AST, package: str, module: str, names: frozenset[str]) -> set[str]:
    """What THIS file calls ``names`` after importing them from ``module``.

    Following the ``as`` alias matters: a construction spelled ``RO(...)`` after
    ``from .contract import RouteOption as RO`` is the same construction, and a check
    that only knew the original spelling would walk straight past it.
    """
    local: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if _imported_modules(node, package) != {module}:
            continue
        local |= {alias.asname or alias.name for alias in node.names if alias.name in names}
    return local


def _every_referenced_name(tree: ast.AST) -> set[str]:
    """Every identifier a file mentions — called, imported, attribute-accessed or defined."""
    return (
        {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        | {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        | {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom | ast.Import)
            for alias in node.names
        }
        | {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        }
    )


def test_one_planner_produces_the_options_and_one_interleave_builds_them() -> None:
    """AC-1 / AC-11 / AC-17 — there is nothing in the tree for a surface to diverge onto.

    Four things, read from the syntax tree rather than from any text match:

    1. NON-VACUITY FIRST. The five helpers both authoring paths already shared must
       still be defined. A deletion that took the whole module with it would otherwise
       satisfy every absence check below for free — "it is not there" and "nothing is
       there" are the same sentence to a search and opposite outcomes to a product.
    2. The deleted second authoring seam has zero references anywhere in the Python
       tree, and so does the deleted private preview interleave.
    3. EXACTLY ONE callable turns a request into the K route options. The two
       primitives that do it may be called from one function in one file and nowhere
       else, so a surface cannot quietly acquire its own definition of "the three
       routes we offer" — which is what the phone had until 2026-08-04, when it called
       the K-route selector directly with no walk-budget policy and produced a
       measurably shorter tour than the workbench did for the same request.
    4. EXACTLY ONE place assembles the option payload. Building either output-contract
       object IS interleaving a route into cards, so every such construction must live
       in the one builder module — and, inside it, in the public builder or its own
       private card helpers.

    UNDO (each turns this RED):
      * add a second ``select_k_routes(...)`` call anywhere under ``src/`` -> clause 3;
      * construct a ``RouteOption`` or ``RouteOptionStop`` outside
        ``src/tour/options.py`` -> clause 4;
      * add a public second builder inside that module -> clause 4's scope check;
      * restore ``_preview_stops`` to the API layer -> clause 2;
      * rename or delete any of the five shared authoring helpers -> clause 1.
    """
    files = _python_files()
    assert files, "found no python files at all; this sweep would pass vacuously"
    trees = {
        path: ast.parse(path.read_text(encoding="utf-8"), filename=str(path)) for path in files
    }
    src_trees = {
        path: tree
        for path, tree in trees.items()
        if path.relative_to(REPO_ROOT).parts[0] == "src"
    }
    assert src_trees, "found no modules under src/; this sweep would pass vacuously"

    # 1. NON-VACUITY. The shared helpers AC-11 requires to survive are still defined,
    #    and so are the one planner and the one interleave this test is about.
    authoring = REPO_ROOT / "src" / "tour" / "authoring.py"
    authoring_defines = {
        node.name
        for node in trees[authoring].body
        if isinstance(node, ast.FunctionDef | ast.ClassDef)
    }
    assert authoring_defines >= SURVIVING_AUTHORING_HELPERS, (
        f"the shared authoring helpers "
        f"{sorted(SURVIVING_AUTHORING_HELPERS - authoring_defines)} are gone. The "
        f"deletion took working code with it, and every 'is it absent?' check in this "
        f"file would now pass for the wrong reason."
    )
    for relative, function in (THE_ONE_PLANNER, (THE_ONE_INTERLEAVE_MODULE, THE_ONE_INTERLEAVE)):
        defined = {
            node.name
            for node in trees[REPO_ROOT / relative].body
            if isinstance(node, ast.FunctionDef)
        }
        assert function in defined, (
            f"{relative} no longer defines {function}, so the single implementation "
            f"this test pins has moved and the pin is watching nothing"
        )

    # 2a. ZERO REFERENCES to the deleted second authoring seam, anywhere a Python file
    #     can name them — as a call, an import, an attribute or a definition. This file
    #     names them as data on purpose, so it excludes itself.
    survivors: dict[str, set[str]] = {}
    for path, tree in trees.items():
        if path.name == "test_tour_one_engine.py":
            continue
        hit = _every_referenced_name(tree) & DELETED_SEAM_NAMES
        if hit:
            survivors[path.relative_to(REPO_ROOT).as_posix()] = hit
    assert not survivors, (
        f"a deleted authoring seam still has live references: {survivors}. While a "
        f"second seam exists, 'both surfaces run the same code' is one import away "
        f"from stopping being true."
    )

    # 2b. The deleted private preview interleave: gone from src/ outright, which is
    #     AC-17's own scope. One TEST module keeps a local helper of that name, and it
    #     is deliberately left alone: it is four lines that call the shared builder, so
    #     it is a wire adapter, not a second implementation — deleting it would delete
    #     the assertions that pin what the workbench renders.
    #
    #     Which is why the rule enforced outside src/ is BEHAVIOURAL rather than
    #     lexical: anything defining a function by that name must reach the one
    #     interleave. A real copy — the fourth interleave that lived in the API layer
    #     until 2026-08-04 and had already drifted from the shared one — fails that,
    #     because a copy by definition does not call the thing it copies.
    lexical = {
        path.relative_to(REPO_ROOT).as_posix()
        for path, tree in src_trees.items()
        if DELETED_PREVIEW_INTERLEAVE in _every_referenced_name(tree)
    }
    assert not lexical, (
        f"{sorted(lexical)} under src/ still name {DELETED_PREVIEW_INTERLEAVE}, the "
        f"API layer's private copy of the interleave. AC-17 requires zero hits there."
    )
    impostors: list[str] = []
    definitions = 0
    for path, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if node.name != DELETED_PREVIEW_INTERLEAVE:
                continue
            definitions += 1
            if not _call_sites(node, frozenset({THE_ONE_INTERLEAVE})):
                impostors.append(f"{path.relative_to(REPO_ROOT).as_posix()}::{node.name}")
    assert not impostors, (
        f"{impostors} define a preview interleave that never calls "
        f"{THE_ONE_INTERLEAVE}, so it is assembling the cards itself. That is the "
        f"fourth copy coming back: it drifted last time by splitting walk-concurrent "
        f"narration onto its own card while the phone did not, and the two surfaces "
        f"stopped agreeing about what a stop is."
    )
    assert definitions, (
        f"nothing defines {DELETED_PREVIEW_INTERLEAVE} anywhere, so the behavioural "
        f"clause above examined nothing. That is a legitimate end state — say so here "
        f"and drop the clause rather than leaving a check that watches an empty set."
    )

    # 3. EXACTLY ONE callable produces the K route options.
    planners: dict[str, set[str]] = {}
    for path, tree in src_trees.items():
        relative = path.relative_to(REPO_ROOT).as_posix()
        for callee, scopes in _call_sites(tree, K_OPTION_PRIMITIVES).items():
            planners.setdefault(callee, set()).update(f"{relative}::{scope}" for scope in scopes)
    assert set(planners) == set(K_OPTION_PRIMITIVES), (
        f"only {sorted(planners)} of {sorted(K_OPTION_PRIMITIVES)} are called anywhere "
        f"under src/. One of the primitives this clause watches has been renamed or has "
        f"gone dead, so the clause is no longer measuring the planner."
    )
    expected_site = {f"{THE_ONE_PLANNER[0]}::{THE_ONE_PLANNER[1]}"}
    for callee, sites in sorted(planners.items()):
        assert sites == expected_site, (
            f"{callee} is called from {sorted(sites)}. Exactly one callable may turn a "
            f"request into the offered route options, and it is "
            f"{THE_ONE_PLANNER[1]} in {THE_ONE_PLANNER[0]}. A second caller is a second "
            f"answer to 'which three walks are we offering', and the two clients would "
            f"then be choosing from different menus."
        )

    # 4. EXACTLY ONE place assembles the option payload.
    builders: dict[str, set[str]] = {}
    for path, tree in src_trees.items():
        relative = path.relative_to(REPO_ROOT).as_posix()
        package = _package_of(path)
        local = _local_names_for(tree, package, CONTRACT_MODULE, INTERLEAVE_TYPES)
        if not local:
            continue
        for _callee, scopes in _call_sites(tree, frozenset(local)).items():
            builders.setdefault(relative, set()).update(scopes)
    assert builders, (
        "nothing under src/ constructs a RouteOption or a RouteOptionStop, so the "
        "output contract is built somewhere this clause cannot see — re-derive it"
    )
    assert set(builders) == {THE_ONE_INTERLEAVE_MODULE}, (
        f"the option payload is assembled in {sorted(builders)}. It may be assembled "
        f"only in {THE_ONE_INTERLEAVE_MODULE}: a second assembler is a second opinion "
        f"about what a stop is, which is exactly the drift that made the preview split "
        f"walk-concurrent narration onto its own card while the phone did not."
    )
    public_builders = {
        scope
        for scope in builders[THE_ONE_INTERLEAVE_MODULE]
        if scope != THE_ONE_INTERLEAVE and not scope.startswith("_")
    }
    assert not public_builders, (
        f"{sorted(public_builders)} in {THE_ONE_INTERLEAVE_MODULE} build the option "
        f"payload alongside {THE_ONE_INTERLEAVE}, so a caller can pick which interleave "
        f"it gets. The card helpers are private for exactly that reason."
    )

    # ...and the request path really goes through it, so this is a live constraint
    # rather than a rule about a module nobody calls.
    routes = REPO_ROOT / "src" / "api" / "routes" / "trips.py"
    assert THE_ONE_INTERLEAVE in _call_sites(trees[routes], frozenset({THE_ONE_INTERLEAVE})), (
        f"no handler in {routes.relative_to(REPO_ROOT)} calls {THE_ONE_INTERLEAVE}, so "
        f"the surfaces are building their option payloads some other way"
    )


# ---- A8 — the whole-tour composer is deleted (CF-4's A8 rows) --------------------------
#
# D6: "compose.py + factcheck.py + compose_gate ladder + Makefile LIVE_TEST_FILES at A8 in
# one step". CF-4 assigns A8 these rows and no others:
#   - AC-1  : src/tour/compose.py and src/tour/factcheck.py absent from the tree;
#   - AC-1  : the compose_script BOUNDARY clause, FIRST half — no
#             ``compose_script``/``compose_script_per_chapter`` edge anywhere in src/ or
#             scripts/. (CF-4: "whichever of A8/A9 lands second MUST assert both halves";
#             A8 lands FIRST, so the second half — "in src/ the only narration-provider
#             construction is the premium executor path" — is A9's, because compose_correct
#             and claim_repetition still construct billing clients until A9 deletes them.)
#   - AC-9(a): conftest's compose-client arm gone;  AC-9(c): its factcheck arms gone;
#   - AC-9(d): the premium-executor + faithfulness arm BYTE-UNTOUCHED. CF-4 records this
#             clause as UNOWNED and strictly stronger than "still armed". A8 claims it:
#             this step edits the arms on either side of it, so this is the step where a
#             stray reflow would happen.
#   - AC-9(e): ``src/api/dependencies.py`` holds no ``get_compose_client`` and no
#             ``get_omission_checker`` (the other two names in that clause,
#             ``get_correction_client`` and ``get_claim_repetition_judge``, die with the
#             corrector and the dark G4 at A9).
#   - AC-10 : ``make tour-build`` runs the $0 stitch+render harness (D7) — asserted through
#             the reduced ``compose_gate`` surface, which no longer exports the ladder
#             ``scripts/tour_build.py`` used to drive.
#
# NOT asserted here (not A8's): compose_correct.py / verify_gate.py / claim_repetition.py
# deletion and the corrector + G4 dependency and conftest arms — all A9's rows in CF-4.

#: The whole-tour composer track this step deletes as files.
COMPOSER_DELETED_FILES = (
    "src/tour/compose.py",
    "src/tour/factcheck.py",
    "tests/test_tour_compose.py",
    "tests/test_tour_compose_live.py",
    "tests/test_openai_compose.py",
    "tests/test_compose_provider.py",
    "tests/test_tour_recompose.py",
    "tests/test_compose_repair_dedup.py",
    "tests/test_compose_revert_asymmetry.py",
    "tests/test_compose_corrector_optin.py",
    "tests/test_compose_omission_detection.py",
    "tests/test_factcheck.py",
)

#: Dotted module names a surviving file must never import once the composer is gone.
COMPOSER_DELETED_MODULES = frozenset({"src.tour.compose", "src.tour.factcheck"})

#: AC-1's boundary clause, first half: the whole-tour entry points. No file under src/ or
#: scripts/ may import or attribute-access either name.
WHOLE_TOUR_ENTRY_POINTS = frozenset({"compose_script", "compose_script_per_chapter"})

#: What is LEFT of ``src/tour/compose_gate.py`` after A8 — exactly the step's own name:
#: "compose_gate reduced to ComposeVerificationError + build_full_verifier". The recompose
#: ladder (``compose_and_verify``, ``serve_or_block``, ``MAX_COMPOSE_ATTEMPTS``,
#: ``ComposeFn``) and the whole-tour repairs (``drop_failing_sentences``,
#: ``repair_composed``, ``repair_composed_surgical``) all die with the whole-tour composer.
#: Equality, not containment: a re-added ladder function fails here.
REDUCED_COMPOSE_GATE_API = frozenset({"ComposeVerificationError", "build_full_verifier"})

COMPOSE_GATE_MODULE = "src.tour.compose_gate"

#: AC-9(d) — the premium-executor + faithfulness arm, VERBATIM as it stands at
#: tests/conftest.py:117-135 before A8 touches the file. "Byte-untouched" is a claim about
#: BYTES, and ``EXPECTED_MONEY_GUARD_ARMS`` (which only proves the pair is still armed)
#: cannot see a reflow, a renamed stub, or an inverted ``provider is None`` branch. This
#: literal can.
PREMIUM_FAITHFULNESS_ARM_SOURCE = '''\
    # PREMIUM authoring money-guard: the workbench now uses the same zero-retry,
    # receipt-preserving physical boundary as certification batches. Product
    # construction is replaced by the explicit $0 adapter; injected fake
    # providers still exercise the real executor in unit tests.
    import src.tour.premium_tour as _premium_mod

    _real_premium = _premium_mod.AnthropicPremiumExecutor

    def _guard_premium(provider=None):
        if provider is None:
            return _premium_mod.OfflinePremiumExecutor()
        return _real_premium(provider)

    monkeypatch.setattr(_premium_mod, "AnthropicPremiumExecutor", _guard_premium)
    # No non-live test constructs the real Haiku checker with a fake SDK, so the
    # billing checker is always swapped for the offline trusting stub.
    monkeypatch.setattr(
        _verify_mod, "HaikuFaithfulnessChecker", _verify_mod.MockFaithfulnessChecker
    )
'''

#: AC-9(e), A8's half. The corrector and G4 providers are A9's.
DEPENDENCIES_REMOVED_AT_A8 = ("get_compose_client", "get_omission_checker")


def _public_top_level_names(tree: ast.Module) -> set[str]:
    """Every public module-level binding: classes, functions and assigned names."""
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return {n for n in names if not n.startswith("_")}


def _names_imported_from(tree: ast.AST, package: str, module: str) -> set[str]:
    """The attribute names a file pulls out of ``module`` via ``from module import x``."""
    package_parts = package.split(".") if package else []
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            base = package_parts[: len(package_parts) - node.level + 1]
            resolved = ".".join([*base, node.module] if node.module else base)
        else:
            resolved = node.module or ""
        if resolved == module:
            names.update(alias.name for alias in node.names)
    return names


def _live_test_files() -> tuple[str, ...]:
    """``LIVE_TEST_FILES`` from the Makefile, following its backslash continuations.

    Plain line/word splitting on the real assignment — no pattern matching. An
    unparseable Makefile raises rather than yielding an empty tuple that would pass
    every assertion below by vacuity.
    """
    lines = (REPO_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("LIVE_TEST_FILES"):
            continue
        _, sep, rest = line.partition(":=")
        assert sep, f"Makefile:{index + 1} is not a `:=` assignment: {line!r}"
        entries: list[str] = []
        cursor, current = index, rest.strip()
        while current.endswith("\\"):
            entries.extend(current[:-1].split())
            cursor += 1
            current = lines[cursor].strip()
        entries.extend(current.split())
        return tuple(entries)
    raise AssertionError("Makefile has no LIVE_TEST_FILES assignment to check")


def test_whole_tour_composer_is_gone() -> None:
    # 1. Every file this step names is gone from disk AND from git's index (a file left
    #    untracked-but-present would still break the "deleted" claim).
    tracked = _tracked_files()
    on_disk = [f for f in COMPOSER_DELETED_FILES if (REPO_ROOT / f).exists()]
    still_tracked = [f for f in COMPOSER_DELETED_FILES if f in tracked]
    assert not on_disk, f"{on_disk} still exist on disk; A8 must delete them."
    assert not still_tracked, f"{still_tracked} are still tracked by git; `git rm` them."

    # 2. No surviving file imports the deleted modules, and (AC-1's boundary clause, first
    #    half) nothing under src/ or scripts/ reaches the whole-tour entry points by import
    #    OR by attribute access — `mod.compose_script(...)` is the same edge with the
    #    import hidden one level up.
    import_offenders: dict[str, set[str]] = {}
    boundary_offenders: dict[str, set[str]] = {}
    for path in _python_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hit = _imported_modules(tree, _package_of(path)) & COMPOSER_DELETED_MODULES
        if hit:
            import_offenders[relative] = hit
        if path.relative_to(REPO_ROOT).parts[0] not in ("src", "scripts"):
            continue
        reached = {
            node.name if isinstance(node, ast.alias) else node.attr
            for node in ast.walk(tree)
            if (isinstance(node, ast.alias) and node.name in WHOLE_TOUR_ENTRY_POINTS)
            or (isinstance(node, ast.Attribute) and node.attr in WHOLE_TOUR_ENTRY_POINTS)
        }
        if reached:
            boundary_offenders[relative] = reached
    assert not import_offenders, (
        f"{import_offenders} still import a module A8 deleted; repoint or delete them."
    )
    assert not boundary_offenders, (
        f"AC-1 boundary violated: {boundary_offenders} still reach the whole-tour "
        "composer entry points. src/ and scripts/ must hold ONE engine."
    )

    # 3. compose_gate is reduced to exactly the two names that survive, and every surviving
    #    importer takes only those two. This is what makes `make tour-build` the $0
    #    stitch+render harness of D7/AC-10: the recompose ladder it drove is not there to
    #    import any more.
    gate_tree = ast.parse((REPO_ROOT / "src" / "tour" / "compose_gate.py").read_text("utf-8"))
    assert _public_top_level_names(gate_tree) == set(REDUCED_COMPOSE_GATE_API), (
        "src/tour/compose_gate.py's public surface is not the reduced "
        f"{sorted(REDUCED_COMPOSE_GATE_API)}; it exports "
        f"{sorted(_public_top_level_names(gate_tree))}."
    )
    gate_importers: dict[str, set[str]] = {}
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        taken = _names_imported_from(tree, _package_of(path), COMPOSE_GATE_MODULE)
        extra = taken - set(REDUCED_COMPOSE_GATE_API)
        if extra:
            gate_importers[path.relative_to(REPO_ROOT).as_posix()] = extra
    assert not gate_importers, (
        f"{gate_importers} import names A8 removed from compose_gate."
    )

    # 4. AC-9 (a)/(c)/(d) — tests/conftest.py. The compose-client and factcheck arms are
    #    gone (checked by what the fixture ARMS, structurally), and the premium-executor +
    #    faithfulness arm is byte-for-byte what it was before this step.
    conftest_source = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    conftest_tree = ast.parse(conftest_source)
    conftest_imports = _imported_modules(conftest_tree, "tests")
    assert not conftest_imports & COMPOSER_DELETED_MODULES, (
        "tests/conftest.py still imports a module A8 deleted."
    )
    armed = _money_guard_armed_pairs(conftest_tree)
    assert armed == set(EXPECTED_MONEY_GUARD_ARMS), (
        "tests/conftest.py's money-guard armed set drifted. "
        f"disarmed={sorted(set(EXPECTED_MONEY_GUARD_ARMS) - armed)} "
        f"unexpected={sorted(armed - set(EXPECTED_MONEY_GUARD_ARMS))}"
    )
    assert PREMIUM_FAITHFULNESS_ARM_SOURCE in conftest_source, (
        "AC-9: the premium-executor + faithfulness money-guard arm (conftest :117-135) is "
        "no longer byte-identical. A8 removes the arms around it and must not reflow, "
        "rename or re-branch it."
    )

    # 5. AC-9(e), A8's half: the whole-tour compose client and the omission checker are no
    #    longer constructible from the API's dependency module.
    deps_tree = ast.parse((REPO_ROOT / "src" / "api" / "dependencies.py").read_text("utf-8"))
    surviving = _public_top_level_names(deps_tree) & set(DEPENDENCIES_REMOVED_AT_A8)
    assert not surviving, (
        f"src/api/dependencies.py still defines {sorted(surviving)}; AC-9 requires them gone."
    )

    # 6. The Makefile's live shard no longer points at a deleted file. The existence half
    #    is the anti-fudge: pruning by pointing the shard at a nonexistent path would make
    #    `make test-live` silently collect nothing.
    live_files = _live_test_files()
    assert live_files, "LIVE_TEST_FILES parsed empty — the check would be vacuous."
    deleted_but_listed = [f for f in live_files if f in COMPOSER_DELETED_FILES]
    missing = [f for f in live_files if not (REPO_ROOT / f).exists()]
    assert not deleted_but_listed, (
        f"Makefile LIVE_TEST_FILES still lists {deleted_but_listed}, which A8 deletes."
    )
    assert not missing, f"Makefile LIVE_TEST_FILES points at nonexistent {missing}."


# ---- A9 — the corrector, the dark G4 and the dead scaffolding (CF-4's A9 rows) ---------
#
# D6: "corrector + dark G4 + dead scaffolding at A9". CF-4 assigns A9 these rows:
#   - AC-1  : src/tour/compose_correct.py, src/tour/verify_gate.py and
#             src/tour/claim_repetition.py absent from the tree;
#   - AC-1  : the boundary clause, SECOND half — "in src/ the only narration-provider
#             construction is the premium executor path". CF-4: "whichever of A8/A9 lands
#             second MUST assert BOTH halves", and A9 lands second, so this node id
#             re-asserts A8's compose_script half as well rather than trusting that A8's
#             own node id is still present and green.
#   - AC-9(b): conftest's corrector arm (:137-152 pre-A8, the last two money-guard rows)
#             gone, leaving EXPECTED_MONEY_GUARD_ARMS at the premium+faithfulness pair;
#   - AC-9(d): that surviving pair still BYTE-UNTOUCHED — A9 deletes the arms below it,
#             which is exactly where a stray reflow would happen;
#   - AC-9(e): src/api/dependencies.py holds none of the four names, i.e. A8's
#             ``get_compose_client``/``get_omission_checker`` PLUS A9's own
#             ``get_correction_client``/``get_claim_repetition_judge``.
# Plus the "dead scaffolding" half of A9's own name, which no AC clause spells out but
# which the step exists to remove: the never-populated ``Script.verify_report`` +
# ``StopVerifyStatus`` contract fields, the three eligibility functions that read them,
# the permanently-empty ``g4``/omission response blocks in the preview payload, and the
# workbench's ``composed_partial`` + ChatGPT narrator labels for engines that are gone.

#: The corrector + dark-G4 track this step deletes as files.
CORRECTOR_DELETED_FILES = (
    "src/tour/compose_correct.py",
    "src/tour/verify_gate.py",
    "src/tour/claim_repetition.py",
    "tests/test_claim_repetition.py",
)

#: Dotted module names a surviving file must never import once the track is gone.
CORRECTOR_DELETED_MODULES = frozenset(
    {
        "src.tour.compose_correct",
        "src.tour.verify_gate",
        "src.tour.claim_repetition",
    }
)

#: AC-1's boundary clause, SECOND half. "Narration-provider construction" is read as the
#: bounded-client factories in ``src/tour/anthropic_client.py`` that build a PROSE-WRITING
#: client — the judge/verify factories are checkers, not narrators, and D8 keeps them.
NARRATION_CLIENT_FACTORIES = frozenset(
    {
        "compose_client",
        "certification_compose_client",
        "certification_batch_compose_client",
    }
)

#: Every file under ``src/`` allowed to pull one of those factories, and which. EQUALITY,
#: not containment: a re-added second narration engine fails here.
#:
#: ``src/tour/certification_provider.py`` IS the premium executor path — it is the physical
#: provider ``premium_tour.AnthropicPremiumExecutor`` wraps. ``src/onboard/beat_draft.py``
#: is the corpus-ingest beat drafter (it writes BEATS into the graph during onboarding, not
#: tour narration at request time), so the tour-narration half of the clause is exactly the
#: one certification_provider row.
EXPECTED_NARRATION_CLIENT_IMPORTERS = {
    "src/tour/certification_provider.py": {"certification_compose_client"},
    "src/onboard/beat_draft.py": {"compose_client"},
}

ANTHROPIC_CLIENT_MODULE = "src.tour.anthropic_client"

#: AC-9(e), the WHOLE clause — A8's two names and A9's two.
DEPENDENCIES_REMOVED_BY_TRACK_A = (
    "get_compose_client",
    "get_omission_checker",
    "get_correction_client",
    "get_claim_repetition_judge",
)

#: Dead scaffolding. ``src/tour/contract.py`` loses the per-stop verify diagnostic that
#: only ``compose_script_per_chapter`` ever populated (D8: "contract.py minus dead
#: verify_report/StopVerifyStatus"), and ``candidate_eligibility.py`` loses the three
#: functions that read it.
#: KEPT, not deleted — the names D8 wrongly called dead. See CF-4: removing them was
#: measured to break 13 saved tours. The constant name is retained so the reversal is
#: visible in the diff rather than silently renamed away.
DEAD_CONTRACT_NAMES = ("StopVerifyStatus",)
DEAD_SCRIPT_FIELD = "verify_report"
DEAD_ELIGIBILITY_FUNCTIONS = (
    "llm_candidate_rejection",
    "llm_candidate_ineligibility",
    "is_complete_llm_candidate",
)
#: Anti-over-deletion: the typed rejection surface the preview route still returns must
#: SURVIVE this step.
SURVIVING_ELIGIBILITY_NAMES = ("CandidateRejection", "CandidateRejectionCode")

#: String constants the preview response payload must no longer build. Every one of these
#: keys was structurally unreachable-as-non-empty after A8 (``omitted_facts`` is a literal
#: ``[]`` and ``omission_stops_checked`` a literal ``0``), so they advertised a check that
#: could not fire.
DEAD_PREVIEW_RESPONSE_KEYS = (
    "g4",
    "omission_stops_checked",
    "omission_findings",
    "coverage_omission",
)

#: Workbench labels for engines Track A deleted: the per-chapter partial-revert status
#: (only ``compose_script_per_chapter`` ever emitted it) and the ChatGPT narrator label
#: (D9 loss 1 — the Opus-vs-ChatGPT compose comparison).
DEAD_WORKBENCH_LABELS = ("composed_partial", "ChatGPT (OpenAI)")


def _class_field_names(tree: ast.Module, class_name: str) -> set[str]:
    """The annotated field names declared directly on a module-level class."""
    node = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name
    )
    return {
        stmt.target.id
        for stmt in node.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    }


def _string_constants(tree: ast.AST) -> set[str]:
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


SUPERSEDED_SPEC_DIRS = (
    "specs/2026-07-26-tour-engine-convergence",
    "specs/2026-07-26-tour-rubric-recalibration",
)

#: The dead review runner and its test. `scripts/tour_text_candidate.py` is its LIVE
#: sibling and must survive — it backs four paid Make targets — so this pair is named
#: explicitly rather than matched by prefix.
DEAD_REVIEW_RUNNER = (
    "scripts/tour_text_candidate_review.py",
    "tests/test_tour_text_candidate_review_runner.py",
)


def test_superseded_specs_and_config_are_gone() -> None:
    """AC-1's last uncovered rows: the repudiated plan folders and the dead runner.

    A judge blocker found these shipping UNGUARDED — every other path AC-1 names had a
    test, these did not, so a future session could restore the folders the owner
    repudiated and nothing would object.

    The two spec folders are the THREE-TIMES-FAILED convergence attempt and its rubric
    sibling. They are not merely stale: a dead `specs/` directory also arms
    `.claude/hooks/team-gate.sh` against any agent prompt naming its path, and the
    owner's clean-up ruling is explicit that a stale plan is read as current and acted
    on. `scripts/tour_text_candidate.py` (no `_review`) is LOAD-BEARING and is asserted
    to survive here, because deleting it by prefix-match would break four paid targets.

    UNDO: restore any of these paths and this goes RED.
    """
    tracked = _tracked_files()
    for directory in SUPERSEDED_SPEC_DIRS:
        assert not (REPO_ROOT / directory).exists(), (
            f"{directory} is back on disk. It is the repudiated plan; a dead specs/ dir "
            "is read as current by the next session and arms team-gate.sh."
        )
        resurrected = sorted(f for f in tracked if f.startswith(directory + "/"))
        assert not resurrected, f"{directory} is tracked again by git: {resurrected[:3]}"

    for path in DEAD_REVIEW_RUNNER:
        assert not (REPO_ROOT / path).exists(), f"{path} is back on disk."
        assert path not in tracked, f"{path} is tracked by git again."

    survivor = "scripts/tour_text_candidate.py"
    assert (REPO_ROOT / survivor).exists() and survivor in tracked, (
        f"{survivor} must SURVIVE — it is the live sibling of the deleted review runner "
        "and backs four paid Make targets. Deleting it by name-prefix is the mistake "
        "this assertion exists to catch."
    )


# ---- Step 13 (AC-13) — the standalone preview proof-of-concept is deleted --------------
#
# OWNER RULING 3: `frontend/tour-preview.html` is deleted outright, not re-pointed. It was
# a standalone POC that made the same two calls as the workbench's own tour view, which
# step 12 rebuilt into a pick-then-build flow. A second, thinner copy of that flow means
# every future change to it is made twice, and the copy that drifts is the one nobody
# opens. Deleted with it: the route that served the page, that route's smoke test, and the
# one browser test that opened it. The route is the reason this is one step and not two —
# a page deleted while its route survives is a live URL that can only 404, which is worse
# than either half alone.

#: Deleted whole by this step. Checked on disk AND in git's index — a file removed from
#: disk but left tracked by git is not deleted.
DELETED_PREVIEW_POC_FILES = (
    "frontend/tour-preview.html",
    "tests/test_preview_page.py",
)

#: The route that served the page: the URL its decorator registered and the handler under
#: it. Both are named, so renaming one and keeping the other cannot pass.
DEAD_PREVIEW_ROUTE = "/tour-preview"
DEAD_PREVIEW_HANDLER = "tour_preview_page"

#: The needle for a surviving MENTION of the deleted page in `src/api/app.py` — code or
#: comment. Scoped to that one file on purpose: the workbench's own tour view is
#: legitimately called "tour preview" all over `tests/test_workbench_ui.py` and
#: `frontend/review.html`, so a repo-wide needle would be a false positive factory.
DEAD_PREVIEW_MENTION = "tour-preview"

#: The only browser test that opened the deleted page. Left behind, it drives Playwright
#: at a 404.
DEAD_PREVIEW_BROWSER_TEST = "test_standalone_tour_preview_renders_basic_lane_honestly"

#: Live neighbours of what is removed — same file, same shape. These are what an
#: over-eager deletion takes with it, so each is asserted to SURVIVE. They double as the
#: non-vacuity proof: every other assertion here is an ABSENCE, and an absence is free if
#: the parse found nothing at all.
SURVIVING_APP_ROUTES = ("/auth", "/api/v1/healthz")
SURVIVING_WORKBENCH_TOUR_TESTS = (
    "test_tour_preview_generates_and_plays",
    "test_tour_preview_renders_basic_lane_honestly",
)


def _registered_routes(tree: ast.AST) -> dict[str, str]:
    """Map ``URL path -> handler name`` for every ``@<obj>.<verb>("/path")`` decorator.

    Structural: it reads the decorator CALLS attached to each function definition, so a
    path surviving only in a comment or a docstring cannot keep it green, and a route
    whose handler was renamed is still found by its path.
    """
    routes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute) or not decorator.args:
                continue
            first = decorator.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                routes[first.value] = node.name
    return routes


def _function_names(tree: ast.AST) -> set[str]:
    """Every function and method name defined in a file, sync or async."""
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_the_standalone_preview_poc_is_gone() -> None:
    """AC-13 — one tour-preview surface, not two (OWNER RULING 3).

    UNDO TEST: ``git checkout HEAD -- frontend/tour-preview.html`` -> RED. Restoring the
    ``/tour-preview`` route in ``src/api/app.py``, the deleted route's smoke test, or the
    browser test that opened the page is RED too.
    """
    app_source = (REPO_ROOT / "src" / "api" / "app.py").read_text(encoding="utf-8")
    app_tree = ast.parse(app_source)
    ui_tree = ast.parse(
        (REPO_ROOT / "tests" / "test_workbench_ui.py").read_text(encoding="utf-8")
    )

    # 1. Non-vacuity FIRST, for BOTH parses. Everything below asserts an absence, and an
    #    absence passes for free against an empty derivation, so prove each sweep still
    #    sees the live neighbours it should. This is also the anti-over-deletion check:
    #    it fails if the deletion took a live route or a live workbench test with it.
    routes = _registered_routes(app_tree)
    missing_routes = [path for path in SURVIVING_APP_ROUTES if path not in routes]
    assert not missing_routes, (
        f"{missing_routes} are no longer registered in src/api/app.py — either this route "
        "sweep stopped reading real decorators, or the deletion took live routes with it."
    )
    ui_tests = _function_names(ui_tree)
    missing_tests = [name for name in SURVIVING_WORKBENCH_TOUR_TESTS if name not in ui_tests]
    assert not missing_tests, (
        f"{missing_tests} are gone from tests/test_workbench_ui.py — step 13 removes only "
        "the standalone page's own browser test; the workbench view keeps its own."
    )

    # 2. The page and the deleted route's smoke test are gone from disk AND from git's
    #    index (a file removed from disk but left tracked is not deleted).
    tracked = _tracked_files()
    on_disk = [f for f in DELETED_PREVIEW_POC_FILES if (REPO_ROOT / f).exists()]
    still_tracked = [f for f in DELETED_PREVIEW_POC_FILES if f in tracked]
    assert not on_disk, f"{on_disk} still exist on disk; step 13 deletes them outright."
    assert not still_tracked, f"{still_tracked} are still tracked by git; `git rm` them."

    # 3. The route that served the page went with it — the registered path AND the handler
    #    under it, so renaming either one and keeping the other still fails.
    assert DEAD_PREVIEW_ROUTE not in routes, (
        f"src/api/app.py still registers {DEAD_PREVIEW_ROUTE} (handler "
        f"{routes.get(DEAD_PREVIEW_ROUTE)!r}), but the page it serves is deleted, so the "
        "route can only 404."
    )
    assert DEAD_PREVIEW_HANDLER not in _function_names(app_tree), (
        f"src/api/app.py still defines {DEAD_PREVIEW_HANDLER}(); the handler and the file "
        "path constant it reads go with the decorator."
    )

    # 4. No surviving mention of the page in app.py — code OR comment. The AST sweep above
    #    cannot see comments, and a comment pointing at a deleted page is read as current
    #    by the next session.
    mentions = [
        f"src/api/app.py:{number} {line.strip()}"
        for number, line in enumerate(app_source.splitlines(), 1)
        if DEAD_PREVIEW_MENTION in line
    ]
    assert not mentions, (
        f"src/api/app.py still mentions the deleted standalone preview page: {mentions}"
    )

    # 5. The browser test that opened the page is gone, by name and by the URL it drove.
    #    `_string_constants` reaches the literal parts of the f-string it used, so a
    #    restored `goto(...)` under a different test name fails here too.
    assert DEAD_PREVIEW_BROWSER_TEST not in ui_tests, (
        f"tests/test_workbench_ui.py still defines {DEAD_PREVIEW_BROWSER_TEST}; it opens "
        "the deleted page and can now only meet a 404."
    )
    goto_urls = [s for s in _string_constants(ui_tree) if DEAD_PREVIEW_ROUTE in s]
    assert not goto_urls, (
        f"tests/test_workbench_ui.py still builds a URL for the deleted page: {goto_urls}"
    )


def test_corrector_and_dark_g4_are_gone() -> None:
    # 1. Every file this step names is gone from disk AND from git's index.
    tracked = _tracked_files()
    on_disk = [f for f in CORRECTOR_DELETED_FILES if (REPO_ROOT / f).exists()]
    still_tracked = [f for f in CORRECTOR_DELETED_FILES if f in tracked]
    assert not on_disk, f"{on_disk} still exist on disk; A9 must delete them."
    assert not still_tracked, f"{still_tracked} are still tracked by git; `git rm` them."

    # 2. No surviving file imports the deleted modules, and — AC-1's boundary clause,
    #    FIRST half, re-asserted here because A9 lands second (CF-4) — nothing under src/
    #    or scripts/ still reaches the whole-tour composer entry points.
    import_offenders: dict[str, set[str]] = {}
    boundary_offenders: dict[str, set[str]] = {}
    narration_importers: dict[str, set[str]] = {}
    for path in _python_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hit = _imported_modules(tree, _package_of(path)) & CORRECTOR_DELETED_MODULES
        if hit:
            import_offenders[relative] = hit
        root = path.relative_to(REPO_ROOT).parts[0]
        if root == "src":
            taken = _names_imported_from(tree, _package_of(path), ANTHROPIC_CLIENT_MODULE)
            narrating = taken & NARRATION_CLIENT_FACTORIES
            if narrating:
                narration_importers[relative] = narrating
        if root not in ("src", "scripts"):
            continue
        reached = {
            node.name if isinstance(node, ast.alias) else node.attr
            for node in ast.walk(tree)
            if (isinstance(node, ast.alias) and node.name in WHOLE_TOUR_ENTRY_POINTS)
            or (isinstance(node, ast.Attribute) and node.attr in WHOLE_TOUR_ENTRY_POINTS)
        }
        if reached:
            boundary_offenders[relative] = reached
    assert not import_offenders, (
        f"{import_offenders} still import a module A9 deleted; repoint or delete them."
    )
    assert not boundary_offenders, (
        f"AC-1 boundary violated: {boundary_offenders} still reach the whole-tour "
        "composer entry points."
    )

    # 3. AC-1's boundary clause, SECOND half: in src/ the only narration-provider
    #    construction is the premium executor path.
    assert narration_importers == EXPECTED_NARRATION_CLIENT_IMPORTERS, (
        "AC-1 boundary violated: src/ narration-provider construction is not the premium "
        f"executor path alone. got={narration_importers} "
        f"expected={EXPECTED_NARRATION_CLIENT_IMPORTERS}"
    )

    # 4. AC-9 (b)/(d) — tests/conftest.py. The corrector and repetition-judge arms are
    #    gone (checked by what the fixture ARMS, structurally), and the premium-executor +
    #    faithfulness arm is byte-for-byte what it was before Track A touched the file.
    conftest_source = (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    conftest_tree = ast.parse(conftest_source)
    assert not _imported_modules(conftest_tree, "tests") & CORRECTOR_DELETED_MODULES, (
        "tests/conftest.py still imports a module A9 deleted."
    )
    armed = _money_guard_armed_pairs(conftest_tree)
    assert armed == set(EXPECTED_MONEY_GUARD_ARMS), (
        "tests/conftest.py's money-guard armed set drifted. "
        f"disarmed={sorted(set(EXPECTED_MONEY_GUARD_ARMS) - armed)} "
        f"unexpected={sorted(armed - set(EXPECTED_MONEY_GUARD_ARMS))}"
    )
    assert PREMIUM_FAITHFULNESS_ARM_SOURCE in conftest_source, (
        "AC-9: the premium-executor + faithfulness money-guard arm is no longer "
        "byte-identical. A9 removes the arms below it and must not reflow it."
    )

    # 5. AC-9(e), the whole clause: none of Track A's four provider hooks survives.
    deps_tree = ast.parse((REPO_ROOT / "src" / "api" / "dependencies.py").read_text("utf-8"))
    surviving = _public_top_level_names(deps_tree) & set(DEPENDENCIES_REMOVED_BY_TRACK_A)
    assert not surviving, (
        f"src/api/dependencies.py still defines {sorted(surviving)}; AC-9 requires them gone."
    )

    # 6. Dead scaffolding — the three eligibility functions that read the per-chapter
    #    composer's output. The typed rejection surface the preview route still returns
    #    must survive.
    #
    #    REVERSED 2026-07-31 (CF-4): this block used to also assert that
    #    ``Script.verify_report`` and ``StopVerifyStatus`` were DELETED, because D8 listed
    #    them as dead. A judge STOP falsified that premise by MEASUREMENT, 13/13: without
    #    them, 13 saved tours (9 Paris + 4 London) become unreadable and
    #    ``make score-saved-tours SCORE_ARGS="--city london"`` goes from scoring 4 tours to
    #    exit 1 — and the founding-case tour (pont-neuf-60min-5afc2e.json) is itself among
    #    the casualties. They are persisted in artifacts on disk, so "nothing populates it"
    #    was true of new output and false of the corpus we already have. The assertion is
    #    now the OPPOSITE: both must SURVIVE, so a future cleanup cannot silently re-delete
    #    them. Re-measured after the reversal: london 4, paris 191, make lint clean.
    contract_tree = ast.parse((REPO_ROOT / "src" / "tour" / "contract.py").read_text("utf-8"))
    contract_names = _public_top_level_names(contract_tree)
    still_needed = set(DEAD_CONTRACT_NAMES) - contract_names
    assert not still_needed, (
        f"src/tour/contract.py no longer defines {sorted(still_needed)}. Deleting these was "
        "MEASURED to make 13 saved tours unreadable and to break `make score-saved-tours "
        '--city london` (4 tours -> exit 1). See CF-4; do not re-delete them.'
    )
    assert DEAD_SCRIPT_FIELD in _class_field_names(contract_tree, "Script"), (
        f"src/tour/contract.py's Script no longer declares {DEAD_SCRIPT_FIELD!r}. It is read "
        "when re-reading tours already saved on disk; removing it breaks 13 of them (CF-4)."
    )
    elig_tree = ast.parse(
        (REPO_ROOT / "src" / "tour" / "candidate_eligibility.py").read_text("utf-8")
    )
    elig_names = _public_top_level_names(elig_tree)
    dead = elig_names & set(DEAD_ELIGIBILITY_FUNCTIONS)
    assert not dead, f"src/tour/candidate_eligibility.py still defines {sorted(dead)}."
    missing = set(SURVIVING_ELIGIBILITY_NAMES) - elig_names
    assert not missing, (
        f"A9 over-deleted: {sorted(missing)} must survive — the preview route returns them."
    )

    # 7. The permanently-empty advisory blocks are gone from the preview response, and the
    #    workbench no longer labels statuses/narrators no engine can produce.
    trips_tree = ast.parse((REPO_ROOT / "src" / "api" / "routes" / "trips.py").read_text("utf-8"))
    dead_keys = _string_constants(trips_tree) & set(DEAD_PREVIEW_RESPONSE_KEYS)
    assert not dead_keys, (
        f"src/api/routes/trips.py still builds {sorted(dead_keys)} — blocks that can only "
        "ever be empty now that the G4 judge and the omission checker are deleted."
    )
    review_html = (REPO_ROOT / "frontend" / "review.html").read_text(encoding="utf-8")
    stale_labels = [label for label in DEAD_WORKBENCH_LABELS if label in review_html]
    assert not stale_labels, (
        f"frontend/review.html still labels {stale_labels}, for engines Track A deleted."
    )


# ---- AC-12 — the unreferenced mobile audio surfaces are gone (unify-tour-algorithm, step 1)
#
# Two pieces of phone code were dead: an audio-player widget no screen ever put on the
# page (``mobile/lib/widgets/beat_audio_player.dart``) and a service method that called a
# server endpoint nobody called (``TripService.confirmTripAudio``). Both are deleted along
# with the tests that were their only users.
#
# This is a filesystem-and-text sweep over the Dart tree, not an ``ast`` walk, because
# Dart is not Python. It is hermetic: no fixture, no database, no provider.

#: Dart identifiers that must not survive anywhere under ``mobile/``. ``beat_audio_player``
#: catches prose cross-references to the deleted file as well as its import path.
# ---- unify-tour-algorithm step 6 — the legacy 0.83 planner is deleted ----------------
#
# Placed next to ``test_corrector_and_dark_g4_are_gone`` rather than at end-of-file, for
# the same reason step 4's guard sits next to the scoreboard one: concurrent lanes append
# here too.

#: Names that only ever existed to express the legacy flat 0.83 walk budget. A tour is
#: now planned at a nominal fraction of 1.00 on every surface, so each of these is a way
#: for a caller to reach a budget the product no longer has.
LEGACY_PLANNER_NAMES = frozenset(
    {
        "ERR_SHORT",
        "LEGACY_ROUTE_PLANNING_POLICY",
        "is_legacy",
        "smallest_duration_min_for_walk_seconds",
    }
)

#: Deleted FUNCTIONS whose names still exist as something else and so cannot go in the
#: set above. ``err_short_total_seconds`` survives as a FIELD on ``Route``
#: (src/tour/contract.py) that the quality rubric legitimately reads; what was deleted is
#: the module-level helper in ``routing`` that computed it from the flat 0.83.
LEGACY_PLANNER_FUNCTIONS = frozenset({"err_short_total_seconds"})

LEGACY_POLICY_ID = "legacy-err-short-v1"


def _src_python_files() -> list[pathlib.Path]:
    return [p for p in _python_files() if p.is_relative_to(REPO_ROOT / "src")]


def test_the_legacy_err_short_planner_is_gone() -> None:
    """AC-14 — one walk budget, and it is the certification one.

    Until 2026-08-04 the engine had two time currencies. The phone's
    ``/trips/generate`` planned on a flat 0.83 of the requested duration; the preview
    and the batch runner planned on the certification band 0.90-1.10, nominal 1.00. The
    same request therefore produced tours of materially different declared length
    depending on which door it came through. The 0.83 policy is deleted, not made
    optional, so there is nothing left to pass.

    This is a symbol-and-behaviour check, deliberately NOT a grep for the literal 0.83:
    the number is a fraction, and a future unrelated 0.83 in a comment would fail a
    text search while proving nothing.

    UNDO (each turns this RED):
      * set both fractions of DEFAULT_ROUTE_PLANNING_POLICY to 0.83 -> assertions 1-5;
      * re-add LEGACY_ROUTE_PLANNING_POLICY, ``is_legacy``, or any single one of the
        seven ``is_legacy`` branches -> assertion 6;
      * point ``density._target_dwell_seconds`` back at a bare ERR_SHORT expression
        -> assertions 5 and 6;
      * drop ``planning_policy=planning_policy`` from selection's density call
        -> assertion 8.
    """
    import pytest

    from src.tour import density
    from src.tour.routing import (
        DEFAULT_ROUTE_PLANNING_POLICY,
        envelope_radius_m,
        route_planning_budget,
    )

    # 1-3. The 60-minute budget is the certification one on the DEFAULT path.
    budget = route_planning_budget(60)

    assert budget.dwell_target_seconds == 2160, "was 1793 under the legacy 0.83"
    assert budget.walk_budget_seconds == 1440, "was 1195 under the legacy 0.83"

    # 4. The reachable walk envelope follows it.
    assert envelope_radius_m(60, round_trip=False) == pytest.approx(888.9, rel=1e-3)

    # 5. THE Q2 EQUALITY: the tourability gate and the planner speak one number. This
    #    was the real defect behind the split — density's radius would have followed the
    #    new policy while its audio target stayed a bare 0.83 expression, so the gate
    #    would read GREEN on a pool holding barely half the audio the planner then tried
    #    to fill: a thin tour served as healthy.
    assert (
        density._target_dwell_seconds(60, DEFAULT_ROUTE_PLANNING_POLICY)
        == budget.dwell_target_seconds
    )

    # 6. STRUCTURAL: none of the legacy names, and no legacy policy id, survives in src/.
    offenders: dict[str, set[str]] = {}
    for path in _src_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        named = (
            {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
            | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
            | {
                alias.name
                for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom)
                for alias in n.names
            }
            | {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        )
        hit = named & LEGACY_PLANNER_NAMES
        if any(
            isinstance(n, ast.Constant) and n.value == LEGACY_POLICY_ID
            for n in ast.walk(tree)
        ):
            hit = hit | {LEGACY_POLICY_ID}
        if hit:
            offenders[path.relative_to(REPO_ROOT).as_posix()] = hit
    assert not offenders, (
        f"a legacy flat-0.83 planning symbol survives in src/: {offenders}"
    )

    # 6b. And the deleted helpers are not merely unreferenced — they are gone. A
    #     surviving definition with no caller is a door left open.
    defined_functions: dict[str, set[str]] = {}
    for path in _src_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hit = {
            n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
        } & LEGACY_PLANNER_FUNCTIONS
        if hit:
            defined_functions[path.relative_to(REPO_ROOT).as_posix()] = hit
    assert not defined_functions, (
        f"a legacy flat-0.83 helper is still DEFINED in src/: {defined_functions}"
    )

    # 7. AC-14's default clause: every RoutePlanningPolicy parameter either requires an
    #    explicit policy or defaults to the certification one. A parameter that could
    #    default to anything else is how the second currency came back last time.
    bad_defaults: dict[str, list[str]] = {}
    for path in _src_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            args = node.args
            positional = args.posonlyargs + args.args
            pairs = list(
                zip(positional[len(positional) - len(args.defaults) :], args.defaults, strict=True)
            ) + [
                (a, d)
                for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=True)
                if d is not None
            ]
            for arg, default in pairs:
                annotation = ast.unparse(arg.annotation) if arg.annotation else ""
                if "RoutePlanningPolicy" not in annotation:
                    continue
                rendered = ast.unparse(default)
                if rendered not in ("None", "DEFAULT_ROUTE_PLANNING_POLICY"):
                    bad_defaults.setdefault(
                        path.relative_to(REPO_ROOT).as_posix(), []
                    ).append(f"{node.name}({arg.arg}={rendered})")
    assert not bad_defaults, (
        f"a planning-policy parameter defaults to something other than the "
        f"certification policy: {bad_defaults}"
    )

    # 8. BEHAVIOURAL, and the remedy for the one change assertion 6 cannot bind: the
    #    policy is really THREADED from select_route into the density gate, not merely
    #    matching by shared default. A deliberately non-default policy must move the
    #    number the gate reports.
    from src.tour import selection
    from src.tour.contract import TourInput
    from src.tour.routing import RoutePlanningPolicy
    from tests.test_tour_selection import _poi, _snap

    pdv = (48.85675, 2.341033)
    pois = [
        _poi(f"q{i:02d}", tier=5, lat=pdv[0] + (i % 5) * 0.0004, lng=pdv[1] + (i // 5) * 0.0004)
        for i in range(12)
    ]
    # Nominal fraction (0.1 + 0.9) / 2 = 0.5, deliberately unlike the certification
    # default's 1.00, so a gate that quietly used its own default is visible. The band
    # is wide so the request is not refused for a TIME reason before it can answer the
    # currency question.
    half = RoutePlanningPolicy.certification(
        minimum_requested_fraction=0.1,
        maximum_requested_fraction=0.9,
        policy_id="test-half-nominal",
    )
    assert density._target_dwell_seconds(60, half) != density._target_dwell_seconds(
        60, DEFAULT_ROUTE_PLANNING_POLICY
    ), "the fixture policy is indistinguishable from the default; it proves nothing"

    # A SPY rather than an assertion on the route: ``Route.tourability`` is None for
    # every GREEN tour by design, so reading the number back off the route would be
    # vacuous on any fixture healthy enough to plan.
    seen: list[object] = []
    real_assess = selection.assess_tourability

    def _spy(tour_input, snapshot, **kwargs):
        seen.append(kwargs.get("planning_policy"))
        return real_assess(tour_input, snapshot, **kwargs)

    selection.assess_tourability = _spy
    try:
        selection.select_route(
            TourInput(start=pdv, duration_min=60, city_slug="paris"),
            _snap(pois),
            planning_policy=half,
        )
    finally:
        selection.assess_tourability = real_assess
    assert seen == [half], (
        "select_route did not hand its planning policy to the density gate, so the "
        f"tourability verdict and the plan are priced in different currencies: {seen}"
    )


def _minimal_assessment():
    """The smallest valid TourabilityAssessment — context only, nothing asserted on it."""
    from src.tour.contract import TourabilityAssessment

    return TourabilityAssessment(
        status="RED",
        walk_radius_m=100.0,
        fill_ratio=0.1,
        dwell_capacity_seconds=10,
        target_dwell_seconds=100,
        reachable_poi_count=0,
        reachable_beat_count=0,
        anchor_candidate_count=0,
        cluster_compactness=0.0,
        duration_min=60,
        round_trip=False,
    )


def test_a_band_refusal_reaches_both_surfaces_with_alternatives() -> None:
    """q3 — a request that cannot fit its time band is a refusal, not a crash.

    Two defects, both landed with step 6's branch collapse. Making the timebox repair
    run for EVERY route shape put ``CertificationPlanningInfeasibleError`` onto the
    phone's ``POST /trips/generate`` for the first time, and that route caught only
    ``TourabilityRefusedError`` — so a traveller whose walk simply did not fit got a 500
    with a stack trace. Separately the preview's handler emitted the literal internal
    identifier ``premium_route_infeasible`` as its ``reason``, and the workbench renders
    ``detail.reason`` straight onto the page, so an operator was shown a symbol.

    UNDO (each turns this RED):
      * drop ``alternatives``/``gap_minutes`` from CertificationPlanningInfeasibleError
        -> assertion 1;
      * narrow the generate route's except back to TourabilityRefusedError alone
        -> assertion 3;
      * restore ``"reason": "premium_route_infeasible"`` -> assertion 4.
    """
    import re

    from src.api.routes.trips import _refusal_detail
    from src.tour.contract import TourInput
    from src.tour.density import FeasibilityAlternative, TourabilityRefusedError
    from src.tour.routing import DEFAULT_ROUTE_PLANNING_POLICY
    from src.tour.selection import CertificationPlanningInfeasibleError, _band_alternatives

    # 1. The band refusal carries the SAME payload a fixed-destination refusal does.
    tour_input = TourInput(start=(48.8567, 2.3410), duration_min=60, city_slug="paris")
    alternatives, gap_minutes = _band_alternatives(
        input=tour_input,
        planning_policy=DEFAULT_ROUTE_PLANNING_POLICY,
        best_elapsed_seconds=7200,
    )
    exc = CertificationPlanningInfeasibleError(
        policy_id="certification-nominal-v1",
        minimum_elapsed_seconds=3240,
        maximum_elapsed_seconds=3960,
        best_elapsed_seconds=7200,
        reason="post-selection transforms moved the exact route outside the band",
        alternatives=alternatives,
        gap_minutes=gap_minutes,
    )
    detail = _refusal_detail(exc)
    assert detail["cause"] == "time_budget"
    assert isinstance(detail["reason"], str) and detail["reason"]
    assert detail["gap_minutes"] == 54, detail
    assert [a["kind"] for a in detail["alternatives"]] == ["extend"], detail
    assert detail["alternatives"][0]["duration_min"] > tour_input.duration_min

    # 2. The density refusal's shape is preserved byte-for-byte beside it.
    density_detail = _refusal_detail(
        TourabilityRefusedError(
            _minimal_assessment(),
            "nothing to see here",
            gap_minutes=7,
            alternatives=(
                FeasibilityAlternative(kind="loop", duration_min=60, drop_end=True),
            ),
        )
    )
    assert density_detail["cause"] == "tourability"
    assert density_detail["gap_minutes"] == 7
    assert [a["kind"] for a in density_detail["alternatives"]] == ["loop"]

    # 3. The phone's route catches BOTH, so neither escapes as a 500.
    trips_path = REPO_ROOT / "src" / "api" / "routes" / "trips.py"
    tree = ast.parse(trips_path.read_text(encoding="utf-8"), filename=str(trips_path))
    generate = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "generate_trip"
    )
    caught: set[str] = set()
    for handler in (h for n in ast.walk(generate) if isinstance(n, ast.Try) for h in n.handlers):
        if handler.type is None:
            continue
        for node in ast.walk(handler.type):
            if isinstance(node, ast.Name):
                caught.add(node.id)
    assert {"TourabilityRefusedError", "CertificationPlanningInfeasibleError"} <= caught, (
        f"generate_trip does not catch the band refusal, so it escapes as a 500: {caught}"
    )

    # 4. No REFUSAL body shows a human an identifier.
    #
    #    Scoped to bodies carrying an ``alternatives`` key, and that scope is the whole
    #    point rather than a convenience. The workbench renders ``detail.reason`` as
    #    prose on exactly one branch — the one it selects with
    #    ``Array.isArray(detail.alternatives)`` — so those bodies are read by a PERSON.
    #    Every other ``reason`` in this file (``already_composed``,
    #    ``compose_verification_failed``, ``build_fingerprint_unavailable`` …) is a
    #    machine-readable protocol code the phone branches on, and turning those into
    #    sentences would break the client, not help anyone.
    #
    #    THE BODY, WHEREVER IT IS BUILT. This used to look only INSIDE an
    #    ``HTTPException(...)`` call, and went vacuous the moment the refusal bodies
    #    moved into ``_refusal_detail`` / ``_infeasible_detail`` and the handlers began
    #    raising ``HTTPException(422, _refusal_detail(exc))``. Nothing about the
    #    product changed; the guard simply stopped being able to see its subject.
    #    Keying on the SHAPE of the body rather than on where it is written is both
    #    simpler and strictly wider: an inline dict and a helper's return value are the
    #    same thing on the wire, and a person reads whichever one arrives.
    identifier = re.compile(r"^[a-z][a-z0-9_]*$")
    leaked: list[str] = []
    rendered_bodies = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
        if "alternatives" not in keys:
            continue
        rendered_bodies += 1
        for key, value in zip(node.keys, node.values, strict=True):
            if not (isinstance(key, ast.Constant) and key.value == "reason"):
                continue
            if (
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and identifier.match(value.value)
            ):
                leaked.append(value.value)
    assert rendered_bodies, (
        "no body in trips.py carries an alternatives key any more, so this guard is "
        "watching nothing — re-derive it against the current handlers"
    )
    assert not leaked, (
        f"a refusal body a human surface renders puts an internal identifier in front "
        f"of a person instead of a sentence: {leaked}"
    )


DEAD_MOBILE_AUDIO_TOKENS = ("BeatAudioPlayer", "beat_audio_player")

#: The dead service method. The substring must be the WHOLE name: the live per-stop method
#: ``confirmTripStopAudio`` contains ``confirmTrip``, so a shorter needle would be a false
#: positive. ``"confirmTripAudio" in "confirmTripStopAudio"`` is False, so this is safe.
DEAD_MOBILE_SERVICE_METHOD = "confirmTripAudio"

#: Files deleted whole by this step. Checked on disk AND in git's index — a file removed
#: from disk but still tracked is not deleted.
DELETED_MOBILE_FILES = (
    "mobile/lib/widgets/beat_audio_player.dart",
    "mobile/test/widgets/beat_audio_player_test.dart",
)

#: Live neighbours of the deleted surfaces. These share a name-shape or a file with what
#: is being removed, so they are what an over-eager deletion takes with it.
SURVIVING_MOBILE_NEIGHBOURS = (
    ("mobile/lib/services/trip_service.dart", "confirmTripStopAudio"),
    ("mobile/lib/pages/trip_itinerary_page.dart", "checkAudioStatus"),
)


def _mentions(
    dart_files: list[pathlib.Path], needles: tuple[str, ...]
) -> dict[str, tuple[int, str]]:
    """Map ``repo-relative path`` -> ``(line number, matched needle)`` for every hit."""
    offenders: dict[str, tuple[int, str]] = {}
    for path in dart_files:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(lines, 1):
            hit = next((needle for needle in needles if needle in line), None)
            if hit is not None:
                offenders[str(path.relative_to(REPO_ROOT))] = (line_no, hit)
                break
    return offenders


def test_the_unreferenced_mobile_audio_surfaces_are_gone() -> None:
    # 1. Non-vacuity FIRST. A wrong root would make every absence assertion below pass
    #    for free, so prove the sweep actually reads Dart source before trusting it.
    mobile_lib = sorted((REPO_ROOT / "mobile" / "lib").rglob("*.dart"))
    mobile_test = sorted((REPO_ROOT / "mobile" / "test").rglob("*.dart"))
    assert mobile_lib, "mobile/lib has no .dart files; this sweep is vacuous."
    assert mobile_test, "mobile/test has no .dart files; this sweep is vacuous."
    dart_files = mobile_lib + mobile_test

    # 2/3. Both deleted files are gone from disk...
    on_disk = [f for f in DELETED_MOBILE_FILES if (REPO_ROOT / f).exists()]
    assert not on_disk, f"{on_disk} still exist on disk; step 1 deletes them outright."

    # ...and gone from git's index, so a `git rm --cached`-shaped half-deletion fails too.
    tracked = _tracked_files()
    still_tracked = [f for f in DELETED_MOBILE_FILES if f in tracked]
    assert not still_tracked, f"{still_tracked} are still tracked by git; `git rm` them."

    # 4. No surviving mention of the widget anywhere under mobile/ — code OR comment.
    widget_offenders = _mentions(dart_files, DEAD_MOBILE_AUDIO_TOKENS)
    assert not widget_offenders, (
        f"{widget_offenders} still mention the deleted audio-player widget "
        f"(path -> line number, matched text); AC-12 requires zero hits."
    )

    # 5. No surviving mention of the dead service method.
    method_offenders = _mentions(dart_files, (DEAD_MOBILE_SERVICE_METHOD,))
    assert not method_offenders, (
        f"{method_offenders} still mention {DEAD_MOBILE_SERVICE_METHOD}; "
        f"AC-12 requires zero hits."
    )

    # 6. Anti-over-deletion: the live neighbours must still be there. This is what stops a
    #    deletion that took the whole file, or the live per-stop method, from passing.
    missing = [
        f"{relative} no longer contains {symbol}"
        for relative, symbol in SURVIVING_MOBILE_NEIGHBOURS
        if symbol not in (REPO_ROOT / relative).read_text(encoding="utf-8")
    ]
    assert not missing, f"{missing}; step 1 removes only the two dead surfaces."
