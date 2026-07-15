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
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.city_registry import onboard_data_root

_DEFAULT_DEPLOY_API_PORT = 8000


def _run(cmd: list[str]) -> None:
    print(f"\n$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True, cwd=str(ROOT))


def _deploy_api_port() -> int:
    """Port for the transient areas-upload API. ``$ONBOARD_DEPLOY_API_PORT`` when
    set (non-empty), else 8000 — so a hermetic deploy can dodge a busy :8000."""
    raw = (os.environ.get("ONBOARD_DEPLOY_API_PORT") or "").strip()
    return int(raw) if raw else _DEFAULT_DEPLOY_API_PORT


def _api_probe(port: int) -> str:
    return f"http://localhost:{port}/api/v1/nodes/Area?skip=0&limit=1"


def _api_healthy(probe: str) -> bool:
    try:
        urllib.request.urlopen(probe, timeout=2)  # localhost probe only
        return True
    except Exception:
        return False


def _port_busy(port: int) -> bool:
    return subprocess.run(
        ["lsof", f"-ti:{port}"], capture_output=True, text=True
    ).stdout.strip() != ""


def _areas_for(slug: str) -> list:
    """The city's Area records (``data/{slug}/areas.json`` under the hermetic-aware
    data root), or ``[]`` when the file is absent, empty, or not a JSON list.
    A fresh onboarded city writes ``areas.json == []`` — no areas to deploy."""
    path = onboard_data_root() / slug / "areas.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _upload_areas_step(slug: str, py: str) -> None:
    """Step 2: Areas + WITHIN edges via a TRANSIENT local API (upload_areas POSTs
    to it).

    ROBUSTNESS FIX: SKIP the whole step — and DO NOT spawn any transient API —
    when the city has no areas (``areas.json == []``/absent, e.g. a fresh
    onboarded city). Only spawn the uvicorn when there are Area nodes to create,
    so a hermetic deploy never hard-fails on a busy port for a city with nothing
    to upload. Honors ``$ONBOARD_DEPLOY_API_PORT`` (default 8000)."""
    if not _areas_for(slug):
        print(f"  [2/3] {slug}: no areas (areas.json empty/absent) — skipping areas upload")
        return

    port = _deploy_api_port()
    if _port_busy(port):
        sys.exit(f"ERROR: :{port} is already in use — deploy manages its own API; free it first.")
    env = {
        **os.environ,
        # Never proxy the localhost API round-trip (matches `make api`).
        "NO_PROXY": "localhost,127.0.0.1,::1",
        "no_proxy": "localhost,127.0.0.1,::1",
    }
    probe = _api_probe(port)
    api = subprocess.Popen(
        [py, "-m", "uvicorn", "src.api.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        env=env,
    )
    try:
        for _ in range(25):
            if _api_healthy(probe):
                break
            if api.poll() is not None:
                sys.exit("ERROR: transient API exited before becoming healthy.")
            time.sleep(1)
        else:
            sys.exit(f"ERROR: transient API never became healthy on :{port}.")
        _run([py, "scripts/upload_areas.py", "--slug", slug])
    finally:
        api.send_signal(signal.SIGTERM)
        try:
            api.wait(timeout=10)
        except subprocess.TimeoutExpired:
            api.kill()


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

    # 2. Areas + WITHIN edges via a transient local API — SKIPPED entirely for a
    #    city with no areas (no transient server spawned; see _upload_areas_step).
    _upload_areas_step(args.slug, py)

    # 3. Verify parity — the deploy is not 'done' until the graph matches the repo.
    _run([py, "-m", "scripts.db_parity", args.slug])
    bar = "=" * 66
    print(f"\n{bar}\n  ✓ DEPLOY COMPLETE — {args.slug} matches repo (parity clean)\n{bar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
