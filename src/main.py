"""Travlr Neo4j setup — create schema, seed data, verify traversals.

Usage:
    make setup          # full setup + seed + verify
    make verify         # verify only (no schema changes)
"""

from __future__ import annotations

import sys

from src.connection import abort_on_connection_error, get_database, get_driver
from src.schema.constraints import apply_all
from src.seed.runner import seed_all
from src.verify.counts import count_nodes_by_label, count_relationships_by_type, total_counts
from src.verify.reporter import print_counts, print_section, print_summary, print_traversals
from src.verify.traversals import run_all_traversals


@abort_on_connection_error
def setup() -> None:
    """Full pipeline: constraints → seed → verify."""
    with get_driver() as driver:
        print_section("APPLYING SCHEMA")
        schema_counts = apply_all(driver)
        print(f"  Constraints: {schema_counts['constraints']}")
        print(f"  Indexes:     {schema_counts['indexes']}")

        print_section("SEEDING DATA")
        seed_counts = seed_all(driver)
        for entity, count in seed_counts.items():
            print(f"  {entity:<12} {count:>3}")

        _run_verification(driver)


@abort_on_connection_error
def verify_only() -> None:
    """Run verification without schema changes or seeding."""
    with get_driver() as driver:
        _run_verification(driver)


def _run_verification(driver) -> None:
    """Shared verification logic."""
    node_counts = count_nodes_by_label(driver)
    rel_counts = count_relationships_by_type(driver)
    print_counts(node_counts, rel_counts)

    traversal_results = run_all_traversals(driver)
    print_traversals(traversal_results)

    totals = total_counts(driver)
    all_passed = print_summary(totals, traversal_results)

    if not all_passed:
        sys.exit(1)


@abort_on_connection_error
def clean() -> None:
    """Wipe all nodes and relationships (for testing)."""
    with get_driver() as driver:
        with driver.session(database=get_database()) as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("  ✓ Database wiped.")


if __name__ == "__main__":
    setup()
