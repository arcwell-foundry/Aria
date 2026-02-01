"""Tests for semantic memory module."""

import json
from datetime import UTC, datetime

import pytest

from src.memory.semantic import FactSource, SemanticFact


def test_fact_source_enum_values() -> None:
    """Test FactSource enum has expected values."""
    assert FactSource.USER_STATED.value == "user_stated"
    assert FactSource.EXTRACTED.value == "extracted"
    assert FactSource.INFERRED.value == "inferred"
    assert FactSource.CRM_IMPORT.value == "crm_import"
    assert FactSource.WEB_RESEARCH.value == "web_research"


def test_semantic_fact_initialization() -> None:
    """Test SemanticFact initializes with required fields."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John Doe",
        predicate="works_at",
        object="Acme Corp",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )

    assert fact.id == "fact-123"
    assert fact.user_id == "user-456"
    assert fact.subject == "John Doe"
    assert fact.predicate == "works_at"
    assert fact.object == "Acme Corp"
    assert fact.confidence == 0.95
    assert fact.source == FactSource.USER_STATED
    assert fact.valid_from == now
    assert fact.valid_to is None
    assert fact.invalidated_at is None
    assert fact.invalidation_reason is None


def test_semantic_fact_with_all_fields() -> None:
    """Test SemanticFact works with all optional fields."""
    now = datetime.now(UTC)
    later = datetime(2026, 12, 31, tzinfo=UTC)
    fact = SemanticFact(
        id="fact-124",
        user_id="user-456",
        subject="Jane Smith",
        predicate="title",
        object="VP of Sales",
        confidence=0.80,
        source=FactSource.CRM_IMPORT,
        valid_from=now,
        valid_to=later,
        invalidated_at=None,
        invalidation_reason=None,
    )

    assert fact.id == "fact-124"
    assert fact.valid_to == later


def test_semantic_fact_to_dict_serializes_correctly() -> None:
    """Test SemanticFact.to_dict returns a serializable dictionary."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John Doe",
        predicate="works_at",
        object="Acme Corp",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )

    data = fact.to_dict()

    assert data["id"] == "fact-123"
    assert data["user_id"] == "user-456"
    assert data["subject"] == "John Doe"
    assert data["predicate"] == "works_at"
    assert data["object"] == "Acme Corp"
    assert data["confidence"] == 0.95
    assert data["source"] == "user_stated"
    assert data["valid_from"] == now.isoformat()
    assert data["valid_to"] is None
    assert data["invalidated_at"] is None
    assert data["invalidation_reason"] is None

    # Verify JSON serializable
    json_str = json.dumps(data)
    assert isinstance(json_str, str)


def test_semantic_fact_from_dict_deserializes_correctly() -> None:
    """Test SemanticFact.from_dict creates SemanticFact from dictionary."""
    now = datetime.now(UTC)
    data = {
        "id": "fact-123",
        "user_id": "user-456",
        "subject": "Jane Smith",
        "predicate": "title",
        "object": "CEO",
        "confidence": 0.90,
        "source": "crm_import",
        "valid_from": now.isoformat(),
        "valid_to": None,
        "invalidated_at": None,
        "invalidation_reason": None,
    }

    fact = SemanticFact.from_dict(data)

    assert fact.id == "fact-123"
    assert fact.user_id == "user-456"
    assert fact.subject == "Jane Smith"
    assert fact.predicate == "title"
    assert fact.object == "CEO"
    assert fact.confidence == 0.90
    assert fact.source == FactSource.CRM_IMPORT
    assert fact.valid_from == now
    assert fact.valid_to is None
