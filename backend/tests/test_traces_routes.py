"""Tests for trace API routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = "user-1"
    return user


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
    def test_get_trace_tree_returns_list(
        self, mock_get_svc: MagicMock, client: TestClient
    ) -> None:
        goal_id = str(uuid.uuid4())
        svc = MagicMock()
        svc.get_trace_tree = AsyncMock(return_value=[])
        mock_get_svc.return_value = svc

        resp = client.get(f"/api/v1/traces/{goal_id}/tree")
        assert resp.status_code == 200
        assert resp.json() == []


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
