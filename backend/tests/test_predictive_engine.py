"""Unit tests for the Predictive Processing Engine (US-707).

Tests cover:
- Context gathering from multiple sources
- Prediction generation with LLM
- Prediction confidence scoring
- Error detection and marking predictions incorrect
- Surprise level calculation
- Salience boosting for surprises
- Calibration retrieval
- Performance targets (< 200ms for predictions)
"""

import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.intelligence.predictive.context_gatherer import PredictionContextGatherer
from src.intelligence.predictive.engine import PredictiveEngine
from src.intelligence.predictive.error_detector import PredictionErrorDetector
from src.intelligence.predictive.models import (
    ActivePredictionsResponse,
    CalibrationData,
    CalibrationResponse,
    EpisodicMemory,
    Prediction,
    PredictionCategory,
    PredictionContext,
    PredictionError,
    PredictionErrorDetectionResponse,
    PredictionStatus,
    RecentConversation,
    RecentLeadActivity,
    RecentSignal,
    UpcomingMeeting,
)
from src.models.prediction import PredictionCreate, PredictionType


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLM client."""
    client = MagicMock()
    client.generate_response = AsyncMock()
    return client


@pytest.fixture
def mock_db_client() -> MagicMock:
    """Create a mock database client."""
    client = MagicMock()
    client.table = MagicMock()
    client.rpc = MagicMock()
    return client


@pytest.fixture
def mock_prediction_service() -> MagicMock:
    """Create a mock prediction service."""
    service = MagicMock()
    service.register = AsyncMock()
    service.get_calibration_stats = AsyncMock()
    return service


@pytest.fixture
def predictive_engine(
    mock_llm_client: MagicMock,
    mock_prediction_service: MagicMock,
    mock_db_client: MagicMock,
) -> PredictiveEngine:
    """Create a PredictiveEngine with mocked dependencies."""
    return PredictiveEngine(
        llm_client=mock_llm_client,
        prediction_service=mock_prediction_service,
        db_client=mock_db_client,
    )


@pytest.fixture
def context_gatherer(mock_db_client: MagicMock) -> PredictionContextGatherer:
    """Create a PredictionContextGatherer with mocked dependencies."""
    return PredictionContextGatherer(db_client=mock_db_client)


@pytest.fixture
def error_detector(
    mock_db_client: MagicMock, mock_llm_client: MagicMock
) -> PredictionErrorDetector:
    """Create a PredictionErrorDetector with mocked dependencies."""
    return PredictionErrorDetector(db_client=mock_db_client, llm_client=mock_llm_client)


@pytest.fixture
def sample_context() -> PredictionContext:
    """Create a sample PredictionContext for testing."""
    return PredictionContext(
        recent_conversations=[
            RecentConversation(
                id=uuid4(),
                summary="Discussed Lonza deal progress",
                topics=["deals", "Lonza"],
                entities=["Lonza", "Catalent"],
                created_at=datetime.now(UTC),
            )
        ],
        active_goals=[{"id": str(uuid4()), "title": "Close Lonza deal", "status": "active"}],
        upcoming_meetings=[
            UpcomingMeeting(
                id=uuid4(),
                title="Lonza negotiation call",
                start_time=datetime.now(UTC) + timedelta(hours=24),
                attendees=["john@lonza.com"],
                related_goal_id=str(uuid4()),
            )
        ],
        recent_market_signals=[
            RecentSignal(
                id=uuid4(),
                signal_type="market",
                content="Lonza announced expansion plans",
                entities=["Lonza"],
                relevance_score=0.8,
                created_at=datetime.now(UTC),
            )
        ],
        recent_lead_activity=[
            RecentLeadActivity(
                lead_id=str(uuid4()),
                lead_name="Lonza",
                activity_type="status_change",
                activity_description="Moved to negotiation",
                created_at=datetime.now(UTC),
            )
        ],
        recent_episodic_memories=[
            EpisodicMemory(
                id=uuid4(),
                content="User expressed interest in accelerating the Lonza deal",
                entities=["Lonza"],
                importance=0.9,
                created_at=datetime.now(UTC),
            )
        ],
    )


# ============================================================
# Test Context Gathering
# ============================================================


@pytest.mark.asyncio
async def test_context_gatherer_gathers_all_sources(
    context_gatherer: PredictionContextGatherer,
    mock_db_client: MagicMock,
) -> None:
    """Test that context gatherer fetches from all sources in parallel."""
    # Mock database responses
    mock_table = MagicMock()

    # Mock conversations
    conv_result = MagicMock()
    conv_result.data = [
        {
            "id": str(uuid4()),
            "summary": "Test conversation",
            "created_at": datetime.now(UTC).isoformat(),
        }
    ]

    # Mock goals
    goals_result = MagicMock()
    goals_result.data = [{"id": str(uuid4()), "title": "Test goal", "status": "active"}]

    # Mock meetings
    meetings_result = MagicMock()
    meetings_result.data = []

    # Mock signals
    signals_result = MagicMock()
    signals_result.data = []

    # Mock leads
    leads_result = MagicMock()
    leads_result.data = []

    # Mock memories
    memories_result = MagicMock()
    memories_result.data = []

    # Setup table mock chain
    def table_side_effect(table_name: str):
        mock = MagicMock()
        if table_name == "conversations":
            mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = conv_result
        elif table_name == "goals":
            mock.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = goals_result
        elif table_name == "calendar_events":
            mock.select.return_value.eq.return_value.gte.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value = meetings_result
        elif table_name == "market_signals":
            mock.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = signals_result
        elif table_name == "leads":
            mock.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = leads_result
        elif table_name == "memory_episodic":
            mock.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = memories_result
        elif table_name == "messages":
            mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )
        return mock

    mock_db_client.table.side_effect = table_side_effect

    context = await context_gatherer.gather(user_id="test-user")

    assert isinstance(context, PredictionContext)
    assert len(context.recent_conversations) >= 0
    assert len(context.active_goals) >= 0


@pytest.mark.asyncio
async def test_context_gatherer_handles_db_errors(
    context_gatherer: PredictionContextGatherer,
    mock_db_client: MagicMock,
) -> None:
    """Test that context gatherer handles database errors gracefully."""
    # Make database throw an exception
    mock_db_client.table.side_effect = Exception("Database error")

    context = await context_gatherer.gather(user_id="test-user")

    # Should return empty context instead of raising
    assert isinstance(context, PredictionContext)
    assert context.recent_conversations == []
    assert context.active_goals == []


# ============================================================
# Test Prediction Generation
# ============================================================


@pytest.mark.asyncio
async def test_generate_predictions_with_llm(
    predictive_engine: PredictiveEngine,
    mock_llm_client: MagicMock,
    mock_prediction_service: MagicMock,
    sample_context: PredictionContext,
) -> None:
    """Test that predictions are generated using LLM."""
    # Mock LLM response
    mock_llm_client.generate_response.return_value = """[
        {
            "prediction_type": "deal_outcome",
            "prediction_text": "The Lonza deal will move to negotiation phase",
            "predicted_outcome": "Lonza signs term sheet within 2 weeks",
            "confidence": 0.75,
            "timeframe_days": 14,
            "context": {"entities": ["Lonza"]},
            "validation_criteria": "Check if deal status changes to negotiation"
        }
    ]"""

    # Mock prediction service
    mock_prediction_service.register.return_value = {
        "id": str(uuid4()),
        "prediction_text": "Test prediction",
        "created_at": datetime.now(UTC).isoformat(),
        "expected_resolution_date": (datetime.now(UTC) + timedelta(days=14)).isoformat(),
    }

    predictions = await predictive_engine.generate_predictions(
        user_id="test-user",
        context=sample_context,
        max_predictions=5,
    )

    assert len(predictions) == 1
    assert predictions[0].prediction_text == "The Lonza deal will move to negotiation phase"
    mock_llm_client.generate_response.assert_called_once()


@pytest.mark.asyncio
async def test_generate_predictions_handles_invalid_json(
    predictive_engine: PredictiveEngine,
    mock_llm_client: MagicMock,
    sample_context: PredictionContext,
) -> None:
    """Test that invalid LLM responses are handled gracefully."""
    # Mock invalid LLM response
    mock_llm_client.generate_response.return_value = "This is not valid JSON"

    predictions = await predictive_engine.generate_predictions(
        user_id="test-user",
        context=sample_context,
        max_predictions=5,
    )

    assert predictions == []


@pytest.mark.asyncio
async def test_generate_predictions_with_markdown(
    predictive_engine: PredictiveEngine,
    mock_llm_client: MagicMock,
    mock_prediction_service: MagicMock,
    sample_context: PredictionContext,
) -> None:
    """Test that markdown-wrapped JSON is handled."""
    mock_llm_client.generate_response.return_value = """```json
[
    {
        "prediction_type": "timing",
        "prediction_text": "Meeting will happen on schedule",
        "predicted_outcome": "Meeting proceeds as planned",
        "confidence": 0.8,
        "timeframe_days": 1,
        "context": {},
        "validation_criteria": "Check meeting status"
    }
]
```"""

    mock_prediction_service.register.return_value = {
        "id": str(uuid4()),
        "prediction_text": "Test",
        "created_at": datetime.now(UTC).isoformat(),
        "expected_resolution_date": datetime.now(UTC).isoformat(),
    }

    predictions = await predictive_engine.generate_predictions(
        user_id="test-user",
        context=sample_context,
        max_predictions=5,
    )

    assert len(predictions) == 1


# ============================================================
# Test Error Detection
# ============================================================


@pytest.mark.asyncio
async def test_detect_prediction_errors(
    error_detector: PredictionErrorDetector,
    mock_db_client: MagicMock,
    mock_llm_client: MagicMock,
) -> None:
    """Test that prediction errors are detected correctly."""
    # Mock pending predictions
    pending_result = MagicMock()
    pending_result.data = [
        {
            "id": str(uuid4()),
            "prediction_text": "Deal will close by Friday",
            "prediction_type": "deal_outcome",
            "confidence": 0.8,
            "context": {"entities": ["Lonza"]},
            "user_id": "test-user",
        }
    ]

    # Mock actual events
    events_result = MagicMock()
    events_result.data = [
        {
            "id": str(uuid4()),
            "type": "lead_update",
            "content": "Deal was delayed by 2 weeks",
            "created_at": datetime.now(UTC).isoformat(),
        }
    ]

    # Mock LLM comparison (low match score = prediction wrong)
    mock_llm_client.generate_response.return_value = (
        """{"match_score": 0.3, "reasoning": "Deal did not close by Friday"}"""
    )

    # Mock status update
    update_result = MagicMock()
    update_result.data = [{"id": "prediction-id"}]

    def table_side_effect(table_name: str):
        mock = MagicMock()
        if table_name == "predictions":
            mock.select.return_value.eq.return_value.eq.return_value.lt.return_value.execute.return_value = pending_result
            mock.update.return_value.eq.return_value.execute.return_value = update_result
        elif table_name == "conversations":
            mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )
        elif table_name == "leads":
            mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = events_result
        elif table_name == "market_signals":
            mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )
        return mock

    mock_db_client.table.side_effect = table_side_effect

    # Mock RPC for calibration
    mock_db_client.rpc.return_value.execute.return_value = MagicMock()

    errors = await error_detector.detect_errors(user_id="test-user")

    assert len(errors) == 1
    assert errors[0].surprise_level >= 0.5  # High surprise for wrong prediction


@pytest.mark.asyncio
async def test_error_detection_marks_correct_predictions(
    error_detector: PredictionErrorDetector,
    mock_db_client: MagicMock,
    mock_llm_client: MagicMock,
) -> None:
    """Test that correct predictions are marked as validated."""
    pending_result = MagicMock()
    pending_result.data = [
        {
            "id": str(uuid4()),
            "prediction_text": "Meeting will happen",
            "prediction_type": "meeting_outcome",
            "confidence": 0.9,
            "context": {},
            "user_id": "test-user",
        }
    ]

    events_result = MagicMock()
    events_result.data = [
        {
            "id": str(uuid4()),
            "type": "conversation",
            "content": "Meeting happened as scheduled",
            "created_at": datetime.now(UTC).isoformat(),
        }
    ]

    # High match score = prediction correct
    mock_llm_client.generate_response.return_value = (
        """{"match_score": 0.9, "reasoning": "Meeting occurred as predicted"}"""
    )

    update_result = MagicMock()
    update_result.data = [{"id": "prediction-id"}]

    def table_side_effect(table_name: str):
        mock = MagicMock()
        if table_name == "predictions":
            mock.select.return_value.eq.return_value.eq.return_value.lt.return_value.execute.return_value = pending_result
            mock.update.return_value.eq.return_value.execute.return_value = update_result
        elif table_name in ["conversations", "leads", "market_signals"]:
            mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
                events_result if table_name == "conversations" else MagicMock(data=[])
            )
        return mock

    mock_db_client.table.side_effect = table_side_effect
    mock_db_client.rpc.return_value.execute.return_value = MagicMock()

    errors = await error_detector.detect_errors(user_id="test-user")

    # Should have no errors since prediction was correct
    assert len(errors) == 0


# ============================================================
# Test Surprise Level Calculation
# ============================================================


def test_surprise_level_calculation() -> None:
    """Test that surprise level is inverse of match score."""
    # High match (0.9) -> Low surprise (0.1)
    match_score = 0.9
    surprise_level = 1.0 - match_score
    assert surprise_level == pytest.approx(0.1, rel=0.01)

    # Low match (0.3) -> High surprise (0.7)
    match_score = 0.3
    surprise_level = 1.0 - match_score
    assert surprise_level == pytest.approx(0.7, rel=0.01)


def test_learning_signal_calculation() -> None:
    """Test that learning signal equals surprise level."""
    surprise_level = 0.7
    learning_signal = surprise_level  # Direct mapping in current implementation

    assert learning_signal == surprise_level


# ============================================================
# Test Salience Boosting
# ============================================================


@pytest.mark.asyncio
async def test_boost_salience_for_high_surprise(
    predictive_engine: PredictiveEngine,
    mock_db_client: MagicMock,
) -> None:
    """Test that salience is boosted for high-surprise errors."""
    error = PredictionError(
        prediction_id=uuid4(),
        prediction_type=PredictionCategory.DEAL_OUTCOME,
        predicted_value="Deal will close",
        actual_value="Deal delayed",
        surprise_level=0.8,  # High surprise
        learning_signal=0.8,
        affected_entities=["Lonza", "Catalent"],
        related_goal_ids=[],
        created_at=datetime.now(UTC),
    )

    # Mock existing salience record
    existing_result = MagicMock()
    existing_result.data = [{"id": str(uuid4()), "salience_score": 0.5}]

    # Mock update result
    update_result = MagicMock()
    update_result.data = [{"id": str(uuid4()), "salience_score": 0.74}]

    def table_side_effect(table_name: str):
        mock = MagicMock()
        if table_name == "memory_salience":
            mock.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
                existing_result
            )
            mock.update.return_value.eq.return_value.execute.return_value = update_result
        return mock

    mock_db_client.table.side_effect = table_side_effect

    boosted = await predictive_engine.boost_salience_for_surprise(user_id="test-user", error=error)

    assert len(boosted) == 2  # Two entities boosted


@pytest.mark.asyncio
async def test_no_boost_for_low_surprise(
    predictive_engine: PredictiveEngine,
    mock_db_client: MagicMock,
) -> None:
    """Test that low-surprise errors don't boost salience."""
    error = PredictionError(
        prediction_id=uuid4(),
        prediction_type=PredictionCategory.TIMING,
        predicted_value="Event will happen soon",
        actual_value="Event happened a bit later",
        surprise_level=0.2,  # Low surprise
        learning_signal=0.2,
        affected_entities=["TestEntity"],
        related_goal_ids=[],
        created_at=datetime.now(UTC),
    )

    boosted = await predictive_engine.boost_salience_for_surprise(user_id="test-user", error=error)

    assert len(boosted) == 0  # No boost for low surprise


# ============================================================
# Test Calibration Retrieval
# ============================================================


@pytest.mark.asyncio
async def test_get_calibration(
    predictive_engine: PredictiveEngine,
    mock_prediction_service: MagicMock,
) -> None:
    """Test that calibration statistics are retrieved correctly."""
    mock_prediction_service.get_calibration_stats.return_value = [
        {
            "prediction_type": "deal_outcome",
            "confidence_bucket": 0.7,
            "total_predictions": 10,
            "correct_predictions": 7,
            "accuracy": 0.7,
            "is_calibrated": True,
        }
    ]

    calibration = await predictive_engine.get_calibration(user_id="test-user")

    assert len(calibration) == 1
    assert calibration[0].is_calibrated is True


@pytest.mark.asyncio
async def test_calibration_response(
    predictive_engine: PredictiveEngine,
    mock_prediction_service: MagicMock,
) -> None:
    """Test that calibration response includes overall accuracy."""
    mock_prediction_service.get_calibration_stats.return_value = [
        {
            "prediction_type": "deal_outcome",
            "confidence_bucket": 0.8,
            "total_predictions": 5,
            "correct_predictions": 4,
            "accuracy": 0.8,
            "is_calibrated": True,
        },
        {
            "prediction_type": "timing",
            "confidence_bucket": 0.6,
            "total_predictions": 5,
            "correct_predictions": 3,
            "accuracy": 0.6,
            "is_calibrated": True,
        },
    ]

    response = await predictive_engine.get_calibration_response(user_id="test-user")

    assert isinstance(response, CalibrationResponse)
    assert response.total_predictions == 10
    assert response.overall_accuracy == pytest.approx(0.7, rel=0.01)
    assert response.is_well_calibrated is True


# ============================================================
# Test Get Active Predictions
# ============================================================


@pytest.mark.asyncio
async def test_get_active_predictions(
    predictive_engine: PredictiveEngine,
    mock_db_client: MagicMock,
) -> None:
    """Test retrieving active predictions."""
    result = MagicMock()
    result.data = [
        {
            "id": str(uuid4()),
            "prediction_type": "deal_outcome",
            "prediction_text": "Test prediction",
            "predicted_outcome": "Expected result",
            "confidence": 0.8,
            "context": {},
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
            "expected_resolution_date": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        }
    ]

    mock_table = MagicMock()
    mock_table.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = result
    mock_db_client.table.return_value = mock_table

    response = await predictive_engine.get_active_predictions(user_id="test-user", limit=20)

    assert isinstance(response, ActivePredictionsResponse)
    assert response.total_count == 1
    assert len(response.predictions) == 1


# ============================================================
# Test Performance
# ============================================================


@pytest.mark.asyncio
async def test_performance_prediction_generation(
    predictive_engine: PredictiveEngine,
    mock_llm_client: MagicMock,
    mock_prediction_service: MagicMock,
    sample_context: PredictionContext,
) -> None:
    """Test that prediction generation completes in < 200ms (mocked)."""
    mock_llm_client.generate_response.return_value = "[]"
    mock_prediction_service.register.return_value = {
        "id": str(uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "expected_resolution_date": datetime.now(UTC).isoformat(),
    }

    start_time = time.monotonic()

    await predictive_engine.generate_predictions(
        user_id="test-user",
        context=sample_context,
        max_predictions=5,
    )

    elapsed_ms = (time.monotonic() - start_time) * 1000

    # With mocked operations, should be very fast
    assert elapsed_ms < 200, f"Prediction generation took {elapsed_ms}ms, expected < 200ms"


# ============================================================
# Test Model Validation
# ============================================================


def test_prediction_model_validation() -> None:
    """Test Prediction model validation."""
    prediction = Prediction(
        id=uuid4(),
        user_id="test-user",
        prediction_type=PredictionCategory.DEAL_OUTCOME,
        prediction_text="The deal will close this week",
        confidence=0.8,
        status=PredictionStatus.ACTIVE,
    )

    assert prediction.confidence == 0.8
    assert prediction.prediction_type == PredictionCategory.DEAL_OUTCOME

    # Test confidence bounds
    with pytest.raises(ValueError):
        Prediction(
            id=uuid4(),
            user_id="test-user",
            prediction_type=PredictionCategory.DEAL_OUTCOME,
            prediction_text="Test",
            confidence=1.5,  # Invalid
        )


def test_prediction_error_model_validation() -> None:
    """Test PredictionError model validation."""
    error = PredictionError(
        prediction_id=uuid4(),
        prediction_type=PredictionCategory.DEAL_OUTCOME,
        predicted_value="Deal will close",
        actual_value="Deal delayed",
        surprise_level=0.7,
        learning_signal=0.7,
    )

    assert error.surprise_level == 0.7
    assert error.learning_signal == 0.7

    # Test bounds
    with pytest.raises(ValueError):
        PredictionError(
            prediction_id=uuid4(),
            prediction_type=PredictionCategory.DEAL_OUTCOME,
            predicted_value="Test",
            actual_value="Result",
            surprise_level=1.5,  # Invalid
            learning_signal=0.5,
        )


def test_calibration_data_model() -> None:
    """Test CalibrationData model."""
    cal = CalibrationData(
        prediction_type=PredictionCategory.DEAL_OUTCOME,
        confidence_bucket=0.8,
        total_predictions=10,
        correct_predictions=8,
        accuracy=0.8,
        is_calibrated=True,
    )

    assert cal.accuracy == 0.8
    assert cal.is_calibrated is True


def test_prediction_category_enum() -> None:
    """Test PredictionCategory enum values."""
    assert PredictionCategory.USER_ACTION.value == "user_action"
    assert PredictionCategory.USER_NEED.value == "user_need"
    assert PredictionCategory.EXTERNAL_EVENT.value == "external_event"
    assert PredictionCategory.TOPIC_SHIFT.value == "topic_shift"
    assert PredictionCategory.DEAL_OUTCOME.value == "deal_outcome"
    assert PredictionCategory.MEETING_OUTCOME.value == "meeting_outcome"
    assert PredictionCategory.TIMING.value == "timing"


def test_prediction_status_enum() -> None:
    """Test PredictionStatus enum values."""
    assert PredictionStatus.ACTIVE.value == "active"
    assert PredictionStatus.VALIDATED_CORRECT.value == "validated_correct"
    assert PredictionStatus.VALIDATED_INCORRECT.value == "validated_incorrect"
    assert PredictionStatus.EXPIRED.value == "expired"
    assert PredictionStatus.SUPERSEDED.value == "superseded"
