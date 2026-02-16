"""Metacognition module for ARIA companion.

This module implements ARIA's ability to assess what she knows and doesn't know,
acknowledge uncertainty appropriately, and calibrate confidence based on track record.

Key features:
- KnowledgeAssessment dataclass: captures confidence, source, and reliability
- MetacognitionService: assesses knowledge from memory and calibration history
- Uncertainty acknowledgment: generates appropriate phrases for low confidence
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, cast

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class KnowledgeSource(str, Enum):
    """Source of ARIA's knowledge on a topic."""

    MEMORY = "memory"  # Directly retrieved from memory with high confidence
    INFERENCE = "inference"  # Inferred from related facts
    UNCERTAIN = "uncertain"  # No reliable information available
    EXTERNAL = "external"  # From external API/research


# Confidence thresholds
RESEARCH_THRESHOLD = 0.5  # Below this, suggest research
HIGH_CONFIDENCE_THRESHOLD = 0.8  # Above this, no uncertainty acknowledgment needed


@dataclass
class KnowledgeAssessment:
    """Assessment of ARIA's knowledge on a specific topic.

    Contains confidence level, source tracking, and recommendations
    for when research is needed.
    """

    topic: str
    confidence: float  # 0.0-1.0
    knowledge_source: KnowledgeSource
    last_updated: datetime
    reliability_notes: str
    should_research: bool
    fact_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize assessment to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "topic": self.topic,
            "confidence": self.confidence,
            "knowledge_source": self.knowledge_source.value,
            "last_updated": self.last_updated.isoformat(),
            "reliability_notes": self.reliability_notes,
            "should_research": self.should_research,
            "fact_count": self.fact_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeAssessment":
        """Create a KnowledgeAssessment from a dictionary.

        Args:
            data: Dictionary containing assessment data.

        Returns:
            KnowledgeAssessment instance.
        """
        last_updated = data.get("last_updated")
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        elif last_updated is None:
            last_updated = datetime.now(UTC)

        return cls(
            topic=data["topic"],
            confidence=data["confidence"],
            knowledge_source=KnowledgeSource(data.get("knowledge_source", "uncertain")),
            last_updated=last_updated,
            reliability_notes=data.get("reliability_notes", ""),
            should_research=data.get("should_research", False),
            fact_count=data.get("fact_count", 0),
        )


@dataclass
class TopicExtraction:
    """Result of extracting topics from a message."""

    topics: list[str] = field(default_factory=list)
    processing_time_ms: float = 0.0


class MetacognitionService:
    """Service for assessing ARIA's knowledge confidence on topics.

    This service handles:
    - Searching memory for facts about topics
    - Calculating confidence based on fact quality and recency
    - Adjusting confidence based on calibration history
    - Generating uncertainty acknowledgments
    - Caching assessments for quick retrieval
    """

    def __init__(
        self,
        db_client: Any = None,
        llm_client: Any = None,
    ) -> None:
        """Initialize the Metacognition service.

        Args:
            db_client: Optional Supabase client (will create if not provided).
            llm_client: Optional LLM client (will create if not provided).
        """
        self._db = db_client or SupabaseClient.get_client()
        self._llm = llm_client or LLMClient()

    async def assess_knowledge(
        self,
        user_id: str,
        topic: str,
    ) -> KnowledgeAssessment:
        """Assess ARIA's knowledge confidence on a specific topic.

        Steps:
        1. Search memory_semantic for facts matching topic
        2. Calculate avg confidence from matching facts
        3. Factor in recency (weight by updated_at)
        4. Query prediction_calibration for topic-area accuracy
        5. Adjust confidence based on track record
        6. Determine knowledge_source
        7. Cache result in metacognition_assessments table
        8. Return KnowledgeAssessment

        Args:
            user_id: User identifier.
            topic: Topic to assess knowledge about.

        Returns:
            KnowledgeAssessment with confidence and recommendations.
        """
        # 1. Search for facts in memory_semantic
        facts = await self._search_facts(user_id, topic)
        fact_count = len(facts)

        # 2. Calculate base confidence from facts
        if fact_count == 0:
            base_confidence = 0.0
            knowledge_source = KnowledgeSource.UNCERTAIN
            reliability_notes = "No relevant facts found in memory."
        else:
            # Weight facts by confidence and recency
            weighted_confidence = self._calculate_weighted_confidence(facts)
            base_confidence = weighted_confidence

            # Determine source based on fact quality
            if fact_count >= 3 and base_confidence >= 0.7:
                knowledge_source = KnowledgeSource.MEMORY
                reliability_notes = (
                    f"Based on {fact_count} facts with average confidence {base_confidence:.2f}."
                )
            elif fact_count >= 1 and base_confidence >= 0.4:
                knowledge_source = KnowledgeSource.INFERENCE
                reliability_notes = (
                    f"Inferred from {fact_count} related facts. Some gaps in knowledge."
                )
            else:
                knowledge_source = KnowledgeSource.UNCERTAIN
                reliability_notes = f"Limited information: {fact_count} facts with low confidence."

        # 3. Get calibration adjustment
        calibration_multiplier = await self._get_calibration_multiplier(user_id, topic)
        adjusted_confidence = base_confidence * calibration_multiplier

        # Cap at 1.0
        adjusted_confidence = min(1.0, adjusted_confidence)

        # 4. Determine if research is needed
        should_research = adjusted_confidence < RESEARCH_THRESHOLD

        # 5. Build assessment
        assessment = KnowledgeAssessment(
            topic=topic,
            confidence=adjusted_confidence,
            knowledge_source=knowledge_source,
            last_updated=datetime.now(UTC),
            reliability_notes=reliability_notes,
            should_research=should_research,
            fact_count=fact_count,
        )

        # 6. Cache in database
        await self._cache_assessment(user_id, assessment)

        logger.debug(
            "Assessed knowledge for topic '%s': confidence=%.2f, source=%s, facts=%d",
            topic,
            adjusted_confidence,
            knowledge_source.value,
            fact_count,
        )

        return assessment

    async def assess_topics(
        self,
        user_id: str,
        message: str,
    ) -> dict[str, KnowledgeAssessment]:
        """Assess knowledge on multiple topics extracted from a message.

        Uses LLM to extract key topics (max 5), then assesses each.

        Args:
            user_id: User identifier.
            message: Message to extract topics from.

        Returns:
            Dict mapping topic to KnowledgeAssessment.
        """
        # Extract topics using LLM
        extraction = await self._extract_topics(message)
        topics = extraction.topics[:5]  # Limit to 5 topics

        # Assess each topic
        assessments: dict[str, KnowledgeAssessment] = {}
        for topic in topics:
            assessments[topic] = await self.assess_knowledge(user_id, topic)

        return assessments

    def acknowledge_uncertainty(
        self,
        assessment: KnowledgeAssessment,
    ) -> str | None:
        """Generate appropriate uncertainty acknowledgment.

        Returns None if confidence is high enough (no acknowledgment needed).

        Args:
            assessment: KnowledgeAssessment to generate acknowledgment for.

        Returns:
            Uncertainty acknowledgment string, or None if not needed.
        """
        if assessment.confidence >= HIGH_CONFIDENCE_THRESHOLD:
            return None

        if assessment.confidence < 0.3:
            return "I don't have reliable information on this. Let me research it."
        if assessment.confidence < 0.5:
            return "I have preliminary information, but please verify before relying on it."
        if assessment.confidence < 0.7:
            return "Based on what I know, though you should verify:"

        # 0.7-0.8: mild acknowledgment
        return "I'm fairly confident, but:"

    async def get_cached_assessment(
        self,
        user_id: str,
        topic: str,
    ) -> KnowledgeAssessment | None:
        """Get a cached assessment if available and recent.

        Args:
            user_id: User identifier.
            topic: Topic to get cached assessment for.

        Returns:
            Cached KnowledgeAssessment or None if not found/stale.
        """
        try:
            result = (
                self._db.table("metacognition_assessments")
                .select("*")
                .eq("user_id", user_id)
                .eq("topic", topic)
                .single()
                .execute()
            )

            if not result.data:
                return None

            return KnowledgeAssessment.from_dict(cast(dict[str, Any], result.data))

        except Exception as e:
            logger.warning(
                "Failed to get cached assessment",
                extra={"user_id": user_id, "topic": topic, "error": str(e)},
            )
            return None

    async def get_calibration(
        self,
        user_id: str,
        topic_area: str,
    ) -> dict[str, Any] | None:
        """Get calibration statistics for a topic area.

        Args:
            user_id: User identifier.
            topic_area: Topic area to get calibration for.

        Returns:
            Calibration stats dict or None if not available.
        """
        try:
            # Map topic to prediction type
            prediction_type = self._map_topic_to_prediction_type(topic_area)

            result = (
                self._db.table("prediction_calibration")
                .select("*")
                .eq("user_id", user_id)
                .eq("prediction_type", prediction_type)
                .execute()
            )

            if not result.data:
                return None

            # Calculate overall accuracy - cast rows to dict
            rows = cast(list[dict[str, Any]], result.data)
            total = sum(row.get("total_predictions", 0) for row in rows)
            correct = sum(row.get("correct_predictions", 0) for row in rows)

            if total == 0:
                return None

            accuracy = correct / total

            return {
                "prediction_type": prediction_type,
                "total_predictions": total,
                "correct_predictions": correct,
                "accuracy": accuracy,
                "buckets": rows,
            }

        except Exception as e:
            logger.warning(
                "Failed to get calibration",
                extra={"user_id": user_id, "topic_area": topic_area, "error": str(e)},
            )
            return None

    # ── Private Methods ─────────────────────────────────────────────────────

    async def _search_facts(
        self,
        user_id: str,
        topic: str,
    ) -> list[dict[str, Any]]:
        """Search memory_semantic for facts about a topic.

        Args:
            user_id: User identifier.
            topic: Topic to search for.

        Returns:
            List of fact dictionaries with confidence and metadata.
        """
        try:
            # Use ILIKE for case-insensitive search
            result = (
                self._db.table("memory_semantic")
                .select("*")
                .eq("user_id", user_id)
                .ilike("fact", f"%{topic}%")
                .limit(20)
                .execute()
            )

            return cast(list[dict[str, Any]], result.data or [])

        except Exception as e:
            logger.warning(
                "Failed to search facts",
                extra={"user_id": user_id, "topic": topic, "error": str(e)},
            )
            return []

    def _calculate_weighted_confidence(
        self,
        facts: list[dict[str, Any]],
    ) -> float:
        """Calculate weighted confidence from facts.

        Weights by confidence and recency (more recent = higher weight).

        Args:
            facts: List of fact dictionaries.

        Returns:
            Weighted confidence score (0.0-1.0).
        """
        if not facts:
            return 0.0

        now = datetime.now(UTC)
        total_weight = 0.0
        weighted_sum = 0.0

        for fact in facts:
            # Get fact confidence
            fact_confidence = fact.get("confidence", 0.5)

            # Calculate recency weight (newer facts weighted higher)
            updated_at_str = fact.get("updated_at") or fact.get("created_at")
            if updated_at_str:
                try:
                    updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                    age_days = (now - updated_at).days
                    # Decay weight: 1.0 at 0 days, 0.5 at 30 days, 0.25 at 90 days
                    recency_weight = 1.0 / (1.0 + age_days / 30.0)
                except (ValueError, TypeError):
                    recency_weight = 0.5
            else:
                recency_weight = 0.5

            # Combined weight
            weight = recency_weight
            weighted_sum += fact_confidence * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        return weighted_sum / total_weight

    async def _get_calibration_multiplier(
        self,
        user_id: str,
        topic: str,
    ) -> float:
        """Get confidence multiplier based on calibration history.

        If ARIA has been over/under-confident in this area before,
        adjust accordingly.

        Args:
            user_id: User identifier.
            topic: Topic to get calibration for.

        Returns:
            Confidence multiplier (0.5-1.5).
        """
        try:
            calibration = await self.get_calibration(user_id, topic)

            if not calibration:
                return 1.0  # No calibration data, no adjustment

            accuracy = calibration.get("accuracy", 0.5)
            total = calibration.get("total_predictions", 0)

            # Need at least 5 predictions for reliable calibration
            if total < 5:
                return 1.0

            # If accuracy is below expected (0.5), reduce confidence
            # If accuracy is above, slightly boost (but cap)
            multiplier = (
                0.5 + accuracy  # 0.5-1.0 range
                if accuracy < 0.5
                else min(1.2, 0.8 + accuracy * 0.4)
            )

            return float(multiplier)

        except Exception as e:
            logger.warning(
                "Failed to get calibration multiplier",
                extra={"user_id": user_id, "topic": topic, "error": str(e)},
            )
            return 1.0

    async def _cache_assessment(
        self,
        user_id: str,
        assessment: KnowledgeAssessment,
    ) -> None:
        """Cache assessment in database.

        Args:
            user_id: User identifier.
            assessment: Assessment to cache.
        """
        try:
            self._db.table("metacognition_assessments").upsert(
                {
                    "user_id": user_id,
                    "topic": assessment.topic,
                    "confidence": assessment.confidence,
                    "knowledge_source": assessment.knowledge_source.value,
                    "last_updated": assessment.last_updated.isoformat(),
                    "reliability_notes": assessment.reliability_notes,
                    "should_research": assessment.should_research,
                    "fact_count": assessment.fact_count,
                },
                on_conflict="user_id,topic",
            ).execute()

        except Exception as e:
            logger.warning(
                "Failed to cache assessment",
                extra={
                    "user_id": user_id,
                    "topic": assessment.topic,
                    "error": str(e),
                },
            )

    async def _extract_topics(self, message: str) -> TopicExtraction:
        """Extract key topics from a message using LLM.

        Args:
            message: Message to extract topics from.

        Returns:
            TopicExtraction with list of topics.
        """
        import time

        start = time.monotonic()

        prompt = f"""Extract the key topics (entities, concepts, or subjects) from this message.
Return ONLY a JSON array of 1-5 topic strings, nothing else.

Message: {message[:1000]}

Topics (JSON array):"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=100,
            )

            # Parse JSON array
            import json

            content = response.strip()
            # Handle potential markdown code blocks
            if content.startswith("```"):
                content = content.split("\n", 1)[1]  # Remove first line
                content = content.rsplit("```", 1)[0]  # Remove closing

            topics = json.loads(content)

            # Validate all items are strings
            topics = [str(t) for t in topics if t] if isinstance(topics, list) else []

            elapsed_ms = (time.monotonic() - start) * 1000

            return TopicExtraction(
                topics=topics[:5],
                processing_time_ms=elapsed_ms,
            )

        except Exception as e:
            logger.warning(
                "Failed to extract topics: %s (input: %s)",
                str(e),
                message[:100],
            )
            return TopicExtraction(topics=[], processing_time_ms=0)

    def _map_topic_to_prediction_type(self, topic: str) -> str:
        """Map a topic to a prediction type for calibration lookup.

        Args:
            topic: Topic string.

        Returns:
            Prediction type string.
        """
        topic_lower = topic.lower()

        # Map common topics to prediction types
        if any(word in topic_lower for word in ["deal", "opportunity", "pipeline"]):
            return "deal_outcome"
        if any(word in topic_lower for word in ["meeting", "call", "demo"]):
            return "meeting_outcome"
        if any(word in topic_lower for word in ["email", "response", "reply"]):
            return "lead_response"
        if any(word in topic_lower for word in ["market", "competitor", "industry"]):
            return "market_signal"
        if any(word in topic_lower for word in ["timing", "deadline", "date"]):
            return "timing"

        # Default
        return "external_event"
