"""Tests for digital twin module."""

import json
from datetime import UTC, datetime


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
