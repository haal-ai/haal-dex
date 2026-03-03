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
VALID_OUTPUT_FORMATS = {"xml", "pdf", "docx", "md", "html"}
FAISS_INDEX_RANGE = range(0, 4)  # 0-3 inclusive


def validate_config(config: PipelineConfig) -> list[str]:
    """Validate a PipelineConfig and return a list of error strings.

    An empty list indicates the configuration is valid.
    """
    errors: list[str] = []

    # --- Pipeline-level checks ---
    if not config.agents:
        errors.append("Pipeline must have at least one agent")

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

        if ptype == "bedrock" and not agent.provider_config.region:
            errors.append(
                f"{prefix}: provider_type 'bedrock' requires region"
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
