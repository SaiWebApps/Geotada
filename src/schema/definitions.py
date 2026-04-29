"""Schema definitions for the Ondoway Neo4j graph.

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
# Relationship property schemas — Schema_v3 §4.1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelPropertyDef:
    """Declares a property that a relationship type supports."""

    name: str
    type: str  # "str", "int", "float", "bool"
    required: bool = False
    default: str | int | float | bool | None = None


RELATIONSHIP_SCHEMAS: dict[str, list[RelPropertyDef]] = {
    "HAS_PROFILE": [],
    "IS_CAPTAIN_OF": [],
    "IS_CREW_OF": [],
    "PREFERS_LENS": [
        RelPropertyDef("weight", "float", required=False, default=1.0),
    ],
    "HAS_STOP": [],
    "ASSIGNED_TO": [],
    "AT_POI": [],
    "PLAYS_BEAT": [],
    "HAS_BEAT": [
        RelPropertyDef("sort_order", "int", required=False, default=0),
    ],
    "TAGGED_WITH": [
        RelPropertyDef("confidence", "float", required=False, default=1.0),
    ],
    "IS_PARENT_OF": [],
}

# ---------------------------------------------------------------------------
# MVP Lenses — Living Doc §08
# ---------------------------------------------------------------------------

MVP_LENSES: list[dict] = [
    {"name": "history", "display_label": "History", "is_parent": True},
    {"name": "arch_design", "display_label": "Architecture & Design", "is_parent": True},
    {"name": "music_nightlife", "display_label": "Music & Nightlife", "is_parent": True},
    {"name": "local_legends", "display_label": "Local Legends & Folklore"},
    {"name": "food_culinary", "display_label": "Food & Culinary Culture"},
    {"name": "art_street", "display_label": "Art & Street Culture"},
    {"name": "literary_film", "display_label": "Literary & Film Locations"},
    {"name": "religious_spiritual", "display_label": "Religious & Spiritual Sites"},
    {"name": "nature_green", "display_label": "Nature & Green Spaces"},
    {"name": "shopping_markets", "display_label": "Shopping & Markets"},
    {"name": "science_innovation", "display_label": "Science & Innovation"},
]

# Child lenses — each references a parent via parent_name
DAG_CHILD_LENSES: list[dict] = [
    {"name": "hidden_history", "display_label": "Hidden History", "parent_name": "history"},
    {"name": "war_revolution", "display_label": "War & Revolution", "parent_name": "history"},
    {"name": "dark_history", "display_label": "Dark History", "parent_name": "history"},
    {"name": "social_change", "display_label": "Social Change", "parent_name": "history"},
    {
        "name": "historic_arch",
        "display_label": "Historic Architecture",
        "parent_name": "arch_design",
    },
    {
        "name": "modern_design",
        "display_label": "Modern & Contemporary Design",
        "parent_name": "arch_design",
    },
    {"name": "music_heritage", "display_label": "Music Heritage", "parent_name": "music_nightlife"},
    {"name": "venues_scenes", "display_label": "Venues & Scenes", "parent_name": "music_nightlife"},
]

# The 16 taggable lenses: 8 children + 8 leaves. Parents are NOT taggable.
TAGGABLE_LENSES: list[str] = [
    # Children of history
    "hidden_history",
    "war_revolution",
    "dark_history",
    "social_change",
    # Children of arch_design
    "historic_arch",
    "modern_design",
    # Children of music_nightlife
    "music_heritage",
    "venues_scenes",
    # Leaves (directly taggable)
    "local_legends",
    "food_culinary",
    "art_street",
    "literary_film",
    "religious_spiritual",
    "nature_green",
    "shopping_markets",
    "science_innovation",
]
