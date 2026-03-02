"""Thesys C1 Generative UI service.

Wraps the Thesys C1 Visualize API (OpenAI-compatible) with circuit breaker
protection and graceful fallback to raw markdown when the service is
unavailable.
"""

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from src.core.config import settings
from src.core.resilience import CircuitBreakerOpen, thesys_circuit_breaker

logger = logging.getLogger(__name__)


class ThesysService:
    """Client for the Thesys C1 Visualize endpoint.

    Uses the OpenAI-compatible chat completions API with C1-specific models.
    Falls back to returning raw content when the service is unavailable or
    the circuit breaker is open.
    """

    def __init__(self) -> None:
        self._enabled = settings.thesys_configured
        self._client: AsyncOpenAI | None = None

        if self._enabled:
            self._client = AsyncOpenAI(
                api_key=settings.THESYS_API_KEY.get_secret_value(),
                base_url=settings.THESYS_BASE_URL,
            )

    @property
    def is_available(self) -> bool:
        """Check if the service is enabled and the circuit breaker is closed."""
        if not self._enabled:
            return False
        try:
            thesys_circuit_breaker.check()
            return True
        except CircuitBreakerOpen:
            return False

    async def visualize(self, content: str, system_prompt: str) -> str:
        """Send content through C1 for rich UI rendering.

        Args:
            content: The text content from Claude to visualize.
            system_prompt: The system prompt with rendering instructions.

        Returns:
            Rendered content from C1, or the original ``content`` unchanged
            if the service is unavailable or the call fails.
        """
        if not self._enabled:
            return content

        try:
            thesys_circuit_breaker.check()
        except CircuitBreakerOpen:
            logger.warning("Thesys circuit breaker open — returning raw content")
            return content

        start = time.perf_counter()
        try:
            result = await self._call_c1(content, system_prompt)
            thesys_circuit_breaker.record_success()
            elapsed = time.perf_counter() - start
            logger.info("Thesys C1 visualize completed in %.2fs", elapsed)
            return result
        except Exception as exc:
            thesys_circuit_breaker.record_failure()
            elapsed = time.perf_counter() - start
            logger.warning(
                "Thesys C1 visualize failed after %.2fs: %s", elapsed, exc,
            )
            return content

    async def _call_c1(self, content: str, system_prompt: str) -> str:
        """Internal non-streaming call to the C1 Visualize endpoint."""
        assert self._client is not None

        response = await self._client.chat.completions.create(
            model=settings.THESYS_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            stream=False,
            timeout=settings.THESYS_TIMEOUT,
        )

        choice = response.choices[0]
        return choice.message.content or content

    async def visualize_stream(
        self, content: str, system_prompt: str,
    ) -> AsyncIterator[str]:
        """Stream C1-rendered content chunk by chunk.

        Yields rendered content chunks. If the service is unavailable,
        yields the original content as a single chunk.
        """
        if not self._enabled or self._client is None:
            yield content
            return

        try:
            thesys_circuit_breaker.check()
        except CircuitBreakerOpen:
            yield content
            return

        start = time.perf_counter()
        try:
            stream = await self._client.chat.completions.create(
                model=settings.THESYS_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                stream=True,
                timeout=settings.THESYS_TIMEOUT,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

            thesys_circuit_breaker.record_success()
            elapsed = time.perf_counter() - start
            logger.info("Thesys C1 stream completed in %.2fs", elapsed)

        except Exception as exc:
            thesys_circuit_breaker.record_failure()
            elapsed = time.perf_counter() - start
            logger.warning(
                "Thesys C1 stream failed after %.2fs: %s — yielding raw content",
                elapsed,
                exc,
            )
            yield content


# Module-level singleton factory
_service_instance: ThesysService | None = None


def get_thesys_service() -> ThesysService:
    """Get or create the singleton ThesysService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ThesysService()
    return _service_instance
