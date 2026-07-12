"""The ONLY path in the compose regression system that spends money.

The bar eval (tests/test_compose_quality_eval.py) proves the machinery — metrics,
gate, orchestration — entirely on in-code synthetic fixtures at $0. THIS tool is
the deliberate, approval-gated capture of what the LIVE Opus prompt actually
produces for a few real stops, so the eval can also measure real drift over time.

Two hard gates protect the budget (the $20 lesson):
  * ``--live`` must be passed explicitly, AND
  * ``ONDOWAY_SNAPSHOT_APPROVE=1`` must be set in the environment.
Without both, the tool only prints the current prompt fingerprint and the plan —
it never calls the API. Capture is candidates=1, attempt-1 only, the named stops
only — never best-of-N over a whole tour.

``compose_prompt_fingerprint`` is imported by the bar eval: it ties every fixture
to the exact compose + entailment prompt text, so editing either prompt turns the
eval RED with "fixtures stale" instead of silently replaying output the current
prompt would no longer generate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from src.tour.compose import _COMPOSE_SYSTEM, ComposeRequest
from src.tour.contract import Script, Sentence
from src.tour.verify import _ENTAILMENT_PROMPT

CAPTURED_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "compose" / "captured"
_APPROVE_ENV = "ONDOWAY_SNAPSHOT_APPROVE"


def compose_prompt_fingerprint() -> str:
    """A short, stable digest of the compose system prompt + the entailment
    prompt template. Any edit to either changes it, invalidating stale goldens."""
    h = hashlib.sha256()
    h.update(_COMPOSE_SYSTEM.encode("utf-8"))
    h.update(_ENTAILMENT_PROMPT.encode("utf-8"))
    return h.hexdigest()[:16]


def capture_live(
    stitched: Script,
    requests_by_stop: dict[int, ComposeRequest],
    stop_indices: list[int],
    out_path: Path,
) -> dict[int, tuple[Sentence, ...]]:
    """Compose each named stop ONCE with the live Opus client and write a golden
    bundle (stop -> sentences + the prompt fingerprint). Callers pass fully-built
    per-stop ComposeRequests so this stays a thin, testable capture step. Spends
    real credits — only reached past the ``main`` approval gate.
    """
    from src.tour.compose import AnthropicComposeClient  # local: keep import off the $0 path

    client = AnthropicComposeClient()
    captured: dict[int, tuple[Sentence, ...]] = {}
    for idx in stop_indices:
        captured[idx] = tuple(client.compose(requests_by_stop[idx], 1, None))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "prompt_fingerprint": compose_prompt_fingerprint(),
                "stitched": stitched.model_dump(),
                "composed_by_stop": {
                    str(idx): [s.model_dump() for s in sents] for idx, sents in captured.items()
                },
            },
            indent=1,
        )
    )
    return captured


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="actually spend credits to capture")
    parser.add_argument("--stops", type=int, default=3, help="how many stratified stops to capture")
    args = parser.parse_args(argv)

    fp = compose_prompt_fingerprint()
    print(f"compose prompt fingerprint: {fp}")

    if not args.live:
        print(
            "\nDRY RUN ($0). The bar eval already proves the machinery on synthetic\n"
            "fixtures for free. Live capture records what the CURRENT prompt produces\n"
            f"for {args.stops} real stop(s) to measure drift. To do it:\n"
            f"  {_APPROVE_ENV}=1 python -m tools.compose_snapshot --live --stops {args.stops}\n"
            f"Estimated cost: ~{args.stops} Opus calls (candidates=1, attempt-1 only)."
        )
        return 0

    if os.environ.get(_APPROVE_ENV) != "1":
        print(
            f"\nREFUSING to spend: set {_APPROVE_ENV}=1 to confirm you approve\n"
            f"~{args.stops} live Opus calls. Nothing was billed.",
            file=sys.stderr,
        )
        return 2

    print(
        "\nLive capture requires a built Marais tour (stitched + per-stop requests).\n"
        "Drive it from the report-tour-issue skill or a caller that constructs the\n"
        "tour and invokes capture_live() — this entry point intentionally does not\n"
        "build a live tour so a bare invocation can never surprise-spend."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
