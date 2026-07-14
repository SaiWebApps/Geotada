"""Shared onboarding flow — the connector resolution + per-source consult +
Wikipedia-extract build that BOTH the CLI (``src/onboard/cli.py``) and the API
router (``src/api/routes/onboard.py``) drive.

These are the PURE flow primitives, decoupled from any CLI concern (no argparse,
no printing): given a ``JobStore`` + ``job_id`` they emit the SAME live progress
events a real run would, so the API's SSE stream and the CLI's summary observe an
identical event log. ``consult_source`` is the one seam that branches on the
network mode:

- ``fetch.HTTP_MODE == "live"`` → go through ``base.run_connector`` (the ingest
  allowlist door — grey-zone wall 2) which actually fetches; or
- the default ``fixture`` mode → load the connector's committed run fixture from
  ``tests/fixtures/onboard/{slug}/`` and call its PURE ``parse`` directly, while
  emitting the SAME ``source_consult`` + scalar-only ``candidate_batch`` events
  ``run_connector`` emits live — so the flow mirrors a real run without touching
  the network.

Splitting these out of ``cli.py`` keeps the API router from importing the CLI's
privates: both callers depend on this module's PUBLIC surface, nothing more.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode

from src.onboard import fetch
from src.onboard.assemble import WikiExtract
from src.onboard.jobs import JobStore
from src.onboard.models import CityContext, ConnectorResult
from src.onboard.sources.base import SourceConnector, run_connector
from src.onboard.sources.osm import OsmSource
from src.onboard.sources.wikidata import WikidataConnector
from src.onboard.sources.wikipedia import WikipediaConnector
from src.onboard.sources.wikivoyage import WikivoyageConnector

# Repo root: src/onboard/flow.py -> src/onboard -> src -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "onboard"

# The connectors an onboarding MODE consults. ``license_clean`` drives the four
# license-clean POI-discovery sources (order sets NAME/COORD precedence ties
# deterministically, matching test_onboard_assemble's _base_results).
MODE_CONNECTORS: dict[str, tuple[str, ...]] = {
    "license_clean": ("wikipedia", "wikivoyage", "wikidata", "osm"),
}

# Slug -> the PURE connector instance whose ``consult_url``/``parse`` this flow
# drives (no network — see module docstring).
CONNECTORS: dict[str, SourceConnector] = {
    "wikipedia": WikipediaConnector(),
    "wikivoyage": WikivoyageConnector(),
    "wikidata": WikidataConnector(),
    "osm": OsmSource(),
}

# Slug -> the committed run fixture the fixture-mode consult feeds that
# connector's ``parse``. Wikipedia uses the fuller ``run/`` geosearch; the others
# use the flat cross-source fixtures (mirrors test_onboard_assemble._base_results).
CONNECTOR_FIXTURE: dict[str, str] = {
    "wikipedia": "run/wikipedia_geosearch.json",
    "wikivoyage": "wikivoyage_page.json",
    "wikidata": "wikidata_sparql.json",
    "osm": "osm_overpass.json",
}


class OnboardError(Exception):
    """A user-facing onboarding failure (the CLI prints it to stderr with a
    non-zero exit; the API converts it into an ``error`` event + status)."""


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def resolve_connectors(modes: list[str]) -> list[str]:
    """The ordered, de-duplicated connector slugs for the requested modes.

    Raises ``OnboardError`` on an unknown mode — a silent no-op would ship a
    thin/empty city.
    """
    ordered: list[str] = []
    for mode in modes:
        if mode not in MODE_CONNECTORS:
            raise OnboardError(
                f"unknown mode {mode!r}; supported modes are {sorted(MODE_CONNECTORS)}"
            )
        for slug in MODE_CONNECTORS[mode]:
            if slug not in ordered:
                ordered.append(slug)
    return ordered


def consult_source(
    slug: str, ctx: CityContext, store: JobStore, job_id: str
) -> ConnectorResult:
    """Consult ONE source, emitting the same live events either mode would.

    In ``live`` mode this delegates to ``base.run_connector`` (the network door).
    In the default ``fixture`` mode it emits a ``source_consult`` event naming the
    concrete URL the connector WOULD GET live, then — instead of fetching, which
    the fixture-mode door forbids — parses the committed fixture and emits a
    scalar-only ``candidate_batch`` event (wall 3: never body text in ``data``).
    """
    connector = CONNECTORS[slug]
    if fetch.HTTP_MODE == "live":
        return run_connector(connector, ctx, store, job_id)

    fixture = FIXTURES_ROOT / ctx.slug / CONNECTOR_FIXTURE[slug]
    if not fixture.exists():
        raise OnboardError(f"no {slug} fixture for {ctx.slug!r}: {fixture} not found")

    url, params = connector.consult_url(ctx)
    full = f"{url}?{urlencode(params)}" if params else url
    store.append_event(job_id, "source_consult", f"Consulting {slug}", source=slug, url=full)

    result = connector.parse(_load_json(fixture), ctx)
    store.append_event(
        job_id,
        "candidate_batch",
        f"{slug}: {len(result.candidates)} candidates, {len(result.documents)} documents",
        source=slug,
        data={"candidates": len(result.candidates), "documents": len(result.documents)},
    )
    return result


def build_extracts(slug: str) -> list[WikiExtract]:
    """Pinned ``WikiExtract``s from ``run/wikipedia_extracts.json``.

    Each entry is ``{title: {"revid": ..., "extract": ...}}``; ``write_city``
    saves each as ``wikipedia/{slug}-rev-{revid}.txt`` verbatim, which the beat
    drafter quotes and ``validate_beats`` grounds against.
    """
    raw = _load_json(FIXTURES_ROOT / slug / "run" / "wikipedia_extracts.json")
    return [
        WikiExtract(
            poi_name=title,
            revid=str(entry["revid"]),
            text=entry["extract"],
            article_title=title,
            url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}?oldid={entry['revid']}",
        )
        for title, entry in raw.items()
    ]
