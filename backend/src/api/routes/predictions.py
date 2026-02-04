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
    prediction_type: PredictionType | None = Query(None, description="Filter by prediction type"),
    limit: int = Query(50, ge=1, le=100, description="Maximum predictions to return"),
) -> list[dict[str, Any]]:
    """List user's predictions.

    Returns a list of predictions, optionally filtered by status or type.
    """
    service = _get_service()
    predictions = await service.list_predictions(current_user.id, status, prediction_type, limit)

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
    prediction_type: PredictionType | None = Query(None, description="Filter by prediction type"),
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
