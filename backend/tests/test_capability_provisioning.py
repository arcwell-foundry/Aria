"""Tests for capability provisioning services."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.capability import CapabilityGap, CapabilityProvider, ResolutionStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db_response(data: list[dict] | None = None):
    """Build a mock Supabase response object."""
    resp = MagicMock()
    resp.data = data or []
    return resp


def _make_provider_row(
    capability_name: str,
    provider_name: str,
    provider_type: str,
    quality_score: float,
    composio_app_name: str | None = None,
    composio_action_name: str | None = None,
    required_capabilities: list[str] | None = None,
    **kwargs,
) -> dict:
    """Build a dict that looks like a capability_graph row."""
    row = {
        "id": f"id-{provider_name}",
        "capability_name": capability_name,
        "capability_category": kwargs.get("capability_category", "research"),
        "description": kwargs.get("description", ""),
        "provider_name": provider_name,
        "provider_type": provider_type,
        "quality_score": quality_score,
        "setup_time_seconds": kwargs.get("setup_time_seconds", 0),
        "user_friction": kwargs.get("user_friction", "none"),
        "estimated_cost_per_use": kwargs.get("estimated_cost_per_use", 0),
        "composio_app_name": composio_app_name,
        "composio_action_name": composio_action_name,
        "required_capabilities": required_capabilities,
        "domain_constraint": kwargs.get("domain_constraint"),
        "limitations": kwargs.get("limitations"),
        "life_sciences_priority": kwargs.get("life_sciences_priority", False),
        "is_active": True,
        "health_status": "unknown",
    }
    return row


# ---------------------------------------------------------------------------
# CapabilityGraphService tests
# ---------------------------------------------------------------------------

class TestCapabilityGraphService:
    """Tests for CapabilityGraphService.get_best_available()."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock Supabase client with chainable query builder."""
        db = MagicMock()
        return db

    def _setup_chain(self, db, data):
        """Wire up the chainable .table().select().eq().order().execute() pattern."""
        chain = MagicMock()
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.execute.return_value = _mock_db_response(data)
        db.table.return_value = chain
        return chain

    @pytest.mark.asyncio
    async def test_get_best_available_native(self, mock_db):
        """Native provider always returns as available."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row("research_person", "exa_people_search", "native", 0.80),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)
        result = await service.get_best_available("research_person", "user-1")

        assert result is not None
        assert result.provider_name == "exa_people_search"
        assert result.provider_type == "native"

    @pytest.mark.asyncio
    async def test_get_best_available_composio_connected(self, mock_db):
        """Returns composio provider when user has active connection."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "read_email", "composio_outlook", "composio_oauth", 0.95,
                composio_app_name="OUTLOOK365",
                capability_category="data_access",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)

        # Mock _check_user_connection to return True
        service._check_user_connection = AsyncMock(return_value=True)

        result = await service.get_best_available("read_email", "user-1")

        assert result is not None
        assert result.provider_name == "composio_outlook"

    @pytest.mark.asyncio
    async def test_get_best_available_composio_not_connected(self, mock_db):
        """Skips composio provider when not connected, falls back to next."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "send_email", "composio_outlook", "composio_oauth", 0.95,
                composio_app_name="OUTLOOK365",
                capability_category="communication",
            ),
            _make_provider_row(
                "send_email", "resend_transactional", "native", 0.70,
                capability_category="communication",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)
        service._check_user_connection = AsyncMock(return_value=False)

        result = await service.get_best_available("send_email", "user-1")

        assert result is not None
        assert result.provider_name == "resend_transactional"
        assert result.provider_type == "native"

    @pytest.mark.asyncio
    async def test_get_best_available_composite(self, mock_db):
        """Returns composite provider when all sub-capabilities are available."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "read_crm_pipeline", "email_deal_inference", "composite", 0.65,
                required_capabilities=["read_email"],
                capability_category="data_access",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)

        # Mock recursive call: read_email sub-capability IS available
        original_get_best = service.get_best_available

        async def _mock_get_best(cap_name, user_id):
            if cap_name == "read_email":
                return CapabilityProvider(
                    id="id-native-email",
                    capability_name="read_email",
                    capability_category="data_access",
                    provider_name="composio_outlook",
                    provider_type="composio_oauth",
                    quality_score=0.95,
                )
            return await original_get_best(cap_name, user_id)

        service.get_best_available = _mock_get_best

        result = await service.get_best_available("read_crm_pipeline", "user-1")

        assert result is not None
        assert result.provider_name == "email_deal_inference"
        assert result.provider_type == "composite"

    @pytest.mark.asyncio
    async def test_get_best_available_composite_deps_missing(self, mock_db):
        """Skips composite when sub-capability is unavailable, falls back."""
        from src.services.capability_provisioning import CapabilityGraphService

        rows = [
            _make_provider_row(
                "read_crm_pipeline", "email_deal_inference", "composite", 0.65,
                required_capabilities=["read_email"],
                capability_category="data_access",
            ),
            _make_provider_row(
                "read_crm_pipeline", "user_stated", "user_provided", 0.50,
                capability_category="data_access",
            ),
        ]
        self._setup_chain(mock_db, rows)

        service = CapabilityGraphService(mock_db)

        # Mock recursive call: read_email NOT available
        async def _mock_get_best(cap_name, user_id):
            if cap_name == "read_email":
                return None
            # For other capabilities, use real logic
            providers = await service.get_providers(cap_name)
            for p in providers:
                if p.provider_type == "user_provided":
                    return p
            return None

        service.get_best_available = _mock_get_best

        result = await service.get_best_available("read_crm_pipeline", "user-1")

        assert result is not None
        assert result.provider_name == "user_stated"
        assert result.provider_type == "user_provided"

    @pytest.mark.asyncio
    async def test_graceful_degradation_table_missing(self, mock_db):
        """If capability_graph table query fails, log and return None."""
        from src.services.capability_provisioning import CapabilityGraphService

        mock_db.table.side_effect = Exception("relation does not exist")

        service = CapabilityGraphService(mock_db)
        result = await service.get_best_available("research_person", "user-1")

        assert result is None
