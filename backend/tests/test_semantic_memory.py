"""Tests for semantic memory module."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from src.memory.semantic import FactSource, SemanticFact, SemanticMemory


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


def test_semantic_fact_is_valid_returns_true_for_active_fact() -> None:
    """Test is_valid returns True for facts within validity window."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=30),
        valid_to=now + timedelta(days=30),
    )

    assert fact.is_valid() is True
    assert fact.is_valid(as_of=now) is True


def test_semantic_fact_is_valid_returns_false_for_invalidated() -> None:
    """Test is_valid returns False for invalidated facts."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=30),
        invalidated_at=now - timedelta(days=1),
        invalidation_reason="superseded",
    )

    assert fact.is_valid() is False


def test_semantic_fact_is_valid_returns_false_for_expired() -> None:
    """Test is_valid returns False for facts past valid_to."""
    now = datetime.now(UTC)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=60),
        valid_to=now - timedelta(days=30),
    )

    assert fact.is_valid() is False


def test_semantic_fact_is_valid_with_as_of_date() -> None:
    """Test is_valid checks against specific point in time."""
    now = datetime.now(UTC)
    past = now - timedelta(days=15)
    fact = SemanticFact(
        id="fact-123",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now - timedelta(days=30),
        valid_to=now - timedelta(days=10),
    )

    # Valid at 15 days ago (within window)
    assert fact.is_valid(as_of=past) is True
    # Invalid now (past valid_to)
    assert fact.is_valid() is False


def test_semantic_fact_contradicts_detects_same_subject_predicate() -> None:
    """Test contradicts detects facts with same subject-predicate but different object."""
    now = datetime.now(UTC)
    fact1 = SemanticFact(
        id="fact-1",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )
    fact2 = SemanticFact(
        id="fact-2",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Other Corp",
        confidence=0.90,
        source=FactSource.EXTRACTED,
        valid_from=now,
    )

    assert fact1.contradicts(fact2) is True
    assert fact2.contradicts(fact1) is True


def test_semantic_fact_contradicts_returns_false_for_different_predicate() -> None:
    """Test contradicts returns False for different predicates."""
    now = datetime.now(UTC)
    fact1 = SemanticFact(
        id="fact-1",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )
    fact2 = SemanticFact(
        id="fact-2",
        user_id="user-456",
        subject="John",
        predicate="lives_in",
        object="New York",
        confidence=0.90,
        source=FactSource.EXTRACTED,
        valid_from=now,
    )

    assert fact1.contradicts(fact2) is False


def test_semantic_fact_contradicts_returns_false_for_same_object() -> None:
    """Test contradicts returns False when objects are the same."""
    now = datetime.now(UTC)
    fact1 = SemanticFact(
        id="fact-1",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.95,
        source=FactSource.USER_STATED,
        valid_from=now,
    )
    fact2 = SemanticFact(
        id="fact-2",
        user_id="user-456",
        subject="John",
        predicate="works_at",
        object="Acme",
        confidence=0.90,
        source=FactSource.EXTRACTED,
        valid_from=now,
    )

    assert fact1.contradicts(fact2) is False


def test_semantic_memory_has_required_methods() -> None:
    """Test SemanticMemory class has required interface methods."""
    memory = SemanticMemory()

    # Check required async methods exist
    assert hasattr(memory, "add_fact")
    assert hasattr(memory, "get_fact")
    assert hasattr(memory, "get_facts_about")
    assert hasattr(memory, "search_facts")
    assert hasattr(memory, "invalidate_fact")
    assert hasattr(memory, "delete_fact")