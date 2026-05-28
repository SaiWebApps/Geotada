"""JWT token creation and verification for access, refresh, and magic link tokens."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from src.api.auth.config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    JWT_ALGORITHM,
    JWT_SECRET_KEY,
    MAGIC_LINK_EXPIRE_MINUTES,
    MAGIC_LINK_SECRET_KEY,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


class TokenError(Exception):
    """Raised when token creation or verification fails."""


def create_access_token(user_id: str, email: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "email": email,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str, session_id: str, token_family: str) -> str:
    now = datetime.now(UTC)
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "sid": session_id,
        "family": token_family,
        "jti": jti,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_magic_token(email: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "email": email,
        "type": "magic",
        "iat": now,
        "exp": now + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, MAGIC_LINK_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_token(token: str, expected_type: str) -> dict:
    """Verify a JWT and return its payload. Raises TokenError on failure."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(f"Invalid token: {exc}") from exc

    if payload.get("type") != expected_type:
        raise TokenError(
            f"Wrong token type: expected {expected_type!r}, got {payload.get('type')!r}"
        )
    return payload


def verify_magic_token(token: str) -> str:
    """Verify a magic link token and return the email. Raises TokenError on failure."""
    try:
        payload = jwt.decode(token, MAGIC_LINK_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Magic link has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError(f"Invalid magic link: {exc}") from exc

    if payload.get("type") != "magic":
        raise TokenError(f"Wrong token type: expected 'magic', got {payload.get('type')!r}")

    email = payload.get("email")
    if not email:
        raise TokenError("Magic link token missing email")
    return email
