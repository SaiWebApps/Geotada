"""Step-4 onboarding CLI — assemble a city + draft its beats, end to end.

Runs the same Step-3 → Step-4 flow the live onboarding API will drive, but in
FIXTURE mode: the connectors' network door (``src.onboard.fetch``) defaults to
``fixture`` and raises on any real GET, so this CLI never touches the network.
Instead it loads each connector's committed run fixture from
``tests/fixtures/onboard/{city}/`` and calls the connector's PURE ``parse``
directly — emitting the same ``source_consult`` / ``candidate_batch`` events to a
``JobStore`` that ``base.run_connector`` emits live, so the flow mirrors the real
run.

The pipeline:

1. Geocode (fixture mode = ``run/city.json``) → ``CityContext``.
2. Parse each license-clean connector over its fixture → ``ConnectorResult`` list.
3. Build pinned ``WikiExtract``s from ``run/wikipedia_extracts.json``.
4. ``assemble`` → geofenced, gravity-tiered POIs (pure, no I/O).
5. ``beat_draft.draft_all`` → beats grounded in the pinned Wikipedia revisions
   (mock provider by default → free; a live provider needs ``--confirm-cost``).
6. ``write_city`` → the ``data/{slug}/`` corpus + registry entry (honouring
   ``ONBOARD_DATA_ROOT`` / ``ONBOARD_REGISTRY_PATH`` so the bar writes to a tmp
   root, never the committed ``data/`` or ``src/cities.json``).
7. Write ``beats.json`` beside the corpus and gate it through
   ``validate_beats.validate`` — non-zero exit on any error.

Usage:
    python -m src.onboard.cli --city london --modes license_clean [--confirm-cost]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode

from scripts import validate_beats
from src.onboard.assemble import WikiExtract, assemble, write_city
from src.onboard.jobs import get_store
from src.onboard.models import CityContext, ConnectorResult
from src.onboard.sources.base import SourceConnector
from src.onboard.sources.osm import OsmSource
from src.onboard.sources.wikidata import WikidataConnector
from src.onboard.sources.wikipedia import WikipediaConnector
from src.onboard.sources.wikivoyage import WikivoyageConnector

# Repo root: src/onboard/cli.py -> src/onboard -> src -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures" / "onboard"

# The connectors an onboarding MODE consults. Step 4 handles ``license_clean``:
# the four license-clean POI-discovery sources (order sets NAME/COORD precedence
# ties deterministically, matching test_onboard_assemble's _base_results).
_MODE_CONNECTORS: dict[str, tuple[str, ...]] = {
    "license_clean": ("wikipedia", "wikivoyage", "wikidata", "osm"),
}

# Slug -> the PURE connector instance whose ``parse`` maps a fixture payload to a
# typed ConnectorResult (no network — see module docstring).
_CONNECTORS: dict[str, SourceConnector] = {
    "wikipedia": WikipediaConnector(),
    "wikivoyage": WikivoyageConnector(),
    "wikidata": WikidataConnector(),
    "osm": OsmSource(),
}

# Slug -> the committed run fixture the CLI feeds that connector's ``parse`` in
# fixture mode. Wikipedia uses the fuller ``run/`` geosearch; the others use the
# flat cross-source fixtures (mirrors test_onboard_assemble._base_results).
_CONNECTOR_FIXTURE: dict[str, str] = {
    "wikipedia": "run/wikipedia_geosearch.json",
    "wikivoyage": "wikivoyage_page.json",
    "wikidata": "wikidata_sparql.json",
    "osm": "osm_overpass.json",
}


class OnboardError(Exception):
    """A user-facing onboarding failure (printed to stderr, non-zero exit)."""


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (tmp sibling + ``os.replace``)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _resolve_connectors(modes: list[str]) -> list[str]:
    """The ordered, de-duplicated connector slugs for the requested modes.

    Raises ``OnboardError`` on an unknown mode — Step 4 only knows the modes in
    ``_MODE_CONNECTORS``; a silent no-op would ship a thin/empty city.
    """
    ordered: list[str] = []
    for mode in modes:
        if mode not in _MODE_CONNECTORS:
            raise OnboardError(
                f"unknown mode {mode!r}; Step-4 handles {sorted(_MODE_CONNECTORS)}"
            )
        for slug in _MODE_CONNECTORS[mode]:
            if slug not in ordered:
                ordered.append(slug)
    return ordered


def _geocode(city: str) -> CityContext:
    """Fixture-mode geocode: read ``run/city.json`` into a ``CityContext``.

    (Live geocoding is a later step; here the city frame comes from the committed
    fixture, so the run is deterministic and network-free.)
    """
    city_json = FIXTURES_ROOT / city / "run" / "city.json"
    if not city_json.exists():
        raise OnboardError(f"no city fixture for {city!r}: {city_json} not found")
    data = _load_json(city_json)
    return CityContext(
        slug=data["slug"],
        display_name=data["display_name"],
        bbox=tuple(data["bbox"]),
    )


def _consult(
    slug: str, ctx: CityContext, store, job_id: str
) -> ConnectorResult:
    """Parse one connector over its fixture, emitting the same live events.

    Mirrors ``base.run_connector``: it emits a ``source_consult`` event naming the
    concrete URL the connector WOULD GET live, then (instead of fetching, which
    the fixture-mode network door forbids) parses the committed fixture and emits
    a scalar-only ``candidate_batch`` event.
    """
    connector = _CONNECTORS[slug]
    fixture = FIXTURES_ROOT / ctx.slug / _CONNECTOR_FIXTURE[slug]
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


def _build_extracts(city: str) -> list[WikiExtract]:
    """Pinned ``WikiExtract``s from ``run/wikipedia_extracts.json``.

    Each entry is ``{title: {"revid": ..., "extract": ...}}``; write_city saves
    each as ``wikipedia/{slug}-rev-{revid}.txt`` verbatim, which the beat drafter
    quotes and ``validate_beats`` grounds against.
    """
    raw = _load_json(FIXTURES_ROOT / city / "run" / "wikipedia_extracts.json")
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


def _load_beat_drafter():
    """Import the parallel-built beat drafter, or exit with a clear message.

    ``src/onboard/beat_draft.py`` is built alongside this CLI; if it has not
    landed yet the run stops with a distinct exit code so the caller re-runs once
    it does, rather than failing obscurely mid-flow.
    """
    try:
        from src.onboard.beat_draft import CostNotConfirmed, draft_all
    except ImportError as exc:
        print(
            "src/onboard/beat_draft.py is not importable yet "
            f"(sibling drafter still building?): {exc}",
            file=sys.stderr,
        )
        raise SystemExit(3) from exc
    return draft_all, CostNotConfirmed


def _env_path(name: str) -> Path | None:
    """The ``Path`` in env var ``name``, or ``None`` if unset/empty."""
    value = os.getenv(name)
    return Path(value) if value else None


def run(city: str, modes: list[str], *, confirm_cost: bool) -> int:
    """Run the full onboarding flow for ``city``. Returns a process exit code."""
    connector_slugs = _resolve_connectors(modes)
    ctx = _geocode(city)

    store = get_store()
    job = store.create(ctx.slug, modes)
    store.set_status(job.id, "running")

    results = [_consult(slug, ctx, store, job.id) for slug in connector_slugs]
    extracts = _build_extracts(city)

    assembled = assemble(results, ctx, extracts)
    store.set_status(job.id, "assembled")

    draft_all, cost_not_confirmed = _load_beat_drafter()
    store.set_status(job.id, "drafting")
    try:
        beats = draft_all(assembled.pois, assembled.wiki_extracts, confirm=confirm_cost)
    except cost_not_confirmed as exc:
        print(
            f"beat drafting needs cost confirmation — re-run with --confirm-cost: {exc}",
            file=sys.stderr,
        )
        return 4

    # write_city honours ONBOARD_DATA_ROOT for the corpus root; it does NOT read
    # ONBOARD_REGISTRY_PATH, so the CLI resolves that env itself and passes it in
    # — without it, register_city would touch the real src/cities.json.
    city_dir = write_city(
        assembled,
        ctx,
        data_root=_env_path("ONBOARD_DATA_ROOT"),
        registry_path=_env_path("ONBOARD_REGISTRY_PATH"),
    )

    beats_path = city_dir / "beats.json"
    _atomic_write_text(beats_path, json.dumps(beats, indent=2, ensure_ascii=False) + "\n")

    errors = validate_beats.validate(beats_path)
    registry_path = _env_path("ONBOARD_REGISTRY_PATH")

    _print_summary(ctx, assembled, beats, city_dir, registry_path, errors)
    return 1 if errors else 0


def _print_summary(
    ctx: CityContext,
    assembled,
    beats: list[dict],
    city_dir: Path,
    registry_path: Path | None,
    errors: list[str],
) -> None:
    """Print the run summary: POI count, tier histogram, beats, registry, gate."""
    hist = Counter(p["importance_tier"] for p in assembled.pois)
    tier_line = "  ".join(f"T{tier}={hist[tier]}" for tier in sorted(hist, reverse=True))

    print("─" * 60)
    print(f"onboard-city: {ctx.display_name} ({ctx.slug})")
    print(f"  POIs:        {len(assembled.pois)}")
    print(f"  tiers:       {tier_line}")
    print(f"  extracts:    {len(assembled.wiki_extracts)} pinned Wikipedia revisions")
    print(f"  beats:       {len(beats)}")
    print(f"  city dir:    {city_dir}")
    print(f"  registry:    {registry_path or '(default src/cities.json)'}")
    if errors:
        print(f"  validate:    FAIL ({len(errors)} issue(s))")
        for line in errors:
            print(f"    - {line}")
    else:
        print("  validate:    PASS")
    print("─" * 60)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.onboard.cli",
        description="Onboard a city end to end (fixture + mock in the bar).",
    )
    parser.add_argument("--city", required=True, help="city slug, e.g. london")
    parser.add_argument(
        "--modes",
        required=True,
        help="comma-separated onboarding modes (Step 4 handles: license_clean)",
    )
    parser.add_argument(
        "--confirm-cost",
        action="store_true",
        help="confirm paid beat-drafting (needed only for a live ONBOARD_PROVIDER)",
    )
    args = parser.parse_args(argv)
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    if not modes:
        parser.error("--modes must name at least one mode")

    try:
        return run(args.city, modes, confirm_cost=args.confirm_cost)
    except OnboardError as exc:
        print(f"onboard-city: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
