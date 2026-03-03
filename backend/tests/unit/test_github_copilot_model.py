"""Unit tests for GitHubCopilotModel — OAuth authentication, stream, config management."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from app.engine.github_copilot_model import GitHubCopilotModel
from app.models.pipeline import OAuthConfig


def _make_oauth(**overrides) -> OAuthConfig:
    defaults = dict(
        client_id="test-client-id",
        client_secret="test-client-secret",
        token_url="https://auth.example.com/token",
        scopes=["copilot"],
    )
    defaults.update(overrides)
    return OAuthConfig(**defaults)


# ---------------------------------------------------------------------------
# Construction & basic attributes
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_stores_oauth_config_and_model_id(self):
        oauth = _make_oauth()
        model = GitHubCopilotModel(oauth_config=oauth, model_id="copilot-gpt-4")
        assert model.oauth_config is oauth
        assert model.model_id == "copilot-gpt-4"
        assert model._token is None

    def test_accepts_none_oauth_config(self):
        model = GitHubCopilotModel(oauth_config=None, model_id="m1")
        assert model.oauth_config is None

    def test_default_config_values(self):
        model = GitHubCopilotModel(oauth_config=None, model_id="m1")
        cfg = model.get_config()
        assert cfg["model_id"] == "m1"
        assert cfg["temperature"] == 0.7
        assert cfg["max_tokens"] == 2048


# ---------------------------------------------------------------------------
# get_config / update_config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_get_config_returns_copy(self):
        model = GitHubCopilotModel(oauth_config=None, model_id="m1")
        cfg1 = model.get_config()
        cfg1["extra"] = "injected"
        assert "extra" not in model.get_config()

    def test_update_config_updates_temperature(self):
        model = GitHubCopilotModel(oauth_config=None, model_id="m1")
        model.update_config(temperature=0.2)
        assert model.get_config()["temperature"] == 0.2

    def test_update_config_updates_max_tokens(self):
        model = GitHubCopilotModel(oauth_config=None, model_id="m1")
        model.update_config(max_tokens=512)
        assert model.get_config()["max_tokens"] == 512

    def test_update_config_updates_model_id(self):
        model = GitHubCopilotModel(oauth_config=None, model_id="m1")
        model.update_config(model_id="m2")
        assert model.model_id == "m2"
        assert model.get_config()["model_id"] == "m2"

    def test_update_config_multiple_keys(self):
        model = GitHubCopilotModel(oauth_config=None, model_id="m1")
        model.update_config(temperature=0.1, max_tokens=100)
        cfg = model.get_config()
        assert cfg["temperature"] == 0.1
        assert cfg["max_tokens"] == 100


# ---------------------------------------------------------------------------
# OAuth token acquisition
# ---------------------------------------------------------------------------

class TestTokenAcquisition:
    def test_acquire_token_raises_without_oauth_config(self):
        model = GitHubCopilotModel(oauth_config=None, model_id="m1")
        with pytest.raises(RuntimeError, match="oauth_config is not set"):
            model._acquire_token()

    def test_acquire_token_success(self):
        oauth = _make_oauth()
        model = GitHubCopilotModel(oauth_config=oauth, model_id="m1")

        token_response = json.dumps({"access_token": "tok-123"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = token_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("app.engine.github_copilot_model.urllib_request.urlopen", return_value=mock_resp):
            token = model._acquire_token()

        assert token == "tok-123"

    def test_acquire_token_missing_access_token_field(self):
        oauth = _make_oauth()
        model = GitHubCopilotModel(oauth_config=oauth, model_id="m1")

        token_response = json.dumps({"error": "bad_request"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = token_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("app.engine.github_copilot_model.urllib_request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="missing 'access_token'"):
                model._acquire_token()

    def test_acquire_token_network_error(self):
        from urllib.error import URLError
        oauth = _make_oauth()
        model = GitHubCopilotModel(oauth_config=oauth, model_id="m1")

        with patch("app.engine.github_copilot_model.urllib_request.urlopen", side_effect=URLError("timeout")):
            with pytest.raises(RuntimeError, match="Failed to acquire OAuth token"):
                model._acquire_token()

    def test_ensure_token_caches(self):
        oauth = _make_oauth()
        model = GitHubCopilotModel(oauth_config=oauth, model_id="m1")

        token_response = json.dumps({"access_token": "cached-tok"}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = token_response
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("app.engine.github_copilot_model.urllib_request.urlopen", return_value=mock_resp) as mock_open:
            model._ensure_token()
            model._ensure_token()
            # Should only call urlopen once (cached).
            assert mock_open.call_count == 1

    def test_invalidate_token_clears_cache(self):
        oauth = _make_oauth()
        model = GitHubCopilotModel(oauth_config=oauth, model_id="m1")
        model._token = "old-tok"
        model.invalidate_token()
        assert model._token is None


# ---------------------------------------------------------------------------
# stream()
# ---------------------------------------------------------------------------

class TestStream:
    def _make_sse_response(self, chunks: list[dict]) -> MagicMock:
        """Build a mock HTTP response that yields SSE lines."""
        lines = []
        for chunk in chunks:
            lines.append(f"data: {json.dumps(chunk)}\n".encode())
        lines.append(b"data: [DONE]\n")

        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.__iter__ = lambda s: iter(lines)
        return mock_resp

    def test_stream_yields_parsed_chunks(self):
        oauth = _make_oauth()
        model = GitHubCopilotModel(oauth_config=oauth, model_id="m1")
        model._token = "pre-set-token"

        chunks = [
            {"choices": [{"delta": {"content": "Hello"}}]},
            {"choices": [{"delta": {"content": " world"}}]},
        ]
        mock_resp = self._make_sse_response(chunks)

        with patch("app.engine.github_copilot_model.urllib_request.urlopen", return_value=mock_resp):
            result = list(model.stream([{"role": "user", "content": "Hi"}]))

        assert len(result) == 2
        assert result[0]["choices"][0]["delta"]["content"] == "Hello"
        assert result[1]["choices"][0]["delta"]["content"] == " world"

    def test_stream_acquires_token_if_missing(self):
        oauth = _make_oauth()
        model = GitHubCopilotModel(oauth_config=oauth, model_id="m1")

        # First call: token acquisition
        token_resp = MagicMock()
        token_resp.read.return_value = json.dumps({"access_token": "new-tok"}).encode()
        token_resp.__enter__ = lambda s: s
        token_resp.__exit__ = MagicMock(return_value=False)

        # Second call: streaming
        stream_resp = self._make_sse_response([{"choices": [{"delta": {"content": "ok"}}]}])

        with patch("app.engine.github_copilot_model.urllib_request.urlopen", side_effect=[token_resp, stream_resp]):
            result = list(model.stream([]))

        assert len(result) == 1
        assert model._token == "new-tok"

    def test_stream_network_error_invalidates_token(self):
        from urllib.error import URLError
        oauth = _make_oauth()
        model = GitHubCopilotModel(oauth_config=oauth, model_id="m1")
        model._token = "will-be-cleared"

        with patch("app.engine.github_copilot_model.urllib_request.urlopen", side_effect=URLError("conn refused")):
            with pytest.raises(RuntimeError, match="GitHub Copilot API request failed"):
                list(model.stream([]))

        assert model._token is None

    def test_stream_skips_empty_and_non_data_lines(self):
        oauth = _make_oauth()
        model = GitHubCopilotModel(oauth_config=oauth, model_id="m1")
        model._token = "tok"

        lines = [
            b"\n",
            b": comment\n",
            b"data: {\"ok\": true}\n",
            b"\n",
            b"data: [DONE]\n",
        ]
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.__iter__ = lambda s: iter(lines)

        with patch("app.engine.github_copilot_model.urllib_request.urlopen", return_value=mock_resp):
            result = list(model.stream([]))

        assert len(result) == 1
        assert result[0] == {"ok": True}


# ---------------------------------------------------------------------------
# Integration with ModelFactory
# ---------------------------------------------------------------------------

class TestModelFactoryIntegration:
    def test_model_factory_creates_github_copilot_model(self):
        from app.engine.model_factory import ModelFactory
        from app.models.pipeline import ProviderConfig

        oauth = _make_oauth()
        config = ProviderConfig(
            provider_type="github_copilot",
            model_id="copilot-gpt-4",
            oauth_config=oauth,
        )
        factory = ModelFactory()
        model = factory.create_model(config)

        assert isinstance(model, GitHubCopilotModel)
        assert model.model_id == "copilot-gpt-4"
        assert model.oauth_config is oauth

    def test_model_factory_import_path(self):
        """Verify GitHubCopilotModel is importable from model_factory (re-export)."""
        from app.engine.model_factory import GitHubCopilotModel as Imported
        assert Imported is GitHubCopilotModel
