from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import tour_batch_regression as cli
from src.tour.batch_regression_state_machine import (
    APPROVED_PLAN_SHA256,
    PLAN_STEP_IDS,
    PlanExecutionState,
)

ROOT = Path(__file__).resolve().parents[1]


def test_cli_exact_preflight_reports_p3(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        cli.main(
            [
                "--target",
                "tour-batch-step",
                "--step",
                "P3",
                "--plan-sha256",
                APPROVED_PLAN_SHA256,
            ]
        )
        == 0
    )

    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "preflight"
    assert output["validated_step"] == "P3"
    assert output["next_step_after_preflight"] == "P4"


@pytest.mark.parametrize(
    "args",
    [
        ["--target", "wrong", "--step", "P3", "--plan-sha256", APPROVED_PLAN_SHA256],
        ["--target", "tour-batch-step", "--step", "P3", "--plan-sha256", "wrong"],
        [
            "--target",
            "tour-batch-step",
            "--step",
            "P3",
            "--plan-sha256",
            APPROVED_PLAN_SHA256[:12],
        ],
        [
            "--target",
            "tour-batch-step",
            "--step",
            "P4",
            "--plan-sha256",
            APPROVED_PLAN_SHA256,
        ],
    ],
)
def test_cli_wrong_inputs_exit_nonzero_before_preflight(
    args: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        cli,
        "_preflight_payload",
        lambda **_kwargs: calls.append("called"),
    )

    assert cli.main(args) != 0
    assert calls == []


@pytest.mark.parametrize("args", [[], ["--target", "tour-batch-step"]])
def test_cli_missing_required_inputs_exit_nonzero(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(args)

    assert exc_info.value.code != 0


@pytest.mark.parametrize(
    ("variables", "expected_error"),
    [
        ([], "STEP is required"),
        (["STEP=P3"], "PLAN_SHA256 is required"),
        (["STEP=P3", "PLAN_SHA256=wrong"], "approved plan hash"),
    ],
)
def test_make_target_rejects_missing_or_wrong_inputs(
    variables: list[str],
    expected_error: str,
) -> None:
    completed = subprocess.run(
        ["make", "tour-batch-step", *variables],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode != 0
    assert expected_error in completed.stdout + completed.stderr


def test_make_target_exact_preflight_reports_p3() -> None:
    completed = subprocess.run(
        [
            "make",
            "tour-batch-step",
            "STEP=P3",
            f"PLAN_SHA256={APPROVED_PLAN_SHA256}",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert '"validated_step": "P3"' in completed.stdout


def test_cli_final_step_preflight_invokes_once_and_reports_no_next_step(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    state = PlanExecutionState.from_completed_prefix(PLAN_STEP_IDS[:-1])
    calls: list[str] = []
    original_payload = cli._preflight_payload
    monkeypatch.setattr(cli, "_load_committed_state", lambda: state)

    def record_payload(**kwargs: str | None) -> dict[str, str | None]:
        calls.append(str(kwargs["validated_step"]))
        return original_payload(**kwargs)

    monkeypatch.setattr(cli, "_preflight_payload", record_payload)

    assert (
        cli.main(
            [
                "--target",
                "tour-batch-step",
                "--step",
                "47",
                "--plan-sha256",
                APPROVED_PLAN_SHA256,
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)

    assert calls == ["47"]
    assert output["validated_step"] == "47"
    assert output["next_step_after_preflight"] is None
