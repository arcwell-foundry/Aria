"""Prediction service for ARIA.

This service handles:
- Registering and tracking predictions
- Validating prediction outcomes
- Calculating calibration statistics
- Extracting predictions from ARIA responses
"""

import logging
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.models.prediction import (
    PredictionCreate,
    PredictionStatus,
    PredictionType,
    PredictionUpdate,
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

    async def get_prediction(self, user_id: str, prediction_id: str) -> dict[str, Any] | None:
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

        logger.warning("Prediction not found for update", extra={"prediction_id": prediction_id})
        return None
