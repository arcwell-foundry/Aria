"""End-to-end tests for Phase 8 Companion System.

Tests cover four key companion subsystems via API routes:
1. Personality pushback on bad decisions
2. Theory of Mind stress detection
3. Narrative identity contextual references
4. Self-reflection self-assessment
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.companion.personality import OpinionResult
from src.companion.theory_of_mind import ConfidenceLevel, MentalState, StressLevel


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_user():
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = "user-test-companion-e2e"
    user.email = "companion-test@example.com"
    return user


@pytest.fixture
def auth_app(fake_user):
    """Create a FastAPI app with auth overridden."""
    from src.api.deps import get_current_user
    from src.main import app

    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(auth_app):
    """Create an async HTTP test client."""
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Test 1: Pushback on Bad Decision ────────────────────────────────────────


@pytest.mark.asyncio
async def test_pushback_on_bad_decision(client):
    """PersonalityService returns should_push_back=True when evidence contradicts the user.

    The opinion route creates a PersonalityService inline, calls form_opinion to get
    an OpinionResult, then calls generate_pushback and record_opinion. We mock the
    service class so all three methods return controlled values and verify the API
    response includes should_push_back=True with a pushback message.
    """
    mock_opinion = OpinionResult(
        has_opinion=True,
        opinion="I disagree with this approach",
        confidence=0.85,
        supporting_evidence=["No regulatory approval in target region"],
        should_push_back=True,
        pushback_reason="The data doesn't support this strategy",
    )

    with patch("src.api.routes.companion.PersonalityService") as MockPS:
        mock_service = MockPS.return_value
        mock_service.form_opinion = AsyncMock(return_value=mock_opinion)
        mock_service.generate_pushback = AsyncMock(
            return_value="I'd recommend reconsidering. The EU market has stronger fundamentals."
        )
        mock_service.record_opinion = AsyncMock(return_value="opinion-id-abc")

        resp = await client.post(
            "/api/v1/personality/opinion",
            json={
                "topic": "Should we target the Asian market?",
                "context": {"note": "Our product has no Asian regulatory approval"},
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["should_push_back"] is True
    assert data["has_opinion"] is True
    assert data["confidence"] == 0.85
    assert data["opinion_id"] == "opinion-id-abc"
    assert "reconsider" in data["pushback_message"].lower() or "EU" in data["pushback_message"]
    assert len(data["supporting_evidence"]) > 0


# ── Test 2: Stress Detection Adjusts Response ──────────────────────────────


@pytest.mark.asyncio
async def test_stress_detection_adjusts_response(client):
    """Theory of Mind detects high stress and recommends a supportive response style.

    The mental-state route creates a TheoryOfMindModule inline and calls
    get_current_state. When the state is non-None, the route reads enum .value
    fields from the MentalState dataclass. We provide a real MentalState with
    StressLevel.HIGH and verify the API response surfaces supportive guidance.
    """
    high_stress_state = MentalState(
        stress_level=StressLevel.HIGH,
        confidence=ConfidenceLevel.UNCERTAIN,
        current_focus="Q1 pipeline shortfall",
        emotional_tone="anxious",
        needs_support=True,
        needs_space=False,
        recommended_response_style="supportive",
    )

    with patch("src.api.routes.companion.TheoryOfMindModule") as MockToM:
        mock_module = MockToM.return_value
        mock_module.get_current_state = AsyncMock(return_value=high_stress_state)

        resp = await client.get("/api/v1/user/mental-state")

    assert resp.status_code == 200
    data = resp.json()
    assert data["stress_level"] == "high"
    assert data["confidence"] == "uncertain"
    assert data["recommended_response_style"] == "supportive"
    assert data["needs_support"] is True
    assert data["emotional_tone"] == "anxious"
    assert data["current_focus"] == "Q1 pipeline shortfall"
    # Verify timestamp is present
    assert "inferred_at" in data


# ── Test 3: Narrative References Appear ─────────────────────────────────────


@pytest.mark.asyncio
async def test_narrative_references_appear(client):
    """Narrative engine returns shared history references for a given topic.

    The /narrative/references route creates a NarrativeIdentityEngine inline,
    calls get_contextual_references with user_id and current_topic, and wraps
    the returned list of strings into a ContextualReferencesResponse.
    """
    mock_references = [
        "Remember when we closed the Novartis CDM deal last quarter?",
        "This reminds me of the territory strategy we built together in January.",
    ]

    with patch("src.api.routes.companion.NarrativeIdentityEngine") as MockNE:
        mock_engine = MockNE.return_value
        mock_engine.get_contextual_references = AsyncMock(return_value=mock_references)

        resp = await client.post(
            "/api/v1/narrative/references",
            json={"current_topic": "Discussing quarterly strategy for Q2"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "references" in data
    assert len(data["references"]) == 2
    assert "Novartis" in data["references"][0]
    assert "territory" in data["references"][1].lower()


# ── Test 4: Self-Assessment Returns Reflection ──────────────────────────────


@pytest.mark.asyncio
async def test_self_assessment_returns_reflection(client):
    """Self-assessment endpoint returns structured reflection with scores and trends.

    The /reflection/self-assessment route creates a SelfReflectionService inline,
    calls generate_self_assessment(user_id, period="weekly"), and maps the returned
    dict into a SelfAssessmentResponse Pydantic model. We mock the service to return
    a dict matching the expected keys and verify the API response structure.
    """
    mock_assessment = {
        "id": "assess-weekly-001",
        "assessment_period": "weekly",
        "overall_score": 0.72,
        "strengths": [
            "Strong at identifying pipeline risks early",
            "Good follow-up email drafting",
        ],
        "weaknesses": [
            "Need more data on APAC market dynamics",
            "Slow to detect sentiment shifts in long threads",
        ],
        "mistakes_acknowledged": [
            {
                "description": "Missed a follow-up deadline for the Roche lead",
                "severity": "medium",
                "corrective_action": "Added calendar reminder system",
            }
        ],
        "improvement_plan": [
            {
                "area": "APAC market intelligence",
                "action": "Integrate additional APAC data sources",
                "priority": "high",
            },
            {
                "area": "Sentiment detection",
                "action": "Fine-tune emotional analysis for longer conversations",
                "priority": "medium",
            },
        ],
        "trend": "improving",
    }

    with patch("src.api.routes.companion.SelfReflectionService") as MockSR:
        mock_service = MockSR.return_value
        mock_service.generate_self_assessment = AsyncMock(return_value=mock_assessment)

        resp = await client.get("/api/v1/reflection/self-assessment")

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "assess-weekly-001"
    assert data["assessment_period"] == "weekly"
    assert data["overall_score"] == 0.72
    assert data["trend"] == "improving"
    assert len(data["strengths"]) == 2
    assert len(data["weaknesses"]) == 2
    assert len(data["mistakes_acknowledged"]) == 1
    assert len(data["improvement_plan"]) == 2
    assert data["mistakes_acknowledged"][0]["severity"] == "medium"
