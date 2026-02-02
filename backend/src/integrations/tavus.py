"""Tavus Conversational Video API client."""

from typing import Any, cast

import httpx

from src.core.config import settings


class TavusClient:
    """Client for Tavus Conversational Video API."""

    BASE_URL = "https://tavusapi.com/v2"

    def __init__(self) -> None:
        """Initialize the Tavus client with API credentials."""
        self.api_key = settings.TAVUS_API_KEY
        self.persona_id: str | None = getattr(settings, "TAVUS_PERSONA_ID", None) or None
        self.headers: dict[str, str] = {
            "x-api-key": self.api_key.get_secret_value() if self.api_key else "",
            "Content-Type": "application/json",
        }

    async def create_conversation(
        self,
        user_id: str,
        conversation_name: str,
        context: str | None = None,
        custom_greeting: str | None = None,
        properties: dict[str, str] | None = None,
    ) -> dict[str, object]:
        """Create a new Tavus conversation and return conversation details.

        Args:
            user_id: The user's ID for tracking
            conversation_name: Name for the conversation
            context: Optional conversational context
            custom_greeting: Optional custom greeting message
            properties: Optional additional properties

        Returns:
            Dictionary with conversation details including room URL
        """
        async with httpx.AsyncClient() as client:
            payload: dict[str, object] = {
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

            response = await client.post(
                f"{self.BASE_URL}/conversations",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            return cast(dict[str, object], response.json())

    async def get_conversation(self, conversation_id: str) -> dict[str, object]:
        """Get conversation details including room URL.

        Args:
            conversation_id: The Tavus conversation ID

        Returns:
            Dictionary with conversation details
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/conversations/{conversation_id}",
                headers=self.headers,
            )
            response.raise_for_status()
            return cast(dict[str, object], response.json())

    async def end_conversation(self, conversation_id: str) -> dict[str, object]:
        """End an active conversation.

        Args:
            conversation_id: The Tavus conversation ID

        Returns:
            Dictionary with response details
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/conversations/{conversation_id}/end",
                headers=self.headers,
            )
            response.raise_for_status()
            return cast(dict[str, object], response.json())

    async def list_conversations(
        self,
        limit: int = 10,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        """List conversations.

        Args:
            limit: Maximum number of conversations to return
            status: Optional status filter

        Returns:
            List of conversation dictionaries
        """
        async with httpx.AsyncClient() as client:
            params: dict[str, str | int] = {"limit": limit}
            if status:
                params["status"] = status

            response = await client.get(
                f"{self.BASE_URL}/conversations",
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            data: dict[str, Any] = cast(dict[str, Any], response.json())
            conversations = data.get("conversations")
            return (
                cast(list[dict[str, object]], conversations)
                if isinstance(conversations, list)
                else []
            )

    async def get_persona(self, persona_id: str | None = None) -> dict[str, object]:
        """Get persona details.

        Args:
            persona_id: Optional persona ID (defaults to configured persona)

        Returns:
            Dictionary with persona details
        """
        pid = persona_id or self.persona_id
        if not pid:
            raise ValueError("Persona ID is required")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}/personas/{pid}",
                headers=self.headers,
            )
            response.raise_for_status()
            return cast(dict[str, object], response.json())

    async def health_check(self) -> bool:
        """Check if Tavus API is accessible.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            await self.get_persona()
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
