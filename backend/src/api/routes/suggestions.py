"""Context-aware suggestion chips API endpoint.

Returns contextual quick actions based on user's current state:
- Upcoming meetings within 4 hours
- Unread market signals from last 7 days
- Pending email drafts
- Open tasks/goals
- Default fallbacks
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter

from src.api.deps import CurrentUser
from src.db.supabase import SupabaseClient
from src.models.suggestions import SuggestionChip, SuggestionsResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/suggestions", tags=["suggestions"])

# Default fallback suggestions (used when contextual suggestions < 4)
DEFAULT_SUGGESTIONS = [
    SuggestionChip(text="What's new in my market?", action="What's new in my market?"),
    SuggestionChip(text="Show my pipeline", action="Show my pipeline"),
    SuggestionChip(text="Draft an email", action="Help me draft an email"),
]


def _format_time_12h(dt: datetime) -> str:
    """Format datetime as lowercase 12-hour time (e.g., '11am', '2:30pm')."""
    hour = dt.hour
    minute = dt.minute

    # Determine AM/PM
    period = "am" if hour < 12 else "pm"

    # Convert to 12-hour format
    hour_12 = hour % 12
    if hour_12 == 0:
        hour_12 = 12

    # Format with optional minutes
    if minute == 0:
        return f"{hour_12}{period}"
    return f"{hour_12}:{minute:02d}{period}"


def _is_buffer_event(title: str | None) -> bool:
    """Check if an event is a buffer event that should be filtered out."""
    if not title:
        return False
    title_lower = title.lower()
    return "[buffer" in title_lower or "buffer]" in title_lower


async def _get_meeting_suggestion(user_id: str, db: Any) -> SuggestionChip | None:
    """Get suggestion for upcoming meeting within 4 hours."""
    now = datetime.now(UTC)
    four_hours_later = now + timedelta(hours=4)

    result = (
        db.table("calendar_events")
        .select("id, title, start_time")
        .eq("user_id", user_id)
        .gte("start_time", now.isoformat())
        .lte("start_time", four_hours_later.isoformat())
        .order("start_time", desc=False)
        .limit(10)
        .execute()
    )

    if not result.data:
        return None

    # Find first non-buffer event
    for event in result.data:
        title = event.get("title")
        if _is_buffer_event(title):
            continue

        start_time_str = event.get("start_time")
        if not start_time_str or not title:
            continue

        # Parse the timestamp
        try:
            # Handle both ISO format with and without timezone
            if start_time_str.endswith("Z"):
                start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
            elif "+" in start_time_str or start_time_str.count("-") > 2:
                start_time = datetime.fromisoformat(start_time_str)
            else:
                # Assume UTC if no timezone
                start_time = datetime.fromisoformat(start_time_str).replace(tzinfo=UTC)

            # Convert to Eastern time for display
            from zoneinfo import ZoneInfo
            eastern = ZoneInfo("America/New_York")
            start_time_local = start_time.astimezone(eastern)
            time_str = _format_time_12h(start_time_local)

            # Truncate title if too long
            display_title = title[:30] + "..." if len(title) > 30 else title

            return SuggestionChip(
                text=f"Prep for {time_str} {display_title}",
                action=f"Help me prepare for my {time_str} meeting with {title}",
            )
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse start_time '{start_time_str}': {e}")
            continue

    return None


async def _get_signals_suggestion(user_id: str, db: Any) -> SuggestionChip | None:
    """Get suggestion for unread market signals from last 7 days."""
    seven_days_ago = datetime.now(UTC) - timedelta(days=7)

    result = (
        db.table("market_signals")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .is_("read_at", "null")
        .gte("detected_at", seven_days_ago.isoformat())
        .execute()
    )

    count = result.count if result.count else 0
    if count == 0:
        return None

    return SuggestionChip(
        text=f"Review {count} new signal{'s' if count != 1 else ''}",
        action="Show me the latest market signals",
    )


async def _get_drafts_suggestion(user_id: str, db: Any) -> SuggestionChip | None:
    """Get suggestion for pending email drafts."""
    result = (
        db.table("email_drafts")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "draft")
        .execute()
    )

    count = result.count if result.count else 0
    if count == 0:
        return None

    return SuggestionChip(
        text=f"{count} draft{'s' if count != 1 else ''} waiting",
        action="Show me my pending email drafts",
    )


async def _get_tasks_suggestion(user_id: str, db: Any) -> SuggestionChip | None:
    """Get suggestion for open tasks/goals."""
    # Goals with status NOT IN complete/failed/cancelled
    result = (
        db.table("goals")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .not_.in_("status", ["complete", "completed", "failed", "cancelled"])
        .execute()
    )

    count = result.count if result.count else 0
    if count == 0:
        return None

    return SuggestionChip(
        text=f"{count} open task{'s' if count != 1 else ''}",
        action="What tasks need my attention?",
    )


@router.get("", response_model=SuggestionsResponse)
async def get_suggestions(
    current_user: CurrentUser,
) -> SuggestionsResponse:
    """Get context-aware suggestion chips for the current user.

    Returns up to 4 suggestions based on the user's current state:
    1. Upcoming meeting within 4 hours (if any)
    2. Unread market signals from last 7 days (if any)
    3. Pending email drafts (if any)
    4. Open tasks/goals (if any)
    5. Default fallbacks to fill remaining slots

    Returns:
        SuggestionsResponse with up to 4 suggestion chips.
    """
    db = SupabaseClient.get_client()
    suggestions: list[SuggestionChip] = []

    # Priority 1: Upcoming meeting
    meeting_suggestion = await _get_meeting_suggestion(current_user.id, db)
    if meeting_suggestion:
        suggestions.append(meeting_suggestion)

    # Priority 2: Unread signals
    signals_suggestion = await _get_signals_suggestion(current_user.id, db)
    if signals_suggestion:
        suggestions.append(signals_suggestion)

    # Priority 3: Pending drafts
    drafts_suggestion = await _get_drafts_suggestion(current_user.id, db)
    if drafts_suggestion:
        suggestions.append(drafts_suggestion)

    # Priority 4: Open tasks
    tasks_suggestion = await _get_tasks_suggestion(current_user.id, db)
    if tasks_suggestion:
        suggestions.append(tasks_suggestion)

    # Fill remaining slots with defaults
    for default in DEFAULT_SUGGESTIONS:
        if len(suggestions) >= 4:
            break
        suggestions.append(default)

    logger.info(
        "Generated suggestions for user",
        extra={"user_id": current_user.id, "count": len(suggestions)},
    )

    return SuggestionsResponse(suggestions=suggestions[:4])
