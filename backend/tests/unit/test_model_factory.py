"""Unit tests for ModelFactory — Bedrock, OpenAI-compatible, and GitHub Copilot providers."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.engine.model_factory import (
    GitHubCopilotModel,
    HealthStatus,
    ModelFactory,
)
from app.models.pipeline import OAuthConfig, ProviderConfig


@pytest.fixture
def factory() -> ModelFactory:
    return ModelFactory()


# ---------------------------------------------------------------------------
# GitHubCopilotModel placeholder
# ---------------------------------------------------------------------------

class TestGitHubCopilotModel:
    def test_stores_config(self):
        oauth = OAuthConfig(
            client_id="cid", client_secret="csec",
            token_url="https://tok", scopes=["read"],
        )
        model = GitHubCopilotModel(oauth_config=oauth, model_id="copilot-1")
        assert model.model_id == "copilot-1"
        assert model.oauth_config is oauth
        assert model._token is None

    def test_get_config(self):
        model = GitHubCopilotModel(oauth_config=None, model_id="m1")
        cfg = model.get_config()
        assert cfg["model_id"] == "m1"
        assert "temperature" in cfg
        assert "max_tokens" in cfg

    def test_uses_device_flow_helper_when_oauth_config_missing(self):
        with patch("app.engine.github_copilot_model.CopilotAuth") as mock_auth_cls:
            mock_auth = MagicMock()
            mock_auth.get_token.return_value = "copilot-token"
            mock_auth_cls.return_value = mock_auth

            model = GitHubCopilotModel(oauth_config=None, model_id="m1")

            assert model._ensure_token() == "copilot-token"

    def test_update_config_works(self):
        model = GitHubCopilotModel(oauth_config=None, model_id="m1")
        model.update_config(temperature=0.5)
        assert model.get_config()["temperature"] == 0.5


# ---------------------------------------------------------------------------
# ModelFactory.create_model — GitHub Copilot (no SDK needed)
# ---------------------------------------------------------------------------

class TestCreateModelGitHubCopilot:
    def test_creates_github_copilot_model(self, factory: ModelFactory):
        oauth = OAuthConfig(
            client_id="cid", client_secret="csec",
            token_url="https://tok", scopes=["read"],
        )
        config = ProviderConfig(
            provider_type="github_copilot",
            model_id="copilot-gpt-4",
            oauth_config=oauth,
        )
        model = factory.create_model(config)
        assert isinstance(model, GitHubCopilotModel)
        assert model.model_id == "copilot-gpt-4"
        assert model.oauth_config is oauth


# ---------------------------------------------------------------------------
# ModelFactory.create_model — Bedrock (mocked SDK)
# ---------------------------------------------------------------------------

class TestCreateModelBedrock:
    def test_creates_bedrock_model_when_sdk_available(self, factory: ModelFactory):
        mock_bedrock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_bedrock_cls.return_value = mock_instance

        config = ProviderConfig(
            provider_type="bedrock",
            model_id="anthropic.claude-3-sonnet",
            region="us-east-1",
            temperature=0.5,
            max_tokens=1024,
        )

        with patch("app.engine.model_factory.BedrockModel", mock_bedrock_cls):
            result = factory.create_model(config)

        mock_bedrock_cls.assert_called_once_with(
            model_id="anthropic.claude-3-sonnet",
            region_name="us-east-1",
            temperature=0.5,
            max_tokens=1024,
        )
        assert result is mock_instance

    def test_uses_boto_session_without_region_name_when_profile_is_provided(self, factory: ModelFactory):
        mock_bedrock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_bedrock_cls.return_value = mock_instance
        mock_session = MagicMock()

        config = ProviderConfig(
            provider_type="bedrock",
            model_id="anthropic.claude-3-sonnet",
            region="us-east-1",
            profile="claude-sso",
            temperature=0.5,
            max_tokens=1024,
        )

        mock_boto3 = SimpleNamespace(Session=MagicMock(return_value=mock_session))

        with patch("app.engine.model_factory.BedrockModel", mock_bedrock_cls), patch.dict(sys.modules, {"boto3": mock_boto3}):
            result = factory.create_model(config)

        mock_bedrock_cls.assert_called_once_with(
            model_id="anthropic.claude-3-sonnet",
            boto_session=mock_session,
            temperature=0.5,
            max_tokens=1024,
        )
        assert result is mock_instance

    def test_prefers_inference_profile_id_when_provided(self, factory: ModelFactory):
        mock_bedrock_cls = MagicMock()
        mock_instance = MagicMock()
        mock_bedrock_cls.return_value = mock_instance

        config = ProviderConfig(
            provider_type="bedrock",
            model_id="anthropic.claude-sonnet-4-6",
            inference_profile_id="arn:aws:bedrock:us-east-1:123456789012:inference-profile/example",
            region="us-east-1",
            temperature=0.2,
            max_tokens=256,
        )

        with patch("app.engine.model_factory.BedrockModel", mock_bedrock_cls):
            result = factory.create_model(config)

        mock_bedrock_cls.assert_called_once_with(
            model_id="arn:aws:bedrock:us-east-1:123456789012:inference-profile/example",
            region_name="us-east-1",
            temperature=0.2,
            max_tokens=256,
        )
        assert result is mock_instance

    def test_raises_when_bedrock_sdk_unavailable(self, factory: ModelFactory):
        config = ProviderConfig(
            provider_type="bedrock",
            model_id="anthropic.claude-3-sonnet",
        )
        with patch("app.engine.model_factory.BedrockModel", None):
            with pytest.raises(ValueError, match="BedrockModel is not available"):
                factory.create_model(config)


# ---------------------------------------------------------------------------
# ModelFactory.create_model — OpenAI-compatible (mocked SDK)
# ---------------------------------------------------------------------------

class TestCreateModelOpenAI:
    def test_creates_openai_model_when_sdk_available(self, factory: ModelFactory):
        mock_openai_cls = MagicMock()
        mock_instance = MagicMock()
        mock_openai_cls.return_value = mock_instance

        config = ProviderConfig(
            provider_type="openai_compatible",
            model_id="gpt-4",
            api_key="sk-test-key",
            endpoint="https://api.openai.com/v1",
        )

        with patch("app.engine.model_factory.OpenAIModel", mock_openai_cls):
            result = factory.create_model(config)

        mock_openai_cls.assert_called_once_with(
            client_args={"api_key": "sk-test-key", "base_url": "https://api.openai.com/v1"},
            model_id="gpt-4",
        )
        assert result is mock_instance

    def test_creates_openai_model_without_endpoint(self, factory: ModelFactory):
        mock_openai_cls = MagicMock()

        config = ProviderConfig(
            provider_type="openai_compatible",
            model_id="gpt-4",
            api_key="sk-test-key",
        )

        with patch("app.engine.model_factory.OpenAIModel", mock_openai_cls):
            factory.create_model(config)

        mock_openai_cls.assert_called_once_with(
            client_args={"api_key": "sk-test-key"},
            model_id="gpt-4",
        )

    def test_raises_when_openai_sdk_unavailable(self, factory: ModelFactory):
        config = ProviderConfig(
            provider_type="openai_compatible",
            model_id="gpt-4",
            api_key="sk-test",
        )
        with patch("app.engine.model_factory.OpenAIModel", None):
            with pytest.raises(ValueError, match="OpenAIModel is not available"):
                factory.create_model(config)


# ---------------------------------------------------------------------------
# ModelFactory.create_model — unsupported provider
# ---------------------------------------------------------------------------

class TestCreateModelUnsupported:
    def test_raises_for_unsupported_provider(self, factory: ModelFactory):
        config = ProviderConfig(
            provider_type="unknown_provider",
            model_id="some-model",
        )
        with pytest.raises(ValueError, match="Unsupported provider type: unknown_provider"):
            factory.create_model(config)


# ---------------------------------------------------------------------------
# ModelFactory.check_provider_health
# ---------------------------------------------------------------------------

class TestCheckProviderHealth:
    async def test_healthy_when_model_creates_successfully(self, factory: ModelFactory):
        oauth = OAuthConfig(
            client_id="cid", client_secret="csec",
            token_url="https://tok", scopes=["read"],
        )
        config = ProviderConfig(
            provider_type="github_copilot",
            model_id="copilot-gpt-4",
            oauth_config=oauth,
        )
        result = await factory.check_provider_health(config)
        assert result.healthy is True
        assert result.provider == "github_copilot"
        assert result.error is None

    async def test_unhealthy_when_model_creation_fails(self, factory: ModelFactory):
        config = ProviderConfig(
            provider_type="bedrock",
            model_id="some-model",
        )
        with patch("app.engine.model_factory.BedrockModel", None):
            result = await factory.check_provider_health(config)
        assert result.healthy is False
        assert result.provider == "bedrock"
        assert "not available" in result.error

    async def test_unhealthy_for_unsupported_provider(self, factory: ModelFactory):
        config = ProviderConfig(
            provider_type="nonexistent",
            model_id="x",
        )
        result = await factory.check_provider_health(config)
        assert result.healthy is False
        assert result.provider == "nonexistent"
        assert "Unsupported provider type" in result.error
