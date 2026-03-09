"""MeetingBaaS API client for dispatching meeting bots.

MeetingBaaS provides bot-as-a-service for joining Zoom and Teams meetings
to record, transcribe, and observe on behalf of a user.
"""

import logging
from typing import Any

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.meetingbaas.com"


class MeetingBaaSError(Exception):
    """Raised when MeetingBaaS API returns an error response."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class MeetingBaaSClient:
    """Client for MeetingBaaS bot dispatch API."""

    def __init__(self) -> None:
        """Initialize with API key from settings."""
        api_key = settings.MEETINGBAAS_API_KEY
        self.api_key: str = api_key.get_secret_value() if api_key else ""
        self.headers: dict[str, str] = {
            "x-spoke-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    async def create_bot(
        self,
        meeting_url: str,
        bot_name: str,
        webhook_url: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch a bot to join a meeting.

        Args:
            meeting_url: The Zoom or Teams meeting URL.
            bot_name: Display name for the bot in the meeting.
            webhook_url: Optional webhook URL for status callbacks.

        Returns:
            Dict with bot_id and status from MeetingBaaS.

        Raises:
            MeetingBaaSError: If the API returns an error.
        """
        payload: dict[str, Any] = {
            "meeting_url": meeting_url,
            "bot_name": bot_name,
            "recording_mode": "speaker_view",
            "bot_image": "https://aria.luminone.com/aria-avatar.png",
            "entry_message": f"Hi everyone, {bot_name} has joined to take notes.",
            "reserved": False,
            "speech_to_text": {
                "provider": "Default",
            },
        }
        if webhook_url:
            payload["webhook_url"] = webhook_url

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    f"{BASE_URL}/bots",
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                logger.info(
                    "MeetingBaaS bot created",
                    extra={
                        "bot_id": data.get("bot_id"),
                        "meeting_url": meeting_url,
                        "bot_name": bot_name,
                    },
                )
                return data
            except httpx.HTTPStatusError as e:
                self._handle_http_error(e)
                raise  # unreachable but satisfies type checker
            except httpx.RequestError as e:
                logger.error("MeetingBaaS connection error: %s", e)
                raise MeetingBaaSError(f"Connection error: {e}") from e

    async def get_bot_status(self, bot_id: str) -> dict[str, Any]:
        """Get the current status of a dispatched bot.

        Args:
            bot_id: The bot ID returned from create_bot.

        Returns:
            Dict with bot status and metadata.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(
                    f"{BASE_URL}/bots/{bot_id}",
                    headers=self.headers,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                self._handle_http_error(e)
                raise
            except httpx.RequestError as e:
                logger.error("MeetingBaaS connection error: %s", e)
                raise MeetingBaaSError(f"Connection error: {e}") from e

    async def delete_bot(self, bot_id: str) -> dict[str, Any]:
        """Remove a bot from a meeting.

        Args:
            bot_id: The bot ID to remove.

        Returns:
            Dict with deletion confirmation.
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.delete(
                    f"{BASE_URL}/bots/{bot_id}",
                    headers=self.headers,
                )
                response.raise_for_status()
                logger.info("MeetingBaaS bot deleted", extra={"bot_id": bot_id})
                return response.json()
            except httpx.HTTPStatusError as e:
                self._handle_http_error(e)
                raise
            except httpx.RequestError as e:
                logger.error("MeetingBaaS connection error: %s", e)
                raise MeetingBaaSError(f"Connection error: {e}") from e

    def _handle_http_error(self, error: httpx.HTTPStatusError) -> None:
        """Handle HTTP errors from MeetingBaaS API.

        Raises:
            MeetingBaaSError: Always.
        """
        status_code = error.response.status_code
        try:
            details = error.response.json()
            message = details.get("message", str(details))
        except Exception:
            details = error.response.text
            message = f"MeetingBaaS API error: {status_code}"

        logger.error(
            "MeetingBaaS API error: status=%s message=%s",
            status_code,
            message,
        )
        raise MeetingBaaSError(message, status_code=status_code, details=details)


_client: MeetingBaaSClient | None = None


def get_meetingbaas_client() -> MeetingBaaSClient:
    """Get or create the singleton MeetingBaaS client.

    Returns:
        MeetingBaaSClient instance.
    """
    global _client
    if _client is None:
        _client = MeetingBaaSClient()
    return _client
