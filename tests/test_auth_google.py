"""Unit tests for Google ID token verification."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.api.auth.google import verify_google_id_token
from src.api.auth.tokens import TokenError


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
