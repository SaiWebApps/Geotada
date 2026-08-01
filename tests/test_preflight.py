"""The prerequisite declarations are only worth what they are checked to be.

Three properties are guarded here, each with the mutation that turns it red:

1.  REGISTRY INTEGRITY -- every ``needs`` name resolves and the graph is acyclic.
    RED when: a requirement names a dependency that does not exist, or two
    requirements depend on each other.

2.  MAKEFILE COVERAGE -- every documented target declares its prerequisites, and
    every name it declares is a real requirement.  This is the check that catches
    the ordinary mistake: adding a target and forgetting the preflight line, or
    typing ``db-development``.
    RED when: a ``##``-documented target has no ``$(PREFLIGHT)`` line, or names a
    requirement the registry does not define.

3.  NO SILENT SUCCESS -- the property the old ``db-up`` violated.  A probe that
    cannot reach its dependency must report failure, and ``check`` must return
    non-zero.  A green run on a dead dependency is the exact bug this replaced.
    RED when: ``check`` returns 0 while a requirement's probe returns not-ok, or a
    requirement whose dependency failed is reported as satisfied.

Hermetic: no container, no database, no provider, no network.  The Makefile is
read as text and lexed with ``shlex``; nothing here starts anything.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAKEFILE = ROOT / "Makefile"
PREFLIGHT_PATH = ROOT / "scripts" / "preflight.py"


def _load_preflight():
    """Load preflight by path; it lives outside the importable package tree.

    The module must be registered in ``sys.modules`` BEFORE it executes:
    ``@dataclass`` resolves annotations through ``sys.modules[cls.__module__]``,
    which is None for a module that is mid-execution and unregistered.
    """
    name = "ondoway_preflight"
    spec = importlib.util.spec_from_file_location(name, PREFLIGHT_PATH)
    assert spec and spec.loader, "preflight module could not be located"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


preflight = _load_preflight()


# ── 1. registry integrity ────────────────────────────────────────────────────


def test_every_declared_dependency_exists():
    for name, requirement in preflight.REGISTRY.items():
        for dependency in requirement.needs:
            assert dependency in preflight.REGISTRY, (
                f"requirement {name!r} depends on {dependency!r}, which is not defined"
            )


def test_every_requirement_resolves_without_a_cycle():
    for name in preflight.REGISTRY:
        plan = preflight.resolve([name])
        assert plan[-1].name == name, f"{name} must be last in its own plan"
        satisfied: set = set()
        for requirement in plan:
            missing = set(requirement.needs) - satisfied
            assert not missing, f"{requirement.name} is ordered before {sorted(missing)}"
            satisfied.add(requirement.name)


def test_every_requirement_carries_an_instruction():
    """Whatever the repair does, a human must be told what to run if it fails.

    The instruction is the fallback for three real cases: the repair failed, the
    repair could not run unattended, or the developer set PREFLIGHT_AUTOFIX=0.
    """
    for name, requirement in preflight.REGISTRY.items():
        assert requirement.instruction.strip(), (
            f"{name!r} has no instruction, so a developer whose repair fails is "
            "told nothing actionable"
        )


# A requirement may only skip having a repair if a machine genuinely cannot be
# brought to that state without a human decision. The list is the argument: an
# empty one means every requirement can restore itself. Adding a name here is a
# claim that must be justified in the comment beside it.
REQUIREMENTS_THAT_CANNOT_SELF_REPAIR: dict = {}


def test_every_requirement_can_restore_itself():
    """Failing with advice is a last resort, not a design.

    Reporting a missing dependency and stopping pushes the work of knowing what
    this project needs onto the developer -- which is the friction the whole
    mechanism exists to remove. A new requirement that cannot fix itself has to
    say why, here.
    """
    missing = [
        name
        for name, requirement in preflight.REGISTRY.items()
        if requirement.repair is None and name not in REQUIREMENTS_THAT_CANNOT_SELF_REPAIR
    ]
    assert not missing, (
        "these requirements only report a failure instead of fixing it: "
        f"{sorted(missing)}. Give each a repair, or justify it in "
        "REQUIREMENTS_THAT_CANNOT_SELF_REPAIR."
    )


def test_an_interactive_repair_is_not_attempted_without_a_terminal(monkeypatch):
    """An unattended run must never block on a sign-in nobody can approve."""
    guided = preflight.Requirement(
        name="guided",
        summary="guided",
        probe=lambda: preflight.Probe(False, "absent"),
        repair=lambda: pytest.fail("an interactive repair ran with no terminal attached"),
        interactive=True,
        instruction="do it by hand",
    )
    silent = preflight.Requirement(
        name="silent",
        summary="silent",
        probe=lambda: preflight.Probe(False, "absent"),
        repair=lambda: preflight.Probe(True, "fixed"),
        instruction="do it by hand",
    )

    monkeypatch.setattr(preflight.sys.stdin, "isatty", lambda: False, raising=False)
    assert preflight._repair_is_possible(guided) is False
    assert preflight._repair_is_possible(silent) is True


def test_the_render_credential_accepts_an_environment_key_off_macos(monkeypatch):
    """A Keychain-only credential locks out every Linux and CI machine.

    scripts/dev_env.py reads RENDER_API_KEY as a fallback; the probe must agree,
    or preflight passes a target that then dies on a missing credential.
    """
    monkeypatch.setattr(preflight.sys, "platform", "linux")
    monkeypatch.delenv("RENDER_API_KEY", raising=False)
    assert preflight._probe_render_key().ok is False

    monkeypatch.setenv("RENDER_API_KEY", "not-a-real-key")
    result = preflight._probe_render_key()
    assert result.ok is True
    assert "not-a-real-key" not in result.detail, "a credential value must never be echoed"


def test_deploy_watching_declares_the_render_cli_it_shells_out_to():
    """The CLI is a separate dependency from the API key, and easy to miss.

    `.claude/hooks/render-deploy-watch.sh` runs `render deploys list`, which needs
    the CLI installed AND signed in through its own browser flow. Neither is the
    Keychain API key the rest of the project uses.
    """
    hook = (ROOT / ".claude" / "hooks" / "render-deploy-watch.sh").read_text(encoding="utf-8")
    assert "render deploys list" in hook, "this guard is pinned to a call that vanished"

    declared = _declared_requirements("render-watch") or []
    assert "render-cli" in declared
    assert "render-cli-auth" in declared


def test_database_specs_agree_with_the_committed_profiles():
    """The probe's port must match the profile the target actually executes under."""
    for spec in preflight.DATABASES:
        profile = preflight._read_profile(spec.profile)
        assert profile, f"profile {spec.profile!r} is missing or empty"
        assert profile.get("NEO4J_URI") == f"bolt://localhost:{spec.port}", (
            f"profile {spec.profile!r} does not point at the port preflight probes"
        )
        assert profile.get("NEO4J_PASSWORD"), (
            f"profile {spec.profile!r} has no password, so the readiness query cannot run"
        )


# ── 2. Makefile coverage ─────────────────────────────────────────────────────


def _makefile_lines() -> list[str]:
    return MAKEFILE.read_text(encoding="utf-8").splitlines()


def _documented_targets() -> list[str]:
    """Targets carrying a `## ` help string -- the ones `make help` advertises."""
    targets = []
    for line in _makefile_lines():
        if line.startswith((" ", "\t", "#")) or ":" not in line or "## " not in line:
            continue
        name = line.split(":", 1)[0].strip()
        if name and not name.startswith("."):
            targets.append(name)
    return targets


def _declared_requirements(target: str) -> list[str] | None:
    """What the target declares, read by the same code the tool itself uses.

    Deliberately not a second implementation: if this parsed the Makefile
    independently, the guard could pass against a reading of the file that
    differs from the one preflight acts on.
    """
    try:
        return preflight.declared_requirements(target)
    except KeyError as exc:
        pytest.fail(str(exc))


# Targets that legitimately declare nothing, and why:
#   they check or install the very prerequisites preflight knows about
#   (doctor, preflight, preflight-list, valhalla-build-tiles),
#   they touch only local files (help, clean, valhalla-status),
#   or they delegate wholly to another target that declares them (setup).
NO_PREREQUISITES = {
    "help",
    "doctor",
    "setup",
    "preflight",
    "preflight-list",
    "clean",
    "valhalla-status",
    "valhalla-build-tiles",
}


def test_delegating_targets_really_do_delegate():
    """A target may skip declaring only if it hands the whole job to one that does.

    Without this, adding a name to NO_PREREQUISITES is an unchecked way to opt a
    target out of the mechanism entirely.
    """
    body = MAKEFILE.read_text(encoding="utf-8").split("\nsetup:", 1)[1].split("\n\n", 1)[0]
    assert "bootstrap" in body, "setup no longer delegates to bootstrap"
    assert _declared_requirements("bootstrap"), "bootstrap itself declares nothing"


def test_every_documented_target_declares_its_prerequisites():
    undeclared = [
        target
        for target in _documented_targets()
        if target not in NO_PREREQUISITES and _declared_requirements(target) is None
    ]
    assert not undeclared, (
        "these targets run without declaring what they need, so they can fail "
        f"halfway through on a missing dependency: {undeclared}"
    )


def test_every_declared_name_is_a_real_requirement():
    unknown = {}
    for target in _documented_targets():
        names = _declared_requirements(target)
        if not names:
            continue
        bad = [name for name in names if name not in preflight.REGISTRY]
        if bad:
            unknown[target] = bad
    assert not unknown, f"targets naming requirements that do not exist: {unknown}"


def test_targets_needing_render_credentials_declare_them():
    """A target that fetches the Render environment must say so up front.

    Provider secrets live only on Render.  Without this, a fresh clone discovers
    the missing credential from a stack trace partway through the command.
    """
    lines = _makefile_lines()
    render_targets = []
    current = None
    for line in lines:
        if line and not line.startswith((" ", "\t", "#")) and ":" in line:
            name = line.split(":", 1)[0].strip()
            current = name if name and not name.startswith(".") else None
        elif current and line.startswith("\t") and "--render" not in line:
            for marker in ("RENDER_LOCAL_EXEC", "RENDER_TEST_EXEC", "CLOUD_EXEC"):
                if f"$({marker})" in line and current not in render_targets:
                    render_targets.append(current)

    assert render_targets, "no Render-backed targets found -- this guard would be vacuous"
    missing = [
        target
        for target in render_targets
        if "render-key" not in (_declared_requirements(target) or [])
    ]
    assert not missing, f"targets that fetch Render credentials without declaring them: {missing}"


# ── 3. no silent success ─────────────────────────────────────────────────────


def _requirement(name, *, ok, needs=(), repair=None):
    return preflight.Requirement(
        name=name,
        summary=name,
        probe=lambda: preflight.Probe(ok, "probed"),
        needs=needs,
        repair=repair,
        instruction="do the thing",
    )


@pytest.fixture
def isolated_registry(monkeypatch):
    registry: dict = {}
    monkeypatch.setattr(preflight, "REGISTRY", registry)
    return registry


def test_a_failed_probe_makes_check_fail(isolated_registry, capsys):
    isolated_registry["thing"] = _requirement("thing", ok=False)
    code = preflight.check(["thing"], autofix=False, label="unit", colour=False)
    output = capsys.readouterr().out

    assert code != 0, "a requirement that did not answer must not report success"
    # Assert the promise, not the banner's wording: name what is missing, and
    # tell the developer what to do about it. Pinning the exact headline made
    # this test fail on a pure rewording, which taught nobody anything.
    assert "thing" in output, "the failing requirement was not named"
    assert "do the thing" in output, "its instruction was not shown"


def test_a_satisfied_probe_makes_check_pass(isolated_registry):
    isolated_registry["thing"] = _requirement("thing", ok=True)
    assert preflight.check(["thing"], autofix=False, label="unit", colour=False) == 0


def test_a_dependent_is_never_reported_satisfied_when_its_dependency_failed(
    isolated_registry, capsys
):
    """The exact old bug: the daemon is down, yet the database reports ready."""
    isolated_registry["daemon"] = _requirement("daemon", ok=False)
    isolated_registry["database"] = _requirement("database", ok=True, needs=("daemon",))

    code = preflight.check(["database"], autofix=False, label="unit", colour=False)
    output = capsys.readouterr().out

    assert code != 0
    assert "skipped" in output, "a dependent must be skipped, not probed, after a failed dependency"
    assert "OK  database" not in output, "the database must never be reported ready here"


def test_a_repair_that_does_not_work_is_reported_as_failure(isolated_registry):
    """A repair claims nothing on its own -- only its re-probe can pass the check."""
    isolated_registry["thing"] = _requirement(
        "thing", ok=False, repair=lambda: preflight.Probe(False, "still broken")
    )
    assert preflight.check(["thing"], autofix=True, label="unit", colour=False) != 0


def test_a_repair_that_works_passes(isolated_registry):
    isolated_registry["thing"] = _requirement(
        "thing", ok=False, repair=lambda: preflight.Probe(True, "started")
    )
    assert preflight.check(["thing"], autofix=True, label="unit", colour=False) == 0


def test_the_diagnostic_reports_gaps_without_failing(isolated_registry, capsys):
    """`make doctor` on a fresh clone must not look like a broken tool.

    A clone is MEANT to be missing things. If the first command a new developer
    runs exits non-zero and prints FAILED, the honest report reads as breakage --
    friction created by the thing meant to remove it.
    """
    isolated_registry["thing"] = _requirement("thing", ok=False)
    code = preflight.check(
        ["thing"], autofix=False, label="this machine", colour=False, report_only=True
    )
    output = capsys.readouterr().out

    assert code == 0, "a diagnostic must not fail merely because something is missing"
    assert "1 of 1 prerequisites are missing" in output
    assert "make setup" in output, "the report must name the command that fixes it"
    assert "FAILED" not in output


def test_a_real_target_still_refuses_when_something_is_missing(isolated_registry):
    """The diagnostic's leniency must not leak into targets that do work."""
    isolated_registry["thing"] = _requirement("thing", ok=False)
    assert preflight.check(["thing"], autofix=False, label="workbench", colour=False) == 1


def test_an_interrupted_map_download_leaves_no_usable_looking_file(monkeypatch, tmp_path):
    """A truncated extract must never be mistaken for a complete one.

    The tile build would consume a half-downloaded file happily and produce a
    quietly wrong road network. So the download goes to a temporary name and is
    moved into place only on success -- and a failure cleans up after itself.
    """
    tiles = tmp_path / "custom_files"
    tiles.mkdir()
    monkeypatch.setattr(preflight, "_tile_directory", lambda: tiles)

    def failing_curl(argv, **kwargs):
        destination = Path(argv[argv.index("-o") + 1])
        destination.write_bytes(b"half a file")  # what curl leaves behind
        return 1

    monkeypatch.setattr(preflight, "_stream", failing_curl)
    result = preflight._repair_valhalla_tiles()

    assert result.ok is False
    assert not list(tiles.glob("*.osm.pbf")), "a failed download left an extract behind"
    assert not list(tiles.glob("*.partial")), "the temporary file was not cleaned up"


def test_a_completed_map_download_is_moved_into_place(monkeypatch, tmp_path):
    tiles = tmp_path / "custom_files"
    tiles.mkdir()
    monkeypatch.setattr(preflight, "_tile_directory", lambda: tiles)

    def working_curl(argv, **kwargs):
        Path(argv[argv.index("-o") + 1]).write_bytes(b"a whole extract")
        return 0

    monkeypatch.setattr(preflight, "_stream", working_curl)
    result = preflight._repair_valhalla_tiles()

    assert result.ok is True, result.detail
    names = sorted(p.name for p in tiles.glob("*.osm.pbf"))
    assert names == sorted(name for name, _ in preflight.OSM_EXTRACTS)
    assert not list(tiles.glob("*.partial"))


def test_the_diagnostic_says_so_when_nothing_is_missing(isolated_registry, capsys):
    isolated_registry["thing"] = _requirement("thing", ok=True)
    code = preflight.check(
        ["thing"], autofix=False, label="this machine", colour=False, report_only=True
    )
    assert code == 0
    assert "Everything this project needs is present." in capsys.readouterr().out


def test_an_unknown_requirement_is_rejected_rather_than_ignored(isolated_registry):
    with pytest.raises(SystemExit):
        preflight.resolve(["no-such-requirement"])


def test_an_unanswerable_docker_query_is_not_reported_as_a_missing_container(monkeypatch):
    """"I could not ask" and "it is not there" are different answers.

    Measured 2026-07-31: under a burst of rapid checks one `docker ps` failed
    while the container had been up 36 hours. Collapsing that into False called a
    healthy database missing -- which would refuse a target, or restart
    containers that were fine.
    """
    monkeypatch.setattr(
        preflight,
        "_run",
        lambda *a, **k: subprocess.CompletedProcess([], returncode=1, stdout="", stderr="boom"),
    )
    monkeypatch.setattr(preflight.time, "sleep", lambda _: None)
    assert preflight._container_running("ondoway-neo4j") is None


def test_a_present_container_is_still_reported_present(monkeypatch):
    """The retry must not mask a genuine answer in either direction."""
    listing = '{"Names":"ondoway-neo4j","State":"running"}\n'
    monkeypatch.setattr(
        preflight,
        "_run",
        lambda *a, **k: subprocess.CompletedProcess([], returncode=0, stdout=listing, stderr=""),
    )
    assert preflight._container_running("ondoway-neo4j") is True
    assert preflight._container_running("ondoway-neo4j-test") is False


# ── the module must stay runnable on the system interpreter ──────────────────


def test_preflight_runs_on_the_system_interpreter():
    """It must report a missing toolchain on a machine that has nothing set up.

    That means it cannot depend on the project's own virtual environment.  This
    executes it with the interpreter Make actually invokes.
    """
    result = subprocess.run(
        ["python3", str(PREFLIGHT_PATH), "--list"],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, f"preflight failed under python3:\n{result.stderr}"
    assert "docker-daemon" in result.stdout, "the requirement table did not render"
