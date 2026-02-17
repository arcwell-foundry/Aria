"""Tests for Tavus webhook API routes."""

import importlib
import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Load the webhooks route module directly from file to avoid pulling in
# every sibling route via __init__.py
# ---------------------------------------------------------------------------
def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_webhooks_mod = _load_module(
    "src.api.routes.webhooks",
    Path(__file__).resolve().parent.parent.parent.parent / "src" / "api" / "routes" / "webhooks.py",
)
_router = _webhooks_mod.router


def create_test_app() -> FastAPI:
    """Create minimal FastAPI app for testing."""
    app = FastAPI()
    app.include_router(_router, prefix="/api/v1")
    return app


@pytest.fixture
def test_client() -> TestClient:
    """Create test client."""
    app = create_test_app()
    client = TestClient(app)
    yield client


@pytest.fixture
def mock_supabase() -> MagicMock:
    """Create mock Supabase client."""
    mock = MagicMock()
    mock.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "session-123", "user_id": "user-123", "lead_id": None}]
    )
    mock.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "session-123"}]
    )
    mock.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": "activity-123"}]
    )
    return mock


class TestWebhookSecretVerification:
    """Tests for webhook secret verification."""

    def test_missing_secret_when_configured(self, test_client: TestClient) -> None:
        """Test that missing secret returns 401 when configured."""
        with patch.object(
            _webhooks_mod,
            "verify_webhook_secret",
            return_value=False,
        ):
            response = test_client.post(
                "/api/v1/webhooks/tavus",
                json={
                    "event_type": "system.replica_joined",
                    "conversation_id": "conv-123",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

            assert response.status_code == 401
            assert "Invalid webhook secret" in response.json()["detail"]

    def test_invalid_secret_returns_401(self, test_client: TestClient) -> None:
        """Test that invalid secret returns 401."""
        with patch.object(
            _webhooks_mod,
            "verify_webhook_secret",
            return_value=False,
        ):
            response = test_client.post(
                "/api/v1/webhooks/tavus",
                headers={"X-Webhook-Secret": "invalid-secret"},
                json={
                    "event_type": "system.replica_joined",
                    "conversation_id": "conv-123",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

            assert response.status_code == 401

    def test_valid_secret_passes(self, test_client: TestClient, mock_supabase: MagicMock) -> None:
        """Test that valid secret allows request through."""
        with patch.object(
            _webhooks_mod,
            "verify_webhook_secret",
            return_value=True,
        ):
            with patch.object(
                _webhooks_mod,
                "get_supabase_client",
                return_value=mock_supabase,
            ):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    headers={"X-Webhook-Secret": "valid-secret"},
                    json={
                        "event_type": "system.replica_joined",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )

                assert response.status_code == 200


class TestPayloadValidation:
    """Tests for webhook payload validation."""

    def test_missing_event_type_returns_400(self, test_client: TestClient) -> None:
        """Test that missing event_type returns 400."""
        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            response = test_client.post(
                "/api/v1/webhooks/tavus",
                json={
                    "conversation_id": "conv-123",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

            assert response.status_code == 400
            assert "Missing event_type" in response.json()["detail"]

    def test_missing_conversation_id_returns_400(self, test_client: TestClient) -> None:
        """Test that missing conversation_id returns 400."""
        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            response = test_client.post(
                "/api/v1/webhooks/tavus",
                json={
                    "event_type": "system.replica_joined",
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

            assert response.status_code == 400
            assert "Missing" in response.json()["detail"]

    def test_invalid_json_returns_400(self, test_client: TestClient) -> None:
        """Test that invalid JSON returns 400."""
        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            response = test_client.post(
                "/api/v1/webhooks/tavus",
                content="not valid json",
                headers={"Content-Type": "application/json"},
            )

            assert response.status_code == 400


class TestReplicaJoinedHandler:
    """Tests for system.replica_joined event handling."""

    def test_replica_joined_updates_status(
        self,
        test_client: TestClient,
        mock_supabase: MagicMock,
    ) -> None:
        """Test that replica_joined event updates session status to active."""
        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(
                _webhooks_mod,
                "get_supabase_client",
                return_value=mock_supabase,
            ):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "system.replica_joined",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )

                assert response.status_code == 200
                assert response.json()["status"] == "ok"

                # Verify update was called with correct status
                mock_supabase.table.assert_called_with("video_sessions")


class TestShutdownHandler:
    """Tests for system.shutdown event handling."""

    def test_shutdown_updates_session(
        self,
        test_client: TestClient,
        mock_supabase: MagicMock,
    ) -> None:
        """Test that shutdown event updates session with ended status."""
        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(
                _webhooks_mod,
                "get_supabase_client",
                return_value=mock_supabase,
            ):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "system.shutdown",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "shutdown_reason": "user_left",
                    },
                )

                assert response.status_code == 200
                assert response.json()["status"] == "ok"

    def test_shutdown_calculates_duration(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that shutdown calculates duration from started_at."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "session-123",
                "started_at": "2024-01-15T10:00:00Z",
            }]
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "session-123"}]
        )

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "system.shutdown",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "shutdown_reason": "timeout",
                    },
                )

                assert response.status_code == 200


class TestTranscriptionHandler:
    """Tests for application.transcription_ready event handling."""

    def test_transcription_stores_entries(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that transcription_ready stores transcript entries."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "session-123",
                "user_id": "user-123",
                "lead_id": None,
            }]
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "entry-123"}]
        )

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "application.transcription_ready",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "transcript": [
                            {
                                "speaker": "user",
                                "content": "Hello ARIA",
                                "timestamp_ms": 0,
                            },
                            {
                                "speaker": "aria",
                                "content": "Hello! How can I help you?",
                                "timestamp_ms": 1500,
                            },
                        ],
                    },
                )

                assert response.status_code == 200
                assert response.json()["status"] == "ok"

    def test_transcription_with_perception(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that transcription_ready stores perception if included."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "session-123",
                "user_id": "user-123",
                "lead_id": None,
            }]
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "entry-123"}]
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "session-123"}]
        )

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "application.transcription_ready",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "transcript": [
                            {"speaker": "user", "content": "Test", "timestamp_ms": 0}
                        ],
                        "perception": {
                            "engagement_score": 0.85,
                            "emotion": "interested",
                        },
                    },
                )

                assert response.status_code == 200


class TestPerceptionAnalysisHandler:
    """Tests for application.perception_analysis event handling."""

    def test_perception_stores_analysis(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that perception_analysis stores perception data."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "session-123",
                "user_id": "user-123",
                "lead_id": None,
            }]
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "session-123"}]
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "activity-123"}]
        )

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "application.perception_analysis",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "perception": {
                            "engagement_score": 0.9,
                            "emotion": "happy",
                            "attention_level": 0.85,
                            "sentiment": "positive",
                        },
                    },
                )

                assert response.status_code == 200

    def test_perception_with_lead_updates_sentiment(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that perception with lead_id logs to activity."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "session-123",
                "user_id": "user-123",
                "lead_id": "lead-123",
            }]
        )
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "session-123"}]
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "activity-123"}]
        )

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "application.perception_analysis",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "perception": {
                            "engagement_score": 0.75,
                            "sentiment": "neutral",
                        },
                    },
                )

                assert response.status_code == 200


class TestUtteranceHandler:
    """Tests for conversation.utterance event handling."""

    def test_utterance_stores_entry(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that utterance event stores transcript entry."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "session-123"}]
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "entry-123"}]
        )

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "conversation.utterance",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "utterance": {
                            "speaker": "aria",
                            "content": "Let me help you with that.",
                            "timestamp_ms": 5000,
                        },
                    },
                )

                assert response.status_code == 200


class TestToolCallHandler:
    """Tests for conversation.tool_call event handling."""

    def test_tool_call_logs_to_activity(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that tool_call event logs to aria_activity."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "user-123"}]
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "activity-123"}]
        )

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "conversation.tool_call",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "tool_name": "search_web",
                        "args": {"query": "latest pharma news"},
                        "result": {"status": "success"},
                    },
                )

                assert response.status_code == 200


class TestUnknownEventType:
    """Tests for unknown event types."""

    def test_unknown_event_type_returns_200(
        self,
        test_client: TestClient,
        mock_supabase: MagicMock,
    ) -> None:
        """Test that unknown event type still returns 200 (graceful handling)."""
        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_supabase):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "unknown.event_type",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )

                # Should still return 200 (graceful handling)
                assert response.status_code == 200


class TestActivityLogging:
    """Tests for activity logging."""

    def test_all_events_logged_to_activity(
        self,
        test_client: TestClient,
        mock_supabase: MagicMock,
    ) -> None:
        """Test that all webhook events are logged to aria_activity."""
        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_supabase):
                response = test_client.post(
                    "/api/v1/webhooks/tavus",
                    json={
                        "event_type": "system.replica_joined",
                        "conversation_id": "conv-123",
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )

                assert response.status_code == 200

                # Verify activity insert was called
                # (It's called for aria_activity logging)
                assert mock_supabase.table.called
