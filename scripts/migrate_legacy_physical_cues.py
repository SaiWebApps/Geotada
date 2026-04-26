#!/usr/bin/env python
"""Migrate legacy `physical_cues: list[str]` beats to v2 list[dict] form.

Vallois (around_and_about_paris) beats predate the unified_v2 extraction prompt
and carry physical_cues as plain prose strings. The Pydantic NarrativeBeatCreate
model rejects these (PhysicalCue requires cue + direction + feature_type), which
hard-blocks /upload for ~30% of the Paris corpus.

This is a LOSSY migration: each legacy string is wrapped as
    {"cue": <string>, "direction": "here", "feature_type": "view"}
- direction="here" is the safe non-directional default
- feature_type="view" matches what most legacy cues describe (visible features)
The pure prose is preserved verbatim in the cue field, so post-launch Vallois
re-extraction can refine the structure without information loss.

Idempotent: beats already in v2 list[dict] form are left untouched.

Usage:
  python scripts/migrate_legacy_physical_cues.py data/paris/beats.json [--dry-run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_DIRECTION = "here"
DEFAULT_FEATURE_TYPE = "view"


def needs_migration(physical_cues) -> bool:
    if not isinstance(physical_cues, list) or not physical_cues:
        return False
    return any(isinstance(item, str) for item in physical_cues)


def migrate_one(physical_cues: list) -> list[dict]:
    out = []
    for item in physical_cues:
        if isinstance(item, str):
            out.append({
                "cue": item,
                "direction": DEFAULT_DIRECTION,
                "feature_type": DEFAULT_FEATURE_TYPE,
            })
        elif isinstance(item, dict):
            out.append(item)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: migrate_legacy_physical_cues.py <beats.json> [--dry-run]", file=sys.stderr)
        return 2

    path = Path(argv[1])
    dry_run = "--dry-run" in argv

    with path.open("r", encoding="utf-8") as fh:
        beats = json.load(fh)

    scanned = 0
    migrated = 0
    samples_before: list[dict] = []
    samples_after: list[dict] = []

    for beat in beats:
        scanned += 1
        pc = beat.get("physical_cues")
        if not needs_migration(pc):
            continue
        before_sample = list(pc)
        new_pc = migrate_one(pc)
        if not dry_run:
            beat["physical_cues"] = new_pc
        migrated += 1
        if len(samples_before) < 3:
            samples_before.append({"beat_id": beat.get("beat_id"), "physical_cues": before_sample})
            samples_after.append({"beat_id": beat.get("beat_id"), "physical_cues": new_pc})

    if not dry_run:
        with path.open("w", encoding="utf-8") as fh:
            json.dump(beats, fh, indent=2, ensure_ascii=False)

    mode = "DRY-RUN" if dry_run else "APPLIED"
    print(f"migrate_legacy_physical_cues: {mode}")
    print(f"  beats scanned:  {scanned}")
    print(f"  beats migrated: {migrated}")
    print(f"  beats untouched (already v2 or empty): {scanned - migrated}")
    print()
    for i, (b, a) in enumerate(zip(samples_before, samples_after), 1):
        print(f"--- sample {i}: {b['beat_id']!r} ---")
        print(f"  before: {b['physical_cues']}")
        print(f"  after:  {a['physical_cues']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
