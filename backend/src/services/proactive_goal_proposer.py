"""Proactive Goal Proposer — converts high-relevance signals and OODA
implication chains into user-facing goal proposals delivered via WebSocket.

When a signal fires or OODA orient produces a high-urgency implication chain,
this service generates a goal proposal with an LLM, routes it through
ProactiveRouter (online → WebSocket, offline → login queue), and stores
the proposal in the ``proactive_proposals`` table for dedup/approval tracking.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.ws import ws_manager
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Minimum relevance score for a signal to trigger a proposal
_MIN_RELEVANCE_SCORE = 0.7

# Maximum proposals generated per OODA orient cycle
_MAX_PROPOSALS_PER_ORIENT = 2


class ProactiveGoalProposer:
    """Bridge between signals/OODA and the goal pipeline.

    Entry points:
    - ``evaluate_signal`` — called after ``SignalService.create_signal()``
    - ``evaluate_implication_chain`` — called after OODA orient phase
    """

    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def evaluate_signal(
        self,
        user_id: str,
        signal_id: str,
        signal_type: str,
        headline: str,
        summary: str | None = None,
        relevance_score: float = 0.0,
        company_name: str | None = None,
    ) -> bool:
        """Evaluate a market signal and optionally propose a goal.

        Args:
            user_id: Owner of the signal.
            signal_id: UUID of the stored signal row.
            signal_type: e.g. "pipeline_update", "competitive_move".
            headline: Short headline from the signal.
            summary: Optional longer summary.
            relevance_score: 0-1 relevance score.
            company_name: Affected company.

        Returns:
            True if a proposal was generated and routed, False otherwise.
        """
        if relevance_score < _MIN_RELEVANCE_SCORE:
            return False

        # Dedup: skip if we already proposed for this signal
        existing = (
            self._db.table("proactive_proposals")
            .select("id")
            .eq("user_id", user_id)
            .eq("source_signal_id", signal_id)
            .limit(1)
            .execute()
        )
        if existing.data:
            logger.debug("Proposal already exists for signal %s", signal_id)
            return False

        affected_count = await self._count_affected_entities(user_id, company_name)

        proposal = await self._generate_proposal(
            user_id=user_id,
            headline=headline,
            summary=summary or headline,
            signal_type=signal_type,
            company_name=company_name,
            affected_count=affected_count,
        )
        if not proposal:
            return False

        await self._store_and_route_proposal(
            user_id=user_id,
            source_signal_id=signal_id,
            source_goal_id=None,
            proposal=proposal,
        )
        return True

    async def evaluate_implication_chain(
        self,
        user_id: str,
        goal_id: str | None,
        chain: dict[str, Any],
    ) -> bool:
        """Evaluate an OODA orient implication chain and optionally propose a goal.

        Only acts on high-urgency chains.

        Args:
            user_id: Owner of the OODA state.
            goal_id: Optional goal that triggered the OODA cycle.
            chain: Implication chain dict (expects ``urgency``, ``headline``,
                ``summary``, ``company_name``).

        Returns:
            True if a proposal was generated and routed.
        """
        urgency = chain.get("urgency", "low")
        if urgency != "high":
            return False

        headline = chain.get("headline", "")
        if not headline:
            return False

        proposal = await self._generate_proposal(
            user_id=user_id,
            headline=headline,
            summary=chain.get("summary", headline),
            signal_type="ooda_implication",
            company_name=chain.get("company_name"),
            affected_count=0,
        )
        if not proposal:
            return False

        await self._store_and_route_proposal(
            user_id=user_id,
            source_signal_id=None,
            source_goal_id=goal_id,
            proposal=proposal,
        )
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate_proposal(
        self,
        user_id: str,
        headline: str,
        summary: str,
        signal_type: str,
        company_name: str | None,
        affected_count: int,
    ) -> dict[str, Any] | None:
        """Use an LLM to generate a goal proposal from signal data.

        Returns a dict with keys: message, goal_title, rationale, approach,
        agents, timeline, goal_type.  Returns None on failure or budget refusal.
        """
        try:
            from src.core.cost_governor import CostGovernor
            from src.core.llm import LLMClient

            governor = CostGovernor(self._db)
            budget = await governor.check_budget(user_id)
            if not budget.can_proceed:
                logger.debug("Budget exhausted — skipping proposal for %s", user_id)
                return None

            llm = LLMClient()

            affected_note = ""
            if affected_count > 0:
                affected_note = f"\nThis affects {affected_count} lead(s) in the user's pipeline."

            prompt = (
                "You are ARIA, an AI Department Director for a life sciences "
                "commercial team. A market signal has been detected that may "
                "warrant proactive action.\n\n"
                f"Signal type: {signal_type}\n"
                f"Company: {company_name or 'Unknown'}\n"
                f"Headline: {headline}\n"
                f"Summary: {summary}\n"
                f"{affected_note}\n\n"
                "Based on this signal, propose ONE actionable goal for the user. "
                "Return a JSON object with these keys:\n"
                '- "message": a brief, direct message to the user (1-2 sentences, '
                "ARIA's voice — confident, no hedging)\n"
                '- "goal_title": concise goal title (max 60 chars)\n'
                '- "rationale": why this matters (1 sentence)\n'
                '- "approach": high-level approach (1-2 sentences)\n'
                '- "agents": array of agent names to use '
                "(from: Hunter, Analyst, Strategist, Scribe, Operator, Scout)\n"
                '- "timeline": estimated timeline (e.g. "1-2 days")\n'
                '- "goal_type": one of "pipeline", "competitive_intel", '
                '"account_strategy", "communication", "market_research"\n\n'
                "Return ONLY the JSON object, no other text."
            )

            # Use PersonaBuilder if available
            system_prompt: str | None = None
            try:
                from src.core.persona import PersonaRequest, get_persona_builder

                builder = get_persona_builder()
                ctx = await builder.build(
                    PersonaRequest(
                        user_id=user_id,
                        agent_name="proactive_proposer",
                        agent_role_description=(
                            "Evaluating market signals and proposing actionable "
                            "goals for the user"
                        ),
                        task_description="Generate a proactive goal proposal from a market signal",
                        output_format="json",
                    )
                )
                system_prompt = ctx.to_system_prompt()
            except Exception:
                pass

            response = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                max_tokens=600,
                temperature=0.5,
            )

            await governor.record_usage(user_id, getattr(llm, "_last_usage", None))

            # Parse JSON
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[: -len("```")]
                cleaned = cleaned.strip()

            return json.loads(cleaned)

        except Exception as e:
            logger.debug("Proposal generation failed: %s", e)
            return None

    async def _count_affected_entities(
        self,
        user_id: str,
        company_name: str | None,
    ) -> int:
        """Count lead_memories matching the given company name."""
        if not company_name:
            return 0
        try:
            result = (
                self._db.table("lead_memories")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .ilike("company_name", f"%{company_name}%")
                .execute()
            )
            return result.count or 0
        except Exception:
            return 0

    async def _store_and_route_proposal(
        self,
        user_id: str,
        source_signal_id: str | None,
        source_goal_id: str | None,
        proposal: dict[str, Any],
    ) -> None:
        """Store the proposal and route it to the user via ProactiveRouter."""
        proposal_id = str(uuid.uuid4())

        # Build rich_content card
        rich_content = [
            {
                "type": "goal_plan",
                "data": {
                    "id": f"signal-proposal-{proposal_id}",
                    "title": proposal.get("goal_title", "Proposed Goal"),
                    "rationale": proposal.get("rationale", ""),
                    "approach": proposal.get("approach", ""),
                    "agents": proposal.get("agents", []),
                    "timeline": proposal.get("timeline", ""),
                    "goal_type": proposal.get("goal_type", "custom"),
                    "status": "proposed",
                    "source_signal_id": source_signal_id,
                    "proposal_id": proposal_id,
                },
            }
        ]

        # Persist proposal
        try:
            self._db.table("proactive_proposals").insert(
                {
                    "id": proposal_id,
                    "user_id": user_id,
                    "source_signal_id": source_signal_id,
                    "source_goal_id": source_goal_id,
                    "goal_title": proposal.get("goal_title", ""),
                    "status": "proposed",
                    "proposal_data": proposal,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception as e:
            logger.debug("Failed to store proposal: %s", e)

        # Route through ProactiveRouter (handles online/offline delivery)
        try:
            from src.services.proactive_router import (
                InsightCategory,
                InsightPriority,
                ProactiveRouter,
            )

            router = ProactiveRouter()
            await router.route(
                user_id=user_id,
                priority=InsightPriority.HIGH,
                category=InsightCategory.MARKET_SIGNAL,
                title=proposal.get("goal_title", "New opportunity detected"),
                message=proposal.get("message", "I've spotted something worth investigating."),
                rich_content=rich_content,
                suggestions=["Tell me more", "Create this goal", "Dismiss"],
                metadata={
                    "proposal_id": proposal_id,
                    "source_signal_id": source_signal_id,
                    "source_goal_id": source_goal_id,
                },
            )
        except Exception as e:
            # Fallback: try direct WebSocket delivery
            logger.debug("ProactiveRouter failed, attempting direct WS delivery: %s", e)
            try:
                await ws_manager.send_aria_message(
                    user_id=user_id,
                    message=proposal.get("message", "I've spotted something worth investigating."),
                    rich_content=rich_content,
                    suggestions=["Tell me more", "Create this goal", "Dismiss"],
                )
            except Exception:
                logger.debug("Direct WS delivery also failed for user %s", user_id)
