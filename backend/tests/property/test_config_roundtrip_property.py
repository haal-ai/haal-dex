# Feature: intent, Property 26: Pipeline config serialization round trip
"""Property 26: Pipeline config serialization round trip

For any valid PipelineConfig, serialize then parse produces equivalent object;
parse(serialize(parse(raw))) == parse(raw).

**Validates: Requirements 19.1, 19.2, 19.3, 19.4**

Strategy:
- Use @st.composite to build valid PipelineConfig instances from random parts
- Serialize to YAML, parse back, verify equality
- Serialize to JSON, parse back, verify equality
- Also verify the idempotent form: parse(serialize(parse(raw))) == parse(raw)
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from app.models.pipeline import (
    AgentConfig,
    OAuthConfig,
    OutputConfig,
    PipelineConfig,
    ProviderConfig,
)
from app.services.config_parser import parse_config, serialize_config

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_provider_types = st.sampled_from(["bedrock", "openai_compatible", "github_copilot"])
_formats = st.sampled_from(["yaml", "json"])
_output_formats = st.sampled_from(["xml", "pdf", "docx", "md", "html"])
_tool_names = st.sampled_from(["read", "write", "python_repl", "shell", "query_faiss"])
_faiss_indexes = st.sampled_from([0, 1, 2, 3])

# Safe text strategy: printable ASCII, no control chars, reasonable length
_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z"), min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

# Identifiers: alphanumeric + hyphens/underscores, no leading/trailing whitespace
_identifier = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,29}", fullmatch=True)


@st.composite
def oauth_config_strategy(draw) -> OAuthConfig:
    return OAuthConfig(
        client_id=draw(_identifier),
        client_secret=draw(_identifier),
        token_url="https://example.com/oauth/token",
        scopes=draw(st.lists(_identifier, min_size=1, max_size=3)),
    )


@st.composite
def provider_config_strategy(draw) -> ProviderConfig:
    provider_type = draw(_provider_types)
    model_id = draw(_identifier)

    oauth_config = None
    region = None
    endpoint = None
    api_key = None

    if provider_type == "github_copilot":
        oauth_config = draw(oauth_config_strategy())
    elif provider_type == "bedrock":
        region = draw(st.sampled_from(["us-east-1", "us-west-2", "eu-west-1"]))
    elif provider_type == "openai_compatible":
        endpoint = draw(st.just("https://api.openai.com/v1"))
        api_key = draw(_identifier)

    return ProviderConfig(
        provider_type=provider_type,
        model_id=model_id,
        endpoint=endpoint,
        api_key=api_key,
        region=region,
        temperature=draw(st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)),
        max_tokens=draw(st.integers(min_value=1, max_value=8192)),
        oauth_config=oauth_config,
    )


@st.composite
def agent_config_strategy(draw, name: str | None = None) -> AgentConfig:
    agent_name = name or draw(_identifier)
    provider = draw(provider_config_strategy())
    return AgentConfig(
        name=agent_name,
        model=f"{provider.provider_type}/{provider.model_id}",
        provider_config=provider,
        description=draw(_safe_text),
        system_prompt=draw(st.one_of(st.none(), _safe_text)),
        faiss_indexes=draw(st.lists(_faiss_indexes, min_size=0, max_size=4, unique=True)),
        tools=draw(st.lists(_tool_names, min_size=0, max_size=5, unique=True)),
        template=draw(st.one_of(st.none(), _identifier)),
    )


@st.composite
def pipeline_config_strategy(draw) -> PipelineConfig:
    num_agents = draw(st.integers(min_value=1, max_value=4))
    # Ensure unique agent names
    names = [f"agent_{i}" for i in range(num_agents)]
    agents = [draw(agent_config_strategy(name=n)) for n in names]

    output_fmts = draw(st.lists(_output_formats, min_size=1, max_size=3, unique=True))

    return PipelineConfig(
        name=draw(_identifier),
        agents=agents,
        output=OutputConfig(template=draw(_identifier), formats=output_fmts),
        execution_timeout=draw(st.integers(min_value=1, max_value=3600)),
    )


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@given(config=pipeline_config_strategy(), fmt=_formats)
@settings(max_examples=100)
def test_serialize_then_parse_produces_equivalent_config(config: PipelineConfig, fmt: str):
    """Property 26: For any valid PipelineConfig, serialize then parse produces
    an equivalent PipelineConfig object.

    **Validates: Requirements 19.1, 19.2, 19.3, 19.4**
    """
    serialized = serialize_config(config, fmt)
    parsed = parse_config(serialized, fmt)
    assert parsed == config, (
        f"Round-trip failed for format={fmt!r}.\n"
        f"Original: {config}\n"
        f"Parsed:   {parsed}"
    )


@given(config=pipeline_config_strategy(), fmt=_formats)
@settings(max_examples=100)
def test_idempotent_round_trip(config: PipelineConfig, fmt: str):
    """Property 26 (idempotent): parse(serialize(parse(raw))) == parse(raw).

    Starting from a valid PipelineConfig, serialize to raw, parse it back,
    serialize again, and parse once more. The two parsed results must be equal.

    **Validates: Requirements 19.1, 19.2, 19.3, 19.4**
    """
    raw = serialize_config(config, fmt)
    first_parse = parse_config(raw, fmt)
    re_serialized = serialize_config(first_parse, fmt)
    second_parse = parse_config(re_serialized, fmt)
    assert first_parse == second_parse, (
        f"Idempotent round-trip failed for format={fmt!r}.\n"
        f"First parse:  {first_parse}\n"
        f"Second parse: {second_parse}"
    )
