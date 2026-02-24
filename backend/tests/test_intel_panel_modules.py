"""Intel panel module tests - 16 endpoints.

Each test hits the API route via httpx AsyncClient with ASGITransport
and verifies 200 status with the correct response shape. All service
and DB calls are mocked at the route-module level.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def fake_user():
    user = MagicMock()
    user.id = "user-test-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def auth_app(fake_user):
    from src.api.deps import get_current_user
    from src.main import app

    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(auth_app):
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --------------------------------------------------------------------------- #
# 1. GET /api/v1/activity  ->  {"activities": list, "count": int}
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_activity_feed(client):
    with patch("src.api.routes.activity._get_service") as mock_get_svc:
        mock_svc = MagicMock()
        mock_svc.get_activity_feed = AsyncMock(
            return_value={
                "activities": [{"id": "1", "title": "Test", "type": "agent"}],
                "total_count": 1,
                "page": 1,
            }
        )
        mock_get_svc.return_value = mock_svc

        resp = await client.get("/api/v1/activity")

    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data
    assert isinstance(data["total"], int)


# --------------------------------------------------------------------------- #
# 2. GET /api/v1/activity/{activity_id} -> activity detail dict
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_activity_agent_status(client):
    mock_detail = {"id": "act-1", "title": "Hunter ran", "agent": "hunter", "status": "completed"}
    with patch("src.services.activity_service.ActivityService.get_activity_detail", new_callable=AsyncMock, return_value=mock_detail):
        resp = await client.get("/api/v1/activity/act-1")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "act-1"


# --------------------------------------------------------------------------- #
# 3. GET /api/v1/analytics/roi  ->  ROIMetricsResponse
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_analytics_roi(client):
    mock_metrics = {
        "time_saved": {
            "hours": 12.5,
            "breakdown": {
                "email_drafts": {"count": 10, "estimated_hours": 3.0},
                "meeting_prep": {"count": 5, "estimated_hours": 4.0},
                "research_reports": {"count": 2, "estimated_hours": 3.5},
                "crm_updates": {"count": 8, "estimated_hours": 2.0},
            },
        },
        "intelligence_delivered": {
            "facts_discovered": 42,
            "signals_detected": 15,
            "gaps_filled": 7,
            "briefings_generated": 5,
        },
        "actions_taken": {
            "total": 30,
            "auto_approved": 20,
            "user_approved": 8,
            "rejected": 2,
        },
        "pipeline_impact": {
            "leads_discovered": 12,
            "meetings_prepped": 6,
            "follow_ups_sent": 18,
        },
        "weekly_trend": [],
        "period": "30d",
        "calculated_at": "2026-02-16T00:00:00Z",
    }

    with patch("src.api.routes.analytics._get_roi_service") as mock_get_svc:
        mock_svc = MagicMock()
        mock_svc.get_all_metrics = AsyncMock(return_value=mock_metrics)
        mock_get_svc.return_value = mock_svc

        resp = await client.get("/api/v1/analytics/roi?period=30d")

    assert resp.status_code == 200
    data = resp.json()
    assert "time_saved" in data
    assert "intelligence_delivered" in data
    assert "actions_taken" in data
    assert "pipeline_impact" in data
    assert "period" in data


# --------------------------------------------------------------------------- #
# 4. GET /api/v1/signals  ->  list
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_signals_list(client):
    with patch("src.api.routes.signals._get_service") as mock_get_svc:
        mock_svc = MagicMock()
        mock_svc.get_signals = AsyncMock(
            return_value=[{"id": "s1", "type": "competitor_move", "company": "Lonza"}]
        )
        mock_get_svc.return_value = mock_svc

        resp = await client.get("/api/v1/signals")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# --------------------------------------------------------------------------- #
# 5. GET /api/v1/battlecards/  ->  list
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_battlecards_list(client):
    with (
        patch(
            "src.api.routes.battle_cards.SupabaseClient.get_user_by_id",
            new_callable=AsyncMock,
            return_value={"company_id": "comp-123"},
        ),
        patch("src.api.routes.battle_cards._get_service") as mock_get_svc,
    ):
        mock_svc = MagicMock()
        mock_svc.list_battle_cards = AsyncMock(
            return_value=[{"competitor_name": "Catalent", "id": "bc-1"}]
        )
        mock_get_svc.return_value = mock_svc

        resp = await client.get("/api/v1/battlecards/")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# --------------------------------------------------------------------------- #
# 6. GET /api/v1/leads  ->  list
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_leads_list(client):
    with patch("src.api.routes.leads.LeadMemoryService") as MockLeadSvc:
        mock_instance = MockLeadSvc.return_value
        mock_instance.list_by_user = AsyncMock(return_value=[])

        resp = await client.get("/api/v1/leads")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# --------------------------------------------------------------------------- #
# 7. GET /api/v1/goals  ->  list
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_goals_list(client):
    with patch("src.api.routes.goals._get_service") as mock_get_svc:
        mock_svc = MagicMock()
        mock_svc.list_goals = AsyncMock(
            return_value=[{"id": "g1", "title": "Increase pipeline", "status": "active"}]
        )
        mock_get_svc.return_value = mock_svc

        resp = await client.get("/api/v1/goals")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# --------------------------------------------------------------------------- #
# 8. GET /api/v1/briefings  ->  list of BriefingListResponse
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_briefings_list(client):
    with patch("src.api.routes.briefings.BriefingService") as MockBriefingSvc:
        mock_instance = MockBriefingSvc.return_value
        mock_instance.list_briefings = AsyncMock(
            return_value=[
                {
                    "id": "b1",
                    "briefing_date": "2026-02-16",
                    "content": {"summary": "Today's brief"},
                }
            ]
        )

        resp = await client.get("/api/v1/briefings")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "id" in data[0]
        assert "briefing_date" in data[0]
        assert "content" in data[0]


# --------------------------------------------------------------------------- #
# 9. GET /api/v1/insights/proactive  ->  ProactiveInsightsResponse
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_proactive_insights(client):
    with (
        patch(
            "src.api.routes.insights.get_supabase_client",
            return_value=MagicMock(),
        ),
        patch("src.api.routes.insights.ProactiveMemoryService") as MockPMSvc,
    ):
        mock_instance = MockPMSvc.return_value
        mock_instance.find_volunteerable_context = AsyncMock(return_value=[])

        resp = await client.get(
            "/api/v1/insights/proactive?context=test+conversation"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "insights" in data
    assert isinstance(data["insights"], list)


# --------------------------------------------------------------------------- #
# 10. GET /api/v1/predictions  ->  list
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_predictions_list(client):
    with patch("src.api.routes.predictions._get_service") as mock_get_svc:
        mock_svc = MagicMock()
        mock_svc.list_predictions = AsyncMock(
            return_value=[
                {"id": "p1", "text": "Lonza will close", "confidence": 0.8}
            ]
        )
        mock_get_svc.return_value = mock_svc

        resp = await client.get("/api/v1/predictions")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# --------------------------------------------------------------------------- #
# 11. GET /api/v1/intelligence/causal-chains  ->  CausalChainsListResponse
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_causal_chains_list(client):
    with (
        patch(
            "src.api.routes.intelligence.get_supabase_client",
            return_value=MagicMock(),
        ),
        patch("src.api.routes.intelligence.CausalChainStore") as MockStore,
    ):
        mock_store = MockStore.return_value
        mock_store.get_chains = AsyncMock(return_value=[])

        resp = await client.get("/api/v1/intelligence/causal-chains")

    assert resp.status_code == 200
    data = resp.json()
    assert "chains" in data
    assert isinstance(data["chains"], list)
    assert "total" in data


# --------------------------------------------------------------------------- #
# 12. GET /api/v1/intelligence/simulations  ->  SimulationListResponse
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_simulations_list(client):
    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_result = MagicMock()
    mock_result.data = []
    mock_table.execute.return_value = mock_result

    with patch(
        "src.api.routes.intelligence.get_supabase_client",
        return_value=mock_db,
    ):
        resp = await client.get("/api/v1/intelligence/simulations")

    assert resp.status_code == 200
    data = resp.json()
    assert "simulations" in data
    assert isinstance(data["simulations"], list)
    assert "total" in data


# --------------------------------------------------------------------------- #
# 13. GET /api/v1/intelligence/connections  ->  ConnectionScanResponse
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_connections_list(client):
    mock_db = MagicMock()
    mock_table = MagicMock()
    mock_db.table.return_value = mock_table
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.limit.return_value = mock_table
    mock_result = MagicMock()
    mock_result.data = []
    mock_table.execute.return_value = mock_result

    with patch(
        "src.api.routes.intelligence.get_supabase_client",
        return_value=mock_db,
    ):
        resp = await client.get("/api/v1/intelligence/connections")

    assert resp.status_code == 200
    data = resp.json()
    assert "connections" in data
    assert isinstance(data["connections"], list)
    assert "events_scanned" in data


# --------------------------------------------------------------------------- #
# 14. GET /api/v1/compliance/consent  ->  dict with consent booleans
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_compliance_consent(client):
    with patch(
        "src.api.routes.compliance.compliance_service.get_consent_status",
        new_callable=AsyncMock,
        return_value={
            "email_analysis": True,
            "document_learning": True,
            "crm_processing": False,
            "writing_style_learning": True,
        },
    ):
        resp = await client.get("/api/v1/compliance/consent")

    assert resp.status_code == 200
    data = resp.json()
    assert "email_analysis" in data
    assert "document_learning" in data
    assert "crm_processing" in data
    assert "writing_style_learning" in data
    assert isinstance(data["email_analysis"], bool)


# --------------------------------------------------------------------------- #
# 15. GET /api/v1/user/cognitive-load  ->  CognitiveLoadState
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_cognitive_load(client):
    with (
        patch(
            "src.api.routes.cognitive_load.get_supabase_client",
            return_value=MagicMock(),
        ),
        patch("src.api.routes.cognitive_load.CognitiveLoadMonitor") as MockMonitor,
    ):
        mock_monitor = MockMonitor.return_value
        # Return None so the route falls through to the default low-load state
        mock_monitor.get_current_load = AsyncMock(return_value=None)

        resp = await client.get("/api/v1/user/cognitive-load")

    assert resp.status_code == 200
    data = resp.json()
    assert "level" in data
    assert "score" in data
    assert "factors" in data
    assert "recommendation" in data
    assert data["level"] == "low"
    assert data["score"] == 0.0


# --------------------------------------------------------------------------- #
# 16. GET /api/v1/notifications  ->  NotificationListResponse
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_notifications_list(client):
    from src.models.notification import NotificationListResponse

    mock_response = NotificationListResponse(
        notifications=[],
        total=0,
        unread_count=0,
    )

    with patch(
        "src.api.routes.notifications.NotificationService.get_notifications",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        resp = await client.get("/api/v1/notifications")

    assert resp.status_code == 200
    data = resp.json()
    assert "notifications" in data
    assert isinstance(data["notifications"], list)
    assert "total" in data
    assert "unread_count" in data
