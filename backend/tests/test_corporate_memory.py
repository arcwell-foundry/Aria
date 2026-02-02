"""Tests for corporate memory module."""

from datetime import UTC, datetime


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


# Isolation and Privacy Tests (Task 6)


def test_graphiti_episode_name_includes_company_namespace() -> None:
    """Test that Graphiti episode names use company namespace for isolation."""
    from src.memory.corporate import CorporateMemory

    memory = CorporateMemory()
    episode_name = memory._get_graphiti_episode_name("company-abc", "fact-123")

    # Should use corp: prefix with company_id for namespace isolation
    assert episode_name == "corp:company-abc:fact-123"
    assert "company-abc" in episode_name


def test_corporate_fact_excludes_user_identifiable_data() -> None:
    """Test that CorporateFact can be created without user-identifiable info."""
    from src.memory.corporate import CorporateFact, CorporateFactSource

    now = datetime.now(UTC)

    # Create fact without any user ID
    fact = CorporateFact(
        id="test-id",
        company_id="company-123",
        subject="Market Trend",
        predicate="shows_growth",
        object="15% YoY",
        confidence=0.8,
        source=CorporateFactSource.AGGREGATED,
        is_active=True,
        created_by=None,  # System-generated, no user
        created_at=now,
        updated_at=now,
    )

    # Fact should not require user_id
    assert fact.created_by is None

    # to_dict should not include any user_id field
    data = fact.to_dict()
    assert "user_id" not in data


def test_fact_body_does_not_contain_user_info() -> None:
    """Test that Graphiti fact body excludes user-identifiable data."""
    from src.memory.corporate import CorporateFact, CorporateFactSource, CorporateMemory

    memory = CorporateMemory()
    now = datetime.now(UTC)

    fact = CorporateFact(
        id="test-id",
        company_id="company-123",
        subject="Industry Trend",
        predicate="affects",
        object="Market Size",
        confidence=0.75,
        source=CorporateFactSource.EXTRACTED,
        is_active=True,
        created_by="user-456",  # Even if created_by is set
        created_at=now,
        updated_at=now,
    )

    body = memory._build_fact_body(fact)

    # Body should contain company_id (needed for namespace)
    assert "company-123" in body

    # Body should NOT contain user_id or created_by
    assert "user-456" not in body
    assert "created_by" not in body.lower()
    assert "user_id" not in body.lower()


def test_corporate_source_confidence_defaults() -> None:
    """Test that corporate fact sources have appropriate default confidence."""
    from src.memory.corporate import CORPORATE_SOURCE_CONFIDENCE, CorporateFactSource

    # Admin-stated should have highest confidence
    assert CORPORATE_SOURCE_CONFIDENCE[CorporateFactSource.ADMIN_STATED] >= 0.9

    # Aggregated should be higher than extracted (more data points)
    assert (
        CORPORATE_SOURCE_CONFIDENCE[CorporateFactSource.AGGREGATED]
        > CORPORATE_SOURCE_CONFIDENCE[CorporateFactSource.EXTRACTED]
    )

    # All confidence values should be in valid range
    for source, confidence in CORPORATE_SOURCE_CONFIDENCE.items():
        assert 0.0 <= confidence <= 1.0, f"Invalid confidence for {source}"
