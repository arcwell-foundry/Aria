"""Debrief approval handler — Stream C1 and C2.

When a user approves a debrief_review action in the Action Queue,
this handler:
1. Generates follow-up email drafts for external attendees (C1)
2. Writes semantic memory facts for each attendee interaction (C1)
3. Enriches future meeting briefs with relationship history (C2)
4. Marks the action as completed
"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


async def handle_debrief_approval(
    action_item: dict[str, Any],
    user_id: str,
    db: Any,
) -> dict[str, Any]:
    """Process an approved debrief_review action.

    Generates follow-up emails for external meeting attendees and
    writes semantic memory facts about the meeting interaction.

    Args:
        action_item: The aria_action_queue row dict.
        user_id: The approving user's ID.
        db: Supabase client instance.

    Returns:
        Result dict with status, email_drafts_created, memory_facts_written.
    """
    payload = action_item.get("payload", {})
    if isinstance(payload, str):
        payload = json.loads(payload)

    debrief_id = payload.get("reference_id") or payload.get("debrief_id")
    if not debrief_id:
        logger.warning("[DebriefApproval] No debrief_id in payload")
        return {"status": "error", "message": "No debrief_id in payload"}

    # ------------------------------------------------------------------
    # 1. Load debrief + related records
    # ------------------------------------------------------------------
    debrief_result = (
        db.table("meeting_debriefs")
        .select("*")
        .eq("id", debrief_id)
        .limit(1)
        .execute()
    )
    if not debrief_result.data:
        logger.warning("[DebriefApproval] Debrief not found: %s", debrief_id)
        return {"status": "error", "message": "Debrief not found"}

    debrief = debrief_result.data[0]
    meeting_title = debrief.get("meeting_title") or "Meeting"
    summary = debrief.get("summary") or ""
    action_items = debrief.get("action_items") or []
    next_steps = debrief.get("next_steps") or []
    stakeholder_signals = debrief.get("stakeholder_signals") or []
    meeting_time = debrief.get("meeting_time") or debrief.get("created_at", "")

    # Fetch calendar event (for attendees)
    calendar_event_id = debrief.get("calendar_event_id")
    calendar_event = None
    if calendar_event_id:
        ce_result = (
            db.table("calendar_events")
            .select("*")
            .eq("id", calendar_event_id)
            .limit(1)
            .execute()
        )
        if ce_result.data:
            calendar_event = ce_result.data[0]

    # Fetch meeting session
    meeting_session_id = (
        debrief.get("meeting_session_id") or payload.get("meeting_session_id")
    )
    session = None
    if meeting_session_id:
        sess_result = (
            db.table("meeting_sessions")
            .select("*")
            .eq("id", meeting_session_id)
            .limit(1)
            .execute()
        )
        if sess_result.data:
            session = sess_result.data[0]

    # Fill in title/time from related records if debrief lacks them
    if meeting_title == "Meeting":
        if calendar_event:
            meeting_title = calendar_event.get("title") or meeting_title
        elif session:
            meeting_title = session.get("meeting_title") or meeting_title

    if not meeting_time and calendar_event:
        meeting_time = calendar_event.get("start_time") or ""

    # ------------------------------------------------------------------
    # 2. Extract attendees
    # ------------------------------------------------------------------
    attendees = _extract_attendees(calendar_event)

    # ------------------------------------------------------------------
    # 3. Draft follow-up emails
    # ------------------------------------------------------------------
    email_drafts_created = 0
    try:
        email_drafts_created = await _create_followup_drafts(
            db=db,
            user_id=user_id,
            debrief_id=debrief_id,
            meeting_session_id=str(meeting_session_id) if meeting_session_id else "",
            meeting_title=meeting_title,
            summary=summary,
            action_items=action_items,
            next_steps=next_steps,
            attendees=attendees,
        )
    except Exception:
        logger.exception("[DebriefApproval] Failed to create email drafts")

    # ------------------------------------------------------------------
    # 4. Memory update (legacy + universal router)
    # ------------------------------------------------------------------
    memory_facts_written = 0
    try:
        memory_facts_written = _write_memory_facts(
            db=db,
            user_id=user_id,
            debrief_id=debrief_id,
            meeting_title=meeting_title,
            meeting_time=meeting_time,
            summary=summary,
            stakeholder_signals=stakeholder_signals,
            action_items=action_items,
            attendees=attendees,
        )
    except Exception:
        logger.exception("[DebriefApproval] Failed to write memory facts")

    # Universal memory router for comprehensive lead memory updates
    try:
        from src.services.memory_writer import write_memory

        attendee_emails = [a.get("email", "") for a in attendees if a.get("email")]
        await write_memory(db, user_id, "meeting_debrief_approved", {
            "debrief_id": str(debrief_id),
            "meeting_title": meeting_title,
            "summary": summary,
            "action_items": action_items,
            "next_steps": next_steps,
            "stakeholder_signals": stakeholder_signals,
            "attendee_emails": attendee_emails,
            "meeting_time": meeting_time,
        })
    except Exception:
        logger.exception("[DebriefApproval] Failed to route via memory_writer")

    # ------------------------------------------------------------------
    # 5. Update action queue
    # ------------------------------------------------------------------
    try:
        db.table("aria_action_queue").update({
            "status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
        }).eq("id", action_item["id"]).execute()
    except Exception:
        logger.exception("[DebriefApproval] Failed to mark action completed")

    result = {
        "status": "completed",
        "email_drafts_created": email_drafts_created,
        "memory_facts_written": memory_facts_written,
    }

    # ------------------------------------------------------------------
    # 6. Enrich future meeting briefs with relationship history (Stream C2)
    # ------------------------------------------------------------------
    try:
        enriched = await _enrich_future_meeting_briefs(
            db=db,
            user_id=user_id,
            debrief_row=debrief,
            calendar_event=calendar_event,
            attendees=attendees,
        )
        result["future_briefs_enriched"] = enriched
    except Exception:
        logger.exception("[DebriefApproval] Failed to enrich future briefs")

    logger.info(
        "[DebriefApproval] Completed",
        extra={
            "debrief_id": debrief_id,
            "email_drafts_created": email_drafts_created,
            "memory_facts_written": memory_facts_written,
            "future_briefs_enriched": result.get("future_briefs_enriched", 0),
        },
    )

    return result


# ======================================================================
# Helpers
# ======================================================================


def _extract_attendees(
    calendar_event: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Extract attendee list from calendar event.

    Handles two formats in calendar_events.attendees:
    - Array of email strings: ["email@example.com"]
    - Array of objects: [{"email": "email@example.com", "name": "John"}]

    Falls back to calendar_events.metadata.attendees.
    Filters out hello@luminone.com.
    """
    raw_attendees: list[Any] = []

    if calendar_event:
        raw_attendees = calendar_event.get("attendees") or []
        if not raw_attendees:
            metadata = calendar_event.get("metadata") or {}
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
            raw_attendees = metadata.get("attendees", [])

    attendees: list[dict[str, str]] = []
    for att in raw_attendees:
        if isinstance(att, str):
            email = att.strip().lower()
            if email and email != "hello@luminone.com":
                attendees.append({"email": email, "name": ""})
        elif isinstance(att, dict):
            email = (att.get("email") or "").strip().lower()
            name = att.get("name") or att.get("displayName") or ""
            if email and email != "hello@luminone.com":
                attendees.append({"email": email, "name": name})

    if not attendees:
        attendees = [
            {"email": "attendee@unknown.com", "name": "Meeting Attendee"}
        ]

    return attendees


async def _create_followup_drafts(
    db: Any,
    user_id: str,
    debrief_id: str,
    meeting_session_id: str,
    meeting_title: str,
    summary: str,
    action_items: list[Any],
    next_steps: list[Any],
    attendees: list[dict[str, str]],
) -> int:
    """Generate and insert follow-up email drafts for each attendee."""
    action_items_text = _format_items(action_items)
    next_steps_text = _format_items(next_steps)

    email_body = await _generate_followup_email(
        meeting_title=meeting_title,
        summary=summary,
        action_items_text=action_items_text,
        next_steps_text=next_steps_text,
    )

    count = 0
    for attendee in attendees:
        try:
            db.table("email_drafts").insert({
                "user_id": user_id,
                "recipient_email": attendee["email"],
                "recipient_name": attendee.get("name") or None,
                "subject": f"Following up \u2014 {meeting_title}",
                "body": email_body,
                "purpose": "follow_up",
                "status": "draft",
                "draft_type": "debrief_followup",
                "context": json.dumps({
                    "debrief_id": debrief_id,
                    "meeting_session_id": meeting_session_id,
                    "source": "debrief_approval",
                }),
            }).execute()
            count += 1
        except Exception:
            logger.exception(
                "[DebriefApproval] Failed to insert email draft for %s",
                attendee["email"],
            )

    return count


def _format_items(items: list[Any]) -> str:
    """Format action items / next steps into readable text for LLM prompt."""
    parts: list[str] = []
    for item in items:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = (
                item.get("item")
                or item.get("task")
                or item.get("description")
                or str(item)
            )
            owner = item.get("owner", "")
            due = item.get("due") or item.get("due_date") or ""
            if owner:
                text += f" (owner: {owner})"
            if due:
                text += f" (due: {due})"
            parts.append(text)
    return "; ".join(parts) if parts else "None specified"


async def _generate_followup_email(
    meeting_title: str,
    summary: str,
    action_items_text: str,
    next_steps_text: str,
) -> str:
    """Generate follow-up email body using LLM, with fallback template."""
    try:
        from src.core.llm import LLMClient
        from src.core.task_types import TaskType

        prompt = (
            "Write a warm, professional follow-up email (max 150 words) "
            "from Dhruv Patwardhan.\n"
            f"Meeting: {meeting_title}.\n"
            f"Summary: {summary}\n"
            f"Action items: {action_items_text}\n"
            f"Next steps: {next_steps_text}\n"
            "Reference specific discussion points. "
            "Confirm action items with owners and deadlines.\n"
            "Return only the email body, no subject line."
        )

        llm = LLMClient()
        response = await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,
            task=TaskType.SCRIBE_DRAFT_EMAIL,
            agent_id="debrief_followup",
        )
        return response.strip()

    except Exception:
        logger.exception(
            "[DebriefApproval] LLM email generation failed, using fallback"
        )
        return (
            f"Hi,\n\n"
            f"Thank you for the productive conversation during our meeting "
            f'"{meeting_title}." I wanted to follow up on what we discussed.\n\n'
            f"Key points from our discussion:\n{summary}\n\n"
            f"Action items we agreed on:\n{action_items_text}\n\n"
            f"Next steps:\n{next_steps_text}\n\n"
            f"Please let me know if I missed anything or if you have questions.\n\n"
            f"Best regards,\nDhruv"
        )


def _write_memory_facts(
    db: Any,
    user_id: str,
    debrief_id: str,
    meeting_title: str,
    meeting_time: str,
    summary: str,
    stakeholder_signals: list[Any],
    action_items: list[Any],
    attendees: list[dict[str, str]],
) -> int:
    """Write semantic memory facts for each external attendee."""
    meeting_date = meeting_time[:10] if meeting_time else "recently"

    signals_text = ""
    if stakeholder_signals:
        signal_parts: list[str] = []
        for s in stakeholder_signals:
            if isinstance(s, str):
                signal_parts.append(s)
            elif isinstance(s, dict):
                signal_parts.append(
                    s.get("content") or s.get("signal") or str(s)
                )
        signals_text = "; ".join(signal_parts[:3])

    count = 0
    for attendee in attendees:
        attendee_name = attendee.get("name") or attendee.get("email", "Unknown")

        fact = (
            f"{attendee_name} met with Dhruv on {meeting_date}. "
            f"{summary}"
        )
        if signals_text:
            fact += f" Signals: {signals_text}"

        try:
            db.table("memory_semantic").insert({
                "user_id": user_id,
                "fact": fact,
                "confidence": 0.9,
                "source": "meeting_debrief",
                "metadata": json.dumps({
                    "debrief_id": debrief_id,
                    "meeting_title": meeting_title,
                    "action_items": action_items,
                    "reference_id": debrief_id,
                }),
            }).execute()
            count += 1
        except Exception:
            logger.exception(
                "[DebriefApproval] Failed to write memory fact for %s",
                attendee_name,
            )

    return count


# ======================================================================
# Stream C2: Future Meeting Brief Enrichment
# ======================================================================


async def _enrich_future_meeting_briefs(
    db: Any,
    user_id: str,
    debrief_row: dict[str, Any],
    calendar_event: dict[str, Any] | None,
    attendees: list[dict[str, str]],
) -> int:
    """Enrich future meeting briefs with relationship history.

    After a debrief is approved, find ALL future calendar events for this user
    that share attendees with the completed meeting, and inject relationship
    history into their metadata so the next meeting brief is pre-loaded.

    Returns count of events enriched.
    """
    # 1. Extract attendee emails from attendees list
    attendee_emails = [
        a.get("email", "").lower()
        for a in attendees
        if a.get("email") and "luminone.com" not in a.get("email", "").lower()
    ]

    if not attendee_emails:
        logger.info(
            "[C2Enrich] No external attendees found for debrief %s, skipping",
            debrief_row.get("id"),
        )
        return 0

    # 2. Find future calendar events for this user that share any of these attendees
    # Using Supabase client with ilike filter on attendees jsonb column
    future_events: list[dict[str, Any]] = []

    for email in attendee_emails:
        try:
            # Query events where attendees jsonb contains this email
            result = (
                db.table("calendar_events")
                .select("id, title, start_time, attendees, metadata")
                .eq("user_id", user_id)
                .gt("start_time", datetime.now(UTC).isoformat())
                .ilike("attendees", f"%{email}%")
                .order("start_time")
                .limit(20)
                .execute()
            )
            if result.data:
                # Deduplicate by event id
                for event in result.data:
                    if event["id"] not in [e["id"] for e in future_events]:
                        future_events.append(event)
        except Exception:
            logger.exception("[C2Enrich] Failed to query future events for %s", email)

    if not future_events:
        logger.info(
            "[C2Enrich] No future events found for attendees %s",
            attendee_emails,
        )
        return 0

    logger.info(
        "[C2Enrich] Found %d future events for attendees %s",
        len(future_events),
        attendee_emails,
    )

    # 3. Load ALL historical debriefs for this user involving these attendees
    historical_debriefs: list[dict[str, Any]] = []

    for email in attendee_emails:
        try:
            # Query debriefs - check if stakeholder_signals or notes contain the email
            # Also check via linked calendar_event attendees
            result = (
                db.table("meeting_debriefs")
                .select(
                    "id, meeting_title, meeting_time, summary, key_decisions, "
                    "action_items, stakeholder_signals, next_steps, sentiment_score, "
                    "calendar_event_id"
                )
                .eq("user_id", user_id)
                .lt("meeting_time", datetime.now(UTC).isoformat())
                .order("meeting_time", desc=True)
                .limit(10)
                .execute()
            )
            if result.data:
                for debrief in result.data:
                    # Check if this debrief is related to these attendees
                    # by checking the linked calendar event's attendees
                    if debrief.get("calendar_event_id"):
                        ce_result = (
                            db.table("calendar_events")
                            .select("attendees")
                            .eq("id", debrief["calendar_event_id"])
                            .limit(1)
                            .execute()
                        )
                        if ce_result.data:
                            cal_attendees = ce_result.data[0].get("attendees") or []
                            cal_emails = [
                                a.get("email", "").lower() if isinstance(a, dict) else str(a).lower()
                                for a in cal_attendees
                            ]
                            if any(e in cal_emails for e in attendee_emails):
                                if debrief["id"] not in [d["id"] for d in historical_debriefs]:
                                    historical_debriefs.append(debrief)
        except Exception:
            logger.exception("[C2Enrich] Failed to query historical debriefs for %s", email)

    # 4. Load stakeholder profiles for these attendees from lead_memory_stakeholders
    stakeholder_profiles: list[dict[str, Any]] = []

    for email in attendee_emails:
        try:
            result = (
                db.table("lead_memory_stakeholders")
                .select(
                    "contact_email, contact_name, title, role, sentiment, "
                    "influence_level, notes, personality_insights, last_contacted_at"
                )
                .ilike("contact_email", email)
                .limit(1)
                .execute()
            )
            if result.data:
                row = result.data[0]
                stakeholder_profiles.append({
                    "email": row.get("contact_email"),
                    "name": row.get("contact_name"),
                    "title": row.get("title"),
                    "role": row.get("role"),
                    "sentiment": row.get("sentiment"),
                    "influence_level": row.get("influence_level"),
                    "notes": row.get("notes"),
                    "personality_insights": row.get("personality_insights"),
                    "last_contacted_at": row.get("last_contacted_at"),
                })
        except Exception:
            logger.exception("[C2Enrich] Failed to query stakeholder profile for %s", email)

    # 5. Load open commitments from memory_prospective for these attendees
    open_commitments: list[dict[str, Any]] = []

    try:
        result = (
            db.table("memory_prospective")
            .select("task, trigger_config, priority, status")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        if result.data:
            for row in result.data:
                trigger_config = row.get("trigger_config") or {}
                open_commitments.append({
                    "task": row.get("task"),
                    "due_date": trigger_config.get("due_date"),
                    "priority": row.get("priority"),
                })
    except Exception:
        logger.exception("[C2Enrich] Failed to query open commitments")

    # 6. Generate talking points via LLM for these attendees
    history_summary = "\n".join([
        f"- {d.get('meeting_time', 'Unknown date')[:10] if d.get('meeting_time') else 'Unknown date'}: "
        f"{d.get('meeting_title') or 'Meeting'} — {(d.get('summary') or '')[:200]}"
        for d in historical_debriefs
    ]) or "No previous meetings recorded."

    talking_points = await _generate_talking_points(
        attendee_emails=attendee_emails,
        history_summary=history_summary,
        open_commitments=[c["task"] for c in open_commitments[:5]],
    )

    # 7. Build the enriched aria_context object
    aria_context = {
        "relationship_history": [
            {
                "date": d.get("meeting_time"),
                "title": d.get("meeting_title"),
                "summary": d.get("summary"),
                "key_decisions": d.get("key_decisions"),
                "sentiment_score": float(d["sentiment_score"]) if d.get("sentiment_score") else None,
                "action_items": d.get("action_items"),
            }
            for d in historical_debriefs[:5]  # Limit to 5 most recent
        ],
        "stakeholder_profiles": stakeholder_profiles,
        "open_commitments": open_commitments[:5],  # Limit to 5
        "talking_points": talking_points,
        "enriched_at": datetime.now(UTC).isoformat(),
        "enriched_from_debrief": str(debrief_row.get("id")),
    }

    # 8. Update each future event's metadata with aria_context
    enriched_count = 0
    for event in future_events:
        try:
            existing_metadata = event.get("metadata") or {}
            if isinstance(existing_metadata, str):
                try:
                    existing_metadata = json.loads(existing_metadata)
                except (json.JSONDecodeError, TypeError):
                    existing_metadata = {}

            updated_metadata = {**existing_metadata, "aria_context": aria_context}

            db.table("calendar_events").update({
                "metadata": updated_metadata,
            }).eq("id", event["id"]).eq("user_id", user_id).execute()

            enriched_count += 1
            logger.info(
                "[C2Enrich] Enriched future event '%s' (id: %s) with relationship history",
                event.get("title"),
                event.get("id"),
            )
        except Exception:
            logger.exception(
                "[C2Enrich] Failed to update event %s",
                event.get("id"),
            )

    logger.info(
        "[C2Enrich] C2 enrichment complete: %d future events enriched for user %s",
        enriched_count,
        user_id,
    )
    return enriched_count


async def _generate_talking_points(
    attendee_emails: list[str],
    history_summary: str,
    open_commitments: list[str],
) -> dict[str, Any]:
    """Generate pre-meeting talking points via LLM."""
    try:
        from src.core.llm import LLMClient
        from src.core.task_types import TaskType

        prompt = f"""Based on the meeting history below, generate structured pre-meeting intelligence.

Attendees: {', '.join(attendee_emails)}
Meeting history:
{history_summary}

Open commitments: {open_commitments}

Return JSON only:
{{
  "talking_points": ["<5 specific, contextual points based on history>"],
  "watch_outs": ["<topics that caused friction or stalled before>"],
  "commitments_to_reference": ["<things promised in previous meetings>"],
  "suggested_opening": "<specific, personal 1-sentence opening referencing last interaction>"
}}"""

        llm = LLMClient()
        response = await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.7,
            task=TaskType.SCRIBE_DRAFT_EMAIL,
            agent_id="c2_talking_points",
        )

        # Parse JSON response
        raw = response.strip()
        # Remove markdown code blocks if present
        raw = re.sub(r"```json|```", "", raw).strip()
        talking_points = json.loads(raw)

        return talking_points

    except Exception:
        logger.exception("[C2Enrich] Could not generate talking points")
        return {
            "talking_points": [],
            "watch_outs": [],
            "commitments_to_reference": open_commitments[:3],
            "suggested_opening": "",
        }

