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
                k: v["correct"] / v["total"] if v["total"] > 0 else None for k, v in by_type.items()
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
