"""Idempotently make the local development graph match committed city data.

This command is intentionally incapable of targeting Aura. It only provisions
the exact local development endpoint at port 7687, and it never deletes data.
If additive deployment cannot resolve drift, the final parity check fails.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
LOCAL_PORT = 7687


def _assert_local_dev() -> None:
    uri = os.environ.get("NEO4J_URI", "")
    parsed = urlparse(uri)
    if (
        parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.port != LOCAL_PORT
        or os.environ.get("NEO4J_DATABASE") != "neo4j"
    ):
        raise SystemExit(
            "REFUSING local data provisioning: expected the exact development "
            f"database at bolt://localhost:{LOCAL_PORT}, got {uri!r}"
        )


def _run(*args: str, quiet: bool = False) -> int:
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        env=os.environ,
        check=False,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.DEVNULL if quiet else None,
    )
    return result.returncode


def _city_slugs() -> list[str]:
    return [
        path.name
        for path in sorted((ROOT / "data").iterdir())
        if path.is_dir() and (path / "poi-raw.json").is_file()
    ]


def main() -> int:
    _assert_local_dev()
    if _run("-m", "scripts.db_parity", quiet=True) == 0:
        print("✓ Local development graph already matches committed data.")
        return 0

    print("Local development graph needs additive provisioning.")
    if _run("-m", "src.main") != 0:
        return 1
    for slug in _city_slugs():
        if _run("-m", "scripts.deploy", "--slug", slug) != 0:
            return 1

    # This is deliberately the final word. Existing extra records are not
    # auto-deleted; they remain a loud failure requiring an explicit db reset.
    return _run("-m", "scripts.db_parity")


if __name__ == "__main__":
    raise SystemExit(main())
