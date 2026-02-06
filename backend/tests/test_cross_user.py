"""Tests for cross-user onboarding acceleration (US-917).

Tests the CrossUserAccelerationService which detects existing Corporate Memory
when user #2+ at a company starts onboarding and recommends step skipping.
"""

import logging
from unittest.mock import Mock

from src.onboarding.cross_user import CompanyCheckResult, CrossUserAccelerationService

logger = logging.getLogger(__name__)


def test_check_company_exists_not_found():
    """Test that checking a non-existent company returns exists=False with full recommendation."""
    # Mock Supabase client
    mock_db = Mock()

    # Mock the query chain - no company found
    mock_query = Mock()
    mock_query.select.return_value = mock_query
    mock_query.eq.return_value = mock_query
    mock_query.maybe_single.return_value = mock_query
    mock_query.execute.return_value = Mock(data=None)

    mock_db.table.return_value = mock_query

    # Create service with mocked client
    service = CrossUserAccelerationService(db=mock_db, llm_client=None)

    # Test with a domain that doesn't exist
    result = service.check_company_exists("nonexistent-company.com")

    # Assert the result indicates company doesn't exist
    assert result.exists is False
    assert result.company_id is None
    assert result.company_name is None
    assert result.richness_score == 0
    assert result.recommendation == "full"


def test_check_company_exists_skip_recommendation():
    """Test that a rich company returns skip recommendation.

    Creates test data with:
    - 40 facts across 7 domains (product, pipeline, leadership, financial,
      manufacturing, partnership, regulatory)
    - 4 documents

    Expected richness calculation:
    - Facts: 40 * 2 = 80, capped at 50
    - Domains: 7 * 10 = 70, capped at 30
    - Documents: 4 * 5 = 20
    - Total: 50 + 30 + 20 = 100 (> 80 threshold for skip)
    """
    # Mock Supabase client
    mock_db = Mock()

    # Test company data
    test_company_id = "rich-company-123"
    test_domain = "rich-corp.com"
    test_company_name = "Rich Corporation"

    # Create facts data (40 facts across 7 domains)
    facts_data = []
    domains = [
        "product",
        "pipeline",
        "leadership",
        "financial",
        "manufacturing",
        "partnership",
        "regulatory",
    ]
    fact_id = 1
    for domain in domains:
        facts_per_domain = 6 if domain != "regulatory" else 4
        for i in range(facts_per_domain):
            facts_data.append({
                "id": f"fact-{fact_id}",
                "company_id": test_company_id,
                "predicate": f"{domain}_predicate_{i}",
                "object": f"{domain}_value_{i}",
            })
            fact_id += 1

    # Track whether we're selecting with count (for facts and documents)
    select_with_count = False

    # Mock the query chain for companies table
    companies_query = Mock()
    companies_query.select.return_value = companies_query
    companies_query.eq.return_value = companies_query
    companies_query.maybe_single.return_value = companies_query
    companies_query.execute.return_value = Mock(data={
        "id": test_company_id,
        "domain": test_domain,
        "name": test_company_name,
    })

    # Mock the query chain for corporate_memory_facts table
    facts_query = Mock()
    facts_query_select_call_count = [0]  # Use list to allow mutation in nested function

    def facts_select(*args, **kwargs):
        facts_query_select_call_count[0] += 1
        nonlocal select_with_count
        select_with_count = "count" in kwargs
        return facts_query

    facts_query.select = facts_select
    facts_query.eq.return_value = facts_query
    facts_query.in_.return_value = facts_query

    def facts_execute():
        if select_with_count:
            result = Mock()
            result.count = 40
            return result
        else:
            result = Mock()
            result.data = facts_data
            return result

    facts_query.execute = facts_execute

    # Mock the query chain for company_documents table
    docs_query = Mock()
    docs_query_select_call_count = [0]

    def docs_select(*args, **kwargs):
        docs_query_select_call_count[0] += 1
        nonlocal select_with_count
        select_with_count = "count" in kwargs
        return docs_query

    docs_query.select = docs_select
    docs_query.eq.return_value = docs_query

    def docs_execute():
        result = Mock()
        result.count = 4
        return result

    docs_query.execute = docs_execute

    # Set up the table() method to return appropriate query mocks
    def table_factory(table_name: str):
        if table_name == "companies":
            return companies_query
        elif table_name == "corporate_memory_facts":
            return facts_query
        elif table_name == "company_documents":
            return docs_query
        return Mock()

    mock_db.table = table_factory

    # Create service with mocked client
    service = CrossUserAccelerationService(db=mock_db, llm_client=None)

    # Test with a rich company domain
    result = service.check_company_exists(test_domain)

    # Assert the result indicates company exists with skip recommendation
    assert result.exists is True
    assert result.company_id == test_company_id
    assert result.company_name == test_company_name
    assert result.richness_score > 80, f"Expected richness > 80, got {result.richness_score}"
    assert result.recommendation == "skip"


def test_check_company_partial_recommendation():
    """Test that a company with moderate richness returns partial recommendation.

    Creates test data with:
    - 15 facts across 3 domains (product, leadership, financial)
    - 1 document

    Expected richness calculation:
    - Facts: 15 * 2 = 30
    - Domains: 3 * 10 = 30
    - Documents: 1 * 5 = 5
    - Total: 30 + 30 + 5 = 65 (within 30-80 range for partial)
    """
    # Mock Supabase client
    mock_db = Mock()

    # Test company data
    test_company_id = "partial-company-123"
    test_domain = "partial-corp.com"
    test_company_name = "Partial Corporation"

    # Create facts data (15 facts across 3 domains)
    facts_data = []
    domains = ["product", "leadership", "financial"]
    fact_id = 1
    for domain in domains:
        for i in range(5):
            facts_data.append({
                "id": f"fact-{fact_id}",
                "company_id": test_company_id,
                "predicate": f"{domain}_predicate_{i}",
                "object": f"{domain}_value_{i}",
            })
            fact_id += 1

    # Track whether we're selecting with count (for facts and documents)
    select_with_count = False

    # Mock the query chain for companies table
    companies_query = Mock()
    companies_query.select.return_value = companies_query
    companies_query.eq.return_value = companies_query
    companies_query.maybe_single.return_value = companies_query
    companies_query.execute.return_value = Mock(data={
        "id": test_company_id,
        "domain": test_domain,
        "name": test_company_name,
    })

    # Mock the query chain for corporate_memory_facts table
    facts_query = Mock()
    facts_query_select_call_count = [0]

    def facts_select(*args, **kwargs):
        facts_query_select_call_count[0] += 1
        nonlocal select_with_count
        select_with_count = "count" in kwargs
        return facts_query

    facts_query.select = facts_select
    facts_query.eq.return_value = facts_query
    facts_query.in_.return_value = facts_query

    def facts_execute():
        if select_with_count:
            result = Mock()
            result.count = 15
            return result
        else:
            result = Mock()
            result.data = facts_data
            return result

    facts_query.execute = facts_execute

    # Mock the query chain for company_documents table
    docs_query = Mock()
    docs_query_select_call_count = [0]

    def docs_select(*args, **kwargs):
        docs_query_select_call_count[0] += 1
        nonlocal select_with_count
        select_with_count = "count" in kwargs
        return docs_query

    docs_query.select = docs_select
    docs_query.eq.return_value = docs_query

    def docs_execute():
        result = Mock()
        result.count = 1
        return result

    docs_query.execute = docs_execute

    # Set up the table() method to return appropriate query mocks
    def table_factory(table_name: str):
        if table_name == "companies":
            return companies_query
        elif table_name == "corporate_memory_facts":
            return facts_query
        elif table_name == "company_documents":
            return docs_query
        return Mock()

    mock_db.table = table_factory

    # Create service with mocked client
    service = CrossUserAccelerationService(db=mock_db, llm_client=None)

    # Test with a partial-richness company domain
    result = service.check_company_exists(test_domain)

    # Assert the result indicates company exists with partial recommendation
    assert result.exists is True
    assert result.company_id == test_company_id
    assert result.company_name == test_company_name
    assert 30 <= result.richness_score <= 80, (
        f"Expected richness between 30-80, got {result.richness_score}"
    )
    assert result.recommendation == "partial"


def test_check_company_low_richness_full_recommendation():
    """Test that a company with minimal richness returns full recommendation.

    Creates test data with:
    - 5 facts with 1 distinct predicate (product)
    - 0 documents

    Expected richness calculation:
    - Facts: 5 * 2 = 10
    - Domains: 1 distinct predicate * 10 = 10
    - Documents: 0 * 5 = 0
    - Total: 10 + 10 + 0 = 20 (< 30 threshold for full)
    """
    # Mock Supabase client
    mock_db = Mock()

    # Test company data
    test_company_id = "minimal-company-123"
    test_domain = "minimal-corp.com"
    test_company_name = "Minimal Corporation"

    # Create facts data (5 facts with same predicate - to test domain coverage correctly)
    facts_data = []
    for i in range(5):
        facts_data.append({
            "id": f"fact-{i + 1}",
            "company_id": test_company_id,
            "predicate": "product_predicate",  # Same predicate for all facts
            "object": f"product_value_{i}",
        })

    # Track whether we're selecting with count (for facts and documents)
    select_with_count = False

    # Mock the query chain for companies table
    companies_query = Mock()
    companies_query.select.return_value = companies_query
    companies_query.eq.return_value = companies_query
    companies_query.maybe_single.return_value = companies_query
    companies_query.execute.return_value = Mock(data={
        "id": test_company_id,
        "domain": test_domain,
        "name": test_company_name,
    })

    # Mock the query chain for corporate_memory_facts table
    facts_query = Mock()
    facts_query_select_call_count = [0]

    def facts_select(*args, **kwargs):
        facts_query_select_call_count[0] += 1
        nonlocal select_with_count
        select_with_count = "count" in kwargs
        return facts_query

    facts_query.select = facts_select
    facts_query.eq.return_value = facts_query
    facts_query.in_.return_value = facts_query

    def facts_execute():
        if select_with_count:
            result = Mock()
            result.count = 5
            return result
        else:
            result = Mock()
            result.data = facts_data
            return result

    facts_query.execute = facts_execute

    # Mock the query chain for company_documents table
    docs_query = Mock()
    docs_query_select_call_count = [0]

    def docs_select(*args, **kwargs):
        docs_query_select_call_count[0] += 1
        nonlocal select_with_count
        select_with_count = "count" in kwargs
        return docs_query

    docs_query.select = docs_select
    docs_query.eq.return_value = docs_query

    def docs_execute():
        result = Mock()
        result.count = 0
        return result

    docs_query.execute = docs_execute

    # Set up the table() method to return appropriate query mocks
    def table_factory(table_name: str):
        if table_name == "companies":
            return companies_query
        elif table_name == "corporate_memory_facts":
            return facts_query
        elif table_name == "company_documents":
            return docs_query
        return Mock()

    mock_db.table = table_factory

    # Create service with mocked client
    service = CrossUserAccelerationService(db=mock_db, llm_client=None)

    # Test with a minimal-richness company domain
    result = service.check_company_exists(test_domain)

    # Assert the result indicates company exists with full recommendation
    assert result.exists is True
    assert result.company_id == test_company_id
    assert result.company_name == test_company_name
    assert result.richness_score < 30, f"Expected richness < 30, got {result.richness_score}"
    assert result.recommendation == "full"
