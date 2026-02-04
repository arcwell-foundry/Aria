# US-515: Lead Memory in Knowledge Graph Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a Lead Memory Graph module that stores lead data as first-class Graphiti nodes with typed relationships, enabling cross-lead queries and pattern detection.

**Architecture:** The module uses a hybrid storage approach: Supabase for structured metadata (existing `lead_memories` table) and Graphiti (Neo4j) for semantic content and relationship traversal. Each lead memory becomes a node with typed relationships (OWNED_BY, HAS_CONTACT, etc.) that enable cross-lead queries like "leads where we discussed pricing" and pattern detection like "leads that went silent".

**Tech Stack:** Python 3.11+, Graphiti (Neo4j), Supabase, pytest, async/await

---

## Prerequisites

- Existing `lead_memories` table in Supabase (from migration `20260202000004_create_lead_memory.sql`)
- Working Graphiti client (`src/db/graphiti.py`)
- Lead memory models (`src/models/lead_memory.py`)
- Exception classes in `src/core/exceptions.py`

---

## Task 1: Add Lead Memory Exception Classes

**Files:**
- Modify: `backend/src/core/exceptions.py:402` (after CorporateFactNotFoundError)

**Step 1: Write the failing test**

Create test file:
```python
# backend/tests/test_lead_memory_graph.py
"""Tests for lead memory graph module."""

import pytest


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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_lead_memory_graph_error_exists tests/test_lead_memory_graph.py::test_lead_memory_not_found_error_exists -v`
Expected: FAIL with "cannot import name 'LeadMemoryGraphError'"

**Step 3: Write minimal implementation**

Add to `backend/src/core/exceptions.py` after line ~402 (after CorporateFactNotFoundError):

```python
class LeadMemoryGraphError(ARIAException):
    """Lead memory graph operation error (500).

    Used for failures when storing or querying lead memory in the knowledge graph.
    """

    def __init__(self, message: str = "Unknown error") -> None:
        """Initialize lead memory graph error.

        Args:
            message: Error details.
        """
        super().__init__(
            message=f"Lead memory graph operation failed: {message}",
            code="LEAD_MEMORY_GRAPH_ERROR",
            status_code=500,
        )


class LeadMemoryNotFoundError(NotFoundError):
    """Lead memory not found error (404)."""

    def __init__(self, lead_id: str) -> None:
        """Initialize lead memory not found error.

        Args:
            lead_id: The ID of the lead memory that was not found.
        """
        super().__init__(resource="Lead memory", resource_id=lead_id)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_lead_memory_graph_error_exists tests/test_lead_memory_graph.py::test_lead_memory_not_found_error_exists -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/core/exceptions.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): add LeadMemoryGraphError and LeadMemoryNotFoundError exceptions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add LEAD to MemoryType Enum

**Files:**
- Modify: `backend/src/memory/audit.py:31-38`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
def test_memory_type_has_lead() -> None:
    """Test MemoryType enum includes LEAD."""
    from src.memory.audit import MemoryType

    assert hasattr(MemoryType, "LEAD")
    assert MemoryType.LEAD.value == "lead"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_memory_type_has_lead -v`
Expected: FAIL with "AttributeError: LEAD"

**Step 3: Write minimal implementation**

Modify `backend/src/memory/audit.py` MemoryType enum:

```python
class MemoryType(Enum):
    """Types of memory that can be audited."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    PROSPECTIVE = "prospective"
    LEAD = "lead"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_memory_type_has_lead -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/audit.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): add LEAD to MemoryType enum for audit logging

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Create LeadMemoryNode Dataclass

**Files:**
- Create: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
from datetime import UTC, datetime


def test_lead_memory_node_initialization() -> None:
    """Test LeadMemoryNode initializes with required fields."""
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_lead_memory_node_initialization tests/test_lead_memory_graph.py::test_lead_memory_node_to_dict tests/test_lead_memory_graph.py::test_lead_memory_node_from_dict -v`
Expected: FAIL with "cannot import name 'LeadMemoryNode'"

**Step 3: Write minimal implementation**

Create `backend/src/memory/lead_memory_graph.py`:

```python
"""Lead memory graph module for knowledge graph operations.

Stores lead memories as first-class nodes in Graphiti with typed relationships:
- OWNED_BY: Lead owned by a user
- CONTRIBUTED_BY: Users who contributed to the lead
- ABOUT_COMPANY: Links to company entity
- HAS_CONTACT: Stakeholder contacts
- HAS_COMMUNICATION: Email/meeting/call events
- HAS_SIGNAL: Market signals and insights
- SYNCED_TO: CRM synchronization link

Enables cross-lead queries and pattern detection.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LeadMemoryNode:
    """A lead memory node for the knowledge graph.

    Represents a sales lead/opportunity/account with all its metadata.
    Stored in both Supabase (structured data) and Graphiti (relationships).
    """

    id: str
    user_id: str
    company_name: str
    lifecycle_stage: str  # lead, opportunity, account
    status: str  # active, won, lost, dormant
    health_score: int
    created_at: datetime
    company_id: str | None = None
    crm_id: str | None = None
    crm_provider: str | None = None
    first_touch_at: datetime | None = None
    last_activity_at: datetime | None = None
    expected_close_date: str | None = None  # ISO date string
    expected_value: float | None = None
    tags: list[str] = field(default_factory=list)
    updated_at: datetime | None = None
    graphiti_node_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize node to dictionary for storage.

        Returns:
            Dictionary suitable for database insertion.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "company_name": self.company_name,
            "company_id": self.company_id,
            "lifecycle_stage": self.lifecycle_stage,
            "status": self.status,
            "health_score": self.health_score,
            "crm_id": self.crm_id,
            "crm_provider": self.crm_provider,
            "first_touch_at": self.first_touch_at.isoformat() if self.first_touch_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "expected_close_date": self.expected_close_date,
            "expected_value": self.expected_value,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "graphiti_node_id": self.graphiti_node_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LeadMemoryNode":
        """Create a LeadMemoryNode from a dictionary.

        Args:
            data: Dictionary from database query.

        Returns:
            LeadMemoryNode instance.
        """
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            company_name=data["company_name"],
            company_id=data.get("company_id"),
            lifecycle_stage=data["lifecycle_stage"],
            status=data["status"],
            health_score=data["health_score"],
            crm_id=data.get("crm_id"),
            crm_provider=data.get("crm_provider"),
            first_touch_at=datetime.fromisoformat(data["first_touch_at"])
            if data.get("first_touch_at")
            else None,
            last_activity_at=datetime.fromisoformat(data["last_activity_at"])
            if data.get("last_activity_at")
            else None,
            expected_close_date=data.get("expected_close_date"),
            expected_value=data.get("expected_value"),
            tags=data.get("tags") or [],
            created_at=datetime.fromisoformat(data["created_at"])
            if isinstance(data.get("created_at"), str)
            else data.get("created_at") or datetime.now(UTC),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else None,
            graphiti_node_id=data.get("graphiti_node_id"),
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_lead_memory_node_initialization tests/test_lead_memory_graph.py::test_lead_memory_node_to_dict tests/test_lead_memory_graph.py::test_lead_memory_node_from_dict -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): add LeadMemoryNode dataclass for graph storage

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Create Relationship Type Enum

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_lead_relationship_types_exist -v`
Expected: FAIL with "cannot import name 'LeadRelationshipType'"

**Step 3: Write minimal implementation**

Add to `backend/src/memory/lead_memory_graph.py` after imports:

```python
from enum import Enum


class LeadRelationshipType(Enum):
    """Types of relationships between lead memory nodes."""

    OWNED_BY = "OWNED_BY"  # Lead -> User (owner)
    CONTRIBUTED_BY = "CONTRIBUTED_BY"  # Lead -> User (contributor)
    ABOUT_COMPANY = "ABOUT_COMPANY"  # Lead -> Company
    HAS_CONTACT = "HAS_CONTACT"  # Lead -> Contact/Stakeholder
    HAS_COMMUNICATION = "HAS_COMMUNICATION"  # Lead -> Event (email/meeting/call)
    HAS_SIGNAL = "HAS_SIGNAL"  # Lead -> Signal/Insight
    SYNCED_TO = "SYNCED_TO"  # Lead -> CRM Record
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_lead_relationship_types_exist -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): add LeadRelationshipType enum for graph relationships

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Create LeadMemoryGraph Service Class with Graphiti Client

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_lead_memory_graph_has_required_methods -v`
Expected: FAIL with "cannot import name 'LeadMemoryGraph'"

**Step 3: Write minimal implementation**

Add to `backend/src/memory/lead_memory_graph.py`:

```python
from typing import TYPE_CHECKING

from src.core.exceptions import LeadMemoryGraphError, LeadMemoryNotFoundError
from src.memory.audit import MemoryOperation, MemoryType, log_memory_operation

if TYPE_CHECKING:
    from graphiti_core import Graphiti


class LeadMemoryGraph:
    """Service for managing lead memories in the knowledge graph.

    Provides methods for storing leads as Graphiti nodes with typed
    relationships, and querying across leads for patterns and insights.
    Uses both Supabase (metadata) and Graphiti (semantic content).
    """

    def _get_graphiti_node_name(self, lead_id: str) -> str:
        """Generate namespaced node name for Graphiti.

        Args:
            lead_id: The lead's UUID.

        Returns:
            Namespaced node name (e.g., "lead:lead-123").
        """
        return f"lead:{lead_id}"

    async def _get_graphiti_client(self) -> "Graphiti":
        """Get the Graphiti client instance.

        Returns:
            Initialized Graphiti client.

        Raises:
            LeadMemoryGraphError: If client initialization fails.
        """
        from src.db.graphiti import GraphitiClient

        try:
            return await GraphitiClient.get_instance()
        except Exception as e:
            raise LeadMemoryGraphError(f"Failed to get Graphiti client: {e}") from e

    async def store_lead(self, lead: LeadMemoryNode) -> str:
        """Store a lead memory node in the knowledge graph.

        Args:
            lead: The lead memory node to store.

        Returns:
            The ID of the stored lead.

        Raises:
            LeadMemoryGraphError: If storage fails.
        """
        raise NotImplementedError

    async def get_lead(self, user_id: str, lead_id: str) -> LeadMemoryNode:
        """Retrieve a specific lead by ID.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead's UUID.

        Returns:
            The requested LeadMemoryNode.

        Raises:
            LeadMemoryNotFoundError: If lead doesn't exist.
            LeadMemoryGraphError: If retrieval fails.
        """
        raise NotImplementedError

    async def update_lead(self, lead: LeadMemoryNode) -> None:
        """Update an existing lead memory node.

        Args:
            lead: The lead with updated data.

        Raises:
            LeadMemoryNotFoundError: If lead doesn't exist.
            LeadMemoryGraphError: If update fails.
        """
        raise NotImplementedError

    async def add_contact(
        self,
        lead_id: str,
        contact_email: str,
        contact_name: str | None = None,
        role: str | None = None,
        influence_level: int = 5,
    ) -> None:
        """Add a contact relationship to a lead.

        Args:
            lead_id: The lead's UUID.
            contact_email: Contact's email address.
            contact_name: Contact's name.
            role: Stakeholder role (decision_maker, influencer, etc.).
            influence_level: 1-10 influence score.

        Raises:
            LeadMemoryGraphError: If operation fails.
        """
        raise NotImplementedError

    async def add_communication(
        self,
        lead_id: str,
        event_type: str,
        content: str,
        occurred_at: datetime,
        participants: list[str] | None = None,
    ) -> None:
        """Add a communication event to a lead.

        Args:
            lead_id: The lead's UUID.
            event_type: Type of communication (email, meeting, call).
            content: Summary of the communication.
            occurred_at: When the communication happened.
            participants: List of participant names/emails.

        Raises:
            LeadMemoryGraphError: If operation fails.
        """
        raise NotImplementedError

    async def add_signal(
        self,
        lead_id: str,
        signal_type: str,
        content: str,
        confidence: float = 0.7,
    ) -> None:
        """Add a market signal or insight to a lead.

        Args:
            lead_id: The lead's UUID.
            signal_type: Type of signal (buying_signal, objection, etc.).
            content: Description of the signal.
            confidence: Confidence score 0-1.

        Raises:
            LeadMemoryGraphError: If operation fails.
        """
        raise NotImplementedError

    async def search_leads(
        self,
        user_id: str,
        query: str,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Search leads using semantic search.

        Args:
            user_id: The user whose leads to search.
            query: Natural language search query.
            limit: Maximum number of leads to return.

        Returns:
            List of matching leads.

        Raises:
            LeadMemoryGraphError: If search fails.
        """
        raise NotImplementedError

    async def find_leads_by_topic(
        self,
        user_id: str,
        topic: str,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Find leads where a specific topic was discussed.

        Args:
            user_id: The user whose leads to search.
            topic: Topic to search for (e.g., "pricing", "implementation").
            limit: Maximum number of leads to return.

        Returns:
            List of leads where the topic was discussed.

        Raises:
            LeadMemoryGraphError: If query fails.
        """
        raise NotImplementedError

    async def find_silent_leads(
        self,
        user_id: str,
        days_inactive: int = 14,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Find leads that have gone silent (no recent activity).

        Args:
            user_id: The user whose leads to check.
            days_inactive: Number of days without activity to consider silent.
            limit: Maximum number of leads to return.

        Returns:
            List of leads with no recent activity.

        Raises:
            LeadMemoryGraphError: If query fails.
        """
        raise NotImplementedError

    async def get_leads_for_company(
        self,
        user_id: str,
        company_id: str,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Get all leads associated with a company.

        Args:
            user_id: The user whose leads to search.
            company_id: The company's UUID.
            limit: Maximum number of leads to return.

        Returns:
            List of leads for the company.

        Raises:
            LeadMemoryGraphError: If query fails.
        """
        raise NotImplementedError
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_lead_memory_graph_has_required_methods -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): add LeadMemoryGraph service class skeleton

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Implement store_lead Method

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


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

        await graph.store_lead(lead)

        # Check the episode body contains ownership info
        call_args = mock_graphiti_client.add_episode.call_args
        episode_body = call_args.kwargs.get("episode_body", "")
        assert "OWNED_BY: user-789" in episode_body
        assert "Company: TechCo" in episode_body
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_store_lead_stores_in_graphiti tests/test_lead_memory_graph.py::test_store_lead_creates_ownership_relationship -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace `store_lead` method in `backend/src/memory/lead_memory_graph.py`:

```python
    def _build_lead_body(self, lead: LeadMemoryNode) -> str:
        """Build structured lead body for Graphiti storage.

        Args:
            lead: The LeadMemoryNode to serialize.

        Returns:
            Structured text representation with relationship markers.
        """
        parts = [
            f"Lead ID: {lead.id}",
            f"Company: {lead.company_name}",
            f"OWNED_BY: {lead.user_id}",
            f"Lifecycle Stage: {lead.lifecycle_stage}",
            f"Status: {lead.status}",
            f"Health Score: {lead.health_score}",
        ]

        if lead.company_id:
            parts.append(f"ABOUT_COMPANY: {lead.company_id}")

        if lead.crm_id:
            parts.append(f"SYNCED_TO: {lead.crm_provider}:{lead.crm_id}")

        if lead.expected_value:
            parts.append(f"Expected Value: {lead.expected_value}")

        if lead.tags:
            parts.append(f"Tags: {', '.join(lead.tags)}")

        return "\n".join(parts)

    async def store_lead(self, lead: LeadMemoryNode) -> str:
        """Store a lead memory node in the knowledge graph.

        Args:
            lead: The lead memory node to store.

        Returns:
            The ID of the stored lead.

        Raises:
            LeadMemoryGraphError: If storage fails.
        """
        try:
            import uuid as uuid_module

            lead_id = lead.id if lead.id else str(uuid_module.uuid4())

            # Get Graphiti client
            client = await self._get_graphiti_client()

            # Build lead body with relationships
            lead_body = self._build_lead_body(lead)

            # Store in Graphiti
            from graphiti_core.nodes import EpisodeType

            await client.add_episode(
                name=self._get_graphiti_node_name(lead_id),
                episode_body=lead_body,
                source=EpisodeType.text,
                source_description=f"lead_memory:{lead.user_id}:{lead.lifecycle_stage}",
                reference_time=lead.created_at,
            )

            logger.info(
                "Stored lead memory in graph",
                extra={
                    "lead_id": lead_id,
                    "user_id": lead.user_id,
                    "company_name": lead.company_name,
                },
            )

            # Audit log
            await log_memory_operation(
                user_id=lead.user_id,
                operation=MemoryOperation.CREATE,
                memory_type=MemoryType.LEAD,
                memory_id=lead_id,
                metadata={"company_name": lead.company_name, "stage": lead.lifecycle_stage},
                suppress_errors=True,
            )

            return lead_id

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to store lead in graph")
            raise LeadMemoryGraphError(f"Failed to store lead: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_store_lead_stores_in_graphiti tests/test_lead_memory_graph.py::test_store_lead_creates_ownership_relationship -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): implement store_lead method with OWNED_BY relationship

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Implement get_lead Method

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
@pytest.mark.asyncio
async def test_get_lead_retrieves_by_id() -> None:
    """Test get_lead retrieves specific lead by ID."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    mock_driver = MagicMock()
    mock_node = MagicMock()
    mock_node.content = f"Lead ID: lead-123\nCompany: Acme Corp\nOWNED_BY: user-456\nLifecycle Stage: lead\nStatus: active\nHealth Score: 75"
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_get_lead_retrieves_by_id tests/test_lead_memory_graph.py::test_get_lead_raises_not_found -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Add/replace in `backend/src/memory/lead_memory_graph.py`:

```python
    def _parse_content_to_lead(
        self,
        lead_id: str,
        content: str,
        created_at: datetime,
    ) -> LeadMemoryNode | None:
        """Parse lead content string into LeadMemoryNode.

        Args:
            lead_id: The lead ID.
            content: The raw content string from Graphiti.
            created_at: When the lead was created.

        Returns:
            LeadMemoryNode if parsing succeeds, None otherwise.
        """
        try:
            lines = content.split("\n")
            user_id = ""
            company_name = ""
            company_id = None
            lifecycle_stage = "lead"
            status = "active"
            health_score = 50
            crm_id = None
            crm_provider = None
            expected_value = None
            tags: list[str] = []

            for line in lines:
                if line.startswith("OWNED_BY:"):
                    user_id = line.replace("OWNED_BY:", "").strip()
                elif line.startswith("Company:"):
                    company_name = line.replace("Company:", "").strip()
                elif line.startswith("ABOUT_COMPANY:"):
                    company_id = line.replace("ABOUT_COMPANY:", "").strip()
                elif line.startswith("Lifecycle Stage:"):
                    lifecycle_stage = line.replace("Lifecycle Stage:", "").strip()
                elif line.startswith("Status:"):
                    status = line.replace("Status:", "").strip()
                elif line.startswith("Health Score:"):
                    try:
                        health_score = int(line.replace("Health Score:", "").strip())
                    except ValueError:
                        pass
                elif line.startswith("SYNCED_TO:"):
                    sync_info = line.replace("SYNCED_TO:", "").strip()
                    if ":" in sync_info:
                        crm_provider, crm_id = sync_info.split(":", 1)
                elif line.startswith("Expected Value:"):
                    try:
                        expected_value = float(line.replace("Expected Value:", "").strip())
                    except ValueError:
                        pass
                elif line.startswith("Tags:"):
                    tags_str = line.replace("Tags:", "").strip()
                    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

            if not user_id or not company_name:
                return None

            return LeadMemoryNode(
                id=lead_id,
                user_id=user_id,
                company_name=company_name,
                company_id=company_id,
                lifecycle_stage=lifecycle_stage,
                status=status,
                health_score=health_score,
                crm_id=crm_id,
                crm_provider=crm_provider,
                expected_value=expected_value,
                tags=tags,
                created_at=created_at,
            )
        except Exception as e:
            logger.warning(f"Failed to parse lead content: {e}")
            return None

    async def get_lead(self, user_id: str, lead_id: str) -> LeadMemoryNode:
        """Retrieve a specific lead by ID.

        Args:
            user_id: The user who owns the lead.
            lead_id: The lead's UUID.

        Returns:
            The requested LeadMemoryNode.

        Raises:
            LeadMemoryNotFoundError: If lead doesn't exist.
            LeadMemoryGraphError: If retrieval fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Query for specific lead by name
            query = """
            MATCH (e:Episode)
            WHERE e.name = $lead_name
            RETURN e
            """

            lead_name = self._get_graphiti_node_name(lead_id)

            result = await client.driver.execute_query(
                query,
                lead_name=lead_name,
            )

            records = result[0] if result else []

            if not records:
                raise LeadMemoryNotFoundError(lead_id)

            # Parse the node into a LeadMemoryNode
            node = records[0]["e"]
            content = getattr(node, "content", "") or node.get("content", "")
            created_at = getattr(node, "created_at", None) or node.get("created_at")

            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            elif created_at is None:
                created_at = datetime.now(UTC)

            lead = self._parse_content_to_lead(
                lead_id=lead_id,
                content=content,
                created_at=created_at,
            )

            if lead is None:
                raise LeadMemoryNotFoundError(lead_id)

            # Verify ownership
            if lead.user_id != user_id:
                raise LeadMemoryNotFoundError(lead_id)

            return lead

        except LeadMemoryNotFoundError:
            raise
        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to get lead from graph", extra={"lead_id": lead_id})
            raise LeadMemoryGraphError(f"Failed to get lead: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_get_lead_retrieves_by_id tests/test_lead_memory_graph.py::test_get_lead_raises_not_found -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): implement get_lead method with ownership verification

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Implement add_communication Method

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_add_communication_stores_event -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace `add_communication` method in `backend/src/memory/lead_memory_graph.py`:

```python
    async def add_communication(
        self,
        lead_id: str,
        event_type: str,
        content: str,
        occurred_at: datetime,
        participants: list[str] | None = None,
    ) -> None:
        """Add a communication event to a lead.

        Args:
            lead_id: The lead's UUID.
            event_type: Type of communication (email, meeting, call).
            content: Summary of the communication.
            occurred_at: When the communication happened.
            participants: List of participant names/emails.

        Raises:
            LeadMemoryGraphError: If operation fails.
        """
        try:
            import uuid as uuid_module

            client = await self._get_graphiti_client()

            # Build communication body with relationship marker
            parts = [
                f"HAS_COMMUNICATION: {lead_id}",
                f"Event Type: {event_type}",
                f"Content: {content}",
                f"Occurred At: {occurred_at.isoformat()}",
            ]

            if participants:
                parts.append(f"Participants: {', '.join(participants)}")

            comm_body = "\n".join(parts)

            # Store as episode linked to lead
            from graphiti_core.nodes import EpisodeType

            comm_id = str(uuid_module.uuid4())
            await client.add_episode(
                name=f"comm:{lead_id}:{comm_id}",
                episode_body=comm_body,
                source=EpisodeType.text,
                source_description=f"lead_communication:{lead_id}:{event_type}",
                reference_time=occurred_at,
            )

            logger.info(
                "Added communication to lead",
                extra={"lead_id": lead_id, "event_type": event_type},
            )

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to add communication to lead")
            raise LeadMemoryGraphError(f"Failed to add communication: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_add_communication_stores_event -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): implement add_communication with HAS_COMMUNICATION relationship

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Implement add_contact Method

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_add_contact_stores_stakeholder -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace `add_contact` method in `backend/src/memory/lead_memory_graph.py`:

```python
    async def add_contact(
        self,
        lead_id: str,
        contact_email: str,
        contact_name: str | None = None,
        role: str | None = None,
        influence_level: int = 5,
    ) -> None:
        """Add a contact relationship to a lead.

        Args:
            lead_id: The lead's UUID.
            contact_email: Contact's email address.
            contact_name: Contact's name.
            role: Stakeholder role (decision_maker, influencer, etc.).
            influence_level: 1-10 influence score.

        Raises:
            LeadMemoryGraphError: If operation fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Build contact body with relationship marker
            parts = [
                f"HAS_CONTACT: {lead_id}",
                f"Contact: {contact_email}",
            ]

            if contact_name:
                parts.append(f"Name: {contact_name}")

            if role:
                parts.append(f"Role: {role}")

            parts.append(f"Influence: {influence_level}")

            contact_body = "\n".join(parts)

            # Store as episode linked to lead
            from graphiti_core.nodes import EpisodeType

            # Use email as unique identifier for contact
            contact_id = contact_email.replace("@", "_at_").replace(".", "_")
            await client.add_episode(
                name=f"contact:{lead_id}:{contact_id}",
                episode_body=contact_body,
                source=EpisodeType.text,
                source_description=f"lead_contact:{lead_id}:{role or 'unknown'}",
                reference_time=datetime.now(UTC),
            )

            logger.info(
                "Added contact to lead",
                extra={"lead_id": lead_id, "contact_email": contact_email, "role": role},
            )

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to add contact to lead")
            raise LeadMemoryGraphError(f"Failed to add contact: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_add_contact_stores_stakeholder -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): implement add_contact with HAS_CONTACT relationship

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Implement add_signal Method

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_add_signal_stores_insight -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace `add_signal` method in `backend/src/memory/lead_memory_graph.py`:

```python
    async def add_signal(
        self,
        lead_id: str,
        signal_type: str,
        content: str,
        confidence: float = 0.7,
    ) -> None:
        """Add a market signal or insight to a lead.

        Args:
            lead_id: The lead's UUID.
            signal_type: Type of signal (buying_signal, objection, etc.).
            content: Description of the signal.
            confidence: Confidence score 0-1.

        Raises:
            LeadMemoryGraphError: If operation fails.
        """
        try:
            import uuid as uuid_module

            client = await self._get_graphiti_client()

            # Build signal body with relationship marker
            parts = [
                f"HAS_SIGNAL: {lead_id}",
                f"Signal Type: {signal_type}",
                f"Content: {content}",
                f"Confidence: {confidence}",
                f"Detected At: {datetime.now(UTC).isoformat()}",
            ]

            signal_body = "\n".join(parts)

            # Store as episode linked to lead
            from graphiti_core.nodes import EpisodeType

            signal_id = str(uuid_module.uuid4())
            await client.add_episode(
                name=f"signal:{lead_id}:{signal_id}",
                episode_body=signal_body,
                source=EpisodeType.text,
                source_description=f"lead_signal:{lead_id}:{signal_type}",
                reference_time=datetime.now(UTC),
            )

            logger.info(
                "Added signal to lead",
                extra={"lead_id": lead_id, "signal_type": signal_type, "confidence": confidence},
            )

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to add signal to lead")
            raise LeadMemoryGraphError(f"Failed to add signal: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_add_signal_stores_insight -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): implement add_signal with HAS_SIGNAL relationship

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Implement search_leads Method

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
@pytest.mark.asyncio
async def test_search_leads_queries_graphiti() -> None:
    """Test search_leads uses Graphiti semantic search."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    mock_edge = MagicMock()
    mock_edge.fact = f"Lead ID: lead-123\nCompany: Acme Corp\nOWNED_BY: user-456\nLifecycle Stage: lead\nStatus: active\nHealth Score: 75"
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_search_leads_queries_graphiti -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace `search_leads` method in `backend/src/memory/lead_memory_graph.py`:

```python
    def _parse_edge_to_lead(self, edge: Any, user_id: str) -> LeadMemoryNode | None:
        """Parse a Graphiti edge into a LeadMemoryNode.

        Args:
            edge: The Graphiti edge object.
            user_id: The expected user ID for ownership verification.

        Returns:
            LeadMemoryNode if parsing succeeds and matches user, None otherwise.
        """
        try:
            fact = getattr(edge, "fact", "")
            created_at = getattr(edge, "created_at", datetime.now(UTC))
            edge_name = getattr(edge, "name", "") or ""

            # Extract lead ID from name (format: lead:lead-id)
            if not edge_name.startswith("lead:"):
                return None

            lead_id = edge_name.replace("lead:", "")

            lead = self._parse_content_to_lead(
                lead_id=lead_id,
                content=fact,
                created_at=created_at if isinstance(created_at, datetime) else datetime.now(UTC),
            )

            # Verify ownership
            if lead and lead.user_id != user_id:
                return None

            return lead
        except Exception as e:
            logger.warning(f"Failed to parse edge to lead: {e}")
            return None

    async def search_leads(
        self,
        user_id: str,
        query: str,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Search leads using semantic search.

        Args:
            user_id: The user whose leads to search.
            query: Natural language search query.
            limit: Maximum number of leads to return.

        Returns:
            List of matching leads.

        Raises:
            LeadMemoryGraphError: If search fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Search with user context
            search_query = f"lead memory for user {user_id}: {query}"
            results = await client.search(search_query)

            leads = []
            for edge in results[:limit]:
                lead = self._parse_edge_to_lead(edge, user_id)
                if lead:
                    leads.append(lead)

            return leads

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to search leads")
            raise LeadMemoryGraphError(f"Failed to search leads: {e}") from e
```

Add import at top of file:

```python
from typing import TYPE_CHECKING, Any
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_search_leads_queries_graphiti -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): implement search_leads with semantic search

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Implement find_leads_by_topic Method

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
@pytest.mark.asyncio
async def test_find_leads_by_topic_searches_communications() -> None:
    """Test find_leads_by_topic searches for topic in lead communications."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    # Mock a communication that mentions pricing
    mock_comm_edge = MagicMock()
    mock_comm_edge.fact = f"HAS_COMMUNICATION: lead-123\nEvent Type: email\nContent: Discussed pricing options for Q2"
    mock_comm_edge.created_at = now
    mock_comm_edge.name = "comm:lead-123:comm-456"

    # Mock the lead itself
    mock_lead_edge = MagicMock()
    mock_lead_edge.fact = f"Lead ID: lead-123\nCompany: Acme Corp\nOWNED_BY: user-456\nLifecycle Stage: opportunity\nStatus: active\nHealth Score: 80"
    mock_lead_edge.created_at = now
    mock_lead_edge.name = "lead:lead-123"

    mock_client.search = AsyncMock(side_effect=[
        [mock_comm_edge],  # First search for topic
        [mock_lead_edge],  # Second search for lead details
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
        # First call should search for topic
        first_call = mock_client.search.call_args_list[0]
        assert "pricing" in first_call[0][0]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_find_leads_by_topic_searches_communications -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace `find_leads_by_topic` method in `backend/src/memory/lead_memory_graph.py`:

```python
    async def find_leads_by_topic(
        self,
        user_id: str,
        topic: str,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Find leads where a specific topic was discussed.

        Searches communications (emails, meetings, calls) for the topic
        and returns the associated leads.

        Args:
            user_id: The user whose leads to search.
            topic: Topic to search for (e.g., "pricing", "implementation").
            limit: Maximum number of leads to return.

        Returns:
            List of leads where the topic was discussed.

        Raises:
            LeadMemoryGraphError: If query fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Search for communications mentioning the topic
            search_query = f"lead communication discussing {topic}"
            results = await client.search(search_query)

            # Extract unique lead IDs from communications
            lead_ids: set[str] = set()
            for edge in results:
                fact = getattr(edge, "fact", "")
                # Parse HAS_COMMUNICATION relationship to get lead ID
                for line in fact.split("\n"):
                    if line.startswith("HAS_COMMUNICATION:"):
                        lead_id = line.replace("HAS_COMMUNICATION:", "").strip()
                        lead_ids.add(lead_id)
                        break

            # Fetch full lead details
            leads = []
            for lead_id in list(lead_ids)[:limit]:
                try:
                    lead = await self.get_lead(user_id, lead_id)
                    leads.append(lead)
                except LeadMemoryNotFoundError:
                    # Lead may have been deleted or belongs to another user
                    continue

            return leads

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to find leads by topic")
            raise LeadMemoryGraphError(f"Failed to find leads by topic: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_find_leads_by_topic_searches_communications -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): implement find_leads_by_topic for cross-lead queries

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Implement find_silent_leads Method

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
from datetime import timedelta


@pytest.mark.asyncio
async def test_find_silent_leads_returns_inactive() -> None:
    """Test find_silent_leads returns leads with no recent activity."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    old_date = now - timedelta(days=30)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    # Mock a lead with old last_activity_at
    mock_lead_edge = MagicMock()
    mock_lead_edge.fact = f"Lead ID: lead-silent\nCompany: Silent Corp\nOWNED_BY: user-456\nLifecycle Stage: lead\nStatus: active\nHealth Score: 60"
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_find_silent_leads_returns_inactive -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace `find_silent_leads` method in `backend/src/memory/lead_memory_graph.py`:

```python
    async def find_silent_leads(
        self,
        user_id: str,
        days_inactive: int = 14,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Find leads that have gone silent (no recent activity).

        Searches for active leads with no communications in the
        specified number of days.

        Args:
            user_id: The user whose leads to check.
            days_inactive: Number of days without activity to consider silent.
            limit: Maximum number of leads to return.

        Returns:
            List of leads with no recent activity.

        Raises:
            LeadMemoryGraphError: If query fails.
        """
        try:
            from datetime import timedelta

            client = await self._get_graphiti_client()

            # Calculate cutoff date
            cutoff_date = datetime.now(UTC) - timedelta(days=days_inactive)

            # Search for leads with status active but no recent communications
            search_query = f"lead memory for user {user_id} active status silent inactive no recent activity"
            results = await client.search(search_query)

            leads = []
            for edge in results[:limit * 2]:  # Get extra to filter
                lead = self._parse_edge_to_lead(edge, user_id)
                if lead and lead.status == "active":
                    # Check if last_activity_at is before cutoff
                    if lead.last_activity_at is None or lead.last_activity_at < cutoff_date:
                        leads.append(lead)
                        if len(leads) >= limit:
                            break

            return leads

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to find silent leads")
            raise LeadMemoryGraphError(f"Failed to find silent leads: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_find_silent_leads_returns_inactive -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): implement find_silent_leads pattern detection

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Implement get_leads_for_company Method

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
@pytest.mark.asyncio
async def test_get_leads_for_company_filters_by_company() -> None:
    """Test get_leads_for_company returns only leads for specific company."""
    from src.memory.lead_memory_graph import LeadMemoryGraph

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    mock_lead_edge = MagicMock()
    mock_lead_edge.fact = f"Lead ID: lead-123\nCompany: Acme Corp\nOWNED_BY: user-456\nABOUT_COMPANY: company-789\nLifecycle Stage: opportunity\nStatus: active\nHealth Score: 80"
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_get_leads_for_company_filters_by_company -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace `get_leads_for_company` method in `backend/src/memory/lead_memory_graph.py`:

```python
    async def get_leads_for_company(
        self,
        user_id: str,
        company_id: str,
        limit: int = 20,
    ) -> list[LeadMemoryNode]:
        """Get all leads associated with a company.

        Uses ABOUT_COMPANY relationship to find all leads
        linked to a specific company entity.

        Args:
            user_id: The user whose leads to search.
            company_id: The company's UUID.
            limit: Maximum number of leads to return.

        Returns:
            List of leads for the company.

        Raises:
            LeadMemoryGraphError: If query fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Search for leads with ABOUT_COMPANY relationship to this company
            search_query = f"lead memory ABOUT_COMPANY {company_id} for user {user_id}"
            results = await client.search(search_query)

            leads = []
            for edge in results[:limit]:
                lead = self._parse_edge_to_lead(edge, user_id)
                if lead and lead.company_id == company_id:
                    leads.append(lead)

            return leads

        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to get leads for company")
            raise LeadMemoryGraphError(f"Failed to get leads for company: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_get_leads_for_company_filters_by_company -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): implement get_leads_for_company with ABOUT_COMPANY relationship

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Implement update_lead Method

**Files:**
- Modify: `backend/src/memory/lead_memory_graph.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
@pytest.mark.asyncio
async def test_update_lead_updates_in_graphiti() -> None:
    """Test update_lead updates lead data in Graphiti."""
    from src.memory.lead_memory_graph import LeadMemoryGraph, LeadMemoryNode

    now = datetime.now(UTC)
    graph = LeadMemoryGraph()
    mock_client = MagicMock()

    # Mock driver for delete and add operations
    mock_driver = MagicMock()
    mock_driver.execute_query = AsyncMock(return_value=([{"deleted": 1}], None, None))
    mock_client.driver = mock_driver
    mock_client.add_episode = AsyncMock(return_value=MagicMock(uuid="updated-uuid"))

    updated_lead = LeadMemoryNode(
        id="lead-123",
        user_id="user-456",
        company_name="Acme Corp",
        lifecycle_stage="opportunity",  # Changed from lead
        status="active",
        health_score=85,  # Updated
        created_at=now,
    )

    with patch.object(graph, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        await graph.update_lead(updated_lead)

        # Should delete old and add new
        mock_driver.execute_query.assert_called_once()
        mock_client.add_episode.assert_called_once()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_update_lead_updates_in_graphiti -v`
Expected: FAIL with "NotImplementedError"

**Step 3: Write minimal implementation**

Replace `update_lead` method in `backend/src/memory/lead_memory_graph.py`:

```python
    async def update_lead(self, lead: LeadMemoryNode) -> None:
        """Update an existing lead memory node.

        Replaces the lead node in Graphiti with updated data.
        Uses delete-then-add pattern to update.

        Args:
            lead: The lead with updated data.

        Raises:
            LeadMemoryNotFoundError: If lead doesn't exist.
            LeadMemoryGraphError: If update fails.
        """
        try:
            client = await self._get_graphiti_client()

            # Delete existing lead node
            lead_name = self._get_graphiti_node_name(lead.id)
            query = """
            MATCH (e:Episode)
            WHERE e.name = $lead_name
            DETACH DELETE e
            RETURN count(e) as deleted
            """

            result = await client.driver.execute_query(
                query,
                lead_name=lead_name,
            )

            records = result[0] if result else []
            deleted_count = records[0]["deleted"] if records else 0

            if deleted_count == 0:
                raise LeadMemoryNotFoundError(lead.id)

            # Re-add with updated data
            lead_body = self._build_lead_body(lead)

            from graphiti_core.nodes import EpisodeType

            await client.add_episode(
                name=lead_name,
                episode_body=lead_body,
                source=EpisodeType.text,
                source_description=f"lead_memory:{lead.user_id}:{lead.lifecycle_stage}:updated",
                reference_time=lead.updated_at or datetime.now(UTC),
            )

            logger.info(
                "Updated lead in graph",
                extra={"lead_id": lead.id, "user_id": lead.user_id},
            )

            # Audit log
            await log_memory_operation(
                user_id=lead.user_id,
                operation=MemoryOperation.UPDATE,
                memory_type=MemoryType.LEAD,
                memory_id=lead.id,
                metadata={"stage": lead.lifecycle_stage, "status": lead.status},
                suppress_errors=True,
            )

        except LeadMemoryNotFoundError:
            raise
        except LeadMemoryGraphError:
            raise
        except Exception as e:
            logger.exception("Failed to update lead in graph")
            raise LeadMemoryGraphError(f"Failed to update lead: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_update_lead_updates_in_graphiti -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/lead_memory_graph.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): implement update_lead method

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: Export from memory __init__.py

**Files:**
- Modify: `backend/src/memory/__init__.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_lead_memory_graph.py`:

```python
def test_lead_memory_graph_exported_from_memory() -> None:
    """Test LeadMemoryGraph is exported from src.memory."""
    from src.memory import LeadMemoryGraph, LeadMemoryNode, LeadRelationshipType

    assert LeadMemoryGraph is not None
    assert LeadMemoryNode is not None
    assert LeadRelationshipType is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_lead_memory_graph_exported_from_memory -v`
Expected: FAIL with "cannot import name"

**Step 3: Write minimal implementation**

Add to `backend/src/memory/__init__.py` imports:

```python
from src.memory.lead_memory_graph import (
    LeadMemoryGraph,
    LeadMemoryNode,
    LeadRelationshipType,
)
```

Add to `__all__` list:

```python
    # Lead Memory Graph
    "LeadMemoryGraph",
    "LeadMemoryNode",
    "LeadRelationshipType",
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py::test_lead_memory_graph_exported_from_memory -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/__init__.py backend/tests/test_lead_memory_graph.py
git commit -m "$(cat <<'EOF'
feat(lead-memory): export LeadMemoryGraph from memory module

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 17: Run Full Test Suite and Linting

**Files:**
- All modified files

**Step 1: Run all tests**

Run: `cd backend && python -m pytest tests/test_lead_memory_graph.py -v`
Expected: All tests PASS

**Step 2: Run mypy type checking**

Run: `cd backend && python -m mypy src/memory/lead_memory_graph.py --strict`
Expected: No errors

**Step 3: Run ruff linting**

Run: `cd backend && python -m ruff check src/memory/lead_memory_graph.py`
Expected: No errors

**Step 4: Run ruff format**

Run: `cd backend && python -m ruff format src/memory/lead_memory_graph.py`
Expected: File formatted

**Step 5: Commit**

```bash
git add .
git commit -m "$(cat <<'EOF'
chore(lead-memory): fix linting and type issues

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 18: Create Integration Test

**Files:**
- Create: `backend/tests/integration/test_lead_memory_graph_integration.py`

**Step 1: Write the test file**

```python
"""Integration tests for lead memory graph module.

These tests require a running Neo4j instance.
Skip with: pytest -m "not integration"
"""

import pytest
from datetime import UTC, datetime

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_lead_memory_graph_full_flow() -> None:
    """Test complete flow: create lead, add relationships, query."""
    pytest.skip("Integration test - requires Neo4j instance")


@pytest.mark.asyncio
async def test_cross_lead_query_finds_related_leads() -> None:
    """Test querying across multiple leads by topic."""
    pytest.skip("Integration test - requires Neo4j instance")
```

**Step 2: Run integration tests (skipped)**

Run: `cd backend && python -m pytest tests/integration/test_lead_memory_graph_integration.py -v`
Expected: Tests skipped

**Step 3: Commit**

```bash
git add backend/tests/integration/test_lead_memory_graph_integration.py
git commit -m "$(cat <<'EOF'
test(lead-memory): add integration test stubs for graph queries

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Summary

This implementation plan creates `src/memory/lead_memory_graph.py` with:

1. **LeadMemoryNode** - Dataclass for Graphiti storage
2. **LeadRelationshipType** - Enum with all 7 relationship types:
   - OWNED_BY, CONTRIBUTED_BY, ABOUT_COMPANY, HAS_CONTACT
   - HAS_COMMUNICATION, HAS_SIGNAL, SYNCED_TO
3. **LeadMemoryGraph** - Service class with:
   - Core methods: store_lead, get_lead, update_lead
   - Relationship methods: add_contact, add_communication, add_signal
   - Cross-lead queries: search_leads, find_leads_by_topic
   - Pattern detection: find_silent_leads
   - Corporate Memory mapping: get_leads_for_company
4. **Unit tests** for all graph query patterns

The implementation follows existing patterns from episodic.py and semantic.py for Graphiti integration, with namespace prefixing (`lead:`, `comm:`, `contact:`, `signal:`) for multi-tenant isolation.
