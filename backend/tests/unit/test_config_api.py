"""Unit tests for pipeline config CRUD endpoints (admin-only)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.config import get_pipeline_store
from app.main import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_config_json() -> str:
    """Return a valid pipeline config as a JSON string."""
    return json.dumps({
        "name": "test-pipeline",
        "agents": [
            {
                "name": "agent1",
                "model": "bedrock/claude-3-sonnet",
                "provider_config": {
                    "provider_type": "bedrock",
                    "model_id": "claude-3-sonnet",
                    "region": "us-east-1",
                },
                "description": "First agent",
                "tools": ["read"],
            }
        ],
        "output": {
            "template": "default",
            "formats": ["pdf"],
        },
    })


def _valid_config_yaml() -> str:
    """Return a valid pipeline config as a YAML string."""
    return (
        "name: yaml-pipeline\n"
        "agents:\n"
        "  - name: agent1\n"
        "    model: bedrock/claude-3-sonnet\n"
        "    provider_config:\n"
        "      provider_type: bedrock\n"
        "      model_id: claude-3-sonnet\n"
        "      region: us-east-1\n"
        "    description: First agent\n"
        "output:\n"
        "  template: default\n"
        "  formats:\n"
        "    - pdf\n"
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    application = create_app()
    # Override the store with a fresh dict per test
    fresh_store: dict = {}
    application.dependency_overrides[get_pipeline_store] = lambda: fresh_store
    yield application
    application.dependency_overrides.clear()


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
# RBAC enforcement
# ---------------------------------------------------------------------------

class TestRBAC:
    """All config endpoints require admin role."""

    @pytest.mark.asyncio
    async def test_list_no_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/config/pipelines")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_user_token_returns_403(self, client: AsyncClient, user_token: str):
        resp = await client.get(
            "/api/config/pipelines",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_user_token_returns_403(self, client: AsyncClient, user_token: str):
        resp = await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_json(), "format": "json"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_user_token_returns_403(self, client: AsyncClient, user_token: str):
        resp = await client.put(
            "/api/config/pipelines/test-pipeline",
            json={"raw": _valid_config_json(), "format": "json"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_user_token_returns_403(self, client: AsyncClient, user_token: str):
        resp = await client.delete(
            "/api/config/pipelines/test-pipeline",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_get_user_token_returns_403(self, client: AsyncClient, user_token: str):
        resp = await client.get(
            "/api/config/pipelines/test-pipeline",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/config/pipelines (list)
# ---------------------------------------------------------------------------

class TestListPipelines:
    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/config/pipelines",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["pipelines"] == []

    @pytest.mark.asyncio
    async def test_list_after_create(self, client: AsyncClient, admin_token: str):
        headers = {"Authorization": f"Bearer {admin_token}"}
        await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_json(), "format": "json"},
            headers=headers,
        )
        resp = await client.get("/api/config/pipelines", headers=headers)
        assert resp.status_code == 200
        pipelines = resp.json()["pipelines"]
        assert len(pipelines) == 1
        assert pipelines[0]["name"] == "test-pipeline"


# ---------------------------------------------------------------------------
# GET /api/config/pipelines/{name}
# ---------------------------------------------------------------------------

class TestGetPipeline:
    @pytest.mark.asyncio
    async def test_get_existing(self, client: AsyncClient, admin_token: str):
        headers = {"Authorization": f"Bearer {admin_token}"}
        await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_json(), "format": "json"},
            headers=headers,
        )
        resp = await client.get("/api/config/pipelines/test-pipeline", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-pipeline"
        assert data["config"]["agents"][0]["name"] == "agent1"

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient, admin_token: str):
        resp = await client.get(
            "/api/config/pipelines/nonexistent",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/config/pipelines (create)
# ---------------------------------------------------------------------------

class TestCreatePipeline:
    @pytest.mark.asyncio
    async def test_create_json(self, client: AsyncClient, admin_token: str):
        resp = await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_json(), "format": "json"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test-pipeline"

    @pytest.mark.asyncio
    async def test_create_yaml(self, client: AsyncClient, admin_token: str):
        resp = await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_yaml(), "format": "yaml"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "yaml-pipeline"

    @pytest.mark.asyncio
    async def test_create_duplicate_returns_409(self, client: AsyncClient, admin_token: str):
        headers = {"Authorization": f"Bearer {admin_token}"}
        await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_json(), "format": "json"},
            headers=headers,
        )
        resp = await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_json(), "format": "json"},
            headers=headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_create_invalid_json_returns_422(self, client: AsyncClient, admin_token: str):
        resp = await client.post(
            "/api/config/pipelines",
            json={"raw": "{invalid json", "format": "json"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_validation_error_returns_422(self, client: AsyncClient, admin_token: str):
        bad_config = json.dumps({
            "name": "bad",
            "agents": [
                {
                    "name": "a",
                    "model": "x",
                    "provider_config": {
                        "provider_type": "invalid_provider",
                        "model_id": "m",
                    },
                    "description": "d",
                }
            ],
            "output": {"template": "t", "formats": ["pdf"]},
        })
        resp = await client.post(
            "/api/config/pipelines",
            json={"raw": bad_config, "format": "json"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert "validation_errors" in detail

    @pytest.mark.asyncio
    async def test_create_unsupported_format_returns_400(self, client: AsyncClient, admin_token: str):
        resp = await client.post(
            "/api/config/pipelines",
            json={"raw": "data", "format": "xml"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PUT /api/config/pipelines/{name} (update)
# ---------------------------------------------------------------------------

class TestUpdatePipeline:
    @pytest.mark.asyncio
    async def test_update_existing(self, client: AsyncClient, admin_token: str):
        headers = {"Authorization": f"Bearer {admin_token}"}
        await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_json(), "format": "json"},
            headers=headers,
        )
        updated = json.dumps({
            "name": "test-pipeline",
            "agents": [
                {
                    "name": "updated-agent",
                    "model": "bedrock/claude-3-sonnet",
                    "provider_config": {
                        "provider_type": "bedrock",
                        "model_id": "claude-3-sonnet",
                        "region": "us-west-2",
                    },
                    "description": "Updated agent",
                    "tools": ["read", "write"],
                }
            ],
            "output": {"template": "default", "formats": ["pdf", "docx"]},
        })
        resp = await client.put(
            "/api/config/pipelines/test-pipeline",
            json={"raw": updated, "format": "json"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["config"]["agents"][0]["name"] == "updated-agent"

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient, admin_token: str):
        resp = await client.put(
            "/api/config/pipelines/nonexistent",
            json={"raw": _valid_config_json(), "format": "json"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_with_name_change(self, client: AsyncClient, admin_token: str):
        headers = {"Authorization": f"Bearer {admin_token}"}
        await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_json(), "format": "json"},
            headers=headers,
        )
        renamed = json.dumps({
            "name": "renamed-pipeline",
            "agents": [
                {
                    "name": "agent1",
                    "model": "bedrock/claude-3-sonnet",
                    "provider_config": {
                        "provider_type": "bedrock",
                        "model_id": "claude-3-sonnet",
                        "region": "us-east-1",
                    },
                    "description": "First agent",
                }
            ],
            "output": {"template": "default", "formats": ["pdf"]},
        })
        resp = await client.put(
            "/api/config/pipelines/test-pipeline",
            json={"raw": renamed, "format": "json"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "renamed-pipeline"

        # Old name should be gone
        resp = await client.get("/api/config/pipelines/test-pipeline", headers=headers)
        assert resp.status_code == 404

        # New name should exist
        resp = await client.get("/api/config/pipelines/renamed-pipeline", headers=headers)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_invalid_config_returns_422(self, client: AsyncClient, admin_token: str):
        headers = {"Authorization": f"Bearer {admin_token}"}
        await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_json(), "format": "json"},
            headers=headers,
        )
        resp = await client.put(
            "/api/config/pipelines/test-pipeline",
            json={"raw": "{bad json", "format": "json"},
            headers=headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/config/pipelines/{name}
# ---------------------------------------------------------------------------

class TestDeletePipeline:
    @pytest.mark.asyncio
    async def test_delete_existing(self, client: AsyncClient, admin_token: str):
        headers = {"Authorization": f"Bearer {admin_token}"}
        await client.post(
            "/api/config/pipelines",
            json={"raw": _valid_config_json(), "format": "json"},
            headers=headers,
        )
        resp = await client.delete("/api/config/pipelines/test-pipeline", headers=headers)
        assert resp.status_code == 204

        # Verify it's gone
        resp = await client.get("/api/config/pipelines/test-pipeline", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient, admin_token: str):
        resp = await client.delete(
            "/api/config/pipelines/nonexistent",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404
