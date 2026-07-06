"""Auth configuration loaded from environment variables."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Minimum acceptable length (in characters) for HS256 signing secrets. A short
# or empty secret makes JWTs trivially forgeable; render.yaml provisions these
# with generateValue:true, which is comfortably longer than this floor.
_MIN_SECRET_LEN: int = 32

# Fixed, obviously-fake stand-in used ONLY in non-production contexts (the test
# suite, or an explicit local opt-in). It is deterministic and clearly not a
# real secret, but it is never the empty string, so tokens minted in dev are
# not signed over "" and a missing env var can never silently downgrade the
# production deploy to a trivially-forgeable key.
_DEV_PLACEHOLDER_SECRET: str = "ondoway-insecure-dev-secret-do-not-use-in-production"


def _allow_insecure_secrets() -> bool:
    """Whether an empty/short signing secret may fall back to a dev placeholder.

    True only outside a real deploy: while running under pytest, or when a
    developer explicitly opts in via ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS. Never
    true on the production deploy, which loads real generated secrets and does
    not set this flag or run under pytest.
    """
    if os.getenv("ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS", "").lower() in {"1", "true", "yes"}:
        return True
    return "pytest" in sys.modules


def _load_signing_secret(env_var: str) -> str:
    """Load a JWT signing secret, failing closed on an empty/short value.

    Raises RuntimeError at import time if the secret is missing or too short,
    so the app refuses to start rather than accepting a trivially-forgeable
    HS256 key. In non-production contexts (see _allow_insecure_secrets) a
    deterministic non-empty dev placeholder is substituted instead.
    """
    value = os.getenv(env_var, "")
    if len(value) >= _MIN_SECRET_LEN:
        return value
    if _allow_insecure_secrets():
        return _DEV_PLACEHOLDER_SECRET
    raise RuntimeError(
        f"{env_var} is unset or shorter than {_MIN_SECRET_LEN} characters. "
        "Refusing to start with an empty/trivially-forgeable HS256 signing key. "
        "Set a strong secret (render.yaml uses generateValue:true), or for local "
        "development export ONDOWAY_ALLOW_INSECURE_AUTH_SECRETS=1 to use a dev placeholder."
    )


JWT_SECRET_KEY: str = _load_signing_secret("JWT_SECRET_KEY")
MAGIC_LINK_SECRET_KEY: str = _load_signing_secret("MAGIC_LINK_SECRET_KEY")
GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
MAGIC_LINK_PROVIDER: str = os.getenv("MAGIC_LINK_PROVIDER", "console")
RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
APPLE_TEAM_ID: str = os.getenv("APPLE_TEAM_ID", "")
BUNDLE_ID: str = "com.ondoway.app"

FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
MAGIC_LINK_FROM_EMAIL: str = os.getenv("MAGIC_LINK_FROM_EMAIL", "onboarding@resend.dev")

ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
REFRESH_TOKEN_EXPIRE_DAYS: int = 14
MAGIC_LINK_EXPIRE_MINUTES: int = 15

JWT_ALGORITHM: str = "HS256"
