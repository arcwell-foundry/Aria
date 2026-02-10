"""ScoutAgent module for ARIA.

Gathers intelligence from web search, news, social media, and filters signals.
"""

import logging
from datetime import UTC
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult
from src.agents.skill_aware_agent import SkillAwareAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.skills.index import SkillIndex
    from src.skills.orchestrator import SkillOrchestrator

logger = logging.getLogger(__name__)


class ScoutAgent(SkillAwareAgent):
    """Gathers intelligence from web, news, and social sources.

    The Scout agent monitors entities, searches for signals,
    deduplicates results, and filters noise from relevant information.
    """

    name = "Scout"
    description = "Intelligence gathering and filtering"
    agent_id = "scout"

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
    ) -> None:
        """Initialize the Scout agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
            skill_orchestrator: Optional orchestrator for multi-skill execution.
            skill_index: Optional index for skill discovery.
        """
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
        )

    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate Scout agent task input.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Check required fields exist
        if "entities" not in task:
            return False

        # Validate entities is a non-empty list
        entities = task["entities"]
        if not isinstance(entities, list):
            return False
        if len(entities) == 0:
            return False

        # Validate signal_types is a list if present
        if "signal_types" in task:
            signal_types = task["signal_types"]
            if not isinstance(signal_types, list):
                return False

        return True

    def _register_tools(self) -> dict[str, Any]:
        """Register Scout agent's intelligence gathering tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "web_search": self._web_search,
            "news_search": self._news_search,
            "social_monitor": self._social_monitor,
            "detect_signals": self._detect_signals,
            "deduplicate_signals": self._deduplicate_signals,
        }

    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the scout agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        # OODA ACT: Log skill consideration before native execution
        await self._log_skill_consideration()

        logger.info("Scout agent starting intelligence gathering task")

        # Extract task parameters
        entities = task["entities"]
        signal_types = task.get("signal_types")

        # Step 1: Detect signals for all entities
        signals = await self._detect_signals(
            entities=entities,
            signal_types=signal_types,
        )

        # Step 2: Filter noise (low relevance signals)
        min_relevance = 0.5
        filtered_signals = [s for s in signals if s.get("relevance_score", 0) >= min_relevance]

        logger.info(
            f"Filtered {len(signals)} signals to {len(filtered_signals)} "
            f"with relevance >= {min_relevance}"
        )

        # Step 3: Deduplicate signals
        deduplicated_signals = await self._deduplicate_signals(filtered_signals)

        logger.info(f"Scout agent completed - returning {len(deduplicated_signals)} signals")

        return AgentResult(success=True, data=deduplicated_signals)

    async def _web_search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search the web for relevant information.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.

        Returns:
            List of search results with title, url, snippet.

        Raises:
            ValueError: If limit is less than or equal to zero.
        """
        # Return empty list for empty or whitespace-only queries
        if not query or query.strip() == "":
            return []

        # Validate limit
        if limit <= 0:
            raise ValueError(f"limit must be greater than 0, got {limit}")

        logger.info(
            f"Web search with query='{query}', limit={limit}",
        )

        # Mock web search results
        mock_results = [
            {
                "title": "Biotechnology Funding Trends 2024",
                "url": "https://example.com/biotech-funding",
                "snippet": "Latest trends in biotechnology funding show increased investment in gene therapy and diagnostic tools.",
            },
            {
                "title": "VC Investment in Life Sciences",
                "url": "https://example.com/vc-life-sciences",
                "snippet": "Venture capital firms are doubling down on life sciences investments with $50B deployed in 2024.",
            },
            {
                "title": "Emerging Biotech Companies to Watch",
                "url": "https://example.com/emerging-biotech",
                "snippet": "A roundup of the most promising emerging biotechnology companies seeking Series A funding.",
            },
        ]

        return mock_results[:limit]

    async def _news_search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search news sources for relevant articles.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.

        Returns:
            List of news articles with title, url, source, published_at.

        Raises:
            ValueError: If limit is less than or equal to zero.
        """
        # Return empty list for empty or whitespace-only queries
        if not query or query.strip() == "":
            return []

        # Validate limit
        if limit <= 0:
            raise ValueError(f"limit must be greater than 0, got {limit}")

        logger.info(
            f"News search with query='{query}', limit={limit}",
        )

        # Mock news search results
        from datetime import datetime

        mock_articles = [
            {
                "title": "Acme Corp Raises $50M in Series B Funding",
                "url": "https://techcrunch.com/2024/01/15/acme-corp-series-b",
                "source": "TechCrunch",
                "published_at": datetime(2024, 1, 15, tzinfo=UTC).isoformat(),
            },
            {
                "title": "Acme Corp Expands to European Markets",
                "url": "https://reuters.com/2024/01/10/acme-corp-europe",
                "source": "Reuters",
                "published_at": datetime(2024, 1, 10, tzinfo=UTC).isoformat(),
            },
            {
                "title": "Acme Corp CEO Named to Top 40 Under 40",
                "url": "https://forbes.com/2024/01/05/acme-corp-ceo",
                "source": "Forbes",
                "published_at": datetime(2024, 1, 5, tzinfo=UTC).isoformat(),
            },
        ]

        return mock_articles[:limit]

    async def _social_monitor(
        self,
        entity: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Monitor social media for entity mentions.

        Args:
            entity: Entity name to monitor (company, person, topic).
            limit: Maximum number of results to return.

        Returns:
            List of social mentions with content, author, platform, url.

        Raises:
            ValueError: If limit is less than or equal to zero.
        """
        # Return empty list for empty or whitespace-only entity
        if not entity or entity.strip() == "":
            return []

        # Validate limit
        if limit <= 0:
            raise ValueError(f"limit must be greater than 0, got {limit}")

        logger.info(
            f"Social monitoring for entity='{entity}', limit={limit}",
        )

        # Mock social media mentions
        mock_mentions = [
            {
                "content": f"Just heard about {entity}'s new product launch! Excited to see what they've built.",
                "author": "@industrywatcher",
                "platform": "twitter",
                "url": "https://twitter.com/industrywatcher/status/1234567890",
            },
            {
                "content": f"{entity} is hiring for senior engineering roles. Great opportunity!",
                "author": "Jane Smith",
                "platform": "linkedin",
                "url": "https://linkedin.com/posts/jane-smith-123",
            },
            {
                "content": f"Anyone else following {entity}'s growth? They're disrupting the industry.",
                "author": "u/techenthusiast",
                "platform": "reddit",
                "url": "https://reddit.com/r/technology/comments/abc123",
            },
        ]

        return mock_mentions[:limit]

    async def _detect_signals(
        self,
        entities: list[str],
        signal_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Detect market signals for monitored entities.

        Args:
            entities: List of entity names to monitor.
            signal_types: Optional list of signal types to filter by.

        Returns:
            List of detected signals with relevance scores.
        """
        # Return empty list for empty entities
        if not entities:
            return []

        logger.info(
            f"Detecting signals for entities={entities}, signal_types={signal_types}",
        )

        # Mock signals database
        all_signals = [
            {
                "company_name": "Acme Corp",
                "signal_type": "funding",
                "headline": "Acme Corp raises $50M Series B",
                "summary": "Acme Corp announced a $50M Series B funding round led by Sequoia Capital.",
                "source_url": "https://techcrunch.com/acme-series-b",
                "source_name": "TechCrunch",
                "relevance_score": 0.92,
                "detected_at": "2024-01-15T10:00:00Z",
            },
            {
                "company_name": "Acme Corp",
                "signal_type": "hiring",
                "headline": "Acme Corp hiring 50 engineers",
                "summary": "Acme Corp is expanding its engineering team with 50 new positions.",
                "source_url": "https://linkedin.com/company/acme-corp/jobs",
                "source_name": "LinkedIn",
                "relevance_score": 0.78,
                "detected_at": "2024-01-14T10:00:00Z",
            },
            {
                "company_name": "Beta Inc",
                "signal_type": "leadership",
                "headline": "Beta Inc appoints new CEO",
                "summary": "Beta Inc has appointed Jane Smith as its new Chief Executive Officer.",
                "source_url": "https://reuters.com/beta-new-ceo",
                "source_name": "Reuters",
                "relevance_score": 0.85,
                "detected_at": "2024-01-13T10:00:00Z",
            },
            {
                "company_name": "Beta Inc",
                "signal_type": "funding",
                "headline": "Beta Inc secures $25M in debt financing",
                "summary": "Beta Inc has secured $25M in debt financing to expand operations.",
                "source_url": "https://bloomberg.com/beta-financing",
                "source_name": "Bloomberg",
                "relevance_score": 0.73,
                "detected_at": "2024-01-12T10:00:00Z",
            },
        ]

        # Filter by entities
        filtered_signals = [s for s in all_signals if s["company_name"] in entities]

        # Filter by signal types if provided
        if signal_types:
            filtered_signals = [s for s in filtered_signals if s["signal_type"] in signal_types]

        return filtered_signals

    async def _deduplicate_signals(
        self,
        signals: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Remove duplicate signals based on content similarity.

        Args:
            signals: List of signals to deduplicate.

        Returns:
            Deduplicated list of signals.
        """
        if not signals:
            return []

        logger.info(f"Deduplicating {len(signals)} signals")

        seen_urls: set[str] = set()
        seen_headlines: set[str] = set()
        deduplicated: list[dict[str, Any]] = []

        # First pass: remove exact duplicates (same URL)
        for signal in signals:
            url = signal.get("source_url", "")
            if url and url in seen_urls:
                continue
            seen_urls.add(url)

            # Check for similar headlines (simple word-based similarity)
            headline = signal.get("headline", "")
            headline_lower = headline.lower().strip()

            # Check if headline is too similar to any seen headline
            is_duplicate = False
            for seen_headline in seen_headlines:
                if self._headlines_are_similar(headline_lower, seen_headline):
                    is_duplicate = True
                    # Keep the one with higher relevance score
                    existing = next(
                        (s for s in deduplicated if s.get("headline", "").lower() == seen_headline),
                        None,
                    )
                    if existing:
                        existing_relevance = existing.get("relevance_score", 0)
                        new_relevance = signal.get("relevance_score", 0)
                        if new_relevance > existing_relevance:
                            # Replace with higher relevance signal
                            deduplicated.remove(existing)
                            deduplicated.append(signal)
                    break

            if not is_duplicate:
                seen_headlines.add(headline_lower)
                deduplicated.append(signal)

        logger.info(f"After deduplication: {len(deduplicated)} signals")

        return deduplicated

    def _headlines_are_similar(
        self,
        headline1: str,
        headline2: str,
        threshold: float = 0.7,
    ) -> bool:
        """Check if two headlines are similar using word overlap.

        Args:
            headline1: First headline (lowercase).
            headline2: Second headline (lowercase).
            threshold: Similarity threshold (0-1).

        Returns:
            True if headlines are similar above threshold.
        """
        # Split into words
        words1 = set(headline1.split())
        words2 = set(headline2.split())

        if not words1 or not words2:
            return False

        # Calculate Jaccard similarity
        intersection = words1 & words2
        union = words1 | words2

        similarity = len(intersection) / len(union) if union else 0

        return similarity >= threshold
