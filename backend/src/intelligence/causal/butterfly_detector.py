"""Butterfly Effect Detection for ARIA Phase 7 Jarvis Intelligence.

This detector identifies when small events will have large cascading impacts
by analyzing implications through the causal chain engine. Events with total
implication impact >3x the base event are flagged as butterfly effects.

Key features:
- Monitor incoming events for cascade potential
- Calculate amplification factor (sum of implication impact scores)
- Estimate time-to-impact for each cascade
- Generate early warning pulses (LOW/MEDIUM/HIGH/CRITICAL)
- Save butterfly insights to jarvis_insights table
"""

import logging
from typing import Any
from uuid import UUID

from src.intelligence.causal.implication_engine import ImplicationEngine
from src.intelligence.causal.models import (
    ButterflyEffect,
    Implication,
    WarningLevel,
)

logger = logging.getLogger(__name__)


class ButterflyDetector:
    """Detects butterfly effects where small events cause large cascades.

    A butterfly effect is detected when an event's downstream implications
    amplify significantly beyond the initial trigger. If the sum of
    implication impact scores exceeds 3x the base impact (1.0), it's
    flagged as a butterfly effect.

    Attributes:
        AMPLIFICATION_THRESHOLD: Minimum amplification (3.0) to flag as butterfly
    """

    AMPLIFICATION_THRESHOLD: float = 3.0

    def __init__(
        self,
        implication_engine: ImplicationEngine,
        db_client: Any,
        llm_client: Any,
    ) -> None:
        """Initialize the butterfly detector.

        Args:
            implication_engine: Engine for analyzing event implications
            db_client: Supabase client for insight persistence
            llm_client: LLM client (kept for potential future enhancements)
        """
        self._implication_engine = implication_engine
        self._db = db_client
        self._llm = llm_client

    async def detect(
        self,
        user_id: str,
        event: str,
        max_hops: int = 4,
    ) -> ButterflyEffect | None:
        """Detect if an event has butterfly effect potential.

        Algorithm:
        1. Analyze event through implication_engine.analyze_event()
        2. Calculate amplification_factor = sum(implication.impact_score)
        3. If amplification < 3.0, return None (not a butterfly)
        4. Find max cascade depth from all causal chains
        5. Estimate time to full cascade impact
        6. Determine warning level based on amplification
        7. Return ButterflyEffect object

        Args:
            user_id: User ID for goal context
            event: Description of the event to analyze
            max_hops: Maximum causal hops to traverse (1-6)

        Returns:
            ButterflyEffect if amplification >= 3.0, else None
        """
        logger.info(
            "Starting butterfly detection",
            extra={
                "user_id": user_id,
                "event_length": len(event),
                "max_hops": max_hops,
            },
        )

        # Step 1: Get implications from the event
        implications = await self._implication_engine.analyze_event(
            user_id=user_id,
            event=event,
            max_hops=max_hops,
            include_neutral=False,
            min_score=0.2,  # Lower threshold to capture more cascade effects
        )

        if not implications:
            logger.info("No implications found for butterfly detection")
            return None

        # Step 2: Calculate amplification (base event impact = 1.0)
        total_impact = sum(impl.impact_score for impl in implications)
        amplification_factor = total_impact  # Since base is 1.0

        logger.info(
            "Butterfly amplification calculated",
            extra={
                "user_id": user_id,
                "implications_count": len(implications),
                "total_impact": total_impact,
                "amplification_factor": amplification_factor,
            },
        )

        # Step 3: Check threshold
        if amplification_factor < self.AMPLIFICATION_THRESHOLD:
            logger.info(
                "Amplification below threshold, not a butterfly effect",
                extra={
                    "amplification": amplification_factor,
                    "threshold": self.AMPLIFICATION_THRESHOLD,
                },
            )
            return None

        # Step 4: Find max cascade depth
        max_depth = 0
        affected_goals: set[str] = set()

        for impl in implications:
            chain_depth = len(impl.causal_chain)
            if chain_depth > max_depth:
                max_depth = chain_depth
            affected_goals.update(impl.affected_goals)

        # Step 5: Estimate cascade time
        time_estimate = await self._estimate_cascade_time(implications)

        # Step 6: Calculate warning level
        warning_level = self._calculate_warning_level(amplification_factor)

        # Calculate combined impact score
        combined_impact_score = sum(impl.combined_score for impl in implications)

        # Build butterfly effect object
        butterfly = ButterflyEffect(
            trigger_event=event,
            amplification_factor=amplification_factor,
            cascade_depth=max_depth,
            time_to_full_impact=time_estimate,
            final_implications=[impl.content for impl in implications[:5]],
            warning_level=warning_level,
            affected_goal_count=len(affected_goals),
            combined_impact_score=combined_impact_score,
        )

        logger.info(
            "Butterfly effect detected",
            extra={
                "user_id": user_id,
                "amplification": amplification_factor,
                "warning_level": warning_level.value,
                "cascade_depth": max_depth,
                "affected_goals": len(affected_goals),
            },
        )

        return butterfly

    def _calculate_warning_level(self, amplification: float) -> WarningLevel:
        """Determine warning level from amplification factor.

        Warning levels are based on how much the cascade amplifies:
        - LOW: 3-5x amplification
        - MEDIUM: 5-7x amplification
        - HIGH: 7-10x amplification
        - CRITICAL: >10x amplification

        Args:
            amplification: The amplification factor

        Returns:
            WarningLevel enum value
        """
        if amplification >= 10.0:
            return WarningLevel.CRITICAL
        elif amplification >= 7.0:
            return WarningLevel.HIGH
        elif amplification >= 5.0:
            return WarningLevel.MEDIUM
        else:
            return WarningLevel.LOW

    async def _estimate_cascade_time(
        self,
        implications: list[Implication],
    ) -> str:
        """Estimate time until full cascade impact.

        Uses weighted average of urgency scores converted to time estimates.
        Higher urgency implies shorter time to full impact.

        Args:
            implications: List of implications to analyze

        Returns:
            Human-readable time estimate string
        """
        if not implications:
            return "Unknown"

        # Weight by impact score
        total_weight = sum(impl.impact_score for impl in implications)
        if total_weight == 0:
            return "Unknown"

        # Calculate weighted urgency (higher urgency = shorter time)
        weighted_urgency = (
            sum(impl.urgency * impl.impact_score for impl in implications) / total_weight
        )

        # Convert urgency (0-1) to time estimate
        if weighted_urgency >= 0.8:
            return "Hours to days"
        elif weighted_urgency >= 0.6:
            return "1-2 weeks"
        elif weighted_urgency >= 0.4:
            return "2-4 weeks"
        elif weighted_urgency >= 0.2:
            return "1-2 months"
        else:
            return "2+ months"

    async def save_butterfly_insight(
        self,
        user_id: str,
        butterfly: ButterflyEffect,
    ) -> UUID | None:
        """Save butterfly effect to jarvis_insights table.

        Persists the detected butterfly effect for later retrieval and
        user engagement tracking.

        Args:
            user_id: User ID
            butterfly: Detected butterfly effect to save

        Returns:
            UUID of saved insight, or None if save failed
        """
        try:
            data = {
                "user_id": user_id,
                "insight_type": "butterfly_effect",
                "trigger_event": butterfly.trigger_event,
                "content": (
                    f"Butterfly effect detected: {butterfly.amplification_factor:.1f}x "
                    f"amplification across {butterfly.cascade_depth} cascade levels. "
                    f"Warning level: {butterfly.warning_level.value}"
                ),
                "classification": "butterfly_effect",
                "impact_score": min(butterfly.amplification_factor / 10.0, 1.0),  # Normalize to 0-1
                "confidence": 0.8,  # Default confidence for butterfly detection
                "urgency": (
                    0.9
                    if butterfly.warning_level in [WarningLevel.HIGH, WarningLevel.CRITICAL]
                    else 0.6
                ),
                "combined_score": (
                    butterfly.combined_impact_score / len(butterfly.final_implications)
                    if butterfly.final_implications
                    else 0.5
                ),
                "causal_chain": [],  # Butterfly effects don't have a single chain
                "affected_goals": [],
                "recommended_actions": [
                    f"Monitor cascade effects over {butterfly.time_to_full_impact}",
                    "Review affected goals for action items",
                ],
                "status": "new",
            }

            result = self._db.table("jarvis_insights").insert(data).execute()

            if result.data and len(result.data) > 0:
                insight_id = UUID(result.data[0]["id"])
                logger.info(
                    "Saved butterfly insight to database",
                    extra={
                        "insight_id": str(insight_id),
                        "user_id": user_id,
                        "warning_level": butterfly.warning_level.value,
                    },
                )
                return insight_id

            return None

        except Exception:
            logger.exception(
                "Failed to save butterfly insight",
                extra={"user_id": user_id},
            )
            return None
