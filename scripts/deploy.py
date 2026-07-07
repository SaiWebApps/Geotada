"""Deploy a city's repo data to the active Neo4j graph, then verify parity.

The repo files are the single source of truth; this is the ONE 'repo -> graph'
path, so no graph is ever hand-maintained (and drifts) again. It is:
  - additive + idempotent (all MERGE-based),
  - audio-safe (beat.audio_url is stamped ON CREATE only — a re-deploy never
    wipes generated TTS), and
  - self-verifying (fails non-zero if parity drifts afterward).

Steps:
  1. POIs + beats   <- scripts.upload_paris   (bbox-guarded MERGE)
  2. Areas + WITHIN <- scripts.upload_areas   (via a TRANSIENT local API this
                                               script starts and always stops)
  3. Parity         <- scripts.db_parity      (repo vs graph; non-zero on drift)

Target selection follows .env exactly like every other tool:
  make deploy CITY=x         -> active graph (local by default)
  make deploy-cloud CITY=x   -> Aura (.env.cloud sourced + --allow-cloud)
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_PROBE = "http://localhost:8000/api/v1/nodes/Area?skip=0&limit=1"


def _run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def _api_healthy() -> bool:
    try:
        urllib.request.urlopen(API_PROBE, timeout=2)  # localhost probe only
        return True
    except Exception:
        return False


def _port_8000_busy() -> bool:
    return subprocess.run(
        ["lsof", "-ti:8000"], capture_output=True, text=True
    ).stdout.strip() != ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", required=True, help="city slug, e.g. new_york")
    ap.add_argument("--allow-cloud", action="store_true", help="permit a non-local target")
    args = ap.parse_args()
    py = sys.executable

    print(f"\n{'='*66}\n  DEPLOY {args.slug} -> active graph (repo = source of truth)\n{'='*66}")

    # 1. POIs + beats (upload_paris enforces the localhost/--allow-cloud guard itself).
    upload = [py, "-m", "scripts.upload_paris", args.slug]
    if args.allow_cloud:
        upload.append("--allow-cloud")
    _run(upload)

    # 2. Areas + WITHIN edges via a transient local API (upload_areas POSTs to it).
    if _port_8000_busy():
        sys.exit("ERROR: :8000 is already in use — deploy manages its own API; free it first.")
    env = {
        **os.environ,
        # Never proxy the localhost API round-trip (matches `make api`).
        "NO_PROXY": "localhost,127.0.0.1,::1",
        "no_proxy": "localhost,127.0.0.1,::1",
    }
    api = subprocess.Popen(
        [py, "-m", "uvicorn", "src.api.app:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=str(ROOT),
        env=env,
    )
    try:
        for _ in range(25):
            if _api_healthy():
                break
            if api.poll() is not None:
                sys.exit("ERROR: transient API exited before becoming healthy.")
            time.sleep(1)
        else:
            sys.exit("ERROR: transient API never became healthy on :8000.")
        _run([py, "scripts/upload_areas.py", "--slug", args.slug])
    finally:
        api.send_signal(signal.SIGTERM)
        try:
            api.wait(timeout=10)
        except subprocess.TimeoutExpired:
            api.kill()

    # 3. Verify parity — the deploy is not 'done' until the graph matches the repo.
    _run([py, "-m", "scripts.db_parity", args.slug])
    bar = "=" * 66
    print(f"\n{bar}\n  ✓ DEPLOY COMPLETE — {args.slug} matches repo (parity clean)\n{bar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
