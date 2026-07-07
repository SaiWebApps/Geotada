"""Auth routes — login, token management, and user info."""

from __future__ import annotations

import os
import time
import uuid
from collections import deque
from threading import Lock

from fastapi import APIRouter, Depends, HTTPException, Request, status
from neo4j import Session

from src.api.auth.apple import verify_apple_id_token
from src.api.auth.dependencies import get_current_user
from src.api.auth.email import EmailDeliveryError, send_magic_link
from src.api.auth.google import verify_google_id_token
from src.api.auth.schemas import (
    AppleAuthRequest,
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

_FIND_BY_GOOGLE_SUB = "MATCH (u:User {google_sub: $sub}) RETURN u"
_SET_GOOGLE_SUB = """
MATCH (u:User {email: $email})
SET u.google_sub = coalesce(u.google_sub, $google_sub)
"""

_FIND_BY_APPLE_SUB = "MATCH (u:User {apple_sub: $sub}) RETURN u"
_SET_APPLE_SUB = """
MATCH (u:User {email: $email})
SET u.apple_sub = coalesce(u.apple_sub, $apple_sub)
"""


# --- Abuse guard: magic-link request ----------------------------------------
# /auth/magic-link/request is unauthenticated and each call sends a real email
# via Resend (billed, and lands in a victim's inbox). Left unguarded, an
# attacker can email-bomb any address and burn the Resend quota. Mirror the
# /feedback rate limiter: a fixed-window counter keyed by BOTH the caller IP
# (stops one host fanning out to many victims) AND the target email (stops many
# IPs bombing one victim). In-process only (per worker); a multi-worker Render
# deploy would need a shared store (e.g. Redis) for a hard guarantee.
_MAGIC_LINK_RATE_LIMIT_MAX = int(os.getenv("MAGIC_LINK_RATE_LIMIT_MAX", "5"))
_MAGIC_LINK_RATE_LIMIT_WINDOW_S = int(os.getenv("MAGIC_LINK_RATE_LIMIT_WINDOW_S", "60"))
_magic_link_rate_state: dict[str, deque[float]] = {}
_magic_link_rate_lock = Lock()


def _client_ip(request: Request) -> str:
    """Resolve the real client IP for rate-limiting.

    On Render (and any reverse proxy) uvicorn is not started with
    --forwarded-allow-ips, so ``request.client.host`` is the proxy peer — the
    SAME address for every external caller. That collapses all clients into a
    single ``ip:`` bucket, so once any few callers trip the window a legitimate
    first-time user is locked out of passwordless login (a login-availability
    DoS) even though their own per-email bucket is empty. Derive the originating
    client from the leftmost entry of ``X-Forwarded-For`` (the edge appends the
    real client IP there), falling back to the socket peer when the header is
    absent (direct connection / local dev). Mirrors
    src/api/routes/feedback.py::_client_ip."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Leftmost hop is the original client; strip whitespace and ignore
        # empty segments from a malformed header.
        for part in forwarded.split(","):
            candidate = part.strip()
            if candidate:
                return candidate
    if request.client:
        return request.client.host
    return "unknown"


def _magic_link_rate_limit(request: Request, email: str) -> None:
    """Per-IP and per-email fixed-window guard. Raises HTTPException(429) when
    either the caller IP or the target email has exceeded
    _MAGIC_LINK_RATE_LIMIT_MAX requests within the trailing window."""
    if _MAGIC_LINK_RATE_LIMIT_MAX <= 0:
        return
    client_ip = _client_ip(request)
    keys = (f"ip:{client_ip}", f"email:{email.lower()}")
    now = time.monotonic()
    cutoff = now - _MAGIC_LINK_RATE_LIMIT_WINDOW_S
    with _magic_link_rate_lock:
        # Prune both keys first so we never mint a token when either is over cap.
        for key in keys:
            hits = _magic_link_rate_state.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= _MAGIC_LINK_RATE_LIMIT_MAX:
                retry_after = max(1, int(hits[0] + _MAGIC_LINK_RATE_LIMIT_WINDOW_S - now))
                raise HTTPException(
                    status_code=429,
                    detail="Too many magic link requests, please retry later",
                    headers={"Retry-After": str(retry_after)},
                )
        for key in keys:
            _magic_link_rate_state[key].append(now)


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**current_user)


@router.post("/magic-link/request", status_code=200)
async def magic_link_request(request: Request, body: MagicLinkRequest):
    _magic_link_rate_limit(request, body.email)
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
    result = session.run("MATCH (u:User {id: $uid}) RETURN u.email AS email", uid=user_id).single()

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
    google_sub = google_info.get("sub", "")

    existing = session.run(_FIND_BY_GOOGLE_SUB, sub=google_sub).single() if google_sub else None
    if existing:
        user_node = existing["u"]
        email = user_node["email"]
    else:
        result = session.run(_MERGE_USER, email=email).single()
        user_node = result["u"]

    user_id = user_node.get("id")

    if google_sub:
        session.run(_SET_GOOGLE_SUB, email=email, google_sub=google_sub)

    session_id = str(uuid.uuid4())
    token_family = str(uuid.uuid4())

    return TokenResponse(
        access_token=create_access_token(user_id, email),
        refresh_token=create_refresh_token(user_id, session_id, token_family),
    )


@router.post("/apple", response_model=TokenResponse)
def apple_auth(
    body: AppleAuthRequest,
    session: Session = Depends(get_session),
):
    try:
        apple_info = verify_apple_id_token(body.identity_token, nonce=body.nonce)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    email = apple_info["email"]
    apple_sub = apple_info.get("sub", "")

    existing = session.run(_FIND_BY_APPLE_SUB, sub=apple_sub).single() if apple_sub else None
    if existing:
        user_node = existing["u"]
        email = user_node["email"]
    else:
        result = session.run(_MERGE_USER, email=email).single()
        user_node = result["u"]

    user_id = user_node.get("id")

    if apple_sub:
        session.run(_SET_APPLE_SUB, email=email, apple_sub=apple_sub)

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
