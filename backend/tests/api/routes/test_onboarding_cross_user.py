"""Tests for cross-user onboarding acceleration API routes (US-917).

These tests follow TDD principles - tests were written first, then implementation.
Tests the API endpoints for detecting existing Corporate Memory when user #2+
at a company starts onboarding and recommending step skipping.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import onboarding


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(onboarding.router)
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

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


class TestGetCrossUserAcceleration:
    """Tests for GET /onboarding/cross-user endpoint."""

    def test_get_cross_user_acceleration_new_company(
        self, test_client: TestClient
    ) -> None:
        """Test GET /cross-user with non-existent domain returns full recommendation."""
        with patch(
            "src.onboarding.cross_user.CrossUserAccelerationService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.check_company_exists = MagicMock(
                return_value=MagicMock(
                    exists=False,
                    company_id=None,
                    company_name=None,
                    richness_score=0,
                    recommendation="full",
                )
            )
            mock_service_class.return_value = mock_service

            with patch(
                "src.api.routes.onboarding.SupabaseClient"
            ) as mock_supabase:
                mock_db = MagicMock()
                mock_supabase.get_client.return_value = mock_db

                response = test_client.get("/onboarding/cross-user?domain=newcompany.com")

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["company_id"] is None
        assert data["company_name"] is None
        assert data["richness_score"] == 0
        assert data["recommendation"] == "full"
        assert data["facts"] == []

    def test_get_cross_user_acceleration_existing_company(
        self, test_client: TestClient
    ) -> None:
        """Test GET /cross-user with existing domain returns company data."""
        with patch(
            "src.onboarding.cross_user.CrossUserAccelerationService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.check_company_exists = MagicMock(
                return_value=MagicMock(
                    exists=True,
                    company_id="company-123",
                    company_name="Acme Corp",
                    richness_score=85,
                    recommendation="skip",
                )
            )
            mock_service.get_company_memory_delta = MagicMock(
                return_value={
                    "facts": [
                        {
                            "id": "fact-1",
                            "fact": "Acme Corp specializes_in biotechnology",
                            "domain": "product",
                            "confidence": 0.9,
                            "source": "extracted",
                        },
                        {
                            "id": "fact-2",
                            "fact": "Acme Corp has_headquarters San Francisco",
                            "domain": "geography",
                            "confidence": 0.85,
                            "source": "aggregated",
                        },
                    ],
                    "high_confidence_facts": [
                        {
                            "id": "fact-1",
                            "fact": "Acme Corp specializes_in biotechnology",
                            "domain": "product",
                            "confidence": 0.9,
                            "source": "extracted",
                        }
                    ],
                    "domains_covered": ["product", "geography"],
                    "total_fact_count": 2,
                }
            )
            mock_service_class.return_value = mock_service

            with patch(
                "src.api.routes.onboarding.SupabaseClient"
            ) as mock_supabase:
                mock_db = MagicMock()
                mock_supabase.get_client.return_value = mock_db

                response = test_client.get("/onboarding/cross-user?domain=acmecorp.com")

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["company_id"] == "company-123"
        assert data["company_name"] == "Acme Corp"
        assert data["richness_score"] == 85
        assert data["recommendation"] == "skip"
        assert len(data["facts"]) == 2
        assert data["facts"][0]["fact"] == "Acme Corp specializes_in biotechnology"
        assert data["facts"][0]["confidence"] == 0.9

    def test_get_cross_user_acceleration_missing_domain_param(
        self, test_client: TestClient
    ) -> None:
        """Test GET /cross-user without domain parameter returns 422."""
        response = test_client.get("/onboarding/cross-user")
        assert response.status_code == 422

    def test_get_cross_user_acceleration_unauthenticated(self) -> None:
        """Test GET /cross-user returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/onboarding/cross-user?domain=test.com")
        assert response.status_code == 401

    def test_get_cross_user_acceleration_partial_recommendation(
        self, test_client: TestClient
    ) -> None:
        """Test GET /cross-user with partial recommendation (30-80 richness)."""
        with patch(
            "src.onboarding.cross_user.CrossUserAccelerationService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.check_company_exists = MagicMock(
                return_value=MagicMock(
                    exists=True,
                    company_id="company-456",
                    company_name="Partial Corp",
                    richness_score=50,
                    recommendation="partial",
                )
            )
            mock_service.get_company_memory_delta = MagicMock(
                return_value={
                    "facts": [],
                    "high_confidence_facts": [],
                    "domains_covered": [],
                    "total_fact_count": 0,
                }
            )
            mock_service_class.return_value = mock_service

            with patch(
                "src.api.routes.onboarding.SupabaseClient"
            ) as mock_supabase:
                mock_db = MagicMock()
                mock_supabase.get_client.return_value = mock_db

                response = test_client.get("/onboarding/cross-user?domain=partialcorp.com")

        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["company_id"] == "company-456"
        assert data["richness_score"] == 50
        assert data["recommendation"] == "partial"


class TestConfirmCompanyData:
    """Tests for POST /onboarding/cross-user/confirm endpoint."""

    def test_confirm_company_data_success(self, test_client: TestClient) -> None:
        """Test POST /cross-user/confirm successfully confirms and links user."""
        with patch(
            "src.onboarding.cross_user.CrossUserAccelerationService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.confirm_company_data = AsyncMock(
                return_value={
                    "user_linked": True,
                    "steps_skipped": ["company_discovery", "document_upload"],
                    "readiness_inherited": 85,
                    "corrections_applied": 0,
                }
            )
            mock_service_class.return_value = mock_service

            with patch(
                "src.api.routes.onboarding.SupabaseClient"
            ) as mock_supabase:
                mock_db = MagicMock()
                mock_supabase.get_client.return_value = mock_db

                response = test_client.post(
                    "/onboarding/cross-user/confirm",
                    json={
                        "company_id": "company-123",
                        "corrections": {},
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["user_linked"] is True
        assert data["steps_skipped"] == ["company_discovery", "document_upload"]
        assert data["readiness_inherited"] == 85
        assert data["corrections_applied"] == 0

    def test_confirm_company_data_with_corrections(
        self, test_client: TestClient
    ) -> None:
        """Test POST /cross-user/confirm with corrections applies them."""
        with patch(
            "src.onboarding.cross_user.CrossUserAccelerationService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.confirm_company_data = AsyncMock(
                return_value={
                    "user_linked": True,
                    "steps_skipped": ["company_discovery", "document_upload"],
                    "readiness_inherited": 75,
                    "corrections_applied": 2,
                }
            )
            mock_service_class.return_value = mock_service

            with patch(
                "src.api.routes.onboarding.SupabaseClient"
            ) as mock_supabase:
                mock_db = MagicMock()
                mock_supabase.get_client.return_value = mock_db

                response = test_client.post(
                    "/onboarding/cross-user/confirm",
                    json={
                        "company_id": "company-123",
                        "corrections": {
                            "headquarters": "New York, NY",
                            "industry": "Biotechnology",
                        },
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["corrections_applied"] == 2

    def test_confirm_company_data_missing_company_id(
        self, test_client: TestClient
    ) -> None:
        """Test POST /cross-user/confirm without company_id returns 422."""
        response = test_client.post(
            "/onboarding/cross-user/confirm",
            json={"corrections": {}},
        )
        assert response.status_code == 422

    def test_confirm_company_data_unauthenticated(self) -> None:
        """Test POST /cross-user/confirm returns 401 without auth."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post(
            "/onboarding/cross-user/confirm",
            json={"company_id": "company-123", "corrections": {}},
        )
        assert response.status_code == 401

    def test_confirm_company_data_service_error(
        self, test_client: TestClient
    ) -> None:
        """Test POST /cross-user/confirm handles service errors gracefully."""
        with patch(
            "src.onboarding.cross_user.CrossUserAccelerationService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.confirm_company_data = AsyncMock(
                side_effect=Exception("Database connection failed")
            )
            mock_service_class.return_value = mock_service

            with patch(
                "src.api.routes.onboarding.SupabaseClient"
            ) as mock_supabase:
                mock_db = MagicMock()
                mock_supabase.get_client.return_value = mock_db

                response = test_client.post(
                    "/onboarding/cross-user/confirm",
                    json={"company_id": "company-123", "corrections": {}},
                )

        assert response.status_code == 500
        assert "Failed to confirm company data" in response.json()["detail"]
