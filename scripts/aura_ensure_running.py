"""Wake a PAUSED Aura instance and BLOCK until it is running.

The free prod Aura auto-pauses after ~3 days; while paused its DNS is withdrawn
(connections fail with NXDOMAIN). Every `-cloud` make target runs this FIRST so a
paused instance is resumed and awaited instead of being mistaken for a dead one
(the 2026-07-12 incident — see feedback-paused-aura-is-not-dead). Unlike the
request-path ResumeCoordinator (fire-and-forget), a deploy MUST wait for
`running`, so this polls to completion.

Safe NO-OP when AURA_CLIENT_ID/SECRET are unset (local dev / CI / a self-hosted
graph): prints a note and exits 0, so it never blocks a non-Aura target.
"""

from __future__ import annotations

import sys
import time

from src.aura_resume import AuraClient, AuraConfig, AuraResumeError

_TIMEOUT_S = 300.0
_POLL_S = 10.0
_TERMINAL_BAD = {"destroying", "loading"}  # states a resume can't fix


def ensure_running(
    client: AuraClient,
    *,
    timeout: float = _TIMEOUT_S,
    poll: float = _POLL_S,
    sleep=time.sleep,
    clock=time.monotonic,
    echo=print,
) -> str:
    """Resume the instance if paused and poll until it is ``running``.

    Returns ``"running"``; raises AuraResumeError/TimeoutError otherwise. Pure over
    the injected client/clock/sleep so it is unit-testable without a live graph.
    """
    status = client.get_status()
    echo(f"[aura] status = {status}")
    if status == "running":
        return "running"
    if status == "paused":
        client.resume()
        echo("[aura] paused → resume initiated; waiting for running...")
    deadline = clock() + timeout
    while clock() < deadline:
        sleep(poll)
        status = client.get_status()
        echo(f"[aura] status = {status}")
        if status == "running":
            return "running"
        if status in _TERMINAL_BAD:
            raise AuraResumeError(f"instance in unrecoverable state {status!r}")
    raise TimeoutError(f"Aura instance not running after {timeout:.0f}s (last status {status!r})")


def main(argv: list[str] | None = None) -> int:
    cfg = AuraConfig.from_env()
    if cfg is None:
        print("[aura] AURA_CLIENT_ID/SECRET unset — resume disabled, skipping (no-op).")
        return 0
    try:
        ensure_running(AuraClient(cfg))
        print("[aura] ✓ instance running.")
        return 0
    except (AuraResumeError, TimeoutError) as exc:
        print(f"[aura] ensure-running FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
