"""Pins that preview and batch generation cannot drift into separate algorithms."""

from __future__ import annotations

import inspect
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

from scripts import tour_batch_candidate
from src.api.routes import trips

ROOT = Path(__file__).resolve().parents[1]

_LISTENER_SRC = """
import socket, sys, time
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", port))
s.listen(1)
while True:
    time.sleep(1)
"""

_CLIENT_SRC = """
import socket, sys, time
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("127.0.0.1", port))
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

        client = subprocess.Popen([sys.executable, str(client_file), str(port)])
        # Let the client's connection settle into ESTABLISHED before we run the
        # launcher's port-freeing step against it.
        time.sleep(0.5)
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

    # Same defect class, same fix, in the flutter-ios launcher's port kill.
    makefile = (ROOT / "Makefile").read_text()
    flutter_ios_target = makefile.split("\nflutter-ios:", 1)[1].split(
        "\n\nflutter-device:", 1
    )[0]
    assert re.search(r"lsof\s+-tiTCP:8000\s+-sTCP:LISTEN", flutter_ios_target), (
        "flutter-ios's port kill must be LISTEN-scoped too"
    )
    assert "-ti:8000" not in flutter_ios_target.replace("-tiTCP:8000", ""), (
        "no unscoped lsof -ti:PORT kill should remain"
    )


def test_preview_uses_shared_premium_plan_and_finalizer() -> None:
    source = inspect.getsource(trips.preview_trip)
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


def test_manual_workbench_starts_routing_and_authorizes_paid_preview() -> None:
    makefile = (ROOT / "Makefile").read_text()
    target = makefile.split("\nworkbench:", 1)[1].split("\n\ndashboard:", 1)[0]
    assert "_ensure-dev-data" in target
    assert "valhalla-up" in target
    assert "$(RENDER_LOCAL_EXEC)" in target
    script = (ROOT / "scripts" / "workbench.sh").read_text()
    assert "ONDOWAY_ENABLE_PAID_LLM_CALLS=1" in script
