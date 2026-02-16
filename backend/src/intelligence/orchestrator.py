"""Jarvis Intelligence Orchestrator (US-710).

Coordinates all 9 intelligence engines into a unified system with
time-budgeted execution, deduplication, and feedback tracking.
"""

from __future__ import annotations

import difflib
import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.intelligence.causal.models import JarvisInsight

logger = logging.getLogger(__name__)

# Engine priority order with default time budgets (ms)
_ENGINE_BUDGETS: list[tuple[str, int]] = [
    ("predictive", 200),
    ("implication", 1000),
    ("butterfly", 500),
    ("connection", 1000),
    ("goal_impact", 500),
    ("temporal", 500),
]

# Deduplication similarity threshold
_DEDUP_THRESHOLD = 0.7


class JarvisOrchestrator:
    """Coordinates all Phase 7 intelligence engines.

    Lazy-initializes engines on first use and provides unified methods
    for briefing generation, event processing, insight retrieval,
    feedback recording, and metrics aggregation.
    """

    def __init__(self, llm_client: Any, db_client: Any) -> None:
        self._llm = llm_client
        self._db = db_client

        # Lazy-init placeholders
        self.__causal: Any | None = None
        self.__implication: Any | None = None
        self.__butterfly: Any | None = None
        self.__connection: Any | None = None
        self.__goal_impact: Any | None = None
        self.__predictive: Any | None = None
        self.__simulation: Any | None = None
        self.__temporal: Any | None = None
        self.__time_horizon: Any | None = None

    # ------------------------------------------------------------------
    # Lazy engine properties
    # ------------------------------------------------------------------

    @property
    def _causal_engine(self) -> Any:
        if self.__causal is None:
            from src.intelligence.causal.engine import CausalChainEngine

            self.__causal = CausalChainEngine(
                graphiti_client=None,
                llm_client=self._llm,
                db_client=self._db,
            )
        return self.__causal

    @property
    def _time_horizon_analyzer(self) -> Any:
        if self.__time_horizon is None:
            from src.intelligence.temporal.time_horizon import TimeHorizonAnalyzer

            self.__time_horizon = TimeHorizonAnalyzer(llm_client=self._llm)
        return self.__time_horizon

    @property
    def _implication_engine(self) -> Any:
        if self.__implication is None:
            from src.intelligence.causal.implication_engine import ImplicationEngine

            self.__implication = ImplicationEngine(
                causal_engine=self._causal_engine,
                db_client=self._db,
                llm_client=self._llm,
                time_horizon_analyzer=self._time_horizon_analyzer,
            )
        return self.__implication

    @property
    def _butterfly_detector(self) -> Any:
        if self.__butterfly is None:
            from src.intelligence.causal.butterfly_detector import ButterflyDetector

            self.__butterfly = ButterflyDetector(
                implication_engine=self._implication_engine,
                db_client=self._db,
                llm_client=self._llm,
            )
        return self.__butterfly

    @property
    def _connection_engine(self) -> Any:
        if self.__connection is None:
            from src.intelligence.causal.connection_engine import (
                CrossDomainConnectionEngine,
            )

            self.__connection = CrossDomainConnectionEngine(
                graphiti_client=None,
                llm_client=self._llm,
                db_client=self._db,
                causal_engine=self._causal_engine,
            )
        return self.__connection

    @property
    def _goal_impact_mapper(self) -> Any:
        if self.__goal_impact is None:
            from src.intelligence.causal.goal_impact import GoalImpactMapper

            self.__goal_impact = GoalImpactMapper(
                db_client=self._db,
                llm_client=self._llm,
            )
        return self.__goal_impact

    @property
    def _predictive_engine(self) -> Any:
        if self.__predictive is None:
            from src.intelligence.predictive.engine import PredictiveEngine

            self.__predictive = PredictiveEngine(
                llm_client=self._llm,
                db_client=self._db,
            )
        return self.__predictive

    @property
    def _simulation_engine(self) -> Any:
        if self.__simulation is None:
            from src.intelligence.simulation.engine import MentalSimulationEngine

            self.__simulation = MentalSimulationEngine(
                causal_engine=self._causal_engine,
                llm_client=self._llm,
                db_client=self._db,
            )
        return self.__simulation

    @property
    def _temporal_reasoner(self) -> Any:
        if self.__temporal is None:
            from src.intelligence.temporal.multi_scale import (
                MultiScaleTemporalReasoner,
            )

            self.__temporal = MultiScaleTemporalReasoner(
                llm_client=self._llm,
                db_client=self._db,
            )
        return self.__temporal

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def generate_briefing(
        self,
        user_id: str,
        context: dict[str, Any] | None = None,
        budget_ms: int = 5000,
    ) -> list[JarvisInsight]:
        """Generate intelligence insights for a morning briefing.

        Runs engines in priority order with time-budgeted execution.
        Skips remaining engines if 80% of budget is exhausted.

        Args:
            user_id: User UUID.
            context: Optional context dict (e.g. briefing_date).
            budget_ms: Total time budget in milliseconds.

        Returns:
            Up to 10 deduplicated insights sorted by combined_score.
        """
        start = time.perf_counter()
        all_insights: list[JarvisInsight] = []
        ctx = context or {}

        for engine_name, engine_budget_ms in _ENGINE_BUDGETS:
            elapsed_ms = (time.perf_counter() - start) * 1000
            if elapsed_ms > budget_ms * 0.8:
                logger.info(
                    "Budget %.0f%% exhausted (%.0fms / %dms), skipping remaining engines",
                    (elapsed_ms / budget_ms) * 100,
                    elapsed_ms,
                    budget_ms,
                )
                break

            try:
                engine_insights = await self._run_engine(
                    engine_name, user_id, ctx, engine_budget_ms
                )
                all_insights.extend(engine_insights)
            except Exception:
                logger.warning("Engine %s failed during briefing", engine_name, exc_info=True)

        deduplicated = self._deduplicate(all_insights)
        deduplicated.sort(key=lambda i: i.combined_score, reverse=True)
        return deduplicated[:10]

    async def process_event(
        self,
        user_id: str,
        event: str,
        source_context: str = "api_request",
        source_id: str | None = None,
    ) -> list[JarvisInsight]:
        """Process an event through the intelligence pipeline.

        Runs: causal traversal -> implications -> butterfly check ->
        goal impact -> time horizon categorization.

        Args:
            user_id: User UUID.
            event: Event description text.
            source_context: Where the event originated.
            source_id: Optional source entity ID.

        Returns:
            List of generated insights (top 5 persisted to DB).
        """
        all_insights: list[JarvisInsight] = []

        logger.info(
            "Processing event from %s (source_id=%s)",
            source_context,
            source_id,
        )

        # Step 1: Implications (includes causal traversal internally)
        try:
            implications = await self._implication_engine.analyze_event(
                user_id=user_id,
                event=event,
                max_hops=4,
                include_neutral=False,
                min_score=0.4,
            )
            for imp in implications[:5]:
                insight = await self._implication_engine.save_insight(
                    user_id=user_id,
                    implication=imp,
                )
                if insight:
                    all_insights.append(insight)
        except Exception:
            logger.warning("Implication analysis failed for event", exc_info=True)

        # Step 2: Butterfly effect detection
        try:
            butterfly = await self._butterfly_detector.detect(
                user_id=user_id,
                event=event,
                max_hops=4,
            )
            if butterfly:
                butterfly_insight = await self._butterfly_detector.save_butterfly_insight(
                    user_id=user_id,
                    butterfly=butterfly,
                )
                if butterfly_insight:
                    all_insights.append(butterfly_insight)
        except Exception:
            logger.warning("Butterfly detection failed for event", exc_info=True)

        # Step 3: Goal impact mapping
        try:
            goal_impacts = await self._goal_impact_mapper.assess_event_impact(
                user_id=user_id,
                event=event,
            )
            for impact in goal_impacts[:3]:
                if hasattr(impact, "to_jarvis_insight"):
                    insight = impact.to_jarvis_insight()
                    if insight:
                        all_insights.append(insight)
        except Exception:
            logger.warning("Goal impact mapping failed for event", exc_info=True)

        # Step 4: Time horizon categorization on resulting insights
        try:
            for insight in all_insights:
                if not insight.time_horizon:
                    horizon = await self._time_horizon_analyzer.analyze(
                        content=insight.content,
                        context=event,
                    )
                    if horizon:
                        insight.time_horizon = horizon.horizon
                        insight.time_to_impact = horizon.time_to_impact
        except Exception:
            logger.warning("Time horizon categorization failed", exc_info=True)

        deduplicated = self._deduplicate(all_insights)
        deduplicated.sort(key=lambda i: i.combined_score, reverse=True)
        return deduplicated[:5]

    async def get_active_insights(
        self,
        user_id: str,
        limit: int = 20,
        insight_type: str | None = None,
    ) -> list[JarvisInsight]:
        """Query active insights from the jarvis_insights table.

        Args:
            user_id: User UUID.
            limit: Maximum number of insights to return.
            insight_type: Optional filter by insight_type.

        Returns:
            List of JarvisInsight sorted by combined_score desc.
        """
        try:
            query = (
                self._db.table("jarvis_insights")
                .select("*")
                .eq("user_id", user_id)
                .in_("status", ["new", "engaged"])
                .order("combined_score", desc=True)
                .limit(limit)
            )
            if insight_type:
                query = query.eq("insight_type", insight_type)

            response = query.execute()
            return [JarvisInsight(**row) for row in (response.data or [])]
        except Exception:
            logger.warning("Failed to fetch active insights", exc_info=True)
            return []

    async def record_feedback(
        self,
        insight_id: str,
        feedback: str,
        user_id: str,
    ) -> None:
        """Record user feedback on an insight.

        Args:
            insight_id: The insight UUID.
            feedback: Feedback value (helpful, not_helpful, wrong).
            user_id: User UUID for authorization.
        """
        try:
            self._db.table("jarvis_insights").update(
                {
                    "status": "feedback",
                    "feedback_text": feedback,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", insight_id).eq("user_id", user_id).execute()
        except Exception:
            logger.warning("Failed to record feedback for insight %s", insight_id, exc_info=True)

    async def get_engine_metrics(self, user_id: str) -> dict[str, Any]:
        """Aggregate metrics from jarvis_insights table.

        Returns counts by type, classification, status, average score,
        and counts for the last 7 and 30 days.
        """
        try:
            response = (
                self._db.table("jarvis_insights")
                .select("insight_type, classification, status, combined_score, created_at")
                .eq("user_id", user_id)
                .execute()
            )
            rows = response.data or []

            by_type: dict[str, int] = {}
            by_classification: dict[str, int] = {}
            by_status: dict[str, int] = {}
            total_score = 0.0
            now = datetime.now(UTC)
            last_7 = 0
            last_30 = 0

            for row in rows:
                by_type[row["insight_type"]] = by_type.get(row["insight_type"], 0) + 1
                by_classification[row["classification"]] = (
                    by_classification.get(row["classification"], 0) + 1
                )
                by_status[row["status"]] = by_status.get(row["status"], 0) + 1
                total_score += row.get("combined_score", 0.0)

                created = row.get("created_at", "")
                if created:
                    try:
                        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        delta = (now - dt).days
                        if delta <= 7:
                            last_7 += 1
                        if delta <= 30:
                            last_30 += 1
                    except (ValueError, TypeError):
                        pass

            return {
                "total_insights": len(rows),
                "by_type": by_type,
                "by_classification": by_classification,
                "by_status": by_status,
                "average_score": round(total_score / len(rows), 3) if rows else 0.0,
                "last_7_days": last_7,
                "last_30_days": last_30,
            }
        except Exception:
            logger.warning("Failed to aggregate engine metrics", exc_info=True)
            return {
                "total_insights": 0,
                "by_type": {},
                "by_classification": {},
                "by_status": {},
                "average_score": 0.0,
                "last_7_days": 0,
                "last_30_days": 0,
            }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _run_engine(
        self,
        engine_name: str,
        user_id: str,
        context: dict[str, Any],
        budget_ms: int,
    ) -> list[JarvisInsight]:
        """Run a single engine and return insights.

        Each engine call is best-effort; failures return empty list.
        The budget_ms is logged for observability; individual engine
        timeouts are handled by the caller's overall budget check.
        """
        logger.debug("Running engine %s with budget %dms", engine_name, budget_ms)

        if engine_name == "predictive":
            predictions = await self._predictive_engine.generate_predictions(
                user_id=user_id,
                context=context,
            )
            return self._predictions_to_insights(predictions, user_id)

        if engine_name == "implication":
            # Analyze recent events from context or a default event
            events = context.get("recent_events", [])
            insights: list[JarvisInsight] = []
            for event_text in events[:3]:
                implications = await self._implication_engine.analyze_event(
                    user_id=user_id,
                    event=event_text,
                    max_hops=3,
                    include_neutral=False,
                    min_score=0.5,
                )
                for imp in implications[:2]:
                    saved = await self._implication_engine.save_insight(
                        user_id=user_id, implication=imp
                    )
                    if saved:
                        insights.append(saved)
            return insights

        if engine_name == "butterfly":
            events = context.get("new_events", [])
            insights = []
            for event_text in events[:2]:
                butterfly = await self._butterfly_detector.detect(
                    user_id=user_id, event=event_text, max_hops=3
                )
                if butterfly:
                    saved = await self._butterfly_detector.save_butterfly_insight(
                        user_id=user_id, butterfly=butterfly
                    )
                    if saved:
                        insights.append(saved)
            return insights

        if engine_name == "connection":
            connections = await self._connection_engine.find_connections(
                user_id=user_id,
                context=context,
            )
            return self._connections_to_insights(connections, user_id)

        if engine_name == "goal_impact":
            events = context.get("recent_events", context.get("new_events", []))
            insights = []
            for event_text in events[:3]:
                impacts = await self._goal_impact_mapper.assess_event_impact(
                    user_id=user_id, event=event_text
                )
                for impact in impacts[:2]:
                    if hasattr(impact, "to_jarvis_insight"):
                        insight = impact.to_jarvis_insight()
                        if insight:
                            insights.append(insight)
            return insights

        if engine_name == "temporal":
            decisions = context.get("pending_decisions", [])
            insights = []
            for decision in decisions[:2]:
                analysis = await self._temporal_reasoner.analyze_decision(
                    user_id=user_id, decision=decision
                )
                if analysis:
                    insights.append(self._temporal_to_insight(analysis, decision, user_id))
            return insights

        return []

    def _deduplicate(self, insights: list[JarvisInsight]) -> list[JarvisInsight]:
        """Remove near-duplicate insights by content similarity.

        Uses SequenceMatcher with threshold 0.7. Also deduplicates
        by identical trigger_event values, keeping higher-scored insight.
        """
        if len(insights) <= 1:
            return insights

        # First pass: deduplicate by trigger_event
        seen_triggers: dict[str, JarvisInsight] = {}
        trigger_deduped: list[JarvisInsight] = []

        for insight in insights:
            trigger = insight.trigger_event.strip().lower()
            if trigger in seen_triggers:
                existing = seen_triggers[trigger]
                if insight.combined_score > existing.combined_score:
                    trigger_deduped.remove(existing)
                    trigger_deduped.append(insight)
                    seen_triggers[trigger] = insight
            else:
                seen_triggers[trigger] = insight
                trigger_deduped.append(insight)

        # Second pass: deduplicate by content similarity
        result: list[JarvisInsight] = []
        for insight in trigger_deduped:
            is_duplicate = False
            for existing in result:
                ratio = difflib.SequenceMatcher(None, insight.content, existing.content).ratio()
                if ratio > _DEDUP_THRESHOLD:
                    # Keep the higher-scored one
                    if insight.combined_score > existing.combined_score:
                        result.remove(existing)
                        result.append(insight)
                    is_duplicate = True
                    break
            if not is_duplicate:
                result.append(insight)

        return result

    def _predictions_to_insights(self, predictions: Any, user_id: str) -> list[JarvisInsight]:
        """Convert PredictiveEngine output to JarvisInsight objects."""
        insights: list[JarvisInsight] = []
        if not predictions:
            return insights

        items = predictions if isinstance(predictions, list) else [predictions]
        for pred in items:
            try:
                content = getattr(pred, "description", str(pred))
                confidence = getattr(pred, "confidence", 0.5)
                insights.append(
                    JarvisInsight(
                        id=UUID("00000000-0000-0000-0000-000000000000"),
                        user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
                        insight_type="prediction",
                        trigger_event="predictive_analysis",
                        content=content,
                        classification="neutral",
                        impact_score=confidence,
                        confidence=confidence,
                        urgency=0.5,
                        combined_score=confidence * 0.8,
                        causal_chain=[],
                        affected_goals=[],
                        recommended_actions=getattr(pred, "recommended_actions", []),
                        status="new",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
            except Exception:
                logger.debug("Failed to convert prediction to insight", exc_info=True)
        return insights

    def _connections_to_insights(self, connections: Any, user_id: str) -> list[JarvisInsight]:
        """Convert CrossDomainConnectionEngine output to JarvisInsight objects."""
        insights: list[JarvisInsight] = []
        if not connections:
            return insights

        items = connections if isinstance(connections, list) else [connections]
        for conn in items:
            try:
                content = getattr(conn, "description", str(conn))
                novelty = getattr(conn, "novelty_score", 0.5)
                insights.append(
                    JarvisInsight(
                        id=UUID("00000000-0000-0000-0000-000000000000"),
                        user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
                        insight_type="connection",
                        trigger_event="cross_domain_analysis",
                        content=content,
                        classification="opportunity",
                        impact_score=novelty,
                        confidence=novelty,
                        urgency=0.3,
                        combined_score=novelty * 0.7,
                        causal_chain=[],
                        affected_goals=[],
                        recommended_actions=[],
                        status="new",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )
            except Exception:
                logger.debug("Failed to convert connection to insight", exc_info=True)
        return insights

    def _temporal_to_insight(self, analysis: Any, decision: str, user_id: str) -> JarvisInsight:
        """Convert temporal analysis to a JarvisInsight."""
        alignment = getattr(analysis, "overall_alignment", 0.5)
        conflicts = getattr(analysis, "conflicts", [])
        content = f"Temporal analysis of '{decision[:80]}': "
        if conflicts:
            content += f"{len(conflicts)} cross-scale conflict(s) detected."
        else:
            content += "No cross-scale conflicts detected."

        return JarvisInsight(
            id=UUID("00000000-0000-0000-0000-000000000000"),
            user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
            insight_type="temporal",
            trigger_event=decision[:200],
            content=content,
            classification="neutral",
            impact_score=1.0 - alignment if conflicts else alignment,
            confidence=0.6,
            urgency=0.7 if conflicts else 0.3,
            combined_score=(1.0 - alignment) * 0.8 if conflicts else alignment * 0.5,
            causal_chain=[],
            affected_goals=[],
            recommended_actions=[],
            time_horizon="medium_term",
            status="new",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )


def create_orchestrator() -> JarvisOrchestrator:
    """Factory function that creates a fully-configured orchestrator."""
    from src.core.llm import LLMClient
    from src.db.supabase import SupabaseClient

    return JarvisOrchestrator(
        llm_client=LLMClient(),
        db_client=SupabaseClient.get_client(),
    )
