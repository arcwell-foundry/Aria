"""Graphiti client module for temporal knowledge graph operations."""

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from src.core.config import settings
from src.core.exceptions import GraphitiConnectionError

if TYPE_CHECKING:
    from graphiti_core import Graphiti

logger = logging.getLogger(__name__)


class GraphitiClient:
    """Singleton Graphiti client for Neo4j operations.

    Provides async access to Graphiti temporal knowledge graph.
    Initializes connection on first use and manages lifecycle.
    """

    _instance: "Graphiti | None" = None
    _initialized: bool = False

    @classmethod
    async def get_instance(cls) -> "Graphiti":
        """Get or create the Graphiti client singleton.

        Returns:
            Initialized Graphiti client.

        Raises:
            GraphitiConnectionError: If client initialization fails.
        """
        if cls._instance is None:
            await cls._initialize()
        return cls._instance  # type: ignore[return-value]

    @classmethod
    async def _initialize(cls) -> None:
        """Initialize the Graphiti client with Neo4j connection."""
        try:
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
                    api_key=settings.OPENAI_API_KEY.get_secret_value(),
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

        except Exception as e:
            logger.exception("Failed to initialize Graphiti client")
            raise GraphitiConnectionError(str(e)) from e

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
        """Reset the client singleton (useful for testing)."""
        cls._instance = None
        cls._initialized = False

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
            await cls._instance.driver.verify_connectivity()
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
        result = await client.add_episode(
            name=name,
            episode_body=episode_body,
            source=EpisodeType.text,
            source_description=source_description,
            reference_time=reference_time,
        )
        return result

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
        results = await client.search(query)
        return list(results)
