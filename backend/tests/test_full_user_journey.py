"""Full user journey integration tests.

Tests the complete user lifecycle through ARIA's API:
signup -> onboarding -> conversations -> chat -> leads ->
battle cards -> signals -> goals -> activity.

Each test mocks the underlying service layer and validates
that routes accept requests and return expected shapes.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_user() -> MagicMock:
    """Create a fake user object that mimics Supabase auth user."""
    user = MagicMock()
    user.id = "user-test-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def auth_app(fake_user: MagicMock) -> Any:
    """Create a FastAPI app with auth dependency overridden."""
    from src.api.deps import get_current_user
    from src.main import app

    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(auth_app: Any) -> AsyncClient:
    """Async HTTP client that does NOT trigger lifespan events."""
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# 1. Signup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup() -> None:
    """Test user signup creates account and returns tokens."""
    from src.main import app

    transport = ASGITransport(app=app)

    # Build a mock Supabase client with the auth chain used by the signup route
    mock_session = MagicMock()
    mock_session.access_token = "access-token-abc"
    mock_session.refresh_token = "refresh-token-xyz"
    mock_session.expires_in = 3600

    mock_auth_user = MagicMock()
    mock_auth_user.id = "new-user-id"

    mock_auth_response = MagicMock()
    mock_auth_response.user = mock_auth_user
    mock_auth_response.session = mock_session

    mock_auth = MagicMock()
    mock_auth.sign_up.return_value = mock_auth_response
    mock_auth.sign_out.return_value = None

    mock_supabase_instance = MagicMock()
    mock_supabase_instance.auth = mock_auth

    with (
        patch(
            "src.api.routes.auth.SupabaseClient.get_client",
            return_value=mock_supabase_instance,
        ),
        patch(
            "src.api.routes.auth.SupabaseClient.create_company",
            new_callable=AsyncMock,
            return_value={"id": "company-1"},
        ),
        patch(
            "src.api.routes.auth.SupabaseClient.create_user_profile",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.routes.auth.SupabaseClient.create_user_settings",
            new_callable=AsyncMock,
        ),
        patch(
            "src.api.routes.auth.SupabaseClient.create_onboarding_state",
            new_callable=AsyncMock,
        ),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/auth/signup",
                json={
                    "email": "newuser@example.com",
                    "password": "securepass123",
                    "full_name": "Test User",
                    "company_name": "Acme Corp",
                },
            )

    assert response.status_code == 201
    data = response.json()
    assert data["access_token"] == "access-token-abc"
    assert data["refresh_token"] == "refresh-token-xyz"
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600


# ---------------------------------------------------------------------------
# 2. List conversations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_conversations(client: AsyncClient) -> None:
    """Test listing conversations returns expected shape."""
    mock_conversation = MagicMock()
    mock_conversation.to_dict.return_value = {
        "id": "conv-1",
        "title": "First chat",
        "message_count": 2,
        "last_message_at": "2026-02-16T00:00:00",
        "last_message_preview": "Hello ARIA",
        "updated_at": "2026-02-16T00:00:00",
    }

    mock_service_instance = MagicMock()
    mock_service_instance.list_conversations = AsyncMock(
        return_value=[mock_conversation],
    )

    # The route also calls db.table("conversations").select(...)... for count
    mock_count_result = MagicMock()
    mock_count_result.count = 1

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = (
        mock_count_result
    )

    with (
        patch(
            "src.api.routes.chat.get_supabase_client",
            return_value=mock_db,
        ),
        patch(
            "src.api.routes.chat.ConversationService",
            return_value=mock_service_instance,
        ),
    ):
        response = await client.get("/api/v1/chat/conversations")

    assert response.status_code == 200
    data = response.json()
    assert "conversations" in data
    assert "total" in data
    assert len(data["conversations"]) == 1
    assert data["conversations"][0]["id"] == "conv-1"


# ---------------------------------------------------------------------------
# 3. Send chat message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_chat_message(client: AsyncClient) -> None:
    """Test sending a chat message returns ARIA's response envelope."""
    mock_service_instance = MagicMock()
    mock_service_instance.process_message = AsyncMock(
        return_value={
            "message": "Hello! I'm ARIA, your AI colleague.",
            "citations": [],
            "conversation_id": "conv-1",
            "rich_content": [],
            "ui_commands": [],
            "suggestions": [],
            "timing": {
                "memory_query_ms": 12.5,
                "llm_response_ms": 450.0,
                "total_ms": 462.5,
            },
            "cognitive_load": None,
            "proactive_insights": [],
        },
    )

    with patch(
        "src.api.routes.chat.ChatService",
        return_value=mock_service_instance,
    ):
        response = await client.post(
            "/api/v1/chat",
            json={
                "message": "Hello ARIA",
                "conversation_id": "conv-1",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Hello! I'm ARIA, your AI colleague."
    assert data["conversation_id"] == "conv-1"
    assert "suggestions" in data
    assert "ui_commands" in data


# ---------------------------------------------------------------------------
# 4. List leads
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_leads(client: AsyncClient) -> None:
    """Test listing leads returns empty list when no leads exist."""
    mock_service_instance = MagicMock()
    mock_service_instance.list_by_user = AsyncMock(return_value=[])

    with patch(
        "src.api.routes.leads.LeadMemoryService",
        return_value=mock_service_instance,
    ):
        response = await client.get("/api/v1/leads")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


# ---------------------------------------------------------------------------
# 5. List battle cards
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_battle_cards(client: AsyncClient) -> None:
    """Test listing battle cards for user's company."""
    mock_profile = {"company_id": "company-1", "full_name": "Test User"}

    mock_service_instance = MagicMock()
    mock_service_instance.list_battle_cards = AsyncMock(
        return_value=[
            {
                "id": "bc-1",
                "competitor_name": "Competitor A",
                "strengths": ["Fast delivery"],
                "weaknesses": ["High price"],
            }
        ],
    )

    with (
        patch(
            "src.api.routes.battle_cards.SupabaseClient.get_user_by_id",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ),
        patch(
            "src.api.routes.battle_cards.BattleCardService",
            return_value=mock_service_instance,
        ),
    ):
        response = await client.get("/api/v1/battlecards/")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["competitor_name"] == "Competitor A"


# ---------------------------------------------------------------------------
# 6. Get signals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_signals(client: AsyncClient) -> None:
    """Test retrieving market signals returns list."""
    mock_service_instance = MagicMock()
    mock_service_instance.get_signals = AsyncMock(return_value=[])

    with patch(
        "src.api.routes.signals.SignalService",
        return_value=mock_service_instance,
    ):
        response = await client.get("/api/v1/signals")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


# ---------------------------------------------------------------------------
# 7. List goals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_goals(client: AsyncClient) -> None:
    """Test listing goals returns list."""
    mock_service_instance = MagicMock()
    mock_service_instance.list_goals = AsyncMock(
        return_value=[
            {
                "id": "goal-1",
                "title": "Research Lonza competitive landscape",
                "status": "active",
                "progress": 35,
            }
        ],
    )

    with patch(
        "src.api.routes.goals.GoalService",
        return_value=mock_service_instance,
    ):
        response = await client.get("/api/v1/goals")

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["title"] == "Research Lonza competitive landscape"


# ---------------------------------------------------------------------------
# 8. Get activity feed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_activity(client: AsyncClient) -> None:
    """Test activity feed returns activities and count."""
    mock_service_instance = MagicMock()
    # Source now uses ActivityFeedService.get_activity_feed (not ActivityService.get_feed)
    # Route returns {"items": ..., "total": ..., "page": ...}
    mock_service_instance.get_activity_feed = AsyncMock(
        return_value={
            "activities": [
                {
                    "id": "act-1",
                    "agent": "Hunter",
                    "activity_type": "lead_discovery",
                    "title": "Discovered 3 new leads matching ICP",
                }
            ],
            "total_count": 1,
            "page": 1,
        },
    )

    with patch(
        "src.api.routes.activity._get_service",
        return_value=mock_service_instance,
    ):
        response = await client.get("/api/v1/activity")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] == 1
    assert data["items"][0]["agent"] == "Hunter"


# ---------------------------------------------------------------------------
# 9. Company discovery submission (onboarding)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_company_discovery(client: AsyncClient) -> None:
    """Test company discovery submission during onboarding."""
    from datetime import UTC, datetime

    from src.onboarding.models import (
        OnboardingState,
        OnboardingStateResponse,
        OnboardingStep,
        ReadinessScores,
    )

    now = datetime.now(UTC)
    state_response = OnboardingStateResponse(
        state=OnboardingState(
            id="onb-1",
            user_id="user-test-123",
            current_step=OnboardingStep.DOCUMENT_UPLOAD,
            step_data={},
            completed_steps=["company_discovery"],
            skipped_steps=[],
            started_at=now,
            updated_at=now,
            completed_at=None,
            readiness_scores=ReadinessScores(),
            metadata={},
        ),
        progress_percentage=12.5,
        total_steps=8,
        completed_count=1,
        current_step_index=1,
        is_complete=False,
    )

    mock_company_service = MagicMock()
    mock_company_service.submit_company_discovery = AsyncMock(
        return_value={
            "success": True,
            "company": {"id": "company-1", "name": "Acme Corp"},
        },
    )

    mock_orchestrator = MagicMock()
    mock_orchestrator.complete_step = AsyncMock(return_value=state_response)

    # The route calls _get_company_service() and _get_orchestrator()
    with (
        patch(
            "src.api.routes.onboarding._get_company_service",
            return_value=mock_company_service,
        ),
        patch(
            "src.api.routes.onboarding._get_orchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        response = await client.post(
            "/api/v1/onboarding/company-discovery/submit",
            json={
                "company_name": "Acme Corp",
                "website": "https://acme.com",
                "email": "user@acme.com",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["state"]["current_step"] == "document_upload"
    assert "company_discovery" in data["state"]["completed_steps"]
    assert data["total_steps"] == 8
    assert data["is_complete"] is False


# ---------------------------------------------------------------------------
# 10. Complete onboarding step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_complete_onboarding_step(client: AsyncClient) -> None:
    """Test completing an onboarding step advances state."""
    from datetime import UTC, datetime

    from src.onboarding.models import (
        OnboardingState,
        OnboardingStateResponse,
        OnboardingStep,
        ReadinessScores,
    )

    now = datetime.now(UTC)
    state_response = OnboardingStateResponse(
        state=OnboardingState(
            id="onb-1",
            user_id="user-test-123",
            current_step=OnboardingStep.USER_PROFILE,
            step_data={},
            completed_steps=["company_discovery", "document_upload"],
            skipped_steps=[],
            started_at=now,
            updated_at=now,
            completed_at=None,
            readiness_scores=ReadinessScores(),
            metadata={},
        ),
        progress_percentage=25.0,
        total_steps=8,
        completed_count=2,
        current_step_index=2,
        is_complete=False,
    )

    mock_orchestrator = MagicMock()
    mock_orchestrator.complete_step = AsyncMock(return_value=state_response)

    with patch(
        "src.api.routes.onboarding._get_orchestrator",
        return_value=mock_orchestrator,
    ):
        response = await client.post(
            "/api/v1/onboarding/steps/document_upload/complete",
            json={"step_data": {"documents_uploaded": 2}},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["state"]["current_step"] == "user_profile"
    assert "document_upload" in data["state"]["completed_steps"]
    assert data["completed_count"] == 2
