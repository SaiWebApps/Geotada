"""Phase 4 Step 4.5—the LIVE compose gate (``make test-live``).

Generates a real Paris tour from the dev graph (7687), stitches it, then runs
the REAL fire-once Anthropic compose behind the M7 gate with the REAL
HaikuFaithfulnessChecker (never the Mock — the gate must have teeth). Live
Anthropic key required; fetched fresh from Render by the definitive suite.
"""

from __future__ import annotations

import os

import httpx
import pytest

from src.tour.beat_select import select_poi_beats
from src.tour.compose import AnthropicComposeClient, compose_script
from src.tour.compose_gate import ComposeVerificationError
from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import GLUE_REFLECTION, generate
from src.tour.render_md import stop_narration_text
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route
from src.tour.verify import HaikuFaithfulnessChecker
from tests.live_graph import open_dev_driver

pytestmark = pytest.mark.live

# Bound the live spend: a modest tour → one Opus compose + one Haiku
# entailment call per beat-cited sentence.
TOUR_DURATION_MIN = 45


def _anthropic_reachable() -> bool:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        with httpx.Client(transport=httpx.HTTPTransport(proxy=None), timeout=5.0) as client:
            resp = client.get("https://api.anthropic.com/v1/models")
        return resp.status_code in (200, 401)
    except (httpx.ProxyError, httpx.ConnectError, httpx.TimeoutException):
        return False


def test_live_compose_gate_serves_verified_or_refuses_safely():
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        pytest.fail("ANTHROPIC_API_KEY missing from fresh Render environment")

    prev = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = api_key
    try:
        if not _anthropic_reachable():
            pytest.fail("Anthropic API unreachable—check Render credential/network")
        driver = open_dev_driver()
        if driver is None:
            pytest.fail("Local dev Neo4j (7687) unreachable after live-test provisioning")
        try:
            snapshot = load_paris_corpus(driver, city_slug="paris")
        finally:
            driver.close()

        tour_input = TourInput(
            start=(48.852966, 2.349902),  # Île de la Cité (dense)
            duration_min=TOUR_DURATION_MIN,
            city_slug="paris",
            lenses=["dark_history"],
        )
        with RoutingClient() as rc:
            route = select_route(tour_input, snapshot, routing_client=rc)
        assert route.pois, "expected a tourable route from a dense central-Paris start"

        plans = []
        for poi in route.pois:
            beats = list(snapshot.beats_for(poi.id))
            beats.extend(route.demoted_beats.get(poi.id, ()))
            plans.append(select_poi_beats(poi, beats, interest_lenses=tour_input.lenses))
        seq = BeatSequence(poi_beats=tuple(plans))
        stitched = generate(seq, route, tour_input)
        assert stitched.validation.passed

        client = AnthropicComposeClient()
        checker = HaikuFaithfulnessChecker()
        try:
            composed = compose_script(
                stitched, seq, route, client=client, faithfulness_checker=checker
            )
        except ComposeVerificationError as exc:
            assert exc.attempts == 2
            assert not exc.report.passed
            print(
                f"\nLIVE COMPOSE GATE SAFELY REFUSED after {exc.attempts} attempts: "
                f"{len(exc.report.untraceable_sentences)} untraceable, "
                f"{len(exc.report.forbidden_phrase_hits)} forbidden, "
                f"{len(exc.report.faithfulness_failures)} faithfulness, "
                f"{len(exc.report.coverage_failures)} coverage"
            )
            return

        # The gate passed with the REAL checker — print the evidence.
        assert composed.validation.passed
        per_stop = stop_narration_text(composed)
        assert per_stop and all(text.strip() for text in per_stop.values())
        reflections = [s for s in composed.script if s.source_id == GLUE_REFLECTION]
        print(
            f"\nLIVE COMPOSE GATE PASSED — {len(route.pois)} stops, "
            f"{len(composed.script)} sentences, {len(reflections)} reflection(s); "
            f"compose tokens in/out: {client.input_tokens}/{client.output_tokens}; "
            f"haiku entailment calls: {checker.calls}"
        )
        for idx in sorted(per_stop):
            print(f"\n--- stop {idx} ---\n{per_stop[idx]}")
    finally:
        if prev is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = prev
