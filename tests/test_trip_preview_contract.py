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
  REACH falls back to the analytic envelope; ``generate()`` defaults to the
  MockGlueClient — no LLM, no network, no container.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_driver
from src.tour.routing import haversine_m, pace_corrected_walk_seconds

START = (48.8568, 2.3414)


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
        app = create_app()
        app.dependency_overrides[get_driver] = lambda: _FakeDriver(records_by_kind)
        # NOT ``with TestClient(app)`` — the context manager runs the lifespan
        # (init_driver -> real Neo4j). Plain requests never touch it.
        return TestClient(app)

    return _make


# ---------------------------------------------------------------------------
# The wire pins
# ---------------------------------------------------------------------------


def test_preview_single_stop_carries_yellow_tourability_on_the_wire(make_client):
    """A YELLOW 1-stop preview must ship the tourability payload on the wire.

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
    assert r.status_code == 200, r.text
    body = r.json()

    dwell = [s for s in body["stops"] if s["band"] == "dwell"]
    assert len(dwell) == 1
    # THE wire pin: the YELLOW assessment made it through trips.py intact.
    tourability = body["tourability"]
    assert tourability is not None, (
        "1-stop preview shipped WITHOUT the YELLOW tourability payload — "
        "thin-area tours are indistinguishable from collapse bugs again"
    )
    assert tourability["status"] == "YELLOW"
    assert tourability["anchor_candidates"] == 1
    assert 0.5 <= tourability["fill_ratio"] < 1.0  # 1200/1793 rounds to 0.67
    assert "reachable_poi_count" in tourability
    # The stop's narration carries real beat text, not just glue.
    assert "lone anchor" in dwell[0]["narration"]
    # The class invariant on the wire: multi-stop OR disclosed.
    assert len(dwell) >= 2 or tourability is not None


def test_preview_green_multi_stop_has_null_tourability_and_multiple_stops(make_client):
    """Control arm: a GREEN multi-stop preview ships tourability == null.

    Pins TODAY'S GREEN contract (the engine attaches tourability ONLY on
    YELLOW — selection._attach_tourability_if_yellow), so the YELLOW test
    cannot be satisfied by an "always attach" shortcut, which would put a
    spurious warning banner on every healthy tour. Also gives the multi-stop
    engine path hermetic API-level coverage (TestPreviewTrip's live-DB
    narration test skips silently on CI without 7687).

    IMPORTANT: do NOT extend this to assert tourability non-null for
    GREEN-but-thin deliveries — the workbench thin-delivery note is the
    disclosure mechanism for GREEN-thin until
    specs/2026-07-02-dwell-audio-reconciliation/ lands; asserting otherwise
    here would encode the deferred design early.
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
            "duration_min": 60,
            "round_trip": False,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    dwell = [s for s in body["stops"] if s["band"] == "dwell"]
    assert len(dwell) >= 2, f"GREEN cluster collapsed on the wire: {body['stops']}"
    # The deliberate GREEN-null pin.
    assert body["tourability"] is None, (
        f"GREEN preview must ship tourability null; got {body['tourability']}"
    )
    for stop in dwell:
        assert stop["narration"], f"dwell stop {stop['poi_name']} has empty narration"
