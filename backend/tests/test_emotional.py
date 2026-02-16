"""Tests for EmotionalIntelligenceEngine.

Tests cover:
- Context detection
- Response generation
- Avoidance list generation
- Shared history integration
- Graceful degradation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.companion.emotional import (
    EmotionalContext,
    EmotionalIntelligenceEngine,
    EmotionalResponse,
    SupportType,
    CONTEXT_AVOIDANCES,
    CONTEXT_SUPPORT_MAP,
)


class TestEmotionalContext:
    """Tests for emotional context classification."""

    @pytest.fixture
    def engine(self) -> EmotionalIntelligenceEngine:
        """Create engine with mocked dependencies."""
        mock_db = MagicMock()
        mock_llm = AsyncMock()
        return EmotionalIntelligenceEngine(
            db_client=mock_db,
            llm_client=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_celebration_detection(self, engine: EmotionalIntelligenceEngine) -> None:
        """Verify celebration context detected from win message."""
        engine._llm.generate_response = AsyncMock(return_value="celebration")

        result = await engine.detect_context("We just closed the Lonza deal!")

        assert result == EmotionalContext.CELEBRATION

    @pytest.mark.asyncio
    async def test_setback_detection(self, engine: EmotionalIntelligenceEngine) -> None:
        """Verify setback context detected from failure message."""
        engine._llm.generate_response = AsyncMock(return_value="setback")

        result = await engine.detect_context("The proposal got rejected again.")

        assert result == EmotionalContext.SETBACK

    @pytest.mark.asyncio
    async def test_frustration_detection(self, engine: EmotionalIntelligenceEngine) -> None:
        """Verify frustration context detected."""
        engine._llm.generate_response = AsyncMock(return_value="frustration")

        result = await engine.detect_context("This CRM is so slow, I can't get anything done!")

        assert result == EmotionalContext.FRUSTRATION

    @pytest.mark.asyncio
    async def test_anxiety_detection(self, engine: EmotionalIntelligenceEngine) -> None:
        """Verify anxiety context detected."""
        engine._llm.generate_response = AsyncMock(return_value="anxiety")

        result = await engine.detect_context("I'm really worried about the quarterly review.")

        assert result == EmotionalContext.ANXIETY

    @pytest.mark.asyncio
    async def test_neutral_detection(self, engine: EmotionalIntelligenceEngine) -> None:
        """Verify neutral context detected for factual messages."""
        engine._llm.generate_response = AsyncMock(return_value="neutral")

        result = await engine.detect_context("Can you pull the Lonza briefing?")

        assert result == EmotionalContext.NEUTRAL

    @pytest.mark.asyncio
    async def test_unrecognized_defaults_to_neutral(
        self, engine: EmotionalIntelligenceEngine
    ) -> None:
        """Verify unrecognized context defaults to neutral."""
        engine._llm.generate_response = AsyncMock(return_value="unknown_category")

        result = await engine.detect_context("Some random message")

        assert result == EmotionalContext.NEUTRAL

    @pytest.mark.asyncio
    async def test_llm_error_defaults_to_neutral(
        self, engine: EmotionalIntelligenceEngine
    ) -> None:
        """Verify LLM errors gracefully degrade to neutral."""
        engine._llm.generate_response = AsyncMock(side_effect=Exception("LLM error"))

        result = await engine.detect_context("Any message")

        assert result == EmotionalContext.NEUTRAL


class TestEmotionalResponse:
    """Tests for emotional response generation."""

    @pytest.fixture
    def engine(self) -> EmotionalIntelligenceEngine:
        """Create engine with mocked dependencies."""
        mock_db = MagicMock()
        mock_llm = AsyncMock()
        return EmotionalIntelligenceEngine(
            db_client=mock_db,
            llm_client=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_setback_response_no_toxic_positivity(
        self, engine: EmotionalIntelligenceEngine
    ) -> None:
        """Ensure setback response doesn't include toxic positivity."""
        engine._llm.generate_response = AsyncMock(
            side_effect=["setback", "I understand this is really difficult."]
        )

        response = await engine.generate_emotional_response(
            user_id="test-user",
            message="The deal fell through at the last minute.",
        )

        assert response.context == EmotionalContext.SETBACK
        assert response.support_type == SupportType.EMPATHIZE
        # Verify avoidances contain toxic positivity patterns
        assert any("toxic positivity" in a.lower() for a in response.avoid_list)
        assert any("everything happens for a reason" in a.lower() for a in response.avoid_list)

    @pytest.mark.asyncio
    async def test_frustration_response_not_minimizing(
        self, engine: EmotionalIntelligenceEngine
    ) -> None:
        """Ensure frustration response avoids minimizing language."""
        engine._llm.generate_response = AsyncMock(
            side_effect=["frustration", "That sounds genuinely frustrating."]
        )

        response = await engine.generate_emotional_response(
            user_id="test-user",
            message="I've been waiting on hold for 30 minutes!",
        )

        assert response.context == EmotionalContext.FRUSTRATION
        # Verify avoidances contain minimizing patterns
        assert any("minimizing" in a.lower() for a in response.avoid_list)
        assert any("calm down" in a.lower() for a in response.avoid_list)

    @pytest.mark.asyncio
    async def test_celebration_response_elements(
        self, engine: EmotionalIntelligenceEngine
    ) -> None:
        """Verify celebration response includes appropriate elements."""
        engine._llm.generate_response = AsyncMock(
            side_effect=["celebration", "Congratulations on the win!"]
        )

        response = await engine.generate_emotional_response(
            user_id="test-user",
            message="We won the contract!",
        )

        assert response.context == EmotionalContext.CELEBRATION
        assert response.support_type == SupportType.CELEBRATE
        assert len(response.response_elements) > 0
        # Should include avoiding generic praise
        assert any("generic" in a.lower() for a in response.avoid_list)

    @pytest.mark.asyncio
    async def test_anxiety_avoidance_list(
        self, engine: EmotionalIntelligenceEngine
    ) -> None:
        """Verify anxiety context has appropriate avoidances."""
        engine._llm.generate_response = AsyncMock(
            side_effect=["anxiety", "Your concerns are valid."]
        )

        response = await engine.generate_emotional_response(
            user_id="test-user",
            message="I'm worried about the presentation.",
        )

        assert response.context == EmotionalContext.ANXIETY
        assert any("don't worry" in a.lower() for a in response.avoid_list)
        assert any("dismissing" in a.lower() or "false reassurance" in a.lower() for a in response.avoid_list)


class TestAvoidanceLists:
    """Tests for context-specific avoidance lists."""

    def test_all_contexts_have_avoidances(self) -> None:
        """Verify each emotional context has defined avoidances."""
        for context in EmotionalContext:
            assert context in CONTEXT_AVOIDANCES, f"Missing avoidances for {context}"
            assert len(CONTEXT_AVOIDANCES[context]) > 0, f"Empty avoidances for {context}"

    def test_all_contexts_have_support_type(self) -> None:
        """Verify each context maps to a support type."""
        for context in EmotionalContext:
            assert context in CONTEXT_SUPPORT_MAP, f"Missing support type for {context}"

    def test_celebration_avoidances(self) -> None:
        """Verify celebration avoidances prevent toxic patterns."""
        avoid = CONTEXT_AVOIDANCES[EmotionalContext.CELEBRATION]
        assert any("generic" in a.lower() for a in avoid)
        assert any("pivoting" in a.lower() or "next task" in a.lower() for a in avoid)
        assert any("downplaying" in a.lower() for a in avoid)

    def test_setback_avoidances(self) -> None:
        """Verify setback avoidances prevent harmful responses."""
        avoid = CONTEXT_AVOIDANCES[EmotionalContext.SETBACK]
        assert any("blame" in a.lower() for a in avoid)
        assert any("problem-solving without acknowledgment" in a.lower() for a in avoid)

    def test_frustration_avoidances(self) -> None:
        """Verify frustration avoidances prevent minimizing."""
        avoid = CONTEXT_AVOIDANCES[EmotionalContext.FRUSTRATION]
        assert any("calm down" in a.lower() for a in avoid)
        assert any("minimizing" in a.lower() for a in avoid)

    def test_anxiety_avoidances(self) -> None:
        """Verify anxiety avoidances prevent dismissal."""
        avoid = CONTEXT_AVOIDANCES[EmotionalContext.ANXIETY]
        assert any("don't worry" in a.lower() for a in avoid)
        assert any("dismissing" in a.lower() for a in avoid)


class TestEmotionalResponseDataclass:
    """Tests for EmotionalResponse dataclass."""

    def test_to_dict(self) -> None:
        """Verify serialization to dictionary."""
        response = EmotionalResponse(
            context=EmotionalContext.CELEBRATION,
            acknowledgment="Great job!",
            support_type=SupportType.CELEBRATE,
            response_elements=["Acknowledge the achievement"],
            avoid_list=["Generic praise"],
        )

        data = response.to_dict()

        assert data["context"] == "celebration"
        assert data["acknowledgment"] == "Great job!"
        assert data["support_type"] == "celebrate"
        assert len(data["response_elements"]) == 1
        assert len(data["avoid_list"]) == 1
        assert "created_at" in data

    def test_from_dict(self) -> None:
        """Verify deserialization from dictionary."""
        data = {
            "context": "setback",
            "acknowledgment": "I understand.",
            "support_type": "empathize",
            "response_elements": ["Validate feelings"],
            "avoid_list": ["Toxic positivity"],
            "created_at": "2024-01-15T10:30:00+00:00",
        }

        response = EmotionalResponse.from_dict(data)

        assert response.context == EmotionalContext.SETBACK
        assert response.acknowledgment == "I understand."
        assert response.support_type == SupportType.EMPATHIZE
        assert len(response.response_elements) == 1
        assert len(response.avoid_list) == 1

    def test_round_trip_serialization(self) -> None:
        """Verify to_dict and from_dict are inverses."""
        original = EmotionalResponse(
            context=EmotionalContext.FRUSTRATION,
            acknowledgment="That sounds frustrating.",
            support_type=SupportType.ACKNOWLEDGE,
            response_elements=["Name the frustration"],
            avoid_list=["Calm down"],
        )

        data = original.to_dict()
        restored = EmotionalResponse.from_dict(data)

        assert restored.context == original.context
        assert restored.acknowledgment == original.acknowledgment
        assert restored.support_type == original.support_type
        assert restored.response_elements == original.response_elements
        assert restored.avoid_list == original.avoid_list


class TestSharedHistory:
    """Tests for shared history integration."""

    @pytest.fixture
    def engine_with_memory(self) -> EmotionalIntelligenceEngine:
        """Create engine with mocked memory service."""
        mock_db = MagicMock()
        mock_llm = AsyncMock()
        mock_memory = AsyncMock()
        mock_memory.search = AsyncMock(return_value=[])
        return EmotionalIntelligenceEngine(
            db_client=mock_db,
            llm_client=mock_llm,
            memory_service=mock_memory,
        )

    @pytest.mark.asyncio
    async def test_conversation_history_included_in_acknowledgment(
        self, engine_with_memory: EmotionalIntelligenceEngine
    ) -> None:
        """Verify acknowledgment references conversation history."""
        # Track all prompts sent to LLM
        captured_prompts: list[str] = []

        async def mock_generate(messages: list[dict[str, str]], **kwargs: object) -> str:
            # Capture the content from messages
            for msg in messages:
                captured_prompts.append(msg.get("content", ""))
            # Return celebration on first call (context), acknowledgment on second
            if len(captured_prompts) == 1:
                return "celebration"
            return "That's a meaningful win given the work you put in."

        engine_with_memory._llm.generate_response = mock_generate

        history = [
            {"role": "user", "content": "I've been working on the Lonza deal for months."},
            {"role": "assistant", "content": "I know how important this is to you."},
        ]

        await engine_with_memory.generate_emotional_response(
            user_id="test-user",
            message="We finally closed it!",
            conversation_history=history,
        )

        # The prompt should include context from the history
        all_prompts = " ".join(captured_prompts)
        assert "months" in all_prompts or "important" in all_prompts or "Lonza" in all_prompts

    @pytest.mark.asyncio
    async def test_shared_history_failure_graceful_degradation(
        self, engine_with_memory: EmotionalIntelligenceEngine
    ) -> None:
        """Verify graceful degradation when memory fails."""
        engine_with_memory._memory = None  # Simulate no memory service
        engine_with_memory._llm.generate_response = AsyncMock(
            side_effect=["celebration", "Congratulations!"]
        )

        response = await engine_with_memory.generate_emotional_response(
            user_id="test-user",
            message="We won!",
        )

        assert response is not None
        assert response.context == EmotionalContext.CELEBRATION


class TestRecordResponse:
    """Tests for recording emotional responses."""

    @pytest.fixture
    def engine(self) -> EmotionalIntelligenceEngine:
        """Create engine with mocked dependencies."""
        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value.data = [{"id": "test-id"}]
        mock_llm = AsyncMock()
        return EmotionalIntelligenceEngine(
            db_client=mock_db,
            llm_client=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_record_response_success(self, engine: EmotionalIntelligenceEngine) -> None:
        """Verify successful response recording."""
        response = EmotionalResponse(
            context=EmotionalContext.CELEBRATION,
            acknowledgment="Great job!",
            support_type=SupportType.CELEBRATE,
        )

        result = await engine.record_response(
            user_id="test-user",
            context=EmotionalContext.CELEBRATION,
            message="We won!",
            response=response,
        )

        assert result is True
        engine._db.table.assert_called_with("companion_emotional_responses")

    @pytest.mark.asyncio
    async def test_record_response_with_reaction(
        self, engine: EmotionalIntelligenceEngine
    ) -> None:
        """Verify recording with user reaction."""
        response = EmotionalResponse(
            context=EmotionalContext.SETBACK,
            acknowledgment="I understand.",
            support_type=SupportType.EMPATHIZE,
        )

        result = await engine.record_response(
            user_id="test-user",
            context=EmotionalContext.SETBACK,
            message="The deal fell through.",
            response=response,
            user_reaction="Helpful, thanks",
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_record_response_db_failure(
        self, engine: EmotionalIntelligenceEngine
    ) -> None:
        """Verify graceful handling of database failures."""
        engine._db.table.side_effect = Exception("DB error")

        response = EmotionalResponse(
            context=EmotionalContext.NEUTRAL,
            acknowledgment="I see.",
            support_type=SupportType.ACKNOWLEDGE,
        )

        result = await engine.record_response(
            user_id="test-user",
            context=EmotionalContext.NEUTRAL,
            message="Hello",
            response=response,
        )

        assert result is False


class TestNeutralContextHandling:
    """Tests for neutral context handling."""

    @pytest.fixture
    def engine(self) -> EmotionalIntelligenceEngine:
        """Create engine with mocked dependencies."""
        mock_db = MagicMock()
        mock_llm = AsyncMock()
        return EmotionalIntelligenceEngine(
            db_client=mock_db,
            llm_client=mock_llm,
        )

    @pytest.mark.asyncio
    async def test_neutral_context_no_forced_emotion(
        self, engine: EmotionalIntelligenceEngine
    ) -> None:
        """Verify neutral messages don't force emotional engagement."""
        engine._llm.generate_response = AsyncMock(
            side_effect=["neutral", "I'll help you with that."]
        )

        response = await engine.generate_emotional_response(
            user_id="test-user",
            message="What's the weather like?",
        )

        assert response.context == EmotionalContext.NEUTRAL
        assert response.support_type == SupportType.ACKNOWLEDGE
        # Should have neutral-specific avoidances
        assert any("forcing" in a.lower() for a in response.avoid_list)

    @pytest.mark.asyncio
    async def test_neutral_response_elements(
        self, engine: EmotionalIntelligenceEngine
    ) -> None:
        """Verify neutral response elements are appropriate."""
        engine._llm.generate_response = AsyncMock(
            side_effect=["neutral", "Got it."]
        )

        response = await engine.generate_emotional_response(
            user_id="test-user",
            message="Show me the report.",
        )

        assert response.context == EmotionalContext.NEUTRAL
        assert any("professional" in e.lower() for e in response.response_elements)


class TestSupportTypeMapping:
    """Tests for context to support type mapping."""

    def test_celebration_maps_to_celebrate(self) -> None:
        """Verify celebration maps to celebrate support type."""
        assert CONTEXT_SUPPORT_MAP[EmotionalContext.CELEBRATION] == SupportType.CELEBRATE

    def test_setback_maps_to_empathize(self) -> None:
        """Verify setback maps to empathize support type."""
        assert CONTEXT_SUPPORT_MAP[EmotionalContext.SETBACK] == SupportType.EMPATHIZE

    def test_frustration_maps_to_acknowledge(self) -> None:
        """Verify frustration maps to acknowledge support type."""
        assert CONTEXT_SUPPORT_MAP[EmotionalContext.FRUSTRATION] == SupportType.ACKNOWLEDGE

    def test_anxiety_maps_to_reassure(self) -> None:
        """Verify anxiety maps to reassure support type."""
        assert CONTEXT_SUPPORT_MAP[EmotionalContext.ANXIETY] == SupportType.REASSURE

    def test_disappointment_maps_to_empathize(self) -> None:
        """Verify disappointment maps to empathize support type."""
        assert CONTEXT_SUPPORT_MAP[EmotionalContext.DISAPPOINTMENT] == SupportType.EMPATHIZE

    def test_excitement_maps_to_celebrate(self) -> None:
        """Verify excitement maps to celebrate support type."""
        assert CONTEXT_SUPPORT_MAP[EmotionalContext.EXCITEMENT] == SupportType.CELEBRATE

    def test_neutral_maps_to_acknowledge(self) -> None:
        """Verify neutral maps to acknowledge support type."""
        assert CONTEXT_SUPPORT_MAP[EmotionalContext.NEUTRAL] == SupportType.ACKNOWLEDGE
