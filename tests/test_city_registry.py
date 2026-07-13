"""Behavior + regression tests for the data-driven city registry.

The registry (``src/city_registry.py`` + ``src/cities.json``) replaced three
hardcoded literals. These tests:
  - pin paris/new_york bbox VALUES byte-equal to the old literals (the refactor's
    regression anchor);
  - exercise the prod cloud-filter (``servable_cities`` in local vs prod mode);
  - round-trip ``register_city`` + ``mark_cloud_deployed`` against a TMP copy of
    cities.json so the committed ``src/cities.json`` is never mutated.

Pure (no Neo4j) → run with ``make test-file FILE=tests/test_city_registry.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src import city_registry


@pytest.fixture(autouse=True)
def _clean_registry_cache():
    """Keep the lru_cache clean around every test so a test that monkeypatches the
    loader or the registry path can never leak cached state into another."""
    clear = getattr(city_registry.load_registry, "cache_clear", None)
    if clear:
        clear()
    yield
    clear = getattr(city_registry.load_registry, "cache_clear", None)
    if clear:
        clear()


def test_bbox_map_byte_equal_to_old_literals() -> None:
    """The refactor MUST preserve the exact bbox tuples the CITY_BBOX literal held."""
    bm = city_registry.bbox_map()
    assert bm["paris"] == (48.70, 49.00, 2.10, 2.60)
    assert bm["new_york"] == (40.45, 40.93, -74.28, -73.68)


def test_supported_cities_today() -> None:
    """Equals the former frozenset({'paris', 'new_york'}) literal exactly."""
    assert city_registry.supported_cities() == frozenset({"paris", "new_york"})


def _fake_registry() -> dict[str, dict]:
    return {
        "paris": {
            "display_name": "Paris",
            "bbox": [48.70, 49.00, 2.10, 2.60],
            "cloud_deployed": True,
        },
        "testburg": {
            "display_name": "Testburg",
            "bbox": [0.0, 1.0, 0.0, 1.0],
            "cloud_deployed": False,
        },
    }


def test_servable_cities_local_includes_non_cloud_deployed(monkeypatch) -> None:
    """LOCAL mode (WORKBENCH_API_ENABLED unset/true): every registered city is
    servable, including a not-yet-cloud-deployed one."""
    monkeypatch.setattr(city_registry, "load_registry", _fake_registry)
    monkeypatch.delenv("WORKBENCH_API_ENABLED", raising=False)
    assert city_registry.servable_cities() == frozenset({"paris", "testburg"})
    # Explicit truthy values stay local too.
    for local_value in ("true", "1", "on", "yes", "anything-else"):
        monkeypatch.setenv("WORKBENCH_API_ENABLED", local_value)
        assert city_registry.servable_cities() == frozenset({"paris", "testburg"}), local_value


def test_servable_cities_prod_excludes_non_cloud_deployed(monkeypatch) -> None:
    """PROD mode (WORKBENCH_API_ENABLED falsey): a non-cloud_deployed city is
    excluded from what the public /trips API may serve — mirrors the same falsey
    parsing as src/api/app.py:_workbench_api_enabled."""
    monkeypatch.setattr(city_registry, "load_registry", _fake_registry)
    for prod_value in ("false", "0", "no", "off", "FALSE", "Off", "  no  "):
        monkeypatch.setenv("WORKBENCH_API_ENABLED", prod_value)
        assert city_registry.servable_cities() == frozenset({"paris"}), prod_value


def test_register_and_mark_round_trip(tmp_path, monkeypatch) -> None:
    """register_city + mark_cloud_deployed round-trip against a TMP cities.json,
    proving atomic write, sorted-key stable diff, and lru_cache invalidation —
    without ever touching the committed src/cities.json."""
    real = Path(city_registry.__file__).resolve().parent / "cities.json"
    tmp_registry = tmp_path / "cities.json"
    tmp_registry.write_text(real.read_text())
    monkeypatch.setattr(city_registry, "_REGISTRY_PATH", tmp_registry)
    city_registry.load_registry.cache_clear()

    entry = {"display_name": "London", "bbox": [51.28, 51.70, -0.52, 0.33], "cloud_deployed": False}
    city_registry.register_city("london", entry)

    # Cache was invalidated: a fresh load sees london.
    reg = city_registry.load_registry()
    assert reg["london"] == entry
    assert city_registry.bbox_map()["london"] == (51.28, 51.70, -0.52, 0.33)

    # The file on disk actually changed, and top-level keys are sorted (stable diff).
    on_disk = json.loads(tmp_registry.read_text())
    assert "london" in on_disk
    assert list(on_disk.keys()) == sorted(on_disk.keys())

    # london starts local-only → excluded from prod servable set.
    monkeypatch.setenv("WORKBENCH_API_ENABLED", "false")
    assert "london" not in city_registry.servable_cities()
    assert "london" in city_registry.supported_cities()

    # mark_cloud_deployed flips the flag AND invalidates the cache.
    city_registry.mark_cloud_deployed("london")
    assert city_registry.load_registry()["london"]["cloud_deployed"] is True
    assert "london" in city_registry.servable_cities()


def test_register_city_validates_entry(tmp_path, monkeypatch) -> None:
    """A malformed entry (missing/short bbox, missing required keys) is refused
    before it can be written."""
    real = Path(city_registry.__file__).resolve().parent / "cities.json"
    tmp_registry = tmp_path / "cities.json"
    tmp_registry.write_text(real.read_text())
    monkeypatch.setattr(city_registry, "_REGISTRY_PATH", tmp_registry)
    city_registry.load_registry.cache_clear()

    with pytest.raises(ValueError):  # no bbox
        city_registry.register_city("bad", {"display_name": "Bad", "cloud_deployed": True})
    with pytest.raises(ValueError):  # bbox wrong length
        city_registry.register_city(
            "bad", {"display_name": "Bad", "bbox": [1, 2, 3], "cloud_deployed": True}
        )
    with pytest.raises(ValueError):  # missing cloud_deployed
        city_registry.register_city("bad", {"display_name": "Bad", "bbox": [1, 2, 3, 4]})

    # None of the rejected writes reached disk.
    assert "bad" not in json.loads(tmp_registry.read_text())


def test_stringly_typed_cloud_deployed_is_rejected_and_never_served(monkeypatch) -> None:
    """The prod cloud-filter's core safety property: a truthy NON-bool
    ``cloud_deployed`` (e.g. the JSON/form string ``"false"``) must NOT leak a
    local-only city into prod. Two independent walls:
      1. ``_validate_entry`` REFUSES a non-bool value at write time.
      2. ``servable_cities()`` uses ``is True`` (not truthiness), so even a
         hand-edited cities.json carrying ``"false"`` is excluded in prod."""
    # Wall 1 — write-time rejection.
    with pytest.raises(ValueError, match="cloud_deployed"):
        city_registry._validate_entry(
            {"display_name": "Bad", "bbox": [51.0, 52.0, -1.0, 1.0], "cloud_deployed": "false"}
        )
    with pytest.raises(ValueError, match="cloud_deployed"):
        city_registry._validate_entry(
            {"display_name": "Bad", "bbox": [51.0, 52.0, -1.0, 1.0], "cloud_deployed": 1}
        )
    # Wall 2 — serve-time defense against a bad value that bypassed wall 1.
    bad = {
        "paris": {"display_name": "Paris", "bbox": [48.7, 49.0, 2.1, 2.6], "cloud_deployed": True},
        "sneaky": {
            "display_name": "Sneaky",
            "bbox": [0.0, 1.0, 0.0, 1.0],
            "cloud_deployed": "false",
        },
    }
    monkeypatch.setattr(city_registry, "load_registry", lambda: bad)
    monkeypatch.setenv("WORKBENCH_API_ENABLED", "false")  # prod
    assert city_registry.servable_cities() == frozenset({"paris"})


def test_validate_entry_rejects_non_numeric_bbox() -> None:
    with pytest.raises(ValueError, match="bbox"):
        city_registry._validate_entry(
            {"display_name": "Bad", "bbox": ["a", "b", "c", "d"], "cloud_deployed": True}
        )
    # A bool is not a valid coordinate (isinstance(True, int) is True in Python).
    with pytest.raises(ValueError, match="bbox"):
        city_registry._validate_entry(
            {"display_name": "Bad", "bbox": [True, 1.0, 2.0, 3.0], "cloud_deployed": True}
        )


def test_register_city_normalizes_and_validates_slug(tmp_path, monkeypatch) -> None:
    """A slug is canonicalized (trim + lowercase) so a stray-cased key can't become
    silently un-servable; a slug with illegal chars is refused outright."""
    real = Path(city_registry.__file__).resolve().parent / "cities.json"
    tmp_registry = tmp_path / "cities.json"
    tmp_registry.write_text(real.read_text())
    monkeypatch.setattr(city_registry, "_REGISTRY_PATH", tmp_registry)
    city_registry.load_registry.cache_clear()

    entry = {"display_name": "London", "bbox": [51.28, 51.70, -0.52, 0.33], "cloud_deployed": False}
    returned = city_registry.register_city("  London ", entry)
    assert returned == "london"
    assert "london" in city_registry.load_registry()
    assert "  London " not in city_registry.load_registry()

    for bad_slug in ("New York", "sao-paulo", "123city", "", "Città"):
        with pytest.raises(ValueError, match="invalid city slug"):
            city_registry.register_city(bad_slug, entry)


def test_mark_unknown_city_raises(tmp_path, monkeypatch) -> None:
    real = Path(city_registry.__file__).resolve().parent / "cities.json"
    tmp_registry = tmp_path / "cities.json"
    tmp_registry.write_text(real.read_text())
    monkeypatch.setattr(city_registry, "_REGISTRY_PATH", tmp_registry)
    city_registry.load_registry.cache_clear()

    with pytest.raises(KeyError):
        city_registry.mark_cloud_deployed("nowhere")
