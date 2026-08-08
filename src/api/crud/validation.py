"""The rules every CRUD module applies before it writes to the graph.

WHY THIS MODULE EXISTS. ``edges.py`` and ``nodes.py`` each carried their own
identical copy of all four things below — the same regex, the same 422 raiser,
the same property-key rule, the same label check. Four decisions, each made
twice. Nothing was wrong with either copy, which is exactly why they survived:
two correct copies read as two careful authors rather than one decision made
twice, and they stay that way right up until somebody tightens the rule in one
file.

The cost is concrete rather than theoretical. Widen what counts as a safe
property name in ``nodes.py`` alone and the graph accepts a key through the node
route that the edge route still refuses — a difference nobody would find except
by hitting it in production.

It is a new file because ``src/api/crud/`` had no shared module at all; the
alternative was making one of the two peers import from the other, which fixes
the duplication and creates a layering lie.
"""

from __future__ import annotations

import re

from fastapi.exceptions import RequestValidationError

from src.api.models.edges import RelType
from src.api.models.nodes import NodeLabel

#: A Neo4j property name that is safe to interpolate into Cypher. Property names
#: cannot be parameterised, so this is the boundary between a value and an
#: injection.
VALID_PROPERTY_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def raise_422(msg: str, loc: tuple[str, ...]) -> None:
    """Refuse a bad request as a 422, not a 500.

    The route layer does not — and must not — special-case ``ValueError`` from
    crud, so a plain ``ValueError`` surfaces to the caller as a 500 and reads as
    "the server is broken" when the truth is "your request was wrong".
    ``RequestValidationError`` is handled globally by FastAPI and renders as a
    422 with no route change.
    """
    raise RequestValidationError(
        [{"type": "value_error", "loc": loc, "msg": msg, "input": None}]
    )


def validate_property_keys(properties: dict) -> None:
    """Every property key must be a safe identifier. Raises ``ValueError``."""
    for key in properties:
        if not VALID_PROPERTY_NAME.match(key):
            raise ValueError(
                f"Invalid property name: {key!r}. "
                "Property names must match ^[a-zA-Z_][a-zA-Z0-9_]*$"
            )


def validate_label(label: str) -> None:
    """The label must be one this schema knows. Raises ``ValueError``."""
    NodeLabel(label)


def validate_rel_type(rel_type: str) -> None:
    """The relationship type must be one this schema knows. Raises ``ValueError``."""
    RelType(rel_type)
