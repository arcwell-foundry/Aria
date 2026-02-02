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

import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
