"""Apple ID token verification via JWKS (Sign in with Apple)."""

from __future__ import annotations

import hashlib
from datetime import timedelta

import jwt
from jwt import PyJWKClient

from src.api.auth.config import BUNDLE_ID
from src.api.auth.tokens import TokenError

APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"

_jwks_client = PyJWKClient(APPLE_JWKS_URL, lifespan=3600)


def verify_apple_id_token(token: str, nonce: str | None = None) -> dict:
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=BUNDLE_ID,
            issuer=APPLE_ISSUER,
            options={"require": ["exp", "iat", "sub"]},
            leeway=timedelta(seconds=30),
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Apple ID token has expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise TokenError(f"Apple ID token audience mismatch: {exc}") from exc
    except jwt.InvalidIssuerError as exc:
        raise TokenError(f"Apple ID token issuer mismatch: {exc}") from exc
    except (jwt.InvalidTokenError, Exception) as exc:
        raise TokenError(f"Apple token verification failed: {exc}") from exc

    if nonce is not None:
        token_nonce = payload.get("nonce")
        expected_hash = hashlib.sha256(nonce.encode()).hexdigest()
        if token_nonce != expected_hash:
            raise TokenError("Apple ID token nonce mismatch")

    email = payload.get("email")
    if not email:
        raise TokenError("Apple ID token missing email claim")

    return {
        "email": email,
        "sub": payload.get("sub", ""),
        "name": payload.get("name", ""),
    }
