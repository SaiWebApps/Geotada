"""Auth routes — login, token management, and user info."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import Session

from src.api.auth.dependencies import get_current_user
from src.api.auth.email import EmailDeliveryError, send_magic_link
from src.api.auth.google import verify_google_id_token
from src.api.auth.schemas import (
    GoogleAuthRequest,
    MagicLinkRequest,
    MagicLinkVerifyRequest,
    OnboardingRequest,
    OnboardingResponse,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from src.api.auth.tokens import (
    TokenError,
    create_access_token,
    create_magic_token,
    create_refresh_token,
    verify_magic_token,
    verify_token,
)
from src.api.dependencies import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

_MERGE_USER = """
MERGE (u:User {email: $email})
SET u.id = coalesce(u.id, randomUUID()),
    u.created_at = coalesce(u.created_at, datetime()),
    u.last_logon = datetime()
RETURN u
"""


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)


@router.post("/magic-link/request", status_code=200)
async def magic_link_request(body: MagicLinkRequest):
    token = create_magic_token(body.email)
    try:
        await send_magic_link(body.email, token)
    except EmailDeliveryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to send magic link email: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Email delivery connection error: {type(exc).__name__}: {exc}",
        ) from exc
    return {"message": "Magic link sent"}


@router.post("/magic-link/verify", response_model=TokenResponse)
def magic_link_verify(
    body: MagicLinkVerifyRequest,
    session: Session = Depends(get_session),
):
    try:
        email = verify_magic_token(body.token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    result = session.run(_MERGE_USER, email=email).single()
    user_node = result["u"]
    user_id = user_node.get("id")

    session_id = str(uuid.uuid4())
    token_family = str(uuid.uuid4())

    return TokenResponse(
        access_token=create_access_token(user_id, email),
        refresh_token=create_refresh_token(user_id, session_id, token_family),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    body: RefreshRequest,
    session: Session = Depends(get_session),
):
    try:
        payload = verify_token(body.refresh_token, "refresh")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    user_id = payload["sub"]
    result = session.run(
        "MATCH (u:User {id: $uid}) RETURN u.email AS email", uid=user_id
    ).single()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return TokenResponse(
        access_token=create_access_token(user_id, result["email"]),
        refresh_token=body.refresh_token,
    )


@router.post("/google", response_model=TokenResponse)
def google_auth(
    body: GoogleAuthRequest,
    session: Session = Depends(get_session),
):
    try:
        google_info = verify_google_id_token(body.id_token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    email = google_info["email"]
    result = session.run(_MERGE_USER, email=email).single()
    user_node = result["u"]
    user_id = user_node.get("id")

    session_id = str(uuid.uuid4())
    token_family = str(uuid.uuid4())

    return TokenResponse(
        access_token=create_access_token(user_id, email),
        refresh_token=create_refresh_token(user_id, session_id, token_family),
    )


_ONBOARDING_QUERY = """
MATCH (u:User {id: $user_id})
MERGE (u)-[hp:HAS_PROFILE]->(p:Profile {display_name: $display_name})
ON CREATE SET p.id = randomUUID(), p.created_at = datetime(),
              hp.id = randomUUID(), hp.created_at = datetime()
WITH p
UNWIND $lens_ids AS lid
MATCH (lens:Lens {id: lid, is_parent: false})
MERGE (p)-[r:PREFERS_LENS]->(lens)
ON CREATE SET r.id = randomUUID(), r.created_at = datetime()
RETURN p.id AS profile_id, p.display_name AS display_name, count(lens) AS lens_count
"""


@router.post("/onboarding/complete", response_model=OnboardingResponse)
def onboarding_complete(
    body: OnboardingRequest,
    current_user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    if len(body.lens_ids) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least 3 lenses required",
        )

    user_id = current_user["id"]
    email = current_user["email"]
    display_name = email.split("@")[0]

    result = session.run(
        _ONBOARDING_QUERY,
        user_id=user_id,
        display_name=display_name,
        lens_ids=body.lens_ids,
    ).single()

    if result is None or result["lens_count"] == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User or lenses not found",
        )

    return OnboardingResponse(
        profile_id=result["profile_id"],
        display_name=result["display_name"],
        lens_count=result["lens_count"],
    )
