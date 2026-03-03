# Feature: intent, Property 7: LLM routing matches agent configuration
"""Property 7: LLM routing matches agent configuration

For any agent configured with provider P and model M in the Pipeline_Config,
the LLM_Router should route that agent's requests to provider P with model M.

**Validates: Requirements 4.1**

Strategy:
- Generate random ProviderConfig instances with valid provider_types
  ("bedrock", "openai_compatible", "github_copilot") and random model_ids.
- For bedrock and openai_compatible, mock the SDK classes so create_model()
  succeeds without real dependencies.
- Verify that create_model() returns a model instance configured with the
  correct provider type and model_id.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from hypothesis import given, settings, strategies as st

from app.engine.github_copilot_model import GitHubCopilotModel
from app.engine.model_factory import ModelFactory
from app.models.pipeline import OAuthConfig, ProviderConfig

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_model_ids = st.text(
    alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyz0123456789-_./"),
    min_size=1,
    max_size=60,
)

_regions = st.sampled_from(["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"])
_temperatures = st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)
_max_tokens = st.integers(min_value=1, max_value=8192)


@st.composite
def bedrock_config(draw) -> ProviderConfig:
    """Draw a valid Bedrock ProviderConfig."""
    return ProviderConfig(
        provider_type="bedrock",
        model_id=draw(_model_ids),
        region=draw(_regions),
        temperature=draw(_temperatures),
        max_tokens=draw(_max_tokens),
    )


@st.composite
def openai_config(draw) -> ProviderConfig:
    """Draw a valid OpenAI-compatible ProviderConfig."""
    endpoint = draw(st.one_of(st.none(), st.just("https://api.openai.com/v1")))
    return ProviderConfig(
        provider_type="openai_compatible",
        model_id=draw(_model_ids),
        api_key=draw(st.text(min_size=1, max_size=40)),
        endpoint=endpoint,
    )


@st.composite
def github_copilot_config(draw) -> ProviderConfig:
    """Draw a valid GitHub Copilot ProviderConfig."""
    oauth = OAuthConfig(
        client_id=draw(st.text(min_size=1, max_size=20)),
        client_secret=draw(st.text(min_size=1, max_size=20)),
        token_url="https://auth.example.com/token",
        scopes=["copilot"],
    )
    return ProviderConfig(
        provider_type="github_copilot",
        model_id=draw(_model_ids),
        oauth_config=oauth,
    )


_any_provider_config = st.one_of(bedrock_config(), openai_config(), github_copilot_config())


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(config=bedrock_config())
@settings(max_examples=100)
def test_bedrock_routing_targets_correct_provider_and_model(config: ProviderConfig):
    """Property 7: For any agent configured with provider 'bedrock' and model M,
    routing should target the Bedrock provider with model M.

    **Validates: Requirements 4.1**
    """
    factory = ModelFactory()

    mock_bedrock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_bedrock_cls.return_value = mock_instance

    with patch("app.engine.model_factory.BedrockModel", mock_bedrock_cls):
        model = factory.create_model(config)

    # Verify the correct SDK class was called with the right model_id
    mock_bedrock_cls.assert_called_once_with(
        model_id=config.model_id,
        region_name=config.region,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    assert model is mock_instance


@given(config=openai_config())
@settings(max_examples=100)
def test_openai_routing_targets_correct_provider_and_model(config: ProviderConfig):
    """Property 7: For any agent configured with provider 'openai_compatible'
    and model M, routing should target the OpenAI-compatible provider with model M.

    **Validates: Requirements 4.1**
    """
    factory = ModelFactory()

    mock_openai_cls = MagicMock()
    mock_instance = MagicMock()
    mock_openai_cls.return_value = mock_instance

    with patch("app.engine.model_factory.OpenAIModel", mock_openai_cls):
        model = factory.create_model(config)

    # Verify the correct SDK class was called with the right model_id
    expected_client_args = {"api_key": config.api_key}
    if config.endpoint:
        expected_client_args["base_url"] = config.endpoint

    mock_openai_cls.assert_called_once_with(
        client_args=expected_client_args,
        model_id=config.model_id,
    )
    assert model is mock_instance


@given(config=github_copilot_config())
@settings(max_examples=100)
def test_github_copilot_routing_targets_correct_provider_and_model(config: ProviderConfig):
    """Property 7: For any agent configured with provider 'github_copilot'
    and model M, routing should create a GitHubCopilotModel with model M
    and the correct oauth_config.

    **Validates: Requirements 4.1**
    """
    factory = ModelFactory()

    model = factory.create_model(config)

    assert isinstance(model, GitHubCopilotModel)
    assert model.model_id == config.model_id
    assert model.oauth_config is config.oauth_config
