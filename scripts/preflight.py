"""Declared prerequisites for every Make target: probe, repair, or refuse.

Each supported target names the exact capabilities it needs.  This module turns
that list into a dependency-ordered plan, PROBES every capability for real -- a
live Cypher query, a health endpoint, an installed executable, a parsed JSON
status document -- repairs the ones it is allowed to repair, and exits non-zero
naming the exact command for the ones it cannot.

Two properties are load-bearing.

First, a probe never infers success from another command's silence.  The recipe
this replaced printed "neo4j ready at bolt://localhost:7687" and exited 0 with
the Docker daemon down, because its success message was simply the last
statement in a chain that ignored three failures.  Every probe here reports the
evidence it actually observed, and a repair re-probes before claiming anything.

Second, this file runs on the SYSTEM interpreter and imports only the standard
library, because the first thing it may have to report is that the project
interpreter does not exist yet.  Keep it runnable on Python 3.9: annotations are
postponed via ``__future__`` (so ``X | None`` is only ever a string here) and no
3.10+ runtime syntax may appear.  Nested same-quote f-strings are 3.12+; avoid
them.

Structural parsing only -- ``json.loads`` on ``--json`` output, ``Path.exists``,
exit codes.  Never match text out of another tool's human-readable output.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent
PROFILE_DIR = ROOT / "config" / "profiles"
COMPOSE_FILE = ROOT / "docker-compose.yml"
MAKEFILE = ROOT / "Makefile"

KEYCHAIN_SERVICE = "ondoway-render-api-key"
RENDER_API_KEY_URL = "https://dashboard.render.com/u/settings?add-api-key="
VALHALLA_STATUS_URL = "http://localhost:8002/status"
PLAYWRIGHT_CACHE = Path.home() / "Library" / "Caches" / "ms-playwright"

# The Colima VM is shared by three Neo4j services and Valhalla's tile load.
# Measured 2026-07-02: a smaller VM let dockerd die mid-gate.  Below this figure
# preflight warns; it never fails, because the sizing may be a deliberate call.
MIN_COLIMA_MEMORY_BYTES = 8 * 1024**3
COLIMA_MEMORY_GIB = 8
COLIMA_CPUS = 4

DAEMON_WAIT_SECONDS = 180
DATABASE_WAIT_SECONDS = 180
VALHALLA_WAIT_SECONDS = 600


class Probe(NamedTuple):
    """One observation: did the capability answer, and what proved it."""

    ok: bool
    detail: str


@dataclass(frozen=True)
class Requirement:
    """A capability a Make target can declare, with how to verify and restore it.

    ``repair`` is expected to exist wherever a machine can honestly be brought to
    the required state without a human decision.  Reporting a missing dependency
    and stopping is a last resort, not a design: it makes the developer research
    what the build already knows.

    ``announce`` marks a repair that costs real time or disk (a large download, a
    toolchain install).  It is still performed automatically -- it just says what
    it is about to spend first, so a long wait is never a mystery.

    ``interactive`` marks a repair that needs a human at the keyboard: pasting a
    credential, approving a browser sign-in.  With no terminal attached the
    repair is skipped and the instruction is printed instead, so an automated
    run can never hang waiting for input nobody can give.
    """

    name: str
    summary: str
    probe: Callable[[], Probe]
    needs: tuple = ()
    repair: Callable[[], Probe] | None = None
    instruction: str = ""
    announce: str = ""
    interactive: bool = False


class DatabaseSpec(NamedTuple):
    key: str
    profile: str
    service: str
    container: str
    port: int


# Keyed by the DB= value the Makefile accepts.  The password is deliberately not
# duplicated here: it is read from the committed profile the target will execute
# under, so a profile edit cannot silently desynchronise from the probe.
DATABASES = (
    DatabaseSpec("dev", "local", "neo4j", "ondoway-neo4j", 7687),
    DatabaseSpec("test", "test", "neo4j-test", "ondoway-neo4j-test", 7688),
    DatabaseSpec("workbench", "workbench", "neo4j-workbench", "ondoway-neo4j-workbench", 7689),
)
DATABASE_BY_KEY = {spec.key: spec for spec in DATABASES}


# ── process helpers ──────────────────────────────────────────────────────────


def _run(
    argv: Sequence[str],
    *,
    timeout: int | None = 60,
    env: dict | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, capture everything, and never raise on a non-zero exit."""
    try:
        return subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
            cwd=str(cwd) if cwd else None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(list(argv), returncode=127, stdout="", stderr=str(exc))


def _stream(argv: Sequence[str], *, cwd: Path | None = None) -> int:
    """Run a command with its output visible; a repair is never silent."""
    try:
        return subprocess.run(list(argv), check=False, cwd=str(cwd) if cwd else None).returncode
    except OSError as exc:
        print(f"    {exc}", file=sys.stderr)
        return 127


def _venv_python() -> Path:
    return ROOT / ".venv" / "bin" / "python"


def _compose(*args: str) -> list:
    return ["docker", "compose", "-f", str(COMPOSE_FILE), "--project-directory", str(ROOT), *args]


def _valhalla_root() -> Path:
    """The main checkout, even from a worktree -- where the tiles physically live.

    Mirrors the Makefile's VALHALLA_ROOT so a worktree can never start a second
    routing engine against an empty tile directory.
    """
    result = _run(["git", "rev-parse", "--git-common-dir"], cwd=ROOT, timeout=15)
    if result.returncode != 0:
        return ROOT
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = (ROOT / common).resolve()
    return common.parent


def _read_profile(name: str) -> dict:
    """Load one committed non-secret profile as KEY=VALUE pairs."""
    path = PROFILE_DIR / name
    values: dict = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _http_ok(url: str, timeout: int = 3) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # localhost only
            return 200 <= response.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _wait_for(check_fn: Callable[[], bool], seconds: int, *, interval: float = 2.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check_fn():
            return True
        time.sleep(interval)
    return check_fn()


# ── toolchain ────────────────────────────────────────────────────────────────


def _brew() -> str | None:
    return shutil.which("brew")


# Where installers drop binaries.  Used ONLY to explain an install that landed
# somewhere the developer's PATH does not reach -- never to widen the PATH a
# probe searches.  A probe must see exactly what the Make recipe will see: if it
# searched extra directories, it could report a tool present that the recipe then
# fails to run, which is the same false green this file exists to eliminate.
INSTALL_DIRECTORIES = (
    Path.home() / ".local" / "bin",
    Path.home() / ".cargo" / "bin",
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
)


def _installed_off_path(tool: str) -> Path | None:
    """Find a tool that exists on disk but is not reachable through PATH."""
    if shutil.which(tool):
        return None
    for directory in INSTALL_DIRECTORIES:
        candidate = directory / tool
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _after_install(tool: str, probe: Callable[[], Probe]) -> Probe:
    """Re-probe once an installer has run, and be precise about a PATH miss."""
    result = probe()
    if result.ok:
        return result
    stray = _installed_off_path(tool)
    if stray is not None:
        return Probe(
            False,
            f"installed to {stray.parent}, which is not on your PATH -- add it "
            "(or open a new shell) and repeat the command",
        )
    return result


def _probe_uv() -> Probe:
    if not shutil.which("uv"):
        return Probe(False, "not on PATH")
    result = _run(["uv", "--version"], timeout=20)
    if result.returncode != 0:
        return Probe(False, "installed but not runnable")
    return Probe(True, result.stdout.strip() or "installed")


def _repair_uv() -> Probe:
    if _brew():
        print("    -> brew install uv")
        _stream(["brew", "install", "uv"])
    else:
        print("    -> curl -LsSf https://astral.sh/uv/install.sh | sh")
        _stream(["/bin/sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"])
    return _after_install("uv", _probe_uv)


REQUIRED_MODULES = ("neo4j", "fastapi", "httpx", "anthropic", "pytest", "playwright")


# Locate the distributions rather than importing them.  `make lint` runs in a
# tight edit loop, and importing this set costs seconds; find_spec answers the
# only question that matters -- is it installed -- in one interpreter start.
_DEPENDENCY_SCRIPT = """
import importlib.util, platform, sys
missing = [m for m in {modules!r} if importlib.util.find_spec(m) is None]
if missing:
    sys.stdout.write("MISSING:" + ",".join(missing))
else:
    sys.stdout.write("OK:" + platform.python_version())
"""


def _probe_python_deps() -> Probe:
    python = _venv_python()
    if not python.is_file():
        return Probe(False, "no .venv")
    script = _DEPENDENCY_SCRIPT.format(modules=list(REQUIRED_MODULES))
    result = _run([str(python), "-c", script], timeout=120)
    answer = result.stdout.strip()
    if result.returncode != 0 or not answer:
        return Probe(False, "the project interpreter could not be queried")
    label, _, payload = answer.partition(":")
    if label != "OK":
        return Probe(False, f"packages not installed: {payload}")
    if not (ROOT / ".venv" / "bin" / "ruff").is_file():
        return Probe(False, "ruff missing (the dev extra is not installed)")
    return Probe(True, f"Python {payload}")


def _repair_python_deps() -> Probe:
    print("    -> uv sync --extra test --extra dev --extra aws")
    if _stream(["uv", "sync", "--extra", "test", "--extra", "dev", "--extra", "aws"], cwd=ROOT):
        return Probe(False, "uv sync failed -- see the output above")
    return _probe_python_deps()


def _probe_docker_cli() -> Probe:
    if not shutil.which("docker"):
        return Probe(False, "not on PATH")
    result = _run(["docker", "compose", "version", "--short"], timeout=30)
    if result.returncode != 0:
        return Probe(False, "docker is present but Compose v2 is missing")
    return Probe(True, "compose " + (result.stdout.strip() or "v2"))


def _repair_docker_cli() -> Probe:
    if not _brew():
        return Probe(False, "Homebrew is not installed, so this cannot be installed for you")
    print("    -> brew install colima docker docker-compose")
    _stream(["brew", "install", "colima", "docker", "docker-compose"])
    return _after_install("docker", _probe_docker_cli)


def _probe_docker_daemon() -> Probe:
    result = _run(["docker", "info", "--format", "{{json .ServerVersion}}"], timeout=30)
    if result.returncode != 0:
        return Probe(False, "daemon not responding")
    try:
        version = json.loads(result.stdout.strip() or '""')
    except json.JSONDecodeError:
        version = ""
    return Probe(True, f"engine {version}" if version else "responding")


def _colima_profiles() -> list:
    """Parse ``colima list --json`` -- one JSON document per line."""
    if not shutil.which("colima"):
        return []
    result = _run(["colima", "list", "--json"], timeout=30)
    if result.returncode != 0:
        return []
    profiles = []
    for line in result.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            entry = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            profiles.append(entry)
    return profiles


def _repair_docker_daemon() -> Probe:
    profiles = _colima_profiles()
    if profiles:
        stopped = [p for p in profiles if p.get("status") != "Running"]
        target = stopped[0] if stopped else profiles[0]
        name = str(target.get("name", "default"))
        print(f"    -> colima start {name}   (existing VM; its own sizing is reused)")
        _stream(["colima", "start", name])
    elif shutil.which("colima"):
        # No VM exists yet.  The hazard was never "create a VM", it was Colima's
        # small DEFAULT sizing: three Neo4j services plus a Valhalla tile load
        # killed dockerd once at that size (2026-07-02).  Naming the sizing
        # removes the hazard, so create it rather than sending the developer away
        # to find a number this file already knows.
        print(f"    -> colima start --cpu {COLIMA_CPUS} --memory {COLIMA_MEMORY_GIB}")
        print("       (no Colima VM existed; creating one sized for this project)")
        _stream([
            "colima", "start",
            "--cpu", str(COLIMA_CPUS),
            "--memory", str(COLIMA_MEMORY_GIB),
        ])
    elif sys.platform == "darwin" and Path("/Applications/Docker.app").exists():
        print("    -> open -a Docker")
        _stream(["open", "-a", "Docker"])
    else:
        return Probe(False, "no Docker Desktop or Colima installation found")

    print("    waiting for the Docker daemon...")
    if not _wait_for(lambda: _probe_docker_daemon().ok, DAEMON_WAIT_SECONDS):
        return Probe(False, f"daemon did not come up within {DAEMON_WAIT_SECONDS}s")
    return _probe_docker_daemon()


def _colima_memory_warnings() -> list:
    warnings = []
    for profile in _colima_profiles():
        memory = profile.get("memory")
        if isinstance(memory, int) and memory < MIN_COLIMA_MEMORY_BYTES:
            name = profile.get("name", "default")
            gib = memory / 1024**3
            warnings.append(
                f"Colima VM {name} has {gib:.1f} GiB; this project assumes 8 GiB "
                "(three Neo4j services plus Valhalla). Resize with: "
                "colima stop && colima start --memory 8"
            )
    return warnings


# ── databases ────────────────────────────────────────────────────────────────


def _container_running(container: str, *, attempts: int = 3) -> bool | None:
    """Is this exact container running?  None means Docker could not be asked.

    The three-way answer is the point.  Collapsing a failed query into False
    reports a healthy container as missing -- the mirror of the bug this file
    exists to prevent, and just as misleading. Measured: under a burst of rapid
    checks a single `docker ps` failed while the container had been up 36 hours,
    and a two-state answer called that a stopped database.
    """
    for attempt in range(attempts):
        result = _run(["docker", "ps", "--format", "{{json .}}"], timeout=30)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                text = line.strip()
                if not text:
                    continue
                try:
                    entry = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict) and entry.get("Names") == container:
                    return True
            return False
        if attempt + 1 < attempts:
            time.sleep(1.0)
    return None


def _cypher_answers(spec: DatabaseSpec) -> bool:
    """Run a real query inside the container -- the only honest readiness test."""
    password = _read_profile(spec.profile).get("NEO4J_PASSWORD", "")
    if not password:
        return False
    result = _run(
        _compose(
            "exec", "-T", spec.service,
            "cypher-shell", "-u", "neo4j", "-p", password, "RETURN 1",
        ),
        timeout=30,
    )
    return result.returncode == 0


def _probe_database(spec: DatabaseSpec) -> Callable[[], Probe]:
    def probe() -> Probe:
        profile = _read_profile(spec.profile)
        expected = f"bolt://localhost:{spec.port}"
        configured = profile.get("NEO4J_URI", "")
        if configured != expected:
            return Probe(
                False,
                f"profile {spec.profile} points at {configured!r}, not {expected}",
            )
        # Ask the database itself first: a successful query is proof, and it
        # cannot be undone by a flaky `docker ps`. The container state is only
        # consulted to explain a failure, never to declare one.
        if _cypher_answers(spec):
            return Probe(True, f"{expected} answering")
        running = _container_running(spec.container)
        if running is None:
            return Probe(False, "Docker did not answer, so the graph's state is unknown")
        if not running:
            return Probe(False, f"container {spec.container} is not running")
        return Probe(False, "container is up but Neo4j is not answering queries")

    return probe


def _repair_database(spec: DatabaseSpec) -> Callable[[], Probe]:
    def repair() -> Probe:
        print(f"    -> docker compose up -d {spec.service}")
        if _stream(_compose("up", "-d", spec.service), cwd=ROOT):
            return Probe(False, f"compose could not start {spec.service}")
        print(f"    waiting for Neo4j on port {spec.port} to answer a query...")
        if not _wait_for(lambda: _cypher_answers(spec), DATABASE_WAIT_SECONDS):
            return Probe(
                False,
                f"{spec.service} never answered within {DATABASE_WAIT_SECONDS}s -- "
                f"check: docker compose logs {spec.service}",
            )
        return _probe_database(spec)()

    return repair


# ── dev data ─────────────────────────────────────────────────────────────────


def _local_profile_env() -> dict:
    env = dict(os.environ)
    env.update(_read_profile("local"))
    return env


def _probe_dev_data() -> Probe:
    python = _venv_python()
    if not python.is_file():
        return Probe(False, "no .venv")
    result = _run(
        [str(python), "-m", "scripts.db_parity"],
        timeout=300,
        env=_local_profile_env(),
        cwd=ROOT,
    )
    if result.returncode != 0:
        return Probe(False, "dev graph does not match the committed city data")
    return Probe(True, "dev graph matches the committed city data")


def _repair_dev_data() -> Probe:
    print("    -> scripts/ensure_dev_data.py   (WRITES to the shared dev graph on 7687)")
    if _stream([str(_venv_python()), "scripts/ensure_dev_data.py"], cwd=ROOT):
        return Probe(False, "provisioning failed -- see the output above")
    return _probe_dev_data()


# ── routing ──────────────────────────────────────────────────────────────────


def _tile_directory() -> Path:
    return _valhalla_root() / "valhalla" / "custom_files"


def _probe_valhalla_tiles() -> Probe:
    tiles = _tile_directory()
    if (tiles / "valhalla_tiles.tar").is_file():
        return Probe(True, "valhalla_tiles.tar present")
    if (tiles / "valhalla_tiles").is_dir() and any((tiles / "valhalla_tiles").iterdir()):
        return Probe(True, "valhalla_tiles/ populated")
    extracts = sorted(tiles.glob("*.osm.pbf")) if tiles.is_dir() else []
    if extracts:
        return Probe(True, f"{len(extracts)} OSM extract(s); tiles build on first start")
    return Probe(False, f"no map data in {tiles}")


OSM_EXTRACTS = (
    (
        "ile-de-france-latest.osm.pbf",
        "https://download.geofabrik.de/europe/france/ile-de-france-latest.osm.pbf",
    ),
    (
        "new-york.osm.pbf",
        "https://download.bbbike.org/osm/bbbike/NewYork/NewYork.osm.pbf",
    ),
)


def _repair_valhalla_tiles() -> Probe:
    """Download the OSM extracts the routing engine builds its tiles from.

    Written to a temporary name and moved into place only on success, so an
    interrupted download can never leave a truncated extract that the tile build
    would then happily consume.
    """
    tiles = _tile_directory()
    tiles.mkdir(parents=True, exist_ok=True)
    for filename, url in OSM_EXTRACTS:
        target = tiles / filename
        if target.is_file() and target.stat().st_size > 0:
            print(f"    {filename} already present")
            continue
        partial = tiles / (filename + ".partial")
        print(f"    -> downloading {filename}")
        if _stream(["curl", "-L", "--fail", "-o", str(partial), url]):
            partial.unlink(missing_ok=True)
            return Probe(False, f"could not download {filename}")
        partial.replace(target)
    return _probe_valhalla_tiles()


def _probe_valhalla() -> Probe:
    if not _http_ok(VALHALLA_STATUS_URL):
        return Probe(False, "no healthy routing endpoint on :8002")
    return Probe(True, "healthy on :8002")


def _repair_valhalla() -> Probe:
    root = _valhalla_root()
    print("    -> docker compose up -d valhalla")
    started = _stream(
        [
            "docker", "compose",
            "-f", str(root / "docker-compose.yml"),
            "--project-directory", str(root),
            "up", "-d", "valhalla",
        ],
        cwd=root,
    )
    if started:
        return Probe(False, "compose could not start valhalla")
    print("    waiting for the routing endpoint (a first start builds tiles)...")
    if not _wait_for(lambda: _http_ok(VALHALLA_STATUS_URL), VALHALLA_WAIT_SECONDS):
        return Probe(
            False,
            f"no healthy endpoint within {VALHALLA_WAIT_SECONDS}s -- "
            "check: docker compose logs valhalla",
        )
    return _probe_valhalla()


# ── credentials ──────────────────────────────────────────────────────────────


def _probe_render_key() -> Probe:
    """Confirm a credential EXISTS.  Its value is never read, logged, or printed.

    Must stay in step with ``keychain_api_key`` in scripts/dev_env.py: Keychain
    first, then RENDER_API_KEY.  If these two disagree, preflight passes a target
    that then dies on a missing credential -- the precise failure mode this whole
    mechanism exists to remove.
    """
    if sys.platform == "darwin":
        account = os.environ.get("USER") or ""
        result = _run(
            ["security", "find-generic-password", "-a", account, "-s", KEYCHAIN_SERVICE],
            timeout=30,
        )
        if result.returncode == 0:
            return Probe(True, "Keychain item present (value not read)")
    if os.environ.get("RENDER_API_KEY", "").strip():
        return Probe(True, "RENDER_API_KEY is set (value not read)")
    if sys.platform != "darwin":
        return Probe(False, "no RENDER_API_KEY, and this platform has no Keychain")
    return Probe(False, "no Render API key in the login Keychain")


def _repair_render_key() -> Probe:
    """Hand the developer the interactive credential flow; never type the secret.

    Opens the page the key is created on and runs the same prompt
    `make render-auth-setup` runs. The developer pastes their own key into the
    OS prompt; nothing here reads, stores, or transmits it.
    """
    if sys.platform != "darwin":
        return Probe(False, "no Keychain on this platform; export RENDER_API_KEY")
    print("    A Render API key is needed. Opening the page that creates one.")
    print(f"    {RENDER_API_KEY_URL}")
    if shutil.which("open"):
        _run(["open", RENDER_API_KEY_URL], timeout=20)
    print("    Keychain will now prompt you to paste the key (it prompts twice).")
    interpreter = _venv_python() if _venv_python().is_file() else Path("python3")
    if _stream([str(interpreter), "scripts/dev_env.py", "auth-setup"], cwd=ROOT):
        return Probe(False, "the key was not stored, or it cannot read ondoway-api")
    return _probe_render_key()


# ── Render CLI (deploy watching only) ────────────────────────────────────────
# Distinct from the API key above, and easy to confuse with it.  Secrets are
# fetched over the REST API and need no CLI; the CLI is used by exactly one
# thing -- watching a deploy to a terminal state -- and it carries its OWN
# browser-based login, stored in ~/.render/.


def _probe_render_cli() -> Probe:
    if not shutil.which("render"):
        return Probe(False, "not on PATH")
    result = _run(["render", "--version"], timeout=30)
    if result.returncode != 0:
        return Probe(False, "installed but not runnable")
    return Probe(True, result.stdout.strip().splitlines()[0] if result.stdout.strip() else "ok")


def _repair_render_cli() -> Probe:
    if not _brew():
        return Probe(False, "Homebrew is not installed, so this cannot be installed for you")
    print("    -> brew install render")
    _stream(["brew", "install", "render"])
    return _after_install("render", _probe_render_cli)


def _probe_render_cli_auth() -> Probe:
    config = Path.home() / ".render" / "cli.yaml"
    if not config.is_file() or config.stat().st_size == 0:
        return Probe(False, "the Render CLI has not been signed in")
    return Probe(True, "signed in (config present)")


def _repair_render_cli_auth() -> Probe:
    """Start the CLI's own sign-in.  The browser approval is the developer's.

    Interactive by declaration, so an unattended run prints the instruction
    instead of blocking on a sign-in nobody is present to approve.
    """
    print("    -> render login   (opens your browser; approve it there)")
    if _stream(["render", "login"]):
        return Probe(False, "sign-in did not complete")
    return _probe_render_cli_auth()


# ── mobile toolchain ─────────────────────────────────────────────────────────


def _probe_flutter() -> Probe:
    if not shutil.which("flutter"):
        return Probe(False, "not on PATH")
    return Probe(True, "installed")


def _repair_flutter() -> Probe:
    if not _brew():
        return Probe(False, "Homebrew is not installed, so this cannot be installed for you")
    print("    -> brew install --cask flutter")
    _stream(["brew", "install", "--cask", "flutter"])
    return _after_install("flutter", _probe_flutter)


def _probe_flutter_deps() -> Probe:
    if (ROOT / "mobile" / ".dart_tool" / "package_config.json").is_file():
        return Probe(True, "packages resolved")
    return Probe(False, "mobile packages are not resolved")


def _repair_flutter_deps() -> Probe:
    print("    -> flutter pub get")
    env = dict(os.environ)
    env["NO_PROXY"] = "pub.dev,*.pub.dev"
    env["no_proxy"] = "pub.dev,*.pub.dev"
    result = subprocess.run(
        ["flutter", "pub", "get"], cwd=str(ROOT / "mobile"), env=env, check=False
    )
    if result.returncode:
        return Probe(False, "flutter pub get failed")
    return _probe_flutter_deps()


def _probe_xcode() -> Probe:
    if sys.platform != "darwin":
        return Probe(False, "macOS only")
    if not shutil.which("xcrun"):
        return Probe(False, "xcrun is missing")
    if _run(["xcrun", "simctl", "help"], timeout=60).returncode != 0:
        return Probe(False, "simctl is unavailable -- the full Xcode app is needed")
    return Probe(True, "simctl available")


def _repair_xcode() -> Probe:
    """Trigger the command-line-tools installer.

    Xcode proper is a multi-gigabyte App Store product tied to an Apple ID; it
    cannot honestly be installed from here, and pretending otherwise would be
    worse than saying so. This does the part that IS automatable and then reports
    precisely what remains.
    """
    if sys.platform != "darwin":
        return Probe(False, "macOS only")
    if not shutil.which("xcrun"):
        print("    -> xcode-select --install   (complete the dialog macOS opens)")
        _stream(["xcode-select", "--install"])
        return Probe(False, "finish the macOS installer dialog, then re-run")
    return Probe(False, "install Xcode from the App Store, then: xcode-select --install")


# ── browser ──────────────────────────────────────────────────────────────────


def _chromium_installed() -> bool:
    if not PLAYWRIGHT_CACHE.is_dir():
        return False
    for entry in PLAYWRIGHT_CACHE.iterdir():
        if (
            entry.is_dir()
            and entry.name.startswith("chromium-")
            and (entry / "INSTALLATION_COMPLETE").exists()
        ):
            return True
    return False


def _probe_playwright_browser() -> Probe:
    if _chromium_installed():
        return Probe(True, "Chromium present in the Playwright cache")
    return Probe(False, f"no Chromium in {PLAYWRIGHT_CACHE}")


def _repair_playwright_browser() -> Probe:
    print("    -> playwright install chromium")
    if _stream([str(_venv_python()), "-m", "playwright", "install", "chromium"], cwd=ROOT):
        return Probe(False, "browser download failed")
    return _probe_playwright_browser()


# ── registry ─────────────────────────────────────────────────────────────────


def _build_registry() -> dict:
    registry: dict = {}

    def add(requirement: Requirement) -> None:
        registry[requirement.name] = requirement

    add(Requirement(
        name="uv",
        summary="Python toolchain",
        probe=_probe_uv,
        repair=_repair_uv,
        instruction="install uv:  curl -LsSf https://astral.sh/uv/install.sh | sh",
    ))
    add(Requirement(
        name="python-deps",
        summary="Python packages",
        probe=_probe_python_deps,
        needs=("uv",),
        repair=_repair_python_deps,
        instruction="make sync",
    ))
    add(Requirement(
        name="docker",
        summary="Docker CLI",
        probe=_probe_docker_cli,
        repair=_repair_docker_cli,
        announce="installing the Docker CLI and Colima through Homebrew",
        instruction="install Docker Desktop, or:  brew install colima docker docker-compose",
    ))
    add(Requirement(
        name="docker-daemon",
        summary="Docker daemon",
        probe=_probe_docker_daemon,
        needs=("docker",),
        repair=_repair_docker_daemon,
        instruction=(
            "start the container runtime.  Colima, sized for this project:  "
            "colima start --cpu 4 --memory 8      -- or open Docker Desktop"
        ),
    ))

    for spec in DATABASES:
        add(Requirement(
            name=f"db-{spec.key}",
            summary=f"Neo4j {spec.key} graph (:{spec.port})",
            probe=_probe_database(spec),
            needs=("docker-daemon",),
            repair=_repair_database(spec),
            instruction=f"make db-up DB={spec.key}",
        ))

    add(Requirement(
        name="dev-data",
        summary="committed city data",
        probe=_probe_dev_data,
        needs=("python-deps", "db-dev"),
        repair=_repair_dev_data,
        instruction="run scripts/ensure_dev_data.py under the local profile",
    ))
    add(Requirement(
        name="valhalla-tiles",
        summary="routing map data",
        probe=_probe_valhalla_tiles,
        repair=_repair_valhalla_tiles,
        announce=(
            "downloading the Ile-de-France and New York OSM extracts -- several hundred "
            "MB. The first routing start then builds tiles from them, which can take well "
            "over an hour. Set PREFLIGHT_AUTOFIX=0 to skip and do this later"
        ),
        instruction="make valhalla-build-tiles",
    ))
    add(Requirement(
        name="valhalla",
        summary="routing engine",
        probe=_probe_valhalla,
        needs=("docker-daemon", "valhalla-tiles"),
        repair=_repair_valhalla,
        instruction="make valhalla-up",
    ))
    add(Requirement(
        name="render-key",
        summary="Render credential",
        probe=_probe_render_key,
        repair=_repair_render_key,
        interactive=True,
        instruction=(
            "make render-auth-setup        -- needs a Render API key whose account can read "
            "the ondoway-api service.  Provider secrets (Anthropic, OpenAI, Resend) are "
            "fetched from Render at run time and are never stored in this repo, so no .env "
            "file can substitute for this.  Off macOS, or in CI: export RENDER_API_KEY"
        ),
    ))
    add(Requirement(
        name="render-cli",
        summary="Render CLI",
        probe=_probe_render_cli,
        repair=_repair_render_cli,
        instruction="brew install render        -- or see https://render.com/docs/cli",
    ))
    add(Requirement(
        name="render-cli-auth",
        summary="Render CLI sign-in",
        probe=_probe_render_cli_auth,
        needs=("render-cli",),
        repair=_repair_render_cli_auth,
        interactive=True,
        instruction="render login        -- separate from the API key; approve it in the browser",
    ))
    add(Requirement(
        name="flutter",
        summary="Flutter SDK",
        probe=_probe_flutter,
        repair=_repair_flutter,
        announce="installing the Flutter SDK through Homebrew -- this is a large download",
        instruction="install the Flutter SDK:  https://docs.flutter.dev/get-started/install",
    ))
    add(Requirement(
        name="flutter-deps",
        summary="Flutter packages",
        probe=_probe_flutter_deps,
        needs=("flutter",),
        repair=_repair_flutter_deps,
        instruction="make flutter-pub-get",
    ))
    add(Requirement(
        name="xcode",
        summary="iOS toolchain",
        probe=_probe_xcode,
        repair=_repair_xcode,
        # The repair triggers the command-line-tools installer, which opens a
        # macOS dialog someone has to accept; Xcode proper is an App Store
        # product tied to an Apple ID and cannot be installed from here at all.
        interactive=True,
        instruction="install Xcode and its command-line tools:  xcode-select --install",
    ))
    add(Requirement(
        name="playwright-browser",
        summary="Chromium for Playwright",
        probe=_probe_playwright_browser,
        needs=("python-deps",),
        repair=_repair_playwright_browser,
        instruction="uv run playwright install chromium",
    ))
    return registry


REGISTRY = _build_registry()


# ── reading a target's declaration back out of the Makefile ──────────────────
# The Makefile is the single place a target's needs are written down.  Anything
# that wants to know what a target requires -- this tool's --target mode, and the
# tests that guard the wiring -- reads it from here, so there is never a second
# copy of that answer to drift.


def _makefile_lines(makefile: Path | None = None) -> list:
    return (makefile or MAKEFILE).read_text(encoding="utf-8").splitlines()


def _prerequisite_sets(lines: list) -> dict:
    """Read the reusable ``PRE_*`` definitions, joining backslash continuations."""
    variables: dict = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("PRE_") and ":=" in line:
            name, _, value = line.partition(":=")
            collected = value.strip()
            while collected.endswith("\\") and index + 1 < len(lines):
                index += 1
                collected = collected[:-1] + " " + lines[index].strip()
            variables[name.strip()] = collected.strip()
        index += 1
    return variables


def _expand(text: str, variables: dict) -> str:
    for _ in range(5):
        before = text
        for name, value in variables.items():
            text = text.replace(f"$({name})", value)
        if text == before:
            break
    return text


def declared_requirements(target: str, *, makefile: Path | None = None) -> list | None:
    """Every requirement name ``target``'s recipe passes to preflight.

    Returns None when the recipe never invokes preflight at all -- which is a
    real answer ("this target declares nothing"), distinct from an empty list
    ("this target declares --all").
    """
    lines = _makefile_lines(makefile)
    variables = _prerequisite_sets(lines)

    start = None
    for number, line in enumerate(lines):
        if line.startswith(target + ":"):
            start = number + 1
            break
    if start is None:
        raise KeyError(f"no target {target!r} in the Makefile")

    body = []
    for line in lines[start:]:
        if line.startswith("\t"):
            body.append(line)
        elif line.strip() and not line.startswith("#"):
            break

    # Join backslash continuations, or a requirement named on a continuation
    # line is invisible here -- which would silently exempt multi-line
    # declarations such as bootstrap's from every check built on this.
    recipe = []
    pending = ""
    for line in body:
        pending += line.rstrip()
        if pending.endswith("\\"):
            pending = pending[:-1] + " "
            continue
        recipe.append(pending)
        pending = ""
    if pending:
        recipe.append(pending)

    if not any("$(PREFLIGHT)" in line for line in recipe):
        return None

    names: list = []
    for line in recipe:
        # EVERY occurrence, not just the first.  A `case` over TARGET=local|cloud
        # collapses to one logical line with a preflight call per branch, and
        # reading only the first silently drops the cloud branch's `render-key`.
        for segment in line.split("$(PREFLIGHT)")[1:]:
            for terminator in ("&&", "||", ";"):
                segment = segment.split(terminator, 1)[0]
            segment = _expand(segment, variables).replace("$(DB)", "dev")
            skip_next = False
            for token in shlex.split(segment, posix=True):
                if skip_next:
                    skip_next = False
                    continue
                if token == "--label":
                    skip_next = True
                    continue
                if token.startswith("-"):
                    continue
                names.append(token)
    return names


def resolve(names: Iterable[str]) -> list:
    """Expand the requested names into a dependency-ordered, de-duplicated plan."""
    ordered: list = []
    seen: set = set()
    visiting: set = set()

    def visit(name: str, trail: tuple) -> None:
        if name in seen:
            return
        if name in visiting:
            path = " -> ".join(trail)
            raise SystemExit(f"preflight: dependency cycle at {name!r} via {path}")
        requirement = REGISTRY.get(name)
        if requirement is None:
            known = ", ".join(sorted(REGISTRY))
            raise SystemExit(f"preflight: unknown requirement {name!r}.  Known: {known}")
        visiting.add(name)
        for dependency in requirement.needs:
            visit(dependency, (*trail, name))
        visiting.discard(name)
        seen.add(name)
        ordered.append(requirement)

    for name in names:
        visit(name, ())
    return ordered


# ── reporting ────────────────────────────────────────────────────────────────


def _colour(enabled: bool, code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if enabled else text


class Reporter:
    """Fixed-width status lines so a failure is findable in a long build log."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _line(self, code: str, mark: str, name: str, detail: str) -> None:
        print(f"  {_colour(self.enabled, code, mark)} {name:<22} {detail}")

    def ok(self, name: str, detail: str) -> None:
        self._line("32", "OK ", name, detail)

    def fixed(self, name: str, detail: str) -> None:
        self._line("33", "FIX", name, detail)

    def failed(self, name: str, detail: str) -> None:
        self._line("31", "!! ", name, detail)

    def note(self, text: str) -> None:
        print(f"  {_colour(self.enabled, '33', '  ?')} {text}")


def _repair_is_possible(requirement: Requirement) -> bool:
    """An interactive repair needs a human; without a terminal, do not attempt it.

    Running `render login` or a Keychain paste prompt from an unattended build
    would block forever on input nobody can supply.
    """
    if not requirement.interactive:
        return True
    return sys.stdin.isatty() and sys.stdout.isatty()


def check(
    names: Sequence[str],
    *,
    autofix: bool,
    label: str,
    colour: bool,
    report_only: bool = False,
) -> int:
    """Verify (and usually restore) a set of requirements.

    ``report_only`` is for a pure diagnostic: it lists what is missing and exits
    0. A fresh clone is MEANT to be missing things, so a report that exits
    non-zero reads as "this tool is broken" the first time anyone runs it.
    """
    plan = resolve(names)
    reporter = Reporter(colour)
    header = f"Preflight: {len(plan)} prerequisite(s)"
    if label:
        header += f" for {label}"
    print(header)

    blocked: list = []
    unsatisfied: set = set()

    for requirement in plan:
        missing = [dep for dep in requirement.needs if dep in unsatisfied]
        if missing:
            reporter.failed(requirement.name, "skipped -- needs " + ", ".join(missing))
            unsatisfied.add(requirement.name)
            continue

        result = requirement.probe()
        if result.ok:
            reporter.ok(requirement.name, result.detail)
        elif autofix and requirement.repair is not None and _repair_is_possible(requirement):
            print(f"  .. {requirement.name}: {result.detail} -- fixing")
            if requirement.announce:
                print(f"     {requirement.announce}")
            result = requirement.repair()
            if result.ok:
                reporter.fixed(requirement.name, result.detail)
            else:
                reporter.failed(requirement.name, result.detail)
                blocked.append(requirement)
                unsatisfied.add(requirement.name)
        else:
            if requirement.repair is not None and not _repair_is_possible(requirement):
                result = Probe(result.ok, result.detail + " (needs a terminal to fix)")
            reporter.failed(requirement.name, result.detail)
            blocked.append(requirement)
            unsatisfied.add(requirement.name)

        if requirement.name == "docker-daemon" and result.ok:
            for warning in _colima_memory_warnings():
                reporter.note(warning)

    if not blocked:
        if report_only:
            print("")
            print("Everything this project needs is present.")
        return 0

    fixable = [r for r in blocked if r.repair is not None and not r.interactive]
    print("")
    if report_only:
        print(f"{len(blocked)} of {len(plan)} prerequisites are missing:")
    else:
        print("Preflight stopped -- the command was not run. Missing:")
    for requirement in blocked:
        print(f"  * {requirement.summary}  [{requirement.name}]")
        print(f"      {requirement.instruction or 'no automatic remedy is available'}")
    print("")
    if fixable:
        print("`make setup` installs and starts all of this for you.")
    else:
        print("`make setup` handles everything it can; the above need you.")
    print("")
    return 0 if report_only else 1


def repair_kind(requirement: Requirement) -> str:
    """How a missing requirement gets restored, in the developer's terms."""
    if requirement.repair is None:
        return "manual"
    if requirement.interactive:
        return "guided"
    if requirement.announce:
        return "auto (slow)"
    return "auto"


def _describe() -> int:
    print("Requirements a Make target can declare:")
    print("  auto = fixed silently | auto (slow) = fixed, announced first | "
          "guided = needs you at the keyboard")
    print("")
    for name in sorted(REGISTRY):
        requirement = REGISTRY[name]
        needs = ", ".join(requirement.needs) if requirement.needs else "-"
        print(
            f"  {name:<20} {requirement.summary:<28} "
            f"needs: {needs:<28} {repair_kind(requirement)}"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify (and where possible restore) the prerequisites a Make target declares."
    )
    parser.add_argument("requirements", nargs="*", help="requirement names to satisfy")
    parser.add_argument("--label", default="", help="target name, for the report header")
    parser.add_argument("--list", action="store_true", help="describe every known requirement")
    parser.add_argument("--all", action="store_true", help="check every known requirement")
    parser.add_argument(
        "--target",
        default="",
        help="check whatever this Make target declares, read from the Makefile",
    )
    parser.add_argument(
        "--no-fix", action="store_true", help="report only; never start or install anything"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="pure diagnostic: check nothing-changing, list what is missing, exit 0",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.list:
        return _describe()

    label = args.label
    if args.target:
        try:
            declared = declared_requirements(args.target)
        except KeyError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        if declared is None:
            print(f"make {args.target} declares no prerequisites.")
            return 0
        names = declared or sorted(REGISTRY)
        label = label or f"make {args.target}"
    else:
        names = sorted(REGISTRY) if args.all else args.requirements

    if not names:
        parser.error("name at least one requirement, or pass --all/--list/--target")

    autofix = (
        not args.no_fix
        and not args.report
        and os.environ.get("PREFLIGHT_AUTOFIX", "1") != "0"
    )
    colour = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
    return check(
        names, autofix=autofix, label=label, colour=colour, report_only=args.report
    )


if __name__ == "__main__":
    raise SystemExit(main())
