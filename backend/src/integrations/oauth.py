"""Composio OAuth client integration using the Composio SDK."""

import asyncio
import logging
from typing import Any

from composio import Composio

from src.core.config import settings
from src.core.resilience import composio_circuit_breaker

logger = logging.getLogger(__name__)


class ComposioOAuthClient:
    """Client for Composio OAuth operations using the official SDK.

    All SDK calls are synchronous — wrapped with asyncio.to_thread()
    for FastAPI compatibility.
    """

    _composio: Composio | None = None
    _auth_config_cache: dict[str, str] = {}

    @property
    def _client(self) -> Composio:
        """Lazy initialization of Composio SDK client."""
        if self._composio is None:
            api_key = (
                settings.COMPOSIO_API_KEY.get_secret_value()
                if settings.COMPOSIO_API_KEY is not None
                else ""
            )
            self._composio = Composio(api_key=api_key)
        return self._composio

    async def _resolve_auth_config_id(self, toolkit_slug: str) -> str:
        """Look up the auth config ID for a toolkit.

        Args:
            toolkit_slug: The toolkit slug (e.g., 'SALESFORCE', 'GMAIL').

        Returns:
            The auth config ID string.

        Raises:
            ValueError: If no auth config exists for this toolkit.
        """
        # Normalise to lowercase — Composio toolkit slugs are always lowercase
        toolkit_slug = toolkit_slug.lower()

        # Check cache first
        if toolkit_slug in self._auth_config_cache:
            logger.debug("Auth config cache hit for %s", toolkit_slug)
            return self._auth_config_cache[toolkit_slug]

        def _list_configs() -> Any:
            return self._client.client.auth_configs.list(
                toolkit_slug=toolkit_slug,
            )

        result = await asyncio.to_thread(_list_configs)

        # Filter to configs that actually match the requested toolkit.
        # Composio returns ALL configs when the slug doesn't match anything,
        # so we must filter client-side to avoid picking an unrelated config.
        matching = [item for item in result.items if item.toolkit.slug == toolkit_slug]

        if not matching:
            logger.debug("No auth configs found for %s", toolkit_slug)
            raise ValueError(
                f"No auth config found for '{toolkit_slug}'. "
                f"Create one at https://app.composio.dev → Auth Configs → "
                f"select '{toolkit_slug}' toolkit and configure OAuth credentials."
            )

        auth_config_id: str = matching[0].id
        self._auth_config_cache[toolkit_slug] = auth_config_id
        logger.debug("Resolved %s → auth_config_id=%s", toolkit_slug, auth_config_id)
        return auth_config_id

    async def generate_auth_url(
        self,
        user_id: str,
        integration_type: str,
        redirect_uri: str,
    ) -> str:
        """Generate OAuth authorization URL for an integration.

        Args:
            user_id: The user's ID.
            integration_type: The toolkit slug (e.g., 'SALESFORCE').
            redirect_uri: The redirect URI for OAuth callback.

        Returns:
            The authorization URL.

        Raises:
            ValueError: If no auth config is found for the toolkit.
        """
        auth_url, _ = await self.generate_auth_url_with_connection_id(
            user_id=user_id,
            integration_type=integration_type,
            redirect_uri=redirect_uri,
        )
        return auth_url

    async def generate_auth_url_with_connection_id(
        self,
        user_id: str,
        integration_type: str,
        redirect_uri: str,
    ) -> tuple[str, str]:
        """Generate OAuth authorization URL and return connection ID.

        Uses the Composio SDK's link.create() to initiate OAuth.

        Args:
            user_id: The user's ID.
            integration_type: The toolkit slug (e.g., 'SALESFORCE').
            redirect_uri: The redirect URI for OAuth callback.

        Returns:
            Tuple of (authorization_url, connection_id).

        Raises:
            ValueError: If no auth config is found for the toolkit.
        """
        auth_config_id = await self._resolve_auth_config_id(integration_type)

        def _create_link() -> Any:
            return self._client.client.link.create(
                auth_config_id=auth_config_id,
                user_id=user_id,
                callback_url=redirect_uri,
            )

        result = await asyncio.to_thread(_create_link)

        redirect_url: str = result.redirect_url
        connection_id: str = result.connected_account_id

        logger.info(
            "OAuth link created via Composio SDK",
            extra={
                "user_id": user_id,
                "integration_type": integration_type,
                "connection_id": connection_id,
            },
        )

        return redirect_url, connection_id

    async def disconnect_integration(
        self,
        user_id: str,
        connection_id: str,
    ) -> None:
        """Disconnect an integration connection.

        Args:
            user_id: The user's ID (kept for interface compatibility).
            connection_id: The Composio connection nanoid.
        """

        def _delete() -> Any:
            return self._client.client.connected_accounts.delete(connection_id)

        await asyncio.to_thread(_delete)

        logger.info(
            "Integration disconnected via Composio SDK",
            extra={"user_id": user_id, "connection_id": connection_id},
        )

    async def test_connection(
        self,
        connection_id: str,
    ) -> bool:
        """Test if a connection is working.

        Args:
            connection_id: The Composio connection nanoid.

        Returns:
            True if connection status is ACTIVE, False otherwise.
        """

        def _retrieve() -> Any:
            return self._client.client.connected_accounts.retrieve(connection_id)

        result = await asyncio.to_thread(_retrieve)
        return str(result.status).upper() == "ACTIVE"

    async def execute_action(
        self,
        connection_id: str,
        action: str,
        params: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute an action via Composio.

        Args:
            connection_id: The Composio connection nanoid.
            action: The tool slug (e.g., 'GMAIL_FETCH_EMAILS', 'OUTLOOK_LIST_MESSAGES').
            params: Parameters for the action.
            user_id: Optional user/entity ID for the action.

        Returns:
            Action result dict with 'successful', 'data', and 'error' keys.
        """
        composio_circuit_breaker.check()

        def _execute() -> Any:
            return self._client.tools.execute(
                slug=action,
                connected_account_id=connection_id,
                user_id=user_id,
                arguments=params,
                dangerously_skip_version_check=True,
            )

        try:
            result = await asyncio.to_thread(_execute)
        except Exception:
            composio_circuit_breaker.record_failure()
            raise
        composio_circuit_breaker.record_success()
        # The SDK returns a dict with 'successful', 'data', 'error' keys
        if isinstance(result, dict):
            return result
        if hasattr(result, "model_dump"):
            return dict(result.model_dump())
        return {"result": str(result)}

    def execute_action_sync(
        self,
        connection_id: str,
        action: str,
        params: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute an action via Composio (synchronous version).

        Args:
            connection_id: The Composio connection nanoid.
            action: The tool slug (e.g., 'GMAIL_FETCH_EMAILS', 'OUTLOOK_LIST_MESSAGES').
            params: Parameters for the action.
            user_id: Optional user/entity ID for the action.

        Returns:
            Action result dict with 'successful', 'data', and 'error' keys.
        """
        result = self._client.tools.execute(
            slug=action,
            connected_account_id=connection_id,
            user_id=user_id,
            arguments=params,
            dangerously_skip_version_check=True,
        )
        # The SDK returns a dict with 'successful', 'data', 'error' keys
        if isinstance(result, dict):
            return result
        if hasattr(result, "model_dump"):
            return dict(result.model_dump())
        return {"result": str(result)}

    async def close(self) -> None:
        """Clean up the SDK client."""
        self._composio = None
        self._auth_config_cache.clear()


# Singleton instance
_oauth_client: ComposioOAuthClient | None = None


def get_oauth_client() -> ComposioOAuthClient:
    """Get the singleton OAuth client instance.

    Returns:
        The ComposioOAuthClient instance.
    """
    global _oauth_client
    if _oauth_client is None:
        _oauth_client = ComposioOAuthClient()
    return _oauth_client
