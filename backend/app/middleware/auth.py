"""FastAPI dependency-injection helpers for authentication and authorization."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.models.auth import UserContext
from app.services.auth_service import AuthService

# ---------------------------------------------------------------------------
# Shared instances
# ---------------------------------------------------------------------------

_bearer_scheme = HTTPBearer(auto_error=False)


def _get_auth_service() -> AuthService:
    """Return a default AuthService (overridable in tests via app.dependency_overrides)."""
    return AuthService()


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    auth_service: AuthService = Depends(_get_auth_service),
) -> UserContext:
    """Extract and validate the Bearer token from the Authorization header.

    Returns the authenticated ``UserContext``.
    Raises ``HTTPException(401)`` when the token is missing or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = await auth_service.validate_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def require_admin(
    user: UserContext = Depends(get_current_user),
    auth_service: AuthService = Depends(_get_auth_service),
) -> UserContext:
    """Ensure the current user has the ``admin`` role.

    Returns the authenticated ``UserContext`` if authorized.
    Raises ``HTTPException(403)`` when the user lacks the admin role.
    """
    if not auth_service.has_role(user, "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user
