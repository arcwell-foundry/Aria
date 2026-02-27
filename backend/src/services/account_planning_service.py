"""Account planning service for US-941.

Provides:
- Territory listing (accounts from lead_memories)
- Account plan generation & updates (LLM-powered)
- Pipeline forecasting (health_score × expected_value)
- Quota CRUD
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Stage probability weights for forecast
STAGE_WEIGHTS: dict[str, float] = {
    "lead": 0.10,
    "opportunity": 0.40,
    "account": 0.80,
}


class AccountPlanningService:
    """Service for account planning and strategic workflows."""

    def __init__(self) -> None:
        self._db = SupabaseClient.get_client()

    # ------------------------------------------------------------------ #
    # Territory                                                           #
    # ------------------------------------------------------------------ #

    async def list_accounts(
        self,
        user_id: str,
        stage: str | None = None,
        sort_by: str = "last_activity_at",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List accounts (lead memories) with optional stage filter.

        Args:
            user_id: The user's ID.
            stage: Optional lifecycle stage filter.
            sort_by: Column to sort by.
            limit: Max rows returned.

        Returns:
            List of account dicts.
        """
        query = (
            self._db.table("lead_memories")
            .select(
                "id, company_name, lifecycle_stage, status, health_score, "
                "expected_value, last_activity_at, tags"
            )
            .eq("user_id", user_id)
        )

        if stage:
            query = query.eq("lifecycle_stage", stage)

        valid_sorts = {
            "last_activity_at",
            "health_score",
            "expected_value",
            "company_name",
        }
        col = sort_by if sort_by in valid_sorts else "last_activity_at"
        desc = col != "company_name"
        result = query.order(col, desc=desc).limit(limit).execute()

        accounts = cast(list[dict[str, Any]], result.data)

        # Attach latest next-action from account_plans if available
        if accounts:
            lead_ids = [a["id"] for a in accounts]
            plans_result = (
                self._db.table("account_plans")
                .select("lead_memory_id, next_actions")
                .eq("user_id", user_id)
                .in_("lead_memory_id", lead_ids)
                .execute()
            )
            plans_map: dict[str, list[Any]] = {
                p["lead_memory_id"]: p["next_actions"]
                for p in cast(list[dict[str, Any]], plans_result.data)
            }
            for acct in accounts:
                actions = plans_map.get(acct["id"], [])
                acct["next_action"] = actions[0].get("action", "") if actions else None

        logger.info(
            "Accounts listed",
            extra={"user_id": user_id, "count": len(accounts)},
        )
        return accounts

    # ------------------------------------------------------------------ #
    # Account Plan                                                        #
    # ------------------------------------------------------------------ #

    async def get_or_generate_plan(self, user_id: str, lead_id: str) -> dict[str, Any] | None:
        """Get existing plan or generate one with LLM.

        Args:
            user_id: The user's ID.
            lead_id: The lead_memory ID.

        Returns:
            Account plan dict, or None if lead not found.
        """
        # Verify lead ownership
        lead_result = (
            self._db.table("lead_memories")
            .select("*")
            .eq("id", lead_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if lead_result is None or lead_result.data is None:
            return None
        lead = cast(dict[str, Any], lead_result.data)

        # Check for existing plan
        plan_result = (
            self._db.table("account_plans")
            .select("*")
            .eq("user_id", user_id)
            .eq("lead_memory_id", lead_id)
            .maybe_single()
            .execute()
        )
        if plan_result is not None and plan_result.data is not None:
            return cast(dict[str, Any], plan_result.data)

        # Generate new plan with LLM
        return await self._generate_plan(user_id, lead_id, lead)

    async def _generate_plan(
        self, user_id: str, lead_id: str, lead: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate an account plan using LLM.

        Args:
            user_id: The user's ID.
            lead_id: The lead_memory ID.
            lead: Lead data dict.

        Returns:
            Newly created account plan dict.
        """
        # Gather stakeholders
        stakeholders_result = (
            self._db.table("lead_stakeholders")
            .select("contact_name, contact_email, title, role, influence_level, sentiment")
            .eq("lead_memory_id", lead_id)
            .execute()
        )
        stakeholders = cast(list[dict[str, Any]], stakeholders_result.data)

        # Gather recent events
        events_result = (
            self._db.table("lead_events")
            .select("event_type, subject, occurred_at")
            .eq("lead_memory_id", lead_id)
            .order("occurred_at", desc=True)
            .limit(20)
            .execute()
        )
        events = cast(list[dict[str, Any]], events_result.data)

        prompt = (
            "You are ARIA, an AI sales strategist for life sciences commercial teams.\n\n"
            f"Account: {lead.get('company_name')}\n"
            f"Stage: {lead.get('lifecycle_stage')}\n"
            f"Health Score: {lead.get('health_score')}/100\n"
            f"Expected Value: ${lead.get('expected_value', 0):,.0f}\n"
            f"Status: {lead.get('status')}\n\n"
            f"Stakeholders: {json.dumps(stakeholders, default=str)}\n\n"
            f"Recent Activity: {json.dumps(events, default=str)}\n\n"
            "Generate a strategic account plan. Respond with ONLY a JSON object:\n"
            "{\n"
            '  "strategy": "Multi-paragraph strategy document in markdown...",\n'
            '  "next_actions": [\n'
            '    {"action": "...", "priority": "high|medium|low", "due_in_days": N}\n'
            "  ],\n"
            '  "stakeholder_summary": {\n'
            '    "champion": "name or null",\n'
            '    "decision_maker": "name or null",\n'
            '    "key_risk": "description"\n'
            "  }\n"
            "}"
        )

        llm = LLMClient()
        try:
            raw = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2048,
                temperature=0.4,
                task=TaskType.STRATEGIST_PLAN,
            )
            plan_data = json.loads(raw)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Account plan generation failed: %s", exc)
            plan_data = {
                "strategy": (
                    f"## Account Plan: {lead.get('company_name')}\n\n"
                    "Strategy generation is temporarily unavailable. "
                    "Please edit this plan manually."
                ),
                "next_actions": [
                    {"action": "Review account history", "priority": "high", "due_in_days": 7}
                ],
                "stakeholder_summary": {
                    "champion": None,
                    "decision_maker": None,
                    "key_risk": "Plan auto-generation failed",
                },
            }

        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("account_plans")
            .insert(
                {
                    "user_id": user_id,
                    "lead_memory_id": lead_id,
                    "strategy": plan_data.get("strategy", ""),
                    "next_actions": plan_data.get("next_actions", []),
                    "stakeholder_summary": plan_data.get("stakeholder_summary", {}),
                    "generated_at": now,
                    "updated_at": now,
                }
            )
            .execute()
        )

        plan = cast(dict[str, Any], result.data[0])
        logger.info(
            "Account plan generated",
            extra={"user_id": user_id, "lead_id": lead_id, "plan_id": plan["id"]},
        )
        return plan

    async def update_plan(self, user_id: str, lead_id: str, strategy: str) -> dict[str, Any] | None:
        """Update account plan strategy text.

        Args:
            user_id: The user's ID.
            lead_id: The lead_memory ID.
            strategy: Updated strategy text.

        Returns:
            Updated plan dict, or None if not found.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("account_plans")
            .update({"strategy": strategy, "updated_at": now})
            .eq("user_id", user_id)
            .eq("lead_memory_id", lead_id)
            .execute()
        )

        if result.data:
            logger.info(
                "Account plan updated",
                extra={"user_id": user_id, "lead_id": lead_id},
            )
            return cast(dict[str, Any], result.data[0])
        return None

    # ------------------------------------------------------------------ #
    # Forecasting                                                         #
    # ------------------------------------------------------------------ #

    async def get_forecast(self, user_id: str) -> dict[str, Any]:
        """Calculate pipeline forecast from lead memories.

        Groups leads by lifecycle_stage, sums expected_value,
        applies stage probability weights.

        Args:
            user_id: The user's ID.

        Returns:
            Forecast dict with stages, total_pipeline, weighted_pipeline.
        """
        result = (
            self._db.table("lead_memories")
            .select("lifecycle_stage, status, health_score, expected_value")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )

        leads = cast(list[dict[str, Any]], result.data)

        stage_agg: dict[str, dict[str, float | int]] = {}
        for lead in leads:
            stage = lead.get("lifecycle_stage", "lead")
            val = float(lead.get("expected_value") or 0)
            health = int(lead.get("health_score", 50))
            weight = STAGE_WEIGHTS.get(stage, 0.10)

            if stage not in stage_agg:
                stage_agg[stage] = {"count": 0, "total_value": 0.0, "weighted_value": 0.0}

            stage_agg[stage]["count"] = int(stage_agg[stage]["count"]) + 1
            stage_agg[stage]["total_value"] = float(stage_agg[stage]["total_value"]) + val
            stage_agg[stage]["weighted_value"] = float(
                stage_agg[stage]["weighted_value"]
            ) + val * weight * (health / 100)

        stages = [
            {
                "stage": s,
                "count": int(d["count"]),
                "total_value": float(d["total_value"]),
                "weighted_value": round(float(d["weighted_value"]), 2),
            }
            for s, d in stage_agg.items()
        ]

        total_pipeline = sum(s["total_value"] for s in stages)
        weighted_pipeline = sum(s["weighted_value"] for s in stages)

        logger.info(
            "Forecast calculated",
            extra={
                "user_id": user_id,
                "total_pipeline": total_pipeline,
                "weighted_pipeline": weighted_pipeline,
            },
        )
        return {
            "stages": stages,
            "total_pipeline": total_pipeline,
            "weighted_pipeline": round(weighted_pipeline, 2),
        }

    # ------------------------------------------------------------------ #
    # Quota                                                               #
    # ------------------------------------------------------------------ #

    async def get_quota(self, user_id: str, period: str | None = None) -> list[dict[str, Any]]:
        """Get quota records for user.

        Args:
            user_id: The user's ID.
            period: Optional period filter.

        Returns:
            List of quota dicts.
        """
        query = self._db.table("user_quotas").select("*").eq("user_id", user_id)
        if period:
            query = query.eq("period", period)
        result = query.order("period", desc=True).limit(10).execute()
        return cast(list[dict[str, Any]], result.data)

    async def set_quota(self, user_id: str, period: str, target_value: float) -> dict[str, Any]:
        """Create or update a quota.

        Args:
            user_id: The user's ID.
            period: Period key (e.g. '2026-Q1').
            target_value: Quota target.

        Returns:
            Upserted quota dict.
        """
        now = datetime.now(UTC).isoformat()
        result = (
            self._db.table("user_quotas")
            .upsert(
                {
                    "user_id": user_id,
                    "period": period,
                    "target_value": target_value,
                    "updated_at": now,
                },
                on_conflict="user_id,period",
            )
            .execute()
        )

        quota = cast(dict[str, Any], result.data[0])
        logger.info(
            "Quota set",
            extra={"user_id": user_id, "period": period, "target": target_value},
        )
        return quota
