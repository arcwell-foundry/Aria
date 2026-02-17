"""Tavus webhook endpoint for handling video session callbacks.

This module implements the webhook handler for Tavus API callbacks,
enabling real-time session tracking, transcript capture, perception
analysis (Raven-1), and lead intelligence enrichment.

Supported event types:
- system.replica_joined: Session became active
- system.shutdown: Session ended
- application.transcription_ready: Full transcript available
- application.perception_analysis: User engagement/emotion data
- conversation.utterance: Real-time utterance
- conversation.tool_call: Tool invocation during conversation
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.integrations.tavus_tool_executor import ToolResult

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from src.core.config import settings
from src.db.supabase import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Tool execution timeout in seconds
TOOL_EXECUTION_TIMEOUT = 15

# Per-conversation locks for sequential tool execution
_conversation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models for Webhook Payloads
# ─────────────────────────────────────────────────────────────────────────────


class TavusWebhookPayload(BaseModel):
    """Base model for all Tavus webhook payloads."""

    event_type: str = Field(..., description="The type of webhook event")
    conversation_id: str = Field(..., description="Tavus conversation ID")
    timestamp: str = Field(..., description="ISO 8601 timestamp of the event")


class ReplicaJoinedPayload(TavusWebhookPayload):
    """Payload for system.replica_joined event."""

    event_type: str = "system.replica_joined"


class ShutdownPayload(TavusWebhookPayload):
    """Payload for system.shutdown event."""

    event_type: str = "system.shutdown"
    shutdown_reason: str | None = Field(
        None, description="Reason for session shutdown"
    )


class TranscriptEntry(BaseModel):
    """Single transcript entry from Tavus."""

    speaker: str = Field(..., description="Speaker identifier (aria or user)")
    content: str = Field(..., description="Transcript text content")
    timestamp_ms: int = Field(0, description="Timestamp in milliseconds")


class TranscriptionPayload(TavusWebhookPayload):
    """Payload for application.transcription_ready event."""

    event_type: str = "application.transcription_ready"
    transcript: list[TranscriptEntry] = Field(
        default_factory=list, description="List of transcript entries"
    )
    perception: dict[str, Any] | None = Field(
        None, description="Optional perception analysis"
    )


class PerceptionAnalysis(BaseModel):
    """Perception analysis data from Raven-1."""

    engagement_score: float | None = Field(None, description="User engagement level 0-1")
    emotion: str | None = Field(None, description="Detected primary emotion")
    attention_level: float | None = Field(None, description="Attention level 0-1")
    sentiment: str | None = Field(None, description="Overall sentiment")
    raw_data: dict[str, Any] | None = Field(None, description="Raw perception data")


class PerceptionPayload(TavusWebhookPayload):
    """Payload for application.perception_analysis event."""

    event_type: str = "application.perception_analysis"
    perception: PerceptionAnalysis = Field(
        ..., description="Perception analysis from Raven-1"
    )


class UtteranceData(BaseModel):
    """Single utterance data."""

    speaker: str = Field(..., description="Speaker identifier")
    content: str = Field(..., description="Utterance text")
    timestamp_ms: int = Field(0, description="Timestamp in milliseconds")


class UtterancePayload(TavusWebhookPayload):
    """Payload for conversation.utterance event."""

    event_type: str = "conversation.utterance"
    utterance: UtteranceData = Field(..., description="The utterance data")


class ToolCallPayload(TavusWebhookPayload):
    """Payload for conversation.tool_call event."""

    event_type: str = "conversation.tool_call"
    tool_name: str = Field(..., description="Name of the invoked tool")
    tool_call_id: str | None = Field(None, description="Unique ID for this tool call")
    args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    result: dict[str, Any] | None = Field(None, description="Tool result if available")


# ─────────────────────────────────────────────────────────────────────────────
# Webhook Secret Verification
# ─────────────────────────────────────────────────────────────────────────────


def verify_webhook_secret(webhook_secret: str | None) -> bool:
    """Verify the webhook secret against configured value.

    Args:
        webhook_secret: The secret from X-Webhook-Secret header.

    Returns:
        True if secret is valid, False otherwise.
    """
    expected_secret = getattr(settings, "TAVUS_WEBHOOK_SECRET", None)
    if not expected_secret:
        logger.warning("TAVUS_WEBHOOK_SECRET not configured - skipping verification")
        return True  # Allow in development if not configured

    if not webhook_secret:
        return False

    return webhook_secret == expected_secret


# ─────────────────────────────────────────────────────────────────────────────
# Event Handlers
# ─────────────────────────────────────────────────────────────────────────────


async def handle_replica_joined(
    conversation_id: str,
    payload: dict[str, Any],
    db: Any,
) -> None:
    """Handle system.replica_joined event.

    Updates video_sessions status to 'active'.

    Args:
        conversation_id: The Tavus conversation ID.
        payload: The full webhook payload.
        db: Supabase client.
    """
    result = (
        db.table("video_sessions")
        .update({"status": "active"})
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    if result.data:
        logger.info(
            "Video session activated",
            extra={"conversation_id": conversation_id},
        )
    else:
        logger.warning(
            "No video session found for replica_joined",
            extra={"conversation_id": conversation_id},
        )


async def handle_shutdown(
    conversation_id: str,
    payload: dict[str, Any],
    db: Any,
) -> None:
    """Handle system.shutdown event.

    Updates video_sessions status to 'ended', calculates duration,
    and stores shutdown_reason.

    Args:
        conversation_id: The Tavus conversation ID.
        payload: The full webhook payload containing shutdown_reason.
        db: Supabase client.
    """
    shutdown_reason = payload.get("shutdown_reason", "unknown")
    now = datetime.now(UTC)

    # First get the session to calculate duration
    session_result = (
        db.table("video_sessions")
        .select("started_at")
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    duration_seconds = None
    if session_result.data and len(session_result.data) > 0:
        started_at_str = session_result.data[0].get("started_at")
        if started_at_str:
            try:
                started_at = datetime.fromisoformat(
                    started_at_str.replace("Z", "+00:00")
                )
                duration_seconds = int((now - started_at).total_seconds())
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse started_at for duration calculation",
                    extra={"conversation_id": conversation_id, "error": str(e)},
                )

    update_data = {
        "status": "ended",
        "ended_at": now.isoformat(),
        "shutdown_reason": shutdown_reason,
    }
    if duration_seconds is not None:
        update_data["duration_seconds"] = duration_seconds

    result = (
        db.table("video_sessions")
        .update(update_data)
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    if result.data:
        logger.info(
            "Video session ended",
            extra={
                "conversation_id": conversation_id,
                "shutdown_reason": shutdown_reason,
                "duration_seconds": duration_seconds,
            },
        )
    else:
        logger.warning(
            "No video session found for shutdown",
            extra={"conversation_id": conversation_id},
        )


async def handle_transcription_ready(
    conversation_id: str,
    payload: dict[str, Any],
    db: Any,
) -> None:
    """Handle application.transcription_ready event.

    Stores transcript entries in video_transcript_entries and
    creates an episodic memory entry.

    Args:
        conversation_id: The Tavus conversation ID.
        payload: The full webhook payload containing transcript.
        db: Supabase client.
    """
    # Get the video session
    session_result = (
        db.table("video_sessions")
        .select("id, user_id, lead_id")
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    if not session_result.data or len(session_result.data) == 0:
        logger.warning(
            "No video session found for transcription",
            extra={"conversation_id": conversation_id},
        )
        return

    session = session_result.data[0]
    video_session_id = session["id"]
    user_id = session["user_id"]

    # Store transcript entries
    transcript = payload.get("transcript", [])
    entries_created = 0

    for entry in transcript:
        try:
            speaker = entry.get("speaker", "user")
            content = entry.get("content", "")
            timestamp_ms = entry.get("timestamp_ms", 0)

            if not content.strip():
                continue

            db.table("video_transcript_entries").insert({
                "video_session_id": video_session_id,
                "speaker": speaker,
                "content": content,
                "timestamp_ms": timestamp_ms,
            }).execute()
            entries_created += 1

        except Exception as e:
            logger.warning(
                "Failed to store transcript entry",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )

    # Store perception analysis if included
    perception = payload.get("perception")
    if perception:
        try:
            db.table("video_sessions").update({
                "perception_analysis": perception
            }).eq("id", video_session_id).execute()
        except Exception as e:
            logger.warning(
                "Failed to store perception analysis",
                extra={"conversation_id": conversation_id, "error": str(e)},
            )

    # Create episodic memory entry for the transcript
    if entries_created > 0:
        await _create_transcript_episode(
            user_id=user_id,
            video_session_id=video_session_id,
            conversation_id=conversation_id,
            transcript=transcript,
            db=db,
        )

    logger.info(
        "Transcript stored",
        extra={
            "conversation_id": conversation_id,
            "entries_count": entries_created,
        },
    )


async def _create_transcript_episode(
    user_id: str,
    video_session_id: str,
    conversation_id: str,
    transcript: list[dict[str, Any]],
    db: Any,
) -> None:
    """Create an episodic memory entry for the transcript.

    Args:
        user_id: The user ID.
        video_session_id: The video session ID.
        conversation_id: The Tavus conversation ID.
        transcript: List of transcript entries.
        db: Supabase client.
    """
    try:
        from src.memory.episodic import Episode, EpisodicMemory

        # Build transcript summary
        transcript_text = "\n".join(
            f"{e.get('speaker', 'unknown')}: {e.get('content', '')}"
            for e in transcript
            if e.get("content", "").strip()
        )

        episode = Episode(
            id=str(uuid.uuid4()),
            user_id=user_id,
            event_type="video_session",
            content=f"Video conversation transcript:\n{transcript_text[:2000]}",  # Limit length
            participants=["aria"],
            occurred_at=datetime.now(UTC),
            recorded_at=datetime.now(UTC),
            context={
                "video_session_id": video_session_id,
                "conversation_id": conversation_id,
                "entry_count": len(transcript),
            },
        )

        episodic_memory = EpisodicMemory()
        await episodic_memory.store_episode(episode)

        logger.info(
            "Created episodic memory for transcript",
            extra={
                "episode_id": episode.id,
                "conversation_id": conversation_id,
            },
        )

    except Exception as e:
        logger.warning(
            "Failed to create episodic memory for transcript",
            extra={
                "conversation_id": conversation_id,
                "error": str(e),
            },
        )


async def handle_perception_analysis(
    conversation_id: str,
    payload: dict[str, Any],
    db: Any,
) -> None:
    """Handle application.perception_analysis event.

    Stores perception JSONB and updates lead health if linked.

    Args:
        conversation_id: The Tavus conversation ID.
        payload: The full webhook payload containing perception data.
        db: Supabase client.
    """
    perception = payload.get("perception", {})

    # Get the video session with lead_id
    session_result = (
        db.table("video_sessions")
        .select("id, user_id, lead_id")
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    if not session_result.data or len(session_result.data) == 0:
        logger.warning(
            "No video session found for perception analysis",
            extra={"conversation_id": conversation_id},
        )
        return

    session = session_result.data[0]
    video_session_id = session["id"]
    lead_id = session.get("lead_id")

    # Store perception analysis
    db.table("video_sessions").update({
        "perception_analysis": perception
    }).eq("id", video_session_id).execute()

    logger.info(
        "Perception analysis stored",
        extra={
            "conversation_id": conversation_id,
            "video_session_id": video_session_id,
        },
    )

    # If linked to a lead, update stakeholder sentiment
    if lead_id:
        await _update_lead_sentiment_from_perception(
            lead_id=lead_id,
            perception=perception,
            db=db,
        )


async def _update_lead_sentiment_from_perception(
    lead_id: str,
    perception: dict[str, Any],
    db: Any,
) -> None:
    """Update lead health score based on perception analysis.

    Args:
        lead_id: The lead ID.
        perception: The perception analysis data.
        db: Supabase client.
    """
    try:
        # Extract sentiment and engagement from perception
        sentiment = perception.get("sentiment", "neutral")
        engagement_score = perception.get("engagement_score", 0.5)

        # Log the perception for lead intelligence
        db.table("aria_activity").insert({
            "user_id": None,  # System-generated
            "activity_type": "webhook.perception_analysis",
            "description": f"Video session perception: sentiment={sentiment}, engagement={engagement_score:.2f}",
            "metadata": {
                "lead_id": lead_id,
                "perception": perception,
            },
        }).execute()

        logger.info(
            "Lead perception logged",
            extra={
                "lead_id": lead_id,
                "sentiment": sentiment,
                "engagement": engagement_score,
            },
        )

    except Exception as e:
        logger.warning(
            "Failed to update lead sentiment from perception",
            extra={"lead_id": lead_id, "error": str(e)},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Perception Tool Call Handling
# ─────────────────────────────────────────────────────────────────────────────

PERCEPTION_TOOLS: frozenset[str] = frozenset({
    "adapt_to_confusion",
    "note_engagement_drop",
})


async def handle_perception_tool_call(
    conversation_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    db: Any,
) -> dict[str, Any] | None:
    """Handle a perception tool call (adapt_to_confusion / note_engagement_drop).

    Records the perception event on the video session, updates per-topic
    statistics, and logs to aria_activity.  Returns a silent spoken_text
    so ARIA adapts organically without an explicit verbal acknowledgement.

    Args:
        conversation_id: The Tavus conversation ID.
        tool_name: The perception tool name.
        arguments: Tool arguments (indicator, topic, metadata, etc.).
        db: Supabase client.

    Returns:
        Dict with ``spoken_text: ""`` on success, or ``None`` on failure.
    """
    # 1. Look up the video session
    session_result = (
        db.table("video_sessions")
        .select("id, user_id, perception_events, started_at")
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    if not session_result.data or len(session_result.data) == 0:
        logger.warning(
            "No video session found for perception tool call",
            extra={"conversation_id": conversation_id, "tool_name": tool_name},
        )
        return None

    session = session_result.data[0]
    session_id: str = session["id"]
    user_id: str = session["user_id"]
    perception_events: list[dict[str, Any]] = session.get("perception_events") or []
    started_at_str: str | None = session.get("started_at")

    # 2. Compute session_time_seconds
    session_time_seconds: float = 0.0
    now = datetime.now(UTC)
    if started_at_str:
        try:
            started_at = datetime.fromisoformat(
                started_at_str.replace("Z", "+00:00")
            )
            session_time_seconds = (now - started_at).total_seconds()
        except (ValueError, TypeError):
            pass

    # 3. Build the perception event
    topic = arguments.get("topic", "unknown")
    indicator = arguments.get("indicator", "")

    event: dict[str, Any] = {
        "tool_name": tool_name,
        "timestamp": now.isoformat(),
        "session_time_seconds": round(session_time_seconds, 2),
        "indicator": indicator,
        "topic": topic,
        "metadata": {k: v for k, v in arguments.items() if k not in ("indicator", "topic")},
    }

    # 4. Deduplication: skip if same tool + topic within 2 seconds of last event
    for prev in reversed(perception_events):
        if prev.get("tool_name") == tool_name and prev.get("topic") == topic:
            try:
                prev_ts = datetime.fromisoformat(prev["timestamp"])
                if abs((now - prev_ts).total_seconds()) < 2.0:
                    logger.debug(
                        "Skipping duplicate perception event",
                        extra={"tool_name": tool_name, "topic": topic},
                    )
                    return {"spoken_text": ""}
            except (ValueError, TypeError, KeyError):
                pass
            break  # Only compare with the most recent matching event

    # 5. Append event to perception_events JSONB array
    perception_events.append(event)
    try:
        db.table("video_sessions").update({
            "perception_events": perception_events,
        }).eq("id", session_id).execute()
    except Exception as e:
        logger.warning(
            "Failed to update perception_events on video_sessions",
            extra={"session_id": session_id, "error": str(e)},
        )

    # 6. Upsert topic stats
    try:
        await _upsert_topic_stats(
            user_id=user_id,
            tool_name=tool_name,
            topic=topic,
            db=db,
        )
    except Exception as e:
        logger.warning(
            "Failed to upsert perception topic stats",
            extra={"user_id": user_id, "topic": topic, "error": str(e)},
        )

    # 7. Log to aria_activity
    try:
        db.table("aria_activity").insert({
            "user_id": user_id,
            "activity_type": f"perception.{tool_name}",
            "description": (
                f"Perception event: {tool_name} on topic '{topic}' "
                f"(indicator: {indicator})"
            ),
            "metadata": {
                "conversation_id": conversation_id,
                "session_id": session_id,
                "event": event,
            },
        }).execute()
    except Exception as e:
        logger.warning(
            "Failed to log perception activity",
            extra={"conversation_id": conversation_id, "error": str(e)},
        )

    logger.info(
        "Perception tool call handled",
        extra={
            "conversation_id": conversation_id,
            "tool_name": tool_name,
            "topic": topic,
            "session_time_seconds": round(session_time_seconds, 2),
        },
    )

    # Silent response — ARIA adapts organically
    return {"spoken_text": ""}


async def _upsert_topic_stats(
    user_id: str,
    tool_name: str,
    topic: str,
    db: Any,
) -> None:
    """Create or update a row in perception_topic_stats.

    Increments the relevant counter (confusion_count or
    disengagement_count) and total_mentions for the user + topic pair.

    Args:
        user_id: The user ID.
        tool_name: The perception tool name.
        topic: The topic string from the tool arguments.
        db: Supabase client.
    """
    now_iso = datetime.now(UTC).isoformat()

    # Check for existing row
    existing = (
        db.table("perception_topic_stats")
        .select("id, confusion_count, disengagement_count, total_mentions")
        .eq("user_id", user_id)
        .eq("topic", topic)
        .execute()
    )

    if existing.data and len(existing.data) > 0:
        row = existing.data[0]
        update_data: dict[str, Any] = {
            "total_mentions": (row.get("total_mentions", 0) or 0) + 1,
        }
        if tool_name == "adapt_to_confusion":
            update_data["confusion_count"] = (row.get("confusion_count", 0) or 0) + 1
            update_data["last_confused_at"] = now_iso
        elif tool_name == "note_engagement_drop":
            update_data["disengagement_count"] = (row.get("disengagement_count", 0) or 0) + 1
            update_data["last_disengaged_at"] = now_iso

        db.table("perception_topic_stats").update(update_data).eq(
            "id", row["id"]
        ).execute()
    else:
        insert_data: dict[str, Any] = {
            "user_id": user_id,
            "topic": topic,
            "confusion_count": 1 if tool_name == "adapt_to_confusion" else 0,
            "disengagement_count": 1 if tool_name == "note_engagement_drop" else 0,
            "total_mentions": 1,
        }
        if tool_name == "adapt_to_confusion":
            insert_data["last_confused_at"] = now_iso
        elif tool_name == "note_engagement_drop":
            insert_data["last_disengaged_at"] = now_iso

        db.table("perception_topic_stats").insert(insert_data).execute()


async def handle_utterance(
    conversation_id: str,
    payload: dict[str, Any],
    db: Any,
) -> None:
    """Handle conversation.utterance event (real-time).

    Stores individual utterance in video_transcript_entries.

    Args:
        conversation_id: The Tavus conversation ID.
        payload: The full webhook payload containing utterance.
        db: Supabase client.
    """
    # Get the video session
    session_result = (
        db.table("video_sessions")
        .select("id")
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    if not session_result.data or len(session_result.data) == 0:
        logger.warning(
            "No video session found for utterance",
            extra={"conversation_id": conversation_id},
        )
        return

    video_session_id = session_result.data[0]["id"]
    utterance = payload.get("utterance", {})

    speaker = utterance.get("speaker", "user")
    content = utterance.get("content", "")
    timestamp_ms = utterance.get("timestamp_ms", 0)

    if not content.strip():
        return

    try:
        db.table("video_transcript_entries").insert({
            "video_session_id": video_session_id,
            "speaker": speaker,
            "content": content,
            "timestamp_ms": timestamp_ms,
        }).execute()

        logger.debug(
            "Utterance stored",
            extra={
                "conversation_id": conversation_id,
                "speaker": speaker,
            },
        )

    except Exception as e:
        logger.warning(
            "Failed to store utterance",
            extra={"conversation_id": conversation_id, "error": str(e)},
        )


async def _execute_tool_with_timeout(
    tool_name: str,
    arguments: dict[str, Any],
    user_id: str,
) -> ToolResult:
    """Execute a video tool with timeout and retry.

    First attempt has a 15-second timeout. On timeout, retries once.
    If both attempts time out, returns a graceful failure message.

    Args:
        tool_name: Name of the tool to execute.
        arguments: Tool arguments.
        user_id: The user's UUID.

    Returns:
        ToolResult with spoken_text and optional rich_content.
    """
    from src.integrations.tavus_tool_executor import ToolResult, VideoToolExecutor

    executor = VideoToolExecutor(user_id=user_id)

    for attempt in range(2):
        try:
            result = await asyncio.wait_for(
                executor.execute(tool_name=tool_name, arguments=arguments),
                timeout=TOOL_EXECUTION_TIMEOUT,
            )
            return result
        except TimeoutError:
            if attempt == 0:
                logger.warning(
                    "Tool execution timed out, retrying",
                    extra={
                        "tool_name": tool_name,
                        "user_id": user_id,
                        "attempt": attempt + 1,
                    },
                )
                continue
            # Second timeout — give up gracefully
            logger.warning(
                "Tool execution timed out after retry",
                extra={"tool_name": tool_name, "user_id": user_id},
            )
            return ToolResult(
                spoken_text=(
                    f"I'm having trouble completing the {tool_name.replace('_', ' ')} "
                    "request right now. Let me try a different approach or come back "
                    "to this in a moment."
                )
            )

    # Should not be reached, but satisfy type checker
    return ToolResult(spoken_text="I wasn't able to complete that request.")


async def handle_tool_call(
    conversation_id: str,
    payload: dict[str, Any],
    db: Any,
) -> dict[str, Any] | None:
    """Handle conversation.tool_call event.

    Executes the requested tool via VideoToolExecutor with sequential
    execution guard (one tool at a time per conversation) and timeout
    handling. Logs execution details to aria_activity.

    Args:
        conversation_id: The Tavus conversation ID.
        payload: The full webhook payload containing tool call info.
        db: Supabase client.

    Returns:
        Dict with tool_call_id, tool_name, and result for the webhook
        response, or None if execution failed.
    """
    tool_name = payload.get("tool_name", "unknown")
    tool_call_id = payload.get("tool_call_id")
    arguments = payload.get("args", {})
    # Tavus may also send arguments as a JSON string under "arguments"
    if not arguments and isinstance(payload.get("arguments"), str):
        import json as _json

        try:
            arguments = _json.loads(payload["arguments"])
        except (ValueError, TypeError):
            arguments = {}

    # Look up user_id from video_sessions
    session_result = (
        db.table("video_sessions")
        .select("user_id")
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    user_id = None
    if session_result.data and len(session_result.data) > 0:
        user_id = session_result.data[0].get("user_id")

    if not user_id:
        logger.warning(
            "No user_id found for tool call — cannot execute",
            extra={"conversation_id": conversation_id, "tool_name": tool_name},
        )
        return None

    # Perception tools are handled separately — silent, no business execution
    if tool_name in PERCEPTION_TOOLS:
        handler_result = await handle_perception_tool_call(
            conversation_id=conversation_id,
            tool_name=tool_name,
            arguments=arguments,
            db=db,
        )
        if handler_result:
            return {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "result": handler_result["spoken_text"],
            }
        return None

    # Sequential execution guard: one tool at a time per conversation
    lock = _conversation_locks[conversation_id]

    start_time = time.monotonic()
    async with lock:
        tool_result = await _execute_tool_with_timeout(tool_name, arguments, user_id)
    duration_ms = int((time.monotonic() - start_time) * 1000)

    spoken_text = tool_result.spoken_text

    success = not spoken_text.startswith(
        "I ran into an issue"
    ) and not spoken_text.startswith("I'm having trouble")

    # Truncate result for logging metadata
    result_summary = (
        spoken_text[:200] + "..." if len(spoken_text) > 200 else spoken_text
    )

    # Log to aria_activity
    try:
        db.table("aria_activity").insert({
            "user_id": user_id,
            "activity_type": "video_tool_call",
            "description": f"Tool '{tool_name}' executed during video session",
            "metadata": {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": arguments,
                "result_summary": result_summary,
                "duration_ms": duration_ms,
                "conversation_id": conversation_id,
                "success": success,
            },
        }).execute()
    except Exception as e:
        logger.warning(
            "Failed to log tool call activity",
            extra={"conversation_id": conversation_id, "error": str(e)},
        )

    # Emit rich_content to frontend via WebSocket
    if tool_result.rich_content is not None:
        try:
            from src.core.ws import ws_manager

            await ws_manager.send_aria_message(
                user_id=user_id,
                message="",
                rich_content=[tool_result.rich_content],
            )
        except Exception as e:
            logger.warning(
                "Failed to send rich content via WebSocket",
                extra={"conversation_id": conversation_id, "error": str(e)},
            )

    logger.info(
        "Video tool call executed",
        extra={
            "conversation_id": conversation_id,
            "tool_name": tool_name,
            "duration_ms": duration_ms,
            "success": success,
        },
    )

    return {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "result": spoken_text,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Event Handler Dispatch
# ─────────────────────────────────────────────────────────────────────────────

EVENT_HANDLERS: dict[str, Any] = {
    "system.replica_joined": handle_replica_joined,
    "system.shutdown": handle_shutdown,
    "application.transcription_ready": handle_transcription_ready,
    "application.perception_analysis": handle_perception_analysis,
    "conversation.utterance": handle_utterance,
    "conversation.tool_call": handle_tool_call,
}


# ─────────────────────────────────────────────────────────────────────────────
# Main Webhook Endpoint
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/tavus")
async def handle_tavus_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
) -> dict[str, Any]:
    """Handle incoming Tavus webhook callbacks.

    This endpoint receives callbacks from Tavus for various video session
    events including session lifecycle, transcription, perception analysis,
    and tool call execution.

    For ``conversation.tool_call`` events the response includes the tool
    execution result so Tavus can incorporate it into the LLM's reply.

    Args:
        request: The incoming FastAPI request.
        x_webhook_secret: Optional webhook secret header for verification.

    Returns:
        Success acknowledgment, optionally with tool result.

    Raises:
        HTTPException: 401 if webhook secret is invalid.
        HTTPException: 400 if payload is invalid.
    """
    # 1. Verify webhook secret
    if not verify_webhook_secret(x_webhook_secret):
        logger.warning(
            "Invalid webhook secret",
            extra={"path": request.url.path},
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook secret",
        )

    # 2. Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.warning(
            "Failed to parse webhook payload",
            extra={"error": str(e)},
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload",
        )

    # 3. Validate required fields
    event_type = payload.get("event_type")
    conversation_id = payload.get("conversation_id")

    if not event_type or not conversation_id:
        logger.warning(
            "Missing required webhook fields",
            extra={"payload": payload},
        )
        raise HTTPException(
            status_code=400,
            detail="Missing event_type or conversation_id",
        )

    # 4. Log the webhook event
    logger.info(
        "Received Tavus webhook",
        extra={
            "event_type": event_type,
            "conversation_id": conversation_id,
        },
    )

    # 5. Get database client
    db = get_supabase_client()

    # 6. Validate conversation_id exists in video_sessions
    session_check = (
        db.table("video_sessions")
        .select("id")
        .eq("tavus_conversation_id", conversation_id)
        .execute()
    )

    if not session_check.data or len(session_check.data) == 0:
        # For system.replica_joined, the session might be created via API
        # before the webhook arrives, so log warning but don't fail
        if event_type == "system.replica_joined":
            logger.warning(
                "Video session not found for replica_joined - may be race condition",
                extra={"conversation_id": conversation_id},
            )
        else:
            logger.warning(
                "Video session not found for webhook",
                extra={
                    "conversation_id": conversation_id,
                    "event_type": event_type,
                },
            )
            # Still process the webhook for logging purposes

    # 7. Log to aria_activity (skip for tool_call — handled inside handler)
    if event_type != "conversation.tool_call":
        try:
            db.table("aria_activity").insert({
                "user_id": None,  # System-generated event
                "activity_type": f"webhook.{event_type}",
                "description": f"Tavus webhook: {event_type}",
                "metadata": {
                    "event_type": event_type,
                    "conversation_id": conversation_id,
                    "timestamp": payload.get("timestamp"),
                },
            }).execute()
        except Exception as e:
            logger.warning(
                "Failed to log webhook to activity",
                extra={"error": str(e)},
            )

    # 8. Dispatch to event handler
    handler_result: dict[str, Any] | None = None
    handler = EVENT_HANDLERS.get(event_type)
    if handler:
        try:
            handler_result = await handler(conversation_id, payload, db)
        except Exception as e:
            logger.exception(
                "Error handling webhook event",
                extra={
                    "event_type": event_type,
                    "conversation_id": conversation_id,
                    "error": str(e),
                },
            )
            # Don't fail the webhook - Tavus will retry
    else:
        logger.warning(
            "Unknown webhook event type",
            extra={"event_type": event_type},
        )

    # 9. Return response — include tool result for tool_call events
    if event_type == "conversation.tool_call" and handler_result:
        return {
            "status": "ok",
            "tool_result": handler_result,
        }

    return {"status": "ok"}
