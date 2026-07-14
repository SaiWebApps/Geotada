"""The Step-3 WIKIDATA source connector.

PURE, like every Step-3 connector: ``consult_url`` names the WDQS SPARQL
endpoint + a bounding-box query for the city, and ``parse`` maps the returned
SPARQL-JSON to typed ``PoiCandidate`` hits. Neither touches the network or the
filesystem — the actual GET goes through ``base.run_connector`` ->
``fetch.http_get_json`` (the allowlist door). Do NOT import ``src.onboard.fetch``
here.

COORDINATE ORDER is the load-bearing detail. A Wikidata ``P625`` coordinate
arrives as a WKT string ``"Point(LON LAT)"`` — LONGITUDE FIRST, then latitude.
``_parse_point`` splits it accordingly, so ``longitude`` gets the first token and
``latitude`` the second. Swapping them would place every POI ~90° off (London at
latitude -0.13 instead of 51.5).
"""

from __future__ import annotations

from src.onboard.models import CityContext, ConnectorResult, PoiCandidate

# WDQS SPARQL endpoint. The provider host must be on the ingest allowlist for the
# real fetch (enforced by fetch.http_get_json, not here).
SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"


def _box_query(ctx: CityContext) -> str:
    """A valid WDQS ``wikibase:box`` query selecting every item with a P625
    coordinate inside ``ctx.bbox``.

    Corners are WKT ``Point(LON LAT)``: SW = (min_lon, min_lat), NE = (max_lon,
    max_lat). WDQS ships the wdt/bd/wikibase/geo/rdfs prefixes by default, so no
    PREFIX header is needed.
    """
    min_lat, max_lat, min_lon, max_lon = ctx.bbox
    sw = f"Point({min_lon} {min_lat})"  # WKT lon-first: south-west corner
    ne = f"Point({max_lon} {max_lat})"  # WKT lon-first: north-east corner
    return (
        "SELECT ?place ?placeLabel ?coord WHERE {\n"
        "  SERVICE wikibase:box {\n"
        "    ?place wdt:P625 ?coord .\n"
        f'    bd:serviceParam wikibase:cornerSouthWest "{sw}"^^geo:wktLiteral .\n'
        f'    bd:serviceParam wikibase:cornerNorthEast "{ne}"^^geo:wktLiteral .\n'
        "  }\n"
        '  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" . }\n'
        "}"
    )


def _parse_point(wkt: str) -> tuple[float, float]:
    """Parse a WKT ``"Point(LON LAT)"`` into ``(longitude, latitude)`` floats.

    LON IS FIRST: strip the ``Point(`` prefix and trailing ``)``, split on
    whitespace to ``[lon_str, lat_str]``.
    """
    inner = wkt.strip().removeprefix("Point(").removesuffix(")")
    lon_str, lat_str = inner.split()
    return float(lon_str), float(lat_str)


class WikidataConnector:
    """Consults the WDQS bounding-box SPARQL query for a city and yields one
    ``PoiCandidate`` per Wikidata item found inside the bbox."""

    slug = "wikidata"

    def consult_url(self, ctx: CityContext) -> tuple[str, dict | None]:
        """The WDQS endpoint + JSON-format box query for ``ctx``. PURE."""
        return (SPARQL_ENDPOINT, {"format": "json", "query": _box_query(ctx)})

    def parse(self, payload: dict, ctx: CityContext) -> ConnectorResult:
        """Map a WDQS SPARQL-JSON ``payload`` to typed candidates. PURE — no I/O.

        Each binding carries an entity URI (``place``), a label (``placeLabel``),
        and a WKT coordinate (``coord``). The Q-number is the URI tail, kept as a
        provenance scalar in ``meta['qid']``.
        """
        candidates: list[PoiCandidate] = []
        for binding in payload.get("results", {}).get("bindings", []):
            # Read every field defensively: real WDQS legitimately OMITS a key
            # (absent, not null) — e.g. no bindable English label, or an entity
            # without a P625 coordinate — and bracket access would KeyError.
            place_uri = binding.get("place", {}).get("value")
            name = binding.get("placeLabel", {}).get("value")
            coord_wkt = binding.get("coord", {}).get("value")
            # A candidate with no usable name is useless for Step-4 dedup; one
            # with no coordinate can't be placed. Skip either rather than crash
            # or emit a degenerate candidate.
            if not name or not coord_wkt or not place_uri:
                continue
            lon, lat = _parse_point(coord_wkt)
            candidates.append(
                PoiCandidate(
                    name=name,
                    source="wikidata",
                    source_url=place_uri,
                    latitude=lat,
                    longitude=lon,
                    meta={"qid": place_uri.rsplit("/", 1)[-1]},
                )
            )
        return ConnectorResult(candidates=candidates)
