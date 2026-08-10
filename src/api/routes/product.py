"""Public read-only product endpoint: the lens taxonomy.

Unlike the workbench CRUD routers (graph/nodes/edges/schema/onboard), this is
mounted UNCONDITIONALLY in src/api/app.py — outside `_workbench_api_enabled()`
— because the mobile client needs it with the gate off (see
specs/2026-08-09-public-read-endpoints/run-context.md, decision
`workbench_stays_off`).

The /profile endpoint from the original branch is intentionally NOT shipped
here: it was an auth-gate-only stub that returned {}. It lands with its real
body (display_name/selected_lens_ids/theme_preference) in a later slice.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from neo4j import Session

from src.api.dependencies import get_session

router = APIRouter(tags=["product"])


@router.get("/lenses")
def list_lenses(session: Session = Depends(get_session)) -> list[dict]:
    """Return the lens taxonomy.

    P3 build (run-context.md decisions `lenses_shape`, `p1_minimal_build`):
    each parent lens carries a nested `children` list of its child lenses
    (id, name, display_label, is_parent:false), gathered via OPTIONAL MATCH
    on IS_PARENT_OF so a childless parent yields an empty list rather than
    being dropped.
    """
    result = session.run(
        "MATCH (parent:Lens {is_parent: true}) "
        "OPTIONAL MATCH (parent)-[:IS_PARENT_OF]->(child:Lens) "
        "RETURN parent.id AS id, parent.name AS name, "
        "parent.display_label AS display_label, parent.is_parent AS is_parent, "
        "collect(CASE WHEN child IS NULL THEN NULL ELSE {"
        "id: child.id, name: child.name, display_label: child.display_label, "
        "is_parent: child.is_parent} END) AS children"
    )
    return [
        {
            "id": record["id"],
            "name": record["name"],
            "display_label": record["display_label"],
            "is_parent": record["is_parent"],
            "children": [c for c in record["children"] if c is not None],
        }
        for record in result
    ]
