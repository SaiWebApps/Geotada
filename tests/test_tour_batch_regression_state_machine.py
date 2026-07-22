from __future__ import annotations

import pytest

from src.tour.batch_regression_state_machine import (
    PLAN_STEP_IDS,
    PlanExecutionState,
    PlanStep,
    StepOrderError,
    StepStatus,
    run_next_step,
)


def _state_after_p1() -> PlanExecutionState:
    return PlanExecutionState.from_completed_prefix(("P1",))


def test_plan_step_ids_are_the_exact_prerequisite_then_execution_order() -> None:
    assert (
        *(f"P{index}" for index in range(1, 11)),
        *(str(index) for index in range(1, 48)),
    ) == PLAN_STEP_IDS


def test_p1_complete_makes_p2_the_sole_next_step() -> None:
    state = _state_after_p1()

    assert state.next_step_id == "P2"
    assert state.completed_step_ids == ("P1",)


@pytest.mark.parametrize("requested_step_id", ["P3", "P1", "not-a-plan-step"])
def test_non_next_step_rejects_before_the_side_effect(
    requested_step_id: str,
) -> None:
    calls: list[str] = []

    with pytest.raises(StepOrderError):
        run_next_step(
            _state_after_p1(),
            requested_step_id=requested_step_id,
            action=lambda: calls.append("called"),
        )

    assert calls == []


def test_malformed_step_identity_is_rejected() -> None:
    calls: list[str] = []
    steps = list(PlanExecutionState.initial().steps)
    steps[0] = PlanStep(id="P2", status=StepStatus.PENDING)

    with pytest.raises(ValueError, match="exact approved order"):
        PlanExecutionState(steps=tuple(steps))

    assert calls == []


def test_noncontiguous_complete_state_is_rejected() -> None:
    calls: list[str] = []
    steps = list(PlanExecutionState.initial().steps)
    steps[0] = PlanStep(id="P1", status=StepStatus.COMPLETE)
    steps[2] = PlanStep(id="P3", status=StepStatus.COMPLETE)

    with pytest.raises(ValueError, match="contiguous prefix"):
        PlanExecutionState(steps=tuple(steps))

    assert calls == []


def test_valid_p2_invokes_once_and_returns_new_advanced_state() -> None:
    state = _state_after_p1()
    calls: list[str] = []

    result = run_next_step(
        state,
        requested_step_id="P2",
        action=lambda: calls.append("called") or "result",
    )

    assert calls == ["called"]
    assert result.value == "result"
    assert result.state.completed_step_ids == ("P1", "P2")
    assert result.state.next_step_id == "P3"
    assert state.completed_step_ids == ("P1",)
    assert state.next_step_id == "P2"


def test_callback_exception_cannot_advance_the_input_state() -> None:
    class ExpectedFailureError(RuntimeError):
        pass

    state = _state_after_p1()

    def fail() -> None:
        raise ExpectedFailureError("action failed")

    with pytest.raises(ExpectedFailureError, match="action failed"):
        run_next_step(state, requested_step_id="P2", action=fail)

    assert state.completed_step_ids == ("P1",)
    assert state.next_step_id == "P2"


def test_all_complete_state_refuses_further_execution_before_side_effect() -> None:
    state = PlanExecutionState.from_completed_prefix(PLAN_STEP_IDS)
    calls: list[str] = []

    with pytest.raises(StepOrderError, match="all plan steps are complete"):
        run_next_step(
            state,
            requested_step_id="47",
            action=lambda: calls.append("called"),
        )

    assert state.next_step_id is None
    assert calls == []
