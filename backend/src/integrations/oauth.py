"""Composio OAuth client integration using the Composio SDK."""

import asyncio
import logging
from typing import Any

from composio import Composio

from src.core.config import settings
from src.core.resilience import CircuitBreaker, composio_circuit_breaker

logger = logging.getLogger(__name__)

# Composio tool name mapping: old (codebase) → new (Composio platform)
# The Composio platform renamed many Outlook tools by adding an extra
# "OUTLOOK_" prefix (e.g. OUTLOOK_GET_MESSAGE → OUTLOOK_OUTLOOK_GET_MESSAGE).
# This map keeps the rest of the codebase unchanged.
_TOOL_NAME_MAP: dict[str, str] = {
    "OUTLOOK_GET_MESSAGE": "OUTLOOK_OUTLOOK_GET_MESSAGE",
    "OUTLOOK_LIST_MESSAGES": "OUTLOOK_OUTLOOK_LIST_MESSAGES",
    "OUTLOOK_SEND_EMAIL": "OUTLOOK_OUTLOOK_SEND_EMAIL",
    "OUTLOOK_CREATE_DRAFT": "OUTLOOK_OUTLOOK_CREATE_DRAFT",
    "OUTLOOK_CREATE_DRAFT_REPLY": "OUTLOOK_OUTLOOK_CREATE_DRAFT_REPLY",
    "OUTLOOK_GET_PROFILE": "OUTLOOK_OUTLOOK_GET_PROFILE",
    "OUTLOOK_CALENDAR_CREATE_EVENT": "OUTLOOK_OUTLOOK_CALENDAR_CREATE_EVENT",
    "OUTLOOK_UPDATE_CALENDAR_EVENT": "OUTLOOK_OUTLOOK_UPDATE_CALENDAR_EVENT",
    "OUTLOOK_DELETE_EVENT": "OUTLOOK_OUTLOOK_DELETE_EVENT",
    "OUTLOOK_LIST_EVENTS": "OUTLOOK_OUTLOOK_LIST_EVENTS",
    "OUTLOOK_GET_EVENT": "OUTLOOK_OUTLOOK_GET_EVENT",
    "OUTLOOK_GET_SCHEDULE": "OUTLOOK_OUTLOOK_GET_SCHEDULE",
    "OUTLOOK_LIST_CONTACTS": "OUTLOOK_OUTLOOK_LIST_CONTACTS",
    "OUTLOOK_GET_CONTACT": "OUTLOOK_OUTLOOK_GET_CONTACT",
    "OUTLOOK_REPLY_EMAIL": "OUTLOOK_OUTLOOK_REPLY_EMAIL",
    "OUTLOOK_SEARCH_MESSAGES": "OUTLOOK_OUTLOOK_SEARCH_MESSAGES",
    "OUTLOOK_MOVE_MESSAGE": "OUTLOOK_OUTLOOK_MOVE_MESSAGE",
    "OUTLOOK_UPDATE_EMAIL": "OUTLOOK_OUTLOOK_UPDATE_EMAIL",
    "OUTLOOK_LIST_MAIL_FOLDERS": "OUTLOOK_OUTLOOK_LIST_MAIL_FOLDERS",
}


def _resolve_tool_name(action: str) -> str:
    """Map legacy tool names to current Composio platform names."""
    return _TOOL_NAME_MAP.get(action, action)


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

    async def exchange_code_for_connection(
        self,
        user_id: str,
        code: str,
        integration_type: "Any",
    ) -> dict[str, Any]:
        """Exchange an OAuth callback code for connection details.

        In Composio's flow, ``link.create()`` returns a ``connected_account_id``
        during auth URL generation.  The "code" the frontend sends back after
        the OAuth redirect IS that connection ID.  This method verifies the
        connection is active and returns normalised connection metadata.

        Args:
            user_id: The user's ID (for logging / future validation).
            code: The connection ID returned by the OAuth callback.
            integration_type: The integration type (for logging).

        Returns:
            Dict with ``connection_id``, ``account_id``, and ``account_email``.

        Raises:
            ValueError: If the connection is not in ACTIVE status.
        """

        def _retrieve() -> Any:
            return self._client.client.connected_accounts.retrieve(code)

        result = await asyncio.to_thread(_retrieve)

        status = str(result.status).upper()
        if status != "ACTIVE":
            raise ValueError(
                f"Connection {code} is not active (status={status}). "
                "The user may need to complete the OAuth flow."
            )

        # Extract account metadata — fields vary by provider so we
        # fall back to empty strings when attributes are absent.
        account_id = getattr(result, "id", None) or code
        account_email = getattr(result, "member_email", None) or ""

        # BL-4 FIX: If member_email is empty, try to fetch from provider profile
        # This is critical for is_from_user detection in email processing
        if not account_email:
            account_email = await self._fetch_email_from_provider_profile(
                code, integration_type, user_id
            )

        logger.info(
            "OAuth code exchanged for connection",
            extra={
                "user_id": user_id,
                "integration_type": str(integration_type),
                "connection_id": code,
                "account_email": account_email or "NOT_FOUND",
            },
        )

        return {
            "connection_id": code,
            "account_id": str(account_id),
            "account_email": account_email,
        }

    async def _fetch_email_from_provider_profile(
        self,
        connection_id: str,
        integration_type: "Any",
        user_id: str,
    ) -> str:
        """Fetch user's email from the provider's profile API.

        Called as a fallback when Composio's member_email is empty.

        Args:
            connection_id: The Composio connection ID.
            integration_type: The integration type (e.g., OUTLOOK, GMAIL).
            user_id: The user's ID for the action.

        Returns:
            The user's email address, or empty string if not found.
        """
        integration_str = str(integration_type).lower()

        try:
            if "outlook" in integration_str or "microsoft" in integration_str:
                # Try OUTLOOK_GET_PROFILE
                result = await self.execute_action(
                    connection_id=connection_id,
                    action="OUTLOOK_GET_PROFILE",
                    params={},
                    user_id=user_id,
                )
                if result.get("successful"):
                    data = result.get("data", {})
                    email = (
                        data.get("emailAddress")
                        or data.get("mail")
                        or data.get("userPrincipalName")
                        or ""
                    )
                    if email:
                        logger.info(
                            "Fetched email from Outlook profile: %s", email
                        )
                        return email

            elif "gmail" in integration_str or "google" in integration_str:
                # Try GMAIL_GET_PROFILE
                result = await self.execute_action(
                    connection_id=connection_id,
                    action="GMAIL_GET_PROFILE",
                    params={},
                    user_id=user_id,
                )
                if result.get("successful"):
                    data = result.get("data", {})
                    email = data.get("emailAddress") or data.get("email") or ""
                    if email:
                        logger.info(
                            "Fetched email from Gmail profile: %s", email
                        )
                        return email

        except Exception as e:
            logger.warning(
                "Failed to fetch email from provider profile: %s", e
            )

        return ""

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

    def _resolve_tool_version(self, action: str) -> str | None:
        """Resolve the latest available version for a Composio tool.

        The SDK requires an explicit version for manual execution.
        We retrieve the tool schema and pick the newest available version.

        Args:
            action: The tool slug (e.g., 'OUTLOOK_GET_MAIL_DELTA').

        Returns:
            The latest version string, or None if unavailable.
        """
        try:
            tool = self._client.client.tools.retrieve(tool_slug=action)
            versions = getattr(tool, "available_versions", None)
            if versions:
                logger.info(
                    "Resolved version for %s: %s (available: %s)",
                    action,
                    versions[0],
                    versions,
                )
                return versions[0]  # newest first
            else:
                logger.warning(
                    "No available_versions for action %s - tool response: %s",
                    action,
                    tool,
                )
        except Exception as e:
            logger.error("Could not resolve version for %s: %s", action, e, exc_info=True)
        return None

    async def execute_action(
        self,
        connection_id: str,
        action: str,
        params: dict[str, Any],
        user_id: str | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        dangerously_skip_version_check: bool = False,
    ) -> dict[str, Any]:
        """Execute an action via Composio.

        Args:
            connection_id: The Composio connection nanoid.
            action: The tool slug (e.g., 'GMAIL_FETCH_EMAILS', 'OUTLOOK_LIST_MESSAGES').
            params: Parameters for the action.
            user_id: Optional user/entity ID for the action.
            circuit_breaker: Optional per-service circuit breaker. Falls back to
                the shared ``composio_circuit_breaker`` when not provided.
            dangerously_skip_version_check: Skip version check for tools without versions.
                Required for some Outlook calendar actions that have no registered version.

        Returns:
            Action result dict with 'successful', 'data', and 'error' keys.
        """
        cb = circuit_breaker or composio_circuit_breaker
        cb.check()

        # Translate legacy tool names to current Composio platform names
        resolved_action = _resolve_tool_name(action)

        # Resolve the tool version required by the SDK (unless skipping)
        version = None
        if not dangerously_skip_version_check:
            version = await asyncio.to_thread(self._resolve_tool_version, resolved_action)

        # Pre-load tool schema so SDK doesn't KeyError on _custom_tools lookup
        if resolved_action not in self._client.tools._tool_schemas:
            try:
                tool_schema = await asyncio.to_thread(
                    self._client.client.tools.retrieve, tool_slug=resolved_action,
                )
                self._client.tools._tool_schemas[resolved_action] = tool_schema
                if version is None:
                    versions = getattr(tool_schema, "available_versions", None)
                    if versions:
                        version = versions[0]
            except Exception as e:
                logger.debug("Could not preload tool schema for %s: %s", resolved_action, e)
        elif version is None:
            # Schema already cached from a prior call — extract version from it
            cached_schema = self._client.tools._tool_schemas[resolved_action]
            versions = getattr(cached_schema, "available_versions", None)
            if versions:
                version = versions[0]

        # Execute Composio action via SDK
        def _execute() -> Any:
            return self._client.tools.execute(
                slug=resolved_action,
                connected_account_id=connection_id,
                user_id=user_id,
                arguments=params,
                version=version,
            )

        try:
            result = await asyncio.to_thread(_execute)
        except Exception:
            cb.record_failure()
            raise
        cb.record_success()
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
        dangerously_skip_version_check: bool = False,
    ) -> dict[str, Any]:
        """Execute an action via Composio (synchronous version).

        Args:
            connection_id: The Composio connection nanoid.
            action: The tool slug (e.g., 'GMAIL_FETCH_EMAILS', 'OUTLOOK_LIST_MESSAGES').
            params: Parameters for the action.
            user_id: Optional user/entity ID for the action.
            dangerously_skip_version_check: Skip version check for tools without versions.
                Required for some Outlook calendar actions that have no registered version.

        Returns:
            Action result dict with 'successful', 'data', and 'error' keys.
        """
        # Translate legacy tool names to current Composio platform names
        resolved_action = _resolve_tool_name(action)

        version: str | None = None

        if not dangerously_skip_version_check:
            # Pre-load tool schema to avoid KeyError in Composio SDK
            # The SDK's execute() tries _custom_tools[slug].info which fails
            # if the tool isn't in the registry. We preload via retrieve().
            if resolved_action not in self._client.tools._tool_schemas:
                try:
                    tool = self._client.client.tools.retrieve(tool_slug=resolved_action)
                    self._client.tools._tool_schemas[resolved_action] = tool
                    versions = getattr(tool, "available_versions", None)
                    if versions:
                        version = versions[0]
                except Exception as e:
                    logger.debug("Could not preload tool schema for %s: %s", resolved_action, e)

            # If we didn't get a version from preload, resolve it now
            if version is None:
                version = self._resolve_tool_version(resolved_action)
        else:
            # Even when skipping version check, preload schema to avoid KeyError
            # and extract version from cached/new schema so the SDK doesn't fail
            if resolved_action not in self._client.tools._tool_schemas:
                try:
                    tool = self._client.client.tools.retrieve(tool_slug=resolved_action)
                    self._client.tools._tool_schemas[resolved_action] = tool
                    versions = getattr(tool, "available_versions", None)
                    if versions:
                        version = versions[0]
                except Exception as e:
                    logger.debug("Could not preload tool schema for %s: %s", resolved_action, e)
            else:
                cached_schema = self._client.tools._tool_schemas[resolved_action]
                versions = getattr(cached_schema, "available_versions", None)
                if versions:
                    version = versions[0]

        # Execute Composio action via SDK
        result = self._client.tools.execute(
            slug=resolved_action,
            connected_account_id=connection_id,
            user_id=user_id,
            arguments=params,
            version=version,
        )
        # The SDK returns a dict with 'successful', 'data', and 'error' keys
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
