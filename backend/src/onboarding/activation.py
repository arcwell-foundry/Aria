"""US-915: Onboarding Completion → Agent Activation.

Activates all agents based on onboarding intelligence when the last
onboarding step completes. Each agent gets specific activation tasks
derived from enrichment data, user's goal, and connected integrations.

Results appear in the user's first morning briefing. All activation
tasks are LOW priority — they yield to user-initiated tasks.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import BaseModel, Field

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class AgentActivation(BaseModel):
    """A planned activation task for a single agent."""

    agent: str  # scout, analyst, hunter, operator, scribe
    task: str
    priority: str = "low"
    goal_title: str
    source_data: dict[str, Any] = Field(default_factory=dict)


class ActivationResult(BaseModel):
    """Summary of the agent activation sequence."""

    activated: int
    agents: list[dict[str, Any]]


class OnboardingCompletionOrchestrator:
    """Activates all agents based on onboarding intelligence.

    Triggered when the last onboarding step completes (or user clicks
    "Skip to dashboard"). Creates proper Goals for each agent with
    tasks derived from enrichment data, user's goal, and connected
    integrations.

    All activation tasks are LOW priority — they yield to any
    user-initiated tasks.
    """

    def __init__(self) -> None:
        """Initialize orchestrator with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def activate(self, user_id: str) -> ActivationResult:
        """Run full agent activation sequence.

        Gathers onboarding context, determines which agents to activate,
        creates goals with agent assignments, records episodic memory,
        and creates prospective memory check-ins.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            ActivationResult with count and list of activated agents.
        """
        # Gather onboarding context
        classification = await self._get_classification(user_id)
        facts = await self._get_facts(user_id)
        integrations = await self._get_integrations(user_id)
        goal = await self._get_first_goal(user_id)
        contacts = await self._get_top_contacts(user_id)

        # Determine activations
        activations = self._plan_activations(classification, facts, integrations, goal, contacts)

        # Create goals and assign agents
        created: list[dict[str, Any]] = []
        for activation in activations:
            goal_id = await self._create_agent_goal(user_id, activation)
            if goal_id:
                created.append(
                    {
                        "agent": activation.agent,
                        "goal_id": goal_id,
                        "task": activation.task,
                        "goal_title": activation.goal_title,
                    }
                )

        # Record episodic memory
        await self._record_episodic_event(user_id, created)

        # Create prospective memory check-ins
        await self._create_prospective_checkins(user_id, created)

        # Audit log
        await self._log_audit(user_id, created)

        logger.info(
            "Agent activation complete",
            extra={
                "user_id": user_id,
                "agents_activated": len(created),
            },
        )

        return ActivationResult(activated=len(created), agents=created)

    def _plan_activations(
        self,
        classification: dict[str, Any] | None,
        facts: list[dict[str, Any]],
        integrations: list[dict[str, Any]],
        goal: dict[str, Any] | None,
        contacts: list[dict[str, Any]],
    ) -> list[AgentActivation]:
        """Determine which agents to activate and with what tasks.

        Args:
            classification: Company classification from enrichment.
            facts: Semantic facts from memory.
            integrations: Active user integrations.
            goal: User's first goal if set.
            contacts: Top contacts from stakeholder mapping / email.

        Returns:
            List of AgentActivation plans.
        """
        activations: list[AgentActivation] = []

        company_type = (classification or {}).get("company_type", "Unknown")
        connected_providers = {i.get("provider", "") for i in integrations}

        # 1. Scout: Always activate for monitoring
        competitors = [f for f in facts if f.get("metadata", {}).get("category") == "competitive"]
        activations.append(
            AgentActivation(
                agent="scout",
                task=(
                    f"Begin monitoring competitors, industry news, and "
                    f"regulatory updates for {company_type}"
                ),
                goal_title="Competitive & Market Monitoring",
                source_data={"competitor_count": len(competitors)},
            )
        )

        # 2. Analyst: Top accounts research (when contacts exist)
        if contacts:
            top_companies = list(
                {
                    c.get("metadata", {}).get("company", "")
                    for c in contacts[:10]
                    if c.get("metadata", {}).get("company")
                }
            )[:3]
            if top_companies:
                activations.append(
                    AgentActivation(
                        agent="analyst",
                        task=(
                            f"Research top accounts: {', '.join(top_companies)}. "
                            f"Produce pre-meeting briefs."
                        ),
                        goal_title="Account Research & Meeting Prep",
                        source_data={"accounts": top_companies},
                    )
                )

        # 3. Hunter: If lead gen goal
        if goal and any(
            kw in goal.get("title", "").lower()
            for kw in ["lead", "pipeline", "prospect", "territory"]
        ):
            activations.append(
                AgentActivation(
                    agent="hunter",
                    task="Begin ICP refinement and initial prospect identification",
                    goal_title="Pipeline Development",
                    source_data={"user_goal": goal.get("title", "")},
                )
            )

        # 4. Operator: If CRM connected
        if connected_providers.intersection({"salesforce", "hubspot"}):
            activations.append(
                AgentActivation(
                    agent="operator",
                    task=(
                        "Scan CRM for data quality issues, stale opportunities, "
                        "missing fields. Prepare pipeline health snapshot."
                    ),
                    goal_title="CRM Health Check",
                )
            )

        # 5. Scribe: If stale threads detected
        stale_threads = [f for f in facts if f.get("metadata", {}).get("type") == "active_deal"]
        if stale_threads:
            activations.append(
                AgentActivation(
                    agent="scribe",
                    task=(
                        f"Pre-draft follow-up emails for {len(stale_threads)} "
                        f"detected stale conversations"
                    ),
                    goal_title="Follow-up Drafts",
                    source_data={"stale_threads": len(stale_threads)},
                )
            )

        return activations

    async def _create_agent_goal(
        self,
        user_id: str,
        activation: AgentActivation,
    ) -> str | None:
        """Create a Goal with agent assignment.

        Creates the goal as ACTIVE (not DRAFT) since activation tasks
        should begin immediately. Assigns the agent via goal_agents table.

        Args:
            user_id: The user's ID.
            activation: The activation plan for this agent.

        Returns:
            Goal ID if created, None on failure.
        """
        try:
            now = datetime.now(UTC).isoformat()
            result = (
                self._db.table("goals")
                .insert(
                    {
                        "user_id": user_id,
                        "title": activation.goal_title,
                        "description": activation.task,
                        "goal_type": "custom",
                        "status": "active",
                        "started_at": now,
                        "config": {
                            "source": "onboarding_activation",
                            "agent": activation.agent,
                            "priority": activation.priority,
                            "source_data": activation.source_data,
                        },
                        "progress": 0,
                    }
                )
                .execute()
            )

            rows = cast(list[dict[str, Any]], result.data)
            goal_id: str = rows[0]["id"]

            # Create agent assignment
            self._db.table("goal_agents").insert(
                {
                    "goal_id": goal_id,
                    "agent_type": activation.agent,
                    "agent_config": {"priority": "low"},
                    "status": "pending",
                }
            ).execute()

            logger.info(
                "Activation goal created",
                extra={
                    "user_id": user_id,
                    "agent": activation.agent,
                    "goal_id": goal_id,
                },
            )

            return goal_id
        except Exception as e:
            logger.warning(
                "Failed to create activation goal",
                extra={
                    "user_id": user_id,
                    "agent": activation.agent,
                    "error": str(e),
                },
            )
            return None

    async def _record_episodic_event(
        self,
        user_id: str,
        created: list[dict[str, Any]],
    ) -> None:
        """Record activation event to episodic memory.

        Args:
            user_id: The user's ID.
            created: List of created activation records.
        """
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            memory = EpisodicMemory()
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="post_onboarding_activation",
                content=(
                    f"Post-onboarding activation: spawned {len(created)} "
                    f"agents for {len(created)} tasks"
                ),
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "agents_activated": len(created),
                    "activations": [{"agent": c["agent"], "task": c["task"]} for c in created],
                },
            )
            await memory.store_episode(episode)
        except Exception as e:
            logger.warning(
                "Episodic recording failed during activation",
                extra={"user_id": user_id, "error": str(e)},
            )

    async def _create_prospective_checkins(
        self,
        user_id: str,
        created: list[dict[str, Any]],
    ) -> None:
        """Create prospective memory check-ins for activation tasks.

        Schedules a check-in for the next day to verify agents
        have produced results for the morning briefing.

        Args:
            user_id: The user's ID.
            created: List of created activation records.
        """
        if not created:
            return

        try:
            from datetime import timedelta

            tomorrow = datetime.now(UTC) + timedelta(days=1)

            self._db.table("memory_prospective").insert(
                {
                    "user_id": user_id,
                    "task": (
                        f"Check activation results: {len(created)} agents "
                        f"were spawned post-onboarding"
                    ),
                    "due_at": tomorrow.isoformat(),
                    "status": "pending",
                    "metadata": {
                        "type": "activation_checkin",
                        "priority": "medium",
                        "agents": [c["agent"] for c in created],
                        "goal_ids": [c["goal_id"] for c in created],
                    },
                }
            ).execute()
        except Exception as e:
            logger.warning(
                "Prospective memory creation failed during activation",
                extra={"user_id": user_id, "error": str(e)},
            )

    async def _log_audit(
        self,
        user_id: str,
        created: list[dict[str, Any]],
    ) -> None:
        """Create audit log entry for activation.

        Args:
            user_id: The user's ID.
            created: List of created activation records.
        """
        try:
            from src.memory.audit import (
                MemoryOperation,
                MemoryType,
                log_memory_operation,
            )

            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.PROCEDURAL,
                memory_id=f"activation_{user_id}",
                metadata={
                    "event": "post_onboarding_activation",
                    "agents_activated": len(created),
                    "agents": [c["agent"] for c in created],
                },
                suppress_errors=True,
            )
        except Exception as e:
            logger.warning(
                "Audit log failed during activation",
                extra={"user_id": user_id, "error": str(e)},
            )

    # --- Data fetchers ---

    async def _get_classification(
        self,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Get company classification from enrichment.

        Args:
            user_id: The user's ID.

        Returns:
            Classification dict or None.
        """
        try:
            profile = (
                self._db.table("user_profiles")
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
                self._db.table("companies")
                .select("settings")
                .eq("id", profile_data["company_id"])
                .maybe_single()
                .execute()
            )
            if not company or not company.data:
                return None

            company_data = cast(dict[str, Any], company.data)
            settings = cast(dict[str, Any], company_data.get("settings", {}))
            return settings.get("classification")
        except Exception as e:
            logger.warning(
                "Failed to get classification",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _get_facts(self, user_id: str) -> list[dict[str, Any]]:
        """Get semantic facts from memory.

        Args:
            user_id: The user's ID.

        Returns:
            List of semantic fact dicts.
        """
        try:
            result = self._db.table("memory_semantic").select("*").eq("user_id", user_id).execute()
            return cast(list[dict[str, Any]], result.data or [])
        except Exception as e:
            logger.warning(
                "Failed to get facts",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def _get_integrations(self, user_id: str) -> list[dict[str, Any]]:
        """Get active user integrations.

        Args:
            user_id: The user's ID.

        Returns:
            List of active integration dicts.
        """
        try:
            result = (
                self._db.table("user_integrations")
                .select("provider, status")
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            )
            return cast(list[dict[str, Any]], result.data or [])
        except Exception as e:
            logger.warning(
                "Failed to get integrations",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def _get_first_goal(self, user_id: str) -> dict[str, Any] | None:
        """Get user's first goal set during onboarding.

        Args:
            user_id: The user's ID.

        Returns:
            Goal dict or None.
        """
        try:
            result = (
                self._db.table("goals")
                .select("title, description, goal_type")
                .eq("user_id", user_id)
                .order("created_at")
                .limit(1)
                .maybe_single()
                .execute()
            )
            if not result or not result.data:
                return None
            return cast(dict[str, Any], result.data)
        except Exception as e:
            logger.warning(
                "Failed to get first goal",
                extra={"user_id": user_id, "error": str(e)},
            )
            return None

    async def _get_top_contacts(self, user_id: str) -> list[dict[str, Any]]:
        """Get top contacts from stakeholder mapping or email analysis.

        Args:
            user_id: The user's ID.

        Returns:
            List of contact fact dicts.
        """
        try:
            result = (
                self._db.table("memory_semantic")
                .select("*")
                .eq("user_id", user_id)
                .eq("source", "stakeholder_mapping")
                .order("confidence", desc=True)
                .limit(10)
                .execute()
            )
            return cast(list[dict[str, Any]], result.data or [])
        except Exception as e:
            logger.warning(
                "Failed to get top contacts",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []
