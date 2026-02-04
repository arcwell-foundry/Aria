# Prediction Registration System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement US-422 - Create a Prediction Registration System that extracts and tracks ARIA's predictions, validates outcomes, and calculates calibration statistics to improve ARIA's self-awareness.

**Architecture:** A new `PredictionService` will extract predictions from ARIA's responses using LLM parsing, store them with confidence scores, track outcomes via validation workflow, and calculate calibration statistics by confidence bucket (0.1 increments). This follows existing service patterns (`GoalService`) and integrates with the chat system for automatic extraction.

**Tech Stack:** Python/FastAPI, Supabase (PostgreSQL + RLS), Pydantic models, pytest with mocking

---

## Task 1: Create Database Migration

**Files:**
- Create: `supabase/migrations/20260203000006_create_predictions.sql`

**Step 1: Write the migration file**

```sql
-- Create predictions table for tracking ARIA's predictions
CREATE TABLE predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Prediction content
    prediction_type TEXT NOT NULL CHECK (
        prediction_type IN ('user_action', 'external_event', 'deal_outcome', 'timing', 'market_signal', 'lead_response', 'meeting_outcome')
    ),
    prediction_text TEXT NOT NULL,
    predicted_outcome TEXT,
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),

    -- Context
    context JSONB,
    source_conversation_id UUID,
    source_message_id UUID,
    validation_criteria TEXT,

    -- Timeline
    expected_resolution_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Outcome
    status TEXT NOT NULL DEFAULT 'pending' CHECK (
        status IN ('pending', 'validated_correct', 'validated_incorrect', 'expired', 'cancelled')
    ),
    validated_at TIMESTAMPTZ,
    validation_notes TEXT
);

-- Create calibration tracking table
CREATE TABLE prediction_calibration (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    prediction_type TEXT NOT NULL,
    confidence_bucket FLOAT NOT NULL CHECK (confidence_bucket >= 0.1 AND confidence_bucket <= 1.0),
    total_predictions INTEGER NOT NULL DEFAULT 0,
    correct_predictions INTEGER NOT NULL DEFAULT 0,
    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, prediction_type, confidence_bucket)
);

-- Indexes for predictions
CREATE INDEX idx_predictions_user_status ON predictions(user_id, status);
CREATE INDEX idx_predictions_resolution ON predictions(expected_resolution_date) WHERE status = 'pending';
CREATE INDEX idx_predictions_type ON predictions(user_id, prediction_type);
CREATE INDEX idx_predictions_created ON predictions(user_id, created_at DESC);

-- Indexes for calibration
CREATE INDEX idx_calibration_user ON prediction_calibration(user_id);
CREATE INDEX idx_calibration_user_type ON prediction_calibration(user_id, prediction_type);

-- Enable RLS
ALTER TABLE predictions ENABLE ROW LEVEL SECURITY;
ALTER TABLE prediction_calibration ENABLE ROW LEVEL SECURITY;

-- RLS policies for predictions
CREATE POLICY "Users can read own predictions" ON predictions
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own predictions" ON predictions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own predictions" ON predictions
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own predictions" ON predictions
    FOR DELETE USING (auth.uid() = user_id);

-- RLS policies for calibration
CREATE POLICY "Users can read own calibration" ON prediction_calibration
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own calibration" ON prediction_calibration
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own calibration" ON prediction_calibration
    FOR UPDATE USING (auth.uid() = user_id);

-- Function for atomic calibration upsert
CREATE OR REPLACE FUNCTION upsert_calibration(
    p_user_id UUID,
    p_prediction_type TEXT,
    p_confidence_bucket FLOAT,
    p_is_correct BOOLEAN
) RETURNS VOID AS $$
BEGIN
    INSERT INTO prediction_calibration (
        user_id, prediction_type, confidence_bucket,
        total_predictions, correct_predictions
    ) VALUES (
        p_user_id, p_prediction_type, p_confidence_bucket,
        1, CASE WHEN p_is_correct THEN 1 ELSE 0 END
    )
    ON CONFLICT (user_id, prediction_type, confidence_bucket)
    DO UPDATE SET
        total_predictions = prediction_calibration.total_predictions + 1,
        correct_predictions = prediction_calibration.correct_predictions +
            CASE WHEN p_is_correct THEN 1 ELSE 0 END,
        last_updated = NOW();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Comments
COMMENT ON TABLE predictions IS 'Stores predictions made by ARIA for learning and calibration';
COMMENT ON COLUMN predictions.confidence IS '0.0-1.0 confidence level in the prediction';
COMMENT ON COLUMN predictions.prediction_type IS 'Category of prediction for calibration tracking';
COMMENT ON TABLE prediction_calibration IS 'Tracks prediction accuracy by confidence bucket for calibration';
COMMENT ON COLUMN prediction_calibration.confidence_bucket IS 'Rounded confidence value (0.1, 0.2, ..., 1.0)';
COMMENT ON FUNCTION upsert_calibration IS 'Atomically updates calibration stats when a prediction is validated';
```

**Step 2: Verify migration file exists**

Run: `ls -la supabase/migrations/20260203000006_create_predictions.sql`
Expected: File exists with correct content

**Step 3: Commit**

```bash
git add supabase/migrations/20260203000006_create_predictions.sql
git commit -m "feat(db): add predictions and calibration tables for US-422"
```

---

## Task 2: Create Pydantic Models

**Files:**
- Create: `backend/src/models/prediction.py`
- Modify: `backend/src/models/__init__.py`

**Step 1: Write the failing test**

Create `backend/tests/test_prediction_models.py`:

```python
"""Tests for prediction models."""

import pytest
from datetime import date, datetime
from pydantic import ValidationError


def test_prediction_type_enum_has_all_types() -> None:
    """Test PredictionType enum has all expected values."""
    from src.models.prediction import PredictionType

    expected = {
        "user_action", "external_event", "deal_outcome",
        "timing", "market_signal", "lead_response", "meeting_outcome"
    }
    actual = {t.value for t in PredictionType}
    assert actual == expected


def test_prediction_status_enum_has_all_statuses() -> None:
    """Test PredictionStatus enum has all expected values."""
    from src.models.prediction import PredictionStatus

    expected = {
        "pending", "validated_correct", "validated_incorrect",
        "expired", "cancelled"
    }
    actual = {s.value for s in PredictionStatus}
    assert actual == expected


def test_prediction_create_validates_confidence_range() -> None:
    """Test PredictionCreate validates confidence is between 0 and 1."""
    from src.models.prediction import PredictionCreate, PredictionType

    # Valid confidence
    valid = PredictionCreate(
        prediction_type=PredictionType.DEAL_OUTCOME,
        prediction_text="Deal will close",
        confidence=0.75,
        expected_resolution_date=date(2026, 3, 1),
    )
    assert valid.confidence == 0.75

    # Invalid: too high
    with pytest.raises(ValidationError):
        PredictionCreate(
            prediction_type=PredictionType.DEAL_OUTCOME,
            prediction_text="Deal will close",
            confidence=1.5,
            expected_resolution_date=date(2026, 3, 1),
        )

    # Invalid: negative
    with pytest.raises(ValidationError):
        PredictionCreate(
            prediction_type=PredictionType.DEAL_OUTCOME,
            prediction_text="Deal will close",
            confidence=-0.1,
            expected_resolution_date=date(2026, 3, 1),
        )


def test_prediction_validate_requires_is_correct() -> None:
    """Test PredictionValidate requires is_correct field."""
    from src.models.prediction import PredictionValidate

    valid = PredictionValidate(is_correct=True, validation_notes="Outcome matched")
    assert valid.is_correct is True

    valid_false = PredictionValidate(is_correct=False)
    assert valid_false.is_correct is False


def test_calibration_stats_response_calculates_accuracy() -> None:
    """Test CalibrationStatsResponse includes accuracy calculation."""
    from src.models.prediction import CalibrationStatsResponse

    stats = CalibrationStatsResponse(
        prediction_type="deal_outcome",
        confidence_bucket=0.8,
        total_predictions=100,
        correct_predictions=78,
        accuracy=0.78,
        is_calibrated=True,
    )
    assert stats.accuracy == 0.78
    assert stats.is_calibrated is True
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_prediction_models.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.models.prediction'"

**Step 3: Write the models file**

Create `backend/src/models/prediction.py`:

```python
"""Prediction-related Pydantic models for ARIA.

This module contains models for prediction tracking, validation, and calibration.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PredictionType(str, Enum):
    """Type of prediction for categorization and calibration tracking."""

    USER_ACTION = "user_action"
    EXTERNAL_EVENT = "external_event"
    DEAL_OUTCOME = "deal_outcome"
    TIMING = "timing"
    MARKET_SIGNAL = "market_signal"
    LEAD_RESPONSE = "lead_response"
    MEETING_OUTCOME = "meeting_outcome"


class PredictionStatus(str, Enum):
    """Current status of a prediction."""

    PENDING = "pending"
    VALIDATED_CORRECT = "validated_correct"
    VALIDATED_INCORRECT = "validated_incorrect"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PredictionCreate(BaseModel):
    """Request model for creating a new prediction."""

    prediction_type: PredictionType = Field(
        ..., description="Category of the prediction"
    )
    prediction_text: str = Field(
        ..., min_length=1, max_length=2000, description="What is being predicted"
    )
    predicted_outcome: str | None = Field(
        None, max_length=1000, description="Expected result of the prediction"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence level (0.0-1.0)"
    )
    context: dict[str, Any] | None = Field(
        None, description="Additional context about the prediction"
    )
    source_conversation_id: str | None = Field(
        None, description="ID of the conversation where prediction was made"
    )
    source_message_id: str | None = Field(
        None, description="ID of the message containing the prediction"
    )
    validation_criteria: str | None = Field(
        None, max_length=1000, description="Criteria for validating the prediction"
    )
    expected_resolution_date: date = Field(
        ..., description="When the prediction should be resolved"
    )


class PredictionUpdate(BaseModel):
    """Request model for updating a prediction."""

    prediction_text: str | None = Field(None, min_length=1, max_length=2000)
    predicted_outcome: str | None = None
    validation_criteria: str | None = Field(None, max_length=1000)
    expected_resolution_date: date | None = None
    status: PredictionStatus | None = None


class PredictionValidate(BaseModel):
    """Request model for validating a prediction outcome."""

    is_correct: bool = Field(..., description="Whether the prediction was correct")
    validation_notes: str | None = Field(
        None, max_length=2000, description="Notes about the validation"
    )


class PredictionResponse(BaseModel):
    """Response model for prediction data."""

    id: str
    user_id: str
    prediction_type: PredictionType
    prediction_text: str
    predicted_outcome: str | None
    confidence: float
    context: dict[str, Any] | None
    source_conversation_id: str | None
    source_message_id: str | None
    validation_criteria: str | None
    expected_resolution_date: date | None
    status: PredictionStatus
    validated_at: datetime | None
    validation_notes: str | None
    created_at: datetime


class CalibrationStatsResponse(BaseModel):
    """Response model for calibration statistics."""

    prediction_type: str = Field(..., description="Type of prediction")
    confidence_bucket: float = Field(
        ..., description="Confidence bucket (0.1, 0.2, ..., 1.0)"
    )
    total_predictions: int = Field(..., description="Total predictions in this bucket")
    correct_predictions: int = Field(..., description="Correct predictions in this bucket")
    accuracy: float = Field(..., description="Actual accuracy (correct/total)")
    is_calibrated: bool = Field(
        ..., description="Whether accuracy is within 10% of confidence"
    )


class AccuracySummaryResponse(BaseModel):
    """Response model for overall prediction accuracy summary."""

    overall_accuracy: float | None = Field(
        None, description="Overall accuracy across all predictions"
    )
    total_predictions: int = Field(..., description="Total validated predictions")
    correct_predictions: int = Field(..., description="Total correct predictions")
    by_type: dict[str, float | None] = Field(
        ..., description="Accuracy by prediction type"
    )


class ExtractedPrediction(BaseModel):
    """Model for a prediction extracted from ARIA's response."""

    content: str = Field(..., description="What is being predicted")
    predicted_outcome: str | None = Field(None, description="Expected result")
    prediction_type: PredictionType = Field(..., description="Category of prediction")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level")
    timeframe_days: int = Field(
        30, ge=1, le=365, description="Days until expected resolution"
    )
```

**Step 4: Update models __init__.py**

Add to `backend/src/models/__init__.py`:

```python
from src.models.prediction import (
    AccuracySummaryResponse,
    CalibrationStatsResponse,
    ExtractedPrediction,
    PredictionCreate,
    PredictionResponse,
    PredictionStatus,
    PredictionType,
    PredictionUpdate,
    PredictionValidate,
)
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_prediction_models.py -v`
Expected: PASS all 5 tests

**Step 6: Commit**

```bash
git add backend/src/models/prediction.py backend/src/models/__init__.py backend/tests/test_prediction_models.py
git commit -m "feat(models): add prediction Pydantic models for US-422"
```

---

## Task 3: Create PredictionService - Core Methods

**Files:**
- Create: `backend/src/services/prediction_service.py`
- Modify: `backend/src/services/__init__.py`

**Step 1: Write the failing tests for core CRUD**

Create `backend/tests/test_prediction_service.py`:

```python
"""Tests for prediction service."""

from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch
from typing import Any

import pytest


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock Supabase client."""
    return MagicMock()


@pytest.mark.asyncio
async def test_register_stores_prediction_in_database(mock_db: MagicMock) -> None:
    """Test register stores prediction in database."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "pred-123",
                    "user_id": "user-456",
                    "prediction_type": "deal_outcome",
                    "prediction_text": "Acme deal will close",
                    "confidence": 0.75,
                    "status": "pending",
                    "expected_resolution_date": "2026-03-01",
                    "created_at": "2026-02-03T10:00:00Z",
                }
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.prediction import PredictionCreate, PredictionType
        from src.services.prediction_service import PredictionService

        service = PredictionService()
        data = PredictionCreate(
            prediction_type=PredictionType.DEAL_OUTCOME,
            prediction_text="Acme deal will close",
            confidence=0.75,
            expected_resolution_date=date(2026, 3, 1),
        )

        result = await service.register("user-456", data)

        assert result["id"] == "pred-123"
        assert result["prediction_type"] == "deal_outcome"
        assert result["confidence"] == 0.75
        assert result["status"] == "pending"
        mock_db.table.assert_called_with("predictions")


@pytest.mark.asyncio
async def test_get_prediction_returns_prediction(mock_db: MagicMock) -> None:
    """Test get_prediction returns a single prediction."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        expected = {
            "id": "pred-123",
            "user_id": "user-456",
            "prediction_type": "deal_outcome",
            "prediction_text": "Acme deal will close",
            "status": "pending",
        }
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=expected
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.prediction_service import PredictionService

        service = PredictionService()
        result = await service.get_prediction("user-456", "pred-123")

        assert result["id"] == "pred-123"
        assert result["prediction_type"] == "deal_outcome"


@pytest.mark.asyncio
async def test_get_prediction_returns_none_when_not_found(mock_db: MagicMock) -> None:
    """Test get_prediction returns None when not found."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.prediction_service import PredictionService

        service = PredictionService()
        result = await service.get_prediction("user-456", "pred-999")

        assert result is None


@pytest.mark.asyncio
async def test_list_predictions_returns_all_by_default(mock_db: MagicMock) -> None:
    """Test list_predictions returns all predictions without filters."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        expected = [
            {"id": "pred-1", "status": "pending"},
            {"id": "pred-2", "status": "validated_correct"},
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=expected
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.prediction_service import PredictionService

        service = PredictionService()
        result = await service.list_predictions("user-456")

        assert len(result) == 2


@pytest.mark.asyncio
async def test_list_predictions_filters_by_status(mock_db: MagicMock) -> None:
    """Test list_predictions filters by status."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "pred-1", "status": "pending"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.prediction import PredictionStatus
        from src.services.prediction_service import PredictionService

        service = PredictionService()
        result = await service.list_predictions("user-456", status=PredictionStatus.PENDING)

        assert len(result) == 1


@pytest.mark.asyncio
async def test_list_predictions_filters_by_type(mock_db: MagicMock) -> None:
    """Test list_predictions filters by prediction type."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "pred-1", "prediction_type": "deal_outcome"}]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.prediction import PredictionType
        from src.services.prediction_service import PredictionService

        service = PredictionService()
        result = await service.list_predictions("user-456", prediction_type=PredictionType.DEAL_OUTCOME)

        assert len(result) == 1


@pytest.mark.asyncio
async def test_get_pending_returns_pending_predictions(mock_db: MagicMock) -> None:
    """Test get_pending returns only pending predictions."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        expected = [
            {"id": "pred-1", "status": "pending", "expected_resolution_date": "2026-02-10"},
        ]
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
            data=expected
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.prediction_service import PredictionService

        service = PredictionService()
        result = await service.get_pending("user-456")

        assert len(result) == 1
        assert result[0]["status"] == "pending"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_prediction_service.py -v -k "register or get_prediction or list_predictions or get_pending"`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.services.prediction_service'"

**Step 3: Write the service file with core methods**

Create `backend/src/services/prediction_service.py`:

```python
"""Prediction service for ARIA.

This service handles:
- Registering and tracking predictions
- Validating prediction outcomes
- Calculating calibration statistics
- Extracting predictions from ARIA responses
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.models.prediction import (
    PredictionCreate,
    PredictionStatus,
    PredictionType,
    PredictionUpdate,
    PredictionValidate,
)

logger = logging.getLogger(__name__)


class PredictionService:
    """Service for prediction tracking and calibration."""

    def __init__(self) -> None:
        """Initialize prediction service with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def register(self, user_id: str, data: PredictionCreate) -> dict[str, Any]:
        """Register a new prediction.

        Args:
            user_id: The user's ID.
            data: Prediction creation data.

        Returns:
            Created prediction dict.
        """
        logger.info(
            "Registering prediction",
            extra={
                "user_id": user_id,
                "prediction_type": data.prediction_type.value,
                "confidence": data.confidence,
            },
        )

        result = (
            self._db.table("predictions")
            .insert(
                {
                    "user_id": user_id,
                    "prediction_type": data.prediction_type.value,
                    "prediction_text": data.prediction_text,
                    "predicted_outcome": data.predicted_outcome,
                    "confidence": data.confidence,
                    "context": data.context,
                    "source_conversation_id": data.source_conversation_id,
                    "source_message_id": data.source_message_id,
                    "validation_criteria": data.validation_criteria,
                    "expected_resolution_date": data.expected_resolution_date.isoformat(),
                    "status": PredictionStatus.PENDING.value,
                }
            )
            .execute()
        )

        prediction = cast(dict[str, Any], result.data[0])
        logger.info("Prediction registered", extra={"prediction_id": prediction["id"]})
        return prediction

    async def get_prediction(
        self, user_id: str, prediction_id: str
    ) -> dict[str, Any] | None:
        """Get a prediction by ID.

        Args:
            user_id: The user's ID.
            prediction_id: The prediction ID.

        Returns:
            Prediction dict, or None if not found.
        """
        result = (
            self._db.table("predictions")
            .select("*")
            .eq("id", prediction_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )

        if result.data is None:
            logger.warning(
                "Prediction not found",
                extra={"user_id": user_id, "prediction_id": prediction_id},
            )
            return None

        logger.info("Prediction retrieved", extra={"prediction_id": prediction_id})
        return cast(dict[str, Any], result.data)

    async def list_predictions(
        self,
        user_id: str,
        status: PredictionStatus | None = None,
        prediction_type: PredictionType | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List user's predictions.

        Args:
            user_id: The user's ID.
            status: Optional filter by prediction status.
            prediction_type: Optional filter by prediction type.
            limit: Maximum number of predictions to return.

        Returns:
            List of prediction dicts.
        """
        query = self._db.table("predictions").select("*").eq("user_id", user_id)

        if status:
            query = query.eq("status", status.value)

        if prediction_type:
            query = query.eq("prediction_type", prediction_type.value)

        result = query.order("created_at", desc=True).limit(limit).execute()

        logger.info(
            "Predictions listed",
            extra={"user_id": user_id, "count": len(result.data)},
        )

        return cast(list[dict[str, Any]], result.data)

    async def get_pending(self, user_id: str) -> list[dict[str, Any]]:
        """Get pending predictions ready for validation.

        Args:
            user_id: The user's ID.

        Returns:
            List of pending predictions sorted by resolution date.
        """
        result = (
            self._db.table("predictions")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", PredictionStatus.PENDING.value)
            .order("expected_resolution_date")
            .execute()
        )

        logger.info(
            "Pending predictions retrieved",
            extra={"user_id": user_id, "count": len(result.data)},
        )

        return cast(list[dict[str, Any]], result.data)

    async def update_prediction(
        self, user_id: str, prediction_id: str, data: PredictionUpdate
    ) -> dict[str, Any] | None:
        """Update a prediction.

        Args:
            user_id: The user's ID.
            prediction_id: The prediction ID.
            data: Prediction update data.

        Returns:
            Updated prediction dict, or None if not found.
        """
        update_data: dict[str, Any] = {
            k: v.value if hasattr(v, "value") else v
            for k, v in data.model_dump(exclude_unset=True).items()
        }

        # Convert date to string
        if "expected_resolution_date" in update_data and update_data["expected_resolution_date"]:
            update_data["expected_resolution_date"] = update_data[
                "expected_resolution_date"
            ].isoformat()

        result = (
            self._db.table("predictions")
            .update(update_data)
            .eq("id", prediction_id)
            .eq("user_id", user_id)
            .execute()
        )

        if result.data:
            logger.info("Prediction updated", extra={"prediction_id": prediction_id})
            return cast(dict[str, Any], result.data[0])

        logger.warning(
            "Prediction not found for update", extra={"prediction_id": prediction_id}
        )
        return None
```

**Step 4: Update services __init__.py**

Add to `backend/src/services/__init__.py`:

```python
from src.services.prediction_service import PredictionService
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_prediction_service.py -v -k "register or get_prediction or list_predictions or get_pending"`
Expected: PASS all 7 tests

**Step 6: Commit**

```bash
git add backend/src/services/prediction_service.py backend/src/services/__init__.py backend/tests/test_prediction_service.py
git commit -m "feat(service): add PredictionService core CRUD methods for US-422"
```

---

## Task 4: Add Validation and Calibration Methods

**Files:**
- Modify: `backend/src/services/prediction_service.py`
- Modify: `backend/tests/test_prediction_service.py`

**Step 1: Add tests for validation and calibration**

Add to `backend/tests/test_prediction_service.py`:

```python
@pytest.mark.asyncio
async def test_validate_updates_prediction_and_calibration(mock_db: MagicMock) -> None:
    """Test validate updates prediction status and calls calibration upsert."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        # Mock getting the prediction first
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "pred-123",
                "user_id": "user-456",
                "prediction_type": "deal_outcome",
                "confidence": 0.75,
                "status": "pending",
            }
        )
        # Mock the update
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "pred-123",
                    "status": "validated_correct",
                    "validated_at": "2026-02-03T12:00:00Z",
                }
            ]
        )
        # Mock the RPC call
        mock_db.rpc.return_value.execute.return_value = MagicMock(data=None)
        mock_db_class.get_client.return_value = mock_db

        from src.models.prediction import PredictionValidate
        from src.services.prediction_service import PredictionService

        service = PredictionService()
        data = PredictionValidate(is_correct=True, validation_notes="Deal closed as predicted")

        result = await service.validate("user-456", "pred-123", data)

        assert result["status"] == "validated_correct"
        mock_db.rpc.assert_called_once()


@pytest.mark.asyncio
async def test_validate_returns_none_when_not_found(mock_db: MagicMock) -> None:
    """Test validate returns None when prediction not found."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.prediction import PredictionValidate
        from src.services.prediction_service import PredictionService

        service = PredictionService()
        data = PredictionValidate(is_correct=True)

        result = await service.validate("user-456", "pred-999", data)

        assert result is None


@pytest.mark.asyncio
async def test_get_calibration_stats_returns_stats(mock_db: MagicMock) -> None:
    """Test get_calibration_stats returns calibration statistics."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "prediction_type": "deal_outcome",
                    "confidence_bucket": 0.8,
                    "total_predictions": 100,
                    "correct_predictions": 78,
                },
                {
                    "prediction_type": "deal_outcome",
                    "confidence_bucket": 0.7,
                    "total_predictions": 50,
                    "correct_predictions": 35,
                },
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.prediction_service import PredictionService

        service = PredictionService()
        result = await service.get_calibration_stats("user-456")

        assert len(result) == 2
        assert result[0]["accuracy"] == 0.78
        assert result[0]["is_calibrated"] is True  # 0.78 is within 0.1 of 0.8


@pytest.mark.asyncio
async def test_get_calibration_stats_filters_by_type(mock_db: MagicMock) -> None:
    """Test get_calibration_stats filters by prediction type."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "prediction_type": "deal_outcome",
                    "confidence_bucket": 0.8,
                    "total_predictions": 100,
                    "correct_predictions": 78,
                },
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.models.prediction import PredictionType
        from src.services.prediction_service import PredictionService

        service = PredictionService()
        result = await service.get_calibration_stats(
            "user-456", prediction_type=PredictionType.DEAL_OUTCOME
        )

        assert len(result) == 1


@pytest.mark.asyncio
async def test_get_accuracy_summary_returns_summary(mock_db: MagicMock) -> None:
    """Test get_accuracy_summary returns overall accuracy stats."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
            data=[
                {"status": "validated_correct", "prediction_type": "deal_outcome"},
                {"status": "validated_correct", "prediction_type": "deal_outcome"},
                {"status": "validated_incorrect", "prediction_type": "deal_outcome"},
                {"status": "validated_correct", "prediction_type": "timing"},
            ]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.prediction_service import PredictionService

        service = PredictionService()
        result = await service.get_accuracy_summary("user-456")

        assert result["total_predictions"] == 4
        assert result["correct_predictions"] == 3
        assert result["overall_accuracy"] == 0.75
        assert result["by_type"]["deal_outcome"] == 2 / 3
        assert result["by_type"]["timing"] == 1.0


@pytest.mark.asyncio
async def test_confidence_to_bucket_rounds_correctly() -> None:
    """Test confidence_to_bucket rounds to nearest 0.1."""
    from src.services.prediction_service import PredictionService

    service = PredictionService()

    assert service._confidence_to_bucket(0.75) == 0.8
    assert service._confidence_to_bucket(0.74) == 0.7
    assert service._confidence_to_bucket(0.05) == 0.1  # Minimum bucket
    assert service._confidence_to_bucket(0.99) == 1.0
    assert service._confidence_to_bucket(0.0) == 0.1  # Clamp to minimum
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_prediction_service.py -v -k "validate or calibration or accuracy or bucket"`
Expected: FAIL with AttributeError

**Step 3: Add validation and calibration methods to service**

Add to `backend/src/services/prediction_service.py`:

```python
    def _confidence_to_bucket(self, confidence: float) -> float:
        """Round confidence to nearest 0.1 bucket.

        Args:
            confidence: Raw confidence value (0.0-1.0).

        Returns:
            Bucketed confidence (0.1, 0.2, ..., 1.0).
        """
        bucket = round(confidence * 10) / 10
        return max(0.1, min(1.0, bucket))

    async def validate(
        self, user_id: str, prediction_id: str, data: PredictionValidate
    ) -> dict[str, Any] | None:
        """Validate a prediction with actual outcome.

        Args:
            user_id: The user's ID.
            prediction_id: The prediction ID.
            data: Validation data with is_correct and optional notes.

        Returns:
            Updated prediction dict, or None if not found.
        """
        # Get the prediction first
        prediction = await self.get_prediction(user_id, prediction_id)
        if prediction is None:
            return None

        # Determine new status
        status = (
            PredictionStatus.VALIDATED_CORRECT
            if data.is_correct
            else PredictionStatus.VALIDATED_INCORRECT
        )

        now = datetime.now(UTC).isoformat()

        # Update the prediction
        result = (
            self._db.table("predictions")
            .update(
                {
                    "status": status.value,
                    "validated_at": now,
                    "validation_notes": data.validation_notes,
                }
            )
            .eq("id", prediction_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data:
            logger.warning(
                "Prediction not found for validation",
                extra={"prediction_id": prediction_id},
            )
            return None

        # Update calibration stats
        bucket = self._confidence_to_bucket(prediction["confidence"])
        await self._update_calibration(
            user_id=user_id,
            prediction_type=prediction["prediction_type"],
            confidence_bucket=bucket,
            is_correct=data.is_correct,
        )

        logger.info(
            "Prediction validated",
            extra={
                "prediction_id": prediction_id,
                "is_correct": data.is_correct,
                "confidence": prediction["confidence"],
                "bucket": bucket,
            },
        )

        return cast(dict[str, Any], result.data[0])

    async def _update_calibration(
        self,
        user_id: str,
        prediction_type: str,
        confidence_bucket: float,
        is_correct: bool,
    ) -> None:
        """Update calibration statistics via RPC.

        Args:
            user_id: The user's ID.
            prediction_type: Type of prediction.
            confidence_bucket: Rounded confidence bucket.
            is_correct: Whether prediction was correct.
        """
        self._db.rpc(
            "upsert_calibration",
            {
                "p_user_id": user_id,
                "p_prediction_type": prediction_type,
                "p_confidence_bucket": confidence_bucket,
                "p_is_correct": is_correct,
            },
        ).execute()

        logger.debug(
            "Calibration updated",
            extra={
                "user_id": user_id,
                "prediction_type": prediction_type,
                "bucket": confidence_bucket,
            },
        )

    async def get_calibration_stats(
        self, user_id: str, prediction_type: PredictionType | None = None
    ) -> list[dict[str, Any]]:
        """Get calibration statistics.

        Args:
            user_id: The user's ID.
            prediction_type: Optional filter by prediction type.

        Returns:
            List of calibration stats with accuracy and calibration status.
        """
        query = self._db.table("prediction_calibration").select("*").eq("user_id", user_id)

        if prediction_type:
            query = query.eq("prediction_type", prediction_type.value)

        result = query.execute()

        stats = []
        for row in result.data:
            total = row["total_predictions"]
            correct = row["correct_predictions"]
            accuracy = correct / total if total > 0 else 0.0
            bucket = row["confidence_bucket"]

            # Calibrated if accuracy is within 10% of confidence bucket
            is_calibrated = abs(accuracy - bucket) <= 0.1

            stats.append(
                {
                    "prediction_type": row["prediction_type"],
                    "confidence_bucket": bucket,
                    "total_predictions": total,
                    "correct_predictions": correct,
                    "accuracy": accuracy,
                    "is_calibrated": is_calibrated,
                }
            )

        logger.info(
            "Calibration stats retrieved",
            extra={"user_id": user_id, "bucket_count": len(stats)},
        )

        return stats

    async def get_accuracy_summary(self, user_id: str) -> dict[str, Any]:
        """Get overall prediction accuracy summary.

        Args:
            user_id: The user's ID.

        Returns:
            Summary with overall accuracy and breakdown by type.
        """
        result = (
            self._db.table("predictions")
            .select("status, prediction_type")
            .eq("user_id", user_id)
            .in_("status", ["validated_correct", "validated_incorrect"])
            .execute()
        )

        total = len(result.data)
        correct = len([p for p in result.data if p["status"] == "validated_correct"])

        by_type: dict[str, dict[str, int]] = {}
        for pred in result.data:
            ptype = pred["prediction_type"]
            if ptype not in by_type:
                by_type[ptype] = {"total": 0, "correct": 0}
            by_type[ptype]["total"] += 1
            if pred["status"] == "validated_correct":
                by_type[ptype]["correct"] += 1

        summary = {
            "overall_accuracy": correct / total if total > 0 else None,
            "total_predictions": total,
            "correct_predictions": correct,
            "by_type": {
                k: v["correct"] / v["total"] if v["total"] > 0 else None
                for k, v in by_type.items()
            },
        }

        logger.info(
            "Accuracy summary retrieved",
            extra={
                "user_id": user_id,
                "total": total,
                "correct": correct,
            },
        )

        return summary
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_prediction_service.py -v`
Expected: PASS all tests

**Step 5: Commit**

```bash
git add backend/src/services/prediction_service.py backend/tests/test_prediction_service.py
git commit -m "feat(service): add validation and calibration methods to PredictionService"
```

---

## Task 5: Add Prediction Extraction via LLM

**Files:**
- Modify: `backend/src/services/prediction_service.py`
- Modify: `backend/tests/test_prediction_service.py`

**Step 1: Add tests for extraction**

Add to `backend/tests/test_prediction_service.py`:

```python
@pytest.mark.asyncio
async def test_extract_and_register_parses_predictions(mock_db: MagicMock) -> None:
    """Test extract_and_register extracts predictions from text."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        with patch("src.services.prediction_service.LLMClient") as mock_llm_class:
            # Mock LLM response
            mock_llm = MagicMock()
            mock_llm.generate_response = MagicMock(
                return_value='[{"content": "Deal will close by March", "predicted_outcome": "Deal closed", "prediction_type": "deal_outcome", "confidence": 0.8, "timeframe_days": 30}]'
            )
            mock_llm_class.return_value = mock_llm

            # Mock DB insert
            mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
                data=[
                    {
                        "id": "pred-123",
                        "prediction_type": "deal_outcome",
                        "prediction_text": "Deal will close by March",
                        "confidence": 0.8,
                        "status": "pending",
                    }
                ]
            )
            mock_db_class.get_client.return_value = mock_db

            from src.services.prediction_service import PredictionService

            service = PredictionService()
            results = await service.extract_and_register(
                user_id="user-456",
                response_text="I believe this deal will close by March with high confidence.",
                conversation_id="conv-789",
                message_id="msg-101",
            )

            assert len(results) == 1
            assert results[0]["prediction_type"] == "deal_outcome"


@pytest.mark.asyncio
async def test_extract_and_register_handles_no_predictions(mock_db: MagicMock) -> None:
    """Test extract_and_register returns empty list when no predictions found."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        with patch("src.services.prediction_service.LLMClient") as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm.generate_response = MagicMock(return_value="[]")
            mock_llm_class.return_value = mock_llm
            mock_db_class.get_client.return_value = mock_db

            from src.services.prediction_service import PredictionService

            service = PredictionService()
            results = await service.extract_and_register(
                user_id="user-456",
                response_text="Here is the information you requested.",
                conversation_id="conv-789",
                message_id="msg-101",
            )

            assert results == []


@pytest.mark.asyncio
async def test_extract_and_register_handles_invalid_json(mock_db: MagicMock) -> None:
    """Test extract_and_register handles invalid JSON gracefully."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        with patch("src.services.prediction_service.LLMClient") as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm.generate_response = MagicMock(return_value="not valid json")
            mock_llm_class.return_value = mock_llm
            mock_db_class.get_client.return_value = mock_db

            from src.services.prediction_service import PredictionService

            service = PredictionService()
            results = await service.extract_and_register(
                user_id="user-456",
                response_text="Some text",
                conversation_id="conv-789",
                message_id="msg-101",
            )

            assert results == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_prediction_service.py -v -k "extract"`
Expected: FAIL with AttributeError

**Step 3: Add extraction method to service**

Add to `backend/src/services/prediction_service.py` (add import at top):

```python
import json

from src.core.llm import LLMClient
```

Add method to class:

```python
    async def extract_and_register(
        self,
        user_id: str,
        response_text: str,
        conversation_id: str | None = None,
        message_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Extract predictions from ARIA's response and register them.

        Uses LLM to parse the response text and identify implicit/explicit
        predictions, then registers each with appropriate metadata.

        Args:
            user_id: The user's ID.
            response_text: ARIA's response text to analyze.
            conversation_id: Optional conversation ID for context.
            message_id: Optional message ID for context.

        Returns:
            List of registered prediction dicts.
        """
        extraction_prompt = """Analyze this AI assistant response and extract any predictions made.

A prediction is a statement about what WILL happen in the future. Look for:
- Explicit predictions: "I predict...", "This will likely...", "I expect..."
- Implicit predictions: confidence about future outcomes, deal closures, timelines
- Probability statements: "There's an 80% chance...", "It's likely that..."

For each prediction found, return a JSON object with:
- content: what is being predicted (the prediction statement)
- predicted_outcome: the expected result (if stated)
- prediction_type: one of [user_action, external_event, deal_outcome, timing, market_signal, lead_response, meeting_outcome]
- confidence: estimated confidence 0.0-1.0 based on language used
- timeframe_days: when this should resolve (days from now, default 30)

Return a JSON array of predictions. Return [] if no predictions found.

Response to analyze:
{response_text}

JSON array only, no explanation:"""

        try:
            llm = LLMClient()
            llm_response = await llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": extraction_prompt.format(response_text=response_text),
                    }
                ],
                temperature=0.0,
                max_tokens=1000,
            )

            # Parse JSON response
            extracted = json.loads(llm_response.strip())

            if not isinstance(extracted, list) or not extracted:
                logger.debug(
                    "No predictions extracted",
                    extra={"user_id": user_id, "response_length": len(response_text)},
                )
                return []

        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse LLM extraction response",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []
        except Exception as e:
            logger.exception(
                "Error during prediction extraction",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

        # Register each extracted prediction
        from datetime import timedelta

        registered = []
        for pred_data in extracted:
            try:
                prediction_type = PredictionType(pred_data.get("prediction_type", "timing"))
                timeframe = pred_data.get("timeframe_days", 30)
                expected_date = datetime.now(UTC).date() + timedelta(days=timeframe)

                data = PredictionCreate(
                    prediction_type=prediction_type,
                    prediction_text=pred_data["content"],
                    predicted_outcome=pred_data.get("predicted_outcome"),
                    confidence=float(pred_data.get("confidence", 0.5)),
                    source_conversation_id=conversation_id,
                    source_message_id=message_id,
                    expected_resolution_date=expected_date,
                )

                result = await self.register(user_id, data)
                registered.append(result)

            except (KeyError, ValueError) as e:
                logger.warning(
                    "Invalid prediction data from extraction",
                    extra={"user_id": user_id, "error": str(e), "data": pred_data},
                )
                continue

        logger.info(
            "Predictions extracted and registered",
            extra={
                "user_id": user_id,
                "extracted_count": len(extracted),
                "registered_count": len(registered),
            },
        )

        return registered
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_prediction_service.py -v`
Expected: PASS all tests

**Step 5: Commit**

```bash
git add backend/src/services/prediction_service.py backend/tests/test_prediction_service.py
git commit -m "feat(service): add LLM-based prediction extraction to PredictionService"
```

---

## Task 6: Create API Routes

**Files:**
- Create: `backend/src/api/routes/predictions.py`
- Modify: `backend/src/api/routes/__init__.py`
- Modify: `backend/src/main.py`

**Step 1: Write the failing tests**

Create `backend/tests/test_api_predictions.py`:

```python
"""Tests for prediction API endpoints."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_user() -> MagicMock:
    """Create mock user."""
    user = MagicMock()
    user.id = "user-456"
    return user


@pytest.fixture
def client(mock_user: MagicMock) -> TestClient:
    """Create test client with mocked auth."""
    with patch("src.api.deps.get_current_user", return_value=mock_user):
        from src.main import app
        return TestClient(app)


def test_create_prediction_returns_created(client: TestClient, mock_user: MagicMock) -> None:
    """Test POST /predictions creates and returns prediction."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.register = AsyncMock(
            return_value={
                "id": "pred-123",
                "prediction_type": "deal_outcome",
                "prediction_text": "Deal will close",
                "confidence": 0.8,
                "status": "pending",
            }
        )
        mock_service_factory.return_value = mock_service

        response = client.post(
            "/api/v1/predictions",
            json={
                "prediction_type": "deal_outcome",
                "prediction_text": "Deal will close",
                "confidence": 0.8,
                "expected_resolution_date": "2026-03-01",
            },
        )

        assert response.status_code == 200
        assert response.json()["id"] == "pred-123"


def test_list_predictions_returns_list(client: TestClient, mock_user: MagicMock) -> None:
    """Test GET /predictions returns list."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.list_predictions = AsyncMock(
            return_value=[
                {"id": "pred-1", "status": "pending"},
                {"id": "pred-2", "status": "validated_correct"},
            ]
        )
        mock_service_factory.return_value = mock_service

        response = client.get("/api/v1/predictions")

        assert response.status_code == 200
        assert len(response.json()) == 2


def test_get_prediction_returns_prediction(client: TestClient, mock_user: MagicMock) -> None:
    """Test GET /predictions/{id} returns prediction."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.get_prediction = AsyncMock(
            return_value={"id": "pred-123", "prediction_type": "deal_outcome"}
        )
        mock_service_factory.return_value = mock_service

        response = client.get("/api/v1/predictions/pred-123")

        assert response.status_code == 200
        assert response.json()["id"] == "pred-123"


def test_get_prediction_returns_404_when_not_found(client: TestClient, mock_user: MagicMock) -> None:
    """Test GET /predictions/{id} returns 404 when not found."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.get_prediction = AsyncMock(return_value=None)
        mock_service_factory.return_value = mock_service

        response = client.get("/api/v1/predictions/pred-999")

        assert response.status_code == 404


def test_validate_prediction_updates_status(client: TestClient, mock_user: MagicMock) -> None:
    """Test PUT /predictions/{id}/validate updates prediction."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.validate = AsyncMock(
            return_value={"id": "pred-123", "status": "validated_correct"}
        )
        mock_service_factory.return_value = mock_service

        response = client.put(
            "/api/v1/predictions/pred-123/validate",
            json={"is_correct": True, "validation_notes": "Closed as predicted"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "validated_correct"


def test_get_calibration_returns_stats(client: TestClient, mock_user: MagicMock) -> None:
    """Test GET /predictions/calibration returns calibration stats."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.get_calibration_stats = AsyncMock(
            return_value=[
                {
                    "prediction_type": "deal_outcome",
                    "confidence_bucket": 0.8,
                    "total_predictions": 100,
                    "correct_predictions": 78,
                    "accuracy": 0.78,
                    "is_calibrated": True,
                }
            ]
        )
        mock_service_factory.return_value = mock_service

        response = client.get("/api/v1/predictions/calibration")

        assert response.status_code == 200
        assert len(response.json()) == 1


def test_get_pending_returns_pending_predictions(client: TestClient, mock_user: MagicMock) -> None:
    """Test GET /predictions/pending returns pending predictions."""
    with patch("src.api.routes.predictions._get_service") as mock_service_factory:
        mock_service = MagicMock()
        mock_service.get_pending = AsyncMock(
            return_value=[{"id": "pred-1", "status": "pending"}]
        )
        mock_service_factory.return_value = mock_service

        response = client.get("/api/v1/predictions/pending")

        assert response.status_code == 200
        assert len(response.json()) == 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_predictions.py -v`
Expected: FAIL with ImportError

**Step 3: Create the routes file**

Create `backend/src/api/routes/predictions.py`:

```python
"""Prediction API routes for ARIA.

This module provides endpoints for:
- Registering predictions
- Listing and retrieving predictions
- Validating prediction outcomes
- Getting calibration statistics
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.api.deps import CurrentUser
from src.models.prediction import (
    PredictionCreate,
    PredictionStatus,
    PredictionType,
    PredictionValidate,
)
from src.services.prediction_service import PredictionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/predictions", tags=["predictions"])


def _get_service() -> PredictionService:
    """Get prediction service instance."""
    return PredictionService()


@router.post("")
async def create_prediction(
    data: PredictionCreate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Register a new prediction.

    Creates a new prediction with the provided type, text, and confidence.
    Predictions start in pending status.
    """
    service = _get_service()
    result = await service.register(current_user.id, data)

    logger.info(
        "Prediction created via API",
        extra={
            "user_id": current_user.id,
            "prediction_id": result["id"],
            "prediction_type": data.prediction_type.value,
        },
    )

    return result


@router.get("")
async def list_predictions(
    current_user: CurrentUser,
    status: PredictionStatus | None = Query(None, description="Filter by status"),
    prediction_type: PredictionType | None = Query(
        None, description="Filter by prediction type"
    ),
    limit: int = Query(50, ge=1, le=100, description="Maximum predictions to return"),
) -> list[dict[str, Any]]:
    """List user's predictions.

    Returns a list of predictions, optionally filtered by status or type.
    """
    service = _get_service()
    predictions = await service.list_predictions(
        current_user.id, status, prediction_type, limit
    )

    logger.info(
        "Predictions listed via API",
        extra={"user_id": current_user.id, "count": len(predictions)},
    )

    return predictions


@router.get("/pending")
async def get_pending_predictions(
    current_user: CurrentUser,
) -> list[dict[str, Any]]:
    """Get pending predictions needing validation.

    Returns predictions that are still pending, sorted by expected resolution date.
    """
    service = _get_service()
    predictions = await service.get_pending(current_user.id)

    logger.info(
        "Pending predictions retrieved via API",
        extra={"user_id": current_user.id, "count": len(predictions)},
    )

    return predictions


@router.get("/calibration")
async def get_calibration_stats(
    current_user: CurrentUser,
    prediction_type: PredictionType | None = Query(
        None, description="Filter by prediction type"
    ),
) -> list[dict[str, Any]]:
    """Get calibration statistics.

    Returns accuracy statistics by confidence bucket to show how well
    calibrated ARIA's predictions are.
    """
    service = _get_service()
    stats = await service.get_calibration_stats(current_user.id, prediction_type)

    logger.info(
        "Calibration stats retrieved via API",
        extra={"user_id": current_user.id, "bucket_count": len(stats)},
    )

    return stats


@router.get("/accuracy")
async def get_accuracy_summary(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get overall prediction accuracy summary.

    Returns summary of prediction accuracy including overall accuracy
    and breakdown by prediction type.
    """
    service = _get_service()
    summary = await service.get_accuracy_summary(current_user.id)

    logger.info(
        "Accuracy summary retrieved via API",
        extra={
            "user_id": current_user.id,
            "total": summary["total_predictions"],
        },
    )

    return summary


@router.get("/{prediction_id}")
async def get_prediction(
    prediction_id: str,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get a specific prediction.

    Returns detailed information about a single prediction.
    """
    service = _get_service()
    prediction = await service.get_prediction(current_user.id, prediction_id)

    if prediction is None:
        logger.warning(
            "Prediction not found via API",
            extra={"user_id": current_user.id, "prediction_id": prediction_id},
        )
        raise HTTPException(status_code=404, detail="Prediction not found")

    logger.info("Prediction retrieved via API", extra={"prediction_id": prediction_id})

    return prediction


@router.put("/{prediction_id}/validate")
async def validate_prediction(
    prediction_id: str,
    data: PredictionValidate,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Validate a prediction with actual outcome.

    Marks a prediction as correct or incorrect and updates calibration statistics.
    """
    service = _get_service()
    prediction = await service.validate(current_user.id, prediction_id, data)

    if prediction is None:
        logger.warning(
            "Prediction not found for validation via API",
            extra={"user_id": current_user.id, "prediction_id": prediction_id},
        )
        raise HTTPException(status_code=404, detail="Prediction not found")

    logger.info(
        "Prediction validated via API",
        extra={
            "prediction_id": prediction_id,
            "is_correct": data.is_correct,
        },
    )

    return prediction
```

**Step 4: Update routes __init__.py**

Add to `backend/src/api/routes/__init__.py`:

```python
from src.api.routes import predictions
```

**Step 5: Update main.py to include router**

Add import at top of `backend/src/main.py`:

```python
from src.api.routes import predictions
```

Add router after other routers:

```python
app.include_router(predictions.router, prefix="/api/v1")
```

**Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_predictions.py -v`
Expected: PASS all tests

**Step 7: Commit**

```bash
git add backend/src/api/routes/predictions.py backend/src/api/routes/__init__.py backend/src/main.py backend/tests/test_api_predictions.py
git commit -m "feat(api): add prediction API endpoints for US-422"
```

---

## Task 7: Run Full Test Suite and Lint

**Files:**
- All backend files

**Step 1: Run all prediction tests**

Run: `cd backend && python -m pytest tests/test_prediction*.py -v`
Expected: All tests pass

**Step 2: Run type checking**

Run: `cd backend && mypy src/models/prediction.py src/services/prediction_service.py src/api/routes/predictions.py --strict`
Expected: Success with no errors (or minor ignorable warnings)

**Step 3: Run linting**

Run: `cd backend && ruff check src/models/prediction.py src/services/prediction_service.py src/api/routes/predictions.py`
Expected: No errors

**Step 4: Run formatter**

Run: `cd backend && ruff format src/models/prediction.py src/services/prediction_service.py src/api/routes/predictions.py`
Expected: Files formatted

**Step 5: Commit any formatting changes**

```bash
git add -u
git commit -m "style: format prediction files with ruff"
```

---

## Task 8: Integration Test - Full Prediction Lifecycle

**Files:**
- Create: `backend/tests/test_prediction_integration.py`

**Step 1: Write integration test**

Create `backend/tests/test_prediction_integration.py`:

```python
"""Integration tests for prediction lifecycle."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_full_prediction_lifecycle() -> None:
    """Test complete prediction lifecycle: create -> validate -> calibration."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db_class.get_client.return_value = mock_db

        # Step 1: Create prediction
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "pred-lifecycle",
                    "user_id": "user-test",
                    "prediction_type": "deal_outcome",
                    "prediction_text": "Deal will close Q1",
                    "confidence": 0.85,
                    "status": "pending",
                    "expected_resolution_date": "2026-03-31",
                    "created_at": "2026-02-03T10:00:00Z",
                }
            ]
        )

        from src.models.prediction import PredictionCreate, PredictionType
        from src.services.prediction_service import PredictionService

        service = PredictionService()
        created = await service.register(
            "user-test",
            PredictionCreate(
                prediction_type=PredictionType.DEAL_OUTCOME,
                prediction_text="Deal will close Q1",
                confidence=0.85,
                expected_resolution_date=date(2026, 3, 31),
            ),
        )

        assert created["id"] == "pred-lifecycle"
        assert created["status"] == "pending"

        # Step 2: Validate prediction
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data={
                "id": "pred-lifecycle",
                "user_id": "user-test",
                "prediction_type": "deal_outcome",
                "confidence": 0.85,
                "status": "pending",
            }
        )
        mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "pred-lifecycle",
                    "status": "validated_correct",
                    "validated_at": "2026-03-15T14:00:00Z",
                }
            ]
        )
        mock_db.rpc.return_value.execute.return_value = MagicMock(data=None)

        from src.models.prediction import PredictionValidate

        validated = await service.validate(
            "user-test",
            "pred-lifecycle",
            PredictionValidate(is_correct=True, validation_notes="Deal closed March 15"),
        )

        assert validated["status"] == "validated_correct"

        # Verify calibration was updated
        mock_db.rpc.assert_called_with(
            "upsert_calibration",
            {
                "p_user_id": "user-test",
                "p_prediction_type": "deal_outcome",
                "p_confidence_bucket": 0.9,  # 0.85 rounds to 0.9
                "p_is_correct": True,
            },
        )

        # Step 3: Check calibration stats
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "prediction_type": "deal_outcome",
                    "confidence_bucket": 0.9,
                    "total_predictions": 10,
                    "correct_predictions": 8,
                }
            ]
        )

        stats = await service.get_calibration_stats("user-test")

        assert len(stats) == 1
        assert stats[0]["accuracy"] == 0.8
        assert stats[0]["is_calibrated"] is True  # 0.8 is within 0.1 of 0.9
```

**Step 2: Run integration test**

Run: `cd backend && python -m pytest tests/test_prediction_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/test_prediction_integration.py
git commit -m "test: add integration test for prediction lifecycle"
```

---

## Task 9: Final Verification and Documentation

**Step 1: Run complete test suite**

Run: `cd backend && python -m pytest tests/ -v --tb=short`
Expected: All tests pass

**Step 2: Verify API starts**

Run: `cd backend && timeout 5 uvicorn src.main:app --reload --port 8000 || true`
Expected: Server starts without import errors

**Step 3: Check API docs**

The FastAPI auto-docs should show the new endpoints at `/docs`:
- POST /api/v1/predictions
- GET /api/v1/predictions
- GET /api/v1/predictions/pending
- GET /api/v1/predictions/calibration
- GET /api/v1/predictions/accuracy
- GET /api/v1/predictions/{prediction_id}
- PUT /api/v1/predictions/{prediction_id}/validate

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(US-422): complete Prediction Registration System implementation

- Add predictions and prediction_calibration tables with RLS
- Add Pydantic models for prediction CRUD operations
- Add PredictionService with register, validate, extract methods
- Add API endpoints for prediction management
- Add calibration tracking with accuracy by confidence bucket
- Add LLM-based prediction extraction from ARIA responses
- Add comprehensive unit and integration tests

Closes US-422"
```

---

## Summary

This plan implements US-422: Prediction Registration System with:

1. **Database**: `predictions` and `prediction_calibration` tables with RLS
2. **Models**: Pydantic models for all prediction operations
3. **Service**: `PredictionService` with CRUD, validation, calibration, and LLM extraction
4. **API**: RESTful endpoints for prediction management
5. **Tests**: Unit tests for models, service, and API; integration test for lifecycle

**Integration Points** (for future tasks):
- Chat backend can call `extract_and_register()` after generating responses
- Notification system can surface pending predictions for validation
- Daily briefing can include predictions needing validation
- ARIA context can include calibration stats for self-awareness

**Key Files Created:**
- `supabase/migrations/20260203000006_create_predictions.sql`
- `backend/src/models/prediction.py`
- `backend/src/services/prediction_service.py`
- `backend/src/api/routes/predictions.py`
- `backend/tests/test_prediction_models.py`
- `backend/tests/test_prediction_service.py`
- `backend/tests/test_api_predictions.py`
- `backend/tests/test_prediction_integration.py`
