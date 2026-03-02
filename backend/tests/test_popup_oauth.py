"""Tests for popup OAuth endpoints.

Validates the auth-url-popup and oauth/callback endpoints.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Patch paths
_OAUTH = "src.api.routes.integrations.get_oauth_client"
_REGISTRY = "src.api.routes.integrations.get_connection_registry"
_INT_SERVICE = "src.api.routes.integrations.get_integration_service"
_WS_MANAGER = "src.core.ws.ws_manager"


def _make_app() -> FastAPI:
    """Create a minimal FastAPI app with the integrations router."""
    from src.api.routes.integrations import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


def _mock_user(user_id: str = "test-user-123") -> MagicMock:
    mock = MagicMock()
    mock.id = user_id
    return mock


@pytest.mark.asyncio
class TestAuthUrlPopup:
    """Tests for POST /{integration_type}/auth-url-popup."""

    async def test_auth_url_popup_returns_url(self) -> None:
        """Endpoint returns authorization_url, integration_type, display_name."""
        with (
            patch(_OAUTH) as mock_oauth_fn,
            patch(_REGISTRY) as mock_registry_fn,
            patch("src.api.routes.integrations.CurrentUser", _mock_user()),
        ):
            mock_oauth = MagicMock()
            mock_oauth.generate_auth_url_with_connection_id = AsyncMock(
                return_value=("https://oauth.example.com/auth", "conn-123")
            )
            mock_oauth_fn.return_value = mock_oauth

            mock_registry = MagicMock()
            mock_registry.register_connection = AsyncMock(return_value={"id": "row-1"})
            mock_registry_fn.return_value = mock_registry

            app = _make_app()

            # Override auth dependency
            from src.api.deps import get_current_user

            app.dependency_overrides[get_current_user] = lambda: _mock_user()

            client = TestClient(app)
            resp = client.post("/api/v1/integrations/gmail/auth-url-popup")

            assert resp.status_code == 200
            body = resp.json()
            assert body["authorization_url"] == "https://oauth.example.com/auth"
            assert body["integration_type"] == "gmail"
            assert "display_name" in body

    async def test_auth_url_popup_creates_pending_connection(self) -> None:
        """Endpoint creates a pending connection row in the registry."""
        with (
            patch(_OAUTH) as mock_oauth_fn,
            patch(_REGISTRY) as mock_registry_fn,
        ):
            mock_oauth = MagicMock()
            mock_oauth.generate_auth_url_with_connection_id = AsyncMock(
                return_value=("https://oauth.example.com/auth", "conn-456")
            )
            mock_oauth_fn.return_value = mock_oauth

            mock_registry = MagicMock()
            mock_registry.register_connection = AsyncMock(return_value={"id": "row-1"})
            mock_registry_fn.return_value = mock_registry

            app = _make_app()

            from src.api.deps import get_current_user

            app.dependency_overrides[get_current_user] = lambda: _mock_user()

            client = TestClient(app)
            client.post("/api/v1/integrations/gmail/auth-url-popup")

            mock_registry.register_connection.assert_called_once()
            call_kwargs = mock_registry.register_connection.call_args[1]
            assert call_kwargs["status"] == "pending"
            assert call_kwargs["composio_connection_id"] == "conn-456"


@pytest.mark.asyncio
class TestOAuthCallback:
    """Tests for GET /oauth/callback."""

    async def test_oauth_callback_returns_html_with_postmessage(self) -> None:
        """Callback returns HTML containing postMessage script."""
        with (
            patch(_OAUTH) as mock_oauth_fn,
            patch(_REGISTRY) as mock_registry_fn,
        ):
            mock_oauth = MagicMock()
            mock_oauth.exchange_code_for_connection = AsyncMock(
                return_value={"connection_id": "conn-789", "account_email": "user@test.com"}
            )
            mock_oauth_fn.return_value = mock_oauth

            mock_registry = MagicMock()
            mock_registry.lookup_by_composio_connection_id = AsyncMock(
                return_value={
                    "id": "row-1",
                    "user_id": "u1",
                    "toolkit_slug": "gmail",
                    "status": "pending",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            mock_registry.register_connection = AsyncMock(return_value={"id": "row-1"})
            mock_registry_fn.return_value = mock_registry

            app = _make_app()
            client = TestClient(app)

            # Patch ws_manager to avoid real WS send
            with patch("src.core.ws.ws_manager") as mock_ws:
                mock_ws.send_integration_connected = AsyncMock()
                resp = client.get(
                    "/api/v1/integrations/oauth/callback",
                    params={"connected_account_id": "conn-789", "integration_type": "gmail"},
                )

            assert resp.status_code == 200
            assert "postMessage" in resp.text
            assert "aria_oauth_success" in resp.text

    async def test_oauth_callback_activates_connection(self) -> None:
        """Callback calls register_connection with status='active'."""
        with (
            patch(_OAUTH) as mock_oauth_fn,
            patch(_REGISTRY) as mock_registry_fn,
        ):
            mock_oauth = MagicMock()
            mock_oauth.exchange_code_for_connection = AsyncMock(
                return_value={"connection_id": "conn-789", "account_email": "user@test.com"}
            )
            mock_oauth_fn.return_value = mock_oauth

            mock_registry = MagicMock()
            mock_registry.lookup_by_composio_connection_id = AsyncMock(
                return_value={
                    "id": "row-1",
                    "user_id": "u1",
                    "toolkit_slug": "gmail",
                    "status": "pending",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            mock_registry.register_connection = AsyncMock(return_value={"id": "row-1"})
            mock_registry_fn.return_value = mock_registry

            app = _make_app()
            client = TestClient(app)

            with patch("src.core.ws.ws_manager") as mock_ws:
                mock_ws.send_integration_connected = AsyncMock()
                client.get(
                    "/api/v1/integrations/oauth/callback",
                    params={"connected_account_id": "conn-789", "integration_type": "gmail"},
                )

            # Find the call that activates (status='active')
            active_calls = [
                c for c in mock_registry.register_connection.call_args_list
                if c[1].get("status") == "active"
            ]
            assert len(active_calls) == 1

    async def test_oauth_callback_sends_ws_event(self) -> None:
        """Callback sends integration.connected WS event."""
        with (
            patch(_OAUTH) as mock_oauth_fn,
            patch(_REGISTRY) as mock_registry_fn,
        ):
            mock_oauth = MagicMock()
            mock_oauth.exchange_code_for_connection = AsyncMock(
                return_value={"connection_id": "conn-789", "account_email": "user@test.com"}
            )
            mock_oauth_fn.return_value = mock_oauth

            mock_registry = MagicMock()
            mock_registry.lookup_by_composio_connection_id = AsyncMock(
                return_value={
                    "id": "row-1",
                    "user_id": "u1",
                    "toolkit_slug": "gmail",
                    "status": "pending",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            mock_registry.register_connection = AsyncMock(return_value={"id": "row-1"})
            mock_registry_fn.return_value = mock_registry

            app = _make_app()
            client = TestClient(app)

            with patch("src.core.ws.ws_manager") as mock_ws:
                mock_ws.send_integration_connected = AsyncMock()
                client.get(
                    "/api/v1/integrations/oauth/callback",
                    params={"connected_account_id": "conn-789", "integration_type": "gmail"},
                )

                mock_ws.send_integration_connected.assert_called_once()
                call_kwargs = mock_ws.send_integration_connected.call_args[1]
                assert call_kwargs["toolkit_slug"] == "gmail"
                assert call_kwargs["status"] == "active"

    async def test_oauth_callback_triggers_email_bootstrap(self) -> None:
        """Callback triggers email bootstrap for gmail integration."""
        with (
            patch(_OAUTH) as mock_oauth_fn,
            patch(_REGISTRY) as mock_registry_fn,
            patch("src.api.routes.integrations.asyncio") as mock_asyncio,
        ):
            mock_oauth = MagicMock()
            mock_oauth.exchange_code_for_connection = AsyncMock(
                return_value={"connection_id": "conn-789", "account_email": "user@test.com"}
            )
            mock_oauth_fn.return_value = mock_oauth

            mock_registry = MagicMock()
            mock_registry.lookup_by_composio_connection_id = AsyncMock(
                return_value={
                    "id": "row-1",
                    "user_id": "u1",
                    "toolkit_slug": "gmail",
                    "status": "pending",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )
            mock_registry.register_connection = AsyncMock(return_value={"id": "row-1"})
            mock_registry_fn.return_value = mock_registry

            app = _make_app()
            client = TestClient(app)

            with patch("src.core.ws.ws_manager") as mock_ws:
                mock_ws.send_integration_connected = AsyncMock()
                client.get(
                    "/api/v1/integrations/oauth/callback",
                    params={"connected_account_id": "conn-789", "integration_type": "gmail"},
                )

            # asyncio.create_task should be called for bootstrap
            mock_asyncio.create_task.assert_called()

    async def test_oauth_callback_rejects_stale_pending(self) -> None:
        """Callback rejects connections older than 10 minutes."""
        with (
            patch(_OAUTH) as mock_oauth_fn,
            patch(_REGISTRY) as mock_registry_fn,
        ):
            mock_oauth_fn.return_value = MagicMock()

            stale_time = (datetime.now(UTC) - timedelta(minutes=15)).isoformat()
            mock_registry = MagicMock()
            mock_registry.lookup_by_composio_connection_id = AsyncMock(
                return_value={
                    "id": "row-1",
                    "user_id": "u1",
                    "toolkit_slug": "gmail",
                    "status": "pending",
                    "created_at": stale_time,
                }
            )
            mock_registry_fn.return_value = mock_registry

            app = _make_app()
            client = TestClient(app)
            resp = client.get(
                "/api/v1/integrations/oauth/callback",
                params={"connected_account_id": "conn-stale", "integration_type": "gmail"},
            )

            assert resp.status_code == 200
            assert "expired" in resp.text.lower()
