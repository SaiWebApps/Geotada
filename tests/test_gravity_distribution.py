"""Regression test: gravity scores in poi-raw.json must come from a real
scoring pass, not agent guesses, and must have a healthy *shape* (enough
unmissable anchors, no mid-tier clustering, a seasoning-heavy base).

This catches two failure modes that bit us:
  1. POIs added via /pipeline-batch agents that bypassed /poi-gravity entirely
     (32% of Paris POIs had no `_pipeline.gravity_audit` block) — guarded by
     `test_every_poi_has_gravity_audit`.
  2. Bell-curved distributions clustered around tier 3 with starved top tiers
     (was: T5 at 3%, T3 ~45%) — guarded by `test_tier_distribution_healthy_shape`.

WHY SHAPE, NOT BANDS (changed 2026-06-16): the original test froze five
per-tier percentage bands. But `.claude/commands/poi-gravity.md` is explicit
that those percentages are "guidelines, not hard rules" whose purpose is to
avoid mid-tier clustering and starved top tiers — NOT to mandate an exact
curve. Rigid bands gave false positives on legitimately bottom-heavy corpora
(e.g. ingesting a "walks" guidebook full of real tier-1/2 local spots pushed
T1/T2 a few points over the cap even though nothing was clustered). Worse, the
"fix" — a forced `--rescore` — reshapes honest tiers to hit quotas, making them
LESS accurate. So this now asserts the three things the rule actually cares
about, which both the skill's ideal pyramid AND a flatter bottom-heavy curve
satisfy, while the historical bug shape still fails (see the proof test below).

The test runs in <10ms with no DB.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data"

# Intent-based shape thresholds (see module docstring).
T5_MIN_PCT = 7.0   # don't starve the unmissable anchors (historical bug: 3%)
T5_MAX_PCT = 20.0  # don't inflate everything to "unmissable"
T3_MAX_PCT = 35.0  # no mid-tier runaway clustering (historical bug: ~45%)


def _distribution_failures(counts: Counter[int], n: int) -> list[str]:
    """Return human-readable failure strings for an unhealthy tier shape.

    Single source of truth for the shape rules, shared by the real-data test
    and the synthetic proof test so the guard and its proof can never drift.
    Empty list == healthy shape.
    """
    pct = {t: counts.get(t, 0) / n * 100 for t in range(1, 6)}
    failures: list[str] = []
    # 1. Enough unmissable anchors, but not inflated.
    if not (T5_MIN_PCT <= pct[5] <= T5_MAX_PCT):
        failures.append(
            f"  T5 anchors: {counts.get(5, 0)}/{n} ({pct[5]:.1f}%) — "
            f"expected {T5_MIN_PCT}-{T5_MAX_PCT}% (too few starves tours; too many is inflation)"
        )
    # 2. No mid-tier runaway clustering at T3.
    if pct[3] > T3_MAX_PCT:
        failures.append(
            f"  T3 clustering: {counts.get(3, 0)}/{n} ({pct[3]:.1f}%) — "
            f"exceeds {T3_MAX_PCT}% cap (bell-curve clustering, not real ranking)"
        )
    # 3. Seasoning-heavy base: the deep-cut tiers must outweigh the headliners.
    if (pct[1] + pct[2]) < (pct[4] + pct[5]):
        failures.append(
            f"  top-heavy: T1+T2 ({pct[1] + pct[2]:.1f}%) < T4+T5 "
            f"({pct[4] + pct[5]:.1f}%) — a corpus should have more seasoning than headliners"
        )
    return failures


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
def test_tier_distribution_healthy_shape(city_dir: Path) -> None:
    """Tier distribution must have a healthy shape: enough unmissable anchors,
    no mid-tier (T3) clustering, and a seasoning-heavy base. This asserts the
    *intent* of the forced-distribution rules rather than five rigid bands, so
    both the skill's ideal pyramid and a flatter bottom-heavy curve pass while
    the historical bell-curve bug still fails (see proof test below)."""
    pois = json.loads((city_dir / "poi-raw.json").read_text())
    n = len(pois)
    if n < 30:
        pytest.skip(f"{city_dir.name}: too few POIs ({n}) for distribution test")

    counts = Counter(p.get("importance_tier") for p in pois)
    failures = _distribution_failures(counts, n)
    if failures:
        pytest.fail(
            f"{city_dir.name}: unhealthy gravity-tier shape. If this is a real "
            f"distribution (not agent guesses), the scores may be fine and these "
            f"thresholds need revisiting; otherwise run `/poi-gravity {city_dir.name} "
            f"--rescore`.\n" + "\n".join(failures)
        )


def test_distribution_guard_catches_historical_bug() -> None:
    """Proof the shape guard still trips on the failure modes it was born for,
    and still accepts both healthy shapes. Keeps the guard and its rationale
    from silently drifting into a no-op."""
    n = 200

    # Historical bug: T5 starved (~3%), T3 runaway-clustered (~45%).
    bug = Counter({5: 6, 4: 24, 3: 90, 2: 50, 1: 30})
    bug_fail = _distribution_failures(bug, n)
    assert bug_fail, "guard must reject the historical bell-curve bug"
    assert any("T5 anchors" in f for f in bug_fail), "must flag starved T5"
    assert any("T3 clustering" in f for f in bug_fail), "must flag T3 clustering"

    # Skill's ideal pyramid (midpoints of poi-gravity.md targets): peaks at T3.
    ideal = Counter({5: 25, 4: 35, 3: 55, 2: 45, 1: 40})  # 12.5/17.5/27.5/22.5/20%
    assert not _distribution_failures(ideal, n), "skill's ideal pyramid must pass"

    # A flatter, bottom-heavy curve (the shape that prompted this rewrite).
    flat = Counter({5: 17, 4: 24, 3: 53, 2: 55, 1: 51})  # 8.5/12/26.5/27.5/25.5%
    assert not _distribution_failures(flat, n), "healthy bottom-heavy curve must pass"

    # Top-heavy corpus (more headliners than seasoning) must fail.
    topheavy = Counter({5: 40, 4: 50, 3: 60, 2: 30, 1: 20})  # T1+T2=25% < T4+T5=45%
    assert any("top-heavy" in f for f in _distribution_failures(topheavy, n)), (
        "guard must reject a top-heavy corpus"
    )
