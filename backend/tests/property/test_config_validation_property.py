# Feature: intent, Property 24: Pipeline config validation reports specific errors
"""Property 24: Pipeline config validation reports specific errors

For any config with invalid settings, report specific validation errors before
execution.

**Validates: Requirements 14.3, 14.4**

Strategy:
- Generate PipelineConfig instances with various invalid settings:
  - Bad provider types
  - Invalid tool names
  - Out-of-range FAISS indexes
  - Invalid output formats
  - Empty agent names
  - Duplicate agent names
  - Missing required provider fields (e.g. bedrock without region)
- Verify validate_config returns non-empty error list with specific messages.
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from app.models.pipeline import (
    AgentConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)
from app.services.config_validator import validate_config

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_identifier = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,19}", fullmatch=True)


def _valid_provider(**overrides) -> ProviderConfig:
    defaults = dict(
        provider_type="bedrock",
        model_id="anthropic.claude-3-sonnet",
        region="us-east-1",
    )
    defaults.update(overrides)
    return ProviderConfig(**defaults)


def _valid_agent(name: str = "agent1", **overrides) -> AgentConfig:
    defaults = dict(
        name=name,
        model="bedrock/claude-3-sonnet",
        provider_config=_valid_provider(),
        description="A test agent",
    )
    defaults.update(overrides)
    return AgentConfig(**defaults)


def _valid_config(**overrides) -> PipelineConfig:
    defaults = dict(
        name="test-pipeline",
        agents=[_valid_agent()],
        output=OutputConfig(template="default", formats=["xml"]),
    )
    defaults.update(overrides)
    return PipelineConfig(**defaults)


@st.composite
def config_with_bad_provider_type(draw) -> PipelineConfig:
    """Generate a config with an invalid provider_type."""
    bad_type = draw(st.text(min_size=1, max_size=20).filter(
        lambda s: s not in ("bedrock", "openai_compatible", "github_copilot")
    ))
    provider = _valid_provider(provider_type=bad_type)
    agent = _valid_agent(provider_config=provider)
    return _valid_config(agents=[agent])


@st.composite
def config_with_invalid_tool(draw) -> PipelineConfig:
    """Generate a config with an invalid tool name."""
    bad_tool = draw(st.text(min_size=1, max_size=20).filter(
        lambda s: s not in ("read", "write", "python_repl", "shell", "query_faiss")
    ))
    agent = _valid_agent(tools=[bad_tool])
    return _valid_config(agents=[agent])


@st.composite
def config_with_out_of_range_faiss(draw) -> PipelineConfig:
    """Generate a config with a FAISS index outside 0-3."""
    bad_idx = draw(st.one_of(
        st.integers(max_value=-1),
        st.integers(min_value=4, max_value=100),
    ))
    agent = _valid_agent(faiss_indexes=[bad_idx])
    return _valid_config(agents=[agent])


@st.composite
def config_with_invalid_output_format(draw) -> PipelineConfig:
    """Generate a config with an invalid output format."""
    bad_fmt = draw(st.text(min_size=1, max_size=10).filter(
        lambda s: s not in ("xml", "pdf", "docx", "md", "html")
    ))
    return _valid_config(output=OutputConfig(template="t", formats=[bad_fmt]))


@st.composite
def config_with_empty_agent_name(draw) -> PipelineConfig:
    """Generate a config with an empty or whitespace-only agent name."""
    empty_name = draw(st.sampled_from(["", "   ", "\t"]))
    agent = _valid_agent(name=empty_name)
    return _valid_config(agents=[agent])


@st.composite
def config_with_duplicate_agent_names(draw) -> PipelineConfig:
    """Generate a config with duplicate agent names."""
    name = draw(_identifier)
    return _valid_config(agents=[_valid_agent(name=name), _valid_agent(name=name)])


def config_with_no_agents() -> st.SearchStrategy[PipelineConfig]:
    """Generate a config with an empty agents list."""
    return st.just(_valid_config(agents=[]))


def config_with_bedrock_missing_region() -> st.SearchStrategy[PipelineConfig]:
    """Generate a config with bedrock provider but no region."""
    provider = ProviderConfig(
        provider_type="bedrock",
        model_id="anthropic.claude-3-sonnet",
        region=None,
    )
    agent = _valid_agent(provider_config=provider)
    return st.just(_valid_config(agents=[agent]))


def config_with_github_copilot_missing_oauth() -> st.SearchStrategy[PipelineConfig]:
    """Generate a config with github_copilot provider but no oauth_config."""
    provider = ProviderConfig(
        provider_type="github_copilot",
        model_id="copilot-chat",
        oauth_config=None,
    )
    agent = _valid_agent(provider_config=provider)
    return st.just(_valid_config(agents=[agent]))


@st.composite
def any_invalid_config(draw) -> PipelineConfig:
    """Draw from any of the invalid config strategies."""
    strategy = draw(st.sampled_from([
        config_with_bad_provider_type(),
        config_with_invalid_tool(),
        config_with_out_of_range_faiss(),
        config_with_invalid_output_format(),
        config_with_empty_agent_name(),
        config_with_duplicate_agent_names(),
        config_with_no_agents(),
        config_with_bedrock_missing_region(),
        config_with_github_copilot_missing_oauth(),
    ]))
    return draw(strategy)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(config=any_invalid_config())
@settings(max_examples=100)
def test_invalid_config_returns_non_empty_errors(config: PipelineConfig):
    """Property 24: For any config with invalid settings, validate_config
    returns a non-empty list of specific validation errors.

    **Validates: Requirements 14.3, 14.4**
    """
    errors = validate_config(config)
    assert len(errors) > 0, (
        f"Expected validation errors for config but got none.\n"
        f"Config: {config}"
    )
    # Each error should be a non-empty descriptive string
    for error in errors:
        assert isinstance(error, str), f"Error must be a string, got {type(error)}"
        assert len(error) > 0, "Error message must be non-empty"


@given(config=any_invalid_config())
@settings(max_examples=100)
def test_invalid_config_errors_identify_specific_fields(config: PipelineConfig):
    """Property 24: Validation errors should identify the specific invalid
    fields or settings, not just generic messages.

    **Validates: Requirements 14.3, 14.4**
    """
    errors = validate_config(config)
    assert len(errors) > 0

    # Each error should contain at least one identifying keyword that
    # references the problematic area
    identifying_keywords = [
        "agent", "provider", "tool", "FAISS", "format", "name",
        "oauth", "region", "index", "output", "duplicate",
    ]
    for error in errors:
        has_identifier = any(kw.lower() in error.lower() for kw in identifying_keywords)
        assert has_identifier, (
            f"Error message lacks field identification: {error!r}"
        )
