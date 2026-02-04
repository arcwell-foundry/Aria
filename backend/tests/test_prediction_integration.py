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
        # Note: 0.85 rounds to 0.8 using Python's banker's rounding (round half to even)
        mock_db.rpc.assert_called_with(
            "upsert_calibration",
            {
                "p_user_id": "user-test",
                "p_prediction_type": "deal_outcome",
                "p_confidence_bucket": 0.8,  # 0.85 rounds to 0.8 (banker's rounding)
                "p_is_correct": True,
            },
        )

        # Step 3: Check calibration stats
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "prediction_type": "deal_outcome",
                    "confidence_bucket": 0.8,
                    "total_predictions": 10,
                    "correct_predictions": 8,
                }
            ]
        )

        stats = await service.get_calibration_stats("user-test")

        assert len(stats) == 1
        assert stats[0]["accuracy"] == 0.8
        assert stats[0]["is_calibrated"] is True  # 0.8 matches bucket 0.8 exactly
