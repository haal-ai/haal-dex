"""ModelFactory: creates Strands model provider instances from ProviderConfig.

Supports Bedrock, OpenAI-compatible, and GitHub Copilot providers.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path
from dataclasses import dataclass

from app.engine.bedrock_runtime_proxy import BedrockRuntimeClientProxy, resolve_aws_profile
from app.models.pipeline import ProviderConfig

# Try importing Strands SDK model providers; fall back to None if unavailable.
try:
    from strands.models import BedrockModel
except ImportError:
    BedrockModel = None  # type: ignore[assignment,misc]

try:
    from strands.models.openai import OpenAIModel
except ImportError:
    OpenAIModel = None  # type: ignore[assignment,misc]

from app.engine.github_copilot_model import GitHubCopilotModel


@dataclass
class HealthStatus:
    """Result of a provider health check."""

    healthy: bool
    provider: str
    error: str | None = None


class ModelFactory:
    """Creates Strands model provider instances from ProviderConfig."""

    @staticmethod
    def _infer_aws_region_from_config() -> str | None:
        """Infer AWS region from ~/.aws/config.

        Resolution order:
        1) AWS_PROFILE env var (or "default") selects the profile section
        2) Read `region` from that profile section

        Supports both section naming conventions used by AWS CLI:
        - [default]
        - [profile my-profile]
        """
        profile = os.getenv("AWS_PROFILE") or "default"

        config_path = Path(os.path.expanduser("~")) / ".aws" / "config"
        if not config_path.exists():
            return None

        parser = configparser.RawConfigParser()
        try:
            parser.read(config_path, encoding="utf-8")
        except Exception:
            return None

        candidates = [
            profile,
            f"profile {profile}",
        ]

        for section in candidates:
            if parser.has_option(section, "region"):
                value = parser.get(section, "region").strip()
                if value:
                    return value

        return None

    def create_model(self, provider_config: ProviderConfig):
        """Create the appropriate Strands model provider based on config.

        Args:
            provider_config: Provider configuration specifying type, model, and credentials.

        Returns:
            A model provider instance (BedrockModel, OpenAIModel, or GitHubCopilotModel).

        Raises:
            ValueError: If the provider_type is unsupported or the required SDK class is unavailable.
        """
        match provider_config.provider_type:
            case "bedrock":
                if BedrockModel is None:
                    raise ValueError(
                        "strands.models.BedrockModel is not available. "
                        "Install strands-agents to use the Bedrock provider."
                    )

                region = (
                    provider_config.region
                    or os.getenv("AWS_REGION")
                    or os.getenv("AWS_DEFAULT_REGION")
                )
                profile = (
                    provider_config.profile
                    or os.getenv("AWS_PROFILE")
                    or os.getenv("AWS_DEFAULT_PROFILE")
                )

                resolved_model_id = (
                    provider_config.inference_profile_id
                    or provider_config.model_id
                )
                bedrock_kwargs = {
                    "model_id": resolved_model_id,
                    "temperature": provider_config.temperature,
                    "max_tokens": provider_config.max_tokens,
                }
                if profile:
                    try:
                        import boto3

                        bedrock_kwargs["boto_session"] = boto3.Session(
                            profile_name=profile,
                            region_name=region,
                        )
                    except Exception:
                        pass
                if "boto_session" not in bedrock_kwargs:
                    bedrock_kwargs["region_name"] = region

                model = BedrockModel(**bedrock_kwargs)

                client = getattr(model, "client", None)
                if client is not None:
                    try:
                        model.client = BedrockRuntimeClientProxy(
                            client,
                            model_id=resolved_model_id,
                            aws_profile=profile,
                            aws_region=region,
                        )
                    except Exception:
                        pass
                return model
            case "openai_compatible":
                if OpenAIModel is None:
                    raise ValueError(
                        "strands.models.openai.OpenAIModel is not available. "
                        "Install strands-agents to use the OpenAI-compatible provider."
                    )
                client_args: dict = {"api_key": provider_config.api_key}
                if provider_config.endpoint:
                    client_args["base_url"] = provider_config.endpoint
                return OpenAIModel(
                    client_args=client_args,
                    model_id=provider_config.model_id,
                )
            case "github_copilot":
                return GitHubCopilotModel(
                    oauth_config=provider_config.oauth_config,
                    model_id=provider_config.model_id,
                )
            case _:
                raise ValueError(f"Unsupported provider type: {provider_config.provider_type}")

    async def check_provider_health(self, provider_config: ProviderConfig) -> HealthStatus:
        """Verify connectivity to the configured provider.

        Attempts to create the model instance. If creation succeeds, the
        provider is considered healthy. Any exception during creation is
        captured and returned as an unhealthy status.
        """
        try:
            self.create_model(provider_config)
            return HealthStatus(healthy=True, provider=provider_config.provider_type)
        except Exception as e:
            return HealthStatus(
                healthy=False,
                provider=provider_config.provider_type,
                error=str(e),
            )
