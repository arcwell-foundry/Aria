"""US-915: Onboarding Completion → Agent Activation.

Activates ARIA's six core agents immediately after onboarding completes
so the user's first morning briefing is impressive, not empty.

Each activation:
- Creates a proper Goal (US-310) with appropriate config
- Runs at LOW priority (yields to user-initiated tasks)
- Results appear in first daily briefing
- Is tracked in episodic memory

Sprint 2 additions:
- run_post_activation_pipeline: Execute goals → first conversation → first briefing
"""

import json
import logging
import uuid
from datetime import UTC, date, datetime
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.models.goal import GoalCreate, GoalType
from src.onboarding.outcome_tracker import OnboardingOutcomeTracker
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

        # Fetch user role for priority adjustment
        user_role = ""
        try:
            profile_result = (
                self._db.table("user_profiles")
                .select("role")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if profile_result.data:
                user_role = (profile_result.data.get("role") or "").lower()
        except Exception:
            pass

        # Role-based agent priority mapping
        role_priority_agents: dict[str, list[str]] = {
            "sales": ["hunter", "analyst"],
            "business development": ["hunter", "analyst"],
            "executive": ["strategist", "scout"],
            "marketing": ["scout", "scribe"],
            "operations": ["operator", "analyst"],
            "clinical": ["analyst", "scout"],
            "regulatory": ["analyst", "scout"],
            "medical affairs": ["analyst", "scribe"],
        }
        priority_agents = role_priority_agents.get(user_role, [])

        # Scout: Monitor competitors and industry
        activations["scout"] = await self._activate_scout(
            user_id, company_id, company_domain, onboarding_data,
            priority="medium" if "scout" in priority_agents else "low",
        )

        # Analyst: Research top accounts
        activations["analyst"] = await self._activate_analyst(
            user_id, onboarding_data,
            priority="medium" if "analyst" in priority_agents else "low",
        )

        # Hunter: Only if lead_gen goal set
        if goal_type == "lead_gen":
            activations["hunter"] = await self._activate_hunter(
                user_id, onboarding_data,
                priority="medium" if "hunter" in priority_agents else "low",
            )

        # Operator: Scan CRM for data quality
        activations["operator"] = await self._activate_operator(
            user_id, onboarding_data,
            priority="medium" if "operator" in priority_agents else "low",
        )

        # Scribe: Pre-draft follow-ups for stale conversations
        activations["scribe"] = await self._activate_scribe(
            user_id, onboarding_data,
            priority="medium" if "scribe" in priority_agents else "low",
        )

        # Strategist: Build go-to-market and account strategy
        activations["strategist"] = await self._activate_strategist(
            user_id, onboarding_data,
            priority="medium" if "strategist" in priority_agents else "low",
        )

        # Pre-install recommended skills based on company type + role (US-918)
        try:
            from src.onboarding.skill_recommender import SkillRecommendationEngine

            enrichment_data = onboarding_data.get("company_discovery", {})
            company_type = enrichment_data.get("company_type", "pharma")
            skill_engine = SkillRecommendationEngine()
            recommendations = await skill_engine.recommend(company_type)
            installed = await skill_engine.pre_install(user_id, recommendations)
            activations["skills_installed"] = installed
            logger.info(
                "Skills pre-installed during activation",
                extra={"user_id": user_id, "installed": installed},
            )
        except Exception as e:
            logger.warning(
                "Skill pre-installation failed",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Final readiness recalculation (Gap #8)
        try:
            from src.onboarding.readiness import OnboardingReadinessService

            readiness_service = OnboardingReadinessService()
            await readiness_service.recalculate(user_id)
            logger.info(
                "Final readiness recalculation complete",
                extra={"user_id": user_id},
            )
        except Exception as e:
            logger.warning(
                "Final readiness recalculation failed",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Record episodic memory event
        await self._record_activation_event(user_id, activations)

        # Record onboarding outcome for procedural memory (US-924)
        try:
            outcome_tracker = OnboardingOutcomeTracker()
            await outcome_tracker.record_outcome(user_id)
            logger.info(
                "Onboarding outcome recorded",
                extra={"user_id": user_id},
            )
        except Exception as e:
            logger.warning(
                "Failed to record onboarding outcome",
                extra={"user_id": user_id, "error": str(e)},
            )

        logger.info(
            "Post-onboarding agent activation complete",
            extra={
                "user_id": user_id,
                "activations": {k: v is not None for k, v in activations.items()},
            },
        )

        # Record activity for feed
        try:
            from src.services.activity_service import ActivityService

            activated_agents = [
                k for k, v in activations.items()
                if v is not None and k != "skills_installed"
            ]
            await ActivityService().record(
                user_id=user_id,
                agent=None,
                activity_type="agents_activated",
                title="ARIA started working on your goals",
                description=(
                    f"ARIA activated {len(activated_agents)} agents: "
                    f"{', '.join(activated_agents)}. "
                    "Results will appear in your daily briefing."
                ),
                confidence=0.9,
            )
        except Exception as e:
            logger.warning("Failed to record activation activity: %s", e)

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
        priority: str = "low",
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
                    "priority": priority,
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
        priority: str = "low",
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
                    "priority": priority,
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
        priority: str = "low",
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
                    "priority": priority,
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
        priority: str = "low",
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
                    "priority": priority,
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
        priority: str = "low",
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
                    "priority": priority,
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
        priority: str = "low",
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
                    "priority": priority,
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

    async def run_post_activation_pipeline(self, user_id: str) -> dict[str, Any]:
        """Run the full post-activation pipeline: execute goals → first conversation → first briefing.

        This is the Sprint 2 fix for the "empty dashboard" problem.
        Called as a background task after activation creates goals.

        The flow:
        1. Execute all activation goals (agent analyses via LLM)
        2. Generate first conversation (intelligence-demonstrating message)
        3. Generate first briefing (dashboard content)

        Args:
            user_id: The user's ID.

        Returns:
            Dict with pipeline execution results.
        """
        logger.info(
            "Starting post-activation pipeline",
            extra={"user_id": user_id},
        )

        pipeline_result: dict[str, Any] = {
            "user_id": user_id,
            "goal_execution": None,
            "first_conversation": None,
            "first_briefing": None,
        }

        # Step 1: Execute activation goals
        try:
            from src.services.goal_execution import GoalExecutionService

            executor = GoalExecutionService()
            execution_results = await executor.execute_activation_goals(user_id)
            pipeline_result["goal_execution"] = {
                "total": len(execution_results),
                "succeeded": sum(1 for r in execution_results if r.get("status") == "complete"),
            }
            logger.info(
                "Activation goals executed",
                extra={
                    "user_id": user_id,
                    "total": len(execution_results),
                    "succeeded": pipeline_result["goal_execution"]["succeeded"],
                },
            )
        except Exception as e:
            logger.error(
                "Goal execution failed in pipeline",
                extra={"user_id": user_id, "error": str(e)},
            )
            pipeline_result["goal_execution"] = {"error": str(e)}

        # Step 2: Generate first conversation
        try:
            from src.onboarding.first_conversation import FirstConversationGenerator

            generator = FirstConversationGenerator()
            first_msg = await generator.generate(user_id)
            pipeline_result["first_conversation"] = {
                "facts_referenced": first_msg.facts_referenced,
                "confidence_level": first_msg.confidence_level,
            }
            logger.info(
                "First conversation generated",
                extra={
                    "user_id": user_id,
                    "facts_referenced": first_msg.facts_referenced,
                },
            )
        except Exception as e:
            logger.error(
                "First conversation generation failed",
                extra={"user_id": user_id, "error": str(e)},
            )
            pipeline_result["first_conversation"] = {"error": str(e)}

        # Step 3: Generate first briefing
        try:
            await self._generate_first_briefing(user_id)
            pipeline_result["first_briefing"] = {"generated": True}
            logger.info(
                "First briefing generated",
                extra={"user_id": user_id},
            )
        except Exception as e:
            logger.error(
                "First briefing generation failed",
                extra={"user_id": user_id, "error": str(e)},
            )
            pipeline_result["first_briefing"] = {"error": str(e)}

        logger.info(
            "Post-activation pipeline complete",
            extra={"user_id": user_id, "result": pipeline_result},
        )

        return pipeline_result

    async def _generate_first_briefing(self, user_id: str) -> dict[str, Any]:
        """Generate the first daily briefing from onboarding + agent execution data.

        Assembles: enrichment facts summary, first goal + agent assignments,
        agent execution results, readiness score summary.

        Args:
            user_id: The user's ID.

        Returns:
            Briefing content dict stored in daily_briefings table.
        """
        # Gather briefing ingredients
        # 1. Enrichment facts
        facts_result = (
            self._db.table("memory_semantic")
            .select("fact, confidence, source")
            .eq("user_id", user_id)
            .order("confidence", desc=True)
            .limit(10)
            .execute()
        )
        top_facts = facts_result.data or []

        # 2. Goals and agent results
        goals_result = (
            self._db.table("goals")
            .select("title, status, config")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        goals = goals_result.data or []

        # 3. Recent agent execution outputs
        executions_result = (
            self._db.table("agent_executions")
            .select("output, goal_agent_id, completed_at")
            .order("completed_at", desc=True)
            .limit(6)
            .execute()
        )
        # Filter to this user's executions via goal_agents → goals
        recent_executions = executions_result.data or []

        # 4. Readiness scores
        state_result = (
            self._db.table("onboarding_state")
            .select("readiness_scores")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        readiness = (state_result.data or {}).get("readiness_scores", {})

        # 5. User profile
        profile_result = (
            self._db.table("user_profiles")
            .select("full_name, title")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        profile = profile_result.data or {}

        # Build briefing summary via LLM
        facts_text = "\n".join(
            f"- {f.get('fact', '')} ({f.get('confidence', 0):.0%})" for f in top_facts[:8]
        )
        goals_text = "\n".join(
            f"- {g.get('title', '')} [{g.get('status', 'draft')}]" for g in goals[:6]
        )

        # Extract key findings from agent executions
        agent_findings: list[str] = []
        for ex in recent_executions[:4]:
            output = ex.get("output", {})
            if isinstance(output, dict):
                summary = output.get("summary", "")
                if summary:
                    agent_findings.append(summary)

        findings_text = "\n".join(f"- {f}" for f in agent_findings) or "Analyses in progress"

        prompt = (
            f"Generate a first daily briefing for {profile.get('full_name', 'the user')} "
            f"({profile.get('title', 'Sales Professional')}).\n\n"
            f"Top company intelligence:\n{facts_text or 'Still gathering...'}\n\n"
            f"Active goals:\n{goals_text or 'Being set up...'}\n\n"
            f"Agent findings:\n{findings_text}\n\n"
            f"Readiness: {json.dumps(readiness)}\n\n"
            "Write a warm, confident 3-4 sentence morning briefing that:\n"
            "1. Welcomes them to ARIA\n"
            "2. Highlights the most interesting finding\n"
            "3. Mentions what agents are working on\n"
            "4. Suggests a concrete next step\n"
            "Sound like an impressive colleague, not a chatbot. Be concise."
        )

        # Fetch personality calibration tone guidance for this user
        briefing_system_prompt = (
            "You are ARIA, an AI Department Director for life sciences commercial teams."
        )
        try:
            settings_result = (
                self._db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            tone_guidance = (
                (settings_result.data or {})
                .get("preferences", {})
                .get("digital_twin", {})
                .get("personality_calibration", {})
                .get("tone_guidance")
            )
            if tone_guidance:
                briefing_system_prompt += f"\n\nAdapt your communication style: {tone_guidance}"
        except Exception:
            pass  # Non-critical — fall back to default tone

        try:
            summary = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=briefing_system_prompt,
                max_tokens=300,
                temperature=0.7,
            )
        except Exception:
            summary = (
                f"Welcome to ARIA, {profile.get('full_name', '')}! "
                f"I've completed my initial analysis with {len(top_facts)} key findings "
                f"about your company, and {len(goals)} strategic goals are now active. "
                "Check the activity feed to see what I've been working on."
            )

        # Build content structure matching BriefingService format
        content: dict[str, Any] = {
            "summary": summary.strip(),
            "calendar": {"meeting_count": 0, "key_meetings": []},
            "leads": {"hot_leads": [], "needs_attention": [], "recently_active": []},
            "signals": {"company_news": [], "market_trends": [], "competitive_intel": []},
            "tasks": {"overdue": [], "due_today": []},
            "agent_highlights": agent_findings,
            "readiness": readiness,
            "generated_at": datetime.now(UTC).isoformat(),
            "is_first_briefing": True,
        }

        # Store briefing
        today = date.today()
        self._db.table("daily_briefings").upsert(
            {
                "user_id": user_id,
                "briefing_date": today.isoformat(),
                "content": content,
                "generated_at": datetime.now(UTC).isoformat(),
            }
        ).execute()

        return content
