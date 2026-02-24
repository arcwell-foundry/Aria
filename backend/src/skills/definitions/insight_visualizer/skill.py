"""InsightVisualizerSkill -- generate Recharts-compatible visualization specs.

This is a Category B LLM skill (structured prompt chain) that queries
Supabase tables for real user data (lead_memories, health_score_history,
lead_memory_events, battle_cards) and injects the aggregated data into
LLM prompt templates to produce structured Recharts JSON specifications.

Unlike pure-LLM skills, this pre-fetches real data so the visualization
is grounded in actual records rather than hallucinated numbers.

Assigned to: AnalystAgent, StrategistAgent
Trust level: core
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.skills.definitions.base import BaseSkillDefinition

logger = logging.getLogger(__name__)

# Template name constants
TEMPLATE_PIPELINE_FUNNEL = "pipeline_funnel"
TEMPLATE_COMPETITIVE_SPIDER = "competitive_spider"
TEMPLATE_TERRITORY_HEATMAP = "territory_heatmap"
TEMPLATE_WIN_LOSS_TREND = "win_loss_trend"
TEMPLATE_ENGAGEMENT_TIMELINE = "engagement_timeline"
TEMPLATE_HEALTH_DISTRIBUTION = "health_distribution"

# Context variable keys
CONTEXT_USER_ID = "user_id"
CONTEXT_TEMPLATE_NAME = "template_name"
CONTEXT_VISUALIZATION_DATA = "visualization_data"
CONTEXT_COMPETITOR_NAMES = "competitor_names"

# Default data window
_DEFAULT_DAYS_BACK = 90

# Max records per query to keep context size reasonable
_MAX_RECORDS = 200


class InsightVisualizerSkill(BaseSkillDefinition):
    """Generate Recharts visualization specs from real user data.

    Extends :class:`BaseSkillDefinition` by querying Supabase for the
    user's actual lead, health, event, and battle card data.  The
    aggregated data is injected into the LLM context so the model
    produces chart specs grounded in real numbers.

    If the database is unreachable, the skill falls back to LLM-only
    generation with a warning in the metadata.

    Args:
        llm_client: LLM client for prompt execution.
        definitions_dir: Override for the skill definitions base directory.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        definitions_dir: Path | None = None,
    ) -> None:
        super().__init__(
            "insight_visualizer",
            llm_client,
            definitions_dir=definitions_dir,
        )

    # ------------------------------------------------------------------
    # Data fetching helpers
    # ------------------------------------------------------------------

    async def _fetch_pipeline_data(self, user_id: str) -> dict[str, Any]:
        """Fetch lead stage distribution for the pipeline funnel.

        Queries ``lead_memories`` grouped by ``status`` to get counts
        per pipeline stage.

        Args:
            user_id: The user whose leads to query.

        Returns:
            Dict with ``stages`` list and ``total_leads`` count.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("lead_memories")
                .select("id, status, company_name, health_score")
                .eq("user_id", user_id)
                .limit(_MAX_RECORDS)
                .execute()
            )
            records = response.data or []

            # Aggregate by status
            stage_counts: dict[str, int] = {}
            stage_health: dict[str, list[float]] = {}
            for record in records:
                status = record.get("status", "unknown") or "unknown"
                stage_counts[status] = stage_counts.get(status, 0) + 1
                hs = record.get("health_score")
                if hs is not None:
                    stage_health.setdefault(status, []).append(float(hs))

            stages = []
            for status, count in stage_counts.items():
                avg_health = None
                if status in stage_health and stage_health[status]:
                    avg_health = round(
                        sum(stage_health[status]) / len(stage_health[status]), 1
                    )
                stages.append({
                    "stage": status,
                    "count": count,
                    "avg_health_score": avg_health,
                })

            return {"stages": stages, "total_leads": len(records)}

        except Exception as exc:
            logger.warning("Failed to fetch pipeline data: %s", exc)
            return {"stages": [], "total_leads": 0, "error": str(exc)}

    async def _fetch_win_loss_data(
        self, user_id: str, days_back: int = _DEFAULT_DAYS_BACK
    ) -> dict[str, Any]:
        """Fetch lead status changes over time for win/loss trends.

        Queries ``lead_memories`` for records updated within the last
        *days_back* days and groups by month and outcome.

        Args:
            user_id: The user whose leads to query.
            days_back: How far back to look.

        Returns:
            Dict with ``monthly_outcomes`` list and ``summary``.
        """
        try:
            client = SupabaseClient.get_client()
            cutoff = (datetime.now(UTC) - timedelta(days=days_back)).isoformat()
            response = (
                client.table("lead_memories")
                .select("id, status, updated_at")
                .eq("user_id", user_id)
                .gte("updated_at", cutoff)
                .limit(_MAX_RECORDS)
                .execute()
            )
            records = response.data or []

            # Group by year-month and status
            monthly: dict[str, dict[str, int]] = {}
            for record in records:
                updated = record.get("updated_at", "")
                if updated:
                    month_key = updated[:7]  # "YYYY-MM"
                else:
                    continue
                status = record.get("status", "unknown") or "unknown"
                monthly.setdefault(month_key, {})
                monthly[month_key][status] = monthly[month_key].get(status, 0) + 1

            monthly_outcomes = [
                {"month": month, "outcomes": outcomes}
                for month, outcomes in sorted(monthly.items())
            ]

            wins = sum(
                1 for r in records
                if (r.get("status") or "").lower() in ("won", "closed_won", "converted")
            )
            losses = sum(
                1 for r in records
                if (r.get("status") or "").lower() in ("lost", "closed_lost", "disqualified")
            )

            return {
                "monthly_outcomes": monthly_outcomes,
                "summary": {
                    "total_records": len(records),
                    "wins": wins,
                    "losses": losses,
                    "days_analyzed": days_back,
                },
            }

        except Exception as exc:
            logger.warning("Failed to fetch win/loss data: %s", exc)
            return {"monthly_outcomes": [], "summary": {}, "error": str(exc)}

    async def _fetch_engagement_data(self, user_id: str) -> dict[str, Any]:
        """Fetch communication events per lead for the engagement timeline.

        Queries ``lead_memory_events`` grouped by lead and event type.

        Args:
            user_id: The user whose events to query.

        Returns:
            Dict with ``leads`` list containing per-lead event counts.
        """
        try:
            client = SupabaseClient.get_client()
            cutoff = (datetime.now(UTC) - timedelta(days=_DEFAULT_DAYS_BACK)).isoformat()
            response = (
                client.table("lead_memory_events")
                .select("id, lead_memory_id, event_type, created_at")
                .eq("user_id", user_id)
                .gte("created_at", cutoff)
                .limit(_MAX_RECORDS)
                .execute()
            )
            records = response.data or []

            # Group by lead
            lead_events: dict[str, dict[str, int]] = {}
            for record in records:
                lead_id = record.get("lead_memory_id", "unknown")
                event_type = record.get("event_type", "other")
                lead_events.setdefault(lead_id, {})
                lead_events[lead_id][event_type] = (
                    lead_events[lead_id].get(event_type, 0) + 1
                )

            leads = [
                {"lead_id": lead_id, "events": events, "total": sum(events.values())}
                for lead_id, events in lead_events.items()
            ]
            leads.sort(key=lambda x: x["total"], reverse=True)

            return {"leads": leads[:50], "total_events": len(records)}

        except Exception as exc:
            logger.warning("Failed to fetch engagement data: %s", exc)
            return {"leads": [], "total_events": 0, "error": str(exc)}

    async def _fetch_health_distribution(self, user_id: str) -> dict[str, Any]:
        """Fetch health score distribution across the portfolio.

        Queries ``lead_memories`` for health scores and buckets them into
        ranges for histogram visualization.

        Args:
            user_id: The user whose leads to query.

        Returns:
            Dict with ``buckets`` list and ``statistics``.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("lead_memories")
                .select("id, company_name, health_score, status")
                .eq("user_id", user_id)
                .not_.is_("health_score", "null")
                .limit(_MAX_RECORDS)
                .execute()
            )
            records = response.data or []

            scores = [
                float(r["health_score"])
                for r in records
                if r.get("health_score") is not None
            ]

            # Bucket into 10-point ranges
            buckets: dict[str, int] = {}
            for score in scores:
                bucket = f"{int(score // 10) * 10}-{int(score // 10) * 10 + 9}"
                if score >= 100:
                    bucket = "90-100"
                buckets[bucket] = buckets.get(bucket, 0) + 1

            bucket_list = [
                {"range": k, "count": v} for k, v in sorted(buckets.items())
            ]

            stats: dict[str, Any] = {}
            if scores:
                stats = {
                    "mean": round(sum(scores) / len(scores), 1),
                    "min": min(scores),
                    "max": max(scores),
                    "count": len(scores),
                }

            return {"buckets": bucket_list, "statistics": stats}

        except Exception as exc:
            logger.warning("Failed to fetch health distribution: %s", exc)
            return {"buckets": [], "statistics": {}, "error": str(exc)}

    async def _fetch_competitive_data(
        self, user_id: str, competitor_names: list[str] | None = None
    ) -> dict[str, Any]:
        """Fetch battle card data for competitive spider chart.

        Queries ``battle_cards`` for the user's competitors and extracts
        scoring dimensions.

        Args:
            user_id: The user whose battle cards to query.
            competitor_names: Optional filter for specific competitors.

        Returns:
            Dict with ``competitors`` list containing dimension scores.
        """
        try:
            client = SupabaseClient.get_client()
            query = (
                client.table("battle_cards")
                .select("*")
                .eq("user_id", user_id)
                .limit(20)
            )
            if competitor_names:
                query = query.in_("competitor_name", competitor_names)

            response = query.execute()
            records = response.data or []

            competitors = []
            for record in records:
                competitors.append({
                    "name": record.get("competitor_name", "Unknown"),
                    "scores": record.get("dimension_scores", {}),
                    "overall_threat": record.get("overall_threat_score"),
                    "updated_at": record.get("updated_at", ""),
                })

            return {"competitors": competitors, "total": len(competitors)}

        except Exception as exc:
            logger.warning("Failed to fetch competitive data: %s", exc)
            return {"competitors": [], "total": 0, "error": str(exc)}

    async def _fetch_territory_data(self, user_id: str) -> dict[str, Any]:
        """Fetch geographic lead distribution for territory heatmap.

        Queries ``lead_memories`` for location data and groups by region.

        Args:
            user_id: The user whose leads to query.

        Returns:
            Dict with ``regions`` list containing lead counts per location.
        """
        try:
            client = SupabaseClient.get_client()
            response = (
                client.table("lead_memories")
                .select("id, company_name, location, status, health_score")
                .eq("user_id", user_id)
                .not_.is_("location", "null")
                .limit(_MAX_RECORDS)
                .execute()
            )
            records = response.data or []

            # Group by location
            regions: dict[str, dict[str, Any]] = {}
            for record in records:
                location = record.get("location", "Unknown") or "Unknown"
                if location not in regions:
                    regions[location] = {"count": 0, "health_scores": []}
                regions[location]["count"] += 1
                hs = record.get("health_score")
                if hs is not None:
                    regions[location]["health_scores"].append(float(hs))

            region_list = []
            for location, data in regions.items():
                avg_health = None
                if data["health_scores"]:
                    avg_health = round(
                        sum(data["health_scores"]) / len(data["health_scores"]), 1
                    )
                region_list.append({
                    "location": location,
                    "lead_count": data["count"],
                    "avg_health_score": avg_health,
                })

            region_list.sort(key=lambda x: x["lead_count"], reverse=True)

            return {"regions": region_list[:50], "total_leads": len(records)}

        except Exception as exc:
            logger.warning("Failed to fetch territory data: %s", exc)
            return {"regions": [], "total_leads": 0, "error": str(exc)}

    # ------------------------------------------------------------------
    # Template → data source mapping
    # ------------------------------------------------------------------

    async def _fetch_data_for_template(
        self,
        template_name: str,
        user_id: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Route to the correct data fetcher based on the template.

        Args:
            template_name: The visualization template being rendered.
            user_id: The requesting user's ID.
            context: Full context dict (may contain competitor_names etc).

        Returns:
            Aggregated data dict for injection into the LLM prompt.
        """
        if template_name == TEMPLATE_PIPELINE_FUNNEL:
            return await self._fetch_pipeline_data(user_id)

        if template_name == TEMPLATE_WIN_LOSS_TREND:
            return await self._fetch_win_loss_data(user_id)

        if template_name == TEMPLATE_ENGAGEMENT_TIMELINE:
            return await self._fetch_engagement_data(user_id)

        if template_name == TEMPLATE_HEALTH_DISTRIBUTION:
            return await self._fetch_health_distribution(user_id)

        if template_name == TEMPLATE_COMPETITIVE_SPIDER:
            competitor_names = context.get(CONTEXT_COMPETITOR_NAMES)
            if isinstance(competitor_names, str):
                competitor_names = [
                    n.strip() for n in competitor_names.split(",") if n.strip()
                ]
            return await self._fetch_competitive_data(user_id, competitor_names)

        if template_name == TEMPLATE_TERRITORY_HEATMAP:
            return await self._fetch_territory_data(user_id)

        logger.warning("No data fetcher for template '%s'", template_name)
        return {}

    # ------------------------------------------------------------------
    # High-level analysis entry point
    # ------------------------------------------------------------------

    async def generate_analysis(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch real user data and generate a Recharts visualization spec.

        This is the primary entry point. It:

        1. Queries the appropriate Supabase table(s) for the user's data.
        2. Injects the aggregated data into *context* under the key
           ``visualization_data``.
        3. Delegates to :meth:`run_template` for LLM-driven chart spec
           generation.

        If the database is unreachable, the method falls back to LLM-only
        generation (no real data injected) and sets a note in the context.

        Args:
            template_name: One of ``pipeline_funnel``,
                ``competitive_spider``, ``territory_heatmap``,
                ``win_loss_trend``, ``engagement_timeline``, or
                ``health_distribution``.
            context: Context dict.  Must include ``user_id``.

        Returns:
            Parsed JSON output conforming to the skill's output schema
            (chart_type, data, config, metadata).

        Raises:
            ValueError: If ``user_id`` is missing from context or the
                template name is unknown.
        """
        user_id: str | None = context.get(CONTEXT_USER_ID)
        if not user_id:
            raise ValueError("InsightVisualizerSkill requires 'user_id' in context")

        logger.info(
            "Generating visualization",
            extra={
                "skill": self._skill_name,
                "template": template_name,
                "user_id": user_id,
            },
        )

        # --- Fetch real data from Supabase ---
        viz_data = await self._fetch_data_for_template(template_name, user_id, context)

        if viz_data and "error" not in viz_data:
            context[CONTEXT_VISUALIZATION_DATA] = json.dumps(viz_data, indent=2)
            record_count = (
                viz_data.get("total_leads", 0)
                or viz_data.get("total_events", 0)
                or viz_data.get("total", 0)
                or len(viz_data.get("stages", []))
                or len(viz_data.get("buckets", []))
                or len(viz_data.get("monthly_outcomes", []))
            )
            logger.info(
                "Injected %d records into visualization context",
                record_count,
            )
        else:
            logger.warning(
                "No data available for '%s' — falling back to LLM-only generation",
                template_name,
            )
            context[CONTEXT_VISUALIZATION_DATA] = json.dumps(
                {
                    "note": (
                        f"Database returned no results for template "
                        f"'{template_name}'. Generate a visualization spec "
                        f"with empty data array and note the data gap in "
                        f"metadata.summary."
                    ),
                },
                indent=2,
            )

        # --- Delegate to LLM template ---
        return await self.run_template(template_name, context)
