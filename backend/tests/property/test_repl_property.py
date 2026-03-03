# Feature: intent, Property 12: Python REPL correctness
"""Property 12: Python REPL correctness

For any valid Python expression, the Python REPL tool should return the
correct evaluation result.

**Validates: Requirements 6.3**

Strategy:
- Generate random integer arithmetic expressions (addition, subtraction,
  multiplication) using Hypothesis strategies.
- Execute via the python_repl tool and verify the output matches the
  expected Python evaluation.
- Avoid division to prevent ZeroDivisionError edge cases.
- Avoid excessively large numbers to keep subprocess execution fast.
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from app.engine.tools import python_repl

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call(tool_fn, **kwargs):
    """Call a tool function, stripping any Strands wrapper if present."""
    fn = getattr(tool_fn, "__wrapped__", tool_fn)
    return fn(**kwargs)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Small integers to keep arithmetic manageable and fast.
_small_ints = st.integers(min_value=-1000, max_value=1000)
_operators = st.sampled_from(["+", "-", "*"])


@st.composite
def arithmetic_expression(draw):
    """Draw a simple binary arithmetic expression and its expected result.

    Returns (expression_string, expected_value).
    """
    a = draw(_small_ints)
    op = draw(_operators)
    b = draw(_small_ints)
    expr = f"{a} {op} {b}"
    expected = eval(expr)  # noqa: S307 — safe: only integers and +-*
    return expr, expected


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------

@given(expr_and_expected=arithmetic_expression())
@settings(max_examples=100, deadline=None)
def test_python_repl_returns_correct_result(expr_and_expected: tuple[str, int]):
    """Property 12: For any valid Python expression, REPL returns correct
    result.

    **Validates: Requirements 6.3**
    """
    expr, expected = expr_and_expected
    code = f"print({expr})"

    result = _call(python_repl, code=code)

    assert result.strip() == str(expected), (
        f"REPL returned {result.strip()!r} for expression {expr!r}, "
        f"expected {expected!r}"
    )
