"""The forecast is fetched, never asked (design §2.5, data row 6.8, demo D3).

``fetch_rain_likelihood`` asks open-meteo — keyless, no account — for one day's
maximum precipitation probability and folds it to ``"rain"`` / ``"dry"`` /
``None``. ``None`` means "no signal": the caller plans exactly as it would
today (design §2.5 "Weather (fetched)" — never asked of the user, never
blocking), so every failure here fails OPEN — two attempts, then ``None``,
never an exception to the caller.

Extends (plan S3.9, per design §10.8.1): considered ``routing_client.py``, the
module that owns this package's HTTP — rejected, because that client speaks to
OUR Valhalla with per-leg receipts and sticky degradation, and a public
one-shot forecast fetch shares none of that contract. The descriptive
User-Agent is imported from the established ingest door rather than restated
(the W1.8 Overpass-406 lesson: anonymous clients get refused).
"""

from __future__ import annotations

from typing import Literal

import httpx

from src.onboard.fetch import ONBOARD_USER_AGENT

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# A day whose maximum precipitation probability reaches this percent plans as a
# rain day (D3 "the rainy day": covered legs, covered anchors); below it, dry.
RAIN_PROBABILITY_THRESHOLD = 50

_ATTEMPTS = 2  # two tries, then None — a forecast is never worth blocking on
_TIMEOUT_S = 5.0

# Same total-fallback tuple as routing_client's _FALLBACK_ERRORS, same reason:
# transport trouble, a bad HTTP status, or an unparseable/missing field must
# all fail open (json.JSONDecodeError subclasses ValueError).
_FAIL_OPEN_ERRORS = (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError)


def fetch_rain_likelihood(
    date_iso: str,
    lat: float,
    lng: float,
    *,
    client: httpx.Client | None = None,
) -> Literal["dry", "rain"] | None:
    """Rain likelihood for ``date_iso`` (YYYY-MM-DD) at (lat, lng), or ``None``.

    ``None`` on ANY failure — network, non-2xx, malformed payload, or a date
    the forecast horizon cannot answer (open-meteo reports those as a null
    probability). An injected ``client`` (tests use ``httpx.MockTransport``)
    carries its own transport and timeout, the routing_client pattern.
    """
    owned = client is None
    http = client or httpx.Client(timeout=_TIMEOUT_S)
    try:
        for _ in range(_ATTEMPTS):
            try:
                response = http.get(
                    FORECAST_URL,
                    params={
                        "latitude": lat,
                        "longitude": lng,
                        "daily": "precipitation_probability_max",
                        "timezone": "auto",
                        "start_date": date_iso,
                        "end_date": date_iso,
                    },
                    headers={"User-Agent": ONBOARD_USER_AGENT},
                )
                response.raise_for_status()
                value = response.json()["daily"]["precipitation_probability_max"][0]
                if value is None:  # answered, but the date is outside the horizon
                    return None
                probability = float(value)
            except _FAIL_OPEN_ERRORS:
                continue
            return "rain" if probability >= RAIN_PROBABILITY_THRESHOLD else "dry"
        return None
    finally:
        if owned:
            http.close()
