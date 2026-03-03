"""Integration tests for authentication and authorization flow.

Validates: Requirements 20.1, 20.2, 20.3
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import (
    ADMIN_CREDS,
    USER_CREDS,
    auth_header,
    login,
    make_pipeline_config_dict,
)


class TestLoginFlow:
    """End-to-end login → token → authenticated request."""

    def test_login_returns_token(self, client: TestClient):
        resp = client.post("/api/auth/login", json=ADMIN_CREDS)
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["roles"] == ["admin", "user"]

    def test_login_invalid_password_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_login_unknown_user_returns_401(self, client: TestClient):
        resp = client.post(
            "/api/auth/login",
            json={"username": "nobody", "password": "x"},
        )
        assert resp.status_code == 401

    def test_me_returns_user_profile(self, client: TestClient, admin_token: str):
        resp = client.get("/api/auth/me", headers=auth_header(admin_token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert "admin" in data["roles"]


class TestUnauthenticatedRejection:
    """Protected endpoints reject requests without a valid token."""

    def test_file_upload_requires_auth(self, client: TestClient):
        resp = client.post("/api/files/upload")
        assert resp.status_code in (401, 403, 422)

    def test_pipeline_execute_requires_auth(self, client: TestClient):
        resp = client.post(
            "/api/pipeline/execute", json=make_pipeline_config_dict()
        )
        assert resp.status_code in (401, 403)

    def test_config_list_requires_auth(self, client: TestClient):
        resp = client.get("/api/config/pipelines")
        assert resp.status_code in (401, 403)

    def test_output_preview_requires_auth(self, client: TestClient):
        resp = client.get("/api/output/fake-session/preview")
        assert resp.status_code in (401, 403)

    def test_metrics_requires_auth(self, client: TestClient):
        resp = client.get("/api/metrics/fake-session")
        assert resp.status_code in (401, 403)

    def test_replay_requires_auth(self, client: TestClient):
        resp = client.get("/api/replay/fake-session")
        assert resp.status_code in (401, 403)

    def test_invalid_token_rejected(self, client: TestClient):
        resp = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid-jwt-token"},
        )
        assert resp.status_code == 401


class TestRoleBasedAccess:
    """Admin-only endpoints reject non-admin users.

    Validates: Requirements 20.4
    """

    def test_non_admin_cannot_list_pipelines(self, client: TestClient, user_token: str):
        resp = client.get(
            "/api/config/pipelines", headers=auth_header(user_token)
        )
        assert resp.status_code == 403

    def test_non_admin_cannot_create_pipeline(self, client: TestClient, user_token: str):
        resp = client.post(
            "/api/config/pipelines",
            json={"raw": "{}", "format": "json"},
            headers=auth_header(user_token),
        )
        assert resp.status_code == 403

    def test_admin_can_list_pipelines(self, client: TestClient, admin_token: str):
        resp = client.get(
            "/api/config/pipelines", headers=auth_header(admin_token)
        )
        assert resp.status_code == 200

    def test_regular_user_can_execute_pipeline(
        self, client: TestClient, user_token: str
    ):
        """Non-admin users can still execute pipelines (Req 20.1)."""
        resp = client.post(
            "/api/pipeline/execute",
            json=make_pipeline_config_dict(),
            headers=auth_header(user_token),
        )
        assert resp.status_code == 200
