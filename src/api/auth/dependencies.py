"""FastAPI dependency for extracting the current authenticated user from a Bearer token."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from neo4j import Session

from src.api.auth.tokens import TokenError, verify_token
from src.api.dependencies import get_session

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session),
) -> dict:
    try:
        payload = verify_token(credentials.credentials, "access")
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    user_id = payload["sub"]
    result = session.run(
        "MATCH (u:User {id: $uid}) RETURN u", uid=user_id
    ).single()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    node = result["u"]
    return {
        "id": node.get("id"),
        "email": node.get("email"),
        "created_at": str(node.get("created_at")) if node.get("created_at") else None,
        "last_logon": str(node.get("last_logon")) if node.get("last_logon") else None,
    }
