"""Tests for Skills Pre-Configuration from Onboarding (US-918).

Tests the SkillRecommendationEngine which recommends and pre-installs
relevant skills based on company classification using LLM reasoning.
"""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.onboarding.skill_recommender import (
    AVAILABLE_SKILLS,
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
    with (
        patch(
            "src.skills.installer.SkillInstaller",
            return_value=mock_installer,
        ),
        patch(
            "src.skills.index.SkillIndex",
        ) as mock_index_class,
        patch(
            "src.onboarding.skill_recommender.LLMClient",
        ) as mock_llm_cls,
    ):
        mock_index = MagicMock()
        mock_index.get_skill = AsyncMock(
            return_value=MagicMock(
                skill_path="test-skill",
                trust_level=SkillTrustLevel.COMMUNITY,
                declared_permissions=[],
            )
        )
        mock_index_class.return_value = mock_index

        # Default LLM response returns valid skill IDs
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(
            return_value=json.dumps([
                "competitive-positioning",
                "market-analysis",
                "regulatory-monitor",
                "pubmed-research",
            ])
        )
        mock_llm_cls.return_value = mock_llm

        yield SkillRecommendationEngine()


# ---------------------------------------------------------------------------
# Available Skills Catalog tests
# ---------------------------------------------------------------------------


class TestSkillsCatalog:
    """Tests for the available skills catalog."""

    def test_catalog_has_skills(self) -> None:
        """Catalog contains available skills."""
        assert len(AVAILABLE_SKILLS) > 10

    def test_each_skill_has_id_and_description(self) -> None:
        """Every skill has both id and description."""
        for skill in AVAILABLE_SKILLS:
            assert "id" in skill
            assert "description" in skill
            assert len(skill["id"]) > 0
            assert len(skill["description"]) > 0

    def test_no_duplicate_skill_ids(self) -> None:
        """No duplicate skill IDs in catalog."""
        ids = [s["id"] for s in AVAILABLE_SKILLS]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# recommend() method tests
# ---------------------------------------------------------------------------


class TestRecommendMethod:
    """Tests for the recommend() method."""

    @pytest.mark.asyncio
    async def test_returns_recommendations_with_community_trust(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """Recommendations use COMMUNITY trust level."""
        result = await engine.recommend("Biotech", role="Sales")

        assert len(result) > 0
        assert all(s["trust_level"] == "community" for s in result)

    @pytest.mark.asyncio
    async def test_accepts_full_classification_object(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """Full classification dict is accepted and used."""
        classification = {
            "company_type": "Bioprocessing Equipment Manufacturer",
            "company_description": "Makes chromatography systems",
            "primary_customers": ["CDMOs", "Pharma"],
            "value_chain_position": "Upstream supplier",
            "primary_modality": "Bioprocessing Equipment",
            "company_posture": "Seller",
            "therapeutic_areas": [],
            "key_products": ["OPUS columns"],
        }

        result = await engine.recommend(
            "Bioprocessing Equipment Manufacturer",
            role="Sales",
            classification=classification,
        )

        assert len(result) > 0
        assert all(s["trust_level"] == "community" for s in result)

    @pytest.mark.asyncio
    async def test_falls_back_on_llm_failure(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """Falls back to default skills when LLM fails."""
        engine._llm.generate_response = AsyncMock(side_effect=Exception("LLM down"))

        result = await engine.recommend("Unknown Type")

        # Should return fallback skills
        assert len(result) == 4
        skill_ids = [s["skill_id"] for s in result]
        assert "competitive-positioning" in skill_ids
        assert "market-analysis" in skill_ids

    @pytest.mark.asyncio
    async def test_falls_back_on_invalid_json(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """Falls back when LLM returns invalid JSON."""
        engine._llm.generate_response = AsyncMock(return_value="not json")

        result = await engine.recommend("Biotech")

        assert len(result) == 4  # Fallback skills

    @pytest.mark.asyncio
    async def test_validates_skill_ids_against_catalog(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """Invalid skill IDs from LLM are filtered out."""
        engine._llm.generate_response = AsyncMock(
            return_value=json.dumps([
                "market-analysis",  # valid
                "nonexistent-skill",  # invalid
                "pubmed-research",  # valid
            ])
        )

        result = await engine.recommend("Biotech")

        skill_ids = [s["skill_id"] for s in result]
        assert "market-analysis" in skill_ids
        assert "pubmed-research" in skill_ids
        assert "nonexistent-skill" not in skill_ids

    @pytest.mark.asyncio
    async def test_caps_at_six_skills(
        self, engine: SkillRecommendationEngine
    ) -> None:
        """Caps recommendations at 6 skills."""
        all_ids = [s["id"] for s in AVAILABLE_SKILLS]
        engine._llm.generate_response = AsyncMock(
            return_value=json.dumps(all_ids)  # Return all skills
        )

        result = await engine.recommend("Biotech")

        assert len(result) <= 6


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
        mock_installer.install.side_effect = [
            MagicMock(id="installed-1"),
            Exception("Skill not found"),
            MagicMock(id="installed-3"),
        ]

        skills = [
            {"skill_id": "skill-1", "trust_level": "community"},
            {"skill_id": "skill-2", "trust_level": "community"},
            {"skill_id": "skill-3", "trust_level": "community"},
        ]

        installed = await engine.pre_install("user-123", skills)

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
        assert call_args[0][0] == "user-abc"
        assert call_args[0][1] == "test-skill"


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

        recommendations = await engine.recommend("Biotech")
        assert len(recommendations) > 0

        installed_count = await engine.pre_install("user-123", recommendations)

        assert installed_count == len(recommendations)
        assert mock_installer.install.call_count == len(recommendations)

    @pytest.mark.asyncio
    async def test_workflow_with_full_classification(
        self, engine: SkillRecommendationEngine, mock_installer: MagicMock
    ) -> None:
        """Workflow works with full classification object."""
        mock_installer.install.return_value = MagicMock(id="installed")

        classification = {
            "company_type": "Clinical-Stage Biotech",
            "company_description": "Develops CAR-T therapies",
            "primary_customers": ["Cancer centers"],
            "value_chain_position": "Drug developer",
            "primary_modality": "Cell Therapy",
            "company_posture": "Buyer",
            "therapeutic_areas": ["Oncology"],
            "key_products": ["CAR-T platform"],
        }

        recommendations = await engine.recommend(
            "Clinical-Stage Biotech",
            classification=classification,
        )
        installed = await engine.pre_install("user-123", recommendations)

        assert installed > 0
        assert installed == len(recommendations)
