"""Tests for VideoSessionService - video session lifecycle management."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.video import SessionType, VideoSessionResponse, VideoSessionStatus


class TestVideoSessionServiceCreateSession:
    """Test suite for VideoSessionService.create_session."""

    @pytest.mark.asyncio
    async def test_create_session_creates_tavus_conversation_and_db_record(self):
        """Test that create_session creates both a Tavus conversation and DB record."""
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_type = SessionType.CHAT
        context = "Discussing Lonza partnership opportunities"

        # Mock Tavus client
        mock_tavus = MagicMock()
        mock_tavus.create_conversation = AsyncMock(
            return_value={
                "conversation_id": "tavus-conv-123",
                "conversation_url": "https://tavus.io/room/abc123",
            }
        )

        # Mock Supabase client
        mock_supabase_client = MagicMock()
        mock_supabase_client.table.return_value.insert.return_value.execute = MagicMock(
            return_value=MagicMock(
                data=[
                    {
                        "id": "session-uuid-123",
                        "user_id": user_id,
                        "tavus_conversation_id": "tavus-conv-123",
                        "room_url": "https://tavus.io/room/abc123",
                        "status": VideoSessionStatus.ACTIVE.value,
                        "session_type": session_type.value,
                        "started_at": datetime.now(UTC).isoformat(),
                        "ended_at": None,
                        "duration_seconds": None,
                        "created_at": datetime.now(UTC).isoformat(),
                        "lead_id": None,
                    }
                ]
            )
        )

        with (
            patch("src.services.video_service.get_tavus_client", return_value=mock_tavus),
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
        ):
            result = await VideoSessionService.create_session(
                user_id=user_id,
                session_type=session_type,
                context=context,
            )

        # Verify Tavus conversation was created
        mock_tavus.create_conversation.assert_called_once()
        call_kwargs = mock_tavus.create_conversation.call_args.kwargs
        assert call_kwargs["user_id"] == user_id
        assert "aria-chat-" in call_kwargs["conversation_name"]
        assert call_kwargs["context"] == context

        # Verify DB record was created
        mock_supabase_client.table.assert_called_once_with("video_sessions")

        # Verify result is VideoSessionResponse
        assert isinstance(result, VideoSessionResponse)
        assert result.user_id == user_id
        assert result.tavus_conversation_id == "tavus-conv-123"
        assert result.room_url == "https://tavus.io/room/abc123"
        assert result.status == VideoSessionStatus.ACTIVE
        assert result.session_type == session_type

    @pytest.mark.asyncio
    async def test_create_session_with_lead_id_passes_lead_context(self):
        """Test that create_session passes lead context when lead_id is provided."""
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        lead_id = str(uuid.uuid4())
        session_type = SessionType.BRIEFING

        # Mock Tavus client
        mock_tavus = MagicMock()
        mock_tavus.create_conversation = AsyncMock(
            return_value={
                "conversation_id": "tavus-conv-456",
                "conversation_url": "https://tavus.io/room/def456",
            }
        )

        # Mock Supabase for lead context lookup
        mock_supabase_client = MagicMock()

        # Lead lookup mock
        lead_result = MagicMock()
        lead_result.data = [
            {
                "company_name": "Lonza",
                "contact_name": "Dr. Sarah Chen",
                "status": "qualified",
                "priority": "high",
            }
        ]

        # Session insert mock
        session_result = MagicMock()
        session_result.data = [
            {
                "id": "session-uuid-456",
                "user_id": user_id,
                "tavus_conversation_id": "tavus-conv-456",
                "room_url": "https://tavus.io/room/def456",
                "status": VideoSessionStatus.ACTIVE.value,
                "session_type": session_type.value,
                "started_at": datetime.now(UTC).isoformat(),
                "ended_at": None,
                "duration_seconds": None,
                "created_at": datetime.now(UTC).isoformat(),
                "lead_id": lead_id,
            }
        ]

        # Set up chain for leads table, then video_sessions table
        mock_supabase_client.table.side_effect = [
            MagicMock(
                select=MagicMock(
                    return_value=MagicMock(
                        eq=MagicMock(
                            return_value=MagicMock(execute=MagicMock(return_value=lead_result))
                        )
                    )
                )
            ),  # leads query
            MagicMock(
                insert=MagicMock(
                    return_value=MagicMock(execute=MagicMock(return_value=session_result))
                )
            ),  # video_sessions insert
        ]

        with (
            patch("src.services.video_service.get_tavus_client", return_value=mock_tavus),
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
        ):
            result = await VideoSessionService.create_session(
                user_id=user_id,
                session_type=session_type,
                context=None,
                lead_id=lead_id,
            )

        # Verify lead context was passed to Tavus
        call_kwargs = mock_tavus.create_conversation.call_args.kwargs
        assert "Lonza" in call_kwargs["context"]

        # Verify result
        assert result.lead_id == lead_id

    @pytest.mark.asyncio
    async def test_create_session_raises_external_service_error_on_tavus_failure(self):
        """Test that create_session raises ExternalServiceError when Tavus fails."""
        from src.core.exceptions import ExternalServiceError
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())

        # Mock Tavus client that fails
        mock_tavus = MagicMock()
        mock_tavus.create_conversation = AsyncMock(side_effect=Exception("Tavus API down"))

        with (
            patch("src.services.video_service.get_tavus_client", return_value=mock_tavus),
            patch("src.services.video_service.SupabaseClient.get_client"),
        ):
            with pytest.raises(ExternalServiceError) as exc_info:
                await VideoSessionService.create_session(
                    user_id=user_id,
                    session_type=SessionType.CHAT,
                    context=None,
                )

            assert "Tavus" in str(exc_info.value)


class TestVideoSessionServiceEndSession:
    """Test suite for VideoSessionService.end_session."""

    @pytest.mark.asyncio
    async def test_end_session_ends_tavus_conversation_and_updates_db(self):
        """Test that end_session ends Tavus conversation and updates DB record."""
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        # Mock Tavus client
        mock_tavus = MagicMock()
        mock_tavus.end_conversation = AsyncMock(return_value={"status": "ended"})

        # Mock Supabase client
        mock_supabase_client = MagicMock()

        # Session fetch result
        fetch_result = MagicMock()
        fetch_result.data = [
            {
                "id": session_id,
                "user_id": user_id,
                "tavus_conversation_id": "tavus-conv-123",
                "room_url": "https://tavus.io/room/abc123",
                "status": VideoSessionStatus.ACTIVE.value,
                "session_type": "chat",
                "started_at": "2024-01-01T10:00:00+00:00",
                "ended_at": None,
                "duration_seconds": None,
                "created_at": "2024-01-01T10:00:00+00:00",
            }
        ]

        # Session update result
        update_result = MagicMock()
        update_result.data = [
            {
                "id": session_id,
                "user_id": user_id,
                "tavus_conversation_id": "tavus-conv-123",
                "room_url": "https://tavus.io/room/abc123",
                "status": VideoSessionStatus.ENDED.value,
                "session_type": "chat",
                "started_at": "2024-01-01T10:00:00+00:00",
                "ended_at": "2024-01-01T10:30:00+00:00",
                "duration_seconds": 1800,
                "created_at": "2024-01-01T10:00:00+00:00",
            }
        ]

        # Create table mock that handles both calls
        table_mock = MagicMock()

        # First call: select().eq().eq().execute()
        select_chain = MagicMock()
        select_chain.eq.return_value.eq.return_value.execute.return_value = fetch_result
        table_mock.select.return_value = select_chain

        # Second call: update().eq().eq().execute()
        update_chain = MagicMock()
        update_chain.eq.return_value.eq.return_value.execute.return_value = update_result
        table_mock.update.return_value = update_chain

        mock_supabase_client.table.return_value = table_mock

        with (
            patch("src.services.video_service.get_tavus_client", return_value=mock_tavus),
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
        ):
            result = await VideoSessionService.end_session(
                session_id=session_id,
                user_id=user_id,
            )

        # Verify Tavus conversation was ended
        mock_tavus.end_conversation.assert_called_once_with("tavus-conv-123")

        # Verify result
        assert result.status == VideoSessionStatus.ENDED
        assert result.ended_at is not None
        assert result.duration_seconds == 1800

    @pytest.mark.asyncio
    async def test_end_session_raises_not_found_for_invalid_session(self):
        """Test that end_session raises NotFoundError for non-existent session."""
        from src.core.exceptions import NotFoundError
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        # Mock Supabase with empty result
        mock_supabase_client = MagicMock()
        fetch_result = MagicMock()
        fetch_result.data = []

        select_mock = MagicMock()
        select_mock.eq.return_value.eq.return_value.execute.return_value = fetch_result
        mock_supabase_client.table.return_value = select_mock

        with (
            patch("src.services.video_service.get_tavus_client"),
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            pytest.raises(NotFoundError),
        ):
            await VideoSessionService.end_session(
                session_id=session_id,
                user_id=user_id,
            )

    @pytest.mark.asyncio
    async def test_end_session_raises_error_for_already_ended_session(self):
        """Test that end_session raises error for already ended session."""
        from src.core.exceptions import ValidationError
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        # Mock Supabase with already ended session
        mock_supabase_client = MagicMock()
        fetch_result = MagicMock()
        fetch_result.data = [
            {
                "id": session_id,
                "user_id": user_id,
                "tavus_conversation_id": "tavus-conv-123",
                "status": VideoSessionStatus.ENDED.value,
                "session_type": "chat",
            }
        ]

        # Create table mock with select chain
        table_mock = MagicMock()
        select_chain = MagicMock()
        select_chain.eq.return_value.eq.return_value.execute.return_value = fetch_result
        table_mock.select.return_value = select_chain

        mock_supabase_client.table.return_value = table_mock

        with (
            patch("src.services.video_service.get_tavus_client"),
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
        ):
            with pytest.raises(ValidationError) as exc_info:
                await VideoSessionService.end_session(
                    session_id=session_id,
                    user_id=user_id,
                )

            assert "already ended" in str(exc_info.value).lower()


class TestVideoSessionServiceGetSessionWithTranscript:
    """Test suite for VideoSessionService.get_session_with_transcript."""

    @pytest.mark.asyncio
    async def test_get_session_with_transcript_returns_session_and_transcripts(self):
        """Test that get_session_with_transcript returns session with all transcript entries."""
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        # Mock Supabase client
        mock_supabase_client = MagicMock()

        # Session fetch mock
        session_result = MagicMock()
        session_result.data = [
            {
                "id": session_id,
                "user_id": user_id,
                "tavus_conversation_id": "tavus-conv-123",
                "room_url": "https://tavus.io/room/abc123",
                "status": VideoSessionStatus.ENDED.value,
                "session_type": "chat",
                "started_at": "2024-01-01T10:00:00+00:00",
                "ended_at": "2024-01-01T10:30:00+00:00",
                "duration_seconds": 1800,
                "created_at": "2024-01-01T10:00:00+00:00",
                "lead_id": None,
                "perception_analysis": {"engagement": 0.85},
            }
        ]

        # Transcript fetch mock
        transcript_result = MagicMock()
        transcript_result.data = [
            {
                "id": "transcript-1",
                "video_session_id": session_id,
                "speaker": "user",
                "content": "Hello ARIA, I need help with the Lonza account.",
                "timestamp_ms": 0,
                "created_at": "2024-01-01T10:00:00+00:00",
            },
            {
                "id": "transcript-2",
                "video_session_id": session_id,
                "speaker": "aria",
                "content": "Of course! I can help you with Lonza. What specifically do you need?",
                "timestamp_ms": 3500,
                "created_at": "2024-01-01T10:00:03+00:00",
            },
        ]

        # Create mock table that handles both video_sessions and video_transcript_entries
        def mock_table(table_name: str):
            mock = MagicMock()
            if table_name == "video_sessions":
                select_chain = MagicMock()
                select_chain.eq.return_value.eq.return_value.execute.return_value = session_result
                mock.select.return_value = select_chain
            elif table_name == "video_transcript_entries":
                select_chain = MagicMock()
                select_chain.eq.return_value.order.return_value.execute.return_value = (
                    transcript_result
                )
                mock.select.return_value = select_chain
            return mock

        mock_supabase_client.table.side_effect = mock_table

        with patch(
            "src.services.video_service.SupabaseClient.get_client",
            return_value=mock_supabase_client,
        ):
            result = await VideoSessionService.get_session_with_transcript(
                session_id=session_id,
                user_id=user_id,
            )

        # Verify result structure
        assert isinstance(result, VideoSessionResponse)
        assert result.id == session_id
        assert result.status == VideoSessionStatus.ENDED
        assert result.transcripts is not None
        assert len(result.transcripts) == 2
        assert result.transcripts[0].speaker == "user"
        assert result.transcripts[1].speaker == "aria"

    @pytest.mark.asyncio
    async def test_get_session_with_transcript_raises_not_found_for_invalid_session(self):
        """Test that get_session_with_transcript raises NotFoundError for non-existent session."""
        from src.core.exceptions import NotFoundError
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        # Mock Supabase with empty result
        mock_supabase_client = MagicMock()
        fetch_result = MagicMock()
        fetch_result.data = []

        select_mock = MagicMock()
        select_mock.eq.return_value.eq.return_value.execute.return_value = fetch_result
        mock_supabase_client.table.return_value = select_mock

        with (
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            pytest.raises(NotFoundError),
        ):
            await VideoSessionService.get_session_with_transcript(
                session_id=session_id,
                user_id=user_id,
            )


class TestVideoSessionServiceProcessTranscript:
    """Test suite for VideoSessionService.process_transcript."""

    @pytest.mark.asyncio
    async def test_process_transcript_stores_entries_and_extracts_insights(self):
        """Test that process_transcript stores transcript entries and extracts insights via Claude."""
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        transcript_data = [
            {
                "speaker": "user",
                "content": "I need to follow up with Lonza about the CDMO proposal.",
                "timestamp_ms": 0,
            },
            {
                "speaker": "aria",
                "content": "I'll help you with that. Should I draft an email to Dr. Chen?",
                "timestamp_ms": 5000,
            },
            {
                "speaker": "user",
                "content": "Yes, please draft it for tomorrow morning.",
                "timestamp_ms": 10000,
            },
        ]

        # Mock Supabase client
        mock_supabase_client = MagicMock()

        # Session fetch mock
        session_result = MagicMock()
        session_result.data = [
            {
                "id": session_id,
                "user_id": user_id,
                "tavus_conversation_id": "tavus-conv-123",
                "status": VideoSessionStatus.ENDED.value,
                "session_type": "chat",
                "lead_id": None,
            }
        ]

        # Create mock table that handles different tables
        tables_called = []

        def mock_table(table_name: str):
            tables_called.append(table_name)
            mock = MagicMock()
            if table_name == "video_sessions":
                select_chain = MagicMock()
                select_chain.eq.return_value.eq.return_value.execute.return_value = session_result
                mock.select.return_value = select_chain
            else:
                # For video_transcript_entries and aria_activity
                mock.insert.return_value.execute.return_value = MagicMock(data=[])
            return mock

        mock_supabase_client.table.side_effect = mock_table

        # Mock LLM client
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(
            return_value="""{
                "key_topics": ["CDMO proposal", "Lonza follow-up", "Email drafting"],
                "action_items": [
                    {"action": "Draft email to Dr. Chen at Lonza", "priority": "high", "due": "tomorrow morning"}
                ],
                "commitments": ["User will send email tomorrow morning"],
                "sentiment": "productive"
            }"""
        )

        # Mock EpisodicMemory
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(return_value="episode-123")

        with (
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.services.video_service.LLMClient", return_value=mock_llm),
            patch("src.services.video_service.EpisodicMemory", return_value=mock_episodic),
        ):
            result = await VideoSessionService.process_transcript(
                session_id=session_id,
                user_id=user_id,
                transcript_data=transcript_data,
            )

        # Verify transcript entries were stored
        assert "video_sessions" in tables_called
        assert "video_transcript_entries" in tables_called

        # Verify LLM was called for insight extraction
        mock_llm.generate_response.assert_called_once()

        # Verify episodic memory was stored
        mock_episodic.store_episode.assert_called_once()

        # Verify result structure
        assert "key_topics" in result
        assert "action_items" in result
        assert "commitments" in result
        assert "sentiment" in result
        assert "CDMO proposal" in result["key_topics"]

    @pytest.mark.asyncio
    async def test_process_transcript_updates_lead_memory_when_lead_linked(self):
        """Test that process_transcript updates lead_memory_events when session is linked to a lead."""
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        lead_id = str(uuid.uuid4())

        transcript_data = [
            {
                "speaker": "user",
                "content": "Discussing Lonza CDMO deal",
                "timestamp_ms": 0,
            }
        ]

        # Mock Supabase client
        mock_supabase_client = MagicMock()

        # Session fetch mock with lead_id
        session_result = MagicMock()
        session_result.data = [
            {
                "id": session_id,
                "user_id": user_id,
                "tavus_conversation_id": "tavus-conv-123",
                "status": VideoSessionStatus.ENDED.value,
                "session_type": "consultation",
                "lead_id": lead_id,
            }
        ]

        # Create mock table that handles different tables
        tables_called = []

        def mock_table(table_name: str):
            tables_called.append(table_name)
            mock = MagicMock()
            if table_name == "video_sessions":
                select_chain = MagicMock()
                select_chain.eq.return_value.eq.return_value.execute.return_value = session_result
                mock.select.return_value = select_chain
            else:
                # For video_transcript_entries, lead_memory_events, and aria_activity
                mock.insert.return_value.execute.return_value = MagicMock(data=[])
            return mock

        mock_supabase_client.table.side_effect = mock_table

        # Mock LLM client
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(
            return_value='{"key_topics": [], "action_items": [], "commitments": [], "sentiment": "neutral"}'
        )

        # Mock EpisodicMemory
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(return_value="episode-123")

        with (
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.services.video_service.LLMClient", return_value=mock_llm),
            patch("src.services.video_service.EpisodicMemory", return_value=mock_episodic),
        ):
            await VideoSessionService.process_transcript(
                session_id=session_id,
                user_id=user_id,
                transcript_data=transcript_data,
            )

        # Verify lead_memory_events was called
        assert "lead_memory_events" in tables_called

    @pytest.mark.asyncio
    async def test_process_transcript_logs_to_aria_activity(self):
        """Test that process_transcript logs the processing to aria_activity table."""
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        transcript_data = [{"speaker": "user", "content": "Test", "timestamp_ms": 0}]

        # Mock Supabase client
        mock_supabase_client = MagicMock()

        # Session fetch mock
        session_result = MagicMock()
        session_result.data = [
            {
                "id": session_id,
                "user_id": user_id,
                "tavus_conversation_id": "tavus-conv-123",
                "status": VideoSessionStatus.ENDED.value,
                "session_type": "chat",
                "lead_id": None,
            }
        ]

        # Create mock table that handles different tables
        tables_called = []

        def mock_table(table_name: str):
            tables_called.append(table_name)
            mock = MagicMock()
            if table_name == "video_sessions":
                select_chain = MagicMock()
                select_chain.eq.return_value.eq.return_value.execute.return_value = session_result
                mock.select.return_value = select_chain
            else:
                # For video_transcript_entries and aria_activity
                mock.insert.return_value.execute.return_value = MagicMock(data=[])
            return mock

        mock_supabase_client.table.side_effect = mock_table

        # Mock LLM client
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(
            return_value='{"key_topics": [], "action_items": [], "commitments": [], "sentiment": "neutral"}'
        )

        # Mock EpisodicMemory
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(return_value="episode-123")

        with (
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.services.video_service.LLMClient", return_value=mock_llm),
            patch("src.services.video_service.EpisodicMemory", return_value=mock_episodic),
        ):
            await VideoSessionService.process_transcript(
                session_id=session_id,
                user_id=user_id,
                transcript_data=transcript_data,
            )

        # Verify aria_activity was logged
        assert "aria_activity" in tables_called

    @pytest.mark.asyncio
    async def test_process_transcript_sends_notification_to_user(self):
        """Test that process_transcript sends a notification when transcript is ready."""
        from src.models.notification import NotificationType
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        transcript_data = [{"speaker": "user", "content": "Test", "timestamp_ms": 0}]

        # Mock Supabase client
        mock_supabase_client = MagicMock()

        # Session fetch mock
        session_result = MagicMock()
        session_result.data = [
            {
                "id": session_id,
                "user_id": user_id,
                "tavus_conversation_id": "tavus-conv-123",
                "status": VideoSessionStatus.ENDED.value,
                "session_type": "chat",
                "lead_id": None,
            }
        ]

        # Create mock table that handles different tables
        def mock_table(table_name: str):
            mock = MagicMock()
            if table_name == "video_sessions":
                select_chain = MagicMock()
                select_chain.eq.return_value.eq.return_value.execute.return_value = session_result
                mock.select.return_value = select_chain
            else:
                # For video_transcript_entries and aria_activity
                mock.insert.return_value.execute.return_value = MagicMock(data=[])
            return mock

        mock_supabase_client.table.side_effect = mock_table

        # Mock LLM client
        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(
            return_value='{"key_topics": ["Test Topic"], "action_items": [], "commitments": [], "sentiment": "positive"}'
        )

        # Mock EpisodicMemory
        mock_episodic = MagicMock()
        mock_episodic.store_episode = AsyncMock(return_value="episode-123")

        # Mock NotificationService
        mock_notification = AsyncMock(
            return_value=MagicMock(id="notification-123", user_id=user_id)
        )

        with (
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            patch("src.services.video_service.LLMClient", return_value=mock_llm),
            patch("src.services.video_service.EpisodicMemory", return_value=mock_episodic),
            patch(
                "src.services.video_service.NotificationService.create_notification",
                mock_notification,
            ),
        ):
            await VideoSessionService.process_transcript(
                session_id=session_id,
                user_id=user_id,
                transcript_data=transcript_data,
            )

        # Verify notification was sent
        mock_notification.assert_called_once()
        call_kwargs = mock_notification.call_args.kwargs
        assert call_kwargs["user_id"] == user_id
        assert call_kwargs["type"] == NotificationType.VIDEO_SESSION_READY
        assert "transcript" in call_kwargs["title"].lower()
        assert session_id in call_kwargs["link"]

    @pytest.mark.asyncio
    async def test_process_transcript_raises_not_found_for_invalid_session(self):
        """Test that process_transcript raises NotFoundError for non-existent session."""
        from src.core.exceptions import NotFoundError
        from src.services.video_service import VideoSessionService

        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())

        # Mock Supabase with empty result
        mock_supabase_client = MagicMock()
        fetch_result = MagicMock()
        fetch_result.data = []

        # Create table mock with select chain
        table_mock = MagicMock()
        select_chain = MagicMock()
        select_chain.eq.return_value.eq.return_value.execute.return_value = fetch_result
        table_mock.select.return_value = select_chain

        mock_supabase_client.table.return_value = table_mock

        with (
            patch(
                "src.services.video_service.SupabaseClient.get_client",
                return_value=mock_supabase_client,
            ),
            pytest.raises(NotFoundError),
        ):
            await VideoSessionService.process_transcript(
                session_id=session_id,
                user_id=user_id,
                transcript_data=[],
            )
