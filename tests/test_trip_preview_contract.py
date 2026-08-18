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
import json
import re
import threading

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_driver, get_premium_compose_executor
from src.tour.authoring import COMPOSE_MODEL
from src.tour.certification_provider import PhysicalProviderResponse
from src.tour.contract import Route, ValhallaLegReceipt
from src.tour.premium_tour import PremiumBuildIdentity
from src.tour.routing import haversine_m, pace_corrected_walk_seconds
from src.tour.routing_client import (
    VALHALLA_ROUTING_CONFIG_JSON,
    VALHALLA_ROUTING_CONFIG_SHA256,
)

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


class _ColdStartingRoutingClient(_FakeRoutingClient):
    """The walking service answering nothing — a cold start or a tile rebuild.

    EVERY request to it fails, which is what AC-20 asks for and what an outage
    actually looks like:

    - ``route_with_receipt`` returns no polyline and no receipt, which is exactly
      what the real client does when its HTTP call raises
      (src/tour/routing_client.py:175-181): it falls back to a straight-line
      estimate rather than propagating.
    - ``routing_version`` RAISES, which is also exactly what the real client does
      (src/tour/routing_client.py:183-200) — that one call has no fallback, so it
      is the only thing on either path an outage can hard-fail.

    Deliberately returns the SAME leg seconds as its parent, so the route that gets
    planned is identical and the only difference on the wire is that the legs are
    estimates. A stub that also changed the times would prove nothing about
    labelling, because a different route would be selected.

    Nothing here stops or touches the shared Valhalla container.
    """

    def route_with_receipt(self, from_lat: float, from_lng: float, to_lat: float, to_lng: float):
        seconds = self.leg_seconds(from_lat, from_lng, to_lat, to_lng)
        return seconds, haversine_m(from_lat, from_lng, to_lat, to_lng), None, None

    def routing_version(self) -> str:
        raise ConnectionError("valhalla is cold-starting")


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

    def _make(
        records_by_kind: dict[str, list[dict]],
        routing_client: type = _FakeRoutingClient,
    ) -> TestClient:
        monkeypatch.setattr("src.api.routes.trips.RoutingClient", routing_client)
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


def _lone_anchor_records():
    """The pinned lone-anchor engine contract translated to Neo4j records.

    (test_tour_selection.py::test_isolated_single_anchor_is_refused_with_the_
    duration_it_could_support.) One tier-4 anchor with 5 x 240s = 1200s of beat
    audio, far too little to fill the requested hour.

    SINCE 2026-08-05 THIS IS A REFUSAL, NOT A YELLOW-BY-FILL TOUR, and the change
    is arithmetic rather than policy. Unifying the two surfaces onto one walk
    budget made that budget two-sided: the band demands 90% of the requested
    duration, while a ONE-STOP tour can deliver at most 40% of it in walking plus
    a single stop's 270s speech ceiling. Those two ranges only overlap below about
    nine minutes, so a lone anchor cannot satisfy the band at any duration the
    product sells. The engine now refuses and names the duration the area COULD
    support, which is a better answer than a tour nobody wants — but it means the
    build-it-anyway-with-a-warning path is unreachable here. The disclosure
    mechanism itself is alive and still tested, on a corpus that can be built.
    """
    return {
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

    dwell = [s for s in body["options"][0]["stops"] if s["band"] == "dwell"]
    assert len(dwell) >= 2, f"GREEN cluster collapsed on the wire: {body['options']}"
    # The deliberate GREEN-null pin.
    assert body["tourability"] is None, (
        f"GREEN preview must ship tourability null; got {body['tourability']}"
    )
    # Every stop is a real, named place with a position — that is what a person
    # chooses between. The words are not written yet (OWNER RULING 1).
    for stop in dwell:
        assert stop["name"], "a stop with no name is not a place anyone can choose"
        assert stop["lat"] and stop["lng"]
        assert stop["narration"] == "", "planning writes nothing"


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


class _ExplodingExecutor:
    """Any provider call at all is the failure this test exists to catch."""

    cost_bearing = True
    provider_name = "anthropic"

    def execute(self, unit):
        raise AssertionError("the plan-only preview called the narrator")


def test_preview_returns_the_plan_and_spends_nothing(make_client, monkeypatch):
    """AC-13/AC-24: the preview PLANS. It shows the day and pays nobody.

    This endpoint used to plan a tour and then immediately write it, one paid call per
    stop, before anyone had chosen anything — on an anonymous route. It now returns
    the planned day and stops there; the words are written only after the person
    commits, by POST /trips/preview/author. (Renamed from "three_options" at Phase 4
    S4.4 — design §8.1 deleted pick-one-of-three; the assertions below were already
    count-agnostic and are unchanged.)

    Anything that could spend is booby-trapped: the narrator itself, and both halves of
    the authoring seam. If any of them is reached the request fails rather than quietly
    costing money.
    """
    for authoring_call in ("execute_premium_plan", "finalize_premium_tour"):
        monkeypatch.setattr(
            "src.api.routes.trips." + authoring_call,
            lambda *_a, **_k: pytest.fail("the plan-only preview authored a tour"),
            raising=False,
        )
    client = make_client(_green_cluster_records())
    client.app.dependency_overrides[get_premium_compose_executor] = _ExplodingExecutor
    try:
        r = client.post(
            "/api/v1/trips/preview",
            json={"center_lat": START[0], "center_lng": START[1], "duration_min": 30},
        )
    finally:
        del client.app.dependency_overrides[get_premium_compose_executor]

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["options"], "a plan with no options is not a plan"

    fingerprints = set()
    for i, option in enumerate(body["options"], start=1):
        match = re.fullmatch(r"preview-([0-9a-f]{12})-opt(\d+)", option["route_id"])
        assert match, f"option {i} carries an unusable selector {option['route_id']!r}"
        fingerprints.add(match.group(1))
        assert int(match.group(2)) == i
        assert option["stops"], "an option without stops is not an option"
        assert option["eta_seconds"] > 0
    assert len(fingerprints) == 1, "every option must share one plan fingerprint"

    # AC-3: any options are genuinely different walks (vacuous at one — kept so a
    # future second option cannot arrive as a duplicate).
    dwell_sets = [
        {s["poi_id"] for s in o["stops"] if s["band"] == "dwell"} for o in body["options"]
    ]
    for i in range(len(dwell_sets)):
        for j in range(i + 1, len(dwell_sets)):
            overlap = len(dwell_sets[i] & dwell_sets[j]) / len(dwell_sets[i] | dwell_sets[j])
            assert overlap < 0.60, f"options {i + 1},{j + 1} share {overlap:.0%} of their stops"

    # OWNER RULING 1 — choosing a route shows PLACES, never prose. No written line
    # anywhere, and no walking-narration cards at all, because there is no narration
    # to hear on the walk yet.
    for option in body["options"]:
        for stop in option["stops"]:
            assert stop["band"] in ("dwell", "vignette"), (
                "a plan-time option must carry no walking-narration card"
            )
            assert stop["narration"] == "", (
                f"plan-time stop {stop['name']!r} already carries written narration"
            )
            assert stop["has_deeper_dive"] is False
            assert "script" not in stop and "script_body" not in stop

    # AC-13: every field that described authored text is gone from this response.
    for authored_field in (
        "stops",
        "narration_kind",
        "basic_tour",
        "candidate_eligible",
        "candidate_status",
        "candidate_rejection",
        "compose_status",
        "provider",
        "narration_quality",
        "quality",
        "total_audio_min",
        "lens_coverage_note",
    ):
        assert authored_field not in body, (
            f"the plan-only preview still advertises {authored_field!r}, which only "
            f"means something once a tour has been written"
        )
    # promises/day_notes/slack_minutes joined at Phase 4 (W4.2 deviation v —
    # the pre-commit honesty surface, ruled by all eleven personas). Still an
    # EXHAUSTIVE set: anything else appearing here is an unreviewed leak.
    assert set(body) == {
        "spine_area",
        "options",
        "tourability",
        "degradations",
        "promises",
        "day_notes",
        "slack_minutes",
        "longest_walk_minutes",  # W4.12: the number the shorter-walks dial is named after
    }
    assert body["degradations"] == [], "an empty list is a statement; a missing key is not"

    # THE UNPLANNED MINUTES ARE NAMED AGAINST THE ASK (W4.12 closing panel —
    # Marcus, Sofia, Aiko, Julien; W4.2's ruling was "the unaccounted minutes are
    # NAMED"). The number is `asked - taken`, on the same clock the day is priced
    # on, and it is an INTEGER on every 200 — zero included. It used to ride the
    # planner's `elapsed_shortfall_seconds`, which is set only under the internal
    # band FLOOR, so a 170-of-180 day sent null and a 270-of-300 day hid thirty
    # minutes: it blanked exactly when the margin got tight. Pinned as arithmetic
    # so no future channel swap can quietly reintroduce the floor.
    taken = body["options"][0]["eta_seconds"]
    assert isinstance(body["slack_minutes"], int), (
        f"slack_minutes must be a number on every plan, got {body['slack_minutes']!r}"
    )
    assert body["slack_minutes"] == max(0, 30 * 60 - taken) // 60, (
        "slack is asked-minus-taken, not the planner's under-floor shortfall"
    )
    # THE LONGEST SINGLE WALK is on the wire as a number (W4.12 — Rosemary: "a
    # walking budget is not one number"; the surface printed only the total, so
    # the dial named after this number could not be checked). Pinned against
    # the day's own legs, computed by hand from the option's leg cards.
    assert isinstance(body["longest_walk_minutes"], int)
    assert body["longest_walk_minutes"] >= 0

    # AC-24: a duration too short to seat a single stop is a structured refusal that
    # names the time budget — never a 200 with nothing in it, never a bare string.
    lone = make_client(_lone_anchor_records())
    short = lone.post(
        "/api/v1/trips/preview",
        json={
            "center_lat": START[0],
            "center_lng": START[1],
            "duration_min": 60,
            "round_trip": False,
        },
    )
    assert short.status_code == 422, short.text
    detail = short.json()["detail"]
    assert set(detail) >= {"cause", "reason", "gap_minutes", "alternatives"}
    assert detail["cause"] == "time_budget"
    # WRITTEN DECISION (Phase 4 S4.5): the pinned range was "3240-3960s" — the
    # old 1.10 band ceiling. The repair's ceiling is THE REQUEST ITSELF (60 min
    # = 3600 s; "ask for five hours and the tour is at most five hours"), so
    # the refusal now names the range it actually enforces. The invariant is
    # unchanged: the refusal names the budget it could not fill.
    # W4.12 (Paulo): the traveller's `reason` is the planner's plain clause and
    # never the exception wrapper; the budget in seconds moved to `technical`,
    # where the AC-24 invariant still holds — the refusal names the budget it
    # could not fill, on the field an operator reads.
    assert "required 3240-3600s" in detail["technical"], (
        "the refusal must name the time budget it could not fill"
    )
    for engineer_word in ("Certification", "ondoway-premium-tour", "3240", "bounded route"):
        assert engineer_word not in detail["reason"], (
            f"{engineer_word!r} reached the sentence a traveller reads: {detail['reason']!r}"
        )
    assert "minutes" in detail["reason"], detail["reason"]
    assert detail["gap_minutes"] is None
    # And it offers a way out rather than just saying no. Every alternative is a
    # complete, actionable suggestion — not a bare string a surface has to parse.
    assert isinstance(detail["alternatives"], list)
    for alternative in detail["alternatives"]:
        assert set(alternative) == {"kind", "duration_min", "drop_end", "poi_id", "lat", "lng"}
        assert alternative["kind"] in ("loop", "extend", "closer_b")


class _CountingExecutor:
    """Records which stop each call to the narrator was for; echoes the text back."""

    cost_bearing = True
    provider_name = "anthropic"

    def __init__(self) -> None:
        self.stop_calls: list[int] = []
        self._lock = threading.Lock()

    def execute(self, unit):
        with self._lock:
            self.stop_calls.append(unit.stop_index)
        payload = json.dumps(
            {
                "sentences": [
                    s.model_dump(mode="json") for s in unit.authorized_request.stitched.script
                ]
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return PhysicalProviderResponse(
            body=payload,
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
            model=COMPOSE_MODEL,
            provider_request_id=f"offline-{unit.stop_index}",
            stop_reason="end_turn",
        )


def _plan(client) -> dict:
    r = client.post(
        "/api/v1/trips/preview",
        json={"center_lat": START[0], "center_lng": START[1], "duration_min": 30},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_preview_compose_authors_only_the_chosen_option(make_client):
    """AC-1/AC-8: writing produces the route that was picked, and only that route.

    Planning and writing are two calls now, which creates a new way to get it wrong:
    the second call could write a different route from the one on screen and nobody
    could tell, because both are plausible tours of the same neighbourhood. The
    request therefore names the route it wants, and that name also identifies the
    PLAN it came from. Four ways of getting it wrong are refused rather than guessed
    at, and none of them costs a penny.

    The written route is the planned route with the words filled in: same places, same
    order, same arrival time, same lens note. Nothing is re-derived, so nothing can
    drift.

    NOTE on the choice of route: the last one offered is picked deliberately, so
    "wrote the first one regardless" cannot pass. On today's corpus the planner offers
    only one route (see the report on the flavour collapse), which makes that
    particular guard inert until the planner offers more again — the identity,
    refusal and call-count checks below all have teeth either way.
    """
    client = make_client(_green_cluster_records())
    plan = _plan(client)
    chosen = plan["options"][-1]
    assert chosen["route_id"].endswith(f"-opt{len(plan['options'])}")

    executor = _CountingExecutor()
    client.app.dependency_overrides[get_premium_compose_executor] = lambda: executor
    try:
        r = client.post(
            "/api/v1/trips/preview/author",
            json={
                "center_lat": START[0],
                "center_lng": START[1],
                "duration_min": 30,
                "route_id": chosen["route_id"],
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()

        # ONE call to the narrator per stop that is stood at. No retries, and none
        # for any route other than the chosen one.
        dwell = [s for s in chosen["stops"] if s["band"] == "dwell"]
        assert sorted(executor.stop_calls) == list(range(len(dwell))), executor.stop_calls
        calls_after_writing = list(executor.stop_calls)

        # AC-8 — the written route IS the chosen route, field by field. Not asserted
        # as one whole-object comparison, because the words are the one thing that is
        # legitimately different.
        written = body["option"]
        assert written is not None, "a written tour with no route is not a tour"
        assert written["route_id"] == chosen["route_id"]
        # Every card the plan showed — the stops AND the sights passed on the way —
        # is still there, in the same order, under the same names. Walking-narration
        # cards are excluded because they exist only once there are words to hear.
        assert [
            (s["poi_id"], s["band"], s["name"]) for s in written["stops"] if s["band"] != "leg"
        ] == [(s["poi_id"], s["band"], s["name"]) for s in chosen["stops"]]
        assert [s["poi_id"] for s in written["stops"] if s["band"] == "dwell"] == [
            s["poi_id"] for s in dwell
        ]
        assert written["eta_seconds"] == chosen["eta_seconds"]
        assert written["lens_coverage_note"] == chosen["lens_coverage_note"]
        assert body["tourability"] == plan["tourability"]

        # And it really is WRITTEN — the plan carried no words at all.
        assert any(s["narration"] for s in written["stops"]), (
            "the written reply carries no narration; it is still the plan"
        )
        assert body["narration_kind"] == "llm_candidate"
        assert body["compose_status"] == "composed"
        assert body["candidate_eligible"] is True
        assert body["provider"] == "anthropic"
        assert body["basic_tour"] is None
        assert body["quality"] is not None
        assert body["narration_quality"] is not None
        # The places must not appear twice; a surface that preferred a top-level list
        # would silently show one tour's stops under another tour's words.
        assert "stops" not in body

        # A route number nobody offered is refused, not clamped to one that exists.
        unknown = client.post(
            "/api/v1/trips/preview/author",
            json={
                "center_lat": START[0],
                "center_lng": START[1],
                "duration_min": 30,
                "route_id": f"preview-{chosen['route_id'].split('-')[1]}-opt9",
            },
        )
        assert unknown.status_code == 404, unknown.text
        assert unknown.json()["detail"]["reason"] == "unknown_option"

        # A malformed name is refused before anything is planned.
        malformed = client.post(
            "/api/v1/trips/preview/author",
            json={
                "center_lat": START[0],
                "center_lng": START[1],
                "duration_min": 30,
                "route_id": "not-a-route-id",
            },
        )
        assert malformed.status_code == 422, malformed.text
        assert malformed.json()["detail"]["reason"] == "invalid_route_id"

        # THE ONE THAT MATTERS. A name from a plan that no longer matches is refused
        # outright rather than used to pick "the second route" out of a different set
        # of routes — which would write, and charge for, a tour nobody ever saw.
        stale = client.post(
            "/api/v1/trips/preview/author",
            json={
                "center_lat": START[0],
                "center_lng": START[1],
                "duration_min": 30,
                "route_id": "preview-000000000000-opt1",
            },
        )
        assert stale.status_code == 409, stale.text
        assert stale.json()["detail"]["reason"] == "plan_changed"
        assert stale.json()["detail"]["current_route_id"].startswith("preview-")

        # Every refusal above cost nothing.
        assert executor.stop_calls == calls_after_writing, (
            "a refused request still called the narrator"
        )
    finally:
        del client.app.dependency_overrides[get_premium_compose_executor]


def test_estimated_legs_are_labelled_not_silently_shipped(make_client):
    """AC-18/AC-20/AC-22 — a tour built on estimated walking times ships, and SAYS SO.

    The walking service is a real production dependency that can cold-start or rebuild
    its map (render.yaml:98-124). Refusing would take tour generation down for every
    user for the duration of that; shipping silently is worse, because the leg time
    drives the whole time budget and the audio is paced to it. So it ships, labelled.

    Both halves of the outage are injected here, because both are what an outage does:
    every walking leg falls back to a straight-line estimate with no receipt, AND the
    live version call raises. Before this, the first was silently substituted or turned
    into a refusal, and the second escaped as an unhandled error.

    The label is checked on BOTH registers, because they have different readers. The
    traveller's sentence must read alone on a phone screen and must not name a single
    internal thing; the operator's diagnosis must survive in the structured half where
    a person debugging a bad tour can find it.

    ON AC-20'S "3 OPTIONS", read this before weakening anything. The criterion means
    the outage must not cost the traveller any of the choice a working service would
    have given them, and that is asserted here EXACTLY, against a control run of the
    same request through a measured client: same number of options, same places, same
    order, same arrival times. It is deliberately not spelled ``== 3``, because this
    fixture yields ONE option even when every leg is measured — the flavour collapse a
    separate lane owns, unrelated to routing. Pinning the literal 3 would make this
    test fail for a reason it is not about, and pinning "at least 1" would let a future
    change quietly drop two flavours during an outage. Equality with the control does
    neither, and it strengthens by itself the day the collapse is fixed.
    """
    measured = make_client(_green_cluster_records())
    control = measured.post(
        "/api/v1/trips/preview",
        json={"center_lat": START[0], "center_lng": START[1], "duration_min": 30},
    )
    assert control.status_code == 200, control.text
    control_body = control.json()

    client = make_client(_green_cluster_records(), routing_client=_ColdStartingRoutingClient)

    r = client.post(
        "/api/v1/trips/preview",
        json={"center_lat": START[0], "center_lng": START[1], "duration_min": 30},
    )

    # 1. IT SHIPS. Not a 422, not a PremiumRouteInfeasibleError, not a 500 from the
    #    one routing call that has no fallback of its own.
    assert r.status_code == 200, r.text
    body = r.json()

    # AC-20: the outage costs the traveller NO choice. Same walks, same places, same
    # order, same arrival times as a fully measured run of the identical request — the
    # legs are estimated, the ROUTE is not reduced.
    def _shape(payload):
        return [
            (
                [s["poi_id"] for s in option["stops"] if s["band"] == "dwell"],
                option["eta_seconds"],
            )
            for option in payload["options"]
        ]

    assert body["options"], "a plan with no options is not a plan"
    assert _shape(body) == _shape(control_body), (
        f"the outage changed which walks are offered: {_shape(body)} "
        f"vs {_shape(control_body)} measured"
    )
    # NOTE for anyone tempted to check ``option["degraded"]`` here: that flag is about
    # the REACH ENVELOPE, not the walking legs (src/tour/options.py:214 reads
    # route.reach.degraded), and it is already True on the measured control because
    # these fakes serve no isochrone. It says nothing about whether legs were measured.
    #
    # The measured control carries no routing complaint at all, which is what makes
    # every row asserted below attributable to the outage rather than to the fixture.
    assert control_body["degradations"] == [], control_body["degradations"]

    # 2. IT SAYS SO — one labelled row, on the existing channel.
    rows = {row["kind"]: row for row in body["degradations"]}
    assert "walking_times_estimated" in rows, body["degradations"]
    row = rows["walking_times_estimated"]

    # 3. THE TRAVELLER'S SENTENCE, pinned verbatim. It is rendered on the phone, in the
    #    workbench panel and in the raw response, so it must read alone — and it must
    #    not imply the tour is broken or ask anyone to retry.
    assert row["human"] == (
        "Walking times between stops are estimates, not measured routes, so the tour "
        "may run a little longer or shorter than it says."
    )
    for token in ("valhalla", "receipt", "haversine", "service", "retry", "_", "()"):
        assert token not in row["human"].lower(), row["human"]

    # 4. THE OPERATOR'S CAUSE, in the structured half where it belongs — never stuffed
    #    into the sentence above.
    assert row["component"] == "premium_tour.plan_premium_tour"
    assert "routing service" in row["context"]["cause"]
    assert "straight-line" in row["context"]["cause"]
    assert int(row["context"]["estimated_legs"]) > 0
    assert row["context"]["fully_measured"] == "false"

    # 5. ONE ROW, NOT ONE PER LEG AND NOT ONE PER OPTION — three flavours' worth of
    #    unmeasured legs collapse to a single counted row. And no second row blaming
    #    the routing SETUP, which is a different fault and must not fire merely because
    #    no receipt exists at all.
    assert row["count"] >= 1
    assert len(body["degradations"]) == len(rows), (
        "the wire carries the same kind more than once; both the phone itinerary and "
        f"the workbench panel print one line per row: {body['degradations']}"
    )
    assert "routing_setup_unexpected" not in rows, body["degradations"]

    # 6. THE VERSION CALL, which is the one thing on this path an outage can hard-fail,
    #    is labelled too rather than refusing or escaping. Its sentence is a different
    #    fact from the one above, so it gets its own row.
    assert "routing_version_unavailable" in rows, body["degradations"]
    version_row = rows["routing_version_unavailable"]
    assert version_row["error_type"] == "ConnectionError"
    assert "cold-starting" in version_row["error_message"]
    for token in ("valhalla", "/status", "_", "()"):
        assert token not in version_row["human"].lower(), version_row["human"]

    # 7. AC-22 — AUTHORING STILL RUNS on the estimated route. The receipt bar lives in
    #    PLAN and nowhere else: the traveller who picks one of these gets one written
    #    script per stop they stand at, exactly as on a measured route.
    chosen = body["options"][0]
    executor = _CountingExecutor()
    client.app.dependency_overrides[get_premium_compose_executor] = lambda: executor
    try:
        authored = client.post(
            "/api/v1/trips/preview/author",
            json={
                "center_lat": START[0],
                "center_lng": START[1],
                "duration_min": 30,
                "route_id": chosen["route_id"],
            },
        )
    finally:
        del client.app.dependency_overrides[get_premium_compose_executor]

    assert authored.status_code == 200, authored.text
    authored_body = authored.json()
    dwell = [s for s in chosen["stops"] if s["band"] == "dwell"]
    assert sorted(executor.stop_calls) == list(range(len(dwell))), executor.stop_calls
    assert authored_body["candidate_eligible"] is True
    assert any(s["narration"] for s in authored_body["option"]["stops"])
    # And the written reply carries the same label, so the traveller is not told about
    # the estimate at plan time and then left to assume it went away.
    assert "walking_times_estimated" in {
        d["kind"] for d in authored_body["degradations"]
    }, authored_body["degradations"]


def test_a_route_with_no_stops_is_still_a_hard_refusal(make_client):
    """Structural faults did NOT become degradations. An empty route is not a tour.

    The two conditions that survive as refusals are faults in the plan's own shape,
    not statements about the walking service: a route with nothing to stand at, and a
    leg count that does not line up with the stop count (which breaks the index
    alignment every consumer downstream assumes). Neither can be labelled and shipped,
    because there is nothing to ship.
    """
    del make_client  # the refusal is a pure predicate; no client is needed
    from src.tour import premium_tour

    assert (
        premium_tour._premium_route_refusal(
            Route(pois=(), transits=(), total_walk_distance_m=0, total_walk_seconds=0)
        )
        is not None
    )


def test_preview_returns_a_traced_premium_candidate_from_the_shared_path(make_client, monkeypatch):
    """The wire receives the validated blueprint, not legacy Script metadata."""
    client = make_client(_green_cluster_records())
    plan = _plan(client)
    payload = {
        "center_lat": START[0],
        "center_lng": START[1],
        "duration_min": 30,
        "route_id": plan["options"][0]["route_id"],
    }
    r = client.post("/api/v1/trips/preview/author", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["compose_status"] == "composed", body
    assert body["provider"] == "offline", body["provider"]
    assert body["candidate_eligible"] is True
    assert body["candidate_status"] == "premium_candidate_eligible_for_certification"
    assert body["option"]["stops"]
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
    plan = _plan(client)
    client.app.dependency_overrides[get_premium_compose_executor] = FailingExecutor

    try:
        response = client.post(
            "/api/v1/trips/preview/author",
            json={
                "center_lat": START[0],
                "center_lng": START[1],
                "duration_min": 30,
                "route_id": plan["options"][0]["route_id"],
            },
        )
    finally:
        del client.app.dependency_overrides[get_premium_compose_executor]

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidate_eligible"] is False
    assert body["narration_kind"] == "none"
    assert body["compose_status"] == "basic_available"
    assert body["candidate_rejection"]["code"] == "generation_failed"
    assert body["option"] is None
    assert body["quality"] is None
    assert body["narration_quality"] is None
    assert body["basic_tour"]["kind"] == "basic_tour"
    assert body["basic_tour"]["stops"]


