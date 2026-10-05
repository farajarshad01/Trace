from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from supabase import Client, create_client

from app.core.config import settings


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """One shared client instead of a new one per request."""

    if not settings.SUPABASE_URL:
        raise RuntimeError("SUPABASE_URL is not configured.")

    if not settings.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not configured.")

    return create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY,
    )


@dataclass(frozen=True)
class AuthUser:
    id: UUID
    email: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


# NOTE: deliberately a plain ``def`` (not ``async def``). Verifying the token
# can make a blocking network call; FastAPI runs sync dependencies in a
# threadpool, so it no longer stalls the event loop for every request.
def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> AuthUser:
    if not authorization:
        raise _unauthorized("Authorization header is missing.")

    if not authorization.startswith("Bearer "):
        raise _unauthorized("Invalid authorization header.")

    token = authorization.removeprefix("Bearer ").strip()

    if not token:
        raise _unauthorized("Access token is missing.")

    try:
        response = get_supabase_client().auth.get_claims(token)
    except Exception:
        raise _unauthorized("Invalid or expired access token.")

    claims = (response or {}).get("claims", {}) or {}
    user_id = claims.get("sub")

    if not user_id:
        raise _unauthorized("User ID was not found in access token.")

    try:
        parsed_id = UUID(user_id)
    except ValueError:
        raise _unauthorized("Invalid user ID.")

    metadata = claims.get("user_metadata") or {}

    return AuthUser(
        id=parsed_id,
        email=claims.get("email") or metadata.get("email"),
        full_name=metadata.get("full_name") or metadata.get("name"),
        avatar_url=metadata.get("avatar_url") or metadata.get("picture"),
    )


def get_current_user_id(
    user: Annotated[AuthUser, Depends(get_current_user)],
) -> UUID:
    return user.id
