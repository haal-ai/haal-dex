"""AgentFactory: creates strands.Agent instances from AgentConfig.

Resolves the model provider via ModelFactory, selects permitted @tool functions
from ALL_TOOLS, automatically includes query_faiss when FAISS index bindings
exist, and logs denied tool access for non-permitted tools.

Requirements: 3.1, 4.1, 5.2, 6.5, 6.6
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.engine.model_factory import ModelFactory
from app.engine.tools import ALL_TOOLS
from app.models.pipeline import AgentConfig

logger = logging.getLogger(__name__)

# Try importing Strands SDK Agent; fall back gracefully if not installed.
try:
    from strands import Agent

    _STRANDS_AGENT_AVAILABLE = True
except ImportError:
    Agent = None  # type: ignore[assignment,misc]
    _STRANDS_AGENT_AVAILABLE = False


@dataclass
class AgentSpec:
    """Fallback representation when strands.Agent is not available."""

    model: Any
    tools: list[Any]
    system_prompt: str
    name: str


class AgentFactory:
    """Creates strands.Agent instances from AgentConfig."""

    def __init__(self, model_factory: ModelFactory) -> None:
        self.model_factory = model_factory

    def create_agent(self, agent_config: AgentConfig) -> Any:
        """Create a strands.Agent with the correct model, tools, and system prompt.

        Steps:
        1. Create model via ModelFactory.create_model(agent_config.provider_config)
        2. Filter ALL_TOOLS to only include tools listed in agent_config.tools
        3. If agent_config.faiss_indexes is non-empty, include query_faiss tool
        4. Log warning for any tool in agent_config.tools that's not in ALL_TOOLS
        5. Return a strands.Agent instance (or AgentSpec if strands not installed)

        Args:
            agent_config: Configuration for the agent to create.

        Returns:
            A strands.Agent instance, or an AgentSpec dataclass if strands is not installed.
        """
        # 1. Resolve model via ModelFactory
        model = self.model_factory.create_model(agent_config.provider_config)

        # 2 & 4. Select permitted tools, log warnings for unknown tools
        permitted_tools: list[Any] = []
        for tool_name in agent_config.tools:
            if tool_name in ALL_TOOLS:
                permitted_tools.append(ALL_TOOLS[tool_name])
            else:
                logger.warning(
                    "Agent '%s': tool '%s' is not in the permitted tool set and will be denied.",
                    agent_config.name,
                    tool_name,
                )

        # 3. Add query_faiss tool if agent has FAISS index bindings
        if agent_config.faiss_indexes:
            faiss_tool = ALL_TOOLS.get("query_faiss")
            if faiss_tool is not None and faiss_tool not in permitted_tools:
                permitted_tools.append(faiss_tool)

        # 5. Resolve system prompt: prefer explicit system_prompt, fall back to description
        system_prompt = agent_config.system_prompt or agent_config.description

        # Build and return the agent
        if _STRANDS_AGENT_AVAILABLE:
            return Agent(
                model=model,
                tools=permitted_tools,
                system_prompt=system_prompt,
                name=agent_config.name,
            )

        # Fallback when strands is not installed
        return AgentSpec(
            model=model,
            tools=permitted_tools,
            system_prompt=system_prompt,
            name=agent_config.name,
        )
