"""Live integration test: magic link email delivery via Resend.

Requires:
- RESEND_API_KEY set in .env
- MAGIC_LINK_PROVIDER=resend
- MAGIC_LINK_FROM_EMAIL set to a verified domain
- Network access to api.resend.com (proxy bypass configured)
"""

from __future__ import annotations

import pytest

from src.api.auth.config import MAGIC_LINK_PROVIDER, RESEND_API_KEY
from src.api.auth.email import EmailDeliveryError, send_magic_link
from src.api.auth.tokens import create_magic_token

_can_send = MAGIC_LINK_PROVIDER == "resend" and bool(RESEND_API_KEY)

needs_resend = pytest.mark.skipif(
    not _can_send,
    reason="MAGIC_LINK_PROVIDER != 'resend' or RESEND_API_KEY not set",
)


@needs_resend
class TestLiveEmailDelivery:
    """Tests that actually hit the Resend API — not mocked."""

    @pytest.mark.anyio
    async def test_send_magic_link_succeeds(self):
        token = create_magic_token("darklordofthesithtitan@gmail.com")
        await send_magic_link("darklordofthesithtitan@gmail.com", token)

    @pytest.mark.anyio
    async def test_send_magic_link_returns_without_error(self):
        token = create_magic_token("darklordofthesithtitan@gmail.com")
        try:
            await send_magic_link("darklordofthesithtitan@gmail.com", token)
        except EmailDeliveryError as e:
            pytest.fail(f"Email delivery failed: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected error: {type(e).__name__}: {e}")

    @pytest.mark.anyio
    async def test_api_endpoint_sends_email(self):
        from fastapi.testclient import TestClient

        from src.api.app import create_app

        app = create_app()
        client = TestClient(app)

        resp = client.post(
            "/api/v1/auth/magic-link/request",
            json={"email": "darklordofthesithtitan@gmail.com"},
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert resp.json()["message"] == "Magic link sent"

    @pytest.mark.anyio
    async def test_invalid_api_key_returns_502(self):
        from unittest.mock import patch

        with patch("src.api.auth.email.RESEND_API_KEY", "invalid-key"):
            token = create_magic_token("test@example.com")
            with pytest.raises(EmailDeliveryError, match="4"):
                await send_magic_link("test@example.com", token)
