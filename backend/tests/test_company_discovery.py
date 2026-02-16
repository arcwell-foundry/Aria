"""Tests for Company Discovery service (US-902).

Tests email domain validation, life sciences gate, company profile creation,
and the full submission flow with proper integration to memory systems.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.onboarding.company_discovery import (
    PERSONAL_DOMAINS,
    CompanyDiscoveryService,
)


@pytest.fixture
def mock_db():
    """Mock Supabase client."""
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
        data=None
    )
    client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "test-company-id", "name": "Test Company", "domain": "testcompany.com"}]
    )
    client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "user-123", "company_id": "test-company-id"}]
    )
    return client


@pytest.fixture
def mock_llm():
    """Mock LLM client for life sciences gate."""
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    """Create service instance with mocked dependencies."""
    serv = CompanyDiscoveryService()
    serv._db = mock_db
    return serv


class TestValidateEmailDomain:
    """Tests for email domain validation."""

    @pytest.mark.parametrize(
        "email,domain",
        [
            ("user@gmail.com", "gmail.com"),
            ("user@yahoo.com", "yahoo.com"),
            ("user@hotmail.com", "hotmail.com"),
            ("user@outlook.com", "outlook.com"),
            ("user@aol.com", "aol.com"),
            ("user@icloud.com", "icloud.com"),
            ("user@mail.com", "mail.com"),
            ("user@protonmail.com", "protonmail.com"),
            ("user@zoho.com", "zoho.com"),
        ],
    )
    async def test_rejects_personal_email_domains(self, service, email, domain):
        """Personal email domains are rejected with clear message."""
        result = await service.validate_email_domain(email)
        assert result["valid"] is False
        assert "corporate email address" in result["reason"].lower()
        assert domain in PERSONAL_DOMAINS

    @pytest.mark.parametrize(
        "email",
        [
            ("user@pfizer.com"),
            ("user@genentech.com"),
            ("user@company.co.uk"),
            ("user@startup.io"),
            ("user@biotech.tech"),
        ],
    )
    async def test_accepts_corporate_email_domains(self, service, email):
        """Corporate email domains are accepted."""
        result = await service.validate_email_domain(email)
        assert result["valid"] is True
        assert result["reason"] is None

    async def test_handles_mixed_case_email(self, service):
        """Email validation is case-insensitive for domain."""
        result = await service.validate_email_domain("user@GMAIL.COM")
        assert result["valid"] is False

    async def test_handles_subdomain(self, service):
        """Subdomains of personal domains are still rejected."""
        result = await service.validate_email_domain("user@mail.gmail.com")
        assert result["valid"] is False


class TestLifeSciencesGate:
    """Tests for LLM-based life sciences vertical detection."""

    async def test_accepts_life_sciences_company(self, service, mock_llm):
        """Valid life sciences companies pass the gate."""
        # Mock LLM to return positive life sciences assessment
        mock_llm.generate_response.return_value = json.dumps(
            {
                "is_life_sciences": True,
                "confidence": 0.95,
                "reasoning": "Pfizer is a major pharmaceutical company",
            }
        )

        with patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm):
            result = await service.check_life_sciences_gate("Pfizer Inc", "https://pfizer.com")

        assert result["is_life_sciences"] is True
        assert result["confidence"] == 0.95
        assert "pharmaceutical" in result["reasoning"].lower()

    async def test_rejects_non_life_sciences_company(self, service, mock_llm):
        """Non-life sciences companies fail the gate gracefully."""
        mock_llm.generate_response.return_value = json.dumps(
            {
                "is_life_sciences": False,
                "confidence": 0.9,
                "reasoning": "Software company specializing in e-commerce",
            }
        )

        with patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm):
            result = await service.check_life_sciences_gate(
                "TechStartup Inc", "https://techstartup.io"
            )

        assert result["is_life_sciences"] is False
        assert result["confidence"] == 0.9
        assert "software" in result["reasoning"].lower()

    async def test_handles_malformed_llm_response(self, service, mock_llm):
        """Gracefully handles LLM responses that aren't valid JSON."""
        mock_llm.generate_response.return_value = "Not valid JSON"

        with patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm):
            result = await service.check_life_sciences_gate("Test Company", "https://test.com")

        assert result["is_life_sciences"] is True
        assert result["confidence"] == 0.5
        assert "manual review" in result["reasoning"].lower()

    async def test_handles_partial_llm_response(self, service, mock_llm):
        """Handles JSON response missing some fields."""
        mock_llm.generate_response.return_value = json.dumps(
            {"is_life_sciences": True, "confidence": 0.8}
        )

        with patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm):
            result = await service.check_life_sciences_gate("Test Company", "https://test.com")

        assert result["is_life_sciences"] is True
        assert result["confidence"] == 0.8
        # reasoning should default to empty string when missing


class TestCheckExistingCompany:
    """Tests for checking if company already exists (cross-user acceleration)."""

    async def test_returns_none_when_company_not_found(self, service, mock_db):
        """Returns None when no existing company matches."""
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )

        result = await service.check_existing_company("newcompany.com")

        assert result is None

    async def test_returns_company_when_found(self, service, mock_db):
        """Returns company data when existing company matches."""
        existing_company = {
            "id": "existing-id",
            "name": "Existing Biotech",
            "domain": "existingbiotech.com",
            "settings": {"source": "onboarding"},
        }
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=existing_company
        )

        result = await service.check_existing_company("existingbiotech.com")

        assert result["id"] == "existing-id"
        assert result["name"] == "Existing Biotech"


class TestCreateCompanyProfile:
    """Tests for company profile creation and user linking."""

    async def test_creates_new_company(self, service, mock_db):
        """Creates new company record and links user."""
        # Mock no existing company
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )
        # Mock company creation
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "new-company-id",
                    "name": "New Biotech",
                    "domain": "newbiotech.com",
                    "settings": {},
                }
            ]
        )

        result = await service.create_company_profile(
            user_id="user-123",
            company_name="New Biotech",
            website="https://newbiotech.com",
            email="user@newbiotech.com",
        )

        assert result["id"] == "new-company-id"
        assert result["is_existing"] is False
        assert result["domain"] == "newbiotech.com"

    async def test_links_user_to_existing_company(self, service, mock_db):
        """Links user to existing company (cross-user acceleration)."""
        existing_company = {
            "id": "existing-id",
            "name": "Existing Biotech",
            "domain": "existingbiotech.com",
            "settings": {},
        }
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=existing_company
        )

        result = await service.create_company_profile(
            user_id="user-456",
            company_name="Existing Biotech",
            website="https://existingbiotech.com",
            email="user2@existingbiotech.com",
        )

        assert result["id"] == "existing-id"
        assert result["is_existing"] is True
        assert result["name"] == "Existing Biotech"

    async def test_normalizes_website_domain(self, service, mock_db):
        """Normalizes various website URL formats to domain."""
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "id", "name": "Test", "domain": "test.com", "settings": {}}]
        )

        test_cases = [
            "https://www.test.com",
            "http://test.com",
            "https://test.com/",
            "http://www.test.com/",
            "www.test.com",
        ]

        for website in test_cases:
            result = await service.create_company_profile(
                user_id="user-123", company_name="Test", website=website, email="user@test.com"
            )
            assert result["domain"] == "test.com"


class TestSubmitCompanyDiscovery:
    """Tests for the full company discovery submission flow."""

    async def test_successful_submission_new_company(self, service, mock_db, mock_llm):
        """Full flow succeeds with valid life sciences company."""
        # Mock no existing company
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            MagicMock(data=None),  # check_existing_company
        ]
        # Mock company creation
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "new-id",
                    "name": "Test Biotech",
                    "domain": "testbiotech.com",
                    "settings": {},
                }
            ]
        )
        # Mock LLM life sciences check
        mock_llm.generate_response.return_value = json.dumps(
            {"is_life_sciences": True, "confidence": 0.9, "reasoning": "Biotech company"}
        )

        with (
            patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm),
            patch(
                "src.onboarding.company_discovery.SupabaseClient.get_client", return_value=mock_db
            ),
            patch("src.onboarding.company_discovery.EpisodicMemory") as mock_memory,
            patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch,
        ):
            mock_memory_instance = AsyncMock()
            mock_memory.return_value = mock_memory_instance
            mock_orch_instance = AsyncMock()
            mock_orch.return_value = mock_orch_instance

            result = await service.submit_company_discovery(
                user_id="user-123",
                company_name="Test Biotech",
                website="https://testbiotech.com",
                email="user@testbiotech.com",
            )

        assert result["success"] is True
        assert result["company"]["id"] == "new-id"
        assert result["company"]["is_existing"] is False
        assert result["gate_result"]["is_life_sciences"] is True
        assert result["enrichment_status"] == "queued"

    async def test_personal_email_rejected(self, service, mock_db):
        """Personal email domain fails validation."""
        result = await service.submit_company_discovery(
            user_id="user-123",
            company_name="Test",
            website="https://test.com",
            email="user@gmail.com",
        )

        assert result["success"] is False
        assert result["type"] == "email_validation"
        assert "corporate email" in result["error"].lower()

    async def test_non_life_sciences_still_succeeds(self, service, mock_db, mock_llm):
        """Non-life sciences company still goes through (gate is informational, not blocking)."""
        mock_llm.generate_response.return_value = json.dumps(
            {"is_life_sciences": False, "confidence": 0.85, "reasoning": "Tech company"}
        )
        # Mock no existing company
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            MagicMock(data=None),  # check_existing_company
        ]
        # Mock company creation
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "new-id",
                    "name": "Tech Corp",
                    "domain": "techcorp.io",
                    "settings": {},
                }
            ]
        )

        with (
            patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm),
            patch(
                "src.onboarding.company_discovery.SupabaseClient.get_client", return_value=mock_db
            ),
            patch("src.onboarding.company_discovery.EpisodicMemory") as mock_memory,
            patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch,
        ):
            mock_memory_instance = AsyncMock()
            mock_memory.return_value = mock_memory_instance
            mock_orch_instance = AsyncMock()
            mock_orch.return_value = mock_orch_instance

            result = await service.submit_company_discovery(
                user_id="user-123",
                company_name="Tech Corp",
                website="https://techcorp.io",
                email="user@techcorp.io",
            )

        # Gate no longer blocks; company is created regardless
        assert result["success"] is True
        assert result["company"]["id"] == "new-id"
        assert result["enrichment_status"] == "queued"

    async def test_existing_company_cross_user_acceleration(self, service, mock_db, mock_llm):
        """User #2+ gets linked to existing company."""
        existing_company = {
            "id": "existing-id",
            "name": "Existing Bio",
            "domain": "existingbio.com",
            "settings": {},
        }
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            MagicMock(data=existing_company),  # check_existing_company
        ]
        mock_llm.generate_response.return_value = json.dumps(
            {"is_life_sciences": True, "confidence": 0.95, "reasoning": "Biotech"}
        )

        with (
            patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm),
            patch(
                "src.onboarding.company_discovery.SupabaseClient.get_client", return_value=mock_db
            ),
            patch("src.onboarding.company_discovery.EpisodicMemory") as mock_memory,
            patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch,
        ):
            mock_memory_instance = AsyncMock()
            mock_memory.return_value = mock_memory_instance
            mock_orch_instance = AsyncMock()
            mock_orch.return_value = mock_orch_instance

            result = await service.submit_company_discovery(
                user_id="user-456",
                company_name="Existing Bio",
                website="https://existingbio.com",
                email="user2@existingbio.com",
            )

        assert result["success"] is True
        assert result["company"]["is_existing"] is True
        assert result["company"]["id"] == "existing-id"

    async def test_records_episodic_memory_on_success(self, service, mock_db, mock_llm):
        """Successful submission records event to episodic memory."""
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            MagicMock(data=None),
        ]
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "id", "name": "Test", "domain": "test.com", "settings": {}}]
        )
        mock_llm.generate_response.return_value = json.dumps(
            {"is_life_sciences": True, "confidence": 0.9, "reasoning": "Bio"}
        )

        with (
            patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm),
            patch(
                "src.onboarding.company_discovery.SupabaseClient.get_client", return_value=mock_db
            ),
            patch("src.onboarding.company_discovery.EpisodicMemory") as mock_memory,
            patch("src.onboarding.orchestrator.OnboardingOrchestrator"),
        ):
            mock_memory_instance = MagicMock()
            mock_memory.return_value = mock_memory_instance
            mock_memory_instance.store_episode = AsyncMock()

            await service.submit_company_discovery(
                user_id="user-123",
                company_name="Test",
                website="https://test.com",
                email="user@test.com",
            )

            # Verify episodic memory was called
            mock_memory_instance.store_episode.assert_called_once()
            call_args = mock_memory_instance.store_episode.call_args
            episode = call_args[0][0]
            assert episode.user_id == "user-123"
            assert episode.event_type == "onboarding_company_registered"

    async def test_updates_readiness_score_on_success(self, service, mock_db, mock_llm):
        """Successful submission updates corporate_memory readiness."""
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            MagicMock(data=None),
        ]
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "id", "name": "Test", "domain": "test.com", "settings": {}}]
        )
        mock_llm.generate_response.return_value = json.dumps(
            {"is_life_sciences": True, "confidence": 0.9, "reasoning": "Bio"}
        )

        with (
            patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm),
            patch(
                "src.onboarding.company_discovery.SupabaseClient.get_client", return_value=mock_db
            ),
            patch("src.onboarding.company_discovery.EpisodicMemory") as mock_memory,
            patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch,
        ):
            mock_memory_instance = MagicMock()
            mock_memory.return_value = mock_memory_instance
            mock_memory_instance.store_episode = AsyncMock()
            mock_orch_instance = AsyncMock()
            mock_orch.return_value = mock_orch_instance

            await service.submit_company_discovery(
                user_id="user-123",
                company_name="Test",
                website="https://test.com",
                email="user@test.com",
            )

            # Verify readiness score was updated
            mock_orch_instance.update_readiness_scores.assert_called_once()
            call_args = mock_orch_instance.update_readiness_scores.call_args
            assert call_args[0][0] == "user-123"
            assert "corporate_memory" in call_args[0][1]

    async def test_handles_episodic_memory_failure_gracefully(
        self, service, mock_db, mock_llm, caplog
    ):
        """Episodic memory failure doesn't block submission."""
        import logging as py_logging

        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            MagicMock(data=None),
        ]
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "id", "name": "Test", "domain": "test.com", "settings": {}}]
        )
        mock_llm.generate_response.return_value = json.dumps(
            {"is_life_sciences": True, "confidence": 0.9, "reasoning": "Bio"}
        )

        with (
            patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm),
            patch(
                "src.onboarding.company_discovery.SupabaseClient.get_client", return_value=mock_db
            ),
            patch("src.onboarding.company_discovery.EpisodicMemory") as mock_memory,
            patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch,
        ):
            # Mock episodic to raise error
            mock_memory_instance = MagicMock()
            mock_memory.return_value = mock_memory_instance
            mock_memory_instance.store_episode = AsyncMock(side_effect=Exception("Memory error"))
            mock_orch_instance = AsyncMock()
            mock_orch.return_value = mock_orch_instance

            result = await service.submit_company_discovery(
                user_id="user-123",
                company_name="Test",
                website="https://test.com",
                email="user@test.com",
            )

        # Still succeeds despite memory failure
        assert result["success"] is True

    async def test_handles_readiness_update_failure_gracefully(
        self, service, mock_db, mock_llm, caplog
    ):
        """Readiness update failure doesn't block submission."""
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            MagicMock(data=None),
        ]
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "id", "name": "Test", "domain": "test.com", "settings": {}}]
        )
        mock_llm.generate_response.return_value = json.dumps(
            {"is_life_sciences": True, "confidence": 0.9, "reasoning": "Bio"}
        )

        with (
            patch("src.onboarding.company_discovery.LLMClient", return_value=mock_llm),
            patch(
                "src.onboarding.company_discovery.SupabaseClient.get_client", return_value=mock_db
            ),
            patch("src.onboarding.company_discovery.EpisodicMemory") as mock_memory,
            patch("src.onboarding.orchestrator.OnboardingOrchestrator") as mock_orch,
        ):
            mock_memory_instance = MagicMock()
            mock_memory.return_value = mock_memory_instance
            mock_memory_instance.store_episode = AsyncMock()
            # Mock orchestrator to raise error
            mock_orch_instance = AsyncMock()
            mock_orch_instance.update_readiness_scores.side_effect = Exception("Update error")
            mock_orch.return_value = mock_orch_instance

            result = await service.submit_company_discovery(
                user_id="user-123",
                company_name="Test",
                website="https://test.com",
                email="user@test.com",
            )

        # Still succeeds despite readiness update failure
        assert result["success"] is True


@pytest.mark.parametrize(
    "website,expected_domain",
    [
        ("https://www.pfizer.com", "pfizer.com"),
        ("http://genentech.com", "genentech.com"),
        ("https://lonza.com/", "lonza.com"),
        ("http://www.catalent.com/products", "catalent.com"),
    ],
)
async def test_domain_normalization(website, expected_domain, mock_db):
    """Website URLs are normalized to clean domains."""
    mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
        data=None
    )
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "id", "name": "Test", "domain": expected_domain, "settings": {}}]
    )

    service = CompanyDiscoveryService()
    service._db = mock_db

    result = await service.create_company_profile(
        user_id="user-123", company_name="Test", website=website, email="user@test.com"
    )

    assert result["domain"] == expected_domain
