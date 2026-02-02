"""Tests for memory API routes."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.deps import get_current_user
from src.main import app


@pytest.fixture
def mock_current_user() -> MagicMock:
    """Create mock current user."""
    user = MagicMock()
    user.id = "test-user-123"
    return user


@pytest.fixture
def test_client(mock_current_user: MagicMock) -> TestClient:
    """Create test client with mocked authentication."""

    async def override_get_current_user() -> MagicMock:
        return mock_current_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_memory_query_returns_effective_confidence(
    test_client: TestClient,
) -> None:
    """Test that memory query returns effective (decayed) confidence."""
    from src.memory.semantic import FactSource, SemanticFact, SemanticMemory

    now = datetime.now(UTC)

    # Old fact with decay
    fact = SemanticFact(
        id="fact-123",
        user_id="test-user-123",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.75,
        source=FactSource.EXTRACTED,
        valid_from=now - timedelta(days=60),
        last_confirmed_at=None,
        corroborating_sources=[],
    )

    with patch.object(SemanticMemory, "search_facts", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = [fact]

        response = test_client.get(
            "/api/v1/memory/query",
            params={"q": "Acme", "types": ["semantic"]},
        )

    assert response.status_code == 200
    data = response.json()

    # Confidence should be decayed from 0.75
    # Expected: 0.75 - ((60-7) * 0.05/30) ≈ 0.66
    expected = 0.75 - ((60 - 7) * 0.05 / 30)
    assert len(data["items"]) == 1
    assert data["items"][0]["confidence"] == pytest.approx(expected, rel=0.05)
