"""New York second-city corpus guards (DB-free).

New York is the second city loaded into the graph (slug ``new_york``). Because
POIs MERGE on ``{name_key, city_name}`` and NarrativeBeats MERGE on ``beat_id``
alone, a NY corpus that (a) leaks POIs outside the NY geofence or (b) reuses a
Paris ``beat_id`` would silently corrupt the shared multi-city graph on upload.
These guards catch both before ``make deploy CITY=new_york`` ever runs.

Runs in <20ms with no DB.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.upload_paris import CITY_BBOX, _in_city_bounds

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
NY_DIR = DATA_ROOT / "new_york"


def _load(path: Path) -> list[dict]:
    return json.loads(path.read_text())


@pytest.mark.skipif(not (NY_DIR / "poi-raw.json").exists(), reason="new_york corpus absent")
def test_new_york_registered_in_city_bbox() -> None:
    """The uploader must know new_york's geofence, or every POI is skipped."""
    assert "new_york" in CITY_BBOX, "new_york missing from CITY_BBOX in upload_paris.py"


@pytest.mark.skipif(not (NY_DIR / "poi-raw.json").exists(), reason="new_york corpus absent")
def test_all_new_york_pois_fall_within_the_nyc_geofence() -> None:
    """Every NY POI with coordinates must sit inside CITY_BBOX['new_york'].

    A POI outside the bbox is silently dropped by the uploader (the Boston-POI /
    (0,0) / stray-coord class), so an out-of-bounds POI here is a data defect
    that would vanish from the tour without warning.
    """
    bbox = CITY_BBOX["new_york"]
    pois = _load(NY_DIR / "poi-raw.json")
    out_of_bounds: list[str] = []
    for poi in pois:
        lat, lon = poi.get("latitude"), poi.get("longitude")
        if lat is None or lon is None:
            continue  # null-coord POIs are a separate (geocode) concern
        if not _in_city_bounds(float(lat), float(lon), bbox):
            out_of_bounds.append(f"{poi.get('name')!r} @ ({lat}, {lon})")
    assert not out_of_bounds, (
        f"{len(out_of_bounds)} new_york POI(s) fall outside CITY_BBOX['new_york']={bbox} "
        f"and would be silently skipped on upload:\n  " + "\n  ".join(out_of_bounds[:20])
    )


@pytest.mark.skipif(not (NY_DIR / "beats.json").exists(), reason="new_york corpus absent")
def test_new_york_beat_ids_are_non_empty_and_unique() -> None:
    """Every NY beat needs a unique beat_id: the uploader refuses an empty
    beat_id (it would collapse distinct beats onto one node), and a duplicate
    within the file MERGEs two source beats into one."""
    beats = _load(NY_DIR / "beats.json")
    ids = [b.get("beat_id", "") for b in beats]
    assert all(ids), "some new_york beats have an empty beat_id"
    dupes = {i for i in ids if ids.count(i) > 1}
    assert not dupes, f"duplicate new_york beat_id(s): {sorted(dupes)[:10]}"


@pytest.mark.skipif(
    not ((NY_DIR / "beats.json").exists() and (DATA_ROOT / "paris" / "beats.json").exists()),
    reason="both city corpora required",
)
def test_new_york_beat_ids_do_not_collide_with_paris() -> None:
    """Multi-city MERGE safety: NarrativeBeat MERGEs on ``beat_id`` alone, so a
    beat_id shared between Paris and New York would overwrite one city's beat
    with the other's on upload. City-prefixed ids keep the namespaces disjoint."""
    ny_ids = {b["beat_id"] for b in _load(NY_DIR / "beats.json") if b.get("beat_id")}
    paris_beats = _load(DATA_ROOT / "paris" / "beats.json")
    paris_ids = {b["beat_id"] for b in paris_beats if b.get("beat_id")}
    collisions = ny_ids & paris_ids
    assert not collisions, (
        f"{len(collisions)} beat_id(s) shared between new_york and paris would corrupt "
        f"the shared graph on upload:\n  " + "\n  ".join(sorted(collisions)[:10])
    )
