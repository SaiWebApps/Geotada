#!/usr/bin/env python
"""Validate a beats.json file for duplicate beats.

Checks two collection-level invariants the Pydantic model can't enforce:

1. `script_body_hash` is unique across all beats in the file.
2. The identity tuple (city_name, poi_name, lens, book_slug, topic_slug) is
   unique across all beats. `legacy_unknown` in the `book_slug` or `topic_slug`
   position acts as a wildcard: two rows that both carry `legacy_unknown` in
   the same position do NOT collide with each other (the legacy migration
   uses this sentinel where the slug couldn't be parsed; the wildcard avoids
   forcing fake collisions on un-recoverable history).

Strictly single-file-path scoped — never reads any other beats.json, env var,
or global state. Pre-upload gate (AC-9) and end-of-extraction gate (AC-11)
both call this script with the city's beats path.

Exit codes:
  0 — all checks pass
  1 — at least one collision (printed with full beat IDs and the conflict type)
  2 — file unreadable / not a JSON list (operator error, distinct from a real
      data-integrity failure)

Usage:
  python scripts/validate_beats.py data/paris/beats.json
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

LEGACY_WILDCARD = "legacy_unknown"


def _load_beats(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a JSON list of beats")
    return data


def _check_hash_uniqueness(beats: list[dict]) -> list[str]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    for beat in beats:
        h = beat.get("script_body_hash", "")
        if not h:
            continue  # missing hash is a different problem; flagged below
        by_hash[h].append(beat.get("beat_id", "<no-beat-id>"))
    errors: list[str] = []
    for h, ids in by_hash.items():
        if len(ids) >= 2:
            errors.append(
                f"HASH_COLLISION script_body_hash={h} beats={ids}"
            )
    missing = [b.get("beat_id", "<no-beat-id>") for b in beats if not b.get("script_body_hash")]
    if missing:
        errors.append(f"HASH_MISSING beats lack script_body_hash: {missing}")
    return errors


def _identity_key(beat: dict) -> tuple[str, str, str, str, str] | None:
    """Build the identity tuple. Returns None when wildcards make this row
    non-collidable with any other row carrying the same wildcard in the same
    position. Two `legacy_unknown` book_slug rows do NOT collide; one
    `legacy_unknown` + one concrete `around_and_about_paris` for the same
    POI/lens/topic likewise do NOT collide (we can't know whether they're the
    same beat). The wildcard is permissive on purpose.
    """
    city_name = beat.get("city_name", "")
    poi_name = beat.get("poi_name", "")
    lens = beat.get("lens", "")
    book_slug = beat.get("book_slug", "")
    topic_slug = beat.get("topic_slug", "")
    if book_slug == LEGACY_WILDCARD or topic_slug == LEGACY_WILDCARD:
        return None
    return (city_name, poi_name, lens, book_slug, topic_slug)


def _check_identity_uniqueness(beats: list[dict]) -> list[str]:
    by_key: dict[tuple, list[str]] = defaultdict(list)
    for beat in beats:
        key = _identity_key(beat)
        if key is None:
            continue
        by_key[key].append(beat.get("beat_id", "<no-beat-id>"))
    errors: list[str] = []
    for key, ids in by_key.items():
        if len(ids) >= 2:
            errors.append(
                "IDENTITY_COLLISION "
                f"(city_name,poi_name,lens,book_slug,topic_slug)={key} beats={ids}"
            )
    return errors


def validate(path: Path) -> list[str]:
    beats = _load_beats(path)
    return _check_hash_uniqueness(beats) + _check_identity_uniqueness(beats)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_beats.py <path-to-beats.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        errors = validate(path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"validate_beats: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    if errors:
        print(f"validate_beats: FAIL ({len(errors)} issue(s)) in {path}")
        for line in errors:
            print(f"  {line}")
        return 1
    print(f"validate_beats: PASS ({path})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
