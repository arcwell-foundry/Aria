"""First Goal Setting service for onboarding (US-910).

Helps users set their first goal, triggering agent activation. Uses onboarding
data to suggest relevant goals, provides templates by role, validates SMART
criteria, and stores goals via the existing Goal system.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation
from src.memory.episodic import Episode, EpisodicMemory
from src.models.goal import GoalCreate, GoalType
from src.services.goal_service import GoalService

logger = logging.getLogger(__name__)


class GoalCategory(str, Enum):
    """Categories of goals for templates and suggestions."""

    MEETING_PREP = "meeting_prep"
    PIPELINE = "pipeline"
    COMPETITIVE_INTEL = "competitive_intel"
    TERRITORY = "territory"
    RESEARCH = "research"
    OUTREACH = "outreach"
    CUSTOM = "custom"


class GoalUrgency(str, Enum):
    """Urgency levels for suggested goals."""

    IMMEDIATE = "immediate"
    THIS_WEEK = "this_week"
    THIS_MONTH = "this_month"
    ONGOING = "ongoing"


class GoalSuggestion(BaseModel):
    """A personalized goal suggestion for the user.

    Attributes:
        title: Goal title.
        description: Goal description.
        category: Goal category for organization.
        urgency: How urgent this goal is.
        reason: Why ARIA is suggesting this goal.
        goal_type: Mapping to GoalType enum.
    """

    title: str
    description: str
    category: GoalCategory
    urgency: GoalUrgency
    reason: str
    goal_type: GoalType


class GoalTemplate(BaseModel):
    """A pre-built goal template by role.

    Attributes:
        title: Goal title.
        description: Goal description.
        category: Goal category.
        goal_type: Mapping to GoalType enum.
        applicable_roles: List of roles this applies to.
    """

    title: str
    description: str
    category: GoalCategory
    goal_type: GoalType
    applicable_roles: list[str]


class SmartValidation(BaseModel):
    """SMART criteria validation result.

    Attributes:
        is_smart: Whether goal meets SMART criteria.
        score: SMART score (0-100).
        feedback: Specific feedback for improvement.
        refined_version: Suggested refined version if needed.
    """

    is_smart: bool
    score: float
    feedback: list[str]
    refined_version: str | None = None


class FirstGoalService:
    """Service for first goal setting during onboarding.

    Generates personalized suggestions, provides templates,
    validates SMART criteria, and creates the first goal.
    """

    # Goal templates by role
    TEMPLATES: dict[str, list[GoalTemplate]] = {
        "sales": [
            GoalTemplate(
                title="Build pipeline in target territory",
                description="Identify and qualify prospects in [territory/region] using ICP criteria",
                category=GoalCategory.PIPELINE,
                goal_type=GoalType.LEAD_GEN,
                applicable_roles=["sales", "bd"],
            ),
            GoalTemplate(
                title="Prepare for upcoming key meetings",
                description="Research and brief me on all scheduled meetings this week",
                category=GoalCategory.MEETING_PREP,
                goal_type=GoalType.ANALYSIS,
                applicable_roles=["sales", "bd", "executive"],
            ),
            GoalTemplate(
                title="Competitive intelligence for top targets",
                description="Analyze competitive positioning for my top 5 target accounts",
                category=GoalCategory.COMPETITIVE_INTEL,
                goal_type=GoalType.RESEARCH,
                applicable_roles=["sales", "bd"],
            ),
        ],
        "marketing": [
            GoalTemplate(
                title="Competitive intelligence tracking",
                description="Monitor and analyze competitor marketing activities and positioning",
                category=GoalCategory.COMPETITIVE_INTEL,
                goal_type=GoalType.RESEARCH,
                applicable_roles=["marketing", "bd"],
            ),
            GoalTemplate(
                title="Market research for campaign planning",
                description="Research [therapeutic area] market landscape for upcoming campaigns",
                category=GoalCategory.RESEARCH,
                goal_type=GoalType.ANALYSIS,
                applicable_roles=["marketing"],
            ),
        ],
        "operations": [
            GoalTemplate(
                title="Territory planning support",
                description="Analyze current territory data and prioritize account targets",
                category=GoalCategory.TERRITORY,
                goal_type=GoalType.ANALYSIS,
                applicable_roles=["operations", "sales", "bd"],
            ),
            GoalTemplate(
                title="Research operational best practices",
                description="Research industry benchmarks for [specific operational area]",
                category=GoalCategory.RESEARCH,
                goal_type=GoalType.RESEARCH,
                applicable_roles=["operations"],
            ),
        ],
        "executive": [
            GoalTemplate(
                title="Executive meeting preparation",
                description="Brief me on all upcoming executive meetings and stakeholder backgrounds",
                category=GoalCategory.MEETING_PREP,
                goal_type=GoalType.ANALYSIS,
                applicable_roles=["executive", "sales", "bd"],
            ),
            GoalTemplate(
                title="Strategic market intelligence",
                description="Provide weekly strategic briefings on market trends and opportunities",
                category=GoalCategory.COMPETITIVE_INTEL,
                goal_type=GoalType.RESEARCH,
                applicable_roles=["executive"],
            ),
        ],
    }

    def __init__(self) -> None:
        """Initialize service with database and LLM clients."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._goal_service = GoalService()

    async def suggest_goals(self, user_id: str) -> list[GoalSuggestion]:
        """Generate personalized goal suggestions from onboarding data.

        Analyzes:
        - Company enrichment classification
        - User role and profile
        - Connected integrations (calendar events, CRM pipeline)
        - Recent activities

        Args:
            user_id: The user's UUID.

        Returns:
            List of personalized goal suggestions.
        """
        suggestions: list[GoalSuggestion] = []
        try:
            # Get user profile and company data
            profile_result = (
                self._db.table("user_profiles")
                .select("*, companies(*)")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )

            profile = profile_result.data if profile_result and profile_result.data else None
            company = profile.get("companies") if profile else None

            # Get onboarding state for enrichment data
            state_result = (
                self._db.table("onboarding_state")
                .select("step_data, readiness_scores, metadata")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            step_data = (
                state_result.data.get("step_data") if state_result and state_result.data else {}
            )
            metadata = (
                state_result.data.get("metadata") if state_result and state_result.data else {}
            )

            # Check for calendar integration and upcoming meetings
            calendar_suggestions = await self._suggest_from_calendar(user_id, step_data)
            suggestions.extend(calendar_suggestions)

            # Check for CRM integration and pipeline suggestions
            crm_suggestions = await self._suggest_from_crm(user_id, step_data)
            suggestions.extend(crm_suggestions)

            # Get suggestions based on company classification
            if company:
                company_suggestions = await self._suggest_from_company(
                    user_id, company, step_data, metadata
                )
                suggestions.extend(company_suggestions)

            # Get suggestions based on user role
            if profile and profile.get("role"):
                role_suggestions = await self._suggest_from_role(
                    user_id, profile["role"], step_data
                )
                suggestions.extend(role_suggestions)

            # If no personalized suggestions, add defaults
            if not suggestions:
                suggestions.extend(self._get_default_suggestions(user_id))

            # Limit to top 5 suggestions
            suggestions = suggestions[:5]

            logger.info(
                "Generated goal suggestions",
                extra={"user_id": user_id, "suggestion_count": len(suggestions)},
            )

            return suggestions

        except Exception as e:
            logger.exception(f"Failed to generate goal suggestions for {user_id}: {e}")
            return self._get_default_suggestions(user_id)

    async def _suggest_from_calendar(
        self, user_id: str, _step_data: dict[str, Any]
    ) -> list[GoalSuggestion]:
        """Generate suggestions from connected calendar data.

        Args:
            user_id: The user's UUID.
            _step_data: Onboarding step data (unused, reserved for future).

        Returns:
            List of calendar-based goal suggestions.
        """
        suggestions: list[GoalSuggestion] = []

        try:
            # Check integration status for calendars
            integration_result = (
                self._db.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("provider", "google")  # or outlook
                .eq("status", "active")
                .execute()
            )

            has_calendar = bool(integration_result.data) if integration_result else False

            if not has_calendar:
                return []

            # Check for upcoming meetings in next 7 days
            # For now, suggest meeting prep as a default
            suggestions.append(
                GoalSuggestion(
                    title="Prepare for upcoming meetings",
                    description="Research and create briefing documents for your scheduled meetings",
                    category=GoalCategory.MEETING_PREP,
                    urgency=GoalUrgency.THIS_WEEK,
                    reason="I see you have calendar connected. I can prepare briefings for your "
                    "upcoming meetings so you walk in prepared.",
                    goal_type=GoalType.ANALYSIS,
                )
            )

        except Exception as e:
            logger.warning(f"Failed to suggest from calendar: {e}")

        return suggestions

    async def _suggest_from_crm(
        self, user_id: str, _step_data: dict[str, Any]
    ) -> list[GoalSuggestion]:
        """Generate suggestions from connected CRM data.

        Args:
            user_id: The user's UUID.
            _step_data: Onboarding step data (unused, reserved for future).

        Returns:
            List of CRM-based goal suggestions.
        """
        suggestions: list[GoalSuggestion] = []

        try:
            # Check integration status for CRM
            integration_result = (
                self._db.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .in_("provider", ["salesforce", "hubspot"])
                .eq("status", "active")
                .execute()
            )

            has_crm = bool(integration_result.data) if integration_result else False

            if not has_crm:
                return []

            # Suggest pipeline-focused goal
            suggestions.append(
                GoalSuggestion(
                    title="Build and qualify pipeline",
                    description="Identify new prospects and qualify existing opportunities in your CRM",
                    category=GoalCategory.PIPELINE,
                    urgency=GoalUrgency.THIS_WEEK,
                    reason="I see you have CRM connected. I can help identify high-potential prospects "
                    "and qualify your existing pipeline.",
                    goal_type=GoalType.LEAD_GEN,
                )
            )

        except Exception as e:
            logger.warning(f"Failed to suggest from CRM: {e}")

        return suggestions

    async def _suggest_from_company(
        self,
        _user_id: str,
        company: dict[str, Any],
        _step_data: dict[str, Any],
        _metadata: dict[str, Any],
    ) -> list[GoalSuggestion]:
        """Generate suggestions based on company classification.

        Args:
            _user_id: The user's UUID (unused, reserved for future).
            company: Company data.
            _step_data: Onboarding step data (unused, reserved for future).
            _metadata: Onboarding metadata (unused, reserved for future).

        Returns:
            List of company-based goal suggestions.
        """
        suggestions: list[GoalSuggestion] = []

        try:
            settings = company.get("settings", {})
            classification = settings.get("classification", {})
            company_type = classification.get("company_type", "Unknown")

            # CDMO/CRO focus on competitive positioning
            if company_type in ["CDMO", "CRO"]:
                suggestions.append(
                    GoalSuggestion(
                        title="Competitive positioning analysis",
                        description="Analyze our competitive positioning in key therapeutic areas",
                        category=GoalCategory.COMPETITIVE_INTEL,
                        urgency=GoalUrgency.THIS_MONTH,
                        reason=f"Given that you're a {company_type}, understanding competitive "
                        "positioning is crucial for client conversations.",
                        goal_type=GoalType.RESEARCH,
                    )
                )

            # Biotech/Pharma focus on pipeline and territory
            elif company_type in ["Biotech", "Large Pharma"]:
                suggestions.append(
                    GoalSuggestion(
                        title="Territory planning and account prioritization",
                        description="Analyze and prioritize target accounts in your territory",
                        category=GoalCategory.TERRITORY,
                        urgency=GoalUrgency.THIS_WEEK,
                        reason=f"For a {company_type}, strategic territory planning drives pipeline "
                        "quality and win rates.",
                        goal_type=GoalType.ANALYSIS,
                    )
                )

        except Exception as e:
            logger.warning(f"Failed to suggest from company: {e}")

        return suggestions

    async def _suggest_from_role(
        self, _user_id: str, role: str, _step_data: dict[str, Any]
    ) -> list[GoalSuggestion]:
        """Generate suggestions based on user role.

        Args:
            _user_id: The user's UUID (unused, reserved for future).
            role: User's role.
            _step_data: Onboarding step data (unused, reserved for future).

        Returns:
            List of role-based goal suggestions.
        """
        suggestions: list[GoalSuggestion] = []
        role_lower = role.lower()

        try:
            # Get applicable templates for this role
            applicable_templates: list[GoalTemplate] = []
            for category_templates in self.TEMPLATES.values():
                for template in category_templates:
                    if any(role_lower in r.lower() for r in template.applicable_roles):
                        applicable_templates.append(template)

            # Convert templates to suggestions
            for template in applicable_templates[:2]:  # Max 2 per role
                suggestions.append(
                    GoalSuggestion(
                        title=template.title,
                        description=template.description,
                        category=template.category,
                        urgency=GoalUrgency.THIS_WEEK,
                        reason=f"As a {role}, this is a high-impact goal I can help you achieve.",
                        goal_type=template.goal_type,
                    )
                )

        except Exception as e:
            logger.warning(f"Failed to suggest from role: {e}")

        return suggestions

    def _get_default_suggestions(self, _user_id: str) -> list[GoalSuggestion]:
        """Get default suggestions when no personalized data available.

        Args:
            _user_id: The user's UUID (unused, reserved for future).

        Returns:
            List of default goal suggestions.
        """
        return [
            GoalSuggestion(
                title="Prepare for upcoming meetings",
                description="Research and create briefing documents for your scheduled meetings",
                category=GoalCategory.MEETING_PREP,
                urgency=GoalUrgency.THIS_WEEK,
                reason="Meeting prep is one of the highest-value activities I can help with. "
                "I'll research attendees, companies, and topics so you're prepared.",
                goal_type=GoalType.ANALYSIS,
            ),
            GoalSuggestion(
                title="Build and qualify pipeline",
                description="Identify new prospects and qualify existing opportunities",
                category=GoalCategory.PIPELINE,
                urgency=GoalUrgency.THIS_WEEK,
                reason="Pipeline generation is foundational. I can help identify prospects "
                "that match your ICP and qualify existing opportunities.",
                goal_type=GoalType.LEAD_GEN,
            ),
            GoalSuggestion(
                title="Competitive intelligence",
                description="Monitor and analyze competitor activities and positioning",
                category=GoalCategory.COMPETITIVE_INTEL,
                urgency=GoalUrgency.THIS_MONTH,
                reason="Staying informed about competitive movements helps you position "
                "more effectively and anticipate market changes.",
                goal_type=GoalType.RESEARCH,
            ),
        ]

    def get_goal_templates(self, role: str | None = None) -> dict[str, list[GoalTemplate]]:
        """Get goal templates, optionally filtered by role.

        Args:
            role: Optional role to filter templates by.

        Returns:
            Dictionary of goal templates by category.
        """
        if not role:
            return self.TEMPLATES

        role_lower = role.lower()
        filtered: dict[str, list[GoalTemplate]] = {}

        for category, templates in self.TEMPLATES.items():
            applicable = [
                t
                for t in templates
                if any(role_lower in r.lower() for r in t.applicable_roles)
            ]
            if applicable:
                filtered[category] = applicable

        return filtered

    async def validate_smart(self, title: str, description: str | None = None) -> SmartValidation:
        """Validate goal against SMART criteria using LLM.

        SMART: Specific, Measurable, Achievable, Relevant, Time-bound.

        Args:
            title: Goal title to validate.
            description: Optional goal description.

        Returns:
            SMART validation result with score and feedback.
        """
        goal_text = f"{title}. {description or ''}"

        prompt = f"""Evaluate this goal against SMART criteria:

Goal: {goal_text}

SMART Criteria:
- Specific: Is the goal clear and well-defined?
- Measurable: Can progress and success be measured?
- Achievable: Is the goal realistic given resources?
- Relevant: Does the goal align with business objectives?
- Time-bound: Is there a clear timeline or deadline?

Provide a JSON response:
{{
    "is_smart": true/false,
    "score": 0-100 (how SMART is this goal?),
    "feedback": [
        "Specific feedback on each criterion if missing",
        "more feedback items as needed"
    ],
    "refined_version": "A SMART version of the goal if original needs work (null if already SMART)"
}}

Be constructive and specific. If the goal is vague, suggest a specific, measurable version.
Respond ONLY with the JSON object."""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.3,
            )

            result = json.loads(response)
            return SmartValidation(**result)

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"SMART validation parse failed: {e}")
            return SmartValidation(
                is_smart=False,
                score=50.0,
                feedback=["Unable to validate automatically. Please ensure your goal is specific."],
                refined_version=None,
            )

    async def create_first_goal(
        self,
        user_id: str,
        title: str,
        description: str | None = None,
        goal_type: GoalType = GoalType.CUSTOM,
    ) -> dict[str, Any]:
        """Create the first goal and trigger agent assignments.

        Args:
            user_id: The user's UUID.
            title: Goal title.
            description: Optional goal description.
            goal_type: Type of goal (defaults to CUSTOM).

        Returns:
            Created goal data with agent assignments.

        Raises:
            Exception: If goal creation fails.
        """
        try:
            logger.info(
                "Creating first goal",
                extra={"user_id": user_id, "title": title, "goal_type": goal_type.value},
            )

            # Create the goal using GoalService
            goal_data = GoalCreate(
                title=title,
                description=description,
                goal_type=goal_type,
                config={
                    "source": "onboarding_first_goal",
                    "created_during_onboarding": True,
                },
            )

            goal = await self._goal_service.create_goal(user_id, goal_data)

            goal_id = goal["id"]
            logger.info(f"Goal created: {goal_id}")

            # Assign agents based on goal type
            await self._assign_agents_to_goal(user_id, goal_id, goal_type)

            # Update goal_clarity readiness score
            await self._update_readiness_score(user_id)

            # Create prospective memory for goal follow-up
            await self._create_goal_milestones(user_id, goal_id, title, description)

            # Record episodic memory
            await self._record_goal_event(user_id, goal_id, title)

            # Audit log
            await log_memory_operation(
                user_id=user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.PROCEDURAL,  # Goals are procedural memory
                memory_id=f"goal_{goal_id}",
                metadata={
                    "title": title,
                    "goal_type": goal_type.value,
                    "created_during_onboarding": True,
                },
                suppress_errors=True,
            )

            return {
                "goal": goal,
                "status": "created",
                "message": "First goal created successfully",
            }

        except Exception as e:
            logger.exception(f"Failed to create first goal: {e}")
            raise

    async def _assign_agents_to_goal(
        self, _user_id: str, goal_id: str, goal_type: GoalType
    ) -> None:
        """Assign appropriate agents to the goal.

        Args:
            _user_id: The user's UUID (unused, reserved for future).
            goal_id: The created goal's UUID.
            goal_type: The type of goal to determine agent assignments.
        """
        # Agent type mapping based on goal type
        agent_assignments: dict[GoalType, list[str]] = {
            GoalType.LEAD_GEN: ["hunter", "analyst"],
            GoalType.RESEARCH: ["analyst", "scout"],
            GoalType.OUTREACH: ["scribe", "hunter"],
            GoalType.ANALYSIS: ["analyst"],
            GoalType.CUSTOM: ["analyst", "scribe"],
        }

        agents = agent_assignments.get(goal_type, ["analyst"])

        # Create agent assignments in goal_agents table
        for agent_type in agents:
            try:
                self._db.table("goal_agents").insert(
                    {
                        "goal_id": goal_id,
                        "agent_type": agent_type,
                        "agent_config": {
                            "priority": "low",  # First goals start low priority
                            "auto_execute": False,  # Require user confirmation first
                        },
                        "status": "pending",
                    }
                ).execute()
                logger.info(f"Assigned {agent_type} to goal {goal_id}")

            except Exception as e:
                logger.warning(f"Failed to assign agent {agent_type}: {e}")

    async def _update_readiness_score(self, user_id: str) -> None:
        """Update goal_clarity readiness sub-score.

        Setting first goal contributes 30 points to goal_clarity.

        Args:
            user_id: The user's UUID.
        """
        try:
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            await orch.update_readiness_scores(user_id, {"goal_clarity": 30.0})

        except Exception as e:
            logger.warning(f"Failed to update readiness score: {e}")

    async def _create_goal_milestones(
        self, user_id: str, goal_id: str, title: str, _description: str | None
    ) -> None:
        """Create prospective memory entries for goal milestones.

        Args:
            user_id: The user's UUID.
            goal_id: The created goal's UUID.
            title: Goal title.
            _description: Goal description (unused, reserved for future).
        """
        try:
            # Create a check-in task for tomorrow
            tomorrow = datetime.now(UTC) + timedelta(days=1)

            self._db.table("memory_prospective").insert(
                {
                    "user_id": user_id,
                    "task": f"Review progress on goal: {title}",
                    "due_date": tomorrow.isoformat(),
                    "status": "pending",
                    "metadata": {
                        "type": "goal_check_in",
                        "goal_id": goal_id,
                        "priority": "low",
                    },
                }
            ).execute()

            logger.info(f"Created milestone check-in for goal {goal_id}")

        except Exception as e:
            logger.warning(f"Failed to create goal milestones: {e}")

    async def _record_goal_event(
        self, user_id: str, goal_id: str, title: str
    ) -> None:
        """Record goal creation in episodic memory.

        Args:
            user_id: The user's UUID.
            goal_id: The created goal's UUID.
            title: Goal title.
        """
        try:
            memory = EpisodicMemory()
            now = datetime.now(UTC)

            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="onboarding_first_goal_set",
                content=f"User set their first goal: {title}",
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "goal_id": goal_id,
                    "goal_title": title,
                    "onboarding_step": "first_goal",
                },
            )

            await memory.store_episode(episode)

        except Exception as e:
            logger.warning(f"Failed to record episodic event: {e}")
