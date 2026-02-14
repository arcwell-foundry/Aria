"""ScoutAgent module for ARIA.

Gathers intelligence from web search, news, social media, and filters signals.
Uses Exa API for real web search with Claude LLM fallback when Exa is unavailable.
"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from src.agents.base import AgentResult
from src.agents.skill_aware_agent import SkillAwareAgent
from src.core.config import settings

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.skills.index import SkillIndex
    from src.skills.orchestrator import SkillOrchestrator

logger = logging.getLogger(__name__)


def _extract_json_from_text(text: str) -> Any:
    """Extract JSON from text that may be wrapped in markdown code fences.

    Tries multiple strategies:
    1. Direct JSON parse of the full text
    2. Regex extraction from ```json ... ``` or ``` ... ``` code fences
    3. Finding the outermost [ ] or { } boundaries and parsing that

    Args:
        text: Raw text that may contain JSON.

    Returns:
        Parsed JSON object (dict or list).

    Raises:
        ValueError: If no valid JSON can be extracted.
    """
    # Strategy 1: Direct parse
    text_stripped = text.strip()
    try:
        return json.loads(text_stripped)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Code fence extraction
    fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
    fence_match = re.search(fence_pattern, text_stripped, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find outermost brackets/braces
    # Try array first, then object
    for open_char, close_char in [("[", "]"), ("{", "}")]:
        start = text_stripped.find(open_char)
        if start == -1:
            continue
        # Find the matching closing character
        depth = 0
        for i in range(start, len(text_stripped)):
            if text_stripped[i] == open_char:
                depth += 1
            elif text_stripped[i] == close_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text_stripped[start : i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not extract valid JSON from text: {text_stripped[:200]}...")


class ScoutAgent(SkillAwareAgent):
    """Gathers intelligence from web, news, and social sources.

    The Scout agent monitors entities, searches for signals,
    deduplicates results, and filters noise from relevant information.

    Uses ExaEnrichmentProvider for real-time web intelligence when configured,
    with Claude LLM fallback for generating intelligence based on
    training knowledge.
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
        self._exa_provider: Any = None
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
        )

    def _get_exa_provider(self) -> Any:
        """Lazily initialize and return the ExaEnrichmentProvider."""
        if self._exa_provider is None:
            try:
                from src.agents.capabilities.enrichment_providers.exa_provider import (
                    ExaEnrichmentProvider,
                )

                self._exa_provider = ExaEnrichmentProvider()
                logger.info("ScoutAgent: ExaEnrichmentProvider initialized")
            except Exception as e:
                logger.warning("ScoutAgent: Failed to initialize ExaEnrichmentProvider: %s", e)
        return self._exa_provider

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
            "find_similar_pages": self._find_similar_pages,
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

        Uses ExaEnrichmentProvider when available, falls back to Claude LLM generation.

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

        # Try Exa provider first
        exa = self._get_exa_provider()
        if exa:
            try:
                results = await exa.search_fast(query=query, num_results=limit)

                formatted_results: list[dict[str, Any]] = []
                for item in results:
                    formatted_results.append({
                        "title": item.title,
                        "url": item.url,
                        "snippet": (item.text or "")[:500],
                    })

                logger.info(f"Exa web search returned {len(formatted_results)} results for '{query}'")
                return formatted_results[:limit]

            except Exception as e:
                logger.warning(f"Exa web search failed for '{query}': {e}")

        # LLM fallback: ask Claude to generate intelligence results
        try:
            prompt = (
                f'Generate {limit} realistic web search results for the query: "{query}"\n\n'
                "Based on your training knowledge, provide results that would be relevant "
                "for a life sciences commercial intelligence analyst.\n\n"
                "Return ONLY a JSON array with objects containing:\n"
                '- "title": article/page title\n'
                '- "url": realistic URL\n'
                '- "snippet": 1-2 sentence summary\n\n'
                "Return valid JSON only, no explanation."
            )

            response_text = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are a web intelligence research assistant. "
                    "Return only valid JSON arrays. No markdown, no explanation."
                ),
                temperature=0.3,
            )

            parsed = _extract_json_from_text(response_text)
            if isinstance(parsed, list):
                logger.info(f"LLM fallback web search returned {len(parsed)} results for '{query}'")
                return parsed[:limit]

            logger.warning("LLM web search response was not a list")
            return []

        except Exception as e:
            logger.warning(f"LLM fallback web search failed for '{query}': {e}")
            return []

    async def _news_search(
        self,
        query: str,
        limit: int = 10,
        days_back: int = 30,
    ) -> list[dict[str, Any]]:
        """Search news sources for relevant articles.

        Uses ExaEnrichmentProvider when available, falls back to Claude LLM generation.

        Args:
            query: Search query string.
            limit: Maximum number of results to return.
            days_back: Number of days to look back (default 30, use 1 for daily mode).

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
            f"News search with query='{query}', limit={limit}, days_back={days_back}",
        )

        # Try Exa provider first
        exa = self._get_exa_provider()
        if exa:
            try:
                results = await exa.search_news(
                    query=f"{query} news",
                    num_results=limit,
                    days_back=days_back,
                )

                articles: list[dict[str, Any]] = []
                for item in results:
                    url = item.url
                    # Extract domain as source name
                    source = ""
                    if url:
                        try:
                            parsed_url = urlparse(url)
                            domain = parsed_url.netloc.replace("www.", "")
                            # Capitalize domain parts for readability
                            source = domain.split(".")[0].capitalize()
                        except Exception:
                            source = "Unknown"

                    articles.append({
                        "title": item.title,
                        "url": url,
                        "source": source,
                        "published_at": item.published_date or datetime.now(tz=UTC).isoformat(),
                    })

                logger.info(f"Exa news search returned {len(articles)} articles for '{query}'")
                return articles[:limit]

            except Exception as e:
                logger.warning(f"Exa news search failed for '{query}': {e}")

        # LLM fallback: ask Claude for recent news
        try:
            prompt = (
                f'Generate {limit} realistic recent news articles about: "{query}"\n\n'
                "Based on your training knowledge, provide news results relevant "
                "to life sciences commercial intelligence.\n\n"
                "Return ONLY a JSON array with objects containing:\n"
                '- "title": news headline\n'
                '- "url": realistic news URL\n'
                '- "source": publication name (e.g., Reuters, FiercePharma, STAT News)\n'
                '- "published_at": ISO 8601 datetime string\n\n'
                "Return valid JSON only, no explanation."
            )

            response_text = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are a news intelligence research assistant for life sciences. "
                    "Return only valid JSON arrays. No markdown, no explanation."
                ),
                temperature=0.3,
            )

            parsed = _extract_json_from_text(response_text)
            if isinstance(parsed, list):
                logger.info(
                    f"LLM fallback news search returned {len(parsed)} articles for '{query}'"
                )
                return parsed[:limit]

            logger.warning("LLM news search response was not a list")
            return []

        except Exception as e:
            logger.warning(f"LLM fallback news search failed for '{query}': {e}")
            return []

    async def _social_monitor(
        self,
        entity: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Monitor social media for entity mentions.

        Uses ExaEnrichmentProvider with social domain filtering when available,
        falls back to Claude LLM generation.

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

        # Try Exa provider first with social media domain filtering
        exa = self._get_exa_provider()
        if exa:
            try:
                results = await exa.search_fast(
                    query=entity,
                    num_results=limit,
                    include_domains=["twitter.com", "linkedin.com", "reddit.com"],
                )

                mentions: list[dict[str, Any]] = []
                for item in results:
                    url = item.url

                    # Determine platform from URL domain
                    platform = "unknown"
                    author = "Unknown"
                    if url:
                        try:
                            parsed_url = urlparse(url)
                            domain = parsed_url.netloc.lower().replace("www.", "")
                            if "twitter.com" in domain or "x.com" in domain:
                                platform = "twitter"
                                # Extract username from path
                                path_parts = parsed_url.path.strip("/").split("/")
                                author = f"@{path_parts[0]}" if path_parts else "@unknown"
                            elif "linkedin.com" in domain:
                                platform = "linkedin"
                                path_parts = parsed_url.path.strip("/").split("/")
                                author = path_parts[1] if len(path_parts) > 1 else "Unknown"
                            elif "reddit.com" in domain:
                                platform = "reddit"
                                path_parts = parsed_url.path.strip("/").split("/")
                                # Reddit URLs: /r/subreddit/comments/id/...
                                if len(path_parts) >= 2 and path_parts[0] == "r":
                                    author = f"r/{path_parts[1]}"
                                else:
                                    author = "Unknown"
                        except Exception:
                            pass

                    mentions.append({
                        "content": (item.text or "")[:500],
                        "author": author,
                        "platform": platform,
                        "url": url,
                    })

                logger.info(f"Exa social monitor returned {len(mentions)} mentions for '{entity}'")
                return mentions[:limit]

            except Exception as e:
                logger.warning(f"Exa social monitoring failed for '{entity}': {e}")

        # LLM fallback: ask Claude for social media intelligence
        try:
            prompt = (
                f'Generate {limit} realistic social media mentions about: "{entity}"\n\n'
                "Based on your training knowledge, provide social media posts/discussions "
                "relevant to life sciences commercial intelligence.\n\n"
                "Return ONLY a JSON array with objects containing:\n"
                '- "content": the social media post or comment text\n'
                '- "author": username or display name\n'
                '- "platform": one of "twitter", "linkedin", "reddit"\n'
                '- "url": realistic social media URL\n\n'
                "Return valid JSON only, no explanation."
            )

            response_text = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are a social media intelligence analyst for life sciences. "
                    "Return only valid JSON arrays. No markdown, no explanation."
                ),
                temperature=0.3,
            )

            parsed = _extract_json_from_text(response_text)
            if isinstance(parsed, list):
                logger.info(
                    f"LLM fallback social monitor returned {len(parsed)} mentions for '{entity}'"
                )
                return parsed[:limit]

            logger.warning("LLM social monitor response was not a list")
            return []

        except Exception as e:
            logger.warning(f"LLM fallback social monitoring failed for '{entity}': {e}")
            return []

    async def _detect_signals(
        self,
        entities: list[str],
        signal_types: list[str] | None = None,
        mode: str = "standard",
    ) -> list[dict[str, Any]]:
        """Detect market signals for monitored entities.

        For each entity, gathers results from web search, news search,
        and social monitoring, then uses Claude to classify and score signals.

        Args:
            entities: List of entity names to monitor.
            signal_types: Optional list of signal types to filter by.
            mode: "standard" for 30-day lookback, "daily" for 1-day lookback.

        Returns:
            List of detected signals with relevance scores.
        """
        # Return empty list for empty entities
        if not entities:
            return []

        # Determine days_back based on mode
        days_back = 1 if mode == "daily" else 30

        logger.info(
            f"Detecting signals for entities={entities}, signal_types={signal_types}, mode={mode}",
        )

        all_signals: list[dict[str, Any]] = []

        for entity in entities:
            # Gather intelligence from all sources
            web_results = await self._web_search(query=entity, limit=5)
            news_results = await self._news_search(query=entity, limit=5, days_back=days_back)
            social_results = await self._social_monitor(entity=entity, limit=5)

            # Combine all gathered results for LLM classification
            gathered_data = {
                "entity": entity,
                "web_results": web_results,
                "news_results": news_results,
                "social_mentions": social_results,
            }

            # Use Claude to classify signals from gathered intelligence
            try:
                prompt = (
                    f'Analyze the following intelligence data about "{entity}" and '
                    "classify each item into market signals.\n\n"
                    f"Intelligence data:\n{json.dumps(gathered_data, indent=2, default=str)}\n\n"
                    "For each meaningful signal, classify it into one of these types:\n"
                    "- funding_round: New funding, investment, or financial events\n"
                    "- leadership_change: Executive appointments, departures, reorgs\n"
                    "- product_launch: New products, services, or feature releases\n"
                    "- regulatory: FDA approvals, compliance changes, regulatory filings\n"
                    "- partnership: Strategic alliances, collaborations, M&A\n"
                    "- hiring: Significant hiring activity, team expansion\n"
                    "- expansion: Geographic expansion, new markets, facility openings\n\n"
                    "Assign a relevance_score (0.0-1.0) based on how important this signal "
                    "is for a life sciences commercial team.\n\n"
                    "Return ONLY a JSON array of signal objects with these fields:\n"
                    '- "company_name": the entity name\n'
                    '- "signal_type": one of the types listed above\n'
                    '- "headline": concise signal headline\n'
                    '- "summary": 1-2 sentence summary of the signal\n'
                    '- "source_url": the source URL if available, or empty string\n'
                    '- "source_name": the source name or publication\n'
                    '- "relevance_score": float between 0.0 and 1.0\n'
                    '- "detected_at": current ISO 8601 datetime\n\n'
                    "If no meaningful signals are found, return an empty array [].\n"
                    "Return valid JSON only, no explanation."
                )

                response_text = await self.llm.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=(
                        "You are a market intelligence signal detection system for life sciences. "
                        "Analyze raw intelligence data and extract structured market signals. "
                        "Be precise with relevance scoring. Return only valid JSON arrays."
                    ),
                    temperature=0.2,
                )

                parsed = _extract_json_from_text(response_text)
                if isinstance(parsed, list):
                    # Validate and normalize each signal
                    for signal in parsed:
                        if not isinstance(signal, dict):
                            continue
                        # Ensure required fields have defaults
                        normalized: dict[str, Any] = {
                            "company_name": signal.get("company_name", entity),
                            "signal_type": signal.get("signal_type", "unknown"),
                            "headline": signal.get("headline", ""),
                            "summary": signal.get("summary", ""),
                            "source_url": signal.get("source_url", ""),
                            "source_name": signal.get("source_name", ""),
                            "relevance_score": float(signal.get("relevance_score", 0.5)),
                            "detected_at": signal.get(
                                "detected_at",
                                datetime.now(tz=UTC).isoformat(),
                            ),
                        }
                        all_signals.append(normalized)

                    logger.info(f"Signal detection found {len(parsed)} signals for '{entity}'")
                else:
                    logger.warning(f"Signal detection response for '{entity}' was not a list")

            except Exception as e:
                logger.warning(f"Signal detection failed for entity '{entity}': {e}")
                continue

        # Filter by signal types if provided
        if signal_types:
            all_signals = [s for s in all_signals if s["signal_type"] in signal_types]

        logger.info(f"Total signals detected: {len(all_signals)}")
        return all_signals

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

    async def _find_similar_pages(
        self,
        url: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find pages similar to a given URL using Exa find_similar.

        Useful for competitor discovery and finding related content.

        Args:
            url: The URL to find similar pages for.
            limit: Maximum number of results to return.

        Returns:
            List of similar pages with title, url, snippet.
        """
        if not url:
            return []

        logger.info(f"Finding similar pages to '{url}'")

        exa = self._get_exa_provider()
        if not exa:
            logger.warning("ExaEnrichmentProvider not available for find_similar")
            return []

        try:
            # Extract domain for exclusion
            domain = ""
            if "://" in url:
                domain = url.split("://")[1].split("/")[0].replace("www.", "")

            results = await exa.find_similar(
                url=url,
                num_results=limit,
                exclude_domains=[domain] if domain else None,
            )

            similar_pages: list[dict[str, Any]] = []
            for item in results:
                similar_pages.append({
                    "title": item.title,
                    "url": item.url,
                    "snippet": (item.text or "")[:500],
                    "similarity_score": item.score,
                })

            logger.info(f"Found {len(similar_pages)} similar pages to '{url}'")
            return similar_pages

        except Exception as e:
            logger.warning(f"find_similar failed for '{url}': {e}")
            return []
