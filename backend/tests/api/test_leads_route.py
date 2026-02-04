"""Tests for leads API routes."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import leads


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(leads.router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""
    from src.api.deps import get_current_user

    app = create_test_app()

    def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestListLeads:
    """Tests for GET /api/v1/leads endpoint."""

    def test_list_leads_requires_auth(self) -> None:
        """Test that listing leads requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/leads")
        assert response.status_code == 401


class TestGetLead:
    """Tests for GET /api/v1/leads/{lead_id} endpoint."""

    def test_get_lead_requires_auth(self) -> None:
        """Test that getting a lead requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/leads/some-lead-id")
        assert response.status_code == 401


class TestAddNote:
    """Tests for POST /api/v1/leads/{lead_id}/notes endpoint."""

    def test_add_note_requires_auth(self) -> None:
        """Test that adding a note requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/leads/some-lead-id/notes",
            json={
                "event_type": "note",
                "content": "Test note",
                "occurred_at": "2025-01-01T00:00:00Z",
            },
        )
        assert response.status_code == 401


class TestExportLeads:
    """Tests for POST /api/v1/leads/export endpoint."""

    def test_export_leads_requires_auth(self) -> None:
        """Test that exporting leads requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/leads/export",
            json=["lead-1", "lead-2"],
        )
        assert response.status_code == 401
