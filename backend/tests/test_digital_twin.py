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


# DigitalTwin Service Tests


import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_digital_twin_has_required_methods() -> None:
    """Test DigitalTwin class has required interface methods."""
    from src.memory.digital_twin import DigitalTwin

    twin = DigitalTwin()

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
        assert "Hi" in guidelines
        assert "Best" in guidelines
        assert "moderate" in guidelines.lower()
        assert len(guidelines) > 50


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

        matching_text = "Hey! Thanks for the update. Let me know if you need anything! 😊"
        score = await twin.score_style_match(user_id="user-123", generated_text=matching_text)

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert score > 0.5


@pytest.mark.asyncio
async def test_score_style_match_returns_default_when_no_data() -> None:
    """Test score_style_match returns 0.5 default when no fingerprint or DB data exists."""
    from src.memory.digital_twin import DigitalTwin

    twin = DigitalTwin()

    with (
        patch.object(twin, "get_fingerprint", new_callable=AsyncMock) as mock_get,
        patch.object(twin, "_score_style_match_from_db", new_callable=AsyncMock) as mock_db,
    ):
        mock_get.return_value = None
        mock_db.return_value = None

        score = await twin.score_style_match(
            user_id="user-123",
            generated_text="Some text here.",
        )

        assert score == 0.5


@pytest.mark.asyncio
async def test_update_fingerprint_batch_updates_from_texts() -> None:
    """Test update_fingerprint processes multiple text samples."""
    from src.memory.digital_twin import DigitalTwin, WritingStyleFingerprint

    twin = DigitalTwin()
    now = datetime.now(UTC)

    # Mock the Graphiti client
    mock_client = MagicMock()
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="graphiti-fp-123"))
    mock_client.search = AsyncMock(return_value=[])

    with patch.object(twin, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        texts = [
            "Hi there! Hope you're doing well.",
            "Hi Team, quick update on the project.",
            "Hi everyone, let's discuss the roadmap.",
        ]

        fingerprint = await twin.update_fingerprint(
            user_id="user-123",
            texts=texts,
            text_type="email",
        )

        assert fingerprint is not None
        assert fingerprint.user_id == "user-123"
        assert fingerprint.samples_analyzed == len(texts)
        assert fingerprint.greeting_style == "Hi"
