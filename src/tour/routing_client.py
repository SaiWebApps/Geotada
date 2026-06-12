"""Valhalla pedestrian routing client with haversine fallback (M1).

Primary engine: a local Valhalla service (Docker, ``make valhalla-up``,
port 8002) speaking the documented JSON API:

- POST /route      {locations: [{lat, lon}, ...], costing: "pedestrian",
                    units: "kilometers"} ->
                    trip.legs[0].summary.time (seconds),
                    trip.legs[0].summary.length (KILOMETERS),
                    trip.legs[0].shape (encoded polyline, 6-digit precision)
- POST /isochrone  {locations: [{lat, lon}], costing: "pedestrian",
                    contours: [{time: minutes}], polygons: true} ->
                    GeoJSON FeatureCollection

Every public method degrades to the pure-math fallback —
``pace_corrected_walk_seconds`` over ``haversine_m`` (src/tour/routing.py) —
when Valhalla is unreachable or answers garbage, so the engine and the test
suite work with no container running. A ``None`` polyline (route) or ``None``
result (isochrone) is the caller's signal that the fallback produced the
numbers; M2 surfaces that as ``TransitSegment.source``.

Nothing consumes this module yet — M2 wires it into ``summarise_route`` and
the contract. See specs/2026-06-12-tour-algorithm-decision/IMPLEMENTATION-PLAN.md M1/M2.
"""

from __future__ import annotations

import httpx

from .routing import haversine_m, pace_corrected_walk_seconds

DEFAULT_BASE_URL = "http://localhost:8002"
DEFAULT_TIMEOUT_S = 2.0
_KM_TO_M = 1000.0

# Any transport problem, bad HTTP status, or unparseable/missing field falls
# back — the fallback must be total or selection dies when the container is
# down. json.JSONDecodeError subclasses ValueError.
_FALLBACK_ERRORS = (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError)


class RoutingClient:
    """Pedestrian leg times/shapes from Valhalla, haversine when it's away."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
    ):
        # An injected client (tests use httpx.MockTransport) carries its own
        # base_url/timeout; base_url/timeout_s apply only to the owned one.
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout_s)
        # M3: sticky degradation. The greedy makes hundreds-to-thousands of
        # leg calls per request; once a TRANSPORT failure proves Valhalla is
        # away, stop attempting HTTP for this instance's lifetime. Bad
        # responses (4xx/5xx/garbage) do NOT degrade — those are per-request.
        self._degraded = False

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RoutingClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def leg_seconds(self, from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> int:
        """Walking seconds for one leg (routed, else pace-corrected haversine)."""
        seconds, _meters, _shape = self.route(from_lat, from_lng, to_lat, to_lng)
        return seconds

    def route(
        self, from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> tuple[int, float, str | None]:
        """(walk_seconds, distance_m, encoded_polyline6 | None) for one leg.

        ``None`` polyline means the haversine fallback produced the numbers
        (distance_m is then the straight-line metres, matching what
        summarise_route records today).
        """
        if self._degraded:
            return self._route_fallback(from_lat, from_lng, to_lat, to_lng)
        try:
            resp = self._client.post(
                "/route",
                json={
                    "locations": [
                        {"lat": from_lat, "lon": from_lng},
                        {"lat": to_lat, "lon": to_lng},
                    ],
                    "costing": "pedestrian",
                    "units": "kilometers",
                },
            )
            resp.raise_for_status()
            leg = resp.json()["trip"]["legs"][0]
            return (
                round(leg["summary"]["time"]),
                float(leg["summary"]["length"]) * _KM_TO_M,
                leg["shape"],
            )
        except httpx.TransportError:
            self._degraded = True
            return self._route_fallback(from_lat, from_lng, to_lat, to_lng)
        except _FALLBACK_ERRORS:
            return self._route_fallback(from_lat, from_lng, to_lat, to_lng)

    @staticmethod
    def _route_fallback(
        from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> tuple[int, float, None]:
        d = haversine_m(from_lat, from_lng, to_lat, to_lng)
        return (pace_corrected_walk_seconds(d), d, None)

    def isochrone(self, lat: float, lng: float, minutes: int) -> dict | None:
        """GeoJSON FeatureCollection of the walking isochrone, or ``None``.

        ``None`` tells the caller to keep using the analytic envelope radius
        (``envelope_radius_m``) — the pre-M1 behavior.
        """
        if self._degraded:
            return None
        try:
            resp = self._client.post(
                "/isochrone",
                json={
                    "locations": [{"lat": lat, "lon": lng}],
                    "costing": "pedestrian",
                    "contours": [{"time": float(minutes)}],
                    "polygons": True,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("type") != "FeatureCollection" or not data.get("features"):
                return None
            return data
        except httpx.TransportError:
            self._degraded = True
            return None
        except _FALLBACK_ERRORS:
            return None
