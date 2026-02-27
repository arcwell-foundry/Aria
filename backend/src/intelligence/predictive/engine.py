"""Predictive Processing Engine for ARIA (US-707).

This engine implements predictive processing cognitive theory where:
- ARIA constantly predicts what will happen next
- Prediction errors (surprises) drive attention and learning
- Calibration improves prediction confidence over time

Key features:
- Generate predictions from context using LLM
- Detect prediction errors by comparing to actual events
- Boost salience for entities involved in surprising outcomes
- Track calibration statistics
"""

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import get_supabase_client
from src.intelligence.predictive.context_gatherer import PredictionContextGatherer
from src.intelligence.predictive.error_detector import PredictionErrorDetector
from src.intelligence.predictive.models import (
    ActivePredictionsResponse,
    CalibrationData,
    CalibrationResponse,
    GeneratePredictionsResponse,
    Prediction,
    PredictionCategory,
    PredictionContext,
    PredictionError,
    PredictionErrorDetectionResponse,
    PredictionStatus,
)
from src.models.prediction import PredictionCreate, PredictionType
from src.services.prediction_service import PredictionService

logger = logging.getLogger(__name__)


class PredictiveEngine:
    """Main engine for predictive processing.

    Generates predictions, detects errors, and manages learning signals
    following predictive processing cognitive theory.

    Attributes:
        DEFAULT_MAX_PREDICTIONS: Default max predictions to generate
        CONTEXT_CONVERSATION_LIMIT: Conversations to use for context
        CONTEXT_MEETING_HORIZON_HOURS: Hours ahead for meetings
        CONTEXT_SIGNAL_DAYS: Days back for signals
        PREDICTION_EXPIRY_HOURS: Hours until prediction expires
    """

    DEFAULT_MAX_PREDICTIONS: int = 5
    CONTEXT_CONVERSATION_LIMIT: int = 3
    CONTEXT_MEETING_HORIZON_HOURS: int = 48
    CONTEXT_SIGNAL_DAYS: int = 7
    PREDICTION_EXPIRY_HOURS: int = 48

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        prediction_service: PredictionService | None = None,
        db_client: Any | None = None,
    ) -> None:
        """Initialize the predictive engine.

        Args:
            llm_client: LLM client for prediction generation
            prediction_service: Service for prediction persistence
            db_client: Supabase client for database operations
        """
        self._llm = llm_client or LLMClient()
        self._db = db_client or get_supabase_client()
        self._prediction_service = prediction_service or PredictionService()
        self._context_gatherer = PredictionContextGatherer(db_client=self._db, llm_client=self._llm)
        self._error_detector = PredictionErrorDetector(db_client=self._db, llm_client=self._llm)

    async def generate_predictions(
        self,
        user_id: str,
        context: PredictionContext | None = None,
        prediction_types: list[PredictionCategory] | None = None,
        max_predictions: int = DEFAULT_MAX_PREDICTIONS,
    ) -> list[Prediction]:
        """Generate predictions for a user.

        Gathers context if not provided, uses LLM to generate predictions,
        saves them to the database, and returns the predictions.

        Args:
            user_id: User ID to generate predictions for
            context: Optional pre-gathered context
            prediction_types: Types of predictions to generate (all if None)
            max_predictions: Maximum number of predictions to generate

        Returns:
            List of generated Prediction objects
        """
        start_time = time.monotonic()

        logger.info(
            "Generating predictions",
            extra={
                "user_id": user_id,
                "max_predictions": max_predictions,
                "types_filter": prediction_types,
            },
        )

        # 1. Gather context if not provided
        if context is None:
            context = await self._context_gatherer.gather(user_id)

        # 2. Use LLM to generate predictions
        raw_predictions = await self._llm_generate_predictions(
            context=context,
            prediction_types=prediction_types,
            max_predictions=max_predictions,
        )

        # 3. Save to predictions table and convert to Prediction objects
        predictions: list[Prediction] = []

        for pred_data in raw_predictions:
            try:
                # Map PredictionCategory to PredictionType for storage
                pred_type_arg = pred_data.get("prediction_type")
                if pred_type_arg is None:
                    pred_type_arg = PredictionCategory.TIMING
                pred_type = self._map_category_to_type(pred_type_arg)

                # Create prediction record
                create_data = PredictionCreate(
                    prediction_type=pred_type,
                    prediction_text=pred_data["prediction_text"],
                    predicted_outcome=pred_data.get("predicted_outcome"),
                    confidence=pred_data.get("confidence", 0.5),
                    context=pred_data.get("context"),
                    source_conversation_id=pred_data.get("source_conversation_id"),
                    source_message_id=None,
                    validation_criteria=pred_data.get("validation_criteria"),
                    expected_resolution_date=(
                        datetime.now(UTC) + timedelta(days=pred_data.get("timeframe_days", 7))
                    ).date(),
                )

                # Save via prediction service
                saved = await self._prediction_service.register(user_id, create_data)

                # Parse dates safely
                expected_res_date: datetime | None = None
                expected_res_str = saved.get("expected_resolution_date")
                if expected_res_str and isinstance(expected_res_str, str):
                    expected_res_date = datetime.fromisoformat(expected_res_str)

                created_date: datetime | None = None
                created_str = saved.get("created_at")
                if created_str and isinstance(created_str, str):
                    created_date = datetime.fromisoformat(created_str)

                # Convert to Prediction model
                prediction = Prediction(
                    id=saved.get("id"),
                    user_id=user_id,
                    prediction_type=pred_data.get("prediction_type", PredictionCategory.TIMING),
                    prediction_text=pred_data["prediction_text"],
                    predicted_outcome=pred_data.get("predicted_outcome"),
                    confidence=pred_data.get("confidence", 0.5),
                    context=pred_data.get("context"),
                    source_conversation_id=pred_data.get("source_conversation_id"),
                    expected_resolution_date=expected_res_date,
                    status=PredictionStatus.ACTIVE,
                    surprise_level=None,
                    learning_signal=None,
                    created_at=created_date,
                    validated_at=None,
                )
                predictions.append(prediction)

            except Exception as e:
                logger.warning(
                    "Failed to save prediction",
                    extra={"user_id": user_id, "error": str(e), "pred": pred_data},
                )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        logger.info(
            "Predictions generated",
            extra={
                "user_id": user_id,
                "predictions_generated": len(predictions),
                "elapsed_ms": elapsed_ms,
            },
        )

        return predictions

    async def _llm_generate_predictions(
        self,
        context: PredictionContext,
        prediction_types: list[PredictionCategory] | None,
        max_predictions: int,
    ) -> list[dict[str, Any]]:
        """Use LLM to generate predictions from context.

        Args:
            context: Gathered context
            prediction_types: Types to generate (all if None)
            max_predictions: Max predictions to generate

        Returns:
            List of prediction dictionaries
        """
        # Build context summary
        context_parts: list[str] = []

        if context.recent_conversations:
            conv_summaries = [c.summary[:200] for c in context.recent_conversations[:3]]
            context_parts.append(f"Recent conversations: {'; '.join(conv_summaries)}")

        if context.active_goals:
            goal_titles = [g.get("title", "")[:100] for g in context.active_goals[:5]]
            context_parts.append(f"Active goals: {'; '.join(goal_titles)}")

        if context.upcoming_meetings:
            meetings = [
                f"{m.title} ({m.start_time.strftime('%Y-%m-%d')})"
                for m in context.upcoming_meetings[:3]
            ]
            context_parts.append(f"Upcoming meetings: {'; '.join(meetings)}")

        if context.recent_market_signals:
            signals = [s.content[:100] for s in context.recent_market_signals[:3]]
            context_parts.append(f"Recent signals: {'; '.join(signals)}")

        if context.recent_lead_activity:
            activities = [
                f"{a.lead_name}: {a.activity_description[:50]}"
                for a in context.recent_lead_activity[:3]
            ]
            context_parts.append(f"Recent lead activity: {'; '.join(activities)}")

        context_str = "\n".join(context_parts) if context_parts else "No recent context."

        # Build types list
        types_str = (
            ", ".join(t.value for t in prediction_types) if prediction_types else "all types"
        )

        prompt = f"""Based on the user's context, generate predictions about what will happen next.

User Context:
{context_str}

Prediction types to consider: {types_str}

Generate {max_predictions} predictions following predictive processing theory:
1. Predict what the user will need or do next
2. Predict external events that may affect their goals
3. Predict outcomes of ongoing deals/meetings
4. Predict topic shifts in future conversations

For each prediction, provide:
- prediction_type: user_action, user_need, external_event, topic_shift, deal_outcome, meeting_outcome, or timing
- prediction_text: The specific prediction statement
- predicted_outcome: What we expect to happen
- confidence: 0.0-1.0 confidence level
- timeframe_days: Days until we can validate this prediction
- context: Brief context object with relevant entities
- validation_criteria: How to validate this prediction

Return ONLY a JSON array of predictions, max {max_predictions} items:
[
  {{
    "prediction_type": "deal_outcome",
    "prediction_text": "The Lonza deal will move to negotiation phase",
    "predicted_outcome": "Lonza signs term sheet within 2 weeks",
    "confidence": 0.75,
    "timeframe_days": 14,
    "context": {{"entities": ["Lonza"], "deal_stage": "proposal"}},
    "validation_criteria": "Check if deal status changes to negotiation"
  }}
]"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=1500,
                task=TaskType.ANALYST_RESEARCH,
                agent_id="predictive",
            )

            # Parse JSON response
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

            predictions = json.loads(response)

            if not isinstance(predictions, list):
                logger.warning("LLM returned non-list predictions")
                return []

            return predictions[:max_predictions]

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM predictions: {e}")
            return []
        except Exception as e:
            logger.exception(f"LLM prediction generation failed: {e}")
            return []

    def _map_category_to_type(self, category: str | PredictionCategory) -> PredictionType:
        """Map PredictionCategory to PredictionType for storage.

        Args:
            category: PredictionCategory value

        Returns:
            Corresponding PredictionType
        """
        category_str = category.value if isinstance(category, PredictionCategory) else category

        mapping = {
            "user_action": PredictionType.USER_ACTION,
            "user_need": PredictionType.USER_ACTION,
            "external_event": PredictionType.EXTERNAL_EVENT,
            "topic_shift": PredictionType.TIMING,
            "deal_outcome": PredictionType.DEAL_OUTCOME,
            "meeting_outcome": PredictionType.MEETING_OUTCOME,
            "timing": PredictionType.TIMING,
        }

        return mapping.get(category_str, PredictionType.TIMING)

    async def detect_prediction_errors(self, user_id: str) -> list[PredictionError]:
        """Detect prediction errors for a user.

        Delegates to the error detector.

        Args:
            user_id: User ID

        Returns:
            List of detected PredictionError objects
        """
        return await self._error_detector.detect_errors(user_id)

    async def get_calibration(
        self,
        user_id: str,
        prediction_type: PredictionCategory | None = None,
    ) -> list[CalibrationData]:
        """Get calibration statistics for predictions.

        Args:
            user_id: User ID
            prediction_type: Optional filter by type

        Returns:
            List of CalibrationData objects
        """
        # Map PredictionCategory to PredictionType if needed
        pred_type: PredictionType | None = None
        if prediction_type:
            pred_type = self._map_category_to_type(prediction_type)

        # Use existing PredictionService for calibration stats
        stats = await self._prediction_service.get_calibration_stats(
            user_id=user_id,
            prediction_type=pred_type,
        )

        calibration_data: list[CalibrationData] = []
        for stat in stats:
            try:
                cal = CalibrationData(
                    prediction_type=prediction_type or PredictionCategory.TIMING,
                    confidence_bucket=stat.get("confidence_bucket", 0.5),
                    total_predictions=stat.get("total_predictions", 0),
                    correct_predictions=stat.get("correct_predictions", 0),
                    accuracy=stat.get("accuracy", 0.0),
                    is_calibrated=stat.get("is_calibrated", False),
                )
                calibration_data.append(cal)
            except Exception as e:
                logger.warning(f"Failed to create CalibrationData: {e}")

        return calibration_data

    async def get_active_predictions(
        self, user_id: str, limit: int = 20
    ) -> ActivePredictionsResponse:
        """Get active predictions for a user.

        Args:
            user_id: User ID
            limit: Maximum predictions to return

        Returns:
            ActivePredictionsResponse with predictions and metadata
        """
        start_time = time.monotonic()

        result = (
            self._db.table("predictions")
            .select("*")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .order("expected_resolution_date")
            .limit(limit)
            .execute()
        )

        predictions: list[Prediction] = []
        by_type: dict[str, int] = {}

        for row in result.data or []:
            try:
                if not isinstance(row, dict):
                    continue
                row_dict: dict[str, Any] = row
                pred_type_str = row_dict.get("prediction_type", "timing")
                if not isinstance(pred_type_str, str):
                    pred_type_str = "timing"
                try:
                    pred_type = PredictionCategory(pred_type_str)
                except ValueError:
                    pred_type = PredictionCategory.TIMING

                # Parse expected_resolution_date safely
                expected_res: datetime | None = None
                exp_res_raw = row_dict.get("expected_resolution_date")
                if exp_res_raw and isinstance(exp_res_raw, str):
                    expected_res = datetime.fromisoformat(exp_res_raw)

                # Parse created_at safely
                created_at_val: datetime | None = None
                created_raw = row_dict.get("created_at")
                if created_raw and isinstance(created_raw, str):
                    created_at_val = datetime.fromisoformat(created_raw)

                prediction = Prediction(
                    id=row_dict.get("id"),
                    user_id=user_id,
                    prediction_type=pred_type,
                    prediction_text=row_dict.get("prediction_text", ""),
                    predicted_outcome=row_dict.get("predicted_outcome"),
                    confidence=row_dict.get("confidence", 0.5),
                    context=row_dict.get("context"),
                    source_conversation_id=row_dict.get("source_conversation_id"),
                    expected_resolution_date=expected_res,
                    status=PredictionStatus.ACTIVE,
                    surprise_level=None,
                    learning_signal=None,
                    created_at=created_at_val,
                    validated_at=None,
                )
                predictions.append(prediction)

                # Count by type
                by_type[pred_type_str] = by_type.get(pred_type_str, 0) + 1

            except Exception as e:
                logger.warning(f"Failed to parse prediction: {e}")

        elapsed_ms = (time.monotonic() - start_time) * 1000

        return ActivePredictionsResponse(
            predictions=predictions,
            total_count=len(predictions),
            by_type=by_type,
            processing_time_ms=elapsed_ms,
        )

    async def boost_salience_for_surprise(
        self,
        user_id: str,
        error: PredictionError,
    ) -> list[dict[str, Any]]:
        """Boost salience for entities involved in a prediction error.

        High surprise = high salience boost to direct attention.

        Args:
            user_id: User ID
            error: Prediction error with entities to boost

        Returns:
            List of updated salience records
        """
        if not error.affected_entities:
            return []

        # Only boost for high surprise
        if error.surprise_level < 0.3:
            return []

        updated: list[dict[str, Any]] = []

        for entity in error.affected_entities:
            try:
                # Check if memory_salience table exists
                # Update or insert salience record
                salience_boost = error.surprise_level  # 0-1 based on surprise

                # Try to update existing record
                existing = (
                    self._db.table("memory_salience")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("entity_name", entity)
                    .execute()
                )

                if existing.data:
                    # Update existing
                    first_row = existing.data[0]
                    if not isinstance(first_row, dict):
                        continue
                    current_salience = first_row.get("salience_score", 0.5)
                    if not isinstance(current_salience, (int, float)):
                        current_salience = 0.5
                    new_salience = min(1.0, float(current_salience) + salience_boost * 0.3)
                    row_id = first_row.get("id")

                    result = (
                        self._db.table("memory_salience")
                        .update(
                            {
                                "salience_score": new_salience,
                                "last_boosted": datetime.now(UTC).isoformat(),
                                "boost_reason": f"prediction_error:{error.prediction_type.value}",
                            }
                        )
                        .eq("id", row_id)
                        .execute()
                    )

                    if result.data and isinstance(result.data[0], dict):
                        updated.append(result.data[0])
                else:
                    # Insert new
                    result = (
                        self._db.table("memory_salience")
                        .insert(
                            {
                                "user_id": user_id,
                                "entity_name": entity,
                                "salience_score": 0.5 + salience_boost * 0.3,
                                "last_boosted": datetime.now(UTC).isoformat(),
                                "boost_reason": f"prediction_error:{error.prediction_type.value}",
                            }
                        )
                        .execute()
                    )

                    if result.data and isinstance(result.data[0], dict):
                        updated.append(result.data[0])

            except Exception as e:
                logger.warning(
                    "Failed to boost salience",
                    extra={
                        "user_id": user_id,
                        "entity": entity,
                        "error": str(e),
                    },
                )

        logger.info(
            "Salience boosted for surprise",
            extra={
                "user_id": user_id,
                "entities_boosted": len(updated),
                "surprise_level": error.surprise_level,
            },
        )

        return updated

    async def generate_predictions_with_metadata(
        self,
        user_id: str,
        context: PredictionContext | None = None,
        prediction_types: list[PredictionCategory] | None = None,
        max_predictions: int = DEFAULT_MAX_PREDICTIONS,
    ) -> GeneratePredictionsResponse:
        """Generate predictions with full response metadata.

        Args:
            user_id: User ID
            context: Optional pre-gathered context
            prediction_types: Types to generate
            max_predictions: Max predictions

        Returns:
            GeneratePredictionsResponse with predictions and metadata
        """
        start_time = time.monotonic()

        # Gather context if not provided
        if context is None:
            context = await self._context_gatherer.gather(user_id)

        predictions = await self.generate_predictions(
            user_id=user_id,
            context=context,
            prediction_types=prediction_types,
            max_predictions=max_predictions,
        )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        return GeneratePredictionsResponse(
            predictions=predictions,
            context_used=context,
            processing_time_ms=elapsed_ms,
        )

    async def detect_errors_with_metadata(
        self,
        user_id: str,
        boost_salience: bool = True,
    ) -> PredictionErrorDetectionResponse:
        """Detect prediction errors with full response metadata.

        Args:
            user_id: User ID
            boost_salience: Whether to boost salience for surprising errors

        Returns:
            PredictionErrorDetectionResponse with errors and metadata
        """
        start_time = time.monotonic()

        # Detect errors
        errors = await self._error_detector.detect_errors(user_id)

        # Expire old predictions
        expired_count = await self._error_detector.expire_old_predictions(user_id)

        # Boost salience for high-surprise errors
        salience_boosted: list[dict[str, Any]] = []
        if boost_salience:
            for error in errors:
                if error.surprise_level >= 0.5:
                    boosted = await self.boost_salience_for_surprise(user_id, error)
                    salience_boosted.extend(boosted)

        # Count validated predictions
        validated_count = len(errors) + sum(1 for e in errors if e.learning_signal < 0.5)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        return PredictionErrorDetectionResponse(
            errors_detected=errors,
            predictions_validated=validated_count,
            predictions_expired=expired_count,
            salience_boosted_entities=salience_boosted,
            processing_time_ms=elapsed_ms,
        )

    async def get_calibration_response(
        self,
        user_id: str,
        prediction_type: PredictionCategory | None = None,
    ) -> CalibrationResponse:
        """Get calibration statistics with response metadata.

        Args:
            user_id: User ID
            prediction_type: Optional type filter

        Returns:
            CalibrationResponse with calibration data
        """
        start_time = time.monotonic()

        calibration_data = await self.get_calibration(user_id, prediction_type)

        # Calculate overall accuracy
        total = sum(c.total_predictions for c in calibration_data)
        correct = sum(c.correct_predictions for c in calibration_data)
        overall_accuracy = correct / total if total > 0 else None

        # Check if well calibrated (within 10% on average)
        is_well_calibrated = (
            all(c.is_calibrated for c in calibration_data) if calibration_data else True
        )

        elapsed_ms = (time.monotonic() - start_time) * 1000

        return CalibrationResponse(
            calibration_data=calibration_data,
            overall_accuracy=overall_accuracy,
            total_predictions=total,
            is_well_calibrated=is_well_calibrated,
            processing_time_ms=elapsed_ms,
        )
