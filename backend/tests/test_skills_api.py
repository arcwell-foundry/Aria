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


class TestInstallSkill:
    def test_install_skill_succeeds(self, test_client: TestClient) -> None:
        """Test POST /skills/install installs a skill."""
        with patch("src.api.routes.skills.SkillInstaller") as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.install = AsyncMock(
                return_value=MagicMock(
                    id="install-1",
                    user_id="test-user-123",
                    skill_id="skill-uuid-1",
                    skill_path="anthropics/skills/pdf",
                    trust_level=MagicMock(value="verified"),
                    permissions_granted=["read"],
                    installed_at=MagicMock(isoformat=MagicMock(return_value="2026-02-01T10:00:00+00:00")),
                    auto_installed=False,
                    execution_count=0,
                    success_count=0,
                    last_used_at=None,
                )
            )
            mock_installer_class.return_value = mock_installer

            response = test_client.post(
                "/api/v1/skills/install",
                json={"skill_id": "skill-uuid-1"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["skill_path"] == "anthropics/skills/pdf"

    def test_install_skill_not_found(self, test_client: TestClient) -> None:
        """Test POST /skills/install returns 404 for unknown skill."""
        with patch("src.api.routes.skills.SkillInstaller") as mock_installer_class:
            from src.skills.installer import SkillNotFoundError

            mock_installer = MagicMock()
            mock_installer.install = AsyncMock(
                side_effect=SkillNotFoundError("Skill not found")
            )
            mock_installer_class.return_value = mock_installer

            response = test_client.post(
                "/api/v1/skills/install",
                json={"skill_id": "nonexistent"},
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestUninstallSkill:
    def test_uninstall_skill_succeeds(self, test_client: TestClient) -> None:
        """Test DELETE /skills/{skill_id} uninstalls a skill."""
        with patch("src.api.routes.skills.SkillInstaller") as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.uninstall = AsyncMock(return_value=True)
            mock_installer_class.return_value = mock_installer

            response = test_client.delete("/api/v1/skills/skill-uuid-1")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "uninstalled"

    def test_uninstall_skill_not_installed(self, test_client: TestClient) -> None:
        """Test DELETE /skills/{skill_id} returns 404 if not installed."""
        with patch("src.api.routes.skills.SkillInstaller") as mock_installer_class:
            mock_installer = MagicMock()
            mock_installer.uninstall = AsyncMock(return_value=False)
            mock_installer_class.return_value = mock_installer

            response = test_client.delete("/api/v1/skills/nonexistent")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestExecuteSkill:
    def test_execute_skill_succeeds(self, test_client: TestClient) -> None:
        """Test POST /skills/execute runs a skill through security pipeline."""
        with patch("src.api.routes.skills._get_executor") as mock_get_executor:
            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(
                return_value=MagicMock(
                    skill_id="skill-uuid-1",
                    skill_path="anthropics/skills/pdf",
                    trust_level=MagicMock(value="verified"),
                    success=True,
                    result={"document_url": "https://example.com/doc.pdf"},
                    error=None,
                    execution_time_ms=150,
                    sanitized=True,
                )
            )
            mock_get_executor.return_value = mock_executor

            response = test_client.post(
                "/api/v1/skills/execute",
                json={
                    "skill_id": "skill-uuid-1",
                    "input_data": {"title": "Q1 Report"},
                },
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["result"]["document_url"] == "https://example.com/doc.pdf"

    def test_execute_skill_failure(self, test_client: TestClient) -> None:
        """Test POST /skills/execute returns error on execution failure."""
        with patch("src.api.routes.skills._get_executor") as mock_get_executor:
            from src.skills.executor import SkillExecutionError

            mock_executor = MagicMock()
            mock_executor.execute = AsyncMock(
                side_effect=SkillExecutionError(
                    "Skill not installed", skill_id="skill-uuid-1", stage="lookup"
                )
            )
            mock_get_executor.return_value = mock_executor

            response = test_client.post(
                "/api/v1/skills/execute",
                json={
                    "skill_id": "skill-uuid-1",
                    "input_data": {"title": "Test"},
                },
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestAuditLog:
    def test_get_audit_log(self, test_client: TestClient) -> None:
        """Test GET /skills/audit returns paginated audit entries."""
        with patch("src.api.routes.skills.SkillAuditService") as mock_audit_class:
            mock_audit = MagicMock()
            mock_audit.get_audit_log = AsyncMock(
                return_value=[
                    {
                        "id": "audit-1",
                        "user_id": "test-user-123",
                        "skill_id": "skill-uuid-1",
                        "skill_path": "anthropics/skills/pdf",
                        "skill_trust_level": "verified",
                        "trigger_reason": "user_request",
                        "success": True,
                        "execution_time_ms": 150,
                        "timestamp": "2026-02-01T10:00:00Z",
                    }
                ]
            )
            mock_audit_class.return_value = mock_audit

            response = test_client.get("/api/v1/skills/audit?limit=10&offset=0")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["skill_path"] == "anthropics/skills/pdf"

    def test_get_audit_log_with_skill_filter(self, test_client: TestClient) -> None:
        """Test GET /skills/audit?skill_id= filters by skill."""
        with patch("src.api.routes.skills.SkillAuditService") as mock_audit_class:
            mock_audit = MagicMock()
            mock_audit.get_audit_for_skill = AsyncMock(return_value=[])
            mock_audit_class.return_value = mock_audit

            response = test_client.get(
                "/api/v1/skills/audit?skill_id=skill-uuid-1"
            )

        assert response.status_code == status.HTTP_200_OK
        mock_audit.get_audit_for_skill.assert_called_once()


class TestAutonomy:
    def test_get_trust_level(self, test_client: TestClient) -> None:
        """Test GET /skills/autonomy/{skill_id} returns trust info."""
        with patch("src.api.routes.skills.SkillAutonomyService") as mock_autonomy_class:
            mock_autonomy = MagicMock()
            mock_autonomy.get_trust_history = AsyncMock(
                return_value=MagicMock(
                    id="trust-1",
                    user_id="test-user-123",
                    skill_id="skill-uuid-1",
                    successful_executions=5,
                    failed_executions=0,
                    session_trust_granted=False,
                    globally_approved=False,
                    globally_approved_at=None,
                    created_at=MagicMock(isoformat=MagicMock(return_value="2026-02-01T10:00:00+00:00")),
                    updated_at=MagicMock(isoformat=MagicMock(return_value="2026-02-01T12:00:00+00:00")),
                )
            )
            mock_autonomy_class.return_value = mock_autonomy

            response = test_client.get("/api/v1/skills/autonomy/skill-uuid-1")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["successful_executions"] == 5
        assert data["globally_approved"] is False

    def test_get_trust_level_no_history(self, test_client: TestClient) -> None:
        """Test GET /skills/autonomy/{skill_id} returns defaults when no history."""
        with patch("src.api.routes.skills.SkillAutonomyService") as mock_autonomy_class:
            mock_autonomy = MagicMock()
            mock_autonomy.get_trust_history = AsyncMock(return_value=None)
            mock_autonomy_class.return_value = mock_autonomy

            response = test_client.get("/api/v1/skills/autonomy/skill-uuid-1")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["successful_executions"] == 0
        assert data["globally_approved"] is False

    def test_grant_global_approval(self, test_client: TestClient) -> None:
        """Test POST /skills/autonomy/{skill_id}/approve grants global approval."""
        with patch("src.api.routes.skills.SkillAutonomyService") as mock_autonomy_class:
            mock_autonomy = MagicMock()
            mock_autonomy.grant_global_approval = AsyncMock(
                return_value=MagicMock(
                    id="trust-1",
                    user_id="test-user-123",
                    skill_id="skill-uuid-1",
                    successful_executions=5,
                    failed_executions=0,
                    session_trust_granted=False,
                    globally_approved=True,
                    globally_approved_at=MagicMock(isoformat=MagicMock(return_value="2026-02-05T10:00:00+00:00")),
                    created_at=MagicMock(isoformat=MagicMock(return_value="2026-02-01T10:00:00+00:00")),
                    updated_at=MagicMock(isoformat=MagicMock(return_value="2026-02-05T10:00:00+00:00")),
                )
            )
            mock_autonomy_class.return_value = mock_autonomy

            response = test_client.post(
                "/api/v1/skills/autonomy/skill-uuid-1/approve"
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["globally_approved"] is True

    def test_grant_approval_fails(self, test_client: TestClient) -> None:
        """Test POST /skills/autonomy/{skill_id}/approve handles failure."""
        with patch("src.api.routes.skills.SkillAutonomyService") as mock_autonomy_class:
            mock_autonomy = MagicMock()
            mock_autonomy.grant_global_approval = AsyncMock(return_value=None)
            mock_autonomy_class.return_value = mock_autonomy

            response = test_client.post(
                "/api/v1/skills/autonomy/nonexistent/approve"
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
