"""Pure sequencing guard for the approved tour batch-regression plan.

This state machine constrains callers that execute actions through
``run_next_step``. It does not restrict an unrestricted shell, persist state, or
provide the external enforcement added by later prerequisites.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

PLAN_STEP_IDS: tuple[str, ...] = (
    *(f"P{index}" for index in range(1, 11)),
    *(str(index) for index in range(1, 48)),
)


class StepStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"


class StepOrderError(RuntimeError):
    """A requested action is not the sole next action in the approved plan."""


@dataclass(frozen=True, slots=True)
class PlanStep:
    id: str
    status: StepStatus


@dataclass(frozen=True, slots=True)
class PlanExecutionState:
    """Immutable state with one COMPLETE prefix followed only by PENDING steps."""

    steps: tuple[PlanStep, ...]

    def __post_init__(self) -> None:
        if tuple(step.id for step in self.steps) != PLAN_STEP_IDS:
            raise ValueError("plan steps must use the exact approved order")

        seen_pending = False
        for step in self.steps:
            if not isinstance(step.status, StepStatus):
                raise ValueError("plan step status must be a StepStatus")
            if step.status is StepStatus.PENDING:
                seen_pending = True
            elif seen_pending:
                raise ValueError("COMPLETE steps must form one contiguous prefix")

    @classmethod
    def initial(cls) -> PlanExecutionState:
        return cls(
            steps=tuple(
                PlanStep(id=step_id, status=StepStatus.PENDING)
                for step_id in PLAN_STEP_IDS
            )
        )

    @classmethod
    def from_completed_prefix(
        cls,
        completed_step_ids: tuple[str, ...],
    ) -> PlanExecutionState:
        if completed_step_ids != PLAN_STEP_IDS[: len(completed_step_ids)]:
            raise ValueError("completed step IDs must be an exact approved prefix")
        completed = len(completed_step_ids)
        return cls(
            steps=tuple(
                PlanStep(
                    id=step_id,
                    status=(
                        StepStatus.COMPLETE if index < completed else StepStatus.PENDING
                    ),
                )
                for index, step_id in enumerate(PLAN_STEP_IDS)
            )
        )

    @property
    def completed_step_ids(self) -> tuple[str, ...]:
        return tuple(
            step.id for step in self.steps if step.status is StepStatus.COMPLETE
        )

    @property
    def next_step_id(self) -> str | None:
        completed = len(self.completed_step_ids)
        if completed == len(self.steps):
            return None
        return self.steps[completed].id


ResultT = TypeVar("ResultT")


@dataclass(frozen=True, slots=True)
class StepRunResult(Generic[ResultT]):
    state: PlanExecutionState
    value: ResultT


def run_next_step(
    state: PlanExecutionState,
    *,
    requested_step_id: str,
    action: Callable[[], ResultT],
) -> StepRunResult[ResultT]:
    """Validate the sole next step before invoking its injected action once."""

    expected_step_id = state.next_step_id
    if expected_step_id is None:
        raise StepOrderError("all plan steps are complete")
    if requested_step_id != expected_step_id:
        raise StepOrderError(
            f"requested step {requested_step_id!r}; next step is {expected_step_id!r}"
        )

    value = action()
    completed = (*state.completed_step_ids, expected_step_id)
    return StepRunResult(
        state=PlanExecutionState.from_completed_prefix(completed),
        value=value,
    )
