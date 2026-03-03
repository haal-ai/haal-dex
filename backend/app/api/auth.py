"""Auth endpoints — login and current-user info."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.middleware.auth import get_current_user
from app.models.auth import AuthToken, LoginRequest, UserContext
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_auth_service() -> AuthService:
    return AuthService()


@router.post("/login", response_model=None)
async def login(
    body: LoginRequest,
    auth_service: AuthService = Depends(_get_auth_service),
) -> dict:
    """Authenticate with username/password and receive a JWT token."""
    try:
        token: AuthToken = await auth_service.authenticate(body)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    return {
        "access_token": token.access_token,
        "token_type": token.token_type,
        "expires_in": token.expires_in,
        "user_id": token.user_id,
        "roles": token.roles,
    }


@router.get("/me")
async def me(user: UserContext = Depends(get_current_user)) -> dict:
    """Return the profile of the currently authenticated user."""
    return {
        "user_id": user.user_id,
        "username": user.username,
        "roles": user.roles,
    }
