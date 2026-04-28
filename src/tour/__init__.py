"""Tour-builder — Phase 2.

POI selection, routing math, and within-POI beat ordering against the
live Neo4j corpus. Phase-1 design at Docs/tour-builder/phase-1-design.md.

This package exposes pure-Python functions over snapshot data structures,
plus thin Neo4j loaders. Generation/validation modules land in Phase 3.
"""

from __future__ import annotations
