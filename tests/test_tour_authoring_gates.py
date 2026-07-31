"""AC-5 — the anti-hallucination gates on the PERSISTED path (`POST /trips/{id}/compose`).

The cutover (step A3) swapped that endpoint's engine to the per-stop authoring seam.
The seam's finalizer was built for the CERTIFICATION replay, which deliberately runs a
structural-only validator, the trusting offline entailment stub, and no coverage
baseline at all.  Moving the persisted endpoint onto it therefore silently dropped
three gates the whole-tour composer had wired for it (ledger decision D3):

* the REAL faithfulness checker (``get_faithfulness_checker`` -> Haiku entailment),
* the coverage baseline (``claims_realized_by`` on the pre-compose stitch), so a bold
  fusion cannot silently DELETE a fact the stitch voiced,
* the full ``validate_script`` scan — the forbidden-phrase / invented-proper-noun /
  invented-year check over glue, which structural traceability cannot see.

Parity with the pre-cutover endpoint ONLY: no new checks, and the certification replay
keeps its own (unchanged) defaults, which is why the three arrive as injectable
parameters rather than as a new default.

``test_unfaithful_output_is_refused_and_trip_untouched`` is the ledger's pinned gate for
this step, so every clause lives inside that one node id: unwiring ANY of the three in
``src/tour/authoring.py`` or ``src/api/routes/trips.py`` must turn it red.

The endpoint is driven for real (live Paris dev graph, a disposable profile and trip)
because the claim under test is not "the finalizer can refuse" but "the PERSISTED path
refuses AND writes nothing" — a gate that runs after the write would look identical at
the seam and lose the trip.  Every provider boundary is a $0 injected double.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.auth.tokens import create_access_token
from src.api.dependencies import get_driver, get_session
from src.tour.authoring import COMPOSE_MODEL, author_prebuilt_route, plan_prebuilt_route_authoring
from src.tour.certification_provider import PhysicalProviderResponse
from src.tour.contract import (
    POI,
    BeatRef,
    BeatSequence,
    POIBeats,
    Route,
    Script,
    ScriptPOI,
    Sentence,
    TourInput,
    TransitSegment,
    ValidationReport,
)
from src.tour.generation import GLUE_REFLECTION
from src.tour.premium_authorities import PREMIUM_AUTHORITIES
from src.tour.premium_tour import (
    PremiumComposeUnit,
    PremiumTourPlan,
    finalize_premium_composition,
    premium_authoring_policy_sha256,
)
from tests.conftest import needs_neo4j
from tests.live_graph import open_dev_driver

# Disposable identities of this module's own (never shared with another test module,
# so a crash here cannot strand another module's fixtures).
PROFILE_ID = "authoring-gates-test-profile"
TEST_USER_ID = "authoring-gates-test-user"
TEST_USER_EMAIL = "authoring-gates@example.test"

# Same known-GREEN multi-stop start as tests/test_trip_api.py (the Île walk).
ILE_START = (48.8568, 2.3414)
ILE_DURATION_MIN = 90

#: A proper noun and a year that appear NOWHERE in the Paris corpus, so a glue
#: sentence carrying them is unambiguously runtime invention.
INVENTED_NAME = "Zarnovia"
INVENTED_YEAR = "1043"

#: What the claim-blurring executor writes over every beat sentence: grammatical,
#: traceable, and sharing no content tokens with any key_claim — so the ONLY gate
#: that can catch it is the coverage baseline.
BLURRED_TEXT = "That much is written down."


def _delete_test_artifacts(driver) -> None:
    with driver.session() as s:
        s.run(
            "MATCH (p:Profile {id: $pid}) "
            "OPTIONAL MATCH (p)-[:IS_CAPTAIN_OF]->(t:Trip) "
            "OPTIONAL MATCH (t)-[:HAS_STOP]->(i:ItineraryItem) "
            "DETACH DELETE t, i",
            pid=PROFILE_ID,
        )
        s.run("MATCH (p:Profile {id: $pid}) DETACH DELETE p", pid=PROFILE_ID)
        s.run("MATCH (u:User {id: $uid}) DETACH DELETE u", uid=TEST_USER_ID)


@pytest.fixture(scope="module")
def live_neo4j():
    driver = open_dev_driver()
    if driver is None:
        pytest.skip(
            "Local Paris dev Neo4j unreachable. This module writes disposable records "
            "and refuses anything but localhost:7687. Run it through "
            "`make test-file FILE=tests/test_tour_authoring_gates.py`."
        )
    yield driver
    driver.close()


@pytest.fixture(scope="module")
def test_profile(live_neo4j):
    _delete_test_artifacts(live_neo4j)  # residue from any crashed prior run
    with live_neo4j.session() as s:
        s.run(
            "MERGE (u:User {id: $uid}) SET u.email = $email",
            uid=TEST_USER_ID,
            email=TEST_USER_EMAIL,
        )
        s.run(
            "MERGE (p:Profile {id: $pid}) SET p.display_name = 'Authoring Gates Test' "
            "WITH p MATCH (u:User {id: $uid}) MERGE (u)-[:HAS_PROFILE]->(p)",
            pid=PROFILE_ID,
            uid=TEST_USER_ID,
        )
    yield
    _delete_test_artifacts(live_neo4j)


@pytest.fixture(scope="module")
def client(live_neo4j, test_profile):
    """TestClient whose request sessions AND engine corpus driver hit the live graph."""
    app = create_app()

    def _live_session():
        with live_neo4j.session() as s:
            yield s

    app.dependency_overrides[get_session] = _live_session
    app.dependency_overrides[get_driver] = lambda: live_neo4j
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {create_access_token(TEST_USER_ID, TEST_USER_EMAIL)}"
        yield c


@pytest.fixture()
def fresh_trip(client):
    """One freshly generated, not-yet-composed trip on the live corpus.

    The glue client is the offline double here, bound once in ``tests/conftest.py``
    (the same door the $0 audio seam uses) rather than per-module. Without it this
    fixture builds a real paid Anthropic client — ``src/tour/generation.py`` is
    real-by-default now and ``POST /trips/generate`` has no injection seam — and
    both tests in this module error at setup instead of running.
    """
    resp = client.post(
        "/api/v1/trips/generate",
        json={
            "profile_id": PROFILE_ID,
            "center_lat": ILE_START[0],
            "center_lng": ILE_START[1],
            "duration_min": ILE_DURATION_MIN,
            "round_trip": False,
            "start_date": "2026-06-12",
            "end_date": "2026-06-13",
            "start_time": "09:00",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# $0 provider doubles — one per gate, each defective in exactly ONE way
# ---------------------------------------------------------------------------


def _offline_response(unit, sentences: list[dict]) -> PhysicalProviderResponse:
    body = json.dumps(
        {"sentences": sentences},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return PhysicalProviderResponse(
        body=body,
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        model=COMPOSE_MODEL,
        provider_request_id=f"offline-{unit.stop_index}",
        stop_reason="end_turn",
    )


def _stitched(unit) -> list[dict]:
    return [s.model_dump(mode="json") for s in unit.authorized_request.stitched.script]


class _RewritingExecutor:
    """Rewrites every beat sentence so it is no longer VERBATIM corpus text.

    That matters: ``verify_faithfulness`` short-circuits a sentence found verbatim in
    its beat's ``script_body`` (the corpus is canonical), so an echo-the-stitch double
    would never reach the entailment checker at all and could not tell a wired checker
    from an unwired one. The original text is kept INSIDE the rewrite, so the coverage
    baseline still sees every claim realized — faithfulness is the only gate that can
    fire.
    """

    cost_bearing = False
    provider_name = "offline"

    def execute(self, unit) -> PhysicalProviderResponse:
        sentences = []
        for sentence in _stitched(unit):
            if sentence["source_type"] == "beat":
                sentence = {**sentence, "text": f"Here is the thing, {sentence['text']}"}
            sentences.append(sentence)
        return _offline_response(unit, sentences)


class _ClaimBlurringExecutor:
    """Deletes the FACTS while keeping the structure: every beat sentence is replaced
    by one grounded-looking, claim-free line.

    Citations, sentence counts and stop indices are untouched, so traceability, the
    glue scan and (under the trusting offline checker) faithfulness all pass. The only
    thing wrong with this tour is that the facts the stitch voiced are gone — which is
    exactly and only what the coverage baseline catches.
    """

    cost_bearing = False
    provider_name = "offline"

    def execute(self, unit) -> PhysicalProviderResponse:
        sentences = []
        for sentence in _stitched(unit):
            if sentence["source_type"] == "beat":
                sentence = {**sentence, "text": BLURRED_TEXT}
            sentences.append(sentence)
        return _offline_response(unit, sentences)


class _InventingGlueExecutor:
    """Adds a proper noun and a year no cited beat carries to a GLUE sentence.

    Glue keeps its own traceable ``source_id`` and every beat sentence is echoed back
    byte-identically, so traceability, faithfulness and coverage are all satisfied:
    only ``validate_script``'s forbidden-phrase / invented-noun / invented-year scan
    can see this. Reflection glue is left alone — it is fail-closed under a DIFFERENT
    gate (entailment), which would muddy the proof.
    """

    cost_bearing = False
    provider_name = "offline"

    def __init__(self) -> None:
        self.stops_invented: list[int] = []
        self._lock = threading.Lock()

    def execute(self, unit) -> PhysicalProviderResponse:
        sentences = []
        invented = False
        for sentence in _stitched(unit):
            if (
                not invented
                and sentence["source_type"] != "beat"
                and sentence["source_id"] != GLUE_REFLECTION
            ):
                sentence = {
                    **sentence,
                    "text": (
                        f"{sentence['text']} The court had moved to "
                        f"{INVENTED_NAME} by {INVENTED_YEAR}."
                    ),
                }
                invented = True
            sentences.append(sentence)
        if invented:
            with self._lock:
                self.stops_invented.append(unit.stop_index)
        return _offline_response(unit, sentences)


class _RejectingChecker:
    """A faithfulness checker that entails NOTHING, and records that it was asked.

    ``verify_faithfulness`` fans the entailment calls out across a thread pool, so the
    call log is locked.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str]] = []
        self._lock = threading.Lock()

    def entails(self, key_claims: tuple[str, ...], sentence_text: str) -> bool:
        with self._lock:
            self.calls.append((key_claims, sentence_text))
        return False


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _override_dep(client, dep: str, value):
    from src.api import dependencies

    target = getattr(dependencies, dep)
    client.app.dependency_overrides[target] = lambda: value
    return target


def _clear_dep(client, target) -> None:
    client.app.dependency_overrides.pop(target, None)


def _persisted(live_neo4j, trip_id: str) -> dict:
    """Every property of every persisted stop, plus the composed marker.

    ``properties(i)`` rather than a hand-listed projection: "byte-unchanged" has to
    mean the whole node, or a gate that rewrote a field this test forgot to name
    would still look clean.
    """
    with live_neo4j.session() as s:
        stops = s.run(
            "MATCH (t:Trip {id: $tid})-[:HAS_STOP]->(i:ItineraryItem) "
            "RETURN properties(i) AS props ORDER BY i.sort_order",
            tid=trip_id,
        ).data()
        composed_route_id = s.run(
            "MATCH (t:Trip {id: $tid}) RETURN t.composed_route_id AS rid", tid=trip_id
        ).single()["rid"]
    return {"stops": [row["props"] for row in stops], "composed_route_id": composed_route_id}


def _compose(client, trip_id: str):
    return client.post(f"/api/v1/trips/{trip_id}/compose", json={"route_id": f"{trip_id}-opt1"})


def _refusal_detail(resp, caplog) -> dict:
    """The 422 body, having first established the refusal came from the GATE.

    The route turns a seam ``ValueError`` (an unauthorable shape, an unparseable
    payload) into a byte-identical 422 — same reason, same zeroed counts — and logs it.
    Without this check a coverage assertion of the form "422 with every reported count
    at zero" would be satisfied by a crash that never ran a gate at all.
    """
    assert resp.status_code == 422, resp.text
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not errors, (
        "the endpoint logged an error, so this 422 is the seam's ValueError branch "
        f"rather than a VERIFY refusal: {[r.getMessage() for r in errors]}"
    )
    detail = resp.json()["detail"]
    assert detail["reason"] == "compose_verification_failed"
    assert detail["attempts"] == 1, "the phone reads detail['attempts']"
    return detail


@needs_neo4j
def test_unfaithful_output_is_refused_and_trip_untouched(client, live_neo4j, fresh_trip, caplog):
    """AC-5 end to end — the pinned gate for this step.

    All three gates live in this one node id on purpose, because each is a way the
    persisted path could keep returning 200 while the trip it persists is unverified:

    * FAITHFULNESS — an injected rejecting checker must actually be consulted and must
      refuse the tour. Proven by the checker's own call log AND by the refusal, so
      neither a checker that is built-but-ignored nor a gate that fires without it
      passes;
    * COVERAGE — a tour whose facts were deleted (citations intact) is refused;
    * INVENTION — glue carrying a proper noun and a year no cited beat has is refused.

    And after every one of them the trip's stops in Neo4j are byte-unchanged and the
    trip is still uncomposed, so the client can offer another flavour (decision D2).
    """
    trip_id = fresh_trip["trip_id"]
    before = _persisted(live_neo4j, trip_id)
    assert before["composed_route_id"] is None
    assert len(before["stops"]) > 1, "a one-stop trip cannot exercise a per-stop gate"

    # --- FAITHFULNESS: the real (injected) checker runs, per stop -------------
    checker = _RejectingChecker()
    checker_target = _override_dep(client, "get_faithfulness_checker", checker)
    executor_target = _override_dep(client, "get_premium_compose_executor", _RewritingExecutor())
    try:
        with caplog.at_level(logging.ERROR, logger="ondoway.api"):
            resp = _compose(client, trip_id)
        detail = _refusal_detail(resp, caplog)
        assert checker.calls, (
            "the faithfulness checker the endpoint depends on was never consulted — "
            "the per-stop finalizer is still verifying with the trusting offline stub"
        )
        assert detail["faithfulness"] > 0, (
            f"a rewritten tour that entails NOTHING was not refused on faithfulness: {detail}"
        )
        assert detail["untraceable"] == 0 and detail["forbidden"] == 0, (
            f"the double should trip faithfulness and nothing else: {detail}"
        )
        assert _persisted(live_neo4j, trip_id) == before, (
            "the trip was mutated by a compose that FAILED verification"
        )
    finally:
        _clear_dep(client, checker_target)
        _clear_dep(client, executor_target)

    # --- COVERAGE: facts deleted, citations intact ----------------------------
    caplog.clear()
    executor_target = _override_dep(
        client, "get_premium_compose_executor", _ClaimBlurringExecutor()
    )
    try:
        with caplog.at_level(logging.ERROR, logger="ondoway.api"):
            resp = _compose(client, trip_id)
        detail = _refusal_detail(resp, caplog)
        # Coverage is the ONLY gate this double can trip, and the wire deliberately
        # does not carry a coverage count — so "refused with every reported count at
        # zero" IS the coverage signature, given _refusal_detail ruled out a crash.
        assert detail["untraceable"] == 0, detail
        assert detail["forbidden"] == 0, detail
        assert detail["provenance"] == 0, detail
        assert detail["faithfulness"] == 0, detail
        assert _persisted(live_neo4j, trip_id) == before
    finally:
        _clear_dep(client, executor_target)

    # --- INVENTION: full validate_script, not structural traceability ---------
    caplog.clear()
    inventor = _InventingGlueExecutor()
    executor_target = _override_dep(client, "get_premium_compose_executor", inventor)
    try:
        with caplog.at_level(logging.ERROR, logger="ondoway.api"):
            resp = _compose(client, trip_id)
        detail = _refusal_detail(resp, caplog)
        assert inventor.stops_invented, (
            "no stop of this stitch carries a non-reflection glue sentence, so the "
            "invention clause never ran — re-pick the fixture tour"
        )
        assert detail["forbidden"] > 0, (
            "invented glue survived: the persisted path is still running "
            f"structural traceability instead of the full validate_script scan: {detail}"
        )
        assert detail["untraceable"] == 0, detail
        assert _persisted(live_neo4j, trip_id) == before
    finally:
        _clear_dep(client, executor_target)


@needs_neo4j
def test_a_faithful_tour_still_composes(client, live_neo4j, fresh_trip):
    """The gates are not a blanket refusal: the echo-the-stitch tour still passes.

    Without this, wiring the three gates to reject EVERYTHING would satisfy the test
    above. It also pins the parity claim from the other side — the stitch a persisted
    trip is built from clears the full scan, the coverage baseline and entailment.
    """
    trip_id = fresh_trip["trip_id"]

    class _EchoExecutor:
        cost_bearing = False
        provider_name = "offline"

        def execute(self, unit) -> PhysicalProviderResponse:
            return _offline_response(unit, _stitched(unit))

    target = _override_dep(client, "get_premium_compose_executor", _EchoExecutor())
    try:
        resp = _compose(client, trip_id)
    finally:
        _clear_dep(client, target)
    assert resp.status_code == 200, resp.text
    assert _persisted(live_neo4j, trip_id)["composed_route_id"] == f"{trip_id}-opt1"


def test_the_certification_replay_keeps_its_own_gate_defaults() -> None:
    """Parity is opt-IN: the certification replay's defaults are untouched (D3).

    The certification path judges prose by MEANING (its structural-only validator is
    deliberate, not an oversight), so the three gates arrive as parameters that default
    to today's behaviour. A change that flipped the defaults instead would silently
    re-gate every certification replay and every Premium build.
    """
    import inspect

    from src.tour.authoring import author_prebuilt_route, finalize_certification_composition

    finalize = inspect.signature(finalize_certification_composition).parameters
    for name in ("faithfulness_checker", "enforce_claim_coverage", "scan_glue_for_invention"):
        assert name in finalize, f"the per-stop finalizer has no injectable {name}"
    assert finalize["faithfulness_checker"].default is None
    assert finalize["enforce_claim_coverage"].default is False
    assert finalize["scan_glue_for_invention"].default is False

    seam = inspect.signature(author_prebuilt_route).parameters
    for name in ("faithfulness_checker", "enforce_claim_coverage", "scan_glue_for_invention"):
        assert name in seam, f"the prebuilt-route seam cannot pass {name} through"


# ---------------------------------------------------------------------------
# AC-6/AC-8 — the cross-stop echo dedup port
# ---------------------------------------------------------------------------

#: A fact voiced verbatim at stop 0, then echoed again at stop 1 — the
#: Île-de-la-Cité three-source-book case ``claim_dedup.suppress_repeated_claims``
#: exists for, just two stops apart instead of two beats at one stop.
_DUP_TEXT = "The span was finished in the winter of 1400."
#: Stop 1's OTHER sentence, carrying a claim nothing else voices — so beat
#: "b1a" is never the SOLE carrier of anything and the dedup pass's "never
#: empty a beat" restore cannot put the echo back.
_NOVEL_TEXT = "Its stone came from a quarry near Fontainebleau."


def _cross_stop_echo_fixture() -> tuple[Script, BeatSequence, Route]:
    """A persisted-trip-shaped (route, sequence, stitched script) pair, pure and
    provider-free, modeled on ``_prebuilt`` in
    ``tests/test_tour_authoring_from_route.py`` — but stop 1 seats ONE beat with
    TWO sentences: an echo of stop 0's fact plus a sentence carrying a claim
    nothing else voices. Both sentences must belong to the SAME beat — the dedup
    pass's "never empty a beat" restore fires per BEAT ID, so if the echo and the
    novel sentence were split across two different one-sentence beats, dropping
    the echo would empty ITS beat and the restore would put it right back.
    """
    pois = (
        POI(id="p0", name="Stop 0", tier=3, poi_role="anchor", lat=48.850, lng=2.350),
        POI(id="p1", name="Stop 1", tier=3, poi_role="anchor", lat=48.851, lng=2.351),
    )
    transits = (
        TransitSegment(
            from_poi_id=None,
            to_poi_id="p0",
            distance_m=100.0,
            walk_seconds=90,
            leg_seconds=100,
            leg_distance_m=110.0,
            source="valhalla",
        ),
        TransitSegment(
            from_poi_id="p0",
            to_poi_id="p1",
            distance_m=100.0,
            walk_seconds=90,
            leg_seconds=100,
            leg_distance_m=110.0,
            source="valhalla",
        ),
    )
    route = Route(
        pois=pois,
        transits=transits,
        total_walk_distance_m=200.0,
        total_walk_seconds=200,
    )
    beat0 = BeatRef(
        id="b0", poi_id="p0", script_body=_DUP_TEXT, key_claims=("the span finished in 1400",)
    )
    beat1 = BeatRef(
        id="b1",
        poi_id="p1",
        script_body=f"{_DUP_TEXT} {_NOVEL_TEXT}",
        key_claims=(
            "the span finished in 1400",
            "its stone came from a quarry near fontainebleau",
        ),
    )
    sequence = BeatSequence(
        poi_beats=(
            POIBeats(
                poi_id="p0",
                poi_name="Stop 0",
                ordering_strategy="narrative_function",
                beats=(beat0,),
            ),
            POIBeats(
                poi_id="p1",
                poi_name="Stop 1",
                ordering_strategy="narrative_function",
                beats=(beat1,),
            ),
        )
    )
    stitched = Script(
        city_slug="paris",
        generated_at="2026-07-30T00:00:00Z",
        inputs=TourInput(start=(48.850, 2.350), duration_min=30, city_slug="paris"),
        total_audio_seconds=24,
        total_walking_seconds=200,
        total_walk_distance_m=200,
        total_planned_seconds=1800,
        selected_pois=(
            ScriptPOI(id="p0", name="Stop 0", tier=3, lat=48.850, lng=2.350, beat_ids=("b0",)),
            ScriptPOI(
                id="p1",
                name="Stop 1",
                tier=3,
                lat=48.851,
                lng=2.351,
                beat_ids=("b1",),
            ),
        ),
        lens_coverage={},
        script=(
            Sentence(text=_DUP_TEXT, source_id="b0", source_type="beat", stop_idx=0),
            Sentence(text=_DUP_TEXT, source_id="b1", source_type="beat", stop_idx=1),
            Sentence(text=_NOVEL_TEXT, source_id="b1", source_type="beat", stop_idx=1),
        ),
        validation=ValidationReport(),
    )
    return stitched, sequence, route


class _EchoExecutor:
    """$0 offline executor that echoes each stop's stitched sentences back
    unchanged — so whatever cross-stop repeat the stitch carries survives
    into the assembled output UNLESS the finalizer itself suppresses it."""

    cost_bearing = False
    provider_name = "offline"

    def execute(self, unit) -> PhysicalProviderResponse:
        return _offline_response(unit, _stitched(unit))


def _preview_surface_plan(plan) -> PremiumTourPlan:
    """Re-seat a prebuilt-route authoring plan as the ``PremiumTourPlan`` that
    ``/trips/preview`` hands to ``finalize_premium_composition``.

    Every field that finalizer READS is carried across byte-for-byte:
    ``units`` (stop_index / authorized_request / authoring_request /
    request_sha256), ``authoring`` (the response-set admission bar), and the
    ``source``/``sequence``/``route`` triple it forwards to the shared finalizer.
    The planning-provenance fields it never touches — the corpus snapshot, the
    route record, the routing version — are placeholders, and are the ONLY
    things this construction fakes. Building the plan through
    ``plan_premium_tour`` instead would need a corpus snapshot, selection and a
    live routing client, none of which the claim under test involves.
    """
    return PremiumTourPlan(
        tour_input=plan.source.inputs,
        snapshot=None,
        snapshot_sha256="0" * 64,
        route=plan.route,
        route_record={},
        sequence=plan.sequence,
        source=plan.source,
        candidate=plan.candidate,
        authoring=plan.authoring,
        units=tuple(
            PremiumComposeUnit(
                stop_index=unit.stop_index,
                poi_name=unit.poi_name,
                authorized_request=unit.authorized_request,
                authoring_request=unit.authoring_request,
                request_sha256=unit.request_sha256,
                input_byte_count=unit.input_byte_count,
                output_token_ceiling=unit.output_token_ceiling,
                sdk_request=unit.sdk_request,
            )
            for unit in plan.units
        ),
        routing_version="offline-test",
        policy_version="offline-test",
        authorities=PREMIUM_AUTHORITIES,
    )


def test_a_sentence_outside_the_authored_stops_is_refused_not_shipped_unattested() -> None:
    """No sentence may ship in composed.script without a CompositionTrace covering it.

    The traces are built by grouping the assembled stream on ``stop_idx``. A sentence
    whose ``stop_idx`` falls OUTSIDE the authored stop set is therefore in no group at
    all: it lands in ``composed.script`` — persisted, voiced to a tourist — attested by
    nothing, with every per-stop trace still internally consistent.

    That is reachable, not theoretical. ``_sentences_from_json`` coerces a BEAT
    sentence's ``stop_idx`` back to the stitch's true stop, but a glue or reflection
    line keeps whatever index the provider echoed, so a mis-echoed one migrates. The
    judge consult on this step named it the single most likely failure.

    UNDO: delete the ``attested != set(range(...))`` check in ``finish`` and this goes
    GREEN — which is exactly what a mutation run proved before this test existed.
    """
    stitched, sequence, route = _cross_stop_echo_fixture()
    plan = plan_prebuilt_route_authoring(
        stitched,
        sequence,
        route,
        authoring_policy_sha256=premium_authoring_policy_sha256(),
    )

    class _StopMigratingExecutor:
        """Echoes the stitch, but re-stamps one GLUE line onto a stop nobody authored."""

        cost_bearing = False
        provider_name = "offline"

        def execute(self, unit) -> PhysicalProviderResponse:
            sentences = _stitched(unit)
            if unit.stop_index == 0:
                # A GLUE line, because `_sentences_from_json` coerces a BEAT
                # sentence's stop_idx back to the stitch's true stop — only a
                # non-beat line can carry a foreign index through parsing.
                sentences.append(
                    {
                        "text": "You are now somewhere this tour never goes.",
                        "source_id": GLUE_REFLECTION,
                        "source_type": "glue",
                        "stop_idx": 99,
                        "also_cites": [],
                    }
                )
            return _offline_response(unit, sentences)

    with pytest.raises(ValueError) as excinfo:
        author_prebuilt_route(plan, executor=_StopMigratingExecutor())

    message = str(excinfo.value)
    assert "attested by no composition trace" in message or "subsequence" in message, (
        "a sentence stamped onto an unauthored stop must be refused by name; the "
        f"finalizer raised something else instead: {message!r}"
    )


def test_cross_stop_echo_is_suppressed() -> None:
    """AC-6/AC-8 — the pinned gate for this step.

    ``compose.py``'s whole-tour composer ran ``_dedup_composed`` (claim-repeat +
    exact-repeat + same-beat near-dup suppression) over the ASSEMBLED sentence
    stream before verifying it, so a fact voiced at one stop and echoed again at
    a LATER stop never shipped twice. The per-stop seam's shared finalizer,
    ``finalize_certification_composition``, assembles per-stop provider output
    into that identical stream but never called the pass — so the same cross-stop
    echo would ship on every authoring surface that finalizer serves.

    AC-6 names BOTH surfaces, so both are DRIVEN here rather than argued from
    the fact that they share a callee:

    * the persisted ``POST /trips/{id}/compose`` engine — ``author_prebuilt_route``;
    * the ``/trips/preview`` engine — ``premium_tour.finalize_premium_composition``,
      the function ``preview_trip`` reaches through ``finalize_premium_tour``.

    Driving only the first would leave a port that moved the pass UP into
    ``author_prebuilt_route`` fully green while ``/trips/preview`` still shipped
    the echo — which is exactly the fix AC-6 forbids. The preview clause is what
    pins the pass to the SHARED finalizer.

    The last block pins the composition trace, because suppression and
    attestation pull against each other — and an earlier version of this test got
    that relationship BACKWARDS, which is what produced the defect a judge consult
    later caught. It asserted ``trace.source_sentences == shipped`` and justified it
    as "FinalTourBlueprint requires a trace's cited source sentences to equal the
    stop's FINAL sentences". That is not what the blueprint requires. Read
    ``artifact.py:763-769``: it indexes INTO ``source_sentences`` using
    ``source_sentence_indexes`` and compares THAT to the final stop text. The model
    is built for a SUBSEQUENCE — ``source_sentence_indexes`` is constrained
    monotonic, unique and in-range, one per final sentence.

    So the honest shape, which the finalizer now produces and this test now pins, is:
    ``source_sentences`` = the RAW provider payload, ``source_sentence_indexes`` =
    which of them survived de-dup. Re-grouping the bundle post-dedup instead made the
    finalizer's fail-closed provenance guard a tautology (comparing the deduped
    stream against itself) AND recorded text the provider never sent under
    ``derivation="provider_response"``, while ``response_sha256`` still named the
    untouched body.
    """
    stitched, sequence, route = _cross_stop_echo_fixture()
    plan = plan_prebuilt_route_authoring(
        stitched,
        sequence,
        route,
        authoring_policy_sha256=premium_authoring_policy_sha256(),
    )
    executor = _EchoExecutor()

    # --- surface 1: POST /trips/{id}/compose -------------------------------
    script = author_prebuilt_route(plan, executor=executor)

    all_texts = [s.text for s in script.script]
    assert all_texts.count(_DUP_TEXT) == 1, (
        f"the cross-stop echo was not suppressed: {_DUP_TEXT!r} appears "
        f"{all_texts.count(_DUP_TEXT)} times in {all_texts!r}"
    )
    assert _NOVEL_TEXT in all_texts, (
        "the dedup pass dropped stop 1's ONLY novel sentence, not just its echo "
        "of stop 0 — this would silently delete a fact, not suppress a repeat"
    )
    stop0_texts = [s.text for s in script.script if s.stop_idx == 0]
    assert stop0_texts == [_DUP_TEXT], "stop 0's own (first) telling must survive untouched"

    # --- surface 2: /trips/preview -----------------------------------------
    premium_plan = _preview_surface_plan(plan)
    responses = tuple(executor.execute(unit) for unit in premium_plan.units)
    composition = finalize_premium_composition(premium_plan, responses)

    preview_texts = [s.text for s in composition.script.script]
    assert preview_texts.count(_DUP_TEXT) == 1, (
        "the /trips/preview finalizer shipped the cross-stop echo: "
        f"{_DUP_TEXT!r} appears {preview_texts.count(_DUP_TEXT)} times in "
        f"{preview_texts!r} — the dedup pass is not on the SHARED choke point"
    )
    assert _NOVEL_TEXT in preview_texts, (
        "the preview surface dropped stop 1's only novel sentence — the dedup "
        "pass is deleting a fact on the surface the editor reviews"
    )
    assert preview_texts == all_texts, (
        "the two surfaces diverged on identical input; AC-6 requires the same "
        f"suppression on both ({preview_texts!r} vs {all_texts!r})"
    )

    # --- the trace still attests the provider response ----------------------
    traces = {trace.stop_index: trace for trace in composition.composition_trace}
    assert sorted(traces) == [0, 1], (
        "dedup emptied a stop out of the trace entirely; suppression must never "
        f"cost a stop its narration (traced stops: {sorted(traces)})"
    )
    raw_by_stop = {
        unit.stop_index: response
        for unit, response in zip(premium_plan.units, responses, strict=True)
    }
    for stop_index, trace in traces.items():
        assert trace.derivation == "provider_response"
        assert trace.response_sha256 == hashlib.sha256(raw_by_stop[stop_index].body).hexdigest(), (
            f"stop {stop_index}'s trace no longer hashes the raw provider body — "
            "the dedup rewrote the attestation of what the provider actually said"
        )
        shipped = tuple(s for s in composition.script.script if s.stop_idx == stop_index)
        # THE INVARIANT FinalTourBlueprint ACTUALLY ENFORCES (artifact.py:763-769):
        # it indexes INTO source_sentences with source_sentence_indexes and compares
        # THAT to the final stop text. So the trace must carry the RAW provider payload
        # plus the indexes of the sentences that survived de-dup — not the deduped text.
        #
        # An earlier version of this test asserted `source_sentences == shipped` and
        # justified it as "FinalTourBlueprint would reject this tour at build time".
        # That justification is false, and it forced the finalizer to rebind
        # composed_by_stop to the post-dedup grouping, which (a) made the fail-closed
        # provenance guard a tautology and (b) recorded text the provider never sent
        # under derivation="provider_response". A judge consult caught both.
        traced = tuple(trace.source_sentences[k] for k in trace.source_sentence_indexes)
        assert traced == shipped, (
            f"stop {stop_index}: indexing the trace's source by its surviving indexes "
            "must reproduce the shipped text exactly — this is the check "
            "FinalTourBlueprint runs at build time"
        )
        raw_texts = tuple(
            s["text"] for s in json.loads(raw_by_stop[stop_index].body)["sentences"]
        )
        assert tuple(s.text for s in trace.source_sentences) == raw_texts, (
            f"stop {stop_index}'s trace must attest the RAW provider payload, not the "
            "post-dedup text: source_payload_sha256 is read as 'what the provider "
            "returned', and response_sha256 already names that same untouched body"
        )
