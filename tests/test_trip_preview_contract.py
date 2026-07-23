"""Hermetic /trips/preview wire contract — fake driver, no Neo4j, no Valhalla.

2026-07-03 single-stop class guard, API layer. The engine side of the
2026-07-02 regression is pinned in test_tour_selection.py (the lone-anchor
YELLOW contract, the endpoint-pull no-collapse guard); nothing before this
module executed trips.py's payload mapping hermetically — TestPreviewTrip in
test_trip_api.py needs the live 7687 graph and skips silently without it.
Someone dropping the ``tourability=...`` kwarg from TripPreviewResponse,
reordering ``route.model_copy`` calls so ``route.tourability`` is lost, or
renaming a TripPreviewTourability field makes 1-stop tours silently look
like bugs again — the exact 2026-07-02 hostile-panel finding. These tests
fail on the wire, where the workbench reads it.

Plumbing (all in-process):

- ``_FakeDriver`` serves canned ``.data()`` records for the FIVE corpus
  Cypher queries ``load_paris_corpus`` runs (src/tour/selection.py), keyed
  on distinctive substrings. The keys must stay EXACT: a shortened key like
  ``[:WITHIN]`` collides with LOAD_AREA_ADJACENCY_CYPHER — only the full
  ``OPTIONAL MATCH (p)-[:WITHIN]`` is unique to the POI query. An unmatched
  query raises, so a NEW corpus query fails loudly instead of returning [].
- ``app.dependency_overrides[get_driver]`` swaps the fake in. The TestClient
  is deliberately NOT entered as a context manager: entering runs the
  lifespan (init_driver -> create_driver), which would attempt a real Neo4j
  connection. Plain requests work without it, and /trips/preview depends
  only on ``get_driver``.
- ``src.api.routes.trips.RoutingClient`` is monkeypatched with a
  deterministic fake (mirrors test_tour_b_materialization.py's
  _DeterministicRoutingClient, plus the context-manager protocol trips.py
  uses via ``with RoutingClient() as ...``). ``isochrone()`` returns None so
  REACH falls back to the analytic envelope. The suite-wide money guard injects
  the explicit offline Premium executor — no LLM, no network, no container.
"""

from __future__ import annotations

import hashlib
import inspect
import json

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_driver, get_premium_compose_executor
from src.tour.contract import ValhallaLegReceipt
from src.tour.premium_tour import PremiumBuildIdentity
from src.tour.routing import haversine_m, pace_corrected_walk_seconds
from src.tour.routing_client import (
    VALHALLA_ROUTING_CONFIG_JSON,
    VALHALLA_ROUTING_CONFIG_SHA256,
)

START = (48.8568, 2.3414)


def _available_stops(body: dict) -> list[dict]:
    if body["candidate_eligible"]:
        return body["stops"]
    return body["basic_tour"]["stops"]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, records: list[dict]):
        self._records = records

    def data(self) -> list[dict]:
        return self._records


class _FakeSession:
    """Supports both ``with driver.session() as s`` and plain use."""

    def __init__(self, records_by_kind: dict[str, list[dict]]):
        self._by_kind = records_by_kind

    def run(self, query: str, **params) -> _FakeResult:
        # Keyed on substrings unique to each corpus query — see module
        # docstring for why the POI key must be the full OPTIONAL MATCH.
        if "OPTIONAL MATCH (p)-[:WITHIN]" in query:
            return _FakeResult(self._by_kind["pois"])
        if "HAS_BEAT" in query:
            return _FakeResult(self._by_kind["beats"])
        if "a.area_type" in query:
            return _FakeResult(self._by_kind["areas"])
        if "shared_pois" in query:
            return _FakeResult(self._by_kind["adjacency"])
        if "IS_PARENT_OF" in query:
            return _FakeResult(self._by_kind["lenses"])
        raise AssertionError(
            f"FakeSession received an unrecognized corpus query — a new query was "
            f"added to load_paris_corpus; teach this fake about it:\n{query}"
        )

    def close(self) -> None:
        return None

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc) -> None:
        return None


class _FakeDriver:
    def __init__(self, records_by_kind: dict[str, list[dict]]):
        self._by_kind = records_by_kind

    def session(self, **kwargs) -> _FakeSession:
        return _FakeSession(self._by_kind)


class _FakeRoutingClient:
    """Deterministic: routed legs = int(pace-corrected haversine); no isochrone.

    Mirrors tests/test_tour_b_materialization.py's _DeterministicRoutingClient
    plus __enter__/__exit__ (trips.py uses ``with RoutingClient() as ...``).
    """

    def __init__(self, *args, **kwargs):
        return None

    def __enter__(self) -> _FakeRoutingClient:
        return self

    def __exit__(self, *exc) -> None:
        return None

    def leg_seconds(self, from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> int:
        return int(pace_corrected_walk_seconds(haversine_m(from_lat, from_lng, to_lat, to_lng)))

    def route(
        self, from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> tuple[int, float, None]:
        d = haversine_m(from_lat, from_lng, to_lat, to_lng)
        return (int(pace_corrected_walk_seconds(d)), d, None)

    def route_with_receipt(self, from_lat: float, from_lng: float, to_lat: float, to_lng: float):
        seconds = self.leg_seconds(from_lat, from_lng, to_lat, to_lng)
        distance_m = haversine_m(from_lat, from_lng, to_lat, to_lng)
        config = json.loads(VALHALLA_ROUTING_CONFIG_JSON)
        request = {
            "locations": [
                {"lat": from_lat, "lon": from_lng},
                {"lat": to_lat, "lon": to_lng},
            ],
            **config,
        }
        response = {
            "trip": {
                "legs": [
                    {
                        "summary": {
                            "time": seconds,
                            "length": distance_m / 1000.0,
                        },
                        "shape": "test-polyline",
                    }
                ]
            }
        }

        def canonical(value):
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

        request_json = canonical(request)
        response_json = canonical(response)
        receipt = ValhallaLegReceipt(
            requested_from=(from_lat, from_lng),
            requested_to=(to_lat, to_lng),
            request_json=request_json,
            request_sha256=hashlib.sha256(request_json.encode()).hexdigest(),
            routing_config_json=VALHALLA_ROUTING_CONFIG_JSON,
            routing_config_sha256=VALHALLA_ROUTING_CONFIG_SHA256,
            response_json=response_json,
            response_sha256=hashlib.sha256(response_json.encode()).hexdigest(),
            seconds=seconds,
            distance_m=distance_m,
            polyline="test-polyline",
        )
        return seconds, distance_m, "test-polyline", receipt

    def routing_version(self) -> str:
        return "test-valhalla"

    def isochrone(self, lat: float, lng: float, minutes: int) -> None:
        return None

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Canned records — the exact RETURN aliases of the corpus Cypher queries.
# ---------------------------------------------------------------------------


def _poi_record(
    pid: str, *, name: str, tier: int, lat: float, lng: float, areas: list[str]
) -> dict:
    return {
        "id": pid,
        "name": name,
        "tier": tier,
        "poi_role": "stop",
        "lat": lat,
        "lng": lng,
        "areas": areas,
    }


def _beat_record(bid: str, poi_id: str, *, body: str, est_spoken_seconds: int = 240) -> dict:
    return {
        "id": bid,
        "poi_id": poi_id,
        "sub_location": None,
        "trigger_address": None,
        "narrative_function": None,
        "beat_type": None,
        "emotional_register": None,
        "beat_length_class": None,
        "est_spoken_seconds": est_spoken_seconds,
        "script_body": body,
        "entities": [],
        "subject_tag": None,
        "active_status": "active",
        "physical_cues": None,
        "pronunciation": None,
        "source_passage": None,
        "source_chunk_slug": None,
        "key_claims": [],
        "lenses": [],
    }


_AREA_RECORDS = [
    {"name": "Île de la Cité", "area_type": "island", "city_name": "paris"},
    {"name": "Paris", "area_type": "city", "city_name": "paris"},
]


@pytest.fixture()
def make_client(monkeypatch):
    """(records_by_kind) -> TestClient with the fake driver + fake routing."""

    def _make(records_by_kind: dict[str, list[dict]]) -> TestClient:
        monkeypatch.setattr("src.api.routes.trips.RoutingClient", _FakeRoutingClient)
        monkeypatch.setattr(
            "src.api.routes.trips.resolve_build_identity",
            lambda: PremiumBuildIdentity(commit_sha="1" * 40),
        )
        app = create_app()
        app.dependency_overrides[get_driver] = lambda: _FakeDriver(records_by_kind)
        # NOT ``with TestClient(app)`` — the context manager runs the lifespan
        # (init_driver -> real Neo4j). Plain requests never touch it.
        return TestClient(app)

    return _make


# ---------------------------------------------------------------------------
# The wire pins
# ---------------------------------------------------------------------------


def test_preview_single_stop_that_cannot_fill_timebox_is_structured_422(make_client):
    """Premium planning must not disguise a materially underfilled route as Basic.

    Fixture = the pinned lone-anchor engine contract
    (test_tour_selection.py::test_isolated_single_anchor_yields_one_stop_with_
    yellow_warning) translated to Neo4j records: one tier-4 anchor with
    5 x 240s = 1200s of beat audio against the 60-min target of 1793s ->
    fill ~0.67 (YELLOW-by-fill), anchor_candidate_count == 1. The wire
    (trips.py::_tourability_payload) must carry it — dropping it is what
    made thin-area single-stop tours look like silent bugs.
    """
    records = {
        "pois": [
            _poi_record(
                "lone-anchor",
                name="Lone Anchor",
                tier=4,
                lat=START[0],
                lng=START[1] + 0.002,  # ~146m east — well inside the 738m envelope
                areas=["Île de la Cité"],
            )
        ],
        "beats": [
            _beat_record(
                f"lone-b{i}",
                "lone-anchor",
                body=f"The lone anchor holds story number {i}. It is a short one.",
            )
            for i in range(5)
        ],
        "areas": _AREA_RECORDS,
        "adjacency": [],
        "lenses": [],
    }
    client = make_client(records)

    r = client.post(
        "/api/v1/trips/preview",
        json={
            "center_lat": START[0],
            "center_lng": START[1],
            "duration_min": 60,
            "round_trip": False,
        },
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["reason"] == "premium_route_infeasible"
    assert "required 3240-3960s" in detail["detail"]
    assert detail["alternatives"] == []


def test_preview_round_trip_plus_end_is_422_not_500(make_client):
    """round_trip + a full end coordinate is a CLIENT error -> 422, never 500.

    TourInput's _end_round_trip_mutex (src/tour/contract.py) raises a pydantic
    ValidationError when both ``end`` and ``round_trip`` are set. The route
    builds that TourInput at the boundary (before load_paris_corpus), so the
    error fires with NO corpus/routing needed. app.py registers no
    ValidationError handler, so before the fix Starlette returned an opaque
    HTTP 500 with a stack trace. It must be a 422 the client can act on.

    Records are intentionally empty: the mutex must be caught at TourInput
    construction, upstream of the corpus load — if the fake driver were ever
    reached it would raise on the unrecognized (never-run) query instead.
    """
    records = {
        "pois": [],
        "beats": [],
        "areas": _AREA_RECORDS,
        "adjacency": [],
        "lenses": [],
    }
    client = make_client(records)

    r = client.post(
        "/api/v1/trips/preview",
        json={
            "center_lat": START[0],
            "center_lng": START[1],
            "end_lat": START[0] + 0.01,
            "end_lng": START[1] + 0.01,
            "round_trip": True,
            "duration_min": 30,
        },
    )
    assert r.status_code == 422, (
        f"round_trip + end must be a 422 client error, not {r.status_code}: {r.text}"
    )
    detail = r.json()["detail"]
    assert detail["reason"] == "invalid_tour_input"
    # The mutex message reaches the client so it can correct the request.
    assert any("mutually exclusive" in e["msg"] for e in detail["errors"]), detail


def test_preview_green_multi_stop_has_null_tourability_and_multiple_stops(make_client):
    """Control arm: a GREEN multi-stop preview ships tourability == null.

    Pins the RICH contract: a GREEN pool that also DELIVERS richly (multi-stop,
    audio at/over target) ships tourability == null — no spurious banner on a
    healthy tour. This is the control arm for the C11a GREEN-thin test below:
    the engine attaches tourability on YELLOW OR ``delivered_thin``, so both
    "always attach" (banner on every tour) and "never attach on GREEN" (the
    2026-07-02 silent pool-vs-delivered collapse) are pinned out. Also gives the
    multi-stop engine path hermetic API-level coverage (TestPreviewTrip's live-DB
    narration test skips silently on CI without 7687).

    The fixture is deliberately BOTH rich pool AND rich delivery: 6 compact
    anchors the greedy seats several of, ~4.0x target audio. Contrast
    test_preview_green_but_thin_delivery_carries_tourability, where the pool is
    GREEN (6 rich anchors, rich-pool escape) but the delivery collapses to one
    stop — that one MUST carry tourability with delivered_thin=True.
    """
    offsets = [
        (0.0004, 0.0),
        (0.0, 0.0007),
        (-0.0005, 0.0),
        (0.0, -0.0009),
        (0.0007, 0.0003),
        (-0.0006, -0.0006),
    ]  # 40-90m around the center — a compact GREEN cluster
    pois = [
        _poi_record(
            f"poi-{i}",
            name=f"Anchor Number {i}",
            tier=5,
            lat=START[0] + dlat,
            lng=START[1] + dlng,
            areas=["Île de la Cité"],
        )
        for i, (dlat, dlng) in enumerate(offsets)
    ]
    beats = [
        _beat_record(
            f"poi-{i}-b{j}",
            f"poi-{i}",
            body=f"Story {j} about anchor {i}. It continues briefly.",
        )
        for i in range(len(offsets))
        for j in range(5)
    ]
    # Density: fill 6 x 1200 / 1793 = 4.0 >= 1.5 with 6 anchors >= 6 ->
    # rich-pool GREEN; the greedy seats all 6 (audio break at 1800 >= 1793,
    # max_anchors = 60 // 10 = 6).
    records = {
        "pois": pois,
        "beats": beats,
        "areas": _AREA_RECORDS,
        "adjacency": [],
        "lenses": [],
    }
    client = make_client(records)

    r = client.post(
        "/api/v1/trips/preview",
        json={
            "center_lat": START[0],
            "center_lng": START[1],
            "duration_min": 30,
            "round_trip": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    dwell = [s for s in _available_stops(body) if s["band"] == "dwell"]
    assert len(dwell) >= 2, f"GREEN cluster collapsed on the wire: {body['stops']}"
    # The deliberate GREEN-null pin.
    assert body["tourability"] is None, (
        f"GREEN preview must ship tourability null; got {body['tourability']}"
    )
    for stop in dwell:
        assert stop["narration"], f"dwell stop {stop['poi_name']} has empty narration"


def _green_cluster_records():
    """A compact GREEN multi-stop cluster (same shape as the green_multi_stop test)
    the composer can voice — reused by the compose/provider wire test below."""
    offsets = [
        (0.0004, 0.0),
        (0.0, 0.0007),
        (-0.0005, 0.0),
        (0.0, -0.0009),
        (0.0007, 0.0003),
        (-0.0006, -0.0006),
    ]
    pois = [
        _poi_record(
            f"poi-{i}",
            name=f"Anchor Number {i}",
            tier=5,
            lat=START[0] + dlat,
            lng=START[1] + dlng,
            areas=["Île de la Cité"],
        )
        for i, (dlat, dlng) in enumerate(offsets)
    ]
    beats = [
        _beat_record(
            f"poi-{i}-b{j}",
            f"poi-{i}",
            body=f"Story {j} about anchor {i}. It continues briefly.",
        )
        for i in range(len(offsets))
        for j in range(5)
    ]
    return {"pois": pois, "beats": beats, "areas": _AREA_RECORDS, "adjacency": [], "lenses": []}


def test_preview_returns_a_traced_premium_candidate_from_the_shared_path(make_client, monkeypatch):
    """The wire receives the validated blueprint, not legacy Script metadata."""
    client = make_client(_green_cluster_records())
    payload = {"center_lat": START[0], "center_lng": START[1], "duration_min": 30}
    r = client.post("/api/v1/trips/preview", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["compose_status"] == "composed", body
    assert body["provider"] == "offline", body["provider"]
    assert body["candidate_eligible"] is True
    assert body["candidate_status"] == "premium_candidate_eligible_for_certification"
    assert body["stops"]
    assert body["basic_tour"] is None
    assert body["narration_quality"] is not None
    assert body["quality"] is not None
    assert body["candidate_rejection"] is None


def test_preview_never_scores_or_returns_mixed_fallback_as_an_llm_candidate(
    make_client, monkeypatch
):
    """A failed physical unit becomes a separate, ungraded Basic Tour."""
    from src.api.routes import trips as trips_route

    class FailingExecutor:
        cost_bearing = False
        provider_name = "offline"

        def execute(self, _unit):
            raise ValueError("deliberate physical failure")

    monkeypatch.setattr(
        trips_route,
        "score_tour",
        lambda *_a, **_k: pytest.fail("Basic Tour reached the quality grader"),
    )
    client = make_client(_green_cluster_records())
    client.app.dependency_overrides[get_premium_compose_executor] = FailingExecutor

    try:
        response = client.post(
            "/api/v1/trips/preview",
            json={"center_lat": START[0], "center_lng": START[1], "duration_min": 30},
        )
    finally:
        del client.app.dependency_overrides[get_premium_compose_executor]

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidate_eligible"] is False
    assert body["narration_kind"] == "none"
    assert body["compose_status"] == "basic_available"
    assert body["candidate_rejection"]["code"] == "generation_failed"
    assert body["stops"] == []
    assert body["quality"] is None
    assert body["narration_quality"] is None
    assert body["basic_tour"]["kind"] == "basic_tour"
    assert body["basic_tour"]["stops"]


def test_preview_green_pool_but_materially_thin_delivery_is_422(make_client):
    """A rich pool cannot waive the Premium route's active-time lower bound.

    This is the engine-side answer to the 2026-07-02 pool-vs-delivered gap: the
    density gate rates the reachable POOL, so a rich area reads GREEN even when
    the DELIVERED route collapses to one stop. Fixture (rescue-proof, post-#21):
    ONE rich dwell anchor (ring-0, tier 4, a deep beat stack that alone clears the
    audio floor) + FIVE pool-counted anchor-candidates (tier 4, 3 beats) that are
    dwell-INELIGIBLE filler-stubs (each < MIN_DWELL_AUDIO_SECONDS). Density counts
    all six (fill 1.5+, anchors 6+ -> the rich-pool escape bypasses the
    compactness ceiling -> GREEN), but selection has exactly ONE dwell candidate,
    so the delivery is a single stop. The #21 under-fill rescue cannot lift it —
    there is no second dwell stop to seat, and the lone rich anchor already meets
    the audio floor (the rescue early-returns). This is the pool-vs-delivered gap
    the rescue genuinely CANNOT fill, which is exactly when the disclosure matters.

    GREEN pool + one delivered stop => selection flags ``delivered_thin`` and
    attaches the assessment (selection.py, C11a). The wire MUST carry it with
    status GREEN, so the workbench can disclose "honest but thin" instead of
    silently reading fully-GREEN. Sibling control:
    test_preview_green_multi_stop_has_null_tourability_and_multiple_stops (rich
    pool that ALSO delivers richly -> null).
    """
    # 6 bearings, 60 degrees apart, each ~330m from the origin. dlat uses
    # 111_320 m/deg; dlng divides by cos(lat) (~0.6583 at 48.857) => 73_281 m/deg.
    ring_m = 330.0
    bearings_m = [
        (0.0, ring_m),  # E
        (285.79, 165.0),  # NE
        (285.79, -165.0),  # NW
        (0.0, -ring_m),  # W
        (-285.79, -165.0),  # SW
        (-285.79, 165.0),  # SE
    ]
    pois = [
        _poi_record(
            f"ring-{i}",
            name=f"Ring Anchor {i}",
            tier=4,
            lat=START[0] + north_m / 111_320.0,
            lng=START[1] + east_m / 73_281.0,
            areas=["Île de la Cité"],
        )
        for i, (north_m, east_m) in enumerate(bearings_m)
    ]
    # ring-0 is the single rich DWELL anchor: 12 x 240s = 2880s uncapped (density
    # reads the full pool; emission tier-caps it, still clearing the audio floor).
    rich_beats = [
        _beat_record(
            "ring-0-b" + str(j),
            "ring-0",
            body=f"Ring anchor 0 carries story {j}. It runs a good while longer.",
        )
        for j in range(12)
    ]
    # ring-1..5 are pool-counted anchor_candidates (tier 4, 3 beats) but
    # dwell-INELIGIBLE filler-stubs (3 x 28s = 84s < MIN_DWELL_AUDIO_SECONDS=90):
    # they inflate the GREEN pool yet give the rescue no second dwell stop.
    stub_beats = [
        _beat_record(
            f"ring-{i}-b{j}",
            f"ring-{i}",
            body=f"Ring anchor {i} note {j}.",
            est_spoken_seconds=28,
        )
        for i in range(1, 6)
        for j in range(3)
    ]
    beats = rich_beats + stub_beats
    records = {
        "pois": pois,
        "beats": beats,
        "areas": _AREA_RECORDS,
        "adjacency": [],
        "lenses": [],
    }
    client = make_client(records)

    r = client.post(
        "/api/v1/trips/preview",
        json={
            "center_lat": START[0],
            "center_lng": START[1],
            "duration_min": 60,
            "round_trip": True,
        },
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["reason"] == "premium_route_infeasible"
    assert "best eligible bounded route 2403s" in detail["detail"]


def test_g4_is_deliberately_dark_and_never_billed():
    """DECISION GUARD. G4 (semantic cross-stop repetition) is BUILT and TESTED but is
    deliberately NOT RUN from preview_trip. It was wired on 2026-07-19 and made dark the
    same day, on measurement, before it ever billed a real preview.

    Two independent reasons, either one sufficient:

    1. IT DOES NOT DETECT THE DEFECT IT EXISTS FOR. ~1100 candidate pairs per tour force
       a sampling strategy. Prefix truncation spent the whole budget on stop 0 (0 of 327
       pairs with a-stop>=1 ever judged). The round-robin stratification that fixed that
       breadth destroyed within-bucket depth instead: measured on the very tour
       claim_repetition.py cites as its founding case
       (data/paris/tours/pont-neuf-60min-5afc2e.json, where "Vert-Galant" is glossed FOUR
       times in different words), MAX_CANDIDATE_PAIRS=200 recovers **0 of the 15
       Vert-Galant edges**. A check that reports "no repetition found" on the canonical
       repetition tour is WORSE than no check.
    2. THE JUDGE IS UNCALIBRATED. HaikuRedundancyJudge has never executed against a live
       model; all 32 of its tests inject a hand-labelled stub. Failure-ledger entry
       FL-2026-111 warned verbatim that "an unproven judge silently gating narration
       would suppress real facts".

    Cost of leaving it on: the cap is a FLOOR, not a ceiling -- every real tour yields
    >1100 candidates, so it billed ~200 Haiku calls (~$0.10) on EVERY preview for the
    recall measured above.

    To re-enable, BOTH must hold: (a) the sampler recovers the Vert-Galant edges at a
    defensible budget, and (b) a labelled bake-off closes FL-2026-111 (~$0.006/tour, the
    pattern in scripts/coverage_calibrate.py). See [[founding-case-efficacy-rule]] --
    recall against the founding case was never measured, which is exactly how a repair
    that zeroed it passed its own test suite.
    """
    import src.api.routes.trips as trips_route

    src = inspect.getsource(trips_route)
    assert "check_tour_repetition(" not in src, (
        "G4 must stay dark until it recovers its founding-case edges AND its judge is "
        "calibrated -- it currently bills ~$0.10/preview for 0 recall on the tour it "
        "was built for"
    )

    preview_source = inspect.getsource(trips_route.preview_trip)
    assert "get_claim_repetition_judge" not in preview_source
