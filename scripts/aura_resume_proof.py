"""Real, human-facing proof that Aura auto-resume works end to end.

Run via ``make aura-resume-proof`` (needs live AURA_CLIENT_ID/SECRET). NOT for CI.

Prints the current instance status, resumes it if paused, then polls every 10s
(up to ~5 min) printing timestamped status transitions (paused -> resuming ->
running). Once running, it opens a VERIFIED Neo4j driver against the instance to
prove it actually serves queries, and returns exit 1 on any failure.

Guarded: if AURA_CLIENT_ID is unset, prints a clear hint and exits 0 (so CI /
local machines without creds are unaffected).
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime

from src.aura_resume import AuraClient, AuraConfig
from src.connection import create_driver

_POLL_INTERVAL = 10.0
_MAX_WAIT = 300.0  # ~5 minutes


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main() -> int:
    if not os.getenv("AURA_CLIENT_ID", "").strip():
        print(
            "AURA_CLIENT_ID/AURA_CLIENT_SECRET not set — nothing to prove.\n"
            "Set them (Aura Console → Account → API Credentials), plus NEO4J_URI "
            "(or AURA_INSTANCE_ID), then re-run `make aura-resume-proof`."
        )
        return 0

    cfg = AuraConfig.from_env()
    if cfg is None:
        print(
            "AURA creds present but no instance id could be derived — set "
            "AURA_INSTANCE_ID or a valid NEO4J_URI host."
        )
        return 1

    client = AuraClient(cfg)
    print(f"[{_stamp()}] Instance {cfg.instance_id}")

    status = client.get_status()
    print(f"[{_stamp()}] status = {status}")

    if status == "paused":
        print(f"[{_stamp()}] paused — issuing resume()...")
        client.resume()

    deadline = time.monotonic() + _MAX_WAIT
    last = status
    while status != "running":
        if time.monotonic() > deadline:
            print(f"[{_stamp()}] TIMEOUT after {_MAX_WAIT:.0f}s — last status = {status}")
            return 1
        time.sleep(_POLL_INTERVAL)
        status = client.get_status()
        if status != last:
            print(f"[{_stamp()}] status = {status}")
            last = status

    print(f"[{_stamp()}] running — verifying a live driver connection (RETURN 1)...")
    driver = create_driver(verify=True)
    try:
        with driver.session(database=os.getenv("NEO4J_DATABASE") or None) as session:
            ok = session.run("RETURN 1 AS ok").single()["ok"]
    finally:
        driver.close()
    if ok != 1:
        print(f"[{_stamp()}] driver connected but probe query wrong: {ok!r}")
        return 1

    print(f"[{_stamp()}] PROOF OK — instance is running and serving queries.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
