"""US-915: Onboarding Completion → Agent Activation.

Activates ARIA's six core agents immediately after onboarding completes
so the user's first morning briefing is impressive, not empty.

Each activation:
- Creates a proper Goal (US-310) with appropriate config
- Runs at LOW priority (yields to user-initiated tasks)
- Results appear in first daily briefing
- Is tracked in episodic memory
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.models.goal import GoalCreate, GoalType
from src.services.goal_service import GoalService

logger = logging.getLogger(__name__)


class OnboardingCompletionOrchestrator:
    """Orchestrates agent activation immediately after onboarding completes.

    The activation step is critical: users expect ARIA to "wake up" and
    start working the moment they finish setup. This service creates
    low-priority goals for each agent based on what ARIA learned during
    onboarding.

    Activation tasks run asynchronously and yield to any user-initiated work.
    """

    def __init__(self) -> None:
        """Initialize orchestrator with database and LLM clients."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._goal_service = GoalService()

    async def activate(self, user_id: str, onboarding_data: dict[str, Any]) -> dict[str, Any]:
        """Activate all agents based on onboarding intelligence.

        Creates goals for Scout, Analyst, Operator, and Scribe agents.
        Hunter activation is conditional on lead_gen goal being set.

        Args:
            user_id: The authenticated user's ID.
            onboarding_data: Collected intelligence from onboarding steps.

        Returns:
            Dict with activation status for each agent.
        """
        logger.info(
            "Starting post-onboarding agent activation",
            extra={"user_id": user_id},
        )

        activations: dict[str, Any] = {
            "scout": None,
            "analyst": None,
            "hunter": None,
            "operator": None,
            "scribe": None,
            "strategist": None,
        }

        # Extract company intelligence from onboarding
        company_id = onboarding_data.get("company_id")
        company_domain = onboarding_data.get("company_discovery", {}).get("website", "")
        user_goal = onboarding_data.get("first_goal", {})
        goal_type = user_goal.get("goal_type")

        # Scout: Monitor competitors and industry
        activations["scout"] = await self._activate_scout(
            user_id, company_id, company_domain, onboarding_data
        )

        # Analyst: Research top accounts
        activations["analyst"] = await self._activate_analyst(user_id, onboarding_data)

        # Hunter: Only if lead_gen goal set
        if goal_type == "lead_gen":
            activations["hunter"] = await self._activate_hunter(user_id, onboarding_data)

        # Operator: Scan CRM for data quality
        activations["operator"] = await self._activate_operator(user_id, onboarding_data)

        # Scribe: Pre-draft follow-ups for stale conversations
        activations["scribe"] = await self._activate_scribe(user_id, onboarding_data)

        # Strategist: Build go-to-market and account strategy
        activations["strategist"] = await self._activate_strategist(user_id, onboarding_data)

        # Record episodic memory event
        await self._record_activation_event(user_id, activations)

        logger.info(
            "Post-onboarding agent activation complete",
            extra={
                "user_id": user_id,
                "activations": {k: v is not None for k, v in activations.items()},
            },
        )

        return {
            "user_id": user_id,
            "activated_at": datetime.now(UTC).isoformat(),
            "activations": activations,
        }

    async def _activate_scout(
        self,
        user_id: str,
        company_id: str | None,
        company_domain: str,
        onboarding_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Activate Scout agent for competitive intelligence monitoring.

        Scout monitors:
        - Identified competitors from enrichment
        - Industry news and regulatory updates
        - Company-specific signals

        Args:
            user_id: The user's ID.
            company_id: User's company ID.
            company_domain: Company website domain.
            onboarding_data: Collected intelligence.

        Returns:
            Created goal dict or None if activation skipped.
        """
        try:
            # Extract competitors from enrichment if available
            enrichment_data = onboarding_data.get("enrichment", {})
            competitors = enrichment_data.get("competitors", [])

            # If no competitors extracted yet, seed with company domain as baseline
            entities = competitors if competitors else [company_domain]

            goal = GoalCreate(
                title="Competitive Intelligence Monitoring",
                description="ARIA monitors your competitors, industry news, and regulatory updates to keep you informed.",
                goal_type=GoalType.RESEARCH,
                config={
                    "agent": "scout",
                    "agent_type": "scout",
                    "priority": "low",  # Yield to user tasks
                    "entities": entities,
                    "signal_types": ["news", "regulatory", "competitor_activity"],
                    "company_id": company_id,
                    "source": "onboarding_activation",
                },
            )

            created = await self._goal_service.create_goal(user_id, goal)

            logger.info(
                "Scout agent activated for competitive monitoring",
                extra={"user_id": user_id, "goal_id": created["id"]},
            )

            return {"goal_id": created["id"], "entities": len(entities)}

        except Exception as e:
            logger.error(
                "Scout activation failed",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _activate_analyst(
        self,
        user_id: str,
        onboarding_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Activate Analyst agent for account research.

        Analyst:
        - Researches top 3 accounts from CRM
        - Produces pre-meeting briefs for next 48h
        - Builds stakeholder intelligence

        Args:
            user_id: The user's ID.
            onboarding_data: Collected intelligence.

        Returns:
            Created goal dict or None if activation skipped.
        """
        try:
            # Check if user has CRM data for account research
            integration_data = onboarding_data.get("integration_wizard", {})
            crm_connected = integration_data.get("crm_connected", False)

            if not crm_connected:
                logger.info(
                    "Analyst activation skipped: no CRM connected",
                    extra={"user_id": user_id},
                )
                return None

            goal = GoalCreate(
                title="Account Research & Briefing",
                description="ARIA researches your key accounts and prepares pre-meeting briefs.",
                goal_type=GoalType.RESEARCH,
                config={
                    "agent": "analyst",
                    "agent_type": "analyst",
                    "priority": "low",
                    "top_n_accounts": 3,
                    "briefing_horizon_hours": 48,
                    "source": "onboarding_activation",
                },
            )

            created = await self._goal_service.create_goal(user_id, goal)

            logger.info(
                "Analyst agent activated for account research",
                extra={"user_id": user_id, "goal_id": created["id"]},
            )

            return {"goal_id": created["id"]}

        except Exception as e:
            logger.error(
                "Analyst activation failed",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _activate_hunter(
        self,
        user_id: str,
        onboarding_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Activate Hunter agent for lead generation.

        Hunter:
        - Refines ICP from onboarding data
        - Identifies initial prospects
        - Requires lead_gen goal to be set

        Args:
            user_id: The user's ID.
            onboarding_data: Collected intelligence.

        Returns:
            Created goal dict or None if activation skipped.
        """
        try:
            goal_data = onboarding_data.get("first_goal", {})
            icp_description = goal_data.get("description", "")

            goal = GoalCreate(
                title="Prospect Identification",
                description=f"ARIA identifies and qualifies prospects matching your ICP: {icp_description}",
                goal_type=GoalType.LEAD_GEN,
                config={
                    "agent": "hunter",
                    "agent_type": "hunter",
                    "priority": "low",
                    "icp_refinement": True,
                    "initial_prospects": 10,
                    "source": "onboarding_activation",
                },
            )

            created = await self._goal_service.create_goal(user_id, goal)

            logger.info(
                "Hunter agent activated for lead generation",
                extra={"user_id": user_id, "goal_id": created["id"]},
            )

            return {"goal_id": created["id"]}

        except Exception as e:
            logger.error(
                "Hunter activation failed",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _activate_operator(
        self,
        user_id: str,
        onboarding_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Activate Operator agent for CRM data quality.

        Operator:
        - Scans CRM for stale opportunities
        - Identifies missing fields
        - Produces pipeline health snapshot

        Args:
            user_id: The user's ID.
            onboarding_data: Collected intelligence.

        Returns:
            Created goal dict or None if activation skipped.
        """
        try:
            integration_data = onboarding_data.get("integration_wizard", {})
            crm_connected = integration_data.get("crm_connected", False)

            if not crm_connected:
                logger.info(
                    "Operator activation skipped: no CRM connected",
                    extra={"user_id": user_id},
                )
                return None

            goal = GoalCreate(
                title="Pipeline Health Analysis",
                description="ARIA scans your pipeline for data quality issues and produces a health snapshot.",
                goal_type=GoalType.ANALYSIS,
                config={
                    "agent": "operator",
                    "agent_type": "operator",
                    "priority": "low",
                    "check_stale_opportunities": True,
                    "check_missing_fields": True,
                    "produce_health_snapshot": True,
                    "source": "onboarding_activation",
                },
            )

            created = await self._goal_service.create_goal(user_id, goal)

            logger.info(
                "Operator agent activated for pipeline health",
                extra={"user_id": user_id, "goal_id": created["id"]},
            )

            return {"goal_id": created["id"]}

        except Exception as e:
            logger.error(
                "Operator activation failed",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _activate_scribe(
        self,
        user_id: str,
        onboarding_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Activate Scribe agent for follow-up drafts.

        Scribe:
        - Detects stale conversations
        - Pre-drafts follow-up emails
        - Uses user's communication style from Digital Twin

        Args:
            user_id: The user's ID.
            onboarding_data: Collected intelligence.

        Returns:
            Created goal dict or None if activation skipped.
        """
        try:
            # Check if email integration provides conversation data
            integration_data = onboarding_data.get("integration_wizard", {})
            email_connected = integration_data.get("email_connected", False)

            if not email_connected:
                logger.info(
                    "Scribe activation skipped: no email connected",
                    extra={"user_id": user_id},
                )
                return None

            goal = GoalCreate(
                title="Follow-Up Email Drafts",
                description="ARIA detects stale conversations and pre-drafts follow-up emails in your style.",
                goal_type=GoalType.OUTREACH,
                config={
                    "agent": "scribe",
                    "agent_type": "scribe",
                    "priority": "low",
                    "stale_threshold_days": 7,
                    "max_drafts": 5,
                    "use_digital_twin_style": True,
                    "source": "onboarding_activation",
                },
            )

            created = await self._goal_service.create_goal(user_id, goal)

            logger.info(
                "Scribe agent activated for follow-up drafts",
                extra={"user_id": user_id, "goal_id": created["id"]},
            )

            return {"goal_id": created["id"]}

        except Exception as e:
            logger.error(
                "Scribe activation failed",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None


    async def _activate_strategist(
        self,
        user_id: str,
        onboarding_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Activate Strategist agent for go-to-market strategy.

        Strategist:
        - Synthesizes company intelligence into strategic recommendations
        - Identifies key account priorities based on enrichment data
        - Creates territory and engagement strategies

        Args:
            user_id: The user's ID.
            onboarding_data: Collected intelligence.

        Returns:
            Created goal dict or None if activation failed.
        """
        try:
            enrichment_data = onboarding_data.get("enrichment", {})
            user_goal = onboarding_data.get("first_goal", {})

            goal = GoalCreate(
                title="Strategic Assessment & Prioritization",
                description="ARIA analyzes your market position and recommends strategic account priorities.",
                goal_type=GoalType.ANALYSIS,
                config={
                    "agent": "strategist",
                    "agent_type": "strategist",
                    "priority": "low",
                    "company_type": enrichment_data.get("company_type"),
                    "user_goal_type": user_goal.get("goal_type"),
                    "source": "onboarding_activation",
                },
            )

            created = await self._goal_service.create_goal(user_id, goal)

            logger.info(
                "Strategist agent activated for strategic assessment",
                extra={"user_id": user_id, "goal_id": created["id"]},
            )

            return {"goal_id": created["id"]}

        except Exception as e:
            logger.error(
                "Strategist activation failed",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _record_activation_event(
        self,
        user_id: str,
        activations: dict[str, Any],
    ) -> None:
        """Record activation event to episodic memory.

        Args:
            user_id: The user's ID.
            activations: Dict of activation results per agent.
        """
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            memory = EpisodicMemory()
            now = datetime.now(UTC)

            activated_count = sum(1 for v in activations.values() if v is not None)

            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="onboarding_activation",
                content=f"Post-onboarding activation: spawned {activated_count} agents",
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "activations": {k: v is not None for k, v in activations.items()},
                    "count": activated_count,
                },
            )
            await memory.store_episode(episode)

        except Exception as e:
            logger.warning(
                "Failed to record activation episodic event",
                extra={"user_id": user_id, "error": str(e)},
            )
