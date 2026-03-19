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
    child.display_label = $child_label
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
    """Seed all MVP lenses + DAG children. Returns total lens count."""
    with driver.session() as session:
        for lens in MVP_LENSES:
            session.execute_write(_create_lens, lens)
        for child in DAG_CHILD_LENSES:
            session.execute_write(_create_child_lens, child)
    return len(MVP_LENSES) + len(DAG_CHILD_LENSES)
