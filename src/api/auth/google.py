"""Google ID token verification via google-auth library."""

from __future__ import annotations

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from src.api.auth.config import GOOGLE_CLIENT_ID
from src.api.auth.tokens import TokenError


def verify_google_id_token(token: str) -> dict:
    try:
        idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), GOOGLE_CLIENT_ID)
    except ValueError as exc:
        raise TokenError(f"Invalid Google ID token: {exc}") from exc
    except Exception as exc:
        raise TokenError(f"Google token verification failed: {exc}") from exc

    email = idinfo.get("email")
    if not email:
        raise TokenError("Google ID token missing email claim")

    if not idinfo.get("email_verified"):
        raise TokenError("Google email not verified")

    return {
        "email": email,
        "sub": idinfo.get("sub", ""),
        "name": idinfo.get("name", ""),
    }
