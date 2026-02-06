"""Tests for US-917: Cross-User Onboarding Acceleration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.cross_user import (
    CompanyCheckResult,
    CrossUserAccelerationService,
    MemoryDeltaFact,
)


@pytest.fixture
def mock_db():
    """Mock Supabase client."""
    return MagicMock()


@pytest.fixture
def service(mock_db):
    """Create CrossUserAccelerationService with mocked database."""
    with patch("src.onboarding.cross_user.SupabaseClient.get_client", return_value=mock_db):
        return CrossUserAccelerationService()


class TestCrossUserAccelerationService:
    """Test suite for CrossUserAccelerationService."""

    def test_normalize_domain(self, service):
        """Test domain normalization."""
        assert service._normalize_domain("https://acme-corp.com") == "acme-corp.com"
        assert service._normalize_domain("http://www.example.com") == "example.com"
        assert service._normalize_domain("www.test.com/path") == "test.com"
        assert service._normalize_domain("sub.domain.com:8080") == "sub.domain.com"
        assert service._normalize_domain("MixedCase.Com") == "mixedcase.com"

    def test_check_company_exists_not_found(self, service, mock_db):
        """Test check_company_exists when company not found."""
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = None

        result = service.check_company_exists("newcompany.com")

        assert result.exists is False
        assert result.company_id is None
        assert result.company_name is None
        assert result.richness_score == 0
        assert result.recommendation == "full"

    def test_check_company_exists_found_with_high_richness(self, service, mock_db):
        """Test check_company_exists with high richness (>70%)."""
        # Mock company found
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={"id": "comp-123", "name": "Acme Corp", "domain": "acme.com"}
        )

        # Mock corporate_facts query with many facts
        mock_facts = [{"predicate": "is", "confidence": 0.8} for _ in range(25)]
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=mock_facts
        )

        with patch.object(service, "_calculate_corporate_richness", return_value=85):
            result = service.check_company_exists("acme.com")

        assert result.exists is True
        assert result.company_id == "comp-123"
        assert result.company_name == "Acme Corp"
        assert result.richness_score == 85
        assert result.recommendation == "skip"

    def test_check_company_exists_found_with_partial_richness(self, service, mock_db):
        """Test check_company_exists with partial richness (30-70%)."""
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={"id": "comp-456", "name": "Biotech Inc", "domain": "biotech.com"}
        )

        with patch.object(service, "_calculate_corporate_richness", return_value=50):
            result = service.check_company_exists("biotech.com")

        assert result.exists is True
        assert result.recommendation == "partial"

    def test_calculate_corporate_richness_no_facts(self, service, mock_db):
        """Test richness calculation with no facts."""
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=None
        )

        richness = service._calculate_corporate_richness("comp-123")
        assert richness == 0

    def test_calculate_corporate_richness_with_facts(self, service, mock_db):
        """Test richness calculation with facts."""
        # Mock 20 facts with 8 unique predicates and 0.8 avg confidence
        predicates = [
            "is",
            "manufactures",
            "focuses on",
            "located in",
            "founded",
            "CEO",
            "revenue",
            "partners",
        ]
        facts = []
        for i in range(20):
            facts.append({"predicate": predicates[i % 8], "confidence": 0.8})

        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=facts
        )

        richness = service._calculate_corporate_richness("comp-123")

        # Expected calculation:
        # fact_score = (20/20) * 100 = 100
        # diversity_score = (8/8) * 100 = 100
        # confidence_score = 0.8 * 100 = 80
        # richness = 100*0.4 + 100*0.3 + 80*0.3 = 40 + 30 + 24 = 94
        assert richness == 94

    def test_get_company_memory_delta_excludes_personal_data(self, service, mock_db):
        """Test memory delta only returns corporate facts, not personal data."""
        # Mock corporate facts (no user-specific data)
        facts_data = [
            {
                "subject": "Acme Corp",
                "predicate": "is",
                "object": "Biotech CDMO",
                "confidence": 0.9,
                "source": "extracted",
            },
            {
                "subject": "Acme Corp",
                "predicate": "manufactures",
                "object": "cell therapies",
                "confidence": 0.85,
                "source": "aggregated",
            },
        ]

        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=facts_data
        )

        delta = service.get_company_memory_delta("comp-123", "user-456")

        assert delta["company_id"] == "comp-123"
        assert delta["count"] == 2
        assert len(delta["facts"]) == 2
        assert delta["facts"][0]["subject"] == "Acme Corp"
        assert delta["facts"][0]["predicate"] == "is"

    @pytest.mark.asyncio
    async def test_confirm_company_data_links_user_and_skips_steps(self, service, mock_db):
        """Test confirm_company_data links user and skips steps."""
        # Mock profile update
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"id": "user-123"}])
        )

        with patch("src.onboarding.cross_user.OnboardingOrchestrator") as mock_orch:
            with patch("src.onboarding.cross_user.OnboardingReadinessService") as mock_readiness:
                mock_orch.return_value.skip_step = AsyncMock()
                mock_readiness.return_value.recalculate = AsyncMock()

                with patch.object(service, "_calculate_corporate_richness", return_value=80):
                    with patch.object(service, "_record_episodic_event", new_callable=AsyncMock):
                        result = await service.confirm_company_data("comp-123", "user-456", {})

        assert result["user_linked"] is True
        assert "company_discovery" in result["steps_skipped"]
        assert "document_upload" in result["steps_skipped"]
        assert result["readiness_inherited"] == 64  # 80 * 0.8

    @pytest.mark.asyncio
    async def test_confirm_company_data_applies_corrections(self, service, mock_db):
        """Test confirm_company_data applies corrections to facts."""
        # Mock profile update
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"id": "user-123"}])
        )

        # Mock fact updates - both succeed in this test
        update_results = [MagicMock(data=[{"id": "fact-1"}]), MagicMock(data=[{"id": "fact-2"}])]
        mock_db.table.return_value.update.side_effect = [
            # First call for profile
            MagicMock(data=[{"id": "user-123"}]),
            # Second call for first fact correction
            update_results[0],
            # Third call for second fact correction
            update_results[1],
        ]

        corrections = {
            "fact-1": "corrected value",
            "fact-2": "another correction",
        }

        with patch("src.onboarding.cross_user.OnboardingOrchestrator") as mock_orch:
            with patch("src.onboarding.cross_user.OnboardingReadinessService") as mock_readiness:
                mock_orch.return_value.skip_step = AsyncMock()
                mock_readiness.return_value.recalculate = AsyncMock()

                with patch.object(service, "_calculate_corporate_richness", return_value=50):
                    with patch.object(service, "_record_episodic_event", new_callable=AsyncMock):
                        result = await service.confirm_company_data(
                            "comp-123", "user-456", corrections
                        )

        assert result["corrections_applied"] == 2  # Both succeeded

    @pytest.mark.asyncio
    async def test_confirm_company_data_low_richness_skips_less(self, service, mock_db):
        """Test confirm_company_data skips less steps with low richness."""
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"id": "user-123"}])
        )

        with patch("src.onboarding.cross_user.OnboardingOrchestrator") as mock_orch:
            with patch("src.onboarding.cross_user.OnboardingReadinessService") as mock_readiness:
                mock_orch.return_value.skip_step = AsyncMock()
                mock_readiness.return_value.recalculate = AsyncMock()

                with patch.object(service, "_calculate_corporate_richness", return_value=40):
                    with patch.object(service, "_record_episodic_event", new_callable=AsyncMock):
                        result = await service.confirm_company_data("comp-123", "user-456", {})

        # Only company_discovery skipped, not document_upload (<70%)
        assert result["steps_skipped"] == ["company_discovery"]

    @pytest.mark.asyncio
    async def test_confirm_company_data_records_episodic_event(self, service, mock_db):
        """Test confirm_company_data records episodic memory event."""
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[{"id": "user-123"}])
        )

        mock_episodic_memory = MagicMock()
        mock_episodic_memory.store_episode = AsyncMock()

        with patch("src.onboarding.cross_user.OnboardingOrchestrator") as mock_orch:
            with patch("src.onboarding.cross_user.OnboardingReadinessService") as mock_readiness:
                mock_orch.return_value.skip_step = AsyncMock()
                mock_readiness.return_value.recalculate = AsyncMock()

                with patch("src.memory.episodic.EpisodicMemory", return_value=mock_episodic_memory):
                    with patch.object(service, "_calculate_corporate_richness", return_value=80):
                        await service.confirm_company_data("comp-123", "user-456", {})

        # Verify episodic event was recorded
        assert mock_episodic_memory.store_episode.call_count == 1
        episode_arg = mock_episodic_memory.store_episode.call_args[0][0]
        assert episode_arg.event_type == "cross_user_acceleration"
        assert "Cross-user acceleration applied" in episode_arg.content


class TestMemoryDeltaFact:
    """Test suite for MemoryDeltaFact."""

    def test_to_dict(self):
        """Test MemoryDeltaFact serialization."""
        fact = MemoryDeltaFact(
            subject="Acme Corp",
            predicate="is",
            object="Biotech CDMO",
            confidence=0.9,
            source="extracted",
        )

        result = fact.to_dict()

        assert result == {
            "subject": "Acme Corp",
            "predicate": "is",
            "object": "Biotech CDMO",
            "confidence": 0.9,
            "source": "extracted",
        }


class TestCompanyCheckResult:
    """Test suite for CompanyCheckResult."""

    def test_result_attributes(self):
        """Test CompanyCheckResult stores all attributes."""
        result = CompanyCheckResult(
            exists=True,
            company_id="comp-123",
            company_name="Acme Corp",
            richness_score=85,
            recommendation="skip",
        )

        assert result.exists is True
        assert result.company_id == "comp-123"
        assert result.company_name == "Acme Corp"
        assert result.richness_score == 85
        assert result.recommendation == "skip"
