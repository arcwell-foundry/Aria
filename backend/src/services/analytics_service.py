"""Analytics Service for ARIA.

Provides comprehensive analytics and metrics calculations across user activities,
lead performance, conversion funnel, activity trends, response times, and ARIA impact.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from src.core.cache import cached
from src.core.exceptions import DatabaseError
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Lifecycle stages in funnel order
LIFECYCLE_STAGES = ["lead", "opportunity", "account"]


def _analytics_cache_key(*args: Any, **kwargs: Any) -> str:
    """Generate cache key for analytics methods based on user_id and date range.

    Args[0] is self for instance methods.
    """
    user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "")
    period_start = args[2] if len(args) > 2 else kwargs.get("period_start")
    period_end = args[3] if len(args) > 3 else kwargs.get("period_end")

    start_str = period_start.isoformat() if period_start else ""
    end_str = period_end.isoformat() if period_end else ""

    # Include calling function context for uniqueness
    return f"analytics:{user_id}:{start_str}:{end_str}"


class AnalyticsService:
    """Service for analytics and metrics calculations."""

    def __init__(self) -> None:
        """Initialize AnalyticsService."""
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

    @cached(ttl=300, key_func=_analytics_cache_key)  # 5 minute TTL
    async def get_overview_metrics(
        self,
        user_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any]:
        """Get high-level overview metrics for a user within a date range.

        Args:
            user_id: The user's UUID.
            period_start: Start datetime for the calculation period.
            period_end: End datetime for the calculation period.

        Returns:
            Dict with leads_created, meetings_booked, emails_sent,
            debriefs_completed, goals_completed, avg_health_score,
            and time_saved_minutes.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            start_iso = period_start.isoformat()
            end_iso = period_end.isoformat()

            # Leads created in period
            leads_resp = (
                self.db.table("lead_memories")
                .select("id")
                .eq("user_id", user_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )
            leads_created = len(leads_resp.data or [])

            # Calendar events with external attendees (meetings booked)
            events_resp = (
                self.db.table("calendar_events")
                .select("id, attendees")
                .eq("user_id", user_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )
            meetings_booked = 0
            for event in events_resp.data or []:
                attendees = event.get("attendees") or []
                if len(attendees) > 0:
                    meetings_booked += 1

            # Emails sent in period
            emails_resp = (
                self.db.table("email_drafts")
                .select("id")
                .eq("user_id", user_id)
                .eq("status", "sent")
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )
            emails_sent = len(emails_resp.data or [])

            # Meeting debriefs completed
            debriefs_resp = (
                self.db.table("meeting_debriefs")
                .select("id")
                .eq("user_id", user_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )
            debriefs_completed = len(debriefs_resp.data or [])

            # Goals completed
            goals_resp = (
                self.db.table("goals")
                .select("id")
                .eq("user_id", user_id)
                .eq("status", "complete")
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )
            goals_completed = len(goals_resp.data or [])

            # Average health score across active leads
            health_resp = (
                self.db.table("lead_memories")
                .select("health_score")
                .eq("user_id", user_id)
                .eq("status", "active")
                .execute()
            )
            health_scores = [
                row["health_score"]
                for row in (health_resp.data or [])
                if row.get("health_score") is not None
            ]
            avg_health_score = (
                round(sum(health_scores) / len(health_scores), 1)
                if health_scores
                else None
            )

            # Time saved from ARIA actions
            actions_resp = (
                self.db.table("aria_actions")
                .select("estimated_minutes_saved")
                .eq("user_id", user_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )
            time_saved_minutes = sum(
                row.get("estimated_minutes_saved", 0)
                for row in (actions_resp.data or [])
            )

            return {
                "leads_created": leads_created,
                "meetings_booked": meetings_booked,
                "emails_sent": emails_sent,
                "debriefs_completed": debriefs_completed,
                "goals_completed": goals_completed,
                "avg_health_score": avg_health_score,
                "time_saved_minutes": time_saved_minutes,
            }

        except Exception as e:
            logger.exception(
                "Error calculating overview metrics",
                extra={"user_id": user_id},
            )
            raise DatabaseError(f"Failed to calculate overview metrics: {e}") from e

    @cached(ttl=300, key_func=_analytics_cache_key)  # 5 minute TTL
    async def get_conversion_funnel(
        self,
        user_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any]:
        """Get conversion funnel metrics showing lead progression through stages.

        Args:
            user_id: The user's UUID.
            period_start: Start datetime for the calculation period.
            period_end: End datetime for the calculation period.

        Returns:
            Dict with stages (counts per stage), conversion_rates
            (stage-to-stage percentages), and avg_days_in_stage.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            start_iso = period_start.isoformat()
            end_iso = period_end.isoformat()

            response = (
                self.db.table("lead_memories")
                .select("id, lifecycle_stage, created_at, updated_at")
                .eq("user_id", user_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )

            leads = response.data or []

            # Count leads per stage
            stage_counts: dict[str, int] = dict.fromkeys(LIFECYCLE_STAGES, 0)
            stage_durations: dict[str, list[float]] = {
                stage: [] for stage in LIFECYCLE_STAGES
            }

            for lead in leads:
                stage = lead.get("lifecycle_stage", "lead")
                if stage in stage_counts:
                    stage_counts[stage] += 1

                # Calculate time in current stage using created_at → updated_at
                created_str = lead.get("created_at")
                updated_str = lead.get("updated_at")
                if created_str and updated_str:
                    try:
                        created = datetime.fromisoformat(
                            created_str.replace("Z", "+00:00")
                        )
                        updated = datetime.fromisoformat(
                            updated_str.replace("Z", "+00:00")
                        )
                        days_in_stage = (updated - created).total_seconds() / 86400
                        if stage in stage_durations:
                            stage_durations[stage].append(days_in_stage)
                    except (ValueError, AttributeError):
                        pass

            # Calculate conversion rates between adjacent stages
            conversion_rates: dict[str, float | None] = {}
            for i in range(len(LIFECYCLE_STAGES) - 1):
                from_stage = LIFECYCLE_STAGES[i]
                to_stage = LIFECYCLE_STAGES[i + 1]
                key = f"{from_stage}_to_{to_stage}"
                from_count = stage_counts[from_stage] + stage_counts[to_stage]
                # All leads that were ever in from_stage includes those that moved to to_stage
                for j in range(i + 2, len(LIFECYCLE_STAGES)):
                    from_count += stage_counts[LIFECYCLE_STAGES[j]]

                if from_count > 0:
                    moved_forward = sum(
                        stage_counts[LIFECYCLE_STAGES[j]]
                        for j in range(i + 1, len(LIFECYCLE_STAGES))
                    )
                    conversion_rates[key] = round(moved_forward / from_count, 4)
                else:
                    conversion_rates[key] = None

            # Calculate average days in each stage
            avg_days_in_stage: dict[str, float | None] = {}
            for stage in LIFECYCLE_STAGES:
                durations = stage_durations[stage]
                if durations:
                    avg_days_in_stage[stage] = round(
                        sum(durations) / len(durations), 1
                    )
                else:
                    avg_days_in_stage[stage] = None

            return {
                "stages": stage_counts,
                "conversion_rates": conversion_rates,
                "avg_days_in_stage": avg_days_in_stage,
            }

        except Exception as e:
            logger.exception(
                "Error calculating conversion funnel",
                extra={"user_id": user_id},
            )
            raise DatabaseError(f"Failed to calculate conversion funnel: {e}") from e

    def _activity_trends_cache_key(*args: Any, **kwargs: Any) -> str:
        """Cache key for activity trends includes granularity."""
        user_id = args[1] if len(args) > 1 else kwargs.get("user_id", "")
        period_start = args[2] if len(args) > 2 else kwargs.get("period_start")
        period_end = args[3] if len(args) > 3 else kwargs.get("period_end")
        granularity = args[4] if len(args) > 4 else kwargs.get("granularity", "day")

        start_str = period_start.isoformat() if period_start else ""
        end_str = period_end.isoformat() if period_end else ""

        return f"activity_trends:{user_id}:{start_str}:{end_str}:{granularity}"

    @cached(ttl=300, key_func=_activity_trends_cache_key)  # 5 minute TTL
    async def get_activity_trends(
        self,
        user_id: str,
        period_start: datetime,
        period_end: datetime,
        granularity: str = "day",
    ) -> dict[str, Any]:
        """Get time-series activity trends grouped by day, week, or month.

        Args:
            user_id: The user's UUID.
            period_start: Start datetime for the calculation period.
            period_end: End datetime for the calculation period.
            granularity: Time grouping - 'day', 'week', or 'month'.

        Returns:
            Dict with series containing time-bucketed counts for
            emails_sent, meetings, aria_actions, and leads_created.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            start_iso = period_start.isoformat()
            end_iso = period_end.isoformat()

            # Fetch emails sent
            emails_resp = (
                self.db.table("email_drafts")
                .select("created_at")
                .eq("user_id", user_id)
                .eq("status", "sent")
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )

            # Fetch calendar events
            events_resp = (
                self.db.table("calendar_events")
                .select("created_at")
                .eq("user_id", user_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )

            # Fetch ARIA actions
            actions_resp = (
                self.db.table("aria_actions")
                .select("created_at")
                .eq("user_id", user_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )

            # Fetch leads created
            leads_resp = (
                self.db.table("lead_memories")
                .select("created_at")
                .eq("user_id", user_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )

            def bucket_key(dt_str: str) -> str | None:
                try:
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    return None
                if granularity == "week":
                    week_start = dt - timedelta(days=dt.weekday())
                    return week_start.strftime("%Y-%m-%d")
                elif granularity == "month":
                    return dt.strftime("%Y-%m")
                else:  # day
                    return dt.strftime("%Y-%m-%d")

            def count_by_bucket(rows: list[dict[str, Any]]) -> dict[str, int]:
                counts: dict[str, int] = defaultdict(int)
                for row in rows:
                    key = bucket_key(row.get("created_at", ""))
                    if key:
                        counts[key] += 1
                return dict(sorted(counts.items()))

            return {
                "granularity": granularity,
                "series": {
                    "emails_sent": count_by_bucket(emails_resp.data or []),
                    "meetings": count_by_bucket(events_resp.data or []),
                    "aria_actions": count_by_bucket(actions_resp.data or []),
                    "leads_created": count_by_bucket(leads_resp.data or []),
                },
            }

        except Exception as e:
            logger.exception(
                "Error calculating activity trends",
                extra={"user_id": user_id},
            )
            raise DatabaseError(f"Failed to calculate activity trends: {e}") from e

    @cached(ttl=300, key_func=_analytics_cache_key)  # 5 minute TTL
    async def get_response_time_metrics(
        self,
        user_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any]:
        """Get email response time metrics.

        Measures the time between email_drafts creation and sent_at timestamp
        to approximate response time.

        Args:
            user_id: The user's UUID.
            period_start: Start datetime for the calculation period.
            period_end: End datetime for the calculation period.

        Returns:
            Dict with avg_response_minutes, by_lead (response time per lead),
            and trend (daily average response times).

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            start_iso = period_start.isoformat()
            end_iso = period_end.isoformat()

            response = (
                self.db.table("email_drafts")
                .select("created_at, sent_at, lead_memory_id")
                .eq("user_id", user_id)
                .eq("status", "sent")
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )

            emails = response.data or []

            all_response_minutes: list[float] = []
            by_lead: dict[str, list[float]] = defaultdict(list)
            by_day: dict[str, list[float]] = defaultdict(list)

            for email in emails:
                created_str = email.get("created_at")
                sent_str = email.get("sent_at")
                if not created_str or not sent_str:
                    continue

                try:
                    created = datetime.fromisoformat(
                        created_str.replace("Z", "+00:00")
                    )
                    sent = datetime.fromisoformat(sent_str.replace("Z", "+00:00"))
                    response_minutes = (sent - created).total_seconds() / 60
                    if response_minutes < 0:
                        continue

                    all_response_minutes.append(response_minutes)

                    lead_id = email.get("lead_memory_id")
                    if lead_id:
                        by_lead[lead_id].append(response_minutes)

                    day_key = created.strftime("%Y-%m-%d")
                    by_day[day_key].append(response_minutes)
                except (ValueError, AttributeError):
                    continue

            avg_response_minutes = (
                round(sum(all_response_minutes) / len(all_response_minutes), 1)
                if all_response_minutes
                else None
            )

            lead_averages = {
                lead_id: round(sum(times) / len(times), 1)
                for lead_id, times in by_lead.items()
            }

            trend = [
                {
                    "date": day,
                    "avg_response_minutes": round(sum(times) / len(times), 1),
                }
                for day, times in sorted(by_day.items())
            ]

            return {
                "avg_response_minutes": avg_response_minutes,
                "by_lead": lead_averages,
                "trend": trend,
            }

        except Exception as e:
            logger.exception(
                "Error calculating response time metrics",
                extra={"user_id": user_id},
            )
            raise DatabaseError(
                f"Failed to calculate response time metrics: {e}"
            ) from e

    @cached(ttl=300, key_func=_analytics_cache_key)  # 5 minute TTL
    async def get_aria_impact_summary(
        self,
        user_id: str,
        period_start: datetime,
        period_end: datetime,
    ) -> dict[str, Any]:
        """Get summary of ARIA's impact including actions, time saved, and pipeline.

        Args:
            user_id: The user's UUID.
            period_start: Start datetime for the calculation period.
            period_end: End datetime for the calculation period.

        Returns:
            Dict with total_actions, by_action_type breakdown,
            estimated_time_saved_minutes, and pipeline_impact data.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            start_iso = period_start.isoformat()
            end_iso = period_end.isoformat()

            # Fetch all ARIA actions in period
            actions_resp = (
                self.db.table("aria_actions")
                .select("action_type, estimated_minutes_saved, status")
                .eq("user_id", user_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )

            actions = actions_resp.data or []

            type_counts: dict[str, int] = defaultdict(int)
            total_minutes_saved = 0
            for action in actions:
                action_type = action.get("action_type", "unknown")
                type_counts[action_type] += 1
                total_minutes_saved += action.get("estimated_minutes_saved", 0)

            # Fetch pipeline impact
            pipeline_resp = (
                self.db.table("pipeline_impact")
                .select("impact_type, estimated_value")
                .eq("user_id", user_id)
                .gte("created_at", start_iso)
                .lte("created_at", end_iso)
                .execute()
            )

            impacts = pipeline_resp.data or []

            impact_breakdown: dict[str, dict[str, Any]] = defaultdict(
                lambda: {"count": 0, "estimated_value": 0.0}
            )
            for impact in impacts:
                impact_type = impact.get("impact_type", "unknown")
                impact_breakdown[impact_type]["count"] += 1
                impact_breakdown[impact_type]["estimated_value"] += impact.get(
                    "estimated_value", 0
                ) or 0

            # Round estimated values
            for data in impact_breakdown.values():
                data["estimated_value"] = round(data["estimated_value"], 2)

            return {
                "total_actions": len(actions),
                "by_action_type": dict(type_counts),
                "estimated_time_saved_minutes": total_minutes_saved,
                "pipeline_impact": dict(impact_breakdown),
            }

        except Exception as e:
            logger.exception(
                "Error calculating ARIA impact summary",
                extra={"user_id": user_id},
            )
            raise DatabaseError(
                f"Failed to calculate ARIA impact summary: {e}"
            ) from e

    async def compare_periods(
        self,
        user_id: str,
        current_start: datetime,
        current_end: datetime,
        previous_start: datetime,
        previous_end: datetime,
    ) -> dict[str, Any]:
        """Compare metrics between two time periods with delta percentages.

        Args:
            user_id: The user's UUID.
            current_start: Start of current period.
            current_end: End of current period.
            previous_start: Start of previous period.
            previous_end: End of previous period.

        Returns:
            Dict with current and previous metrics plus delta_pct for each metric.

        Raises:
            DatabaseError: If database operation fails.
        """
        try:
            current = await self.get_overview_metrics(
                user_id, current_start, current_end
            )
            previous = await self.get_overview_metrics(
                user_id, previous_start, previous_end
            )

            deltas: dict[str, float | None] = {}
            comparable_keys = [
                "leads_created",
                "meetings_booked",
                "emails_sent",
                "debriefs_completed",
                "goals_completed",
                "time_saved_minutes",
            ]
            for key in comparable_keys:
                curr_val = current.get(key, 0)
                prev_val = previous.get(key, 0)
                if prev_val and prev_val > 0:
                    deltas[key] = round(
                        ((curr_val - prev_val) / prev_val) * 100, 1
                    )
                elif curr_val > 0:
                    deltas[key] = 100.0
                else:
                    deltas[key] = 0.0

            # Health score delta (absolute change, not percentage)
            curr_health = current.get("avg_health_score")
            prev_health = previous.get("avg_health_score")
            if curr_health is not None and prev_health is not None:
                deltas["avg_health_score"] = round(curr_health - prev_health, 1)
            else:
                deltas["avg_health_score"] = None

            return {
                "current": current,
                "previous": previous,
                "delta_pct": deltas,
            }

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception(
                "Error comparing periods",
                extra={"user_id": user_id},
            )
            raise DatabaseError(f"Failed to compare periods: {e}") from e
