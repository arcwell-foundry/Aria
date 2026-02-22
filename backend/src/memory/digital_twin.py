"""Digital twin module for user writing style analysis.

The Digital Twin captures a user's writing style fingerprint to enable
ARIA to communicate in their voice. This includes:
- Sentence structure and length patterns
- Vocabulary level and formality
- Common phrases and expressions
- Greeting and sign-off styles
- Punctuation and emoji usage patterns

Fingerprints are stored in Graphiti for semantic querying and
temporal tracking of style evolution.
"""

import contextlib
import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from src.core.exceptions import DigitalTwinError

if TYPE_CHECKING:
    from graphiti_core import Graphiti

logger = logging.getLogger(__name__)


@dataclass
class WritingStyleFingerprint:
    """A writing style fingerprint representing a user's communication patterns.

    Captures linguistic features extracted from the user's emails, messages,
    and documents to enable style-matched content generation.
    """

    id: str
    user_id: str
    average_sentence_length: float
    vocabulary_level: str  # simple, moderate, advanced
    formality_score: float  # 0.0 (informal) to 1.0 (formal)
    common_phrases: list[str]
    greeting_style: str  # e.g., "Hi", "Dear", "Hey"
    sign_off_style: str  # e.g., "Best", "Thanks", "Regards"
    emoji_usage: bool
    punctuation_patterns: dict[str, float]  # char -> frequency ratio
    samples_analyzed: int
    confidence: float  # 0.0 to 1.0 based on sample size
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Serialize fingerprint to a dictionary.

        Returns:
            Dictionary representation suitable for JSON serialization.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "average_sentence_length": self.average_sentence_length,
            "vocabulary_level": self.vocabulary_level,
            "formality_score": self.formality_score,
            "common_phrases": self.common_phrases,
            "greeting_style": self.greeting_style,
            "sign_off_style": self.sign_off_style,
            "emoji_usage": self.emoji_usage,
            "punctuation_patterns": self.punctuation_patterns,
            "samples_analyzed": self.samples_analyzed,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WritingStyleFingerprint":
        """Create a WritingStyleFingerprint instance from a dictionary.

        Args:
            data: Dictionary containing fingerprint data.

        Returns:
            WritingStyleFingerprint instance with restored state.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            average_sentence_length=data["average_sentence_length"],
            vocabulary_level=data["vocabulary_level"],
            formality_score=data["formality_score"],
            common_phrases=data["common_phrases"],
            greeting_style=data["greeting_style"],
            sign_off_style=data["sign_off_style"],
            emoji_usage=data["emoji_usage"],
            punctuation_patterns=data["punctuation_patterns"],
            samples_analyzed=data["samples_analyzed"],
            confidence=data["confidence"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


class TextStyleAnalyzer:
    """Analyzes text to extract writing style features.

    Extracts various linguistic features from text samples including
    sentence length, vocabulary level, formality, punctuation patterns,
    emoji usage, common phrases, and greeting/sign-off styles.
    """

    # Common greeting patterns at the start of messages
    GREETING_PATTERNS: list[str] = [
        "Dear",
        "Hi",
        "Hey",
        "Hello",
        "Good morning",
        "Good afternoon",
        "Good evening",
        "Greetings",
    ]

    # Common sign-off patterns at the end of messages
    SIGNOFF_PATTERNS: list[str] = [
        "Best regards",
        "Best",
        "Regards",
        "Sincerely",
        "Thanks",
        "Thank you",
        "Cheers",
        "Warm regards",
        "Kind regards",
        "Take care",
    ]

    # Words that indicate formal writing
    FORMAL_WORDS: set[str] = {
        "pursuant",
        "hereby",
        "regarding",
        "concerning",
        "furthermore",
        "therefore",
        "consequently",
        "accordingly",
        "henceforth",
        "notwithstanding",
        "aforementioned",
        "herein",
        "therein",
        "wherein",
        "whereas",
        "respectfully",
        "sincerely",
        "formally",
        "request",
        "advise",
        "acknowledge",
        "confirm",
    }

    # Patterns that indicate informal writing
    INFORMAL_PATTERNS: list[re.Pattern[str]] = [
        re.compile(r"\bgonna\b", re.IGNORECASE),
        re.compile(r"\bwanna\b", re.IGNORECASE),
        re.compile(r"\bgotta\b", re.IGNORECASE),
        re.compile(r"\blol\b", re.IGNORECASE),
        re.compile(r"\blomao\b", re.IGNORECASE),
        re.compile(r"\bbtw\b", re.IGNORECASE),
        re.compile(r"\bidk\b", re.IGNORECASE),
        re.compile(r"\bomg\b", re.IGNORECASE),
        re.compile(r":\)", re.IGNORECASE),
        re.compile(r":\(", re.IGNORECASE),
        re.compile(r":D", re.IGNORECASE),
        re.compile(r";-?\)", re.IGNORECASE),
        re.compile(r"\bya\b", re.IGNORECASE),
        re.compile(r"\byeah\b", re.IGNORECASE),
        re.compile(r"\bnope\b", re.IGNORECASE),
        re.compile(r"\byep\b", re.IGNORECASE),
        re.compile(r"\bcool\b", re.IGNORECASE),
        re.compile(r"\bawesome\b", re.IGNORECASE),
    ]

    # Regex for detecting Unicode emojis
    EMOJI_PATTERN: re.Pattern[str] = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map symbols
        "\U0001f1e0-\U0001f1ff"  # flags
        "\U00002702-\U000027b0"  # dingbats
        "\U0001f900-\U0001f9ff"  # supplemental symbols and pictographs
        "\U0001fa00-\U0001fa6f"  # chess symbols
        "\U0001fa70-\U0001faff"  # symbols and pictographs extended-A
        "\U00002600-\U000026ff"  # misc symbols
        "]+",
        re.UNICODE,
    )

    # Words considered advanced vocabulary (average word length > 8 chars)
    ADVANCED_WORDS: set[str] = {
        "pharmaceutical",
        "consortium",
        "comprehensive",
        "demonstrates",
        "unprecedented",
        "efficacy",
        "cardiovascular",
        "rehabilitation",
        "protocols",
        "acquisition",
        "implementation",
        "infrastructure",
        "methodology",
        "subsequently",
        "predominantly",
        "substantially",
        "significantly",
        "approximately",
        "consideration",
        "recommendation",
    }

    def extract_sentence_length(self, text: str) -> float:
        """Extract average words per sentence from text.

        Args:
            text: Input text to analyze.

        Returns:
            Average number of words per sentence.
        """
        # Split text into sentences
        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return 0.0

        total_words = 0
        for sentence in sentences:
            words = re.findall(r"\b\w+\b", sentence)
            total_words += len(words)

        return total_words / len(sentences)

    def extract_vocabulary_level(self, text: str) -> str:
        """Determine vocabulary level from text.

        Args:
            text: Input text to analyze.

        Returns:
            Vocabulary level: "simple", "moderate", or "advanced".
        """
        words = re.findall(r"\b\w+\b", text.lower())

        if not words:
            return "simple"

        # Count advanced words
        advanced_count = sum(1 for w in words if w in self.ADVANCED_WORDS)

        # Calculate average word length
        avg_word_length = sum(len(w) for w in words) / len(words)

        # Count long words (8+ chars)
        long_word_count = sum(1 for w in words if len(w) >= 8)
        long_word_ratio = long_word_count / len(words)

        # Determine level based on metrics
        if advanced_count >= 2 or avg_word_length > 6 or long_word_ratio > 0.3:
            return "advanced"
        elif avg_word_length > 4.5 or long_word_ratio > 0.15:
            return "moderate"
        else:
            return "simple"

    def extract_formality_score(self, text: str) -> float:
        """Calculate formality score from text.

        Args:
            text: Input text to analyze.

        Returns:
            Formality score from 0.0 (informal) to 1.0 (formal).
        """
        words = re.findall(r"\b\w+\b", text.lower())
        text_lower = text.lower()

        if not words:
            return 0.5

        # Count formal indicators
        formal_count = sum(1 for w in words if w in self.FORMAL_WORDS)

        # Count informal indicators
        informal_count = 0
        for pattern in self.INFORMAL_PATTERNS:
            informal_count += len(pattern.findall(text_lower))

        # Check for emoji usage
        if self.detect_emoji_usage(text):
            informal_count += 2

        # Check for contractions (informal)
        contractions = re.findall(r"\b\w+'\w+\b", text)
        informal_count += len(contractions)

        # Check for formal salutations
        if re.search(r"\bDear\s+(Mr\.|Mrs\.|Ms\.|Dr\.)", text):
            formal_count += 3

        # Check for "Please" and "Thank you" (formal)
        if re.search(r"\bplease\b", text_lower):
            formal_count += 1
        if re.search(r"\bthank you\b", text_lower):
            formal_count += 1

        # Calculate score
        total_indicators = formal_count + informal_count
        if total_indicators == 0:
            # Neutral text - base on sentence structure
            avg_sentence_length = self.extract_sentence_length(text)
            if avg_sentence_length > 15:
                return 0.6
            return 0.5

        formality_ratio = formal_count / total_indicators
        return min(1.0, max(0.0, formality_ratio))

    def extract_punctuation_patterns(self, text: str) -> dict[str, float]:
        """Extract punctuation frequency ratios from text.

        Args:
            text: Input text to analyze.

        Returns:
            Dictionary mapping punctuation characters to their frequency ratios.
        """
        # Define punctuation to track
        punctuation_marks = ".!?,;:-"

        # Count occurrences
        counts: dict[str, int] = {}
        for char in punctuation_marks:
            count = text.count(char)
            if count > 0:
                counts[char] = count

        # Calculate ratios
        total = sum(counts.values())
        if total == 0:
            return {}

        return {char: count / total for char, count in counts.items()}

    def detect_emoji_usage(self, text: str) -> bool:
        """Detect if text contains emoji characters.

        Args:
            text: Input text to analyze.

        Returns:
            True if emojis are present, False otherwise.
        """
        return bool(self.EMOJI_PATTERN.search(text))

    def extract_common_phrases(self, texts: list[str], min_occurrences: int = 2) -> list[str]:
        """Extract common 2-4 word phrases from texts.

        Args:
            texts: List of text samples to analyze.
            min_occurrences: Minimum times a phrase must appear.

        Returns:
            List of common phrases found across texts.
        """
        phrase_counter: Counter[str] = Counter()

        for text in texts:
            # Extract words
            words = re.findall(r"\b\w+\b", text)

            # Generate 2-4 word phrases
            for n in range(2, 5):
                for i in range(len(words) - n + 1):
                    phrase = " ".join(words[i : i + n])
                    phrase_counter[phrase] += 1

        # Filter by minimum occurrences
        common_phrases = [
            phrase for phrase, count in phrase_counter.items() if count >= min_occurrences
        ]

        return common_phrases

    def extract_greeting_style(self, texts: list[str]) -> str:
        """Extract most common greeting style from texts.

        Args:
            texts: List of text samples to analyze.

        Returns:
            Most common greeting pattern or empty string if none found.
        """
        greeting_counter: Counter[str] = Counter()

        for text in texts:
            # Check for each greeting pattern at the start
            for greeting in self.GREETING_PATTERNS:
                pattern = re.compile(
                    rf"^{re.escape(greeting)}\b",
                    re.IGNORECASE | re.MULTILINE,
                )
                if pattern.search(text):
                    greeting_counter[greeting] += 1
                    break  # Only count one greeting per text

        if not greeting_counter:
            return ""

        # Return the most common greeting
        return greeting_counter.most_common(1)[0][0]

    def extract_sign_off_style(self, texts: list[str]) -> str:
        """Extract most common sign-off style from texts.

        Args:
            texts: List of text samples to analyze.

        Returns:
            Most common sign-off pattern or empty string if none found.
        """
        signoff_counter: Counter[str] = Counter()

        for text in texts:
            # Check for each sign-off pattern near the end
            for signoff in self.SIGNOFF_PATTERNS:
                # Look for sign-off followed by comma, newline, or end
                pattern = re.compile(
                    rf"\b{re.escape(signoff)}\b[\s,]*(?:\n|$)",
                    re.IGNORECASE | re.MULTILINE,
                )
                if pattern.search(text):
                    # Normalize to title case
                    signoff_counter[signoff] += 1
                    break  # Only count one sign-off per text

        if not signoff_counter:
            return ""

        # Return the most common sign-off
        return signoff_counter.most_common(1)[0][0]


class DigitalTwin:
    """Service class for digital twin operations.

    Provides async interface for analyzing user writing styles,
    storing fingerprints, and generating style-matched content.
    Uses Graphiti (Neo4j) as the underlying storage for semantic
    querying and temporal tracking.
    """

    # Default style guidelines returned when no user data exists
    _DEFAULT_STYLE_GUIDELINES = (
        "Write in a clear, professional tone.\n"
        "Use straightforward language.\n"
        "Keep sentences concise and readable."
    )

    def __init__(self) -> None:
        """Initialize the DigitalTwin service."""
        self._analyzer = TextStyleAnalyzer()

    async def _get_graphiti_client(self) -> "Graphiti":
        """Get the Graphiti client instance.

        Returns:
            Initialized Graphiti client.

        Raises:
            DigitalTwinError: If client initialization fails.
        """
        from src.db.graphiti import GraphitiClient

        try:
            return await GraphitiClient.get_instance()
        except Exception as e:
            raise DigitalTwinError(f"Failed to get Graphiti client: {e}") from e

    async def _get_style_guidelines_from_db(self, user_id: str) -> str | None:
        """Fall back to DB-backed style data when Graphiti is unavailable.

        Queries recipient_writing_profiles and digital_twin_profiles tables
        to build style guidelines without the knowledge graph.

        Args:
            user_id: The user ID.

        Returns:
            Style guidelines string, or None if no DB data exists.
        """
        from src.db.supabase import SupabaseClient

        try:
            db = SupabaseClient.get_client()

            # Try digital_twin_profiles first (general style)
            result = (
                db.table("digital_twin_profiles")
                .select("tone, writing_style, vocabulary_patterns, formality_level")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if result and result.data:
                row = result.data
                lines = []
                tone = row.get("tone", "professional")
                formality = row.get("formality_level", "business")
                writing_style = row.get("writing_style", "")

                if writing_style:
                    lines.append(f"Writing style: {writing_style}")
                if tone:
                    lines.append(f"Tone: {tone}")
                if formality:
                    lines.append(f"Formality level: {formality}")

                if lines:
                    logger.info(
                        "[EMAIL_PIPELINE] Using DB-backed style guidelines for user %s",
                        user_id,
                    )
                    return "\n".join(lines)

        except Exception as e:
            logger.warning(
                "[EMAIL_PIPELINE] DB fallback for style guidelines failed for user %s: %s",
                user_id,
                e,
            )

        return None

    def _build_fingerprint_body(self, fingerprint: WritingStyleFingerprint) -> str:
        """Build a structured fingerprint body string for storage.

        Args:
            fingerprint: The WritingStyleFingerprint instance to serialize.

        Returns:
            Structured text representation of the fingerprint.
        """
        # Format punctuation patterns as a string
        punct_str = ",".join(
            f"{char}={ratio:.2f}" for char, ratio in fingerprint.punctuation_patterns.items()
        )

        # Format common phrases as comma-separated string
        phrases_str = ", ".join(fingerprint.common_phrases)

        parts = [
            f"average_sentence_length: {fingerprint.average_sentence_length}",
            f"vocabulary_level: {fingerprint.vocabulary_level}",
            f"formality_score: {fingerprint.formality_score}",
            f"common_phrases: {phrases_str}",
            f"greeting_style: {fingerprint.greeting_style}",
            f"sign_off_style: {fingerprint.sign_off_style}",
            f"emoji_usage: {fingerprint.emoji_usage}",
            f"punctuation_patterns: {punct_str}",
            f"samples_analyzed: {fingerprint.samples_analyzed}",
            f"confidence: {fingerprint.confidence}",
            f"created_at: {fingerprint.created_at.isoformat()}",
            f"updated_at: {fingerprint.updated_at.isoformat()}",
        ]

        return "\n".join(parts)

    def _parse_fingerprint_from_edge(
        self, edge: Any, user_id: str
    ) -> WritingStyleFingerprint | None:
        """Parse a Graphiti edge into a WritingStyleFingerprint.

        Args:
            edge: The Graphiti edge object.
            user_id: The user ID.

        Returns:
            WritingStyleFingerprint if parsing succeeds, None otherwise.
        """
        try:
            fact = getattr(edge, "fact", "")
            edge_uuid = getattr(edge, "uuid", None) or str(uuid.uuid4())
            created_at = getattr(edge, "created_at", datetime.now(UTC))

            # Parse structured content from fact
            lines = fact.split("\n")
            avg_sentence_length = 0.0
            vocabulary_level = "moderate"
            formality_score = 0.5
            common_phrases: list[str] = []
            greeting_style = ""
            sign_off_style = ""
            emoji_usage = False
            punctuation_patterns: dict[str, float] = {}
            samples_analyzed = 0
            confidence = 0.0
            fp_created_at = created_at
            fp_updated_at = created_at

            for line in lines:
                if line.startswith("average_sentence_length:"):
                    with contextlib.suppress(ValueError):
                        avg_sentence_length = float(
                            line.replace("average_sentence_length:", "").strip()
                        )
                elif line.startswith("vocabulary_level:"):
                    vocabulary_level = line.replace("vocabulary_level:", "").strip()
                elif line.startswith("formality_score:"):
                    with contextlib.suppress(ValueError):
                        formality_score = float(line.replace("formality_score:", "").strip())
                elif line.startswith("common_phrases:"):
                    phrases_str = line.replace("common_phrases:", "").strip()
                    if phrases_str:
                        common_phrases = [p.strip() for p in phrases_str.split(",") if p.strip()]
                elif line.startswith("greeting_style:"):
                    greeting_style = line.replace("greeting_style:", "").strip()
                elif line.startswith("sign_off_style:"):
                    sign_off_style = line.replace("sign_off_style:", "").strip()
                elif line.startswith("emoji_usage:"):
                    emoji_str = line.replace("emoji_usage:", "").strip().lower()
                    emoji_usage = emoji_str == "true"
                elif line.startswith("punctuation_patterns:"):
                    punct_str = line.replace("punctuation_patterns:", "").strip()
                    if punct_str:
                        for item in punct_str.split(","):
                            if "=" in item:
                                char, ratio = item.split("=", 1)
                                with contextlib.suppress(ValueError):
                                    punctuation_patterns[char.strip()] = float(ratio.strip())
                elif line.startswith("samples_analyzed:"):
                    with contextlib.suppress(ValueError):
                        samples_analyzed = int(line.replace("samples_analyzed:", "").strip())
                elif line.startswith("confidence:"):
                    with contextlib.suppress(ValueError):
                        confidence = float(line.replace("confidence:", "").strip())
                elif line.startswith("created_at:"):
                    with contextlib.suppress(ValueError):
                        fp_created_at = datetime.fromisoformat(
                            line.replace("created_at:", "").strip()
                        )
                elif line.startswith("updated_at:"):
                    with contextlib.suppress(ValueError):
                        fp_updated_at = datetime.fromisoformat(
                            line.replace("updated_at:", "").strip()
                        )

            return WritingStyleFingerprint(
                id=edge_uuid,
                user_id=user_id,
                average_sentence_length=avg_sentence_length,
                vocabulary_level=vocabulary_level,
                formality_score=formality_score,
                common_phrases=common_phrases,
                greeting_style=greeting_style,
                sign_off_style=sign_off_style,
                emoji_usage=emoji_usage,
                punctuation_patterns=punctuation_patterns,
                samples_analyzed=samples_analyzed,
                confidence=confidence,
                created_at=fp_created_at,
                updated_at=fp_updated_at,
            )

        except Exception as e:
            logger.warning(f"Failed to parse fingerprint from edge: {e}")
            return None

    async def analyze_sample(self, user_id: str, text: str, text_type: str) -> None:
        """Analyze text and update the user's fingerprint.

        Performs incremental weighted average when updating existing fingerprint.

        Args:
            user_id: The user ID.
            text: The text sample to analyze.
            text_type: The type of text (e.g., "email", "message").

        Raises:
            DigitalTwinError: If analysis fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Get existing fingerprint if it exists
            existing = await self.get_fingerprint(user_id)

            # Extract features from the new text
            sentence_length = self._analyzer.extract_sentence_length(text)
            vocabulary_level = self._analyzer.extract_vocabulary_level(text)
            formality_score = self._analyzer.extract_formality_score(text)
            punctuation_patterns = self._analyzer.extract_punctuation_patterns(text)
            emoji_usage = self._analyzer.detect_emoji_usage(text)

            # For single sample, extract greeting/sign-off
            greeting_style = self._analyzer.extract_greeting_style([text])
            sign_off_style = self._analyzer.extract_sign_off_style([text])
            common_phrases = self._analyzer.extract_common_phrases([text], min_occurrences=1)

            now = datetime.now(UTC)

            if existing:
                # Incremental weighted average
                old_weight = existing.samples_analyzed
                new_weight = 1
                total_weight = old_weight + new_weight

                avg_sentence_length = (
                    existing.average_sentence_length * old_weight + sentence_length * new_weight
                ) / total_weight

                new_formality = (
                    existing.formality_score * old_weight + formality_score * new_weight
                ) / total_weight

                # Merge punctuation patterns
                merged_punct: dict[str, float] = {}
                all_chars = set(existing.punctuation_patterns.keys()) | set(
                    punctuation_patterns.keys()
                )
                for char in all_chars:
                    old_val = existing.punctuation_patterns.get(char, 0.0)
                    new_val = punctuation_patterns.get(char, 0.0)
                    merged_punct[char] = (
                        old_val * old_weight + new_val * new_weight
                    ) / total_weight

                # Merge common phrases (keep unique)
                merged_phrases = list(set(existing.common_phrases + common_phrases[:5]))[:10]

                # Update greeting/sign-off if new ones found
                final_greeting = greeting_style if greeting_style else existing.greeting_style
                final_sign_off = sign_off_style if sign_off_style else existing.sign_off_style

                # Emoji usage: True if any sample has emojis
                final_emoji_usage = existing.emoji_usage or emoji_usage

                # Vocabulary level: take most recent for simplicity
                final_vocabulary_level = vocabulary_level

                samples = existing.samples_analyzed + 1

                # Confidence increases with more samples (max 0.95)
                confidence = min(0.95, 0.5 + (samples * 0.05))

                fingerprint = WritingStyleFingerprint(
                    id=existing.id,
                    user_id=user_id,
                    average_sentence_length=avg_sentence_length,
                    vocabulary_level=final_vocabulary_level,
                    formality_score=new_formality,
                    common_phrases=merged_phrases,
                    greeting_style=final_greeting,
                    sign_off_style=final_sign_off,
                    emoji_usage=final_emoji_usage,
                    punctuation_patterns=merged_punct,
                    samples_analyzed=samples,
                    confidence=confidence,
                    created_at=existing.created_at,
                    updated_at=now,
                )
            else:
                # Create new fingerprint
                fingerprint = WritingStyleFingerprint(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    average_sentence_length=sentence_length,
                    vocabulary_level=vocabulary_level,
                    formality_score=formality_score,
                    common_phrases=common_phrases[:10],
                    greeting_style=greeting_style,
                    sign_off_style=sign_off_style,
                    emoji_usage=emoji_usage,
                    punctuation_patterns=punctuation_patterns,
                    samples_analyzed=1,
                    confidence=0.55,
                    created_at=now,
                    updated_at=now,
                )

            # Build fingerprint body and store
            fingerprint_body = self._build_fingerprint_body(fingerprint)

            from graphiti_core.nodes import EpisodeType

            await client.add_episode(
                name=f"fingerprint:{user_id}",
                episode_body=fingerprint_body,
                source=EpisodeType.text,
                source_description=f"digital_twin:{user_id}:{text_type}",
                reference_time=now,
            )

            logger.info(
                f"Updated fingerprint for user {user_id}",
                extra={"user_id": user_id, "samples_analyzed": fingerprint.samples_analyzed},
            )

        except DigitalTwinError:
            raise
        except Exception as e:
            logger.exception(f"Failed to analyze sample: {e}")
            raise DigitalTwinError(f"Failed to analyze sample: {e}") from e

    async def get_fingerprint(self, user_id: str) -> WritingStyleFingerprint | None:
        """Retrieve a user's writing style fingerprint.

        Args:
            user_id: The user ID.

        Returns:
            WritingStyleFingerprint if found, None otherwise.

        Raises:
            DigitalTwinError: If retrieval fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Search for fingerprint
            query = f"fingerprint for user {user_id}"
            results = await client.search(query)

            if not results:
                return None

            # Parse the first matching result
            for edge in results:
                fingerprint = self._parse_fingerprint_from_edge(edge, user_id)
                if fingerprint:
                    return fingerprint

            return None

        except DigitalTwinError:
            raise
        except Exception as e:
            logger.exception(f"Failed to get fingerprint: {e}")
            raise DigitalTwinError(f"Failed to get fingerprint: {e}") from e

    async def get_style_guidelines(self, user_id: str) -> str:
        """Get prompt-ready style instructions for the user.

        Returns a multi-line string with style instructions that can
        be included in LLM prompts to generate style-matched content.
        Falls back to DB-backed profiles when Graphiti is unavailable.

        Args:
            user_id: The user ID.

        Returns:
            Style guidelines string (never raises).
        """
        fingerprint = None
        try:
            fingerprint = await self.get_fingerprint(user_id)
        except Exception as e:
            logger.warning(
                "[EMAIL_PIPELINE] Graphiti unavailable for style guidelines, "
                "using DB fallback for user %s: %s",
                user_id,
                e,
            )
            # Try DB fallback
            db_guidelines = await self._get_style_guidelines_from_db(user_id)
            if db_guidelines:
                return db_guidelines
            return self._DEFAULT_STYLE_GUIDELINES

        if not fingerprint:
            # No Graphiti data — try DB fallback before returning defaults
            db_guidelines = await self._get_style_guidelines_from_db(user_id)
            if db_guidelines:
                return db_guidelines
            return self._DEFAULT_STYLE_GUIDELINES

        lines = []

        # Greeting style
        if fingerprint.greeting_style:
            lines.append(f"Start messages with greetings like '{fingerprint.greeting_style}'.")

        # Sign-off style
        if fingerprint.sign_off_style:
            lines.append(f"End messages with sign-offs like '{fingerprint.sign_off_style}'.")

        # Vocabulary level
        if fingerprint.vocabulary_level == "simple":
            lines.append("Use simple, everyday language.")
        elif fingerprint.vocabulary_level == "advanced":
            lines.append("Use sophisticated vocabulary when appropriate.")
        else:
            lines.append("Use moderate vocabulary - neither too simple nor too complex.")

        # Formality
        if fingerprint.formality_score < 0.4:
            lines.append("Keep a casual, informal tone.")
        elif fingerprint.formality_score > 0.7:
            lines.append("Maintain a formal, professional tone.")
        else:
            lines.append("Use a balanced, semi-formal tone.")

        # Sentence length
        if fingerprint.average_sentence_length < 10:
            lines.append("Keep sentences short and punchy.")
        elif fingerprint.average_sentence_length > 20:
            lines.append("Use longer, more detailed sentences.")
        else:
            lines.append("Use medium-length sentences.")

        # Emoji usage
        if fingerprint.emoji_usage:
            lines.append("Include relevant emojis when appropriate.")
        else:
            lines.append("Do not use emojis.")

        # Common phrases
        if fingerprint.common_phrases:
            phrases = ", ".join(f"'{p}'" for p in fingerprint.common_phrases[:3])
            lines.append(f"Consider using phrases like: {phrases}.")

        return "\n".join(lines)

    async def _score_style_match_from_db(
        self, user_id: str, generated_text: str
    ) -> float | None:
        """Score style match using DB-backed profile when Graphiti is unavailable.

        Compares measurable text attributes (sentence length, formality
        indicators, message length) against the stored user profile to
        produce a continuous score that varies per draft.

        Args:
            user_id: The user ID.
            generated_text: The text to score.

        Returns:
            Similarity score from 0.0 to 1.0, or None if no DB data exists.
        """
        from src.db.supabase import SupabaseClient

        try:
            db = SupabaseClient.get_client()
            result = (
                db.table("digital_twin_profiles")
                .select("tone, writing_style, vocabulary_patterns, formality_level")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )

            if not result or not result.data:
                return None

            row = result.data
            writing_style = row.get("writing_style", "")
            if not writing_style and not row.get("formality_level") and not row.get("tone"):
                return None

            scores: list[float] = []

            # 1. Sentence length comparison (continuous)
            draft_sentences = [s.strip() for s in generated_text.split(".") if s.strip()]
            avg_draft_len = (
                sum(len(s.split()) for s in draft_sentences) / max(len(draft_sentences), 1)
            )
            expected_len = 15  # default
            if writing_style:
                low = writing_style.lower()
                if "concise" in low or "brief" in low or "short" in low:
                    expected_len = 10
                elif "detailed" in low or "thorough" in low or "long" in low:
                    expected_len = 22
            if expected_len > 0:
                len_score = 1.0 - min(abs(avg_draft_len - expected_len) / expected_len, 1.0)
                scores.append(len_score)

            # 2. Formality match via indicator words (continuous)
            formality = row.get("formality_level", "moderate") or "moderate"
            formal_indicators = ["regards", "sincerely", "dear", "pleased", "kindly"]
            casual_indicators = ["hey", "thanks!", "cheers", "!", "lol"]
            draft_lower = generated_text.lower()
            formal_count = sum(1 for w in formal_indicators if w in draft_lower)
            casual_count = sum(1 for w in casual_indicators if w in draft_lower)
            if formality in ("formal", "very_formal"):
                form_score = min(formal_count * 0.3, 1.0) if formal_count > casual_count else 0.3
            elif formality in ("casual", "informal"):
                form_score = min(casual_count * 0.3, 1.0) if casual_count > formal_count else 0.3
            else:
                form_score = 0.7  # moderate/business matches most things
            scores.append(form_score)

            # 3. Message length similarity (continuous ratio)
            draft_words = len(generated_text.split())
            expected_words = 80  # default
            if writing_style:
                low = writing_style.lower()
                if "concise" in low or "brief" in low:
                    expected_words = 50
                elif "detailed" in low or "thorough" in low:
                    expected_words = 150
            if expected_words > 0 and draft_words > 0:
                length_ratio = min(draft_words, expected_words) / max(draft_words, expected_words)
                scores.append(length_ratio)

            if not scores:
                return None

            return round(sum(scores) / len(scores), 3)

        except Exception as e:
            logger.warning(
                "[EMAIL_PIPELINE] DB fallback for style scoring failed for user %s: %s",
                user_id,
                e,
            )
            return None

    async def score_style_match(self, user_id: str, generated_text: str) -> float:
        """Score how well generated text matches the user's style.

        Compares the features of generated text against the user's
        fingerprint to produce a similarity score.
        Falls back to DB-based comparison when Graphiti is unavailable.

        Args:
            user_id: The user ID.
            generated_text: The text to score.

        Returns:
            Similarity score from 0.0 to 1.0 (never raises).
        """
        try:
            fingerprint = await self.get_fingerprint(user_id)
        except Exception as e:
            logger.warning(
                "[EMAIL_PIPELINE] Graphiti unavailable for style scoring, "
                "trying DB fallback for user %s: %s",
                user_id,
                e,
            )
            # Try DB fallback before returning default
            db_score = await self._score_style_match_from_db(user_id, generated_text)
            if db_score is not None:
                return db_score
            return 0.5

        if not fingerprint:
            # No Graphiti data — try DB fallback before returning default
            db_score = await self._score_style_match_from_db(user_id, generated_text)
            if db_score is not None:
                return db_score
            return 0.5

        scores: list[float] = []

        # Compare sentence length (allow 50% variance)
        gen_sentence_length = self._analyzer.extract_sentence_length(generated_text)
        if fingerprint.average_sentence_length > 0:
            length_diff = abs(gen_sentence_length - fingerprint.average_sentence_length)
            length_score = max(0.0, 1.0 - (length_diff / fingerprint.average_sentence_length))
            scores.append(length_score)

        # Compare formality
        gen_formality = self._analyzer.extract_formality_score(generated_text)
        formality_diff = abs(gen_formality - fingerprint.formality_score)
        formality_score = max(0.0, 1.0 - formality_diff)
        scores.append(formality_score)

        # Compare vocabulary level
        gen_vocabulary = self._analyzer.extract_vocabulary_level(generated_text)
        vocabulary_score = 1.0 if gen_vocabulary == fingerprint.vocabulary_level else 0.5
        scores.append(vocabulary_score)

        # Compare emoji usage
        gen_emoji = self._analyzer.detect_emoji_usage(generated_text)
        emoji_score = 1.0 if gen_emoji == fingerprint.emoji_usage else 0.5
        scores.append(emoji_score)

        # Check for greeting style match
        if fingerprint.greeting_style:
            greeting_match = fingerprint.greeting_style.lower() in generated_text.lower()
            scores.append(1.0 if greeting_match else 0.5)

        # Check for sign-off style match
        if fingerprint.sign_off_style:
            signoff_match = fingerprint.sign_off_style.lower() in generated_text.lower()
            scores.append(1.0 if signoff_match else 0.5)

        # Check for common phrases
        if fingerprint.common_phrases:
            phrase_matches = sum(
                1
                for phrase in fingerprint.common_phrases
                if phrase.lower() in generated_text.lower()
            )
            phrase_score = min(1.0, phrase_matches / len(fingerprint.common_phrases))
            scores.append(phrase_score)

        if not scores:
            return 0.5

        return sum(scores) / len(scores)

    async def update_fingerprint(
        self, user_id: str, texts: list[str], text_type: str = "email"
    ) -> WritingStyleFingerprint:
        """Batch update fingerprint from multiple text samples.

        Analyzes all provided texts and creates/updates the fingerprint
        in a single operation.

        Args:
            user_id: The user ID.
            texts: List of text samples to analyze.
            text_type: The type of texts (default: "email").

        Returns:
            The updated WritingStyleFingerprint.

        Raises:
            DigitalTwinError: If update fails.
        """
        if not texts:
            raise DigitalTwinError("No texts provided for fingerprint update")

        try:
            client = await self._get_graphiti_client()

            # Analyze all texts
            sentence_lengths: list[float] = []
            formality_scores: list[float] = []
            vocabulary_levels: list[str] = []
            all_punct: dict[str, list[float]] = {}
            emoji_usages: list[bool] = []

            for text in texts:
                sentence_lengths.append(self._analyzer.extract_sentence_length(text))
                formality_scores.append(self._analyzer.extract_formality_score(text))
                vocabulary_levels.append(self._analyzer.extract_vocabulary_level(text))
                emoji_usages.append(self._analyzer.detect_emoji_usage(text))

                punct = self._analyzer.extract_punctuation_patterns(text)
                for char, ratio in punct.items():
                    if char not in all_punct:
                        all_punct[char] = []
                    all_punct[char].append(ratio)

            # Compute averages
            avg_sentence_length = sum(sentence_lengths) / len(sentence_lengths)
            avg_formality = sum(formality_scores) / len(formality_scores)

            # Most common vocabulary level
            vocab_counter: Counter[str] = Counter(vocabulary_levels)
            vocabulary_level = vocab_counter.most_common(1)[0][0]

            # Average punctuation patterns
            punct_patterns = {char: sum(ratios) / len(ratios) for char, ratios in all_punct.items()}

            # Any emoji usage
            emoji_usage = any(emoji_usages)

            # Extract greeting, sign-off, and phrases from all texts
            greeting_style = self._analyzer.extract_greeting_style(texts)
            sign_off_style = self._analyzer.extract_sign_off_style(texts)
            common_phrases = self._analyzer.extract_common_phrases(texts, min_occurrences=2)[:10]

            now = datetime.now(UTC)
            samples = len(texts)
            confidence = min(0.95, 0.5 + (samples * 0.05))

            fingerprint = WritingStyleFingerprint(
                id=str(uuid.uuid4()),
                user_id=user_id,
                average_sentence_length=avg_sentence_length,
                vocabulary_level=vocabulary_level,
                formality_score=avg_formality,
                common_phrases=common_phrases,
                greeting_style=greeting_style,
                sign_off_style=sign_off_style,
                emoji_usage=emoji_usage,
                punctuation_patterns=punct_patterns,
                samples_analyzed=samples,
                confidence=confidence,
                created_at=now,
                updated_at=now,
            )

            # Store in Graphiti
            fingerprint_body = self._build_fingerprint_body(fingerprint)

            from graphiti_core.nodes import EpisodeType

            await client.add_episode(
                name=f"fingerprint:{user_id}",
                episode_body=fingerprint_body,
                source=EpisodeType.text,
                source_description=f"digital_twin:{user_id}:{text_type}",
                reference_time=now,
            )

            logger.info(
                f"Created fingerprint for user {user_id} from {samples} samples",
                extra={"user_id": user_id, "samples": samples},
            )

            return fingerprint

        except DigitalTwinError:
            raise
        except Exception as e:
            logger.exception(f"Failed to update fingerprint: {e}")
            raise DigitalTwinError(f"Failed to update fingerprint: {e}") from e
