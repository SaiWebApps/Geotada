"""Provider-free preflight for the approved batch-regression Make boundary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.tour.batch_regression_state_machine import (
    APPROVED_PLAN_SHA256,
    PLAN_STEP_IDS,
    PlanExecutionState,
    PlanStep,
    StepOrderError,
    StepStatus,
    dispatch_plan_step,
)

STATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "specs/2026-07-22-tour-batch-regression/prerequisite-state.v1.json"
)


def _load_committed_state() -> PlanExecutionState:
    document = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    if document.get("plan_sha256") != APPROVED_PLAN_SHA256:
        raise ValueError("state plan hash differs from the approved plan")
    if document.get("approved_plan_sha256") != APPROVED_PLAN_SHA256:
        raise ValueError("state approval hash differs from the approved plan")

    prerequisites = document.get("prerequisites")
    if not isinstance(prerequisites, list):
        raise ValueError("state prerequisites must be a list")
    expected_prerequisite_ids = PLAN_STEP_IDS[:10]
    if tuple(item.get("id") for item in prerequisites) != expected_prerequisite_ids:
        raise ValueError("state prerequisites differ from the approved order")

    prerequisite_steps = tuple(
        PlanStep(id=item["id"], status=StepStatus(item["status"]))
        for item in prerequisites
    )
    execution_steps = tuple(
        PlanStep(id=step_id, status=StepStatus.PENDING) for step_id in PLAN_STEP_IDS[10:]
    )
    return PlanExecutionState(steps=(*prerequisite_steps, *execution_steps))


def _preflight_payload(
    *,
    validated_step: str,
    next_step_after_preflight: str | None,
) -> dict[str, str | None]:
    return {
        "mode": "preflight",
        "validated_step": validated_step,
        "next_step_after_preflight": next_step_after_preflight,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one approved tour batch step without executing it."
    )
    parser.add_argument("--target", required=True)
    parser.add_argument("--step", required=True)
    parser.add_argument("--plan-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        state = _load_committed_state()
        result = dispatch_plan_step(
            state,
            requested_step_id=args.step,
            make_target=args.target,
            plan_sha256=args.plan_sha256,
            action=lambda: _preflight_payload(
                validated_step=args.step,
                next_step_after_preflight=None,
            ),
        )
    except (
        OSError,
        json.JSONDecodeError,
        KeyError,
        StepOrderError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"tour batch preflight rejected: {exc}", file=sys.stderr)
        return 2

    payload = dict(result.value)
    payload["next_step_after_preflight"] = result.state.next_step_id
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
