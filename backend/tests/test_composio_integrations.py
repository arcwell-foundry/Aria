"""Tests for Composio/OAuth integration API routes.

Tests the integration endpoints at /api/v1/integrations/* by constructing
a minimal FastAPI app with only the integrations router mounted. All
external dependencies (Composio SDK, Supabase, auth) are fully mocked.
"""

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Module-level setup: stub the composio SDK if not installed so the
# integrations route module can be loaded without the full dependency chain.
# ---------------------------------------------------------------------------
if "composio" not in sys.modules:
    sys.modules["composio"] = MagicMock()


def _load_module_from_file(module_name: str, file_path: Path) -> ModuleType:
    """Load a Python module directly from its file path.

    Bypasses the package __init__.py to avoid pulling in every sibling route
    module (and their heavy transitive imports like python-multipart, qrcode,
    composio SDK, etc.).
    """
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Load only the integrations route module, bypassing __init__.py
_routes_mod = _load_module_from_file(
    "src.api.routes.integrations",
    Path(__file__).resolve().parent.parent / "src" / "api" / "routes" / "integrations.py",
)
router = _routes_mod.router

from src.api.deps import get_current_user  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_user() -> MagicMock:
    """Create a mock authenticated user."""
    user = MagicMock()
    user.id = "user-test-123"
    user.email = "test@example.com"
    return user


@pytest.fixture
def client(fake_user: MagicMock) -> TestClient:
    """Create a test client with a minimal app and mocked auth.

    Mounts only the integrations router under /api/v1 to avoid pulling in
    unrelated route modules that may have heavy transitive imports.
    """
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    async def override_get_current_user() -> MagicMock:
        return fake_user

    test_app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(test_app) as tc:
        yield tc
    test_app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_oauth_providers_configured(client: TestClient) -> None:
    """Available integrations endpoint returns supported OAuth providers.

    Verifies that GET /api/v1/integrations/available calls the integration
    service and returns a list of provider configurations with the expected
    AvailableIntegrationResponse schema fields.
    """
    mock_available = [
        {
            "integration_type": "gmail",
            "display_name": "Gmail",
            "description": "Connect Gmail for email drafting and analysis",
            "icon": "mail",
            "is_connected": False,
            "status": None,
        },
        {
            "integration_type": "salesforce",
            "display_name": "Salesforce",
            "description": "Sync leads and opportunities from Salesforce",
            "icon": "crm",
            "is_connected": False,
            "status": None,
        },
        {
            "integration_type": "hubspot",
            "display_name": "HubSpot",
            "description": "Connect HubSpot CRM for lead management",
            "icon": "crm",
            "is_connected": False,
            "status": None,
        },
    ]

    with patch.object(
        _routes_mod, "get_integration_service"
    ) as mock_svc_fn:
        mock_svc = MagicMock()
        mock_svc_fn.return_value = mock_svc
        mock_svc.get_available_integrations = AsyncMock(
            return_value=mock_available,
        )

        resp = client.get("/api/v1/integrations/available")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 3

    # Verify each provider has the required AvailableIntegrationResponse fields
    for provider in data:
        assert "integration_type" in provider
        assert "display_name" in provider
        assert "description" in provider
        assert "icon" in provider
        assert "is_connected" in provider

    provider_types = [p["integration_type"] for p in data]
    assert "gmail" in provider_types
    assert "salesforce" in provider_types
    assert "hubspot" in provider_types


def test_integration_auth_url_generation(client: TestClient) -> None:
    """OAuth flow initiation returns a valid authorization URL.

    Verifies that POST /api/v1/integrations/{type}/auth-url validates the
    integration type against INTEGRATION_CONFIGS, calls the Composio OAuth
    client, and returns the authorization URL with metadata.
    """
    expected_auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        "?client_id=test&scope=gmail.readonly"
        "&redirect_uri=http://localhost:3000/callback"
    )

    with patch.object(
        _routes_mod, "get_oauth_client"
    ) as mock_oauth_fn:
        mock_oauth = MagicMock()
        mock_oauth_fn.return_value = mock_oauth
        mock_oauth.generate_auth_url = AsyncMock(
            return_value=expected_auth_url,
        )

        resp = client.post(
            "/api/v1/integrations/gmail/auth-url",
            json={"redirect_uri": "http://localhost:3000/callback"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "authorization_url" in data
    assert data["authorization_url"] == expected_auth_url
    assert data["integration_type"] == "gmail"
    assert data["display_name"] == "Gmail"

    # Verify the OAuth client was called with correct arguments
    mock_oauth.generate_auth_url.assert_awaited_once()
    call_kwargs = mock_oauth.generate_auth_url.call_args
    assert call_kwargs.kwargs["user_id"] == "user-test-123"
    assert call_kwargs.kwargs["redirect_uri"] == "http://localhost:3000/callback"


def test_graceful_degradation_without_composio(client: TestClient) -> None:
    """When no integrations are connected, the list endpoint returns empty.

    Verifies that GET /api/v1/integrations returns an empty list (not an
    error) when the integration service has no records for the user. This
    is the expected state before any Composio OAuth flow completes and
    validates that the endpoint degrades gracefully.
    """
    with patch.object(
        _routes_mod, "get_integration_service"
    ) as mock_svc_fn:
        mock_svc = MagicMock()
        mock_svc_fn.return_value = mock_svc
        mock_svc.get_user_integrations = AsyncMock(return_value=[])

        resp = client.get("/api/v1/integrations")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_connect_integration_exchanges_code(client: TestClient) -> None:
    """POST /{type}/connect exchanges the OAuth code via exchange_code_for_connection.

    Verifies the route calls exchange_code_for_connection on the OAuth client
    and creates the integration record via the service.
    """
    mock_connection_data = {
        "connection_id": "conn-abc-123",
        "account_id": "acct-xyz",
        "account_email": "test@example.com",
    }
    mock_integration = {
        "id": "int-001",
        "integration_type": "gmail",
        "display_name": "test@example.com",
        "status": "active",
        "last_sync_at": None,
        "sync_status": "success",
        "error_message": None,
        "created_at": "2026-02-18T00:00:00Z",
    }

    with (
        patch.object(_routes_mod, "get_oauth_client") as mock_oauth_fn,
        patch.object(_routes_mod, "get_integration_service") as mock_svc_fn,
    ):
        mock_oauth = MagicMock()
        mock_oauth_fn.return_value = mock_oauth
        mock_oauth.exchange_code_for_connection = AsyncMock(
            return_value=mock_connection_data,
        )

        mock_svc = MagicMock()
        mock_svc_fn.return_value = mock_svc
        mock_svc.create_integration = AsyncMock(
            return_value=mock_integration,
        )

        resp = client.post(
            "/api/v1/integrations/gmail/connect",
            json={"code": "conn-abc-123-longer-code"},
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == "int-001"
    assert data["integration_type"] == "gmail"

    mock_oauth.exchange_code_for_connection.assert_awaited_once()
    call_kwargs = mock_oauth.exchange_code_for_connection.call_args.kwargs
    assert call_kwargs["code"] == "conn-abc-123-longer-code"
    assert call_kwargs["user_id"] == "user-test-123"


def test_sync_integration_delegates_to_service(client: TestClient) -> None:
    """POST /{id}/sync delegates to IntegrationService.trigger_sync.

    Verifies the route simply calls trigger_sync and returns its result,
    without duplicating status manipulation logic.
    """
    mock_result = {
        "id": "int-001",
        "integration_type": "salesforce",
        "display_name": "SF Instance",
        "status": "active",
        "last_sync_at": "2026-02-18T12:00:00Z",
        "sync_status": "success",
        "error_message": None,
        "created_at": "2026-01-01T00:00:00Z",
    }

    with patch.object(
        _routes_mod, "get_integration_service"
    ) as mock_svc_fn:
        mock_svc = MagicMock()
        mock_svc_fn.return_value = mock_svc
        mock_svc.trigger_sync = AsyncMock(return_value=mock_result)

        resp = client.post("/api/v1/integrations/int-001/sync")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sync_status"] == "success"
    mock_svc.trigger_sync.assert_awaited_once_with("int-001")


# ---------------------------------------------------------------------------
# Unit tests for ComposioOAuthClient.exchange_code_for_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_code_for_connection_active() -> None:
    """exchange_code_for_connection returns connection details for ACTIVE status."""
    from src.integrations.oauth import ComposioOAuthClient

    client = ComposioOAuthClient()

    # Mock the Composio SDK client
    mock_result = MagicMock()
    mock_result.status = "ACTIVE"
    mock_result.id = "acct-id-123"
    mock_result.member_email = "user@example.com"

    mock_connected_accounts = MagicMock()
    mock_connected_accounts.retrieve.return_value = mock_result

    mock_inner_client = MagicMock()
    mock_inner_client.connected_accounts = mock_connected_accounts

    mock_composio = MagicMock()
    mock_composio.client = mock_inner_client

    client._composio = mock_composio

    result = await client.exchange_code_for_connection(
        user_id="user-1",
        code="conn-nanoid-abc",
        integration_type="gmail",
    )

    assert result["connection_id"] == "conn-nanoid-abc"
    assert result["account_id"] == "acct-id-123"
    assert result["account_email"] == "user@example.com"
    mock_connected_accounts.retrieve.assert_called_once_with("conn-nanoid-abc")


@pytest.mark.asyncio
async def test_exchange_code_for_connection_inactive_raises() -> None:
    """exchange_code_for_connection raises ValueError for non-ACTIVE status."""
    from src.integrations.oauth import ComposioOAuthClient

    client = ComposioOAuthClient()

    mock_result = MagicMock()
    mock_result.status = "PENDING"

    mock_connected_accounts = MagicMock()
    mock_connected_accounts.retrieve.return_value = mock_result

    mock_inner_client = MagicMock()
    mock_inner_client.connected_accounts = mock_connected_accounts

    mock_composio = MagicMock()
    mock_composio.client = mock_inner_client

    client._composio = mock_composio

    with pytest.raises(ValueError, match="not active"):
        await client.exchange_code_for_connection(
            user_id="user-1",
            code="conn-nanoid-abc",
            integration_type="gmail",
        )
