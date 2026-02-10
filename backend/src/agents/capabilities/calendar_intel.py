"""Calendar Intelligence capability for OperatorAgent.

Provides calendar-aware intelligence for ARIA: fetching upcoming events via
Google Calendar OAuth, triggering pre-meeting brief generation based on
user-configured lead time, detecting scheduling patterns for productivity
insights, and prompting post-meeting debriefs.

Key responsibilities:
- Fetch upcoming events via Composio Google Calendar integration
- Trigger meeting brief generation N hours before a meeting
- Detect scheduling patterns (busiest days, preferred times, travel)
- Prompt for post-meeting debrief notes after meetings end
"""

import logging
import time
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.db.supabase import SupabaseClient
from src.integrations.deep_sync_domain import CalendarEvent
from src.integrations.oauth import get_oauth_client

logger = logging.getLogger(__name__)


# ── Default configuration ─────────────────────────────────────────────────

_DEFAULT_LEAD_HOURS = 24
_DEFAULT_LOOKAHEAD_HOURS = 48
_PATTERN_ANALYSIS_DAYS = 30


class CalendarIntelligenceCapability(BaseCapability):
    """Calendar intelligence: upcoming events, meeting prep, patterns, debriefs.

    Wraps the Composio Google Calendar integration to provide:
    - Upcoming event fetching with configurable lookahead
    - Automatic meeting brief generation triggered by lead-time preferences
    - Calendar pattern detection for productivity coaching
    - Post-meeting debrief creation for knowledge capture

    Designed for OperatorAgent (scheduling automation and calendar ops).
    """

    capability_name: str = "calendar-intelligence"
    agent_types: list[str] = ["OperatorAgent"]
    oauth_scopes: list[str] = ["google_calendar_readonly"]
    data_classes: list[str] = ["INTERNAL"]

    # ── BaseCapability abstract interface ──────────────────────────────────

    async def can_handle(self, task: dict[str, Any]) -> float:
        """Return confidence for calendar-intelligence tasks."""
        task_type = task.get("type", "")
        if task_type in {
            "get_upcoming",
            "trigger_meeting_prep",
            "detect_scheduling_patterns",
            "post_meeting_trigger",
        }:
            return 0.95
        if "calendar" in task_type.lower() or "meeting" in task_type.lower():
            return 0.6
        return 0.0

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any],  # noqa: ARG002
    ) -> CapabilityResult:
        """Route to the correct method based on task type."""
        start = time.monotonic()
        user_id = self._user_context.user_id
        task_type = task.get("type", "")

        try:
            if task_type == "get_upcoming":
                hours = int(task.get("hours", _DEFAULT_LOOKAHEAD_HOURS))
                events = await self.get_upcoming(user_id, hours=hours)
                data: dict[str, Any] = {
                    "events": [self._event_to_dict(e) for e in events],
                    "count": len(events),
                    "lookahead_hours": hours,
                }

            elif task_type == "trigger_meeting_prep":
                event_data = task.get("event", {})
                event = self._dict_to_event(event_data)
                await self.trigger_meeting_prep(event)
                data = {
                    "event_id": event.external_id,
                    "brief_status": "generating",
                }

            elif task_type == "detect_scheduling_patterns":
                patterns = await self.detect_scheduling_patterns(user_id)
                data = patterns

            elif task_type == "post_meeting_trigger":
                event_data = task.get("event", {})
                event = self._dict_to_event(event_data)
                await self.post_meeting_trigger(event)
                data = {
                    "event_id": event.external_id,
                    "debrief_status": "pending",
                }

            else:
                return CapabilityResult(
                    success=False,
                    error=f"Unknown task type: {task_type}",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )

            elapsed = int((time.monotonic() - start) * 1000)
            return CapabilityResult(success=True, data=data, execution_time_ms=elapsed)

        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.exception(
                "Calendar intelligence task failed",
                extra={"user_id": user_id, "task_type": task_type},
            )
            return CapabilityResult(
                success=False,
                error=str(exc),
                execution_time_ms=elapsed,
            )

    def get_data_classes_accessed(self) -> list[str]:
        """Calendar data is internal (not confidential or regulated)."""
        return ["internal"]

    # ── Public methods ─────────────────────────────────────────────────────

    async def get_upcoming(
        self,
        user_id: str,
        *,
        hours: int = _DEFAULT_LOOKAHEAD_HOURS,
    ) -> list[CalendarEvent]:
        """Fetch upcoming calendar events via Google Calendar API.

        Args:
            user_id: Authenticated user UUID.
            hours: How many hours ahead to look (default 48).

        Returns:
            List of CalendarEvent objects sorted by start_time.
        """
        connection_id = await self._get_calendar_connection(user_id)
        if not connection_id:
            logger.info(
                "No Google Calendar integration for user",
                extra={"user_id": user_id},
            )
            return []

        now = datetime.now(UTC)
        time_max = now + timedelta(hours=hours)

        oauth_client = get_oauth_client()
        try:
            result = await oauth_client.execute_action(
                connection_id=connection_id,
                action="list_events",
                params={
                    "timeMin": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "timeMax": time_max.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to fetch calendar events",
                extra={"user_id": user_id, "error": str(exc)},
            )
            return []

        raw_events = result.get("data", [])
        if not isinstance(raw_events, list):
            raw_events = []

        events: list[CalendarEvent] = []
        for raw in raw_events:
            try:
                events.append(self._parse_google_event(raw))
            except Exception:
                logger.warning(
                    "Failed to parse calendar event",
                    extra={"event": raw},
                    exc_info=True,
                )

        events.sort(key=lambda e: e.start_time)

        await self.log_activity(
            activity_type="calendar_fetch",
            title="Fetched upcoming calendar events",
            description=f"Retrieved {len(events)} events in the next {hours} hours",
            confidence=0.9,
            metadata={"event_count": len(events), "lookahead_hours": hours},
        )

        return events

    async def trigger_meeting_prep(self, event: CalendarEvent) -> None:
        """Trigger meeting brief generation for an upcoming event.

        Checks the user's configured ``meeting_brief_lead_hours`` preference
        to determine if a brief should be generated now. If the meeting is
        within the lead window and no brief exists yet, creates a ``pending``
        entry in the ``meeting_briefs`` table.

        Args:
            event: The calendar event to prepare for.
        """
        user_id = self._user_context.user_id
        client = SupabaseClient.get_client()

        # Check if brief already exists
        existing = (
            client.table("meeting_briefs")
            .select("id, status")
            .eq("user_id", user_id)
            .eq("calendar_event_id", event.external_id)
            .maybe_single()
            .execute()
        )
        if existing.data:
            logger.debug(
                "Meeting brief already exists",
                extra={
                    "user_id": user_id,
                    "event_id": event.external_id,
                    "status": existing.data.get("status"),
                },
            )
            return

        # Check lead-time preference
        lead_hours = await self._get_meeting_lead_hours(user_id)
        now = datetime.now(UTC)
        hours_until = (event.start_time - now).total_seconds() / 3600

        if hours_until > lead_hours:
            logger.debug(
                "Meeting too far out for prep",
                extra={
                    "event_id": event.external_id,
                    "hours_until": round(hours_until, 1),
                    "lead_hours": lead_hours,
                },
            )
            return

        # Create pending brief
        brief_id = str(uuid.uuid4())
        brief_row = {
            "id": brief_id,
            "user_id": user_id,
            "calendar_event_id": event.external_id,
            "meeting_title": event.title,
            "meeting_time": event.start_time.isoformat(),
            "attendees": event.attendees,
            "status": "pending",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        client.table("meeting_briefs").insert(brief_row).execute()

        await self.log_activity(
            activity_type="meeting_prep_triggered",
            title=f"Meeting prep queued: {event.title}",
            description=(
                f"Created pending brief for '{event.title}' at "
                f"{event.start_time.strftime('%Y-%m-%d %H:%M')} "
                f"with {len(event.attendees)} attendees"
            ),
            confidence=0.9,
            metadata={
                "brief_id": brief_id,
                "event_id": event.external_id,
                "meeting_time": event.start_time.isoformat(),
                "attendee_count": len(event.attendees),
            },
        )

        logger.info(
            "Meeting brief created",
            extra={
                "user_id": user_id,
                "brief_id": brief_id,
                "event_id": event.external_id,
                "meeting_time": event.start_time.isoformat(),
            },
        )

    async def detect_scheduling_patterns(self, user_id: str) -> dict[str, Any]:
        """Analyze calendar patterns over the past 30 days.

        Examines historical events to identify:
        - Busiest days of the week
        - Preferred meeting time slots
        - Average meetings per day
        - Travel indicators (location-based events)
        - Meeting duration distribution

        Args:
            user_id: Authenticated user UUID.

        Returns:
            Dictionary with pattern analysis results.
        """
        connection_id = await self._get_calendar_connection(user_id)
        if not connection_id:
            return {"error": "No Google Calendar integration found"}

        now = datetime.now(UTC)
        time_min = now - timedelta(days=_PATTERN_ANALYSIS_DAYS)

        oauth_client = get_oauth_client()
        try:
            result = await oauth_client.execute_action(
                connection_id=connection_id,
                action="list_events",
                params={
                    "timeMin": time_min.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "timeMax": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to fetch historical calendar events",
                extra={"user_id": user_id, "error": str(exc)},
            )
            return {"error": f"Failed to fetch calendar data: {exc}"}

        raw_events = result.get("data", [])
        if not isinstance(raw_events, list):
            raw_events = []

        events: list[CalendarEvent] = []
        for raw in raw_events:
            try:
                events.append(self._parse_google_event(raw))
            except Exception:
                continue

        if not events:
            return {
                "total_events": 0,
                "analysis_period_days": _PATTERN_ANALYSIS_DAYS,
                "message": "No events found in analysis period",
            }

        # Analyze patterns
        day_counts: Counter[int] = Counter()
        hour_counts: Counter[int] = Counter()
        durations_minutes: list[float] = []
        locations: list[str] = []
        dates_with_meetings: set[str] = set()

        for event in events:
            day_counts[event.start_time.weekday()] += 1
            hour_counts[event.start_time.hour] += 1
            dates_with_meetings.add(event.start_time.strftime("%Y-%m-%d"))

            duration = (event.end_time - event.start_time).total_seconds() / 60
            if 0 < duration < 480:  # Ignore all-day or zero-duration
                durations_minutes.append(duration)

            if event.location:
                locations.append(event.location)

        day_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        busiest_days = [
            {"day": day_names[day], "count": count} for day, count in day_counts.most_common(3)
        ]

        # Group hours into time slots
        morning = sum(hour_counts[h] for h in range(6, 12))
        afternoon = sum(hour_counts[h] for h in range(12, 17))
        evening = sum(hour_counts[h] for h in range(17, 22))
        preferred_slots = sorted(
            [
                {"slot": "morning (6-12)", "count": morning},
                {"slot": "afternoon (12-17)", "count": afternoon},
                {"slot": "evening (17-22)", "count": evening},
            ],
            key=lambda s: s["count"],
            reverse=True,
        )

        avg_duration = (
            round(sum(durations_minutes) / len(durations_minutes), 1) if durations_minutes else 0.0
        )
        avg_meetings_per_day = (
            round(len(events) / len(dates_with_meetings), 1) if dates_with_meetings else 0.0
        )

        # Detect travel patterns: events with physical locations
        travel_events = [loc for loc in locations if loc and not loc.startswith("http")]
        unique_locations = list(set(travel_events))

        patterns = {
            "total_events": len(events),
            "analysis_period_days": _PATTERN_ANALYSIS_DAYS,
            "avg_meetings_per_day": avg_meetings_per_day,
            "avg_duration_minutes": avg_duration,
            "busiest_days": busiest_days,
            "preferred_time_slots": preferred_slots,
            "travel_patterns": {
                "events_with_location": len(travel_events),
                "unique_locations": unique_locations[:10],
            },
        }

        await self.log_activity(
            activity_type="scheduling_patterns_analyzed",
            title="Calendar patterns analyzed",
            description=(
                f"Analyzed {len(events)} events over {_PATTERN_ANALYSIS_DAYS} days. "
                f"Avg {avg_meetings_per_day} meetings/day, "
                f"avg {avg_duration} min duration."
            ),
            confidence=0.85,
            metadata=patterns,
        )

        return patterns

    async def post_meeting_trigger(self, event: CalendarEvent) -> None:
        """Create a meeting debrief entry after a meeting ends.

        Inserts a ``meeting_debriefs`` row with status prompting the user
        for notes. Links to an existing lead_memory if an attendee matches.

        Args:
            event: The calendar event that just ended.
        """
        user_id = self._user_context.user_id
        client = SupabaseClient.get_client()

        # Check if debrief already exists
        existing = (
            client.table("meeting_debriefs")
            .select("id")
            .eq("user_id", user_id)
            .eq("meeting_id", event.external_id)
            .maybe_single()
            .execute()
        )
        if existing.data:
            logger.debug(
                "Meeting debrief already exists",
                extra={"user_id": user_id, "event_id": event.external_id},
            )
            return

        # Try to link to a lead_memory via attendee email
        linked_lead_id = await self._find_linked_lead(user_id, event.attendees)

        now = datetime.now(UTC)
        debrief_id = str(uuid.uuid4())
        debrief_row = {
            "id": debrief_id,
            "user_id": user_id,
            "meeting_id": event.external_id,
            "meeting_title": event.title,
            "meeting_time": event.start_time.isoformat(),
            "outcome": "neutral",
            "follow_up_needed": False,
            "created_at": now.isoformat(),
        }
        if linked_lead_id:
            debrief_row["linked_lead_id"] = linked_lead_id

        client.table("meeting_debriefs").insert(debrief_row).execute()

        await self.log_activity(
            activity_type="post_meeting_debrief",
            title=f"Debrief created: {event.title}",
            description=(
                f"Post-meeting debrief created for '{event.title}'. Awaiting notes from user."
            ),
            confidence=0.9,
            related_entity_type="lead" if linked_lead_id else None,
            related_entity_id=linked_lead_id,
            metadata={
                "debrief_id": debrief_id,
                "event_id": event.external_id,
                "meeting_time": event.start_time.isoformat(),
                "linked_lead_id": linked_lead_id,
            },
        )

        logger.info(
            "Meeting debrief created",
            extra={
                "user_id": user_id,
                "debrief_id": debrief_id,
                "event_id": event.external_id,
                "linked_lead_id": linked_lead_id,
            },
        )

    # ── Scheduler integration ──────────────────────────────────────────────

    async def check_upcoming_meetings(self) -> int:
        """Cron-callable method: check upcoming meetings and trigger briefs.

        Fetches upcoming events within the user's configured lead window
        and triggers meeting prep for any that don't yet have a brief.
        Intended to be called by the daily scheduler.

        Returns:
            Number of briefs triggered.
        """
        user_id = self._user_context.user_id
        lead_hours = await self._get_meeting_lead_hours(user_id)

        events = await self.get_upcoming(user_id, hours=lead_hours)
        briefs_triggered = 0

        for event in events:
            try:
                await self.trigger_meeting_prep(event)
                briefs_triggered += 1
            except Exception:
                logger.warning(
                    "Failed to trigger meeting prep",
                    extra={"event_id": event.external_id},
                    exc_info=True,
                )

        return briefs_triggered

    # ── Private helpers ────────────────────────────────────────────────────

    async def _get_calendar_connection(self, user_id: str) -> str | None:
        """Look up the user's active Google Calendar integration.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            Composio connection_id string, or None if not connected.
        """
        client = SupabaseClient.get_client()
        try:
            resp = (
                client.table("user_integrations")
                .select("*")
                .eq("user_id", user_id)
                .eq("integration_type", "google_calendar")
                .eq("status", "active")
                .maybe_single()
                .execute()
            )
            if resp.data and resp.data.get("composio_connection_id"):
                return str(resp.data["composio_connection_id"])
        except Exception:
            logger.warning(
                "Failed to lookup calendar integration",
                extra={"user_id": user_id},
                exc_info=True,
            )
        return None

    async def _get_meeting_lead_hours(self, user_id: str) -> int:
        """Fetch the user's meeting_brief_lead_hours preference.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            Lead hours (int), defaults to 24 if not configured.
        """
        client = SupabaseClient.get_client()
        try:
            resp = (
                client.table("user_preferences")
                .select("meeting_brief_lead_hours")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if resp.data:
                return int(resp.data.get("meeting_brief_lead_hours", _DEFAULT_LEAD_HOURS))
        except Exception:
            logger.warning(
                "Failed to fetch meeting lead hours preference",
                extra={"user_id": user_id},
                exc_info=True,
            )
        return _DEFAULT_LEAD_HOURS

    async def _find_linked_lead(
        self,
        user_id: str,
        attendee_emails: list[str],
    ) -> str | None:
        """Try to match attendee emails to an existing lead_memory.

        Args:
            user_id: Authenticated user UUID.
            attendee_emails: List of attendee email addresses.

        Returns:
            lead_memory UUID if a match is found, else None.
        """
        if not attendee_emails:
            return None

        client = SupabaseClient.get_client()
        for email in attendee_emails:
            try:
                resp = (
                    client.table("lead_memories")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("primary_email", email)
                    .maybe_single()
                    .execute()
                )
                if resp.data:
                    return str(resp.data["id"])
            except Exception:
                continue
        return None

    @staticmethod
    def _parse_google_event(raw: dict[str, Any]) -> CalendarEvent:
        """Parse a raw Google Calendar event into a CalendarEvent.

        Args:
            raw: Raw event dict from Google Calendar API.

        Returns:
            CalendarEvent domain object.
        """
        external_id = raw.get("id", "")
        title = raw.get("summary", "No Title")

        start_obj = raw.get("start", {})
        end_obj = raw.get("end", {})

        start_str = start_obj.get("dateTime") or start_obj.get("date", "")
        end_str = end_obj.get("dateTime") or end_obj.get("date", "")

        start_time = _parse_datetime(start_str)
        end_time = _parse_datetime(end_str)

        attendees_data = raw.get("attendees", [])
        attendees = [a["email"] for a in attendees_data if a.get("email")]

        return CalendarEvent(
            external_id=external_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            description=raw.get("description"),
            location=raw.get("location"),
            data=raw,
        )

    @staticmethod
    def _event_to_dict(event: CalendarEvent) -> dict[str, Any]:
        """Serialise a CalendarEvent to a JSON-friendly dict."""
        return {
            "external_id": event.external_id,
            "title": event.title,
            "start_time": event.start_time.isoformat(),
            "end_time": event.end_time.isoformat(),
            "attendees": event.attendees,
            "description": event.description,
            "location": event.location,
            "is_external": event.is_external,
        }

    @staticmethod
    def _dict_to_event(data: dict[str, Any]) -> CalendarEvent:
        """Deserialise a dict back into a CalendarEvent."""
        return CalendarEvent(
            external_id=data.get("external_id", data.get("id", "")),
            title=data.get("title", ""),
            start_time=_parse_datetime(data.get("start_time", "")),
            end_time=_parse_datetime(data.get("end_time", "")),
            attendees=data.get("attendees", []),
            description=data.get("description"),
            location=data.get("location"),
            is_external=data.get("is_external", False),
        )


# ── Module-level helpers ──────────────────────────────────────────────────


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO-ish datetime string into a timezone-aware datetime.

    Handles Google Calendar's format variants including the ``Z`` suffix
    and date-only strings (all-day events).

    Args:
        value: ISO datetime string (e.g. ``"2026-02-10T14:00:00Z"``).

    Returns:
        Timezone-aware datetime in UTC.
    """
    if not value:
        return datetime.now(UTC)

    # Handle Z suffix
    cleaned = value.replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        # Date-only (all-day event)
        try:
            dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            return datetime.now(UTC)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    return dt
