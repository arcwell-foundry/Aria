"""Extract lead intelligence signals from email content.

When ARIA processes emails (autonomous or on-demand), this service checks
whether the sender/company matches an existing lead in the pipeline and
extracts business intelligence signals (competitor mentions, deal stage
changes, stakeholder shifts, etc.) via LLM analysis.

Matched signals are recorded as lead events (EventType.SIGNAL) so they
appear in the lead timeline and feed into health-score recalculation.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.memory.lead_memory import LeadMemoryService
from src.memory.lead_memory_events import LeadEventService
from src.models.lead_memory import EventType, LeadEventCreate

logger = logging.getLogger(__name__)

# Freemail / personal domains — skip these for lead matching
PERSONAL_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "aol.com", "icloud.com", "me.com", "mac.com", "live.com",
    "msn.com", "protonmail.com", "proton.me", "hey.com",
    "fastmail.com", "zoho.com", "yandex.com", "mail.com",
    "gmx.com", "gmx.net",
})

_SIGNAL_EXTRACTION_PROMPT = """\
Analyze this email and extract business intelligence signals relevant \
to a sales pursuit.

Subject: {subject}
Body (truncated to 3000 chars):
{body}
Thread context: {thread_context}

Extract signals in these categories:
- competitor_mention: Any competitor named or compared
- deal_stage_signal: Budget discussion, timeline, procurement, approval
- stakeholder_change: New person involved, role change, org restructure
- timeline_shift: Deadline moved, project delayed/accelerated
- sentiment_shift: Tone changed (more urgent, cooling off, frustrated)
- budget_signal: Pricing discussion, budget constraints, funding
- technical_requirement: Specific product/feature needs mentioned

Return a JSON array. Each signal object:
{{"category": "...", "detail": "...", "confidence": 0.0-1.0}}

Rules:
- Only include signals with confidence > 0.6.
- If no meaningful signals found, return [].
- Keep "detail" concise (one sentence).
- Do NOT wrap the JSON in markdown code fences.
"""


class EmailLeadIntelligence:
    """Extract lead intelligence from emails and update lead memory."""

    def __init__(self) -> None:
        self._llm = LLMClient()
        self._lead_service = LeadMemoryService()

    async def process_email_for_leads(
        self,
        user_id: str,
        email: dict[str, Any],
        thread_summary: str = "",
    ) -> list[dict[str, Any]]:
        """Check if email is from a lead/account and extract intel.

        Args:
            user_id: The user who owns the leads.
            email: Dict with at least sender_email, subject, body.
            thread_summary: Optional thread summary for context.

        Returns:
            List of signal dicts with lead_id, company, signal info.
            Empty list if sender is not associated with any lead.
        """
        sender_email = email.get("sender_email", "")
        sender_domain = sender_email.rsplit("@", 1)[-1].lower() if "@" in sender_email else ""

        if not sender_domain or sender_domain in PERSONAL_DOMAINS:
            return []

        try:
            leads = await self._match_sender_to_leads(user_id, sender_domain)
        except Exception:
            logger.exception("Failed to match sender %s to leads", sender_email)
            return []

        if not leads:
            return []

        # Extract intelligence signals via LLM
        body = email.get("body", "")
        if isinstance(body, dict):
            body = body.get("content", "")

        signals = await self._extract_signals(
            body=str(body)[:3000],
            subject=email.get("subject", ""),
            thread_context=thread_summary,
            user_id=user_id,
        )

        if not signals:
            return []

        # Record each signal against matched leads
        updates: list[dict[str, Any]] = []
        for lead in leads:
            for signal in signals:
                await self._record_signal(user_id, lead, signal)
                updates.append({
                    "lead_id": lead["id"],
                    "company": lead["company_name"],
                    "signal": signal,
                })

            # Recalculate health score if we got deal/budget/timeline signals
            recalc_categories = {"deal_stage_signal", "budget_signal", "timeline_shift"}
            if any(s["category"] in recalc_categories for s in signals):
                try:
                    await self._lead_service.calculate_health_score(user_id, lead["id"])
                except Exception:
                    logger.warning(
                        "Health score recalc failed for lead %s", lead["id"],
                    )

        if updates:
            logger.info(
                "LEAD_INTEL: %d signals across %d leads from %s",
                len(updates),
                len(leads),
                sender_email,
            )

        return updates

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _match_sender_to_leads(
        self, user_id: str, sender_domain: str,
    ) -> list[dict[str, Any]]:
        """Match a sender domain to existing active leads.

        Matches on company_name containing the domain's root
        (e.g. 'savillex' from 'savillex.com').
        """
        domain_root = sender_domain.split(".")[0]

        client = SupabaseClient.get_client()
        response = (
            client.table("lead_memories")
            .select("id, company_name, status, health_score")
            .eq("user_id", user_id)
            .ilike("company_name", f"%{domain_root}%")
            .in_("status", ["active", "won"])
            .execute()
        )

        return response.data or []

    async def _extract_signals(
        self,
        body: str,
        subject: str,
        thread_context: str,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Use LLM to extract business intelligence signals from email."""
        if not body.strip() and not subject.strip():
            return []

        prompt = _SIGNAL_EXTRACTION_PROMPT.format(
            subject=subject,
            body=body,
            thread_context=thread_context or "(none)",
        )

        try:
            result = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1024,
                user_id=user_id,
            )
        except Exception:
            logger.exception("LLM signal extraction failed")
            return []

        # Strip markdown fences if present
        text = result.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        try:
            signals = json.loads(text)
            if not isinstance(signals, list):
                return []
            # Validate structure
            return [
                s for s in signals
                if isinstance(s, dict)
                and "category" in s
                and "detail" in s
                and s.get("confidence", 0) > 0.6
            ]
        except (json.JSONDecodeError, TypeError):
            logger.warning("Failed to parse LLM signal extraction output")
            return []

    async def _record_signal(
        self,
        user_id: str,
        lead: dict[str, Any],
        signal: dict[str, Any],
    ) -> None:
        """Record an extracted signal as a lead event."""
        try:
            client = SupabaseClient.get_client()
            event_service = LeadEventService(db_client=client)

            event_data = LeadEventCreate(
                event_type=EventType.SIGNAL,
                direction=None,
                subject=f"Email intel: {signal['category']}",
                content=signal["detail"],
                participants=[],
                occurred_at=datetime.now(UTC),
                source="email_intelligence",
            )

            await event_service.add_event(
                user_id=user_id,
                lead_memory_id=lead["id"],
                event_data=event_data,
            )

            if signal["category"] == "competitor_mention":
                logger.info(
                    "COMPETITOR_DETECTED: %s for lead %s (%s)",
                    signal["detail"],
                    lead["id"],
                    lead["company_name"],
                )

        except Exception:
            logger.exception(
                "Failed to record signal for lead %s", lead["id"],
            )
