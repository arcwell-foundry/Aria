"""Tests for corporate memory API endpoints."""

import pytest


def test_create_corporate_fact_request_model() -> None:
    """Test CreateCorporateFactRequest model validation."""
    from src.api.routes.memory import CreateCorporateFactRequest

    request = CreateCorporateFactRequest(
        subject="Acme Corp",
        predicate="has_industry",
        object="Technology",
        source="admin_stated",
        confidence=0.9,
    )
    assert request.subject == "Acme Corp"
    assert request.predicate == "has_industry"
    assert request.confidence == 0.9


def test_corporate_fact_response_model() -> None:
    """Test CorporateFactResponse model structure."""
    from datetime import UTC, datetime

    from src.api.routes.memory import CorporateFactResponse

    response = CorporateFactResponse(
        id="test-id",
        company_id="company-123",
        subject="Test",
        predicate="test_pred",
        object="Value",
        confidence=0.8,
        source="extracted",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    assert response.id == "test-id"


def test_create_corporate_fact_response_model() -> None:
    """Test CreateCorporateFactResponse model."""
    from src.api.routes.memory import CreateCorporateFactResponse

    response = CreateCorporateFactResponse(id="fact-123")
    assert response.id == "fact-123"
    assert response.message == "Corporate fact created successfully"
