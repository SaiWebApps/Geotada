"""Schema definitions for the Travlr Neo4j graph.

Pure data module — no database calls. Consumed by schema.constraints
and tests to keep the source of truth in one place.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UniqueConstraint:
    label: str
    property: str

    @property
    def name(self) -> str:
        return f"uniq_{self.label.lower()}_{self.property}"


@dataclass(frozen=True)
class Index:
    label: str
    properties: tuple[str, ...]
    index_type: str = "RANGE"  # RANGE | POINT

    @property
    def name(self) -> str:
        props = "_".join(self.properties)
        return f"idx_{self.label.lower()}_{props}"


# ---------------------------------------------------------------------------
# Constraints — Schema_v3 §3
# ---------------------------------------------------------------------------

UNIQUE_CONSTRAINTS: list[UniqueConstraint] = [
    UniqueConstraint("User", "id"),
    UniqueConstraint("User", "email"),
    UniqueConstraint("Profile", "id"),
    UniqueConstraint("Trip", "id"),
    UniqueConstraint("ItineraryItem", "id"),
    UniqueConstraint("POI", "id"),
    UniqueConstraint("NarrativeBeat", "id"),
    UniqueConstraint("Lens", "id"),
    UniqueConstraint("Lens", "name"),
]

# ---------------------------------------------------------------------------
# Indexes — Schema_v3 §3.5, §3.6
# ---------------------------------------------------------------------------

INDEXES: list[Index] = [
    Index("POI", ("location",), index_type="POINT"),
    Index("NarrativeBeat", ("active_status", "version"), index_type="RANGE"),
]

# ---------------------------------------------------------------------------
# Relationship types — Schema_v3 §4 (all 11)
# ---------------------------------------------------------------------------

RELATIONSHIP_TYPES: list[str] = [
    "HAS_PROFILE",
    "IS_CAPTAIN_OF",
    "IS_CREW_OF",
    "PREFERS_LENS",
    "HAS_STOP",
    "ASSIGNED_TO",
    "AT_POI",
    "PLAYS_BEAT",
    "HAS_BEAT",
    "TAGGED_WITH",
    "IS_PARENT_OF",
]

# ---------------------------------------------------------------------------
# MVP Lenses — Living Doc §08
# ---------------------------------------------------------------------------

MVP_LENSES: list[dict[str, str]] = [
    {"name": "hidden_history", "display_label": "Hidden History"},
    {"name": "arch_design", "display_label": "Architecture & Design"},
    {"name": "local_legends", "display_label": "Local Legends & Folklore"},
    {"name": "food_culinary", "display_label": "Food & Culinary Culture"},
    {"name": "art_street", "display_label": "Art & Street Culture"},
    {"name": "dark_history", "display_label": "Dark History"},
    {"name": "literary_film", "display_label": "Literary & Film Locations"},
    {"name": "religious_spiritual", "display_label": "Religious & Spiritual Sites"},
    {"name": "music_nightlife", "display_label": "Music & Nightlife History"},
    {"name": "revolutionary", "display_label": "Revolutionary Moments"},
    {"name": "nature_green", "display_label": "Nature & Green Spaces"},
    {"name": "shopping_markets", "display_label": "Shopping & Markets"},
]

# Child lens to prove DAG (IS_PARENT_OF)
DAG_CHILD_LENSES: list[dict] = [
    {
        "name": "arch_gothic_01",
        "display_label": "Gothic Architecture",
        "parent_name": "arch_design",
    },
]
