# backend/tests/test_lead_memory_graph.py
"""Tests for lead memory graph module."""


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
