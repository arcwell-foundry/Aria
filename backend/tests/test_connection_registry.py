"""Tests for ConnectionRegistryService.

Validates registration, caching, dual-write, disconnect, and failure recording.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Patch paths
_SUPABASE = "src.integrations.connection_registry.SupabaseClient"
_INT_SERVICE = "src.integrations.service.get_integration_service"
_INT_DOMAIN = "src.integrations.domain.IntegrationType"


def _mock_supabase_chain(return_data: Any = None) -> MagicMock:
    """Build a chained Supabase mock: table().select().eq()...execute()."""
    mock_client = MagicMock()
    mock_result = MagicMock()
    mock_result.data = return_data

    # Support arbitrary chaining
    chain = MagicMock()
    chain.execute.return_value = mock_result
    chain.eq.return_value = chain
    chain.limit.return_value = chain
    chain.maybe_single.return_value = chain
    chain.select.return_value = chain
    chain.insert.return_value = chain
    chain.update.return_value = chain
    chain.upsert.return_value = chain
    chain.rpc.return_value = chain

    mock_client.table.return_value = chain
    mock_client.rpc.return_value = chain
    return mock_client


@pytest.mark.asyncio
class TestConnectionRegistry:
    """Unit tests for ConnectionRegistryService."""

    async def test_register_connection_creates_row(self) -> None:
        """register_connection upserts into user_connections."""
        with patch(_SUPABASE) as mock_cls:
            row = {
                "id": "conn-1",
                "user_id": "u1",
                "toolkit_slug": "gmail",
                "status": "active",
            }
            mock_db = _mock_supabase_chain([row])
            mock_cls.get_client.return_value = mock_db

            from src.integrations.connection_registry import ConnectionRegistryService

            registry = ConnectionRegistryService()

            # Suppress dual-write (tested separately)
            with patch.object(registry, "_dual_write_integration", new_callable=AsyncMock):
                result = await registry.register_connection(
                    user_id="u1",
                    toolkit_slug="gmail",
                    composio_connection_id="conn-id-123",
                    status="active",
                )

            assert result["toolkit_slug"] == "gmail"
            assert result["status"] == "active"
            # Verify upsert was called on user_connections table
            mock_db.table.assert_any_call("user_connections")

    async def test_register_connection_dual_writes_to_user_integrations(self) -> None:
        """register_connection calls IntegrationService.create_integration."""
        with (
            patch(_SUPABASE) as mock_cls,
            patch(_INT_SERVICE) as mock_svc_fn,
        ):
            row = {"id": "conn-1", "user_id": "u1", "toolkit_slug": "gmail", "status": "active"}
            mock_db = _mock_supabase_chain([row])
            mock_cls.get_client.return_value = mock_db

            mock_svc = MagicMock()
            mock_svc.get_integration = AsyncMock(return_value=None)
            mock_svc.create_integration = AsyncMock(return_value={"id": "int-1"})
            mock_svc_fn.return_value = mock_svc

            from src.integrations.connection_registry import ConnectionRegistryService

            registry = ConnectionRegistryService()
            await registry.register_connection(
                user_id="u1",
                toolkit_slug="gmail",
                composio_connection_id="conn-id-123",
                account_email="test@example.com",
                status="active",
            )

            mock_svc.create_integration.assert_called_once()
            call_kwargs = mock_svc.create_integration.call_args
            assert call_kwargs[1]["account_email"] == "test@example.com"

    async def test_get_connection_returns_active(self) -> None:
        """get_connection queries user_connections with status=active."""
        with patch(_SUPABASE) as mock_cls:
            row = {
                "id": "conn-1",
                "user_id": "u1",
                "toolkit_slug": "gmail",
                "status": "active",
                "composio_connection_id": "cid-1",
            }
            mock_db = _mock_supabase_chain(row)  # maybe_single returns dict
            mock_cls.get_client.return_value = mock_db

            from src.integrations.connection_registry import ConnectionRegistryService

            registry = ConnectionRegistryService()
            result = await registry.get_connection("u1", "gmail")

            assert result is not None
            assert result["toolkit_slug"] == "gmail"

    async def test_get_connection_cache_hit(self) -> None:
        """Second call returns from cache, not DB."""
        with patch(_SUPABASE) as mock_cls:
            row = {"id": "conn-1", "user_id": "u1", "toolkit_slug": "gmail", "status": "active"}
            mock_db = _mock_supabase_chain(row)
            mock_cls.get_client.return_value = mock_db

            from src.integrations.connection_registry import ConnectionRegistryService

            registry = ConnectionRegistryService()

            # First call — DB hit
            await registry.get_connection("u1", "gmail")
            # Second call — cache hit
            await registry.get_connection("u1", "gmail")

            # table() should only be called once for user_connections select
            user_conn_calls = [
                c for c in mock_db.table.call_args_list
                if c[0][0] == "user_connections"
            ]
            assert len(user_conn_calls) == 1

    async def test_disconnect_sets_status(self) -> None:
        """disconnect updates status to 'disconnected'."""
        with patch(_SUPABASE) as mock_cls:
            mock_db = _mock_supabase_chain([])
            mock_cls.get_client.return_value = mock_db

            from src.integrations.connection_registry import ConnectionRegistryService

            registry = ConnectionRegistryService()
            await registry.disconnect("u1", "gmail")

            # Verify update was called with disconnected status
            chain = mock_db.table.return_value
            chain.update.assert_called_once()
            update_data = chain.update.call_args[0][0]
            assert update_data["status"] == "disconnected"

    async def test_record_failure_calls_rpc(self) -> None:
        """record_failure calls increment_connection_failure_count RPC."""
        with patch(_SUPABASE) as mock_cls:
            mock_db = _mock_supabase_chain(None)
            # RPC returns the new count
            rpc_result = MagicMock()
            rpc_result.data = 2
            rpc_chain = MagicMock()
            rpc_chain.execute.return_value = rpc_result
            mock_db.rpc.return_value = rpc_chain

            mock_cls.get_client.return_value = mock_db

            from src.integrations.connection_registry import ConnectionRegistryService

            registry = ConnectionRegistryService()
            count = await registry.record_failure("u1", "gmail")

            assert count == 2
            mock_db.rpc.assert_called_once_with(
                "increment_connection_failure_count",
                {"p_user_id": "u1", "p_toolkit_slug": "gmail"},
            )

    async def test_cache_invalidation_on_register(self) -> None:
        """register_connection invalidates the cache for that key."""
        with patch(_SUPABASE) as mock_cls:
            row = {"id": "conn-1", "user_id": "u1", "toolkit_slug": "gmail", "status": "active"}
            mock_db = _mock_supabase_chain([row])
            mock_cls.get_client.return_value = mock_db

            from src.integrations.connection_registry import ConnectionRegistryService

            registry = ConnectionRegistryService()

            # Pre-populate cache
            registry._cache["u1:gmail"] = {"old": "data"}

            with patch.object(registry, "_dual_write_integration", new_callable=AsyncMock):
                await registry.register_connection(
                    user_id="u1", toolkit_slug="gmail", status="active"
                )

            # Cache should be invalidated (key removed)
            assert "u1:gmail" not in registry._cache
