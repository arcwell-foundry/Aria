"""Email Intelligence capability for ScribeAgent and OperatorAgent.

Enhances the existing EmailDraftingService with sending, response tracking,
multi-step sequencing, and send-time optimization. The DraftService handles
draft generation and Digital Twin style matching; this capability adds the
intelligence layer on top.

Key responsibilities:
- Send emails via Gmail/Outlook OAuth (Composio)
- Manage multi-step email sequences with timing
- Track inbox responses to ARIA-sent emails
- Optimize send times from historical interaction data
"""

import logging
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.core.exceptions import EmailSendError, NotFoundError
from src.db.supabase import SupabaseClient
from src.integrations.oauth import get_oauth_client
from src.models.lead_memory import Direction, EventType
from src.services.crm_audit import CRMAuditOperation, get_crm_audit_service
from src.services.draft_service import get_draft_service

logger = logging.getLogger(__name__)


# ── Lightweight result / domain dataclasses ──────────────────────────────


class SendResult:
    """Result of sending an email through the capability."""

    def __init__(
        self,
        *,
        draft_id: str,
        status: str,
        sent_at: datetime | None = None,
        provider: str | None = None,
        error: str | None = None,
        crm_logged: bool = False,
        lead_event_id: str | None = None,
    ) -> None:
        self.draft_id = draft_id
        self.status = status
        self.sent_at = sent_at
        self.provider = provider
        self.error = error
        self.crm_logged = crm_logged
        self.lead_event_id = lead_event_id

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "draft_id": self.draft_id,
            "status": self.status,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "provider": self.provider,
            "error": self.error,
            "crm_logged": self.crm_logged,
            "lead_event_id": self.lead_event_id,
        }


class EmailStep:
    """A single step in a multi-step email sequence."""

    def __init__(
        self,
        *,
        position: int,
        purpose: str,
        delay_hours: int = 0,
        subject_hint: str | None = None,
        tone: str = "friendly",
        context: str | None = None,
    ) -> None:
        self.position = position
        self.purpose = purpose
        self.delay_hours = delay_hours
        self.subject_hint = subject_hint
        self.tone = tone
        self.context = context

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "position": self.position,
            "purpose": self.purpose,
            "delay_hours": self.delay_hours,
            "subject_hint": self.subject_hint,
            "tone": self.tone,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EmailStep":
        """Deserialise from dict."""
        return cls(
            position=int(data.get("position", 0)),
            purpose=str(data.get("purpose", "")),
            delay_hours=int(data.get("delay_hours", 0)),
            subject_hint=data.get("subject_hint"),
            tone=str(data.get("tone", "friendly")),
            context=data.get("context"),
        )


class ResponseEvent:
    """A detected reply to an ARIA-sent email."""

    def __init__(
        self,
        *,
        draft_id: str,
        from_email: str,
        subject: str,
        snippet: str,
        received_at: datetime,
        lead_memory_id: str | None = None,
        sentiment: str | None = None,
    ) -> None:
        self.draft_id = draft_id
        self.from_email = from_email
        self.subject = subject
        self.snippet = snippet
        self.received_at = received_at
        self.lead_memory_id = lead_memory_id
        self.sentiment = sentiment

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "draft_id": self.draft_id,
            "from_email": self.from_email,
            "subject": self.subject,
            "snippet": self.snippet,
            "received_at": self.received_at.isoformat(),
            "lead_memory_id": self.lead_memory_id,
            "sentiment": self.sentiment,
        }


# ── Capability implementation ────────────────────────────────────────────


class EmailIntelligenceCapability(BaseCapability):
    """Email intelligence: sending, sequencing, tracking, and optimization.

    Wraps the existing ``DraftService`` for draft generation and adds:
    - OAuth-based sending via Gmail/Outlook
    - Multi-step email sequences with timing control
    - Inbox response tracking tied to lead_memory_events
    - Send-time optimization from historical data

    Designed for ScribeAgent (drafting + sending) and OperatorAgent
    (sequencing + tracking automation).
    """

    capability_name: str = "email-intelligence"
    agent_types: list[str] = ["ScribeAgent", "OperatorAgent"]
    oauth_scopes: list[str] = ["gmail_send", "gmail_readonly"]
    data_classes: list[str] = ["INTERNAL", "CONFIDENTIAL"]

    # ── BaseCapability abstract interface ──────────────────────────────────

    async def can_handle(self, task: dict[str, Any]) -> float:
        """Return confidence for email-intelligence tasks."""
        task_type = task.get("type", "")
        if task_type in {
            "send_email",
            "email_sequence",
            "track_responses",
            "optimize_send_time",
        }:
            return 0.95
        if "email" in task_type.lower():
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
            if task_type == "send_email":
                draft_id = task.get("draft_id", "")
                result = await self.send_email(user_id, draft_id)
                data = result.to_dict()

            elif task_type == "email_sequence":
                lead_id = task.get("lead_id", "")
                steps_raw = task.get("sequence", [])
                steps = [EmailStep.from_dict(s) for s in steps_raw]
                await self.manage_sequence(user_id, lead_id, steps)
                data = {
                    "lead_id": lead_id,
                    "steps_configured": len(steps),
                }

            elif task_type == "track_responses":
                events = await self.track_responses(user_id)
                data = {"responses": [e.to_dict() for e in events]}

            elif task_type == "optimize_send_time":
                recipient_email = task.get("recipient_email", "")
                optimal = await self.optimize_send_time(user_id, recipient_email)
                data = {
                    "recipient_email": recipient_email,
                    "optimal_send_time": optimal.isoformat(),
                }

            else:
                return CapabilityResult(
                    success=False,
                    error=f"Unknown task type: {task_type}",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            await self.log_activity(
                activity_type="email_intelligence",
                title=f"Email intelligence: {task_type}",
                description=f"Completed {task_type} for user {user_id}",
                confidence=0.85,
                metadata={"task_type": task_type, **data},
            )
            return CapabilityResult(success=True, data=data, execution_time_ms=elapsed_ms)

        except (EmailSendError, NotFoundError) as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("Email intelligence capability failed")
            return CapabilityResult(
                success=False,
                error=str(exc),
                execution_time_ms=elapsed_ms,
            )

    def get_data_classes_accessed(self) -> list[str]:
        """Declare data classification levels."""
        return ["internal", "confidential"]

    # ── Public methods ────────────────────────────────────────────────────

    async def send_email(self, user_id: str, draft_id: str) -> SendResult:
        """Send an email draft via Gmail/Outlook API using OAuth.

        Delegates the actual send to ``DraftService.send_draft``, then
        enriches the result with CRM audit logging and lead event tracking.

        Args:
            user_id: Authenticated user UUID.
            draft_id: The email_drafts row ID to send.

        Returns:
            SendResult with status, provider info, and downstream tracking IDs.
        """
        draft_service = get_draft_service()

        # Fetch the draft before sending so we have metadata for downstream tracking
        draft = await draft_service.get_draft(user_id, draft_id)
        if draft is None:
            raise NotFoundError("Draft", draft_id)

        # Determine email provider
        provider = await self._detect_email_provider(user_id)

        # Delegate actual send to existing DraftService
        try:
            updated_draft = await draft_service.send_draft(user_id, draft_id)
        except EmailSendError:
            raise
        except Exception as exc:
            logger.exception("Unexpected error sending draft")
            raise EmailSendError(str(exc), draft_id=draft_id) from exc

        now = datetime.now(UTC)
        sent_at_raw = updated_draft.get("sent_at")
        sent_at = (
            datetime.fromisoformat(str(sent_at_raw).replace("Z", "+00:00")) if sent_at_raw else now
        )

        # ── CRM audit logging ────────────────────────────────────────
        crm_logged = False
        lead_memory_id = draft.get("lead_memory_id")

        if lead_memory_id:
            try:
                audit = get_crm_audit_service()
                await audit.log_sync_operation(
                    user_id=user_id,
                    lead_memory_id=lead_memory_id,
                    operation=CRMAuditOperation.PUSH,
                    provider=provider or "email",
                    success=True,
                    details={
                        "action": "email_sent",
                        "draft_id": draft_id,
                        "recipient": draft["recipient_email"],
                        "subject": draft.get("subject", ""),
                    },
                )
                crm_logged = True
            except Exception as exc:
                logger.warning(
                    "Failed to log email send to CRM audit",
                    extra={"draft_id": draft_id, "error": str(exc)},
                )

        # ── Lead event tracking ───────────────────────────────────────
        lead_event_id: str | None = None

        if lead_memory_id:
            try:
                lead_event_id = await self._record_lead_event(
                    user_id=user_id,
                    lead_memory_id=lead_memory_id,
                    draft=draft,
                    sent_at=sent_at,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to record lead event for sent email",
                    extra={"draft_id": draft_id, "error": str(exc)},
                )

        logger.info(
            "Email sent via capability",
            extra={
                "user_id": user_id,
                "draft_id": draft_id,
                "provider": provider,
                "crm_logged": crm_logged,
            },
        )

        return SendResult(
            draft_id=draft_id,
            status="sent",
            sent_at=sent_at,
            provider=provider,
            crm_logged=crm_logged,
            lead_event_id=lead_event_id,
        )

    async def manage_sequence(
        self,
        user_id: str,
        lead_id: str,
        sequence: list[EmailStep],
    ) -> None:
        """Configure a multi-step email sequence for a lead.

        Creates draft entries for each step with ``metadata.sequence_position``
        and schedules future steps via prospective memory timestamps.
        The first step (position 0 with delay_hours=0) is created immediately;
        later steps are stored as drafts with ``scheduled_at`` in the future.

        Args:
            user_id: Authenticated user UUID.
            lead_id: The lead_memory ID to attach the sequence to.
            sequence: Ordered list of EmailStep objects defining the sequence.
        """
        client = SupabaseClient.get_client()

        # Validate lead exists
        lead_resp = (
            client.table("lead_memories")
            .select("id, company_name, primary_contact_email")
            .eq("id", lead_id)
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if not lead_resp.data:
            raise NotFoundError("Lead memory", lead_id)

        lead = lead_resp.data
        recipient_email = str(lead.get("primary_contact_email", ""))
        sequence_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        for step in sequence:
            scheduled_at = now + timedelta(hours=step.delay_hours)
            status = "draft" if step.delay_hours == 0 else "draft"

            draft_data: dict[str, Any] = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "recipient_email": recipient_email,
                "recipient_name": lead.get("company_name"),
                "subject": step.subject_hint or "",
                "body": "",  # Body generated on send via DraftService
                "purpose": step.purpose,
                "tone": step.tone,
                "status": status,
                "lead_memory_id": lead_id,
                "context": {
                    "sequence_id": sequence_id,
                    "sequence_position": step.position,
                    "sequence_total": len(sequence),
                    "step_context": step.context,
                },
                "metadata": {
                    "sequence_id": sequence_id,
                    "sequence_position": step.position,
                    "sequence_total": len(sequence),
                    "scheduled_at": scheduled_at.isoformat(),
                },
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            try:
                client.table("email_drafts").insert(draft_data).execute()
            except Exception as exc:
                logger.warning(
                    "Failed to create sequence step draft",
                    extra={
                        "user_id": user_id,
                        "lead_id": lead_id,
                        "position": step.position,
                        "error": str(exc),
                    },
                )

        logger.info(
            "Email sequence configured",
            extra={
                "user_id": user_id,
                "lead_id": lead_id,
                "sequence_id": sequence_id,
                "steps": len(sequence),
            },
        )

    async def track_responses(self, user_id: str) -> list[ResponseEvent]:
        """Monitor inbox for replies to ARIA-sent emails.

        Scans the user's email inbox (via Composio Gmail readonly) for
        messages that are replies to previously sent drafts, and records
        new responses as lead_memory_events.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            List of newly detected ResponseEvent objects.
        """
        client = SupabaseClient.get_client()
        responses: list[ResponseEvent] = []

        # Get recently sent drafts to check for replies
        sent_resp = (
            client.table("email_drafts")
            .select("id, recipient_email, subject, lead_memory_id, sent_at")
            .eq("user_id", user_id)
            .eq("status", "sent")
            .order("sent_at", desc=True)
            .limit(50)
            .execute()
        )
        sent_drafts = sent_resp.data or []

        if not sent_drafts:
            return responses

        # Get email integration for inbox access
        integration = await self._get_email_integration(user_id)
        if not integration:
            logger.info(
                "No email integration for response tracking",
                extra={"user_id": user_id},
            )
            return responses

        oauth_client = get_oauth_client()
        connection_id = str(integration["composio_connection_id"])

        # Build lookup of recipient → draft for matching
        draft_lookup: dict[str, dict[str, Any]] = {}
        for draft in sent_drafts:
            email = str(draft.get("recipient_email", "")).lower()
            if email and email not in draft_lookup:
                draft_lookup[email] = draft

        # Fetch recent inbox messages
        try:
            inbox_result = await oauth_client.execute_action(
                connection_id=connection_id,
                action="gmail_fetch_emails",
                params={
                    "max_results": 50,
                    "label": "INBOX",
                },
            )
            messages = inbox_result.get("data", [])
            if not isinstance(messages, list):
                messages = []
        except Exception as exc:
            logger.warning(
                "Failed to fetch inbox for response tracking",
                extra={"user_id": user_id, "error": str(exc)},
            )
            return responses

        # Match inbox messages to sent drafts
        for message in messages:
            from_email = str(message.get("from", "")).lower()
            subject = str(message.get("subject", ""))
            snippet = str(message.get("snippet", ""))[:500]
            message_id = str(message.get("id", ""))

            # Check for known recipients
            matched_draft = draft_lookup.get(from_email)
            if not matched_draft:
                continue

            # Skip if already tracked (dedup by source_id)
            lead_memory_id = matched_draft.get("lead_memory_id")
            if lead_memory_id:
                existing = (
                    client.table("lead_memory_events")
                    .select("id")
                    .eq("lead_memory_id", lead_memory_id)
                    .eq("source", "gmail")
                    .eq("source_id", message_id)
                    .maybe_single()
                    .execute()
                )
                if existing.data:
                    continue

            received_at_raw = message.get("date") or message.get("internalDate")
            try:
                if isinstance(received_at_raw, str):
                    received_at = datetime.fromisoformat(received_at_raw.replace("Z", "+00:00"))
                elif isinstance(received_at_raw, int | float):
                    received_at = datetime.fromtimestamp(received_at_raw / 1000, tz=UTC)
                else:
                    received_at = datetime.now(UTC)
            except (ValueError, TypeError):
                received_at = datetime.now(UTC)

            # Record as lead event
            if lead_memory_id:
                try:
                    await self._record_response_event(
                        user_id=user_id,
                        lead_memory_id=lead_memory_id,
                        message_id=message_id,
                        from_email=from_email,
                        subject=subject,
                        snippet=snippet,
                        received_at=received_at,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to record response lead event",
                        extra={"message_id": message_id, "error": str(exc)},
                    )

            response_event = ResponseEvent(
                draft_id=str(matched_draft.get("id", "")),
                from_email=from_email,
                subject=subject,
                snippet=snippet,
                received_at=received_at,
                lead_memory_id=lead_memory_id,
            )
            responses.append(response_event)

        logger.info(
            "Response tracking complete",
            extra={"user_id": user_id, "responses_found": len(responses)},
        )
        return responses

    async def optimize_send_time(
        self,
        user_id: str,
        recipient_email: str,
    ) -> datetime:
        """Analyze past email interactions to find optimal send time.

        Examines historical response times from the recipient to determine
        when they are most likely to read and respond to emails. Falls back
        to a sensible default (10:00 AM in the user's next business day)
        if insufficient data exists.

        Args:
            user_id: Authenticated user UUID.
            recipient_email: The recipient to optimize for.

        Returns:
            Recommended datetime (UTC) to send the next email.
        """
        client = SupabaseClient.get_client()
        now = datetime.now(UTC)

        # Find lead_memory_id for this recipient
        lead_resp = (
            client.table("lead_memories")
            .select("id")
            .eq("user_id", user_id)
            .eq("primary_contact_email", recipient_email)
            .maybe_single()
            .execute()
        )

        if not lead_resp.data:
            # No lead history — return default (next business day 10am UTC)
            return self._next_business_day_default(now)

        lead_id = str(lead_resp.data["id"])

        # Get all email events for this lead
        events_resp = (
            client.table("lead_memory_events")
            .select("event_type, direction, occurred_at")
            .eq("lead_memory_id", lead_id)
            .in_("event_type", [EventType.EMAIL_SENT.value, EventType.EMAIL_RECEIVED.value])
            .order("occurred_at", desc=False)
            .execute()
        )
        events = events_resp.data or []

        if len(events) < 2:
            return self._next_business_day_default(now)

        # Analyze response hours — when do replies arrive?
        reply_hours: list[int] = []
        for event in events:
            if event.get("event_type") == EventType.EMAIL_RECEIVED.value:
                try:
                    occurred = datetime.fromisoformat(
                        str(event["occurred_at"]).replace("Z", "+00:00")
                    )
                    reply_hours.append(occurred.hour)
                except (ValueError, TypeError):
                    continue

        if not reply_hours:
            return self._next_business_day_default(now)

        # Find the most common reply hour and target ~1 hour before
        optimal_hour = int(statistics.mode(reply_hours))
        send_hour = max(optimal_hour - 1, 8)  # Don't go earlier than 8am UTC

        # Schedule for tomorrow at the optimal hour
        tomorrow = now + timedelta(days=1)
        # Skip weekends
        while tomorrow.weekday() >= 5:  # Saturday=5, Sunday=6
            tomorrow += timedelta(days=1)

        optimal_time = tomorrow.replace(hour=send_hour, minute=0, second=0, microsecond=0)

        logger.info(
            "Send time optimized",
            extra={
                "user_id": user_id,
                "recipient": recipient_email,
                "optimal_hour": send_hour,
                "reply_hours_sample": len(reply_hours),
            },
        )
        return optimal_time

    # ── Private helpers ───────────────────────────────────────────────────

    async def _detect_email_provider(self, user_id: str) -> str | None:
        """Detect which email provider the user has connected."""
        integration = await self._get_email_integration(user_id)
        if integration:
            return str(integration.get("integration_type", ""))
        return None

    async def _get_email_integration(self, user_id: str) -> dict[str, Any] | None:
        """Get user's email integration (Gmail or Outlook).

        Tries Gmail first (primary for life sciences), then Outlook.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            Integration row dict, or None if no email integration found.
        """
        client = SupabaseClient.get_client()

        for provider in ("gmail", "outlook"):
            try:
                resp = (
                    client.table("user_integrations")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("integration_type", provider)
                    .eq("status", "active")
                    .maybe_single()
                    .execute()
                )
                if resp.data and resp.data.get("composio_connection_id"):
                    return resp.data
            except Exception:
                continue

        return None

    async def _record_lead_event(
        self,
        user_id: str,
        lead_memory_id: str,
        draft: dict[str, Any],
        sent_at: datetime,
    ) -> str:
        """Record an outbound email as a lead_memory_event."""
        from src.memory.lead_memory_events import LeadEventService
        from src.models.lead_memory import LeadEventCreate

        client = SupabaseClient.get_client()
        event_service = LeadEventService(db_client=client)

        event_data = LeadEventCreate(
            event_type=EventType.EMAIL_SENT,
            direction=Direction.OUTBOUND,
            subject=draft.get("subject"),
            content=draft.get("body", "")[:5000],
            participants=[draft["recipient_email"]],
            occurred_at=sent_at,
            source="aria_draft",
            source_id=draft["id"],
        )

        return await event_service.add_event(
            user_id=user_id,
            lead_memory_id=lead_memory_id,
            event_data=event_data,
        )

    async def _record_response_event(
        self,
        user_id: str,
        lead_memory_id: str,
        message_id: str,
        from_email: str,
        subject: str,
        snippet: str,
        received_at: datetime,
    ) -> str:
        """Record an inbound reply as a lead_memory_event."""
        from src.memory.lead_memory_events import LeadEventService
        from src.models.lead_memory import LeadEventCreate

        client = SupabaseClient.get_client()
        event_service = LeadEventService(db_client=client)

        event_data = LeadEventCreate(
            event_type=EventType.EMAIL_RECEIVED,
            direction=Direction.INBOUND,
            subject=subject,
            content=snippet,
            participants=[from_email],
            occurred_at=received_at,
            source="gmail",
            source_id=message_id,
        )

        return await event_service.add_event(
            user_id=user_id,
            lead_memory_id=lead_memory_id,
            event_data=event_data,
        )

    @staticmethod
    def _next_business_day_default(now: datetime) -> datetime:
        """Return next business day at 10:00 AM UTC as default send time."""
        tomorrow = now + timedelta(days=1)
        while tomorrow.weekday() >= 5:
            tomorrow += timedelta(days=1)
        return tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
