"""Pins that preview and batch generation cannot drift into separate algorithms."""

from __future__ import annotations

import inspect
from pathlib import Path

from scripts import tour_batch_candidate
from src.api.routes import trips

ROOT = Path(__file__).resolve().parents[1]


def test_preview_uses_shared_premium_plan_and_finalizer() -> None:
    source = inspect.getsource(trips.preview_trip)
    assert "plan_premium_tour(" in source
    assert "finalize_premium_tour(" in source
    assert "compose_script_per_chapter(" not in source
    assert "select_route(" not in source


def test_batch_uses_the_same_shared_premium_plan() -> None:
    source = inspect.getsource(tour_batch_candidate._plan_tour)
    assert "plan_premium_tour(" in source
    assert "select_k_routes(" not in source
    assert "_certification_compose_requests(" not in source

    finalizer_source = inspect.getsource(tour_batch_candidate._assemble_provider_tour)
    assert "finalize_premium_composition(" in finalizer_source


def test_batch_policy_delegates_to_the_shared_policy_factory() -> None:
    source = inspect.getsource(tour_batch_candidate._planning_policy)
    assert "certification_planning_policy(" in source
    assert "RoutePlanningPolicy.certification(" not in source


def test_manual_workbench_starts_routing_and_authorizes_paid_preview() -> None:
    makefile = (ROOT / "Makefile").read_text()
    assert "workbench: db-up valhalla-up" in makefile
    script = (ROOT / "scripts" / "workbench.sh").read_text()
    assert "ONDOWAY_ENABLE_PAID_LLM_CALLS=1" in script
