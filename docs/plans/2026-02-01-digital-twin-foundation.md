# Digital Twin Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Digital Twin Foundation (US-209) to capture and analyze user writing style for personalized communication.

**Architecture:** Store writing style fingerprints as semantic facts in Graphiti. The DigitalTwin service analyzes text samples to extract style features (sentence length, vocabulary level, formality, punctuation patterns, greeting/sign-off styles). Style guidelines are generated for LLM prompts, and a style match scorer evaluates generated text against the user's fingerprint.

**Tech Stack:** Python 3.11+, FastAPI, Graphiti (Neo4j), Pydantic, pytest with AsyncMock

---

## Task 1: Add DigitalTwin Exceptions

**Files:**
- Modify: `backend/src/core/exceptions.py`
- Test: `backend/tests/test_exceptions.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_exceptions.py`:

```python
def test_digital_twin_error_has_correct_attributes() -> None:
    """Test DigitalTwinError has correct message, code, and status."""
    from src.core.exceptions import DigitalTwinError

    error = DigitalTwinError("Style extraction failed")
    assert error.message == "Digital twin operation failed: Style extraction failed"
    assert error.code == "DIGITAL_TWIN_ERROR"
    assert error.status_code == 500


def test_fingerprint_not_found_error_has_correct_attributes() -> None:
    """Test FingerprintNotFoundError has correct message and details."""
    from src.core.exceptions import FingerprintNotFoundError

    error = FingerprintNotFoundError("fp-123")
    assert "Fingerprint" in error.message
    assert "fp-123" in error.message
    assert error.status_code == 404
    assert error.details["resource"] == "Fingerprint"
    assert error.details["resource_id"] == "fp-123"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_exceptions.py::test_digital_twin_error_has_correct_attributes tests/test_exceptions.py::test_fingerprint_not_found_error_has_correct_attributes -v`

Expected: FAIL with "cannot import name 'DigitalTwinError'"

**Step 3: Write minimal implementation**

Add to `backend/src/core/exceptions.py` (after ProspectiveMemoryError class):

```python
class DigitalTwinError(ARIAException):
    """Digital twin operation error (500).

    Used for failures when analyzing writing style or managing fingerprints.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize digital twin error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Digital twin operation failed: {message}",
            code="DIGITAL_TWIN_ERROR",
            status_code=500,
        )


class FingerprintNotFoundError(NotFoundError):
    """Writing style fingerprint not found error (404)."""

    def __init__(self, fingerprint_id: str) -> None:
        """Initialize fingerprint not found error.

        Args:
            fingerprint_id: The ID of the fingerprint that was not found.
        """
        super().__init__(resource="Fingerprint", resource_id=fingerprint_id)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_exceptions.py::test_digital_twin_error_has_correct_attributes tests/test_exceptions.py::test_fingerprint_not_found_error_has_correct_attributes -v`

Expected: PASS

**Step 5: Commit**

```bash
cd backend && git add src/core/exceptions.py tests/test_exceptions.py
git commit -m "$(cat <<'EOF'
feat(memory): add DigitalTwinError and FingerprintNotFoundError exceptions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Create WritingStyleFingerprint Dataclass

**Files:**
- Create: `backend/src/memory/digital_twin.py`
- Test: `backend/tests/test_digital_twin.py`

**Step 1: Write the failing test**

Create `backend/tests/test_digital_twin.py`:

```python
"""Tests for digital twin module."""

import json
from datetime import UTC, datetime

import pytest


def test_writing_style_fingerprint_initialization() -> None:
    """Test WritingStyleFingerprint initializes with required fields."""
    from src.memory.digital_twin import WritingStyleFingerprint

    now = datetime.now(UTC)
    fingerprint = WritingStyleFingerprint(
        id="fp-123",
        user_id="user-456",
        average_sentence_length=15.5,
        vocabulary_level="moderate",
        formality_score=0.7,
        common_phrases=["best regards", "looking forward"],
        greeting_style="Hi",
        sign_off_style="Best",
        emoji_usage=False,
        punctuation_patterns={"!": 0.05, "?": 0.1},
        samples_analyzed=10,
        confidence=0.8,
        created_at=now,
        updated_at=now,
    )

    assert fingerprint.id == "fp-123"
    assert fingerprint.user_id == "user-456"
    assert fingerprint.average_sentence_length == 15.5
    assert fingerprint.vocabulary_level == "moderate"
    assert fingerprint.formality_score == 0.7
    assert fingerprint.common_phrases == ["best regards", "looking forward"]
    assert fingerprint.greeting_style == "Hi"
    assert fingerprint.sign_off_style == "Best"
    assert fingerprint.emoji_usage is False
    assert fingerprint.punctuation_patterns == {"!": 0.05, "?": 0.1}
    assert fingerprint.samples_analyzed == 10
    assert fingerprint.confidence == 0.8


def test_writing_style_fingerprint_to_dict_serializes_correctly() -> None:
    """Test WritingStyleFingerprint.to_dict returns a serializable dictionary."""
    from src.memory.digital_twin import WritingStyleFingerprint

    now = datetime.now(UTC)
    fingerprint = WritingStyleFingerprint(
        id="fp-123",
        user_id="user-456",
        average_sentence_length=12.0,
        vocabulary_level="simple",
        formality_score=0.5,
        common_phrases=["thanks"],
        greeting_style="Hey",
        sign_off_style="Cheers",
        emoji_usage=True,
        punctuation_patterns={".": 0.8},
        samples_analyzed=5,
        confidence=0.6,
        created_at=now,
        updated_at=now,
    )

    data = fingerprint.to_dict()

    assert data["id"] == "fp-123"
    assert data["user_id"] == "user-456"
    assert data["average_sentence_length"] == 12.0
    assert data["vocabulary_level"] == "simple"
    assert data["formality_score"] == 0.5
    assert data["common_phrases"] == ["thanks"]
    assert data["greeting_style"] == "Hey"
    assert data["sign_off_style"] == "Cheers"
    assert data["emoji_usage"] is True
    assert data["punctuation_patterns"] == {".": 0.8}
    assert data["samples_analyzed"] == 5
    assert data["confidence"] == 0.6
    assert data["created_at"] == now.isoformat()
    assert data["updated_at"] == now.isoformat()

    # Verify JSON serializable
    json_str = json.dumps(data)
    assert isinstance(json_str, str)


def test_writing_style_fingerprint_from_dict_deserializes_correctly() -> None:
    """Test WritingStyleFingerprint.from_dict creates instance from dictionary."""
    from src.memory.digital_twin import WritingStyleFingerprint

    now = datetime.now(UTC)
    data = {
        "id": "fp-789",
        "user_id": "user-abc",
        "average_sentence_length": 20.0,
        "vocabulary_level": "advanced",
        "formality_score": 0.9,
        "common_phrases": ["per our discussion", "as previously mentioned"],
        "greeting_style": "Dear",
        "sign_off_style": "Sincerely",
        "emoji_usage": False,
        "punctuation_patterns": {".": 0.7, ",": 0.2, ";": 0.1},
        "samples_analyzed": 25,
        "confidence": 0.95,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    fingerprint = WritingStyleFingerprint.from_dict(data)

    assert fingerprint.id == "fp-789"
    assert fingerprint.user_id == "user-abc"
    assert fingerprint.average_sentence_length == 20.0
    assert fingerprint.vocabulary_level == "advanced"
    assert fingerprint.formality_score == 0.9
    assert fingerprint.common_phrases == ["per our discussion", "as previously mentioned"]
    assert fingerprint.greeting_style == "Dear"
    assert fingerprint.sign_off_style == "Sincerely"
    assert fingerprint.emoji_usage is False
    assert fingerprint.punctuation_patterns == {".": 0.7, ",": 0.2, ";": 0.1}
    assert fingerprint.samples_analyzed == 25
    assert fingerprint.confidence == 0.95
    assert fingerprint.created_at == now
    assert fingerprint.updated_at == now
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_digital_twin.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.memory.digital_twin'"

**Step 3: Write minimal implementation**

Create `backend/src/memory/digital_twin.py`:

```python
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
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_digital_twin.py -v`

Expected: PASS (3 tests)

**Step 5: Commit**

```bash
cd backend && git add src/memory/digital_twin.py tests/test_digital_twin.py
git commit -m "$(cat <<'EOF'
feat(memory): add WritingStyleFingerprint dataclass for digital twin

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Implement Text Style Analyzer

**Files:**
- Modify: `backend/src/memory/digital_twin.py`
- Test: `backend/tests/test_digital_twin.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_digital_twin.py`:

```python
def test_text_style_analyzer_extract_sentence_length() -> None:
    """Test TextStyleAnalyzer extracts average sentence length."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    text = "Hello there. How are you today? I hope you are doing well."
    result = analyzer.extract_sentence_length(text)

    # 3 sentences, roughly 3 + 5 + 7 = 15 words, avg 5
    assert 4.0 <= result <= 6.0


def test_text_style_analyzer_extract_vocabulary_level_simple() -> None:
    """Test TextStyleAnalyzer detects simple vocabulary."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    text = "Hi! How are you? I am good. See you soon."
    result = analyzer.extract_vocabulary_level(text)

    assert result == "simple"


def test_text_style_analyzer_extract_vocabulary_level_advanced() -> None:
    """Test TextStyleAnalyzer detects advanced vocabulary."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    text = (
        "The pharmaceutical consortium's comprehensive analysis demonstrates "
        "unprecedented efficacy in cardiovascular rehabilitation protocols."
    )
    result = analyzer.extract_vocabulary_level(text)

    assert result == "advanced"


def test_text_style_analyzer_extract_formality_informal() -> None:
    """Test TextStyleAnalyzer detects informal tone."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    text = "Hey! What's up? Gonna grab lunch? lol that's awesome :)"
    result = analyzer.extract_formality_score(text)

    assert result < 0.4


def test_text_style_analyzer_extract_formality_formal() -> None:
    """Test TextStyleAnalyzer detects formal tone."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    text = (
        "Dear Mr. Johnson, I am writing to formally request a meeting "
        "regarding the proposed acquisition. Please advise on your availability."
    )
    result = analyzer.extract_formality_score(text)

    assert result > 0.6


def test_text_style_analyzer_extract_punctuation_patterns() -> None:
    """Test TextStyleAnalyzer extracts punctuation patterns."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    text = "Hello! How are you? I am fine. Great to hear!"
    result = analyzer.extract_punctuation_patterns(text)

    assert "." in result
    assert "!" in result
    assert "?" in result
    # Should be ratios, not counts
    total = sum(result.values())
    assert 0.99 <= total <= 1.01  # Should sum to ~1.0


def test_text_style_analyzer_detect_emoji_usage_true() -> None:
    """Test TextStyleAnalyzer detects emoji usage."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    text = "Thanks so much! 😊 Looking forward to it! 🎉"
    result = analyzer.detect_emoji_usage(text)

    assert result is True


def test_text_style_analyzer_detect_emoji_usage_false() -> None:
    """Test TextStyleAnalyzer detects no emoji usage."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    text = "Thank you for your consideration. I look forward to hearing from you."
    result = analyzer.detect_emoji_usage(text)

    assert result is False


def test_text_style_analyzer_extract_common_phrases() -> None:
    """Test TextStyleAnalyzer extracts common phrases."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    texts = [
        "Best regards, John",
        "Looking forward to your response. Best regards, John",
        "Thank you. Best regards, John",
    ]
    result = analyzer.extract_common_phrases(texts)

    # "Best regards" should be detected
    assert any("best regards" in phrase.lower() for phrase in result)


def test_text_style_analyzer_extract_greeting_style() -> None:
    """Test TextStyleAnalyzer extracts greeting style."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    texts = [
        "Hi Sarah, hope you're doing well.",
        "Hi Team, quick update on the project.",
        "Hi everyone, let's discuss the roadmap.",
    ]
    result = analyzer.extract_greeting_style(texts)

    assert result == "Hi"


def test_text_style_analyzer_extract_sign_off_style() -> None:
    """Test TextStyleAnalyzer extracts sign-off style."""
    from src.memory.digital_twin import TextStyleAnalyzer

    analyzer = TextStyleAnalyzer()
    texts = [
        "Let me know your thoughts.\n\nBest,\nJohn",
        "Looking forward to it.\n\nBest,\nJohn",
        "Talk soon.\n\nBest,\nJohn",
    ]
    result = analyzer.extract_sign_off_style(texts)

    assert result == "Best"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_digital_twin.py::test_text_style_analyzer_extract_sentence_length -v`

Expected: FAIL with "cannot import name 'TextStyleAnalyzer'"

**Step 3: Write minimal implementation**

Add to `backend/src/memory/digital_twin.py` (after WritingStyleFingerprint class):

```python
import re
from collections import Counter


class TextStyleAnalyzer:
    """Analyzes text samples to extract writing style features.

    Provides methods to extract individual style metrics from text,
    which are combined to build a WritingStyleFingerprint.
    """

    # Common greeting patterns
    GREETING_PATTERNS = [
        "Dear", "Hi", "Hey", "Hello", "Good morning", "Good afternoon",
        "Good evening", "Greetings", "To whom it may concern",
    ]

    # Common sign-off patterns
    SIGNOFF_PATTERNS = [
        "Best", "Best regards", "Regards", "Sincerely", "Thanks", "Thank you",
        "Cheers", "Warm regards", "Kind regards", "Yours truly", "Take care",
    ]

    # Formal indicators
    FORMAL_WORDS = {
        "pursuant", "hereby", "regarding", "concerning", "aforementioned",
        "acknowledge", "advise", "request", "inquire", "furthermore",
        "therefore", "consequently", "respectively", "accordingly",
        "sincerely", "respectfully", "cordially", "formally",
    }

    # Informal indicators
    INFORMAL_PATTERNS = [
        r"\bgonna\b", r"\bwanna\b", r"\bgotta\b", r"\bkinda\b", r"\bsorta\b",
        r"\blol\b", r"\bomg\b", r"\bbtw\b", r"\bidk\b", r"\bimo\b",
        r":\)", r":\(", r":D", r";-?\)", r"<3",
    ]

    # Emoji regex pattern
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U000024C2-\U0001F251"  # enclosed characters
        "]+"
    )

    def extract_sentence_length(self, text: str) -> float:
        """Extract average sentence length in words.

        Args:
            text: The text to analyze.

        Returns:
            Average number of words per sentence.
        """
        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return 0.0

        total_words = 0
        for sentence in sentences:
            words = sentence.split()
            total_words += len(words)

        return total_words / len(sentences)

    def extract_vocabulary_level(self, text: str) -> str:
        """Determine vocabulary complexity level.

        Uses average word length as a proxy for vocabulary complexity.
        Real implementation would use more sophisticated metrics.

        Args:
            text: The text to analyze.

        Returns:
            One of: "simple", "moderate", "advanced"
        """
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())

        if not words:
            return "moderate"

        # Calculate average word length
        avg_word_length = sum(len(w) for w in words) / len(words)

        # Count long words (8+ chars)
        long_word_ratio = len([w for w in words if len(w) >= 8]) / len(words)

        if avg_word_length >= 6.0 or long_word_ratio >= 0.2:
            return "advanced"
        elif avg_word_length >= 4.5 or long_word_ratio >= 0.1:
            return "moderate"
        else:
            return "simple"

    def extract_formality_score(self, text: str) -> float:
        """Calculate formality score from 0 (informal) to 1 (formal).

        Args:
            text: The text to analyze.

        Returns:
            Formality score between 0.0 and 1.0.
        """
        text_lower = text.lower()
        words = re.findall(r'\b[a-zA-Z]+\b', text_lower)

        if not words:
            return 0.5

        # Count formal indicators
        formal_count = sum(1 for w in words if w in self.FORMAL_WORDS)

        # Count informal indicators
        informal_count = 0
        for pattern in self.INFORMAL_PATTERNS:
            informal_count += len(re.findall(pattern, text_lower, re.IGNORECASE))

        # Check for contractions (informal)
        contractions = len(re.findall(r"\b\w+'\w+\b", text))
        informal_count += contractions

        # Check for emojis (informal)
        if self.EMOJI_PATTERN.search(text):
            informal_count += 2

        # Calculate score
        total_indicators = formal_count + informal_count
        if total_indicators == 0:
            # Default to moderate formality if no indicators
            return 0.5

        formal_ratio = formal_count / total_indicators
        return min(1.0, max(0.0, formal_ratio))

    def extract_punctuation_patterns(self, text: str) -> dict[str, float]:
        """Extract punctuation usage patterns as frequency ratios.

        Args:
            text: The text to analyze.

        Returns:
            Dictionary mapping punctuation marks to their frequency ratios.
        """
        punctuation_marks = ['.', '!', '?', ',', ';', ':', '-', '—']
        counts: dict[str, int] = {}

        for mark in punctuation_marks:
            counts[mark] = text.count(mark)

        total = sum(counts.values())

        if total == 0:
            return {".": 1.0}

        return {mark: count / total for mark, count in counts.items() if count > 0}

    def detect_emoji_usage(self, text: str) -> bool:
        """Detect whether emojis are used in the text.

        Args:
            text: The text to analyze.

        Returns:
            True if emojis are present, False otherwise.
        """
        return bool(self.EMOJI_PATTERN.search(text))

    def extract_common_phrases(
        self, texts: list[str], min_occurrences: int = 2
    ) -> list[str]:
        """Extract common phrases that appear across multiple texts.

        Args:
            texts: List of text samples.
            min_occurrences: Minimum times a phrase must appear.

        Returns:
            List of common phrases.
        """
        # Extract 2-4 word phrases
        all_phrases: list[str] = []

        for text in texts:
            words = text.split()
            for n in range(2, 5):  # 2, 3, 4 word phrases
                for i in range(len(words) - n + 1):
                    phrase = " ".join(words[i:i + n])
                    # Clean punctuation from ends
                    phrase = phrase.strip(".,!?;:")
                    if len(phrase) > 3:  # Ignore very short phrases
                        all_phrases.append(phrase.lower())

        # Count occurrences
        phrase_counts = Counter(all_phrases)

        # Return phrases that appear at least min_occurrences times
        common = [
            phrase for phrase, count in phrase_counts.most_common(20)
            if count >= min_occurrences
        ]

        return common[:10]  # Return top 10

    def extract_greeting_style(self, texts: list[str]) -> str:
        """Identify the most common greeting style.

        Args:
            texts: List of text samples (emails, messages).

        Returns:
            Most common greeting (e.g., "Hi", "Dear", "Hey").
        """
        greeting_counts: dict[str, int] = Counter()

        for text in texts:
            first_line = text.strip().split("\n")[0]
            for greeting in self.GREETING_PATTERNS:
                if first_line.lower().startswith(greeting.lower()):
                    greeting_counts[greeting] += 1
                    break

        if not greeting_counts:
            return "Hi"  # Default

        return greeting_counts.most_common(1)[0][0]

    def extract_sign_off_style(self, texts: list[str]) -> str:
        """Identify the most common sign-off style.

        Args:
            texts: List of text samples (emails, messages).

        Returns:
            Most common sign-off (e.g., "Best", "Thanks", "Regards").
        """
        signoff_counts: dict[str, int] = Counter()

        for text in texts:
            lines = text.strip().split("\n")
            # Check last few lines for sign-offs
            for line in lines[-5:]:
                line_clean = line.strip().rstrip(",")
                for signoff in self.SIGNOFF_PATTERNS:
                    if line_clean.lower() == signoff.lower():
                        signoff_counts[signoff] += 1
                        break
                    elif line_clean.lower().startswith(signoff.lower()):
                        signoff_counts[signoff] += 1
                        break

        if not signoff_counts:
            return "Best"  # Default

        return signoff_counts.most_common(1)[0][0]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_digital_twin.py -v -k "text_style_analyzer"`

Expected: PASS (11 tests)

**Step 5: Commit**

```bash
cd backend && git add src/memory/digital_twin.py tests/test_digital_twin.py
git commit -m "$(cat <<'EOF'
feat(memory): add TextStyleAnalyzer for writing style extraction

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Implement DigitalTwin Service Class

**Files:**
- Modify: `backend/src/memory/digital_twin.py`
- Test: `backend/tests/test_digital_twin.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_digital_twin.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


def test_digital_twin_has_required_methods() -> None:
    """Test DigitalTwin class has required interface methods."""
    from src.memory.digital_twin import DigitalTwin

    twin = DigitalTwin()

    # Check required async methods exist
    assert hasattr(twin, "analyze_sample")
    assert hasattr(twin, "get_fingerprint")
    assert hasattr(twin, "get_style_guidelines")
    assert hasattr(twin, "score_style_match")
    assert hasattr(twin, "update_fingerprint")


@pytest.mark.asyncio
async def test_analyze_sample_extracts_style_features() -> None:
    """Test analyze_sample extracts style features from text."""
    from src.memory.digital_twin import DigitalTwin

    twin = DigitalTwin()
    mock_client = MagicMock()
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="graphiti-fp-123"))
    mock_client.search = AsyncMock(return_value=[])

    with patch.object(twin, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        await twin.analyze_sample(
            user_id="user-123",
            text="Hi there! How are you doing today? Looking forward to catching up soon.",
            text_type="email",
        )

        mock_client.add_episode.assert_called_once()


@pytest.mark.asyncio
async def test_get_fingerprint_retrieves_by_user_id() -> None:
    """Test get_fingerprint retrieves fingerprint for user."""
    from src.memory.digital_twin import DigitalTwin

    twin = DigitalTwin()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    mock_edge = MagicMock()
    mock_edge.fact = (
        f"average_sentence_length: 12.0\n"
        f"vocabulary_level: moderate\n"
        f"formality_score: 0.6\n"
        f"common_phrases: best regards, looking forward\n"
        f"greeting_style: Hi\n"
        f"sign_off_style: Best\n"
        f"emoji_usage: False\n"
        f"punctuation_patterns: .=0.7,!=0.2,?=0.1\n"
        f"samples_analyzed: 10\n"
        f"confidence: 0.8\n"
        f"created_at: {now.isoformat()}\n"
        f"updated_at: {now.isoformat()}"
    )
    mock_edge.uuid = "fp-123"
    mock_edge.created_at = now

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(twin, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        fingerprint = await twin.get_fingerprint(user_id="user-123")

        assert fingerprint is not None
        assert fingerprint.user_id == "user-123"
        mock_client.search.assert_called_once()


@pytest.mark.asyncio
async def test_get_fingerprint_returns_none_when_not_found() -> None:
    """Test get_fingerprint returns None when no fingerprint exists."""
    from src.memory.digital_twin import DigitalTwin

    twin = DigitalTwin()
    mock_client = MagicMock()
    mock_client.search = AsyncMock(return_value=[])

    with patch.object(twin, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        fingerprint = await twin.get_fingerprint(user_id="user-123")

        assert fingerprint is None


@pytest.mark.asyncio
async def test_get_style_guidelines_returns_prompt_instructions() -> None:
    """Test get_style_guidelines returns prompt-ready instructions."""
    from src.memory.digital_twin import DigitalTwin, WritingStyleFingerprint

    twin = DigitalTwin()
    now = datetime.now(UTC)

    fingerprint = WritingStyleFingerprint(
        id="fp-123",
        user_id="user-123",
        average_sentence_length=15.0,
        vocabulary_level="moderate",
        formality_score=0.7,
        common_phrases=["looking forward", "best regards"],
        greeting_style="Hi",
        sign_off_style="Best",
        emoji_usage=False,
        punctuation_patterns={".": 0.6, "!": 0.2, "?": 0.2},
        samples_analyzed=20,
        confidence=0.85,
        created_at=now,
        updated_at=now,
    )

    with patch.object(twin, "get_fingerprint", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = fingerprint

        guidelines = await twin.get_style_guidelines(user_id="user-123")

        assert isinstance(guidelines, str)
        assert "Hi" in guidelines  # Greeting style
        assert "Best" in guidelines  # Sign-off style
        assert "moderate" in guidelines.lower()  # Vocabulary level
        assert len(guidelines) > 50  # Should be substantial


@pytest.mark.asyncio
async def test_get_style_guidelines_returns_default_when_no_fingerprint() -> None:
    """Test get_style_guidelines returns default when no fingerprint exists."""
    from src.memory.digital_twin import DigitalTwin

    twin = DigitalTwin()

    with patch.object(twin, "get_fingerprint", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        guidelines = await twin.get_style_guidelines(user_id="user-123")

        assert isinstance(guidelines, str)
        assert "professional" in guidelines.lower() or "clear" in guidelines.lower()


@pytest.mark.asyncio
async def test_score_style_match_returns_score() -> None:
    """Test score_style_match returns similarity score."""
    from src.memory.digital_twin import DigitalTwin, WritingStyleFingerprint

    twin = DigitalTwin()
    now = datetime.now(UTC)

    fingerprint = WritingStyleFingerprint(
        id="fp-123",
        user_id="user-123",
        average_sentence_length=12.0,
        vocabulary_level="simple",
        formality_score=0.4,
        common_phrases=["thanks", "let me know"],
        greeting_style="Hey",
        sign_off_style="Thanks",
        emoji_usage=True,
        punctuation_patterns={".": 0.5, "!": 0.3, "?": 0.2},
        samples_analyzed=15,
        confidence=0.8,
        created_at=now,
        updated_at=now,
    )

    with patch.object(twin, "get_fingerprint", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = fingerprint

        # Text that matches the informal style
        matching_text = "Hey! Thanks for the update. Let me know if you need anything! 😊"
        score = await twin.score_style_match(user_id="user-123", generated_text=matching_text)

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Should be a decent match


@pytest.mark.asyncio
async def test_score_style_match_returns_zero_when_no_fingerprint() -> None:
    """Test score_style_match returns 0 when no fingerprint exists."""
    from src.memory.digital_twin import DigitalTwin

    twin = DigitalTwin()

    with patch.object(twin, "get_fingerprint", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        score = await twin.score_style_match(
            user_id="user-123",
            generated_text="Some text here.",
        )

        assert score == 0.0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_digital_twin.py::test_digital_twin_has_required_methods -v`

Expected: FAIL with "cannot import name 'DigitalTwin'"

**Step 3: Write minimal implementation**

Add to `backend/src/memory/digital_twin.py` (after TextStyleAnalyzer class):

```python
import uuid as uuid_module
from typing import TYPE_CHECKING

from src.core.exceptions import DigitalTwinError

if TYPE_CHECKING:
    from graphiti_core import Graphiti


class DigitalTwin:
    """Service for managing user digital twins and writing style fingerprints.

    Provides async methods for:
    - Analyzing text samples to build/update fingerprints
    - Retrieving fingerprints for users
    - Generating style guidelines for LLM prompts
    - Scoring how well generated text matches a user's style
    """

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

    def _build_fingerprint_body(self, fingerprint: WritingStyleFingerprint) -> str:
        """Build a structured fingerprint body string for storage.

        Args:
            fingerprint: The fingerprint to serialize.

        Returns:
            Structured text representation.
        """
        punct_str = ",".join(
            f"{k}={v:.2f}" for k, v in fingerprint.punctuation_patterns.items()
        )
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
            content = getattr(edge, "fact", "")
            edge_uuid = getattr(edge, "uuid", None) or str(uuid_module.uuid4())
            created_at = getattr(edge, "created_at", datetime.now(UTC))

            lines = content.split("\n")
            data: dict[str, Any] = {}

            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    data[key.strip()] = value.strip()

            # Parse punctuation patterns
            punct_patterns: dict[str, float] = {}
            if "punctuation_patterns" in data:
                for item in data["punctuation_patterns"].split(","):
                    if "=" in item:
                        mark, ratio = item.split("=")
                        punct_patterns[mark.strip()] = float(ratio.strip())

            # Parse common phrases
            phrases = []
            if "common_phrases" in data and data["common_phrases"]:
                phrases = [p.strip() for p in data["common_phrases"].split(",")]

            # Parse timestamps
            fp_created = created_at
            if "created_at" in data:
                fp_created = datetime.fromisoformat(data["created_at"])

            fp_updated = datetime.now(UTC)
            if "updated_at" in data:
                fp_updated = datetime.fromisoformat(data["updated_at"])

            return WritingStyleFingerprint(
                id=edge_uuid,
                user_id=user_id,
                average_sentence_length=float(data.get("average_sentence_length", 15.0)),
                vocabulary_level=data.get("vocabulary_level", "moderate"),
                formality_score=float(data.get("formality_score", 0.5)),
                common_phrases=phrases,
                greeting_style=data.get("greeting_style", "Hi"),
                sign_off_style=data.get("sign_off_style", "Best"),
                emoji_usage=data.get("emoji_usage", "False").lower() == "true",
                punctuation_patterns=punct_patterns or {".": 1.0},
                samples_analyzed=int(data.get("samples_analyzed", 0)),
                confidence=float(data.get("confidence", 0.5)),
                created_at=fp_created,
                updated_at=fp_updated,
            )
        except Exception as e:
            logger.warning(f"Failed to parse fingerprint from edge: {e}")
            return None

    async def analyze_sample(
        self,
        user_id: str,
        text: str,
        text_type: str,
    ) -> None:
        """Analyze a text sample and update the user's fingerprint.

        Args:
            user_id: The user whose fingerprint to update.
            text: The text sample to analyze.
            text_type: Type of text (email, message, document).

        Raises:
            DigitalTwinError: If analysis or storage fails.
        """
        try:
            # Get existing fingerprint or create new
            existing = await self.get_fingerprint(user_id)

            # Extract features from new sample
            sentence_length = self._analyzer.extract_sentence_length(text)
            vocab_level = self._analyzer.extract_vocabulary_level(text)
            formality = self._analyzer.extract_formality_score(text)
            punctuation = self._analyzer.extract_punctuation_patterns(text)
            emoji = self._analyzer.detect_emoji_usage(text)

            now = datetime.now(UTC)

            if existing:
                # Incremental update: weighted average with existing
                n = existing.samples_analyzed
                new_n = n + 1

                # Weighted average for numeric values
                new_sentence_length = (
                    existing.average_sentence_length * n + sentence_length
                ) / new_n
                new_formality = (existing.formality_score * n + formality) / new_n

                # Update fingerprint
                fingerprint = WritingStyleFingerprint(
                    id=existing.id,
                    user_id=user_id,
                    average_sentence_length=new_sentence_length,
                    vocabulary_level=vocab_level,  # Use latest
                    formality_score=new_formality,
                    common_phrases=existing.common_phrases,  # Keep existing
                    greeting_style=existing.greeting_style,
                    sign_off_style=existing.sign_off_style,
                    emoji_usage=emoji or existing.emoji_usage,
                    punctuation_patterns=punctuation,  # Use latest
                    samples_analyzed=new_n,
                    confidence=min(0.95, 0.5 + (new_n * 0.02)),  # Increase with samples
                    created_at=existing.created_at,
                    updated_at=now,
                )
            else:
                # Create new fingerprint
                fingerprint = WritingStyleFingerprint(
                    id=str(uuid_module.uuid4()),
                    user_id=user_id,
                    average_sentence_length=sentence_length,
                    vocabulary_level=vocab_level,
                    formality_score=formality,
                    common_phrases=[],
                    greeting_style="Hi",
                    sign_off_style="Best",
                    emoji_usage=emoji,
                    punctuation_patterns=punctuation,
                    samples_analyzed=1,
                    confidence=0.5,
                    created_at=now,
                    updated_at=now,
                )

            # Store in Graphiti
            client = await self._get_graphiti_client()
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
                "Updated fingerprint",
                extra={
                    "user_id": user_id,
                    "samples_analyzed": fingerprint.samples_analyzed,
                    "confidence": fingerprint.confidence,
                },
            )

        except DigitalTwinError:
            raise
        except Exception as e:
            logger.exception("Failed to analyze sample", extra={"user_id": user_id})
            raise DigitalTwinError(f"Failed to analyze sample: {e}") from e

    async def get_fingerprint(self, user_id: str) -> WritingStyleFingerprint | None:
        """Retrieve the writing style fingerprint for a user.

        Args:
            user_id: The user ID.

        Returns:
            The fingerprint if found, None otherwise.

        Raises:
            DigitalTwinError: If retrieval fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Search for fingerprint by user
            query = f"writing style fingerprint for user {user_id}"
            results = await client.search(query)

            for edge in results:
                fingerprint = self._parse_fingerprint_from_edge(edge, user_id)
                if fingerprint:
                    return fingerprint

            return None

        except DigitalTwinError:
            raise
        except Exception as e:
            logger.exception("Failed to get fingerprint", extra={"user_id": user_id})
            raise DigitalTwinError(f"Failed to get fingerprint: {e}") from e

    async def get_style_guidelines(self, user_id: str) -> str:
        """Get prompt-ready style guidelines for a user.

        Args:
            user_id: The user ID.

        Returns:
            Style guidelines string for use in LLM prompts.
        """
        fingerprint = await self.get_fingerprint(user_id)

        if not fingerprint:
            return (
                "Write in a professional, clear style. Use moderate sentence lengths "
                "and standard business language. Be concise and direct."
            )

        # Build style guidelines
        formality_desc = (
            "formal" if fingerprint.formality_score > 0.7
            else "informal" if fingerprint.formality_score < 0.3
            else "moderately formal"
        )

        emoji_desc = "Use emojis sparingly." if fingerprint.emoji_usage else "Avoid emojis."

        guidelines = f"""Write in this person's style:
- Use {formality_desc} language
- Average sentence length: approximately {fingerprint.average_sentence_length:.0f} words
- Vocabulary level: {fingerprint.vocabulary_level}
- Start messages with "{fingerprint.greeting_style}"
- End messages with "{fingerprint.sign_off_style}"
- {emoji_desc}"""

        if fingerprint.common_phrases:
            phrases = ", ".join(fingerprint.common_phrases[:5])
            guidelines += f"\n- Use phrases like: {phrases}"

        return guidelines

    async def score_style_match(
        self,
        user_id: str,
        generated_text: str,
    ) -> float:
        """Score how well generated text matches the user's writing style.

        Args:
            user_id: The user ID.
            generated_text: The text to score.

        Returns:
            Match score from 0.0 (no match) to 1.0 (perfect match).
        """
        fingerprint = await self.get_fingerprint(user_id)

        if not fingerprint:
            return 0.0

        # Extract features from generated text
        gen_sentence_length = self._analyzer.extract_sentence_length(generated_text)
        gen_vocab = self._analyzer.extract_vocabulary_level(generated_text)
        gen_formality = self._analyzer.extract_formality_score(generated_text)
        gen_emoji = self._analyzer.detect_emoji_usage(generated_text)

        # Calculate similarity scores for each feature
        scores: list[float] = []

        # Sentence length similarity (within 30% is good)
        if fingerprint.average_sentence_length > 0:
            length_ratio = gen_sentence_length / fingerprint.average_sentence_length
            length_score = 1.0 - min(1.0, abs(1.0 - length_ratio))
            scores.append(length_score)

        # Vocabulary level match (exact match = 1.0, otherwise 0.5)
        vocab_score = 1.0 if gen_vocab == fingerprint.vocabulary_level else 0.5
        scores.append(vocab_score)

        # Formality score similarity
        formality_diff = abs(gen_formality - fingerprint.formality_score)
        formality_score = 1.0 - formality_diff
        scores.append(formality_score)

        # Emoji usage match
        emoji_score = 1.0 if gen_emoji == fingerprint.emoji_usage else 0.5
        scores.append(emoji_score)

        # Average all scores
        return sum(scores) / len(scores) if scores else 0.0

    async def update_fingerprint(
        self,
        user_id: str,
        texts: list[str],
        text_type: str = "email",
    ) -> WritingStyleFingerprint:
        """Batch update fingerprint from multiple text samples.

        Extracts common phrases, greeting/sign-off styles from the full batch.

        Args:
            user_id: The user ID.
            texts: List of text samples.
            text_type: Type of texts (email, message, document).

        Returns:
            Updated fingerprint.

        Raises:
            DigitalTwinError: If update fails.
        """
        try:
            # Analyze all samples
            for text in texts:
                await self.analyze_sample(user_id, text, text_type)

            # Extract batch-level features
            common_phrases = self._analyzer.extract_common_phrases(texts)
            greeting = self._analyzer.extract_greeting_style(texts)
            signoff = self._analyzer.extract_sign_off_style(texts)

            # Get current fingerprint and update with batch features
            fingerprint = await self.get_fingerprint(user_id)

            if fingerprint:
                now = datetime.now(UTC)
                updated = WritingStyleFingerprint(
                    id=fingerprint.id,
                    user_id=user_id,
                    average_sentence_length=fingerprint.average_sentence_length,
                    vocabulary_level=fingerprint.vocabulary_level,
                    formality_score=fingerprint.formality_score,
                    common_phrases=common_phrases,
                    greeting_style=greeting,
                    sign_off_style=signoff,
                    emoji_usage=fingerprint.emoji_usage,
                    punctuation_patterns=fingerprint.punctuation_patterns,
                    samples_analyzed=fingerprint.samples_analyzed,
                    confidence=fingerprint.confidence,
                    created_at=fingerprint.created_at,
                    updated_at=now,
                )

                # Store updated fingerprint
                client = await self._get_graphiti_client()
                fingerprint_body = self._build_fingerprint_body(updated)

                from graphiti_core.nodes import EpisodeType

                await client.add_episode(
                    name=f"fingerprint:{user_id}",
                    episode_body=fingerprint_body,
                    source=EpisodeType.text,
                    source_description=f"digital_twin:{user_id}:batch",
                    reference_time=now,
                )

                return updated

            raise DigitalTwinError("No fingerprint found after batch analysis")

        except DigitalTwinError:
            raise
        except Exception as e:
            logger.exception("Failed to update fingerprint", extra={"user_id": user_id})
            raise DigitalTwinError(f"Failed to update fingerprint: {e}") from e
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_digital_twin.py -v`

Expected: PASS (all tests)

**Step 5: Run quality gates**

Run: `cd backend && mypy src/memory/digital_twin.py --strict && ruff check src/memory/digital_twin.py`

Expected: PASS

**Step 6: Commit**

```bash
cd backend && git add src/memory/digital_twin.py tests/test_digital_twin.py
git commit -m "$(cat <<'EOF'
feat(memory): add DigitalTwin service for writing style analysis

Implements US-209 Digital Twin Foundation with:
- analyze_sample: Extract style features from text
- get_fingerprint: Retrieve user's writing style fingerprint
- get_style_guidelines: Generate LLM prompt instructions
- score_style_match: Evaluate generated text against user style
- update_fingerprint: Batch update from multiple samples

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Export DigitalTwin from Memory Module

**Files:**
- Modify: `backend/src/memory/__init__.py`

**Step 1: Write the failing test**

Add test to verify exports (can be done inline):

Run: `cd backend && python -c "from src.memory import DigitalTwin, WritingStyleFingerprint; print('OK')"`

Expected: FAIL with ImportError

**Step 2: Modify the exports**

Update `backend/src/memory/__init__.py`:

```python
"""Six-type memory system for ARIA.

This module implements ARIA's cognitive memory architecture:
- Working: Current conversation context (in-memory, session only)
- Episodic: Past events and interactions (Graphiti)
- Semantic: Facts and knowledge (Graphiti + pgvector)
- Procedural: Learned workflows (Supabase)
- Prospective: Future tasks/reminders (Supabase)
- Lead: Sales pursuit tracking (Graphiti + Supabase)
- Digital Twin: User writing style fingerprinting (Graphiti)
"""

from src.memory.digital_twin import (
    DigitalTwin,
    TextStyleAnalyzer,
    WritingStyleFingerprint,
)
from src.memory.episodic import Episode, EpisodicMemory
from src.memory.procedural import ProceduralMemory, Workflow
from src.memory.prospective import (
    ProspectiveMemory,
    ProspectiveTask,
    TaskPriority,
    TaskStatus,
    TriggerType,
)
from src.memory.semantic import FactSource, SemanticFact, SemanticMemory
from src.memory.working import (
    WorkingMemory,
    WorkingMemoryManager,
    count_tokens,
)

__all__ = [
    # Working Memory
    "WorkingMemory",
    "WorkingMemoryManager",
    "count_tokens",
    # Episodic Memory
    "Episode",
    "EpisodicMemory",
    # Semantic Memory
    "FactSource",
    "SemanticFact",
    "SemanticMemory",
    # Procedural Memory
    "ProceduralMemory",
    "Workflow",
    # Prospective Memory
    "ProspectiveMemory",
    "ProspectiveTask",
    "TriggerType",
    "TaskStatus",
    "TaskPriority",
    # Digital Twin
    "DigitalTwin",
    "WritingStyleFingerprint",
    "TextStyleAnalyzer",
]
```

**Step 3: Verify the import works**

Run: `cd backend && python -c "from src.memory import DigitalTwin, WritingStyleFingerprint; print('OK')"`

Expected: "OK"

**Step 4: Commit**

```bash
cd backend && git add src/memory/__init__.py
git commit -m "$(cat <<'EOF'
feat(memory): export DigitalTwin classes from memory module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add API Route for Digital Twin Fingerprint

**Files:**
- Modify: `backend/src/api/routes/memory.py`
- Test: `backend/tests/api/routes/test_memory_routes.py` (create if not exists)

**Step 1: Write the failing test**

Create `backend/tests/api/routes/test_memory_routes.py` (if not exists) or add:

```python
"""Tests for memory API routes."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes.memory import router


@pytest.fixture
def app() -> FastAPI:
    """Create test FastAPI app."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "user-123"
    return user


def test_get_fingerprint_returns_fingerprint(
    client: TestClient, mock_current_user: MagicMock
) -> None:
    """Test GET /fingerprint returns user's fingerprint."""
    from src.memory.digital_twin import WritingStyleFingerprint

    now = datetime.now(UTC)
    fingerprint = WritingStyleFingerprint(
        id="fp-123",
        user_id="user-123",
        average_sentence_length=15.0,
        vocabulary_level="moderate",
        formality_score=0.7,
        common_phrases=["best regards"],
        greeting_style="Hi",
        sign_off_style="Best",
        emoji_usage=False,
        punctuation_patterns={".": 0.8, "!": 0.2},
        samples_analyzed=10,
        confidence=0.8,
        created_at=now,
        updated_at=now,
    )

    with patch("src.api.routes.memory.get_current_user", return_value=mock_current_user):
        with patch("src.api.routes.memory.DigitalTwin") as mock_twin_class:
            mock_twin = MagicMock()
            mock_twin.get_fingerprint = AsyncMock(return_value=fingerprint)
            mock_twin_class.return_value = mock_twin

            response = client.get("/api/v1/memory/fingerprint")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "fp-123"
            assert data["vocabulary_level"] == "moderate"
            assert data["formality_score"] == 0.7


def test_get_fingerprint_returns_404_when_not_found(
    client: TestClient, mock_current_user: MagicMock
) -> None:
    """Test GET /fingerprint returns 404 when no fingerprint exists."""
    with patch("src.api.routes.memory.get_current_user", return_value=mock_current_user):
        with patch("src.api.routes.memory.DigitalTwin") as mock_twin_class:
            mock_twin = MagicMock()
            mock_twin.get_fingerprint = AsyncMock(return_value=None)
            mock_twin_class.return_value = mock_twin

            response = client.get("/api/v1/memory/fingerprint")

            assert response.status_code == 404


def test_post_analyze_sample_stores_sample(
    client: TestClient, mock_current_user: MagicMock
) -> None:
    """Test POST /fingerprint/analyze stores and analyzes sample."""
    with patch("src.api.routes.memory.get_current_user", return_value=mock_current_user):
        with patch("src.api.routes.memory.DigitalTwin") as mock_twin_class:
            mock_twin = MagicMock()
            mock_twin.analyze_sample = AsyncMock()
            mock_twin_class.return_value = mock_twin

            response = client.post(
                "/api/v1/memory/fingerprint/analyze",
                json={
                    "text": "Hi there! Looking forward to connecting.",
                    "text_type": "email",
                },
            )

            assert response.status_code == 200
            mock_twin.analyze_sample.assert_called_once()


def test_get_style_guidelines_returns_guidelines(
    client: TestClient, mock_current_user: MagicMock
) -> None:
    """Test GET /fingerprint/guidelines returns style guidelines."""
    with patch("src.api.routes.memory.get_current_user", return_value=mock_current_user):
        with patch("src.api.routes.memory.DigitalTwin") as mock_twin_class:
            mock_twin = MagicMock()
            mock_twin.get_style_guidelines = AsyncMock(
                return_value="Write in a professional style..."
            )
            mock_twin_class.return_value = mock_twin

            response = client.get("/api/v1/memory/fingerprint/guidelines")

            assert response.status_code == 200
            data = response.json()
            assert "guidelines" in data
            assert len(data["guidelines"]) > 0


def test_post_score_style_match_returns_score(
    client: TestClient, mock_current_user: MagicMock
) -> None:
    """Test POST /fingerprint/score returns style match score."""
    with patch("src.api.routes.memory.get_current_user", return_value=mock_current_user):
        with patch("src.api.routes.memory.DigitalTwin") as mock_twin_class:
            mock_twin = MagicMock()
            mock_twin.score_style_match = AsyncMock(return_value=0.85)
            mock_twin_class.return_value = mock_twin

            response = client.post(
                "/api/v1/memory/fingerprint/score",
                json={"text": "Hi! Thanks for reaching out."},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["score"] == 0.85
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/routes/test_memory_routes.py -v`

Expected: FAIL (endpoints don't exist yet)

**Step 3: Add API routes**

Add to `backend/src/api/routes/memory.py` (after existing imports):

```python
from src.memory.digital_twin import DigitalTwin, WritingStyleFingerprint
from src.core.exceptions import DigitalTwinError
```

Add request/response models (after existing models):

```python
# Digital Twin Models
class FingerprintResponse(BaseModel):
    """Response body for fingerprint retrieval."""

    id: str
    user_id: str
    average_sentence_length: float
    vocabulary_level: str
    formality_score: float = Field(..., ge=0.0, le=1.0)
    common_phrases: list[str]
    greeting_style: str
    sign_off_style: str
    emoji_usage: bool
    punctuation_patterns: dict[str, float]
    samples_analyzed: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime


class AnalyzeSampleRequest(BaseModel):
    """Request body for analyzing a text sample."""

    text: str = Field(..., min_length=10, description="Text sample to analyze")
    text_type: Literal["email", "message", "document"] = Field(
        "email", description="Type of text"
    )


class AnalyzeSampleResponse(BaseModel):
    """Response body for sample analysis."""

    message: str = "Sample analyzed successfully"


class StyleGuidelinesResponse(BaseModel):
    """Response body for style guidelines."""

    guidelines: str


class ScoreStyleMatchRequest(BaseModel):
    """Request body for scoring style match."""

    text: str = Field(..., min_length=1, description="Text to score")


class ScoreStyleMatchResponse(BaseModel):
    """Response body for style match score."""

    score: float = Field(..., ge=0.0, le=1.0)
```

Add endpoints (after existing endpoints):

```python
# Digital Twin Endpoints


@router.get("/fingerprint", response_model=FingerprintResponse)
async def get_fingerprint(
    current_user: CurrentUser,
) -> FingerprintResponse:
    """Get the user's writing style fingerprint.

    Retrieves the accumulated writing style fingerprint for the current user,
    built from analyzed text samples.

    Args:
        current_user: Authenticated user.

    Returns:
        User's writing style fingerprint.

    Raises:
        HTTPException: 404 if no fingerprint exists.
    """
    twin = DigitalTwin()
    try:
        fingerprint = await twin.get_fingerprint(user_id=current_user.id)
    except DigitalTwinError as e:
        logger.error(
            "Failed to get fingerprint",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Digital twin service unavailable") from None

    if fingerprint is None:
        raise HTTPException(status_code=404, detail="No fingerprint found for user")

    return FingerprintResponse(
        id=fingerprint.id,
        user_id=fingerprint.user_id,
        average_sentence_length=fingerprint.average_sentence_length,
        vocabulary_level=fingerprint.vocabulary_level,
        formality_score=fingerprint.formality_score,
        common_phrases=fingerprint.common_phrases,
        greeting_style=fingerprint.greeting_style,
        sign_off_style=fingerprint.sign_off_style,
        emoji_usage=fingerprint.emoji_usage,
        punctuation_patterns=fingerprint.punctuation_patterns,
        samples_analyzed=fingerprint.samples_analyzed,
        confidence=fingerprint.confidence,
        created_at=fingerprint.created_at,
        updated_at=fingerprint.updated_at,
    )


@router.post("/fingerprint/analyze", response_model=AnalyzeSampleResponse)
async def analyze_sample(
    current_user: CurrentUser,
    request: AnalyzeSampleRequest,
) -> AnalyzeSampleResponse:
    """Analyze a text sample to update the user's writing style fingerprint.

    Extracts writing style features from the provided text and updates
    the user's fingerprint with an incremental weighted average.

    Args:
        current_user: Authenticated user.
        request: Analysis request with text sample.

    Returns:
        Success confirmation.
    """
    twin = DigitalTwin()
    try:
        await twin.analyze_sample(
            user_id=current_user.id,
            text=request.text,
            text_type=request.text_type,
        )
    except DigitalTwinError as e:
        logger.error(
            "Failed to analyze sample",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Digital twin service unavailable") from None

    logger.info(
        "Analyzed text sample",
        extra={
            "user_id": current_user.id,
            "text_type": request.text_type,
            "text_length": len(request.text),
        },
    )

    return AnalyzeSampleResponse()


@router.get("/fingerprint/guidelines", response_model=StyleGuidelinesResponse)
async def get_style_guidelines(
    current_user: CurrentUser,
) -> StyleGuidelinesResponse:
    """Get style guidelines for generating text in the user's voice.

    Returns prompt-ready instructions that can be used with an LLM
    to generate text matching the user's writing style.

    Args:
        current_user: Authenticated user.

    Returns:
        Style guidelines string.
    """
    twin = DigitalTwin()
    try:
        guidelines = await twin.get_style_guidelines(user_id=current_user.id)
    except DigitalTwinError as e:
        logger.error(
            "Failed to get style guidelines",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Digital twin service unavailable") from None

    return StyleGuidelinesResponse(guidelines=guidelines)


@router.post("/fingerprint/score", response_model=ScoreStyleMatchResponse)
async def score_style_match(
    current_user: CurrentUser,
    request: ScoreStyleMatchRequest,
) -> ScoreStyleMatchResponse:
    """Score how well text matches the user's writing style.

    Compares the provided text against the user's fingerprint and
    returns a similarity score from 0.0 to 1.0.

    Args:
        current_user: Authenticated user.
        request: Score request with text to evaluate.

    Returns:
        Style match score.
    """
    twin = DigitalTwin()
    try:
        score = await twin.score_style_match(
            user_id=current_user.id,
            generated_text=request.text,
        )
    except DigitalTwinError as e:
        logger.error(
            "Failed to score style match",
            extra={"error": str(e), "user_id": current_user.id},
        )
        raise HTTPException(status_code=503, detail="Digital twin service unavailable") from None

    return ScoreStyleMatchResponse(score=score)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/api/routes/test_memory_routes.py -v`

Expected: PASS (all tests)

**Step 5: Run full quality gates**

Run: `cd backend && pytest tests/ -v && mypy src/ --strict && ruff check src/`

Expected: PASS

**Step 6: Commit**

```bash
cd backend && git add src/api/routes/memory.py tests/api/routes/test_memory_routes.py
git commit -m "$(cat <<'EOF'
feat(api): add Digital Twin fingerprint endpoints

Adds REST API endpoints for Digital Twin functionality:
- GET /memory/fingerprint - Retrieve user's writing style fingerprint
- POST /memory/fingerprint/analyze - Analyze text sample
- GET /memory/fingerprint/guidelines - Get LLM style instructions
- POST /memory/fingerprint/score - Score text against user style

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Run Full Quality Gates and Final Verification

**Step 1: Run all backend tests**

Run: `cd backend && pytest tests/ -v`

Expected: All tests PASS

**Step 2: Run type checking**

Run: `cd backend && mypy src/ --strict`

Expected: No errors

**Step 3: Run linting**

Run: `cd backend && ruff check src/`

Expected: No errors

**Step 4: Run formatting check**

Run: `cd backend && ruff format src/ --check`

Expected: No errors (or run `ruff format src/` to fix)

**Step 5: Verify US-209 acceptance criteria**

Checklist:
- [x] `src/memory/digital_twin.py` created
- [x] Captures: writing style, vocabulary, tone preferences
- [x] Extracts patterns from user's emails/messages
- [x] Stores fingerprint in semantic memory (Graphiti)
- [x] Method to get style guidelines for a user
- [x] Method to score style match of generated text
- [x] Updates incrementally with new samples
- [x] Unit tests for fingerprint extraction

**Step 6: Final commit (if any formatting changes)**

```bash
cd backend && git add -A
git commit -m "$(cat <<'EOF'
chore: format and final cleanup for US-209

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This plan implements US-209: Digital Twin Foundation with the following components:

1. **Exceptions** - `DigitalTwinError` and `FingerprintNotFoundError`
2. **WritingStyleFingerprint** - Dataclass capturing all writing style metrics
3. **TextStyleAnalyzer** - Utility class for extracting style features from text
4. **DigitalTwin** - Service class for managing fingerprints and style analysis
5. **API Endpoints** - REST API for fingerprint CRUD and style operations

The implementation follows existing patterns in the codebase:
- Dataclass with `to_dict()`/`from_dict()` methods
- Service class with async methods and Graphiti storage
- Structured logging with extra context
- Pydantic models for request/response validation
- Comprehensive unit tests with mocking

Total estimated tasks: 7
Testing approach: TDD with pytest and AsyncMock
Storage: Graphiti (Neo4j) for temporal queries
