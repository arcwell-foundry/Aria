"""Goal Execution Service — runs agent analyses for activation goals.

This is the missing link between activation (which creates goals) and the
dashboard (which displays results). For beta, execution is synchronous:
each agent runs a focused LLM analysis, stores the result, and moves on.

Agent types and their analyses:
- Scout: Competitive landscape summary (top competitors, recent news, market signals)
- Analyst: Account analysis (company profile, key stakeholders, opportunities)
- Hunter: Prospect identification (3-5 companies matching user's ICP)
- Strategist: Strategic recommendations synthesis
- Scribe: Follow-up email or talking points draft
- Operator: Data quality report (what ARIA knows vs gaps)
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)


class GoalExecutionService:
    """Executes agent goals by running LLM-powered analyses.

    For beta this is synchronous — each agent runs its analysis via
    a single LLM call, stores the result, and moves to the next.
    """

    def __init__(self) -> None:
        """Initialize with database, LLM, and activity service."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._activity = ActivityService()

    async def execute_goal(self, goal_id: str, user_id: str) -> dict[str, Any]:
        """Execute a single goal by running all assigned agents.

        Args:
            goal_id: The goal to execute.
            user_id: The user who owns this goal.

        Returns:
            Dict with goal_id, status, and list of agent results.
        """
        logger.info(
            "Starting goal execution",
            extra={"goal_id": goal_id, "user_id": user_id},
        )

        # Fetch the goal
        goal_result = (
            self._db.table("goals")
            .select("*, goal_agents(*)")
            .eq("id", goal_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not goal_result.data:
            logger.warning("Goal not found", extra={"goal_id": goal_id})
            return {"goal_id": goal_id, "status": "not_found", "results": []}

        goal = goal_result.data

        # Update goal status to active
        now = datetime.now(UTC).isoformat()
        self._db.table("goals").update(
            {"status": "active", "started_at": now, "updated_at": now}
        ).eq("id", goal_id).execute()

        # Gather context for agent execution
        context = await self._gather_execution_context(user_id)

        # Execute each assigned agent
        agent_type = goal.get("config", {}).get("agent_type", "")
        results: list[dict[str, Any]] = []

        if agent_type:
            # Single agent goal (activation goals have one agent_type in config)
            result = await self._execute_agent(
                user_id=user_id,
                goal=goal,
                agent_type=agent_type,
                context=context,
            )
            results.append(result)
        else:
            # Multi-agent goal: run each assigned agent
            for agent in goal.get("goal_agents", []):
                result = await self._execute_agent(
                    user_id=user_id,
                    goal=goal,
                    agent_type=agent.get("agent_type", ""),
                    context=context,
                    goal_agent_id=agent.get("id"),
                )
                results.append(result)

        # Update goal status to complete
        now = datetime.now(UTC).isoformat()
        self._db.table("goals").update(
            {
                "status": "complete",
                "progress": 100,
                "completed_at": now,
                "updated_at": now,
            }
        ).eq("id", goal_id).execute()

        logger.info(
            "Goal execution complete",
            extra={
                "goal_id": goal_id,
                "user_id": user_id,
                "agent_count": len(results),
                "success_count": sum(1 for r in results if r.get("success")),
            },
        )

        return {
            "goal_id": goal_id,
            "status": "complete",
            "results": results,
        }

    async def execute_activation_goals(self, user_id: str) -> list[dict[str, Any]]:
        """Execute all activation goals for a user.

        Queries for goals with config.source = 'onboarding_activation'
        and executes each one.

        Args:
            user_id: The user whose activation goals to execute.

        Returns:
            List of execution result dicts.
        """
        logger.info(
            "Executing activation goals",
            extra={"user_id": user_id},
        )

        # Query activation goals
        goals_result = (
            self._db.table("goals")
            .select("id, title, config")
            .eq("user_id", user_id)
            .eq("status", "draft")
            .execute()
        )

        activation_goals = [
            g
            for g in (goals_result.data or [])
            if g.get("config", {}).get("source") == "onboarding_activation"
        ]

        if not activation_goals:
            logger.info("No activation goals found", extra={"user_id": user_id})
            return []

        all_results: list[dict[str, Any]] = []

        for goal in activation_goals:
            try:
                result = await self.execute_goal(goal["id"], user_id)
                all_results.append(result)
            except Exception as e:
                logger.error(
                    "Failed to execute activation goal",
                    extra={
                        "goal_id": goal["id"],
                        "user_id": user_id,
                        "error": str(e),
                    },
                )
                all_results.append(
                    {
                        "goal_id": goal["id"],
                        "status": "failed",
                        "error": str(e),
                        "results": [],
                    }
                )

        logger.info(
            "Activation goals execution complete",
            extra={
                "user_id": user_id,
                "total": len(all_results),
                "succeeded": sum(1 for r in all_results if r.get("status") == "complete"),
            },
        )

        return all_results

    async def _execute_agent(
        self,
        user_id: str,
        goal: dict[str, Any],
        agent_type: str,
        context: dict[str, Any],
        goal_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a single agent's analysis.

        Args:
            user_id: The user's ID.
            goal: The goal dict with title, description, config.
            agent_type: The agent type (scout, analyst, hunter, etc.).
            context: Gathered execution context (enrichment data, facts, etc.).
            goal_agent_id: Optional goal_agent row ID for execution tracking.

        Returns:
            Dict with agent_type, success, and content.
        """
        logger.info(
            "Executing agent analysis",
            extra={
                "user_id": user_id,
                "agent_type": agent_type,
                "goal_title": goal.get("title"),
            },
        )

        # Build agent-specific prompt
        prompt_builder = {
            "scout": self._build_scout_prompt,
            "analyst": self._build_analyst_prompt,
            "hunter": self._build_hunter_prompt,
            "strategist": self._build_strategist_prompt,
            "scribe": self._build_scribe_prompt,
            "operator": self._build_operator_prompt,
        }

        builder = prompt_builder.get(agent_type)
        if not builder:
            logger.warning(f"Unknown agent type: {agent_type}")
            return {"agent_type": agent_type, "success": False, "error": "Unknown agent type"}

        prompt = builder(goal, context)

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are ARIA, an AI Department Director for life sciences "
                    "commercial teams. You are performing an initial analysis based "
                    "on onboarding data. Be specific, actionable, and concise. "
                    "Respond with a JSON object only."
                ),
                max_tokens=2048,
                temperature=0.4,
            )

            # Parse the JSON response
            try:
                content = json.loads(response)
            except json.JSONDecodeError:
                content = {"raw_analysis": response.strip()}

            # Store execution result
            await self._store_execution(
                user_id=user_id,
                goal_id=goal["id"],
                agent_type=agent_type,
                content=content,
                goal_agent_id=goal_agent_id,
            )

            # Record activity
            await self._activity.record(
                user_id=user_id,
                agent=agent_type,
                activity_type="analysis_complete",
                title=f"{agent_type.title()} completed initial analysis",
                description=content.get(
                    "summary", f"{agent_type.title()} analysis for: {goal.get('title', '')}"
                ),
                confidence=0.8,
                related_entity_type="goal",
                related_entity_id=goal["id"],
            )

            return {
                "agent_type": agent_type,
                "success": True,
                "content": content,
            }

        except Exception as e:
            logger.error(
                "Agent execution failed",
                extra={
                    "agent_type": agent_type,
                    "user_id": user_id,
                    "error": str(e),
                },
            )
            return {
                "agent_type": agent_type,
                "success": False,
                "error": str(e),
            }

    async def _store_execution(
        self,
        user_id: str,  # noqa: ARG002
        goal_id: str,
        agent_type: str,
        content: dict[str, Any],
        goal_agent_id: str | None = None,
    ) -> None:
        """Store agent execution result in agent_executions table.

        Args:
            user_id: The user's ID (for future audit trail use).
            goal_id: The goal ID.
            agent_type: The agent type.
            content: The execution output.
            goal_agent_id: Optional goal_agent row ID.
        """
        now = datetime.now(UTC).isoformat()

        # If no goal_agent_id, find or create one
        if not goal_agent_id:
            agent_result = (
                self._db.table("goal_agents")
                .select("id")
                .eq("goal_id", goal_id)
                .eq("agent_type", agent_type)
                .maybe_single()
                .execute()
            )
            if agent_result.data:
                goal_agent_id = agent_result.data["id"]
            else:
                # Create a goal_agents record
                insert_result = (
                    self._db.table("goal_agents")
                    .insert(
                        {
                            "goal_id": goal_id,
                            "agent_type": agent_type,
                            "agent_config": {"source": "goal_execution"},
                            "status": "complete",
                        }
                    )
                    .execute()
                )
                if insert_result.data:
                    goal_agent_id = insert_result.data[0]["id"]

        if goal_agent_id:
            # Store in agent_executions table
            self._db.table("agent_executions").insert(
                {
                    "goal_agent_id": goal_agent_id,
                    "input": {"goal_id": goal_id, "agent_type": agent_type},
                    "output": content,
                    "status": "complete",
                    "tokens_used": 0,
                    "started_at": now,
                    "completed_at": now,
                }
            ).execute()

            # Update goal_agent status
            self._db.table("goal_agents").update({"status": "complete"}).eq(
                "id", goal_agent_id
            ).execute()

        logger.info(
            "Execution stored",
            extra={
                "goal_id": goal_id,
                "agent_type": agent_type,
                "goal_agent_id": goal_agent_id,
            },
        )

    async def _gather_execution_context(self, user_id: str) -> dict[str, Any]:
        """Gather context needed for agent execution.

        Pulls enrichment data, semantic facts, user profile, company info,
        and first goal to give agents context for their analyses.

        Args:
            user_id: The user's ID.

        Returns:
            Context dict with all gathered data.
        """
        # Get user profile
        profile_result = (
            self._db.table("user_profiles").select("*").eq("id", user_id).maybe_single().execute()
        )
        profile = profile_result.data or {}

        # Get company info
        company: dict[str, Any] = {}
        if profile.get("company_id"):
            company_result = (
                self._db.table("companies")
                .select("*")
                .eq("id", profile["company_id"])
                .maybe_single()
                .execute()
            )
            company = company_result.data or {}

        # Get top semantic facts
        facts_result = (
            self._db.table("memory_semantic")
            .select("fact, confidence, source, metadata")
            .eq("user_id", user_id)
            .order("confidence", desc=True)
            .limit(30)
            .execute()
        )
        facts = facts_result.data or []

        # Get knowledge gaps
        gaps_result = (
            self._db.table("prospective_memories")
            .select("task, metadata")
            .eq("user_id", user_id)
            .execute()
        )
        gaps = [
            g
            for g in (gaps_result.data or [])
            if g.get("metadata", {}).get("type") == "knowledge_gap"
        ]

        # Get readiness scores
        state_result = (
            self._db.table("onboarding_state")
            .select("readiness_scores")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        readiness = (state_result.data or {}).get("readiness_scores", {})

        # Build enrichment summary from facts
        fact_texts = [f.get("fact", "") for f in facts[:20]]

        return {
            "profile": profile,
            "company": company,
            "company_name": company.get("name", "the company"),
            "company_domain": company.get("domain", ""),
            "classification": company.get("settings", {}).get("classification", {}),
            "facts": fact_texts,
            "facts_full": facts,
            "gaps": [g.get("task", "") for g in gaps[:5]],
            "readiness": readiness,
        }

    # --- Prompt Builders ---

    def _build_scout_prompt(self, goal: dict[str, Any], ctx: dict[str, Any]) -> str:
        """Build Scout agent prompt for competitive landscape analysis."""
        competitors = goal.get("config", {}).get("entities", [])
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:15])

        return (
            f"Analyze the competitive landscape for {ctx['company_name']}.\n\n"
            f"Company domain: {ctx['company_domain']}\n"
            f"Classification: {json.dumps(ctx['classification'])}\n"
            f"Known competitors/entities: {', '.join(str(c) for c in competitors) or 'None identified yet'}\n"
            f"Key facts:\n{facts or 'Limited data available'}\n\n"
            "Produce a competitive landscape analysis. Respond with JSON:\n"
            "{\n"
            '  "summary": "2-3 sentence overview",\n'
            '  "competitors": [\n'
            '    {"name": "...", "relationship": "direct|indirect|adjacent", "key_differentiator": "..."}\n'
            "  ],\n"
            '  "market_signals": ["signal 1", "signal 2"],\n'
            '  "opportunities": ["opportunity based on competitive gaps"],\n'
            '  "watch_items": ["things to monitor"]\n'
            "}"
        )

    def _build_analyst_prompt(
        self,
        goal: dict[str, Any],  # noqa: ARG002
        ctx: dict[str, Any],
    ) -> str:
        """Build Analyst agent prompt for account analysis."""
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:15])

        return (
            f"Perform an account analysis for {ctx['company_name']}.\n\n"
            f"Company domain: {ctx['company_domain']}\n"
            f"Classification: {json.dumps(ctx['classification'])}\n"
            f"User role: {ctx['profile'].get('title', 'Unknown')}\n"
            f"Key facts:\n{facts or 'Limited data available'}\n\n"
            "Produce an account analysis. Respond with JSON:\n"
            "{\n"
            '  "summary": "2-3 sentence company profile",\n'
            '  "key_stakeholders": [\n'
            '    {"role": "...", "importance": "high|medium|low", "approach": "..."}\n'
            "  ],\n"
            '  "opportunities": ["concrete opportunity 1"],\n'
            '  "risks": ["risk or challenge"],\n'
            '  "recommended_actions": ["specific next step"]\n'
            "}"
        )

    def _build_hunter_prompt(self, goal: dict[str, Any], ctx: dict[str, Any]) -> str:
        """Build Hunter agent prompt for prospect identification."""
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:10])
        icp_description = goal.get("config", {}).get("icp_refinement", "")

        return (
            f"Identify potential prospect companies for {ctx['company_name']}.\n\n"
            f"Company domain: {ctx['company_domain']}\n"
            f"Classification: {json.dumps(ctx['classification'])}\n"
            f"ICP context: {icp_description}\n"
            f"Key facts:\n{facts or 'Limited data available'}\n\n"
            "Identify 3-5 types of prospect companies that would match the user's "
            "ideal customer profile based on what we know. Respond with JSON:\n"
            "{\n"
            '  "summary": "ICP analysis summary",\n'
            '  "icp_characteristics": ["characteristic 1", "characteristic 2"],\n'
            '  "prospect_profiles": [\n'
            '    {"company_type": "...", "why_good_fit": "...", "approach_strategy": "..."}\n'
            "  ],\n"
            '  "search_criteria": ["criteria for finding prospects"],\n'
            '  "next_steps": ["action to refine targeting"]\n'
            "}"
        )

    def _build_strategist_prompt(
        self,
        goal: dict[str, Any],  # noqa: ARG002
        ctx: dict[str, Any],
    ) -> str:
        """Build Strategist agent prompt for strategic recommendations."""
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:15])
        gaps = "\n".join(f"- {g}" for g in ctx["gaps"][:5])

        return (
            f"Synthesize strategic recommendations for {ctx['company_name']}.\n\n"
            f"Company domain: {ctx['company_domain']}\n"
            f"Classification: {json.dumps(ctx['classification'])}\n"
            f"User role: {ctx['profile'].get('title', 'Unknown')}\n"
            f"Key facts:\n{facts or 'Limited data available'}\n"
            f"Knowledge gaps:\n{gaps or 'None identified'}\n"
            f"Readiness scores: {json.dumps(ctx['readiness'])}\n\n"
            "Produce strategic recommendations. Respond with JSON:\n"
            "{\n"
            '  "summary": "Strategic assessment overview",\n'
            '  "market_position": "assessment of current position",\n'
            '  "strategic_priorities": [\n'
            '    {"priority": "...", "rationale": "...", "timeline": "short|medium|long"}\n'
            "  ],\n"
            '  "quick_wins": ["actionable item achievable this week"],\n'
            '  "key_risks": ["strategic risk to address"],\n'
            '  "recommended_focus": "top recommendation for this quarter"\n'
            "}"
        )

    def _build_scribe_prompt(
        self,
        goal: dict[str, Any],  # noqa: ARG002
        ctx: dict[str, Any],
    ) -> str:
        """Build Scribe agent prompt for follow-up draft."""
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:10])

        return (
            f"Draft initial talking points for {ctx['company_name']}.\n\n"
            f"User: {ctx['profile'].get('full_name', 'the user')}, "
            f"{ctx['profile'].get('title', 'Sales Professional')}\n"
            f"Company: {ctx['company_name']}\n"
            f"Key facts:\n{facts or 'Limited data available'}\n\n"
            "Produce talking points and a sample email draft that the user "
            "could use for outreach. Respond with JSON:\n"
            "{\n"
            '  "summary": "What these talking points cover",\n'
            '  "talking_points": ["point 1", "point 2", "point 3"],\n'
            '  "email_draft": {\n'
            '    "subject": "...",\n'
            '    "body": "..."\n'
            "  },\n"
            '  "tone_notes": "guidance on delivery",\n'
            '  "personalization_hooks": ["detail to reference in conversation"]\n'
            "}"
        )

    def _build_operator_prompt(
        self,
        goal: dict[str, Any],  # noqa: ARG002
        ctx: dict[str, Any],
    ) -> str:
        """Build Operator agent prompt for data quality report."""
        facts = "\n".join(f"- {f}" for f in ctx["facts"][:15])
        gaps = "\n".join(f"- {g}" for g in ctx["gaps"][:5])

        return (
            f"Generate a data quality report for {ctx['company_name']}.\n\n"
            f"Current data:\n{facts or 'No facts available'}\n"
            f"Known gaps:\n{gaps or 'No gaps identified'}\n"
            f"Readiness scores: {json.dumps(ctx['readiness'])}\n"
            f"Total facts available: {len(ctx.get('facts_full', []))}\n\n"
            "Assess what ARIA knows vs what's missing. Respond with JSON:\n"
            "{\n"
            '  "summary": "Data quality overview",\n'
            '  "coverage": {\n'
            '    "company_intel": "strong|moderate|weak",\n'
            '    "contact_network": "strong|moderate|weak",\n'
            '    "competitive_intel": "strong|moderate|weak",\n'
            '    "pipeline_data": "strong|moderate|weak"\n'
            "  },\n"
            '  "data_quality_score": 0-100,\n'
            '  "critical_gaps": ["most important missing data"],\n'
            '  "recommended_actions": ["action to improve data quality"],\n'
            '  "integration_suggestions": ["connect X for better coverage"]\n'
            "}"
        )
