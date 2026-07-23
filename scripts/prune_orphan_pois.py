"""Prune graph POIs (and beats) that the repo no longer contains.

`scripts/deploy.py` is additive (all MERGE), so it can ADD repo POIs/beats but
can never REMOVE a node the repo dropped — after a POI is merged/renamed/deleted
in the repo, its old node lingers in the graph and `db_parity` stays red forever.
This is the missing complement: it deletes exactly the graph POIs whose
`name_key` is absent from the repo poi-raw, and the beats (reachable from this
city's POIs) whose `beat_id` is absent from the repo beats.json, so deploy +
prune reaches true parity.

SAFETY:
  - Dry-run by default; nothing is deleted without ``--apply``.
  - Refuses a non-local (Aura) target unless ``--allow-cloud`` (same guard as
    upload_paris), so an accidental raw run cannot touch production.
  - Aborts if the orphan POI set exceeds a sanity cap (a name_key-normalization
    bug must never turn this into a graph wipe) unless ``--force``.
  - Beats are detected via the POI edge, NOT a `city_name` property (beats carry
    none on deploy-loaded graphs — only the seed path sets it; db_parity scopes
    them the same way), so the beat sweep can't silently match zero.

Usage:
  make prune-orphans CITY=new_york              # dry-run against the active graph
  make prune-orphans CITY=new_york APPLY=1      # local delete
  make prune-orphans CITY=new_york TARGET=cloud CONFIRM_CLOUD_WRITE=1 APPLY=1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from neo4j import GraphDatabase

from scripts.upload_paris import _assert_upload_target_allowed, _city_paths
from src.api.models.nodes import canonical_name_key

# Never delete more than this share of a city's graph POIs without --force: a
# too-aggressive orphan set almost always means a name_key mismatch, not real drift.
_MAX_ORPHAN_FRACTION = 0.15
_MAX_ORPHAN_ABSOLUTE = 20

_POI_QUERY = "MATCH (p:POI {city_name:$slug}) RETURN p.name AS name, p.name_key AS name_key"
_BEAT_QUERY = (
    "MATCH (:POI {city_name:$slug})-[:HAS_BEAT]->(b:NarrativeBeat) "
    "WHERE b.beat_id IS NOT NULL RETURN DISTINCT b.beat_id AS id"
)
_DELETE_BEATS = (
    "MATCH (b:NarrativeBeat) WHERE b.beat_id IN $ids DETACH DELETE b RETURN count(b) AS n"
)
_DELETE_POIS = (
    "MATCH (p:POI {city_name:$slug}) WHERE p.name_key IN $keys DETACH DELETE p RETURN count(p) AS n"
)
_OTHER_CITY_POIS = "MATCH (p:POI) WHERE p.city_name <> $slug RETURN count(p) AS n"


def repo_keys(slug: str) -> tuple[set[str], set[str]]:
    poi_path, beats_path = _city_paths(slug)
    pois = json.loads(Path(poi_path).read_text())
    beats = json.loads(Path(beats_path).read_text())
    return (
        {canonical_name_key(p["name"]) for p in pois},
        {b["beat_id"] for b in beats if b.get("beat_id")},
    )


def orphan_cap(total_pois: int) -> int:
    return max(_MAX_ORPHAN_ABSOLUTE, int(total_pois * _MAX_ORPHAN_FRACTION))


def compute_orphans(
    poi_rows: list[dict], beat_rows: list[dict], repo_poi_keys: set[str], repo_beat_ids: set[str]
) -> tuple[int, list[tuple[str, str]], list[str]]:
    """Pure: (total_pois, orphan_pois[(name,name_key)], orphan_beat_ids)."""
    orphan_pois = sorted(
        (r["name"], r["name_key"]) for r in poi_rows if r["name_key"] not in repo_poi_keys
    )
    orphan_beats = sorted(r["id"] for r in beat_rows if r["id"] not in repo_beat_ids)
    return len(poi_rows), orphan_pois, orphan_beats


def run_prune(
    session, slug: str, repo_poi_keys: set[str], repo_beat_ids: set[str],
    *, apply: bool = False, force: bool = False, echo=print,
) -> int:
    """Core, session-injectable so it is testable without a live graph.

    Returns a process exit code: 0 ok / dry-run, 2 sanity-cap abort.
    """
    poi_rows = session.run(_POI_QUERY, slug=slug).data()
    beat_rows = session.run(_BEAT_QUERY, slug=slug).data()
    total, orphan_pois, orphan_beats = compute_orphans(
        poi_rows, beat_rows, repo_poi_keys, repo_beat_ids
    )
    echo(f"graph POIs: {total} | repo POIs: {len(repo_poi_keys)}")
    echo(f"orphan POIs (in graph, not in repo): {len(orphan_pois)}")
    for name, key in orphan_pois:
        echo(f"  - {name!r}  (name_key={key})")
    echo(f"orphan beats (in graph, not in repo): {len(orphan_beats)}")
    for bid in orphan_beats[:20]:
        echo(f"  - {bid}")

    if not orphan_pois and not orphan_beats:
        echo("\n✓ nothing to prune — graph has no repo-orphan POIs or beats.")
        return 0

    cap = orphan_cap(total)
    if len(orphan_pois) > cap and not force:
        echo(
            f"\nABORT: {len(orphan_pois)} orphan POIs exceeds the sanity cap ({cap}). "
            f"This usually means a name_key mismatch, not real drift. Inspect the list above; "
            f"pass --force only if these deletions are truly intended."
        )
        return 2

    if not apply:
        echo("\nDRY RUN — pass --apply (APPLY=1) to delete the above. Nothing changed.")
        return 0

    # All deletes in ONE transaction guarded by a cross-city tripwire: if any
    # OTHER city's POI count changes, the whole thing rolls back. Beats go first
    # (by globally-unique beat_id — independent of the POI edge the POI delete
    # then removes), then the orphan POIs.
    def _delete_txn(tx):
        other_before = tx.run(_OTHER_CITY_POIS, slug=slug).single()["n"]
        db = tx.run(_DELETE_BEATS, ids=orphan_beats).single()["n"] if orphan_beats else 0
        dp = tx.run(_DELETE_POIS, slug=slug, keys=[k for _, k in orphan_pois]).single()["n"]
        other_after = tx.run(_OTHER_CITY_POIS, slug=slug).single()["n"]
        if other_before != other_after:
            raise RuntimeError(
                f"CROSS-CITY TRIPWIRE: other-city POIs {other_before} -> {other_after}; "
                f"transaction rolled back, nothing deleted."
            )
        return dp, db

    deleted_pois, deleted_beats = session.execute_write(_delete_txn)
    echo(f"\n✓ pruned {deleted_pois} orphan POI(s) + {deleted_beats} orphan beat(s). "
         f"Run `make db-parity CITY={slug}` to confirm parity.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", required=True, help="city slug, e.g. new_york")
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    ap.add_argument("--allow-cloud", action="store_true", help="permit a non-local (Aura) target")
    ap.add_argument("--force", action="store_true", help="bypass the orphan-fraction sanity cap")
    args = ap.parse_args(argv)

    _assert_upload_target_allowed(args.allow_cloud)
    repo_poi_keys, repo_beat_ids = repo_keys(args.slug)
    uri = os.getenv("NEO4J_URI", "")
    auth = (os.getenv("NEO4J_USER", ""), os.getenv("NEO4J_PASSWORD", ""))
    print(f"\n{'='*66}\n  PRUNE ORPHANS {args.slug} @ {uri}\n{'='*66}")
    driver = GraphDatabase.driver(uri, auth=auth)
    try:
        with driver.session() as session:
            return run_prune(
                session, args.slug, repo_poi_keys, repo_beat_ids,
                apply=args.apply, force=args.force,
            )
    finally:
        driver.close()


if __name__ == "__main__":
    sys.exit(main())
