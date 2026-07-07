"""Multi-city Area-convention guard (DB-free).

scripts/upload_areas.py resolves POI->Area WITHIN edges by matching each Area's
``city_name`` against the POIs' ``city_name`` — and POIs are loaded under their
directory slug (``data/{slug}/`` -> ``city_name = slug``). So every Area's
``city_name`` MUST equal its directory slug, or the POI->Area edges silently
fail to resolve and the hierarchy loads ORPHANED (no containment -> the tour
engine gets no ``spine_area`` and no area-alignment scoring).

This guards the exact casing landmine that left Paris Areas keyed ``'Paris'``
while its POIs (and the ``paris`` slug) were lowercase — which made the Aura
area load resolve zero POIs until it was standardized (2026-07-06).

Runs in <20ms with no DB.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"


def _slugs_with_areas() -> list[str]:
    if not DATA_ROOT.exists():
        return []
    return [
        d.name
        for d in sorted(DATA_ROOT.iterdir())
        if d.is_dir() and (d / "areas.json").exists()
    ]


@pytest.mark.parametrize("slug", _slugs_with_areas())
def test_area_city_name_matches_directory_slug(slug: str) -> None:
    """Every Area's city_name must equal its city directory slug, or the
    POI->Area edge resolution in upload_areas silently drops every edge."""
    areas = json.loads((DATA_ROOT / slug / "areas.json").read_text())
    offenders = sorted({a.get("city_name") for a in areas if a.get("city_name") != slug})
    assert not offenders, (
        f"data/{slug}/areas.json has Area city_name(s) {offenders} != directory slug "
        f"'{slug}'. upload_areas matches Area.city_name to POI.city_name (='{slug}'); "
        f"a mismatch orphans every POI->Area WITHIN edge and the engine loses spine_area."
    )
