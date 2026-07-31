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
