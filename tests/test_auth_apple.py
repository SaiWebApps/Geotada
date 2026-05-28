"""Unit + integration tests for Apple ID token verification and auth endpoint."""

from __future__ import annotations

import hashlib
import time
from unittest.mock import MagicMock, patch

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from src.api.auth.apple import verify_apple_id_token
from src.api.auth.config import BUNDLE_ID
from src.api.auth.tokens import TokenError
from tests.conftest import needs_neo4j

_TEST_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_TEST_PUBLIC_KEY = _TEST_KEY.public_key()

_WRONG_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_apple_jwt(
    claims: dict | None = None,
    key=None,
    algorithm: str = "RS256",
) -> str:
    now = int(time.time())
    payload = {
        "iss": "https://appleid.apple.com",
        "aud": BUNDLE_ID,
        "exp": now + 3600,
        "iat": now,
        "sub": "apple-uid-001",
        "email": "user@icloud.com",
    }
    if claims:
        payload.update(claims)
    return pyjwt.encode(payload, key or _TEST_KEY, algorithm=algorithm)


def _mock_jwks_client():
    mock_key = MagicMock()
    mock_key.key = _TEST_PUBLIC_KEY
    mock_client = MagicMock()
    mock_client.get_signing_key_from_jwt.return_value = mock_key
    return mock_client


class TestVerifyAppleIdToken:
    @patch("src.api.auth.apple._jwks_client")
    def test_valid_token_returns_user_info(self, mock_client):
        mock_client.get_signing_key_from_jwt.return_value = MagicMock(key=_TEST_PUBLIC_KEY)

        token = _make_apple_jwt()
        result = verify_apple_id_token(token)

        assert result["email"] == "user@icloud.com"
        assert result["sub"] == "apple-uid-001"

    @patch("src.api.auth.apple._jwks_client")
    def test_wrong_audience_raises_token_error(self, mock_client):
        mock_client.get_signing_key_from_jwt.return_value = MagicMock(key=_TEST_PUBLIC_KEY)

        token = _make_apple_jwt({"aud": "com.wrong.app"})
        with pytest.raises(TokenError, match="audience mismatch"):
            verify_apple_id_token(token)

    @patch("src.api.auth.apple._jwks_client")
    def test_wrong_issuer_raises_token_error(self, mock_client):
        mock_client.get_signing_key_from_jwt.return_value = MagicMock(key=_TEST_PUBLIC_KEY)

        token = _make_apple_jwt({"iss": "https://evil.com"})
        with pytest.raises(TokenError, match="issuer mismatch"):
            verify_apple_id_token(token)

    @patch("src.api.auth.apple._jwks_client")
    def test_expired_token_raises_token_error(self, mock_client):
        mock_client.get_signing_key_from_jwt.return_value = MagicMock(key=_TEST_PUBLIC_KEY)

        token = _make_apple_jwt({"exp": int(time.time()) - 3600})
        with pytest.raises(TokenError, match="expired"):
            verify_apple_id_token(token)

    @patch("src.api.auth.apple._jwks_client")
    def test_missing_email_raises_token_error(self, mock_client):
        mock_client.get_signing_key_from_jwt.return_value = MagicMock(key=_TEST_PUBLIC_KEY)

        now = int(time.time())
        payload = {
            "iss": "https://appleid.apple.com",
            "aud": BUNDLE_ID,
            "exp": now + 3600,
            "iat": now,
            "sub": "apple-uid-001",
        }
        token = pyjwt.encode(payload, _TEST_KEY, algorithm="RS256")
        with pytest.raises(TokenError, match="missing email"):
            verify_apple_id_token(token)

    @patch("src.api.auth.apple._jwks_client")
    def test_nonce_valid_accepted(self, mock_client):
        mock_client.get_signing_key_from_jwt.return_value = MagicMock(key=_TEST_PUBLIC_KEY)

        nonce = "random-nonce-string"
        nonce_hash = hashlib.sha256(nonce.encode()).hexdigest()
        token = _make_apple_jwt({"nonce": nonce_hash})

        result = verify_apple_id_token(token, nonce=nonce)
        assert result["email"] == "user@icloud.com"

    @patch("src.api.auth.apple._jwks_client")
    def test_nonce_mismatch_raises_token_error(self, mock_client):
        mock_client.get_signing_key_from_jwt.return_value = MagicMock(key=_TEST_PUBLIC_KEY)

        token = _make_apple_jwt({"nonce": "wrong-hash-value"})
        with pytest.raises(TokenError, match="nonce mismatch"):
            verify_apple_id_token(token, nonce="my-nonce")

    @patch("src.api.auth.apple._jwks_client")
    def test_invalid_signature_raises_token_error(self, mock_client):
        wrong_public_key = _WRONG_KEY.public_key()
        mock_client.get_signing_key_from_jwt.return_value = MagicMock(key=wrong_public_key)

        token = _make_apple_jwt()
        with pytest.raises(TokenError, match="verification failed"):
            verify_apple_id_token(token)


@needs_neo4j
class TestAppleAuthEndpoint:
    @patch("src.api.auth.routes.verify_apple_id_token")
    def test_apple_login_creates_user(self, mock_verify, client, clean_driver):
        mock_verify.return_value = {
            "email": "appleuser@icloud.com",
            "sub": "apple-create-001",
            "name": "Apple User",
        }

        resp = client.post(
            "/api/v1/auth/apple",
            json={"identity_token": "fake-apple-token"},
        )
        assert resp.status_code == 200

        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

        from src.connection import get_database

        with clean_driver.session(database=get_database()) as s:
            result = s.run(
                "MATCH (u:User {email: 'appleuser@icloud.com'}) RETURN u"
            ).single()
            assert result is not None
            assert result["u"]["email"] == "appleuser@icloud.com"

    @patch("src.api.auth.routes.verify_apple_id_token")
    def test_apple_login_merges_existing_user(self, mock_verify, client, clean_driver):
        from src.connection import get_database

        with clean_driver.session(database=get_database()) as s:
            s.run(
                """
                MERGE (u:User {email: $email})
                SET u.id = $uid,
                    u.created_at = datetime(),
                    u.last_logon = datetime()
                """,
                email="existing-apple@icloud.com",
                uid="pre-existing-apple-id",
            )

        mock_verify.return_value = {
            "email": "existing-apple@icloud.com",
            "sub": "apple-existing-002",
            "name": "Existing Apple",
        }

        resp = client.post(
            "/api/v1/auth/apple",
            json={"identity_token": "fake-apple-token"},
        )
        assert resp.status_code == 200

        with clean_driver.session(database=get_database()) as s:
            result = s.run(
                "MATCH (u:User {email: 'existing-apple@icloud.com'}) RETURN count(u) AS c"
            ).single()
            assert result["c"] == 1

    @patch("src.api.auth.routes.verify_apple_id_token")
    def test_apple_login_stores_apple_sub(self, mock_verify, client, clean_driver):
        mock_verify.return_value = {
            "email": "subtest@icloud.com",
            "sub": "apple-sub-stored-003",
            "name": "Sub Test",
        }

        resp = client.post(
            "/api/v1/auth/apple",
            json={"identity_token": "fake-apple-token"},
        )
        assert resp.status_code == 200

        from src.connection import get_database

        with clean_driver.session(database=get_database()) as s:
            result = s.run("MATCH (u:User {email: 'subtest@icloud.com'}) RETURN u").single()
            assert result is not None
            assert result["u"]["apple_sub"] == "apple-sub-stored-003"

    @patch(
        "src.api.auth.routes.verify_apple_id_token",
        side_effect=TokenError("Apple token verification failed"),
    )
    def test_apple_login_invalid_token_returns_401(self, mock_verify, client):
        resp = client.post(
            "/api/v1/auth/apple",
            json={"identity_token": "bad-token"},
        )
        assert resp.status_code == 401
        assert "Apple token verification failed" in resp.json()["detail"]


@needs_neo4j
class TestAccountLinking:
    @patch("src.api.auth.routes.verify_google_id_token")
    @patch("src.api.auth.routes.verify_apple_id_token")
    def test_google_then_apple_same_email_one_user(
        self, mock_apple, mock_google, client, clean_driver
    ):
        email = "linked-ga@test.com"
        mock_google.return_value = {"email": email, "sub": "g-link-001", "name": "User"}
        mock_apple.return_value = {"email": email, "sub": "a-link-001", "name": "User"}

        client.post("/api/v1/auth/google", json={"id_token": "g-tok"})
        client.post("/api/v1/auth/apple", json={"identity_token": "a-tok"})

        from src.connection import get_database

        with clean_driver.session(database=get_database()) as s:
            result = s.run(
                "MATCH (u:User {email: $email}) RETURN u, count(u) AS c",
                email=email,
            ).single()
            assert result["c"] == 1
            user = result["u"]
            assert user["google_sub"] == "g-link-001"
            assert user["apple_sub"] == "a-link-001"

    @patch("src.api.auth.routes.verify_apple_id_token")
    @patch("src.api.auth.routes.verify_google_id_token")
    def test_apple_then_google_same_email_one_user(
        self, mock_google, mock_apple, client, clean_driver
    ):
        email = "linked-ag@test.com"
        mock_apple.return_value = {"email": email, "sub": "a-link-002", "name": "User"}
        mock_google.return_value = {"email": email, "sub": "g-link-002", "name": "User"}

        client.post("/api/v1/auth/apple", json={"identity_token": "a-tok"})
        client.post("/api/v1/auth/google", json={"id_token": "g-tok"})

        from src.connection import get_database

        with clean_driver.session(database=get_database()) as s:
            result = s.run(
                "MATCH (u:User {email: $email}) RETURN u, count(u) AS c",
                email=email,
            ).single()
            assert result["c"] == 1
            user = result["u"]
            assert user["apple_sub"] == "a-link-002"
            assert user["google_sub"] == "g-link-002"

    @patch("src.api.auth.routes.verify_apple_id_token")
    def test_magic_link_then_apple_preserves_session(self, mock_apple, client, clean_driver):
        from src.api.auth.tokens import create_magic_token

        email = "magic-apple@test.com"
        magic_token = create_magic_token(email)
        resp = client.post("/api/v1/auth/magic-link/verify", json={"token": magic_token})
        assert resp.status_code == 200

        mock_apple.return_value = {"email": email, "sub": "a-magic-003", "name": "Magic User"}
        resp = client.post("/api/v1/auth/apple", json={"identity_token": "a-tok"})
        assert resp.status_code == 200

        from src.connection import get_database

        with clean_driver.session(database=get_database()) as s:
            result = s.run(
                "MATCH (u:User {email: $email}) RETURN u, count(u) AS c",
                email=email,
            ).single()
            assert result["c"] == 1
            assert result["u"]["apple_sub"] == "a-magic-003"
