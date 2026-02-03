"""Composio OAuth client integration."""

from typing import Any

import httpx

from src.core.config import settings


class ComposioOAuthClient:
    """Client for Composio OAuth operations using their REST API."""

    _http_client: httpx.AsyncClient | None = None

    @property
    def _http(self) -> httpx.AsyncClient:
        """Lazy initialization of HTTP client."""
        if self._http_client is None:
            headers: dict[str, str] = {
                "Content-Type": "application/json",
            }
            if settings.COMPOSIO_API_KEY is not None:
                headers["x-api-key"] = settings.COMPOSIO_API_KEY.get_secret_value()

            self._http_client = httpx.AsyncClient(
                base_url=settings.COMPOSIO_BASE_URL,
                headers=headers,
                timeout=30.0,
            )
        return self._http_client

    async def generate_auth_url(
        self,
        user_id: str,
        integration_type: str,
        redirect_uri: str,
    ) -> str:
        """Generate OAuth authorization URL for an integration.

        Args:
            user_id: The user's ID
            integration_type: The integration type (e.g., 'google_calendar')
            redirect_uri: The redirect URI for OAuth callback

        Returns:
            The authorization URL

        Raises:
            httpx.HTTPError: If the API request fails
        """
        response = await self._http.post(
            "/oauth/auth_url",
            json={
                "user_id": user_id,
                "integration_type": integration_type,
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return str(data["authorization_url"])

    async def exchange_code_for_connection(
        self,
        user_id: str,
        code: str,
        integration_type: str,
    ) -> dict[str, Any]:
        """Exchange OAuth code for a connection.

        Args:
            user_id: The user's ID
            code: The OAuth authorization code
            integration_type: The integration type

        Returns:
            Connection details including connection_id

        Raises:
            httpx.HTTPError: If the API request fails
        """
        response = await self._http.post(
            "/oauth/exchange",
            json={
                "user_id": user_id,
                "code": code,
                "integration_type": integration_type,
            },
        )
        response.raise_for_status()
        return dict(response.json())

    async def disconnect_integration(
        self,
        user_id: str,
        connection_id: str,
    ) -> None:
        """Disconnect an integration connection.

        Args:
            user_id: The user's ID
            connection_id: The connection ID to disconnect

        Raises:
            httpx.HTTPError: If the API request fails
        """
        response = await self._http.delete(
            f"/connections/{connection_id}",
            params={"user_id": user_id},
        )
        response.raise_for_status()

    async def test_connection(
        self,
        connection_id: str,
    ) -> bool:
        """Test if a connection is working.

        Args:
            connection_id: The connection ID to test

        Returns:
            True if connection is working, False otherwise

        Raises:
            httpx.HTTPError: If the API request fails
        """
        response = await self._http.get(
            f"/connections/{connection_id}/test",
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return bool(data.get("is_working", False))

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None


# Singleton instance
_oauth_client: ComposioOAuthClient | None = None


def get_oauth_client() -> ComposioOAuthClient:
    """Get the singleton OAuth client instance.

    Returns:
        The ComposioOAuthClient instance
    """
    global _oauth_client
    if _oauth_client is None:
        _oauth_client = ComposioOAuthClient()
    return _oauth_client
