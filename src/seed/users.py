"""Seed test User and Profile nodes with HAS_PROFILE + PREFERS_LENS relationships."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.schema.definitions import TAGGABLE_LENSES

from src.connection import get_database

if TYPE_CHECKING:
    from neo4j import Driver

_MERGE_USER = """
MERGE (u:User {email: $email})
SET u.id = coalesce(u.id, randomUUID()),
    u.created_at = coalesce(u.created_at, datetime()),
    u.last_logon = datetime()
"""

_MERGE_PROFILE = """
MATCH (u:User {email: $email})
MERGE (u)-[:HAS_PROFILE]->(p:Profile {display_name: $display_name})
SET p.id = coalesce(p.id, randomUUID())
"""

_MERGE_PREFERS_LENS = """
MATCH (p:Profile {display_name: $profile_name})
MATCH (l:Lens {name: $lens_name})
MERGE (p)-[:PREFERS_LENS]->(l)
"""

TEST_USER_EMAIL = "testuser@travlr.app"

PROFILES: list[dict] = [
    {
        "display_name": "Mom",
        "lenses": ["hidden_history", "food_culinary", "literary_film"],
    },
    {
        "display_name": "Kid",
        "lenses": ["art_street", "nature_green", "local_legends"],
    },
]

# Validate all profile lens preferences are taggable at import time
for _profile in PROFILES:
    for _ln in _profile["lenses"]:
        assert _ln in TAGGABLE_LENSES, f"Profile lens '{_ln}' is not a taggable lens"


def _create_user(tx, email: str) -> None:
    tx.run(_MERGE_USER, email=email)


def _create_profile(tx, email: str, display_name: str) -> None:
    tx.run(_MERGE_PROFILE, email=email, display_name=display_name)


def _link_lens(tx, profile_name: str, lens_name: str) -> None:
    tx.run(_MERGE_PREFERS_LENS, profile_name=profile_name, lens_name=lens_name)


def seed_users(driver: Driver) -> dict[str, int]:
    """Seed test user, profiles, and lens preferences. Returns counts."""
    with driver.session(database=get_database()) as session:
        session.execute_write(_create_user, TEST_USER_EMAIL)

        for profile in PROFILES:
            session.execute_write(_create_profile, TEST_USER_EMAIL, profile["display_name"])
            for lens_name in profile["lenses"]:
                session.execute_write(_link_lens, profile["display_name"], lens_name)

    return {"users": 1, "profiles": len(PROFILES)}
