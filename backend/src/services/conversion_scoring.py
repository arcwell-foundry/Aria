"""Conversion scoring service for ARIA.

This service calculates conversion probability for leads using a weighted
logistic regression on nine normalized features extracted from lead memory data.
"""

import logging
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.core.cache import cached
from src.db.supabase import SupabaseClient
from src.models.lead_memory import LeadStatus
from src.services.activity_service import ActivityService

logger = logging.getLogger(__name__)


# Feature weights (sum to 1.0)
FEATURE_WEIGHTS: dict[str, float] = {
    "engagement_frequency": 0.18,
    "stakeholder_depth": 0.12,
    "avg_response_time": 0.10,
    "sentiment_trend": 0.12,
    "stage_velocity": 0.10,
    "health_score_trend": 0.08,
    "meeting_frequency": 0.12,
    "commitment_fulfillment_theirs": 0.12,
    "commitment_fulfillment_ours": 0.06,
}

# Expected days per lifecycle stage for velocity calculation
STAGE_EXPECTED_DAYS: dict[str, int] = {
    "lead": 30,
    "opportunity": 60,
    "account": 90,
}

# Staleness threshold in hours
STALENESS_THRESHOLD_HOURS = 24


def _conversion_score_cache_key(*args: Any, **kwargs: Any) -> str:
    """Generate cache key for conversion scoring.

    Args[0] is self, args[1] is lead_memory_id.
    """
    lead_id = args[1] if len(args) > 1 else kwargs.get("lead_memory_id", "")
    force_refresh = args[2] if len(args) > 2 else kwargs.get("force_refresh", False)

    # Include force_refresh in key so forced refreshes bypass cache
    return f"conversion_score:{lead_id}:{force_refresh}"


class ConversionScore(BaseModel):
    """Conversion score for a lead."""

    lead_memory_id: UUID
    conversion_probability: float = Field(ge=0.0, le=100.0, description="0-100%")
    confidence: float = Field(ge=0.0, le=1.0, description="Data completeness score")
    feature_values: dict[str, float] = Field(default_factory=dict, description="Normalized 0-1")
    feature_importance: dict[str, float] = Field(
        default_factory=dict, description="Weighted contribution to score"
    )
    calculated_at: datetime


class FeatureDriver(BaseModel):
    """A feature that influences the conversion score."""

    name: str
    value: float
    contribution: float
    description: str


class ScoreExplanation(BaseModel):
    """Natural language explanation of a conversion score."""

    lead_memory_id: UUID
    conversion_probability: float
    summary: str
    key_drivers: list[FeatureDriver]
    key_risks: list[FeatureDriver]
    recommendation: str


class BatchScoreResult(BaseModel):
    """Result of batch scoring all leads."""

    scored: int
    errors: list[dict[str, Any]]
    duration_seconds: float


class ScoringError(Exception):
    """Error during scoring calculation."""

    def __init__(self, message: str, lead_id: str | None = None) -> None:
        self.lead_id = lead_id
        super().__init__(message)


class LeadNotFoundError(ScoringError):
    """Lead not found in database."""

    pass


class ConversionScoringService:
    """Service for calculating conversion probability scores for leads."""

    def __init__(self) -> None:
        """Initialize conversion scoring service with Supabase client."""
        self._db = SupabaseClient.get_client()
        self._activity_service = ActivityService()

    @cached(ttl=600, key_func=_conversion_score_cache_key)  # 10 minute TTL
    async def calculate_conversion_score(
        self, lead_memory_id: UUID | str, force_refresh: bool = False
    ) -> ConversionScore:
        """Calculate conversion probability for a lead.

        Args:
            lead_memory_id: The lead's ID.
            force_refresh: If True, bypass staleness check and recalculate.

        Returns:
            ConversionScore with probability, confidence, and feature details.

        Raises:
            LeadNotFoundError: If lead doesn't exist.
            ScoringError: If scoring calculation fails.
        """
        lead_id_str = str(lead_memory_id)

        # Fetch lead
        lead = await self._fetch_lead(lead_id_str)
        if not lead:
            raise LeadNotFoundError(f"Lead not found: {lead_id_str}", lead_id=lead_id_str)

        # Check if lead is won/lost - return cached or None
        if lead.get("status") in [LeadStatus.WON.value, LeadStatus.LOST.value]:
            cached = self._get_cached_score(lead)
            if cached:
                logger.info(
                    "Returning cached score for won/lost lead",
                    extra={"lead_id": lead_id_str, "status": lead.get("status")},
                )
                return cached
            raise ScoringError(
                f"Cannot score lead with status {lead.get('status')}", lead_id=lead_id_str
            )

        # Check staleness
        if not force_refresh:
            cached = self._get_cached_score(lead)
            if cached and not self._is_stale(cached):
                logger.debug(
                    "Returning cached score (not stale)",
                    extra={"lead_id": lead_id_str},
                )
                return cached

        # Calculate all features
        try:
            feature_values = await self._calculate_all_features(lead)
        except Exception as e:
            logger.exception(
                "Error calculating features",
                extra={"lead_id": lead_id_str, "error": str(e)},
            )
            raise ScoringError(f"Feature calculation failed: {e}", lead_id=lead_id_str) from e

        # Calculate weighted score
        raw_score = self._calculate_weighted_score(feature_values)

        # Apply logistic transformation
        conversion_probability = self._logistic_transform(raw_score)

        # Calculate confidence based on data availability
        confidence = self._calculate_confidence(feature_values, lead)

        # Apply new lead penalty
        if self._is_new_lead(lead):
            confidence *= 0.5
            logger.debug(
                "Applied new lead confidence penalty",
                extra={"lead_id": lead_id_str, "adjusted_confidence": confidence},
            )

        # Calculate feature importance (contribution to score)
        feature_importance = {
            name: value * FEATURE_WEIGHTS[name]
            for name, value in feature_values.items()
            if name in FEATURE_WEIGHTS
        }

        score = ConversionScore(
            lead_memory_id=UUID(lead_id_str),
            conversion_probability=round(conversion_probability, 1),
            confidence=round(confidence, 3),
            feature_values=feature_values,
            feature_importance=feature_importance,
            calculated_at=datetime.now(UTC),
        )

        # Cache score in lead metadata
        await self._cache_score(lead_id_str, score)

        # Create prediction record for tracking
        await self._create_prediction_record(lead, score)

        logger.info(
            "Calculated conversion score",
            extra={
                "lead_id": lead_id_str,
                "probability": score.conversion_probability,
                "confidence": score.confidence,
            },
        )

        return score

    async def explain_score(self, lead_memory_id: UUID | str) -> ScoreExplanation:
        """Generate natural language explanation of a lead's conversion score.

        Args:
            lead_memory_id: The lead's ID.

        Returns:
            ScoreExplanation with summary, drivers, risks, and recommendation.
        """
        score = await self.calculate_conversion_score(lead_memory_id)
        lead = await self._fetch_lead(str(lead_memory_id))

        if not lead:
            raise LeadNotFoundError(f"Lead not found: {lead_memory_id}")

        # Identify drivers (high value + positive contribution)
        feature_contributions = [
            (name, score.feature_values.get(name, 0), score.feature_importance.get(name, 0))
            for name in FEATURE_WEIGHTS
        ]

        # Sort by contribution
        sorted_features = sorted(feature_contributions, key=lambda x: x[2], reverse=True)

        key_drivers: list[FeatureDriver] = []
        key_risks: list[FeatureDriver] = []

        for name, value, contribution in sorted_features:
            driver = FeatureDriver(
                name=name,
                value=value,
                contribution=contribution,
                description=self._describe_feature(name, value, lead),
            )

            if value >= 0.5 and contribution > 0 and len(key_drivers) < 3:
                key_drivers.append(driver)
            elif value < 0.5 and contribution > 0.01 and len(key_risks) < 2:
                key_risks.append(driver)

        # Generate summary
        summary = self._generate_summary(score, key_drivers, key_risks, lead)

        # Generate recommendation
        recommendation = self._generate_recommendation(key_risks, lead)

        return ScoreExplanation(
            lead_memory_id=UUID(str(lead_memory_id)),
            conversion_probability=score.conversion_probability,
            summary=summary,
            key_drivers=key_drivers,
            key_risks=key_risks,
            recommendation=recommendation,
        )

    async def batch_score_all_leads(self, user_id: UUID | str) -> BatchScoreResult:
        """Score all active leads for a user.

        Updates lead_memories.metadata['conversion_score'] for each lead
        and creates prediction records for accuracy tracking.

        Args:
            user_id: The user's ID.

        Returns:
            BatchScoreResult with count and any errors.
        """
        start_time = datetime.now(UTC)

        # Fetch all active leads
        result = (
            self._db.table("lead_memories")
            .select("id")
            .eq("user_id", str(user_id))
            .eq("status", LeadStatus.ACTIVE.value)
            .execute()
        )

        leads = result.data or []
        scored = 0
        errors: list[dict[str, Any]] = []

        for lead in leads:
            try:
                await self.calculate_conversion_score(lead["id"], force_refresh=True)
                scored += 1
            except ScoringError as e:
                errors.append({"lead_id": lead["id"], "error": str(e)})
                logger.warning(
                    "Failed to score lead in batch",
                    extra={"lead_id": lead["id"], "error": str(e)},
                )
            except Exception as e:
                errors.append({"lead_id": lead["id"], "error": f"Unexpected error: {e}"})
                logger.exception(
                    "Unexpected error scoring lead",
                    extra={"lead_id": lead["id"]},
                )

        duration = (datetime.now(UTC) - start_time).total_seconds()

        logger.info(
            "Batch scoring completed",
            extra={
                "user_id": str(user_id),
                "scored": scored,
                "errors": len(errors),
                "duration_seconds": duration,
            },
        )

        # Log to activity feed
        try:
            await self._activity_service.record(
                user_id=str(user_id),
                agent="analyst",
                activity_type="score_calculated",
                title=f"Scored {scored} leads",
                description=f"Batch scoring completed: {scored} scored, {len(errors)} errors in {duration:.1f}s",
                confidence=0.9,
                metadata={
                    "scored": scored,
                    "errors": len(errors),
                    "duration_seconds": duration,
                },
            )
        except Exception:
            logger.warning("Failed to log batch scoring activity")

        return BatchScoreResult(scored=scored, errors=errors, duration_seconds=duration)

    # === Feature Calculation Methods ===

    async def _calculate_all_features(self, lead: dict[str, Any]) -> dict[str, float]:
        """Calculate all normalized features for a lead."""
        lead_id = lead["id"]
        now = datetime.now(UTC)

        # Run feature calculations
        engagement = await self._calculate_engagement_frequency(lead_id, now)
        stakeholder = await self._calculate_stakeholder_depth(lead_id)
        response_time = await self._calculate_avg_response_time(lead_id, now)
        sentiment = await self._calculate_sentiment_trend(lead_id, now)
        velocity = self._calculate_stage_velocity(lead)
        health_trend = await self._calculate_health_score_trend(lead_id, now)
        meeting = await self._calculate_meeting_frequency(lead_id, now)
        commit_theirs, commit_ours = await self._calculate_commitment_fulfillment(lead_id)

        return {
            "engagement_frequency": engagement,
            "stakeholder_depth": stakeholder,
            "avg_response_time": response_time,
            "sentiment_trend": sentiment,
            "stage_velocity": velocity,
            "health_score_trend": health_trend,
            "meeting_frequency": meeting,
            "commitment_fulfillment_theirs": commit_theirs,
            "commitment_fulfillment_ours": commit_ours,
        }

    async def _calculate_engagement_frequency(self, lead_id: str, now: datetime) -> float:
        """Calculate normalized engagement frequency (events in last 30 days)."""
        thirty_days_ago = (now - timedelta(days=30)).isoformat()

        result = (
            self._db.table("lead_memory_events")
            .select("id", count="exact")
            .eq("lead_memory_id", lead_id)
            .gte("occurred_at", thirty_days_ago)
            .execute()
        )

        count = result.count or 0
        # Normalize: 20+ interactions = 1.0
        return min(count / 20, 1.0)

    async def _calculate_stakeholder_depth(self, lead_id: str) -> float:
        """Calculate normalized stakeholder depth (weighted by influence)."""
        result = (
            self._db.table("lead_memory_stakeholders")
            .select("role, influence_level")
            .eq("lead_memory_id", lead_id)
            .in_("role", ["decision_maker", "champion", "influencer"])
            .execute()
        )

        stakeholders = result.data or []

        if not stakeholders:
            return 0.0

        # Sum of influence levels
        total_influence = sum(s.get("influence_level", 5) for s in stakeholders)
        max_possible = len(stakeholders) * 10

        return min(total_influence / max_possible, 1.0) if max_possible > 0 else 0.0

    async def _calculate_avg_response_time(self, lead_id: str, now: datetime) -> float:
        """Calculate normalized average response time for email replies."""
        thirty_days_ago = (now - timedelta(days=30)).isoformat()

        # Fetch email events ordered by time
        result = (
            self._db.table("lead_memory_events")
            .select("event_type, direction, occurred_at")
            .eq("lead_memory_id", lead_id)
            .in_("event_type", ["email_sent", "email_received"])
            .gte("occurred_at", thirty_days_ago)
            .order("occurred_at")
            .execute()
        )

        events = result.data or []

        if len(events) < 2:
            # No data - return neutral, but this affects confidence
            return 0.5

        # Calculate response times (inbound after outbound)
        response_times: list[float] = []
        last_outbound: datetime | None = None

        for event in events:
            occurred_at = datetime.fromisoformat(event["occurred_at"].replace("Z", "+00:00"))

            if event["event_type"] == "email_sent" and event.get("direction") == "outbound":
                last_outbound = occurred_at
            elif (
                event["event_type"] == "email_received"
                and event.get("direction") == "inbound"
                and last_outbound
            ):
                delta_hours = (occurred_at - last_outbound).total_seconds() / 3600
                if delta_hours > 0:
                    response_times.append(delta_hours)
                last_outbound = None

        if not response_times:
            return 0.5

        avg_hours = sum(response_times) / len(response_times)
        # Normalize: under 72 hours = positive, instant = 1.0
        return max(0.0, 1.0 - min(avg_hours / 72, 1.0))

    async def _calculate_sentiment_trend(self, lead_id: str, _now: datetime) -> float:
        """Calculate normalized sentiment trend over 30 days.

        Blends stakeholder sentiment with video session perception data when
        available. Video engagement scores are weighted at 30% when present.

        Note: Currently calculates current state only. Historical sentiment
        tracking would require a sentiment_history table for true trend analysis.
        _now parameter reserved for future historical comparison.
        """
        # Current period sentiments
        current_result = (
            self._db.table("lead_memory_stakeholders")
            .select("sentiment")
            .eq("lead_memory_id", lead_id)
            .execute()
        )

        # For trend, we'd need historical sentiment data
        # Since we don't have a sentiment history table, calculate current state
        stakeholders = current_result.data or []

        if not stakeholders:
            stakeholder_score = 0.5
        else:
            positive = sum(1 for s in stakeholders if s.get("sentiment") == "positive")
            negative = sum(1 for s in stakeholders if s.get("sentiment") == "negative")
            total = len(stakeholders)

            # Net sentiment score (-1 to +1), then normalize to 0-1
            net_sentiment = (positive - negative) / total if total > 0 else 0
            stakeholder_score = (net_sentiment + 1) / 2

        # Fetch recent video session engagement for this lead
        video_result = (
            self._db.table("video_sessions")
            .select("perception_analysis")
            .eq("lead_id", lead_id)
            .eq("status", "ended")
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )

        video_sessions = video_result.data or []
        engagement_scores = [
            session["perception_analysis"]["engagement_score"]
            for session in video_sessions
            if isinstance(session.get("perception_analysis"), dict)
            and isinstance(
                session["perception_analysis"].get("engagement_score"), (int, float)
            )
        ]

        if engagement_scores:
            avg_video_engagement = sum(engagement_scores) / len(engagement_scores)
            return stakeholder_score * 0.7 + avg_video_engagement * 0.3

        return stakeholder_score

    def _calculate_stage_velocity(self, lead: dict[str, Any]) -> float:
        """Calculate normalized stage velocity (time in stage vs expected)."""
        lifecycle_stage = lead.get("lifecycle_stage", "lead")
        updated_at_str = lead.get("updated_at")

        if not updated_at_str:
            return 0.5

        try:
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            days_in_stage = (datetime.now(UTC) - updated_at).days
        except (ValueError, TypeError):
            return 0.5

        expected_days = STAGE_EXPECTED_DAYS.get(lifecycle_stage, 30)

        # Normalize: faster movement = higher score
        # If days_in_stage > expected, score drops
        ratio = days_in_stage / expected_days
        return max(0.0, 1.0 - min(ratio, 1.5) / 1.5)

    async def _calculate_health_score_trend(self, lead_id: str, now: datetime) -> float:
        """Calculate normalized health score trend (slope over 30 days)."""
        thirty_days_ago = (now - timedelta(days=30)).isoformat()

        result = (
            self._db.table("health_score_history")
            .select("score, calculated_at")
            .eq("lead_memory_id", lead_id)
            .gte("calculated_at", thirty_days_ago)
            .order("calculated_at")
            .execute()
        )

        history = result.data or []

        if len(history) < 2:
            return 0.5

        # Simple linear regression for slope
        scores = [h["score"] for h in history]
        n = len(scores)

        if n < 2:
            return 0.5

        # Calculate slope: sum((x - x_mean) * (y - y_mean)) / sum((x - x_mean)^2)
        x_mean = (n - 1) / 2
        y_mean = sum(scores) / n

        numerator = sum((i - x_mean) * (scores[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.5

        slope = numerator / denominator

        # Normalize: slope of ~2 points per day = improving fast
        # 0.5 + (slope * 0.05) with slope in points per day
        normalized = 0.5 + (slope * 0.05)
        return max(0.0, min(1.0, normalized))

    async def _calculate_meeting_frequency(self, lead_id: str, now: datetime) -> float:
        """Calculate normalized meeting frequency (debriefs in last 60 days)."""
        sixty_days_ago = (now - timedelta(days=60)).isoformat()

        result = (
            self._db.table("debriefs")
            .select("id", count="exact")
            .eq("lead_memory_id", lead_id)
            .gte("created_at", sixty_days_ago)
            .execute()
        )

        count = result.count or 0
        # Normalize: 4+ meetings = 1.0
        return min(count / 4, 1.0)

    async def _calculate_commitment_fulfillment(self, lead_id: str) -> tuple[float, float]:
        """Calculate commitment fulfillment rates for theirs and ours.

        Returns:
            Tuple of (theirs_fulfillment, ours_fulfillment), both 0-1.
        """
        result = (
            self._db.table("lead_memory_insights")
            .select("metadata, addressed_at")
            .eq("lead_memory_id", lead_id)
            .eq("insight_type", "commitment")
            .execute()
        )

        insights = result.data or []

        theirs_total = 0
        theirs_fulfilled = 0
        ours_total = 0
        ours_fulfilled = 0

        for insight in insights:
            metadata = insight.get("metadata") or {}
            direction = metadata.get("direction", "theirs")
            addressed = insight.get("addressed_at") is not None

            if direction == "theirs":
                theirs_total += 1
                if addressed:
                    theirs_fulfilled += 1
            else:
                ours_total += 1
                if addressed:
                    ours_fulfilled += 1

        # Default to 0.5 (neutral) if no commitments
        theirs_rate = theirs_fulfilled / theirs_total if theirs_total > 0 else 0.5
        ours_rate = ours_fulfilled / ours_total if ours_total > 0 else 0.5

        return theirs_rate, ours_rate

    # === Helper Methods ===

    def _calculate_weighted_score(self, feature_values: dict[str, float]) -> float:
        """Calculate raw weighted score from normalized features."""
        return sum(
            feature_values.get(name, 0.5) * weight for name, weight in FEATURE_WEIGHTS.items()
        )

    def _logistic_transform(self, raw_score: float) -> float:
        """Apply logistic transformation to get probability."""
        # Centered at 0.5, steepness factor of 10
        return 100 / (1 + math.exp(-10 * (raw_score - 0.5)))

    def _calculate_confidence(
        self, feature_values: dict[str, float], _lead: dict[str, Any]
    ) -> float:
        """Calculate confidence based on data availability.

        Note: _lead parameter is reserved for future use (e.g., confidence
        adjustments based on lead age, industry, etc.).
        """
        confidence = 0.0

        # Check each feature for meaningful data
        # Engagement has data if > 0
        if feature_values.get("engagement_frequency", 0) > 0:
            confidence += FEATURE_WEIGHTS["engagement_frequency"]
        else:
            confidence += FEATURE_WEIGHTS["engagement_frequency"] * 0.3

        # Stakeholders exist
        if feature_values.get("stakeholder_depth", 0) > 0:
            confidence += FEATURE_WEIGHTS["stakeholder_depth"]
        else:
            confidence += FEATURE_WEIGHTS["stakeholder_depth"] * 0.3

        # Response time has data
        if feature_values.get("avg_response_time", 0.5) != 0.5:
            confidence += FEATURE_WEIGHTS["avg_response_time"]
        else:
            confidence += FEATURE_WEIGHTS["avg_response_time"] * 0.5

        # Other features contribute to confidence with their weight if not at default
        for feature in [
            "sentiment_trend",
            "stage_velocity",
            "health_score_trend",
            "meeting_frequency",
        ]:
            if feature_values.get(feature, 0.5) != 0.5:
                confidence += FEATURE_WEIGHTS[feature]
            else:
                confidence += FEATURE_WEIGHTS[feature] * 0.5

        # Commitments
        if feature_values.get("commitment_fulfillment_theirs", 0.5) != 0.5:
            confidence += FEATURE_WEIGHTS["commitment_fulfillment_theirs"]
        else:
            confidence += FEATURE_WEIGHTS["commitment_fulfillment_theirs"] * 0.5

        if feature_values.get("commitment_fulfillment_ours", 0.5) != 0.5:
            confidence += FEATURE_WEIGHTS["commitment_fulfillment_ours"]
        else:
            confidence += FEATURE_WEIGHTS["commitment_fulfillment_ours"] * 0.5

        return min(confidence, 1.0)

    def _is_new_lead(self, lead: dict[str, Any]) -> bool:
        """Check if lead is less than 7 days old."""
        created_at_str = lead.get("created_at")
        if not created_at_str:
            return False

        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            age_days = (datetime.now(UTC) - created_at).days
            return age_days < 7
        except (ValueError, TypeError):
            return False

    async def _fetch_lead(self, lead_id: str) -> dict[str, Any] | None:
        """Fetch a lead by ID."""
        result = self._db.table("lead_memories").select("*").eq("id", lead_id).single().execute()

        return result.data

    def _get_cached_score(self, lead: dict[str, Any]) -> ConversionScore | None:
        """Get cached score from lead metadata if available."""
        metadata = lead.get("metadata") or {}
        cached = metadata.get("conversion_score")

        if not cached:
            return None

        try:
            return ConversionScore(**cached)
        except Exception:
            return None

    def _is_stale(self, score: ConversionScore) -> bool:
        """Check if cached score is stale (> 24 hours old)."""
        age = datetime.now(UTC) - score.calculated_at
        return age.total_seconds() > STALENESS_THRESHOLD_HOURS * 3600

    async def _cache_score(self, lead_id: str, score: ConversionScore) -> None:
        """Cache score in lead metadata."""
        # First get current metadata
        lead = await self._fetch_lead(lead_id)
        metadata = lead.get("metadata") or {} if lead else {}

        # Update with new score
        metadata["conversion_score"] = score.model_dump()

        # Ensure calculated_at is serialized properly
        metadata["conversion_score"]["calculated_at"] = score.calculated_at.isoformat()

        self._db.table("lead_memories").update({"metadata": metadata}).eq("id", lead_id).execute()

    async def _create_prediction_record(self, lead: dict[str, Any], score: ConversionScore) -> None:
        """Create prediction record for accuracy tracking."""
        try:
            self._db.table("predictions").insert(
                {
                    "user_id": lead.get("user_id"),
                    "prediction_type": "deal_outcome",
                    "prediction_text": f"{lead.get('company_name', 'Lead')} will convert",
                    "predicted_outcome": "won",
                    "confidence": score.confidence,
                    "context": {
                        "lead_memory_id": str(score.lead_memory_id),
                        "conversion_probability": score.conversion_probability,
                        "feature_values": score.feature_values,
                    },
                    "expected_resolution_date": (datetime.now(UTC) + timedelta(days=90))
                    .date()
                    .isoformat(),
                    "status": "pending",
                }
            ).execute()
        except Exception as e:
            # Don't fail scoring if prediction creation fails
            logger.warning(
                "Failed to create prediction record",
                extra={"lead_id": str(score.lead_memory_id), "error": str(e)},
            )

    def _describe_feature(self, name: str, value: float, _lead: dict[str, Any]) -> str:
        """Generate human-readable description of a feature value.

        Note: _lead parameter is reserved for future use (e.g., contextual
        descriptions based on company name, lifecycle stage, etc.).
        """
        descriptions = {
            "engagement_frequency": f"{int(value * 20)} interactions this month"
            if value > 0
            else "no recent engagement",
            "stakeholder_depth": "strong stakeholder coverage"
            if value > 0.6
            else "limited stakeholder mapping",
            "avg_response_time": "fast responses" if value > 0.7 else "slow response times",
            "sentiment_trend": "positive sentiment trend"
            if value > 0.6
            else "concerning sentiment",
            "stage_velocity": "progressing well" if value > 0.5 else "stalled in current stage",
            "health_score_trend": "health improving" if value > 0.6 else "health declining",
            "meeting_frequency": f"{int(value * 4)} recent meetings"
            if value > 0
            else "no recent meetings",
            "commitment_fulfillment_theirs": f"{int(value * 100)}% commitment rate"
            if value != 0.5
            else "no commitment data",
            "commitment_fulfillment_ours": "we're delivering on commitments"
            if value > 0.7
            else "we may be dropping commitments",
        }
        return descriptions.get(name, f"{name}: {value:.2f}")

    def _generate_summary(
        self,
        score: ConversionScore,
        drivers: list[FeatureDriver],
        risks: list[FeatureDriver],
        lead: dict[str, Any],
    ) -> str:
        """Generate natural language summary of the score."""
        company = lead.get("company_name", "This lead")

        summary = f"{company} has a {score.conversion_probability:.0f}% conversion probability"

        if drivers:
            driver_text = ", ".join(d.description for d in drivers[:2])
            summary += f". Key strengths: {driver_text}"

        if risks:
            risk_text = risks[0].description
            summary += f". Concern: {risk_text}"

        return summary + "."

    def _generate_recommendation(self, risks: list[FeatureDriver], lead: dict[str, Any]) -> str:
        """Generate actionable recommendation based on risks."""
        if not risks:
            lifecycle = lead.get("lifecycle_stage", "lead")
            if lifecycle == "lead":
                return "Continue nurturing and consider advancing to opportunity."
            elif lifecycle == "opportunity":
                return "Focus on closing activities and stakeholder alignment."
            return "Maintain engagement and monitor for expansion opportunities."

        # Generate recommendation based on top risk
        top_risk = risks[0]

        recommendations = {
            "engagement_frequency": "Schedule a check-in or send relevant content to re-engage.",
            "stakeholder_depth": "Map additional stakeholders and expand relationships.",
            "avg_response_time": "Consider alternative contact methods or timing.",
            "sentiment_trend": "Address concerns directly in your next conversation.",
            "stage_velocity": "Identify blockers and create urgency with value messaging.",
            "health_score_trend": "Investigate the root cause of declining engagement.",
            "meeting_frequency": "Propose a meeting to advance the relationship.",
            "commitment_fulfillment_theirs": "Follow up on outstanding commitments gently.",
            "commitment_fulfillment_ours": "Prioritize delivering on our commitments.",
        }

        return recommendations.get(top_risk.name, "Review and address identified concerns.")
