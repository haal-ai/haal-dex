# Feature: intent, Property 8: Unreachable LLM provider error identification
"""Property 8: Unreachable LLM provider error identification

For any unreachable provider, error identifies provider name and failure reason.

**Validates: Requirements 4.5**

Strategy:
- Generate random ProviderConfig instances where the provider would fail:
  - bedrock with SDK unavailable (BedrockModel is None)
  - openai_compatible with SDK unavailable (OpenAIModel is None)
  - unsupported provider types
- Verify check_provider_health() returns HealthStatus with healthy=False
  and error containing the provider name or failure reason.
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given, settings, strategies as st

from app.engine.model_factory import HealthStatus, ModelFactory
from app.models.pipeline import OAuthConfig, ProviderConfig

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_model_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-_./"),
    min_size=1,
    max_size=60,
)

# Provider types that are NOT supported — should always produce errors.
_unsupported_providers = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz_"),
    min_size=1,
    max_size=30,
).filter(lambda s: s not in {"bedrock", "openai_compatible", "github_copilot"})


@st.composite
def unavailable_bedrock_config(draw) -> ProviderConfig:
    """Draw a Bedrock config that will fail because SDK is unavailable."""
    return ProviderConfig(
        provider_type="bedrock",
        model_id=draw(_model_ids),
        region=draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"])),
    )


@st.composite
def unavailable_openai_config(draw) -> ProviderConfig:
    """Draw an OpenAI-compatible config that will fail because SDK is unavailable."""
    return ProviderConfig(
        provider_type="openai_compatible",
        model_id=draw(_model_ids),
        api_key=draw(st.text(min_size=1, max_size=20)),
    )


@st.composite
def unsupported_provider_config(draw) -> ProviderConfig:
    """Draw a config with an unsupported provider type."""
    return ProviderConfig(
        provider_type=draw(_unsupported_providers),
        model_id=draw(_model_ids),
    )


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(config=unavailable_bedrock_config())
@settings(max_examples=100)
async def test_unavailable_bedrock_error_identifies_provider_and_reason(config: ProviderConfig):
    """Property 8: For any unreachable Bedrock provider (SDK unavailable),
    check_provider_health returns unhealthy status with error identifying
    the provider and failure reason.

    **Validates: Requirements 4.5**
    """
    factory = ModelFactory()

    with patch("app.engine.model_factory.BedrockModel", None):
        result = await factory.check_provider_health(config)

    assert isinstance(result, HealthStatus)
    assert result.healthy is False
    assert result.provider == "bedrock"
    assert result.error is not None
    # Error should mention the provider or SDK unavailability
    assert "BedrockModel" in result.error or "bedrock" in result.error.lower()


@given(config=unavailable_openai_config())
@settings(max_examples=100)
async def test_unavailable_openai_error_identifies_provider_and_reason(config: ProviderConfig):
    """Property 8: For any unreachable OpenAI-compatible provider (SDK unavailable),
    check_provider_health returns unhealthy status with error identifying
    the provider and failure reason.

    **Validates: Requirements 4.5**
    """
    factory = ModelFactory()

    with patch("app.engine.model_factory.OpenAIModel", None):
        result = await factory.check_provider_health(config)

    assert isinstance(result, HealthStatus)
    assert result.healthy is False
    assert result.provider == "openai_compatible"
    assert result.error is not None
    # Error should mention the provider or SDK unavailability
    assert "OpenAIModel" in result.error or "openai" in result.error.lower()


@given(config=unsupported_provider_config())
@settings(max_examples=100)
async def test_unsupported_provider_error_identifies_provider_and_reason(config: ProviderConfig):
    """Property 8: For any unsupported provider type, check_provider_health
    returns unhealthy status with error identifying the provider name.

    **Validates: Requirements 4.5**
    """
    factory = ModelFactory()

    result = await factory.check_provider_health(config)

    assert isinstance(result, HealthStatus)
    assert result.healthy is False
    assert result.provider == config.provider_type
    assert result.error is not None
    # Error should mention the unsupported provider type
    assert config.provider_type in result.error
