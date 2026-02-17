"""Tests for ARIA Tavus Persona Manager."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.tavus_persona import (
    ARIA_GUARDRAILS,
    ARIA_PERSONA_LAYERS,
    ARIA_PERSONA_NAME,
    ARIAPersonaManager,
    SessionType,
    get_aria_persona_manager,
)


@pytest.fixture
def persona_manager() -> ARIAPersonaManager:
    """Create an ARIAPersonaManager instance with mocked dependencies.

    Returns:
        ARIAPersonaManager with mocked services.
    """
    manager = ARIAPersonaManager()
    # Mock internal clients
    manager._tavus_client = MagicMock()
    manager._profile_service = MagicMock()
    manager._briefing_service = MagicMock()
    manager._goal_service = MagicMock()
    manager._db = MagicMock()
    return manager


@pytest.fixture
def mock_tavus_client() -> MagicMock:
    """Create a mock TavusClient.

    Returns:
        Mocked TavusClient.
    """
    client = MagicMock()
    client.create_guardrails = AsyncMock(return_value={"guardrails_id": "gr_test123"})
    client.create_persona = AsyncMock(return_value={"persona_id": "persona_test123"})
    client.list_personas = AsyncMock(return_value=[])
    client.delete_persona = AsyncMock(return_value={"deleted": True})
    client.get_persona = AsyncMock(
        return_value={"persona_id": "persona_test123", "persona_name": ARIA_PERSONA_NAME}
    )
    return client


# ====================
# Enum Tests
# ====================


def test_session_type_values() -> None:
    """Test SessionType enum has expected values."""
    assert SessionType.CHAT == "chat"
    assert SessionType.BRIEFING == "briefing"
    assert SessionType.DEBRIEF == "debrief"
    assert SessionType.CONSULTATION == "consultation"


# ====================
# Configuration Tests
# ====================


def test_aria_persona_name() -> None:
    """Test ARIA persona name is defined."""
    assert ARIA_PERSONA_NAME == "ARIA - Life Sciences AI Director"


def test_aria_persona_layers_structure() -> None:
    """Test ARIA persona layers have required keys."""
    assert "perception" in ARIA_PERSONA_LAYERS
    assert "conversational_flow" in ARIA_PERSONA_LAYERS
    assert "stt" in ARIA_PERSONA_LAYERS
    assert "llm" in ARIA_PERSONA_LAYERS
    assert "tts" in ARIA_PERSONA_LAYERS


def test_aria_persona_layers_perception() -> None:
    """Test perception layer configuration."""
    perception = ARIA_PERSONA_LAYERS["perception"]
    assert perception["perception_model"] == "raven-1"
    assert "visual_awareness_queries" in perception
    assert "perception_analysis_queries" in perception
    assert len(perception["visual_awareness_queries"]) > 0
    assert len(perception["perception_analysis_queries"]) > 0


def test_aria_persona_layers_conversational_flow() -> None:
    """Test conversational flow layer configuration."""
    flow = ARIA_PERSONA_LAYERS["conversational_flow"]
    assert flow["turn_detection_model"] == "sparrow-1"
    assert flow["turn_taking_patience"] == "medium"
    assert flow["replica_interruptibility"] == "low"


def test_aria_persona_layers_llm() -> None:
    """Test LLM layer configuration."""
    llm = ARIA_PERSONA_LAYERS["llm"]
    assert llm["model"] == "claude-sonnet-4-5-20250929"
    assert llm["base_url"] == "https://api.anthropic.com/v1"
    assert llm["speculative_inference"] is True


def test_aria_persona_layers_tts() -> None:
    """Test TTS layer configuration."""
    tts = ARIA_PERSONA_LAYERS["tts"]
    assert tts["tts_engine"] == "cartesia"
    assert tts["tts_emotion_control"] is True
    assert "voice_settings" in tts


def test_aria_guardrails_structure() -> None:
    """Test ARIA guardrails have required structure."""
    assert len(ARIA_GUARDRAILS) >= 3

    for guardrail in ARIA_GUARDRAILS:
        assert "type" in guardrail
        assert "action" in guardrail
        assert "response" in guardrail


def test_aria_guardrails_medical_block() -> None:
    """Test medical advice guardrail exists."""
    medical_guardrails = [
        g for g in ARIA_GUARDRAILS if "medical" in str(g.get("topics", [])).lower()
    ]
    assert len(medical_guardrails) >= 1
    assert medical_guardrails[0]["action"] == "block"


def test_aria_guardrails_competitor_block() -> None:
    """Test competitor pricing guardrail exists."""
    competitor_guardrails = [
        g for g in ARIA_GUARDRAILS if "competitor" in str(g.get("topics", [])).lower()
    ]
    assert len(competitor_guardrails) >= 1


# ====================
# Guardrails Creation Tests
# ====================


@pytest.mark.asyncio
async def test_create_aria_guardrails(persona_manager: ARIAPersonaManager) -> None:
    """Test creating ARIA guardrails."""
    mock_client = MagicMock()
    mock_client.create_guardrails = AsyncMock(return_value={"guardrails_id": "gr_new123"})
    persona_manager._tavus_client = mock_client

    result = await persona_manager.create_aria_guardrails()

    assert result["guardrails_id"] == "gr_new123"
    mock_client.create_guardrails.assert_called_once_with(ARIA_GUARDRAILS)


# ====================
# Persona Creation Tests
# ====================


@pytest.mark.asyncio
async def test_create_aria_persona(persona_manager: ARIAPersonaManager) -> None:
    """Test creating ARIA persona."""
    mock_client = MagicMock()
    mock_client.create_persona = AsyncMock(
        return_value={"persona_id": "persona_new123", "persona_name": ARIA_PERSONA_NAME}
    )
    persona_manager._tavus_client = mock_client

    with patch("src.integrations.tavus_persona.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = MagicMock()
        mock_settings.ANTHROPIC_API_KEY.get_secret_value = MagicMock(return_value="test_api_key")

        result = await persona_manager.create_aria_persona(
            guardrails_id="gr_123",
            replica_id="replica_123",
        )

    assert result["persona_id"] == "persona_new123"
    mock_client.create_persona.assert_called_once()

    # Verify call arguments
    call_args = mock_client.create_persona.call_args
    assert call_args.kwargs["persona_name"] == ARIA_PERSONA_NAME
    assert call_args.kwargs["guardrails_id"] == "gr_123"
    assert call_args.kwargs["default_replica_id"] == "replica_123"


# ====================
# Get or Create Tests
# ====================


@pytest.mark.asyncio
async def test_get_or_create_persona_existing(
    persona_manager: ARIAPersonaManager,
) -> None:
    """Test getting existing persona."""
    mock_client = MagicMock()
    mock_client.list_personas = AsyncMock(
        return_value=[
            {
                "persona_id": "existing_123",
                "persona_name": ARIA_PERSONA_NAME,
                "guardrails_id": "gr_existing",
            }
        ]
    )
    persona_manager._tavus_client = mock_client

    result = await persona_manager.get_or_create_persona(replica_id="replica_123")

    assert result["persona_id"] == "existing_123"
    assert result["guardrails_id"] == "gr_existing"
    assert result["created"] is False


@pytest.mark.asyncio
async def test_get_or_create_persona_create_new(
    persona_manager: ARIAPersonaManager,
) -> None:
    """Test creating new persona when none exists."""
    mock_client = MagicMock()
    mock_client.list_personas = AsyncMock(return_value=[])
    mock_client.create_guardrails = AsyncMock(return_value={"guardrails_id": "gr_new"})
    mock_client.create_persona = AsyncMock(
        return_value={"persona_id": "persona_new", "persona_name": ARIA_PERSONA_NAME}
    )
    persona_manager._tavus_client = mock_client

    with patch("src.integrations.tavus_persona.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = MagicMock()
        mock_settings.ANTHROPIC_API_KEY.get_secret_value = MagicMock(return_value="test_key")

        result = await persona_manager.get_or_create_persona(replica_id="replica_123")

    assert result["persona_id"] == "persona_new"
    assert result["guardrails_id"] == "gr_new"
    assert result["created"] is True


@pytest.mark.asyncio
async def test_get_or_create_persona_force_recreate(
    persona_manager: ARIAPersonaManager,
) -> None:
    """Test force recreation of existing persona."""
    mock_client = MagicMock()
    mock_client.list_personas = AsyncMock(
        return_value=[
            {
                "persona_id": "old_123",
                "persona_name": ARIA_PERSONA_NAME,
                "guardrails_id": "gr_old",
            }
        ]
    )
    mock_client.delete_persona = AsyncMock(return_value={"deleted": True})
    mock_client.create_guardrails = AsyncMock(return_value={"guardrails_id": "gr_new"})
    mock_client.create_persona = AsyncMock(
        return_value={"persona_id": "persona_new", "persona_name": ARIA_PERSONA_NAME}
    )
    persona_manager._tavus_client = mock_client

    with patch("src.integrations.tavus_persona.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = MagicMock()
        mock_settings.ANTHROPIC_API_KEY.get_secret_value = MagicMock(return_value="test_key")

        result = await persona_manager.get_or_create_persona(
            replica_id="replica_123",
            force_recreate=True,
        )

    assert result["persona_id"] == "persona_new"
    assert result["created"] is True
    mock_client.delete_persona.assert_called_once_with("old_123")


@pytest.mark.asyncio
async def test_get_or_create_persona_missing_replica(
    persona_manager: ARIAPersonaManager,
) -> None:
    """Test error when replica ID is missing."""
    with patch("src.integrations.tavus_persona.settings") as mock_settings:
        mock_settings.TAVUS_REPLICA_ID = ""

        with pytest.raises(ValueError, match="Replica ID is required"):
            await persona_manager.get_or_create_persona()


# ====================
# Context Building Tests
# ====================


@pytest.mark.asyncio
async def test_build_context_chat(persona_manager: ARIAPersonaManager) -> None:
    """Test building context for chat session."""
    # Mock user context
    persona_manager._get_user_context = AsyncMock(
        return_value="Name: Test User\nTitle: Sales Director"
    )
    # Mock chat context
    persona_manager._get_chat_context = AsyncMock(
        return_value="Active goals: 2\n  - Q1 Pipeline (45%)"
    )
    # Mock recent conversations
    persona_manager._get_recent_conversation_context = AsyncMock(
        return_value="- Discussed Lonza opportunity."
    )

    context = await persona_manager.build_context(
        user_id="user_123",
        session_type=SessionType.CHAT,
    )

    assert "## User Profile" in context
    assert "Test User" in context
    assert "## Current Context" in context
    assert "## Recent Conversations" in context


@pytest.mark.asyncio
async def test_build_context_briefing(persona_manager: ARIAPersonaManager) -> None:
    """Test building context for briefing session."""
    persona_manager._get_user_context = AsyncMock(return_value="Name: Test User")
    persona_manager._get_briefing_context = AsyncMock(
        return_value="Summary: Good morning!\nMeetings today: 3"
    )
    persona_manager._get_recent_conversation_context = AsyncMock(return_value=None)

    context = await persona_manager.build_context(
        user_id="user_123",
        session_type=SessionType.BRIEFING,
    )

    assert "## User Profile" in context
    assert "## Today's Briefing" in context
    assert "Good morning!" in context


@pytest.mark.asyncio
async def test_build_context_debrief(persona_manager: ARIAPersonaManager) -> None:
    """Test building context for debrief session."""
    persona_manager._get_user_context = AsyncMock(return_value="Name: Test User")
    persona_manager._get_debrief_context = AsyncMock(
        return_value="Meeting: Lonza QBR\nAttendees: John, Jane"
    )
    persona_manager._get_recent_conversation_context = AsyncMock(return_value=None)

    context = await persona_manager.build_context(
        user_id="user_123",
        session_type=SessionType.DEBRIEF,
        additional_context={
            "meeting_title": "Lonza QBR",
            "attendees": ["john@lonza.com", "jane@lonza.com"],
        },
    )

    assert "## Meeting Debrief" in context
    assert "Lonza QBR" in context


@pytest.mark.asyncio
async def test_build_context_consultation(persona_manager: ARIAPersonaManager) -> None:
    """Test building context for consultation session."""
    persona_manager._get_user_context = AsyncMock(return_value="Name: Test User")
    persona_manager._get_consultation_context = AsyncMock(
        return_value="Goal: Win Lonza Account\nType: account\nProgress: 35%"
    )
    persona_manager._get_recent_conversation_context = AsyncMock(return_value=None)

    context = await persona_manager.build_context(
        user_id="user_123",
        session_type=SessionType.CONSULTATION,
        additional_context={"goal_id": "goal_123"},
    )

    assert "## Goal Consultation" in context


@pytest.mark.asyncio
async def test_build_context_with_additional(persona_manager: ARIAPersonaManager) -> None:
    """Test building context with additional context."""
    persona_manager._get_user_context = AsyncMock(return_value="Name: Test")
    persona_manager._get_chat_context = AsyncMock(return_value="Goals: 1")
    persona_manager._get_recent_conversation_context = AsyncMock(return_value=None)

    context = await persona_manager.build_context(
        user_id="user_123",
        session_type=SessionType.CHAT,
        additional_context={"extra_context": "User just had a call with Cytiva."},
    )

    assert "## Additional Context" in context
    assert "Cytiva" in context


@pytest.mark.asyncio
async def test_build_context_empty(persona_manager: ARIAPersonaManager) -> None:
    """Test building context when all context methods return None."""
    persona_manager._get_user_context = AsyncMock(return_value=None)
    persona_manager._get_chat_context = AsyncMock(return_value=None)
    persona_manager._get_recent_conversation_context = AsyncMock(return_value=None)

    context = await persona_manager.build_context(
        user_id="user_123",
        session_type=SessionType.CHAT,
    )

    assert context == ""


# ====================
# User Context Tests
# ====================


@pytest.mark.asyncio
async def test_get_user_context(persona_manager: ARIAPersonaManager) -> None:
    """Test getting user context."""
    mock_profile_service = MagicMock()
    mock_profile_service.get_full_profile = AsyncMock(
        return_value={
            "user": {
                "full_name": "John Doe",
                "title": "Sales Director",
            },
            "company": {
                "name": "Acme Biotech",
                "industry": "Biotechnology",
            },
        }
    )
    persona_manager._profile_service = mock_profile_service

    context = await persona_manager._get_user_context("user_123")

    assert "John Doe" in context
    assert "Sales Director" in context
    assert "Acme Biotech" in context


@pytest.mark.asyncio
async def test_get_user_context_error(persona_manager: ARIAPersonaManager) -> None:
    """Test getting user context handles errors gracefully."""
    mock_profile_service = MagicMock()
    mock_profile_service.get_full_profile = AsyncMock(side_effect=Exception("Database error"))
    persona_manager._profile_service = mock_profile_service

    context = await persona_manager._get_user_context("user_123")

    assert context is None


# ====================
# Briefing Context Tests
# ====================


@pytest.mark.asyncio
async def test_get_briefing_context(persona_manager: ARIAPersonaManager) -> None:
    """Test getting briefing context."""
    mock_briefing_service = MagicMock()
    mock_briefing_service.get_or_generate_briefing = AsyncMock(
        return_value={
            "summary": "Good morning! You have 3 meetings today.",
            "calendar": {
                "meeting_count": 3,
                "key_meetings": [
                    {"time": "10:00 AM", "title": "Lonza QBR"},
                ],
            },
            "leads": {
                "hot_leads": [
                    {"company_name": "Cytiva", "health_score": 85},
                ],
            },
            "email_summary": {
                "drafts_waiting": 2,
                "drafts_high_confidence": 1,
            },
            "signals": {
                "company_news": [{"headline": "Funding round"}],
                "competitive_intel": [],
            },
        }
    )
    persona_manager._briefing_service = mock_briefing_service

    context = await persona_manager._get_briefing_context("user_123")

    assert "Good morning!" in context
    assert "3 meetings" in context.lower() or "Meetings today: 3" in context
    assert "Cytiva" in context


@pytest.mark.asyncio
async def test_get_briefing_context_error(persona_manager: ARIAPersonaManager) -> None:
    """Test getting briefing context handles errors."""
    mock_briefing_service = MagicMock()
    mock_briefing_service.get_or_generate_briefing = AsyncMock(
        side_effect=Exception("Service error")
    )
    persona_manager._briefing_service = mock_briefing_service

    context = await persona_manager._get_briefing_context("user_123")

    assert context is None


# ====================
# Singleton Tests
# ====================


def test_get_aria_persona_manager_singleton() -> None:
    """Test get_aria_persona_manager returns singleton."""
    # Reset the singleton
    import src.integrations.tavus_persona as module

    module._aria_persona_manager = None

    manager1 = get_aria_persona_manager()
    manager2 = get_aria_persona_manager()

    assert manager1 is manager2


# ====================
# Lazy Property Tests
# ====================


def test_tavus_client_lazy_init(persona_manager: ARIAPersonaManager) -> None:
    """Test tavus_client is lazily initialized."""
    # Reset internal client
    persona_manager._tavus_client = None

    with patch("src.integrations.tavus_persona.TavusClient") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance

        client = persona_manager.tavus_client

        assert client is mock_instance
        mock_class.assert_called_once()


def test_profile_service_lazy_init(persona_manager: ARIAPersonaManager) -> None:
    """Test profile_service is lazily initialized."""
    persona_manager._profile_service = None

    with patch("src.services.profile_service.ProfileService") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance

        service = persona_manager.profile_service

        assert service is mock_instance


def test_briefing_service_lazy_init(persona_manager: ARIAPersonaManager) -> None:
    """Test briefing_service is lazily initialized."""
    persona_manager._briefing_service = None

    with patch("src.services.briefing.BriefingService") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance

        service = persona_manager.briefing_service

        assert service is mock_instance


def test_goal_service_lazy_init(persona_manager: ARIAPersonaManager) -> None:
    """Test goal_service is lazily initialized."""
    persona_manager._goal_service = None

    with patch("src.services.goal_service.GoalService") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance

        service = persona_manager.goal_service

        assert service is mock_instance
