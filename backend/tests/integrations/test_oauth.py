"""Tests for OAuth integration client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.integrations.oauth import ComposioOAuthClient, get_oauth_client


@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings."""
    with patch("src.integrations.oauth.settings") as m:
        m.COMPOSIO_API_KEY.get_secret_value.return_value = "test-key"
        m.COMPOSIO_BASE_URL = "https://test.api.composio.dev"
        yield m


@pytest.mark.asyncio
async def test_get_oauth_client_singleton():
    """Test that get_oauth_client returns singleton instance."""
    client1 = get_oauth_client()
    client2 = get_oauth_client()
    assert client1 is client2


@pytest.mark.asyncio
async def test_generate_auth_url():
    """Test generating OAuth authorization URL."""
    client = ComposioOAuthClient()

    # Mock the async HTTP client
    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value={
        "authorization_url": "https://auth.composio.dev/authorize?code=test123"
    })
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_response)

    # Patch the private attribute that the _http property uses
    with patch.object(client, "_http_client", mock_http):
        url = await client.generate_auth_url(
            user_id="user-123",
            integration_type="google_calendar",
            redirect_uri="http://localhost:5173/integrations/callback"
        )

        assert url == "https://auth.composio.dev/authorize?code=test123"
        mock_http.post.assert_called_once()
