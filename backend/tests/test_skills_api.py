"""Tests for skills API routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


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

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestListUserSkills:
    def test_list_user_skills_returns_installed_skills(
        self, test_client: TestClient
    ) -> None:
        """Test that list_user_skills returns all installed skills for user."""
        with patch("src.api.routes.skills.SkillInstaller") as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.list_user_skills = AsyncMock(
                return_value=[
                    {
                        "id": "install-1",
                        "user_id": "test-user-123",
                        "skill_id": "skill-uuid-1",
                        "skill_path": "anthropics/skills/pdf",
                        "trust_level": "verified",
                        "execution_count": 5,
                        "success_count": 5,
                        "installed_at": "2026-02-01T10:00:00+00:00",
                    }
                ]
            )
            mock_installer_class.return_value = mock_installer

            response = test_client.get("/api/v1/skills/installed")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["skill_path"] == "anthropics/skills/pdf"


class TestAvailableSkills:
    def test_search_available_skills(self, test_client: TestClient) -> None:
        """Test GET /skills/available returns skills from index."""
        with patch("src.api.routes.skills.SkillIndex") as mock_index_class:
            mock_index = MagicMock()
            mock_index.search = AsyncMock(
                return_value=[
                    MagicMock(
                        id="skill-uuid-1",
                        skill_path="anthropics/skills/pdf",
                        skill_name="PDF Generator",
                        description="Generate PDF documents",
                        author="anthropic",
                        version="1.0.0",
                        tags=["document", "pdf"],
                        trust_level=MagicMock(value="verified"),
                        life_sciences_relevant=False,
                    )
                ]
            )
            mock_index_class.return_value = mock_index

            response = test_client.get(
                "/api/v1/skills/available?query=pdf"
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["skill_name"] == "PDF Generator"

    def test_search_available_skills_with_trust_filter(
        self, test_client: TestClient
    ) -> None:
        """Test GET /skills/available filters by trust level."""
        with patch("src.api.routes.skills.SkillIndex") as mock_index_class:
            mock_index = MagicMock()
            mock_index.search = AsyncMock(return_value=[])
            mock_index_class.return_value = mock_index

            response = test_client.get(
                "/api/v1/skills/available?query=test&trust_level=core"
            )

        assert response.status_code == status.HTTP_200_OK
        mock_index.search.assert_called_once()
        call_kwargs = mock_index.search.call_args
        assert call_kwargs.kwargs.get("trust_level") is not None


class TestSkillsRequireAuth:
    def test_all_endpoints_require_authentication(self) -> None:
        """Test all skill endpoints require authentication."""
        client = TestClient(app)

        endpoints = [
            ("GET", "/api/v1/skills/available"),
            ("GET", "/api/v1/skills/installed"),
            ("POST", "/api/v1/skills/install"),
            ("DELETE", "/api/v1/skills/some-skill-id"),
            ("POST", "/api/v1/skills/execute"),
            ("GET", "/api/v1/skills/audit"),
            ("GET", "/api/v1/skills/autonomy/some-skill-id"),
            ("POST", "/api/v1/skills/autonomy/some-skill-id/approve"),
        ]

        for method, path in endpoints:
            response = getattr(client, method.lower())(path)
            assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"{method} {path} should require auth"
            )
