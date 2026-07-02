"""Phase 4 Step 4.5 — the LIVE compose gate (`make tour-compose-gate`).

Generates a real Paris tour from the dev graph (7687), stitches it, then runs
the REAL fire-once Anthropic compose behind the M7 gate with the REAL
HaikuFaithfulnessChecker (never the Mock — the gate must have teeth). Live
Anthropic key required; excluded from the hermetic ``make test``.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

from src.tour.beat_select import select_poi_beats
from src.tour.compose import AnthropicComposeClient, compose_script
from src.tour.compose_gate import ComposeVerificationError
from src.tour.contract import BeatSequence, TourInput
from src.tour.generation import GLUE_REFLECTION, generate
from src.tour.render_md import stop_narration_text
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_route
from src.tour.verify import HaikuFaithfulnessChecker

pytestmark = pytest.mark.live

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# Bound the live spend: a modest tour → one Opus compose + one Haiku
# entailment call per beat-cited sentence.
TOUR_DURATION_MIN = 45


def _parse_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE from .env WITHOUT mutating os.environ (the conftest
    fixture points os.environ at the TEST instance; the gate reads dev)."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _live_driver(env: dict[str, str]):
    uri = env.get("NEO4J_URI", "")
    user = env.get("NEO4J_USER", "")
    pw = env.get("NEO4J_PASSWORD", "")
    if not (uri and user and pw):
        return None
    try:
        d = GraphDatabase.driver(uri, auth=(user, pw))
        d.verify_connectivity()
        return d
    except (ServiceUnavailable, AuthError, Exception):
        return None


def _anthropic_reachable() -> bool:
    if not os.getenv("ANTHROPIC_API_KEY"):
        return False
    try:
        with httpx.Client(transport=httpx.HTTPTransport(proxy=None), timeout=5.0) as client:
            resp = client.get("https://api.anthropic.com/v1/models")
        return resp.status_code in (200, 401)
    except (httpx.ProxyError, httpx.ConnectError, httpx.TimeoutException):
        return False


def test_live_compose_gate_produces_verified_narration():
    env = _parse_env_file(ENV_PATH)
    api_key = env.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not in .env — needed for the live compose.")

    prev = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = api_key
    try:
        if not _anthropic_reachable():
            pytest.skip("Anthropic API unreachable — check ANTHROPIC_API_KEY / proxy.")
        driver = _live_driver(env)
        if driver is None:
            pytest.skip("Live Paris Neo4j (7687) unreachable — start it with `make db-up`.")
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
            pytest.fail(
                f"Compose gate REFUSED the flavour after {exc.attempts} attempts: "
                f"{exc.report.untraceable_sentences} {exc.report.forbidden_phrase_hits} "
                f"{exc.report.faithfulness_failures}"
            )

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
