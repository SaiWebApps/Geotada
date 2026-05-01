"""Unit tests for magic link email delivery."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.api.auth.email import EmailDeliveryError, _build_magic_link, send_magic_link


class TestBuildMagicLink:
    def test_link_contains_token(self):
        link = _build_magic_link("test-token-123")
        assert "test-token-123" in link

    def test_link_uses_hash_fragment_routing(self):
        link = _build_magic_link("tok")
        assert "/#/auth/callback?token=tok" in link

    @patch("src.api.auth.email.FRONTEND_URL", "https://app.ondoway.com")
    def test_link_uses_configured_frontend_url(self):
        link = _build_magic_link("tok")
        assert link.startswith("https://app.ondoway.com/")


class TestSendMagicLink:
    @pytest.mark.anyio
    async def test_sends_correct_request_to_resend(self):
        mock_response = httpx.Response(200, json={"id": "email-123"})

        with patch("src.api.auth.email.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await send_magic_link("user@example.com", "magic-token-xyz")

            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            assert call_kwargs[0][0] == "https://api.resend.com/emails"
            body = call_kwargs[1]["json"]
            assert body["to"] == ["user@example.com"]
            assert body["subject"] == "Sign in to Ondoway"
            assert "magic-token-xyz" in body["html"]

    @pytest.mark.anyio
    async def test_raises_on_resend_api_failure(self):
        mock_response = httpx.Response(403, text="Invalid API key")

        with patch("src.api.auth.email.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            with pytest.raises(EmailDeliveryError, match="403"):
                await send_magic_link("user@example.com", "tok")

    @pytest.mark.anyio
    async def test_email_html_contains_clickable_link(self):
        mock_response = httpx.Response(200, json={"id": "email-123"})

        with patch("src.api.auth.email.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await send_magic_link("user@example.com", "abc123")

            body = mock_client.post.call_args[1]["json"]
            assert '<a href="' in body["html"]
            assert "abc123" in body["html"]
