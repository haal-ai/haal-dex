# Feature: intent, Property 13: Tool permission enforcement
"""Property 13: Tool permission enforcement

For any agent with permitted tools P and any tool T not in P, invoking T
should be denied and the denied attempt should be logged.

**Validates: Requirements 6.6**

Strategy:
- Draw a random non-empty subset of ALL_TOOLS keys as the permitted set P.
- Compute the denied set D = ALL_TOOLS.keys() - P.
- Build a permission filter function (mirroring AgentFactory behaviour) that
  only returns tools in P.
- Verify that every tool in D is excluded from the filtered result.
- Verify that a logging callback is invoked for each denied tool.
"""

from __future__ import annotations

import logging
from hypothesis import given, settings, assume, strategies as st

from app.engine.tools import ALL_TOOLS

# ---------------------------------------------------------------------------
# Permission filter (mirrors AgentFactory.create_agent tool selection)
# ---------------------------------------------------------------------------

def filter_permitted_tools(
    requested_tools: list[str],
    permitted_tool_names: set[str],
    logger: logging.Logger | None = None,
) -> list[object]:
    """Return only the tools whose names are in *permitted_tool_names*.

    For any requested tool not in the permitted set, log a denied message.
    This mirrors the AgentFactory behaviour described in the design.
    """
    permitted = []
    for tool_name in requested_tools:
        if tool_name in permitted_tool_names and tool_name in ALL_TOOLS:
            permitted.append(ALL_TOOLS[tool_name])
        else:
            if logger is not None:
                logger.warning(
                    "Tool '%s' denied — not in permitted set %s",
                    tool_name,
                    permitted_tool_names,
                )
    return permitted


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_all_tool_names = sorted(ALL_TOOLS.keys())

# A non-empty strict subset of ALL_TOOLS keys (so there is always at least
# one denied tool).
@st.composite
def permitted_and_denied(draw):
    """Draw a permitted subset P and compute the denied set D.

    Guarantees |P| >= 1 and |D| >= 1.
    """
    subset = draw(
        st.frozensets(st.sampled_from(_all_tool_names), min_size=1, max_size=len(_all_tool_names) - 1)
    )
    denied = set(_all_tool_names) - subset
    assume(len(denied) >= 1)
    return set(subset), denied


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(pd=permitted_and_denied())
@settings(max_examples=100)
def test_denied_tools_are_excluded_and_logged(pd: tuple[set[str], set[str]]):
    """Property 13: For any agent with permitted tools P and tool T not in P,
    T is denied and logged.

    **Validates: Requirements 6.6**
    """
    permitted_names, denied_names = pd

    # Collect log messages
    logged_denials: list[str] = []

    class _CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            logged_denials.append(record.getMessage())

    logger = logging.getLogger("test_tool_permission")
    logger.setLevel(logging.WARNING)
    handler = _CapturingHandler()
    logger.addHandler(handler)

    try:
        # Request ALL tools — the filter should only return permitted ones.
        result = filter_permitted_tools(
            requested_tools=_all_tool_names,
            permitted_tool_names=permitted_names,
            logger=logger,
        )

        # 1. Every returned tool must be in the permitted set.
        returned_fns = set(result)
        for name in permitted_names:
            assert ALL_TOOLS[name] in returned_fns, (
                f"Permitted tool {name!r} missing from result"
            )

        # 2. No denied tool should appear in the result.
        for name in denied_names:
            assert ALL_TOOLS[name] not in returned_fns, (
                f"Denied tool {name!r} should not be in result"
            )

        # 3. A log entry must exist for each denied tool.
        for name in denied_names:
            assert any(name in msg for msg in logged_denials), (
                f"No denial log found for tool {name!r}; "
                f"logged: {logged_denials}"
            )
    finally:
        logger.removeHandler(handler)
