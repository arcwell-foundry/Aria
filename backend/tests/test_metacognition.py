"""Tests for Metacognition module."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.companion.metacognition import (
    HIGH_CONFIDENCE_THRESHOLD,
    RESEARCH_THRESHOLD,
    KnowledgeAssessment,
    KnowledgeSource,
    MetacognitionService,
    TopicExtraction,
)


# ── Enum Tests ────────────────────────────────────────────────────────────────


def test_knowledge_source_enum_values() -> None:
    """Test KnowledgeSource enum has expected values."""
    assert KnowledgeSource.MEMORY.value == "memory"
    assert KnowledgeSource.INFERENCE.value == "inference"
    assert KnowledgeSource.UNCERTAIN.value == "uncertain"
    assert KnowledgeSource.EXTERNAL.value == "external"


# ── KnowledgeAssessment Tests ─────────────────────────────────────────────────


def test_knowledge_assessment_creation() -> None:
    """Test KnowledgeAssessment creation with valid data."""
    assessment = KnowledgeAssessment(
        topic="WuXi pricing",
        confidence=0.75,
        knowledge_source=KnowledgeSource.MEMORY,
        last_updated=datetime.now(UTC),
        reliability_notes="Based on 5 facts with average confidence 0.82.",
        should_research=False,
        fact_count=5,
    )

    assert assessment.topic == "WuXi pricing"
    assert assessment.confidence == 0.75
    assert assessment.knowledge_source == KnowledgeSource.MEMORY
    assert assessment.should_research is False
    assert assessment.fact_count == 5


def test_knowledge_assessment_to_dict() -> None:
    """Test KnowledgeAssessment.to_dict serializes correctly."""
    now = datetime.now(UTC)
    assessment = KnowledgeAssessment(
        topic="Lonza capabilities",
        confidence=0.6,
        knowledge_source=KnowledgeSource.INFERENCE,
        last_updated=now,
        reliability_notes="Inferred from related facts.",
        should_research=False,
        fact_count=2,
    )

    data = assessment.to_dict()

    assert data["topic"] == "Lonza capabilities"
    assert data["confidence"] == 0.6
    assert data["knowledge_source"] == "inference"
    assert data["reliability_notes"] == "Inferred from related facts."
    assert data["should_research"] is False
    assert data["fact_count"] == 2


def test_knowledge_assessment_from_dict() -> None:
    """Test KnowledgeAssessment.from_dict creates correct instance."""
    now = datetime.now(UTC)
    data = {
        "topic": "Catalent news",
        "confidence": 0.3,
        "knowledge_source": "uncertain",
        "last_updated": now.isoformat(),
        "reliability_notes": "No relevant facts found.",
        "should_research": True,
        "fact_count": 0,
    }

    assessment = KnowledgeAssessment.from_dict(data)

    assert assessment.topic == "Catalent news"
    assert assessment.confidence == 0.3
    assert assessment.knowledge_source == KnowledgeSource.UNCERTAIN
    assert assessment.should_research is True
    assert assessment.fact_count == 0


# ── Uncertainty Acknowledgment Tests ──────────────────────────────────────────


class TestUncertaintyAcknowledgment:
    """Tests for uncertainty acknowledgment generation."""

    def test_no_acknowledgment_for_high_confidence(self) -> None:
        """High confidence (>= 0.8) should return None."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        assessment = KnowledgeAssessment(
            topic="Test topic",
            confidence=0.85,
            knowledge_source=KnowledgeSource.MEMORY,
            last_updated=datetime.now(UTC),
            reliability_notes="",
            should_research=False,
            fact_count=5,
        )

        result = service.acknowledge_uncertainty(assessment)
        assert result is None

    def test_acknowledgment_for_very_low_confidence(self) -> None:
        """Very low confidence (< 0.3) should return research message."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        assessment = KnowledgeAssessment(
            topic="Test topic",
            confidence=0.2,
            knowledge_source=KnowledgeSource.UNCERTAIN,
            last_updated=datetime.now(UTC),
            reliability_notes="",
            should_research=True,
            fact_count=0,
        )

        result = service.acknowledge_uncertainty(assessment)
        assert result is not None
        assert "don't have reliable" in result.lower()
        assert "research" in result.lower()

    def test_acknowledgment_for_low_confidence(self) -> None:
        """Low confidence (0.3-0.5) should return preliminary warning."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        assessment = KnowledgeAssessment(
            topic="Test topic",
            confidence=0.4,
            knowledge_source=KnowledgeSource.INFERENCE,
            last_updated=datetime.now(UTC),
            reliability_notes="",
            should_research=True,
            fact_count=1,
        )

        result = service.acknowledge_uncertainty(assessment)
        assert result is not None
        assert "preliminary" in result.lower() or "verify" in result.lower()

    def test_acknowledgment_for_medium_confidence(self) -> None:
        """Medium confidence (0.5-0.7) should return verification suggestion."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        assessment = KnowledgeAssessment(
            topic="Test topic",
            confidence=0.6,
            knowledge_source=KnowledgeSource.INFERENCE,
            last_updated=datetime.now(UTC),
            reliability_notes="",
            should_research=False,
            fact_count=2,
        )

        result = service.acknowledge_uncertainty(assessment)
        assert result is not None
        assert "verify" in result.lower()

    def test_acknowledgment_for_moderate_confidence(self) -> None:
        """Moderate confidence (0.7-0.8) should return mild acknowledgment."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        assessment = KnowledgeAssessment(
            topic="Test topic",
            confidence=0.75,
            knowledge_source=KnowledgeSource.MEMORY,
            last_updated=datetime.now(UTC),
            reliability_notes="",
            should_research=False,
            fact_count=3,
        )

        result = service.acknowledge_uncertainty(assessment)
        assert result is not None
        assert "confident" in result.lower() or "but:" in result.lower()


# ── Knowledge Assessment Tests ────────────────────────────────────────────────


class TestAssessKnowledge:
    """Tests for knowledge assessment."""

    @pytest.mark.asyncio
    async def test_high_confidence_with_many_facts(self) -> None:
        """Many high-confidence facts should result in high confidence."""
        # Mock table operations
        mock_table = MagicMock()

        # Mock fact search - return 5 high-confidence facts
        mock_table.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "fact": "WuXi AppTec pricing is competitive",
                    "confidence": 0.9,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                {
                    "fact": "WuXi offers volume discounts",
                    "confidence": 0.85,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                {
                    "fact": "WuXi pricing increased 5% in 2025",
                    "confidence": 0.8,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                {
                    "fact": "WuXi provides tiered pricing",
                    "confidence": 0.75,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
                {
                    "fact": "WuXi offers early payment discounts",
                    "confidence": 0.7,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            ]
        )

        # Mock calibration lookup - return None (no calibration data)
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        # Mock upsert for caching
        mock_table.upsert.return_value.execute.return_value = MagicMock(data=[{}])

        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        service = MetacognitionService(
            db_client=mock_db,
            llm_client=MagicMock(),
        )

        assessment = await service.assess_knowledge("user-123", "WuXi pricing")

        assert assessment.fact_count == 5
        assert assessment.confidence >= 0.5
        assert assessment.knowledge_source in [
            KnowledgeSource.MEMORY,
            KnowledgeSource.INFERENCE,
        ]
        assert assessment.should_research is False

    @pytest.mark.asyncio
    async def test_low_confidence_no_facts(self) -> None:
        """No facts should result in uncertain source and research needed."""
        mock_table = MagicMock()

        # Mock empty fact search
        mock_table.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        service = MetacognitionService(
            db_client=mock_db,
            llm_client=MagicMock(),
        )

        assessment = await service.assess_knowledge("user-123", "Unknown topic")

        assert assessment.fact_count == 0
        assert assessment.confidence == 0.0
        assert assessment.knowledge_source == KnowledgeSource.UNCERTAIN
        assert assessment.should_research is True

    @pytest.mark.asyncio
    async def test_calibration_adjustment(self) -> None:
        """Confidence should be adjusted based on calibration history."""
        # Test the calibration multiplier directly
        mock_table = MagicMock()

        # Mock calibration with poor accuracy
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "prediction_type": "deal_outcome",
                    "confidence_bucket": 0.7,
                    "total_predictions": 10,
                    "correct_predictions": 3,  # 30% accuracy - should reduce confidence
                }
            ]
        )

        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        service = MetacognitionService(
            db_client=mock_db,
            llm_client=MagicMock(),
        )

        # Get calibration multiplier - should be less than 1.0 for poor accuracy
        multiplier = await service._get_calibration_multiplier("user-123", "deal pricing")

        # With 30% accuracy, multiplier should be around 0.8 (0.5 + 0.3)
        assert multiplier < 1.0
        assert multiplier >= 0.5


# ── Topic Extraction Tests ────────────────────────────────────────────────────


class TestTopicExtraction:
    """Tests for topic extraction from messages."""

    @pytest.mark.asyncio
    async def test_extract_topics_from_message(self) -> None:
        """LLM should extract key topics from message."""
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(
            return_value='["WuXi AppTec", "pricing", "CDMO"]'
        )

        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=mock_llm,
        )

        extraction = await service._extract_topics(
            "What do you know about WuXi AppTec's pricing for CDMO services?"
        )

        assert len(extraction.topics) == 3
        assert "WuXi AppTec" in extraction.topics
        assert "pricing" in extraction.topics
        assert "CDMO" in extraction.topics

    @pytest.mark.asyncio
    async def test_extract_topics_handles_markdown(self) -> None:
        """Topic extraction should handle markdown code blocks."""
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(
            return_value='```json\n["Lonza", "manufacturing"]\n```'
        )

        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=mock_llm,
        )

        extraction = await service._extract_topics("Tell me about Lonza manufacturing")

        assert len(extraction.topics) == 2
        assert "Lonza" in extraction.topics

    @pytest.mark.asyncio
    async def test_extract_topics_handles_invalid_json(self) -> None:
        """Topic extraction should handle invalid JSON gracefully."""
        mock_llm = MagicMock()
        # Return something that can't be parsed as JSON array
        mock_llm.generate_response = AsyncMock(return_value="This is not valid JSON at all")

        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=mock_llm,
        )

        extraction = await service._extract_topics("Some message")

        # Should return empty list on JSON parse error
        assert extraction.topics == []
        assert isinstance(extraction.topics, list)


# ── Caching Tests ─────────────────────────────────────────────────────────────


class TestCaching:
    """Tests for assessment caching."""

    @pytest.mark.asyncio
    async def test_cache_assessment(self) -> None:
        """Assessment should be cached in database."""
        mock_table = MagicMock()
        mock_table.upsert.return_value.execute.return_value = MagicMock(data=[{}])

        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        service = MetacognitionService(
            db_client=mock_db,
            llm_client=MagicMock(),
        )

        assessment = KnowledgeAssessment(
            topic="Test topic",
            confidence=0.75,
            knowledge_source=KnowledgeSource.MEMORY,
            last_updated=datetime.now(UTC),
            reliability_notes="Test notes",
            should_research=False,
            fact_count=3,
        )

        await service._cache_assessment("user-123", assessment)

        mock_table.upsert.assert_called_once()
        call_args = mock_table.upsert.call_args[0][0]
        assert call_args["user_id"] == "user-123"
        assert call_args["topic"] == "Test topic"
        assert call_args["confidence"] == 0.75

    @pytest.mark.asyncio
    async def test_get_cached_assessment(self) -> None:
        """Cached assessment should be retrievable."""
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "topic": "Cached topic",
                "confidence": 0.65,
                "knowledge_source": "inference",
                "last_updated": datetime.now(UTC).isoformat(),
                "reliability_notes": "Cached notes",
                "should_research": False,
                "fact_count": 2,
            }
        )

        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        service = MetacognitionService(
            db_client=mock_db,
            llm_client=MagicMock(),
        )

        cached = await service.get_cached_assessment("user-123", "Cached topic")

        assert cached is not None
        assert cached.topic == "Cached topic"
        assert cached.confidence == 0.65
        assert cached.knowledge_source == KnowledgeSource.INFERENCE

    @pytest.mark.asyncio
    async def test_get_cached_assessment_not_found(self) -> None:
        """Should return None if no cached assessment exists."""
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )

        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        service = MetacognitionService(
            db_client=mock_db,
            llm_client=MagicMock(),
        )

        cached = await service.get_cached_assessment("user-123", "Unknown topic")

        assert cached is None


# ── Weighted Confidence Tests ─────────────────────────────────────────────────


class TestWeightedConfidence:
    """Tests for weighted confidence calculation."""

    def test_weighted_confidence_recency(self) -> None:
        """More recent facts should have higher weight."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        now = datetime.now(UTC)

        # Mix old and new facts with different confidence levels
        # New fact with lower confidence should still contribute meaningfully
        old_fact = {
            "confidence": 0.9,
            "updated_at": (now - timedelta(days=90)).isoformat(),
        }
        new_fact = {
            "confidence": 0.6,
            "updated_at": now.isoformat(),
        }

        # Combined weighted confidence
        confidence_mixed = service._calculate_weighted_confidence([old_fact, new_fact])

        # Confidence should be between 0.6 and 0.9
        # But the newer fact should pull it closer to 0.6 due to higher recency weight
        assert 0.6 <= confidence_mixed <= 0.9

        # Pure old fact should have lower effective weight
        confidence_old_only = service._calculate_weighted_confidence([old_fact])
        # Pure new fact
        confidence_new_only = service._calculate_weighted_confidence([new_fact])

        # Both should return their base confidence (single fact, weight cancels)
        # But with mixed facts, newer should have more influence
        # With 0.9 old (weight ~0.25) and 0.6 new (weight 1.0):
        # weighted = (0.9*0.25 + 0.6*1.0) / (0.25 + 1.0) = 0.825/1.25 = 0.66
        assert confidence_mixed < 0.9  # Should be pulled down by newer lower-confidence fact

    def test_weighted_confidence_empty(self) -> None:
        """Empty facts should return 0."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        confidence = service._calculate_weighted_confidence([])
        assert confidence == 0.0

    def test_weighted_confidence_average(self) -> None:
        """Weighted confidence should be reasonable average."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        facts = [
            {"confidence": 0.8, "updated_at": datetime.now(UTC).isoformat()},
            {"confidence": 0.6, "updated_at": datetime.now(UTC).isoformat()},
        ]

        confidence = service._calculate_weighted_confidence(facts)

        # Should be between 0.6 and 0.8
        assert 0.6 <= confidence <= 0.8


# ── Topic Mapping Tests ───────────────────────────────────────────────────────


class TestTopicMapping:
    """Tests for topic to prediction type mapping."""

    def test_map_deal_topic(self) -> None:
        """Deal-related topics should map to deal_outcome."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        assert service._map_topic_to_prediction_type("deal pricing") == "deal_outcome"
        assert service._map_topic_to_prediction_type("opportunity stage") == "deal_outcome"
        assert service._map_topic_to_prediction_type("pipeline status") == "deal_outcome"

    def test_map_meeting_topic(self) -> None:
        """Meeting-related topics should map to meeting_outcome."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        assert service._map_topic_to_prediction_type("meeting notes") == "meeting_outcome"
        assert service._map_topic_to_prediction_type("demo schedule") == "meeting_outcome"
        assert service._map_topic_to_prediction_type("call outcome") == "meeting_outcome"

    def test_map_market_topic(self) -> None:
        """Market-related topics should map to market_signal."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        assert service._map_topic_to_prediction_type("market trends") == "market_signal"
        assert service._map_topic_to_prediction_type("competitor news") == "market_signal"
        assert service._map_topic_to_prediction_type("industry analysis") == "market_signal"

    def test_map_default_topic(self) -> None:
        """Unknown topics should default to external_event."""
        service = MetacognitionService(
            db_client=MagicMock(),
            llm_client=MagicMock(),
        )

        assert service._map_topic_to_prediction_type("random topic") == "external_event"
        assert service._map_topic_to_prediction_type("unknown concept") == "external_event"


# ── Calibration Integration Tests ─────────────────────────────────────────────


class TestCalibrationIntegration:
    """Tests for calibration multiplier calculations."""

    @pytest.mark.asyncio
    async def test_calibration_multiplier_no_data(self) -> None:
        """No calibration data should return 1.0 multiplier."""
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )

        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        service = MetacognitionService(
            db_client=mock_db,
            llm_client=MagicMock(),
        )

        multiplier = await service._get_calibration_multiplier("user-123", "test topic")
        assert multiplier == 1.0

    @pytest.mark.asyncio
    async def test_calibration_multiplier_insufficient_data(self) -> None:
        """Less than 5 predictions should return 1.0 multiplier."""
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "total_predictions": 3,
                    "correct_predictions": 2,
                }
            ]
        )

        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        service = MetacognitionService(
            db_client=mock_db,
            llm_client=MagicMock(),
        )

        multiplier = await service._get_calibration_multiplier("user-123", "test topic")
        assert multiplier == 1.0

    @pytest.mark.asyncio
    async def test_calibration_multiplier_poor_accuracy(self) -> None:
        """Poor accuracy should reduce confidence multiplier."""
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "total_predictions": 10,
                    "correct_predictions": 3,  # 30% accuracy
                }
            ]
        )

        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        service = MetacognitionService(
            db_client=mock_db,
            llm_client=MagicMock(),
        )

        multiplier = await service._get_calibration_multiplier("user-123", "deal pricing")

        # 30% accuracy should give multiplier around 0.8
        assert multiplier < 1.0
        assert multiplier >= 0.5

    @pytest.mark.asyncio
    async def test_calibration_multiplier_good_accuracy(self) -> None:
        """Good accuracy should slightly boost confidence (capped at 1.2)."""
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "total_predictions": 20,
                    "correct_predictions": 18,  # 90% accuracy
                }
            ]
        )

        mock_db = MagicMock()
        mock_db.table.return_value = mock_table

        service = MetacognitionService(
            db_client=mock_db,
            llm_client=MagicMock(),
        )

        multiplier = await service._get_calibration_multiplier("user-123", "meeting outcome")

        # Good accuracy should boost slightly but cap at 1.2
        assert multiplier > 1.0
        assert multiplier <= 1.2


# ── Threshold Constant Tests ──────────────────────────────────────────────────


def test_threshold_values() -> None:
    """Verify threshold constants are set correctly."""
    assert RESEARCH_THRESHOLD == 0.5
    assert HIGH_CONFIDENCE_THRESHOLD == 0.8
