"""Orchestrate all seed operations in dependency order.

Order matters: Lenses → Users/Profiles → POIs → Beats → Trip/Items.
Each module uses MERGE, so re-running is safe.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.seed.lenses import seed_lenses
from src.seed.locations import seed_pois
from src.seed.narratives import seed_beats
from src.seed.trips import seed_trip
from src.seed.users import seed_users

if TYPE_CHECKING:
    from neo4j import Driver


def seed_all(driver: Driver) -> dict[str, int]:
    """Run all seed operations. Returns a summary of counts."""
    lens_count = seed_lenses(driver)
    user_counts = seed_users(driver)
    poi_count = seed_pois(driver)
    beat_count = seed_beats(driver)
    trip_counts = seed_trip(driver)

    return {
        "lenses": lens_count,
        **user_counts,
        "pois": poi_count,
        "beats": beat_count,
        **trip_counts,
    }
