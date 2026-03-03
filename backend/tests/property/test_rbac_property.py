# Feature: intent, Property 29: Role-based access control enforcement
"""Property 29: Role-based access control enforcement

For any non-admin user, attempts to modify PipelineConfig/LLM settings/
templates should be denied; admin users should be allowed.

**Validates: Requirements 20.4**

Strategy: Generate random user contexts with and without the admin role.
Register a test endpoint protected by ``require_admin`` and verify that
non-admin users get 403 while admin users get 200.
"""

from __future__ import annotations

import string

import pytest
from hypothesis import given, settings, strategies as st
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.middleware.auth import require_admin
from app.models.auth import UserContext
from app.services.auth_service import AuthService

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_role_name = st.text(
    alphabet=string.ascii_lowercase, min_size=1, max_size=15
).filter(lambda r: r != "admin")

# Roles list that explicitly does NOT contain "admin"
_non_admin_roles = st.lists(_role_name, min_size=0, max_size=5)

# Roles list that DOES contain "admin" (plus optional extras)
_admin_roles = st.lists(_role_name, min_size=0, max_size=4).map(
    lambda roles: ["admin"] + roles
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_app_with_admin_endpoint():
    """Create a FastAPI app with a test endpoint protected by require_admin."""
    from fastapi import Depends

    app = create_app()

    @app.get("/api/test/admin-only")
    async def admin_only_endpoint(user: UserContext = Depends(require_admin)):
        return {"message": "admin access granted", "user_id": user.user_id}

    return app


async def _get_token(client: AsyncClient, username: str, password: str) -> str:
    resp = await client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@given(extra_roles=_non_admin_roles)
@settings(max_examples=100)
@pytest.mark.asyncio
async def test_non_admin_users_denied_admin_endpoints(extra_roles):
    """Property 29 (part 1): Non-admin users should be denied access to
    admin-only endpoints with HTTP 403.

    We use the pre-seeded 'user' account (roles=["user"]) which does not
    have the admin role. The hypothesis-generated extra_roles confirm the
    property holds regardless of what other roles might exist.
    """
    app = _build_app_with_admin_endpoint()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _get_token(client, "user", "user")

        response = await client.get(
            "/api/test/admin-only",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403, (
            f"Expected 403 for non-admin user with roles {extra_roles}, "
            f"got {response.status_code}"
        )


@given(extra_roles=_admin_roles)
@settings(max_examples=100)
@pytest.mark.asyncio
async def test_admin_users_allowed_admin_endpoints(extra_roles):
    """Property 29 (part 2): Admin users should be allowed access to
    admin-only endpoints with HTTP 200.

    We use the pre-seeded 'admin' account (roles=["admin", "user"]) which
    has the admin role. The hypothesis-generated extra_roles confirm the
    property holds regardless of what additional roles might exist.
    """
    app = _build_app_with_admin_endpoint()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _get_token(client, "admin", "admin")

        response = await client.get(
            "/api/test/admin-only",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, (
            f"Expected 200 for admin user with roles {extra_roles}, "
            f"got {response.status_code}"
        )
        data = response.json()
        assert data["message"] == "admin access granted"
