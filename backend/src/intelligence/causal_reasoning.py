"""Sales Causal Reasoning Engine for ARIA cognition.

Wraps the existing ImplicationEngine to produce sales-actionable
recommendations with timing. Converts market signals into concrete
sales actions by:
1. Fetching recent signals from market_signals table
2. Running each through ImplicationEngine for causal chain analysis
3. Reformatting implications via LLM into SalesAction objects
4. Linking affected leads
5. Persisting results to jarvis_insights

Key design choices:
- Uses CostGovernor for every LLM call
- Uses PersonaBuilder for system prompts
- 1-hour cache on signal analysis to avoid re-processing
- Fail-open: exceptions are logged and empty results returned
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import get_supabase_client
from src.intelligence.causal.engine import CausalChainEngine
from src.intelligence.causal.implication_engine import ImplicationEngine
from src.intelligence.causal.models import Implication
from src.intelligence.temporal import TimeHorizonAnalyzer

logger = logging.getLogger(__name__)

# Cache TTL for signal analysis
_SIGNAL_CACHE_TTL_SECONDS = 3600  # 1 hour


@dataclass
class SalesAction:
    """A sales-actionable recommendation derived from causal reasoning."""

    signal: str  # Original market signal text
    causal_narrative: str  # Human-readable causal chain explanation
    recommended_action: str  # What the sales rep should do
    timing: str  # When to act (e.g., "Within 48 hours", "This week")
    confidence: float  # 0-1
    urgency: str  # "immediate" | "this_week" | "this_month" | "monitor"
    affected_lead_ids: list[str] = field(default_factory=list)
    affected_goal_ids: list[str] = field(default_factory=list)
    implication_type: str = "neutral"  # "opportunity" | "threat" | "neutral"


@dataclass
class CausalReasoningResult:
    """Result of analyzing signals for sales actions."""

    actions: list[SalesAction]
    signals_analyzed: int
    processing_time_ms: float


class SalesCausalReasoningEngine:
    """Converts market signals into sales-actionable recommendations.

    Wraps ImplicationEngine to add:
    - Sales-specific action + timing layer
    - Lead linking
    - LLM reformatting into actionable language
    - Persistence to jarvis_insights
    """

    def __init__(
        self,
        db_client: Any | None = None,
        llm_client: LLMClient | None = None,
        graphiti_client: Any | None = None,
    ) -> None:
        """Initialize the engine.

        Args:
            db_client: Supabase client (created if not provided).
            llm_client: LLM client (created if not provided).
            graphiti_client: Graphiti client for knowledge graph queries.
        """
        self._db = db_client or get_supabase_client()
        self._llm = llm_client or LLMClient()
        self._graphiti = graphiti_client

        # Lazily initialized
        self._implication_engine: ImplicationEngine | None = None
        self._persona_builder: Any = None
        self._cost_governor: Any = None

        # Cache: signal_hash -> (result, timestamp)
        self._cache: dict[str, tuple[list[SalesAction], float]] = {}

    def _get_implication_engine(self) -> ImplicationEngine | None:
        """Lazily initialize the ImplicationEngine."""
        if self._implication_engine is not None:
            return self._implication_engine

        try:
            causal_engine = CausalChainEngine(
                graphiti_client=self._graphiti,
                llm_client=self._llm,
                db_client=self._db,
            )
            time_horizon = TimeHorizonAnalyzer(self._llm)
            self._implication_engine = ImplicationEngine(
                causal_engine=causal_engine,
                db_client=self._db,
                llm_client=self._llm,
                time_horizon_analyzer=time_horizon,
            )
            return self._implication_engine
        except Exception as e:
            logger.warning("Failed to initialize ImplicationEngine: %s", e)
            return None

    def _get_cost_governor(self) -> Any:
        """Lazily initialize CostGovernor."""
        if self._cost_governor is None:
            try:
                from src.core.cost_governor import CostGovernor

                self._cost_governor = CostGovernor(self._db)
            except Exception as e:
                logger.warning("Failed to initialize CostGovernor: %s", e)
        return self._cost_governor

    def _get_persona_builder(self) -> Any:
        """Lazily initialize PersonaBuilder."""
        if self._persona_builder is None:
            try:
                from src.core.persona import get_persona_builder

                self._persona_builder = get_persona_builder()
            except Exception as e:
                logger.warning("Failed to initialize PersonaBuilder: %s", e)
        return self._persona_builder

    async def analyze_recent_signals(
        self,
        user_id: str,
        limit: int = 5,
        hours_back: int = 24,
    ) -> CausalReasoningResult:
        """Fetch recent market signals and analyze each for sales actions.

        Args:
            user_id: User identifier.
            limit: Maximum signals to analyze.
            hours_back: How far back to look for signals.

        Returns:
            CausalReasoningResult with all generated actions.
        """
        start = time.monotonic()
        all_actions: list[SalesAction] = []

        try:
            # Fetch recent signals
            cutoff = (datetime.now(UTC) - timedelta(hours=hours_back)).isoformat()
            result = (
                self._db.table("market_signals")
                .select("id, signal_type, content, source, created_at")
                .eq("user_id", user_id)
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )

            signals = result.data or []
            if not signals:
                return CausalReasoningResult(
                    actions=[], signals_analyzed=0,
                    processing_time_ms=(time.monotonic() - start) * 1000,
                )

            for signal in signals:
                signal_text = signal.get("content", "")
                if not signal_text:
                    continue

                actions = await self.analyze_signal(user_id, signal_text)
                all_actions.extend(actions)

        except Exception as e:
            logger.warning("Failed to analyze recent signals: %s", e)

        elapsed_ms = (time.monotonic() - start) * 1000
        return CausalReasoningResult(
            actions=all_actions,
            signals_analyzed=len(all_actions),
            processing_time_ms=elapsed_ms,
        )

    async def analyze_signal(
        self,
        user_id: str,
        signal: str,
    ) -> list[SalesAction]:
        """Analyze a single signal for sales-actionable implications.

        Args:
            user_id: User identifier.
            signal: Signal text to analyze.

        Returns:
            List of SalesAction objects derived from the signal.
        """
        # Check cache
        cache_key = f"{user_id}:{hash(signal)}"
        cached = self._cache.get(cache_key)
        if cached:
            actions, cached_at = cached
            if time.monotonic() - cached_at < _SIGNAL_CACHE_TTL_SECONDS:
                return actions

        try:
            # Check CostGovernor budget
            governor = self._get_cost_governor()
            if governor:
                budget = await governor.check_budget(user_id)
                if not budget.can_proceed:
                    logger.info(
                        "CostGovernor budget exceeded, skipping causal reasoning",
                        extra={"user_id": user_id},
                    )
                    return []

            # Get implications from ImplicationEngine
            engine = self._get_implication_engine()
            if engine is None:
                return []

            implications = await engine.analyze_event(
                user_id=user_id,
                event=signal,
                max_hops=3,
                min_score=0.3,
            )

            if not implications:
                return []

            # Reformat implications into sales actions via LLM
            actions = await self._reformat_implications_to_actions(
                user_id, signal, implications
            )

            # Link affected leads
            for action in actions:
                lead_ids = await self._link_affected_leads(
                    user_id, signal, implications
                )
                action.affected_lead_ids = lead_ids

            # Persist top actions to jarvis_insights
            for action in actions[:3]:
                await self._persist_action(user_id, action)

            # Cache result
            self._cache[cache_key] = (actions, time.monotonic())

            return actions

        except Exception as e:
            logger.warning("Failed to analyze signal: %s", e)
            return []

    async def _reformat_implications_to_actions(
        self,
        user_id: str,
        signal: str,
        implications: list[Implication],
    ) -> list[SalesAction]:
        """Use LLM to convert raw implications into SalesAction objects.

        Args:
            user_id: User identifier.
            signal: Original signal text.
            implications: Implications from ImplicationEngine.

        Returns:
            List of SalesAction objects.
        """
        if not implications:
            return []

        try:
            # Build context from implications
            impl_summaries = []
            for impl in implications[:5]:
                chain_str = " → ".join(
                    f"{hop.get('source_entity', '?')} [{hop.get('relationship', '?')}] "
                    f"{hop.get('target_entity', '?')}"
                    for hop in impl.causal_chain
                )
                impl_summaries.append(
                    f"- Type: {impl.type.value}, Score: {impl.combined_score:.2f}\n"
                    f"  Chain: {chain_str}\n"
                    f"  Content: {impl.content}\n"
                    f"  Recommendations: {', '.join(impl.recommended_actions)}"
                )

            system_prompt = (
                "You are a life sciences sales intelligence analyst. "
                "Convert causal chain implications into concrete, "
                "actionable sales recommendations with specific timing.\n\n"
                "Return ONLY a valid JSON array. Each element must have:\n"
                '{"recommended_action": "string", "timing": "string", '
                '"urgency": "immediate|this_week|this_month|monitor", '
                '"causal_narrative": "1-2 sentence causal explanation"}\n\n'
                "Focus on what a sales rep should DO, not what they should know."
            )

            user_prompt = (
                f"Market Signal: {signal}\n\n"
                f"Causal Implications:\n"
                + "\n".join(impl_summaries)
                + "\n\nGenerate 1-3 sales actions:"
            )

            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                temperature=0.4,
                max_tokens=500,
                user_id=user_id,
            )

            # Parse JSON response
            raw = response.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()

            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                parsed = [parsed]

            actions: list[SalesAction] = []
            for item in parsed[:3]:
                if not isinstance(item, dict):
                    continue

                # Get best implication for metadata
                best_impl = implications[0]

                actions.append(
                    SalesAction(
                        signal=signal,
                        causal_narrative=item.get("causal_narrative", ""),
                        recommended_action=item.get("recommended_action", ""),
                        timing=item.get("timing", ""),
                        confidence=best_impl.confidence,
                        urgency=item.get("urgency", "monitor"),
                        affected_goal_ids=best_impl.affected_goals,
                        implication_type=best_impl.type.value,
                    )
                )

            return actions

        except Exception as e:
            logger.warning("Failed to reformat implications: %s", e)
            # Fallback: create basic actions from implications
            return self._fallback_actions(signal, implications)

    def _fallback_actions(
        self,
        signal: str,
        implications: list[Implication],
    ) -> list[SalesAction]:
        """Create basic SalesAction objects without LLM reformatting."""
        actions: list[SalesAction] = []
        for impl in implications[:3]:
            chain_str = " → ".join(
                f"{hop.get('source_entity', '?')} → {hop.get('target_entity', '?')}"
                for hop in impl.causal_chain
            )
            actions.append(
                SalesAction(
                    signal=signal,
                    causal_narrative=f"Causal path: {chain_str}. {impl.content}",
                    recommended_action=(
                        impl.recommended_actions[0]
                        if impl.recommended_actions
                        else "Review this signal for action."
                    ),
                    timing=impl.time_to_impact or "Unknown",
                    confidence=impl.confidence,
                    urgency=self._urgency_from_score(impl.urgency),
                    affected_goal_ids=impl.affected_goals,
                    implication_type=impl.type.value,
                )
            )
        return actions

    @staticmethod
    def _urgency_from_score(urgency_score: float) -> str:
        """Convert numeric urgency to category string."""
        if urgency_score >= 0.8:
            return "immediate"
        elif urgency_score >= 0.6:
            return "this_week"
        elif urgency_score >= 0.4:
            return "this_month"
        return "monitor"

    async def _link_affected_leads(
        self,
        user_id: str,
        signal: str,
        implications: list[Implication],
    ) -> list[str]:
        """Find leads affected by the signal's causal chain.

        Queries the leads table using entity names from the causal chain.

        Args:
            user_id: User identifier.
            signal: Original signal text.
            implications: Implications with causal chain data.

        Returns:
            List of lead IDs.
        """
        try:
            # Collect entity names from causal chains
            entity_names: set[str] = set()
            for impl in implications:
                for hop in impl.causal_chain:
                    entity_names.add(hop.get("source_entity", ""))
                    entity_names.add(hop.get("target_entity", ""))

            entity_names.discard("")

            if not entity_names:
                return []

            # Query leads by entity names (ilike for case-insensitive match)
            lead_ids: list[str] = []
            for entity in list(entity_names)[:5]:
                result = (
                    self._db.table("leads")
                    .select("id")
                    .eq("user_id", user_id)
                    .ilike("company", f"%{entity}%")
                    .limit(3)
                    .execute()
                )
                if result.data:
                    lead_ids.extend(r["id"] for r in result.data)

            return list(set(lead_ids))

        except Exception as e:
            logger.warning("Failed to link affected leads: %s", e)
            return []

    async def _persist_action(
        self,
        user_id: str,
        action: SalesAction,
    ) -> None:
        """Persist a sales action to jarvis_insights.

        Args:
            user_id: User identifier.
            action: SalesAction to persist.
        """
        try:
            self._db.table("jarvis_insights").insert({
                "user_id": user_id,
                "insight_type": "causal_sales_action",
                "trigger_event": action.signal,
                "content": action.recommended_action,
                "classification": action.implication_type,
                "impact_score": action.confidence,
                "confidence": action.confidence,
                "urgency": 0.8 if action.urgency == "immediate" else 0.5,
                "combined_score": action.confidence,
                "causal_chain": [],
                "affected_goals": action.affected_goal_ids,
                "recommended_actions": [action.recommended_action],
                "time_horizon": action.urgency,
                "time_to_impact": action.timing,
                "status": "new",
            }).execute()
        except Exception as e:
            logger.warning("Failed to persist sales action: %s", e)
