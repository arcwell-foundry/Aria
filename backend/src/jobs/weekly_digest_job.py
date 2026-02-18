"""Proactive weekly digest generation job (Task i).

Runs Monday at 7:00 AM. Generates an LLM-synthesized weekly summary
for each active user, stored in ``weekly_digests``. Routed as MEDIUM
priority. If video briefing is enabled, creates a Tavus session.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.core.business_hours import get_active_user_ids, get_user_timezone
from src.db.supabase import SupabaseClient
from src.services.proactive_router import InsightCategory, InsightPriority, ProactiveRouter

logger = logging.getLogger(__name__)


async def run_weekly_digest_job() -> dict[str, Any]:
    """Generate weekly digests for all active users.

    For each user (timezone-aware, Monday morning):
    1. Check if digest for this week already exists (idempotent)
    2. Gather week stats: activities, goals, signals, health changes, email stats
    3. LLM synthesize: executive_summary, wins[], risks[], recommendations
    4. Store in weekly_digests
    5. Route via ProactiveRouter (MEDIUM)
    6. If video_briefing_enabled, create Tavus briefing session

    Returns:
        Summary dict with generation statistics.
    """
    stats: dict[str, Any] = {
        "users_processed": 0,
        "digests_generated": 0,
        "digests_skipped_existing": 0,
        "digests_skipped_not_monday": 0,
        "video_sessions_created": 0,
        "errors": 0,
    }

    db = SupabaseClient.get_client()
    router = ProactiveRouter()
    user_ids = get_active_user_ids()

    logger.info("Weekly digest job: processing %d users", len(user_ids))

    for user_id in user_ids:
        try:
            stats["users_processed"] += 1

            # Check if it's Monday morning in user's timezone
            tz_str = get_user_timezone(user_id)
            try:
                tz = ZoneInfo(tz_str)
            except (KeyError, ValueError):
                tz = ZoneInfo("UTC")

            local_now = datetime.now(tz)
            if local_now.weekday() != 0 or local_now.hour < 7:
                stats["digests_skipped_not_monday"] += 1
                continue

            # Calculate week_start (Monday of this week)
            week_start = local_now.date() - timedelta(days=local_now.weekday())

            # Idempotency check
            existing = (
                db.table("weekly_digests")
                .select("id")
                .eq("user_id", user_id)
                .eq("week_start", week_start.isoformat())
                .limit(1)
                .execute()
            )
            if existing.data:
                stats["digests_skipped_existing"] += 1
                continue

            # Gather week stats
            week_data = await _gather_week_stats(db, user_id, week_start)

            # LLM synthesize
            digest = await _synthesize_digest(week_data)

            # Store
            db.table("weekly_digests").insert(
                {
                    "user_id": user_id,
                    "week_start": week_start.isoformat(),
                    "content": week_data,
                    "executive_summary": digest["executive_summary"],
                    "wins": digest["wins"],
                    "risks": digest["risks"],
                    "stats": digest["stats"],
                }
            ).execute()

            stats["digests_generated"] += 1

            # Route as MEDIUM
            await router.route(
                user_id=user_id,
                priority=InsightPriority.MEDIUM,
                category=InsightCategory.WEEKLY_DIGEST,
                title="Weekly Digest Ready",
                message=digest["executive_summary"],
                link="/briefing",
                metadata={
                    "week_start": week_start.isoformat(),
                    "wins_count": len(digest["wins"]),
                    "risks_count": len(digest["risks"]),
                },
            )

            # Video briefing if enabled
            try:
                prefs = (
                    db.table("user_preferences")
                    .select("video_briefing_enabled")
                    .eq("user_id", user_id)
                    .maybe_single()
                    .execute()
                )
                if prefs and prefs.data and prefs.data.get("video_briefing_enabled"):
                    from src.integrations.tavus_persona import SessionType
                    from src.services.video_service import VideoSessionService

                    await VideoSessionService.create_session(
                        user_id=user_id,
                        session_type=SessionType.BRIEFING,
                        context=digest["executive_summary"],
                        custom_greeting="Good morning! I have your weekly digest ready. Let me walk you through the highlights.",
                    )
                    stats["video_sessions_created"] += 1
            except Exception:
                logger.warning(
                    "Video briefing creation failed for weekly digest",
                    extra={"user_id": user_id},
                    exc_info=True,
                )

        except Exception:
            logger.warning(
                "Weekly digest generation failed for user %s",
                user_id,
                exc_info=True,
            )
            stats["errors"] += 1

    logger.info("Weekly digest job complete", extra=stats)
    return stats


async def _gather_week_stats(
    db: Any,
    user_id: str,
    week_start: date,
) -> dict[str, Any]:
    """Gather activity data for the past week."""
    week_end = week_start + timedelta(days=7)
    start_iso = datetime(
        week_start.year, week_start.month, week_start.day, tzinfo=ZoneInfo("UTC")
    ).isoformat()
    end_iso = datetime(
        week_end.year, week_end.month, week_end.day, tzinfo=ZoneInfo("UTC")
    ).isoformat()

    data: dict[str, Any] = {
        "activities": [],
        "goals_completed": [],
        "goals_progressed": [],
        "signals_detected": 0,
        "health_changes": [],
        "email_stats": {},
    }

    # Activity summary
    try:
        activity_result = (
            db.table("aria_activity")
            .select("activity_type, title")
            .eq("user_id", user_id)
            .gte("created_at", start_iso)
            .lt("created_at", end_iso)
            .limit(100)
            .execute()
        )
        data["activities"] = activity_result.data or []
    except Exception:
        pass

    # Goals
    try:
        goals_result = (
            db.table("goals")
            .select("id, title, status, progress")
            .eq("user_id", user_id)
            .gte("updated_at", start_iso)
            .lt("updated_at", end_iso)
            .execute()
        )
        for goal in goals_result.data or []:
            if goal.get("status") == "completed":
                data["goals_completed"].append(goal["title"])
            elif goal.get("progress", 0) > 0:
                data["goals_progressed"].append(goal["title"])
    except Exception:
        pass

    # Signals
    try:
        signals_result = (
            db.table("intelligence_signals")
            .select("id")
            .eq("user_id", user_id)
            .gte("created_at", start_iso)
            .lt("created_at", end_iso)
            .execute()
        )
        data["signals_detected"] = len(signals_result.data or [])
    except Exception:
        pass

    # Health score changes
    try:
        health_result = (
            db.table("health_score_history")
            .select("lead_memory_id, score, previous_score")
            .eq("user_id", user_id)
            .gte("created_at", start_iso)
            .lt("created_at", end_iso)
            .execute()
        )
        data["health_changes"] = health_result.data or []
    except Exception:
        pass

    # Email stats
    try:
        email_result = (
            db.table("email_processing_runs")
            .select("emails_processed, drafts_generated")
            .eq("user_id", user_id)
            .gte("created_at", start_iso)
            .lt("created_at", end_iso)
            .execute()
        )
        runs = email_result.data or []
        data["email_stats"] = {
            "runs": len(runs),
            "emails_processed": sum(r.get("emails_processed", 0) for r in runs),
            "drafts_generated": sum(r.get("drafts_generated", 0) for r in runs),
        }
    except Exception:
        pass

    return data


async def _synthesize_digest(week_data: dict[str, Any]) -> dict[str, Any]:
    """Use LLM to synthesize a weekly digest from raw data."""
    try:
        from src.core.llm import LLMClient

        llm = LLMClient()

        activities_count = len(week_data.get("activities", []))
        goals_completed = week_data.get("goals_completed", [])
        goals_progressed = week_data.get("goals_progressed", [])
        signals = week_data.get("signals_detected", 0)
        email_stats = week_data.get("email_stats", {})

        prompt = f"""Generate a concise weekly business digest summary. Include:
1. An executive_summary (2-3 sentences)
2. Up to 3 wins (positive highlights)
3. Up to 3 risks (areas needing attention)
4. Key stats

Data for the week:
- {activities_count} activities recorded
- Goals completed: {', '.join(goals_completed) if goals_completed else 'None'}
- Goals progressed: {', '.join(goals_progressed) if goals_progressed else 'None'}
- {signals} market signals detected
- Emails processed: {email_stats.get('emails_processed', 0)}
- Drafts generated: {email_stats.get('drafts_generated', 0)}

Respond in this exact JSON format:
{{"executive_summary": "...", "wins": ["..."], "risks": ["..."], "stats": {{"activities": N, "goals_completed": N, "signals": N}}}}
"""

        response = await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )

        # Parse LLM response
        import json

        # Try to extract JSON from the response
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])

    except Exception:
        logger.warning("LLM digest synthesis failed, using fallback", exc_info=True)

    # Fallback
    return {
        "executive_summary": f"This week saw {len(week_data.get('activities', []))} activities across your pipeline.",
        "wins": week_data.get("goals_completed", [])[:3],
        "risks": [],
        "stats": {
            "activities": len(week_data.get("activities", [])),
            "goals_completed": len(week_data.get("goals_completed", [])),
            "signals": week_data.get("signals_detected", 0),
        },
    }
