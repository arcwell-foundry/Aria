"""Email Intelligence Extraction Service.

Extracts structured facts from email content and correlates them with
ARIA's unified data lake (market signals, calendar, battle cards, goals,
and existing semantic memory). Creates actionable insights that flow to
the action queue and briefings.

Architecture:
- Called after email classification in email_analyzer.py
- Processes NEEDS_REPLY and FYI emails (skips SKIP)
- Deduplicates by checking email_id in memory_semantic metadata
- Cross-references extracted facts against all ARIA memory sources
- Creates aria_actions for time-sensitive signals
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import SupabaseClient

if TYPE_CHECKING:
    from src.services.email_analyzer import EmailCategory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class ExtractedFact(BaseModel):
    """A single fact extracted from an email."""

    fact: str
    type: str  # person, company, commitment, deal_signal, topic, date
    confidence: float
    entity: str  # company or person name


class CorrelationInsight(BaseModel):
    """An insight from correlating email facts with ARIA's data lake."""

    pattern_type: str  # engagement_trend, deal_signal, follow_up_needed, new_relationship, competitive_context, meeting_context, goal_progress
    insight: str
    strategic_implication: str | None = None
    confidence: float
    entities: list[str] = field(default_factory=list)
    source_connections: dict[str, Any] = field(default_factory=dict)  # What was correlated
    is_actionable: bool = False
    action_type: str | None = None  # lead_discovery, follow_up, etc.


class ExtractionResult(BaseModel):
    """Result of email intelligence extraction."""

    emails_processed: int
    facts_extracted: int
    insights_generated: int
    actions_created: int
    skipped_already_processed: int


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EmailIntelligenceService:
    """Service for extracting intelligence from emails and correlating with data lake."""

    def __init__(self, llm_client: LLMClient | None = None):
        """Initialize the service."""
        self._llm = llm_client or LLMClient()
        self._supabase = SupabaseClient.get_client()

    async def extract_and_store(
        self,
        user_id: str,
        emails: list[EmailCategory],
    ) -> ExtractionResult:
        """Main entry point. Extracts facts from emails and correlates with data lake.

        Args:
            user_id: The user ID.
            emails: List of classified emails (NEEDS_REPLY or FYI).

        Returns:
            ExtractionResult with counts.
        """
        result = ExtractionResult(
            emails_processed=0,
            facts_extracted=0,
            insights_generated=0,
            actions_created=0,
            skipped_already_processed=0,
        )

        if not emails:
            return result

        # Step 1: Filter out already-processed emails
        new_emails = await self._filter_new_emails(user_id, emails)
        result.skipped_already_processed = len(emails) - len(new_emails)

        if not new_emails:
            logger.info(
                "EmailIntelligence: All emails already processed for user %s",
                user_id,
            )
            return result

        result.emails_processed = len(new_emails)

        # Step 2: Extract facts from each new email
        all_facts: list[tuple[EmailCategory, list[ExtractedFact]]] = []
        for email in new_emails:
            facts = await self._extract_facts_from_email(email)
            if facts:
                all_facts.append((email, facts))

        total_facts = sum(len(f) for _, f in all_facts)
        result.facts_extracted = total_facts

        if total_facts == 0:
            logger.info("EmailIntelligence: No facts extracted from %d emails", len(new_emails))
            return result

        # Step 3: Store facts to memory_semantic
        for email, facts in all_facts:
            await self._store_facts_to_memory(user_id, email, facts)

        # Step 4: Correlate with data lake and generate insights
        all_extracted_facts = [f for _, facts_list in all_facts for f in facts_list]
        insights = await self._correlate_with_data_lake(user_id, new_emails, all_extracted_facts)
        result.insights_generated = len(insights)

        # Step 5: Store insights to cross_email_intelligence
        if insights:
            await self._store_insights(user_id, insights)

        # Step 6: Create aria_actions for actionable insights
        actionable = [i for i in insights if i.is_actionable and i.action_type]
        for insight in actionable:
            await self._create_aria_action(user_id, insight)
        result.actions_created = len(actionable)

        logger.info(
            "EmailIntelligence: Processed %d emails, extracted %d facts, generated %d insights, created %d actions",
            result.emails_processed,
            result.facts_extracted,
            result.insights_generated,
            result.actions_created,
        )

        return result

    # ---------------------------------------------------------------------------
    # Deduplication
    # ---------------------------------------------------------------------------

    async def _filter_new_emails(
        self,
        user_id: str,
        emails: list[EmailCategory],
    ) -> list[EmailCategory]:
        """Filter out emails that have already been processed.

        Checks if email_id exists in memory_semantic metadata.
        """
        email_ids = [e.email_id for e in emails]
        if not email_ids:
            return []

        # Query memory_semantic for existing email_ids
        try:
            response = (
                self._supabase.table("memory_semantic")
                .select("metadata->>email_id")
                .eq("user_id", user_id)
                .eq("source", "email_content_extraction")
                .in_("metadata->>email_id", email_ids)
                .execute()
            )

            processed_ids = set()
            for row in response.data or []:
                email_id = row.get("metadata->>email_id") or row.get("email_id")
                if email_id:
                    processed_ids.add(email_id)

            new_emails = [e for e in emails if e.email_id not in processed_ids]
            logger.debug(
                "EmailIntelligence: %d/%d emails are new (not already processed)",
                len(new_emails),
                len(emails),
            )
            return new_emails

        except Exception as e:
            logger.warning(
                "EmailIntelligence: Failed to check processed emails, processing all: %s",
                e,
            )
            return emails

    # ---------------------------------------------------------------------------
    # Fact Extraction (LLM)
    # ---------------------------------------------------------------------------

    async def _extract_facts_from_email(
        self,
        email: EmailCategory,
    ) -> list[ExtractedFact]:
        """Call Haiku to extract structured facts from email content."""
        # Build content for extraction
        body_text = email.body or email.snippet or ""
        if len(body_text) > 2000:
            body_text = body_text[:2000] + "..."

        prompt = f"""Extract structured facts from this email. Return JSON array of facts.

Email from: {email.sender_name} ({email.sender_email})
Subject: {email.subject}
Body: {body_text}

Extract ONLY facts that are explicitly stated or directly implied:
- People mentioned (name, title, company, role if stated)
- Companies mentioned (name, what's said about them)
- Commitments or action items (who committed to what, by when)
- Deal/business signals (pricing discussed, NDA mentioned, demo requested, timeline given)
- Topics discussed (what the email is actually about)
- Dates or deadlines mentioned

Rules:
- Only extract facts explicitly present in the email text
- Never infer or assume beyond what's written
- Each fact should be a single clear statement
- Include the sender's relationship context (e.g., "Jayesh Zala is from Nira Systems")

Return format (JSON array only, no markdown):
[
  {{"fact": "clear factual statement", "type": "person|company|commitment|deal_signal|topic|date", "confidence": 0.9, "entity": "company or person name"}}
]

If no facts can be extracted, return an empty array: []"""

        try:
            response = await self._llm.generate(
                messages=[{"role": "user", "content": prompt}],
                task=TaskType.ENTITY_EXTRACT,
                user_id="",  # Don't track per-user for extraction
                max_tokens=1024,
                temperature=0.1,
            )

            # Parse JSON response
            response_text = response.strip()
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                response_text = re.sub(r"^```(?:json)?\s*", "", response_text)
                response_text = re.sub(r"\s*```$", "", response_text)

            facts_data = json.loads(response_text)
            if not isinstance(facts_data, list):
                logger.warning(
                    "EmailIntelligence: LLM returned non-list for email %s",
                    email.email_id,
                )
                return []

            facts = []
            for item in facts_data:
                try:
                    fact = ExtractedFact(
                        fact=item.get("fact", ""),
                        type=item.get("type", "topic"),
                        confidence=min(1.0, max(0.0, float(item.get("confidence", 0.7)))),
                        entity=item.get("entity", ""),
                    )
                    if fact.fact:
                        facts.append(fact)
                except Exception as e:
                    logger.debug("EmailIntelligence: Skipping invalid fact item: %s", e)

            logger.debug(
                "EmailIntelligence: Extracted %d facts from email %s",
                len(facts),
                email.email_id,
            )
            return facts

        except json.JSONDecodeError as e:
            logger.warning(
                "EmailIntelligence: Failed to parse LLM response for email %s: %s",
                email.email_id,
                e,
            )
            return []
        except Exception as e:
            logger.error(
                "EmailIntelligence: LLM extraction failed for email %s: %s",
                email.email_id,
                e,
            )
            return []

    # ---------------------------------------------------------------------------
    # Storage
    # ---------------------------------------------------------------------------

    async def _store_facts_to_memory(
        self,
        user_id: str,
        email: EmailCategory,
        facts: list[ExtractedFact],
    ) -> None:
        """Store extracted facts to memory_semantic table."""
        for fact in facts:
            try:
                row = {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "fact": fact.fact,
                    "confidence": fact.confidence,
                    "source": "email_content_extraction",
                    "metadata": json.dumps({
                        "email_id": email.email_id,
                        "sender": email.sender_email,
                        "sender_name": email.sender_name,
                        "subject": email.subject,
                        "entity": fact.entity,
                        "type": fact.type,
                        "extracted_at": datetime.now(UTC).isoformat(),
                    }),
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
                self._supabase.table("memory_semantic").insert(row).execute()
            except Exception as e:
                logger.warning(
                    "EmailIntelligence: Failed to store fact for email %s: %s",
                    email.email_id,
                    e,
                )

    async def _store_insights(
        self,
        user_id: str,
        insights: list[CorrelationInsight],
    ) -> None:
        """Store insights to cross_email_intelligence table."""
        for insight in insights:
            try:
                # Extract company domains from entities
                domains = self._extract_domains_from_entities(insight.entities)

                row = {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "pattern_type": insight.pattern_type,
                    "company_domain": domains[0] if domains else None,
                    "email_count": len(insight.entities),
                    "senders": insight.entities,
                    "insight": insight.insight,
                    "strategic_implication": insight.strategic_implication,
                    "detected_at": datetime.now(UTC).isoformat(),
                    "briefing_included": False,
                }
                self._supabase.table("cross_email_intelligence").insert(row).execute()
            except Exception as e:
                logger.warning(
                    "EmailIntelligence: Failed to store insight: %s",
                    e,
                )

    def _extract_domains_from_entities(self, entities: list[str]) -> list[str]:
        """Extract email domains from entity list."""
        domains = []
        for entity in entities:
            if "@" in entity:
                domain = entity.split("@")[-1].lower()
                # Skip common email providers
                if domain not in ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com"):
                    domains.append(domain)
        return list(set(domains))

    # ---------------------------------------------------------------------------
    # Cross-Source Correlation
    # ---------------------------------------------------------------------------

    async def _correlate_with_data_lake(
        self,
        user_id: str,
        emails: list[EmailCategory],
        facts: list[ExtractedFact],
    ) -> list[CorrelationInsight]:
        """Cross-reference extracted facts against all ARIA memory sources.

        Correlates with:
        - market_signals: company name matches
        - calendar_events: sender email matches attendees
        - battle_cards: competitor name matches
        - goals: keyword matches in goal titles
        - memory_semantic: existing facts about same entities
        """
        insights: list[CorrelationInsight] = []

        # Collect entities from facts
        companies = {f.entity for f in facts if f.type == "company"}
        people = {f.entity for f in facts if f.type == "person"}
        deal_signals = [f for f in facts if f.type == "deal_signal"]
        commitments = [f for f in facts if f.type == "commitment"]

        # Get sender domains for company inference
        sender_domains: dict[str, str] = {}
        for email in emails:
            if "@" in email.sender_email:
                domain = email.sender_email.split("@")[-1].lower()
                if domain not in ("gmail.com", "yahoo.com", "outlook.com", "hotmail.com"):
                    sender_domains[email.sender_email] = domain

        # 1. Correlate with market_signals
        market_insights = await self._correlate_market_signals(user_id, companies, sender_domains)
        insights.extend(market_insights)

        # 2. Correlate with calendar_events
        calendar_insights = await self._correlate_calendar(
            user_id,
            [e.sender_email for e in emails],
            people,
        )
        insights.extend(calendar_insights)

        # 3. Correlate with battle_cards
        battle_insights = await self._correlate_battle_cards(user_id, companies, sender_domains)
        insights.extend(battle_insights)

        # 4. Correlate with goals
        goal_insights = await self._correlate_goals(user_id, emails, people, companies)
        insights.extend(goal_insights)

        # 5. Correlate with existing memory_semantic
        memory_insights = await self._correlate_memory(user_id, facts)
        insights.extend(memory_insights)

        # 6. Generate deal signal insights
        if deal_signals:
            deal_insights = self._generate_deal_signal_insights(deal_signals, emails)
            insights.extend(deal_insights)

        # 7. Check for follow-up gaps
        followup_insights = await self._check_follow_up_gaps(user_id, emails)
        insights.extend(followup_insights)

        return insights

    async def _correlate_market_signals(
        self,
        user_id: str,
        companies: set[str],
        sender_domains: dict[str, str],
    ) -> list[CorrelationInsight]:
        """Correlate with market_signals table."""
        insights: list[CorrelationInsight] = []
        if not companies and not sender_domains:
            return insights

        try:
            # Get recent market signals (last 30 days)
            thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
            response = (
                self._supabase.table("market_signals")
                .select("*")
                .eq("user_id", user_id)
                .gte("detected_at", thirty_days_ago)
                .is_("dismissed_at", "null")
                .execute()
            )

            for signal in response.data or []:
                signal_company = (signal.get("company_name") or "").lower()
                signal_domain = signal.get("metadata", {}).get("domain", "")

                # Check if any email relates to this signal
                matched_company = None
                for company in companies:
                    if company.lower() in signal_company or signal_company in company.lower():
                        matched_company = company
                        break

                matched_domain = None
                for email, domain in sender_domains.items():
                    if domain in signal_domain or signal_domain in domain:
                        matched_domain = domain
                        break

                if matched_company or matched_domain:
                    insights.append(CorrelationInsight(
                        pattern_type="competitive_context",
                        insight=f"Email from {matched_company or matched_domain} relates to market signal: {signal.get('headline', 'Unknown signal')}",
                        strategic_implication=signal.get("summary"),
                        confidence=0.85,
                        entities=[matched_company or matched_domain],
                        source_connections={
                            "market_signal_id": signal.get("id"),
                            "signal_type": signal.get("signal_type"),
                        },
                        is_actionable=True,
                        action_type="lead_discovery",
                    ))

        except Exception as e:
            logger.warning("EmailIntelligence: Failed to correlate market signals: %s", e)

        return insights

    async def _correlate_calendar(
        self,
        user_id: str,
        sender_emails: list[str],
        people: set[str],
    ) -> list[CorrelationInsight]:
        """Correlate with calendar_events table."""
        insights: list[CorrelationInsight] = []
        if not sender_emails:
            return insights

        try:
            # Get upcoming events (next 14 days)
            now = datetime.now(UTC)
            future = (now + timedelta(days=14)).isoformat()

            response = (
                self._supabase.table("calendar_events")
                .select("*")
                .eq("user_id", user_id)
                .gte("start_time", now.isoformat())
                .lte("start_time", future)
                .execute()
            )

            for event in response.data or []:
                attendees = event.get("attendees", [])
                if isinstance(attendees, str):
                    try:
                        attendees = json.loads(attendees)
                    except Exception:
                        attendees = []

                attendee_emails = {a.get("email", "").lower() for a in attendees if isinstance(a, dict)}

                # Check if any sender is an attendee
                matched_senders = []
                for sender in sender_emails:
                    if sender.lower() in attendee_emails:
                        matched_senders.append(sender)

                if matched_senders:
                    event_title = event.get("title", "Upcoming meeting")
                    event_time = event.get("start_time", "")
                    insights.append(CorrelationInsight(
                        pattern_type="meeting_context",
                        insight=f"Email from {matched_senders[0]} ahead of scheduled meeting: '{event_title}'",
                        strategic_implication=f"Review this email for meeting prep. Meeting scheduled for {event_time}",
                        confidence=0.9,
                        entities=matched_senders,
                        source_connections={
                            "calendar_event_id": event.get("id"),
                            "event_title": event_title,
                            "event_time": event_time,
                        },
                        is_actionable=True,
                        action_type="meeting_prep",
                    ))

        except Exception as e:
            logger.warning("EmailIntelligence: Failed to correlate calendar: %s", e)

        return insights

    async def _correlate_battle_cards(
        self,
        user_id: str,
        companies: set[str],
        sender_domains: dict[str, str],
    ) -> list[CorrelationInsight]:
        """Correlate with battle_cards table."""
        insights: list[CorrelationInsight] = []

        # First get user's company_id
        try:
            user_resp = (
                self._supabase.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .single()
                .execute()
            )
            company_id = user_resp.data.get("company_id") if user_resp.data else None
            if not company_id:
                return insights
        except Exception:
            return insights

        try:
            response = (
                self._supabase.table("battle_cards")
                .select("*")
                .eq("company_id", company_id)
                .execute()
            )

            for card in response.data or []:
                competitor = (card.get("competitor_name") or "").lower()
                competitor_domain = (card.get("competitor_domain") or "").lower()

                matched = False
                matched_entity = None

                for company in companies:
                    if company.lower() in competitor or competitor in company.lower():
                        matched = True
                        matched_entity = company
                        break

                if not matched:
                    for email, domain in sender_domains.items():
                        if domain in competitor_domain or competitor_domain in domain:
                            matched = True
                            matched_entity = domain
                            break

                if matched:
                    overview = card.get("overview", "")
                    insights.append(CorrelationInsight(
                        pattern_type="competitive_context",
                        insight=f"Email involves tracked competitor: {card.get('competitor_name')}",
                        strategic_implication=f"Battle card available: {overview[:200] if overview else 'Review battle card for competitive positioning'}",
                        confidence=0.85,
                        entities=[matched_entity],
                        source_connections={
                            "battle_card_id": card.get("id"),
                            "competitor_name": card.get("competitor_name"),
                        },
                        is_actionable=False,  # Informational, not action-creating
                    ))

        except Exception as e:
            logger.warning("EmailIntelligence: Failed to correlate battle cards: %s", e)

        return insights

    async def _correlate_goals(
        self,
        user_id: str,
        emails: list[EmailCategory],
        people: set[str],
        companies: set[str],
    ) -> list[CorrelationInsight]:
        """Correlate with goals table."""
        insights: list[CorrelationInsight] = []

        try:
            # Get active goals
            response = (
                self._supabase.table("goals")
                .select("*")
                .eq("user_id", user_id)
                .in_("status", ["active", "in_progress"])
                .execute()
            )

            for goal in response.data or []:
                goal_title = (goal.get("title") or "").lower()
                goal_id = goal.get("id")

                # Check if any email sender/person relates to goal title
                matched_entities = []
                matched_emails = []

                for person in people:
                    if person.lower() in goal_title:
                        matched_entities.append(person)

                for company in companies:
                    if company.lower() in goal_title:
                        matched_entities.append(company)

                # Also check sender names against goal title
                for email in emails:
                    sender_name = (email.sender_name or "").lower()
                    if sender_name and any(word in goal_title for word in sender_name.split() if len(word) > 3):
                        matched_emails.append(email.sender_email)

                if matched_entities or matched_emails:
                    insights.append(CorrelationInsight(
                        pattern_type="goal_progress",
                        insight=f"Email relates to active goal: '{goal.get('title')}'",
                        strategic_implication="This email may represent progress toward the goal. Consider updating goal status.",
                        confidence=0.8,
                        entities=list(set(matched_entities + matched_emails)),
                        source_connections={
                            "goal_id": goal_id,
                            "goal_title": goal.get("title"),
                            "goal_status": goal.get("status"),
                        },
                        is_actionable=False,
                    ))

        except Exception as e:
            logger.warning("EmailIntelligence: Failed to correlate goals: %s", e)

        return insights

    async def _correlate_memory(
        self,
        user_id: str,
        facts: list[ExtractedFact],
    ) -> list[CorrelationInsight]:
        """Correlate with existing memory_semantic facts."""
        insights: list[CorrelationInsight] = []

        if not facts:
            return insights

        try:
            # Get existing facts about the same entities
            entities = list({f.entity for f in facts if f.entity})
            if not entities:
                return insights

            for entity in entities[:5]:  # Limit queries
                response = (
                    self._supabase.table("memory_semantic")
                    .select("*")
                    .eq("user_id", user_id)
                    .neq("source", "email_content_extraction")  # Exclude today's extractions
                    .ilike("fact", f"%{entity}%")
                    .limit(5)
                    .execute()
                )

                existing_facts = response.data or []
                if existing_facts:
                    # Check for confirmations or contradictions
                    existing_summaries = [f.get("fact", "")[:100] for f in existing_facts[:3]]
                    insights.append(CorrelationInsight(
                        pattern_type="memory_reinforcement",
                        insight=f"New email information relates to existing knowledge about {entity}",
                        strategic_implication=f"Existing facts: {'; '.join(existing_summaries)}",
                        confidence=0.75,
                        entities=[entity],
                        source_connections={
                            "related_fact_count": len(existing_facts),
                        },
                        is_actionable=False,
                    ))

        except Exception as e:
            logger.warning("EmailIntelligence: Failed to correlate memory: %s", e)

        return insights

    def _generate_deal_signal_insights(
        self,
        deal_signals: list[ExtractedFact],
        emails: list[EmailCategory],
    ) -> list[CorrelationInsight]:
        """Generate insights from deal signals extracted from emails."""
        insights: list[CorrelationInsight] = []

        for signal in deal_signals:
            # Find the originating email
            originating_email = None
            for email in emails:
                if signal.entity:
                    originating_email = email
                    break

            insights.append(CorrelationInsight(
                pattern_type="deal_signal",
                insight=f"Deal signal detected: {signal.fact}",
                strategic_implication="This may indicate buying intent or deal progression. Consider appropriate follow-up.",
                confidence=signal.confidence,
                entities=[signal.entity] if signal.entity else [],
                source_connections={
                    "signal_type": "deal_signal",
                    "originating_email": originating_email.email_id if originating_email else None,
                },
                is_actionable=True,
                action_type="lead_discovery",
            ))

        return insights

    async def _check_follow_up_gaps(
        self,
        user_id: str,
        emails: list[EmailCategory],
    ) -> list[CorrelationInsight]:
        """Check for follow-up gaps (>3 days since last contact with NEEDS_REPLY senders)."""
        insights: list[CorrelationInsight] = []

        try:
            # Get last contact dates from email_scan_log
            sender_emails = [e.sender_email for e in emails if e.category == "NEEDS_REPLY"]
            if not sender_emails:
                return insights

            three_days_ago = (datetime.now(UTC) - timedelta(days=3)).isoformat()

            for sender_email in sender_emails:
                # Check most recent email from this sender before today
                response = (
                    self._supabase.table("email_scan_log")
                    .select("scanned_at, category")
                    .eq("user_id", user_id)
                    .eq("sender_email", sender_email)
                    .lt("scanned_at", datetime.now(UTC).replace(hour=0, minute=0, second=0).isoformat())
                    .order("scanned_at", desc=True)
                    .limit(1)
                    .execute()
                )

                if response.data:
                    last_contact = response.data[0].get("scanned_at")
                    if last_contact:
                        last_dt = datetime.fromisoformat(last_contact.replace("Z", "+00:00"))
                        days_since = (datetime.now(UTC) - last_dt).days

                        if days_since >= 3:
                            insights.append(CorrelationInsight(
                                pattern_type="follow_up_needed",
                                insight=f"Follow-up gap: {days_since} days since last contact with {sender_email}",
                                strategic_implication="This contact may need re-engagement. Consider reaching out proactively.",
                                confidence=0.8,
                                entities=[sender_email],
                                source_connections={
                                    "days_since_contact": days_since,
                                    "last_contact": last_contact,
                                },
                                is_actionable=True,
                                action_type="follow_up",
                            ))

        except Exception as e:
            logger.warning("EmailIntelligence: Failed to check follow-up gaps: %s", e)

        return insights

    # ---------------------------------------------------------------------------
    # Action Creation
    # ---------------------------------------------------------------------------

    async def _create_aria_action(
        self,
        user_id: str,
        insight: CorrelationInsight,
    ) -> None:
        """Create an aria_actions entry for an actionable insight."""
        try:
            # Estimate time saved based on action type
            time_saved_map = {
                "lead_discovery": 15,
                "follow_up": 10,
                "meeting_prep": 20,
            }

            row = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "action_type": insight.action_type,
                "source_id": insight.source_connections.get("originating_email")
                or insight.source_connections.get("market_signal_id")
                or insight.source_connections.get("calendar_event_id"),
                "status": "pending",
                "estimated_minutes_saved": time_saved_map.get(insight.action_type, 10),
                "metadata": json.dumps({
                    "pattern_type": insight.pattern_type,
                    "insight": insight.insight,
                    "strategic_implication": insight.strategic_implication,
                    "confidence": insight.confidence,
                    "entities": insight.entities,
                    "source_connections": insight.source_connections,
                    "created_from": "email_intelligence",
                    "created_at": datetime.now(UTC).isoformat(),
                }),
                "created_at": datetime.now(UTC).isoformat(),
            }

            self._supabase.table("aria_actions").insert(row).execute()
            logger.info(
                "EmailIntelligence: Created aria_action %s for insight: %s",
                insight.action_type,
                insight.insight[:50],
            )

        except Exception as e:
            logger.warning(
                "EmailIntelligence: Failed to create aria_action: %s",
                e,
            )
