"""Valhalla pedestrian routing client with haversine fallback (M1).

Primary engine: Valhalla at ``VALHALLA_URL`` (the Render private service in
production; Docker via ``make valhalla-up`` locally, port 8002) speaking the
documented JSON API:

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

import hashlib
import json
import os

import httpx

from .contract import ValhallaLegReceipt
from .routing import PACE_KMH, haversine_m, pace_corrected_walk_seconds

# Pace pin (2026-07-02, hostile-panel finding): Valhalla defaults pedestrians
# to ~5.1 km/h; the engine's whole budget model (envelopes, walk budgets, the
# haversine fallback) is spec'd at PACE_KMH = 3.0 (§3.2 rule ledger 20-25).
# Without this, routed leg times assume a walker ~70% faster than the product
# designs for, and the isochrone reach (~1.7km at 20min) diverges ~2.2x from
# the analytic envelope (738m) — the root of the density-gate/REACH mismatch.
_PEDESTRIAN_COSTING_OPTIONS = {"pedestrian": {"walking_speed": PACE_KMH}}
_ROUTING_CONFIG = {
    "costing": "pedestrian",
    "costing_options": _PEDESTRIAN_COSTING_OPTIONS,
    "units": "kilometers",
}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


VALHALLA_ROUTING_CONFIG_JSON = _canonical_json(_ROUTING_CONFIG)
VALHALLA_ROUTING_CONFIG_SHA256 = hashlib.sha256(
    VALHALLA_ROUTING_CONFIG_JSON.encode("utf-8")
).hexdigest()

DEFAULT_BASE_URL = "http://localhost:8002"
BASE_URL_ENV = "VALHALLA_URL"
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
        base_url: str | None = None,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        client: httpx.Client | None = None,
    ):
        # An injected client (tests use httpx.MockTransport) carries its own
        # base_url/timeout; base_url/timeout_s apply only to the owned one.
        resolved_base_url = base_url or os.getenv(BASE_URL_ENV, DEFAULT_BASE_URL)
        if "://" not in resolved_base_url:
            resolved_base_url = f"http://{resolved_base_url}"
        self._client = client or httpx.Client(base_url=resolved_base_url, timeout=timeout_s)
        # M3: sticky degradation. The greedy makes hundreds-to-thousands of
        # leg calls per request; once a TRANSPORT failure proves Valhalla is
        # away, stop attempting HTTP for this instance's lifetime. Bad
        # responses (4xx/5xx/garbage) do NOT degrade — those are per-request.
        self._degraded = False
        self._routing_version: str | None = None

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
        seconds, distance_m, shape, _receipt = self.route_with_receipt(
            from_lat, from_lng, to_lat, to_lng
        )
        return seconds, distance_m, shape

    def route_with_receipt(
        self, from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> tuple[int, float, str | None, ValhallaLegReceipt | None]:
        """Route one leg and retain replayable evidence when Valhalla succeeds.

        Fallback behavior remains byte-for-byte compatible with :meth:`route`;
        a ``None`` receipt is the explicit signal that no Valhalla result exists.
        """
        if self._degraded:
            seconds, distance_m, shape = self._route_fallback(from_lat, from_lng, to_lat, to_lng)
            return seconds, distance_m, shape, None

        request_payload = {
            "locations": [
                {"lat": from_lat, "lon": from_lng},
                {"lat": to_lat, "lon": to_lng},
            ],
            **_ROUTING_CONFIG,
        }
        try:
            resp = self._client.post(
                "/route",
                json=request_payload,
            )
            resp.raise_for_status()
            response_payload = resp.json()
            leg = response_payload["trip"]["legs"][0]
            seconds = round(leg["summary"]["time"])
            distance_m = float(leg["summary"]["length"]) * _KM_TO_M
            shape = leg["shape"]
            request_json = _canonical_json(request_payload)
            response_json = _canonical_json(response_payload)
            receipt = ValhallaLegReceipt(
                requested_from=(from_lat, from_lng),
                requested_to=(to_lat, to_lng),
                request_json=request_json,
                request_sha256=hashlib.sha256(request_json.encode("utf-8")).hexdigest(),
                routing_config_json=VALHALLA_ROUTING_CONFIG_JSON,
                routing_config_sha256=VALHALLA_ROUTING_CONFIG_SHA256,
                response_json=response_json,
                response_sha256=hashlib.sha256(response_json.encode("utf-8")).hexdigest(),
                seconds=seconds,
                distance_m=distance_m,
                polyline=shape,
            )
            return seconds, distance_m, shape, receipt
        except httpx.TransportError:
            self._degraded = True
            seconds, distance_m, shape = self._route_fallback(from_lat, from_lng, to_lat, to_lng)
            return seconds, distance_m, shape, None
        except _FALLBACK_ERRORS:
            seconds, distance_m, shape = self._route_fallback(from_lat, from_lng, to_lat, to_lng)
            return seconds, distance_m, shape, None

    def routing_version(self) -> str:
        """Return the Valhalla version from this exact client instance.

        Premium provenance must bind route receipts to the engine that produced
        them. Missing or malformed status is therefore an error at the Premium
        boundary; ordinary Basic routing remains independently fallback-safe.
        """

        if self._routing_version is not None:
            return self._routing_version
        response = self._client.get("/status")
        response.raise_for_status()
        payload = response.json()
        version = payload.get("version")
        if not isinstance(version, str) or not version.strip():
            raise ValueError("Valhalla status omitted a routing version")
        self._routing_version = version.strip()
        return self._routing_version

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
                    "costing_options": _PEDESTRIAN_COSTING_OPTIONS,
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
