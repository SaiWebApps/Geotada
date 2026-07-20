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

import inspect

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_claim_repetition_judge, get_driver
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
            "duration_min": 60,
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


def test_preview_always_runs_the_one_algorithm_and_scores_quality(make_client):
    """The workbench Opus-vs-ChatGPT wiring on the wire, hermetic + $0 (the autouse
    money-guard stubs BOTH composers offline, so no live spend): compose=true threads
    the chosen REAL provider through and the response carries ``provider`` +
    objective ``narration_quality``. An unknown/absent provider falls back to Opus —
    never a mock passthrough label. UNDO: drop the provider/quality block in
    preview_trip, or add a mock provider branch -> these assertions fail."""
    client = make_client(_green_cluster_records())
    # No flags. The request carries ONLY where and how long.
    payload = {"center_lat": START[0], "center_lng": START[1], "duration_min": 60}
    r = client.post("/api/v1/trips/preview", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["compose_status"] in {"composed", "composed_partial", "refused"}, body
    assert body["provider"] == "anthropic", body["provider"]
    if body["compose_status"] != "refused":
        q = body["narration_quality"]
        assert q is not None, body
        assert set(q) >= {"stilted_score", "engagement_score", "burstiness", "tells_per_100w"}, q
        assert 0.0 <= q["stilted_score"] <= 1.0
        assert 0.0 <= q["engagement_score"] <= 1.0


def test_preview_labels_env_provider_when_request_omits_it(make_client, monkeypatch):
    """The response ``provider`` must name the ACTUAL narrator. With
    COMPOSE_PROVIDER=openai set and NO provider in the request, the injected default
    resolves to ChatGPT, so the label must say 'openai' — not 'anthropic' derived
    from the empty request field. $0 (money-guard stubs the client).
    UNDO: label from body.provider alone -> this reports 'anthropic' -> RED."""
    monkeypatch.setenv("COMPOSE_PROVIDER", "openai")
    client = make_client(_green_cluster_records())
    r = client.post(
        "/api/v1/trips/preview",
        json={"center_lat": START[0], "center_lng": START[1], "duration_min": 60, "compose": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    if body["compose_status"] != "refused":
        assert body["provider"] == "openai", body["provider"]


def test_preview_green_but_thin_delivery_carries_tourability(make_client):
    """C11a: a GREEN-density pool that DELIVERS thin ships tourability != null.

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
    assert r.status_code == 200, r.text
    body = r.json()

    dwell = [s for s in body["stops"] if s["band"] == "dwell"]
    # The delivery collapsed: the walk budget affords one edge anchor round-trip.
    assert len(dwell) == 1, f"expected a thin one-stop delivery, got {body['stops']}"
    # THE C11a wire pin: GREEN-but-thin is DISCLOSED, not silently GREEN.
    tourability = body["tourability"]
    assert tourability is not None, (
        "GREEN-but-thin delivery shipped WITHOUT tourability — the exact "
        "pool-vs-delivered silent collapse C11a exists to disclose"
    )
    assert tourability["status"] == "GREEN"
    assert tourability["delivered_thin"] is True
    # Density saw the rich pool: 6 anchor candidates cleared the rich-pool gate.
    assert tourability["anchor_candidates"] >= 6
    assert tourability["fill_ratio"] >= 1.5


# ---------------------------------------------------------------------------
# G4 (claim_repetition) route wiring — Defect 3: the conftest money-guard stub
# ALWAYS returns same_fact=False, so g4_findings is EMPTY across the entire
# non-live suite and the merge/severity logic in trips.py never executes against
# a non-empty finding set anywhere else. These tests inject a judge that DOES
# find a redundancy, so the wiring is exercised for real.
# ---------------------------------------------------------------------------


class _AlwaysRedundantJudge:
    """Deterministic, offline: rules every candidate pair redundant. Used ONLY to
    exercise the route's merge-into-response wiring — never a claim about the real
    judge's accuracy."""

    def same_fact(self, a: str, b: str) -> bool:
        return True


def _cluster_with_shared_entity_records():
    """A GREEN multi-stop cluster where EVERY beat at EVERY stop declares the same
    corpus entity — a real G4 candidate pair, cross-stop, once composed.
    ``MockComposeClient`` (the money guard's offline compose stub) passes
    ``source_type == "beat"`` sentences through unchanged (see ``compose.py``'s
    docstring), so whichever beats the selection/corrector pipeline keeps still
    carry the entity tag and stop_idx exactly as declared here — every beat, not
    just one per stop, because which beat SURVIVES beat-capping/correction is an
    internal detail of the engine this test does not own or want to couple to.

    ONLY 2 beats per POI (not 5, unlike ``_green_cluster_records``) — deliberately
    under ``quality_rubric.STARVE_MIN_BEATS`` (5) so a real rubric PASS is reachable
    here: this fixture exists to prove G4 stays advisory even when nothing else is
    wrong with the tour, which a fixture that always trips C1-starved could never
    discriminate (see the route test below, which needs at least one non-degenerate
    passing case to catch the Defect-2 mutation)."""
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
            body=f"Story {j} about anchor {i} and the Common Landmark. It continues.",
        )
        for i in range(len(offsets))
        for j in range(2)
    ]
    for beat in beats:
        beat["entities"] = ["Common Landmark"]
    return {"pois": pois, "beats": beats, "areas": _AREA_RECORDS, "adjacency": [], "lenses": []}


def test_g4_is_deliberately_dark_and_never_billed(make_client):
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

    # An always-True judge must still produce nothing: the check never runs.
    client = make_client(_cluster_with_shared_entity_records())
    client.app.dependency_overrides[get_claim_repetition_judge] = lambda: _AlwaysRedundantJudge()
    try:
        r = client.post(
            "/api/v1/trips/preview",
            json={"center_lat": START[0], "center_lng": START[1], "duration_min": 60},
        )
    finally:
        del client.app.dependency_overrides[get_claim_repetition_judge]

    assert r.status_code == 200, r.text
    quality = r.json()["quality"]
    assert quality["g4"]["judge_calls"] == 0, "G4 is dark -- it must never bill a call"
    assert quality["g4"]["findings"] == []
    assert quality["passed"] == (len(quality["blockers"]) == 0), (
        "quality['passed'] must depend only on the deterministic rubric"
    )

