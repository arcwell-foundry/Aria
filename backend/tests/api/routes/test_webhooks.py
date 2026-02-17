"""Tests for Tavus webhook API routes."""

import asyncio
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
    """Tests for conversation.tool_call event handling with execution."""

    def _make_mock_db(self, user_id: str = "user-123") -> MagicMock:
        """Create a mock DB that returns user_id from video_sessions."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": "session-123", "user_id": user_id}]
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "activity-123"}]
        )
        return mock_db

    def test_tool_call_executes_and_returns_result(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that tool_call event executes the tool and returns the result."""
        mock_db = self._make_mock_db()
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = "I found 3 companies matching your criteria."

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                with patch(
                    "src.integrations.tavus_tool_executor.VideoToolExecutor",
                    return_value=mock_executor,
                ):
                    response = test_client.post(
                        "/api/v1/webhooks/tavus",
                        json={
                            "event_type": "conversation.tool_call",
                            "conversation_id": "conv-exec-123",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "tool_name": "search_companies",
                            "tool_call_id": "tc-001",
                            "args": {"query": "biotech"},
                        },
                    )

                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "ok"
                    assert "tool_result" in data
                    assert data["tool_result"]["tool_name"] == "search_companies"
                    assert data["tool_result"]["tool_call_id"] == "tc-001"
                    assert "3 companies" in data["tool_result"]["result"]

    def test_tool_call_logs_activity_with_duration(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that tool execution logs to aria_activity with duration_ms."""
        mock_db = self._make_mock_db()
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = "Here's the battle card for Lonza."

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                with patch(
                    "src.integrations.tavus_tool_executor.VideoToolExecutor",
                    return_value=mock_executor,
                ):
                    response = test_client.post(
                        "/api/v1/webhooks/tavus",
                        json={
                            "event_type": "conversation.tool_call",
                            "conversation_id": "conv-log-123",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "tool_name": "get_battle_card",
                            "args": {"competitor_name": "Lonza"},
                        },
                    )

                    assert response.status_code == 200

                    # Find the aria_activity insert call (not the session lookup)
                    insert_calls = [
                        call
                        for call in mock_db.table.call_args_list
                        if call.args == ("aria_activity",)
                    ]
                    assert len(insert_calls) >= 1, "aria_activity insert should be called"

    def test_tool_call_no_user_returns_ok_without_result(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that tool_call with no user_id returns ok but no tool_result."""
        mock_db = MagicMock()
        # Return empty session data — no user_id found
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
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
                        "conversation_id": "conv-no-user",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "tool_name": "search_companies",
                        "args": {"query": "biotech"},
                    },
                )

                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
                # No tool_result when user_id is missing
                assert "tool_result" not in data

    def test_tool_call_parses_json_string_arguments(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that tool_call handles JSON string arguments from Tavus."""
        mock_db = self._make_mock_db()
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = "Found results."

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                with patch(
                    "src.integrations.tavus_tool_executor.VideoToolExecutor",
                    return_value=mock_executor,
                ):
                    response = test_client.post(
                        "/api/v1/webhooks/tavus",
                        json={
                            "event_type": "conversation.tool_call",
                            "conversation_id": "conv-json-args",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "tool_name": "search_companies",
                            "arguments": '{"query": "pharma"}',
                        },
                    )

                    assert response.status_code == 200
                    assert "tool_result" in response.json()

    def test_tool_call_timeout_retries_once(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that tool execution retries once on timeout."""
        mock_db = self._make_mock_db()

        call_count = 0

        async def slow_then_fast(tool_name: str, arguments: dict) -> str:  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(20)  # Will be cancelled by timeout
            return "Done on retry."

        mock_executor = MagicMock()
        mock_executor.execute = slow_then_fast

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                with patch(
                    "src.integrations.tavus_tool_executor.VideoToolExecutor",
                    return_value=mock_executor,
                ):
                    # Reduce timeout for faster test
                    with patch.object(_webhooks_mod, "TOOL_EXECUTION_TIMEOUT", 0.1):
                        response = test_client.post(
                            "/api/v1/webhooks/tavus",
                            json={
                                "event_type": "conversation.tool_call",
                                "conversation_id": "conv-timeout",
                                "timestamp": datetime.now(UTC).isoformat(),
                                "tool_name": "search_pubmed",
                                "args": {"query": "mRNA"},
                            },
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert data["status"] == "ok"
                        assert "tool_result" in data
                        assert data["tool_result"]["result"] == "Done on retry."

    def test_tool_call_double_timeout_returns_graceful_message(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that double timeout returns a graceful failure message."""
        mock_db = self._make_mock_db()

        async def always_slow(tool_name: str, arguments: dict) -> str:  # noqa: ARG001
            await asyncio.sleep(20)
            return "Never reached"

        mock_executor = MagicMock()
        mock_executor.execute = always_slow

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                with patch(
                    "src.integrations.tavus_tool_executor.VideoToolExecutor",
                    return_value=mock_executor,
                ):
                    with patch.object(_webhooks_mod, "TOOL_EXECUTION_TIMEOUT", 0.1):
                        response = test_client.post(
                            "/api/v1/webhooks/tavus",
                            json={
                                "event_type": "conversation.tool_call",
                                "conversation_id": "conv-double-timeout",
                                "timestamp": datetime.now(UTC).isoformat(),
                                "tool_name": "search_clinical_trials",
                                "args": {"condition": "cancer"},
                            },
                        )

                        assert response.status_code == 200
                        data = response.json()
                        assert "tool_result" in data
                        assert "having trouble" in data["tool_result"]["result"]

    def test_tool_call_does_not_double_log_webhook_activity(
        self,
        test_client: TestClient,
    ) -> None:
        """Test that tool_call event skips the generic webhook activity log."""
        mock_db = self._make_mock_db()
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = "Result here."

        with patch.object(_webhooks_mod, "verify_webhook_secret", return_value=True):
            with patch.object(_webhooks_mod, "get_supabase_client", return_value=mock_db):
                with patch(
                    "src.integrations.tavus_tool_executor.VideoToolExecutor",
                    return_value=mock_executor,
                ):
                    response = test_client.post(
                        "/api/v1/webhooks/tavus",
                        json={
                            "event_type": "conversation.tool_call",
                            "conversation_id": "conv-no-double-log",
                            "timestamp": datetime.now(UTC).isoformat(),
                            "tool_name": "get_pipeline_summary",
                            "args": {},
                        },
                    )

                    assert response.status_code == 200

                    # The generic webhook.conversation.tool_call activity
                    # should NOT be inserted — only the handler's video_tool_call
                    insert_calls = mock_db.table.return_value.insert.call_args_list
                    for call in insert_calls:
                        if call.args:
                            row = call.args[0]
                            if isinstance(row, dict) and row.get("activity_type", "").startswith("webhook."):
                                pytest.fail(
                                    "Generic webhook activity log should be skipped for tool_call events"
                                )


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
