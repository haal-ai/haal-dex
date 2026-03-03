# Feature: intent, Property 22: Metrics recording and CSV export round trip
"""Property 22: Metrics recording and CSV export round trip

For any session with agent executions, the Metrics_Collector should record
input tokens, output tokens, and LLM call count per agent. Exporting as CSV
and parsing the CSV should yield the same metric values that were recorded.

**Validates: Requirements 11.1, 11.2**

Strategy:
- Generate a random session_id (text)
- Generate a list of (agent_id, input_tokens, output_tokens) records
- Record them all via MetricsCollector.record()
- Export CSV via MetricsCollector.export_csv()
- Parse the CSV back
- Verify that per-agent aggregated totals (input_tokens, output_tokens,
  llm_call_count) in the CSV match the expected aggregated values
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict

from hypothesis import given, settings, strategies as st

from app.services.metrics_collector import MetricsCollector

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Identifiers: non-empty printable strings without commas/newlines (CSV-safe)
_id_chars = st.characters(
    whitelist_categories=("L", "N"),
    min_codepoint=48,
    max_codepoint=122,
)
_session_id = st.text(_id_chars, min_size=1, max_size=20)
_agent_id = st.text(_id_chars, min_size=1, max_size=20)

# Token counts: non-negative integers (realistic range)
_tokens = st.integers(min_value=0, max_value=100_000)

# A single record tuple: (agent_id, input_tokens, output_tokens)
_record = st.tuples(_agent_id, _tokens, _tokens)

# A non-empty list of records for a session
_records = st.lists(_record, min_size=1, max_size=30)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _aggregate(records: list[tuple[str, int, int]]) -> dict[str, dict[str, int]]:
    """Compute expected per-agent aggregates from raw records."""
    agg: dict[str, dict[str, int]] = defaultdict(
        lambda: {"input_tokens": 0, "output_tokens": 0, "llm_call_count": 0}
    )
    for agent_id, inp, out in records:
        agg[agent_id]["input_tokens"] += inp
        agg[agent_id]["output_tokens"] += out
        agg[agent_id]["llm_call_count"] += 1
    return dict(agg)


def _parse_csv(csv_str: str) -> dict[str, dict[str, int]]:
    """Parse an exported CSV string into a dict keyed by agent_id."""
    reader = csv.DictReader(io.StringIO(csv_str))
    result: dict[str, dict[str, int]] = {}
    for row in reader:
        result[row["agent_id"]] = {
            "input_tokens": int(row["input_tokens"]),
            "output_tokens": int(row["output_tokens"]),
            "llm_call_count": int(row["llm_call_count"]),
        }
    return result


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@given(session_id=_session_id, records=_records)
@settings(max_examples=100)
def test_metrics_csv_round_trip(
    session_id: str,
    records: list[tuple[str, int, int]],
):
    """Property 22: Record metrics, export CSV, parse CSV yields same values.

    **Validates: Requirements 11.1, 11.2**
    """
    mc = MetricsCollector()

    # Record all entries
    for agent_id, input_tokens, output_tokens in records:
        mc.record(session_id, agent_id, input_tokens, output_tokens)

    # Export CSV
    csv_str = mc.export_csv(session_id)

    # Parse CSV
    parsed = _parse_csv(csv_str)

    # Compute expected aggregates
    expected = _aggregate(records)

    # Verify: same set of agents
    assert set(parsed.keys()) == set(expected.keys()), (
        f"Agent mismatch: CSV has {set(parsed.keys())}, "
        f"expected {set(expected.keys())}"
    )

    # Verify: per-agent values match
    for agent_id in expected:
        assert parsed[agent_id]["input_tokens"] == expected[agent_id]["input_tokens"], (
            f"input_tokens mismatch for agent {agent_id!r}: "
            f"CSV={parsed[agent_id]['input_tokens']}, expected={expected[agent_id]['input_tokens']}"
        )
        assert parsed[agent_id]["output_tokens"] == expected[agent_id]["output_tokens"], (
            f"output_tokens mismatch for agent {agent_id!r}: "
            f"CSV={parsed[agent_id]['output_tokens']}, expected={expected[agent_id]['output_tokens']}"
        )
        assert parsed[agent_id]["llm_call_count"] == expected[agent_id]["llm_call_count"], (
            f"llm_call_count mismatch for agent {agent_id!r}: "
            f"CSV={parsed[agent_id]['llm_call_count']}, expected={expected[agent_id]['llm_call_count']}"
        )

    # Verify: CSV header is correct
    reader = csv.reader(io.StringIO(csv_str))
    header = next(reader)
    assert header == ["session_id", "agent_id", "input_tokens", "output_tokens", "llm_call_count"]

    # Verify: session_id column matches in every row
    for row in reader:
        assert row[0] == session_id, (
            f"session_id mismatch in CSV row: got {row[0]!r}, expected {session_id!r}"
        )
