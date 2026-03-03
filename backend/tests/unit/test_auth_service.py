"""Unit tests for AuthService — JWT issuance, validation, and role checking."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import Settings
from app.models.auth import LoginRequest, UserContext
from app.services.auth_service import AuthService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _settings(**overrides) -> Settings:
    defaults = {
        "secret_key": "test-secret-key",
        "jwt_algorithm": "HS256",
        "jwt_expiration_minutes": 60,
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
def auth_service() -> AuthService:
    return AuthService(settings=_settings())


# ---------------------------------------------------------------------------
# authenticate()
# ---------------------------------------------------------------------------

class TestAuthenticate:
    """Tests for AuthService.authenticate()."""

    @pytest.mark.asyncio
    async def test_valid_admin_credentials(self, auth_service: AuthService):
        token = await auth_service.authenticate(LoginRequest("admin", "admin"))
        assert token.access_token
        assert token.token_type == "bearer"
        assert token.user_id == "user-001"
        assert "admin" in token.roles
        assert token.expires_in == 3600

    @pytest.mark.asyncio
    async def test_valid_user_credentials(self, auth_service: AuthService):
        token = await auth_service.authenticate(LoginRequest("user", "user"))
        assert token.user_id == "user-002"
        assert token.roles == ["user"]

    @pytest.mark.asyncio
    async def test_unknown_username_raises(self, auth_service: AuthService):
        with pytest.raises(ValueError, match="Invalid username or password"):
            await auth_service.authenticate(LoginRequest("nobody", "pass"))

    @pytest.mark.asyncio
    async def test_wrong_password_raises(self, auth_service: AuthService):
        with pytest.raises(ValueError, match="Invalid username or password"):
            await auth_service.authenticate(LoginRequest("admin", "wrong"))

    @pytest.mark.asyncio
    async def test_jwt_payload_contains_expected_claims(self, auth_service: AuthService):
        token = await auth_service.authenticate(LoginRequest("admin", "admin"))
        payload = jwt.decode(
            token.access_token, "test-secret-key", algorithms=["HS256"]
        )
        assert payload["sub"] == "user-001"
        assert payload["username"] == "admin"
        assert payload["roles"] == ["admin", "user"]
        assert "exp" in payload
        assert "iat" in payload


# ---------------------------------------------------------------------------
# validate_token()
# ---------------------------------------------------------------------------

class TestValidateToken:
    """Tests for AuthService.validate_token()."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user_context(self, auth_service: AuthService):
        auth_token = await auth_service.authenticate(LoginRequest("admin", "admin"))
        ctx = await auth_service.validate_token(auth_token.access_token)
        assert isinstance(ctx, UserContext)
        assert ctx.user_id == "user-001"
        assert ctx.username == "admin"
        assert "admin" in ctx.roles
        assert ctx.token == auth_token.access_token

    @pytest.mark.asyncio
    async def test_expired_token_raises(self, auth_service: AuthService):
        # Manually craft an already-expired token
        payload = {
            "sub": "user-001",
            "username": "admin",
            "roles": ["admin"],
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=5),
        }
        expired_token = jwt.encode(payload, "test-secret-key", algorithm="HS256")
        with pytest.raises(ValueError, match="Token has expired"):
            await auth_service.validate_token(expired_token)

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self, auth_service: AuthService):
        with pytest.raises(ValueError, match="Invalid token"):
            await auth_service.validate_token("not.a.valid.jwt")

    @pytest.mark.asyncio
    async def test_wrong_secret_raises(self, auth_service: AuthService):
        payload = {
            "sub": "user-001",
            "username": "admin",
            "roles": ["admin"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        bad_token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        with pytest.raises(ValueError, match="Invalid token"):
            await auth_service.validate_token(bad_token)


# ---------------------------------------------------------------------------
# has_role()
# ---------------------------------------------------------------------------

class TestHasRole:
    """Tests for AuthService.has_role()."""

    def test_user_with_role(self, auth_service: AuthService):
        ctx = UserContext(user_id="u1", username="a", roles=["admin", "user"], token="t")
        assert auth_service.has_role(ctx, "admin") is True

    def test_user_without_role(self, auth_service: AuthService):
        ctx = UserContext(user_id="u1", username="a", roles=["user"], token="t")
        assert auth_service.has_role(ctx, "admin") is False

    def test_empty_roles(self, auth_service: AuthService):
        ctx = UserContext(user_id="u1", username="a", roles=[], token="t")
        assert auth_service.has_role(ctx, "user") is False
