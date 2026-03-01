"""Skill trust graduation and health monitoring.

- SkillTrustManager: Records executions, graduates trust (LOW→MEDIUM→HIGH),
  demotes on consecutive failures.
- SkillHealthMonitor: Scheduled job checks error rates, marks degraded/broken,
  auto-disables broken skills.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TRUST_ORDER = ["LOW", "MEDIUM", "HIGH"]


class SkillTrustManager:
    """Manages trust graduation for ARIA-generated skills.

    LOW → MEDIUM: 5 successful executions, 0 failures
    MEDIUM → HIGH: 20 successful executions, <5% error rate
    Demotion: 3 consecutive failures → downgrade one level
    """

    def __init__(self, db_client: Any) -> None:
        self._db = db_client

    async def record_execution(
        self, skill_id: str, success: bool, quality_score: float
    ) -> None:
        """Record a skill execution and check for trust graduation/demotion."""
        skill_result = (
            self._db.table("aria_generated_skills")
            .select("*")
            .eq("id", skill_id)
            .single()
            .execute()
        )
        skill = skill_result.data

        updates: dict[str, Any] = {
            "execution_count": skill["execution_count"] + 1,
            "last_executed_at": datetime.now(timezone.utc).isoformat(),
        }

        if success:
            updates["success_count"] = skill["success_count"] + 1
        else:
            updates["failure_count"] = skill["failure_count"] + 1

        # Running average quality score
        prev_avg = skill.get("avg_quality_score") or quality_score
        prev_count = skill.get("execution_count", 0) or 1
        updates["avg_quality_score"] = (
            (prev_avg * prev_count + quality_score) / (prev_count + 1)
        )

        # Check trust graduation
        new_trust = self._check_graduation(skill, updates)
        if new_trust and new_trust != skill["trust_level"]:
            tenant_config = await self._get_tenant_config(skill["user_id"])
            max_auto = (tenant_config or {}).get("max_auto_trust_level", "MEDIUM")

            if _TRUST_ORDER.index(new_trust) <= _TRUST_ORDER.index(max_auto):
                updates["trust_level"] = new_trust
                if new_trust in ("MEDIUM", "HIGH"):
                    updates["status"] = "graduated"
            else:
                await self._request_approval(skill, "trust_graduation", new_trust)

        # Check for trust demotion (3 consecutive failures)
        if not success:
            try:
                recent = (
                    self._db.table("skill_audit_log")
                    .select("metadata")
                    .eq("skill_id", skill_id)
                    .order("timestamp", desc=True)
                    .limit(3)
                    .execute()
                )
                recent_failures = sum(
                    1
                    for r in (recent.data or [])
                    if (r.get("metadata") or {}).get("success") is False
                )
                if recent_failures >= 3:
                    current_idx = _TRUST_ORDER.index(skill["trust_level"])
                    if current_idx > 0:
                        updates["trust_level"] = _TRUST_ORDER[current_idx - 1]
                        logger.warning(
                            "Skill %s trust demoted to %s",
                            skill_id,
                            updates["trust_level"],
                        )
            except Exception:
                logger.warning("Failed to check demotion for %s", skill_id, exc_info=True)

        (
            self._db.table("aria_generated_skills")
            .update(updates)
            .eq("id", skill_id)
            .execute()
        )

    def _check_graduation(
        self, skill: dict[str, Any], updates: dict[str, Any]
    ) -> Optional[str]:
        """Check if skill qualifies for trust graduation."""
        total_success = updates.get("success_count", skill["success_count"])
        total_fail = updates.get("failure_count", skill["failure_count"])
        total = total_success + total_fail

        if total == 0:
            return None

        error_rate = total_fail / total

        if skill["trust_level"] == "LOW" and total_success >= 5 and total_fail == 0:
            return "MEDIUM"
        elif skill["trust_level"] == "MEDIUM" and total_success >= 20 and error_rate < 0.05:
            return "HIGH"

        return None

    async def _request_approval(
        self, skill: dict[str, Any], approval_type: str, requested_trust: str
    ) -> None:
        """Create approval queue entry for admin review."""
        try:
            self._db.table("skill_approval_queue").insert({
                "skill_id": skill["id"],
                "tenant_id": skill.get("tenant_id", ""),
                "requested_by": skill["user_id"],
                "approval_type": approval_type,
                "current_trust_level": skill["trust_level"],
                "requested_trust_level": requested_trust,
                "justification": (
                    f"Skill '{skill.get('display_name', skill['id'])}' has "
                    f"{skill['success_count']} successes with "
                    f"{skill['failure_count']} failures."
                ),
            }).execute()
        except Exception:
            logger.warning("Failed to create approval queue entry", exc_info=True)

    async def _get_tenant_config(self, user_id: str) -> dict[str, Any] | None:
        """Load tenant config for trust graduation limits."""
        try:
            profile_result = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if not profile_result.data or not profile_result.data.get("company_id"):
                return None

            config_result = (
                self._db.table("tenant_capability_config")
                .select("*")
                .eq("tenant_id", profile_result.data["company_id"])
                .limit(1)
                .maybe_single()
                .execute()
            )
            return config_result.data if config_result.data else None
        except Exception:
            logger.warning("Failed to load tenant config", exc_info=True)
            return None


class SkillHealthMonitor:
    """Monitors health of ARIA-generated skills. Runs as scheduled job.

    Checks error rate from skill_audit_log over last 7 days.
    >15% error rate → degraded (pulse signal generated)
    >50% error rate → broken (auto-disable, find replacement)
    """

    def __init__(self, db_client: Any, pulse_engine: Any = None) -> None:
        self._db = db_client
        self._pulse = pulse_engine

    async def check_all_active_skills(self) -> None:
        """Health check all active and graduated skills."""
        try:
            skills_result = (
                self._db.table("aria_generated_skills")
                .select("*")
                .in_("status", ["active", "graduated"])
                .execute()
            )
        except Exception:
            logger.exception("Failed to query active skills for health check")
            return

        for skill in skills_result.data or []:
            health = await self._assess_health(skill)

            try:
                (
                    self._db.table("aria_generated_skills")
                    .update({
                        "health_status": health["status"],
                        "error_rate_7d": health["error_rate_7d"],
                        "last_health_check": datetime.now(timezone.utc).isoformat(),
                    })
                    .eq("id", skill["id"])
                    .execute()
                )
            except Exception:
                logger.warning("Failed to update health for skill %s", skill["id"])

            if health["status"] == "degraded" and self._pulse:
                try:
                    await self._pulse.process_signal(
                        user_id=skill["user_id"],
                        signal={
                            "pulse_type": "skill_health",
                            "source": "skill_health_monitor",
                            "title": f"Skill '{skill['display_name']}' performance degraded",
                            "content": (
                                f"Error rate: {health['error_rate_7d']:.0%} (was <5%). "
                                f"I'm looking for alternatives or can rebuild this skill."
                            ),
                            "signal_category": "capability",
                        },
                    )
                except Exception:
                    logger.warning("Failed to send pulse for degraded skill %s", skill["id"])

            elif health["status"] == "broken":
                try:
                    (
                        self._db.table("aria_generated_skills")
                        .update({"status": "disabled"})
                        .eq("id", skill["id"])
                        .execute()
                    )
                except Exception:
                    logger.warning("Failed to disable broken skill %s", skill["id"])

    async def _assess_health(self, skill: dict[str, Any]) -> dict[str, Any]:
        """Assess skill health from recent execution data."""
        seven_days_ago = (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).isoformat()
        try:
            recent = (
                self._db.table("skill_audit_log")
                .select("metadata")
                .eq("skill_id", skill.get("skill_name", skill["id"]))
                .gte("timestamp", seven_days_ago)
                .execute()
            )
        except Exception:
            return {"status": "unknown", "error_rate_7d": 0}

        if not recent.data:
            return {"status": "unknown", "error_rate_7d": 0}

        total = len(recent.data)
        failures = sum(
            1
            for r in recent.data
            if not (r.get("metadata") or {}).get("success", True)
        )
        error_rate = failures / total if total > 0 else 0

        if error_rate > 0.5:
            return {"status": "broken", "error_rate_7d": error_rate}
        elif error_rate > 0.15:
            return {"status": "degraded", "error_rate_7d": error_rate}
        else:
            return {"status": "healthy", "error_rate_7d": error_rate}
