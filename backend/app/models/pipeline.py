from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OAuthConfig:
    client_id: str
    client_secret: str
    token_url: str
    scopes: list[str]


@dataclass
class ProviderConfig:
    provider_type: str  # "bedrock" | "openai_compatible" | "github_copilot"
    model_id: str
    inference_profile_id: str | None = None
    endpoint: str | None = None
    api_key: str | None = None
    region: str | None = None
    temperature: float = 0.7
    max_tokens: int = 2048
    oauth_config: OAuthConfig | None = None


@dataclass
class AgentConfig:
    name: str
    model: str
    provider_config: ProviderConfig
    description: str
    system_prompt: str | None = None
    faiss_indexes: list[int] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    template: str | None = None


@dataclass
class OutputConfig:
    template: str
    formats: list[str]


@dataclass
class PipelineConfig:
    name: str
    agents: list[AgentConfig]
    output: OutputConfig
    execution_timeout: int = 600
