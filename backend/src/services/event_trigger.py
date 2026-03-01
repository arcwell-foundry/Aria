"""EventTriggerService — Central event router for ARIA.

All events (external webhooks + internal signals) flow through this service.
It classifies, routes to handlers, emits to Pulse Engine, and delivers via WebSocket.

Flow: Event arrives → ingest() → classify() → route to handler → emit to Pulse → deliver
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4
import time
import re
import logging

logger = logging.getLogger(__name__)


class EventSource(str, Enum):
    COMPOSIO = "composio"
    INTERNAL = "internal"
    RECONCILIATION = "reconciliation"


class EventType(str, Enum):
    # External — email
    EMAIL_RECEIVED = "email.received"
    EMAIL_SENT = "email.sent"
    EMAIL_THREAD_REPLY = "email.thread_reply"
    # External — calendar
    CALENDAR_EVENT_CREATED = "calendar.event_created"
    CALENDAR_EVENT_UPDATED = "calendar.event_updated"
    CALENDAR_EVENT_DELETED = "calendar.event_deleted"
    CALENDAR_EVENT_REMINDER = "calendar.event_reminder"
    # External — CRM
    CRM_LEAD_CREATED = "crm.lead_created"
    CRM_LEAD_UPDATED = "crm.lead_updated"
    CRM_DEAL_STAGE_CHANGED = "crm.deal_stage_changed"
    CRM_CONTACT_UPDATED = "crm.contact_updated"
    # External — Slack
    SLACK_MESSAGE_RECEIVED = "slack.message_received"
    SLACK_MENTION = "slack.mention"
    # Internal
    GOAL_COMPLETED = "goal.completed"
    GOAL_BLOCKED = "goal.blocked"
    AGENT_TASK_FINISHED = "agent.task_finished"
    DRAFT_APPROVED = "draft.approved"
    DRAFT_REJECTED = "draft.rejected"
    ACTION_APPROVED = "action.approved"
    ACTION_REJECTED = "action.rejected"
    # System
    RECONCILIATION_FOUND = "reconciliation.found"


@dataclass
class EventEnvelope:
    """Typed container for all events flowing through the system."""
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: EventType | str = ""
    source: EventSource = EventSource.COMPOSIO
    user_id: str = ""
    source_id: str = ""
    payload: dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)


@dataclass
class EventClassification:
    """Result of fast, no-LLM classification."""
    event_type: str
    priority_hint: str = "normal"
    matched_leads: list[str] = field(default_factory=list)
    matched_goals: list[str] = field(default_factory=list)
    matched_contacts: list[str] = field(default_factory=list)
    is_vip_sender: bool = False
    handler_key: str = ""
    skip_processing: bool = False
    skip_reason: str = ""


@dataclass
class HandlerOutput:
    """Result from a domain-specific handler."""
    artifacts: list[dict] = field(default_factory=list)
    signals: list[dict] = field(default_factory=list)
    actions: list[dict] = field(default_factory=list)
    summary: str = ""
    error: str = ""


class EventTriggerService:
    """Central event router. All events flow through here.

    Usage:
        service = EventTriggerService(db, ws_manager, pulse_engine)
        service.register_handler("email", EmailEventHandler())

        # From webhook:
        await service.ingest(envelope)

        # From internal code:
        await service.emit_internal(EventType.GOAL_COMPLETED, user_id, payload)
    """

    def __init__(self, db: Any, ws_manager: Any, pulse_engine: Any = None) -> None:
        self.db = db
        self.ws_manager = ws_manager
        self.pulse_engine = pulse_engine
        self._handlers: dict[str, Any] = {}
        self._vip_cache: dict[str, set] = {}
        self._active_goals_cache: dict[str, list] = {}
        self._lead_contacts_cache: dict[str, dict] = {}

    def register_handler(self, key: str, handler: Any) -> None:
        self._handlers[key] = handler
        logger.info("Registered event handler: %s", key)

    async def ingest(self, envelope: EventEnvelope) -> dict:
        """Main entry point. Process an event through the full pipeline."""
        start_time = time.time()
        event_log_id = None

        try:
            # 0. Deduplicate
            if envelope.source_id:
                existing = self._check_duplicate(envelope)
                if existing:
                    logger.info("Duplicate event skipped: %s", envelope.source_id)
                    return {"status": "duplicate", "existing_id": existing}

            # 1. Log receipt
            event_log_id = self._log_event(envelope, "received")

            # 2. Fast classify (no LLM, <10ms)
            classification = await self._classify(envelope)
            self._update_event_log(event_log_id, "classified", classification=classification)

            if classification.skip_processing:
                self._update_event_log(
                    event_log_id, "skipped",
                    handler_result={"skip_reason": classification.skip_reason},
                )
                return {"status": "skipped", "reason": classification.skip_reason}

            # 3. Route to handler
            handler = self._handlers.get(classification.handler_key)
            if not handler:
                logger.warning("No handler for key: %s", classification.handler_key)
                self._update_event_log(event_log_id, "no_handler")
                return {"status": "no_handler", "handler_key": classification.handler_key}

            self._update_event_log(event_log_id, "processing")
            handler_output = await handler.process(envelope, classification)
            self._update_event_log(event_log_id, "handled", handler_result=handler_output.__dict__)

            # 4. Always notify user immediately via WebSocket
            await self._deliver_direct(envelope.user_id, handler_output, classification)
            self._update_event_log(event_log_id, "delivered")

            # 5. Also emit to Pulse Engine for bundling/briefing strategy
            if self.pulse_engine and handler_output.signals:
                for signal_data in handler_output.signals:
                    try:
                        pulse_signal_id = await self._emit_to_pulse(
                            envelope.user_id, signal_data, classification,
                        )
                        if pulse_signal_id:
                            self._update_event_log(
                                event_log_id, "delivered",
                                pulse_signal_id=pulse_signal_id,
                            )
                    except Exception as e:
                        logger.error("Pulse emission failed: %s", e)

            latency_ms = int((time.time() - start_time) * 1000)
            self._update_event_log(event_log_id, latency_ms=latency_ms)

            logger.info(
                "Event processed: %s for user %s in %dms (handler=%s, priority=%s)",
                envelope.event_type, envelope.user_id[:8], latency_ms,
                classification.handler_key, classification.priority_hint,
            )

            return {
                "status": "processed",
                "event_log_id": event_log_id,
                "latency_ms": latency_ms,
                "handler": classification.handler_key,
                "priority": classification.priority_hint,
                "artifacts_count": len(handler_output.artifacts),
                "signals_count": len(handler_output.signals),
            }

        except Exception as e:
            logger.error("Event processing failed: %s", e, exc_info=True)
            if event_log_id:
                self._update_event_log(event_log_id, "failed", error=str(e))
            return {"status": "failed", "error": str(e)}

    async def emit_internal(self, event_type: EventType, user_id: str, payload: dict) -> dict:
        """Convenience method for internal events."""
        envelope = EventEnvelope(
            event_type=event_type,
            source=EventSource.INTERNAL,
            user_id=user_id,
            payload=payload,
        )
        return await self.ingest(envelope)

    # ── Fast classify (rules + regex, no LLM) ─────────────────────────

    async def _classify(self, envelope: EventEnvelope) -> EventClassification:
        """Classify event using rules + regex. NO LLM. Target: <10ms."""
        event_type = getattr(envelope.event_type, "value", envelope.event_type)
        payload = envelope.payload
        classification = EventClassification(event_type=event_type)

        # Handler routing from event type prefix
        if event_type.startswith("email."):
            classification.handler_key = "email"
        elif event_type.startswith("calendar."):
            classification.handler_key = "calendar"
        elif event_type.startswith("crm."):
            classification.handler_key = "crm"
        elif event_type.startswith("slack."):
            classification.handler_key = "slack"
        elif event_type.startswith("goal.") or event_type.startswith("agent."):
            classification.handler_key = "internal"
        elif event_type.startswith("draft.") or event_type.startswith("action."):
            classification.handler_key = "action"
        else:
            classification.handler_key = "default"

        # Email-specific
        if classification.handler_key == "email":
            sender = payload.get("sender", payload.get("from", "")).lower()
            subject = payload.get("subject", "")

            # Check against active leads (stakeholder emails)
            lead_contacts = self._get_lead_contacts(envelope.user_id)
            if sender in lead_contacts:
                classification.matched_leads.append(lead_contacts[sender])
                classification.priority_hint = "high"

            # Check against active goals
            active_goals = self._get_active_goals(envelope.user_id)
            for goal in active_goals:
                goal_keywords = goal.get("keywords", [])
                if any(kw.lower() in subject.lower() for kw in goal_keywords if kw):
                    classification.matched_goals.append(goal["id"])

            # Urgency keywords
            urgency_patterns = r"\b(urgent|asap|eod|deadline|immediately|critical|time.?sensitive)\b"
            if re.search(urgency_patterns, subject, re.IGNORECASE):
                classification.priority_hint = "urgent"

            # Noise detection
            noise_patterns = [
                r"unsubscribe", r"noreply@", r"no-reply@",
                r"newsletter", r"automated.?message", r"do.?not.?reply",
            ]
            sender_plus_body = sender + " " + payload.get("snippet", "")
            if any(re.search(p, sender_plus_body, re.IGNORECASE) for p in noise_patterns):
                classification.priority_hint = "low"

        # Calendar-specific
        elif classification.handler_key == "calendar":
            if payload.get("status") == "cancelled":
                classification.priority_hint = "high"

        # CRM-specific
        elif classification.handler_key == "crm":
            if event_type == EventType.CRM_DEAL_STAGE_CHANGED:
                classification.priority_hint = "high"

        return classification

    # ── Cached lookups ─────────────────────────────────────────────────

    def _get_lead_contacts(self, user_id: str) -> dict:
        """Get lead stakeholder email → lead_id mapping. Cached."""
        if user_id in self._lead_contacts_cache:
            return self._lead_contacts_cache[user_id]

        try:
            # Join stakeholders with active leads
            result = self.db.table("lead_memory_stakeholders") \
                .select("contact_email, lead_memory_id, lead_memories!inner(user_id, status)") \
                .eq("lead_memories.user_id", user_id) \
                .eq("lead_memories.status", "active") \
                .execute()

            contacts = {}
            for r in (result.data or []):
                email = r.get("contact_email", "")
                if email:
                    contacts[email.lower()] = r["lead_memory_id"]
            self._lead_contacts_cache[user_id] = contacts
            return contacts
        except Exception:
            return {}

    def _get_active_goals(self, user_id: str) -> list:
        """Get active goals with keywords for matching. Cached."""
        if user_id in self._active_goals_cache:
            return self._active_goals_cache[user_id]

        try:
            result = self.db.table("goals") \
                .select("id, title, config") \
                .eq("user_id", user_id) \
                .eq("status", "active") \
                .execute()

            goals = []
            for r in (result.data or []):
                keywords = []
                if r.get("config") and isinstance(r["config"], dict):
                    keywords = r["config"].get("keywords", [])
                title_words = [w for w in r.get("title", "").split() if len(w) > 3]
                keywords.extend(title_words)
                goals.append({"id": r["id"], "keywords": keywords})

            self._active_goals_cache[user_id] = goals
            return goals
        except Exception:
            return []

    def clear_caches(self, user_id: str | None = None) -> None:
        """Clear lookup caches. Call when leads/goals change."""
        if user_id:
            self._vip_cache.pop(user_id, None)
            self._active_goals_cache.pop(user_id, None)
            self._lead_contacts_cache.pop(user_id, None)
        else:
            self._vip_cache.clear()
            self._active_goals_cache.clear()
            self._lead_contacts_cache.clear()

    # ── Pulse emission ─────────────────────────────────────────────────

    async def _emit_to_pulse(
        self, user_id: str, signal_data: dict, classification: EventClassification,
    ) -> Optional[str]:
        """Send signal to Pulse Engine for salience scoring."""
        signal_data["matched_leads"] = classification.matched_leads
        signal_data["matched_goals"] = classification.matched_goals
        signal_data["is_vip"] = classification.is_vip_sender
        signal_data["priority_hint"] = classification.priority_hint

        # Map to Pulse Engine expected format
        pulse_signal = {
            "source": signal_data.get("source", "event_trigger"),
            "title": signal_data.get("title", ""),
            "content": signal_data.get("content", signal_data.get("summary", "")),
            "signal_category": signal_data.get("signal_category", signal_data.get("source", "email")),
            "pulse_type": signal_data.get("pulse_type", "event"),
            "entities": signal_data.get("entities", []),
            "related_goal_id": classification.matched_goals[0] if classification.matched_goals else None,
            "related_lead_id": classification.matched_leads[0] if classification.matched_leads else None,
            "raw_data": signal_data,
        }

        if hasattr(self.pulse_engine, "process_signal"):
            result = await self.pulse_engine.process_signal(user_id, pulse_signal)
            return result.get("id") if isinstance(result, dict) else None

        # Fallback: direct WebSocket
        await self._deliver_direct(
            user_id, HandlerOutput(summary=signal_data.get("summary", "")), classification,
        )
        return None

    # ── Direct WebSocket delivery ──────────────────────────────────────

    async def _deliver_direct(
        self, user_id: str, output: HandlerOutput, classification: EventClassification,
    ) -> None:
        """Push via WebSocket (bypasses Pulse for urgent items)."""
        if not output.summary and not output.artifacts:
            return

        title = self._generate_notification_title(classification)
        try:
            await self.ws_manager.send_signal(
                user_id=user_id,
                signal_type=classification.event_type,
                title=title,
                severity="high" if classification.priority_hint in ("high", "urgent") else "medium",
                data={
                    "message": output.summary or "New event processed",
                    "priority": classification.priority_hint,
                    "event_type": classification.event_type,
                    "artifacts": output.artifacts[:3],
                    "matched_leads": classification.matched_leads,
                    "matched_goals": classification.matched_goals,
                },
            )
        except Exception as e:
            logger.error("WebSocket delivery failed for user %s: %s", user_id, e)

    def _generate_notification_title(self, classification: EventClassification) -> str:
        type_titles = {
            "email.received": "New email",
            "email.thread_reply": "Email reply",
            "calendar.event_created": "New meeting",
            "calendar.event_updated": "Meeting changed",
            "calendar.event_deleted": "Meeting cancelled",
            "crm.deal_stage_changed": "Deal stage changed",
            "crm.lead_created": "New lead",
            "goal.completed": "Goal completed",
            "agent.task_finished": "Task finished",
        }
        title = type_titles.get(classification.event_type, "Event")
        if classification.is_vip_sender:
            title += " (VIP)"
        return title

    # ── Database ops (SYNC — no await) ─────────────────────────────────

    def _check_duplicate(self, envelope: EventEnvelope) -> Optional[str]:
        """Check if source_id was already processed."""
        try:
            result = self.db.table("event_log") \
                .select("id") \
                .eq("user_id", envelope.user_id) \
                .eq("source_id", envelope.source_id) \
                .neq("status", "failed") \
                .limit(1) \
                .execute()

            if result.data:
                return result.data[0]["id"]
        except Exception:
            pass
        return None

    def _log_event(self, envelope: EventEnvelope, status: str) -> str:
        """Create event_log entry. Returns event_log id."""
        try:
            result = self.db.table("event_log").insert({
                "user_id": envelope.user_id,
                "event_type": getattr(envelope.event_type, "value", envelope.event_type),
                "event_source": envelope.source.value,
                "source_id": envelope.source_id or None,
                "payload": envelope.payload,
                "status": status,
                "is_reconciliation": envelope.source == EventSource.RECONCILIATION,
            }).execute()

            return result.data[0]["id"] if result.data else envelope.id
        except Exception as e:
            logger.error("Failed to log event: %s", e)
            return envelope.id

    def _update_event_log(self, event_log_id: str, status: str | None = None, **kwargs: Any) -> None:
        """Update event_log entry."""
        try:
            update: dict[str, Any] = {}
            if status:
                update["status"] = status
            if "classification" in kwargs:
                cls = kwargs["classification"]
                update["classification"] = cls.__dict__ if hasattr(cls, "__dict__") else cls
            if "handler_result" in kwargs:
                update["handler_result"] = kwargs["handler_result"]
            if "pulse_signal_id" in kwargs:
                update["pulse_signal_id"] = kwargs["pulse_signal_id"]
            if "error" in kwargs:
                update["error_message"] = kwargs["error"]
            if "latency_ms" in kwargs:
                update["latency_ms"] = kwargs["latency_ms"]
            if status == "handled":
                update["processed_at"] = datetime.now(timezone.utc).isoformat()
            if status == "delivered":
                update["delivered_at"] = datetime.now(timezone.utc).isoformat()

            if update:
                self.db.table("event_log") \
                    .update(update) \
                    .eq("id", event_log_id) \
                    .execute()
        except Exception as e:
            logger.error("Failed to update event log %s: %s", event_log_id, e)
