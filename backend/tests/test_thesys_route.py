"""Tests for Thesys C1 API routes."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.api.routes.thesys import router


# Fake user object
_FAKE_USER = MagicMock()
_FAKE_USER.id = "user-123"


@pytest.fixture
def app() -> FastAPI:
    """Create a minimal FastAPI app with the thesys router and auth override."""
    _app = FastAPI()
    _app.include_router(router, prefix="/api/v1")
    _app.dependency_overrides[get_current_user] = lambda: _FAKE_USER
    return _app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestThesysHealthEndpoint:
    @patch("src.api.routes.thesys.settings")
    def test_health_returns_status(
        self, mock_settings: MagicMock, client: TestClient,
    ) -> None:
        mock_settings.thesys_configured = True
        resp = client.get("/api/v1/thesys/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "configured" in data
        assert "circuit_breaker" in data

    @patch("src.api.routes.thesys.settings")
    def test_health_not_configured(
        self, mock_settings: MagicMock, client: TestClient,
    ) -> None:
        mock_settings.thesys_configured = False
        resp = client.get("/api/v1/thesys/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False


class TestVisualizeSyncEndpoint:
    @patch("src.api.routes.thesys.settings")
    def test_returns_markdown_when_not_configured(
        self, mock_settings: MagicMock, client: TestClient,
    ) -> None:
        mock_settings.thesys_configured = False
        resp = client.post(
            "/api/v1/thesys/visualize/sync",
            json={"content": "Hello world"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["render_mode"] == "markdown"
        assert data["rendered_content"] == "Hello world"

    @patch("src.api.routes.thesys.settings")
    def test_returns_c1_when_configured(
        self, mock_settings: MagicMock, client: TestClient,
    ) -> None:
        mock_settings.thesys_configured = True

        mock_svc = MagicMock()
        mock_svc.is_available = True
        mock_svc.visualize = AsyncMock(return_value="<div>Rich</div>")

        with (
            patch(
                "src.services.thesys_classifier.ThesysRoutingClassifier.classify",
                return_value=(True, "pipeline_data"),
            ),
            patch(
                "src.services.thesys_service.get_thesys_service",
                return_value=mock_svc,
            ),
        ):
            resp = client.post(
                "/api/v1/thesys/visualize/sync",
                json={"content": "x" * 300 + " pipeline revenue"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["render_mode"] == "c1"
            assert data["rendered_content"] == "<div>Rich</div>"
