"""Knowledge Gap Detection & Prospective Memory Generation (US-912).

Identifies what ARIA doesn't know but should, then creates Prospective
Memory entries to fill those gaps. Runs at onboarding completion and
periodically thereafter.

Gap analysis per memory domain:
- Corporate Memory: products, competitors, leadership, pricing, partnerships, certifications, financial
- Digital Twin: writing style, communication patterns, scheduling preferences
- Competitive Intelligence: competitor profiles, differentiation
- Integration connectivity: CRM, calendar, email, Slack
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import BaseModel

from src.db.supabase import SupabaseClient
from src.memory.episodic import Episode, EpisodicMemory

logger = logging.getLogger(__name__)


class KnowledgeGap(BaseModel):
    """A detected knowledge gap in a specific domain."""

    domain: str  # corporate_memory, digital_twin, competitive_intel, integrations
    subdomain: str  # e.g., "leadership", "pricing", "writing_style"
    description: str
    priority: str  # critical, high, medium, low
    fill_strategy: str  # "agent_research", "user_prompt", "integration_sync"
    suggested_agent: str | None = None  # analyst, scout, hunter, operator
    suggested_prompt: str | None = None  # Natural conversation prompt for user
    estimated_effort: str = "low"  # low, medium, high


class GapAnalysisResult(BaseModel):
    """Result of a full gap analysis across all memory domains."""

    gaps: list[KnowledgeGap] = []
    total_gaps: int = 0
    critical_gaps: int = 0
    domains_analyzed: int = 0
    completeness_by_domain: dict[str, float] = {}


# Required knowledge domains for Corporate Memory analysis
_CORPORATE_DOMAINS: dict[str, dict[str, Any]] = {
    "leadership": {
        "keywords": ["ceo", "cto", "cfo", "vp", "chief", "president", "director"],
        "priority": "high",
        "agent": "analyst",
        "prompt": "Who are the key decision-makers at your target accounts?",
    },
    "products": {
        "keywords": ["product", "pipeline", "drug", "therapy", "platform", "service"],
        "priority": "high",
        "agent": "analyst",
        "prompt": "Can you tell me about your company's main products or services?",
    },
    "competitors": {
        "keywords": ["competitor", "competing", "rival", "alternative"],
        "priority": "high",
        "agent": "scout",
        "prompt": "Who do you see as your top 3 competitors?",
    },
    "pricing": {
        "keywords": ["pricing", "price", "cost", "rate", "fee"],
        "priority": "medium",
        "agent": None,
        "prompt": (
            "I don't have information about your pricing model yet. "
            "Could you share how you typically price your services?"
        ),
    },
    "partnerships": {
        "keywords": ["partner", "collaboration", "alliance", "deal"],
        "priority": "medium",
        "agent": "scout",
        "prompt": None,
    },
    "certifications": {
        "keywords": ["certification", "certified", "iso", "gmp", "fda approved"],
        "priority": "medium",
        "agent": "analyst",
        "prompt": "What certifications or regulatory approvals does your company hold?",
    },
    "financial": {
        "keywords": ["revenue", "funding", "series", "ipo", "valuation", "profit"],
        "priority": "low",
        "agent": "scout",
        "prompt": None,
    },
}

# Critical integrations to check
_CRITICAL_INTEGRATIONS: dict[str, dict[str, Any]] = {
    "crm": {"names": {"salesforce", "hubspot"}, "priority": "high"},
    "calendar": {"names": {"googlecalendar", "outlook365calendar"}, "priority": "high"},
    "email": {"names": {"google", "microsoft"}, "priority": "high"},
    "slack": {"names": {"slack"}, "priority": "medium"},
}

# Priority → completeness penalty mapping
_PRIORITY_PENALTY: dict[str, int] = {
    "critical": 25,
    "high": 15,
    "medium": 8,
    "low": 3,
}


class KnowledgeGapDetector:
    """Identifies knowledge gaps and creates Prospective Memory entries.

    Compares what ARIA knows against ideal profiles for the user's
    company type, role, and goals. Gaps become agent tasks or
    natural conversation prompts.
    """

    def __init__(self) -> None:
        self.db = SupabaseClient.get_client()

    async def detect_gaps(self, user_id: str) -> GapAnalysisResult:
        """Run full gap analysis across all memory domains.

        Args:
            user_id: The user to analyze.

        Returns:
            GapAnalysisResult with all detected gaps and completeness scores.
        """
        facts = await self._get_semantic_facts(user_id)
        settings = await self._get_user_settings(user_id)
        integrations = await self._get_integrations(user_id)
        classification = await self._get_company_classification(user_id)

        corp_gaps = await self._analyze_corporate_memory(facts, classification)
        twin_gaps = await self._analyze_digital_twin(settings, facts)
        intel_gaps = await self._analyze_competitive_intel(facts, classification)
        integ_gaps = self._analyze_integrations(integrations)

        all_gaps = corp_gaps + twin_gaps + intel_gaps + integ_gaps

        result = GapAnalysisResult(
            gaps=all_gaps,
            total_gaps=len(all_gaps),
            critical_gaps=len([g for g in all_gaps if g.priority == "critical"]),
            domains_analyzed=4,
            completeness_by_domain={
                "corporate_memory": self._domain_completeness(corp_gaps),
                "digital_twin": self._domain_completeness(twin_gaps),
                "competitive_intel": self._domain_completeness(intel_gaps),
                "integrations": self._domain_completeness(integ_gaps),
            },
        )

        await self._create_prospective_entries(user_id, all_gaps)
        await self._store_gap_report(user_id, result)

        try:
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="knowledge_gap_analysis",
                content=(
                    f"Identified {result.total_gaps} knowledge gaps "
                    f"across {result.domains_analyzed} domains"
                ),
                participants=[],
                occurred_at=datetime.now(UTC),
                recorded_at=datetime.now(UTC),
                context={
                    "total_gaps": result.total_gaps,
                    "critical_gaps": result.critical_gaps,
                    "completeness": result.completeness_by_domain,
                },
            )
            await EpisodicMemory().store_episode(episode)
        except Exception as e:
            logger.warning(f"Episodic record failed: {e}")

        return result

    async def _analyze_corporate_memory(
        self,
        facts: list[dict[str, Any]],
        classification: dict[str, Any] | None,  # noqa: ARG002
    ) -> list[KnowledgeGap]:
        """Check Corporate Memory against ideal profile.

        Scans semantic facts for keywords and metadata categories
        that indicate knowledge about each corporate domain.

        Args:
            facts: Semantic facts from memory_semantic.
            classification: Company classification from enrichment.

        Returns:
            List of KnowledgeGaps for missing corporate domains.
        """
        gaps: list[KnowledgeGap] = []
        fact_text = " ".join(f.get("fact", "").lower() for f in facts)
        fact_categories = {f.get("metadata", {}).get("category") for f in facts}

        for domain, config in _CORPORATE_DOMAINS.items():
            has_info = (
                any(kw in fact_text for kw in config["keywords"]) or domain in fact_categories
            )
            if not has_info:
                gaps.append(
                    KnowledgeGap(
                        domain="corporate_memory",
                        subdomain=domain,
                        description=f"No information about {domain}",
                        priority=config["priority"],
                        fill_strategy="agent_research" if config["agent"] else "user_prompt",
                        suggested_agent=config["agent"],
                        suggested_prompt=config["prompt"],
                    )
                )

        return gaps

    async def _analyze_digital_twin(
        self,
        settings: dict[str, Any] | None,
        facts: list[dict[str, Any]],  # noqa: ARG002
    ) -> list[KnowledgeGap]:
        """Check Digital Twin completeness.

        Examines user_settings.preferences.digital_twin for writing style,
        communication patterns, and scheduling preferences.

        Args:
            settings: User settings from user_settings table.
            facts: Semantic facts (unused currently, reserved for future).

        Returns:
            List of KnowledgeGaps for missing Digital Twin domains.
        """
        gaps: list[KnowledgeGap] = []

        dt = (settings or {}).get("preferences", {}).get("digital_twin", {})

        # Writing style
        ws = dt.get("writing_style", {})
        if not ws or ws.get("confidence", 0) < 0.5:
            gaps.append(
                KnowledgeGap(
                    domain="digital_twin",
                    subdomain="writing_style",
                    description="Writing style fingerprint is low confidence or missing",
                    priority="high",
                    fill_strategy="user_prompt",
                    suggested_prompt=(
                        "I'd love to match your writing style more closely. "
                        "Could you forward me 3-4 recent emails you wrote? "
                        "I'll analyze them and draft everything in your voice."
                    ),
                )
            )

        # Communication patterns
        patterns = dt.get("communication_patterns", {})
        if not patterns or not patterns.get("peak_send_hours"):
            gaps.append(
                KnowledgeGap(
                    domain="digital_twin",
                    subdomain="communication_patterns",
                    description="Communication patterns not yet established",
                    priority="medium",
                    fill_strategy="integration_sync",
                    suggested_prompt=(
                        "Connecting your email would help me understand your "
                        "communication rhythm — when you're most active, who you "
                        "talk to most, and how you like to follow up."
                    ),
                )
            )

        # Scheduling preferences
        if not dt.get("scheduling_preferences"):
            gaps.append(
                KnowledgeGap(
                    domain="digital_twin",
                    subdomain="scheduling",
                    description="No scheduling preferences captured",
                    priority="low",
                    fill_strategy="user_prompt",
                    suggested_prompt=(
                        "What does your ideal meeting schedule look like? "
                        "Morning focus time, afternoon meetings? Any days you protect?"
                    ),
                )
            )

        return gaps

    async def _analyze_competitive_intel(
        self,
        facts: list[dict[str, Any]],
        classification: dict[str, Any] | None,  # noqa: ARG002
    ) -> list[KnowledgeGap]:
        """Check competitive intelligence depth.

        Looks for competitor-tagged facts and differentiation data.

        Args:
            facts: Semantic facts from memory_semantic.
            classification: Company classification from enrichment.

        Returns:
            List of KnowledgeGaps for missing competitive intelligence.
        """
        gaps: list[KnowledgeGap] = []

        competitor_facts = [
            f
            for f in facts
            if f.get("metadata", {}).get("category") == "competitive"
            or "competitor" in f.get("fact", "").lower()
        ]

        if len(competitor_facts) < 3:
            gaps.append(
                KnowledgeGap(
                    domain="competitive_intel",
                    subdomain="competitor_profiles",
                    description=(
                        f"Only {len(competitor_facts)} competitor data points "
                        f"found — need deeper profiles"
                    ),
                    priority="high",
                    fill_strategy="agent_research",
                    suggested_agent="analyst",
                )
            )

        diff_facts = [
            f
            for f in facts
            if "differentiat" in f.get("fact", "").lower()
            or "advantage" in f.get("fact", "").lower()
        ]
        if not diff_facts:
            gaps.append(
                KnowledgeGap(
                    domain="competitive_intel",
                    subdomain="differentiation",
                    description="No competitive differentiation data captured",
                    priority="high",
                    fill_strategy="user_prompt",
                    suggested_prompt=(
                        "What makes your company different from competitors? "
                        "What's your strongest selling point in a competitive deal?"
                    ),
                )
            )

        return gaps

    def _analyze_integrations(self, integrations: list[dict[str, Any]]) -> list[KnowledgeGap]:
        """Check which critical integrations are missing.

        Compares connected providers against the required set of
        CRM, calendar, email, and Slack integrations.

        Args:
            integrations: List of user integration records.

        Returns:
            List of KnowledgeGaps for missing integrations.
        """
        gaps: list[KnowledgeGap] = []
        connected = {i.get("integration_type", "") for i in integrations}

        for category, config in _CRITICAL_INTEGRATIONS.items():
            if not config["names"].intersection(connected):
                gaps.append(
                    KnowledgeGap(
                        domain="integrations",
                        subdomain=category,
                        description=f"No {category} integration connected",
                        priority=config["priority"],
                        fill_strategy="integration_sync",
                        suggested_prompt=(
                            f"Connecting your {category} would significantly "
                            f"improve my effectiveness. Want to set that up?"
                        ),
                    )
                )

        return gaps

    def _domain_completeness(self, gaps: list[KnowledgeGap]) -> float:
        """Calculate domain completeness inversely from gap count and priority.

        Args:
            gaps: Gaps detected in this domain.

        Returns:
            Completeness score 0-100. 100 means no gaps.
        """
        if not gaps:
            return 100.0
        penalty = sum(_PRIORITY_PENALTY.get(g.priority, 5) for g in gaps)
        return max(0.0, 100.0 - penalty)

    async def _create_prospective_entries(self, user_id: str, gaps: list[KnowledgeGap]) -> None:
        """Create Prospective Memory entries for each gap.

        Each gap becomes a pending task in prospective_memories with
        metadata about the domain, priority, fill strategy, and
        any suggested agent or prompt.

        Args:
            user_id: The user who owns these gaps.
            gaps: Detected knowledge gaps to create entries for.
        """
        for gap in gaps:
            try:
                entry = {
                    "user_id": user_id,
                    "task": f"Fill knowledge gap: {gap.description}",
                    "status": "pending",
                    "metadata": {
                        "type": "knowledge_gap",
                        "domain": gap.domain,
                        "subdomain": gap.subdomain,
                        "priority": gap.priority,
                        "fill_strategy": gap.fill_strategy,
                        "suggested_agent": gap.suggested_agent,
                        "suggested_prompt": gap.suggested_prompt,
                    },
                }
                self.db.table("prospective_memories").insert(entry).execute()  # type: ignore[arg-type]
            except Exception as e:
                logger.warning(f"Failed to create prospective entry: {e}")

    async def _store_gap_report(self, user_id: str, result: GapAnalysisResult) -> None:
        """Store the gap report in onboarding_state metadata.

        Args:
            user_id: The user to store the report for.
            result: The gap analysis result to persist.
        """
        self.db.table("onboarding_state").update(
            {
                "metadata": {
                    "gap_analysis": {
                        "total_gaps": result.total_gaps,
                        "critical_gaps": result.critical_gaps,
                        "completeness": result.completeness_by_domain,
                        "analyzed_at": datetime.now(UTC).isoformat(),
                    }
                }
            }
        ).eq("user_id", user_id).execute()

    # --- Data fetchers ---

    async def _get_semantic_facts(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch semantic facts for a user.

        Args:
            user_id: The user to fetch facts for.

        Returns:
            List of fact records from memory_semantic.
        """
        result = (
            self.db.table("memory_semantic")
            .select("fact, confidence, source, metadata")
            .eq("user_id", user_id)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data or [])

    async def _get_user_settings(self, user_id: str) -> dict[str, Any] | None:
        """Fetch user settings.

        Args:
            user_id: The user to fetch settings for.

        Returns:
            User settings record or None.
        """
        result = (
            self.db.table("user_settings")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return cast(dict[str, Any], result.data)
        return None

    async def _get_integrations(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch user integrations.

        Args:
            user_id: The user to fetch integrations for.

        Returns:
            List of integration records.
        """
        result = (
            self.db.table("user_integrations")
            .select("integration_type, created_at")
            .eq("user_id", user_id)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data or [])

    async def _get_onboarding_state(self, user_id: str) -> dict[str, Any] | None:
        """Fetch onboarding state.

        Args:
            user_id: The user to fetch state for.

        Returns:
            Onboarding state record or None.
        """
        result = (
            self.db.table("onboarding_state")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            return cast(dict[str, Any], result.data)
        return None

    async def _get_company_classification(self, user_id: str) -> dict[str, Any] | None:
        """Fetch company classification for a user.

        Looks up the user's company and returns its classification
        from company settings.

        Args:
            user_id: The user to look up.

        Returns:
            Classification dict or None.
        """
        profile = (
            self.db.table("user_profiles")
            .select("company_id")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        if not profile or not profile.data:
            return None
        profile_data = cast(dict[str, Any], profile.data)
        if not profile_data.get("company_id"):
            return None
        company = (
            self.db.table("companies")
            .select("settings")
            .eq("id", profile_data["company_id"])
            .maybe_single()
            .execute()
        )
        if company and company.data:
            company_data = cast(dict[str, Any], company.data)
            return cast(
                dict[str, Any] | None,
                company_data.get("settings", {}).get("classification"),
            )
        return None
