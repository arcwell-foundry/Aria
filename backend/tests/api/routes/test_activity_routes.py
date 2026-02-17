"""Tests for activity API routes.

Tests cover:
- GET /api/v1/activity — paginated feed with filters
- GET /api/v1/activity/poll — real-time polling
- GET /api/v1/activity/stats — activity summary stats
- GET /api/v1/activity/{id} — single activity detail
- POST /api/v1/activity — record activity
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.api.routes import activity


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(activity.router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    user = MagicMock()
    user.id = "test-user-123"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    app = create_test_app()

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


SAMPLE_ACTIVITY = {
    "id": "act-1",
    "user_id": "test-user-123",
    "agent": "hunter",
    "activity_type": "lead_discovered",
    "title": "Discovered Acme Bio",
    "description": "Found via web research",
    "reasoning": "Matched ICP",
    "confidence": 0.85,
    "related_entity_type": "lead",
    "related_entity_id": "lead-1",
    "metadata": {},
    "created_at": "2026-02-17T10:00:00Z",
    "entity_details": None,
}


# ------------------------------------------------------------------ #
# GET /api/v1/activity                                                #
# ------------------------------------------------------------------ #


class TestGetActivityFeed:
    """Tests for GET /api/v1/activity."""

    def test_returns_paginated_feed(self, test_client: TestClient) -> None:
        feed_result = {
            "activities": [SAMPLE_ACTIVITY],
            "total_count": 1,
            "page": 1,
            "page_size": 50,
        }
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_feed = AsyncMock(return_value=feed_result)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert data["total"] == 1
        assert data["page"] == 1
        assert len(data["items"]) == 1

    def test_passes_type_filter(self, test_client: TestClient) -> None:
        feed_result = {
            "activities": [SAMPLE_ACTIVITY],
            "total_count": 1,
            "page": 1,
            "page_size": 50,
        }
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_feed = AsyncMock(return_value=feed_result)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity?type=lead_discovered")

        assert response.status_code == 200
        call_kwargs = mock_service.get_activity_feed.call_args[1]
        assert call_kwargs["filters"]["activity_type"] == "lead_discovered"

    def test_passes_agent_filter(self, test_client: TestClient) -> None:
        feed_result = {
            "activities": [],
            "total_count": 0,
            "page": 1,
            "page_size": 50,
        }
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_feed = AsyncMock(return_value=feed_result)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity?agent=hunter")

        assert response.status_code == 200
        call_kwargs = mock_service.get_activity_feed.call_args[1]
        assert call_kwargs["filters"]["agent"] == "hunter"

    def test_passes_entity_type_filter(self, test_client: TestClient) -> None:
        feed_result = {
            "activities": [],
            "total_count": 0,
            "page": 1,
            "page_size": 50,
        }
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_feed = AsyncMock(return_value=feed_result)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity?entity_type=lead")

        assert response.status_code == 200
        call_kwargs = mock_service.get_activity_feed.call_args[1]
        assert call_kwargs["filters"]["related_entity_type"] == "lead"

    def test_passes_entity_id_filter(self, test_client: TestClient) -> None:
        feed_result = {
            "activities": [],
            "total_count": 0,
            "page": 1,
            "page_size": 50,
        }
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_feed = AsyncMock(return_value=feed_result)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity?entity_id=lead-1")

        assert response.status_code == 200
        call_kwargs = mock_service.get_activity_feed.call_args[1]
        assert call_kwargs["filters"]["related_entity_id"] == "lead-1"

    def test_passes_since_filter(self, test_client: TestClient) -> None:
        feed_result = {
            "activities": [],
            "total_count": 0,
            "page": 1,
            "page_size": 50,
        }
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_feed = AsyncMock(return_value=feed_result)
            mock_factory.return_value = mock_service

            response = test_client.get(
                "/api/v1/activity?since=2026-02-17T00:00:00Z"
            )

        assert response.status_code == 200
        call_kwargs = mock_service.get_activity_feed.call_args[1]
        assert call_kwargs["filters"]["date_start"] == "2026-02-17T00:00:00Z"

    def test_passes_pagination_params(self, test_client: TestClient) -> None:
        feed_result = {
            "activities": [],
            "total_count": 100,
            "page": 3,
            "page_size": 10,
        }
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_feed = AsyncMock(return_value=feed_result)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity?page=3&page_size=10")

        assert response.status_code == 200
        call_kwargs = mock_service.get_activity_feed.call_args[1]
        assert call_kwargs["page"] == 3
        assert call_kwargs["page_size"] == 10
        assert response.json()["page"] == 3

    def test_combined_filters(self, test_client: TestClient) -> None:
        feed_result = {
            "activities": [SAMPLE_ACTIVITY],
            "total_count": 1,
            "page": 1,
            "page_size": 50,
        }
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_feed = AsyncMock(return_value=feed_result)
            mock_factory.return_value = mock_service

            response = test_client.get(
                "/api/v1/activity?type=lead_discovered&agent=hunter&entity_type=lead"
            )

        assert response.status_code == 200
        call_kwargs = mock_service.get_activity_feed.call_args[1]
        assert call_kwargs["filters"]["activity_type"] == "lead_discovered"
        assert call_kwargs["filters"]["agent"] == "hunter"
        assert call_kwargs["filters"]["related_entity_type"] == "lead"

    def test_empty_feed(self, test_client: TestClient) -> None:
        feed_result = {
            "activities": [],
            "total_count": 0,
            "page": 1,
            "page_size": 50,
        }
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_feed = AsyncMock(return_value=feed_result)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_rejects_invalid_page_size(self, test_client: TestClient) -> None:
        response = test_client.get("/api/v1/activity?page_size=999")
        assert response.status_code == 422

    def test_rejects_page_zero(self, test_client: TestClient) -> None:
        response = test_client.get("/api/v1/activity?page=0")
        assert response.status_code == 422

    def test_server_error(self, test_client: TestClient) -> None:
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_feed = AsyncMock(
                side_effect=Exception("DB down")
            )
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity")

        assert response.status_code == 500

    def test_unauthenticated(self) -> None:
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/activity")
        assert response.status_code == 401


# ------------------------------------------------------------------ #
# GET /api/v1/activity/poll                                           #
# ------------------------------------------------------------------ #


class TestPollActivity:
    """Tests for GET /api/v1/activity/poll."""

    def test_returns_new_activities(self, test_client: TestClient) -> None:
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_real_time_updates = AsyncMock(
                return_value=[SAMPLE_ACTIVITY]
            )
            mock_factory.return_value = mock_service

            response = test_client.get(
                "/api/v1/activity/poll?since=2026-02-17T09:00:00Z"
            )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "count" in data
        assert data["count"] == 1
        assert data["items"][0]["id"] == "act-1"

    def test_passes_since_to_service(self, test_client: TestClient) -> None:
        timestamp = "2026-02-17T09:00:00Z"
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_real_time_updates = AsyncMock(return_value=[])
            mock_factory.return_value = mock_service

            test_client.get(f"/api/v1/activity/poll?since={timestamp}")

        call_kwargs = mock_service.get_real_time_updates.call_args[1]
        assert call_kwargs["since_timestamp"] == timestamp

    def test_returns_empty_when_no_updates(self, test_client: TestClient) -> None:
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_real_time_updates = AsyncMock(return_value=[])
            mock_factory.return_value = mock_service

            response = test_client.get(
                "/api/v1/activity/poll?since=2026-02-17T12:00:00Z"
            )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["count"] == 0

    def test_requires_since_param(self, test_client: TestClient) -> None:
        response = test_client.get("/api/v1/activity/poll")
        assert response.status_code == 422

    def test_server_error(self, test_client: TestClient) -> None:
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_real_time_updates = AsyncMock(
                side_effect=Exception("DB down")
            )
            mock_factory.return_value = mock_service

            response = test_client.get(
                "/api/v1/activity/poll?since=2026-02-17T09:00:00Z"
            )

        assert response.status_code == 500

    def test_unauthenticated(self) -> None:
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/activity/poll?since=2026-02-17T09:00:00Z")
        assert response.status_code == 401


# ------------------------------------------------------------------ #
# GET /api/v1/activity/stats                                          #
# ------------------------------------------------------------------ #


class TestGetActivityStats:
    """Tests for GET /api/v1/activity/stats."""

    def test_returns_stats(self, test_client: TestClient) -> None:
        stats = {
            "total": 15,
            "by_type": {"email_drafted": 5, "lead_discovered": 10},
            "by_agent": {"hunter": 10, "scribe": 5},
            "period": "7d",
            "since": "2026-02-10T10:00:00Z",
        }
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_stats = AsyncMock(return_value=stats)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 15
        assert data["by_type"]["email_drafted"] == 5
        assert data["by_agent"]["hunter"] == 10
        assert data["period"] == "7d"

    def test_accepts_7d_period(self, test_client: TestClient) -> None:
        stats = {"total": 0, "by_type": {}, "by_agent": {}, "period": "7d", "since": ""}
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_stats = AsyncMock(return_value=stats)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity/stats?period=7d")

        assert response.status_code == 200
        mock_service.get_activity_stats.assert_called_once()
        call_kwargs = mock_service.get_activity_stats.call_args[1]
        assert call_kwargs["period"] == "7d"

    def test_accepts_30d_period(self, test_client: TestClient) -> None:
        stats = {"total": 0, "by_type": {}, "by_agent": {}, "period": "30d", "since": ""}
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_stats = AsyncMock(return_value=stats)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity/stats?period=30d")

        assert response.status_code == 200

    def test_accepts_1d_period(self, test_client: TestClient) -> None:
        stats = {"total": 0, "by_type": {}, "by_agent": {}, "period": "1d", "since": ""}
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_stats = AsyncMock(return_value=stats)
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity/stats?period=1d")

        assert response.status_code == 200

    def test_rejects_invalid_period(self, test_client: TestClient) -> None:
        response = test_client.get("/api/v1/activity/stats?period=invalid")
        assert response.status_code == 422

    def test_defaults_to_7d(self, test_client: TestClient) -> None:
        stats = {"total": 0, "by_type": {}, "by_agent": {}, "period": "7d", "since": ""}
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_stats = AsyncMock(return_value=stats)
            mock_factory.return_value = mock_service

            test_client.get("/api/v1/activity/stats")

        call_kwargs = mock_service.get_activity_stats.call_args[1]
        assert call_kwargs["period"] == "7d"

    def test_server_error(self, test_client: TestClient) -> None:
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.get_activity_stats = AsyncMock(
                side_effect=Exception("DB down")
            )
            mock_factory.return_value = mock_service

            response = test_client.get("/api/v1/activity/stats")

        assert response.status_code == 500

    def test_unauthenticated(self) -> None:
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/activity/stats")
        assert response.status_code == 401


# ------------------------------------------------------------------ #
# GET /api/v1/activity/{activity_id}                                  #
# ------------------------------------------------------------------ #


class TestGetActivityDetail:
    """Tests for GET /api/v1/activity/{activity_id}."""

    def test_returns_activity(self, test_client: TestClient) -> None:
        with patch("src.services.activity_service.ActivityService") as mock_cls:
            instance = MagicMock()
            instance.get_activity_detail = AsyncMock(return_value=SAMPLE_ACTIVITY)
            mock_cls.return_value = instance

            response = test_client.get("/api/v1/activity/act-1")

        assert response.status_code == 200
        assert response.json()["id"] == "act-1"

    def test_returns_404_when_not_found(self, test_client: TestClient) -> None:
        with patch("src.services.activity_service.ActivityService") as mock_cls:
            instance = MagicMock()
            instance.get_activity_detail = AsyncMock(return_value=None)
            mock_cls.return_value = instance

            response = test_client.get("/api/v1/activity/nonexistent")

        assert response.status_code == 404

    def test_unauthenticated(self) -> None:
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/activity/act-1")
        assert response.status_code == 401


# ------------------------------------------------------------------ #
# POST /api/v1/activity                                               #
# ------------------------------------------------------------------ #


class TestRecordActivity:
    """Tests for POST /api/v1/activity."""

    def test_creates_activity(self, test_client: TestClient) -> None:
        created = {**SAMPLE_ACTIVITY}
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.create_activity = AsyncMock(return_value=created)
            mock_factory.return_value = mock_service

            response = test_client.post(
                "/api/v1/activity",
                json={
                    "activity_type": "lead_discovered",
                    "title": "Discovered Acme Bio",
                    "agent": "hunter",
                },
            )

        assert response.status_code == 200
        assert response.json()["id"] == "act-1"

    def test_rejects_missing_required_fields(self, test_client: TestClient) -> None:
        response = test_client.post("/api/v1/activity", json={})
        assert response.status_code == 422

    def test_server_error(self, test_client: TestClient) -> None:
        with patch("src.api.routes.activity._get_service") as mock_factory:
            mock_service = MagicMock()
            mock_service.create_activity = AsyncMock(
                side_effect=Exception("DB down")
            )
            mock_factory.return_value = mock_service

            response = test_client.post(
                "/api/v1/activity",
                json={
                    "activity_type": "lead_discovered",
                    "title": "Test",
                },
            )

        assert response.status_code == 500

    def test_unauthenticated(self) -> None:
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/activity",
            json={"activity_type": "test", "title": "Test"},
        )
        assert response.status_code == 401
