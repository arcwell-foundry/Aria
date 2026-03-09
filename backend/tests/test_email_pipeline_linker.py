"""Tests for email_pipeline_linker service."""

import pytest
from unittest.mock import MagicMock
from src.utils.email_pipeline_linker import (
    get_pipeline_context_for_email,
    PipelineContext,
    _extract_domain,
)


class TestExtractDomain:
    """Tests for _extract_domain helper."""

    def test_standard_email(self):
        assert _extract_domain("user@example.com") == "example.com"

    def test_uppercase_email(self):
        assert _extract_domain("User@Example.COM") == "example.com"

    def test_subdomain_email(self):
        assert _extract_domain("user@mail.corporate.example.com") == "mail.corporate.example.com"

    def test_invalid_email_no_at(self):
        assert _extract_domain("invalid-email") == ""

    def test_empty_email(self):
        assert _extract_domain("") == ""


class TestGetPipelineContextForEmail:
    """Tests for get_pipeline_context_for_email function."""

    @pytest.mark.asyncio
    async def test_returns_none_for_empty_email(self):
        """Should return None when email is empty."""
        mock_db = MagicMock()
        result = await get_pipeline_context_for_email(
            db=mock_db,
            user_id="test-user-id",
            contact_email=""
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_contact(self):
        """Should return None when no pipeline data exists."""
        mock_db = MagicMock()

        # Mock lead_memory_stakeholders - no match
        stakeholder_chain = MagicMock()
        stakeholder_chain.data = []

        # Mock monitored_entities - no match
        entity_chain = MagicMock()
        entity_chain.data = []

        # Mock memory_semantic - no match
        memory_chain = MagicMock()
        memory_chain.data = []

        # Set up table routing
        def table_router(name):
            mock_table = MagicMock()
            if name == "lead_memory_stakeholders":
                mock_table.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = stakeholder_chain
            elif name == "monitored_entities":
                mock_table.select.return_value.eq.return_value.eq.return_value.contains.return_value.limit.return_value.execute.return_value = entity_chain
            elif name == "memory_semantic":
                mock_table.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = memory_chain
            return mock_table

        mock_db.table = table_router

        result = await get_pipeline_context_for_email(
            db=mock_db,
            user_id="test-user-id",
            contact_email="unknown@random.com"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_matches_domain_to_monitored_entity(self):
        """Should find company via domain match in monitored_entities."""
        mock_db = MagicMock()

        # Mock lead_memory_stakeholders - no match
        stakeholder_chain = MagicMock()
        stakeholder_chain.data = []

        # Mock monitored_entities - match
        entity_chain = MagicMock()
        entity_chain.data = [{
            "entity_name": "Silicon Valley Bank",
            "entity_type": "partner",
            "monitoring_config": {}
        }]

        # Mock lead_memories lookup (after entity match)
        lead_chain = MagicMock()
        lead_chain.data = []

        def table_router(name):
            mock_table = MagicMock()
            if name == "lead_memory_stakeholders":
                mock_table.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = stakeholder_chain
            elif name == "monitored_entities":
                mock_table.select.return_value.eq.return_value.eq.return_value.contains.return_value.limit.return_value.execute.return_value = entity_chain
            elif name == "lead_memories":
                mock_table.select.return_value.eq.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = lead_chain
            return mock_table

        mock_db.table = table_router

        result = await get_pipeline_context_for_email(
            db=mock_db,
            user_id="test-user-id",
            contact_email="ries.mcmillan@svb.com"
        )

        assert result is not None
        assert result.get("company_name") == "Silicon Valley Bank"
        assert result.get("relationship_type") == "partner"
        assert result.get("source") == "monitored_entities"
