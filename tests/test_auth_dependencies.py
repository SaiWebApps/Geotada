"""Unit tests for get_current_user dependency."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.auth.dependencies import get_current_user
from src.api.auth.tokens import create_access_token, create_refresh_token


class TestGetCurrentUserUnit:
    """Unit tests — mock the Neo4j session, test token logic only."""

    def _make_credentials(self, token: str):
        creds = MagicMock()
        creds.credentials = token
        return creds

    def _make_session_with_user(self, user_id: str, email: str):
        node = {"id": user_id, "email": email, "created_at": None, "last_logon": None}
        result = MagicMock()
        result.single.return_value = {"u": node}
        session = MagicMock()
        session.run.return_value = result
        return session

    def _make_session_no_user(self):
        result = MagicMock()
        result.single.return_value = None
        session = MagicMock()
        session.run.return_value = result
        return session

    def test_valid_access_token_returns_user(self):
        token = create_access_token("user-42", "test@ondoway.app")
        creds = self._make_credentials(token)
        session = self._make_session_with_user("user-42", "test@ondoway.app")

        user = get_current_user(creds, session)

        assert user["id"] == "user-42"
        assert user["email"] == "test@ondoway.app"

    def test_expired_token_raises_401(self):
        with patch("src.api.auth.tokens.ACCESS_TOKEN_EXPIRE_MINUTES", -1):
            token = create_access_token("user-42", "test@ondoway.app")

        creds = self._make_credentials(token)
        session = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(creds, session)
        assert exc_info.value.status_code == 401

    def test_invalid_token_raises_401(self):
        creds = self._make_credentials("not.a.valid.jwt")
        session = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(creds, session)
        assert exc_info.value.status_code == 401

    def test_refresh_token_rejected(self):
        token = create_refresh_token("user-42", "sess-1", "fam-1")
        creds = self._make_credentials(token)
        session = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(creds, session)
        assert exc_info.value.status_code == 401

    def test_user_not_in_db_raises_401(self):
        token = create_access_token("deleted-user", "gone@ondoway.app")
        creds = self._make_credentials(token)
        session = self._make_session_no_user()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(creds, session)
        assert exc_info.value.status_code == 401

    def test_tampered_token_raises_401(self):
        token = create_access_token("user-42", "test@ondoway.app")
        tampered = token[:-4] + "XXXX"
        creds = self._make_credentials(tampered)
        session = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            get_current_user(creds, session)
        assert exc_info.value.status_code == 401
