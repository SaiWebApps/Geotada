"""Tests for the onboarding/complete endpoint and edge source_id filtering."""

from __future__ import annotations

from src.api.auth.tokens import create_access_token
from src.connection import get_database
from src.seed.lenses import seed_lenses
from tests.conftest import needs_neo4j


def _seed_onboarding_user(driver):
    """Insert a test user and ensure lenses exist."""
    seed_lenses(driver)
    with driver.session(database=get_database()) as session:
        session.run(
            "MERGE (u:User {id: 'test-onboarding-user-id'}) "
            "SET u.email = 'onboard@ondoway.app', "
            "u.created_at = coalesce(u.created_at, datetime())"
        )


def _cleanup_onboarding_user(driver):
    """Remove test user, profile, and edges."""
    with driver.session(database=get_database()) as session:
        session.run(
            "MATCH (u:User {id: 'test-onboarding-user-id'}) "
            "OPTIONAL MATCH (u)-[:HAS_PROFILE]->(p:Profile) "
            "OPTIONAL MATCH (p)-[r:PREFERS_LENS]->() "
            "DETACH DELETE p, u"
        )


def _get_auth_headers(driver):
    _seed_onboarding_user(driver)
    token = create_access_token("test-onboarding-user-id", "onboard@ondoway.app")
    return {"Authorization": f"Bearer {token}"}


def _get_child_lens_ids(client, clean_driver, count=3):
    seed_lenses(clean_driver)
    resp = client.get("/api/v1/nodes/Lens?limit=200")
    assert resp.status_code == 200
    lenses = resp.json()["items"]
    children = [l for l in lenses if not l["properties"].get("is_parent", False)]
    assert len(children) >= count, f"Need at least {count} child lenses, found {len(children)}"
    return [c["id"] for c in children[:count]]


@needs_neo4j
class TestOnboardingComplete:
    def test_creates_profile_and_lens_preferences(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        lens_ids = _get_child_lens_ids(client, clean_driver)
        try:
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["display_name"] == "Onboard"
            assert data["lens_count"] == 3
            assert data["profile_id"]
        finally:
            _cleanup_onboarding_user(clean_driver)

    def test_rejects_fewer_than_3_lenses(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        lens_ids = _get_child_lens_ids(client, clean_driver, 2)
        try:
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            assert resp.status_code == 422
            assert "At least 3 lenses" in resp.json()["detail"]
        finally:
            _cleanup_onboarding_user(clean_driver)

    def test_rejects_empty_lens_list(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        try:
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": []},
                headers=headers,
            )
            assert resp.status_code == 422
        finally:
            _cleanup_onboarding_user(clean_driver)

    def test_requires_auth(self, client, clean_driver):
        lens_ids = _get_child_lens_ids(client, clean_driver)
        resp = client.post(
            "/api/v1/auth/onboarding/complete",
            json={"lens_ids": lens_ids},
        )
        assert resp.status_code == 401

    def test_idempotent_on_retry(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        lens_ids = _get_child_lens_ids(client, clean_driver)
        try:
            resp1 = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            assert resp1.status_code == 200
            profile_id_1 = resp1.json()["profile_id"]

            resp2 = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            assert resp2.status_code == 200
            assert resp2.json()["profile_id"] == profile_id_1
        finally:
            _cleanup_onboarding_user(clean_driver)

    def test_ignores_parent_lens_ids(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        resp = client.get("/api/v1/nodes/Lens?limit=200")
        lenses = resp.json()["items"]
        parents = [l for l in lenses if l["properties"].get("is_parent", False)]
        children = [l for l in lenses if not l["properties"].get("is_parent", False)]
        mixed_ids = [p["id"] for p in parents[:2]] + [c["id"] for c in children[:3]]
        try:
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": mixed_ids},
                headers=headers,
            )
            assert resp.status_code == 200
            assert resp.json()["lens_count"] == 3
        finally:
            _cleanup_onboarding_user(clean_driver)


@needs_neo4j
class TestEdgeSourceIdFilter:
    def test_list_edges_with_source_id(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        lens_ids = _get_child_lens_ids(client, clean_driver)
        try:
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            profile_id = resp.json()["profile_id"]

            resp = client.get(
                f"/api/v1/edges/PREFERS_LENS?source_id={profile_id}&limit=200"
            )
            assert resp.status_code == 200
            edges = resp.json()["items"]
            assert len(edges) == 3
            assert all(e["source_id"] == profile_id for e in edges)
        finally:
            _cleanup_onboarding_user(clean_driver)

    def test_list_edges_without_source_id_returns_all(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        lens_ids = _get_child_lens_ids(client, clean_driver)
        try:
            client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            resp = client.get("/api/v1/edges/PREFERS_LENS?limit=200")
            assert resp.status_code == 200
            assert resp.json()["total"] >= 3
        finally:
            _cleanup_onboarding_user(clean_driver)

    def test_source_id_filter_returns_empty_for_unknown(self, client):
        resp = client.get(
            "/api/v1/edges/PREFERS_LENS?source_id=nonexistent-id&limit=200"
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []


@needs_neo4j
class TestProfileThemePreference:
    """Tests for storing and retrieving theme_preference on Profile nodes."""

    def test_set_theme_preference_via_node_update(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        lens_ids = _get_child_lens_ids(client, clean_driver)
        try:
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            assert resp.status_code == 200
            profile_id = resp.json()["profile_id"]

            resp = client.put(
                f"/api/v1/nodes/Profile/{profile_id}",
                json={"properties": {"theme_preference": "dark"}},
            )
            assert resp.status_code == 200
        finally:
            _cleanup_onboarding_user(clean_driver)

    def test_get_theme_preference_after_set(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        lens_ids = _get_child_lens_ids(client, clean_driver)
        try:
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            profile_id = resp.json()["profile_id"]

            client.put(
                f"/api/v1/nodes/Profile/{profile_id}",
                json={"properties": {"theme_preference": "dark"}},
            )

            resp = client.get(f"/api/v1/nodes/Profile/{profile_id}")
            assert resp.status_code == 200
            assert resp.json()["properties"]["theme_preference"] == "dark"
        finally:
            _cleanup_onboarding_user(clean_driver)

    def test_theme_preference_null_for_new_profile(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        lens_ids = _get_child_lens_ids(client, clean_driver)
        try:
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            profile_id = resp.json()["profile_id"]

            resp = client.get(f"/api/v1/nodes/Profile/{profile_id}")
            assert resp.status_code == 200
            assert "theme_preference" not in resp.json()["properties"]
        finally:
            _cleanup_onboarding_user(clean_driver)

    def test_theme_preference_accepts_all_valid_values(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        lens_ids = _get_child_lens_ids(client, clean_driver)
        try:
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            profile_id = resp.json()["profile_id"]

            for value in ("system", "light", "dark"):
                resp = client.put(
                    f"/api/v1/nodes/Profile/{profile_id}",
                    json={"properties": {"theme_preference": value}},
                )
                assert resp.status_code == 200, f"Failed for value '{value}'"
        finally:
            _cleanup_onboarding_user(clean_driver)

    def test_theme_preference_survives_onboarding_retry(self, client, clean_driver):
        headers = _get_auth_headers(clean_driver)
        lens_ids = _get_child_lens_ids(client, clean_driver)
        try:
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            profile_id = resp.json()["profile_id"]

            client.put(
                f"/api/v1/nodes/Profile/{profile_id}",
                json={"properties": {"theme_preference": "dark"}},
            )

            # Re-run onboarding (idempotent — ON CREATE SET only fires on new nodes)
            resp = client.post(
                "/api/v1/auth/onboarding/complete",
                json={"lens_ids": lens_ids},
                headers=headers,
            )
            assert resp.status_code == 200

            resp = client.get(f"/api/v1/nodes/Profile/{profile_id}")
            assert resp.status_code == 200
            assert resp.json()["properties"]["theme_preference"] == "dark"
        finally:
            _cleanup_onboarding_user(clean_driver)
