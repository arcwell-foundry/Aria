"""Skills Pre-Configuration from Onboarding (US-918).

Recommends and pre-installs relevant skills based on company type,
user role, and therapeutic area discovered during onboarding.

Skills are installed at COMMUNITY trust level, building trust through
usage as designed in US-530 (Autonomy System).
"""

import logging
from typing import Any

from src.security.trust_levels import SkillTrustLevel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Skill Recommendations Mapping
# ---------------------------------------------------------------------------

# Mapping of company type to recommended skill IDs
# These are skill_path values that would exist in skills_index
SKILL_RECOMMENDATIONS: dict[str, list[str]] = {
    "Cell/Gene Therapy": [
        "clinical-trial-analysis",
        "regulatory-monitor-rmat",
        "pubmed-research",
        "patient-advocacy-tracking",
    ],
    "CDMO": [
        "competitive-positioning",
        "manufacturing-capacity-analysis",
        "quality-compliance-monitor",
        "rfp-response-helper",
    ],
    "Large Pharma": [
        "market-analysis",
        "kol-mapping",
        "patent-monitor",
        "formulary-tracking",
    ],
    "Biotech": [
        "clinical-trial-analysis",
        "investor-relations-monitor",
        "competitive-positioning",
        "pubmed-research",
    ],
    "CRO": [
        "site-identification",
        "protocol-analysis",
        "regulatory-monitor",
        "competitive-pricing",
    ],
    "Diagnostics": [
        "market-analysis",
        "regulatory-monitor-510k",
        "payer-landscape",
        "competitive-positioning",
    ],
    "Medical Device": [
        "regulatory-monitor-510k",
        "kol-mapping",
        "competitive-positioning",
        "market-analysis",
    ],
}


# Default fallback when company type not recognized
_DEFAULT_RECOMMENDATIONS = SKILL_RECOMMENDATIONS["Biotech"]


class SkillRecommendationEngine:
    """Service for recommending and pre-installing skills during onboarding.

    Uses company classification from CompanyEnrichmentEngine (US-903)
    to recommend relevant skills. Skills are installed at COMMUNITY
    trust level and earn higher trust through usage.

    Integrates with:
    - SkillInstaller (US-525): For skill installation
    - SkillIndex (US-524): For skill metadata lookup
    - OnboardingReadinessService (US-913): For integrations score update
    """

    def __init__(self) -> None:
        """Initialize the skill recommendation engine."""
        self._installer: Any = None

    async def recommend(
        self, company_type: str, role: str = ""
    ) -> list[dict[str, Any]]:
        """Get skill recommendations for a company type.

        Args:
            company_type: The company classification from enrichment
                         (e.g., "Cell/Gene Therapy", "CDMO", "Large Pharma")
            role: Optional user role for future refinement

        Returns:
            List of skill recommendation dicts with skill_id and trust_level.
            All recommendations use COMMUNITY trust level initially.
        """
        # Get skill IDs for company type, fall back to Biotech default
        skill_ids = SKILL_RECOMMENDATIONS.get(company_type, _DEFAULT_RECOMMENDATIONS)

        # Return as recommendation dicts with COMMUNITY trust level
        recommendations = [
            {"skill_id": skill_id, "trust_level": SkillTrustLevel.COMMUNITY.value}
            for skill_id in skill_ids
        ]

        logger.debug(
            f"Generated {len(recommendations)} skill recommendations "
            f"for company_type='{company_type}', role='{role}'"
        )

        return recommendations

    async def pre_install(
        self, user_id: str, skills: list[dict[str, Any]]
    ) -> int:
        """Pre-install recommended skills at COMMUNITY trust level.

        Installs each skill using SkillInstaller from Phase 5B (US-525).
        Skills are marked as auto_installed=True to distinguish from
        user-initiated installations.

        Installation failures are logged but don't stop the process—
        some skills may not exist in the index yet.

        Args:
            user_id: The user's UUID
            skills: List of skill recommendation dicts from recommend()

        Returns:
            Number of skills successfully installed
        """
        if not skills:
            return 0

        # Lazy import to avoid circular dependency
        from src.skills.installer import SkillInstaller

        installed_count = 0

        for skill in skills:
            skill_id = skill["skill_id"]
            try:
                installer = SkillInstaller()
                await installer.install(
                    user_id,
                    skill_id,
                    auto_installed=True,
                )
                installed_count += 1
                logger.info(f"Pre-installed skill {skill_id} for user {user_id}")
            except Exception as e:
                # Log warning but continue with other skills
                logger.warning(
                    f"Skill install failed for {skill_id} (user {user_id}): {e}"
                )

        logger.info(
            f"Pre-installed {installed_count}/{len(skills)} skills for user {user_id}"
        )

        return installed_count
