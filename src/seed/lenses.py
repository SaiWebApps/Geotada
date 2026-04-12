"""Seed MVP lenses and the DAG parent-child relationship."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.schema.definitions import DAG_CHILD_LENSES, MVP_LENSES

if TYPE_CHECKING:
    from neo4j import Driver

_MERGE_LENS = """
MERGE (l:Lens {name: $name})
SET l.id = coalesce(l.id, randomUUID()),
    l.display_label = $display_label,
    l.is_parent = $is_parent
"""

_MERGE_CHILD_WITH_PARENT = """
MERGE (child:Lens {name: $child_name})
SET child.id = coalesce(child.id, randomUUID()),
    child.display_label = $child_label,
    child.is_parent = false
WITH child
MATCH (parent:Lens {name: $parent_name})
MERGE (parent)-[:IS_PARENT_OF]->(child)
"""


def _create_lens(tx, lens: dict) -> None:
    tx.run(
        _MERGE_LENS,
        name=lens["name"],
        display_label=lens["display_label"],
        is_parent=lens.get("is_parent", False),
    )


def _create_child_lens(tx, child: dict) -> None:
    tx.run(
        _MERGE_CHILD_WITH_PARENT,
        child_name=child["name"],
        child_label=child["display_label"],
        parent_name=child["parent_name"],
    )


def seed_lenses(driver: Driver) -> int:
    """Seed all MVP lenses + DAG children. Returns total lens count.

    After seeding, asserts that the DB contains no Lens nodes with names
    outside the canonical set defined in `definitions.py`. If unknown
    lenses are found, raises RuntimeError listing them — this catches
    schema drift from stale seed files or hand-run queries.
    """
    canonical = {lens["name"] for lens in MVP_LENSES} | {c["name"] for c in DAG_CHILD_LENSES}

    with driver.session() as session:
        for lens in MVP_LENSES:
            session.execute_write(_create_lens, lens)
        for child in DAG_CHILD_LENSES:
            session.execute_write(_create_child_lens, child)

        # Drift detection: every Lens in the DB must be canonical
        result = session.run(
            "MATCH (l:Lens) WHERE NOT l.name IN $canonical RETURN l.name AS name",
            canonical=list(canonical),
        )
        unknown = [r["name"] for r in result]
        if unknown:
            raise RuntimeError(
                f"Lens drift detected: {len(unknown)} unknown lens(es) in DB: {unknown}. "
                f"These are not in src/schema/definitions.py. Run cleanup or update definitions."
            )

    return len(MVP_LENSES) + len(DAG_CHILD_LENSES)
