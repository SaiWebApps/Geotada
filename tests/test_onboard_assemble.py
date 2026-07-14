"""Step-4 CORE tests for ``src/onboard/assemble.py`` (pure ``assemble`` +
disk/registry ``write_city``).

Pure — no Neo4j, no network. Candidates are built from the committed
``tests/fixtures/onboard/london/`` fixtures via the real Step-3 connectors
(``run/`` for the fuller geosearch + extracts, the flat wikidata/osm/wikivoyage
files for cross-source signal), then merged/written into ``tmp_path``. Each
behavior below has a mutation/undo target documented on the test so a reverted
fix goes RED. Run with:
    make test-file FILE=tests/test_onboard_assemble.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from src import city_registry
from src.onboard.assemble import (
    AssembledCity,
    WikiExtract,
    assemble,
    write_city,
)
from src.onboard.assemble import _norm as _assemble_norm
from src.onboard.models import (
    CityContext,
    ConnectorResult,
    DiscoveryPointer,
    PoiCandidate,
)
from src.onboard.sources.osm import OsmSource
from src.onboard.sources.wikidata import WikidataConnector
from src.onboard.sources.wikipedia import WikipediaConnector
from src.onboard.sources.wikivoyage import WikivoyageConnector
from tests.test_data_integrity import _norm  # the INDEPENDENT CI guard's normalizer
from tests.test_gravity_distribution import _distribution_failures

FIXTURES = Path(__file__).parent / "fixtures" / "onboard" / "london"


# ---------------------------------------------------------------------------
# Fixture loaders / builders.
# ---------------------------------------------------------------------------
def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _ctx() -> CityContext:
    city = _load("run/city.json")
    return CityContext(
        slug=city["slug"], display_name=city["display_name"], bbox=tuple(city["bbox"])
    )


def _base_results(ctx: CityContext) -> list[ConnectorResult]:
    """The four real connectors parsed over the committed fixtures: the fuller
    ``run/`` geosearch + the flat wikidata/osm/wikivoyage for cross-source signal."""
    return [
        WikipediaConnector().parse(_load("run/wikipedia_geosearch.json"), ctx),
        WikidataConnector().parse(_load("wikidata_sparql.json"), ctx),
        OsmSource().parse(_load("osm_overpass.json"), ctx),
        WikivoyageConnector().parse(_load("wikivoyage_page.json"), ctx),
    ]


def _extracts() -> list[WikiExtract]:
    raw = _load("run/wikipedia_extracts.json")
    return [
        WikiExtract(
            poi_name=title,
            revid=str(d["revid"]),
            text=d["extract"],
            article_title=title,
            url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        )
        for title, d in raw.items()
    ]


# Collision checks copied from tests/test_data_integrity.py (:92 accent/case dup,
# :151 name/variation collision) so we assert them directly on assemble's output.
def _accent_dup_collisions(pois: list[dict]) -> list[str]:
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for p in pois:
        key = _norm(p["name"])
        if key in seen:
            dupes.append(f"{seen[key]!r} <-> {p['name']!r}")
        else:
            seen[key] = p["name"]
    return dupes


def _variation_collisions(pois: list[dict]) -> list[str]:
    reverse: dict[str, str] = {}
    collisions: list[str] = []
    for p in pois:
        keys = {_norm(p["name"])}
        for v in p.get("name_variations", []) or []:
            keys.add(_norm(v))
        for k in keys:
            if not k:
                continue
            owner = reverse.get(k)
            if owner and owner != p["name"]:
                collisions.append(f"{k!r} owned by {owner!r} and {p['name']!r}")
            reverse[k] = p["name"]
    return collisions


# ---------------------------------------------------------------------------
# Behaviors.
# ---------------------------------------------------------------------------
def test_assemble_norm_matches_data_integrity_guard() -> None:
    """assemble's merge key MUST be the byte-for-byte copy of the CI guard's
    ``_norm`` (accent-strip + casefold + strip) — if they ever drift, a merge
    that assemble thinks is unique collides in test_data_integrity."""
    for sample in ["Café de Paris", "CAFE  de  paris", "  Notre-Dame  ", "Big Ben", "Æthel"]:
        assert _assemble_norm(sample) == _norm(sample)


def test_at_least_30_pois_all_geofenced_and_audited() -> None:
    """>=30 POIs; every POI carries lat/lon and a truthy gravity_audit.
    UNDO: drop the ``_assign_tiers`` audit stamp (or the coord walk) -> RED."""
    ctx = _ctx()
    city = assemble(_base_results(ctx), ctx, _extracts())

    assert len(city.pois) >= 30, f"expected >=30 POIs, got {len(city.pois)}"
    for p in city.pois:
        assert p["latitude"] is not None and p["longitude"] is not None, p["name"]
        assert p["_pipeline"]["gravity_audit"], f"{p['name']} has no gravity_audit"
        audit = p["_pipeline"]["gravity_audit"]
        assert audit["signal_source"] == "onboard_auto_v1"
        assert audit["assigned_gravity"] == p["importance_tier"]
        assert audit["of"] == len(city.pois)


def test_forced_distribution_satisfies_shape_guard() -> None:
    """The forced rank-quantile tiers pass test_gravity_distribution's shape rule.
    UNDO: change the boundaries to a T3-heavy split (e.g. all mid) -> RED."""
    ctx = _ctx()
    city = assemble(_base_results(ctx), ctx, _extracts())

    counts = Counter(p["importance_tier"] for p in city.pois)
    failures = _distribution_failures(counts, len(city.pois))
    assert not failures, "unhealthy tier shape:\n" + "\n".join(failures)


def test_accent_and_variation_collision_free() -> None:
    """Accent/case dups and fuzzy near-dups merge; no name/variation collides.
    UNDO: bucket by ``canonical_name_key`` (keeps accents) -> the accented pair
    stays two POIs that collide under ``_norm`` -> RED."""
    ctx = _ctx()
    # Accent dup >75 m apart: exact-_norm merge must still collapse it (a wrong,
    # accent-KEEPING key would leave two POIs the fuzzy pass can't rejoin at range).
    accent_pair = ConnectorResult(
        candidates=[
            PoiCandidate(
                name="Café de Paris",
                source="wikivoyage",
                source_url="https://en.wikivoyage.org/wiki/London",
                latitude=51.510,
                longitude=-0.130,
            ),
            PoiCandidate(
                name="Cafe de Paris",
                source="osm",
                source_url="https://www.openstreetmap.org/node/999001",
                latitude=51.512,
                longitude=-0.135,
            ),
        ]
    )
    # Fuzzy near-dup at the same coords as the geosearch St Paul's -> one POI with
    # the alternate spelling demoted to a variation.
    fuzzy_dup = ConnectorResult(
        candidates=[
            PoiCandidate(
                name="St. Paul's Cathedral",
                source="wikivoyage",
                source_url="https://en.wikivoyage.org/wiki/London",
                latitude=51.5138,
                longitude=-0.0984,
            )
        ]
    )
    city = assemble([*_base_results(ctx), accent_pair, fuzzy_dup], ctx, _extracts())

    assert _accent_dup_collisions(city.pois) == []
    assert _variation_collisions(city.pois) == []

    # The accented pair collapsed to exactly one POI.
    cafe = [p for p in city.pois if _norm(p["name"]) == "cafe de paris"]
    assert len(cafe) == 1, f"accent dup did not merge: {[p['name'] for p in cafe]}"

    # The fuzzy near-dup became a name_variation on the canonical St Paul's POI.
    stpauls = next(p for p in city.pois if p["name"] == "St Paul's Cathedral")
    assert "St. Paul's Cathedral" in stpauls["name_variations"]


def test_out_of_bbox_candidate_dropped_and_centroid_in_bbox() -> None:
    """A candidate whose coords fall outside the bbox is DROPPED (never clipped),
    and the surviving centroid stays inside the bbox.
    UNDO: remove the bbox filter -> the sentinel is present -> RED."""
    ctx = _ctx()
    min_lat, max_lat, min_lon, max_lon = ctx.bbox
    sentinel = ConnectorResult(
        candidates=[
            PoiCandidate(
                name="Out Of Bbox Sentinel",
                source="wikidata",
                source_url="http://www.wikidata.org/entity/Q99999999",
                latitude=10.0,  # far outside London
                longitude=40.0,
            )
        ]
    )
    city = assemble([*_base_results(ctx), sentinel], ctx, _extracts())

    names = {p["name"] for p in city.pois}
    assert "Out Of Bbox Sentinel" not in names

    mean_lat = sum(p["latitude"] for p in city.pois) / len(city.pois)
    mean_lon = sum(p["longitude"] for p in city.pois) / len(city.pois)
    assert min_lat <= mean_lat <= max_lat
    assert min_lon <= mean_lon <= max_lon


def test_wall3_discovery_pointer_never_reaches_disk(tmp_path: Path) -> None:
    """WALL 3: a ConnectorResult carrying a shadow-library DiscoveryPointer must
    leave NO trace — not a filename, not a byte, not a POI name/variation.
    UNDO: give AssembledCity a ``pointers`` field that write_city dumps -> RED."""
    ctx = _ctx()
    pointer_result = ConnectorResult(
        pointers=[
            DiscoveryPointer(
                source="annas_archive",
                title="SHADOWMARKER",
                source_url="https://annas-archive.org/md5/x",
            )
        ]
    )
    city = assemble([*_base_results(ctx), pointer_result], ctx, _extracts())
    city_dir = write_city(
        city, ctx, data_root=tmp_path, registry_path=tmp_path / "cities.json"
    )

    # (a) Only the whitelisted files exist — nothing derived from the pointer.
    expected = {
        Path("poi-raw.json"),
        Path("areas.json"),
        Path("within_edges.json"),
        Path("book-log.json"),
    }
    for slug, ext in city.wiki_extracts.items():
        expected.add(Path("wikipedia") / f"{slug}-rev-{ext.revid}.txt")
    written = {p.relative_to(city_dir) for p in city_dir.rglob("*") if p.is_file()}
    assert written == expected, f"unexpected/missing files: {written ^ expected}"

    # (b) No written byte contains the pointer's title / host / url.
    forbidden = ("SHADOWMARKER", "annas-archive", "annas_archive", "md5/x")
    for path in city_dir.rglob("*"):
        if path.is_file():
            blob = path.read_text()
            for needle in forbidden:
                assert needle not in blob, f"{needle!r} leaked into {path.name}"

    # (c) No POI name or variation derives from the pointer.
    for p in city.pois:
        assert "SHADOWMARKER" not in p["name"]
        assert all("SHADOWMARKER" not in v for v in p["name_variations"])


def test_registry_entry_written_without_centre(tmp_path: Path) -> None:
    """write_city registers london with display_name/bbox/cloud_deployed=false and
    NO ``centre`` (register_city validates only those three fields).
    UNDO: remove the register_city call -> london absent from cities.json -> RED."""
    ctx = _ctx()
    city = assemble(_base_results(ctx), ctx, _extracts())
    registry_path = tmp_path / "cities.json"
    write_city(city, ctx, data_root=tmp_path, registry_path=registry_path)

    registry = json.loads(registry_path.read_text())
    assert "london" in registry
    entry = registry["london"]
    assert entry["display_name"] == "London"
    assert entry["bbox"] == [51.28, 51.7, -0.51, 0.33]
    assert entry["cloud_deployed"] is False
    assert "centre" not in entry


def test_registry_global_not_leaked(tmp_path: Path) -> None:
    """The redirected registry global is restored (try/finally), so the real
    src/cities.json is untouched and no sibling test sees a leaked path."""
    original = city_registry._REGISTRY_PATH
    ctx = _ctx()
    city = assemble(_base_results(ctx), ctx, _extracts())
    write_city(city, ctx, data_root=tmp_path, registry_path=tmp_path / "cities.json")

    assert original == city_registry._REGISTRY_PATH
    assert "london" not in city_registry.load_registry()


def test_thin_city_raises_valueerror_naming_count(tmp_path: Path) -> None:
    """write_city refuses a thin city and names the count; nothing is written."""
    ctx = _ctx()
    tiny = AssembledCity(
        slug="london",
        pois=[{"name": f"P{i}", "latitude": 51.5, "longitude": -0.1} for i in range(5)],
        wiki_extracts={},
    )
    with pytest.raises(ValueError, match=r"\b5\b"):
        write_city(tiny, ctx, data_root=tmp_path, registry_path=tmp_path / "cities.json")

    assert not (tmp_path / "london").exists()


def test_write_city_rejects_traversal_slug_and_writes_nothing(tmp_path: Path) -> None:
    """write_city validates ``city.slug`` at the VERY TOP — before any mkdir/write
    — so a path-traversal slug ('../evil') raises ValueError and creates NO file:
    not inside the data root, and NOT at the escaped target outside it. (>=30 POIs
    so the slug guard, not the thin-city guard, is what fires.)

    UNDO: remove the slug guard at the top of write_city -> it mkdirs
    tmp_path/../evil and writes poi-raw.json OUTSIDE the data root (register_city's
    late slug check raises only AFTER the files are on disk) -> the escaped target
    exists -> RED."""
    ctx = _ctx()  # a valid ctx; write_city keys off city.slug, not ctx.slug
    evil = AssembledCity(
        slug="../evil",
        pois=[{"name": f"P{i}", "latitude": 51.5, "longitude": -0.1} for i in range(30)],
        wiki_extracts={},
    )
    escaped = tmp_path.parent / "evil"
    assert not escaped.exists(), "precondition: escaped target must not pre-exist"

    with pytest.raises(ValueError, match=r"slug"):
        write_city(evil, ctx, data_root=tmp_path, registry_path=tmp_path / "cities.json")

    assert not escaped.exists(), f"traversal target was written OUTSIDE the data root: {escaped}"
    assert not (tmp_path / "..evil").exists()
    written = list(tmp_path.iterdir())
    assert written == [], f"files written into the data root: {written}"


# ---------------------------------------------------------------------------
# FIX 1 — every write_text must pass encoding="utf-8" (accented cities round-trip
# on a non-utf-8-locale runner; validate_beats READS with encoding="utf-8").
# ---------------------------------------------------------------------------
def test_write_city_writes_utf8_and_roundtrips_nonascii(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every corpus file write_city produces passes encoding='utf-8', so an
    accented POI/extract (Café/Zürich) round-trips byte-exact — matching
    validate_beats' utf-8 read.
    UNDO: drop encoding='utf-8' from assemble._atomic_write_text -> a corpus file
    is written with encoding=None -> RED."""
    captured: list[tuple[Path, object]] = []
    real_write_text = Path.write_text

    def _spy(self, data, *args, **kwargs):
        captured.append((self, kwargs.get("encoding")))
        return real_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _spy)

    ctx = _ctx()
    city = assemble(_base_results(ctx), ctx, _extracts())
    city.pois[0]["name"] = "Café de Flore"
    city.wiki_extracts["cafe-de-flore-nonascii"] = WikiExtract(
        poi_name="Café de Flore",
        revid="1",
        text="Zürich, naïve façade — Café crème.",
        article_title="Café de Flore",
        url="https://en.wikipedia.org/wiki/Cafe_de_Flore",
    )
    city_dir = write_city(city, ctx, data_root=tmp_path, registry_path=tmp_path / "cities.json")

    # (a) EVERY corpus-file write under the city dir passed encoding='utf-8'.
    corpus_writes = [(p, enc) for p, enc in captured if city_dir in p.parents]
    assert corpus_writes, "no corpus files were written"
    for p, enc in corpus_writes:
        assert enc == "utf-8", f"{p.name} written with encoding={enc!r}, not 'utf-8'"

    # (b) Non-ASCII POI name + extract text round-trip byte-exact under a utf-8 read.
    pois = json.loads((city_dir / "poi-raw.json").read_text(encoding="utf-8"))
    assert any(p["name"] == "Café de Flore" for p in pois)
    extract_txt = (city_dir / "wikipedia" / "cafe-de-flore-nonascii-rev-1.txt").read_text(
        encoding="utf-8"
    )
    assert extract_txt == "Zürich, naïve façade — Café crème."


def test_cli_atomic_write_text_uses_utf8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI's beats.json writer also passes encoding='utf-8', so accented beats
    round-trip on a non-utf-8-locale runner (validate_beats reads utf-8).
    UNDO: drop encoding='utf-8' from cli._atomic_write_text -> RED."""
    from src.onboard.cli import _atomic_write_text as _cli_atomic_write_text

    captured: list[object] = []
    real_write_text = Path.write_text

    def _spy(self, data, *args, **kwargs):
        captured.append(kwargs.get("encoding"))
        return real_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _spy)

    target = tmp_path / "beats.json"
    _cli_atomic_write_text(target, "Zürich café — naïve façade")

    assert captured == ["utf-8"], captured
    assert target.read_text(encoding="utf-8") == "Zürich café — naïve façade"


# ---------------------------------------------------------------------------
# FIX 2 — same-name merging must be GEO-AWARE (distinct places sharing a name are
# NOT silently collapsed; co-located duplicates still merge to one POI).
# ---------------------------------------------------------------------------
def test_same_name_distant_places_are_kept_separate() -> None:
    """Two GENUINELY DISTINCT places sharing an exact name but ~17 km apart must
    stay TWO POIs (geo-aware split), deterministically disambiguated — never
    silently collapsed to one with the other's data lost.
    UNDO: revert the geo-split (merge the whole exact-norm bucket) -> one POI -> RED."""
    ctx = _ctx()
    distant = ConnectorResult(
        candidates=[
            PoiCandidate(
                name="St Mary's Church",
                source="osm",
                source_url="https://www.openstreetmap.org/node/111",
                latitude=51.55,  # North London
                longitude=-0.10,
            ),
            PoiCandidate(
                name="St Mary's Church",
                source="wikidata",
                source_url="http://www.wikidata.org/entity/Q222",
                latitude=51.40,  # South London, ~17 km away
                longitude=-0.05,
            ),
        ]
    )
    city = assemble([*_base_results(ctx), distant], ctx, _extracts())

    marys = [p for p in city.pois if p["name"].startswith("St Mary's Church")]
    assert sorted(p["name"] for p in marys) == [
        "St Mary's Church",
        "St Mary's Church (2)",
    ], [p["name"] for p in marys]

    # Both distinct places survived — neither silently dropped.
    coords = {(round(p["latitude"], 2), round(p["longitude"], 2)) for p in marys}
    assert coords == {(51.55, -0.10), (51.40, -0.05)}, coords

    # No accent/case collision introduced by the disambiguation.
    assert _accent_dup_collisions(city.pois) == []
    assert _variation_collisions(city.pois) == []


def test_same_name_colocated_still_merges() -> None:
    """Two same-name candidates ~20 m apart are the SAME place -> exactly ONE POI:
    the geo-split must not OVER-split co-located duplicates.
    UNDO: n/a (guards the fix against over-correction; distant test guards under)."""
    ctx = _ctx()
    colocated = ConnectorResult(
        candidates=[
            PoiCandidate(
                name="St Mary's Church",
                source="osm",
                source_url="https://www.openstreetmap.org/node/1",
                latitude=51.50000,
                longitude=-0.10000,
            ),
            PoiCandidate(
                name="St Mary's Church",
                source="wikidata",
                source_url="http://www.wikidata.org/entity/Q1",
                latitude=51.50018,  # ~20 m north
                longitude=-0.10000,
            ),
        ]
    )
    city = assemble([*_base_results(ctx), colocated], ctx, _extracts())

    marys = [p for p in city.pois if p["name"].startswith("St Mary's Church")]
    assert len(marys) == 1, [p["name"] for p in marys]
    assert marys[0]["name"] == "St Mary's Church"
    # It merged the two co-located sources into one POI.
    assert marys[0]["_pipeline"]["gravity_audit"]["cross_source_agreement"] == 2


# ---------------------------------------------------------------------------
# FIX 3 — the registry redirect must restore the global even if register_city
# raises (try/finally), and never corrupt the real src/cities.json.
# ---------------------------------------------------------------------------
def test_registry_global_restored_on_register_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_register restores city_registry._REGISTRY_PATH even when register_city
    raises mid-write, so a failed onboarding leaks neither the redirected global
    to sibling tests nor a byte into the real src/cities.json.
    UNDO: replace the try/finally in _register with a plain call -> the global
    stays redirected after the raise -> RED."""
    original_path = city_registry._REGISTRY_PATH
    real_registry_bytes = original_path.read_bytes()

    def _boom(*args, **kwargs):
        raise RuntimeError("register blew up")

    monkeypatch.setattr(city_registry, "register_city", _boom)

    ctx = _ctx()
    city = assemble(_base_results(ctx), ctx, _extracts())
    with pytest.raises(RuntimeError, match="register blew up"):
        write_city(city, ctx, data_root=tmp_path, registry_path=tmp_path / "cities.json")

    # The module global was restored despite the raise ...
    assert original_path == city_registry._REGISTRY_PATH
    # ... and the real src/cities.json is byte-for-byte untouched.
    assert original_path.read_bytes() == real_registry_bytes
