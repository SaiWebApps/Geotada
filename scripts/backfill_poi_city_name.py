"""One-time Neo4j backfill: set city_name='paris' on every POI node missing it.

Run BEFORE deploying the Scope 2 MERGE-key change to production.
Without this, the new MERGE `{name, city_name}` will fail to match the
existing 239 Paris POI nodes (they have no city_name) and create duplicates,
orphaning the 548 HAS_BEAT edges pointing at the originals.

Usage:
    .venv/bin/python scripts/backfill_poi_city_name.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys

from neo4j import GraphDatabase


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--city-name", default="paris")
    args = parser.parse_args()

    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ["NEO4J_PASSWORD"]

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as session:
        before = session.run(
            "MATCH (p:POI) WHERE p.city_name IS NULL RETURN count(p) AS n"
        ).single()["n"]
        total = session.run("MATCH (p:POI) RETURN count(p) AS n").single()["n"]
        print(f"POI nodes total: {total}")
        print(f"POI nodes missing city_name: {before}")

        if before == 0:
            print("Nothing to backfill.")
            return 0

        if args.dry_run:
            print(f"[dry-run] Would SET city_name='{args.city_name}' on {before} nodes.")
            return 0

        result = session.run(
            "MATCH (p:POI) WHERE p.city_name IS NULL "
            "SET p.city_name = $city_name RETURN count(p) AS updated",
            city_name=args.city_name,
        ).single()
        updated = result["updated"]
        print(f"Updated {updated} POI nodes with city_name='{args.city_name}'.")

        after = session.run(
            "MATCH (p:POI) WHERE p.city_name IS NULL RETURN count(p) AS n"
        ).single()["n"]
        if after != 0:
            print(f"FAIL: {after} POI nodes still missing city_name.", file=sys.stderr)
            return 1

    driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
