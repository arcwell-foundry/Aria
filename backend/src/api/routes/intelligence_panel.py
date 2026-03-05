"""Intelligence Panel API endpoint.

Returns contextual intelligence data for the right panel on the ARIA Chat page:
- Upcoming meetings (max 3, with EST times and relative dates)
- Recent market signals (max 3, by detected_at DESC)
- Quick stats (pending drafts, open tasks, battle cards, pipeline count)
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient
from src.models.intelligence_panel import (
    IntelligencePanelResponse,
    MeetingsSection,
    QuickStats,
    RecentSignal,
    SignalsSection,
    UpcomingMeeting,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intelligence-panel", tags=["intelligence-panel"])

EASTERN = ZoneInfo("America/New_York")


def _is_buffer_event(title: str | None) -> bool:
    """Check if an event is a buffer event that should be filtered out."""
    if not title:
        return False
    title_lower = title.lower()
    return "[buffer" in title_lower or "buffer]" in title_lower


def _format_time(dt: datetime) -> str:
    """Format datetime as 12-hour time string (e.g., '11:00 AM')."""
    return dt.strftime("%-I:%M %p")


def _format_relative_date(dt: datetime, now: datetime) -> str:
    """Format date as relative string: Today, Tomorrow, or 'Mar 10'."""
    dt_date = dt.date()
    now_date = now.date()

    if dt_date == now_date:
        return "Today"
    if dt_date == now_date + timedelta(days=1):
        return "Tomorrow"
    # Within 7 days: show "Mar 10" style
    return dt.strftime("%b %-d")


def _parse_timestamp(ts_str: str) -> datetime:
    """Parse a timestamp string to a timezone-aware datetime."""
    if ts_str.endswith("Z"):
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    if "+" in ts_str or ts_str.count("-") > 2:
        return datetime.fromisoformat(ts_str)
    return datetime.fromisoformat(ts_str).replace(tzinfo=UTC)


async def _get_upcoming_meetings(user_id: str, db: Any) -> tuple[list[UpcomingMeeting], int]:
    """Get upcoming meetings, filtering buffer events. Returns (top 3, total count)."""
    now = datetime.now(UTC)
    now_eastern = now.astimezone(EASTERN)

    result = (
        db.table("calendar_events")
        .select("title, start_time, attendees")
        .eq("user_id", user_id)
        .gte("start_time", now.isoformat())
        .order("start_time", desc=False)
        .limit(20)
        .execute()
    )

    meetings: list[UpcomingMeeting] = []
    total = 0

    for row in result.data or []:
        title = row.get("title")
        if _is_buffer_event(title):
            continue
        if not title:
            continue

        total += 1
        if len(meetings) >= 3:
            continue  # Keep counting total but don't add more

        start_str = row.get("start_time")
        if not start_str:
            continue

        try:
            start_dt = _parse_timestamp(start_str)
            start_eastern = start_dt.astimezone(EASTERN)

            attendees_raw = row.get("attendees") or []
            attendees = []
            if isinstance(attendees_raw, list):
                for a in attendees_raw:
                    if isinstance(a, dict):
                        attendees.append(a.get("email", ""))
                    elif isinstance(a, str):
                        attendees.append(a)

            meetings.append(
                UpcomingMeeting(
                    title=title,
                    time=_format_time(start_eastern),
                    date=_format_relative_date(start_eastern, now_eastern),
                    attendees=[a for a in attendees if a],
                )
            )
        except (ValueError, TypeError) as e:
            logger.warning("Failed to parse meeting time '%s': %s", start_str, e)
            continue

    return meetings, total


async def _get_recent_signals(user_id: str, db: Any) -> tuple[list[RecentSignal], int, int]:
    """Get recent signals. Returns (top 3, unread_count, total_count)."""
    # Get top 3 recent signals
    recent_result = (
        db.table("market_signals")
        .select("company_name, headline, signal_type, relevance_score")
        .eq("user_id", user_id)
        .order("detected_at", desc=True)
        .limit(3)
        .execute()
    )

    signals = [
        RecentSignal(
            company=row.get("company_name", "Unknown"),
            headline=row.get("headline", ""),
            type=row.get("signal_type", "unknown"),
            score=float(row.get("relevance_score", 0)),
        )
        for row in (recent_result.data or [])
    ]

    # Get total count
    total_result = (
        db.table("market_signals")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    total_count = total_result.count if total_result.count else 0

    # Get unread count
    unread_result = (
        db.table("market_signals")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .is_("read_at", "null")
        .execute()
    )
    unread_count = unread_result.count if unread_result.count else 0

    return signals, unread_count, total_count


async def _get_quick_stats(user_id: str, db: Any) -> QuickStats:
    """Get quick stats: pending drafts, open tasks, battle cards, pipeline count."""
    # Pending drafts
    drafts_result = (
        db.table("email_drafts")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "draft")
        .execute()
    )
    pending_drafts = drafts_result.count if drafts_result.count else 0

    # Open tasks (goals with active-ish status)
    tasks_result = (
        db.table("goals")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .not_.in_("status", ["complete", "completed", "failed", "cancelled"])
        .execute()
    )
    open_tasks = tasks_result.count if tasks_result.count else 0

    # Battle cards (global, no user_id filter)
    cards_result = (
        db.table("battle_cards")
        .select("id", count="exact")
        .execute()
    )
    battle_cards = cards_result.count if cards_result.count else 0

    return QuickStats(
        pending_drafts=pending_drafts,
        open_tasks=open_tasks,
        battle_cards=battle_cards,
        pipeline_count=0,
    )


@router.get("", response_model=IntelligencePanelResponse)
async def get_intelligence_panel(
    current_user: CurrentUser,
) -> IntelligencePanelResponse:
    """Get intelligence panel data for the current user.

    Returns meetings, signals, and quick stats for the right panel
    on the ARIA Chat page.
    """
    db = SupabaseClient.get_client()

    meetings, meeting_count = await _get_upcoming_meetings(current_user.id, db)
    signals, unread_count, total_count = await _get_recent_signals(current_user.id, db)
    quick_stats = await _get_quick_stats(current_user.id, db)

    logger.info(
        "Generated intelligence panel data",
        extra={
            "user_id": current_user.id,
            "meetings": len(meetings),
            "signals": len(signals),
        },
    )

    return IntelligencePanelResponse(
        meetings=MeetingsSection(upcoming=meetings, count=meeting_count),
        signals=SignalsSection(
            recent=signals,
            unread_count=unread_count,
            total_count=total_count,
        ),
        quick_stats=quick_stats,
    )
