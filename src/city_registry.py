"""Data-driven city registry — the single writable surface for city registration.

Historically a city was registered by editing hardcoded Python literals
(``CITY_BBOX`` in ``scripts/upload_paris.py``, ``SUPPORTED_CITIES`` in
``src/tour/contract.py``) plus dropping a ``data/{slug}/`` corpus. The new-city
onboarding panel registers a city at RUNTIME, so those literals now derive from
this module, which is backed by the writable ``src/cities.json``.

Why ``src/cities.json`` (not ``data/``): the production Dockerfile ships ``src/``
and ``frontend/`` only — never ``data/`` — so the registry file must live under
``src/`` to be importable in prod.

Prod cloud-filter: a city can be onboarded + uploaded LOCALLY (visible to the
local workbench) before it is deployed to Aura. Such a city must NOT be servable
by the public prod ``/trips`` API. ``servable_cities()`` enforces this — it
returns every registered slug in local/workbench mode, but only ``cloud_deployed``
slugs when the workbench is disabled (the prod signal
``WORKBENCH_API_ENABLED=false``). ``supported_cities()`` stays "all registered"
so the onboarding data-integrity guard and the local workbench keep seeing every
registered city.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

# A registry slug is the canonical city key: it also names the ``data/{slug}/``
# corpus dir and is what ``_validate_city_slug`` normalizes a request to, so a key
# with stray case/whitespace/punctuation would be un-servable and silently wrong.
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Registry file lives next to this module (ships in the prod image under src/).
_REGISTRY_PATH = Path(__file__).resolve().parent / "cities.json"


@lru_cache(maxsize=1)
def load_registry() -> dict[str, dict]:
    """Read + parse ``src/cities.json`` (cached).

    The cache is invalidated by ``register_city`` / ``mark_cloud_deployed`` via
    ``load_registry.cache_clear()``; anything that writes the file directly must
    clear it too.
    """
    with open(_REGISTRY_PATH) as f:
        return json.load(f)


def bbox_map() -> dict[str, tuple[float, float, float, float]]:
    """``{slug: (min_lat, max_lat, min_lon, max_lon)}`` — replaces the old
    ``CITY_BBOX`` literal. bbox order matches ``scripts/upload_paris.py``."""
    return {slug: tuple(entry["bbox"]) for slug, entry in load_registry().items()}


def supported_cities() -> frozenset[str]:
    """ALL registered slugs. Backs ``SUPPORTED_CITIES`` + the onboarding
    data-integrity guard; the local workbench serves every registered city."""
    return frozenset(load_registry())


def _prod_cloud_filter_active() -> bool:
    """True when the public prod cloud-filter should apply — i.e. the workbench is
    DISABLED. Mirrors ``src/api/app.py:_workbench_api_enabled`` falsey parsing
    exactly, so ``false``/``0``/``no``/``off`` (any case) all count as prod."""
    return os.getenv("WORKBENCH_API_ENABLED", "true").strip().lower() in (
        "false",
        "0",
        "no",
        "off",
    )


def servable_cities() -> frozenset[str]:
    """Slugs the API may serve for a /trips request.

    ALL registered slugs normally; ONLY ``cloud_deployed`` slugs when the
    workbench is disabled (prod), so a locally-onboarded but not-yet-deployed city
    is never served by the public prod /trips API.
    """
    registry = load_registry()
    if _prod_cloud_filter_active():
        # `is True` (not truthiness): a stringly-typed ``"cloud_deployed": "false"``
        # is truthy in Python and would otherwise leak a local-only city into prod.
        # ``_validate_entry`` also rejects non-bool values at write time (belt +
        # suspenders — a hand-edited cities.json can still carry a bad value).
        return frozenset(
            slug for slug, entry in registry.items() if entry.get("cloud_deployed") is True
        )
    return frozenset(registry)


def _validate_entry(entry: dict) -> None:
    """A registry entry must carry a display_name, a numeric 4-element bbox, and a
    BOOLEAN cloud_deployed flag — refuse a half-formed entry before it is written
    (a silently-missing or wrong-typed field would surface far downstream).

    The ``cloud_deployed`` type-check is a safety property, not a nicety: an
    untrusted caller (the Step-5 onboarding API / CLI) that hands a stringly-typed
    ``"false"`` through JSON/form deserialization would, absent this check, write a
    truthy value that ``servable_cities()`` serves in prod — leaking a local-only
    city into the public API, the exact failure this registry exists to prevent."""
    if "display_name" not in entry:
        raise ValueError("city entry is missing 'display_name'")
    bbox = entry.get("bbox")
    if not isinstance(bbox, list | tuple) or len(bbox) != 4:
        raise ValueError(
            "city entry 'bbox' must be a 4-element [min_lat, max_lat, min_lon, max_lon]"
        )
    if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in bbox):
        raise ValueError("city entry 'bbox' values must all be numbers")
    if "cloud_deployed" not in entry:
        raise ValueError("city entry is missing 'cloud_deployed'")
    if not isinstance(entry["cloud_deployed"], bool):
        raise ValueError(
            "city entry 'cloud_deployed' must be a JSON boolean (true/false), "
            f"got {entry['cloud_deployed']!r}"
        )


def _atomic_write(registry: dict[str, dict]) -> None:
    """Write ``cities.json`` atomically (temp file in the same dir + ``os.replace``),
    keys sorted for a stable diff, then invalidate the loader cache."""
    tmp = _REGISTRY_PATH.with_name(_REGISTRY_PATH.name + ".tmp")
    tmp.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, _REGISTRY_PATH)
    load_registry.cache_clear()


def _normalize_slug(slug: str) -> str:
    """Canonicalize + validate a slug (lowercased, trimmed). Raises on anything
    that isn't ``[a-z][a-z0-9_]*`` so a mis-typed key can never be silently
    un-servable (``_validate_city_slug`` normalizes the same way)."""
    norm = (slug or "").strip().lower()
    if not _SLUG_RE.match(norm):
        raise ValueError(
            f"invalid city slug {slug!r}: must match {_SLUG_RE.pattern} "
            "(lowercase letters/digits/underscore, letter-initial)"
        )
    return norm


def register_city(slug: str, entry: dict) -> str:
    """Atomically add/update a city in ``cities.json`` and clear the cache.

    ``slug`` is normalized to the canonical ``[a-z][a-z0-9_]*`` form (the returned
    value); ``entry`` must have ``display_name``, a numeric 4-element ``bbox``, and
    a boolean ``cloud_deployed`` (a new city typically registers with
    ``cloud_deployed: false`` until it is deployed to Aura).
    """
    norm = _normalize_slug(slug)
    _validate_entry(entry)
    registry = dict(load_registry())
    registry[norm] = dict(entry)
    _atomic_write(registry)
    return norm


def mark_cloud_deployed(slug: str) -> None:
    """Set ``cloud_deployed=true`` for an existing slug (atomic write + cache clear)."""
    registry = dict(load_registry())
    if slug not in registry:
        raise KeyError(f"cannot mark unknown city {slug!r} cloud-deployed; register it first")
    entry = dict(registry[slug])
    entry["cloud_deployed"] = True
    registry[slug] = entry
    _atomic_write(registry)
