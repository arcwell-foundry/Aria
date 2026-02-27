"""Writing sample analysis and Digital Twin style fingerprint generation.

Analyzes user-provided writing samples (emails, documents, reports) to build
a comprehensive WritingStyleFingerprint stored in the Digital Twin. This powers
ARIA's ability to draft communications that sound like the user.

US-906: Writing Sample Analysis & Digital Twin Bootstrap
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import BaseModel

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import SupabaseClient
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation
from src.memory.episodic import Episode, EpisodicMemory

logger = logging.getLogger(__name__)


class WritingStyleFingerprint(BaseModel):
    """Comprehensive writing style analysis stored in Digital Twin.

    Captures structural, vocabulary, punctuation, tone, and communication
    patterns from analyzed writing samples.
    """

    # Structure
    avg_sentence_length: float = 0.0
    sentence_length_variance: float = 0.0
    paragraph_style: str = "medium"  # short_punchy, medium, long_detailed

    # Vocabulary
    lexical_diversity: float = 0.0  # 0-1
    formality_index: float = 0.5  # 0 (casual) to 1 (formal)
    vocabulary_sophistication: str = "moderate"  # simple, moderate, advanced

    # Punctuation patterns
    uses_em_dashes: bool = False
    uses_semicolons: bool = False
    exclamation_frequency: str = "rare"  # never, rare, occasional, frequent
    ellipsis_usage: bool = False

    # Communication patterns
    opening_style: str = ""  # "Hi [Name]", "Dear", direct without greeting, etc.
    closing_style: str = ""  # "Best", "Thanks", "Cheers", etc.

    # Tone
    directness: float = 0.5  # 0 (indirect) to 1 (very direct)
    warmth: float = 0.5  # 0 (cold/clinical) to 1 (warm/personal)
    assertiveness: float = 0.5  # 0 (hedging) to 1 (assertive)
    data_driven: bool = False  # references numbers/data frequently

    # Habits
    hedging_frequency: str = "moderate"  # low, moderate, high
    emoji_usage: str = "never"  # never, rare, occasional, frequent
    rhetorical_style: str = "balanced"  # analytical, narrative, persuasive, balanced

    # Summary
    style_summary: str = ""  # Human-readable description
    confidence: float = 0.0  # How confident in the fingerprint (based on sample quality)


class RecipientWritingProfile(BaseModel):
    """Per-recipient writing style profile.

    Captures how the user adapts their writing style for a specific
    recipient, enabling ARIA to match tone per-contact.
    """

    recipient_email: str
    recipient_name: str | None = None
    relationship_type: str = "unknown"  # internal_team, external_executive, external_peer, vendor, new_contact
    formality_level: float = 0.5  # 0=very casual, 1=very formal
    average_message_length: int = 0  # words
    greeting_style: str = ""  # e.g., "Hi Sarah,", "Dear Dr. Fischer,"
    signoff_style: str = ""  # e.g., "Best,", "Thanks,", "Regards,"
    tone: str = "balanced"  # warm, direct, formal, casual, balanced
    uses_emoji: bool = False
    email_count: int = 0
    last_email_date: str | None = None  # ISO datetime string


_ANALYSIS_PROMPT = """Analyze these writing samples from a life sciences professional \
and extract their writing style fingerprint.

WRITING SAMPLES:
{samples}

Analyze and return a JSON object with these fields:
{{
    "avg_sentence_length": <float: average words per sentence>,
    "sentence_length_variance": <float: how much sentence length varies>,
    "paragraph_style": "<short_punchy|medium|long_detailed>",
    "lexical_diversity": <float 0-1: vocabulary variety>,
    "formality_index": <float 0-1: 0=casual, 1=formal>,
    "vocabulary_sophistication": "<simple|moderate|advanced>",
    "uses_em_dashes": <bool>,
    "uses_semicolons": <bool>,
    "exclamation_frequency": "<never|rare|occasional|frequent>",
    "ellipsis_usage": <bool>,
    "opening_style": "<how they typically start emails/messages>",
    "closing_style": "<how they typically end>",
    "directness": <float 0-1>,
    "warmth": <float 0-1>,
    "assertiveness": <float 0-1>,
    "data_driven": <bool>,
    "hedging_frequency": "<low|moderate|high>",
    "emoji_usage": "<never|rare|occasional|frequent>",
    "rhetorical_style": "<analytical|narrative|persuasive|balanced>",
    "style_summary": "<2-3 sentence human-readable summary of their writing style>",
    "confidence": <float 0-1: how confident you are based on sample quality/quantity>
}}

Return ONLY the JSON object, no other text. Be precise. \
Base your analysis on actual patterns in the text, not assumptions."""

_RECIPIENT_ANALYSIS_PROMPT = """Analyze how this person writes to different recipients.
Below are groups of sent emails, organized by recipient. For each recipient, analyze the
writing style the sender uses SPECIFICALLY with that person.

{recipient_groups}

For each recipient, return a JSON array with objects containing:
[
  {{
    "recipient_email": "<email address>",
    "recipient_name": "<inferred name or null>",
    "relationship_type": "<internal_team|external_executive|external_peer|vendor|new_contact>",
    "formality_level": <float 0-1: 0=very casual, 1=very formal>,
    "average_message_length": <int: average words per email to this person>,
    "greeting_style": "<exact greeting pattern used, e.g. 'Hi Sarah,' or 'Dear Dr. Fischer,'>",
    "signoff_style": "<exact sign-off pattern used, e.g. 'Best,' or 'Thanks,'>",
    "tone": "<warm|direct|formal|casual|balanced>",
    "uses_emoji": <bool: whether emojis appear in messages to this person>
  }}
]

IMPORTANT:
- Base analysis on ACTUAL patterns in the emails, not assumptions
- relationship_type should be inferred from email domain, greeting formality, and content
- greeting_style and signoff_style should reflect what the sender ACTUALLY writes
- Return ONLY the JSON array, no other text"""


class WritingAnalysisService:
    """Analyzes writing samples to build Digital Twin style fingerprint.

    Coordinates LLM-based analysis, storage in user_settings (Digital Twin),
    readiness score updates, and episodic memory recording.
    """

    def __init__(self) -> None:
        """Initialize with LLM client and episodic memory."""
        self.llm = LLMClient()
        self.episodic = EpisodicMemory()

    async def analyze_samples(
        self,
        user_id: str,
        samples: list[str],
    ) -> WritingStyleFingerprint:
        """Analyze writing samples and generate style fingerprint.

        Args:
            user_id: The user whose style to analyze.
            samples: List of text samples (emails, docs, posts).

        Returns:
            WritingStyleFingerprint with comprehensive style analysis.
        """
        if not samples:
            return WritingStyleFingerprint(
                style_summary="No samples provided yet.",
                confidence=0.0,
            )

        # Combine samples for analysis (cap at 10 samples, 6000 chars)
        combined = "\n\n---SAMPLE BREAK---\n\n".join(samples[:10])
        prompt = _ANALYSIS_PROMPT.format(samples=combined[:6000])

        fingerprint = await self._run_analysis(prompt)

        # Store in Digital Twin
        await self._store_fingerprint(user_id, fingerprint)

        # Update readiness
        await self._update_readiness(user_id, fingerprint.confidence)

        # Record episodic memory
        await self._record_episodic_event(user_id, len(samples), fingerprint)

        # Audit log
        await log_memory_operation(
            user_id=user_id,
            operation=MemoryOperation.CREATE,
            memory_type=MemoryType.SEMANTIC,
            memory_id=f"writing_fingerprint_{user_id}",
            metadata={
                "sample_count": len(samples),
                "confidence": fingerprint.confidence,
            },
            suppress_errors=True,
        )

        return fingerprint

    async def _run_analysis(self, prompt: str) -> WritingStyleFingerprint:
        """Run LLM analysis and parse the response into a fingerprint.

        Args:
            prompt: The formatted analysis prompt.

        Returns:
            Parsed WritingStyleFingerprint, or a low-confidence fallback on error.
        """
        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.3,
                task=TaskType.ONBOARD_PERSONALITY,
            )

            # Strip markdown code fences if present
            text = response.strip()
            if text.startswith("```"):
                # Remove opening fence (possibly with language tag)
                first_newline = text.index("\n")
                text = text[first_newline + 1 :]
            if text.endswith("```"):
                text = text[:-3].rstrip()

            data: dict[str, Any] = json.loads(text)
            return WritingStyleFingerprint(**data)
        except Exception as e:
            logger.warning("Fingerprint parse failed: %s", e)
            return WritingStyleFingerprint(
                style_summary="Analysis in progress — more samples will improve accuracy.",
                confidence=0.3,
            )

    async def _store_fingerprint(
        self,
        user_id: str,
        fingerprint: WritingStyleFingerprint,
    ) -> None:
        """Store fingerprint in user_settings preferences (Digital Twin data).

        Uses upsert to handle both first-time and subsequent analyses.

        Args:
            user_id: The user whose fingerprint to store.
            fingerprint: The analyzed fingerprint.
        """
        try:
            db = SupabaseClient.get_client()

            # Get current preferences to merge
            result = (
                db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            current_prefs: dict[str, Any] = {}
            if result and result.data:
                row = cast(dict[str, Any], result.data)
                current_prefs = row.get("preferences", {}) or {}

            # Merge digital_twin data
            digital_twin = current_prefs.get("digital_twin", {})
            digital_twin["writing_style"] = fingerprint.model_dump()
            digital_twin["writing_style_updated_at"] = datetime.now(UTC).isoformat()
            current_prefs["digital_twin"] = digital_twin

            # Update
            (
                db.table("user_settings")
                .update({"preferences": current_prefs})
                .eq("user_id", user_id)
                .execute()
            )
        except Exception as e:
            logger.warning("Failed to store fingerprint: %s", e)

    async def _update_readiness(
        self,
        user_id: str,
        confidence: float,
    ) -> None:
        """Update digital_twin readiness based on fingerprint confidence.

        Writing analysis can bring digital_twin readiness to max 40
        (other signals like email patterns bring it higher).

        Args:
            user_id: The user whose readiness to update.
            confidence: The fingerprint confidence (0-1).
        """
        try:
            from src.onboarding.orchestrator import OnboardingOrchestrator

            orch = OnboardingOrchestrator()
            readiness = min(40.0, confidence * 40)
            await orch.update_readiness_scores(user_id, {"digital_twin": readiness})
        except Exception as e:
            logger.warning("Readiness update failed: %s", e)

    async def _record_episodic_event(
        self,
        user_id: str,
        sample_count: int,
        fingerprint: WritingStyleFingerprint,
    ) -> None:
        """Record writing analysis event to episodic memory.

        Args:
            user_id: The user who submitted samples.
            sample_count: Number of samples analyzed.
            fingerprint: The generated fingerprint.
        """
        try:
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="onboarding_writing_analyzed",
                content=(
                    f"Analyzed {sample_count} writing samples, generated style fingerprint. "
                    f"{fingerprint.style_summary}"
                ),
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "onboarding_step": "writing_samples",
                    "sample_count": sample_count,
                    "confidence": fingerprint.confidence,
                    "style_summary": fingerprint.style_summary,
                },
            )
            await self.episodic.store_episode(episode)
        except Exception as e:
            logger.warning("Episodic record failed: %s", e)

    async def get_fingerprint(self, user_id: str) -> WritingStyleFingerprint | None:
        """Retrieve stored fingerprint from Digital Twin.

        Args:
            user_id: The user whose fingerprint to retrieve.

        Returns:
            WritingStyleFingerprint if stored, None otherwise.
        """
        try:
            db = SupabaseClient.get_client()
            result = (
                db.table("user_settings")
                .select("preferences")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if result and result.data:
                row = cast(dict[str, Any], result.data)
                prefs: dict[str, Any] = row.get("preferences", {}) or {}
                dt = prefs.get("digital_twin", {})
                ws = dt.get("writing_style")
                if ws:
                    return WritingStyleFingerprint(**ws)
        except Exception as e:
            logger.warning("Failed to get fingerprint: %s", e)
        return None

    async def analyze_recipient_samples(
        self,
        user_id: str,
        sent_emails: list[dict[str, Any]],
    ) -> list[RecipientWritingProfile]:
        """Analyze sent emails grouped by recipient to build per-contact profiles.

        Groups emails by primary recipient, takes the top 20 by frequency,
        and uses LLM to analyze writing style differences per recipient.

        Args:
            user_id: The user whose emails to analyze.
            sent_emails: List of email dicts with 'to', 'body', 'date', 'subject'.

        Returns:
            List of RecipientWritingProfile for analyzed recipients.
        """
        if not sent_emails:
            return []

        # Group emails by primary recipient
        recipient_emails: dict[str, list[dict[str, Any]]] = {}
        for email in sent_emails:
            recipients = email.get("to", [])
            if not recipients:
                continue
            # Use first recipient as primary
            primary = recipients[0] if isinstance(recipients[0], str) else recipients[0].get("email", "")
            primary = primary.lower().strip()
            if not primary:
                continue
            if primary not in recipient_emails:
                recipient_emails[primary] = []
            recipient_emails[primary].append(email)

        if not recipient_emails:
            return []

        # Sort by email count descending, take top 20
        sorted_recipients = sorted(
            recipient_emails.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:20]

        # Build prompt with grouped samples
        groups: list[str] = []
        recipient_counts: dict[str, int] = {}
        recipient_last_dates: dict[str, str] = {}

        for recipient, emails in sorted_recipients:
            recipient_counts[recipient] = len(emails)
            # Track last email date
            dates = [e.get("date", "") for e in emails if e.get("date")]
            if dates:
                recipient_last_dates[recipient] = max(dates)

            # Include up to 5 sample bodies per recipient (cap at 500 chars each)
            sample_bodies = []
            for e in emails[:5]:
                body = e.get("body", "")[:500]
                if body:
                    sample_bodies.append(body)

            if sample_bodies:
                group_text = (
                    f"--- RECIPIENT: {recipient} ({len(emails)} emails) ---\n"
                    + "\n\n".join(sample_bodies)
                )
                groups.append(group_text)

        if not groups:
            return []

        prompt = _RECIPIENT_ANALYSIS_PROMPT.format(
            recipient_groups="\n\n".join(groups)
        )

        # Call LLM
        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                temperature=0.3,
                task=TaskType.ONBOARD_PERSONALITY,
            )

            # Strip markdown fences
            text = response.strip()
            if text.startswith("```"):
                first_newline = text.index("\n")
                text = text[first_newline + 1:]
            if text.endswith("```"):
                text = text[:-3].rstrip()

            raw_profiles: list[dict[str, Any]] = json.loads(text)
        except Exception as e:
            logger.warning("Recipient style analysis failed: %s", e)
            return []

        # Build profiles and store
        profiles: list[RecipientWritingProfile] = []
        for raw in raw_profiles:
            email_addr = raw.get("recipient_email", "").lower().strip()
            if not email_addr:
                continue

            profile = RecipientWritingProfile(
                recipient_email=email_addr,
                recipient_name=raw.get("recipient_name"),
                relationship_type=raw.get("relationship_type", "unknown"),
                formality_level=float(raw.get("formality_level", 0.5)),
                average_message_length=int(raw.get("average_message_length", 0)),
                greeting_style=raw.get("greeting_style", ""),
                signoff_style=raw.get("signoff_style", ""),
                tone=raw.get("tone", "balanced"),
                uses_emoji=bool(raw.get("uses_emoji", False)),
                email_count=recipient_counts.get(email_addr, 0),
                last_email_date=recipient_last_dates.get(email_addr),
            )
            profiles.append(profile)

        # Store profiles in database
        await self._store_recipient_profiles(user_id, profiles)

        return profiles

    async def _store_recipient_profiles(
        self,
        user_id: str,
        profiles: list[RecipientWritingProfile],
    ) -> None:
        """Store recipient writing profiles in database.

        Uses upsert with (user_id, recipient_email) as conflict key.

        Args:
            user_id: The user who owns these profiles.
            profiles: List of profiles to store.
        """
        if not profiles:
            return

        try:
            db = SupabaseClient.get_client()

            for profile in profiles:
                row = {
                    "user_id": user_id,
                    "recipient_email": profile.recipient_email,
                    "recipient_name": profile.recipient_name,
                    "relationship_type": profile.relationship_type,
                    "formality_level": profile.formality_level,
                    "average_message_length": profile.average_message_length,
                    "greeting_style": profile.greeting_style,
                    "signoff_style": profile.signoff_style,
                    "tone": profile.tone,
                    "uses_emoji": profile.uses_emoji,
                    "email_count": profile.email_count,
                    "last_email_date": profile.last_email_date,
                }
                db.table("recipient_writing_profiles").upsert(
                    row,
                    on_conflict="user_id,recipient_email",
                ).execute()

        except Exception as e:
            logger.warning("Failed to store recipient profiles: %s", e)

    async def get_recipient_style(
        self,
        user_id: str,
        recipient_email: str,
    ) -> tuple[RecipientWritingProfile, bool] | None:
        """Get writing style adapted for a specific recipient.

        Looks up per-recipient profile first. If not found, falls back
        to global WritingStyleFingerprint converted to a RecipientWritingProfile.

        Args:
            user_id: The user whose style to look up.
            recipient_email: The recipient to get style for.

        Returns:
            Tuple of (RecipientWritingProfile, is_recipient_specific) or None
            if no style data exists at all. is_recipient_specific is True when
            a per-recipient profile was found, False when falling back to global.
        """
        try:
            db = SupabaseClient.get_client()

            # Try recipient-specific profile first
            result = (
                db.table("recipient_writing_profiles")
                .select("*")
                .eq("user_id", user_id)
                .eq("recipient_email", recipient_email.lower().strip())
                .maybe_single()
                .execute()
            )

            if result and result.data:
                data = cast(dict[str, Any], result.data)
                profile = RecipientWritingProfile(
                    recipient_email=data.get("recipient_email", recipient_email),
                    recipient_name=data.get("recipient_name"),
                    relationship_type=data.get("relationship_type", "unknown"),
                    formality_level=float(data.get("formality_level", 0.5)),
                    average_message_length=int(data.get("average_message_length", 0)),
                    greeting_style=data.get("greeting_style", ""),
                    signoff_style=data.get("signoff_style", ""),
                    tone=data.get("tone", "balanced"),
                    uses_emoji=bool(data.get("uses_emoji", False)),
                    email_count=int(data.get("email_count", 0)),
                    last_email_date=data.get("last_email_date"),
                )
                return profile, True

            # Fall back to global fingerprint
            global_fp = await self.get_fingerprint(user_id)
            if global_fp:
                # Convert global fingerprint to a RecipientWritingProfile
                profile = RecipientWritingProfile(
                    recipient_email=recipient_email,
                    relationship_type="new_contact",
                    formality_level=global_fp.formality_index,
                    greeting_style=global_fp.opening_style,
                    signoff_style=global_fp.closing_style,
                    tone=self._map_tone_from_fingerprint(global_fp),
                    uses_emoji=global_fp.emoji_usage != "never",
                )
                return profile, False

        except Exception as e:
            logger.warning("Failed to get recipient style: %s", e)

        return None

    @staticmethod
    def _map_tone_from_fingerprint(fp: WritingStyleFingerprint) -> str:
        """Map global fingerprint tone metrics to a single tone label.

        Args:
            fp: The global writing style fingerprint.

        Returns:
            One of: warm, direct, formal, casual, balanced.
        """
        if fp.formality_index >= 0.7:
            return "formal"
        if fp.warmth >= 0.7:
            return "warm"
        if fp.directness >= 0.7:
            return "direct"
        if fp.formality_index <= 0.3:
            return "casual"
        return "balanced"
