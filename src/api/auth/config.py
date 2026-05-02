"""Auth configuration loaded from environment variables."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "")
MAGIC_LINK_SECRET_KEY: str = os.getenv("MAGIC_LINK_SECRET_KEY", "")
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
