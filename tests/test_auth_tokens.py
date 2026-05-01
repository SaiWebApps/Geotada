"""Unit tests for JWT token service — no Neo4j needed."""

from __future__ import annotations

import time
from unittest.mock import patch

import jwt
import pytest

from src.api.auth.config import JWT_ALGORITHM
from src.api.auth.tokens import (
    TokenError,
    create_access_token,
    create_magic_token,
    create_refresh_token,
    verify_magic_token,
    verify_token,
)


class TestAccessToken:
    def test_round_trip(self):
        token = create_access_token("user-123", "test@ondoway.app")
        payload = verify_token(token, "access")
        assert payload["sub"] == "user-123"
        assert payload["email"] == "test@ondoway.app"
        assert payload["type"] == "access"

    def test_contains_iat_and_exp(self):
        token = create_access_token("user-123", "test@ondoway.app")
        payload = verify_token(token, "access")
        assert "iat" in payload
        assert "exp" in payload
        assert payload["exp"] > payload["iat"]

    def test_expired_token_rejected(self):
        with patch("src.api.auth.tokens.ACCESS_TOKEN_EXPIRE_MINUTES", -1):
            token = create_access_token("user-123", "test@ondoway.app")
        with pytest.raises(TokenError, match="expired"):
            verify_token(token, "access")

    def test_wrong_type_rejected(self):
        token = create_access_token("user-123", "test@ondoway.app")
        with pytest.raises(TokenError, match="Wrong token type"):
            verify_token(token, "refresh")

    def test_tampered_signature_rejected(self):
        token = create_access_token("user-123", "test@ondoway.app")
        tampered = token[:-4] + "XXXX"
        with pytest.raises(TokenError, match="Invalid token"):
            verify_token(tampered, "access")

    def test_garbage_rejected(self):
        with pytest.raises(TokenError, match="Invalid token"):
            verify_token("not.a.jwt", "access")


class TestRefreshToken:
    def test_round_trip(self):
        token = create_refresh_token("user-123", "session-456", "family-789")
        payload = verify_token(token, "refresh")
        assert payload["sub"] == "user-123"
        assert payload["sid"] == "session-456"
        assert payload["family"] == "family-789"
        assert payload["type"] == "refresh"
        assert "jti" in payload

    def test_jti_is_unique(self):
        t1 = create_refresh_token("u", "s", "f")
        t2 = create_refresh_token("u", "s", "f")
        p1 = verify_token(t1, "refresh")
        p2 = verify_token(t2, "refresh")
        assert p1["jti"] != p2["jti"]

    def test_expired_token_rejected(self):
        with patch("src.api.auth.tokens.REFRESH_TOKEN_EXPIRE_DAYS", -1):
            token = create_refresh_token("u", "s", "f")
        with pytest.raises(TokenError, match="expired"):
            verify_token(token, "refresh")


class TestMagicToken:
    def test_round_trip(self):
        token = create_magic_token("user@ondoway.app")
        email = verify_magic_token(token)
        assert email == "user@ondoway.app"

    def test_expired_token_rejected(self):
        with patch("src.api.auth.tokens.MAGIC_LINK_EXPIRE_MINUTES", -1):
            token = create_magic_token("user@ondoway.app")
        with pytest.raises(TokenError, match="expired"):
            verify_magic_token(token)

    def test_wrong_key_rejected(self):
        payload = {
            "email": "user@ondoway.app",
            "type": "magic",
            "exp": time.time() + 600,
        }
        token = jwt.encode(payload, "wrong-secret", algorithm=JWT_ALGORITHM)
        with pytest.raises(TokenError, match="Invalid magic link"):
            verify_magic_token(token)

    def test_access_token_rejected_as_magic(self):
        token = create_access_token("user-123", "test@ondoway.app")
        with pytest.raises(TokenError, match="Wrong token type"):
            verify_magic_token(token)

    def test_magic_token_rejected_as_access(self):
        token = create_magic_token("user@ondoway.app")
        with pytest.raises(TokenError, match="Wrong token type"):
            verify_token(token, "access")


class TestCrossTokenSafety:
    def test_refresh_token_not_usable_as_access(self):
        token = create_refresh_token("u", "s", "f")
        with pytest.raises(TokenError, match="Wrong token type"):
            verify_token(token, "access")

    def test_access_token_not_usable_as_refresh(self):
        token = create_access_token("u", "e@test.com")
        with pytest.raises(TokenError, match="Wrong token type"):
            verify_token(token, "refresh")
