"""Jarvis Intelligence Orchestrator (US-710).

Coordinates all 9 intelligence engines into a unified system with
parallel execution, deduplication, and feedback tracking.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from src.intelligence.causal.models import JarvisInsight
from src.intelligence.context_enricher import ContextEnricher

logger = logging.getLogger(__name__)

# Engines to run during briefing generation (all run in parallel)
_BRIEFING_ENGINES: list[str] = [
    "predictive",
    "implication",
    "butterfly",
    "connection",
    "goal_impact",
    "temporal",
]

# Per-engine timeout in seconds — tuned to each engine's workload
_ENGINE_TIMEOUT_S = 20

# Engine-specific timeouts for process_event pipeline
_PROCESS_EVENT_TIMEOUTS: dict[str, int] = {
    "implication": 30,  # Heavy LLM engine (includes causal traversal + context enrichment)
    "butterfly": 30,   # Wraps implication engine internally
    "goal_impact": 10,  # DB query + LLM for impact classification
    "time_horizon": 10,
    "connection": 15,
    "temporal": 10,
    "predictive": 15,
}


class JarvisOrchestrator:
    """Coordinates all Phase 7 intelligence engines.

    Lazy-initializes engines on first use and provides unified methods
    for briefing generation, event processing, insight retrieval,
    feedback recording, and metrics aggregation.
    """

    def __init__(self, llm_client: Any, db_client: Any) -> None:
        self._llm = llm_client
        self._db = db_client

        # Context enricher (initialized eagerly — no LLM dependency)
        self._context_enricher = ContextEnricher(self._db)

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
        budget_ms: int = 60000,
    ) -> list[JarvisInsight]:
        """Generate intelligence insights for a morning briefing.

        Runs all engines in parallel with per-engine timeouts.
        This is a background task (not user-facing), so the budget
        is generous enough for LLM calls to complete.

        Args:
            user_id: User UUID.
            context: Optional context dict (e.g. briefing_date).
            budget_ms: Total time budget in milliseconds (default 60s).

        Returns:
            Up to 10 deduplicated insights sorted by combined_score.
        """
        start = time.perf_counter()
        all_insights: list[JarvisInsight] = []
        ctx = context or {}

        # --- Context enrichment for briefing ---
        # Use a general enrichment (no specific company) to get user identity,
        # competitive landscape, and active goals into the context.
        enriched_ctx = await self._context_enricher.enrich_event_context(
            user_id=user_id,
            event="morning briefing generation",
            company_name=ctx.get("company_name", ""),
            existing_context=ctx,
        )
        aria_brief = self._context_enricher.format_context_for_llm(enriched_ctx)
        enriched_ctx["aria_context_brief"] = aria_brief

        # Run all engines in parallel with per-engine timeout
        tasks = [
            self._run_engine_with_timeout(
                engine_name, user_id, enriched_ctx,
                timeout_s=_PROCESS_EVENT_TIMEOUTS.get(engine_name, _ENGINE_TIMEOUT_S),
            )
            for engine_name in _BRIEFING_ENGINES
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for engine_name, result in zip(_BRIEFING_ENGINES, results):
            if isinstance(result, Exception):
                logger.warning(
                    "Engine %s failed during briefing: %s",
                    engine_name,
                    result,
                )
            elif isinstance(result, list):
                all_insights.extend(result)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "Briefing generation complete: %d insights in %.0fms",
            len(all_insights),
            elapsed_ms,
        )

        deduplicated = self._deduplicate(all_insights)
        # _deduplicate already sorts by confidence, just cap at 10 for briefings
        return deduplicated[:10]

    async def process_event(
        self,
        user_id: str,
        event: str,
        source_context: str = "api_request",
        source_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> list[JarvisInsight]:
        """Process an event through the intelligence pipeline.

        Runs implication, butterfly, and goal impact engines in parallel
        with per-engine timeouts. Then enriches with time horizons.

        Args:
            user_id: User UUID.
            event: Event description text.
            source_context: Where the event originated.
            source_id: Optional source entity ID.
            context: Optional context dict with additional event info.

        Returns:
            List of generated insights (top 5 persisted to DB).
        """
        start = time.perf_counter()
        all_insights: list[JarvisInsight] = []

        logger.info(
            "Processing event from %s (source_id=%s)",
            source_context,
            source_id,
        )

        # --- Context enrichment: assemble ARIA's institutional knowledge ---
        ctx = context or {}
        enriched_context = await self._context_enricher.enrich_event_context(
            user_id=user_id,
            event=event,
            company_name=ctx.get("company_name", "") if isinstance(ctx, dict) else "",
            signal_type=ctx.get("signal_type", "") if isinstance(ctx, dict) else "",
            existing_context=ctx if isinstance(ctx, dict) else {},
        )
        aria_brief = self._context_enricher.format_context_for_llm(enriched_context)
        enriched_context["aria_context_brief"] = aria_brief

        # Prepend context brief to the event so engines include it in LLM prompts
        enriched_event = f"{aria_brief}\n\n---\nEVENT TO ANALYZE:\n{event}" if aria_brief else event

        # Run all engines in parallel with per-engine timeouts
        # Phase 1: Run implication + goal_impact in parallel
        async def _run_implications() -> tuple[list[JarvisInsight], list[Any]]:
            """Returns (insights, raw_implications) so butterfly can reuse."""
            insights: list[JarvisInsight] = []
            implications = await self._implication_engine.analyze_event(
                user_id=user_id,
                event=enriched_event,
                max_hops=1,
                include_neutral=False,
                min_score=0.4,
                skip_time_horizon=True,
            )
            for imp in implications[:5]:
                insight = await self._implication_engine.save_insight(
                    user_id=user_id,
                    implication=imp,
                )
                if insight:
                    insights.append(insight)
            return insights, implications

        async def _run_goal_impact() -> list[JarvisInsight]:
            insights: list[JarvisInsight] = []
            goal_impacts = await self._goal_impact_mapper.assess_event_impact(
                user_id=user_id,
                event=enriched_event,
            )
            for impact in goal_impacts[:3]:
                insights.append(self._goal_impact_to_insight(impact, event, user_id))
            return insights

        # Run implication and goal_impact in parallel
        impl_task = asyncio.ensure_future(
            asyncio.wait_for(
                _run_implications(),
                timeout=_PROCESS_EVENT_TIMEOUTS.get("implication", 15),
            )
        )
        goal_task = asyncio.ensure_future(
            asyncio.wait_for(
                _run_goal_impact(),
                timeout=_PROCESS_EVENT_TIMEOUTS.get("goal_impact", 5),
            )
        )

        impl_result: tuple[list[JarvisInsight], list[Any]] = ([], [])
        goal_result: list[JarvisInsight] = []

        results = await asyncio.gather(impl_task, goal_task, return_exceptions=True)

        if isinstance(results[0], Exception):
            logger.warning("Engine implication failed in process_event: %s", results[0])
        else:
            impl_result = results[0]
            all_insights.extend(impl_result[0])

        if isinstance(results[1], Exception):
            logger.warning("Engine goal_impact failed in process_event: %s", results[1])
        else:
            goal_result = results[1]
            all_insights.extend(goal_result)

        # Phase 2: Lightweight butterfly check using already-computed implications
        # (avoids re-running the full causal traversal)
        raw_implications = impl_result[1]
        if raw_implications:
            total_impact = sum(imp.impact_score for imp in raw_implications)
            if total_impact >= self._butterfly_detector.AMPLIFICATION_THRESHOLD:
                logger.info(
                    "Butterfly effect detected (amplification=%.1f)",
                    total_impact,
                )
                # Build a simple butterfly insight from the implication data
                combined_impact = sum(imp.combined_score for imp in raw_implications)
                cascade_depth = max(
                    (len(imp.causal_chain) for imp in raw_implications), default=0
                )
                all_insights.append(
                    JarvisInsight(
                        id=UUID("00000000-0000-0000-0000-000000000000"),
                        user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
                        insight_type="butterfly",
                        trigger_event=event[:200],
                        content=(
                            f"Butterfly effect detected: this event cascades through "
                            f"{len(raw_implications)} implications with "
                            f"{total_impact:.1f}x amplification. "
                            f"{raw_implications[0].content[:200]}"
                        ),
                        classification="threat"
                        if any(i.type.value == "threat" for i in raw_implications)
                        else "opportunity",
                        impact_score=min(total_impact / 10.0, 1.0),
                        confidence=sum(i.confidence for i in raw_implications)
                        / len(raw_implications),
                        urgency=0.8,
                        combined_score=min(combined_impact / 5.0, 1.0),
                        causal_chain=[],
                        affected_goals=list(
                            {g for imp in raw_implications for g in imp.affected_goals}
                        ),
                        recommended_actions=[],
                        status="new",
                        created_at=datetime.now(UTC),
                        updated_at=datetime.now(UTC),
                    )
                )

        # Enrich with time horizon categorization (lightweight, 5s timeout)
        try:
            async def _enrich_one(insight: JarvisInsight) -> None:
                if not insight.time_horizon:
                    horizon = await self._time_horizon_analyzer.analyze(
                        content=insight.content,
                        context=event,
                    )
                    if horizon:
                        insight.time_horizon = horizon.horizon
                        insight.time_to_impact = horizon.time_to_impact

            await asyncio.wait_for(
                asyncio.gather(*[_enrich_one(i) for i in all_insights], return_exceptions=True),
                timeout=_PROCESS_EVENT_TIMEOUTS.get("time_horizon", 5),
            )
        except asyncio.TimeoutError:
            logger.warning("Time horizon enrichment timed out")
        except Exception:
            logger.warning("Time horizon categorization failed", exc_info=True)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "process_event complete: %d insights in %.0fms",
            len(all_insights),
            elapsed_ms,
        )

        deduplicated = self._deduplicate(all_insights)
        # _deduplicate already sorts by confidence and caps at 5
        return deduplicated

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

    async def _run_engine_with_timeout(
        self,
        engine_name: str,
        user_id: str,
        context: dict[str, Any],
        timeout_s: int = _ENGINE_TIMEOUT_S,
    ) -> list[JarvisInsight]:
        """Run a single engine with timeout protection.

        Wraps _run_engine with asyncio.wait_for so one slow engine
        cannot block the entire pipeline.
        """
        try:
            return await asyncio.wait_for(
                self._run_engine(engine_name, user_id, context),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning("Engine %s timed out after %ds", engine_name, timeout_s)
            return []
        except Exception:
            logger.warning("Engine %s failed", engine_name, exc_info=True)
            return []

    async def _run_engine(
        self,
        engine_name: str,
        user_id: str,
        context: dict[str, Any],
    ) -> list[JarvisInsight]:
        """Run a single engine and return insights.

        Each engine call is best-effort; failures return empty list.
        """
        logger.info("[JARVIS] Engine %s starting", engine_name)

        # Helper: prepend ARIA context brief to an event string
        aria_brief = context.get("aria_context_brief", "")

        def _enrich(event_text: str) -> str:
            if aria_brief:
                return f"{aria_brief}\n\n---\nEVENT TO ANALYZE:\n{event_text}"
            return event_text

        if engine_name == "predictive":
            # Don't pass the raw dict as context — PredictiveEngine expects
            # a typed PredictionContext object. Passing None lets the engine
            # gather its own context via PredictionContextGatherer.
            predictions = await self._predictive_engine.generate_predictions(
                user_id=user_id,
                context=None,
            )
            return self._predictions_to_insights(predictions, user_id)

        if engine_name == "implication":
            # Analyze recent events from context or a default event
            events = context.get("recent_events", [])
            insights: list[JarvisInsight] = []
            for event_text in events[:3]:
                implications = await self._implication_engine.analyze_event(
                    user_id=user_id,
                    event=_enrich(event_text),
                    max_hops=2,
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
                    user_id=user_id, event=_enrich(event_text), max_hops=2
                )
                if butterfly:
                    saved = await self._butterfly_detector.save_butterfly_insight(
                        user_id=user_id, butterfly=butterfly
                    )
                    if saved:
                        insights.append(saved)
            return insights

        if engine_name == "connection":
            # Extract events from context dict — find_connections expects
            # events: list[str] | None, not a context dict.
            events = context.get("recent_events", context.get("new_events"))
            enriched_events = [_enrich(e) for e in events] if events else events
            connections = await self._connection_engine.find_connections(
                user_id=user_id,
                events=enriched_events,
            )
            return self._connections_to_insights(connections, user_id)

        if engine_name == "goal_impact":
            events = context.get("recent_events", context.get("new_events", []))
            insights = []
            for event_text in events[:3]:
                impacts = await self._goal_impact_mapper.assess_event_impact(
                    user_id=user_id, event=_enrich(event_text)
                )
                for impact in impacts[:2]:
                    insights.append(self._goal_impact_to_insight(impact, event_text, user_id))
            return insights

        if engine_name == "temporal":
            decisions = context.get("pending_decisions", [])
            insights = []
            for decision in decisions[:2]:
                analysis = await self._temporal_reasoner.analyze_decision(
                    user_id=user_id, decision=_enrich(decision)
                )
                if analysis:
                    insights.append(self._temporal_to_insight(analysis, decision, user_id))
            return insights

        return []

    def _deduplicate(self, insights: list[JarvisInsight]) -> list[JarvisInsight]:
        """Remove near-duplicate insights, keeping highest confidence per classification group.

        Groups insights by classification (threat/opportunity), deduplicates within
        each group using word-overlap similarity, limits to 3 per classification,
        and returns max 5 insights sorted by confidence.
        """
        if len(insights) <= 5:
            return insights

        # Group by classification
        groups: dict[str, list[JarvisInsight]] = {}
        for insight in insights:
            cls = insight.classification or "neutral"
            groups.setdefault(cls, []).append(insight)

        deduped: list[JarvisInsight] = []
        for cls, group_insights in groups.items():
            # Sort by confidence (combined_score) descending
            group_insights.sort(key=lambda x: x.combined_score, reverse=True)

            kept: list[JarvisInsight] = []
            for insight in group_insights:
                # Check if this is too similar to any already-kept insight
                is_duplicate = False
                for kept_insight in kept:
                    if self._content_similarity(insight.content, kept_insight.content) > 0.6:
                        is_duplicate = True
                        break

                if not is_duplicate:
                    kept.append(insight)
                    if len(kept) >= 3:  # Max 3 per classification
                        break

            deduped.extend(kept)

        # Final cap at 5, sorted by confidence
        deduped.sort(key=lambda x: x.combined_score, reverse=True)
        return deduped[:5]

    @staticmethod
    def _content_similarity(text1: str, text2: str) -> float:
        """Simple word-overlap similarity (Jaccard index).

        Returns a value between 0.0 (no overlap) and 1.0 (identical word sets).
        """
        if not text1 or not text2:
            return 0.0
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    def _predictions_to_insights(self, predictions: Any, user_id: str) -> list[JarvisInsight]:
        """Convert PredictiveEngine output to JarvisInsight objects."""
        insights: list[JarvisInsight] = []
        if not predictions:
            return insights

        items = predictions if isinstance(predictions, list) else [predictions]
        for pred in items:
            try:
                content = getattr(pred, "prediction_text", None) or getattr(pred, "description", str(pred))
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
                content = getattr(conn, "explanation", None) or getattr(conn, "description", str(conn))
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

    def _goal_impact_to_insight(
        self, impact: Any, event: str, user_id: str
    ) -> JarvisInsight:
        """Convert a GoalImpact to a JarvisInsight."""
        impact_type = getattr(impact, "impact_type", None)
        classification = "neutral"
        if impact_type:
            type_val = impact_type.value if hasattr(impact_type, "value") else str(impact_type)
            if type_val in ("accelerates", "creates_opportunity"):
                classification = "opportunity"
            elif type_val == "blocks":
                classification = "threat"

        impact_score = getattr(impact, "impact_score", 0.5)
        return JarvisInsight(
            id=UUID("00000000-0000-0000-0000-000000000000"),
            user_id=UUID(user_id) if isinstance(user_id, str) else user_id,
            insight_type="goal_impact",
            trigger_event=event[:200],
            content=getattr(impact, "explanation", str(impact)),
            classification=classification,
            impact_score=impact_score,
            confidence=0.7,
            urgency=0.5,
            combined_score=impact_score * 0.7,
            causal_chain=[],
            affected_goals=[getattr(impact, "goal_id", "")],
            recommended_actions=[],
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
