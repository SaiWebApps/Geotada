"""Static regression tests for the data integrity bugs found in the
2026-04-08 audit. Runs against poi-raw.json and beats.json only — no DB.

Catches:
  - B1: Accent-duplicate POIs (e.g. 'Café de Flore' + 'Cafe de Flore')
  - B6: Ghost beat stubs (missing beat_id or script_body)
  - Beat→POI orphans in source files
  - POI name / name_variations collisions
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn"
    )


def _norm(s: str) -> str:
    return _strip_accents(s).lower().strip()


def _city_dirs() -> list[Path]:
    if not DATA_ROOT.exists():
        return []
    return [d for d in sorted(DATA_ROOT.iterdir()) if d.is_dir() and (d / "poi-raw.json").exists()]


@pytest.mark.parametrize("city_dir", _city_dirs(), ids=lambda d: d.name)
def test_every_data_city_is_fully_registered(city_dir: Path) -> None:
    """Onboarding fail-fast: any city with data/ must ALSO be registered in every
    surface the engine reads, or it silently misbehaves — upload rejects POIs
    outside CITY_BBOX, and the API 422s a city absent from SUPPORTED_CITIES. This
    catches a half-onboarded city at CI time instead of at deploy/request time, so
    the tour algorithm truly generalizes to 'any and all cities' we add."""
    from scripts.upload_paris import CITY_BBOX
    from src.tour.contract import SUPPORTED_CITIES

    city = city_dir.name
    problems: list[str] = []
    if city not in CITY_BBOX:
        problems.append("missing from CITY_BBOX (upload_paris.py) — every POI skipped on upload")
    if city not in SUPPORTED_CITIES:
        problems.append("missing from SUPPORTED_CITIES (contract.py) — the API 422s every request")
    if not (city_dir / "beats.json").exists():
        problems.append("has poi-raw.json but no beats.json — POIs would seat with zero narration")
    assert not problems, f"city '{city}' is not fully onboarded:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("city_dir", _city_dirs(), ids=lambda d: d.name)
def test_no_accent_or_case_duplicate_pois(city_dir: Path) -> None:
    """No two POIs should collide after accent stripping + case folding.
    Would have caught the 'Café de Flore' vs 'Cafe de Flore' duplicate bug."""
    pois = json.loads((city_dir / "poi-raw.json").read_text())
    seen: dict[str, str] = {}
    dupes: list[str] = []
    for p in pois:
        key = _norm(p["name"])
        if key in seen:
            dupes.append(f"'{seen[key]}' ↔ '{p['name']}'")
        else:
            seen[key] = p["name"]
    if dupes:
        pytest.fail(
            f"{city_dir.name}: {len(dupes)} POI pair(s) collide after "
            f"Unicode/case normalization:\n  " + "\n  ".join(dupes)
        )


@pytest.mark.parametrize("city_dir", _city_dirs(), ids=lambda d: d.name)
def test_no_ghost_beat_stubs(city_dir: Path) -> None:
    """Every beat in beats.json must have a beat_id and non-empty script_body.
    Would have caught the 19 metadata-only stubs in the 2026-04-08 audit."""
    beats = json.loads((city_dir / "beats.json").read_text())
    missing_id = [i for i, b in enumerate(beats) if not b.get("beat_id")]
    missing_body = [i for i, b in enumerate(beats) if not (b.get("script_body") or "").strip()]
    problems = []
    if missing_id:
        problems.append(f"{len(missing_id)} beat(s) missing beat_id")
    if missing_body:
        problems.append(f"{len(missing_body)} beat(s) with empty script_body")
    if problems:
        pytest.fail(f"{city_dir.name}: " + "; ".join(problems))


@pytest.mark.parametrize("city_dir", _city_dirs(), ids=lambda d: d.name)
def test_every_beat_references_known_poi(city_dir: Path) -> None:
    """Every beat.poi_name must match a POI in poi-raw.json (case-insensitive).
    Catches orphan beats in the source files before they reach the DB."""
    pois = json.loads((city_dir / "poi-raw.json").read_text())
    beats = json.loads((city_dir / "beats.json").read_text())
    poi_keys = {_norm(p["name"]) for p in pois}
    # Also include name_variations
    for p in pois:
        for v in p.get("name_variations", []) or []:
            poi_keys.add(_norm(v))
    orphans: list[str] = []
    for b in beats:
        pn = b.get("poi_name")
        if pn and _norm(pn) not in poi_keys:
            orphans.append(f"'{pn}' (beat {b.get('beat_id', '?')})")
    if orphans:
        pytest.fail(
            f"{city_dir.name}: {len(orphans)} beat(s) reference unknown POIs:\n  "
            + "\n  ".join(orphans[:20])
        )


@pytest.mark.parametrize("city_dir", _city_dirs(), ids=lambda d: d.name)
def test_no_poi_name_variation_collisions(city_dir: Path) -> None:
    """A POI's name_variations must not collide with another POI's name or
    variations. Prevents confusion during POI matching in upload/upsert."""
    pois = json.loads((city_dir / "poi-raw.json").read_text())
    reverse_index: dict[str, str] = {}  # norm → canonical poi name
    collisions: list[str] = []
    for p in pois:
        keys = {_norm(p["name"])}
        for v in p.get("name_variations", []) or []:
            keys.add(_norm(v))
        for k in keys:
            if not k:
                continue
            owner = reverse_index.get(k)
            if owner and owner != p["name"]:
                collisions.append(f"'{k}' owned by both '{owner}' and '{p['name']}'")
            reverse_index[k] = p["name"]
    if collisions:
        pytest.fail(
            f"{city_dir.name}: {len(collisions)} name/variation collision(s):\n  "
            + "\n  ".join(collisions[:20])
        )
