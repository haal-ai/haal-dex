"""Unit tests for auth middleware and auth API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.models.auth import LoginRequest
from app.services.auth_service import AuthService


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def admin_token(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    return resp.json()["access_token"]


@pytest.fixture
async def user_token(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"username": "user", "password": "user"},
    )
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

class TestLogin:
    @pytest.mark.asyncio
    async def test_login_valid_admin(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"]
        assert data["token_type"] == "bearer"
        assert data["user_id"] == "user-001"
        assert "admin" in data["roles"]

    @pytest.mark.asyncio
    async def test_login_valid_user(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "user", "password": "user"},
        )
        assert resp.status_code == 200
        assert resp.json()["roles"] == ["user"]

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401
        assert "Invalid username or password" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_unknown_user(self, client: AsyncClient):
        resp = await client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "x"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/auth/me
# ---------------------------------------------------------------------------

class TestMe:
    @pytest.mark.asyncio
    async def test_me_authenticated(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "user-001"
        assert data["username"] == "admin"
        assert "admin" in data["roles"]

    @pytest.mark.asyncio
    async def test_me_no_token(self, client: AsyncClient):
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_invalid_token(self, client: AsyncClient):
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Middleware: get_current_user / require_admin
# ---------------------------------------------------------------------------

class TestMiddleware:
    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self, client: AsyncClient):
        """Any protected endpoint without a token should return 401."""
        resp = await client.get("/api/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, client: AsyncClient):
        """An expired JWT should be rejected with 401."""
        import jwt as pyjwt
        from datetime import datetime, timedelta, timezone

        payload = {
            "sub": "user-001",
            "username": "admin",
            "roles": ["admin"],
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
            "iat": datetime.now(timezone.utc) - timedelta(minutes=5),
        }
        expired = pyjwt.encode(payload, "change-me-in-production", algorithm="HS256")
        resp = await client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code == 401
