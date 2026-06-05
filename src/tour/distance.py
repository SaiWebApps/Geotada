"""Runtime walking-distance abstraction — three-tier resolution.

Every call to :func:`walking_time` / :func:`walking_distance_m` /
:func:`walking_polyline` resolves through three tiers, gated by the
``TOUR_DISTANCE_MODE`` environment variable:

- ``auto`` (default): matrix → live OSRM → haversine fallback.
- ``live``: live OSRM → haversine fallback (skips the matrix).
- ``haversine``: haversine only (skips matrix and live OSRM).

Tier 1 — **matrix.** If both endpoints carry a POI id and both ids are
present (with non-sentinel values) in the loaded distance matrix, the
pre-computed metres/seconds are returned. O(1) dict lookup.

Tier 2 — **live OSRM.** Calls the foot-profile ``/route`` service on the
configured OSRM server (default ``http://127.0.0.1:5000``; the corporate
proxy 403s ``localhost`` but not ``127.0.0.1``, and the httpx client is
built with ``trust_env=False`` so it never consults a system proxy).
Retries once on failure. Results are wrapped in a 1-hour TTL cache keyed
by coarsely-rounded coordinates.

Tier 3 — **haversine fallback.** Used on OSRM failure (both attempts) or
when mode is ``haversine``. Time comes from
:func:`routing.pace_corrected_walk_seconds`; distance is
``haversine_m * HAVERSINE_CORRECTION``. Every fallback emits a WARNING.

Fallback logs are PII-safe: raw lat/lng for arbitrary points are never
written. Points with a POI id log that id; otherwise the nearest matrix
POI id plus a coarse (~100m) bucketed coordinate hash is logged.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from pathlib import Path

import httpx
from cachetools import TTLCache

from .routing import (
    HAVERSINE_CORRECTION,
    haversine_m,
    pace_corrected_walk_seconds,
)

logger = logging.getLogger(__name__)

# A point is (lat, lng) or (lat, lng, poi_id). Latitude first.
Point = tuple[float, float] | tuple[float, float, "str | None"]

_DEFAULT_OSRM_BASE_URL = "http://127.0.0.1:5000"

# Monotonic per-tier counters.
_counters: dict[str, int] = {"matrix_hit": 0, "live_osrm": 0, "fallback": 0}

# Live-OSRM TTL cache, keyed by rounded coords. Guarded by a lock.
_route_cache: TTLCache = TTLCache(maxsize=1024, ttl=3600)
_cache_lock = threading.Lock()

# Lazily-created shared httpx client (trust_env=False — never use a proxy).
_http_client: httpx.Client | None = None
_client_lock = threading.Lock()


def _base_url() -> str:
    return os.getenv("OSRM_BASE_URL", _DEFAULT_OSRM_BASE_URL)


def _get_client() -> httpx.Client:
    global _http_client
    if _http_client is None:
        with _client_lock:
            if _http_client is None:
                _http_client = httpx.Client(trust_env=False, timeout=10.0)
    return _http_client


def get_counters() -> dict:
    """Return a snapshot of the monotonic per-tier counters."""
    return dict(_counters)


def reset_counters() -> None:
    """Zero all per-tier counters (test isolation)."""
    for key in _counters:
        _counters[key] = 0


def _mode() -> str:
    return os.getenv("TOUR_DISTANCE_MODE", "auto").strip().lower() or "auto"


# ---------------------------------------------------------------------------
# Matrix handle
# ---------------------------------------------------------------------------


class MatrixHandle:
    """In-memory view of a city's pre-computed distance matrix.

    ``pairs`` maps ``(from_id, to_id) -> (distance_m, duration_sec)``.
    ``coords`` maps ``poi_id -> (lat, lng)`` for nearest-POI labelling.
    """

    def __init__(
        self,
        pairs: dict[tuple[str, str], tuple[float, int]],
        coords: dict[str, tuple[float, float]],
    ) -> None:
        self._pairs = pairs
        self._coords = coords

    def __len__(self) -> int:
        return len(self._pairs)

    def get(self, from_id: str, to_id: str) -> tuple[float, int] | None:
        """Return (distance_m, duration_sec) or None for miss/sentinel."""
        value = self._pairs.get((from_id, to_id))
        if value is None:
            return None
        distance_m, duration_sec = value
        if distance_m < 0 or duration_sec < 0:
            return None
        return value

    def memory_mb(self) -> float:
        """Rough in-memory footprint of the matrix in megabytes."""
        import sys

        total = sys.getsizeof(self._pairs) + sys.getsizeof(self._coords)
        for key, value in self._pairs.items():
            total += sys.getsizeof(key) + sys.getsizeof(value)
        for key, value in self._coords.items():
            total += sys.getsizeof(key) + sys.getsizeof(value)
        return total / (1024.0 * 1024.0)

    def nearest_poi_id(self, lat: float, lng: float) -> str | None:
        """Return the closest POI id to (lat, lng), or None if empty."""
        best_id: str | None = None
        best_d = float("inf")
        for poi_id, (plat, plng) in self._coords.items():
            d = haversine_m(lat, lng, plat, plng)
            if d < best_d:
                best_d = d
                best_id = poi_id
        return best_id


def load_matrix(city: str) -> MatrixHandle | None:
    """Load ``data/{city}/distance_matrix.sqlite`` into memory.

    Returns None (and logs a WARNING) if the file is missing — callers
    run in degraded routing mode. Never raises on a missing file.
    """
    path = Path("data") / city / "distance_matrix.sqlite"
    if not path.is_file():
        logger.warning("Distance matrix missing for city=%s (%s)", city, path)
        return None

    pairs: dict[tuple[str, str], tuple[float, int]] = {}
    coords: dict[str, tuple[float, float]] = {}
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute("SELECT from_poi_id, to_poi_id, distance_m, duration_sec FROM pairs")
        for from_id, to_id, distance_m, duration_sec in cur:
            pairs[(from_id, to_id)] = (float(distance_m), int(duration_sec))
        # Optional coords table for PII-safe nearest-POI labelling.
        has_coords = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='poi_coords'"
        ).fetchone()
        if has_coords:
            for poi_id, lat, lng in conn.execute("SELECT poi_id, lat, lng FROM poi_coords"):
                coords[poi_id] = (float(lat), float(lng))
    finally:
        conn.close()

    return MatrixHandle(pairs, coords)


# The process-wide matrix used by the runtime distance functions. The API
# lifespan loads it once; tests may set it directly.
_active_matrix: MatrixHandle | None = None


def set_active_matrix(handle: MatrixHandle | None) -> None:
    """Install the matrix used by the runtime distance functions."""
    global _active_matrix
    _active_matrix = handle


def get_active_matrix() -> MatrixHandle | None:
    return _active_matrix


# ---------------------------------------------------------------------------
# Point helpers
# ---------------------------------------------------------------------------


def _latlng(point: Point) -> tuple[float, float]:
    return (point[0], point[1])


def _poi_id(point: Point) -> str | None:
    if len(point) >= 3:
        return point[2]  # type: ignore[misc]
    return None


def _pii_safe_point_label(point: Point) -> str:
    """A log-safe label for a point — never the raw precise coordinates.

    Prefers the carried POI id; else the nearest matrix POI id plus a
    coarse (~100m, 3-decimal) bucketed-coordinate hash; else "unknown".
    """
    poi_id = _poi_id(point)
    if poi_id:
        return f"poi:{poi_id}"

    lat, lng = _latlng(point)
    bucket = (round(lat, 3), round(lng, 3))
    bucket_hash = hash(bucket) & 0xFFFFFF
    nearest = "unknown"
    if _active_matrix is not None:
        near_id = _active_matrix.nearest_poi_id(lat, lng)
        if near_id:
            nearest = near_id
    return f"nearest:{nearest} bucket:{bucket_hash:06x}"


# ---------------------------------------------------------------------------
# Live OSRM (patchable at module scope for tests)
# ---------------------------------------------------------------------------


def _cache_key(a: Point, b: Point) -> tuple[float, float, float, float]:
    a_lat, a_lng = _latlng(a)
    b_lat, b_lng = _latlng(b)
    return (round(a_lat, 5), round(a_lng, 5), round(b_lat, 5), round(b_lng, 5))


def _osrm_route(a: Point, b: Point) -> tuple[float, int, list[tuple[float, float]]] | None:
    """Call the OSRM ``/route`` foot service. Retries once on failure.

    Returns (distance_m, duration_sec, polyline_latlng) or None if both
    attempts fail. ``polyline_latlng`` is a list of (lat, lng) points.
    """
    a_lat, a_lng = _latlng(a)
    b_lat, b_lng = _latlng(b)
    url = (
        f"{_base_url()}/route/v1/foot/"
        f"{a_lng},{a_lat};{b_lng},{b_lat}"
        "?overview=full&geometries=geojson"
    )
    client = _get_client()
    last_exc: Exception | None = None
    for _attempt in range(2):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                last_exc = RuntimeError(f"OSRM code={data.get('code')!r}")
                continue
            route = data["routes"][0]
            distance_m = float(route["distance"])
            duration_sec = round(float(route["duration"]))
            geometry = route.get("geometry", {})
            coords = geometry.get("coordinates", []) if isinstance(geometry, dict) else []
            polyline = [(float(lat), float(lng)) for lng, lat in coords]
            return (distance_m, duration_sec, polyline)
        except Exception as exc:
            last_exc = exc
    logger.debug("OSRM route failed after retry: %s", last_exc)
    return None


def _live_lookup(a: Point, b: Point) -> tuple[float, int, list[tuple[float, float]]] | None:
    """Cached live-OSRM lookup. Returns the same shape as ``_osrm_route``."""
    key = _cache_key(a, b)
    with _cache_lock:
        cached = _route_cache.get(key)
    if cached is not None:
        return cached
    result = _osrm_route(a, b)
    if result is not None:
        with _cache_lock:
            _route_cache[key] = result
    return result


# ---------------------------------------------------------------------------
# Three-tier resolution
# ---------------------------------------------------------------------------


def _resolve(a: Point, b: Point) -> tuple[float, int, list[tuple[float, float]]]:
    """Resolve (distance_m, duration_sec, polyline) for a→b across tiers.

    The returned distance is always >= 0 (never the -1 sentinel).
    """
    mode = _mode()
    a_latlng = _latlng(a)
    b_latlng = _latlng(b)

    # Tier 1 — matrix (auto only, both endpoints must carry POI ids).
    if mode == "auto" and _active_matrix is not None:
        a_id = _poi_id(a)
        b_id = _poi_id(b)
        if a_id and b_id:
            hit = _active_matrix.get(a_id, b_id)
            if hit is not None:
                distance_m, duration_sec = hit
                _counters["matrix_hit"] += 1
                return (distance_m, duration_sec, [a_latlng, b_latlng])

    # Tier 2 — live OSRM (auto or live).
    if mode in ("auto", "live"):
        live = _live_lookup(a, b)
        if live is not None:
            distance_m, duration_sec, polyline = live
            _counters["live_osrm"] += 1
            geometry = polyline if polyline else [a_latlng, b_latlng]
            return (distance_m, duration_sec, geometry)

    # Tier 3 — haversine fallback (mode == haversine, or OSRM failed).
    hav = haversine_m(a_latlng[0], a_latlng[1], b_latlng[0], b_latlng[1])
    duration_sec = pace_corrected_walk_seconds(hav)
    distance_m = hav * HAVERSINE_CORRECTION
    _counters["fallback"] += 1
    if mode != "haversine":
        logger.warning(
            "Distance fallback to haversine: from=%s to=%s",
            _pii_safe_point_label(a),
            _pii_safe_point_label(b),
        )
    return (distance_m, duration_sec, [a_latlng, b_latlng])


def walking_time(a: Point, b: Point) -> int:
    """Walking duration from a to b, in seconds (always >= 0)."""
    _distance_m, duration_sec, _polyline = _resolve(a, b)
    return duration_sec


def walking_distance_m(a: Point, b: Point) -> float:
    """Walking distance from a to b, in metres (always >= 0)."""
    distance_m, _duration_sec, _polyline = _resolve(a, b)
    return distance_m


def walking_polyline(a: Point, b: Point) -> list[tuple[float, float]]:
    """Route geometry from a to b as (lat, lng) points.

    Live OSRM returns the full geometry; fallback/matrix tiers return the
    straight segment ``[a_latlng, b_latlng]``.
    """
    _distance_m, _duration_sec, polyline = _resolve(a, b)
    return polyline
