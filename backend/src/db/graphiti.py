"""Graphiti client module for temporal knowledge graph operations."""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from src.core.resilience import graphiti_circuit_breaker
from src.core.config import settings
from src.core.exceptions import GraphitiConnectionError

if TYPE_CHECKING:
    from graphiti_core import Graphiti

logger = logging.getLogger(__name__)

_graphiti_circuit_breaker = graphiti_circuit_breaker

# Maximum seconds to wait for Neo4j connection during initialization
_NEO4J_INIT_TIMEOUT = 10.0


class GraphitiClient:
    """Singleton Graphiti client for Neo4j operations.

    Provides async access to Graphiti temporal knowledge graph.
    Initializes connection on first use and manages lifecycle.
    """

    _instance: "Graphiti | None" = None
    _initialized: bool = False
    _init_failed: bool = False

    @classmethod
    async def get_instance(cls) -> "Graphiti":
        """Get or create the Graphiti client singleton.

        Returns:
            Initialized Graphiti client.

        Raises:
            GraphitiConnectionError: If client initialization fails.
        """
        # Fast-fail if a previous initialization already failed — avoids
        # repeated timeout waits on every call when Neo4j is down.
        if cls._init_failed:
            raise GraphitiConnectionError(
                "Graphiti initialization previously failed; "
                "call reset_client() to retry"
            )
        if cls._instance is None:
            await cls._initialize()
        return cls._instance  # type: ignore[return-value]

    @classmethod
    async def _initialize(cls) -> None:
        """Initialize the Graphiti client with Neo4j connection.

        Fast-fails when OPENAI_API_KEY is missing or when Neo4j is
        unreachable within ``_NEO4J_INIT_TIMEOUT`` seconds, preventing
        the retry storm that would otherwise hang the server.
        """
        # Early bail-out: OPENAI_API_KEY is required for the embedder
        openai_key = os.environ.get("OPENAI_API_KEY", "") or (
            settings.OPENAI_API_KEY.get_secret_value()
            if settings.OPENAI_API_KEY
            else ""
        )
        if not openai_key:
            cls._init_failed = True
            logger.warning(
                "[EMAIL_PIPELINE] OPENAI_API_KEY not set, skipping Graphiti/Neo4j initialization"
            )
            raise GraphitiConnectionError(
                "OPENAI_API_KEY not set — cannot initialize Graphiti embedder"
            )

        try:
            await asyncio.wait_for(
                cls._do_initialize(openai_key), timeout=_NEO4J_INIT_TIMEOUT
            )
        except TimeoutError as exc:
            cls._init_failed = True
            cls._instance = None
            cls._initialized = False
            logger.warning(
                "[EMAIL_PIPELINE] Neo4j connection timed out after %.0fs, "
                "skipping graph operations",
                _NEO4J_INIT_TIMEOUT,
            )
            raise GraphitiConnectionError(
                f"Neo4j connection timed out after {_NEO4J_INIT_TIMEOUT}s"
            ) from exc
        except GraphitiConnectionError:
            cls._init_failed = True
            raise
        except Exception as e:
            cls._init_failed = True
            cls._instance = None
            cls._initialized = False
            logger.exception(
                "[EMAIL_PIPELINE] Graphiti initialization failed: %s", e
            )
            raise GraphitiConnectionError(str(e)) from e

    @classmethod
    async def _do_initialize(cls, openai_key: str) -> None:
        """Inner initialization logic, called with a timeout wrapper."""
        from graphiti_core import Graphiti
        from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
        from graphiti_core.llm_client import LLMConfig
        from graphiti_core.llm_client.anthropic_client import AnthropicClient

        llm_client = AnthropicClient(
            config=LLMConfig(
                api_key=settings.ANTHROPIC_API_KEY.get_secret_value(),
                model="claude-sonnet-4-20250514",
                small_model="claude-3-5-haiku-20241022",
            )
        )

        embedder = OpenAIEmbedder(
            config=OpenAIEmbedderConfig(
                api_key=openai_key,
                embedding_model="text-embedding-3-small",
            )
        )

        cls._instance = Graphiti(
            uri=settings.NEO4J_URI,
            user=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD.get_secret_value(),
            llm_client=llm_client,
            embedder=embedder,
        )

        await cls._instance.build_indices_and_constraints()
        cls._initialized = True
        logger.info("Graphiti client initialized successfully")

    @classmethod
    async def close(cls) -> None:
        """Close the Graphiti client connection."""
        if cls._instance is not None:
            try:
                await cls._instance.close()  # type: ignore[no-untyped-call]
                logger.info("Graphiti client connection closed")
            except Exception as e:
                logger.warning(f"Error closing Graphiti connection: {e}")
            finally:
                cls._instance = None
                cls._initialized = False

    @classmethod
    def reset_client(cls) -> None:
        """Reset the client singleton (useful for testing or retrying init)."""
        cls._instance = None
        cls._initialized = False
        cls._init_failed = False

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if client is initialized.

        Returns:
            True if client is initialized and ready.
        """
        return cls._initialized

    @classmethod
    async def health_check(cls) -> bool:
        """Check if the Graphiti/Neo4j connection is healthy.

        Returns:
            True if connection is healthy, False otherwise.
        """
        if not cls._initialized or cls._instance is None:
            return False

        try:
            # Execute a simple query to verify connectivity (5s timeout)
            await asyncio.wait_for(
                cls._instance.driver.execute_query("RETURN 1 AS health"),
                timeout=5.0,
            )
            return True
        except Exception as e:
            logger.warning(f"Graphiti health check failed: {e}")
            return False

    @classmethod
    async def add_episode(
        cls,
        name: str,
        episode_body: str,
        source_description: str,
        reference_time: datetime,
    ) -> object:
        """Add an episode to the knowledge graph.

        Args:
            name: Unique name for the episode.
            episode_body: Content of the episode.
            source_description: Description of the data source.
            reference_time: When this episode occurred.

        Returns:
            The created episode object.

        Raises:
            GraphitiConnectionError: If client is not initialized.
        """
        from graphiti_core.nodes import EpisodeType

        client = await cls.get_instance()
        result = await _graphiti_circuit_breaker.call(
            client.add_episode,
            name=name,
            episode_body=episode_body,
            source=EpisodeType.text,
            source_description=source_description,
            reference_time=reference_time,
        )
        return result

    @classmethod
    async def add_entity(
        cls,
        name: str,
        entity_type: str,
        metadata: dict[str, Any],
        **_kwargs: Any,
    ) -> object:
        """Store an entity by creating an episode that references it.

        Wraps entity creation as an episode with entity metadata,
        since Graphiti's core abstraction is episodes (not raw nodes).

        Args:
            name: Entity name (e.g. person name, company name).
            entity_type: Entity type (e.g. 'person', 'company', 'product').
            metadata: Additional properties for the entity.
            **_kwargs: Additional keyword args (e.g. user_id) for future use.

        Returns:
            The created episode object.
        """
        props = json.dumps(metadata) if metadata else "{}"
        episode_body = f"Entity discovered: {name} ({entity_type}). Properties: {props}"
        return await cls.add_episode(
            name=f"entity_{entity_type}_{name}",
            episode_body=episode_body,
            source_description="onboarding_entity_extraction",
            reference_time=datetime.now(UTC),
        )

    @classmethod
    async def search(cls, query: str) -> list[object]:
        """Search the knowledge graph.

        Args:
            query: Search query string.

        Returns:
            List of matching edges/facts.

        Raises:
            GraphitiConnectionError: If client is not initialized.
        """
        client = await cls.get_instance()
        results = await _graphiti_circuit_breaker.call(client.search, query)
        return list(results)
