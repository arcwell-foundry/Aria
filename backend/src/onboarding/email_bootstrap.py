"""Priority Email Bootstrap for accelerated onboarding ingestion (US-908).

Processes the last 60 days of SENT mail immediately after email connection
to rapidly seed the relationship graph, refine the Digital Twin writing
style fingerprint, detect active deals, and identify follow-up commitments.

Full 1-year archive is queued for nightly batch processing.
"""

import json
import logging
import uuid
from collections import Counter
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EmailContact(BaseModel):
    """A contact discovered from email recipients."""

    email: str
    name: str | None = None
    title: str | None = None
    company: str | None = None
    interaction_count: int = 0
    last_interaction: str | None = None
    relationship_type: str = "unknown"  # colleague, client, prospect, vendor, personal


class ActiveThread(BaseModel):
    """An email thread with enough activity to be notable."""

    subject: str
    participants: list[str]
    message_count: int
    last_activity: str
    thread_type: str = "unknown"  # deal, project, routine, personal
    commitments: list[str] = Field(default_factory=list)


class CommunicationPatterns(BaseModel):
    """Timing and behavioural patterns extracted from sent emails."""

    avg_response_time_hours: float = 0.0
    peak_send_hours: list[int] = Field(default_factory=list)
    peak_send_days: list[str] = Field(default_factory=list)
    emails_per_day_avg: float = 0.0
    follow_up_cadence_days: float = 0.0
    top_recipients: list[str] = Field(default_factory=list)


class EmailBootstrapResult(BaseModel):
    """Summary of a bootstrap run."""

    emails_processed: int = 0
    contacts_discovered: int = 0
    active_threads: int = 0
    commitments_detected: int = 0
    writing_samples_extracted: int = 0
    communication_patterns: CommunicationPatterns | None = None


# Type alias for the optional progress callback.
ProgressCallback = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class PriorityEmailIngestion:
    """Accelerated email processing during onboarding.

    Processes last 60 days of SENT mail to rapidly build:
    - Relationship graph (contacts, companies, frequency)
    - Writing style refinement (augments US-906 fingerprint)
    - Active deal detection
    - Communication patterns
    - Follow-up commitments
    """

    def __init__(self) -> None:
        """Initialize with database and LLM clients."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run_bootstrap(
        self,
        user_id: str,
        progress_callback: ProgressCallback | None = None,
    ) -> EmailBootstrapResult:
        """Run priority email bootstrap for a user.

        Processes the last 60 days of sent emails through the full
        extraction and storage pipeline.

        Args:
            user_id: The authenticated user's ID.
            progress_callback: Optional async callback for stage updates.

        Returns:
            EmailBootstrapResult with processing summary.
        """
        result = EmailBootstrapResult()

        logger.info("EMAIL_BOOTSTRAP: Starting for user %s", user_id)

        # Store initial processing status
        await self._store_bootstrap_status(user_id, "processing")

        try:
            # 1. Load privacy exclusions
            logger.info("EMAIL_BOOTSTRAP: Loading privacy exclusions for user %s", user_id)
            exclusions = await self._load_exclusions(user_id)
            logger.info(
                "EMAIL_BOOTSTRAP: Loaded %d privacy exclusions for user %s",
                len(exclusions),
                user_id,
            )

            # 2. Fetch sent emails (last 60 days)
            if progress_callback:
                await progress_callback(
                    {"stage": "fetching", "message": "Fetching recent emails..."}
                )

            logger.info(
                "EMAIL_BOOTSTRAP: Fetching sent emails (last 60 days) for user %s",
                user_id,
            )
            emails = await self._fetch_sent_emails(user_id, days=60)
            result.emails_processed = len(emails)
            logger.info(
                "EMAIL_BOOTSTRAP: Fetched %d sent emails from last 60 days for user %s",
                len(emails),
                user_id,
            )

            if not emails:
                logger.info("EMAIL_BOOTSTRAP: No emails found for user %s", user_id)
                return result

            # 3. Filter out excluded senders/domains
            logger.info(
                "EMAIL_BOOTSTRAP: Applying %d exclusions to %d emails for user %s",
                len(exclusions),
                len(emails),
                user_id,
            )
            emails = self._apply_exclusions(emails, exclusions)
            logger.info(
                "EMAIL_BOOTSTRAP: %d emails remaining after exclusions for user %s",
                len(emails),
                user_id,
            )

            # 4. Extract contacts
            if progress_callback:
                await progress_callback(
                    {
                        "stage": "contacts",
                        "message": f"Analyzing {len(emails)} emails for contacts...",
                    }
                )
            logger.info("EMAIL_BOOTSTRAP: Extracting contacts for user %s", user_id)
            contacts = await self._extract_contacts(emails)
            result.contacts_discovered = len(contacts)
            logger.info(
                "EMAIL_BOOTSTRAP: Extracted %d contacts for user %s",
                len(contacts),
                user_id,
            )

            # 5. Identify active threads
            if progress_callback:
                await progress_callback(
                    {
                        "stage": "threads",
                        "message": (
                            f"Found {len(contacts)} contacts. Identifying active conversations..."
                        ),
                    }
                )
            logger.info(
                "EMAIL_BOOTSTRAP: Identifying active threads for user %s",
                user_id,
            )
            threads = await self._identify_active_threads(emails)
            result.active_threads = len(threads)
            logger.info(
                "EMAIL_BOOTSTRAP: Detected %d active deal threads for user %s",
                len([t for t in threads if t.thread_type == "deal"]),
                user_id,
            )

            # 6. Detect commitments
            logger.info("EMAIL_BOOTSTRAP: Detecting commitments for user %s", user_id)
            commitments = await self._detect_commitments(emails)
            result.commitments_detected = len(commitments)
            logger.info(
                "EMAIL_BOOTSTRAP: Detected %d commitments for user %s",
                len(commitments),
                user_id,
            )

            # 7. Extract writing samples for style refinement
            writing_samples = self._extract_writing_samples(emails)
            result.writing_samples_extracted = len(writing_samples)
            logger.info(
                "EMAIL_BOOTSTRAP: Writing style refined from %d email samples for user %s",
                len(writing_samples),
                user_id,
            )

            # 8. Analyze communication patterns
            result.communication_patterns = self._analyze_patterns(emails)
            logger.info(
                "EMAIL_BOOTSTRAP: Analyzed communication patterns for user %s",
                user_id,
            )

            # 9. Store results
            logger.info("EMAIL_BOOTSTRAP: Storing results for user %s", user_id)
            await self._store_contacts(user_id, contacts)
            await self._store_threads(user_id, threads)
            await self._store_commitments(user_id, commitments)
            await self._refine_writing_style(user_id, writing_samples)
            await self._store_patterns(user_id, result.communication_patterns)
            await self._build_recipient_profiles(user_id, emails)
            logger.info("EMAIL_BOOTSTRAP: All results stored for user %s", user_id)

            # 10. Update readiness
            await self._update_readiness(user_id, result)

            # 11. Record episodic
            await self._record_episodic(user_id, result)

            # 12. Trigger retroactive enrichment (US-923)
            await self._trigger_retroactive_enrichment(user_id, contacts)

            # Record activity for feed
            try:
                from src.services.activity_service import ActivityService

                await ActivityService().record(
                    user_id=user_id,
                    agent="analyst",
                    activity_type="email_bootstrap_complete",
                    title="Analyzed email history",
                    description=(
                        "ARIA analyzed email history — identified key contacts and active deals"
                    ),
                    confidence=0.8,
                )
            except Exception as e:
                logger.warning("Failed to record email bootstrap activity: %s", e)

            # 13. Activate learning mode (restricts drafting to top contacts initially)
            try:
                from src.services.learning_mode_service import get_learning_mode_service

                learning_mode = get_learning_mode_service()
                activation_result = await learning_mode.activate_learning_mode(user_id)
                if activation_result.get("success"):
                    logger.info(
                        "EMAIL_BOOTSTRAP: Learning mode activated for user %s with %d top contacts",
                        user_id,
                        activation_result.get("top_contacts_count", 0),
                    )
                else:
                    logger.warning(
                        "EMAIL_BOOTSTRAP: Failed to activate learning mode for user %s: %s",
                        user_id,
                        activation_result.get("error"),
                    )
            except Exception as e:
                logger.warning("EMAIL_BOOTSTRAP: Learning mode activation failed: %s", e)

            # Final summary log
            logger.info(
                "EMAIL_BOOTSTRAP: Complete for user %s. "
                "%d contacts, %d deals, %d patterns stored",
                user_id,
                result.contacts_discovered,
                result.active_threads,
                1 if result.communication_patterns else 0,
            )

            if progress_callback:
                await progress_callback(
                    {
                        "stage": "complete",
                        "message": (
                            f"Processed {result.emails_processed} emails. "
                            f"Found {result.contacts_discovered} contacts, "
                            f"{result.active_threads} active conversations."
                        ),
                    }
                )

            # Store final complete status
            await self._store_bootstrap_status(user_id, "complete", result)

            return result

        except Exception as e:
            logger.error("Email bootstrap failed: %s", e, exc_info=True)
            # Store error status
            await self._store_bootstrap_status(
                user_id, "error", error_message=str(e)
            )
            return result

    # ------------------------------------------------------------------
    # Privacy exclusions
    # ------------------------------------------------------------------

    async def _load_exclusions(self, user_id: str) -> list[dict[str, Any]]:
        """Load privacy exclusions from user settings.

        Args:
            user_id: The user whose exclusions to load.

        Returns:
            List of exclusion dicts with 'type' and 'value' keys.
        """
        result = (
            self._db.table("user_settings")
            .select("integrations")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if result and result.data:
            data: dict[str, Any] = result.data  # type: ignore[assignment]
            email_config = data.get("integrations", {}).get("email", {})
            return email_config.get("privacy_exclusions", [])
        return []

    # ------------------------------------------------------------------
    # Email fetching
    # ------------------------------------------------------------------

    async def _fetch_sent_emails(self, user_id: str, days: int = 60) -> list[dict[str, Any]]:
        """Fetch sent emails via Composio.

        Detects the user's email provider (Gmail or Outlook) from user_integrations
        and uses the appropriate Composio action.

        Args:
            user_id: The user whose emails to fetch.
            days: How many days of history to fetch.

        Returns:
            List of email dicts with: to, cc, subject, body, date, thread_id.
        """
        try:
            # Detect provider from user_integrations
            result = (
                self._db.table("user_integrations")
                .select("integration_type")
                .eq("user_id", user_id)
                .in_("integration_type", ["gmail", "outlook"])
                .maybe_single()
                .execute()
            )

            if not result or not result.data:
                logger.warning(
                    "EMAIL_BOOTSTRAP: No email integration found for user %s",
                    user_id,
                )
                return []

            provider = result.data.get("integration_type", "").lower()
            logger.info(
                "EMAIL_BOOTSTRAP: Detected email provider '%s' for user %s",
                provider,
                user_id,
            )

            from composio import ComposioToolSet

            toolset = ComposioToolSet()
            entity = toolset.get_entity(id=user_id)

            since_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()

            # Use appropriate Composio action based on provider
            if provider == "outlook":
                logger.info(
                    "EMAIL_BOOTSTRAP: Using OUTLOOK365_FETCH_EMAILS for user %s",
                    user_id,
                )
                response = entity.execute(
                    action="OUTLOOK365_FETCH_EMAILS",
                    params={
                        "folder": "sentitems",
                        "start_date": since_date,
                        "max_results": 500,
                    },
                )
            else:
                # Default to Gmail
                logger.info(
                    "EMAIL_BOOTSTRAP: Using GMAIL_FETCH_EMAILS for user %s",
                    user_id,
                )
                response = entity.execute(
                    action="GMAIL_FETCH_EMAILS",
                    params={
                        "label": "SENT",
                        "after": since_date,
                        "max_results": 500,
                    },
                )

            emails = response.get("emails", []) if isinstance(response, dict) else []
            logger.info(
                "EMAIL_BOOTSTRAP: Composio returned %d emails for user %s",
                len(emails),
                user_id,
            )
            return emails

        except Exception as e:
            logger.error(
                "EMAIL_BOOTSTRAP: Email fetch failed for user %s: %s",
                user_id,
                e,
                exc_info=True,
            )
            return []

    # ------------------------------------------------------------------
    # Exclusion filtering
    # ------------------------------------------------------------------

    def _apply_exclusions(
        self,
        emails: list[dict[str, Any]],
        exclusions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Filter emails based on privacy exclusions.

        Checks both 'to' and 'cc' recipients against sender and domain
        exclusion rules.

        Args:
            emails: Raw email dicts.
            exclusions: Exclusion rules from user settings.

        Returns:
            Filtered email list.
        """
        excluded_senders = {e["value"].lower() for e in exclusions if e.get("type") == "sender"}
        excluded_domains = {e["value"].lower() for e in exclusions if e.get("type") == "domain"}

        filtered: list[dict[str, Any]] = []
        for email in emails:
            recipients = list(email.get("to", [])) + list(email.get("cc", []))
            excluded = False
            for r in recipients:
                addr = r.lower() if isinstance(r, str) else r.get("email", "").lower()
                if addr in excluded_senders:
                    excluded = True
                    break
                domain = addr.split("@")[-1] if "@" in addr else ""
                if domain in excluded_domains:
                    excluded = True
                    break
            if not excluded:
                filtered.append(email)

        return filtered

    # ------------------------------------------------------------------
    # Contact extraction
    # ------------------------------------------------------------------

    async def _extract_contacts(self, emails: list[dict[str, Any]]) -> list[EmailContact]:
        """Extract and deduplicate contacts from email recipients.

        Args:
            emails: Email dicts to scan.

        Returns:
            Up to 50 contacts sorted by interaction count (descending).
        """
        contact_map: dict[str, EmailContact] = {}

        for email in emails:
            recipients = list(email.get("to", [])) + list(email.get("cc", []))
            for r in recipients:
                addr = r.lower() if isinstance(r, str) else r.get("email", "").lower()
                name = r.get("name", "") if isinstance(r, dict) else ""

                if addr not in contact_map:
                    contact_map[addr] = EmailContact(
                        email=addr,
                        name=name or None,
                        interaction_count=0,
                        last_interaction=email.get("date"),
                    )

                contact_map[addr].interaction_count += 1
                if email.get("date"):
                    contact_map[addr].last_interaction = email["date"]

        contacts = sorted(
            contact_map.values(),
            key=lambda c: c.interaction_count,
            reverse=True,
        )

        # Classify top 20 contacts via LLM
        top_contacts = contacts[:20]
        if top_contacts:
            await self._classify_contacts(top_contacts, emails)

        return contacts[:50]

    async def _classify_contacts(
        self,
        contacts: list[EmailContact],
        emails: list[dict[str, Any]],  # noqa: ARG002
    ) -> None:
        """Use LLM to classify contact relationships.

        Args:
            contacts: Contacts to classify (mutated in place).
            emails: Email corpus for context (currently unused in prompt).
        """
        contact_summaries = [
            f"- {c.email} (name: {c.name or 'unknown'}, interactions: {c.interaction_count})"
            for c in contacts
        ]

        prompt = (
            "Classify these email contacts by relationship type.\n\n"
            "Contacts:\n" + "\n".join(contact_summaries) + "\n\n"
            "For each contact, determine the likely relationship type "
            "based on the email address and name.\n"
            "Return JSON array:\n"
            '[{"email": "addr", "relationship_type": '
            '"colleague|client|prospect|vendor|personal|recruiter", '
            '"company": "inferred company name or null", '
            '"title": "inferred title or null"}]\n\n'
            "Use email domain to infer company. Be conservative with title inference."
        )

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.3,
        )

        try:
            classifications: list[dict[str, Any]] = json.loads(response)
            class_map = {c["email"].lower(): c for c in classifications}
            for contact in contacts:
                if contact.email.lower() in class_map:
                    c = class_map[contact.email.lower()]
                    contact.relationship_type = c.get("relationship_type", "unknown")
                    contact.company = c.get("company")
                    contact.title = c.get("title")
        except Exception as e:
            logger.warning("Contact classification failed: %s", e)

    # ------------------------------------------------------------------
    # Thread identification
    # ------------------------------------------------------------------

    async def _identify_active_threads(self, emails: list[dict[str, Any]]) -> list[ActiveThread]:
        """Identify email threads that appear to be active conversations.

        Threads with 3+ messages are considered active.

        Args:
            emails: Email dicts to scan.

        Returns:
            List of ActiveThread objects for threads with >= 3 messages.
        """
        threads: dict[str, list[dict[str, Any]]] = {}
        for email in emails:
            thread_key = email.get("thread_id") or email.get("subject", "")
            if not thread_key:
                thread_key = email.get("subject", "")
            if thread_key not in threads:
                threads[thread_key] = []
            threads[thread_key].append(email)

        active: list[ActiveThread] = []
        for _key, msgs in threads.items():
            if len(msgs) >= 3:
                participants: set[str] = set()
                for m in msgs:
                    for r in list(m.get("to", [])) + list(m.get("cc", [])):
                        addr = r if isinstance(r, str) else r.get("email", "")
                        if addr:
                            participants.add(addr)

                active.append(
                    ActiveThread(
                        subject=msgs[0].get("subject", ""),
                        participants=list(participants),
                        message_count=len(msgs),
                        last_activity=msgs[-1].get("date", ""),
                    )
                )

        # Classify top threads via LLM
        if active[:10]:
            await self._classify_threads(active[:10])

        return active

    async def _classify_threads(self, threads: list[ActiveThread]) -> None:
        """Use LLM to classify thread types.

        Args:
            threads: Threads to classify (mutated in place).
        """
        thread_summaries = [
            f'- Subject: "{t.subject}", Messages: {t.message_count}, '
            f"Participants: {len(t.participants)}"
            for t in threads
        ]

        prompt = (
            "Classify these email threads by type.\n\n"
            "Threads:\n" + "\n".join(thread_summaries) + "\n\n"
            "Return JSON array:\n"
            '[{"subject": "...", "thread_type": '
            '"deal|project|routine|personal", '
            '"is_active_deal": true/false}]\n\n'
            '"deal" = active sales negotiation or business discussion\n'
            '"project" = ongoing project coordination\n'
            '"routine" = regular updates, newsletters, recurring meetings\n'
            '"personal" = non-business'
        )

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
        )

        try:
            classifications: list[dict[str, Any]] = json.loads(response)
            class_map = {c["subject"]: c for c in classifications}
            for thread in threads:
                if thread.subject in class_map:
                    thread.thread_type = class_map[thread.subject].get("thread_type", "unknown")
        except Exception as e:
            logger.warning("Thread classification failed: %s", e)

    # ------------------------------------------------------------------
    # Commitment detection
    # ------------------------------------------------------------------

    async def _detect_commitments(self, emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Detect commitments and follow-ups in sent emails.

        Args:
            emails: Email dicts to scan (most recent sampled).

        Returns:
            List of commitment dicts with keys:
            commitment, to, deadline, subject.
        """
        recent = sorted(emails, key=lambda e: e.get("date", ""), reverse=True)[:20]

        bodies: list[str] = []
        for e in recent:
            body = e.get("body", "")[:500]
            if body:
                bodies.append(f"Subject: {e.get('subject', '')}\nTo: {e.get('to', [])}\n{body}")

        if not bodies:
            return []

        prompt = (
            "Detect any commitments or follow-up promises in these sent emails.\n\n"
            + "\n---\n".join(bodies[:10])
            + "\n\n"
            "Return JSON array of detected commitments:\n"
            '[{"commitment": "what was promised", "to": "recipient", '
            '"deadline": "mentioned deadline or null", '
            '"subject": "email subject"}]\n\n'
            'Look for phrases like "I\'ll send", "Let me get back to you", '
            '"I\'ll follow up", "by Friday", etc.\n'
            "Only include clear, actionable commitments."
        )

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
        )

        try:
            result: list[dict[str, Any]] = json.loads(response)
            return result
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Writing sample extraction
    # ------------------------------------------------------------------

    def _extract_writing_samples(self, emails: list[dict[str, Any]]) -> list[str]:
        """Extract clean writing samples from sent emails for style refinement.

        Only emails between 100 and 3000 characters are suitable.

        Args:
            emails: Email dicts to extract from.

        Returns:
            Up to 20 writing samples.
        """
        samples: list[str] = []
        for email in emails:
            body = email.get("body", "")
            if 100 < len(body) < 3000:
                samples.append(body)
        return samples[:20]

    # ------------------------------------------------------------------
    # Pattern analysis
    # ------------------------------------------------------------------

    def _analyze_patterns(self, emails: list[dict[str, Any]]) -> CommunicationPatterns:
        """Analyze communication timing patterns.

        Args:
            emails: Email dicts with date fields.

        Returns:
            CommunicationPatterns with peak hours, days, and volume.
        """
        hours: list[int] = []
        days: list[str] = []
        unique_dates: set[str] = set()

        for email in emails:
            date_str = email.get("date", "")
            if not date_str:
                continue
            try:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                hours.append(dt.hour)
                days.append(dt.strftime("%A"))
                unique_dates.add(date_str[:10])
            except (ValueError, TypeError):
                pass

        hour_counts = Counter(hours)
        day_counts = Counter(days)

        peak_hours = [h for h, _ in hour_counts.most_common(3)]
        peak_days = [d for d, _ in day_counts.most_common(3)]

        total_days = max(1, len(unique_dates))

        return CommunicationPatterns(
            peak_send_hours=peak_hours,
            peak_send_days=peak_days,
            emails_per_day_avg=round(len(emails) / total_days, 1),
        )

    # ------------------------------------------------------------------
    # Storage helpers
    # ------------------------------------------------------------------

    async def _store_contacts(self, user_id: str, contacts: list[EmailContact]) -> None:
        """Store discovered contacts in Corporate Memory / relationship graph.

        Args:
            user_id: Owner of the contacts.
            contacts: Up to 50 contacts to store.
        """
        for contact in contacts[:50]:
            try:
                self._db.table("memory_semantic").insert(
                    {
                        "user_id": user_id,
                        "fact": (
                            f"Contact: {contact.name or contact.email} "
                            f"({contact.relationship_type}) - "
                            f"{contact.interaction_count} interactions"
                        ),
                        "confidence": 0.85,
                        "source": "email_bootstrap",
                        "metadata": {
                            "type": "contact",
                            "email": contact.email,
                            "name": contact.name,
                            "company": contact.company,
                            "title": contact.title,
                            "relationship_type": contact.relationship_type,
                            "interaction_count": contact.interaction_count,
                        },
                    }
                ).execute()
            except Exception as e:
                logger.warning("Failed to store contact: %s", e)

    async def _store_threads(self, user_id: str, threads: list[ActiveThread]) -> None:
        """Store active threads — deal threads become Lead Memory entries.

        Only threads classified as 'deal' are persisted, with a
        ``needs_user_confirmation`` flag so users can verify.

        Args:
            user_id: Owner of the threads.
            threads: Active threads to filter and store.
        """
        deal_threads = [t for t in threads if t.thread_type == "deal"]
        for thread in deal_threads:
            try:
                self._db.table("memory_semantic").insert(
                    {
                        "user_id": user_id,
                        "fact": (
                            f"Active deal thread: {thread.subject} "
                            f"({thread.message_count} messages, "
                            f"{len(thread.participants)} participants)"
                        ),
                        "confidence": 0.7,
                        "source": "email_bootstrap",
                        "metadata": {
                            "type": "active_deal",
                            "subject": thread.subject,
                            "participants": thread.participants,
                            "needs_user_confirmation": True,
                        },
                    }
                ).execute()
            except Exception as e:
                logger.warning("Failed to store thread: %s", e)

    async def _store_commitments(self, user_id: str, commitments: list[dict[str, Any]]) -> None:
        """Store detected commitments in Prospective Memory.

        Args:
            user_id: Owner of the commitments.
            commitments: Commitment dicts from LLM detection.
        """
        for c in commitments:
            try:
                self._db.table("prospective_memories").insert(
                    {
                        "user_id": user_id,
                        "task": f"Follow up: {c.get('commitment', '')}",
                        "due_date": c.get("deadline"),
                        "status": "pending",
                        "metadata": {
                            "type": "email_commitment",
                            "to": c.get("to"),
                            "source": "email_bootstrap",
                        },
                    }
                ).execute()
            except Exception as e:
                logger.warning("Failed to store commitment: %s", e)

    async def _refine_writing_style(self, user_id: str, samples: list[str]) -> None:
        """Refine Digital Twin writing style with email data.

        Args:
            user_id: User whose style to refine.
            samples: Raw email body text samples.
        """
        if not samples:
            return
        try:
            from src.onboarding.writing_analysis import WritingAnalysisService

            service = WritingAnalysisService()
            await service.analyze_samples(user_id, samples)
        except Exception as e:
            logger.warning("Writing style refinement failed: %s", e)

    async def _build_recipient_profiles(self, user_id: str, emails: list[dict[str, Any]]) -> None:
        """Build per-recipient writing style profiles from sent emails.

        Args:
            user_id: User whose profiles to build.
            emails: Sent email dicts with 'to', 'body', 'date', 'subject'.
        """
        if not emails:
            return
        try:
            from src.onboarding.writing_analysis import WritingAnalysisService

            service = WritingAnalysisService()
            profiles = await service.analyze_recipient_samples(user_id, emails)
            logger.info(
                "EMAIL_BOOTSTRAP: Built %d recipient writing profiles for user %s",
                len(profiles),
                user_id,
            )
        except Exception as e:
            logger.warning("Recipient profile building failed: %s", e)

    async def _store_patterns(self, user_id: str, patterns: CommunicationPatterns) -> None:
        """Store communication patterns in Digital Twin.

        Args:
            user_id: User whose patterns to store.
            patterns: Analyzed communication patterns.
        """
        try:
            self._db.table("user_settings").update(
                {"preferences": {"digital_twin": {"communication_patterns": patterns.model_dump()}}}
            ).eq("user_id", user_id).execute()
        except Exception as e:
            logger.warning("Failed to store patterns: %s", e)

    async def _store_bootstrap_status(
        self,
        user_id: str,
        status: str,
        result: EmailBootstrapResult | None = None,
        error_message: str | None = None,
    ) -> None:
        """Store bootstrap status in onboarding_state metadata.

        This allows the frontend to poll for progress.

        Args:
            user_id: User whose bootstrap status to update.
            status: Current status ("processing", "complete", "error").
            result: Bootstrap result (required when status is "complete").
            error_message: Error message (required when status is "error").
        """
        try:
            # Build the status object
            status_data: dict[str, Any] = {"status": status}

            if status == "complete" and result:
                status_data.update(
                    {
                        "emails_processed": result.emails_processed,
                        "contacts_discovered": result.contacts_discovered,
                        "active_threads": result.active_threads,
                        "commitments_detected": result.commitments_detected,
                        "writing_samples_extracted": result.writing_samples_extracted,
                        "communication_patterns": (
                            result.communication_patterns.model_dump()
                            if result.communication_patterns
                            else None
                        ),
                    }
                )
            elif status == "error" and error_message:
                status_data["error_message"] = error_message

            # Fetch current metadata
            current = (
                self._db.table("onboarding_state")
                .select("metadata")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            # Merge with existing metadata
            existing_metadata: dict[str, Any] = {}
            if current and current.data:
                existing_metadata = current.data.get("metadata", {})  # type: ignore[union-attr]

            existing_metadata["email_bootstrap"] = status_data

            # Update the metadata
            self._db.table("onboarding_state").update(
                {"metadata": existing_metadata}
            ).eq("user_id", user_id).execute()

            logger.info(
                "EMAIL_BOOTSTRAP: Stored status '%s' for user %s", status, user_id
            )
        except Exception as e:
            logger.warning("Failed to store bootstrap status: %s", e)

    # ------------------------------------------------------------------
    # Readiness & episodic
    # ------------------------------------------------------------------

    async def _update_readiness(self, user_id: str, result: EmailBootstrapResult) -> None:
        """Update readiness scores based on bootstrap results.

        Args:
            user_id: User whose readiness to update.
            result: Bootstrap result with counts.
        """
        try:
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()

            updates: dict[str, float] = {}
            if result.contacts_discovered > 0:
                updates["relationship_graph"] = min(60.0, result.contacts_discovered * 3.0)
            if result.writing_samples_extracted > 0:
                updates["digital_twin"] = min(70.0, 40.0 + result.writing_samples_extracted * 1.5)

            if updates:
                await orch.update_readiness_scores(user_id, updates)
        except Exception as e:
            logger.warning("Readiness update failed: %s", e)

    async def _record_episodic(self, user_id: str, result: EmailBootstrapResult) -> None:
        """Record bootstrap completion in episodic memory.

        Args:
            user_id: User who completed bootstrap.
            result: Bootstrap result summary.
        """
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="onboarding_email_bootstrap_complete",
                content=(
                    f"Email bootstrap processed {result.emails_processed} emails. "
                    f"Discovered {result.contacts_discovered} contacts, "
                    f"{result.active_threads} active threads, "
                    f"{result.commitments_detected} commitments."
                ),
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "emails_processed": result.emails_processed,
                    "contacts_discovered": result.contacts_discovered,
                    "active_threads": result.active_threads,
                    "commitments_detected": result.commitments_detected,
                },
            )
            memory = EpisodicMemory()
            await memory.store_episode(episode)
        except Exception as e:
            logger.warning("Episodic record failed: %s", e)

    async def _trigger_retroactive_enrichment(
        self,
        user_id: str,
        contacts: list[dict[str, Any]],
    ) -> None:
        """Trigger retroactive enrichment after email processing (US-923).

        Converts discovered contacts into entity dicts and calls the
        RetroactiveEnrichmentService to cross-reference against existing
        memory and enrich partially-known entities.

        Args:
            user_id: User whose memory to enrich.
            contacts: Contacts extracted from email processing.
        """
        try:
            from src.memory.retroactive_enrichment import (
                RetroactiveEnrichmentService,
            )

            entities = [
                {
                    "name": c.get("name", c.get("email", "")),
                    "type": c.get("relationship", "contact"),
                    "confidence": 0.75,
                    "source": "email_archive",
                    "facts": [
                        f"{c.get('name', 'Unknown')} contacted via email "
                        f"({c.get('email_count', 0)} messages)"
                    ],
                    "relationships": [],
                }
                for c in contacts
                if c.get("name") or c.get("email")
            ]

            if entities:
                service = RetroactiveEnrichmentService()
                result = await service.enrich_after_email_archive(user_id, entities)
                logger.info(
                    "Retroactive enrichment after email bootstrap: "
                    "%d entities enriched, %d significant",
                    result.get("enriched", 0),
                    result.get("significant", 0),
                    extra={"user_id": user_id},
                )
        except Exception as e:
            logger.warning(
                "Retroactive enrichment failed (non-blocking): %s",
                e,
                extra={"user_id": user_id},
            )
