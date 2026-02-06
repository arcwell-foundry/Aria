"""Tests for Skills Pre-Configuration from Onboarding (US-918).

Tests the SkillRecommendationEngine which recommends and pre-installs
relevant skills based on company type, user role, and therapeutic area
discovered during onboarding.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.skill_recommender import (
    SKILL_RECOMMENDATIONS,
    SkillRecommendationEngine,
)
from src.security.trust_levels import SkillTrustLevel

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_installer():
    """Mock SkillInstaller."""
    installer = MagicMock()
    installer.install = AsyncMock(return_value=MagicMock(id="installed-skill"))
    return installer


@pytest.fixture
def engine(mock_installer):
    """Create SkillRecommendationEngine with mocked dependencies."""
    # Patch SkillInstaller and also SkillIndex where it's imported in install() method
    with patch(
        "src.skills.installer.SkillInstaller",
        return_value=mock_installer,
    ), patch(
        "src.skills.index.SkillIndex",
    ) as mock_index_class:
        # Mock the SkillIndex instance and its get_skill method
        mock_index = MagicMock()
        mock_index.get_skill = AsyncMock(return_value=MagicMock(
            skill_path="test-skill",
            trust_level=SkillTrustLevel.COMMUNITY,
            declared_permissions=[],
        ))
        mock_index_class.return_value = mock_index
        yield SkillRecommendationEngine()


# ---------------------------------------------------------------------------
# Mapping table tests
# ---------------------------------------------------------------------------


class TestSkillMappingTable:
    """Tests for the skill recommendations mapping table."""

    def test_cell_gene_therapy_mapping(self) -> None:
        """Cell/Gene Therapy companies get clinical and regulatory skills."""
        skills = SKILL_RECOMMENDATIONS.get("Cell/Gene Therapy", [])

        assert "clinical-trial-analysis" in skills
        assert "regulatory-monitor-rmat" in skills
        assert "pubmed-research" in skills
        assert "patient-advocacy-tracking" in skills

    def test_cdmo_mapping(self) -> None:
        """CDMO companies get competitive and manufacturing skills."""
        skills = SKILL_RECOMMENDATIONS.get("CDMO", [])

        assert "competitive-positioning" in skills
        assert "manufacturing-capacity-analysis" in skills
        assert "quality-compliance-monitor" in skills
        assert "rfp-response-helper" in skills

    def test_large_pharma_mapping(self) -> None:
        """Large Pharma companies get market and KOL skills."""
        skills = SKILL_RECOMMENDATIONS.get("Large Pharma", [])

        assert "market-analysis" in skills
        assert "kol-mapping" in skills
        assert "patent-monitor" in skills
        assert "formulary-tracking" in skills

    def test_biotech_mapping(self) -> None:
        """Biotech companies get clinical, investor, and competitive skills."""
        skills = SKILL_RECOMMENDATIONS.get("Biotech", [])

        assert "clinical-trial-analysis" in skills
        assert "investor-relations-monitor" in skills
        assert "competitive-positioning" in skills
        assert "pubmed-research" in skills

    def test_cro_mapping(self) -> None:
        """CRO companies get site identification and protocol skills."""
        skills = SKILL_RECOMMENDATIONS.get("CRO", [])

        assert "site-identification" in skills
        assert "protocol-analysis" in skills
        assert "regulatory-monitor" in skills
        assert "competitive-pricing" in skills

    def test_diagnostics_mapping(self) -> None:
        """Diagnostics companies get regulatory and market skills."""
        skills = SKILL_RECOMMENDATIONS.get("Diagnostics", [])

        assert "market-analysis" in skills
        assert "regulatory-monitor-510k" in skills
        assert "payer-landscape" in skills
        assert "competitive-positioning" in skills

    def test_medical_device_mapping(self) -> None:
        """Medical Device companies get regulatory and KOL skills."""
        skills = SKILL_RECOMMENDATIONS.get("Medical Device", [])

        assert "regulatory-monitor-510k" in skills
        assert "kol-mapping" in skills
        assert "competitive-positioning" in skills
        assert "market-analysis" in skills


# ---------------------------------------------------------------------------
# recommend() method tests
# ---------------------------------------------------------------------------


class TestRecommendMethod:
    """Tests for the recommend() method."""

    @pytest.mark.asyncio
    async def test_returns_skills_for_known_company_type(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """Known company types return their mapped skills with community trust."""
        result = await engine.recommend("CDMO", role="Sales")

        assert len(result) == 4
        assert all(s["trust_level"] == "community" for s in result)
        skill_ids = [s["skill_id"] for s in result]
        assert "competitive-positioning" in skill_ids
        assert "manufacturing-capacity-analysis" in skill_ids

    @pytest.mark.asyncio
    async def test_uses_biotech_fallback_for_unknown_type(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """Unknown company types fall back to Biotech recommendations."""
        result = await engine.recommend("Unknown Type", role="BD")

        assert len(result) > 0
        # Should match Biotech mapping
        skill_ids = [s["skill_id"] for s in result]
        assert "clinical-trial-analysis" in skill_ids
        assert "competitive-positioning" in skill_ids

    @pytest.mark.asyncio
    async def test_handles_empty_role_parameter(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """Empty role parameter doesn't cause errors."""
        result = await engine.recommend("Large Pharma", role="")

        assert len(result) > 0
        assert all(s["trust_level"] == "community" for s in result)

    @pytest.mark.asyncio
    async def test_handles_none_role_parameter(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """None role parameter doesn't cause errors."""
        result = await engine.recommend("Diagnostics", role=None)  # type: ignore

        assert len(result) > 0
        assert all(s["trust_level"] == "community" for s in result)

    @pytest.mark.asyncio
    async def test_case_sensitive_company_type(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """Company type matching is case-sensitive for exactness."""
        # Exact case should match
        result_exact = await engine.recommend("CDMO")
        assert len(result_exact) == 4

        # Different case should fall back to Biotech
        result_diff = await engine.recommend("cdmo")
        assert len(result_diff) == 4  # Biotech has 4 skills


# ---------------------------------------------------------------------------
# pre_install() method tests
# ---------------------------------------------------------------------------


class TestPreInstallMethod:
    """Tests for the pre_install() method."""

    @pytest.mark.asyncio
    async def test_installs_all_recommended_skills(
        self, engine: SkillRecommendationEngine, mock_installer: MagicMock
    ) -> None:
        """All recommended skills are installed for the user."""
        skills = [
            {"skill_id": "skill-1", "trust_level": "community"},
            {"skill_id": "skill-2", "trust_level": "community"},
            {"skill_id": "skill-3", "trust_level": "community"},
        ]

        installed = await engine.pre_install("user-123", skills)

        assert installed == 3
        assert mock_installer.install.call_count == 3

    @pytest.mark.asyncio
    async def test_passes_auto_installed_flag(
        self, engine: SkillRecommendationEngine, mock_installer: MagicMock
    ) -> None:
        """Skills are marked as auto_installed during pre-install."""
        skills = [{"skill_id": "skill-1", "trust_level": "community"}]

        await engine.pre_install("user-123", skills)

        # Check that auto_installed=True was passed
        call_kwargs = mock_installer.install.call_args.kwargs
        assert call_kwargs.get("auto_installed") is True

    @pytest.mark.asyncio
    async def test_continues_on_single_install_failure(
        self, engine: SkillRecommendationEngine, mock_installer: MagicMock
    ) -> None:
        """Installation continues even if one skill fails."""
        # First call succeeds, second fails, third succeeds
        mock_installer.install.side_effect = [
            MagicMock(id="installed-1"),  # Success
            Exception("Skill not found"),  # Failure
            MagicMock(id="installed-3"),  # Success
        ]

        skills = [
            {"skill_id": "skill-1", "trust_level": "community"},
            {"skill_id": "skill-2", "trust_level": "community"},
            {"skill_id": "skill-3", "trust_level": "community"},
        ]

        installed = await engine.pre_install("user-123", skills)

        # Should return 2 (successful installs), not 3 or 0
        assert installed == 2

    @pytest.mark.asyncio
    async def test_handles_empty_skill_list(
        self, engine: SkillRecommendationEngine, mock_installer: MagicMock
    ) -> None:
        """Empty skill list returns 0 installed."""
        installed = await engine.pre_install("user-123", [])

        assert installed == 0
        mock_installer.install.assert_not_called()

    @pytest.mark.asyncio
    async def test_logs_warnings_for_failures(
        self, engine: SkillRecommendationEngine, mock_installer: MagicMock, caplog
    ) -> None:
        """Installation failures are logged as warnings."""
        mock_installer.install.side_effect = Exception("Skill not found")

        skills = [{"skill_id": "bad-skill", "trust_level": "community"}]

        with caplog.at_level(logging.WARNING):
            await engine.pre_install("user-123", skills)

        assert "bad-skill" in caplog.text or "Skill install failed" in caplog.text

    @pytest.mark.asyncio
    async def test_passes_user_id_and_skill_id(
        self, engine: SkillRecommendationEngine, mock_installer: MagicMock
    ) -> None:
        """Correct user_id and skill_id are passed to installer."""
        skills = [{"skill_id": "test-skill", "trust_level": "community"}]

        await engine.pre_install("user-abc", skills)

        call_args = mock_installer.install.call_args
        assert call_args[0][0] == "user-abc"  # First positional arg (user_id)
        assert call_args[0][1] == "test-skill"  # Second positional arg (skill_id)


# ---------------------------------------------------------------------------
# Full workflow tests
# ---------------------------------------------------------------------------


class TestFullWorkflow:
    """Integration tests for the full recommendation and install workflow."""

    @pytest.mark.asyncio
    async def test_recommend_and_install_workflow(
        self, engine: SkillRecommendationEngine, mock_installer: MagicMock
    ) -> None:
        """Full workflow from recommendation to installation."""
        mock_installer.install.return_value = MagicMock(id="installed-xyz")

        # Step 1: Get recommendations
        recommendations = await engine.recommend("Cell/Gene Therapy")
        assert len(recommendations) > 0

        # Step 2: Install recommendations
        installed_count = await engine.pre_install("user-123", recommendations)

        assert installed_count == len(recommendations)
        assert mock_installer.install.call_count == len(recommendations)

    @pytest.mark.asyncio
    async def test_workflow_with_real_company_types(
        self, engine: SkillRecommendationEngine, mock_installer: MagicMock
    ) -> None:
        """Workflow works for all defined company types."""
        company_types = [
            "Cell/Gene Therapy",
            "CDMO",
            "Large Pharma",
            "Biotech",
            "CRO",
            "Diagnostics",
            "Medical Device",
        ]

        mock_installer.install.return_value = MagicMock(id="installed")

        for company_type in company_types:
            recommendations = await engine.recommend(company_type)
            installed = await engine.pre_install("user-123", recommendations)

            assert installed > 0, f"No skills installed for {company_type}"
            assert installed == len(recommendations)
