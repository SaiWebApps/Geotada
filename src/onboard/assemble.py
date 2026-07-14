"""Step-4 CORE: merge cross-source candidates into a writable ``data/{slug}/``.

Two surfaces, one wall between them:

- ``assemble`` is PURE (no I/O): it merges the ``PoiCandidate`` hits from every
  Step-3 ``ConnectorResult`` into deduplicated POI dicts, geofences them to the
  city bbox, and forces a healthy gravity-tier distribution — returning an
  ``AssembledCity``. It reads ONLY ``result.candidates``; it NEVER touches
  ``result.pointers`` or ``result.documents``, so a shadow-library
  ``DiscoveryPointer`` has no path into the assembled city (grey-zone wall 3).
- ``write_city`` is the ONLY disk/registry touch: it atomically writes the exact
  ``data/{slug}/`` corpus the Step-8 uploader consumes and registers the city.

The merge/dedup + forced distribution are designed against the silent CI guards
that turn RED the instant ``data/{slug}/`` exists:

- ``tests/test_data_integrity.py`` dedups on accent-strip + casefold (``_norm``,
  copied byte-for-byte below) and forbids name/variation collisions, so the merge
  key MIRRORS ``_norm`` (not ``canonical_name_key``, which keeps accents) and a
  post-merge sweep drops any colliding variation.

ZERO-FALSE-MERGE is GEO-AWARE, not name-only: two candidates that normalize to
the same name merge ONLY when they are co-located (within ``_SAME_PLACE_METERS``);
distinct places that merely share a name (e.g. two "St Mary's Church" in different
boroughs) are split into separate POIs and deterministically disambiguated
("Name", "Name (2)", ...), so no place is ever silently dropped by a name clash.
The fuzzy near-dup pass adds a second, tighter geo gate for near-identical names.
- ``tests/test_gravity_distribution.py`` requires a truthy
  ``_pipeline.gravity_audit`` on every POI plus a healthy tier SHAPE (T5 ∈
  [7,20]%, T3 ≤ 35%, T1+T2 ≥ T4+T5); the rank-quantile forced distribution below
  emits exactly that shape.
- ``scripts/upload_paris.py`` silently drops out-of-bbox POIs, so ``assemble``
  drops them here (never clips) — keeping the centroid inside the registry bbox.
"""

from __future__ import annotations

import json
import logging
import math
import os
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from rapidfuzz import fuzz

from scripts.beat_builder import slugify
from src import city_registry
from src.onboard.models import CityContext, ConnectorResult, PoiCandidate

logger = logging.getLogger(__name__)

# Repo root: src/onboard/assemble.py -> src/onboard -> src -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The minimum POI count a real city must carry — never ship a thin city.
MIN_POIS = 30

# NAME-source precedence: which source's spelling wins as the display name.
_NAME_PRIORITY: dict[str, int] = {
    "wikidata": 0,
    "wikipedia": 1,
    "osm": 2,
    "wikivoyage": 3,
}

# COORD-source precedence: the first source (in this order) that carries a
# non-null lat/lon wins the merged POI's coordinates.
_COORD_PRECEDENCE: tuple[str, ...] = ("wikidata", "osm", "wikipedia", "wikivoyage")

# Conservative near-dup thresholds (poi-dedup's ZERO-FALSE-MERGE rule): a pair
# auto-merges ONLY when the names are near-identical AND essentially co-located.
_FUZZ_MIN_RATIO = 94
_FUZZ_MAX_METERS = 75.0

# GEO gate for the EXACT-norm bucket path: two candidates that normalize to the
# SAME name are the SAME place only if within this distance; farther apart they
# are DISTINCT places sharing a name (e.g. two "St Mary's Church" in different
# boroughs) and must NOT be silently collapsed. Wider than the fuzzy gate above
# because an exact-name match is stronger evidence of co-reference than a fuzzy one.
_SAME_PLACE_METERS = 150.0


# ---------------------------------------------------------------------------
# Normalization — copied BYTE-FOR-BYTE from tests/test_data_integrity.py:23-30
# so the merge key matches the dedup guard exactly (accent-strip + casefold +
# strip). Do NOT import the test; this is the load-bearing duplicate.
# ---------------------------------------------------------------------------
def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn"
    )


def _norm(s: str) -> str:
    return _strip_accents(s).lower().strip()


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in metres."""
    r = 6371000.0  # mean Earth radius (m)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# Frozen interface consumed by Step-4 beat_draft / cli (Devs B & C).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WikiExtract:
    """One pinned Wikipedia revision's plain text, keyed to a POI.

    ``write_city`` saves each as ``wikipedia/{slugify(poi_name)}-rev-{revid}.txt``
    VERBATIM — the same pinned-revision layout ``scripts/wiki_fetch.py`` produces,
    which ``validate_beats.py`` later checks beats' ``source_passage`` against.
    """

    poi_name: str
    revid: str
    text: str
    article_title: str
    url: str


@dataclass
class AssembledCity:
    """The pure result of ``assemble`` — everything ``write_city`` needs and
    NOTHING that could carry shadow-library text.

    ``pois`` are finished POI dicts (poi-raw.json shape); ``wiki_extracts`` maps
    ``slugify(poi_name) -> WikiExtract``. ``cloud_deployed`` is threaded from
    ``assemble`` to the registry entry ``write_city`` writes (a new city defaults
    to local-only, ``False``, until deployed to Aura). There is deliberately NO
    ``pointers`` field: ``DiscoveryPointer`` never reaches disk (wall 3).
    """

    slug: str
    pois: list[dict]
    wiki_extracts: dict[str, WikiExtract] = field(default_factory=dict)
    cloud_deployed: bool = False


# ---------------------------------------------------------------------------
# Merge helpers (all pure).
# ---------------------------------------------------------------------------
def _name_priority(source: str) -> int:
    return _NAME_PRIORITY.get(source, 99)


def _display_name(cands: list[PoiCandidate]) -> str:
    """The display name for a merged group: the highest-priority NAME source's
    spelling; ties broken by ``_norm`` then raw name for determinism."""
    return min(cands, key=lambda c: (_name_priority(c.source), _norm(c.name), c.name)).name


def _merged_coords(cands: list[PoiCandidate]) -> tuple[float | None, float | None]:
    """First non-null (lat, lon) walking ``_COORD_PRECEDENCE``; a source not in
    the precedence list is only used as a last resort."""
    for src in _COORD_PRECEDENCE:
        for c in cands:
            if c.source == src and c.latitude is not None and c.longitude is not None:
                return c.latitude, c.longitude
    for c in cands:
        if c.latitude is not None and c.longitude is not None:
            return c.latitude, c.longitude
    return None, None


class _UnionFind:
    """Tiny union-find so a chain of near-dups (A~B, B~C) collapses to one POI."""

    def __init__(self, keys: list[str]) -> None:
        self._parent = {k: k for k in keys}

    def find(self, x: str) -> str:
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # Path-compress.
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


def _short_description(cands: list[PoiCandidate]) -> str:
    """The best (longest) non-empty candidate ``short_description``, else ""."""
    descs = [c.short_description for c in cands if (c.short_description or "").strip()]
    return max(descs, key=len) if descs else ""


def _bucket_candidates(results: list[ConnectorResult]) -> dict[str, list[PoiCandidate]]:
    """Bucket every candidate across every result by ``_norm(name)`` (the exact
    accent+case dedup key). This is the first pass; ``_geo_split_bucket`` then
    splits each bucket by proximity so a shared exact name never merges two
    genuinely DISTINCT places (see ZERO-FALSE-MERGE in the module docstring)."""
    buckets: dict[str, list[PoiCandidate]] = {}
    for result in results:
        for cand in result.candidates:
            buckets.setdefault(_norm(cand.name), []).append(cand)
    return buckets


def _geo_split_bucket(cands: list[PoiCandidate]) -> list[list[PoiCandidate]]:
    """Split ONE exact-``_norm`` bucket into same-place clusters by proximity.

    The common case is UNCHANGED from the pre-fix single-group merge: when a bucket
    has 0 or 1 placeable point, or ALL its placeable points co-locate (within
    ``_SAME_PLACE_METERS``), the whole bucket — coord AND no-coord candidates, in
    original order — is returned as ONE cluster. (A wholly-coordless bucket is that
    one cluster too; ``_merged_coords`` returns ``None`` and the caller drops it, as
    before.) This is what keeps an already-correct city byte-for-byte identical.

    The fix bites ONLY when the placeable points fall into 2+ proximity clusters:
    genuinely DISTINCT places share a name (e.g. two "St Mary's Church" 17 km apart).
    Then each cluster is a separate place (original relative order preserved); any
    no-coord candidate can't be assigned to one place, so it forms its own coordless
    cluster the caller drops (never mis-attributed). Greedy union-find over pairwise
    distance, so a chain of near points stays one cluster. Never crashes on missing
    coords."""
    coord_idx = [
        i for i, c in enumerate(cands) if c.latitude is not None and c.longitude is not None
    ]
    if len(coord_idx) <= 1:
        return [list(cands)]  # 0 or 1 placeable point -> one place (as before)

    keys = [str(k) for k in range(len(coord_idx))]
    uf = _UnionFind(keys)
    for a in range(len(coord_idx)):
        for b in range(a + 1, len(coord_idx)):
            ca, cb = cands[coord_idx[a]], cands[coord_idx[b]]
            if (
                _haversine_m(ca.latitude, ca.longitude, cb.latitude, cb.longitude)
                <= _SAME_PLACE_METERS
            ):
                uf.union(keys[a], keys[b])

    root_per_pos = [uf.find(keys[a]) for a in range(len(coord_idx))]
    roots_in_order: list[str] = []
    for r in root_per_pos:
        if r not in roots_in_order:
            roots_in_order.append(r)
    if len(roots_in_order) == 1:
        return [list(cands)]  # all placeable points co-locate -> one place (as before)

    # GENUINE SPLIT: distinct places share this name.
    clusters_by_root: dict[str, list[PoiCandidate]] = {r: [] for r in roots_in_order}
    for a, i in enumerate(coord_idx):
        clusters_by_root[root_per_pos[a]].append(cands[i])
    clusters = [clusters_by_root[r] for r in roots_in_order]
    no_coord = [c for c in cands if c.latitude is None or c.longitude is None]
    if no_coord:
        clusters.append(no_coord)
    return clusters


def _disambiguate_same_name(pois: list[dict], ctx: CityContext) -> None:
    """DE-COLLIDE canonical names of DISTINCT places (in place).

    A bucket that geo-split into 2+ surviving places leaves POIs sharing one
    ``_norm`` name — which would (a) trip the CI accent/case dedup guard and (b)
    make two places look like one. Keep the first (by DESCENDING cross-source
    agreement, then coords for determinism) as the plain name and append
    ``' (2)'``, ``' (3)'``, ... to the rest, LOGGING each split so the divergence is
    never silent. (Distinct ``_norm`` names can only arise within one exact-norm
    bucket, so this touches nothing the fuzzy pass legitimately merged.)"""
    by_norm: dict[str, list[dict]] = {}
    for poi in pois:
        by_norm.setdefault(_norm(poi["name"]), []).append(poi)
    for group in by_norm.values():
        if len(group) < 2:
            continue
        ordered = sorted(
            group,
            key=lambda p: (
                -p["_pipeline"]["gravity_audit"]["cross_source_agreement"],
                p["latitude"],
                p["longitude"],
            ),
        )
        base = ordered[0]["name"]
        logger.info(
            "assemble(%s): same-name split — %r kept as %d distinct places at %s",
            ctx.slug,
            base,
            len(ordered),
            [(round(p["latitude"], 5), round(p["longitude"], 5)) for p in ordered],
        )
        for n, poi in enumerate(ordered[1:], start=2):
            poi["name"] = f"{base} ({n})"


def _fuzzy_union(buckets: dict[str, list[PoiCandidate]]) -> _UnionFind:
    """Conservative rapidfuzz near-dup pass over the exact-norm buckets: union a
    pair ONLY when ``token_sort_ratio >= 94`` AND the two representative points
    are within 75 m. Bucket order is fixed (dict insertion) for determinism."""
    keys = list(buckets)
    names = {k: _display_name(buckets[k]) for k in keys}
    coords = {k: _merged_coords(buckets[k]) for k in keys}
    uf = _UnionFind(keys)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            if fuzz.token_sort_ratio(names[a], names[b]) < _FUZZ_MIN_RATIO:
                continue
            (la, oa), (lb, ob) = coords[a], coords[b]
            if la is None or lb is None:
                continue
            if _haversine_m(la, oa, lb, ob) <= _FUZZ_MAX_METERS:
                uf.union(a, b)
    return uf


def _variations(group: list[PoiCandidate], canonical: str) -> list[str]:
    """Distinct display strings in a merged group (by ``_norm``) other than the
    canonical name — includes each candidate's own ``name_variations``."""
    seen = {_norm(canonical)}
    out: list[str] = []
    for cand in group:
        for name in (cand.name, *cand.name_variations):
            key = _norm(name)
            if key and key not in seen:
                seen.add(key)
                out.append(name)
    return out


def _sweep_collisions(pois: list[dict]) -> None:
    """POST-MERGE COLLISION SWEEP (in place): drop any ``name_variation`` whose
    ``_norm`` collides with ANOTHER POI's name or an already-claimed key, so
    ``test_data_integrity`` :92 (accent/case dup) and :151 (variation collision)
    stay green. Canonical names are collision-free by construction (one per
    surviving ``_norm`` bucket); only variations can collide."""
    reverse: dict[str, str] = {}
    # Claim every canonical name first — canonical names always win a collision.
    for poi in pois:
        reverse[_norm(poi["name"])] = poi["name"]
    for poi in pois:
        own = _norm(poi["name"])
        kept: list[str] = []
        for var in poi["name_variations"]:
            key = _norm(var)
            if not key or key == own:
                continue  # empty, or a restatement of the POI's own name
            owner = reverse.get(key)
            if owner is not None and owner != poi["name"]:
                continue  # collides with another POI's name/variation — drop it
            reverse[key] = poi["name"]
            kept.append(var)
        poi["name_variations"] = kept


def _assign_tiers(pois: list[dict]) -> None:
    """FORCED GRAVITY DISTRIBUTION (in place): deterministic rank-quantile.

    Rank by ``(-agreement, -(wikidata+wikipedia bonus), _norm(name))`` then slice
    at boundaries [10, 25, 50, 75]% into tiers 5/4/3/2/1. This emits exactly the
    SHAPE ``test_gravity_distribution`` demands (T5 ≈ 10%, T3 ≈ 25%, bottom-heavy),
    independent of the raw agreement values, and stamps every POI's audit block.
    """
    n = len(pois)

    def _rank_key(poi: dict) -> tuple[int, int, str]:
        audit = poi["_pipeline"]["gravity_audit"]
        srcs = set(audit["sources"])
        bonus = int("wikidata" in srcs) + int("wikipedia" in srcs)
        return (-audit["cross_source_agreement"], -bonus, _norm(poi["name"]))

    ranked = sorted(pois, key=_rank_key)
    b = [int(0.10 * n), int(0.25 * n), int(0.50 * n), int(0.75 * n)]
    scored_at = date.today().isoformat()
    for idx, poi in enumerate(ranked):
        if idx < b[0]:
            tier = 5
        elif idx < b[1]:
            tier = 4
        elif idx < b[2]:
            tier = 3
        elif idx < b[3]:
            tier = 2
        else:
            tier = 1
        poi["importance_tier"] = tier
        audit = poi["_pipeline"]["gravity_audit"]
        audit["assigned_gravity"] = tier
        audit["rank"] = idx
        audit["of"] = n
        audit["scored_at"] = scored_at


def assemble(
    results: list[ConnectorResult],
    ctx: CityContext,
    extracts: list[WikiExtract],
    *,
    cloud_deployed: bool = False,
) -> AssembledCity:
    """Merge cross-source candidates into geofenced, gravity-tiered POI dicts.

    PURE — no network, no disk, no registry. Reads ONLY ``result.candidates``;
    ``result.pointers`` / ``result.documents`` are never consulted (wall 3).
    """
    min_lat, max_lat, min_lon, max_lon = ctx.bbox

    # 1. MERGE/DEDUP: exact-norm buckets, GEO-SPLIT each bucket into same-place
    # clusters (distinct places sharing a name stay separate), then a conservative
    # fuzzy near-dup union-find over the clusters.
    buckets = _bucket_candidates(results)
    clusters: dict[str, list[PoiCandidate]] = {}
    for bkey, bcands in buckets.items():
        for i, cluster in enumerate(_geo_split_bucket(bcands)):
            clusters[f"{bkey}\x00{i}"] = cluster
    uf = _fuzzy_union(clusters)
    groups: dict[str, list[PoiCandidate]] = {}
    for key, cands in clusters.items():
        groups.setdefault(uf.find(key), []).extend(cands)

    # 2. COORDS + 3. BBOX drop (never clip).
    pois: list[dict] = []
    dropped_no_coords = 0
    dropped_out_of_bbox = 0
    for group in groups.values():
        canonical = _display_name(group)
        lat, lon = _merged_coords(group)
        if lat is None or lon is None:
            dropped_no_coords += 1
            continue
        if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
            dropped_out_of_bbox += 1
            continue
        sources = sorted({c.source for c in group})
        source_urls = sorted({c.source_url for c in group if c.source_url})
        pois.append(
            {
                "name": canonical,
                "short_description": _short_description(group),
                "name_variations": _variations(group, canonical),
                "latitude": lat,
                "longitude": lon,
                "city_name": ctx.slug,
                "trigger_radius": 30,
                "kid_friendly": "yes",
                "poi_role": "stop",
                "importance_tier": None,  # stamped by _assign_tiers
                "_pipeline": {
                    "discovery_sources": sources,
                    "source_urls": source_urls,
                    "gravity_audit": {
                        "signal_source": "onboard_auto_v1",
                        "assigned_gravity": None,  # stamped below
                        "cross_source_agreement": len(sources),
                        "sources": sources,
                        "rank": None,  # stamped below
                        "of": None,  # stamped below
                        "method": "rank_quantile_forced_distribution",
                        "scored_at": None,  # stamped below
                    },
                },
            }
        )

    if dropped_out_of_bbox or dropped_no_coords:
        logger.info(
            "assemble(%s): dropped %d POI(s) outside bbox %s, %d with no coordinates",
            ctx.slug,
            dropped_out_of_bbox,
            ctx.bbox,
            dropped_no_coords,
        )

    # 1 (cont.) DISAMBIGUATE distinct places that share a name (geo-split), then
    # POST-MERGE COLLISION SWEEP over the surviving set.
    _disambiguate_same_name(pois, ctx)
    _sweep_collisions(pois)

    # 4. FORCED GRAVITY DISTRIBUTION.
    _assign_tiers(pois)

    # 5. wiki_extracts keyed by slug.
    wiki_extracts = {slugify(e.poi_name): e for e in extracts}

    return AssembledCity(
        slug=ctx.slug,
        pois=pois,
        wiki_extracts=wiki_extracts,
        cloud_deployed=cloud_deployed,
    )


# ---------------------------------------------------------------------------
# write_city — the ONLY disk / registry touch.
# ---------------------------------------------------------------------------
def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (tmp sibling + ``os.replace``)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _book_log(city: AssembledCity, ctx: CityContext) -> dict:
    """A ``scripts/wiki_fetch.py``-format book-log: one 'Wikipedia' book whose
    ``chunks_processed`` name each pinned ``{poi_slug}-rev-{revid}`` file (the
    slug ``wiki_fetch.scan_log`` scans for)."""
    processed_at = date.today().isoformat()
    chunks = [
        {
            "chunk": f"{poi_slug}-rev-{ext.revid}",
            "processed_at": processed_at,
            "beats_extracted": 0,
            "pois_touched": [ext.poi_name],
        }
        for poi_slug, ext in city.wiki_extracts.items()
    ]
    return {
        "city": ctx.display_name,
        "books_processed": [
            {
                "book_title": "Wikipedia",
                "author": "Wikipedia contributors",
                "source": "wikipedia",
                "chunks_processed": chunks,
            }
        ],
    }


def _register(city: AssembledCity, ctx: CityContext, registry_path: Path | None) -> None:
    """Register the city. When ``registry_path`` is the default (or None) this
    writes the real ``src/cities.json``; otherwise it redirects the module global
    to ``registry_path`` under try/finally so the global is NEVER leaked to
    sibling tests (the target is seeded from the current registry first)."""
    entry = {
        "display_name": ctx.display_name,
        "bbox": list(ctx.bbox),
        "cloud_deployed": city.cloud_deployed,
    }
    default = city_registry._REGISTRY_PATH
    if registry_path is None or registry_path == default:
        city_registry.register_city(city.slug, entry)
        return

    original = city_registry._REGISTRY_PATH
    try:
        # Seed the redirected registry from the CURRENT (real) registry contents
        # so register_city merges into a full copy, not an empty file.
        current = dict(city_registry.load_registry())
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        city_registry._REGISTRY_PATH = registry_path
        city_registry.load_registry.cache_clear()
        city_registry.register_city(city.slug, entry)
    finally:
        city_registry._REGISTRY_PATH = original
        city_registry.load_registry.cache_clear()


def write_city(
    city: AssembledCity,
    ctx: CityContext,
    *,
    data_root: Path | None = None,
    registry_path: Path | None = None,
) -> Path:
    """Atomically write the ``data/{slug}/`` corpus and register the city.

    Writes EXACTLY: ``poi-raw.json``, ``areas.json`` (``[]``), ``within_edges.json``
    (well-formed empty), ``book-log.json``, and one verbatim
    ``wikipedia/{poi_slug}-rev-{revid}.txt`` per ``WikiExtract`` — nothing else.
    Refuses to write a thin city (< 30 POIs). Returns the city directory.
    """
    if len(city.pois) < MIN_POIS:
        raise ValueError(
            f"refusing to write a thin city {city.slug!r}: only {len(city.pois)} POI(s), "
            f"need at least {MIN_POIS}"
        )

    root = (
        data_root
        or (Path(os.environ["ONBOARD_DATA_ROOT"]) if os.getenv("ONBOARD_DATA_ROOT") else None)
        or REPO_ROOT / "data"
    )
    city_dir = root / city.slug
    wiki_dir = city_dir / "wikipedia"
    wiki_dir.mkdir(parents=True, exist_ok=True)

    _atomic_write_text(
        city_dir / "poi-raw.json",
        json.dumps(city.pois, indent=2, ensure_ascii=False) + "\n",
    )
    _atomic_write_text(city_dir / "areas.json", json.dumps([], indent=2) + "\n")
    _atomic_write_text(
        city_dir / "within_edges.json",
        json.dumps(
            {
                "_meta": {
                    "generated_by": "src/onboard/assemble.py",
                    "city_name": city.slug,
                    "total_pois": len(city.pois),
                    "total_areas": 0,
                    "poi_to_area_count": 0,
                    "area_to_area_count": 0,
                    "orphans": [],
                },
                "poi_to_area": [],
                "area_to_area": [],
            },
            indent=2,
        )
        + "\n",
    )
    _atomic_write_text(
        city_dir / "book-log.json",
        json.dumps(_book_log(city, ctx), indent=2, ensure_ascii=False) + "\n",
    )
    for poi_slug, ext in city.wiki_extracts.items():
        _atomic_write_text(wiki_dir / f"{poi_slug}-rev-{ext.revid}.txt", ext.text)

    _register(city, ctx, registry_path)
    return city_dir
