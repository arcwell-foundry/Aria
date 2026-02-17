"""Tavus Conversational Video API client."""

import logging
from typing import Any, cast

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


class TavusAPIError(Exception):
    """Raised when Tavus API returns an error response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        """Initialize TavusAPIError.

        Args:
            message: Error message
            status_code: HTTP status code if available
            details: Additional error details from API response
        """
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class TavusConnectionError(Exception):
    """Raised when unable to connect to Tavus API."""

    pass


class TavusClient:
    """Client for Tavus Conversational Video API."""

    BASE_URL = "https://tavusapi.com/v2"

    def __init__(self) -> None:
        """Initialize the Tavus client with API credentials."""
        self.api_key = settings.TAVUS_API_KEY
        self.persona_id: str | None = getattr(settings, "TAVUS_PERSONA_ID", None) or None
        self.replica_id: str | None = getattr(settings, "TAVUS_REPLICA_ID", None) or None
        self.callback_url: str | None = getattr(settings, "TAVUS_CALLBACK_URL", None) or None
        self.guardrails_id: str | None = getattr(settings, "TAVUS_GUARDRAILS_ID", None) or None
        self.headers: dict[str, str] = {
            "x-api-key": self.api_key.get_secret_value() if self.api_key else "",
            "Content-Type": "application/json",
        }

    def _handle_http_error(self, error: httpx.HTTPStatusError) -> None:
        """Handle HTTP errors and raise appropriate Tavus exceptions.

        Args:
            error: The HTTP status error from httpx.

        Raises:
            TavusAPIError: With details from the API response.
        """
        status_code = error.response.status_code
        try:
            details = error.response.json()
            message = details.get("message", str(details))
        except Exception:
            details = error.response.text
            message = f"Tavus API error: {status_code}"

        logger.error(
            "Tavus API error: status=%s message=%s",
            status_code,
            message,
        )
        raise TavusAPIError(message, status_code=status_code, details=details)

    def _handle_connection_error(self, error: httpx.RequestError) -> None:
        """Handle connection errors and raise TavusConnectionError.

        Args:
            error: The request error from httpx.

        Raises:
            TavusConnectionError: Always raised with connection details.
        """
        logger.error("Tavus connection error: %s", str(error))
        raise TavusConnectionError(f"Failed to connect to Tavus API: {error}") from error

    # ====================
    # Conversation Methods
    # ====================

    async def create_conversation(
        self,
        user_id: str,
        conversation_name: str,
        context: str | None = None,
        custom_greeting: str | None = None,
        properties: dict[str, str] | None = None,
        replica_id: str | None = None,
        callback_url: str | None = None,
        memory_stores: list[dict[str, Any]] | None = None,
        document_ids: list[str] | None = None,
        document_tags: list[str] | None = None,
        retrieval_strategy: str | None = None,
        audio_only: bool = False,
    ) -> dict[str, Any]:
        """Create a new Tavus conversation and return conversation details.

        Args:
            user_id: The user's ID for tracking
            conversation_name: Name for the conversation
            context: Optional conversational context
            custom_greeting: Optional custom greeting message
            properties: Optional additional properties
            replica_id: Optional replica ID (defaults to configured replica)
            callback_url: Optional callback URL for events
            memory_stores: Optional list of memory store configurations
            document_ids: Optional list of document IDs to attach
            document_tags: Optional list of document tags to match
            retrieval_strategy: Optional retrieval strategy for knowledge
            audio_only: Whether to create an audio-only conversation

        Returns:
            Dictionary with conversation details including room URL

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        payload: dict[str, Any] = {
            "persona_id": self.persona_id,
            "conversation_name": conversation_name,
            "conversational_context": context or self._default_context(),
            "properties": {
                "user_id": user_id,
                **(properties or {}),
            },
        }

        if custom_greeting:
            payload["custom_greeting"] = custom_greeting

        if replica_id or self.replica_id:
            payload["replica_id"] = replica_id or self.replica_id

        if callback_url or self.callback_url:
            payload["callback_url"] = callback_url or self.callback_url

        if memory_stores:
            payload["memory_stores"] = memory_stores

        if document_ids:
            payload["document_ids"] = document_ids

        if document_tags:
            payload["document_tags"] = document_tags

        if retrieval_strategy:
            payload["retrieval_strategy"] = retrieval_strategy

        if audio_only:
            payload["audio_only"] = audio_only

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/conversations",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise  # Never reached, but satisfies type checker
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise  # Never reached, but satisfies type checker

    async def get_conversation(
        self,
        conversation_id: str,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """Get conversation details including room URL.

        Args:
            conversation_id: The Tavus conversation ID
            verbose: Whether to include transcript and perception analysis

        Returns:
            Dictionary with conversation details

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/conversations/{conversation_id}",
                    headers=self.headers,
                    params={"verbose": str(verbose).lower()},
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def end_conversation(self, conversation_id: str) -> dict[str, Any]:
        """End an active conversation.

        Args:
            conversation_id: The Tavus conversation ID

        Returns:
            Dictionary with response details

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/conversations/{conversation_id}/end",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def delete_conversation(self, conversation_id: str) -> dict[str, Any]:
        """Delete a conversation.

        Args:
            conversation_id: The Tavus conversation ID

        Returns:
            Dictionary with response details

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.BASE_URL}/conversations/{conversation_id}",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def list_conversations(
        self,
        limit: int = 10,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List conversations.

        Args:
            limit: Maximum number of conversations to return
            status: Optional status filter

        Returns:
            List of conversation dictionaries

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                params: dict[str, str | int] = {"limit": limit}
                if status:
                    params["status"] = status

                response = await client.get(
                    f"{self.BASE_URL}/conversations",
                    headers=self.headers,
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                data: dict[str, Any] = cast(dict[str, Any], response.json())
                conversations = data.get("conversations")
                return (
                    cast(list[dict[str, Any]], conversations)
                    if isinstance(conversations, list)
                    else []
                )
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    # ====================
    # Persona Methods
    # ====================

    async def create_persona(
        self,
        persona_name: str,
        system_prompt: str,
        context: str,
        layers: dict[str, Any],
        default_replica_id: str,
        document_ids: list[str] | None = None,
        guardrails_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new persona.

        Args:
            persona_name: Name for the persona
            system_prompt: System prompt for the persona
            context: Conversational context
            layers: Persona layers configuration
            default_replica_id: Default replica ID for the persona
            document_ids: Optional list of document IDs to attach
            guardrails_id: Optional guardrails ID

        Returns:
            Dictionary with persona_id and persona_name

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        payload: dict[str, Any] = {
            "persona_name": persona_name,
            "system_prompt": system_prompt,
            "context": context,
            "layers": layers,
            "default_replica_id": default_replica_id,
        }

        if document_ids:
            payload["document_ids"] = document_ids

        if guardrails_id:
            payload["guardrails_id"] = guardrails_id

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/personas",
                    headers=self.headers,
                    json=payload,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def get_persona(self, persona_id: str | None = None) -> dict[str, Any]:
        """Get persona details.

        Args:
            persona_id: Optional persona ID (defaults to configured persona)

        Returns:
            Dictionary with persona details

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
            ValueError: If no persona ID is provided or configured
        """
        pid = persona_id or self.persona_id
        if not pid:
            raise ValueError("Persona ID is required")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/personas/{pid}",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def patch_persona(
        self,
        persona_id: str,
        patches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Update a persona using JSON Patch format (RFC 6902).

        Args:
            persona_id: The persona ID to update
            patches: List of JSON Patch operations

        Returns:
            Dictionary with updated persona details

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.patch(
                    f"{self.BASE_URL}/personas/{persona_id}",
                    headers=self.headers,
                    json=patches,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def list_personas(self) -> list[dict[str, Any]]:
        """List all personas.

        Returns:
            List of persona dictionaries

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/personas",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data: dict[str, Any] = cast(dict[str, Any], response.json())
                personas = data.get("personas", data)
                return cast(list[dict[str, Any]], personas) if isinstance(personas, list) else []
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def delete_persona(self, persona_id: str) -> dict[str, Any]:
        """Delete a persona.

        Args:
            persona_id: The persona ID to delete

        Returns:
            Dictionary with confirmation

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.BASE_URL}/personas/{persona_id}",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    # ====================
    # Knowledge Base Methods
    # ====================

    async def create_document(
        self,
        document_name: str,
        file_url_or_path: str,
        tags: list[str] | None = None,
        crawl: bool = False,
    ) -> dict[str, Any]:
        """Create a document in the knowledge base.

        Args:
            document_name: Name for the document
            file_url_or_path: URL or path to the document
            tags: Optional list of tags for the document
            crawl: Whether to crawl linked documents (for URLs)

        Returns:
            Dictionary with document_id

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        payload: dict[str, Any] = {
            "document_name": document_name,
            "file_url_or_path": file_url_or_path,
        }

        if tags:
            payload["tags"] = tags

        if crawl:
            payload["crawl"] = crawl

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/documents",
                    headers=self.headers,
                    json=payload,
                    timeout=60.0,  # Longer timeout for document uploads
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def get_document(self, document_id: str) -> dict[str, Any]:
        """Get document details.

        Args:
            document_id: The document ID

        Returns:
            Dictionary with document details

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/documents/{document_id}",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def list_documents(self) -> list[dict[str, Any]]:
        """List all documents in the knowledge base.

        Returns:
            List of document dictionaries

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/documents",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data: dict[str, Any] = cast(dict[str, Any], response.json())
                documents = data.get("documents", data)
                return cast(list[dict[str, Any]], documents) if isinstance(documents, list) else []
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def delete_document(self, document_id: str) -> dict[str, Any]:
        """Delete a document from the knowledge base.

        Args:
            document_id: The document ID to delete

        Returns:
            Dictionary with confirmation

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.BASE_URL}/documents/{document_id}",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    # ====================
    # Guardrails Methods
    # ====================

    async def create_guardrails(
        self,
        guardrails: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Create guardrails configuration.

        Args:
            guardrails: List of guardrail configurations

        Returns:
            Dictionary with guardrails_id

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/guardrails",
                    headers=self.headers,
                    json={"guardrails": guardrails},
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def get_guardrails(self, guardrails_id: str) -> dict[str, Any]:
        """Get guardrails configuration.

        Args:
            guardrails_id: The guardrails ID

        Returns:
            Dictionary with guardrails configuration

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/guardrails/{guardrails_id}",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    # ====================
    # Replica Methods
    # ====================

    async def list_replicas(self) -> list[dict[str, Any]]:
        """List all available replicas.

        Returns:
            List of replica dictionaries

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/replicas",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data: dict[str, Any] = cast(dict[str, Any], response.json())
                replicas = data.get("replicas", data)
                return cast(list[dict[str, Any]], replicas) if isinstance(replicas, list) else []
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    async def get_replica(self, replica_id: str) -> dict[str, Any]:
        """Get replica details including training progress.

        Args:
            replica_id: The replica ID

        Returns:
            Dictionary with replica details and training_progress

        Raises:
            TavusAPIError: If the API returns an error
            TavusConnectionError: If unable to connect to the API
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/replicas/{replica_id}",
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                return cast(dict[str, Any], response.json())
        except httpx.HTTPStatusError as e:
            self._handle_http_error(e)
            raise
        except httpx.RequestError as e:
            self._handle_connection_error(e)
            raise

    # ====================
    # Health Check
    # ====================

    async def health_check(self) -> bool:
        """Check if Tavus API is accessible via GET /v2/conversations with limit=1.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/conversations",
                    headers=self.headers,
                    params={"limit": 1},
                    timeout=10.0,
                )
                response.raise_for_status()
                return True
        except Exception:
            return False

    def _default_context(self) -> str:
        """Default conversational context for ARIA.

        Returns:
            Default context string for ARIA conversations
        """
        return """You are ARIA, an AI Department Director for Life Sciences commercial teams.
You help sales professionals with research, meeting preparation, and strategic advice.
You are professional, knowledgeable about the Life Sciences industry, and proactive.
Keep responses concise and actionable."""


# Singleton instance
_tavus_client: TavusClient | None = None


def get_tavus_client() -> TavusClient:
    """Get or create Tavus client singleton.

    Returns:
        The shared TavusClient instance
    """
    global _tavus_client
    if _tavus_client is None:
        _tavus_client = TavusClient()
    return _tavus_client
