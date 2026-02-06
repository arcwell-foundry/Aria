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


def test_get_company_memory_delta_filters_personal_data():
    """Test that get_company_memory_delta only returns corporate facts, never personal data.

    Even if a company has both corporate and personal facts, only corporate facts
    (with sources in _CORPORATE_SOURCES) should be returned in the memory delta.

    Personal sources like 'email_analysis' and 'writing_sample' must be excluded.
    """
    # Mock Supabase client
    mock_db = Mock()

    # Test company and user data
    test_company_id = "test-company-456"
    test_user_id = "user-2-id"

    # Create mixed facts data (both corporate and personal sources)
    facts_data = [
        # Corporate facts (should be included)
        {
            "id": "fact-1",
            "company_id": test_company_id,
            "subject": "Company",
            "predicate": "specializes_in",
            "object": "biologics manufacturing",
            "confidence": 0.95,
            "source": "extracted",
            "is_active": True,
        },
        {
            "id": "fact-2",
            "company_id": test_company_id,
            "subject": "Company",
            "predicate": "has_headquarters",
            "object": "San Francisco, CA",
            "confidence": 0.90,
            "source": "aggregated",
            "is_active": True,
        },
        {
            "id": "fact-3",
            "company_id": test_company_id,
            "subject": "Company",
            "predicate": "founded_in",
            "object": "2015",
            "confidence": 0.85,
            "source": "admin_stated",
            "is_active": True,
        },
        # Personal facts (should NOT appear in results)
        {
            "id": "fact-4",
            "company_id": test_company_id,
            "subject": "User",
            "predicate": "prefers",
            "object": "detailed reports",
            "confidence": 0.90,
            "source": "email_analysis",  # Personal source - should be filtered
            "is_active": True,
        },
        {
            "id": "fact-5",
            "company_id": test_company_id,
            "subject": "User",
            "predicate": "writes_in_style",
            "object": "concise",
            "confidence": 0.95,
            "source": "writing_sample",  # Personal source - should be filtered
            "is_active": True,
        },
    ]

    # Mock the query chain for corporate_memory_facts table
    facts_query = Mock()

    facts_query.select.return_value = facts_query
    facts_query.eq.return_value = facts_query

    # Track which sources were filtered and filter the data accordingly
    filtered_sources = []

    def mock_in_filter(self, sources):
        nonlocal filtered_sources
        filtered_sources = sources
        return facts_query

    facts_query.in_ = mock_in_filter

    # Mock execute to return filtered data (simulate database filtering)
    def mock_execute():
        # Simulate the database filtering by source
        filtered_facts = [
            f for f in facts_data
            if f.get("source") in CrossUserAccelerationService._CORPORATE_SOURCES
        ]
        return Mock(data=filtered_facts)

    facts_query.execute = mock_execute

    # Set up the table() method
    mock_db.table.return_value = facts_query

    # Create service with mocked client
    service = CrossUserAccelerationService(db=mock_db, llm_client=None)

    # Get company memory delta
    result = service.get_company_memory_delta(test_company_id, test_user_id)

    # Verify the query filtered by corporate sources
    assert filtered_sources == list(service._CORPORATE_SOURCES), (
        f"Query should filter by corporate sources, got {filtered_sources}"
    )

    # Verify the result structure
    assert "facts" in result, "Result should include 'facts' key"
    assert "high_confidence_facts" in result, "Result should include 'high_confidence_facts' key"
    assert "domains_covered" in result, "Result should include 'domains_covered' key"
    assert "total_fact_count" in result, "Result should include 'total_fact_count' key"

    # Verify only corporate facts were returned (no personal sources)
    corporate_facts = [f for f in facts_data if f["source"] in service._CORPORATE_SOURCES]
    personal_facts = [f for f in facts_data if f["source"] in service._PERSONAL_SOURCES]

    assert len(result["facts"]) == len(corporate_facts), (
        f"Expected {len(corporate_facts)} facts, got {len(result['facts'])}"
    )
    assert result["total_fact_count"] == len(corporate_facts), (
        f"Expected total_fact_count={len(corporate_facts)}, got {result['total_fact_count']}"
    )

    # Verify no personal sources in results
    sources_in_result = [f["source"] for f in result["facts"]]
    assert "email_analysis" not in sources_in_result, (
        "Personal source 'email_analysis' should not be in results"
    )
    assert "writing_sample" not in sources_in_result, (
        "Personal source 'writing_sample' should not be in results"
    )

    # Verify high_confidence_facts subset
    high_confidence_corporate = [f for f in corporate_facts if f["confidence"] >= 0.8]
    assert len(result["high_confidence_facts"]) == len(high_confidence_corporate), (
        f"Expected {len(high_confidence_corporate)} high-confidence facts, "
        f"got {len(result['high_confidence_facts'])}"
    )

    # Verify all high-confidence facts have confidence >= 0.8
    for fact in result["high_confidence_facts"]:
        assert fact["confidence"] >= 0.8, (
            f"High-confidence fact {fact['id']} has confidence {fact['confidence']}"
        )
