"""Tests for trace API routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.core.delegation_trace import DelegationTrace
from src.main import app


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = "user-1"
    return user


def _make_trace(
    *,
    delegatee: str = "scout",
    cost_usd: float = 0.1,
    duration_ms: int = 5000,
    status: str = "completed",
    verification_passed: bool | None = None,
) -> DelegationTrace:
    """Helper to build a DelegationTrace for testing."""
    vr = None
    if verification_passed is not None:
        vr = {
            "passed": verification_passed,
            "issues": [] if verification_passed else ["stale data"],
            "confidence": 0.9,
            "suggestions": [],
        }
    return DelegationTrace(
        trace_id=str(uuid.uuid4()),
        goal_id=str(uuid.uuid4()),
        parent_trace_id=None,
        user_id="user-1",
        delegator="orchestrator",
        delegatee=delegatee,
        task_description=f"Task for {delegatee}",
        cost_usd=cost_usd,
        status=status,
        duration_ms=duration_ms,
        verification_result=vr,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """Create a test client with mocked auth via dependency override."""

    async def _override() -> MagicMock:
        return _mock_user()

    app.dependency_overrides[get_current_user] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestTraceTreeEndpoint:
    @patch("src.api.routes.traces._get_service")
    def test_get_trace_tree_empty(
        self, mock_get_svc: MagicMock, client: TestClient
    ) -> None:
        goal_id = str(uuid.uuid4())
        svc = MagicMock()
        svc.get_trace_tree = AsyncMock(return_value=[])
        mock_get_svc.return_value = svc

        resp = client.get(f"/api/v1/traces/{goal_id}/tree")
        assert resp.status_code == 200
        body = resp.json()
        assert body["traces"] == []
        assert body["summary"]["agent_count"] == 0
        assert body["summary"]["unique_agents"] == []
        assert body["summary"]["total_cost_usd"] == 0.0
        assert body["summary"]["total_duration_ms"] == 0
        assert body["summary"]["verification_passes"] == 0
        assert body["summary"]["verification_failures"] == 0
        assert body["summary"]["retries"] == 0

    @patch("src.api.routes.traces._get_service")
    def test_get_trace_tree_with_traces(
        self, mock_get_svc: MagicMock, client: TestClient
    ) -> None:
        goal_id = str(uuid.uuid4())
        traces = [
            _make_trace(delegatee="scout", cost_usd=0.08, duration_ms=12300, verification_passed=True),
            _make_trace(delegatee="analyst", cost_usd=0.12, duration_ms=8100, verification_passed=True),
            _make_trace(
                delegatee="strategist",
                cost_usd=0.15,
                duration_ms=15200,
                status="re_delegated",
                verification_passed=False,
            ),
        ]
        svc = MagicMock()
        svc.get_trace_tree = AsyncMock(return_value=traces)
        mock_get_svc.return_value = svc

        resp = client.get(f"/api/v1/traces/{goal_id}/tree")
        assert resp.status_code == 200
        body = resp.json()

        assert len(body["traces"]) == 3
        summary = body["summary"]
        assert summary["agent_count"] == 3
        assert set(summary["unique_agents"]) == {"scout", "analyst", "strategist"}
        assert summary["total_cost_usd"] == 0.35
        assert summary["total_duration_ms"] == 35600
        assert summary["verification_passes"] == 2
        assert summary["verification_failures"] == 1
        assert summary["retries"] == 1


class TestRecentTracesEndpoint:
    @patch("src.api.routes.traces._get_service")
    def test_get_recent_traces(
        self, mock_get_svc: MagicMock, client: TestClient
    ) -> None:
        svc = MagicMock()
        svc.get_user_traces = AsyncMock(return_value=[])
        mock_get_svc.return_value = svc

        resp = client.get("/api/v1/traces/recent")
        assert resp.status_code == 200
        assert resp.json() == []
