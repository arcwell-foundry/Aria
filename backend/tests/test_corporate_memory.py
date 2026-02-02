"""Tests for corporate memory module."""

from datetime import UTC, datetime

import pytest


def test_corporate_fact_source_enum() -> None:
    """Test CorporateFactSource enum values."""
    from src.memory.corporate import CorporateFactSource

    assert CorporateFactSource.EXTRACTED.value == "extracted"
    assert CorporateFactSource.AGGREGATED.value == "aggregated"
    assert CorporateFactSource.ADMIN_STATED.value == "admin_stated"


def test_corporate_fact_dataclass() -> None:
    """Test CorporateFact dataclass initialization."""
    from src.memory.corporate import CorporateFact, CorporateFactSource

    now = datetime.now(UTC)
    fact = CorporateFact(
        id="test-id",
        company_id="company-123",
        subject="Acme Corp",
        predicate="has_headquarters",
        object="San Francisco",
        confidence=0.85,
        source=CorporateFactSource.ADMIN_STATED,
        is_active=True,
        created_by="user-456",
        created_at=now,
        updated_at=now,
    )

    assert fact.id == "test-id"
    assert fact.company_id == "company-123"
    assert fact.subject == "Acme Corp"
    assert fact.predicate == "has_headquarters"
    assert fact.object == "San Francisco"
    assert fact.confidence == 0.85
    assert fact.source == CorporateFactSource.ADMIN_STATED
    assert fact.is_active is True
    assert fact.created_by == "user-456"


def test_corporate_fact_to_dict() -> None:
    """Test CorporateFact serialization to dictionary."""
    from src.memory.corporate import CorporateFact, CorporateFactSource

    now = datetime.now(UTC)
    fact = CorporateFact(
        id="test-id",
        company_id="company-123",
        subject="Test Subject",
        predicate="test_predicate",
        object="Test Object",
        confidence=0.75,
        source=CorporateFactSource.EXTRACTED,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    data = fact.to_dict()
    assert data["id"] == "test-id"
    assert data["company_id"] == "company-123"
    assert data["source"] == "extracted"
    assert data["created_at"] == now.isoformat()


def test_corporate_fact_from_dict() -> None:
    """Test CorporateFact deserialization from dictionary."""
    from src.memory.corporate import CorporateFact, CorporateFactSource

    now = datetime.now(UTC)
    data = {
        "id": "test-id",
        "company_id": "company-123",
        "subject": "Test Subject",
        "predicate": "test_predicate",
        "object": "Test Object",
        "confidence": 0.8,
        "source": "aggregated",
        "is_active": True,
        "graphiti_episode_name": "corp:company-123:test-id",
        "created_by": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    fact = CorporateFact.from_dict(data)
    assert fact.id == "test-id"
    assert fact.company_id == "company-123"
    assert fact.source == CorporateFactSource.AGGREGATED
    assert fact.graphiti_episode_name == "corp:company-123:test-id"


def test_corporate_memory_class_exists() -> None:
    """Test CorporateMemory class can be instantiated."""
    from src.memory.corporate import CorporateMemory

    memory = CorporateMemory()
    assert memory is not None
