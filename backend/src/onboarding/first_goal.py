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
from src.core.task_types import TaskType
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
        """Generate personalized goal suggestions using enrichment data and LLM.

        Gathers full user context — profile, company classification, enrichment
        facts from memory_semantic, connected integrations, and upcoming
        calendar events — then uses the LLM to produce highly specific,
        actionable goal suggestions grounded in real data.

        Args:
            user_id: The user's UUID.

        Returns:
            List of personalized goal suggestions (max 5).
        """
        try:
            # Gather all context in parallel-safe order
            context = await self._gather_suggestion_context(user_id)

            # Use LLM to generate personalized suggestions from context
            suggestions = await self._generate_llm_suggestions(context)

            if suggestions:
                logger.info(
                    "Generated LLM goal suggestions",
                    extra={"user_id": user_id, "suggestion_count": len(suggestions)},
                )
                return suggestions[:5]

            # LLM failed — fall back to defaults
            logger.warning("LLM suggestions empty, using defaults", extra={"user_id": user_id})
            return self._get_default_suggestions(user_id)

        except Exception as e:
            logger.exception(f"Failed to generate goal suggestions for {user_id}: {e}")
            return self._get_default_suggestions(user_id)

    async def _gather_suggestion_context(self, user_id: str) -> dict[str, Any]:
        """Gather all available context for goal suggestion generation.

        Fetches user profile, company data, enrichment facts, connected
        integrations, and upcoming calendar events.

        Args:
            user_id: The user's UUID.

        Returns:
            Context dict with all available data for prompt construction.
        """
        context: dict[str, Any] = {
            "user_id": user_id,
            "full_name": None,
            "title": None,
            "role": None,
            "department": None,
            "company_name": None,
            "company_type": None,
            "therapeutic_areas": [],
            "key_products": [],
            "enrichment_facts": [],
            "connected_integrations": [],
            "upcoming_meetings": [],
            "has_crm": False,
            "has_calendar": False,
        }

        # 1. User profile + company
        try:
            profile_result = (
                self._db.table("user_profiles")
                .select("full_name, title, role, department, companies(*)")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if profile_result and profile_result.data:
                profile = profile_result.data
                context["full_name"] = profile.get("full_name")
                context["title"] = profile.get("title")
                context["role"] = profile.get("role")
                context["department"] = profile.get("department")

                company = profile.get("companies")
                if company:
                    context["company_name"] = company.get("name")
                    context["key_products"] = company.get("key_products") or []
                    settings = company.get("settings") or {}
                    classification = settings.get("classification") or {}
                    context["company_type"] = classification.get("company_type")
                    context["company_description"] = classification.get("company_description", "")
                    context["primary_customers"] = classification.get("primary_customers", [])
                    context["value_chain_position"] = classification.get("value_chain_position", "")
                    context["therapeutic_areas"] = classification.get("therapeutic_areas", [])
                    context["key_products"] = (
                        classification.get("key_products", []) or context["key_products"]
                    )
        except Exception as e:
            logger.warning(f"Failed to fetch profile for suggestions: {e}")

        # 2. Enrichment facts from memory_semantic (top 15 by confidence)
        try:
            facts_result = (
                self._db.table("memory_semantic")
                .select("fact, confidence, source, metadata")
                .eq("user_id", user_id)
                .gte("confidence", 0.6)
                .order("confidence", desc=True)
                .limit(15)
                .execute()
            )
            if facts_result and facts_result.data:
                context["enrichment_facts"] = facts_result.data
        except Exception as e:
            logger.warning(f"Failed to fetch enrichment facts: {e}")

        # 3. Connected integrations
        try:
            integrations_result = (
                self._db.table("user_integrations")
                .select("integration_type, status")
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            )
            if integrations_result and integrations_result.data:
                providers = [i["integration_type"] for i in integrations_result.data]
                context["connected_integrations"] = providers
                context["has_crm"] = any(p in providers for p in ["salesforce", "hubspot"])
                context["has_calendar"] = any(p in providers for p in ["google", "outlook"])
        except Exception as e:
            logger.warning(f"Failed to fetch integrations: {e}")

        # 4. Upcoming calendar events (next 7 days)
        if context["has_calendar"]:
            try:
                now = datetime.now(UTC)
                week_ahead = now + timedelta(days=7)
                events_result = (
                    self._db.table("calendar_events")
                    .select("title, start_time, attendees, external_company")
                    .eq("user_id", user_id)
                    .gte("start_time", now.isoformat())
                    .lte("start_time", week_ahead.isoformat())
                    .order("start_time")
                    .limit(10)
                    .execute()
                )
                if events_result and events_result.data:
                    context["upcoming_meetings"] = events_result.data
            except Exception as e:
                # Table may not exist yet — not critical
                logger.debug(f"Calendar events query failed (may not exist): {e}")

        return context

    async def _generate_llm_suggestions(self, context: dict[str, Any]) -> list[GoalSuggestion]:
        """Use the LLM to generate personalized goal suggestions.

        Builds a rich prompt from all gathered context and asks the LLM
        to produce 2-3 specific, actionable suggestions.

        Args:
            context: Gathered user/company/enrichment context.

        Returns:
            List of GoalSuggestion objects from LLM output.
        """
        prompt = self._build_suggestion_prompt(context)

        # Primary: PersonaBuilder for system prompt
        system_prompt: str | None = None
        user_id = context.get("user_id", "")
        if user_id:
            try:
                from src.core.persona import PersonaRequest, get_persona_builder

                builder = get_persona_builder()
                ctx = await builder.build(PersonaRequest(
                    user_id=user_id,
                    agent_name="onboarding_goal",
                    agent_role_description=(
                        "Generating personalized goal suggestions during onboarding"
                    ),
                    task_description="Suggest 2-3 specific, actionable goals based on user context",
                    output_format="json",
                ))
                system_prompt = ctx.to_system_prompt()
            except Exception as e:
                logger.warning("PersonaBuilder unavailable, using fallback: %s", e)

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                max_tokens=1024,
                temperature=0.4,
                task=TaskType.ONBOARD_FIRST_CONVO,
            )

            result = json.loads(response)
            if not isinstance(result, list) or len(result) == 0:
                logger.warning("LLM returned non-list or empty suggestions")
                return []

            suggestions: list[GoalSuggestion] = []
            for item in result[:5]:
                if not isinstance(item, dict) or "title" not in item:
                    continue
                try:
                    suggestions.append(
                        GoalSuggestion(
                            title=item["title"],
                            description=item.get("description", ""),
                            category=GoalCategory(item.get("category", "custom")),
                            urgency=GoalUrgency(item.get("urgency", "this_week")),
                            reason=item.get("reason", ""),
                            goal_type=GoalType(item.get("goal_type", "custom")),
                        )
                    )
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping malformed suggestion: {e}")
                    continue

            return suggestions

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"LLM suggestion generation failed: {e}")
            return []

    def _build_suggestion_prompt(self, context: dict[str, Any]) -> str:
        """Build the LLM prompt for goal suggestion generation.

        Args:
            context: Gathered user/company/enrichment context.

        Returns:
            Formatted prompt string.
        """
        # User identity
        full_name = context.get("full_name") or "the user"
        title = context.get("title") or "team member"
        company_name = context.get("company_name") or "their company"
        company_type = context.get("company_type") or "life sciences company"
        company_description = context.get("company_description") or ""
        primary_customers = context.get("primary_customers") or []
        value_chain_position = context.get("value_chain_position") or ""
        role = context.get("role") or "user"
        department = context.get("department") or ""
        therapeutic_areas = context.get("therapeutic_areas") or []
        key_products = context.get("key_products") or []

        # Build enrichment facts block
        enrichment_facts = context.get("enrichment_facts") or []
        facts_block = "No enrichment data available yet."
        if enrichment_facts:
            facts_lines = []
            for f in enrichment_facts:
                confidence = f.get("confidence", 0)
                source = f.get("source", "unknown")
                facts_lines.append(
                    f"- {f['fact']} (confidence: {confidence:.0%}, source: {source})"
                )
            facts_block = "\n".join(facts_lines)

        # Connected integrations
        integrations = context.get("connected_integrations") or []
        integrations_block = ", ".join(integrations) if integrations else "none connected"

        # Upcoming meetings
        meetings = context.get("upcoming_meetings") or []
        meetings_block = "None scheduled (or calendar not connected)."
        if meetings:
            meeting_lines = []
            for m in meetings:
                event_title = m.get("title", "Untitled meeting")
                start = m.get("start_time", "")
                ext_company = m.get("external_company")
                line = f"- {event_title} on {start[:10] if start else 'TBD'}"
                if ext_company:
                    line += f" (with {ext_company})"
                meeting_lines.append(line)
            meetings_block = "\n".join(meeting_lines)

        # Therapeutic areas and products
        ta_block = ", ".join(therapeutic_areas) if therapeutic_areas else "not specified"
        products_block = ", ".join(key_products) if key_products else "not specified"

        # Category and goal_type enums for the LLM
        categories = [c.value for c in GoalCategory]
        goal_types = [g.value for g in GoalType]

        # Company context block
        customers_block = ", ".join(primary_customers) if primary_customers else "not specified"

        return f"""You are ARIA, an AI assistant for life sciences commercial teams.

The user is {full_name}, {title} at {company_name}.
{company_name} is a {company_type}.
{f"Company description: {company_description}" if company_description else ""}
{f"Primary customers: {customers_block}" if primary_customers else ""}
{f"Value chain position: {value_chain_position}" if value_chain_position else ""}
Therapeutic focus areas: {ta_block}
Key products: {products_block}
The user's role is: {role}
{f"Department: {department}" if department else ""}

Here's what I know about their company from enrichment research:
{facts_block}

Connected integrations: {integrations_block}

Upcoming meetings (next 7 days):
{meetings_block}

Generate 2-3 highly specific, actionable goal suggestions as a JSON array.
Each suggestion must be an object with these exact keys:
  "title": concise goal title (reference specific companies, products, or data points),
  "description": 1-2 sentence description of what ARIA will do,
  "category": one of {json.dumps(categories)},
  "urgency": one of {json.dumps([u.value for u in GoalUrgency])},
  "reason": 1-2 sentence explanation of why THIS goal matters for THIS person (reference specific facts),
  "goal_type": one of {json.dumps(goal_types)}

Rules:
- If there are upcoming meetings with external companies, the FIRST suggestion MUST be meeting prep for the soonest external meeting, titled "Prepare for your meeting with [company] on [date]".
- Reference specific facts about the company, competitors, products, or industry — NOT generic advice.
- Each suggestion should be immediately useful for someone in the user's role.
- The "reason" must cite specific enrichment facts or context, not generic statements.
- NEVER say "you're a [company type]" — the company is the [type], not the person.
- If CRM is connected, include a pipeline-related suggestion.
- If only email is connected (no CRM), suggest relationship or communication goals.

Respond ONLY with the JSON array, no markdown or commentary."""

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
                reason="Meeting prep is where I add the most value. "
                "I'll research attendees, companies, and topics so you're prepared.",
                goal_type=GoalType.ANALYSIS,
            ),
            GoalSuggestion(
                title="Build and qualify pipeline",
                description="Identify new prospects and qualify existing opportunities",
                category=GoalCategory.PIPELINE,
                urgency=GoalUrgency.THIS_WEEK,
                reason="Pipeline generation is foundational. I'll identify prospects "
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
                t for t in templates if any(role_lower in r.lower() for r in t.applicable_roles)
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
                task=TaskType.ONBOARD_FIRST_CONVO,
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

            # Run SMART validation before persisting (P2-25)
            original_title = title
            original_description = description
            try:
                smart_result = await self.validate_smart(title, description)
                if smart_result.score < 40 and smart_result.refined_version:
                    logger.info(
                        "SMART score below threshold, using refined version",
                        extra={
                            "user_id": user_id,
                            "original_score": smart_result.score,
                            "refined": smart_result.refined_version,
                        },
                    )
                    title = smart_result.refined_version
            except Exception as e:
                logger.warning("SMART validation failed, proceeding with original: %s", e)

            # Create the goal using GoalService
            goal_data = GoalCreate(
                title=title,
                description=description,
                goal_type=goal_type,
                config={
                    "source": "onboarding_first_goal",
                    "created_during_onboarding": True,
                    "original_title": original_title,
                    "original_description": original_description,
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
        self, user_id: str, goal_id: str, title: str, description: str | None
    ) -> None:
        """Decompose a goal into milestones via LLM and persist them.

        Calls ``_decompose_goal`` to obtain 3-5 concrete milestones, inserts
        each into the ``goal_milestones`` table, and creates a prospective
        memory check-in for the next day.

        Args:
            user_id: The user's UUID.
            goal_id: The created goal's UUID.
            title: Goal title.
            description: Goal description used for LLM decomposition.
        """
        try:
            # --- 1. Decompose goal into milestones via LLM ----------------
            milestones = await self._decompose_goal(title, description)

            # --- 2. Persist each milestone --------------------------------
            now = datetime.now(UTC)
            for i, milestone in enumerate(milestones):
                estimated_days = milestone.get("estimated_days", (i + 1) * 7)
                due_date = now + timedelta(days=int(estimated_days))

                self._db.table("goal_milestones").insert(
                    {
                        "goal_id": goal_id,
                        "title": milestone["title"],
                        "description": milestone.get("description", ""),
                        "agent_type": milestone.get("agent_type"),
                        "success_criteria": milestone.get("success_criteria"),
                        "status": "pending",
                        "sort_order": i + 1,
                        "due_date": due_date.isoformat(),
                    }
                ).execute()

            logger.info(f"Created {len(milestones)} milestones for goal {goal_id}")

            # --- 3. Prospective memory check-in (preserved behaviour) -----
            tomorrow = now + timedelta(days=1)

            self._db.table("prospective_memories").insert(
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

    async def _decompose_goal(self, title: str, description: str | None) -> list[dict[str, Any]]:
        """Use the LLM to break a goal into 3-5 actionable milestones.

        Each milestone contains:
        - ``title``: Short milestone name.
        - ``description``: What needs to happen.
        - ``agent_type``: Which ARIA agent owns the milestone
          (hunter | analyst | scout | scribe | operator | strategist).
        - ``estimated_days``: Days from now until the milestone is due.
        - ``success_criteria``: How to know the milestone is complete.

        On any LLM or parsing failure the method returns three sensible
        fallback milestones so that the caller always receives a valid list.

        Args:
            title: The goal title.
            description: Optional longer goal description.

        Returns:
            A list of 3-5 milestone dicts.
        """
        desc_block = description or "No additional description provided."

        prompt = (
            "You are ARIA, an AI Department Director for life-sciences "
            "commercial teams. A user has set the following goal:\n\n"
            f"Title: {title}\n"
            f"Description: {desc_block}\n\n"
            "Break this goal into 3-5 concrete, sequential milestones. "
            "Return ONLY a JSON array (no markdown, no commentary). "
            "Each element must be an object with exactly these keys:\n"
            '  "title": short milestone name,\n'
            '  "description": what needs to happen,\n'
            '  "agent_type": one of "hunter", "analyst", "scout", '
            '"scribe", "operator", "strategist",\n'
            '  "estimated_days": integer days from today,\n'
            '  "success_criteria": how to know this milestone is done.\n\n'
            "Choose agent_type based on the nature of the milestone:\n"
            "- hunter: pipeline generation, outreach, prospecting\n"
            "- analyst: data analysis, reporting, metrics\n"
            "- scout: market research, competitive intelligence\n"
            "- scribe: documentation, content creation, meeting notes\n"
            "- operator: process automation, integrations, scheduling\n"
            "- strategist: planning, account strategy, deal coaching\n"
        )

        try:
            raw = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
                temperature=0.3,
                task=TaskType.ONBOARD_FIRST_CONVO,
            )
            result = json.loads(raw)

            # Validate shape: must be a list of dicts with at least a title
            if (
                isinstance(result, list)
                and len(result) >= 2
                and all(isinstance(m, dict) and "title" in m for m in result)
            ):
                return result[:5]  # cap at 5

            logger.warning("LLM returned unexpected milestone structure; using fallbacks")
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Goal decomposition LLM call failed: {e}")

        # ----- Fallback milestones ----------------------------------------
        return [
            {
                "title": "Research & preparation",
                "description": f"Gather background information relevant to: {title}",
                "agent_type": "scout",
                "estimated_days": 3,
                "success_criteria": "Key data points collected and summarised",
            },
            {
                "title": "Strategy & planning",
                "description": f"Create an action plan to achieve: {title}",
                "agent_type": "strategist",
                "estimated_days": 7,
                "success_criteria": "Written plan with owners and timelines",
            },
            {
                "title": "Execute & track",
                "description": f"Carry out the plan and track progress toward: {title}",
                "agent_type": "operator",
                "estimated_days": 14,
                "success_criteria": "Measurable progress against plan milestones",
            },
        ]

    async def _record_goal_event(self, user_id: str, goal_id: str, title: str) -> None:
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
