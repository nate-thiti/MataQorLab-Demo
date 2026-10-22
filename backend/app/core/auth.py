from __future__ import annotations

from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.supabase import get_supabase_client

_bearer = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        supabase = get_supabase_client()
        user_response = supabase.auth.get_user(token)
        user = user_response.user if user_response else None
        if not user or not user.id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        return str(user.id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


def require_matching_user_id(body_user_id: str, auth_user_id: str) -> str:
    if body_user_id != auth_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return auth_user_id


def validate_supabase_storage_url(url: str) -> None:
    """Allow only signed URLs from this project's Supabase Storage (SSRF guard)."""
    if not url or not isinstance(url, str):
        raise HTTPException(status_code=400, detail="URL is required")

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("https", "http"):
        raise HTTPException(status_code=400, detail="Invalid storage URL scheme")

    supabase_host = urlparse(settings.SUPABASE_URL).netloc.lower()
    if parsed.netloc.lower() != supabase_host:
        raise HTTPException(status_code=400, detail="URL must point to project storage")

    path = parsed.path or ""
    if "/storage/v1/object/" not in path:
        raise HTTPException(status_code=400, detail="Invalid Supabase storage URL")
