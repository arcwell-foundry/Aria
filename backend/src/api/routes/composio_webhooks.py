"""Composio webhook ingestion endpoint for event triggers.

Receives POST requests from Composio when triggers fire
(new email, calendar change, CRM update, etc.).

Security: Verify HMAC signature using COMPOSIO_WEBHOOK_SECRET env var.
No JWT auth — Composio can't send JWTs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from src.services.event_trigger import (
    EventEnvelope,
    EventSource,
    EventTriggerService,
    EventType,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["composio-webhooks"])

COMPOSIO_TRIGGER_MAP: dict[str, EventType] = {
    "GMAIL_NEW_GMAIL_MESSAGE": EventType.EMAIL_RECEIVED,
    "GMAIL_NEW_GMAIL_THREAD": EventType.EMAIL_THREAD_REPLY,
    "OUTLOOK_NEW_EMAIL": EventType.EMAIL_RECEIVED,
    "OUTLOOK_NEW_CALENDAR_EVENT": EventType.CALENDAR_EVENT_CREATED,
    "OUTLOOK_CALENDAR_EVENT_UPDATED": EventType.CALENDAR_EVENT_UPDATED,
    "GOOGLECALENDAR_EVENT_CREATED": EventType.CALENDAR_EVENT_CREATED,
    "GOOGLECALENDAR_EVENT_UPDATED": EventType.CALENDAR_EVENT_UPDATED,
    "GOOGLECALENDAR_EVENT_DELETED": EventType.CALENDAR_EVENT_DELETED,
    "SALESFORCE_NEW_LEAD": EventType.CRM_LEAD_CREATED,
    "SALESFORCE_LEAD_UPDATED": EventType.CRM_LEAD_UPDATED,
    "SALESFORCE_OPPORTUNITY_STAGE_CHANGED": EventType.CRM_DEAL_STAGE_CHANGED,
    "HUBSPOT_NEW_CONTACT": EventType.CRM_CONTACT_UPDATED,
    "HUBSPOT_DEAL_STAGE_CHANGED": EventType.CRM_DEAL_STAGE_CHANGED,
    "SLACK_RECEIVE_MESSAGE": EventType.SLACK_MESSAGE_RECEIVED,
    "SLACK_RECEIVE_MENTION": EventType.SLACK_MENTION,
}


def _verify_composio_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """Verify Composio webhook HMAC-SHA256 signature."""
    if not signature:
        return False
    computed = hmac.new(secret.encode(), payload_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, signature)


@router.post("/composio")
async def handle_composio_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(None, alias="x-webhook-signature"),
) -> dict[str, Any]:
    """Receive webhook from Composio when a trigger fires.

    Always returns 200 to prevent Composio from retrying.
    Errors are logged internally in event_log.
    """
    body = await request.body()

    # Verify signature if secret is configured
    webhook_secret = os.getenv("COMPOSIO_WEBHOOK_SECRET")
    if webhook_secret and x_webhook_signature:
        if not _verify_composio_signature(body, x_webhook_signature, webhook_secret):
            logger.warning("Invalid Composio webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid JSON")

    trigger_name = data.get("trigger_name", "")
    trigger_id = data.get("trigger_id", "")
    connected_account_id = data.get("connected_account_id", "")
    payload = data.get("payload", {})

    logger.info("Composio webhook received: %s (trigger_id=%s)", trigger_name, trigger_id)

    # Map trigger to ARIA event type
    event_type: EventType | str = COMPOSIO_TRIGGER_MAP.get(trigger_name, f"composio.{trigger_name.lower()}")

    # Resolve user_id from connected_account_id
    db = request.app.state.db
    user_id = _resolve_user_id(db, connected_account_id)
    if not user_id:
        logger.error("Cannot resolve user for connected_account_id: %s", connected_account_id)
        return {"status": "user_not_found", "connected_account_id": connected_account_id}

    source_id = _extract_source_id(trigger_name, payload)

    envelope = EventEnvelope(
        event_type=event_type,
        source=EventSource.COMPOSIO,
        user_id=user_id,
        source_id=source_id,
        payload=payload,
        metadata={
            "trigger_name": trigger_name,
            "trigger_id": trigger_id,
            "connected_account_id": connected_account_id,
        },
    )

    event_service: EventTriggerService = request.app.state.event_trigger_service
    result = await event_service.ingest(envelope)

    return {"status": "accepted", "result": result}


def _resolve_user_id(db: Any, connected_account_id: str) -> str | None:
    """Look up ARIA user_id from Composio connected_account_id."""
    try:
        # Check composio_connection_id in user_integrations
        result = db.table("user_integrations") \
            .select("user_id") \
            .eq("composio_connection_id", connected_account_id) \
            .limit(1) \
            .execute()
        if result.data:
            return result.data[0]["user_id"]

        # Fallback: check composio_account_id
        result = db.table("user_integrations") \
            .select("user_id") \
            .eq("composio_account_id", connected_account_id) \
            .limit(1) \
            .execute()
        if result.data:
            return result.data[0]["user_id"]
    except Exception as e:
        logger.error("User resolution failed: %s", e)

    return None


def _extract_source_id(trigger_name: str, payload: dict) -> str:
    """Extract a stable unique ID from the event payload for deduplication."""
    if "GMAIL" in trigger_name:
        return payload.get("id", payload.get("messageId", ""))
    elif "OUTLOOK" in trigger_name:
        return payload.get("id", payload.get("internetMessageId", ""))
    elif "CALENDAR" in trigger_name or "GOOGLECALENDAR" in trigger_name:
        return payload.get("id", payload.get("eventId", ""))
    elif "SALESFORCE" in trigger_name:
        return payload.get("Id", payload.get("id", ""))
    elif "HUBSPOT" in trigger_name:
        return payload.get("objectId", payload.get("id", ""))
    elif "SLACK" in trigger_name:
        return payload.get("ts", payload.get("event_ts", ""))
    return ""
