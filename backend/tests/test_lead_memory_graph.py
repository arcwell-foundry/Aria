# backend/tests/test_lead_memory_graph.py
"""Tests for lead memory graph module."""


def test_lead_memory_graph_exported_from_memory() -> None:
    """Test LeadMemoryGraph is exported from src.memory."""
    from src.memory import LeadMemoryGraph, LeadMemoryNode, LeadRelationshipType

    assert LeadMemoryGraph is not None
    assert LeadMemoryNode is not None
    assert LeadRelationshipType is not None


def test_lead_memory_graph_error_exists() -> None:
    """Test LeadMemoryGraphError exception class exists."""
    from src.core.exceptions import LeadMemoryGraphError

    error = LeadMemoryGraphError("test error")
    assert "test error" in str(error)
    assert error.status_code == 500
    assert error.code == "LEAD_MEMORY_GRAPH_ERROR"


def test_lead_memory_not_found_error_exists() -> None:
    """Test LeadMemoryNotFoundError exception class exists."""
    from src.core.exceptions import LeadMemoryNotFoundError

    error = LeadMemoryNotFoundError("lead-123")
    assert "lead-123" in str(error)
    assert error.status_code == 404


def test_memory_type_has_lead() -> None:
    """Test MemoryType enum includes LEAD."""
    from src.memory.audit import MemoryType

    assert hasattr(MemoryType, "LEAD")
    assert MemoryType.LEAD.value == "lead"


def test_lead_memory_node_initialization() -> None:
    """Test LeadMemoryNode initializes with required fields."""
    from datetime import UTC, datetime

    from src.memory.lead_memory_graph import LeadMemoryNode

    now = datetime.now(UTC)
    node = LeadMemoryNode(
        id="lead-123",
        user_id="user-456",
        company_name="Acme Corp",
        company_id="company-789",
        lifecycle_stage="lead",
        status="active",
        health_score=75,
        first_touch_at=now,
        last_activity_at=now,
        created_at=now,
    )

    assert node.id == "lead-123"
    assert node.user_id == "user-456"
    assert node.company_name == "Acme Corp"
    assert node.lifecycle_stage == "lead"
    assert node.status == "active"
    assert node.health_score == 75


def test_lead_memory_node_to_dict() -> None:
    """Test LeadMemoryNode serializes to dictionary."""
    from datetime import UTC, datetime

    from src.memory.lead_memory_graph import LeadMemoryNode

    now = datetime.now(UTC)
    node = LeadMemoryNode(
        id="lead-123",
        user_id="user-456",
        company_name="Acme Corp",
        lifecycle_stage="opportunity",
        status="active",
        health_score=80,
        created_at=now,
    )

    data = node.to_dict()
    assert data["id"] == "lead-123"
    assert data["company_name"] == "Acme Corp"
    assert data["lifecycle_stage"] == "opportunity"
    assert "created_at" in data


def test_lead_memory_node_from_dict() -> None:
    """Test LeadMemoryNode deserializes from dictionary."""
    from datetime import UTC, datetime

    from src.memory.lead_memory_graph import LeadMemoryNode

    now = datetime.now(UTC)
    data = {
        "id": "lead-123",
        "user_id": "user-456",
        "company_name": "Acme Corp",
        "company_id": None,
        "lifecycle_stage": "lead",
        "status": "active",
        "health_score": 65,
        "crm_id": "SF-001",
        "crm_provider": "salesforce",
        "first_touch_at": now.isoformat(),
        "last_activity_at": now.isoformat(),
        "expected_close_date": None,
        "expected_value": 50000.0,
        "tags": ["enterprise", "healthcare"],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    node = LeadMemoryNode.from_dict(data)
    assert node.id == "lead-123"
    assert node.company_name == "Acme Corp"
    assert node.crm_id == "SF-001"
    assert node.expected_value == 50000.0
    assert node.tags == ["enterprise", "healthcare"]


def test_lead_relationship_types_exist() -> None:
    """Test LeadRelationshipType enum has all required types."""
    from src.memory.lead_memory_graph import LeadRelationshipType

    assert LeadRelationshipType.OWNED_BY.value == "OWNED_BY"
    assert LeadRelationshipType.CONTRIBUTED_BY.value == "CONTRIBUTED_BY"
    assert LeadRelationshipType.ABOUT_COMPANY.value == "ABOUT_COMPANY"
    assert LeadRelationshipType.HAS_CONTACT.value == "HAS_CONTACT"
    assert LeadRelationshipType.HAS_COMMUNICATION.value == "HAS_COMMUNICATION"
    assert LeadRelationshipType.HAS_SIGNAL.value == "HAS_SIGNAL"
    assert LeadRelationshipType.SYNCED_TO.value == "SYNCED_TO"


def test_lead_memory_graph_has_required_methods() -> None:
    """Test LeadMemoryGraph class has required interface methods."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    graph = LeadMemoryGraph()

    # Core methods
    assert hasattr(graph, "store_lead")
    assert hasattr(graph, "get_lead")
    assert hasattr(graph, "update_lead")

    # Relationship methods
    assert hasattr(graph, "add_contact")
    assert hasattr(graph, "add_communication")
    assert hasattr(graph, "add_signal")

    # Query methods
    assert hasattr(graph, "search_leads")
    assert hasattr(graph, "find_leads_by_topic")
    assert hasattr(graph, "find_silent_leads")
    assert hasattr(graph, "get_leads_for_company")


# --- store_lead tests ---

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_graphiti_client() -> MagicMock:
    """Create a mock GraphitiClient for testing."""
    mock_instance = MagicMock()
    mock_instance.add_episode = AsyncMock(return_value=MagicMock(uuid="graphiti-lead-123"))
    return mock_instance


@pytest.mark.asyncio
async def test_store_lead_stores_in_graphiti(mock_graphiti_client: MagicMock) -> None:
    """Test that store_lead stores lead in Graphiti."""
    from src.memory.lead_memory_graph import LeadMemoryGraph, LeadMemoryNode

    now = datetime.now(UTC)
    lead = LeadMemoryNode(
        id="lead-123",
        user_id="user-456",
        company_name="Acme Corp",
        lifecycle_stage="lead",
        status="active",
        health_score=75,
        created_at=now,
    )

    graph = LeadMemoryGraph()

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get_client:
        mock_get_client.return_value = mock_graphiti_client
        # Patch the audit logging to avoid database calls
        with patch("src.memory.audit.log_memory_operation", new_callable=AsyncMock):
            result = await graph.store_lead(lead)

            assert result == "lead-123"
            mock_graphiti_client.add_episode.assert_called_once()


@pytest.mark.asyncio
async def test_store_lead_creates_ownership_relationship(mock_graphiti_client: MagicMock) -> None:
    """Test that store_lead creates OWNED_BY relationship in episode body."""
    from src.memory.lead_memory_graph import LeadMemoryGraph, LeadMemoryNode

    now = datetime.now(UTC)
    lead = LeadMemoryNode(
        id="lead-456",
        user_id="user-789",
        company_name="TechCo",
        lifecycle_stage="opportunity",
        status="active",
        health_score=80,
        created_at=now,
    )

    graph = LeadMemoryGraph()

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get_client:
        mock_get_client.return_value = mock_graphiti_client
        # Patch the audit logging to avoid database calls
        with patch("src.memory.audit.log_memory_operation", new_callable=AsyncMock):
            await graph.store_lead(lead)

            # Check the episode body contains ownership info
            call_args = mock_graphiti_client.add_episode.call_args
            episode_body = call_args.kwargs.get("episode_body", "")
            assert "OWNED_BY: user-789" in episode_body
            assert "Company: TechCo" in episode_body


# --- get_lead tests ---


@pytest.mark.asyncio
async def test_get_lead_retrieves_by_id() -> None:
    """Test get_lead retrieves specific lead by ID."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_node = MagicMock()
    mock_node.content = "Lead ID: lead-123\nCompany: Acme Corp\nOWNED_BY: user-456\nLifecycle Stage: lead\nStatus: active\nHealth Score: 75"
    mock_node.created_at = now
    mock_record = {"e": mock_node}
    mock_driver.execute_query = AsyncMock(return_value=([mock_record], None, None))
    mock_client.driver = mock_driver

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        lead = await graph.get_lead(user_id="user-456", lead_id="lead-123")

        assert lead is not None
        assert lead.id == "lead-123"
        assert lead.company_name == "Acme Corp"
        mock_driver.execute_query.assert_called_once()


@pytest.mark.asyncio
async def test_get_lead_raises_not_found() -> None:
    """Test get_lead raises LeadMemoryNotFoundError when not found."""
    from src.core.exceptions import LeadMemoryNotFoundError
    from src.memory.lead_memory_graph import LeadMemoryGraph

    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([], None, None))
    mock_client.driver = mock_driver

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        with pytest.raises(LeadMemoryNotFoundError):
            await graph.get_lead(user_id="user-456", lead_id="nonexistent")


# --- add_communication tests ---


@pytest.mark.asyncio
async def test_add_communication_stores_event() -> None:
    """Test add_communication stores communication event with HAS_COMMUNICATION relationship."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="comm-uuid"))

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        await graph.add_communication(
            lead_id="lead-123",
            event_type="email",
            content="Discussed pricing options for enterprise tier",
            occurred_at=now,
            participants=["john@acme.com", "sarah@techco.com"],
        )

        mock_client.add_episode.assert_called_once()
        call_args = mock_client.add_episode.call_args
        episode_body = call_args.kwargs.get("episode_body", "")
        assert "HAS_COMMUNICATION: lead-123" in episode_body
        assert "Event Type: email" in episode_body
        assert "pricing" in episode_body


# --- add_contact tests ---


@pytest.mark.asyncio
async def test_add_contact_stores_stakeholder() -> None:
    """Test add_contact stores contact with HAS_CONTACT relationship."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    graph = LeadMemoryGraph()
    mock_client = MagicMock()
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="contact-uuid"))

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        await graph.add_contact(
            lead_id="lead-123",
            contact_email="john.smith@acme.com",
            contact_name="John Smith",
            role="decision_maker",
            influence_level=9,
        )

        mock_client.add_episode.assert_called_once()
        call_args = mock_client.add_episode.call_args
        episode_body = call_args.kwargs.get("episode_body", "")
        assert "HAS_CONTACT: lead-123" in episode_body
        assert "Contact: john.smith@acme.com" in episode_body
        assert "Role: decision_maker" in episode_body
        assert "Influence: 9" in episode_body


# --- add_signal tests ---


@pytest.mark.asyncio
async def test_add_signal_stores_insight() -> None:
    """Test add_signal stores market signal with HAS_SIGNAL relationship."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    graph = LeadMemoryGraph()
    mock_client = MagicMock()
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="signal-uuid"))

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        await graph.add_signal(
            lead_id="lead-123",
            signal_type="buying_signal",
            content="CEO mentioned expanding to EU market next quarter",
            confidence=0.85,
        )

        mock_client.add_episode.assert_called_once()
        call_args = mock_client.add_episode.call_args
        episode_body = call_args.kwargs.get("episode_body", "")
        assert "HAS_SIGNAL: lead-123" in episode_body
        assert "Signal Type: buying_signal" in episode_body
        assert "EU market" in episode_body
        assert "Confidence: 0.85" in episode_body


# --- search_leads tests ---


@pytest.mark.asyncio
async def test_search_leads_queries_graphiti() -> None:
    """Test search_leads uses Graphiti semantic search."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    mock_edge = MagicMock()
    mock_edge.fact = "Lead ID: lead-123\nCompany: Acme Corp\nOWNED_BY: user-456\nLifecycle Stage: lead\nStatus: active\nHealth Score: 75"
    mock_edge.created_at = now
    mock_edge.name = "lead:lead-123"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await graph.search_leads("user-456", "enterprise deals", limit=10)

        assert isinstance(results, list)
        mock_client.search.assert_called_once()
        call_args = mock_client.search.call_args
        assert "enterprise deals" in call_args[0][0]


# --- find_leads_by_topic tests ---


@pytest.mark.asyncio
async def test_find_leads_by_topic_searches_communications() -> None:
    """Test find_leads_by_topic searches for topic in lead communications."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    mock_comm_edge = MagicMock()
    mock_comm_edge.fact = "HAS_COMMUNICATION: lead-123\nEvent Type: email\nContent: Discussed pricing options for Q2"
    mock_comm_edge.created_at = now
    mock_comm_edge.name = "comm:lead-123:comm-456"

    mock_lead_edge = MagicMock()
    mock_lead_edge.fact = "Lead ID: lead-123\nCompany: Acme Corp\nOWNED_BY: user-456\nLifecycle Stage: opportunity\nStatus: active\nHealth Score: 80"
    mock_lead_edge.created_at = now
    mock_lead_edge.name = "lead:lead-123"

    mock_client.search = AsyncMock(side_effect=[
        [mock_comm_edge],
        [mock_lead_edge],
    ])

    mock_driver = MagicMock()
    mock_node = MagicMock()
    mock_node.content = mock_lead_edge.fact
    mock_node.created_at = now
    mock_driver.execute_query = AsyncMock(return_value=([{"e": mock_node}], None, None))
    mock_client.driver = mock_driver

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await graph.find_leads_by_topic("user-456", "pricing", limit=10)

        assert isinstance(results, list)
        first_call = mock_client.search.call_args_list[0]
        assert "pricing" in first_call[0][0]


# --- find_silent_leads tests ---

from datetime import timedelta


@pytest.mark.asyncio
async def test_find_silent_leads_returns_inactive() -> None:
    """Test find_silent_leads returns leads with no recent activity."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    old_date = now - timedelta(days=30)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    mock_lead_edge = MagicMock()
    mock_lead_edge.fact = "Lead ID: lead-silent\nCompany: Silent Corp\nOWNED_BY: user-456\nLifecycle Stage: lead\nStatus: active\nHealth Score: 60"
    mock_lead_edge.created_at = old_date
    mock_lead_edge.name = "lead:lead-silent"

    mock_client.search = AsyncMock(return_value=[mock_lead_edge])

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await graph.find_silent_leads("user-456", days_inactive=14, limit=10)

        assert isinstance(results, list)
        mock_client.search.assert_called_once()
        call_args = mock_client.search.call_args
        assert "inactive" in call_args[0][0].lower() or "silent" in call_args[0][0].lower()


# --- get_leads_for_company tests ---


@pytest.mark.asyncio
async def test_get_leads_for_company_filters_by_company() -> None:
    """Test get_leads_for_company returns only leads for specific company."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    mock_lead_edge = MagicMock()
    mock_lead_edge.fact = "Lead ID: lead-123\nCompany: Acme Corp\nOWNED_BY: user-456\nABOUT_COMPANY: company-789\nLifecycle Stage: opportunity\nStatus: active\nHealth Score: 80"
    mock_lead_edge.created_at = now
    mock_lead_edge.name = "lead:lead-123"

    mock_client.search = AsyncMock(return_value=[mock_lead_edge])

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        results = await graph.get_leads_for_company("user-456", "company-789", limit=10)

        assert isinstance(results, list)
        mock_client.search.assert_called_once()
        call_args = mock_client.search.call_args
        assert "company-789" in call_args[0][0]


# --- update_lead tests ---


@pytest.mark.asyncio
async def test_update_lead_updates_in_graphiti() -> None:
    """Test update_lead updates lead data in Graphiti."""
    from src.memory.lead_memory_graph import LeadMemoryGraph, LeadMemoryNode

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([{"deleted": 1}], None, None))
    mock_client.driver = mock_driver
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="updated-uuid"))

    updated_lead = LeadMemoryNode(
        id="lead-123",
        user_id="user-456",
        company_name="Acme Corp",
        lifecycle_stage="opportunity",
        status="active",
        health_score=85,
        created_at=now,
    )

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client
        # Patch the audit logging to avoid database calls
        with patch("src.memory.audit.log_memory_operation", new_callable=AsyncMock):
            await graph.update_lead(updated_lead)

            mock_driver.execute_query.assert_called_once()
            mock_client.add_episode.assert_called_once()
