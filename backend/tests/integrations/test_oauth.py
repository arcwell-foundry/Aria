"""Tests for Composio OAuth client (SDK-based)."""

from unittest.mock import MagicMock, patch

import pytest

from src.integrations.oauth import ComposioOAuthClient, get_oauth_client


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton between tests."""
    import src.integrations.oauth as oauth_module

    oauth_module._oauth_client = None
    yield
    oauth_module._oauth_client = None


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings so Composio SDK isn't initialized with real keys."""
    with patch("src.integrations.oauth.settings") as m:
        mock_key = MagicMock()
        mock_key.get_secret_value.return_value = "test-composio-key"
        m.COMPOSIO_API_KEY = mock_key
        yield m


@pytest.fixture
def mock_composio():
    """Create a mocked Composio SDK instance."""
    with patch("src.integrations.oauth.Composio") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


def test_get_oauth_client_singleton():
    """Test that get_oauth_client returns the same instance."""
    client1 = get_oauth_client()
    client2 = get_oauth_client()
    assert client1 is client2


@pytest.mark.asyncio
async def test_generate_auth_url_with_connection_id(mock_composio):
    """Test generating OAuth URL returns auth_url and connection_id."""
    client = ComposioOAuthClient()
    # Inject mocked SDK
    client._composio = mock_composio

    # Mock auth_configs.list to return a config
    mock_config = MagicMock()
    mock_config.id = "auth-config-123"
    mock_config.toolkit.slug = "googlecalendar"
    mock_list_response = MagicMock()
    mock_list_response.items = [mock_config]
    mock_composio.client.auth_configs.list.return_value = mock_list_response

    # Mock link.create to return redirect URL and connection ID
    mock_link_response = MagicMock()
    mock_link_response.redirect_url = "https://accounts.google.com/o/oauth2/auth?..."
    mock_link_response.connected_account_id = "conn-nano-456"
    mock_composio.client.link.create.return_value = mock_link_response

    auth_url, connection_id = await client.generate_auth_url_with_connection_id(
        user_id="user-123",
        integration_type="GOOGLECALENDAR",
        redirect_uri="http://localhost:5173/integrations/callback",
    )

    assert auth_url == "https://accounts.google.com/o/oauth2/auth?..."
    assert connection_id == "conn-nano-456"

    mock_composio.client.auth_configs.list.assert_called_once_with(
        toolkit_slug="googlecalendar",
    )
    mock_composio.client.link.create.assert_called_once_with(
        auth_config_id="auth-config-123",
        user_id="user-123",
        callback_url="http://localhost:5173/integrations/callback",
    )


@pytest.mark.asyncio
async def test_generate_auth_url_delegates(mock_composio):
    """Test that generate_auth_url returns just the URL string."""
    client = ComposioOAuthClient()
    client._composio = mock_composio

    mock_config = MagicMock()
    mock_config.id = "auth-cfg-1"
    mock_config.toolkit.slug = "salesforce"
    mock_list_response = MagicMock()
    mock_list_response.items = [mock_config]
    mock_composio.client.auth_configs.list.return_value = mock_list_response

    mock_link_response = MagicMock()
    mock_link_response.redirect_url = "https://oauth.example.com/start"
    mock_link_response.connected_account_id = "conn-789"
    mock_composio.client.link.create.return_value = mock_link_response

    url = await client.generate_auth_url(
        user_id="user-1",
        integration_type="SALESFORCE",
        redirect_uri="http://localhost/callback",
    )

    assert url == "https://oauth.example.com/start"


@pytest.mark.asyncio
async def test_generate_auth_url_no_auth_config(mock_composio):
    """Test that missing auth config raises ValueError with actionable message."""
    client = ComposioOAuthClient()
    client._composio = mock_composio

    mock_list_response = MagicMock()
    mock_list_response.items = []
    mock_composio.client.auth_configs.list.return_value = mock_list_response

    with pytest.raises(ValueError, match="No auth config found for 'slack'"):
        await client.generate_auth_url_with_connection_id(
            user_id="user-1",
            integration_type="SLACK",
            redirect_uri="http://localhost/callback",
        )


@pytest.mark.asyncio
async def test_auth_config_caching(mock_composio):
    """Test that auth config IDs are cached after first lookup."""
    client = ComposioOAuthClient()
    client._composio = mock_composio

    mock_config = MagicMock()
    mock_config.id = "cached-config-id"
    mock_config.toolkit.slug = "hubspot"
    mock_list_response = MagicMock()
    mock_list_response.items = [mock_config]
    mock_composio.client.auth_configs.list.return_value = mock_list_response

    mock_link_response = MagicMock()
    mock_link_response.redirect_url = "https://oauth.example.com"
    mock_link_response.connected_account_id = "conn-1"
    mock_composio.client.link.create.return_value = mock_link_response

    # First call — should hit auth_configs.list
    await client.generate_auth_url_with_connection_id(
        user_id="u1", integration_type="HUBSPOT", redirect_uri="http://x/cb",
    )
    assert mock_composio.client.auth_configs.list.call_count == 1

    # Second call — should use cache, not call list again
    await client.generate_auth_url_with_connection_id(
        user_id="u2", integration_type="HUBSPOT", redirect_uri="http://x/cb",
    )
    assert mock_composio.client.auth_configs.list.call_count == 1


@pytest.mark.asyncio
async def test_disconnect_integration(mock_composio):
    """Test disconnect calls connected_accounts.delete."""
    client = ComposioOAuthClient()
    client._composio = mock_composio

    mock_composio.client.connected_accounts.delete.return_value = MagicMock()

    await client.disconnect_integration(
        user_id="user-1",
        connection_id="conn-nano-123",
    )

    mock_composio.client.connected_accounts.delete.assert_called_once_with(
        "conn-nano-123",
    )


@pytest.mark.asyncio
async def test_test_connection_active(mock_composio):
    """Test that ACTIVE status returns True."""
    client = ComposioOAuthClient()
    client._composio = mock_composio

    mock_account = MagicMock()
    mock_account.status = "ACTIVE"
    mock_composio.client.connected_accounts.retrieve.return_value = mock_account

    result = await client.test_connection("conn-123")
    assert result is True

    mock_composio.client.connected_accounts.retrieve.assert_called_once_with("conn-123")


@pytest.mark.asyncio
async def test_test_connection_inactive(mock_composio):
    """Test that non-ACTIVE status returns False."""
    client = ComposioOAuthClient()
    client._composio = mock_composio

    mock_account = MagicMock()
    mock_account.status = "INITIATED"
    mock_composio.client.connected_accounts.retrieve.return_value = mock_account

    result = await client.test_connection("conn-456")
    assert result is False


@pytest.mark.asyncio
async def test_execute_action(mock_composio):
    """Test execute_action calls tools.execute."""
    client = ComposioOAuthClient()
    client._composio = mock_composio

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {"success": True, "data": {"id": "msg-1"}}
    mock_composio.tools.execute.return_value = mock_result

    result = await client.execute_action(
        connection_id="conn-1",
        action="gmail_send_email",
        params={"to": "test@example.com", "body": "Hello"},
    )

    assert result == {"success": True, "data": {"id": "msg-1"}}
    mock_composio.tools.execute.assert_called_once_with(
        slug="gmail_send_email",
        connected_account_id="conn-1",
        user_id=None,
        arguments={"to": "test@example.com", "body": "Hello"},
    )


@pytest.mark.asyncio
async def test_close_clears_state(mock_composio):
    """Test that close() resets the SDK client and cache."""
    client = ComposioOAuthClient()
    client._composio = mock_composio
    client._auth_config_cache["SALESFORCE"] = "cached-id"

    await client.close()

    assert client._composio is None
    assert client._auth_config_cache == {}
