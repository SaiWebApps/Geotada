"""Integration tests for POST /api/v1/trips/generate — real engine, live corpus.

Since M0b the endpoint runs the real tour engine (src/tour), whose density
gate refuses sparse areas (needs >=4 anchor candidates). The conftest test
instance (port 7688) only carries toy seed data (3 POIs / 5 beats), so these
tests run against the LIVE local Paris dev graph (port 7687) the way
tests/test_tour_golden_*.py do—through a separate, localhost-only dev-graph
profile and overridden app session/driver dependencies.

Unlike the goldens these tests WRITE to the dev graph: a disposable test
Profile and the Trips/ItineraryItems the endpoint persists. Setup and
teardown both delete them, so a crashed run never accumulates residue.

The tour input mirrors fixtures/tour_golden/ile_oneway_90min.json (Pont Neuf
metro, 90 min, one-way) — a known-GREEN multi-stop start on the live corpus.
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth.tokens import create_access_token
from src.api.dependencies import get_driver, get_session
from src.tour.authoring import COMPOSE_MODEL
from src.tour.certification_provider import PhysicalProviderResponse
from src.tour.contract import TourInput
from src.tour.density import TourabilityRefusedError
from src.tour.routing_client import RoutingClient
from src.tour.selection import load_paris_corpus, select_k_routes, select_route
from tests.conftest import needs_neo4j
from tests.live_graph import open_dev_driver

LENSED_PROFILE_ID = "m0b-trip-api-test-profile-lensed"
NOLENS_PROFILE_ID = "m0b-trip-api-test-profile-nolens"
PROFILE_IDS = [LENSED_PROFILE_ID, NOLENS_PROFILE_ID]
# The trip routes are ownership-scoped (2026-07-19 IDOR fix): they require a bearer
# token AND the profile must hang off the calling User. Own both disposable profiles
# with one disposable User so these tests exercise the authorized path.
TEST_USER_ID = "m0b-trip-api-test-user"
TEST_USER_EMAIL = "m0b-trip-api@example.test"
PROFILE_LENSES = ["hidden_history", "literary_heritage"]

# Same input as fixtures/tour_golden/ile_oneway_90min.json.
ILE_START = (48.8568, 2.3414)
ILE_DURATION_MIN = 90


def _live_driver():
    """Open only the localhost:7687 graph; this module writes disposable data."""
    return open_dev_driver()


def _delete_test_artifacts(driver) -> None:
    """Remove the disposable profiles and any trips/items they captain."""
    with driver.session() as s:
        s.run(
            "MATCH (p:Profile) WHERE p.id IN $pids "
            "OPTIONAL MATCH (p)-[:IS_CAPTAIN_OF]->(t:Trip) "
            "OPTIONAL MATCH (t)-[:HAS_STOP]->(i:ItineraryItem) "
            "DETACH DELETE t, i",
            pids=PROFILE_IDS,
        )
        s.run("MATCH (p:Profile) WHERE p.id IN $pids DETACH DELETE p", pids=PROFILE_IDS)
        s.run("MATCH (u:User {id: $uid}) DETACH DELETE u", uid=TEST_USER_ID)


@pytest.fixture(scope="module")
def live_neo4j():
    d = _live_driver()
    if d is None:
        pytest.skip(
            "Local Paris dev Neo4j unreachable. These tests write disposable "
            "records and refuse anything but localhost:7687. Run through "
            "`make test` or `make test-file FILE=tests/test_trip_api.py`."
        )
    yield d
    d.close()


@pytest.fixture(scope="module")
def test_profiles(live_neo4j):
    """Disposable profiles on the live graph: one lensed, one without lenses."""
    _delete_test_artifacts(live_neo4j)  # clear residue from any crashed prior run
    with live_neo4j.session() as s:
        s.run(
            "MERGE (u:User {id: $uid}) SET u.email = $email",
            uid=TEST_USER_ID,
            email=TEST_USER_EMAIL,
        )
        for pid in PROFILE_IDS:
            s.run(
                "MERGE (p:Profile {id: $pid}) SET p.display_name = 'M0b API Test' "
                "WITH p MATCH (u:User {id: $uid}) MERGE (u)-[:HAS_PROFILE]->(p)",
                pid=pid,
                uid=TEST_USER_ID,
            )
        linked = s.run(
            "MATCH (p:Profile {id: $pid}) "
            "UNWIND $lenses AS lname "
            "MATCH (l:Lens {name: lname}) "
            "MERGE (p)-[:PREFERS_LENS]->(l) "
            "RETURN count(l) AS linked",
            pid=LENSED_PROFILE_ID,
            lenses=PROFILE_LENSES,
        ).single()["linked"]
        assert linked == len(PROFILE_LENSES), (
            f"Live graph is missing Lens nodes for {PROFILE_LENSES} — "
            f"linked only {linked}. Re-sync the dev corpus (make db-up + upload)."
        )
    yield
    _delete_test_artifacts(live_neo4j)


@pytest.fixture(scope="module")
def client(live_neo4j, test_profiles):
    """TestClient whose request sessions AND engine corpus driver hit the live graph."""
    app = create_app()

    def _live_session():
        with live_neo4j.session() as s:
            yield s

    app.dependency_overrides[get_session] = _live_session
    app.dependency_overrides[get_driver] = lambda: live_neo4j
    with TestClient(app) as c:
        # Ownership-scoped routes: authenticate as the User owning both profiles.
        c.headers["Authorization"] = f"Bearer {create_access_token(TEST_USER_ID, TEST_USER_EMAIL)}"
        yield c


@pytest.fixture(scope="module")
def snapshot(live_neo4j):
    return load_paris_corpus(live_neo4j, city_slug="paris")


@pytest.fixture(scope="module")
def ile_engine_route(snapshot):
    """The engine's own answer for the Île input — the reference the API must match."""
    tour_input = TourInput(
        start=ILE_START,
        duration_min=ILE_DURATION_MIN,
        city_slug="paris",
        lenses=None,
        round_trip=False,
    )
    # Same routing mode as the endpoint (RoutingClient; falls back to
    # haversine when local Valhalla is down) or stop-order comparisons
    # diverge whenever Valhalla is up.
    with RoutingClient() as rc:
        return select_route(tour_input, snapshot, routing_client=rc)


def _body(profile_id: str, **overrides) -> dict:
    body = {
        "profile_id": profile_id,
        "center_lat": ILE_START[0],
        "center_lng": ILE_START[1],
        "duration_min": ILE_DURATION_MIN,
        "round_trip": False,
        "start_date": "2026-06-12",
        "end_date": "2026-06-13",
        "start_time": "09:00",
    }
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def ile_response(client):
    """One engine-backed generation, shared by the response-shape assertions.

    Uses the no-lens profile so the engine input (lenses=None) matches
    ile_engine_route exactly.
    """
    resp = client.post("/api/v1/trips/generate", json=_body(NOLENS_PROFILE_ID))
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    return resp.json()


@needs_neo4j
class TestTripGenerateEngine:
    """The endpoint must surface the real engine's selection, order, and beats."""

    def test_response_shape(self, ile_response):
        data = ile_response
        assert isinstance(data["trip_id"], str) and data["trip_id"]
        assert data["profile_id"] == NOLENS_PROFILE_ID
        assert data["total_stops"] == len(data["stops"]) > 0
        assert data["anchor_count"] + data["flavour_count"] == data["total_stops"]
        assert isinstance(data["lens_coverage"], dict)
        for stop in data["stops"]:
            assert stop["beat_ids"], "every engine stop narrates at least one beat"
            assert stop["beat_id"] == stop["beat_ids"][0]
            assert stop["dwell_seconds"] >= 0
        # Primary-beat passthrough: the corpus' active beats carry script
        # bodies, so a generated trip must surface them (mobile's
        # audio-already-exists fast path reads these fields).
        assert any(s["script_body"] for s in data["stops"])

    def test_options_surface_k_flavours(self, ile_response):
        """M6: the response carries 1-3 RouteOptions; options[0]'s DWELL stops
        mirror the persisted trip; pairwise Jaccard over dwell sets < 0.60.

        Track B (B.3) interleaves band="vignette" walk-past stops into
        RouteOption.stops — additive annotations, not itinerary stops — so
        the mirror and diversity assertions are dwell-scoped (the persisted
        trip and the selection-time diversity filter are both dwell-only).
        """
        options = ile_response["options"]
        assert 1 <= len(options) <= 3

        def dwell_ids(option):
            return [s["poi_id"] for s in option["stops"] if s["band"] == "dwell"]

        assert dwell_ids(options[0]) == [s["poi_id"] for s in ile_response["stops"]]
        id_sets = [set(dwell_ids(o)) for o in options]
        for i in range(len(id_sets)):
            for j in range(i + 1, len(id_sets)):
                overlap = len(id_sets[i] & id_sets[j]) / len(id_sets[i] | id_sets[j])
                assert overlap < 0.60, f"options {i},{j} share {overlap:.0%}"
        for option in options:
            assert option["route_id"].startswith(ile_response["trip_id"])
            assert option["eta_seconds"] > 0
            assert option["stops"], "an option without stops is not an option"
            for stop in option["stops"]:
                assert stop["band"] in ("dwell", "vignette")

    def test_stop_order_matches_select_route(self, ile_response, ile_engine_route):
        expected = [p.id for p in ile_engine_route.pois]
        got = [s["poi_id"] for s in ile_response["stops"]]
        assert got == expected, (
            f"API stop order diverged from select_route. "
            f"Engine: {[p.name for p in ile_engine_route.pois]}; API poi_ids: {got}."
        )

    def test_beat_ids_traceable_to_route_pois(self, ile_response, ile_engine_route, snapshot):
        allowed = {
            poi.id: (
                {b.id for b in snapshot.beats_for(poi.id)}
                | {b.id for b in ile_engine_route.demoted_beats.get(poi.id, ())}
            )
            for poi in ile_engine_route.pois
        }
        for stop in ile_response["stops"]:
            orphans = set(stop["beat_ids"]) - allowed[stop["poi_id"]]
            assert not orphans, (
                f"Stop {stop['poi_name']} returned beat_ids not traceable to its "
                f"POI (or its demoted pool): {sorted(orphans)}"
            )

    def test_persists_multi_beat_graph(self, ile_response, live_neo4j):
        """Each ItineraryItem stores beat_ids + primary and one PLAYS_BEAT per beat."""
        with live_neo4j.session() as s:
            records = s.run(
                """
                MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(item:ItineraryItem)
                MATCH (item)-[:PLAYS_BEAT]->(beat:NarrativeBeat)
                WITH item, collect(beat.id) AS edge_beats
                RETURN item.sort_order AS sort_order,
                       item.beat_ids AS beat_ids,
                       item.primary_beat_id AS primary_beat_id,
                       edge_beats
                ORDER BY item.sort_order
                """,
                tid=ile_response["trip_id"],
            ).data()
        assert len(records) == ile_response["total_stops"]
        for item in records:
            assert item["beat_ids"], "item must store the engine's beat_ids"
            assert item["primary_beat_id"] == item["beat_ids"][0]
            assert sorted(item["edge_beats"]) == sorted(item["beat_ids"]), (
                "PLAYS_BEAT edges must cover exactly the stored beat_ids"
            )

    def test_persists_extra_beat_ids_for_keep_exploring(self, ile_response, live_neo4j):
        """KE1: each ItineraryItem persists its 'keep exploring here' extras
        (extra_beat_ids) and a null extra_narration (composed later at /compose).
        On the dense Île walk the per-tier cap (R1) always overflows at least one
        marquee stop, so the extras are genuinely non-empty."""
        with live_neo4j.session() as s:
            items = s.run(
                """
                MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(item:ItineraryItem)
                RETURN item.beat_ids AS beat_ids,
                       item.extra_beat_ids AS extra_beat_ids,
                       item.extra_narration AS extra_narration
                ORDER BY item.sort_order
                """,
                tid=ile_response["trip_id"],
            ).data()
        assert len(items) == ile_response["total_stops"]
        for it in items:
            assert it["extra_beat_ids"] is not None, "extra_beat_ids persisted (possibly empty)"
            assert it["extra_narration"] is None, "extra_narration is null until /compose"
            # extras never overlap the voiced beats (they are the un-voiced remainder)
            assert set(it["extra_beat_ids"]).isdisjoint(it["beat_ids"])
        assert any(it["extra_beat_ids"] for it in items), (
            "the dense Île walk must overflow the per-tier cap at ≥1 stop -> non-empty extras"
        )
        # and the API GET surfaces the same persisted extras
        for stop in ile_response["stops"]:
            assert "extra_beat_ids" in stop and stop.get("extra_narration") is None


@needs_neo4j
class TestTripGenerateLensPrecedence:
    """Request lenses win; else the profile's PREFERS_LENS; else unbiased."""

    def test_profile_lenses_feed_engine(self, client, snapshot):
        resp = client.post("/api/v1/trips/generate", json=_body(LENSED_PROFILE_ID))
        assert resp.status_code == 201, resp.text
        with RoutingClient() as rc:
            engine_route = select_route(
                TourInput(
                    start=ILE_START,
                    duration_min=ILE_DURATION_MIN,
                    city_slug="paris",
                    lenses=sorted(PROFILE_LENSES),  # the route sorts profile lenses
                    round_trip=False,
                ),
                snapshot,
                routing_client=rc,
            )
        got = [s["poi_id"] for s in resp.json()["stops"]]
        assert got == [p.id for p in engine_route.pois]

    def test_request_lenses_override_profile(self, client, snapshot):
        request_lenses = ["dark_history"]
        resp = client.post(
            "/api/v1/trips/generate",
            json=_body(LENSED_PROFILE_ID, lenses=request_lenses),
        )
        assert resp.status_code == 201, resp.text
        with RoutingClient() as rc:
            engine_route = select_route(
                TourInput(
                    start=ILE_START,
                    duration_min=ILE_DURATION_MIN,
                    city_slug="paris",
                    lenses=request_lenses,
                    round_trip=False,
                ),
                snapshot,
                routing_client=rc,
            )
        got = [s["poi_id"] for s in resp.json()["stops"]]
        assert got == [p.id for p in engine_route.pois]


@needs_neo4j
class TestTripGenerateErrors:
    def test_profile_not_found_404(self, client):
        resp = client.post(
            "/api/v1/trips/generate", json=_body("nonexistent-profile-id-xyz")
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_sparse_origin_refused_422(self, client):
        """The density gate's RED refusal maps to a structured 422 body. Sydney
        is far from every Paris POI, so there is no fixed-destination overshoot:
        gap_minutes is None and alternatives is empty (those only appear for an
        A→B feasibility refusal, exercised in TestTripGenerateFixedDestination)."""
        body = _body(NOLENS_PROFILE_ID, center_lat=-33.8688, center_lng=151.2093)
        resp = client.post("/api/v1/trips/generate", json=body)
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert isinstance(detail, dict)
        assert isinstance(detail["reason"], str) and detail["reason"]
        assert detail["gap_minutes"] is None
        assert detail["alternatives"] == []


# Versailles palace — a real Paris-region coordinate ~14km SW of the Île start.
# The routed A→B leg (or its haversine fallback) is hours long, dwarfing any
# tour walk budget, so a fixed-end A→B request from the Île GREEN start lands in
# the Step-2.2 fixed-destination feasibility refusal — never density-RED (the
# Île start stays GREEN at 90 min). Far enough that no selected POI snaps within
# B_SNAP_PROXIMITY_M, so the engine synthesizes a sentinel at B's exact coord.
VERSAILLES_END = (48.8049, 2.1204)


@needs_neo4j
class TestTripGenerateFixedDestination:
    """Step 2.6: end_lat/end_lng thread into TourInput.end; the route ends at B,
    and an unreachable B yields a structured 422 mirroring the Step-2.2 error."""

    def test_no_end_request_unchanged(self, ile_response, ile_engine_route):
        """A request WITHOUT end_lat/end_lng is the legacy open-walk path: the
        engine's end=None route is unchanged, so its last stop is unchanged."""
        engine_last = ile_engine_route.pois[-1].id
        api_last = ile_response["stops"][-1]["poi_id"]
        assert api_last == engine_last

    def test_ab_request_route_ends_at_b(self, client, snapshot, ile_engine_route):
        """An in-budget A→B request returns a route ending at B. B is the coord
        of a real POI the open Île route selected, so B-materialization snaps B
        onto a selected anchor: the API's final stop is the engine's fixed-end
        route's final POI (derived live, both via RoutingClient)."""
        # A selected anchor from the open route → guaranteed in-corridor and
        # reachable, so the A→B request is feasible (no refusal).
        b_poi = ile_engine_route.pois[-1]
        b_end = (b_poi.lat, b_poi.lng)
        with RoutingClient() as rc:
            engine_route = select_route(
                TourInput(
                    start=ILE_START,
                    duration_min=ILE_DURATION_MIN,
                    city_slug="paris",
                    lenses=None,
                    round_trip=False,
                    end=b_end,
                ),
                snapshot,
                routing_client=rc,
            )
        resp = client.post(
            "/api/v1/trips/generate",
            json=_body(NOLENS_PROFILE_ID, end_lat=b_end[0], end_lng=b_end[1]),
        )
        assert resp.status_code == 201, resp.text
        got = [s["poi_id"] for s in resp.json()["stops"]]
        expected = [p.id for p in engine_route.pois]
        assert got == expected, (
            f"API order diverged from fixed-end select_route: {got} vs {expected}"
        )
        # The route literally ends at B (the materialized fixed_end).
        assert got[-1] == engine_route.pois[-1].id

    def test_over_budget_ab_returns_structured_422(self, client, snapshot):
        """An A→B request whose routed A→B leg exceeds the walk budget returns a
        422 whose JSON body matches the live Step-2.2 TourabilityRefusedError:
        {reason, gap_minutes, alternatives:[{kind,...}]} with the kind enum
        (loop/extend, plus closer_b when an anchor fits the budget)."""
        # Reproduce the endpoint's own engine call to derive the truth live —
        # robust whether Valhalla is up (routed leg) or down (haversine).
        tour_input = TourInput(
            start=ILE_START,
            duration_min=ILE_DURATION_MIN,
            city_slug="paris",
            lenses=None,
            round_trip=False,
            end=VERSAILLES_END,
        )
        with (
            RoutingClient() as rc,
            pytest.raises(TourabilityRefusedError) as caught,
        ):
            select_k_routes(tour_input, snapshot, 3, routing_client=rc)
        exc = caught.value
        # Guard: this must be the FIXED-DESTINATION feasibility refusal (carries
        # gap_minutes + alternatives), not a plain density-RED refusal.
        assert exc.gap_minutes is not None and exc.gap_minutes > 0
        assert exc.alternatives, "fixed-destination refusal must offer alternatives"
        expected_kinds = [a.kind for a in exc.alternatives]
        assert {"loop", "extend"} <= set(expected_kinds)
        assert set(expected_kinds) <= {"loop", "extend", "closer_b"}

        resp = client.post(
            "/api/v1/trips/generate",
            json=_body(NOLENS_PROFILE_ID, end_lat=VERSAILLES_END[0], end_lng=VERSAILLES_END[1]),
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert isinstance(detail, dict)
        assert detail["reason"] == str(exc)
        assert detail["gap_minutes"] == exc.gap_minutes
        # The structured alternatives mirror the engine's FeasibilityAlternative
        # tuple field-for-field (kind enum + duration_min/drop_end/poi_id/lat/lng).
        assert [a["kind"] for a in detail["alternatives"]] == expected_kinds
        assert detail["alternatives"] == [
            {
                "kind": a.kind,
                "duration_min": a.duration_min,
                "drop_end": a.drop_end,
                "poi_id": a.poi_id,
                "lat": a.lat,
                "lng": a.lng,
            }
            for a in exc.alternatives
        ]


class TestPreviewTrip:
    """POST /trips/preview (Phase 1.5d): engine narration, no profile, no persistence."""

    def test_preview_returns_per_stop_narration(self, client):
        resp = client.post(
            "/api/v1/trips/preview",
            json={
                "center_lat": ILE_START[0],
                "center_lng": ILE_START[1],
                "duration_min": ILE_DURATION_MIN,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["candidate_eligible"]:
            assert data["narration_kind"] == "llm_candidate"
            assert data["basic_tour"] is None
            selected_stops = data["stops"]
            selected_audio_min = data["total_audio_min"]
        else:
            assert data["narration_kind"] == "none"
            assert data["stops"] == []
            assert data["basic_tour"] is not None
            selected_stops = data["basic_tour"]["stops"]
            selected_audio_min = data["basic_tour"]["total_audio_min"]
        assert selected_stops, "preview should return narration in exactly one lane"
        for stop in selected_stops:
            assert stop["poi_name"]
            assert stop["narration"].strip(), "each stop must carry narration text"
        assert selected_audio_min >= 1

    def test_preview_sparse_origin_422(self, client):
        resp = client.post(
            "/api/v1/trips/preview",
            json={"center_lat": -33.8688, "center_lng": 151.2093, "duration_min": 90},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Phase 4 Step 4.7 — POST /trips/{trip_id}/compose
# ---------------------------------------------------------------------------

COMPOSE_MARKER = "COMPOSED-MARKER: the story, retold for you."


class _MarkerAuthoringExecutor:
    """Deterministic author: opens the first stop with a recognizable phrase —
    route-independent proof that the AUTHORED output (not the stitch) was persisted.

    It edits sentence TEXT only and leaves every citation alone, so the marker is
    the single variable: anything that fails afterwards is a real gate finding, not
    the double inventing an untraceable sentence.
    """

    cost_bearing = False
    provider_name = "offline"

    def execute(self, unit) -> PhysicalProviderResponse:
        sentences = [s.model_dump(mode="json") for s in unit.authorized_request.stitched.script]
        if unit.stop_index == 0:
            sentences[0] = {
                **sentences[0],
                "text": f"{COMPOSE_MARKER} {sentences[0]['text']}",
            }
        return _offline_response(unit, sentences)


def _provider_bytes(sentences: list[dict]) -> bytes:
    """The exact JSON envelope the per-stop authoring seam parses back."""
    return json.dumps(
        {"sentences": sentences},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _offline_response(unit, sentences: list[dict]) -> PhysicalProviderResponse:
    return PhysicalProviderResponse(
        body=_provider_bytes(sentences),
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        model=COMPOSE_MODEL,
        provider_request_id=f"offline-{unit.stop_index}",
        stop_reason="end_turn",
    )


class _PerStopCountingExecutor:
    """A COST-BEARING physical-boundary double for the per-stop authoring seam.

    It records which dwell stop each physical call was made for and echoes the
    grounded stitch straight back, so the assertions are on the number of calls the
    endpoint actually made — not on a status code that could be green with the old
    whole-tour composer still doing the work. ``cost_bearing`` is True on purpose:
    the spend guard only arms for billable providers, so a $0 stub could never
    prove the reservation.
    """

    cost_bearing = True
    provider_name = "anthropic"

    def __init__(self) -> None:
        self.stop_calls: list[int] = []
        self._lock = threading.Lock()

    def execute(self, unit) -> PhysicalProviderResponse:
        with self._lock:
            self.stop_calls.append(unit.stop_index)
        return _offline_response(
            unit,
            [s.model_dump(mode="json") for s in unit.authorized_request.stitched.script],
        )


class _HallucinatingExecutor:
    """Authors one sentence citing a beat that is not in the grounded source.

    That is the untraceable-citation half of VERIFY, so the per-stop finalizer must
    refuse the whole tour. $0 and non-billing, so it reserves nothing and the spend
    assertions in the same test stay about the paid path.
    """

    cost_bearing = False
    provider_name = "offline"

    def execute(self, unit) -> PhysicalProviderResponse:
        sentences = [s.model_dump(mode="json") for s in unit.authorized_request.stitched.script]
        sentences[0] = {
            **sentences[0],
            "source_id": "beat-that-was-never-in-the-corpus",
            "source_type": "beat",
            "also_cites": [],
        }
        return _offline_response(unit, sentences)


def _override_dep(client, dep: str, value):
    """Swap a FastAPI dependency for a test double; returns the override key."""
    from src.api import dependencies

    target = getattr(dependencies, dep)
    client.app.dependency_overrides[target] = lambda: value
    return target


def _clear_dep(client, target) -> None:
    client.app.dependency_overrides.pop(target, None)


@pytest.fixture()
def cutover_trip(client):
    """One freshly generated, not-yet-composed trip on the live corpus."""
    resp = client.post("/api/v1/trips/generate", json=_body(NOLENS_PROFILE_ID))
    assert resp.status_code == 201, resp.text
    return resp.json()


@needs_neo4j
def test_compose_authors_per_stop_and_keeps_the_wire_contract(client, live_neo4j, cutover_trip):
    """AC-3 + AC-7 — the pinned gate for the compose cutover.

    Every clause lives in this one node id on purpose, because each of them is
    a way the cutover could go wrong while the endpoint still looked healthy:

    * the ENGINE is the per-stop authoring seam — proven by counting physical
      calls at the injected provider boundary (one per dwell stop), not by the
      status code, which the old whole-tour composer would also return 200 for;
    * the WIRE CONTRACT the phone parses is unchanged — 200 with fresh stop ids
      and persisted extra_narration, 409 already_composed, 404 for an unknown
      trip and for an unknown route_id, and a 422 whose detail carries BOTH
      ``reason == "compose_verification_failed"`` and ``attempts``
      (mobile/lib/services/trip_service.dart:227-229 reads exactly those two);
    * the SPEND PRECHECK reserves the real call count (n_stops, not 1) and runs
      AFTER the already-composed check, so a duplicate compose is a 409 that
      reserves nothing and calls nobody.
    """
    trip_id = cutover_trip["trip_id"]
    n_stops = len(cutover_trip["stops"])
    assert n_stops > 1, "a one-stop trip cannot tell per-stop authoring from whole-tour"
    generated_stop_ids = {st["stop_id"] for st in cutover_trip["stops"]}

    def trip_row():
        with live_neo4j.session() as s:
            items = s.run(
                "MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) "
                "RETURN i.id AS id, i.narration AS narration, "
                "i.extra_narration AS extra_narration, i.audio_url AS audio "
                "ORDER BY i.sort_order",
                tid=trip_id,
            ).data()
            composed_route = s.run(
                "MATCH (t:Trip {id: $tid}) RETURN t.composed_route_id AS rid", tid=trip_id
            ).single()["rid"]
        return items, composed_route

    # --- 404: unknown trip, and an unknown route_id on a real trip ---------
    assert (
        client.post(
            "/api/v1/trips/no-such-trip/compose", json={"route_id": "no-such-trip-opt1"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt99"}
        ).status_code
        == 404
    )

    # --- 422: an unauthorable flavour is refused, and nothing is persisted --
    before_items, before_route = trip_row()
    assert before_route is None
    target = _override_dep(client, "get_premium_compose_executor", _HallucinatingExecutor())
    try:
        refused = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
    finally:
        _clear_dep(client, target)
    assert refused.status_code == 422, refused.text
    detail = refused.json()["detail"]
    assert detail["reason"] == "compose_verification_failed"
    assert detail["attempts"] >= 1, "the phone reads detail['attempts'] and must find it"
    assert detail["untraceable"] > 0, "the hallucinated citation must be the named cause"
    assert trip_row() == (before_items, None), "a refusal must leave the trip untouched"

    # --- 200: one physical call per dwell stop ----------------------------
    # (A reset_spend_guard() call sat here to clear the rate limiter's counters
    # between phases. The limiter was deleted 2026-07-31 by owner order, so there
    # is nothing to reset.)
    executor = _PerStopCountingExecutor()
    target = _override_dep(client, "get_premium_compose_executor", executor)
    try:
        resp = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # THE CUTOVER ITSELF: one authoring call per dwell stop, at the seam.
        assert sorted(executor.stop_calls) == list(range(n_stops)), (
            "compose did not author the persisted route stop-by-stop through the "
            f"injected seam (calls: {sorted(executor.stop_calls)})"
        )
        # (AC-7 asserted here that the rate limiter reserved one unit per dwell
        # stop rather than a flat 1. The limiter was DELETED 2026-07-31 by owner
        # order, so there is no reservation to check. The per-stop authoring
        # itself is still proven, by the stop_calls assertion directly above.)

        # The wire contract the phone and the workbench read.
        assert data["trip_id"] == trip_id
        assert data["route_id"] == f"{trip_id}-opt1"
        assert data["attempts"] >= 1
        assert len(data["stops"]) == n_stops
        assert not ({st["stop_id"] for st in data["stops"]} & generated_stop_ids), (
            "compose must re-persist the stops under FRESH item ids"
        )
        items, composed_route = trip_row()
        assert composed_route == f"{trip_id}-opt1"
        assert [i["id"] for i in items] == [st["stop_id"] for st in data["stops"]]
        assert all(i["audio"] is None for i in items), "compose voices nothing"
        assert all(st["narration"] for st in data["stops"]), "every stop is narrated"
        # extra_narration is persisted, and exactly for the stops that have extras.
        assert any(i["extra_narration"] for i in items), (
            "the dense Île walk overflows at least one stop, so /compose must "
            "persist its keep-exploring narration"
        )
        for stop, item in zip(data["stops"], items, strict=True):
            assert stop["extra_narration"] == item["extra_narration"]
            assert bool(item["extra_narration"]) == bool(stop["extra_beat_ids"])

        # --- 409: a duplicate compose costs nothing ------------------------
        calls_after_success = list(executor.stop_calls)
        second = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
        assert second.status_code == 409
        assert second.json()["detail"]["reason"] == "already_composed"
        assert executor.stop_calls == calls_after_success, (
            "the already-composed trip still reached the provider"
        )
    finally:
        _clear_dep(client, target)


@needs_neo4j
class TestComposeTripEndpoint:
    @pytest.fixture()
    def fresh_trip(self, client):
        resp = client.post("/api/v1/trips/generate", json=_body(NOLENS_PROFILE_ID))
        assert resp.status_code == 201, resp.text
        return resp.json()

    def _override(self, client, dep, value):
        return _override_dep(client, dep, value)

    def _clear(self, client, target):
        _clear_dep(client, target)


    def test_compose_persists_marker_narration_with_fresh_stop_ids(
        self, client, live_neo4j, fresh_trip
    ):
        trip_id = fresh_trip["trip_id"]
        target = self._override(
            client, "get_premium_compose_executor", _MarkerAuthoringExecutor()
        )
        try:
            resp = client.post(
                f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
            )
        finally:
            self._clear(client, target)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["trip_id"] == trip_id
        assert data["route_id"] == f"{trip_id}-opt1"
        assert data["attempts"] == 1
        assert len(data["stops"]) == len(fresh_trip["stops"])
        # The composed marker landed in the persisted stop-0 narration...
        assert data["stops"][0]["narration"].startswith(COMPOSE_MARKER)
        # ...and the DB agrees: fresh items, marker narration, NO audio fields.
        with live_neo4j.session() as s:
            rows = s.run(
                "MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) "
                "RETURN i.id AS id, i.narration AS narration, i.audio_url AS audio "
                "ORDER BY i.sort_order",
                tid=trip_id,
            ).data()
            composed_route = s.run(
                "MATCH (t:Trip {id: $tid}) RETURN t.composed_route_id AS rid", tid=trip_id
            ).single()["rid"]
        assert [r["id"] for r in rows] == [st["stop_id"] for st in data["stops"]]
        assert rows[0]["narration"].startswith(COMPOSE_MARKER)
        assert all(r["audio"] is None for r in rows)
        assert composed_route == f"{trip_id}-opt1"

    def test_compose_persists_extra_narration_traceable_to_extra_beats(
        self, client, live_neo4j, fresh_trip, snapshot
    ):
        """KE2: /compose stitches each stop's overflow corpus beats into
        ``extra_narration`` DETERMINISTICALLY (no LLM/VERIFY — the extras are
        faithful curated beats). The persisted ItineraryItems must carry:
        non-empty extra_narration exactly for stops WITH extra_beat_ids, None for
        stops without, and text drawn ONLY from those extra beats' script_body."""
        trip_id = fresh_trip["trip_id"]
        from src.tour.generation import split_sentences

        resp = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
        assert resp.status_code == 200, resp.text

        with live_neo4j.session() as s:
            items = s.run(
                """
                MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(item:ItineraryItem)
                RETURN item.beat_ids AS beat_ids,
                       item.extra_beat_ids AS extra_beat_ids,
                       item.extra_narration AS extra_narration
                ORDER BY item.sort_order
                """,
                tid=trip_id,
            ).data()

        beats_by_id = {
            ref.id: ref for refs in snapshot.beats_by_poi.values() for ref in refs
        }

        def _stitch(beat_ids):
            # Same deterministic stitch the endpoint uses: each extra beat's body
            # split into sentences and space-joined, in extra_beat_ids order.
            sents: list[str] = []
            for bid in beat_ids:
                ref = beats_by_id.get(bid)
                if ref and ref.script_body:
                    sents.extend(split_sentences(ref.script_body))
            return " ".join(sents)

        saw_extras = False
        for it in items:
            extras = it["extra_beat_ids"] or []
            if extras:
                saw_extras = True
                assert it["extra_narration"], (
                    "a stop WITH extra_beat_ids must carry a non-empty extra_narration"
                )
                # extra_narration is EXACTLY the deterministic stitch of THIS stop's
                # extra beats' script_body — no LLM invention, only corpus text, and
                # consistent with the persisted extra_beat_ids order.
                assert it["extra_narration"] == _stitch(extras), (
                    "extra_narration must be the deterministic stitch of its extra beats"
                )
                # Traceability, the human-readable way: each contributing extra beat's
                # (normalized) body is a substring of the narration.
                for bid in extras:
                    ref = beats_by_id.get(bid)
                    if ref and ref.script_body:
                        body = " ".join(split_sentences(ref.script_body))
                        assert body in it["extra_narration"], (
                            f"extra beat {bid} body not found verbatim in extra_narration"
                        )
            else:
                assert it["extra_narration"] is None, (
                    "a stop with NO extra_beat_ids must have a null extra_narration"
                )
        assert saw_extras, "the dense Île walk must overflow ≥1 stop -> extras to voice"
        # The compose response surfaces the same extra_narration it persisted.
        for stop in resp.json()["stops"]:
            if stop.get("extra_beat_ids"):
                assert stop.get("extra_narration")

    def test_second_compose_is_conflict(self, client, fresh_trip):
        trip_id = fresh_trip["trip_id"]
        first = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
        assert first.status_code == 200, first.text
        second = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
        )
        assert second.status_code == 409
        assert second.json()["detail"]["reason"] == "already_composed"

    def test_unknown_route_id_and_trip_are_404(self, client, fresh_trip):
        trip_id = fresh_trip["trip_id"]
        bad_opt = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt99"}
        )
        assert bad_opt.status_code == 404
        no_trip = client.post(
            "/api/v1/trips/no-such-trip/compose", json={"route_id": "no-such-trip-opt1"}
        )
        assert no_trip.status_code == 404

    def test_refused_flavour_is_422_and_leaves_trip_untouched(
        self, client, live_neo4j, fresh_trip
    ):
        """A flavour VERIFY refuses must never reach Neo4j.

        The refusal is triggered through the gate the per-stop path runs TODAY —
        source traceability, via an authored sentence citing a beat that is not in
        the grounded source. It used to be triggered through the entailment checker,
        which the whole-tour composer took as an injected dependency; the per-stop
        finalizer does not accept one yet, so injecting a rejecting checker here
        would assert nothing at all. Restoring the real faithfulness entailment and
        the coverage baseline on this path is the NEXT step of the ledger (A4,
        AC-5), and until it lands the persisted path's anti-hallucination gate is
        the structural half only. What this test pins either way is the part that
        matters most: a refusal costs the trip nothing.
        """
        trip_id = fresh_trip["trip_id"]

        def narrations():
            with live_neo4j.session() as s:
                return s.run(
                    "MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) "
                    "RETURN i.id AS id, i.narration AS narration ORDER BY i.sort_order",
                    tid=trip_id,
                ).data()

        before = narrations()
        target = self._override(
            client, "get_premium_compose_executor", _HallucinatingExecutor()
        )
        try:
            resp = client.post(
                f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"}
            )
        finally:
            self._clear(client, target)
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert detail["reason"] == "compose_verification_failed"
        # One physical call per stop and no retry, so the count the phone reads is 1.
        assert detail["attempts"] == 1
        assert detail["untraceable"] > 0
        # The refusal left the trip exactly as generated — same items, same
        # narration, and no composed_route_id (another flavour can be tried).
        assert narrations() == before
        with live_neo4j.session() as s:
            rid = s.run(
                "MATCH (t:Trip {id: $tid}) RETURN t.composed_route_id AS rid", tid=trip_id
            ).single()["rid"]
        assert rid is None

    def test_generate_persists_per_flavour_anchor_identity(self, live_neo4j, fresh_trip):
        """C9f-i: options_json entries are per-flavour dicts carrying the C9
        exempt-anchor identity ({poi_ids, start_anchor_poi_id, fixed_end_poi_id}),
        so /compose restores the SAME exempt set the greedy used (pois[0] is not
        the start-anchor after Held-Karp). fresh_trip is an open walk, so at least
        one flavour records a positional start-anchor."""
        trip_id = fresh_trip["trip_id"]
        with live_neo4j.session() as s:
            from src.api.crud.trips import get_trip_compose_inputs

            options = get_trip_compose_inputs(s, trip_id)["options"]
        assert options and all(isinstance(e, dict) for e in options)
        for e in options:
            assert set(e) >= {"poi_ids", "start_anchor_poi_id", "fixed_end_poi_id"}
            if e["start_anchor_poi_id"] is not None:
                assert e["start_anchor_poi_id"] in e["poi_ids"]
            if e["fixed_end_poi_id"] is not None:
                assert e["fixed_end_poi_id"] in e["poi_ids"]
        # Not vacuously all-None: an open walk seats a positional start-anchor.
        assert any(e["start_anchor_poi_id"] is not None for e in options)

    def test_second_option_composes_its_stored_pick(self, client, live_neo4j, fresh_trip):
        trip_id = fresh_trip["trip_id"]
        with live_neo4j.session() as s:
            from src.api.crud.trips import get_trip_compose_inputs

            stored = get_trip_compose_inputs(s, trip_id)
        options = stored["options"]
        assert len(options) >= 2, "dense Île generation must preserve a second route option"
        resp = client.post(
            f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt2"}
        )
        assert resp.status_code == 200, resp.text
        # C9f-i: options entries are per-flavour {poi_ids, anchor ids} dicts.
        assert [st["poi_id"] for st in resp.json()["stops"]] == options[1]["poi_ids"]
