#!/usr/bin/env python
"""Find candidate duplicate beat pairs via MinHash LSH.

Reads a city's beats.json, builds a MinHash over 5-gram word shingles per
beat, queries an LSH index at the configured Jaccard threshold, and emits
candidate pairs with their exact pairwise Jaccard (computed on the shingle
sets, not the MinHash approximation).

Read-only. Never mutates beats.json. Called by scripts/beat_dedup.py and by
tests.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from datasketch import MinHash, MinHashLSH

DEFAULT_THRESHOLD = 0.5
DEFAULT_NUM_PERM = 128
DEFAULT_SHINGLE = 5


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def shingle_set(text: str, size: int = DEFAULT_SHINGLE) -> set[str]:
    words = _normalize(text).split()
    if len(words) < size:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def _minhash(shingles: set[str], num_perm: int) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for s in shingles:
        m.update(s.encode("utf-8"))
    return m


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def find_pairs(
    beats: list[dict],
    threshold: float = DEFAULT_THRESHOLD,
    num_perm: int = DEFAULT_NUM_PERM,
    shingle_size: int = DEFAULT_SHINGLE,
) -> list[dict]:
    """Return candidate pairs as `[{'beat_a': id, 'beat_b': id, 'jaccard': f}]`.

    Pairs are sorted by Jaccard descending. Each unordered pair appears once
    (keyed by sorted(beat_id_a, beat_id_b)).
    """
    shingles_by_id: dict[str, set[str]] = {}
    minhashes: dict[str, MinHash] = {}
    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)

    for beat in beats:
        bid = beat.get("beat_id")
        if not bid:
            continue
        body = beat.get("script_body", "")
        sh = shingle_set(body, shingle_size)
        if not sh:
            continue
        shingles_by_id[bid] = sh
        mh = _minhash(sh, num_perm)
        minhashes[bid] = mh
        lsh.insert(bid, mh)

    seen: set[tuple[str, str]] = set()
    pairs: list[dict] = []
    for bid, mh in minhashes.items():
        for cand in lsh.query(mh):
            if cand == bid:
                continue
            key = tuple(sorted((bid, cand)))
            if key in seen:
                continue
            seen.add(key)
            j = _jaccard(shingles_by_id[bid], shingles_by_id[cand])
            if j >= threshold:
                pairs.append({"beat_a": key[0], "beat_b": key[1], "jaccard": round(j, 4)})

    pairs.sort(key=lambda p: p["jaccard"], reverse=True)
    return pairs


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("city", help="city slug (e.g. paris); reads data/{city}/beats.json")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--num-perm", type=int, default=DEFAULT_NUM_PERM)
    ap.add_argument("--shingle-size", type=int, default=DEFAULT_SHINGLE)
    ap.add_argument(
        "--beats-path",
        default=None,
        help="override path (default: data/{city}/beats.json)",
    )
    args = ap.parse_args(argv[1:])

    path = Path(args.beats_path) if args.beats_path else Path("data") / args.city / "beats.json"
    try:
        with path.open("r", encoding="utf-8") as fh:
            beats = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"dedup_pairs: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    pairs = find_pairs(
        beats,
        threshold=args.threshold,
        num_perm=args.num_perm,
        shingle_size=args.shingle_size,
    )
    json.dump(pairs, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
