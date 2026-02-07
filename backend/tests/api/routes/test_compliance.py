"""Tests for compliance API routes (US-929).

These tests follow TDD principles - tests were written first, then implementation.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import compliance


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(compliance.router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_admin_user() -> MagicMock:
    """Create mock admin user."""
    user = MagicMock()
    user.id = "admin-user-123"
    user.email = "admin@example.com"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""
    from src.api.deps import get_current_user

    app = create_test_app()

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def admin_test_client(mock_admin_user: MagicMock) -> TestClient:
    """Create test client with mocked admin authentication."""
    from src.api.deps import get_current_user

    app = create_test_app()

    async def override_get_current_user() -> MagicMock:
        return mock_admin_user

    # We need to also override the AdminUser dependency
    # AdminUser is an alias to require_role(["admin"])
    # We'll mock get_current_user to return our admin user and patch the role check

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def mock_export_data() -> dict:
    """Create mock data export response."""
    return {
        "export_date": "2026-02-06T10:00:00+00:00",
        "user_id": "test-user-123",
        "user_profile": {"id": "test-user-123", "email": "test@example.com"},
        "user_settings": {"user_id": "test-user-123", "preferences": {}},
        "onboarding_state": [],
        "semantic_memory": [],
        "prospective_memory": [],
        "conversations": [],
        "messages": [],
        "documents": [],
        "audit_log": [],
    }


@pytest.fixture
def mock_consent_status() -> dict:
    """Create mock consent status response."""
    return {
        "email_analysis": True,
        "document_learning": True,
        "crm_processing": False,
        "writing_style_learning": True,
    }


@pytest.fixture
def mock_retention_policies() -> dict:
    """Create mock retention policies response."""
    return {
        "audit_query_logs": {"duration_days": 90, "description": "Query logs retained for 90 days"},
        "audit_write_logs": {"duration_days": -1, "description": "Write logs retained permanently"},
        "email_data": {
            "duration_days": 365,
            "description": "Email data retained for 1 year by default",
        },
        "conversation_history": {
            "duration_days": -1,
            "description": "Conversation history retained until deleted by user",
        },
        "note": "Contact support to request changes to retention policies",
    }


class TestGetDataExport:
    """Tests for GET /api/v1/compliance/data/export endpoint."""

    def test_get_data_export_requires_auth(self) -> None:
        """Test that data export requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/compliance/data/export")
        assert response.status_code == 401

    def test_get_data_export_returns_json(
        self, test_client: TestClient, mock_export_data: dict
    ) -> None:
        """Test that data export returns structured JSON."""
        with patch.object(
            compliance.compliance_service,
            "export_user_data",
            new=AsyncMock(return_value=mock_export_data),
        ):
            response = test_client.get("/api/v1/compliance/data/export")

        assert response.status_code == 200
        data = response.json()
        assert "export_date" in data
        assert "user_id" in data

    def test_get_data_export_includes_all_sections(
        self, test_client: TestClient, mock_export_data: dict
    ) -> None:
        """Test that data export includes all data sections."""
        with patch.object(
            compliance.compliance_service,
            "export_user_data",
            new=AsyncMock(return_value=mock_export_data),
        ):
            response = test_client.get("/api/v1/compliance/data/export")

        assert response.status_code == 200
        data = response.json()
        assert "user_profile" in data
        assert "user_settings" in data
        assert "onboarding_state" in data
        assert "semantic_memory" in data
        assert "prospective_memory" in data
        assert "conversations" in data
        assert "messages" in data
        assert "documents" in data
        assert "audit_log" in data

    def test_get_data_export_service_error(self, test_client: TestClient) -> None:
        """Test that data export handles service errors."""
        with patch.object(
            compliance.compliance_service,
            "export_user_data",
            new=AsyncMock(side_effect=Exception("Database error")),
        ):
            response = test_client.get("/api/v1/compliance/data/export")

        assert response.status_code == 500


class TestDeleteUserData:
    """Tests for POST /api/v1/compliance/data/delete endpoint."""

    def test_delete_data_requires_auth(self) -> None:
        """Test that data deletion requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/compliance/data/delete", json={"confirmation": "DELETE MY DATA"}
        )
        assert response.status_code == 401

    def test_delete_data_requires_confirmation(self, test_client: TestClient) -> None:
        """Test that data deletion requires exact confirmation."""
        response = test_client.post(
            "/api/v1/compliance/data/delete",
            json={"confirmation": "wrong"},
        )
        assert response.status_code == 400

    def test_delete_data_success(self, test_client: TestClient) -> None:
        """Test that data deletion works with correct confirmation."""
        mock_response = {
            "deleted": True,
            "user_id": "test-user-123",
            "summary": {"semantic_memory": 5, "conversations": 2},
        }

        with patch.object(
            compliance.compliance_service,
            "delete_user_data",
            new=AsyncMock(return_value=mock_response),
        ):
            response = test_client.post(
                "/api/v1/compliance/data/delete",
                json={"confirmation": "DELETE MY DATA"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["user_id"] == "test-user-123"

    def test_delete_data_service_error(self, test_client: TestClient) -> None:
        """Test that data deletion handles service errors."""
        with patch.object(
            compliance.compliance_service,
            "delete_user_data",
            new=AsyncMock(side_effect=Exception("Database error")),
        ):
            response = test_client.post(
                "/api/v1/compliance/data/delete",
                json={"confirmation": "DELETE MY DATA"},
            )

        assert response.status_code == 500


class TestDeleteDigitalTwin:
    """Tests for DELETE /api/v1/compliance/data/digital-twin endpoint."""

    def test_delete_digital_twin_requires_auth(self) -> None:
        """Test that digital twin deletion requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.delete("/api/v1/compliance/data/digital-twin")
        assert response.status_code == 401

    def test_delete_digital_twin_success(self, test_client: TestClient) -> None:
        """Test that digital twin deletion endpoint works."""
        mock_response = {
            "deleted": True,
            "user_id": "test-user-123",
            "deleted_at": "2026-02-06T10:00:00+00:00",
        }

        with patch.object(
            compliance.compliance_service,
            "delete_digital_twin",
            new=AsyncMock(return_value=mock_response),
        ):
            response = test_client.delete("/api/v1/compliance/data/digital-twin")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["user_id"] == "test-user-123"
        assert "deleted_at" in data

    def test_delete_digital_twin_service_error(self, test_client: TestClient) -> None:
        """Test that digital twin deletion handles service errors."""
        with patch.object(
            compliance.compliance_service,
            "delete_digital_twin",
            new=AsyncMock(side_effect=Exception("Database error")),
        ):
            response = test_client.delete("/api/v1/compliance/data/digital-twin")

        assert response.status_code == 500


class TestGetConsent:
    """Tests for GET /api/v1/compliance/consent endpoint."""

    def test_get_consent_requires_auth(self) -> None:
        """Test that consent endpoint requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/compliance/consent")
        assert response.status_code == 401

    def test_get_consent_returns_all_categories(
        self, test_client: TestClient, mock_consent_status: dict
    ) -> None:
        """Test that consent endpoint returns all categories."""
        with patch.object(
            compliance.compliance_service,
            "get_consent_status",
            new=AsyncMock(return_value=mock_consent_status),
        ):
            response = test_client.get("/api/v1/compliance/consent")

        assert response.status_code == 200
        data = response.json()
        assert "email_analysis" in data
        assert "document_learning" in data
        assert "crm_processing" in data
        assert "writing_style_learning" in data

    def test_get_consent_service_error(self, test_client: TestClient) -> None:
        """Test that consent endpoint handles service errors."""
        with patch.object(
            compliance.compliance_service,
            "get_consent_status",
            new=AsyncMock(side_effect=Exception("Database error")),
        ):
            response = test_client.get("/api/v1/compliance/consent")

        assert response.status_code == 500


class TestUpdateConsent:
    """Tests for PATCH /api/v1/compliance/consent endpoint."""

    def test_update_consent_requires_auth(self) -> None:
        """Test that consent update requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.patch(
            "/api/v1/compliance/consent", json={"category": "email_analysis", "granted": False}
        )
        assert response.status_code == 401

    def test_patch_consent_updates_category(self, test_client: TestClient) -> None:
        """Test that PATCH consent updates a category."""
        mock_response = {
            "category": "email_analysis",
            "granted": False,
            "updated_at": "2026-02-06T10:00:00+00:00",
        }

        with patch.object(
            compliance.compliance_service,
            "update_consent",
            new=AsyncMock(return_value=mock_response),
        ):
            response = test_client.patch(
                "/api/v1/compliance/consent",
                json={"category": "email_analysis", "granted": False},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "email_analysis"
        assert data["granted"] is False

    def test_update_consent_invalid_category(self, test_client: TestClient) -> None:
        """Test that invalid consent category returns error."""
        with patch.object(
            compliance.compliance_service,
            "update_consent",
            new=AsyncMock(
                side_effect=compliance.ComplianceError("Invalid consent category: invalid")
            ),
        ):
            response = test_client.patch(
                "/api/v1/compliance/consent",
                json={"category": "invalid", "granted": False},
            )

        assert response.status_code == 500

    def test_update_consent_service_error(self, test_client: TestClient) -> None:
        """Test that consent update handles service errors."""
        with patch.object(
            compliance.compliance_service,
            "update_consent",
            new=AsyncMock(side_effect=Exception("Database error")),
        ):
            response = test_client.patch(
                "/api/v1/compliance/consent",
                json={"category": "email_analysis", "granted": False},
            )

        assert response.status_code == 500


class TestMarkDontLearn:
    """Tests for POST /api/v1/compliance/data/dont-learn endpoint."""

    def test_mark_dont_learn_requires_auth(self) -> None:
        """Test that don't learn requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/api/v1/compliance/data/dont-learn", json={"content_ids": ["mem-1"]}
        )
        assert response.status_code == 401

    def test_mark_dont_learn_excludes_content(self, test_client: TestClient) -> None:
        """Test that don't learn marks content as excluded."""
        mock_response = {"marked_count": 2, "total_requested": 2}

        with patch.object(
            compliance.compliance_service,
            "mark_dont_learn",
            new=AsyncMock(return_value=mock_response),
        ):
            response = test_client.post(
                "/api/v1/compliance/data/dont-learn",
                json={"content_ids": ["mem-1", "mem-2"]},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["marked_count"] == 2
        assert data["total_requested"] == 2

    def test_mark_dont_learn_empty_list(self, test_client: TestClient) -> None:
        """Test that empty content_ids list fails validation."""
        response = test_client.post(
            "/api/v1/compliance/data/dont-learn",
            json={"content_ids": []},
        )
        # Pydantic validation should catch this
        assert response.status_code == 422

    def test_mark_dont_learn_service_error(self, test_client: TestClient) -> None:
        """Test that don't learn handles service errors."""
        with patch.object(
            compliance.compliance_service,
            "mark_dont_learn",
            new=AsyncMock(side_effect=Exception("Database error")),
        ):
            response = test_client.post(
                "/api/v1/compliance/data/dont-learn",
                json={"content_ids": ["mem-1"]},
            )

        assert response.status_code == 500


class TestGetRetentionPolicies:
    """Tests for GET /api/v1/compliance/retention endpoint."""

    def test_get_retention_policies_requires_auth(self) -> None:
        """Test that retention policies endpoint requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/compliance/retention")
        assert response.status_code == 401

    def test_get_retention_policies_works(
        self, test_client: TestClient, mock_retention_policies: dict
    ) -> None:
        """Test that retention policies endpoint returns policies."""
        with (
            patch(
                "src.db.supabase.SupabaseClient.get_user_by_id",
                new=AsyncMock(return_value={"company_id": "company-123"}),
            ),
            patch.object(
                compliance.compliance_service,
                "get_retention_policies",
                new=AsyncMock(return_value=mock_retention_policies),
            ),
        ):
            response = test_client.get("/api/v1/compliance/retention")

        assert response.status_code == 200
        data = response.json()
        assert "audit_query_logs" in data
        assert "audit_write_logs" in data
        assert "email_data" in data
        assert "conversation_history" in data

    def test_get_retention_policies_service_error(self, test_client: TestClient) -> None:
        """Test that retention policies handles service errors."""
        with (
            patch(
                "src.db.supabase.SupabaseClient.get_user_by_id",
                new=AsyncMock(return_value={"company_id": "company-123"}),
            ),
            patch.object(
                compliance.compliance_service,
                "get_retention_policies",
                new=AsyncMock(side_effect=Exception("Database error")),
            ),
        ):
            response = test_client.get("/api/v1/compliance/retention")

        assert response.status_code == 500


class TestExportCompanyData:
    """Tests for GET /api/v1/compliance/data/export/company endpoint."""

    def test_export_company_requires_auth(self) -> None:
        """Test that company export requires authentication."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/compliance/data/export/company")
        assert response.status_code == 401

    def test_export_company_requires_admin(self, test_client: TestClient) -> None:
        """Test that company export requires admin role."""
        # Patch get_user_by_id to return non-admin role
        with patch(
            "src.db.supabase.SupabaseClient.get_user_by_id",
            new=AsyncMock(return_value={"role": "user", "company_id": "company-123"}),
        ):
            response = test_client.get("/api/v1/compliance/data/export/company")
        # Regular user (not admin) should get 403
        assert response.status_code == 403

    def test_export_company_success(self, admin_test_client: TestClient) -> None:
        """Test that company export works for admin users."""
        mock_response = {
            "export_date": "2026-02-06T10:00:00+00:00",
            "company_id": "company-123",
            "exported_by": "admin-user-123",
            "company": {"id": "company-123", "name": "Test Company"},
            "users": [],
            "documents": [],
            "corporate_memory": {
                "note": "Corporate memory stored in Graphiti/Neo4j - use separate export"
            },
        }

        # Mock both the role check (in deps.py) and the user profile fetch (in the route)
        with patch("src.db.supabase.SupabaseClient.get_user_by_id") as mock_get_user:
            # First call is from role check, returns admin role
            # Second call is from the route itself, returns company_id
            mock_get_user.side_effect = AsyncMock(
                side_effect=[
                    {"role": "admin", "company_id": "company-123"},  # Role check
                    {"company_id": "company-123"},  # Route call
                ]
            )
            with patch.object(
                compliance.compliance_service,
                "export_company_data",
                new=AsyncMock(return_value=mock_response),
            ):
                response = admin_test_client.get("/api/v1/compliance/data/export/company")

        assert response.status_code == 200
        data = response.json()
        assert "company_id" in data
        assert "exported_by" in data

    def test_export_company_service_error(self, admin_test_client: TestClient) -> None:
        """Test that company export handles service errors."""
        with patch("src.db.supabase.SupabaseClient.get_user_by_id") as mock_get_user:
            mock_get_user.side_effect = AsyncMock(
                side_effect=[
                    {"role": "admin", "company_id": "company-123"},  # Role check
                    {"company_id": "company-123"},  # Route call
                ]
            )
            with patch.object(
                compliance.compliance_service,
                "export_company_data",
                new=AsyncMock(side_effect=Exception("Database error")),
            ):
                response = admin_test_client.get("/api/v1/compliance/data/export/company")

        assert response.status_code == 500
