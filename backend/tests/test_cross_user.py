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
