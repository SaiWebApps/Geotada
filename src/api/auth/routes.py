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
