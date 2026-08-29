"""Pydantic request/response models for auth endpoints."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkVerifyRequest(BaseModel):
    token: str


class GoogleAuthRequest(BaseModel):
    id_token: str


class AppleAuthRequest(BaseModel):
    identity_token: str
    nonce: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    created_at: str | None = None
    last_logon: str | None = None


class OnboardingRequest(BaseModel):
    lens_ids: list[str]


class OnboardingResponse(BaseModel):
    profile_id: str
    display_name: str
    lens_count: int


class WorkbenchSessionResponse(BaseModel):
    """The editorial workbench's own identity: a real user, profile and access token.

    No refresh token, deliberately: this is a local operator session that can be
    re-minted by asking again, so there is nothing to rotate and nothing worth
    leaving in flight for fourteen days.
    """

    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    profile_id: str
