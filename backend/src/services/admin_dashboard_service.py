"""Admin Dashboard Service.

Provides aggregated query methods for the admin dashboard endpoints.
All methods query Supabase directly and return typed dictionaries.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class AdminDashboardService:
    """Query methods for the admin dashboard."""

    async def get_dashboard_overview(self) -> dict[str, Any]:
        """Top-level KPIs for the dashboard overview.

        Returns:
            Dictionary with active_users, cost_today, active_ooda,
            pass_rate, avg_trust, cost_alert.
        """
        client = SupabaseClient.get_client()
        today = datetime.now(UTC).date().isoformat()

        # Active users (usage today)
        usage_resp = client.table("usage_tracking").select(
            "user_id, estimated_cost_usd"
        ).eq("date", today).execute()
        usage_rows = usage_resp.data or []
        active_users = len(usage_rows)
        cost_today = sum(float(r.get("estimated_cost_usd", 0)) for r in usage_rows)
        cost_alert = cost_today > 30.0

        # Active OODA cycles
        ooda_resp = client.table("ooda_cycle_logs").select(
            "cycle_id", count="exact"
        ).eq("is_complete", False).execute()
        active_ooda = len({r["cycle_id"] for r in (ooda_resp.data or [])})

        # Verification pass rate (last 7 days)
        week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        traces_resp = client.table("delegation_traces").select(
            "verification_result"
        ).not_.is_("verification_result", "null").gte(
            "created_at", week_ago
        ).execute()
        traces_data = traces_resp.data or []
        total_verified = len(traces_data)
        passed = sum(
            1 for t in traces_data
            if isinstance(t.get("verification_result"), dict)
            and t["verification_result"].get("passed", False)
        )
        pass_rate = (passed / total_verified * 100) if total_verified else 0.0

        # Average trust
        trust_resp = client.table("user_trust_profiles").select(
            "trust_score"
        ).execute()
        trust_rows = trust_resp.data or []
        avg_trust = (
            sum(float(r.get("trust_score", 0)) for r in trust_rows) / len(trust_rows)
            if trust_rows
            else 0.0
        )

        return {
            "active_users": active_users,
            "cost_today": round(cost_today, 2),
            "active_ooda": active_ooda,
            "pass_rate": round(pass_rate, 1),
            "avg_trust": round(avg_trust, 3),
            "cost_alert": cost_alert,
        }

    async def get_active_ooda_cycles(self, limit: int = 50) -> list[dict[str, Any]]:
        """Active (incomplete) OODA cycles for real-time monitoring.

        Args:
            limit: Maximum number of cycles to return.

        Returns:
            List of active cycle summaries.
        """
        client = SupabaseClient.get_client()
        resp = client.table("ooda_cycle_logs").select("*").eq(
            "is_complete", False
        ).order("created_at", desc=True).limit(limit * 4).execute()

        rows = resp.data or []

        # Group by cycle_id
        cycles: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            cid = row["cycle_id"]
            cycles.setdefault(cid, []).append(row)

        result = []
        for cycle_id, phases in list(cycles.items())[:limit]:
            phases.sort(key=lambda p: p.get("created_at", ""))
            latest = phases[-1]
            total_duration = sum(p.get("duration_ms", 0) for p in phases)
            total_tokens = sum(p.get("tokens_used", 0) for p in phases)
            agents = []
            for p in phases:
                if p.get("agents_dispatched"):
                    agents.extend(p["agents_dispatched"])

            result.append({
                "cycle_id": cycle_id,
                "goal_id": latest.get("goal_id", ""),
                "user_id": latest.get("user_id", ""),
                "current_phase": latest.get("phase", ""),
                "iteration": latest.get("iteration", 0),
                "total_duration_ms": total_duration,
                "total_tokens": total_tokens,
                "phases_completed": len(phases),
                "agents_dispatched": list(set(agents)),
                "started_at": phases[0].get("created_at", ""),
            })

        return result

    async def get_agent_waterfall(
        self, hours: int = 24, limit: int = 200
    ) -> list[dict[str, Any]]:
        """Agent execution timeline for waterfall visualization.

        Args:
            hours: How far back to look.
            limit: Maximum executions to return.

        Returns:
            List of agent execution records.
        """
        client = SupabaseClient.get_client()
        since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

        resp = client.table("delegation_traces").select(
            "trace_id, delegatee, status, cost_usd, created_at, "
            "task_description, inputs, outputs, verification_result"
        ).gte("created_at", since).order(
            "created_at", desc=True
        ).limit(limit).execute()

        result = []
        for row in resp.data or []:
            inputs_size = len(str(row.get("inputs", "")))
            outputs_size = len(str(row.get("outputs", "")))
            verification = row.get("verification_result")
            passed = None
            if isinstance(verification, dict):
                passed = verification.get("passed")

            result.append({
                "trace_id": row.get("trace_id", ""),
                "delegatee": row.get("delegatee", ""),
                "status": row.get("status", ""),
                "cost_usd": float(row.get("cost_usd", 0) or 0),
                "created_at": row.get("created_at", ""),
                "task_description": (row.get("task_description", "") or "")[:100],
                "input_size": inputs_size,
                "output_size": outputs_size,
                "verification_passed": passed,
            })

        return result

    async def get_team_usage(
        self, days: int = 30, granularity: str = "day"  # noqa: ARG002
    ) -> dict[str, Any]:
        """Team token usage over time.

        Args:
            days: How far back to look.
            granularity: Aggregation level (day/week). Reserved for future use.

        Returns:
            Dictionary with users list, daily totals, and alerts.
        """
        client = SupabaseClient.get_client()
        since = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()

        resp = client.table("usage_tracking").select("*").gte(
            "date", since
        ).order("date", desc=True).execute()

        rows = resp.data or []

        # Per-user aggregation
        user_totals: dict[str, dict[str, Any]] = {}
        daily_totals: dict[str, dict[str, float]] = {}
        alerts: list[dict[str, Any]] = []

        for row in rows:
            uid = row.get("user_id", "")
            date = row.get("date", "")
            cost = float(row.get("estimated_cost_usd", 0))
            tokens = int(row.get("input_tokens_total", 0)) + int(
                row.get("output_tokens_total", 0)
            )
            thinking = int(row.get("thinking_tokens_total", 0))

            # User totals
            if uid not in user_totals:
                user_totals[uid] = {
                    "user_id": uid,
                    "total_cost": 0.0,
                    "total_tokens": 0,
                    "total_thinking_tokens": 0,
                    "total_calls": 0,
                    "days_active": 0,
                }
            user_totals[uid]["total_cost"] += cost
            user_totals[uid]["total_tokens"] += tokens
            user_totals[uid]["total_thinking_tokens"] += thinking
            user_totals[uid]["total_calls"] += int(row.get("llm_calls_total", 0))
            user_totals[uid]["days_active"] += 1

            # Daily totals
            if date not in daily_totals:
                daily_totals[date] = {
                    "date": date,
                    "cost": 0.0,
                    "tokens": 0,
                    "thinking_tokens": 0,
                }
            daily_totals[date]["cost"] += cost
            daily_totals[date]["tokens"] += tokens
            daily_totals[date]["thinking_tokens"] += thinking

            # Alert if user exceeds $30/day
            if cost > 30.0:
                alerts.append({
                    "user_id": uid,
                    "date": date,
                    "cost": round(cost, 2),
                    "message": f"User exceeded $30/day limit: ${cost:.2f}",
                })

        return {
            "users": sorted(
                user_totals.values(), key=lambda u: u["total_cost"], reverse=True
            ),
            "daily_totals": sorted(
                daily_totals.values(), key=lambda d: d["date"], reverse=True  # type: ignore[arg-type]
            ),
            "alerts": alerts,
        }

    async def get_trust_summaries(self) -> list[dict[str, Any]]:
        """Per-user trust overview.

        Returns:
            List of user trust summaries with categories.
        """
        client = SupabaseClient.get_client()
        resp = client.table("user_trust_profiles").select("*").execute()
        rows = resp.data or []

        # Group by user
        users: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            uid = row.get("user_id", "")
            users.setdefault(uid, []).append(row)

        result = []
        for user_id, categories in users.items():
            scores = [float(c.get("trust_score", 0)) for c in categories]
            avg = sum(scores) / len(scores) if scores else 0.0

            # Detect "stuck" users: trust < 0.3 with > 5 actions
            total_actions = sum(
                int(c.get("successful_actions", 0)) + int(c.get("failed_actions", 0))
                for c in categories
            )
            is_stuck = avg < 0.3 and total_actions > 5

            result.append({
                "user_id": user_id,
                "avg_trust": round(avg, 3),
                "categories": [
                    {
                        "action_category": c.get("action_category", ""),
                        "trust_score": float(c.get("trust_score", 0)),
                        "successful_actions": int(c.get("successful_actions", 0)),
                        "failed_actions": int(c.get("failed_actions", 0)),
                        "override_count": int(c.get("override_count", 0)),
                    }
                    for c in categories
                ],
                "is_stuck": is_stuck,
                "total_actions": total_actions,
            })

        return sorted(result, key=lambda u: u["avg_trust"])

    async def get_trust_evolution(
        self, user_id: str | None = None, days: int = 30
    ) -> list[dict[str, Any]]:
        """Trust score time series.

        Args:
            user_id: Optional filter for specific user.
            days: How far back to look.

        Returns:
            List of trust evolution data points.
        """
        client = SupabaseClient.get_client()
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

        query = client.table("trust_score_history").select("*").gte(
            "recorded_at", since
        ).order("recorded_at", desc=False)

        if user_id:
            query = query.eq("user_id", user_id)

        resp = query.limit(1000).execute()

        return [
            {
                "user_id": row.get("user_id", ""),
                "action_category": row.get("action_category", ""),
                "trust_score": float(row.get("trust_score", 0)),
                "change_type": row.get("change_type", ""),
                "recorded_at": row.get("recorded_at", ""),
            }
            for row in (resp.data or [])
        ]

    async def get_verification_stats(self, days: int = 30) -> dict[str, Any]:
        """Verification pass/fail rates.

        Args:
            days: How far back to look.

        Returns:
            Dictionary with overall pass rate, by-agent, and by-task-type breakdowns.
        """
        client = SupabaseClient.get_client()
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()

        resp = client.table("delegation_traces").select(
            "delegatee, task_description, verification_result"
        ).not_.is_("verification_result", "null").gte(
            "created_at", since
        ).execute()

        rows = resp.data or []

        total = len(rows)
        passed_count = 0
        by_agent: dict[str, dict[str, int]] = {}
        by_task_type: dict[str, dict[str, int]] = {}

        for row in rows:
            vr = row.get("verification_result", {})
            passed = isinstance(vr, dict) and vr.get("passed", False)
            if passed:
                passed_count += 1

            agent = row.get("delegatee", "unknown")
            by_agent.setdefault(agent, {"passed": 0, "failed": 0, "total": 0})
            by_agent[agent]["total"] += 1
            by_agent[agent]["passed" if passed else "failed"] += 1

            # Extract task type from description
            desc = row.get("task_description", "") or ""
            task_type = desc.split()[0].lower() if desc else "unknown"
            by_task_type.setdefault(task_type, {"passed": 0, "failed": 0, "total": 0})
            by_task_type[task_type]["total"] += 1
            by_task_type[task_type]["passed" if passed else "failed"] += 1

        overall_pass_rate = (passed_count / total * 100) if total else 0.0

        # Find worst agent
        worst_agent = ""
        worst_rate = 100.0
        for agent, stats in by_agent.items():
            rate = (stats["passed"] / stats["total"] * 100) if stats["total"] else 100
            if rate < worst_rate:
                worst_rate = rate
                worst_agent = agent

        return {
            "overall_pass_rate": round(overall_pass_rate, 1),
            "total_verified": total,
            "total_passed": passed_count,
            "worst_agent": worst_agent,
            "by_agent": [
                {
                    "agent": agent,
                    "passed": stats["passed"],
                    "failed": stats["failed"],
                    "total": stats["total"],
                    "pass_rate": round(
                        (stats["passed"] / stats["total"] * 100) if stats["total"] else 0, 1
                    ),
                }
                for agent, stats in sorted(
                    by_agent.items(),
                    key=lambda x: (x[1]["passed"] / x[1]["total"] * 100) if x[1]["total"] else 0,
                )
            ],
            "by_task_type": [
                {
                    "task_type": tt,
                    "passed": stats["passed"],
                    "failed": stats["failed"],
                    "total": stats["total"],
                    "pass_rate": round(
                        (stats["passed"] / stats["total"] * 100) if stats["total"] else 0, 1
                    ),
                }
                for tt, stats in sorted(
                    by_task_type.items(),
                    key=lambda x: (x[1]["passed"] / x[1]["total"] * 100) if x[1]["total"] else 0,
                )
            ],
        }
