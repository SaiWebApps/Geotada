"""Regression test: Dockerfile CMD must forward SIGTERM to uvicorn.

The shell-form `CMD uvicorn ...` makes /bin/sh -c PID 1; SIGTERM from Render is
delivered to the shell, not uvicorn, so the FastAPI lifespan shutdown
(close_driver() in src/api/dependencies.py) never runs and the container is
SIGKILLed after the grace window. The fix is the exec form with an explicit
`exec` so uvicorn replaces the shell and becomes PID 1 (receiving signals),
while the `sh -c` wrapper preserves `${PORT}` expansion.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parent.parent / "Dockerfile"


def _cmd_line() -> str:
    for line in DOCKERFILE.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("CMD"):
            return stripped
    raise AssertionError("No CMD instruction found in Dockerfile")


def test_cmd_uses_json_exec_form() -> None:
    """CMD must be JSON-array (exec) form, not shell form, so no wrapping shell
    lingers as PID 1 swallowing SIGTERM."""
    cmd = _cmd_line()
    argv = cmd[len("CMD") :].strip()
    parsed = json.loads(argv)  # shell-form `CMD uvicorn ...` is not valid JSON
    assert isinstance(parsed, list), f"CMD must be a JSON array, got {parsed!r}"


def test_cmd_execs_uvicorn_and_expands_port() -> None:
    """The command must `exec` uvicorn (so it becomes PID 1 and receives
    SIGTERM) while keeping `${PORT}` expansion via a shell wrapper."""
    cmd = _cmd_line()
    parsed = json.loads(cmd[len("CMD") :].strip())
    joined = " ".join(parsed)
    assert re.search(r"\bexec\s+uvicorn\b", joined), (
        f"CMD must `exec uvicorn` so uvicorn replaces the shell as PID 1; got {parsed!r}"
    )
    assert "${PORT" in joined, f"CMD must still expand ${{PORT}} at runtime; got {parsed!r}"
