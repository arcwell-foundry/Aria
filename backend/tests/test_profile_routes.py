"""Tests for Profile Page API Routes (US-921)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.core.exceptions import ARIAException


@pytest.fixture
def mock_current_user():
    """Mock authenticated user."""
    user = MagicMock()
    user.id = "user-123"
    return user


@pytest.fixture
def mock_admin_user():
    """Mock authenticated admin user."""
    user = MagicMock()
    user.id = "admin-456"
    return user


@pytest.fixture
def mock_profile_service():
    """Mock ProfileService."""
    with patch("src.api.routes.profile.ProfileService") as mock_cls:
        service_instance = MagicMock()
        mock_cls.return_value = service_instance
        yield service_instance


@pytest.fixture
def client(mock_current_user):
    """Create test client with mocked auth."""
    from fastapi import FastAPI

    from src.api.deps import get_current_user
    from src.api.routes.profile import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    app.dependency_overrides[get_current_user] = lambda: mock_current_user

    return TestClient(app)


class TestGetProfile:
    """Test GET /profile endpoint."""

    def test_returns_full_profile(self, client, mock_profile_service):
        """GET /profile returns merged user + company + integrations."""
        mock_profile_service.get_full_profile = AsyncMock(
            return_value={
                "user": {
                    "id": "user-123",
                    "full_name": "Jane Doe",
                    "title": "VP Sales",
                    "department": "Commercial",
                    "linkedin_url": "https://linkedin.com/in/janedoe",
                    "avatar_url": None,
                    "company_id": "company-456",
                    "role": "user",
                    "communication_preferences": {},
                    "privacy_exclusions": [],
                    "default_tone": "friendly",
                    "tracked_competitors": [],
                    "created_at": "2024-01-01T00:00:00Z",
                    "updated_at": "2024-01-01T00:00:00Z",
                },
                "company": {
                    "id": "company-456",
                    "name": "BioPharm Inc",
                    "website": "https://biopharm.com",
                    "industry": "Life Sciences",
                },
                "integrations": [],
            }
        )

        response = client.get(
            "/api/v1/profile",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user"]["id"] == "user-123"
        assert data["user"]["full_name"] == "Jane Doe"
        assert data["company"]["name"] == "BioPharm Inc"

    def test_returns_401_without_auth(self):
        """GET /profile returns 401 without authentication."""
        from fastapi import FastAPI

        from src.api.routes.profile import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        unauth_client = TestClient(app)

        response = unauth_client.get("/api/v1/profile")
        assert response.status_code == 401


class TestUpdateUserDetails:
    """Test PUT /profile/user endpoint."""

    def test_updates_user_details(self, client, mock_profile_service):
        """PUT /profile/user updates name, title, department."""
        mock_profile_service.update_user_details = AsyncMock(
            return_value={
                "id": "user-123",
                "full_name": "Jane Smith",
                "title": "SVP Sales",
            }
        )

        response = client.put(
            "/api/v1/profile/user",
            json={"full_name": "Jane Smith", "title": "SVP Sales"},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Jane Smith"
        assert data["title"] == "SVP Sales"

    def test_validates_linkedin_url_format(self, client, mock_profile_service):  # noqa: ARG002
        """PUT /profile/user rejects invalid LinkedIn URL."""
        response = client.put(
            "/api/v1/profile/user",
            json={"linkedin_url": "not-a-url"},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 422


class TestUpdateCompanyDetails:
    """Test PUT /profile/company endpoint."""

    def test_admin_can_update_company(self, client, mock_profile_service):
        """Admin can update company details."""
        mock_profile_service.update_company_details = AsyncMock(
            return_value={
                "id": "company-456",
                "name": "BioPharm Inc",
                "industry": "Biotech",
            }
        )

        response = client.put(
            "/api/v1/profile/company",
            json={"industry": "Biotech"},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["industry"] == "Biotech"

    def test_non_admin_gets_403(self, client, mock_profile_service):
        """Non-admin user gets 403 when updating company."""
        mock_profile_service.update_company_details = AsyncMock(
            side_effect=ARIAException(
                message="Only admins can update company details",
                code="INSUFFICIENT_PERMISSIONS",
                status_code=403,
            )
        )

        response = client.put(
            "/api/v1/profile/company",
            json={"industry": "Biotech"},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 403


class TestGetDocuments:
    """Test GET /profile/documents endpoint."""

    def test_returns_both_document_types(self, client, mock_profile_service):
        """GET /profile/documents returns company and user documents."""
        mock_profile_service.list_documents = AsyncMock(
            return_value={
                "company_documents": [
                    {"id": "doc-1", "filename": "deck.pdf"},
                ],
                "user_documents": [
                    {"id": "doc-2", "filename": "sample.docx"},
                ],
            }
        )

        response = client.get(
            "/api/v1/profile/documents",
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["company_documents"]) == 1
        assert len(data["user_documents"]) == 1


class TestUpdatePreferences:
    """Test PUT /profile/preferences endpoint."""

    def test_updates_preferences(self, client, mock_profile_service):
        """PUT /profile/preferences updates communication settings."""
        mock_profile_service.update_preferences = AsyncMock(
            return_value={
                "id": "user-123",
                "default_tone": "formal",
                "tracked_competitors": ["Acme"],
            }
        )

        response = client.put(
            "/api/v1/profile/preferences",
            json={
                "default_tone": "formal",
                "tracked_competitors": ["Acme"],
            },
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["default_tone"] == "formal"

    def test_rejects_invalid_tone(self, client, mock_profile_service):  # noqa: ARG002
        """PUT /profile/preferences rejects invalid tone value."""
        response = client.put(
            "/api/v1/profile/preferences",
            json={"default_tone": "screaming"},
            headers={"Authorization": "Bearer fake-token"},
        )

        assert response.status_code == 422
