"""Tests for conversation priming service."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_priming_exports_from_memory_module() -> None:
    """ConversationPrimingService and ConversationContext should be exported from src.memory."""
    from src.memory import ConversationContext, ConversationPrimingService

    assert ConversationContext is not None
    assert ConversationPrimingService is not None


def test_conversation_context_importable() -> None:
    """ConversationContext should be importable from memory.priming."""
    from src.memory.priming import ConversationContext

    assert ConversationContext is not None


def test_conversation_context_initialization() -> None:
    """ConversationContext should initialize with all required fields."""
    from src.memory.priming import ConversationContext

    context = ConversationContext(
        recent_episodes=[{"summary": "Test episode"}],
        open_threads=[{"topic": "pricing", "status": "pending"}],
        salient_facts=[{"subject": "John", "predicate": "works_at", "object": "Acme"}],
        relevant_entities=[{"name": "John Doe", "type": "person"}],
        formatted_context="## Recent Conversations\n- Test episode",
    )

    assert len(context.recent_episodes) == 1
    assert len(context.open_threads) == 1
    assert len(context.salient_facts) == 1
    assert len(context.relevant_entities) == 1
    assert "Recent Conversations" in context.formatted_context


def test_conversation_context_to_dict() -> None:
    """ConversationContext.to_dict should return serializable dict."""
    import json

    from src.memory.priming import ConversationContext

    context = ConversationContext(
        recent_episodes=[],
        open_threads=[],
        salient_facts=[],
        relevant_entities=[],
        formatted_context="No context available",
    )

    data = context.to_dict()

    assert isinstance(data, dict)
    assert "recent_episodes" in data
    assert "formatted_context" in data

    # Verify JSON serializable
    json_str = json.dumps(data)
    assert isinstance(json_str, str)


class TestConversationPrimingServiceInit:
    """Tests for ConversationPrimingService initialization."""

    def test_priming_service_importable(self) -> None:
        """ConversationPrimingService should be importable."""
        from src.memory.priming import ConversationPrimingService

        assert ConversationPrimingService is not None

    def test_priming_service_stores_dependencies(self) -> None:
        """ConversationPrimingService should store injected dependencies."""
        from src.memory.priming import ConversationPrimingService

        mock_conversation_service = MagicMock()
        mock_salience_service = MagicMock()
        mock_db_client = MagicMock()

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        assert service.conversations is mock_conversation_service
        assert service.salience is mock_salience_service
        assert service.db is mock_db_client

    def test_priming_service_has_constants(self) -> None:
        """ConversationPrimingService should have configuration constants."""
        from src.memory.priming import ConversationPrimingService

        assert ConversationPrimingService.MAX_EPISODES == 3
        assert ConversationPrimingService.MAX_THREADS == 5
        assert ConversationPrimingService.MAX_FACTS == 10
        assert ConversationPrimingService.SALIENCE_THRESHOLD == 0.3

    def test_priming_service_has_prime_method(self) -> None:
        """ConversationPrimingService should have prime_conversation method."""
        from src.memory.priming import ConversationPrimingService

        mock_conversation_service = MagicMock()
        mock_salience_service = MagicMock()
        mock_db_client = MagicMock()

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        assert hasattr(service, "prime_conversation")
        assert callable(service.prime_conversation)


class TestPrimeConversation:
    """Tests for prime_conversation method."""

    @pytest.fixture
    def mock_conversation_service(self) -> MagicMock:
        """Create mock ConversationService."""
        mock = MagicMock()
        now = datetime.now(UTC)

        # Mock get_recent_episodes
        mock.get_recent_episodes = AsyncMock(
            return_value=[
                MagicMock(
                    id="ep-1",
                    summary="Discussed Q1 targets",
                    key_topics=["sales", "Q1"],
                    ended_at=now - timedelta(hours=1),
                    open_threads=[],
                    outcomes=[{"type": "decision", "content": "Increase budget"}],
                ),
                MagicMock(
                    id="ep-2",
                    summary="Weekly sync call",
                    key_topics=["sync"],
                    ended_at=now - timedelta(days=1),
                    open_threads=[{"topic": "hiring", "status": "pending"}],
                    outcomes=[],
                ),
            ]
        )

        # Mock get_open_threads
        mock.get_open_threads = AsyncMock(
            return_value=[
                {"topic": "pricing", "status": "awaiting_response", "context": "Client review"},
                {"topic": "contract", "status": "pending", "context": "Legal review"},
            ]
        )

        return mock

    @pytest.fixture
    def mock_salience_service(self) -> MagicMock:
        """Create mock SalienceService."""
        mock = MagicMock()
        mock.get_by_salience = AsyncMock(
            return_value=[
                {
                    "graphiti_episode_id": "fact-1",
                    "current_salience": 0.85,
                    "access_count": 5,
                },
                {
                    "graphiti_episode_id": "fact-2",
                    "current_salience": 0.72,
                    "access_count": 2,
                },
            ]
        )
        return mock

    @pytest.fixture
    def mock_db_client(self) -> MagicMock:
        """Create mock Supabase client for fact lookup."""
        mock = MagicMock()
        # Mock semantic_facts query for fact details
        mock_response = MagicMock(
            data=[
                {
                    "id": "fact-1",
                    "subject": "John Doe",
                    "predicate": "works_at",
                    "object": "Acme Corp",
                    "confidence": 0.95,
                },
                {
                    "id": "fact-2",
                    "subject": "Acme Corp",
                    "predicate": "industry",
                    "object": "Technology",
                    "confidence": 0.90,
                },
            ]
        )
        mock.table.return_value.select.return_value.eq.return_value.in_.return_value.execute.return_value = mock_response
        return mock

    @pytest.mark.asyncio
    async def test_prime_conversation_fetches_episodes(
        self,
        mock_conversation_service: MagicMock,
        mock_salience_service: MagicMock,
        mock_db_client: MagicMock,
    ) -> None:
        """prime_conversation should fetch recent episodes."""
        from src.memory.priming import ConversationPrimingService

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        await service.prime_conversation(user_id="user-123")

        mock_conversation_service.get_recent_episodes.assert_called_once_with(
            user_id="user-123",
            limit=3,
            min_salience=0.3,
        )

    @pytest.mark.asyncio
    async def test_prime_conversation_fetches_threads(
        self,
        mock_conversation_service: MagicMock,
        mock_salience_service: MagicMock,
        mock_db_client: MagicMock,
    ) -> None:
        """prime_conversation should fetch open threads."""
        from src.memory.priming import ConversationPrimingService

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        await service.prime_conversation(user_id="user-123")

        mock_conversation_service.get_open_threads.assert_called_once_with(
            user_id="user-123",
            limit=5,
        )

    @pytest.mark.asyncio
    async def test_prime_conversation_fetches_salient_facts(
        self,
        mock_conversation_service: MagicMock,
        mock_salience_service: MagicMock,
        mock_db_client: MagicMock,
    ) -> None:
        """prime_conversation should fetch high-salience facts."""
        from src.memory.priming import ConversationPrimingService

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        await service.prime_conversation(user_id="user-123")

        mock_salience_service.get_by_salience.assert_called_once_with(
            user_id="user-123",
            memory_type="semantic",
            min_salience=0.3,
            limit=10,
        )

    @pytest.mark.asyncio
    async def test_prime_conversation_returns_context(
        self,
        mock_conversation_service: MagicMock,
        mock_salience_service: MagicMock,
        mock_db_client: MagicMock,
    ) -> None:
        """prime_conversation should return ConversationContext."""
        from src.memory.priming import ConversationContext, ConversationPrimingService

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        result = await service.prime_conversation(user_id="user-123")

        assert isinstance(result, ConversationContext)
        assert len(result.recent_episodes) == 2
        assert len(result.open_threads) == 2
        assert len(result.salient_facts) == 2


class TestFormatContext:
    """Tests for context formatting."""

    def test_format_context_includes_episodes(self) -> None:
        """_format_context should include episode summaries."""
        from src.memory.priming import ConversationPrimingService

        mock_conversation_service = MagicMock()
        mock_salience_service = MagicMock()
        mock_db_client = MagicMock()

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        episodes = [
            {
                "summary": "Discussed Q1 targets",
                "topics": ["sales"],
                "outcomes": [],
                "open_threads": [],
            },
            {"summary": "Weekly sync call", "topics": ["sync"], "outcomes": [], "open_threads": []},
        ]

        formatted = service._format_context(episodes, [], [], [])

        assert "## Recent Conversations" in formatted
        assert "Discussed Q1 targets" in formatted
        assert "Weekly sync call" in formatted

    def test_format_context_includes_outcomes(self) -> None:
        """_format_context should include episode outcomes."""
        from src.memory.priming import ConversationPrimingService

        mock_conversation_service = MagicMock()
        mock_salience_service = MagicMock()
        mock_db_client = MagicMock()

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        episodes = [
            {
                "summary": "Budget meeting",
                "topics": ["budget"],
                "outcomes": [{"type": "decision", "content": "Approved $50K"}],
                "open_threads": [],
            },
        ]

        formatted = service._format_context(episodes, [], [], [])

        assert "Outcomes:" in formatted
        assert "Approved $50K" in formatted

    def test_format_context_includes_threads(self) -> None:
        """_format_context should include open threads."""
        from src.memory.priming import ConversationPrimingService

        mock_conversation_service = MagicMock()
        mock_salience_service = MagicMock()
        mock_db_client = MagicMock()

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        threads = [
            {"topic": "pricing", "status": "awaiting_response", "context": "Client review"},
            {"topic": "contract", "status": "pending", "context": "Legal"},
        ]

        formatted = service._format_context([], threads, [], [])

        assert "## Open Threads" in formatted
        assert "pricing: awaiting_response" in formatted
        assert "contract: pending" in formatted

    def test_format_context_includes_facts(self) -> None:
        """_format_context should include salient facts with confidence."""
        from src.memory.priming import ConversationPrimingService

        mock_conversation_service = MagicMock()
        mock_salience_service = MagicMock()
        mock_db_client = MagicMock()

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        facts = [
            {"subject": "John", "predicate": "works_at", "object": "Acme", "confidence": 0.95},
            {"subject": "Acme", "predicate": "industry", "object": "Tech", "confidence": 0.80},
        ]

        formatted = service._format_context([], [], facts, [])

        assert "## Key Facts I Remember" in formatted
        assert "John works_at Acme" in formatted
        assert "95%" in formatted

    def test_format_context_limits_facts_to_five(self) -> None:
        """_format_context should only show top 5 facts."""
        from src.memory.priming import ConversationPrimingService

        mock_conversation_service = MagicMock()
        mock_salience_service = MagicMock()
        mock_db_client = MagicMock()

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        facts = [
            {"subject": f"Entity{i}", "predicate": "is", "object": "test", "confidence": 0.9}
            for i in range(10)
        ]

        formatted = service._format_context([], [], facts, [])

        # Count occurrences of fact lines (each starts with "- Entity")
        fact_lines = [line for line in formatted.split("\n") if line.startswith("- Entity")]
        assert len(fact_lines) == 5

    def test_format_context_empty_returns_fallback(self) -> None:
        """_format_context should return fallback when empty."""
        from src.memory.priming import ConversationPrimingService

        mock_conversation_service = MagicMock()
        mock_salience_service = MagicMock()
        mock_db_client = MagicMock()

        service = ConversationPrimingService(
            conversation_service=mock_conversation_service,
            salience_service=mock_salience_service,
            db_client=mock_db_client,
        )

        formatted = service._format_context([], [], [], [])

        assert formatted == "No prior context available."


class TestPrimeEndpoint:
    """Tests for GET /api/v1/memory/prime endpoint."""

    @pytest.fixture
    def test_app(self) -> FastAPI:
        """Create test FastAPI app with memory routes."""
        from src.api.deps import get_current_user
        from src.api.routes.memory import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")

        # Mock user for authentication
        mock_user = MagicMock()
        mock_user.id = "user-test-123"

        async def override_get_current_user() -> MagicMock:
            return mock_user

        app.dependency_overrides[get_current_user] = override_get_current_user
        return app

    @pytest.fixture
    def client(self, test_app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(test_app)

    def test_prime_endpoint_requires_auth(self) -> None:
        """GET /api/v1/memory/prime should require authentication."""
        from src.api.routes.memory import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        unauthenticated_client = TestClient(app)

        response = unauthenticated_client.get("/api/v1/memory/prime")

        # Should get 401 or 403 (auth required), or 422 if validation fails first
        assert response.status_code in [401, 403, 422]

    def test_prime_endpoint_returns_context(self, test_app: FastAPI) -> None:
        """GET /api/v1/memory/prime should return priming context."""
        # Mock the SupabaseClient to avoid real DB calls
        with patch("src.api.routes.memory.SupabaseClient") as mock_supabase:
            mock_client = MagicMock()
            mock_supabase.get_client.return_value = mock_client

            # Mock conversation_episodes query
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )
            # Mock open threads query
            mock_client.table.return_value.select.return_value.eq.return_value.neq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )
            # Mock salience query
            mock_client.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=[]
            )

            client = TestClient(test_app)
            response = client.get("/api/v1/memory/prime")

            # Should return 200 with response body
            assert response.status_code == 200
            data = response.json()
            assert "recent_context" in data
            assert "open_threads" in data
            assert "salient_facts" in data
            assert "formatted_context" in data
