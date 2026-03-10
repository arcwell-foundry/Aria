"""Gamma API client for AI-powered presentation generation.

Gamma's API allows programmatic creation of presentations, documents,
and websites from text prompts or existing content.

API Flow:
1. POST /v1.0/generations - Start async generation, returns generationId
2. Poll GET /v1.0/generations/{id} - Check status until "completed"
3. Receive gammaId, gammaUrl when complete

Text modes:
- generate: Create from scratch using AI
- condense: Summarize existing content
- preserve: Keep content as-is, just format nicely
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)


class GammaTextMode(str, Enum):
    """Text processing mode for Gamma generation."""

    GENERATE = "generate"  # Create from scratch using AI
    CONDENSE = "condense"  # Summarize existing content
    PRESERVE = "preserve"  # Keep content, just format


@dataclass
class GammaGenerationResult:
    """Result of a completed Gamma generation."""

    generation_id: str
    gamma_id: str
    gamma_url: str
    credits_deducted: int
    credits_remaining: int


class GammaClientError(Exception):
    """Base exception for Gamma client errors."""

    pass


class GammaExportError(GammaClientError):
    """Raised when PPTX export fails or times out."""

    pass


class GammaClient:
    """Client for Gamma API - AI-powered presentation generation.

    Provides methods to create presentations from text prompts or
    existing content, with async polling for completion.
    """

    BASE_URL = "https://public-api.gamma.app/v1.0"
    POLL_INTERVAL = 3.0  # seconds between status checks
    MAX_POLL_ATTEMPTS = 100  # ~5 minutes max wait

    def __init__(self) -> None:
        """Initialize the Gamma client."""
        try:
            if settings.GAMMA_API_KEY:
                self._api_key = settings.GAMMA_API_KEY.get_secret_value()
            else:
                self._api_key = None
        except Exception as e:
            logger.exception("Failed to get GAMMA_API_KEY: %s", e)
            self._api_key = None

        if not self._api_key:
            logger.warning(
                "GammaClient initialized WITHOUT API key - all generations will fail"
            )
        else:
            logger.info("GammaClient initialized with API key")

    @property
    def is_configured(self) -> bool:
        """Check if the client has a valid API key."""
        return bool(self._api_key)

    async def _get_headers(self) -> dict[str, str]:
        """Get API request headers."""
        return {
            "x-api-key": self._api_key or "",
            "Content-Type": "application/json",
        }

    async def start_generation(
        self,
        input_text: str,
        text_mode: GammaTextMode = GammaTextMode.GENERATE,
    ) -> str:
        """Start an async Gamma generation.

        Args:
            input_text: The text prompt or content to generate from.
            text_mode: How to process the input text.

        Returns:
            generation_id for polling.

        Raises:
            GammaClientError: If API key not configured or API error.
        """
        if not self._api_key:
            raise GammaClientError("GAMMA_API_KEY not configured")

        logger.info(
            "Gamma generation started: mode=%s text_len=%d",
            text_mode.value,
            len(input_text),
        )

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{self.BASE_URL}/generations",
                    headers=await self._get_headers(),
                    json={
                        "inputText": input_text,
                        "textMode": text_mode.value,
                    },
                )
                response.raise_for_status()
                data = response.json()
                generation_id = data["generationId"]
                logger.info("Gamma generation queued: id=%s", generation_id)
                return generation_id
            except httpx.HTTPStatusError as e:
                error_body = e.response.text[:500] if e.response else "No response"
                logger.exception("Gamma API HTTP error: %s - %s", e.response.status_code, error_body)
                raise GammaClientError(f"Gamma API error: {error_body}") from e
            except Exception as e:
                logger.exception("Gamma generation failed unexpectedly: %s", e)
                raise GammaClientError(f"Gamma generation failed: {e}") from e

    async def check_generation(self, generation_id: str) -> dict[str, Any]:
        """Check the status of a generation.

        Args:
            generation_id: The generation ID to check.

        Returns:
            Dict with status and result data if completed.

        Raises:
            GammaClientError: If API error.
        """
        if not self._api_key:
            raise GammaClientError("GAMMA_API_KEY not configured")

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/generations/{generation_id}",
                    headers=await self._get_headers(),
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                error_body = e.response.text[:500] if e.response else "No response"
                raise GammaClientError(f"Gamma API error: {error_body}") from e

    async def wait_for_completion(
        self,
        generation_id: str,
        poll_interval: float | None = None,
        max_attempts: int | None = None,
    ) -> GammaGenerationResult:
        """Poll until generation completes and return result.

        Args:
            generation_id: The generation ID to wait for.
            poll_interval: Seconds between status checks (default: 3.0).
            max_attempts: Maximum polling attempts (default: 100).

        Returns:
            GammaGenerationResult with gamma URL and metadata.

        Raises:
            GammaClientError: If generation fails or times out.
        """
        interval = poll_interval or self.POLL_INTERVAL
        attempts = max_attempts or self.MAX_POLL_ATTEMPTS

        for attempt in range(attempts):
            data = await self.check_generation(generation_id)
            status = data.get("status")

            if status == "completed":
                logger.info(
                    "Gamma generation completed: id=%s url=%s",
                    generation_id,
                    data.get("gammaUrl"),
                )
                return GammaGenerationResult(
                    generation_id=generation_id,
                    gamma_id=data.get("gammaId", ""),
                    gamma_url=data.get("gammaUrl", ""),
                    credits_deducted=data.get("credits", {}).get("deducted", 0),
                    credits_remaining=data.get("credits", {}).get("remaining", 0),
                )

            if status == "failed":
                error_msg = data.get("error", "Unknown error")
                raise GammaClientError(f"Gamma generation failed: {error_msg}")

            logger.debug(
                "Gamma generation pending: id=%s attempt=%d/%d",
                generation_id,
                attempt + 1,
                attempts,
            )
            await asyncio.sleep(interval)

        raise GammaClientError(
            f"Gamma generation timed out after {attempts * interval}s"
        )

    async def generate(
        self,
        input_text: str,
        text_mode: GammaTextMode = GammaTextMode.GENERATE,
        poll_interval: float | None = None,
        max_attempts: int | None = None,
    ) -> GammaGenerationResult:
        """Generate a Gamma presentation (convenience method).

        Combines start_generation and wait_for_completion into a single call.

        Args:
            input_text: The text prompt or content to generate from.
            text_mode: How to process the input text.
            poll_interval: Seconds between status checks.
            max_attempts: Maximum polling attempts.

        Returns:
            GammaGenerationResult with gamma URL and metadata.

        Raises:
            GammaClientError: If any step fails.
        """
        generation_id = await self.start_generation(input_text, text_mode)
        return await self.wait_for_completion(generation_id, poll_interval, max_attempts)

    async def export_pptx(self, gamma_id: str) -> bytes:
        """Export a Gamma presentation as PPTX bytes.

        Calls Gamma export endpoint to download the presentation file.

        Args:
            gamma_id: Gamma's internal presentation ID.

        Returns:
            Raw PPTX file bytes.

        Raises:
            GammaExportError: If export fails or times out.
        """
        if not self._api_key:
            raise GammaExportError("GAMMA_API_KEY not configured")

        logger.info("Exporting PPTX for gamma_id=%s", gamma_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{self.BASE_URL}/decks/{gamma_id}/export/pptx",
                    headers=await self._get_headers(),
                )
                response.raise_for_status()
                logger.info(
                    "PPTX export complete: gamma_id=%s size=%d bytes",
                    gamma_id,
                    len(response.content),
                )
                return response.content
            except httpx.HTTPStatusError as e:
                error_body = e.response.text[:500] if e.response else "No response"
                logger.exception(
                    "Gamma PPTX export HTTP error: %s - %s",
                    e.response.status_code,
                    error_body,
                )
                raise GammaExportError(
                    f"Gamma PPTX export failed: {error_body}"
                ) from e
            except httpx.TimeoutException as e:
                logger.exception("Gamma PPTX export timed out: gamma_id=%s", gamma_id)
                raise GammaExportError(
                    f"Gamma PPTX export timed out for gamma_id={gamma_id}"
                ) from e
            except Exception as e:
                logger.exception("Gamma PPTX export failed: %s", e)
                raise GammaExportError(
                    f"Gamma PPTX export failed: {e}"
                ) from e

    async def health_check(self) -> bool:
        """Verify Gamma API connectivity.

        Returns:
            True if the API responds successfully.
        """
        if not self._api_key:
            return False

        try:
            # Start a minimal generation to test connectivity
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/generations",
                    headers=await self._get_headers(),
                    json={
                        "inputText": "test",
                        "textMode": "generate",
                    },
                )
                # 200 means we can at least start a generation
                # 400 validation error also means auth works
                return response.status_code in (200, 400)
        except Exception as e:
            logger.warning("Gamma health check failed: %s", e)
            return False


# Singleton client instance
_client: GammaClient | None = None


def get_gamma_client() -> GammaClient:
    """Get the singleton Gamma client instance.

    Returns:
        GammaClient instance (may not be configured if API key missing).
    """
    global _client
    if _client is None:
        _client = GammaClient()
    return _client
