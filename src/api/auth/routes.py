"""Auth routes — login, token management, and user info."""

from __future__ import annotations

import os
import time
import uuid
from collections import deque
from datetime import UTC, datetime
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


# --- Refresh-token store: rotation + revocation ------------------------------
# A refresh token is valid for REFRESH_TOKEN_EXPIRE_DAYS (14). Minting one and
# never recording it means a LEAKED token silently mints fresh access tokens for
# the whole window, with no denylist, no reuse detection and no logout — the only
# remedy would be rotating JWT_SECRET_KEY for every user at once. So persist the
# jti and rotate on every use: presenting an already-consumed jti is the signature
# of a stolen token being replayed, and the standard response is to revoke the
# entire token family (both the thief's copy and the victim's).
#
# The MERGE key is the jti, a uuid4 minted per token — globally unique, so the
# key is safe across users and cities.
_MERGE_REFRESH_TOKEN = """
MATCH (u:User {id: $user_id})
MERGE (t:RefreshToken {jti: $jti})
ON CREATE SET t.sid = $sid,
              t.family = $family,
              t.user_id = $user_id,
              t.issued_at = datetime(),
              t.expires_at = datetime($expires_at),
              t.used = false,
              t.revoked = false
MERGE (u)-[r:HAS_REFRESH_TOKEN]->(t)
ON CREATE SET r.id = randomUUID(), r.created_at = datetime()
"""

_LOOKUP_REFRESH_TOKEN = """
MATCH (t:RefreshToken {jti: $jti})
RETURN t.used AS used, t.revoked AS revoked, t.family AS family, t.user_id AS user_id
"""

_MARK_REFRESH_TOKEN_USED = "MATCH (t:RefreshToken {jti: $jti}) SET t.used = true"

_REVOKE_REFRESH_FAMILY = "MATCH (t:RefreshToken {family: $family}) SET t.revoked = true"

_REVOKE_ALL_FOR_USER = "MATCH (t:RefreshToken {user_id: $user_id}) SET t.revoked = true"

# Expired rows can never authenticate anything, so drop them opportunistically —
# otherwise the store grows by one node per login for the life of the deployment.
_DELETE_EXPIRED_REFRESH_TOKENS = """
MATCH (t:RefreshToken) WHERE t.expires_at < datetime() DETACH DELETE t
"""
_REFRESH_CLEANUP_INTERVAL_S = int(os.getenv("REFRESH_TOKEN_CLEANUP_INTERVAL_S", "3600"))
_last_refresh_cleanup = 0.0


def _issue_refresh_token(session: Session, user_id: str, session_id: str, token_family: str) -> str:
    """Mint a refresh token AND record it, so it can later be rotated/revoked."""
    global _last_refresh_cleanup

    token = create_refresh_token(user_id, session_id, token_family)
    payload = verify_token(token, "refresh")
    expires_at = datetime.fromtimestamp(payload["exp"], UTC).isoformat()
    session.run(
        _MERGE_REFRESH_TOKEN,
        jti=payload["jti"],
        sid=session_id,
        family=token_family,
        user_id=user_id,
        expires_at=expires_at,
    )

    now = time.monotonic()
    if now - _last_refresh_cleanup >= _REFRESH_CLEANUP_INTERVAL_S:
        _last_refresh_cleanup = now
        session.run(_DELETE_EXPIRED_REFRESH_TOKENS)

    return token


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
# Number of trusted reverse-proxy hops in front of the app. On Render there is
# exactly one edge proxy, so the real client IP is the entry
# ``_TRUSTED_PROXY_HOPS`` from the RIGHT end of X-Forwarded-For.
_TRUSTED_PROXY_HOPS = int(os.getenv("AUTH_TRUSTED_PROXY_HOPS", "1"))
# Optional global fixed-window cap (defense-in-depth). Per-IP limits are
# inherently bypassable at scale by genuine IP rotation, so also bound the TOTAL
# accepted magic-link sends per window across all clients. Set <=0 to disable.
_MAGIC_LINK_GLOBAL_RATE_LIMIT_MAX = int(os.getenv("MAGIC_LINK_GLOBAL_RATE_LIMIT_MAX", "60"))
_magic_link_rate_state: dict[str, deque[float]] = {}
_magic_link_global_hits: deque[float] = deque()
_magic_link_rate_lock = Lock()
_magic_link_last_sweep = 0.0


def _client_ip(request: Request) -> str:
    """Resolve the real client IP for rate-limiting.

    ``X-Forwarded-For`` is client-controllable: a caller can prepend arbitrary
    fake entries on the LEFT, so the leftmost hop can NOT be trusted as the
    identity — trusting it lets an attacker land every request in a fresh
    ``ip:`` bucket (a new spoofed IP each time), so the per-IP cap never fires
    and one host can email-bomb unlimited addresses through Resend.

    Instead we trust only our own edge. With ``_TRUSTED_PROXY_HOPS`` proxies in
    front of the app (1 on Render), the real client is the entry the innermost
    trusted proxy observed and appended — i.e. counting ``_TRUSTED_PROXY_HOPS``
    from the RIGHT of the header. Anything to the left of that is
    attacker-supplied and ignored. Fall back to the socket peer when the header
    is absent (direct connection / local dev).

    Behind a proxy ``request.client.host`` is the proxy peer — the SAME address
    for every external caller — so keying on it alone would collapse all
    clients into one bucket and lock legitimate first-time users out of
    passwordless login."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            idx = max(0, len(parts) - _TRUSTED_PROXY_HOPS)
            return parts[idx]
    if request.client:
        return request.client.host
    return "unknown"


def _sweep_magic_link_state_locked(now: float, cutoff: float) -> None:
    """Drop every key whose window is empty. Caller must hold the lock.

    The per-request reclaim below only ever revisits the two keys of the current
    request, so a key left holding a stale-but-non-empty deque (its client never
    came back) would be retained forever. Sweep the whole table once per window
    — O(keys) at most once every ``_MAGIC_LINK_RATE_LIMIT_WINDOW_S``."""
    global _magic_link_last_sweep
    if now - _magic_link_last_sweep < _MAGIC_LINK_RATE_LIMIT_WINDOW_S:
        return
    _magic_link_last_sweep = now
    for key in list(_magic_link_rate_state):
        hits = _magic_link_rate_state[key]
        while hits and hits[0] <= cutoff:
            hits.popleft()
        if not hits:
            del _magic_link_rate_state[key]


def _magic_link_rate_limit(request: Request, email: str) -> None:
    """Global, per-IP and per-email fixed-window guard. Raises HTTPException(429)
    when the global cap, the caller IP, or the target email has exceeded its
    allowance within the trailing window.

    The limiter's own state is attacker-reachable (keys derive from a header and
    a request body), so every exit path — including the 429 raise — reclaims any
    key left with an empty window. Without that, each rejected request would leak
    a permanent dict entry and an unauthenticated caller could grow the worker's
    RSS until the container is OOM-killed."""
    now = time.monotonic()
    cutoff = now - _MAGIC_LINK_RATE_LIMIT_WINDOW_S
    client_ip = _client_ip(request)
    keys = (f"ip:{client_ip}", f"email:{email.lower()}")
    with _magic_link_rate_lock:
        _sweep_magic_link_state_locked(now, cutoff)

        # Global cap FIRST, before any setdefault: once it trips, a flood cannot
        # mint further keys at all, which bounds the state under IP rotation.
        if _MAGIC_LINK_GLOBAL_RATE_LIMIT_MAX > 0:
            while _magic_link_global_hits and _magic_link_global_hits[0] <= cutoff:
                _magic_link_global_hits.popleft()
            if len(_magic_link_global_hits) >= _MAGIC_LINK_GLOBAL_RATE_LIMIT_MAX:
                retry_after = max(
                    1,
                    int(_magic_link_global_hits[0] + _MAGIC_LINK_RATE_LIMIT_WINDOW_S - now),
                )
                raise HTTPException(
                    status_code=429,
                    detail="Magic link requests are temporarily rate limited, please retry later",
                    headers={"Retry-After": str(retry_after)},
                )

        if _MAGIC_LINK_RATE_LIMIT_MAX <= 0:
            if _MAGIC_LINK_GLOBAL_RATE_LIMIT_MAX > 0:
                _magic_link_global_hits.append(now)
            return

        try:
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
            if _MAGIC_LINK_GLOBAL_RATE_LIMIT_MAX > 0:
                _magic_link_global_hits.append(now)
        finally:
            # Reclaim keys this request created but never filled (the 429 path
            # leaves the not-yet-checked key with an empty deque).
            for key in keys:
                if not _magic_link_rate_state.get(key):
                    _magic_link_rate_state.pop(key, None)


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
        refresh_token=_issue_refresh_token(session, user_id, session_id, token_family),
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
    jti = payload.get("jti")
    family = payload.get("family")
    session_id = payload.get("sid") or str(uuid.uuid4())

    # A refresh token that carries no jti/family predates the rotation store and
    # cannot be tracked or revoked — refuse it rather than honour it blindly.
    if not jti or not family:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is not rotatable, please sign in again",
        )

    record = session.run(_LOOKUP_REFRESH_TOKEN, jti=jti).single()
    if record is None or record["revoked"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is no longer valid",
        )

    if record["used"]:
        # Replay of an already-consumed token: either the legitimate client or a
        # thief holds a copy. We cannot tell which, so revoke the whole family —
        # the standard reuse-detection response — and force a fresh sign-in.
        session.run(_REVOKE_REFRESH_FAMILY, family=family)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token reuse detected, session revoked",
        )

    result = session.run("MATCH (u:User {id: $uid}) RETURN u.email AS email", uid=user_id).single()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    session.run(_MARK_REFRESH_TOKEN_USED, jti=jti)

    return TokenResponse(
        access_token=create_access_token(user_id, result["email"]),
        # Rotate: same sid + family, fresh jti. Returning the submitted token
        # would leave a single long-lived secret in flight for 14 days.
        refresh_token=_issue_refresh_token(session, user_id, session_id, family),
    )


@router.post("/logout", status_code=200)
def logout(
    body: RefreshRequest,
    session: Session = Depends(get_session),
):
    """Revoke the presented refresh token's family (sign out this device).

    Idempotent and never 401s: a client clearing its local tokens must be able to
    fire-and-forget this call even when the token it holds is already expired or
    unknown."""
    try:
        payload = verify_token(body.refresh_token, "refresh")
    except TokenError:
        return {"message": "Logged out"}

    family = payload.get("family")
    if family:
        session.run(_REVOKE_REFRESH_FAMILY, family=family)
    return {"message": "Logged out"}


@router.post("/logout-all", status_code=200)
def logout_all(
    current_user: dict = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Revoke every refresh token for the authenticated user (stolen-device case)."""
    session.run(_REVOKE_ALL_FOR_USER, user_id=current_user["id"])
    return {"message": "All sessions revoked"}


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
        refresh_token=_issue_refresh_token(session, user_id, session_id, token_family),
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
        refresh_token=_issue_refresh_token(session, user_id, session_id, token_family),
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
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
