"""Skills Pre-Configuration from Onboarding (US-918).

Recommends and pre-installs relevant skills based on company classification,
user role, and therapeutic area discovered during onboarding.

Uses LLM reasoning over the full classification object instead of rigid
company_type string matching. Skills are installed at COMMUNITY trust level,
building trust through usage as designed in US-530 (Autonomy System).
"""

import json
import logging
from typing import Any

from src.core.llm import LLMClient
from src.security.trust_levels import SkillTrustLevel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Available Skills Catalog
# ---------------------------------------------------------------------------

# All available skills that can be recommended.
# The LLM chooses from this catalog based on the full company classification.
AVAILABLE_SKILLS: list[dict[str, str]] = [
    {
        "id": "clinical-trial-analysis",
        "description": "Monitor and analyze clinical trials, phases, endpoints, and results",
    },
    {
        "id": "regulatory-monitor-rmat",
        "description": "Track RMAT (Regenerative Medicine Advanced Therapy) designations and regulatory updates",
    },
    {
        "id": "pubmed-research",
        "description": "Search and summarize PubMed literature for scientific intelligence",
    },
    {
        "id": "patient-advocacy-tracking",
        "description": "Monitor patient advocacy groups and their influence on treatment access",
    },
    {
        "id": "competitive-positioning",
        "description": "Analyze competitive landscape, positioning, and differentiation",
    },
    {
        "id": "manufacturing-capacity-analysis",
        "description": "Track manufacturing capacity, facility expansions, and production capabilities",
    },
    {
        "id": "quality-compliance-monitor",
        "description": "Monitor quality systems, FDA warning letters, and compliance events",
    },
    {"id": "rfp-response-helper", "description": "Help draft and organize RFP/RFI responses"},
    {
        "id": "market-analysis",
        "description": "Analyze market size, trends, and growth opportunities",
    },
    {
        "id": "kol-mapping",
        "description": "Identify and map Key Opinion Leaders in therapeutic areas",
    },
    {"id": "patent-monitor", "description": "Track patent filings, expirations, and IP landscape"},
    {"id": "formulary-tracking", "description": "Monitor formulary decisions and payer coverage"},
    {
        "id": "investor-relations-monitor",
        "description": "Track investor presentations, SEC filings, and financial events",
    },
    {"id": "site-identification", "description": "Identify and evaluate clinical trial sites"},
    {
        "id": "protocol-analysis",
        "description": "Analyze clinical trial protocols and study designs",
    },
    {
        "id": "regulatory-monitor",
        "description": "General regulatory monitoring across FDA, EMA, and other agencies",
    },
    {"id": "competitive-pricing", "description": "Track and analyze competitor pricing strategies"},
    {
        "id": "regulatory-monitor-510k",
        "description": "Monitor 510(k) submissions and medical device regulatory pathway",
    },
    {
        "id": "payer-landscape",
        "description": "Analyze payer landscape, reimbursement, and market access",
    },
]

# Formatted catalog for LLM prompt
_SKILLS_CATALOG_TEXT = "\n".join(f"- {s['id']}: {s['description']}" for s in AVAILABLE_SKILLS)


class SkillRecommendationEngine:
    """Service for recommending and pre-installing skills during onboarding.

    Uses LLM reasoning over the full company classification from
    CompanyEnrichmentEngine (US-903) to recommend relevant skills.
    Skills are installed at COMMUNITY trust level and earn higher
    trust through usage.

    Integrates with:
    - SkillInstaller (US-525): For skill installation
    - SkillIndex (US-524): For skill metadata lookup
    - OnboardingReadinessService (US-913): For integrations score update
    """

    def __init__(self) -> None:
        """Initialize the skill recommendation engine."""
        self._installer: Any = None
        self._llm = LLMClient()

    async def recommend(
        self,
        company_type: str,
        role: str = "",
        classification: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Get skill recommendations using LLM reasoning over classification.

        When a full classification dict is provided, the LLM reasons about
        which skills are most relevant based on the company's actual business,
        customers, value chain position, and products. Falls back to
        company_type-only reasoning when classification is not available.

        Args:
            company_type: The company type string (used as fallback context).
            role: Optional user role for refinement.
            classification: Full classification dict from enrichment (preferred).

        Returns:
            List of skill recommendation dicts with skill_id and trust_level.
            All recommendations use COMMUNITY trust level initially.
        """
        skill_ids = await self._llm_recommend(company_type, role, classification)

        recommendations = [
            {"skill_id": skill_id, "trust_level": SkillTrustLevel.COMMUNITY.value}
            for skill_id in skill_ids
        ]

        logger.debug(
            f"Generated {len(recommendations)} skill recommendations "
            f"for company_type='{company_type}', role='{role}'"
        )

        return recommendations

    async def _llm_recommend(
        self,
        company_type: str,
        role: str,
        classification: dict[str, Any] | None,
    ) -> list[str]:
        """Use LLM to select skills based on full classification context.

        Args:
            company_type: Company type string.
            role: User role.
            classification: Full classification dict.

        Returns:
            List of skill IDs (4-6 skills).
        """
        # Build context block from classification
        if classification:
            context = (
                f"Company type: {classification.get('company_type', company_type)}\n"
                f"Description: {classification.get('company_description', 'Not available')}\n"
                f"Primary customers: {', '.join(classification.get('primary_customers', []))}\n"
                f"Value chain position: {classification.get('value_chain_position', 'Unknown')}\n"
                f"Primary modality: {classification.get('primary_modality', 'Unknown')}\n"
                f"Company posture: {classification.get('company_posture', 'Unknown')}\n"
                f"Therapeutic areas: {', '.join(classification.get('therapeutic_areas', []))}\n"
                f"Key products: {', '.join(classification.get('key_products', []))}\n"
            )
        else:
            context = f"Company type: {company_type}\n"

        if role:
            context += f"User role: {role}\n"

        prompt = f"""Given this company classification, select the 4-6 most relevant skills from the catalog below.

{context}

Available skills:
{_SKILLS_CATALOG_TEXT}

Select skills that would be most useful for a sales professional at this specific type of company.
Consider:
- What the company actually does (not just a generic category)
- Who their customers are
- Where they sit in the value chain
- What competitive intelligence would be most valuable

Return ONLY a JSON array of skill IDs (strings), no additional text. Example: ["market-analysis", "competitive-positioning"]"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            skill_ids = json.loads(response)
            if isinstance(skill_ids, list) and all(isinstance(s, str) for s in skill_ids):
                # Validate against available skills
                valid_ids = {s["id"] for s in AVAILABLE_SKILLS}
                return [s for s in skill_ids if s in valid_ids][:6]
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"LLM skill recommendation failed: {e}")

        # Fallback: return general-purpose skills
        return [
            "competitive-positioning",
            "market-analysis",
            "regulatory-monitor",
            "pubmed-research",
        ]

    async def pre_install(self, user_id: str, skills: list[dict[str, Any]]) -> int:
        """Pre-install recommended skills at COMMUNITY trust level.

        Installs each skill using SkillInstaller from Phase 5B (US-525).
        Skills are marked as auto_installed=True to distinguish from
        user-initiated installations.

        Installation failures are logged but don't stop the process--
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
                logger.warning(f"Skill install failed for {skill_id} (user {user_id}): {e}")

        logger.info(f"Pre-installed {installed_count}/{len(skills)} skills for user {user_id}")

        return installed_count
