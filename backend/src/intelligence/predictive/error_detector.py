"""Prediction error detector for the Predictive Processing Engine.

Detects prediction errors (surprises) by comparing predictions against
actual events and generates learning signals for attention allocation.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.intelligence.predictive.models import (
    PredictionCategory,
    PredictionError,
    PredictionStatus,
)

logger = logging.getLogger(__name__)


class PredictionErrorDetector:
    """Detects prediction errors and generates learning signals.

    Compares pending predictions against actual events to identify
    prediction errors (surprises). High surprise levels trigger
    attention allocation to relevant entities.

    Attributes:
        MATCH_THRESHOLD: Below this score, prediction is considered wrong
        HIGH_SURPRISE_THRESHOLD: Above this, boost entity salience
    """

    MATCH_THRESHOLD: float = 0.7
    HIGH_SURPRISE_THRESHOLD: float = 0.6

    def __init__(self, db_client: Any, llm_client: LLMClient | None = None) -> None:
        """Initialize the error detector.

        Args:
            db_client: Supabase client for database queries
            llm_client: LLM client for semantic comparison
        """
        self._db = db_client
        self._llm = llm_client or LLMClient()

    async def detect_errors(self, user_id: str) -> list[PredictionError]:
        """Detect prediction errors for a user.

        Gets pending predictions that have passed their expected resolution
        date and compares them against actual events.

        Args:
            user_id: User ID to detect errors for

        Returns:
            List of detected prediction errors
        """
        logger.info("Detecting prediction errors", extra={"user_id": user_id})

        # Get pending predictions past their resolution date
        pending = await self._get_pending_predictions(user_id)

        if not pending:
            logger.info("No pending predictions to validate", extra={"user_id": user_id})
            return []

        # Get actual events for comparison
        actual_events = await self._get_actual_events(user_id)

        errors: list[PredictionError] = []

        for pred in pending:
            try:
                match_score = await self._compare_prediction_to_actual(pred, actual_events)

                if match_score < self.MATCH_THRESHOLD:
                    # Prediction was wrong - create error
                    error = await self._create_prediction_error(pred, actual_events, match_score)
                    errors.append(error)

                    # Mark prediction as incorrect
                    await self._mark_prediction_status(
                        pred["id"],
                        PredictionStatus.VALIDATED_INCORRECT,
                    )
                else:
                    # Prediction was correct
                    await self._mark_prediction_status(
                        pred["id"],
                        PredictionStatus.VALIDATED_CORRECT,
                    )
                    # Update calibration
                    await self._update_calibration(pred, is_correct=True)

            except Exception as e:
                logger.warning(
                    "Failed to validate prediction",
                    extra={
                        "user_id": user_id,
                        "prediction_id": pred.get("id"),
                        "error": str(e),
                    },
                )

        logger.info(
            "Prediction error detection complete",
            extra={
                "user_id": user_id,
                "predictions_checked": len(pending),
                "errors_detected": len(errors),
            },
        )

        return errors

    async def _get_pending_predictions(self, user_id: str) -> list[dict[str, Any]]:
        """Get pending predictions past their resolution date.

        Args:
            user_id: User ID

        Returns:
            List of pending prediction dictionaries
        """
        now = datetime.now(UTC).isoformat()

        result = (
            self._db.table("predictions")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .lt("expected_resolution_date", now)
            .execute()
        )

        return cast(list[dict[str, Any]], result.data or [])

    async def _get_actual_events(self, user_id: str) -> list[dict[str, Any]]:
        """Get actual events that occurred for comparison.

        Gathers events from multiple sources:
        - Recent conversations
        - Lead status changes
        - Market signals
        - Meeting outcomes

        Args:
            user_id: User ID

        Returns:
            List of actual event dictionaries
        """
        events: list[dict[str, Any]] = []

        try:
            # Get recent conversation summaries
            conv_result = (
                self._db.table("conversations")
                .select("id, summary, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(10)
                .execute()
            )
            for conv in conv_result.data or []:
                events.append(
                    {
                        "type": "conversation",
                        "content": conv.get("summary", ""),
                        "id": conv["id"],
                        "created_at": conv.get("created_at"),
                    }
                )

        except Exception as e:
            logger.debug(f"Failed to get conversations: {e}")

        try:
            # Get recent lead updates
            leads_result = (
                self._db.table("leads")
                .select("id, company_name, lifecycle_stage, updated_at")
                .eq("user_id", user_id)
                .order("updated_at", desc=True)
                .limit(10)
                .execute()
            )
            for lead in leads_result.data or []:
                events.append(
                    {
                        "type": "lead_update",
                        "content": f"{lead.get('company_name')} status: {lead.get('lifecycle_stage')}",
                        "id": lead["id"],
                        "created_at": lead.get("updated_at"),
                    }
                )

        except Exception as e:
            logger.debug(f"Failed to get leads: {e}")

        try:
            # Get recent market signals
            signals_result = (
                self._db.table("market_signals")
                .select("id, summary, signal_type, created_at")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )
            for signal in signals_result.data or []:
                events.append(
                    {
                        "type": "market_signal",
                        "content": signal.get("summary", ""),
                        "id": signal["id"],
                        "created_at": signal.get("created_at"),
                    }
                )

        except Exception as e:
            logger.debug(f"Failed to get signals: {e}")

        return events

    async def _compare_prediction_to_actual(
        self,
        prediction: dict[str, Any],
        actual_events: list[dict[str, Any]],
    ) -> float:
        """Compare a prediction to actual events using LLM.

        Args:
            prediction: Prediction dictionary
            actual_events: List of actual event dictionaries

        Returns:
            Match score (0.0 to 1.0)
        """
        if not actual_events:
            # No events to compare against - can't validate
            return 0.5

        prompt = f"""Compare this prediction to actual events and determine if the prediction came true.

Prediction: {prediction.get("prediction_text", "")}
Expected outcome: {prediction.get("predicted_outcome", "Not specified")}
Confidence: {prediction.get("confidence", 0.5)}

Actual events that occurred:
{json.dumps([e.get("content", "")[:200] for e in actual_events[:10]], indent=2)}

Score the match from 0.0 to 1.0:
- 1.0: Prediction exactly came true
- 0.7+: Prediction mostly came true
- 0.5: Unclear if prediction came true
- 0.3-: Prediction mostly did not come true
- 0.0: Prediction completely wrong

Return ONLY a JSON object: {{"match_score": 0.0-1.0, "reasoning": "brief explanation"}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=200,
                task=TaskType.ANALYST_RESEARCH,
                agent_id="error_detector",
            )

            # Parse response
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

            data = json.loads(response)
            return float(data.get("match_score", 0.5))

        except Exception as e:
            logger.warning(
                "Failed to compare prediction to actual",
                extra={"prediction_id": prediction.get("id"), "error": str(e)},
            )
            return 0.5

    async def _create_prediction_error(
        self,
        prediction: dict[str, Any],
        _actual_events: list[dict[str, Any]],
        match_score: float,
    ) -> PredictionError:
        """Create a prediction error record.

        Args:
            prediction: Failed prediction
            actual_events: Actual events that occurred
            match_score: Match score (low = big surprise)

        Returns:
            PredictionError model
        """
        # Calculate surprise level (inverse of match score)
        surprise_level = 1.0 - match_score

        # Learning signal: high surprise = attend more
        # Low surprise but wrong = still learn but less urgency
        learning_signal = surprise_level

        # Get prediction type
        pred_type_str = prediction.get("prediction_type", "timing")
        try:
            prediction_type = PredictionCategory(pred_type_str)
        except ValueError:
            # Map from PredictionType to PredictionCategory
            type_mapping = {
                "user_action": PredictionCategory.USER_ACTION,
                "external_event": PredictionCategory.EXTERNAL_EVENT,
                "deal_outcome": PredictionCategory.DEAL_OUTCOME,
                "timing": PredictionCategory.TIMING,
                "market_signal": PredictionCategory.EXTERNAL_EVENT,
                "lead_response": PredictionCategory.USER_NEED,
                "meeting_outcome": PredictionCategory.MEETING_OUTCOME,
            }
            prediction_type = type_mapping.get(pred_type_str, PredictionCategory.TIMING)

        # Extract entities from prediction context
        entities: list[str] = []
        context = prediction.get("context")
        if context and isinstance(context, dict):
            entities = context.get("entities", [])

        # Get related goal IDs from context
        goal_ids: list[str] = []
        if context and isinstance(context, dict):
            goal_ids = context.get("related_goal_ids", [])

        return PredictionError(
            prediction_id=prediction["id"],
            prediction_type=prediction_type,
            predicted_value=prediction.get("prediction_text", ""),
            actual_value="Did not occur as predicted",
            surprise_level=surprise_level,
            learning_signal=learning_signal,
            affected_entities=entities,
            related_goal_ids=goal_ids,
            created_at=datetime.now(UTC),
        )

    async def _mark_prediction_status(
        self,
        prediction_id: str,
        status: PredictionStatus,
    ) -> None:
        """Update prediction status.

        Args:
            prediction_id: Prediction ID
            status: New status
        """
        now = datetime.now(UTC).isoformat()

        self._db.table("predictions").update(
            {
                "status": status.value,
                "validated_at": now,
            }
        ).eq("id", prediction_id).execute()

        logger.debug(
            "Prediction status updated",
            extra={"prediction_id": prediction_id, "status": status.value},
        )

    async def _update_calibration(
        self,
        prediction: dict[str, Any],
        is_correct: bool,
    ) -> None:
        """Update calibration statistics.

        Args:
            prediction: Prediction dictionary
            is_correct: Whether prediction was correct
        """
        confidence = prediction.get("confidence", 0.5)
        bucket = round(confidence * 10) / 10
        bucket = max(0.1, min(1.0, bucket))

        self._db.rpc(
            "upsert_calibration",
            {
                "p_user_id": prediction.get("user_id"),
                "p_prediction_type": prediction.get("prediction_type", "timing"),
                "p_confidence_bucket": bucket,
                "p_is_correct": is_correct,
            },
        ).execute()

        logger.debug(
            "Calibration updated",
            extra={
                "prediction_id": prediction.get("id"),
                "is_correct": is_correct,
                "bucket": bucket,
            },
        )

    async def expire_old_predictions(self, user_id: str) -> int:
        """Mark very old predictions as expired.

        Args:
            user_id: User ID

        Returns:
            Number of predictions expired
        """
        # Expire predictions older than 30 days past their expected resolution
        cutoff = datetime.now(UTC)
        cutoff_str = cutoff.isoformat()

        result = (
            self._db.table("predictions")
            .update({"status": PredictionStatus.EXPIRED.value})
            .eq("user_id", user_id)
            .eq("status", "pending")
            .lt("expected_resolution_date", cutoff_str)
            .execute()
        )

        count = len(result.data) if result.data else 0

        if count > 0:
            logger.info(
                "Expired old predictions",
                extra={"user_id": user_id, "count": count},
            )

        return count
