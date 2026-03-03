"""Unit tests for MetricsCollector and metrics API endpoints."""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from app.models.metrics import AgentMetrics, SessionMetrics
from app.services.metrics_collector import MetricsCollector


# ── MetricsCollector unit tests ──────────────────────────────────────


class TestRecord:
    """Tests for MetricsCollector.record()."""

    def test_single_record(self) -> None:
        mc = MetricsCollector()
        mc.record("s1", "agent-a", 100, 50)

        metrics = mc.get_session_metrics("s1")
        assert len(metrics.agent_metrics) == 1
        am = metrics.agent_metrics[0]
        assert am.agent_id == "agent-a"
        assert am.input_tokens == 100
        assert am.output_tokens == 50
        assert am.llm_call_count == 1

    def test_multiple_records_same_agent_accumulate(self) -> None:
        mc = MetricsCollector()
        mc.record("s1", "agent-a", 100, 50)
        mc.record("s1", "agent-a", 200, 80)

        am = mc.get_session_metrics("s1").agent_metrics[0]
        assert am.input_tokens == 300
        assert am.output_tokens == 130
        assert am.llm_call_count == 2

    def test_multiple_agents_tracked_separately(self) -> None:
        mc = MetricsCollector()
        mc.record("s1", "agent-a", 10, 5)
        mc.record("s1", "agent-b", 20, 15)

        metrics = mc.get_session_metrics("s1")
        ids = {am.agent_id for am in metrics.agent_metrics}
        assert ids == {"agent-a", "agent-b"}

    def test_multiple_sessions_isolated(self) -> None:
        mc = MetricsCollector()
        mc.record("s1", "agent-a", 10, 5)
        mc.record("s2", "agent-a", 99, 88)

        m1 = mc.get_session_metrics("s1").agent_metrics[0]
        m2 = mc.get_session_metrics("s2").agent_metrics[0]
        assert m1.input_tokens == 10
        assert m2.input_tokens == 99


class TestRecordFromNodeResult:
    """Tests for MetricsCollector.record_from_node_result()."""

    def test_extracts_usage_from_node_result(self) -> None:
        mc = MetricsCollector()
        node_result = {
            "agent_id": "summarizer",
            "usage": {"input_tokens": 500, "output_tokens": 200},
        }
        mc.record_from_node_result("s1", node_result)

        am = mc.get_session_metrics("s1").agent_metrics[0]
        assert am.agent_id == "summarizer"
        assert am.input_tokens == 500
        assert am.output_tokens == 200
        assert am.llm_call_count == 1

    def test_missing_usage_defaults_to_zero(self) -> None:
        mc = MetricsCollector()
        mc.record_from_node_result("s1", {"agent_id": "x"})

        am = mc.get_session_metrics("s1").agent_metrics[0]
        assert am.input_tokens == 0
        assert am.output_tokens == 0
        assert am.llm_call_count == 1

    def test_missing_agent_id_defaults_to_unknown(self) -> None:
        mc = MetricsCollector()
        mc.record_from_node_result("s1", {"usage": {"input_tokens": 1, "output_tokens": 2}})

        am = mc.get_session_metrics("s1").agent_metrics[0]
        assert am.agent_id == "unknown"


class TestGetSessionMetrics:
    """Tests for MetricsCollector.get_session_metrics()."""

    def test_returns_session_metrics_type(self) -> None:
        mc = MetricsCollector()
        mc.record("s1", "a", 1, 2)
        result = mc.get_session_metrics("s1")
        assert isinstance(result, SessionMetrics)
        assert result.session_id == "s1"

    def test_unknown_session_returns_empty(self) -> None:
        mc = MetricsCollector()
        result = mc.get_session_metrics("nonexistent")
        assert result.session_id == "nonexistent"
        assert result.agent_metrics == []


class TestExportCsv:
    """Tests for MetricsCollector.export_csv()."""

    def test_csv_header_and_rows(self) -> None:
        mc = MetricsCollector()
        mc.record("s1", "agent-a", 100, 50)
        mc.record("s1", "agent-b", 200, 80)

        csv_str = mc.export_csv("s1")
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)

        assert rows[0] == ["session_id", "agent_id", "input_tokens", "output_tokens", "llm_call_count"]
        # Data rows (order may vary, so check as set of tuples)
        data = {tuple(r) for r in rows[1:]}
        assert ("s1", "agent-a", "100", "50", "1") in data
        assert ("s1", "agent-b", "200", "80", "1") in data

    def test_csv_empty_session(self) -> None:
        mc = MetricsCollector()
        csv_str = mc.export_csv("empty")
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        # Only header row
        assert len(rows) == 1
        assert rows[0][0] == "session_id"

    def test_csv_values_match_recorded(self) -> None:
        mc = MetricsCollector()
        mc.record("s1", "a", 10, 20)
        mc.record("s1", "a", 30, 40)

        csv_str = mc.export_csv("s1")
        reader = csv.reader(io.StringIO(csv_str))
        rows = list(reader)
        data_row = rows[1]
        assert data_row == ["s1", "a", "40", "60", "2"]


# ── API endpoint tests ──────────────────────────────────────────────


@pytest.fixture()
def client() -> TestClient:
    """Create a test client with auth dependency overridden."""
    from app.api.metrics import get_metrics_collector, router
    from app.middleware.auth import get_current_user
    from app.models.auth import UserContext

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    # Override auth to always return a test user
    app.dependency_overrides[get_current_user] = lambda: UserContext(
        user_id="test-user",
        username="tester",
        roles=["user"],
        token="fake-token",
    )

    # Fresh collector per test
    collector = MetricsCollector()
    app.dependency_overrides[get_metrics_collector] = lambda: collector

    return TestClient(app), collector  # type: ignore[return-value]


class TestMetricsEndpoints:
    """Tests for GET /api/metrics/{session_id} and GET /api/metrics/{session_id}/csv."""

    def test_get_session_metrics_json(self, client) -> None:
        test_client, collector = client
        collector.record("sess-1", "agent-x", 100, 50)

        resp = test_client.get("/api/metrics/sess-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "sess-1"
        assert len(body["agent_metrics"]) == 1
        am = body["agent_metrics"][0]
        assert am["agent_id"] == "agent-x"
        assert am["input_tokens"] == 100
        assert am["output_tokens"] == 50
        assert am["llm_call_count"] == 1

    def test_get_session_metrics_empty(self, client) -> None:
        test_client, _ = client
        resp = test_client.get("/api/metrics/no-such-session")
        assert resp.status_code == 200
        assert resp.json()["agent_metrics"] == []

    def test_get_session_metrics_csv(self, client) -> None:
        test_client, collector = client
        collector.record("sess-1", "agent-x", 100, 50)

        resp = test_client.get("/api/metrics/sess-1/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in resp.headers.get("content-disposition", "")

        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        assert rows[0] == ["session_id", "agent_id", "input_tokens", "output_tokens", "llm_call_count"]
        assert rows[1] == ["sess-1", "agent-x", "100", "50", "1"]

    def test_csv_empty_session(self, client) -> None:
        test_client, _ = client
        resp = test_client.get("/api/metrics/empty/csv")
        assert resp.status_code == 200
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 1  # header only
