"""Universal memory routing service.

Routes event-driven data to appropriate memory tables:
- memory_semantic: Facts with confidence scores
- lead_memory_events: Timeline of lead interactions
- lead_memory_stakeholders: Contact map with sentiment
- lead_memory_insights: AI-generated insights
- memory_prospective: Future tasks and reminders
- skill_working_memory: Skill execution context

All operations are wrapped in try/except with logger.exception() — never raises.
Call this from every service after every output.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


async def write_memory(
    db: Any,
    user_id: str,
    event_type: str,
    data: dict[str, Any],
) -> None:
    """Universal memory router. Never raises — all operations wrapped in try/except.

    Call this from every service after every output.

    Args:
        db: Supabase client instance.
        user_id: The user's ID.
        event_type: Type of event (e.g., 'email_scanned', 'meeting_debrief_approved').
        data: Event-specific data payload.
    """
    try:
        handler = _EVENT_HANDLERS.get(event_type)
        if not handler:
            logger.warning(
                "[MemoryWriter] Unknown event_type: %s — skipping",
                event_type,
            )
            return

        await handler(db, user_id, data)
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to route event_type=%s for user=%s",
            event_type,
            user_id,
        )


# ============================================================================
# Event Handlers
# ============================================================================


async def _handle_email_scanned(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'email_scanned' event to memory_semantic and optionally lead_memory_events."""
    email_id = data.get("email_id", "")
    sender_email = data.get("sender_email", "")
    sender_name = data.get("sender_name", "Unknown")
    subject = data.get("subject", "")
    category = data.get("category", "UNKNOWN")
    urgency = data.get("urgency", "NORMAL")
    snippet = data.get("snippet", "")
    scanned_at = data.get("scanned_at") or datetime.now(UTC).isoformat()
    confidence = data.get("confidence", 0.7)

    # Insert into memory_semantic
    date_str = scanned_at[:10] if scanned_at else "recently"
    fact = (
        f"{sender_name} sent email about '{subject}' on {date_str}. "
        f"Category: {category}. Urgency: {urgency}."
    )

    try:
        db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": fact,
            "confidence": confidence,
            "source": "email_scan",
            "metadata": json.dumps({
                "email_id": email_id,
                "sender_email": sender_email,
                "sender_name": sender_name,
                "subject": subject,
                "category": category,
                "urgency": urgency,
            }),
        }).execute()
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to insert memory_semantic for email_scanned"
        )

    # Try to resolve lead_memory_id and insert into lead_memory_events
    lead_memory_id = await _resolve_lead_memory_id(db, user_id, sender_email)
    if lead_memory_id:
        try:
            db.table("lead_memory_events").insert({
                "lead_memory_id": lead_memory_id,
                "event_type": "email_received",
                "direction": "inbound",
                "subject": subject,
                "content": snippet[:5000] if snippet else None,
                "occurred_at": scanned_at,
                "source": "email_scan",
                "source_id": email_id,
                "metadata": json.dumps({
                    "category": category,
                    "urgency": urgency,
                    "sender_name": sender_name,
                }),
            }).execute()
        except Exception:
            logger.exception(
                "[MemoryWriter] Failed to insert lead_memory_events for email_scanned"
            )


async def _handle_email_sent(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'email_sent' event to memory_semantic and optionally lead_memory_events."""
    recipient_email = data.get("recipient_email", "")
    recipient = data.get("recipient_name") or recipient_email
    subject = data.get("subject", "")
    sent_at = data.get("sent_at") or datetime.now(UTC).isoformat()

    date_str = sent_at[:10] if sent_at else "recently"
    fact = f"Dhruv sent email to {recipient} re: '{subject}' on {date_str}."

    try:
        db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": fact,
            "confidence": 0.8,
            "source": "email_sent",
            "metadata": json.dumps({
                "recipient_email": recipient_email,
                "subject": subject,
            }),
        }).execute()
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to insert memory_semantic for email_sent"
        )

    # Try to resolve lead_memory_id
    lead_memory_id = await _resolve_lead_memory_id(db, user_id, recipient_email)
    if lead_memory_id:
        try:
            db.table("lead_memory_events").insert({
                "lead_memory_id": lead_memory_id,
                "event_type": "email_sent",
                "direction": "outbound",
                "subject": subject,
                "occurred_at": sent_at,
                "source": "email_sent",
                "metadata": json.dumps({
                    "recipient_email": recipient_email,
                }),
            }).execute()
        except Exception:
            logger.exception(
                "[MemoryWriter] Failed to insert lead_memory_events for email_sent"
            )


async def _handle_meeting_brief_generated(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'meeting_brief_generated' event to memory_semantic."""
    meeting_title = data.get("meeting_title", "Meeting")
    attendee_emails = data.get("attendee_emails", [])
    calendar_event_id = data.get("calendar_event_id")
    meeting_time = data.get("meeting_time") or datetime.now(UTC).isoformat()

    attendees_str = ", ".join(attendee_emails[:3]) if attendee_emails else "attendees"
    date_str = meeting_time[:10] if meeting_time else "upcoming"

    fact = f"Meeting brief prepared for '{meeting_title}' with {attendees_str} on {date_str}."

    try:
        db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": fact,
            "confidence": 0.9,
            "source": "meeting_brief",
            "metadata": json.dumps({
                "calendar_event_id": calendar_event_id,
                "attendee_emails": attendee_emails,
                "meeting_time": meeting_time,
            }),
        }).execute()
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to insert memory_semantic for meeting_brief_generated"
        )


async def _handle_meeting_debrief_approved(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'meeting_debrief_approved' event to multiple memory tables.

    Routes to:
    - memory_semantic: one fact per attendee (with dedup check)
    - lead_memory_events: per attendee
    - lead_memory_stakeholders: upsert per attendee
    - lead_memory_insights: per stakeholder_signal
    - memory_prospective: per action_item with due date
    """
    debrief_id = data.get("debrief_id", "")
    meeting_title = data.get("meeting_title", "Meeting")
    summary = data.get("summary", "")
    action_items = data.get("action_items", [])
    next_steps = data.get("next_steps", [])
    stakeholder_signals = data.get("stakeholder_signals", [])
    attendee_emails = data.get("attendee_emails", [])
    meeting_time = data.get("meeting_time") or datetime.now(UTC).isoformat()

    date_str = meeting_time[:10] if meeting_time else "recently"

    # 1. Insert memory_semantic facts per attendee (skip if already exists)
    for email in attendee_emails:
        try:
            # Check for existing fact with same debrief_id
            existing = (
                db.table("memory_semantic")
                .select("id")
                .eq("user_id", user_id)
                .eq("source", "meeting_debrief")
                .eq("metadata->>debrief_id", debrief_id)
                .limit(1)
                .execute()
            )
            if existing.data:
                continue  # Skip duplicate

            fact = (
                f"{email} attended '{meeting_title}' with Dhruv on {date_str}. "
                f"{summary[:200]}" if summary else ""
            )

            db.table("memory_semantic").insert({
                "user_id": user_id,
                "fact": fact,
                "confidence": 0.9,
                "source": "meeting_debrief",
                "metadata": json.dumps({
                    "debrief_id": debrief_id,
                    "meeting_title": meeting_title,
                    "attendee_email": email,
                    "action_items": action_items,
                    "next_steps": next_steps,
                }),
            }).execute()
        except Exception:
            logger.exception(
                "[MemoryWriter] Failed to insert memory_semantic for debrief %s, attendee %s",
                debrief_id,
                email,
            )

    # 2. Insert lead_memory_events per attendee
    for email in attendee_emails:
        lead_memory_id = await _resolve_lead_memory_id(db, user_id, email)
        if not lead_memory_id:
            continue

        try:
            db.table("lead_memory_events").insert({
                "lead_memory_id": lead_memory_id,
                "event_type": "meeting",
                "direction": "attended",
                "subject": meeting_title,
                "content": summary[:5000] if summary else None,
                "occurred_at": meeting_time,
                "source": "meeting_debrief",
                "source_id": debrief_id,
                "metadata": json.dumps({
                    "attendee_email": email,
                    "stakeholder_signals": stakeholder_signals,
                }),
            }).execute()
        except Exception:
            logger.exception(
                "[MemoryWriter] Failed to insert lead_memory_events for debrief %s",
                debrief_id,
            )

    # 3. Upsert lead_memory_stakeholders per attendee
    for email in attendee_emails:
        lead_memory_id = await _resolve_lead_memory_id(db, user_id, email)
        if not lead_memory_id:
            continue

        # Extract name from email or use email as name
        contact_name = email.split("@")[0].replace(".", " ").title()

        # Determine sentiment from stakeholder_signals
        sentiment = _extract_sentiment(stakeholder_signals, email)

        await _upsert_stakeholder(
            db=db,
            contact_email=email,
            contact_name=contact_name,
            lead_memory_id=lead_memory_id,
            sentiment=sentiment,
            meeting_time=meeting_time,
            summary=summary,
            stakeholder_signals=stakeholder_signals,
            meeting_title=meeting_title,
        )

    # 4. Insert lead_memory_insights per stakeholder_signal
    for signal in stakeholder_signals:
        signal_text = None
        if isinstance(signal, str):
            signal_text = signal
        elif isinstance(signal, dict):
            signal_text = signal.get("content") or signal.get("signal") or signal.get("text")

        if not signal_text:
            continue

        # Try to find a lead_memory_id from any attendee
        for email in attendee_emails:
            lead_memory_id = await _resolve_lead_memory_id(db, user_id, email)
            if not lead_memory_id:
                continue

            try:
                db.table("lead_memory_insights").insert({
                    "lead_memory_id": lead_memory_id,
                    "insight_type": "stakeholder_signal",
                    "content": signal_text,
                    "confidence": 0.85,
                    "detected_at": datetime.now(UTC).isoformat(),
                }).execute()
                break  # Only insert once per signal
            except Exception:
                logger.exception(
                    "[MemoryWriter] Failed to insert lead_memory_insights for signal"
                )

    # 5. Insert memory_prospective per action_item with due date
    for item in action_items:
        if isinstance(item, str):
            task_text = item
            owner = None
            due = None
        elif isinstance(item, dict):
            task_text = (
                item.get("item")
                or item.get("task")
                or item.get("description")
                or str(item)
            )
            owner = item.get("owner")
            due = item.get("due") or item.get("due_date")
        else:
            continue

        if not due:
            continue  # Skip items without due dates

        task_full = f"{task_text} (owner: {owner}, due: {due})" if owner else f"{task_text} (due: {due})"

        try:
            db.table("memory_prospective").insert({
                "user_id": user_id,
                "task": task_full,
                "trigger_config": json.dumps({
                    "due_date": due,
                    "reference_id": str(debrief_id),
                    "source": "meeting_debrief",
                }),
                "status": "pending",
                "priority": "high",
            }).execute()
        except Exception:
            logger.exception(
                "[MemoryWriter] Failed to insert memory_prospective for action_item"
            )


async def _handle_competitive_signal(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'competitive_signal' event to memory_semantic."""
    entity_name = data.get("entity_name", "Competitor")
    signal = data.get("signal", "")
    signal_type = data.get("signal_type", "unknown")
    source_url = data.get("source_url")
    detected_at = data.get("detected_at") or datetime.now(UTC).isoformat()

    date_str = detected_at[:10] if detected_at else "recently"
    fact = f"Competitive signal re {entity_name}: {signal} on {date_str}."

    try:
        db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": fact,
            "confidence": 0.8,
            "source": "scout_agent",
            "metadata": json.dumps({
                "entity_name": entity_name,
                "signal_type": signal_type,
                "source_url": source_url,
            }),
        }).execute()
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to insert memory_semantic for competitive_signal"
        )


async def _handle_lead_created(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'lead_created' event to memory_semantic."""
    company = data.get("company", "Unknown Company")
    contact_name = data.get("contact_name", "Unknown Contact")
    title = data.get("title", "")
    source = data.get("source", "hunter_agent")

    fact = f"New lead: {company} — {contact_name}, {title}. Source: {source}."

    try:
        db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": fact,
            "confidence": 0.85,
            "source": "hunter_agent",
            "metadata": json.dumps(data),
        }).execute()
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to insert memory_semantic for lead_created"
        )


async def _handle_goal_executed(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'goal_executed' event to memory_semantic."""
    goal_title = data.get("goal_title", "Goal")
    result_summary = data.get("result_summary", "")
    goal_id = data.get("goal_id")
    agent = data.get("agent")

    fact = f"ARIA executed: {goal_title}. Result: {result_summary}."

    try:
        db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": fact,
            "confidence": 0.9,
            "source": "goal_execution",
            "metadata": json.dumps({
                "goal_id": goal_id,
                "agent": agent,
                "result": result_summary,
            }),
        }).execute()
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to insert memory_semantic for goal_executed"
        )


async def _handle_brainstorm_message(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'brainstorm_message' event to skill_working_memory.

    skill_working_memory schema:
    - plan_id: References skill_execution_plans
    - step_number: Step within the plan
    - skill_id: Skill identifier
    - input_summary: User message
    - output_summary: ARIA response
    - artifacts: JSONB for additional data
    """
    plan_id = data.get("plan_id")
    meeting_ref = data.get("meeting_ref")
    user_message = data.get("user_message", "")
    aria_response = data.get("aria_response", "")

    if not plan_id:
        logger.warning(
            "[MemoryWriter] brainstorm_message missing plan_id — skipping"
        )
        return

    try:
        # Find the next step number for this plan
        existing = (
            db.table("skill_working_memory")
            .select("step_number")
            .eq("plan_id", plan_id)
            .order("step_number", desc=True)
            .limit(1)
            .execute()
        )
        next_step = (existing.data[0]["step_number"] + 1) if existing.data else 1

        db.table("skill_working_memory").insert({
            "plan_id": plan_id,
            "step_number": next_step,
            "skill_id": "brainstorm",
            "input_summary": user_message[:1000] if user_message else None,
            "output_summary": aria_response[:2000] if aria_response else None,
            "artifacts": json.dumps({
                "meeting_ref": meeting_ref,
                "timestamp": datetime.now(UTC).isoformat(),
            }),
            "extracted_facts": [],
            "next_step_hints": [],
            "status": "completed",
        }).execute()
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to insert skill_working_memory for brainstorm_message"
        )


async def _handle_slide_deck_created(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'slide_deck_created' event to memory_semantic."""
    title = data.get("title", "Slide Deck")
    meeting_title = data.get("meeting_title", "")
    deck_url = data.get("deck_url", "")
    meeting_id = data.get("meeting_id")
    calendar_event_id = data.get("calendar_event_id")
    created_at = data.get("created_at") or datetime.now(UTC).isoformat()

    date_str = created_at[:10] if created_at else "recently"
    fact = f"Slide deck '{title}' created for '{meeting_title}' on {date_str}. URL: {deck_url}."

    try:
        db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": fact,
            "confidence": 1.0,
            "source": "gamma_integration",
            "metadata": json.dumps({
                "deck_url": deck_url,
                "meeting_id": meeting_id,
                "calendar_event_id": calendar_event_id,
            }),
        }).execute()
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to insert memory_semantic for slide_deck_created"
        )


async def _handle_calendar_event_synced(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'calendar_event_synced' event to memory_semantic."""
    title = data.get("title", "Meeting")
    attendees = data.get("attendees", [])
    start_time = data.get("start_time") or datetime.now(UTC).isoformat()
    calendar_event_id = data.get("calendar_event_id")

    attendees_str = ", ".join(attendees[:3]) if attendees else "attendees"
    date_str = start_time[:10] if start_time else "scheduled"

    fact = f"Meeting scheduled: '{title}' with {attendees_str} at {date_str}."

    try:
        db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": fact,
            "confidence": 1.0,
            "source": "calendar_sync",
            "metadata": json.dumps({
                "calendar_event_id": calendar_event_id,
                "attendee_emails": attendees,
                "start_time": start_time,
            }),
        }).execute()
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to insert memory_semantic for calendar_event_synced"
        )


async def _handle_crm_note_pushed(
    db: Any,
    user_id: str,
    data: dict[str, Any],
) -> None:
    """Route 'crm_note_pushed' event to memory_semantic."""
    contact = data.get("contact", "Contact")
    account = data.get("account", "Account")
    summary = data.get("summary", "")

    fact = f"CRM note pushed for {contact}/{account}: {summary}."

    try:
        db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": fact,
            "confidence": 0.9,
            "source": "crm_sync",
            "metadata": json.dumps(data),
        }).execute()
    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to insert memory_semantic for crm_note_pushed"
        )


# ============================================================================
# Event Handler Registry
# ============================================================================

_EVENT_HANDLERS: dict[str, Any] = {
    "email_scanned": _handle_email_scanned,
    "email_sent": _handle_email_sent,
    "meeting_brief_generated": _handle_meeting_brief_generated,
    "meeting_debrief_approved": _handle_meeting_debrief_approved,
    "competitive_signal": _handle_competitive_signal,
    "lead_created": _handle_lead_created,
    "goal_executed": _handle_goal_executed,
    "brainstorm_message": _handle_brainstorm_message,
    "slide_deck_created": _handle_slide_deck_created,
    "calendar_event_synced": _handle_calendar_event_synced,
    "crm_note_pushed": _handle_crm_note_pushed,
}


# ============================================================================
# Helper Functions
# ============================================================================


async def _resolve_lead_memory_id(
    db: Any,
    user_id: str,
    email: str,
) -> str | None:
    """Query lead_memory WHERE user_id=user_id and contact email matches.

    Checks both:
    - lead_memory_stakeholders.contact_email
    - lead_memories linked via company domain matching

    Args:
        db: Supabase client instance.
        user_id: The user's ID.
        email: Contact email address to match.

    Returns:
        lead_memory_id or None if not found.
    """
    if not email:
        return None

    email_lower = email.lower().strip()

    try:
        # First try: direct match in lead_memory_stakeholders
        stakeholders_result = (
            db.table("lead_memory_stakeholders")
            .select("lead_memory_id")
            .ilike("contact_email", email_lower)
            .limit(1)
            .execute()
        )

        if stakeholders_result.data:
            # Verify the lead_memory belongs to this user
            lead_id = stakeholders_result.data[0].get("lead_memory_id")
            if lead_id:
                lead_result = (
                    db.table("lead_memories")
                    .select("id")
                    .eq("id", lead_id)
                    .eq("user_id", user_id)
                    .limit(1)
                    .execute()
                )
                if lead_result.data:
                    return str(lead_id)

        # Second try: match by company domain
        if "@" in email_lower:
            domain = email_lower.split("@")[1]
            # Query lead_memories with matching company
            leads_result = (
                db.table("lead_memories")
                .select("id")
                .eq("user_id", user_id)
                .ilike("company_name", f"%{domain.split('.')[0]}%")
                .eq("status", "active")
                .limit(1)
                .execute()
            )
            if leads_result.data:
                return str(leads_result.data[0]["id"])

        return None

    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to resolve lead_memory_id for email=%s",
            email,
        )
        return None


async def _upsert_stakeholder(
    db: Any,
    contact_email: str,
    contact_name: str,
    lead_memory_id: str | None,
    sentiment: str,
    meeting_time: str,
    summary: str,
    stakeholder_signals: list[Any],
    meeting_title: str,
) -> None:
    """Upsert lead_memory_stakeholders row.

    Uses ON CONFLICT (lead_memory_id, contact_email) DO UPDATE.
    """
    if not lead_memory_id:
        return

    try:
        # Check for existing stakeholder
        existing = (
            db.table("lead_memory_stakeholders")
            .select("id, notes, personality_insights")
            .eq("lead_memory_id", lead_memory_id)
            .eq("contact_email", contact_email.lower())
            .limit(1)
            .execute()
        )

        personality_insights = {
            "stakeholder_signals": stakeholder_signals,
            "last_meeting": meeting_title,
        }

        if existing.data:
            # Update existing
            row = existing.data[0]
            existing_notes = row.get("notes") or ""
            existing_insights = row.get("personality_insights") or {}

            # Merge personality insights
            if isinstance(existing_insights, dict):
                existing_insights.update(personality_insights)
                personality_insights = existing_insights

            # Append to notes
            new_notes = f"{existing_notes} | {summary}" if existing_notes else summary

            db.table("lead_memory_stakeholders").update({
                "sentiment": sentiment,
                "last_contacted_at": meeting_time,
                "notes": new_notes[:5000] if new_notes else None,
                "personality_insights": personality_insights,
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", row["id"]).execute()
        else:
            # Insert new
            db.table("lead_memory_stakeholders").insert({
                "lead_memory_id": lead_memory_id,
                "contact_email": contact_email.lower(),
                "contact_name": contact_name,
                "sentiment": sentiment,
                "last_contacted_at": meeting_time,
                "notes": summary[:5000] if summary else None,
                "personality_insights": personality_insights,
            }).execute()

    except Exception:
        logger.exception(
            "[MemoryWriter] Failed to upsert stakeholder for email=%s",
            contact_email,
        )


def _extract_sentiment(
    stakeholder_signals: list[Any],
    email: str,
) -> str:
    """Extract overall sentiment from stakeholder_signals.

    Args:
        stakeholder_signals: List of signal strings or dicts.
        email: Contact email for context (not used currently).

    Returns:
        'positive', 'neutral', or 'negative'.
    """
    if not stakeholder_signals:
        return "neutral"

    positive_keywords = [
        "excited", "interested", "positive", "enthusiastic",
        "committed", "agreed", "supportive", "engaged",
        "ready", "eager", "confident",
    ]
    negative_keywords = [
        "concerned", "hesitant", "negative", "worried",
        "frustrated", "resistant", "blocked", "skeptical",
        "delayed", "risk", "objection",
    ]

    text = " ".join(
        s if isinstance(s, str) else str(s)
        for s in stakeholder_signals
    ).lower()

    positive_count = sum(1 for kw in positive_keywords if kw in text)
    negative_count = sum(1 for kw in negative_keywords if kw in text)

    if positive_count > negative_count:
        return "positive"
    elif negative_count > positive_count:
        return "negative"
    return "neutral"
