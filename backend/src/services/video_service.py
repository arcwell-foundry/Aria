"""Video session service for orchestrating Tavus video sessions.

This service handles the full lifecycle of video sessions:
- Creating sessions with Tavus and persisting to DB
- Ending sessions and calculating duration
- Retrieving sessions with transcripts
- Processing transcripts with AI insight extraction
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.exceptions import (
    DatabaseError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import SupabaseClient
from src.integrations.tavus import get_tavus_client
from src.memory.episodic import Episode, EpisodicMemory
from src.models.notification import NotificationType
from src.models.video import (
    SessionType,
    TranscriptEntryResponse,
    VideoSessionResponse,
    VideoSessionStatus,
)
from src.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

# Default Knowledge Base tags for all video conversations
_DEFAULT_KB_TAGS = ["aria-context", "life-sciences", "competitive"]


def _document_tags_for_session(session_type: SessionType) -> list[str]:
    """Return Knowledge Base document tags for a given session type.

    Briefing and consultation sessions include "signals" for market intelligence.
    """
    tags = list(_DEFAULT_KB_TAGS)
    if session_type in (SessionType.BRIEFING, SessionType.CONSULTATION):
        tags.append("signals")
    return tags


class VideoSessionService:
    """Service for managing video session lifecycle with Tavus integration.

    This service orchestrates:
    - Tavus conversation creation and termination
    - Database persistence of session records
    - Transcript processing with Claude-powered insight extraction
    - Episodic memory storage for session insights
    - Activity logging for audit trail
    """

    @staticmethod
    async def create_session(
        user_id: str,
        session_type: SessionType,
        context: str | None = None,
        custom_greeting: str | None = None,
        lead_id: str | None = None,
    ) -> VideoSessionResponse:
        """Create a new video session with Tavus and persist to database.

        Args:
            user_id: The user's UUID.
            session_type: Type of video session (chat, briefing, debrief, consultation).
            context: Optional conversational context.
            custom_greeting: Optional custom greeting for ARIA.
            lead_id: Optional lead ID to link the session to.

        Returns:
            VideoSessionResponse with created session details.

        Raises:
            ExternalServiceError: If Tavus API fails.
            DatabaseError: If database persistence fails.
        """
        session_id = str(uuid.uuid4())
        tavus = get_tavus_client()

        # Build context including lead info if provided
        full_context = context or ""
        if lead_id:
            lead_context = await VideoSessionService._build_lead_context(lead_id)
            if lead_context:
                full_context = f"{full_context}\n\n{lead_context}" if full_context else lead_context

        # Create Tavus conversation
        try:
            tavus_response = await tavus.create_conversation(
                user_id=user_id,
                conversation_name=f"aria-{session_type.value}-{session_id[:8]}",
                context=full_context or None,
                custom_greeting=custom_greeting,
                memory_stores=[{"memory_store_id": f"aria-user-{user_id}"}],
                document_tags=_document_tags_for_session(session_type),
                retrieval_strategy="balanced",
            )
        except Exception as e:
            logger.exception(
                "Tavus API error creating conversation",
                extra={"user_id": user_id, "error": str(e)},
            )
            raise ExternalServiceError(
                service="Tavus",
                message=f"Failed to create video session: {e}",
            ) from e

        tavus_conversation_id = str(tavus_response.get("conversation_id", ""))
        room_url = str(tavus_response.get("conversation_url", "")) or None

        # Persist to database
        now = datetime.now(UTC).isoformat()
        row: dict[str, Any] = {
            "id": session_id,
            "user_id": user_id,
            "tavus_conversation_id": tavus_conversation_id,
            "room_url": room_url,
            "status": VideoSessionStatus.ACTIVE.value,
            "session_type": session_type.value,
            "started_at": now,
            "ended_at": None,
            "duration_seconds": None,
            "created_at": now,
            "lead_id": lead_id,
        }

        try:
            client = SupabaseClient.get_client()
            result = client.table("video_sessions").insert(row).execute()

            if not result.data or len(result.data) == 0:
                raise DatabaseError("Failed to insert video session")

            saved = result.data[0]
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception(
                "Database error creating video session",
                extra={"session_id": session_id, "user_id": user_id},
            )
            raise DatabaseError(f"Failed to create video session: {e}") from e

        logger.info(
            "Video session created",
            extra={
                "session_id": session_id,
                "user_id": user_id,
                "tavus_conversation_id": tavus_conversation_id,
                "lead_id": lead_id,
            },
        )

        return VideoSessionResponse(
            id=saved["id"],
            user_id=saved["user_id"],
            tavus_conversation_id=saved["tavus_conversation_id"],
            room_url=saved.get("room_url"),
            status=saved["status"],
            session_type=saved["session_type"],
            started_at=saved.get("started_at"),
            ended_at=saved.get("ended_at"),
            duration_seconds=saved.get("duration_seconds"),
            created_at=saved["created_at"],
            lead_id=saved.get("lead_id"),
        )

    @staticmethod
    async def end_session(
        session_id: str,
        user_id: str,
    ) -> VideoSessionResponse:
        """End an active video session.

        Args:
            session_id: The video session UUID.
            user_id: The user's UUID (for authorization).

        Returns:
            VideoSessionResponse with updated session details.

        Raises:
            NotFoundError: If session not found or doesn't belong to user.
            ValidationError: If session is already ended.
            ExternalServiceError: If Tavus API fails (non-blocking).
            DatabaseError: If database update fails.
        """
        # Fetch existing session
        client = SupabaseClient.get_client()
        result = (
            client.table("video_sessions")
            .select("*")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data or len(result.data) == 0:
            raise NotFoundError("Video session", session_id)

        session = result.data[0]

        if session["status"] == VideoSessionStatus.ENDED.value:
            raise ValidationError("Video session already ended")

        # End conversation on Tavus side (non-blocking - log warning if fails)
        tavus = get_tavus_client()
        try:
            await tavus.end_conversation(session["tavus_conversation_id"])
        except Exception as e:
            logger.warning(
                "Failed to end Tavus conversation (may already be ended)",
                extra={
                    "session_id": session_id,
                    "tavus_conversation_id": session["tavus_conversation_id"],
                    "error": str(e),
                },
            )

        # Calculate duration
        now = datetime.now(UTC)
        started_at = session.get("started_at")
        duration_seconds: int | None = None
        if started_at:
            started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            duration_seconds = int((now - started_dt).total_seconds())

        # Update the session record
        update_data = {
            "status": VideoSessionStatus.ENDED.value,
            "ended_at": now.isoformat(),
            "duration_seconds": duration_seconds,
        }

        try:
            update_result = (
                client.table("video_sessions")
                .update(update_data)
                .eq("id", session_id)
                .eq("user_id", user_id)
                .execute()
            )

            if not update_result.data or len(update_result.data) == 0:
                raise DatabaseError("Failed to update video session")

            updated = update_result.data[0]
        except DatabaseError:
            raise
        except Exception as e:
            logger.exception(
                "Database error ending video session",
                extra={"session_id": session_id, "user_id": user_id},
            )
            raise DatabaseError(f"Failed to end video session: {e}") from e

        logger.info(
            "Video session ended",
            extra={
                "session_id": session_id,
                "user_id": user_id,
                "duration_seconds": duration_seconds,
            },
        )

        return VideoSessionResponse(
            id=updated["id"],
            user_id=updated["user_id"],
            tavus_conversation_id=updated["tavus_conversation_id"],
            room_url=updated.get("room_url"),
            status=updated["status"],
            session_type=updated["session_type"],
            started_at=updated.get("started_at"),
            ended_at=updated.get("ended_at"),
            duration_seconds=updated.get("duration_seconds"),
            created_at=updated["created_at"],
            lead_id=updated.get("lead_id"),
            perception_analysis=updated.get("perception_analysis"),
        )

    @staticmethod
    async def get_session_with_transcript(
        session_id: str,
        user_id: str,
    ) -> VideoSessionResponse:
        """Get a video session with all transcript entries.

        Args:
            session_id: The video session UUID.
            user_id: The user's UUID (for authorization).

        Returns:
            VideoSessionResponse with session details and transcripts.

        Raises:
            NotFoundError: If session not found or doesn't belong to user.
        """
        client = SupabaseClient.get_client()

        # Fetch session
        result = (
            client.table("video_sessions")
            .select("*")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data or len(result.data) == 0:
            raise NotFoundError("Video session", session_id)

        session = result.data[0]

        # Fetch transcripts
        transcripts: list[TranscriptEntryResponse] | None = None
        try:
            transcript_result = (
                client.table("video_transcript_entries")
                .select("*")
                .eq("video_session_id", session_id)
                .order("timestamp_ms")
                .execute()
            )
            if transcript_result.data:
                transcripts = [
                    TranscriptEntryResponse(
                        id=entry["id"],
                        video_session_id=entry["video_session_id"],
                        speaker=entry["speaker"],
                        content=entry["content"],
                        timestamp_ms=entry["timestamp_ms"],
                        created_at=entry["created_at"],
                    )
                    for entry in transcript_result.data
                ]
        except Exception as e:
            logger.warning(
                "Failed to fetch transcripts for session",
                extra={"session_id": session_id, "error": str(e)},
            )

        return VideoSessionResponse(
            id=session["id"],
            user_id=session["user_id"],
            tavus_conversation_id=session["tavus_conversation_id"],
            room_url=session.get("room_url"),
            status=session["status"],
            session_type=session["session_type"],
            started_at=session.get("started_at"),
            ended_at=session.get("ended_at"),
            duration_seconds=session.get("duration_seconds"),
            created_at=session["created_at"],
            lead_id=session.get("lead_id"),
            perception_analysis=session.get("perception_analysis"),
            transcripts=transcripts,
        )

    @staticmethod
    async def process_transcript(
        session_id: str,
        user_id: str,
        transcript_data: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Process a video transcript: store entries, extract insights, log to memory.

        This method:
        1. Stores each transcript entry in video_transcript_entries
        2. Uses Claude API to extract insights (topics, actions, commitments, sentiment)
        3. Stores insights in episodic_memories
        4. If linked to a lead, updates lead_memory_events
        5. Logs to aria_activity

        Args:
            session_id: The video session UUID.
            user_id: The user's UUID.
            transcript_data: List of transcript entries with speaker, content, timestamp_ms.

        Returns:
            Dictionary with extracted insights:
            - key_topics: List of main topics discussed
            - action_items: List of action items with priority and due dates
            - commitments: List of commitments made
            - sentiment: Overall sentiment of the conversation

        Raises:
            NotFoundError: If session not found.
            DatabaseError: If database operations fail.
        """
        client = SupabaseClient.get_client()

        # Fetch session to verify ownership and get lead_id
        result = (
            client.table("video_sessions")
            .select("*")
            .eq("id", session_id)
            .eq("user_id", user_id)
            .execute()
        )

        if not result.data or len(result.data) == 0:
            raise NotFoundError("Video session", session_id)

        session = result.data[0]
        lead_id = session.get("lead_id")

        # Store transcript entries
        if transcript_data:
            entries_to_insert = [
                {
                    "id": str(uuid.uuid4()),
                    "video_session_id": session_id,
                    "speaker": entry["speaker"],
                    "content": entry["content"],
                    "timestamp_ms": entry["timestamp_ms"],
                    "created_at": datetime.now(UTC).isoformat(),
                }
                for entry in transcript_data
            ]

            try:
                client.table("video_transcript_entries").insert(entries_to_insert).execute()
            except Exception as e:
                logger.warning(
                    "Failed to store transcript entries",
                    extra={"session_id": session_id, "error": str(e)},
                )

        # Extract insights using Claude
        insights = await VideoSessionService._extract_insights(transcript_data)

        # Store in episodic memory
        await VideoSessionService._store_episodic_memory(
            user_id=user_id,
            session_id=session_id,
            session_type=session.get("session_type", "chat"),
            transcript_data=transcript_data,
            insights=insights,
        )

        # If linked to lead, update lead_memory_events
        if lead_id:
            await VideoSessionService._update_lead_memory(
                lead_id=lead_id,
                user_id=user_id,
                session_id=session_id,
                insights=insights,
            )

        # Log to aria_activity
        await VideoSessionService._log_activity(
            user_id=user_id,
            session_id=session_id,
            insights=insights,
        )

        # Notify user that transcript is ready
        await VideoSessionService._send_notification(
            user_id=user_id,
            session_id=session_id,
            session_type=session.get("session_type", "chat"),
            insights=insights,
        )

        logger.info(
            "Video transcript processed",
            extra={
                "session_id": session_id,
                "user_id": user_id,
                "entry_count": len(transcript_data),
                "lead_id": lead_id,
            },
        )

        return insights

    @staticmethod
    async def _build_lead_context(lead_id: str) -> str:
        """Build context string from lead data.

        Args:
            lead_id: The lead UUID.

        Returns:
            Context string with lead information.
        """
        try:
            client = SupabaseClient.get_client()
            result = (
                client.table("leads")
                .select("company_name, contact_name, status, priority, notes")
                .eq("id", lead_id)
                .execute()
            )

            if result.data:
                lead = result.data[0]
                context_parts = [f"Lead Company: {lead.get('company_name', 'Unknown')}"]
                if lead.get("contact_name"):
                    context_parts.append(f"Lead Contact: {lead['contact_name']}")
                if lead.get("status"):
                    context_parts.append(f"Lead Status: {lead['status']}")
                if lead.get("priority"):
                    context_parts.append(f"Lead Priority: {lead['priority']}")
                return "\n".join(context_parts)
        except Exception as e:
            logger.warning(
                "Failed to fetch lead context",
                extra={"lead_id": lead_id, "error": str(e)},
            )

        return ""

    @staticmethod
    async def _extract_insights(
        transcript_data: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Extract insights from transcript using Claude API.

        Args:
            transcript_data: List of transcript entries.

        Returns:
            Dictionary with key_topics, action_items, commitments, sentiment.
        """
        if not transcript_data:
            return {
                "key_topics": [],
                "action_items": [],
                "commitments": [],
                "sentiment": "neutral",
            }

        # Build transcript text
        transcript_text = "\n".join(
            f"[{entry['speaker']}]: {entry['content']}" for entry in transcript_data
        )

        system_prompt = """You are ARIA's transcript analysis module. Analyze video conversation transcripts and extract structured insights.

You must respond with a valid JSON object containing:
- key_topics: list of main topics discussed (strings)
- action_items: list of action items, each with "action", "priority" (high/medium/low), and "due" fields
- commitments: list of commitments made during the conversation (strings)
- sentiment: overall sentiment (positive/neutral/negative/mixed)

Example response:
{
    "key_topics": ["Topic 1", "Topic 2"],
    "action_items": [{"action": "Do something", "priority": "high", "due": "tomorrow"}],
    "commitments": ["User will follow up by Friday"],
    "sentiment": "positive"
}"""

        user_message = f"""Analyze this conversation transcript and extract insights:

{transcript_text}

Respond with only valid JSON."""

        try:
            llm = LLMClient()
            response = await llm.generate_response(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                temperature=0.3,
                task=TaskType.MEMORY_SUMMARIZE,
            )

            # Parse JSON response
            # Handle potential markdown code blocks
            response_text = response.strip()
            if response_text.startswith("```"):
                # Remove markdown code block markers
                lines = response_text.split("\n")
                response_text = "\n".join(
                    line for line in lines if not line.startswith("```")
                ).strip()

            insights = json.loads(response_text)

            # Validate structure
            return {
                "key_topics": insights.get("key_topics", []),
                "action_items": insights.get("action_items", []),
                "commitments": insights.get("commitments", []),
                "sentiment": insights.get("sentiment", "neutral"),
            }

        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse insight JSON from LLM",
                extra={"error": str(e), "response": response[:200] if response else None},
            )
            return {
                "key_topics": [],
                "action_items": [],
                "commitments": [],
                "sentiment": "neutral",
            }
        except Exception as e:
            logger.exception(
                "Failed to extract insights from transcript",
                extra={"error": str(e)},
            )
            return {
                "key_topics": [],
                "action_items": [],
                "commitments": [],
                "sentiment": "neutral",
            }

    @staticmethod
    async def _store_episodic_memory(
        user_id: str,
        session_id: str,
        session_type: str,
        transcript_data: list[dict[str, Any]],
        insights: dict[str, Any],
    ) -> None:
        """Store session insights in episodic memory.

        Args:
            user_id: The user's UUID.
            session_id: The video session UUID.
            session_type: Type of video session.
            transcript_data: The transcript entries.
            insights: Extracted insights.
        """
        try:
            # Build episode content
            content_parts = [f"Video session ({session_type})"]

            if insights.get("key_topics"):
                content_parts.append(f"Topics: {', '.join(insights['key_topics'])}")

            if insights.get("action_items"):
                actions = [item.get("action", "") for item in insights["action_items"]]
                content_parts.append(f"Actions: {'; '.join(actions)}")

            if insights.get("commitments"):
                content_parts.append(f"Commitments: {'; '.join(insights['commitments'])}")

            content_parts.append(f"Sentiment: {insights.get('sentiment', 'neutral')}")

            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type=f"video_session_{session_type}",
                content="\n".join(content_parts),
                participants=["aria", "user"],
                occurred_at=datetime.now(UTC),
                recorded_at=datetime.now(UTC),
                context={
                    "session_id": session_id,
                    "insights": insights,
                    "entry_count": len(transcript_data),
                },
            )

            episodic = EpisodicMemory()
            await episodic.store_episode(episode)

            logger.info(
                "Stored video session in episodic memory",
                extra={"session_id": session_id, "user_id": user_id},
            )

        except Exception as e:
            logger.warning(
                "Failed to store episodic memory for video session",
                extra={"session_id": session_id, "error": str(e)},
            )

    @staticmethod
    async def _update_lead_memory(
        lead_id: str,
        user_id: str,
        session_id: str,
        insights: dict[str, Any],
    ) -> None:
        """Update lead memory events with session insights.

        Args:
            lead_id: The lead UUID.
            user_id: The user's UUID.
            session_id: The video session UUID.
            insights: Extracted insights.
        """
        try:
            client = SupabaseClient.get_client()

            event_data = {
                "id": str(uuid.uuid4()),
                "lead_id": lead_id,
                "user_id": user_id,
                "event_type": "video_session",
                "event_data": {
                    "session_id": session_id,
                    "key_topics": insights.get("key_topics", []),
                    "action_items": insights.get("action_items", []),
                    "commitments": insights.get("commitments", []),
                    "sentiment": insights.get("sentiment", "neutral"),
                },
                "created_at": datetime.now(UTC).isoformat(),
            }

            client.table("lead_memory_events").insert(event_data).execute()

            logger.info(
                "Updated lead memory with video session",
                extra={"lead_id": lead_id, "session_id": session_id},
            )

        except Exception as e:
            logger.warning(
                "Failed to update lead memory",
                extra={"lead_id": lead_id, "session_id": session_id, "error": str(e)},
            )

    @staticmethod
    async def _log_activity(
        user_id: str,
        session_id: str,
        insights: dict[str, Any],
    ) -> None:
        """Log video transcript processing to aria_activity.

        Args:
            user_id: The user's UUID.
            session_id: The video session UUID.
            insights: Extracted insights.
        """
        try:
            client = SupabaseClient.get_client()

            activity_data = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "agent": "aria",
                "activity_type": "video_transcript_processed",
                "title": "Video transcript processed",
                "description": f"Processed video session with {len(insights.get('key_topics', []))} topics identified",
                "reasoning": "",
                "confidence": 0.9,
                "related_entity_type": "video_session",
                "related_entity_id": session_id,
                "metadata": {
                    "key_topics": insights.get("key_topics", []),
                    "action_count": len(insights.get("action_items", [])),
                    "sentiment": insights.get("sentiment", "neutral"),
                },
                "created_at": datetime.now(UTC).isoformat(),
            }

            client.table("aria_activity").insert(activity_data).execute()

            logger.info(
                "Logged video transcript activity",
                extra={"session_id": session_id, "user_id": user_id},
            )

        except Exception as e:
            logger.warning(
                "Failed to log video activity",
                extra={"session_id": session_id, "error": str(e)},
            )

    @staticmethod
    async def _send_notification(
        user_id: str,
        session_id: str,
        session_type: str,
        insights: dict[str, Any],
    ) -> None:
        """Send notification to user that transcript is ready.

        Args:
            user_id: The user's UUID.
            session_id: The video session UUID.
            session_type: Type of video session.
            insights: Extracted insights.
        """
        try:
            topic_summary = ""
            if insights.get("key_topics"):
                topics = insights["key_topics"][:3]  # Show max 3 topics
                topic_summary = f" Topics: {', '.join(topics)}."

            await NotificationService.create_notification(
                user_id=user_id,
                type=NotificationType.VIDEO_SESSION_READY,
                title="Video session transcript ready",
                message=f"Your {session_type} session transcript has been processed.{topic_summary}",
                link=f"/video/sessions/{session_id}",
                metadata={
                    "session_id": session_id,
                    "session_type": session_type,
                    "action_count": len(insights.get("action_items", [])),
                    "sentiment": insights.get("sentiment", "neutral"),
                },
            )

            logger.info(
                "Sent video transcript notification",
                extra={"session_id": session_id, "user_id": user_id},
            )

        except Exception as e:
            logger.warning(
                "Failed to send video transcript notification",
                extra={"session_id": session_id, "error": str(e)},
            )
