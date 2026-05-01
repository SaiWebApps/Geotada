"""Magic link email delivery via Resend."""

from __future__ import annotations

import httpx

from src.api.auth.config import (
    FRONTEND_URL,
    MAGIC_LINK_FROM_EMAIL,
    RESEND_API_KEY,
)


class EmailDeliveryError(Exception):
    """Raised when email sending fails."""


def _build_magic_link(token: str) -> str:
    return f"{FRONTEND_URL}/auth?token={token}"


async def send_magic_link(email: str, token: str) -> None:
    link = _build_magic_link(token)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={
                "from": MAGIC_LINK_FROM_EMAIL,
                "to": [email],
                "subject": "Sign in to Ondoway",
                "html": (
                    "<h2>Sign in to Ondoway</h2>"
                    f'<p><a href="{link}">Click here to sign in</a></p>'
                    "<p>This link expires in 15 minutes.</p>"
                    "<p>If you didn't request this, ignore this email.</p>"
                ),
            },
            timeout=10.0,
        )

    if resp.status_code >= 400:
        raise EmailDeliveryError(
            f"Resend API returned {resp.status_code}: {resp.text}"
        )
