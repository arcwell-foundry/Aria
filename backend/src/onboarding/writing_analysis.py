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
