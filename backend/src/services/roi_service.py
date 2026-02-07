"""ROI Analytics Service (US-943).

Calculates and aggregates Return on Investment metrics for ARIA,
including time saved, intelligence delivered, actions taken, and
pipeline impact.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, cast

from src.core.exceptions import ARIAException, DatabaseError
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Time saved constants (minutes per action)
TIME_SAVED_MINUTES = {
    "email_draft": 15,
    "meeting_prep": 30,
    "research_report": 60,
    "crm_update": 5,
}


class ROIService:
    """Service for calculating ROI metrics from ARIA activity."""

    def __init__(self) -> None:
        """Initialize ROIService."""
        self._client: Any = None

    @property
    def db(self) -> Any:
        """Get Supabase client lazily.

        Returns:
            Supabase client instance.
        """
        if self._client is None:
            self._client = SupabaseClient.get_client()
        return self._client

    def _get_period_start(self, period: str) -> datetime:
        """Get the start datetime for a given period.

        Args:
            period: Time period identifier (7d, 30d, 90d, all).

        Returns:
            Datetime representing the start of the period.

        Raises:
            ValueError: If period is not recognized.
        """
        now = datetime.utcnow()
        if period == "7d":
            return now - timedelta(days=7)
        elif period == "30d":
            return now - timedelta(days=30)
        elif period == "90d":
            return now - timedelta(days=90)
        elif period == "all":
            # Return a very old date to get all records
            return datetime(2020, 1, 1)
        else:
            raise ValueError(f"Invalid period: {period}. Must be one of: 7d, 30d, 90d, all")

    async def get_time_saved_metrics(
        self,
        user_id: str,
        period_start: datetime,
    ) -> dict[str, Any]:
        """Calculate time saved metrics from aria_actions table.

        Args:
            user_id: The user's UUID.
            period_start: Start datetime for the calculation period.

        Returns:
            Dict with total hours saved and breakdown by activity.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            response = (
                self.db.table("aria_actions")
                .select("action_type", "estimated_minutes_saved")
                .eq("user_id", user_id)
                .gte("created_at", period_start.isoformat())
                .execute()
            )

            actions = response.data or []

            # Calculate totals
            total_minutes = 0
            breakdown: dict[str, dict[str, int | float]] = {
                "email_drafts": {"count": 0, "estimated_hours": 0.0},
                "meeting_prep": {"count": 0, "estimated_hours": 0.0},
                "research_reports": {"count": 0, "estimated_hours": 0.0},
                "crm_updates": {"count": 0, "estimated_hours": 0.0},
            }

            for action in actions:
                action_type = action.get("action_type")
                minutes_saved = action.get("estimated_minutes_saved", 0)

                # Map action_type to breakdown key
                if action_type == "email_draft":
                    key = "email_drafts"
                    minutes = TIME_SAVED_MINUTES.get("email_draft", minutes_saved)
                elif action_type == "meeting_prep":
                    key = "meeting_prep"
                    minutes = TIME_SAVED_MINUTES.get("meeting_prep", minutes_saved)
                elif action_type == "research_report":
                    key = "research_reports"
                    minutes = TIME_SAVED_MINUTES.get("research_report", minutes_saved)
                elif action_type == "crm_update":
                    key = "crm_updates"
                    minutes = TIME_SAVED_MINUTES.get("crm_update", minutes_saved)
                else:
                    # Skip other action types for time saved calculation
                    continue

                breakdown[key]["count"] = cast(int, breakdown[key]["count"]) + 1
                breakdown[key]["estimated_hours"] = (
                    cast(float, breakdown[key]["estimated_hours"]) + (minutes / 60)
                )
                total_minutes += minutes

            total_hours = total_minutes / 60

            return {
                "hours": round(total_hours, 2),
                "breakdown": {
                    "email_drafts": {
                        "count": breakdown["email_drafts"]["count"],
                        "estimated_hours": round(
                            cast(float, breakdown["email_drafts"]["estimated_hours"]), 2
                        ),
                    },
                    "meeting_prep": {
                        "count": breakdown["meeting_prep"]["count"],
                        "estimated_hours": round(
                            cast(float, breakdown["meeting_prep"]["estimated_hours"]), 2
                        ),
                    },
                    "research_reports": {
                        "count": breakdown["research_reports"]["count"],
                        "estimated_hours": round(
                            cast(float, breakdown["research_reports"]["estimated_hours"]), 2
                        ),
                    },
                    "crm_updates": {
                        "count": breakdown["crm_updates"]["count"],
                        "estimated_hours": round(
                            cast(float, breakdown["crm_updates"]["estimated_hours"]), 2
                        ),
                    },
                },
            }

        except Exception as e:
            logger.exception("Error calculating time saved metrics", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to calculate time saved metrics: {e}") from e

    async def get_intelligence_metrics(
        self,
        user_id: str,
        period_start: datetime,
    ) -> dict[str, Any]:
        """Calculate intelligence delivered metrics from intelligence_delivered table.

        Args:
            user_id: The user's UUID.
            period_start: Start datetime for the calculation period.

        Returns:
            Dict with counts by intelligence type.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            response = (
                self.db.table("intelligence_delivered")
                .select("intelligence_type")
                .eq("user_id", user_id)
                .gte("delivered_at", period_start.isoformat())
                .execute()
            )

            intelligence_records = response.data or []

            # Count by type
            metrics = {
                "facts_discovered": 0,
                "signals_detected": 0,
                "gaps_filled": 0,
                "briefings_generated": 0,
            }

            for record in intelligence_records:
                intel_type = record.get("intelligence_type")
                if intel_type == "fact":
                    metrics["facts_discovered"] += 1
                elif intel_type == "signal":
                    metrics["signals_detected"] += 1
                elif intel_type == "gap_filled":
                    metrics["gaps_filled"] += 1
                elif intel_type == "briefing":
                    metrics["briefings_generated"] += 1
                # proactive_insight is not tracked in the current model

            return metrics

        except Exception as e:
            logger.exception(
                "Error calculating intelligence metrics",
                extra={"user_id": user_id},
            )
            raise DatabaseError(f"Failed to calculate intelligence metrics: {e}") from e

    async def get_actions_metrics(
        self,
        user_id: str,
        period_start: datetime,
    ) -> dict[str, Any]:
        """Calculate actions taken metrics from aria_actions table.

        Args:
            user_id: The user's UUID.
            period_start: Start datetime for the calculation period.

        Returns:
            Dict with counts by status.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            response = (
                self.db.table("aria_actions")
                .select("status")
                .eq("user_id", user_id)
                .gte("created_at", period_start.isoformat())
                .execute()
            )

            actions = response.data or []

            # Count by status
            metrics = {
                "total": len(actions),
                "auto_approved": 0,
                "user_approved": 0,
                "rejected": 0,
            }

            for action in actions:
                status = action.get("status")
                if status == "auto_approved":
                    metrics["auto_approved"] += 1
                elif status == "user_approved":
                    metrics["user_approved"] += 1
                elif status == "rejected":
                    metrics["rejected"] += 1
                # pending actions are counted in total but not in approval categories

            return metrics

        except Exception as e:
            logger.exception(
                "Error calculating actions metrics",
                extra={"user_id": user_id},
            )
            raise DatabaseError(f"Failed to calculate actions metrics: {e}") from e

    async def get_pipeline_metrics(
        self,
        user_id: str,
        period_start: datetime,
    ) -> dict[str, Any]:
        """Calculate pipeline impact metrics from pipeline_impact table.

        Args:
            user_id: The user's UUID.
            period_start: Start datetime for the calculation period.

        Returns:
            Dict with counts by impact type.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            response = (
                self.db.table("pipeline_impact")
                .select("impact_type")
                .eq("user_id", user_id)
                .gte("created_at", period_start.isoformat())
                .execute()
            )

            impacts = response.data or []

            # Count by type
            metrics = {
                "leads_discovered": 0,
                "meetings_prepped": 0,
                "follow_ups_sent": 0,
            }

            for impact in impacts:
                impact_type = impact.get("impact_type")
                if impact_type == "lead_discovered":
                    metrics["leads_discovered"] += 1
                elif impact_type == "meeting_prepped":
                    metrics["meetings_prepped"] += 1
                elif impact_type == "follow_up_sent":
                    metrics["follow_ups_sent"] += 1
                # deal_influenced is not tracked in the current model

            return metrics

        except Exception as e:
            logger.exception(
                "Error calculating pipeline metrics",
                extra={"user_id": user_id},
            )
            raise DatabaseError(f"Failed to calculate pipeline metrics: {e}") from e

    async def get_weekly_trend(
        self,
        user_id: str,
        period_start: datetime,
    ) -> list[dict[str, Any]]:
        """Calculate weekly time-saved trend from aria_actions table.

        Args:
            user_id: The user's UUID.
            period_start: Start datetime for the calculation period.

        Returns:
            List of weekly data points with week_start and hours_saved.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            response = (
                self.db.table("aria_actions")
                .select("action_type", "estimated_minutes_saved", "created_at")
                .eq("user_id", user_id)
                .gte("created_at", period_start.isoformat())
                .order("created_at")
                .execute()
            )

            actions = response.data or []

            # Group by week
            weekly_data: dict[str, float] = {}

            for action in actions:
                created_at_str = action.get("created_at")
                if not created_at_str:
                    continue

                try:
                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue

                # Get week start (Monday)
                week_start = created_at - timedelta(days=created_at.weekday())
                week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                week_key = week_start.strftime("%Y-%m-%d")

                # Calculate time saved
                action_type = action.get("action_type")
                minutes_saved = action.get("estimated_minutes_saved", 0)

                if action_type in TIME_SAVED_MINUTES:
                    minutes = TIME_SAVED_MINUTES[action_type]
                    weekly_data[week_key] = weekly_data.get(week_key, 0) + (minutes / 60)

            # Convert to list and sort by week
            trend = [
                {"week_start": week, "hours_saved": round(hours, 2)}
                for week, hours in sorted(weekly_data.items())
            ]

            return trend

        except Exception as e:
            logger.exception(
                "Error calculating weekly trend",
                extra={"user_id": user_id},
            )
            raise DatabaseError(f"Failed to calculate weekly trend: {e}") from e

    async def get_all_metrics(
        self,
        user_id: str,
        period: str = "30d",
    ) -> dict[str, Any]:
        """Aggregate all ROI metrics for a user and period.

        Args:
            user_id: The user's UUID.
            period: Time period identifier (7d, 30d, 90d, all).

        Returns:
            Complete ROI metrics response with all metric categories.

        Raises:
            ARIAException: If operation fails.
        """
        try:
            period_start = self._get_period_start(period)

            # Fetch all metrics sequentially
            time_saved = await self.get_time_saved_metrics(user_id, period_start)
            intelligence = await self.get_intelligence_metrics(user_id, period_start)
            actions = await self.get_actions_metrics(user_id, period_start)
            pipeline = await self.get_pipeline_metrics(user_id, period_start)
            weekly_trend = await self.get_weekly_trend(user_id, period_start)

            # Calculate derived metrics
            time_saved_per_week = None
            if weekly_trend:
                total_hours = sum(point["hours_saved"] for point in weekly_trend)
                time_saved_per_week = round(total_hours / len(weekly_trend), 2)

            action_approval_rate = None
            if actions["total"] > 0:
                approved = actions["auto_approved"] + actions["user_approved"]
                action_approval_rate = round(approved / actions["total"], 2)

            return {
                "time_saved": time_saved,
                "intelligence_delivered": intelligence,
                "actions_taken": actions,
                "pipeline_impact": pipeline,
                "weekly_trend": weekly_trend,
                "period": period,
                "calculated_at": datetime.utcnow().isoformat(),
                "time_saved_per_week": time_saved_per_week,
                "action_approval_rate": action_approval_rate,
            }

        except ValueError as e:
            raise ARIAException(
                message=str(e),
                code="INVALID_PERIOD",
                status_code=400,
            ) from e
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception(
                "Error aggregating ROI metrics",
                extra={"user_id": user_id, "period": period},
            )
            raise ARIAException(
                message="Failed to aggregate ROI metrics",
                code="ROI_METRICS_ERROR",
                status_code=500,
            ) from e
