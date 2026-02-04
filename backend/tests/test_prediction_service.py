"""Tests for prediction service."""

from datetime import date
from unittest.mock import MagicMock, patch

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
        result = await service.list_predictions(
            "user-456", prediction_type=PredictionType.DEAL_OUTCOME
        )

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
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
            MagicMock(
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
async def test_confidence_to_bucket_rounds_correctly(mock_db: MagicMock) -> None:
    """Test confidence_to_bucket rounds to nearest 0.1."""
    with patch("src.services.prediction_service.SupabaseClient") as mock_db_class:
        mock_db_class.get_client.return_value = mock_db

        from src.services.prediction_service import PredictionService

        service = PredictionService()

        assert service._confidence_to_bucket(0.75) == 0.8
        assert service._confidence_to_bucket(0.74) == 0.7
        assert service._confidence_to_bucket(0.05) == 0.1  # Minimum bucket
        assert service._confidence_to_bucket(0.99) == 1.0
        assert service._confidence_to_bucket(0.0) == 0.1  # Clamp to minimum
