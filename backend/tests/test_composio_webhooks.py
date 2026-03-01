"""Tests for Composio webhook ingestion endpoint."""

import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.api.routes.composio_webhooks import router, COMPOSIO_TRIGGER_MAP
from src.services.event_trigger import EventTriggerService, EventType


@pytest.fixture
def mock_event_service():
    service = MagicMock(spec=EventTriggerService)
    service.ingest = AsyncMock(return_value={
        "status": "processed", "event_log_id": "evt-001", "latency_ms": 15,
    })
    return service


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Default: resolve user from composio_connection_id
    db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"user_id": "user-001"}]
    )
    return db


@pytest.fixture
def app(mock_event_service, mock_db):
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    test_app.state.event_trigger_service = mock_event_service
    test_app.state.db = mock_db
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestComposioWebhook:
    def test_gmail_webhook_accepted(self, client, mock_event_service):
        payload = {
            "trigger_name": "GMAIL_NEW_GMAIL_MESSAGE",
            "trigger_id": "trig-001",
            "connected_account_id": "conn-abc",
            "payload": {
                "id": "msg-gmail-001",
                "sender": "sarah@lonza.com",
                "subject": "PFA Pricing",
                "snippet": "Thanks for following up...",
            },
        }
        resp = client.post("/api/v1/webhooks/composio", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
        mock_event_service.ingest.assert_called_once()

    def test_calendar_webhook_accepted(self, client, mock_event_service):
        payload = {
            "trigger_name": "GOOGLECALENDAR_EVENT_CREATED",
            "trigger_id": "trig-002",
            "connected_account_id": "conn-abc",
            "payload": {
                "id": "cal-001",
                "summary": "Q1 Review",
                "start": {"dateTime": "2026-03-02T10:00:00Z"},
            },
        }
        resp = client.post("/api/v1/webhooks/composio", json=payload)
        assert resp.status_code == 200

    def test_unknown_trigger_still_accepted(self, client, mock_event_service):
        payload = {
            "trigger_name": "UNKNOWN_TRIGGER_TYPE",
            "trigger_id": "trig-003",
            "connected_account_id": "conn-abc",
            "payload": {"data": "some data"},
        }
        resp = client.post("/api/v1/webhooks/composio", json=payload)
        assert resp.status_code == 200

    def test_unresolvable_user_returns_200(self, client, mock_db):
        # No user found for this connected_account_id
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        payload = {
            "trigger_name": "GMAIL_NEW_GMAIL_MESSAGE",
            "trigger_id": "trig-004",
            "connected_account_id": "conn-unknown",
            "payload": {"id": "msg-002"},
        }
        resp = client.post("/api/v1/webhooks/composio", json=payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "user_not_found"

    def test_invalid_json_returns_400(self, client):
        resp = client.post(
            "/api/v1/webhooks/composio",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    def test_trigger_map_covers_main_integrations(self):
        assert "GMAIL_NEW_GMAIL_MESSAGE" in COMPOSIO_TRIGGER_MAP
        assert "OUTLOOK_NEW_EMAIL" in COMPOSIO_TRIGGER_MAP
        assert "GOOGLECALENDAR_EVENT_CREATED" in COMPOSIO_TRIGGER_MAP
        assert "SALESFORCE_NEW_LEAD" in COMPOSIO_TRIGGER_MAP
        assert "HUBSPOT_DEAL_STAGE_CHANGED" in COMPOSIO_TRIGGER_MAP
        assert "SLACK_RECEIVE_MESSAGE" in COMPOSIO_TRIGGER_MAP
