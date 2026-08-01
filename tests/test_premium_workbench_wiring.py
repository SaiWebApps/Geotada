"""Pins that preview and batch generation cannot drift into separate algorithms."""

from __future__ import annotations

import importlib.util
import inspect
import socket
import subprocess
import sys
import time
from pathlib import Path

from scripts import tour_batch_candidate
from src.api.routes import trips

ROOT = Path(__file__).resolve().parents[1]


def _declared_requirements(target: str):
    """What a Make target declares, read by the code preflight itself uses.

    preflight lives outside the importable package tree and must stay runnable on
    the system interpreter, so it is loaded by path.  It must be registered in
    sys.modules BEFORE it executes: @dataclass resolves annotations through
    sys.modules[cls.__module__].
    """
    name = "ondoway_preflight"
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "preflight.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module.declared_requirements(target)


_LISTENER_SRC = """
import socket, sys, time
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", port))
# Backlog 16, not 1. Nothing ever calls accept(), so connections stay queued and the
# readiness probe below occupies a slot before the client arrives. PRECAUTIONARY — see
# the honest note on the wait loop; this was NOT shown to be the cause.
s.listen(16)
while True:
    time.sleep(1)
"""

_CLIENT_SRC = """
import pathlib, socket, sys, time
port = int(sys.argv[1])
ready = pathlib.Path(sys.argv[2])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("127.0.0.1", port))
ready.write_text("established")  # written ONLY once the socket is ESTABLISHED
while True:
    time.sleep(1)
"""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _alive(proc: subprocess.Popen) -> bool:
    # `ps -p <pid>` still finds a just-killed, unreaped child (it shows as
    # <defunct>) — Popen.poll() reaps it via waitpid(WNOHANG) and reports the
    # real state.
    return proc.poll() is None


def _extract_port_free_snippet(script_text: str) -> str:
    """The bash block between the healthz-reuse `else` and the `cd "$ROOT"` that
    follows it — this is the launcher's port-freeing step for scripts/workbench.sh,
    regardless of exactly how that step is implemented."""
    else_marker = "\nelse\n"
    cd_marker = '\n  cd "$ROOT"\n'
    else_start = script_text.index(else_marker)
    cd_start = script_text.index(cd_marker, else_start)
    return script_text[else_start + len(else_marker) : cd_start]


def test_launchers_kill_only_listening_sockets(tmp_path) -> None:
    script_text = (ROOT / "scripts" / "workbench.sh").read_text()
    snippet = _extract_port_free_snippet(script_text)

    port = _free_port()

    listener_file = tmp_path / "listener.py"
    listener_file.write_text(_LISTENER_SRC)
    client_file = tmp_path / "client.py"
    client_file.write_text(_CLIENT_SRC)

    listener = subprocess.Popen([sys.executable, str(listener_file), str(port)])
    client = None
    try:
        # Wait for the listener to actually be bound before connecting a client.
        for _ in range(50):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.2)
                try:
                    probe.connect(("127.0.0.1", port))
                    break
                except OSError:
                    time.sleep(0.1)
        else:
            raise RuntimeError("listener fixture never came up")

        # WAIT ON THE CONDITION, NEVER ON THE CLOCK. This was `time.sleep(0.5)`.
        #
        # HONEST STATUS (2026-07-27): this test WAS flaky — it failed 1 of 3 runs in
        # isolation, with the client exiting rc=1 on ConnectionRefusedError, which made
        # the assertion below report "a client/ESTABLISHED socket must never be
        # signalled" and blame the launcher for a fixture fault. After this change it
        # passed 8 of 8. But the ROOT CAUSE IS NOT ESTABLISHED, and two hypotheses were
        # tested and REFUTED rather than assumed:
        #   - "0.5 s is too short for interpreter startup" — measured: the client reaches
        #     ESTABLISHED in 23-32 ms over 10 runs, 0/10 anywhere near the budget.
        #   - "listen(1)'s backlog is exhausted by the readiness probe" — measured:
        #     0/15 connect failures at backlog 1, and 0/15 at 16.
        # So waiting on the ready file is a genuine robustness improvement and the right
        # shape regardless, but do NOT record this flake as diagnosed. If it recurs,
        # start from the port-freeing snippet itself — the one part neither experiment
        # exercised — and capture the client's stderr, which is currently discarded.
        ready_file = tmp_path / "client-established"
        client = subprocess.Popen(
            [sys.executable, str(client_file), str(port), str(ready_file)]
        )
        for _ in range(100):  # up to 10s
            if ready_file.exists():
                break
            if not _alive(client):
                raise RuntimeError(
                    f"client exited (rc={client.returncode}) before connecting — a "
                    "fixture fault, not a failure of the launcher under test"
                )
            time.sleep(0.1)
        else:
            raise RuntimeError("client never reached ESTABLISHED within 10s")

        assert _alive(listener)
        assert _alive(client)

        expected_cmd = subprocess.run(
            ["ps", "-p", str(listener.pid), "-o", "comm="],
            capture_output=True,
            text=True,
        ).stdout.strip()

        result = subprocess.run(
            ["bash", "-c", f"PORT={port}\n{snippet}"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout + result.stderr

        # AC-1: the listener PID is in the selected set and gets terminated.
        deadline = time.time() + 5
        while time.time() < deadline and _alive(listener):
            time.sleep(0.1)
        assert not _alive(listener), "the LISTEN-state process must be killed"

        # AC-2 / AC-3: a process whose only socket on the port is client-side
        # (ESTABLISHED here — the same defect class as the CLOSED sockets a real
        # Claude-desktop client left behind) is never signalled.
        assert _alive(client), (
            "a client/ESTABLISHED socket on the port must never be signalled"
        )

        # AC-5: the PID and command name are printed before signalling — not a
        # silent kill.
        assert str(listener.pid) in output, "must print the killed PID"
        assert expected_cmd and expected_cmd in output, (
            "must print the killed process's command name"
        )
    finally:
        for proc in (client, listener):
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

    # Same defect class in the flutter-ios launcher. It no longer frees the port
    # itself: it declares the `port-8000` requirement, and preflight both scopes
    # the query to LISTEN sockets AND refuses to signal a process it cannot
    # identify as this project's own server -- neither of which the inlined shell
    # kill ever did. So the requirement here is that flutter-ios does not
    # hand-roll a kill at all; if it ever does again, it must be LISTEN-scoped.
    makefile = (ROOT / "Makefile").read_text()
    flutter_ios_target = makefile.split("\nflutter-ios:", 1)[1].split(
        "\n\nflutter-device:", 1
    )[0]
    if "lsof" in flutter_ios_target:
        assert "-sTCP:LISTEN" in flutter_ios_target, (
            "flutter-ios re-introduced a port kill that is not LISTEN-scoped"
        )
    else:
        assert "port-8000" in _declared_requirements("flutter-ios"), (
            "flutter-ios neither frees :8000 itself nor declares the requirement "
            "that does it safely"
        )
    assert "-ti:8000" not in flutter_ios_target.replace("-tiTCP:8000", ""), (
        "no unscoped lsof -ti:PORT kill should remain"
    )


def test_preview_uses_shared_premium_plan_and_finalizer() -> None:
    # Read the IMPLEMENTATION, not the route wrapper. ``preview_trip`` is now a
    # thin shell that opens the degradation-collection scope and delegates; the
    # planning it must not reimplement lives in ``_preview_trip_impl``. Reading
    # the wrapper would pass vacuously the moment anything else moves behind an
    # indirection, which is the failure this whole file exists to catch.
    source = inspect.getsource(trips._preview_trip_impl)
    assert "plan_premium_tour(" in source
    assert "finalize_premium_tour(" in source
    assert "compose_script_per_chapter(" not in source
    assert "select_route(" not in source


def test_batch_uses_the_same_shared_premium_plan() -> None:
    source = inspect.getsource(tour_batch_candidate._plan_tour)
    assert "plan_premium_tour(" in source
    assert "select_k_routes(" not in source
    assert "_certification_compose_requests(" not in source

    finalizer_source = inspect.getsource(tour_batch_candidate._assemble_provider_tour)
    assert "finalize_premium_composition(" in finalizer_source


def test_batch_policy_delegates_to_the_shared_policy_factory() -> None:
    source = inspect.getsource(tour_batch_candidate._planning_policy)
    assert "certification_planning_policy(" in source
    assert "RoutePlanningPolicy.certification(" not in source


def test_manual_workbench_starts_routing_for_the_preview() -> None:
    """The workbench preview routes, so the target must provision routing itself.

    Asserted against the requirements the target DECLARES, resolved by the same
    code preflight acts on (`scripts/preflight.py`), rather than against literal
    text in the recipe: a preview that silently lost its dev graph or its routing
    engine is the failure this pins, and that is a property of the declaration,
    not of how it happens to be spelled.
    """
    declared = _declared_requirements("workbench")
    assert declared is not None, "the workbench target declares no prerequisites at all"
    assert "dev-data" in declared, "the preview would run against an unprovisioned graph"
    assert "valhalla" in declared, "the preview could not route"

    makefile = (ROOT / "Makefile").read_text()
    target = makefile.split("\nworkbench:", 1)[1].split("\n\ndashboard:", 1)[0]
    assert "$(RENDER_LOCAL_EXEC)" in target
