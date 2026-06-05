"""Scope 1 — distance.py three-tier walking-distance abstraction.

Covers the production routing infrastructure: matrix → live OSRM →
haversine fallback resolution, OSRM-down degradation, missing-matrix
degradation, PII-safe fallback logging, the live-OSRM TTL cache, and a
matrix-lookup latency budget.

Tests mock the patchable seams (``_osrm_route``, the active matrix) so
unit tests never depend on the live OSRM container. The perf test (T5)
does load the real ``data/paris/distance_matrix.sqlite``.
"""

from __future__ import annotations

import logging
import timeit

import pytest

from src.tour import distance
from src.tour.contract import POI
from src.tour.routing import summarise_route


@pytest.fixture(autouse=True)
def _isolate_distance_state(monkeypatch):
    """Reset all process-wide distance state around every test.

    Counters, the active matrix, the TTL cache, and the mode env var are
    shared module globals; isolate them so tests don't bleed into each
    other regardless of pass/fail order.
    """
    monkeypatch.setenv("TOUR_DISTANCE_MODE", "auto")
    distance.reset_counters()
    distance.set_active_matrix(None)
    distance._route_cache.clear()
    yield
    distance.reset_counters()
    distance.set_active_matrix(None)
    distance._route_cache.clear()


def _matrix(
    pairs: dict[tuple[str, str], tuple[float, int]],
    coords: dict[str, tuple[float, float]] | None = None,
) -> distance.MatrixHandle:
    return distance.MatrixHandle(pairs, coords or {})


def _poi(pid: str, lat: float, lng: float) -> POI:
    return POI(id=pid, name=pid, tier=5, poi_role="stop", lat=lat, lng=lng)


# ---------------------------------------------------------------------------
# T1 — three-tier resolution
# ---------------------------------------------------------------------------


# Acceptance Criterion: AC-3 — walking_time resolves matrix → live OSRM →
# haversine, in that order, incrementing the matching per-tier counter.
def test_walking_time_three_tier_resolution(monkeypatch):
    # Tier 1: both POI ids present in the matrix → matrix path.
    handle = _matrix({("a", "b"): (1234.5, 999)})
    distance.set_active_matrix(handle)

    osrm_calls: list[tuple] = []

    def _fake_osrm(p, q):
        osrm_calls.append((p, q))
        return (500.0, 321, [(48.87, 2.32), (48.85, 2.34)])

    monkeypatch.setattr(distance, "_osrm_route", _fake_osrm)

    matrix_secs = distance.walking_time((48.87, 2.32, "a"), (48.85, 2.34, "b"))
    assert matrix_secs == 999
    assert distance.get_counters()["matrix_hit"] == 1
    assert osrm_calls == []  # matrix hit must not touch OSRM

    # Tier 2: POI ids NOT in the matrix → live OSRM path.
    live_secs = distance.walking_time((48.87, 2.32, "x"), (48.85, 2.34, "y"))
    assert live_secs == 321
    assert distance.get_counters()["live_osrm"] == 1
    assert len(osrm_calls) == 1

    # Tier 3: OSRM returns None → haversine fallback.
    distance._route_cache.clear()
    monkeypatch.setattr(distance, "_osrm_route", lambda p, q: None)
    fallback_secs = distance.walking_time((48.87, 2.32, "x"), (48.85, 2.34, "y"))
    assert fallback_secs > 0
    assert distance.get_counters()["fallback"] == 1


# ---------------------------------------------------------------------------
# T2 — OSRM down → haversine fallback, with WARNING
# ---------------------------------------------------------------------------


# Acceptance Criterion: AC-3a — in auto mode with no matrix and OSRM down,
# walking_time returns a positive haversine value and logs a WARNING.
def test_osrm_down_falls_back_to_haversine(monkeypatch, caplog):
    distance.set_active_matrix(None)
    monkeypatch.setattr(distance, "_osrm_route", lambda a, b: None)

    with caplog.at_level(logging.WARNING, logger="src.tour.distance"):
        secs = distance.walking_time((48.87, 2.32, "a"), (48.85, 2.34, "b"))

    assert secs > 0
    assert distance.get_counters()["fallback"] == 1
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("haversine" in r.getMessage().lower() for r in warnings)


# ---------------------------------------------------------------------------
# T3 — matrix missing → live OSRM
# ---------------------------------------------------------------------------


# Acceptance Criterion: AC-3b — with no active matrix, two POI-id points
# resolve via live OSRM (not the matrix tier).
def test_matrix_missing_falls_back_to_osrm(monkeypatch):
    distance.set_active_matrix(None)
    sentinel = (777.0, 4242, [(48.87, 2.32), (48.85, 2.34)])
    monkeypatch.setattr(distance, "_osrm_route", lambda a, b: sentinel)

    secs = distance.walking_time((48.87, 2.32, "a"), (48.85, 2.34, "b"))

    assert secs == 4242
    counters = distance.get_counters()
    assert counters["live_osrm"] == 1
    assert counters["matrix_hit"] == 0


# ---------------------------------------------------------------------------
# T4 — everything down → haversine, route still builds
# ---------------------------------------------------------------------------


# Acceptance Criterion: AC-3c — matrix None + OSRM None → haversine value,
# WARNING logged, and summarise_route still yields a usable Route.
def test_all_down_haversine(monkeypatch, caplog):
    distance.set_active_matrix(None)
    monkeypatch.setattr(distance, "_osrm_route", lambda a, b: None)

    with caplog.at_level(logging.WARNING, logger="src.tour.distance"):
        secs = distance.walking_time((48.87, 2.32, "a"), (48.85, 2.34, "b"))

    assert secs > 0
    assert any(
        r.levelno == logging.WARNING and "haversine" in r.getMessage().lower()
        for r in caplog.records
    )

    route = summarise_route(
        [_poi("a", 48.86, 2.35), _poi("b", 48.87, 2.36)],
        start_lat=48.85,
        start_lng=2.35,
        round_trip=False,
        duration_min=60,
        spine_area=None,
    )
    assert route.total_walk_seconds >= 0
    assert len(route.transits) == 2


# ---------------------------------------------------------------------------
# T5 — matrix lookup latency (perf)
# ---------------------------------------------------------------------------


# Acceptance Criterion: AC-6 — a matrix get() p99 latency stays under 1ms,
# proving tier-1 lookups are O(1)-fast on the real Paris matrix.
def test_matrix_lookup_p99_under_1ms():
    handle = distance.load_matrix("paris")
    if handle is None:
        pytest.fail(
            "data/paris/distance_matrix.sqlite is missing — cannot run the "
            "matrix-lookup perf test. Build it with "
            "scripts/build_distance_matrix.py before running the suite."
        )
    assert len(handle) > 0

    # Pick a real valid (non-sentinel) pair from the loaded matrix.
    pair: tuple[str, str] | None = None
    for from_id, to_id in handle._pairs:
        if handle.get(from_id, to_id) is not None:
            pair = (from_id, to_id)
            break
    assert pair is not None, "no valid (non-sentinel) pair found in matrix"
    from_id, to_id = pair

    samples = timeit.repeat(
        lambda: handle.get(from_id, to_id),
        number=1,
        repeat=10_000,
    )
    samples.sort()
    p99 = samples[int(len(samples) * 0.99)]
    assert p99 < 1e-3, f"matrix get() p99={p99 * 1e3:.4f}ms exceeds 1ms budget"


# ---------------------------------------------------------------------------
# T6 — PII-safe fallback logging
# ---------------------------------------------------------------------------


# Acceptance Criterion: SECURITY §7 — fallback WARNINGs for id-less points
# never leak raw precise coordinates into the log stream.
def test_pii_safe_logging(monkeypatch, caplog):
    distance.set_active_matrix(None)
    monkeypatch.setattr(distance, "_osrm_route", lambda a, b: None)

    with caplog.at_level(logging.WARNING, logger="src.tour.distance"):
        # No POI ids carried — the label must NOT echo the raw coords.
        distance.walking_time((48.87, 2.32), (48.85, 2.34))

    assert distance.get_counters()["fallback"] == 1
    leaked = ["48.87", "2.32", "48.85", "2.34"]
    for record in caplog.records:
        message = record.getMessage()
        for raw in leaked:
            assert raw not in message, f"raw coordinate {raw!r} leaked into log: {message!r}"


# ---------------------------------------------------------------------------
# T7 — live-OSRM TTL cache
# ---------------------------------------------------------------------------


# Acceptance Criterion: perf-best-practice — identical live lookups hit the
# TTL cache; the underlying _osrm_route is called only once.
def test_lru_cache_polyline(monkeypatch):
    distance.set_active_matrix(None)
    distance._route_cache.clear()

    call_count = 0

    def _counting_osrm(a, b):
        nonlocal call_count
        call_count += 1
        return (640.0, 512, [(48.87, 2.32), (48.85, 2.34)])

    monkeypatch.setattr(distance, "_osrm_route", _counting_osrm)

    first = distance.walking_polyline((48.87, 2.32), (48.85, 2.34))
    second = distance.walking_polyline((48.87, 2.32), (48.85, 2.34))

    assert call_count == 1, "second identical lookup should be served from cache"
    assert first == second
