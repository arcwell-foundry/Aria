"""Tests for enhanced Digital Twin (US-808).

Tests the writing style API endpoint that exposes the user's
digital twin fingerprint for viewing and style-matched content generation.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import CurrentUser, get_current_user
from src.main import app
from src.memory.digital_twin import WritingStyleFingerprint


@pytest.fixture
def mock_user() -> MagicMock:
    """Create a mock current user."""
    user = MagicMock(spec=CurrentUser)
    user.id = "test-user-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def client(mock_user: MagicMock) -> TestClient:
    """Create a test client with authentication override."""

    async def override_get_current_user() -> MagicMock:
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    test_client = TestClient(app, raise_server_exceptions=False)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_fingerprint() -> WritingStyleFingerprint:
    """Create a mock writing style fingerprint for testing."""
    return WritingStyleFingerprint(
        id="test-fp-id",
        user_id="test-user-123",
        average_sentence_length=15.5,
        vocabulary_level="moderate",
        formality_score=0.65,
        common_phrases=["follow up", "best regards", "as discussed"],
        greeting_style="Hi",
        sign_off_style="Best",
        emoji_usage=False,
        punctuation_patterns={".": 0.6, ",": 0.3, "!": 0.1},
        samples_analyzed=10,
        confidence=0.85,
        created_at=datetime(2026, 2, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2026, 2, 15, 9, 30, 0, tzinfo=UTC),
    )


@pytest.fixture
def mock_style_guidelines() -> str:
    """Create mock style guidelines for testing."""
    return (
        "Start messages with greetings like 'Hi'.\n"
        "End messages with sign-offs like 'Best'.\n"
        "Use moderate vocabulary - neither too simple nor too complex.\n"
        "Use a balanced, semi-formal tone.\n"
        "Use medium-length sentences.\n"
        "Do not use emojis.\n"
        "Consider using phrases like: 'follow up', 'best regards', 'as discussed'."
    )


class TestWritingStyleEndpoint:
    """Tests for GET /api/v1/user/writing-style."""

    def test_returns_writing_style_profile(
        self,
        client: TestClient,
        mock_user: MagicMock,  # noqa: ARG002
        mock_fingerprint: WritingStyleFingerprint,
        mock_style_guidelines: str,
    ) -> None:
        """Endpoint returns user's writing style fingerprint."""
        with (
            patch(
                "src.api.routes.companion.DigitalTwin.get_fingerprint",
                new_callable=AsyncMock,
            ) as mock_get_fp,
            patch(
                "src.api.routes.companion.DigitalTwin.get_style_guidelines",
                new_callable=AsyncMock,
            ) as mock_get_guidelines,
        ):
            mock_get_fp.return_value = mock_fingerprint
            mock_get_guidelines.return_value = mock_style_guidelines

            response = client.get("/api/v1/user/writing-style")

            assert response.status_code == 200
            data = response.json()

            assert data["average_sentence_length"] == 15.5
            assert data["vocabulary_level"] == "moderate"
            assert data["formality_score"] == 0.65
            assert data["common_phrases"] == ["follow up", "best regards", "as discussed"]
            assert data["greeting_style"] == "Hi"
            assert data["sign_off_style"] == "Best"
            assert data["emoji_usage"] is False
            assert data["confidence"] == 0.85
            assert data["samples_analyzed"] == 10
            assert "Start messages with greetings like 'Hi'" in data["style_guidelines"]
            # Accept either +00:00 or Z suffix for UTC datetime
            assert data["created_at"] in ["2026-02-01T12:00:00+00:00", "2026-02-01T12:00:00Z"]
            assert data["updated_at"] in ["2026-02-15T09:30:00+00:00", "2026-02-15T09:30:00Z"]

    def test_returns_none_when_no_fingerprint(
        self,
        client: TestClient,
        mock_user: MagicMock,  # noqa: ARG002
    ) -> None:
        """Returns None when user has no writing style data."""
        with patch(
            "src.api.routes.companion.DigitalTwin.get_fingerprint",
            new_callable=AsyncMock,
        ) as mock_get_fp:
            mock_get_fp.return_value = None

            response = client.get("/api/v1/user/writing-style")

            assert response.status_code == 200
            assert response.json() is None

    def test_includes_style_guidelines(
        self,
        client: TestClient,
        mock_user: MagicMock,  # noqa: ARG002
        mock_fingerprint: WritingStyleFingerprint,
        mock_style_guidelines: str,
    ) -> None:
        """Response includes prompt-ready style guidelines."""
        with (
            patch(
                "src.api.routes.companion.DigitalTwin.get_fingerprint",
                new_callable=AsyncMock,
            ) as mock_get_fp,
            patch(
                "src.api.routes.companion.DigitalTwin.get_style_guidelines",
                new_callable=AsyncMock,
            ) as mock_get_guidelines,
        ):
            mock_get_fp.return_value = mock_fingerprint
            mock_get_guidelines.return_value = mock_style_guidelines

            response = client.get("/api/v1/user/writing-style")

            assert response.status_code == 200
            guidelines = response.json()["style_guidelines"]

            # Verify guidelines contain expected style instructions
            assert "greetings like 'Hi'" in guidelines
            assert "sign-offs like 'Best'" in guidelines
            assert "moderate vocabulary" in guidelines
            assert "semi-formal tone" in guidelines
            assert "Do not use emojis" in guidelines

    def test_reflects_simple_vocabulary_style(
        self,
        client: TestClient,
        mock_user: MagicMock,  # noqa: ARG002
    ) -> None:
        """Response reflects simple vocabulary level correctly."""
        fingerprint = WritingStyleFingerprint(
            id="test-fp-id",
            user_id="test-user-123",
            average_sentence_length=8.0,
            vocabulary_level="simple",
            formality_score=0.3,
            common_phrases=[],
            greeting_style="Hey",
            sign_off_style="Cheers",
            emoji_usage=True,
            punctuation_patterns={},
            samples_analyzed=5,
            confidence=0.6,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        guidelines = (
            "Start messages with greetings like 'Hey'.\n"
            "End messages with sign-offs like 'Cheers'.\n"
            "Use simple, everyday language.\n"
            "Keep a casual, informal tone.\n"
            "Keep sentences short and punchy.\n"
            "Include relevant emojis when appropriate."
        )

        with (
            patch(
                "src.api.routes.companion.DigitalTwin.get_fingerprint",
                new_callable=AsyncMock,
            ) as mock_get_fp,
            patch(
                "src.api.routes.companion.DigitalTwin.get_style_guidelines",
                new_callable=AsyncMock,
            ) as mock_get_guidelines,
        ):
            mock_get_fp.return_value = fingerprint
            mock_get_guidelines.return_value = guidelines

            response = client.get("/api/v1/user/writing-style")

            assert response.status_code == 200
            data = response.json()

            assert data["vocabulary_level"] == "simple"
            assert data["formality_score"] == 0.3
            assert data["emoji_usage"] is True
            assert data["greeting_style"] == "Hey"
            assert data["sign_off_style"] == "Cheers"
            assert data["average_sentence_length"] == 8.0

    def test_reflects_advanced_formal_style(
        self,
        client: TestClient,
        mock_user: MagicMock,  # noqa: ARG002
    ) -> None:
        """Response reflects advanced vocabulary and formal style correctly."""
        fingerprint = WritingStyleFingerprint(
            id="test-fp-id",
            user_id="test-user-123",
            average_sentence_length=25.0,
            vocabulary_level="advanced",
            formality_score=0.9,
            common_phrases=["pursuant to", "regarding the matter"],
            greeting_style="Dear",
            sign_off_style="Sincerely",
            emoji_usage=False,
            punctuation_patterns={},
            samples_analyzed=20,
            confidence=0.95,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        guidelines = (
            "Start messages with greetings like 'Dear'.\n"
            "End messages with sign-offs like 'Sincerely'.\n"
            "Use sophisticated vocabulary when appropriate.\n"
            "Maintain a formal, professional tone.\n"
            "Use longer, more detailed sentences.\n"
            "Do not use emojis."
        )

        with (
            patch(
                "src.api.routes.companion.DigitalTwin.get_fingerprint",
                new_callable=AsyncMock,
            ) as mock_get_fp,
            patch(
                "src.api.routes.companion.DigitalTwin.get_style_guidelines",
                new_callable=AsyncMock,
            ) as mock_get_guidelines,
        ):
            mock_get_fp.return_value = fingerprint
            mock_get_guidelines.return_value = guidelines

            response = client.get("/api/v1/user/writing-style")

            assert response.status_code == 200
            data = response.json()

            assert data["vocabulary_level"] == "advanced"
            assert data["formality_score"] == 0.9
            assert data["emoji_usage"] is False
            assert data["greeting_style"] == "Dear"
            assert data["sign_off_style"] == "Sincerely"
            assert data["average_sentence_length"] == 25.0
            assert data["confidence"] == 0.95
            assert data["samples_analyzed"] == 20

    def test_requires_authentication(self) -> None:
        """Endpoint requires authentication."""
        # Create a client without auth override
        unauthenticated_client = TestClient(app, raise_server_exceptions=False)
        response = unauthenticated_client.get("/api/v1/user/writing-style")

        # Should return 401 or 403 depending on auth setup
        assert response.status_code in [401, 403, 422]


class TestWritingStyleEndpointIntegration:
    """Integration tests for writing style endpoint with digital twin service."""

    def test_endpoint_calls_digital_twin_service(
        self,
        client: TestClient,
        mock_user: MagicMock,
    ) -> None:
        """Endpoint properly calls the digital twin service methods."""
        fingerprint = WritingStyleFingerprint(
            id="test-fp-id",
            user_id="test-user-123",
            average_sentence_length=12.0,
            vocabulary_level="moderate",
            formality_score=0.5,
            common_phrases=[],
            greeting_style="",
            sign_off_style="",
            emoji_usage=False,
            punctuation_patterns={},
            samples_analyzed=3,
            confidence=0.65,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with (
            patch(
                "src.api.routes.companion.DigitalTwin.get_fingerprint",
                new_callable=AsyncMock,
            ) as mock_get_fp,
            patch(
                "src.api.routes.companion.DigitalTwin.get_style_guidelines",
                new_callable=AsyncMock,
            ) as mock_get_guidelines,
        ):
            mock_get_fp.return_value = fingerprint
            mock_get_guidelines.return_value = "Default guidelines"

            response = client.get("/api/v1/user/writing-style")

            assert response.status_code == 200
            # Verify service methods were called with correct user ID
            mock_get_fp.assert_called_once_with(mock_user.id)
            mock_get_guidelines.assert_called_once_with(mock_user.id)
