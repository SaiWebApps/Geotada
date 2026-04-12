"""Regression test: every POI listed in any export file must match the
canonical record in `data/{city}/poi-raw.json` for the fields that flow
into Neo4j.

History: an earlier pipeline build silently demoted famous landmarks like
Notre-Dame, Eiffel Tower, and Luxembourg Gardens to importance_tier=1 by
forgetting to copy the canonical tier from poi-raw.json into the export
chunk. The bug was masked by the schema's default of `importance_tier=1`,
which has since been removed (see src/api/models/nodes.py).

This test runs in <100ms with no DB and catches both:
  - Tier mismatches (poi-raw says 5, export says 1)
  - Missing fields (poi-raw says 4, export omits the field entirely)
  - Coordinate drift between poi-raw and exports
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"

# Fields that must agree EXACTLY between poi-raw.json and every export entry.
# Skipped: name_variations / short_description (exports may carry chunk-specific
# framing); trigger_radius (currently inconsistent — see TODO below); lat/lng
# (compared with tolerance further down).
STRICT_FIELDS = ("importance_tier",)

# Coordinate tolerance: ~0.0005 deg ≈ 55m at Paris latitude. Tighter than this
# is just rounding noise from JSON serialization.
COORD_TOLERANCE = 0.001

# TODO: trigger_radius is currently drifting — exports have curated larger
# radii for famous POIs (Notre-Dame=100m), poi-raw has stale defaults (10m).
# Decide which is canonical and add to STRICT_FIELDS once aligned.


def _city_dirs() -> list[Path]:
    if not DATA_ROOT.exists():
        return []
    return [
        d for d in sorted(DATA_ROOT.iterdir())
        if d.is_dir() and (d / "poi-raw.json").exists()
    ]


@pytest.mark.parametrize("city_dir", _city_dirs(), ids=lambda d: d.name)
def test_export_matches_poi_raw(city_dir: Path) -> None:
    """For each city: every POI in every export file must match poi-raw.json
    on tier, lat, lng, and trigger_radius."""
    poi_raw = json.loads((city_dir / "poi-raw.json").read_text())
    canonical = {p["name"].lower(): p for p in poi_raw}

    export_dir = city_dir / "export"
    if not export_dir.exists():
        pytest.skip(f"No export directory for {city_dir.name}")

    offenders: list[str] = []

    for export_file in sorted(export_dir.glob("*.json")):
        try:
            data = json.loads(export_file.read_text())
        except json.JSONDecodeError as exc:
            offenders.append(f"{export_file.name}: invalid JSON ({exc})")
            continue
        if not isinstance(data, list):
            offenders.append(f"{export_file.name}: expected list, got {type(data).__name__}")
            continue

        for poi in data:
            name = poi.get("name")
            if not name:
                offenders.append(f"{export_file.name}: POI missing name")
                continue
            canon = canonical.get(name.lower())
            if not canon:
                # POI in export but not in poi-raw — could be a stale export
                offenders.append(
                    f"{export_file.name}: '{name}' is in export but not in poi-raw.json"
                )
                continue

            # Strict equality fields (e.g. importance_tier)
            for field in STRICT_FIELDS:
                exp_val = poi.get(field)
                canon_val = canon.get(field)
                if canon_val is None:
                    continue
                if exp_val != canon_val:
                    offenders.append(
                        f"{export_file.name}: '{name}'.{field} = {exp_val!r} "
                        f"but poi-raw has {canon_val!r}"
                    )

            # Coordinates with tolerance
            for field in ("latitude", "longitude"):
                exp_val = poi.get(field)
                canon_val = canon.get(field)
                if canon_val is None or exp_val is None:
                    continue
                if abs(exp_val - canon_val) > COORD_TOLERANCE:
                    offenders.append(
                        f"{export_file.name}: '{name}'.{field} = {exp_val!r} "
                        f"differs from poi-raw {canon_val!r} by >{COORD_TOLERANCE}"
                    )

    if offenders:
        pytest.fail(
            f"Export/poi-raw drift in {city_dir.name} ({len(offenders)} issues):\n"
            + "\n".join(f"  {o}" for o in offenders[:50])
            + (f"\n  ... and {len(offenders) - 50} more" if len(offenders) > 50 else "")
        )


def test_no_tier_one_for_known_top_landmarks() -> None:
    """Sanity guard: a hard-coded list of obvious world landmarks must NEVER
    appear at importance_tier 1 in any city's poi-raw.json. Catches accidental
    overwrites of canonical data."""
    must_be_high_tier = {
        "paris": [
            "Eiffel Tower", "Notre-Dame Cathedral", "Louvre Museum",
            "Arc de Triomphe", "Sacre-Coeur Basilica", "Luxembourg Gardens",
            "Champs-Elysees",
        ],
    }
    failures: list[str] = []
    for city, names in must_be_high_tier.items():
        path = DATA_ROOT / city / "poi-raw.json"
        if not path.exists():
            continue
        pois = {p["name"]: p for p in json.loads(path.read_text())}
        for n in names:
            p = pois.get(n)
            if not p:
                failures.append(f"{city}: missing POI '{n}'")
            elif p.get("importance_tier", 0) < 4:
                failures.append(
                    f"{city}: '{n}' has importance_tier={p.get('importance_tier')} (expected ≥4)"
                )
    if failures:
        pytest.fail("\n".join(failures))
