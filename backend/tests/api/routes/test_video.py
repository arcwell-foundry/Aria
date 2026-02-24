"""Tests for video API routes."""

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.models.video import SessionType, VideoSessionStatus

# ---------------------------------------------------------------------------
# Load the video route module directly from file to avoid pulling in
# every sibling route via __init__.py, which causes order-dependent failures
# in the full test suite due to accumulated import side-effects.
# ---------------------------------------------------------------------------


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Mock external dependencies before loading the module
if "httpx" not in sys.modules:
    sys.modules["httpx"] = MagicMock()

_video_mod = _load_module(
    "src.api.routes.video",
    Path(__file__).resolve().parent.parent.parent.parent / "src" / "api" / "routes" / "video.py",
)
_router = _video_mod.router


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(_router, prefix="/api/v1")
    return app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def mock_tavus() -> MagicMock:
    """Create mock Tavus client."""
    client = MagicMock()
    client.create_conversation = AsyncMock(
        return_value={
            "conversation_id": "tavus-conv-123",
            "conversation_url": "https://daily.co/room/test-room",
        }
    )
    client.end_conversation = AsyncMock(return_value={"status": "ended"})
    return client


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock database client."""
    return MagicMock()


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""
    app = create_test_app()

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


class TestCreateVideoSession:
    """Tests for POST /video/sessions endpoint."""

    def test_create_session_with_default_params(
        self, test_client: TestClient, mock_tavus: MagicMock, mock_db: MagicMock
    ) -> None:
        """Test creating a session with default parameters."""
        mock_insert_result = MagicMock()
        mock_insert_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ACTIVE.value,
            "session_type": SessionType.CHAT.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": None,
            "duration_seconds": None,
            "created_at": datetime.now(UTC).isoformat(),
            "lead_id": None,
            "perception_analysis": {},
        }]

        with patch.object(_video_mod, "get_tavus_client", return_value=mock_tavus):
            with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
                with patch.object(_video_mod, "build_aria_context", return_value="Test context"):
                    with patch.object(_video_mod, "ws_manager") as mock_ws:
                        mock_ws.send_to_user = AsyncMock()
                        mock_db.table.return_value.insert.return_value.execute.return_value = (
                            mock_insert_result
                        )

                        response = test_client.post(
                            "/api/v1/video/sessions",
                            json={},
                        )

                        assert response.status_code == 200, (
                            f"Expected 200, got {response.status_code}: {response.text}"
                        )
                        data = response.json()
                        assert data["session_type"] == "chat"
                        assert data["status"] == "active"

    def test_create_session_with_all_tavus_params(
        self, test_client: TestClient, mock_tavus: MagicMock, mock_db: MagicMock
    ) -> None:
        """Verify Tavus call includes memory_stores, document_tags, retrieval_strategy."""
        mock_insert_result = MagicMock()
        mock_insert_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ACTIVE.value,
            "session_type": SessionType.BRIEFING.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": None,
            "duration_seconds": None,
            "created_at": datetime.now(UTC).isoformat(),
            "lead_id": None,
            "perception_analysis": {},
        }]

        with patch.object(_video_mod, "get_tavus_client", return_value=mock_tavus):
            with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
                with patch.object(_video_mod, "build_aria_context", return_value="Test context"):
                    with patch.object(_video_mod, "ws_manager") as mock_ws:
                        mock_ws.send_to_user = AsyncMock()
                        mock_db.table.return_value.insert.return_value.execute.return_value = (
                            mock_insert_result
                        )

                        response = test_client.post(
                            "/api/v1/video/sessions",
                            json={
                                "session_type": "briefing",
                                "context": "Custom context",
                                "custom_greeting": "Hello!",
                            },
                        )

                        assert response.status_code == 200
                        # Verify Tavus was called with the enhanced parameters
                        mock_tavus.create_conversation.assert_called_once()
                        call_kwargs = mock_tavus.create_conversation.call_args[1]
                        assert "memory_stores" in call_kwargs
                        assert call_kwargs["memory_stores"] == [
                            {"memory_store_id": "aria-user-test-user-123"}
                        ]
                        assert call_kwargs["document_tags"] == ["aria-context", "life-sciences", "competitive", "signals"]
                        assert call_kwargs["retrieval_strategy"] == "balanced"

    def test_create_session_with_lead_id(
        self, test_client: TestClient, mock_tavus: MagicMock, mock_db: MagicMock
    ) -> None:
        """Verify lead_id is stored and lead context is included."""
        lead_id = "lead-456"
        mock_insert_result = MagicMock()
        mock_insert_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ACTIVE.value,
            "session_type": SessionType.CONSULTATION.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": None,
            "duration_seconds": None,
            "created_at": datetime.now(UTC).isoformat(),
            "lead_id": lead_id,
            "perception_analysis": {},
        }]

        with patch.object(_video_mod, "get_tavus_client", return_value=mock_tavus):
            with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
                with patch.object(
                    _video_mod,
                    "build_aria_context",
                    return_value="Lead context included",
                ) as mock_build_context:
                    with patch.object(_video_mod, "ws_manager") as mock_ws:
                        mock_ws.send_to_user = AsyncMock()
                        mock_db.table.return_value.insert.return_value.execute.return_value = (
                            mock_insert_result
                        )

                        response = test_client.post(
                            "/api/v1/video/sessions",
                            json={
                                "session_type": "consultation",
                                "lead_id": lead_id,
                            },
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["lead_id"] == lead_id
                        # Verify build_aria_context was called with lead_id
                        mock_build_context.assert_called_once()
                        call_args = mock_build_context.call_args[1]
                        assert call_args["lead_id"] == lead_id

    def test_create_session_tavus_error(self, test_client: TestClient, mock_db: MagicMock) -> None:
        """Verify 502 error when Tavus API fails."""
        mock_tavus = MagicMock()
        mock_tavus.create_conversation = AsyncMock(
            side_effect=Exception("Tavus API error")
        )

        with patch.object(_video_mod, "get_tavus_client", return_value=mock_tavus):
            with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
                with patch.object(_video_mod, "build_aria_context", return_value="Test"):
                    response = test_client.post(
                        "/api/v1/video/sessions",
                        json={"session_type": "chat"},
                    )

                    assert response.status_code == 502
                    assert "Video service temporarily unavailable" in response.json()["detail"]

    def test_create_session_consultation_type(
        self, test_client: TestClient, mock_tavus: MagicMock, mock_db: MagicMock
    ) -> None:
        """Test creating a consultation session."""
        mock_insert_result = MagicMock()
        mock_insert_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ACTIVE.value,
            "session_type": SessionType.CONSULTATION.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": None,
            "duration_seconds": None,
            "created_at": datetime.now(UTC).isoformat(),
            "lead_id": None,
            "perception_analysis": {},
        }]

        with patch.object(_video_mod, "get_tavus_client", return_value=mock_tavus):
            with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
                with patch.object(_video_mod, "build_aria_context", return_value="Test"):
                    with patch.object(_video_mod, "ws_manager") as mock_ws:
                        mock_ws.send_to_user = AsyncMock()
                        mock_db.table.return_value.insert.return_value.execute.return_value = (
                            mock_insert_result
                        )

                        response = test_client.post(
                            "/api/v1/video/sessions",
                            json={"session_type": "consultation"},
                        )

                        assert response.status_code == 200
                        assert response.json()["session_type"] == "consultation"

    def test_create_audio_only_session(
        self, test_client: TestClient, mock_tavus: MagicMock, mock_db: MagicMock
    ) -> None:
        """Verify audio_only=True is passed to Tavus and stored in DB."""
        mock_insert_result = MagicMock()
        mock_insert_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ACTIVE.value,
            "session_type": SessionType.CHAT.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": None,
            "duration_seconds": None,
            "created_at": datetime.now(UTC).isoformat(),
            "lead_id": None,
            "perception_analysis": {},
            "is_audio_only": True,
        }]

        with patch.object(_video_mod, "get_tavus_client", return_value=mock_tavus):
            with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
                with patch.object(_video_mod, "build_aria_context", return_value="Test context"):
                    with patch.object(_video_mod, "ws_manager") as mock_ws:
                        mock_ws.send_to_user = AsyncMock()
                        mock_db.table.return_value.insert.return_value.execute.return_value = (
                            mock_insert_result
                        )

                        response = test_client.post(
                            "/api/v1/video/sessions",
                            json={"audio_only": True},
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["is_audio_only"] is True

                        # Verify Tavus was called with audio_only=True
                        mock_tavus.create_conversation.assert_called_once()
                        call_kwargs = mock_tavus.create_conversation.call_args[1]
                        assert call_kwargs["audio_only"] is True

                        # Verify DB insert includes is_audio_only
                        insert_call = mock_db.table.return_value.insert.call_args[0][0]
                        assert insert_call["is_audio_only"] is True


class TestGetVideoSession:
    """Tests for GET /video/sessions/{id} endpoint."""

    def test_get_session_with_perception(
        self, test_client: TestClient, mock_db: MagicMock
    ) -> None:
        """Verify perception_analysis is returned."""
        perception_data = {
            "engagement_score": 0.85,
            "emotions": {"happy": 0.7, "neutral": 0.3},
        }
        mock_select_result = MagicMock()
        mock_select_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ENDED.value,
            "session_type": SessionType.CHAT.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "duration_seconds": 300,
            "created_at": datetime.now(UTC).isoformat(),
            "lead_id": None,
            "perception_analysis": perception_data,
        }]
        mock_transcript_result = MagicMock()
        mock_transcript_result.data = []

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
                mock_select_result
            )
            mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
                mock_transcript_result
            )

            response = test_client.get("/api/v1/video/sessions/session-123")

            assert response.status_code == 200
            data = response.json()
            assert data["perception_analysis"] == perception_data

    def test_get_session_with_transcripts(
        self, test_client: TestClient, mock_db: MagicMock
    ) -> None:
        """Verify ended session includes transcripts."""
        mock_select_result = MagicMock()
        mock_select_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ENDED.value,
            "session_type": SessionType.CHAT.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "duration_seconds": 300,
            "created_at": datetime.now(UTC).isoformat(),
            "lead_id": None,
            "perception_analysis": {},
        }]
        mock_transcript_result = MagicMock()
        mock_transcript_result.data = [
            {
                "id": "transcript-1",
                "video_session_id": "session-123",
                "speaker": "aria",
                "content": "Hello, how can I help?",
                "timestamp_ms": 0,
                "created_at": datetime.now(UTC).isoformat(),
            },
            {
                "id": "transcript-2",
                "video_session_id": "session-123",
                "speaker": "user",
                "content": "I need help with my pipeline.",
                "timestamp_ms": 2500,
                "created_at": datetime.now(UTC).isoformat(),
            },
        ]

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            # Set up chain for session query
            session_chain = (
                mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value
            )
            session_chain.execute.return_value = mock_select_result

            # Set up chain for transcript query
            transcript_chain = mock_db.table.return_value.select.return_value.eq.return_value.order.return_value
            transcript_chain.execute.return_value = mock_transcript_result

            response = test_client.get("/api/v1/video/sessions/session-123")

            assert response.status_code == 200
            data = response.json()
            assert data["transcripts"] is not None
            assert len(data["transcripts"]) == 2
            assert data["transcripts"][0]["speaker"] == "aria"
            assert data["transcripts"][1]["speaker"] == "user"

    def test_get_session_not_found(self, test_client: TestClient, mock_db: MagicMock) -> None:
        """Verify 404 for non-existent session."""
        mock_select_result = MagicMock()
        mock_select_result.data = []

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
                mock_select_result
            )

            response = test_client.get("/api/v1/video/sessions/nonexistent")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    def test_get_active_session_no_transcripts(
        self, test_client: TestClient, mock_db: MagicMock
    ) -> None:
        """Verify active sessions don't fetch transcripts."""
        mock_select_result = MagicMock()
        mock_select_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ACTIVE.value,
            "session_type": SessionType.CHAT.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": None,
            "duration_seconds": None,
            "created_at": datetime.now(UTC).isoformat(),
            "lead_id": None,
            "perception_analysis": {},
        }]

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
                mock_select_result
            )

            response = test_client.get("/api/v1/video/sessions/session-123")

            assert response.status_code == 200
            data = response.json()
            assert data["transcripts"] is None


class TestListVideoSessions:
    """Tests for GET /video/sessions endpoint."""

    def test_list_sessions_pagination(
        self, test_client: TestClient, mock_db: MagicMock
    ) -> None:
        """Verify limit/offset work correctly."""
        mock_select_result = MagicMock()
        mock_select_result.data = [
            {
                "id": f"session-{i}",
                "user_id": "test-user-123",
                "tavus_conversation_id": f"tavus-{i}",
                "room_url": f"https://daily.co/room/{i}",
                "status": VideoSessionStatus.ENDED.value,
                "session_type": SessionType.CHAT.value,
                "started_at": datetime.now(UTC).isoformat(),
                "ended_at": datetime.now(UTC).isoformat(),
                "duration_seconds": 100 + i,
                "created_at": datetime.now(UTC).isoformat(),
                "lead_id": None,
                "perception_analysis": {},
            }
            for i in range(5)
        ]
        mock_select_result.count = 25

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            # Set up the chain with proper ordering
            chain = mock_db.table.return_value.select.return_value.eq.return_value
            chain.order.return_value.range.return_value.execute.return_value = (
                mock_select_result
            )

            response = test_client.get("/api/v1/video/sessions?limit=5&offset=10")

            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 5
            assert data["total"] == 25
            assert data["limit"] == 5
            assert data["offset"] == 10

    def test_list_sessions_filter_by_type(
        self, test_client: TestClient, mock_db: MagicMock
    ) -> None:
        """Verify session_type filter works."""
        mock_select_result = MagicMock()
        mock_select_result.data = [
            {
                "id": "session-1",
                "user_id": "test-user-123",
                "tavus_conversation_id": "tavus-1",
                "room_url": "https://daily.co/room/1",
                "status": VideoSessionStatus.ENDED.value,
                "session_type": SessionType.BRIEFING.value,
                "started_at": datetime.now(UTC).isoformat(),
                "ended_at": datetime.now(UTC).isoformat(),
                "duration_seconds": 100,
                "created_at": datetime.now(UTC).isoformat(),
                "lead_id": None,
                "perception_analysis": {},
            }
        ]
        mock_select_result.count = 1

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            # Set up chain with session_type filter
            chain = (
                mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value
            )
            chain.order.return_value.range.return_value.execute.return_value = (
                mock_select_result
            )

            response = test_client.get("/api/v1/video/sessions?session_type=briefing")

            assert response.status_code == 200
            data = response.json()
            assert all(item["session_type"] == "briefing" for item in data["items"])

    def test_list_sessions_filter_by_status(
        self, test_client: TestClient, mock_db: MagicMock
    ) -> None:
        """Verify status filter works."""
        mock_select_result = MagicMock()
        mock_select_result.data = [
            {
                "id": "session-1",
                "user_id": "test-user-123",
                "tavus_conversation_id": "tavus-1",
                "room_url": "https://daily.co/room/1",
                "status": VideoSessionStatus.ACTIVE.value,
                "session_type": SessionType.CHAT.value,
                "started_at": datetime.now(UTC).isoformat(),
                "ended_at": None,
                "duration_seconds": None,
                "created_at": datetime.now(UTC).isoformat(),
                "lead_id": None,
                "perception_analysis": {},
            }
        ]
        mock_select_result.count = 1

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            # Set up chain with status filter
            chain = (
                mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value
            )
            chain.order.return_value.range.return_value.execute.return_value = (
                mock_select_result
            )

            response = test_client.get("/api/v1/video/sessions?status=active")

            assert response.status_code == 200
            data = response.json()
            assert all(item["status"] == "active" for item in data["items"])

    def test_list_sessions_empty(
        self, test_client: TestClient, mock_db: MagicMock
    ) -> None:
        """Verify empty list returns empty items."""
        mock_select_result = MagicMock()
        mock_select_result.data = []
        mock_select_result.count = 0

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            chain = mock_db.table.return_value.select.return_value.eq.return_value
            chain.order.return_value.range.return_value.execute.return_value = (
                mock_select_result
            )

            response = test_client.get("/api/v1/video/sessions")

            assert response.status_code == 200
            data = response.json()
            assert data["items"] == []
            assert data["total"] == 0


class TestEndVideoSession:
    """Tests for POST /video/sessions/{id}/end endpoint."""

    def test_end_session_calls_tavus(
        self, test_client: TestClient, mock_tavus: MagicMock, mock_db: MagicMock
    ) -> None:
        """Verify Tavus end_conversation is called."""
        mock_select_result = MagicMock()
        mock_select_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ACTIVE.value,
            "session_type": SessionType.CHAT.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": None,
            "duration_seconds": None,
            "created_at": datetime.now(UTC).isoformat(),
        }]

        mock_update_result = MagicMock()
        mock_update_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ENDED.value,
            "session_type": SessionType.CHAT.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "duration_seconds": 5,
            "created_at": datetime.now(UTC).isoformat(),
            "lead_id": None,
            "perception_analysis": {},
        }]

        with patch.object(_video_mod, "get_tavus_client", return_value=mock_tavus):
            with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
                with patch.object(_video_mod, "ws_manager") as mock_ws:
                    mock_ws.send_to_user = AsyncMock()
                    # Set up select chain
                    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
                        mock_select_result
                    )
                    # Set up update chain
                    mock_db.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
                        mock_update_result
                    )

                    response = test_client.post("/api/v1/video/sessions/session-123/end")

                    assert response.status_code == 200
                    mock_tavus.end_conversation.assert_called_once_with("tavus-conv-123")

    def test_end_session_already_ended(
        self, test_client: TestClient, mock_db: MagicMock
    ) -> None:
        """Verify 400 when trying to end already-ended session."""
        mock_select_result = MagicMock()
        mock_select_result.data = [{
            "id": "session-123",
            "user_id": "test-user-123",
            "tavus_conversation_id": "tavus-conv-123",
            "room_url": "https://daily.co/room/test-room",
            "status": VideoSessionStatus.ENDED.value,
            "session_type": SessionType.CHAT.value,
            "started_at": datetime.now(UTC).isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "duration_seconds": 300,
            "created_at": datetime.now(UTC).isoformat(),
        }]

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
                mock_select_result
            )

            response = test_client.post("/api/v1/video/sessions/session-123/end")

            assert response.status_code == 400
            assert "already ended" in response.json()["detail"].lower()

    def test_end_session_not_found(
        self, test_client: TestClient, mock_db: MagicMock
    ) -> None:
        """Verify 404 for non-existent session."""
        mock_select_result = MagicMock()
        mock_select_result.data = []

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = (
                mock_select_result
            )

            response = test_client.post("/api/v1/video/sessions/nonexistent/end")

            assert response.status_code == 404


class TestUnauthorized:
    """Tests for authentication requirements."""

    def test_unauthorized_create(self) -> None:
        """Verify 401 without auth token on create."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post("/api/v1/video/sessions", json={})
        assert response.status_code == 401

    def test_unauthorized_list(self) -> None:
        """Verify 401 without auth token on list."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/video/sessions")
        assert response.status_code == 401

    def test_unauthorized_get(self) -> None:
        """Verify 401 without auth token on get."""
        app = create_test_app()
        client = TestClient(app)
        response = client.get("/api/v1/video/sessions/session-123")
        assert response.status_code == 401

    def test_unauthorized_end(self) -> None:
        """Verify 401 without auth token on end."""
        app = create_test_app()
        client = TestClient(app)
        response = client.post("/api/v1/video/sessions/session-123/end")
        assert response.status_code == 401


class TestBuildAriaContext:
    """Tests for the build_aria_context helper function."""

    @pytest.mark.asyncio
    async def test_build_context_with_lead(self, mock_db: MagicMock) -> None:
        """Test that lead context is included when lead_id provided."""
        profile_result = MagicMock()
        profile_result.data = {
            "full_name": "John Doe",
            "title": "Sales Manager",
            "role": "Sales Manager",
            "companies": {"name": "Acme Corp"},
        }

        goals_result = MagicMock()
        goals_result.data = [
            {"title": "Close Q1 deals", "status": "active", "priority": 1},
        ]

        lead_result = MagicMock()
        lead_result.data = [{
            "company_name": "Target Corp",
            "contact_name": "Jane Smith",
            "status": "qualified",
            "priority": "high",
        }]

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            # Set up different query chains
            def table_side_effect(table_name: str):
                mock_chain = MagicMock()
                if table_name == "user_profiles":
                    mock_chain.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
                        profile_result
                    )
                elif table_name == "goals":
                    mock_chain.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
                        goals_result
                    )
                elif table_name == "leads":
                    mock_chain.select.return_value.eq.return_value.execute.return_value = (
                        lead_result
                    )
                return mock_chain

            mock_db.table.side_effect = table_side_effect

            context = await _video_mod.build_aria_context(
                user_id="user-123",
                session_type="consultation",
                lead_id="lead-456",
            )

            assert "John Doe" in context
            assert "Acme Corp" in context
            assert "Target Corp" in context
            assert "Jane Smith" in context
            assert "consultation" in context.lower()

    @pytest.mark.asyncio
    async def test_build_context_without_lead(self, mock_db: MagicMock) -> None:
        """Test that context is built without lead when no lead_id."""
        profile_result = MagicMock()
        profile_result.data = {
            "full_name": "Jane Smith",
            "title": "Account Executive",
            "role": "Account Executive",
            "companies": {"name": "Tech Inc"},
        }

        goals_result = MagicMock()
        goals_result.data = []

        with patch.object(_video_mod, "get_supabase_client", return_value=mock_db):
            def table_side_effect(table_name: str):
                mock_chain = MagicMock()
                if table_name == "user_profiles":
                    mock_chain.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value = (
                        profile_result
                    )
                elif table_name == "goals":
                    mock_chain.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
                        goals_result
                    )
                return mock_chain

            mock_db.table.side_effect = table_side_effect

            context = await _video_mod.build_aria_context(
                user_id="user-123",
                session_type="briefing",
                lead_id=None,
            )

            assert "Jane Smith" in context
            assert "Tech Inc" in context
            assert "briefing" in context.lower()
            # Should not have lead-specific info
            assert "Lead Company" not in context
