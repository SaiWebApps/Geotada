"""Regression test: gravity scores in poi-raw.json must come from a real
scoring pass, not agent guesses, and must follow the forced distribution
documented in `.claude/commands/poi-gravity.md`.

This catches two failure modes that bit us today:
  1. POIs added via /pipeline-batch agents that bypassed /poi-gravity entirely
     (32% of Paris POIs had no `_pipeline.gravity_audit` block).
  2. Bell-curved distributions clustered around tier 3 instead of the
     bottom-heavy curve the rules require (was: T5 at 3% vs target 10-15%).

The test runs in <100ms with no DB. To re-baseline after intentional schema
changes, update DISTRIBUTION_TARGETS below.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"

# Forced distribution targets per .claude/commands/poi-gravity.md, with a small
# tolerance band so natural breakpoints don't trip the test.
# (lo_pct, hi_pct) — both inclusive.
DISTRIBUTION_TARGETS: dict[int, tuple[float, float]] = {
    5: (8.0, 18.0),  # rules say 10-15%, allow ±3
    4: (12.0, 22.0),  # rules say 15-20%, allow ±3
    3: (22.0, 32.0),  # rules say 25-30%, allow ±3
    2: (17.0, 27.0),  # rules say 20-25%, allow ±3
    1: (12.0, 22.0),  # rules say 15-20%, allow ±3
}


def _city_dirs() -> list[Path]:
    if not DATA_ROOT.exists():
        return []
    return [d for d in sorted(DATA_ROOT.iterdir()) if d.is_dir() and (d / "poi-raw.json").exists()]


@pytest.mark.parametrize("city_dir", _city_dirs(), ids=lambda d: d.name)
def test_every_poi_has_gravity_audit(city_dir: Path) -> None:
    """Every POI must have a `_pipeline.gravity_audit` block proving it went
    through a real scoring pass. Agent-guessed tiers without an audit trail
    are not allowed."""
    pois = json.loads((city_dir / "poi-raw.json").read_text())
    unaudited = [p["name"] for p in pois if not p.get("_pipeline", {}).get("gravity_audit")]
    if unaudited:
        pytest.fail(
            f"{city_dir.name}: {len(unaudited)} POI(s) lack a gravity_audit "
            f"block (tier was guessed by agent, not formally scored). "
            f"Run `/poi-gravity {city_dir.name} --rescore` to fix.\n"
            "First 20: " + ", ".join(unaudited[:20])
        )


@pytest.mark.parametrize("city_dir", _city_dirs(), ids=lambda d: d.name)
def test_tier_distribution_within_targets(city_dir: Path) -> None:
    """Tier distribution must follow the forced-distribution rules.
    Bell-curved distributions clustered in the middle indicate agent guessing
    rather than real comparative ranking."""
    pois = json.loads((city_dir / "poi-raw.json").read_text())
    n = len(pois)
    if n < 30:
        pytest.skip(f"{city_dir.name}: too few POIs ({n}) for distribution test")

    counts = Counter(p.get("importance_tier") for p in pois)
    failures: list[str] = []
    for tier, (lo_pct, hi_pct) in DISTRIBUTION_TARGETS.items():
        actual = counts[tier]
        actual_pct = actual / n * 100
        if not (lo_pct <= actual_pct <= hi_pct):
            failures.append(
                f"  T{tier}: {actual:3d}/{n} ({actual_pct:.1f}%) — target {lo_pct}-{hi_pct}%"
            )
    if failures:
        pytest.fail(
            f"{city_dir.name}: tier distribution outside forced-distribution "
            f"targets. Run `/poi-gravity {city_dir.name} --rescore` to recalibrate.\n"
            + "\n".join(failures)
        )
