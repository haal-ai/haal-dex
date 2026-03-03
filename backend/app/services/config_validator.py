"""Pipeline configuration validator.

Validates a PipelineConfig instance for semantic correctness beyond what the
parser checks (structural validity).  Returns a list of human-readable error
strings — an empty list means the config is valid.

Validates: Requirements 14.3, 14.4
"""

from __future__ import annotations

from app.models.pipeline import PipelineConfig

VALID_PROVIDER_TYPES = {"bedrock", "openai_compatible", "github_copilot"}
VALID_TOOL_NAMES = {"read", "write", "python_repl", "shell", "query_faiss"}
VALID_OUTPUT_FORMATS = {"pdf", "docx", "md", "html", "pptx"}
FAISS_INDEX_RANGE = range(0, 4)  # 0-3 inclusive


def validate_config(config: PipelineConfig) -> list[str]:
    """Validate a PipelineConfig and return a list of error strings.

    An empty list indicates the configuration is valid.
    """
    errors: list[str] = []

    # --- Pipeline-level checks ---
    if not config.agents:
        errors.append("Pipeline must have at least one agent")

    # --- Output compatibility checks ---
    if "pptx" in (config.output.formats or []) and config.output.template != "demo-slide-outline":
        errors.append(
            "output: pptx export requires template 'demo-slide-outline' (slide-outline intermediate format)."
        )

    # --- Agent-level checks ---
    seen_names: set[str] = set()
    for i, agent in enumerate(config.agents):
        prefix = f"agents[{i}]"

        # Non-empty name
        if not agent.name or not agent.name.strip():
            errors.append(f"{prefix}: agent name must be non-empty")

        # Duplicate agent names
        if agent.name in seen_names:
            errors.append(f"{prefix}: duplicate agent name '{agent.name}'")
        seen_names.add(agent.name)

        # Valid provider_type
        ptype = agent.provider_config.provider_type
        if ptype not in VALID_PROVIDER_TYPES:
            errors.append(
                f"{prefix}: invalid provider_type '{ptype}'. "
                f"Must be one of {sorted(VALID_PROVIDER_TYPES)}"
            )

        # Provider-specific requirements
        if ptype == "github_copilot" and agent.provider_config.oauth_config is None:
            errors.append(
                f"{prefix}: provider_type 'github_copilot' requires oauth_config"
            )

        if ptype == "bedrock":
            model_id = agent.provider_config.model_id or ""
            inference_profile_id = agent.provider_config.inference_profile_id

            # Bedrock may mark unversioned Claude 3 IDs as "Legacy" and deny access.
            legacy_to_active = {
                "anthropic.claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
                "anthropic.claude-3-opus": "anthropic.claude-3-opus-20240229-v1:0",
                "anthropic.claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
            }
            if model_id in legacy_to_active:
                errors.append(
                    f"{prefix}: bedrock model_id '{model_id}' is legacy/unsupported in some accounts. "
                    f"Use '{legacy_to_active[model_id]}' (or another active Bedrock model ID)."
                )

            inference_profile_required_prefixes = (
                "anthropic.claude-sonnet-4",
                "anthropic.claude-opus-4",
                "anthropic.claude-3-7-sonnet",
            )
            if model_id.startswith(inference_profile_required_prefixes) and not inference_profile_id:
                errors.append(
                    f"{prefix}: bedrock model_id '{model_id}' requires inference_profile_id (Bedrock inference profile ARN/ID). "
                    "This model may not support on-demand throughput in your account; create/select an inference profile in Bedrock and paste its ARN/ID."
                )

        # Tool names
        for tool_name in agent.tools:
            if tool_name not in VALID_TOOL_NAMES:
                errors.append(
                    f"{prefix}: invalid tool name '{tool_name}'. "
                    f"Must be one of {sorted(VALID_TOOL_NAMES)}"
                )

        # FAISS index range
        for idx in agent.faiss_indexes:
            if idx not in FAISS_INDEX_RANGE:
                errors.append(
                    f"{prefix}: FAISS index {idx} out of range. Must be 0-3"
                )

    # --- Output checks ---
    if not config.output.formats:
        errors.append("output: must have at least one format")

    for fmt in config.output.formats:
        if fmt not in VALID_OUTPUT_FORMATS:
            errors.append(
                f"output: invalid format '{fmt}'. "
                f"Must be one of {sorted(VALID_OUTPUT_FORMATS)}"
            )

    return errors
