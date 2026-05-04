"""Unit + integration tests for Google ID token verification and auth endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.api.auth.google import verify_google_id_token
from src.api.auth.tokens import TokenError
from tests.conftest import needs_neo4j


class TestVerifyGoogleIdToken:
    @patch("src.api.auth.google.id_token.verify_oauth2_token")
    def test_valid_token_returns_user_info(self, mock_verify):
        mock_verify.return_value = {
            "email": "user@gmail.com",
            "sub": "google-uid-123",
            "name": "Test User",
        }

        result = verify_google_id_token("valid-google-token")

        assert result["email"] == "user@gmail.com"
        assert result["sub"] == "google-uid-123"
        assert result["name"] == "Test User"

    @patch("src.api.auth.google.id_token.verify_oauth2_token")
    def test_invalid_token_raises_token_error(self, mock_verify):
        mock_verify.side_effect = ValueError("Token expired or invalid")

        with pytest.raises(TokenError, match="Invalid Google ID token"):
            verify_google_id_token("bad-token")

    @patch("src.api.auth.google.id_token.verify_oauth2_token")
    def test_missing_email_raises_token_error(self, mock_verify):
        mock_verify.return_value = {"sub": "123"}

        with pytest.raises(TokenError, match="missing email"):
            verify_google_id_token("token-no-email")

    @patch("src.api.auth.google.id_token.verify_oauth2_token")
    def test_passes_correct_client_id(self, mock_verify):
        mock_verify.return_value = {
            "email": "user@gmail.com",
            "sub": "123",
        }

        with patch("src.api.auth.google.GOOGLE_CLIENT_ID", "my-client-id"):
            verify_google_id_token("tok")

        call_args = mock_verify.call_args
        assert call_args[0][0] == "tok"
        assert call_args[0][2] == "my-client-id"


@needs_neo4j
class TestGoogleAuthEndpoint:
    """Integration tests for POST /api/v1/auth/google — verifies Neo4j interactions."""

    @patch("src.api.auth.routes.verify_google_id_token")
    def test_google_login_creates_user_in_neo4j(self, mock_verify, client, clean_driver):
        """POST /auth/google with valid token creates a User node in Neo4j."""
        mock_verify.return_value = {
            "email": "googleuser@test.com",
            "sub": "g-create-123",
            "name": "Test Google User",
        }

        resp = client.post("/api/v1/auth/google", json={"id_token": "fake-google-token"})
        assert resp.status_code == 200

        # Verify user node was created in Neo4j with the correct email
        from src.connection import get_database

        with clean_driver.session(database=get_database()) as s:
            result = s.run("MATCH (u:User {email: 'googleuser@test.com'}) RETURN u").single()
            assert result is not None
            user_node = result["u"]
            assert user_node["email"] == "googleuser@test.com"
            assert user_node["id"] is not None

    @patch("src.api.auth.routes.verify_google_id_token")
    def test_google_login_returns_access_and_refresh_tokens(
        self, mock_verify, client, clean_driver
    ):
        """POST /auth/google returns both access_token and refresh_token."""
        mock_verify.return_value = {
            "email": "tokens@test.com",
            "sub": "g-tokens-456",
            "name": "Token User",
        }

        resp = client.post("/api/v1/auth/google", json={"id_token": "fake-google-token"})
        assert resp.status_code == 200

        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        # Tokens should be non-empty JWT strings
        assert len(data["access_token"].split(".")) == 3
        assert len(data["refresh_token"].split(".")) == 3

    @patch("src.api.auth.routes.verify_google_id_token")
    def test_google_login_merges_existing_user(self, mock_verify, client, clean_driver):
        """POST /auth/google for an existing email merges (no duplicate User nodes)."""
        from src.connection import get_database

        # Seed a user first
        with clean_driver.session(database=get_database()) as s:
            s.run(
                """
                MERGE (u:User {email: $email})
                SET u.id = $uid,
                    u.created_at = datetime(),
                    u.last_logon = datetime()
                """,
                email="existing@test.com",
                uid="pre-existing-id",
            )

        mock_verify.return_value = {
            "email": "existing@test.com",
            "sub": "g-existing-789",
            "name": "Existing User",
        }

        resp = client.post("/api/v1/auth/google", json={"id_token": "fake-google-token"})
        assert resp.status_code == 200

        # Verify exactly one user node exists for this email (no duplicate)
        with clean_driver.session(database=get_database()) as s:
            result = s.run(
                "MATCH (u:User {email: 'existing@test.com'}) RETURN count(u) AS c"
            ).single()
            assert result["c"] == 1

    @patch(
        "src.api.auth.routes.verify_google_id_token",
        side_effect=TokenError("Invalid Google ID token"),
    )
    def test_google_login_invalid_token_returns_401(self, mock_verify, client):
        """POST /auth/google with an invalid token returns 401 Unauthorized."""
        resp = client.post("/api/v1/auth/google", json={"id_token": "bad-token"})
        assert resp.status_code == 401
        assert "Invalid Google ID token" in resp.json()["detail"]
