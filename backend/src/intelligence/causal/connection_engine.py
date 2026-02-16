"""Cross-Domain Connection Engine for ARIA Phase 7 Jarvis Intelligence.

Discovers non-obvious connections between seemingly unrelated events
by analyzing entity overlap, querying Graphiti for paths, and using
LLM to assess novelty and generate insights.
"""

import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from src.intelligence.causal.engine import CausalChainEngine
from src.intelligence.causal.models import (
    ConnectionInsight,
    ConnectionScanRequest,
    ConnectionScanResponse,
    ConnectionType,
    EntityExtraction,
)

logger = logging.getLogger(__name__)


class CrossDomainConnectionEngine:
    """Engine for discovering cross-domain connections between events.

    Analyzes recent events from multiple sources (market signals, lead
    memories, episodic memories) to find non-obvious connections that
    humans might miss.

    Attributes:
        NOVELTY_THRESHOLD: Minimum novelty score (0.5) to surface insight
        MAX_EVENTS_TO_SCAN: Maximum events to analyze in one scan (50)
    """

    NOVELTY_THRESHOLD: float = 0.5
    MAX_EVENTS_TO_SCAN: int = 50

    def __init__(
        self,
        graphiti_client: Any | None,
        llm_client: Any,
        db_client: Any,
        causal_engine: CausalChainEngine | None = None,
    ) -> None:
        """Initialize the connection engine.

        Args:
            graphiti_client: Graphiti client for graph path queries (optional)
            llm_client: LLM client for entity extraction and novelty assessment
            db_client: Supabase client for fetching events and saving insights
            causal_engine: Optional causal engine for deeper analysis
        """
        self._graphiti = graphiti_client
        self._llm = llm_client
        self._db = db_client
        self._causal = causal_engine

    async def find_connections(
        self,
        user_id: str,
        events: list[str] | None = None,
        days_back: int = 7,
        min_novelty: float = 0.5,
    ) -> list[ConnectionInsight]:
        """Find cross-domain connections between events.

        Algorithm:
        1. If events not provided, fetch recent events from:
           - market_signals (last 7 days)
           - lead_memory_events (last 7 days)
           - episodic_memories (last 7 days)
        2. For each pair of events (or LLM-clustered groups):
           a. Extract entities from both events
           b. Check for entity overlap (direct connection)
           c. Query Graphiti for paths between entities (indirect connection)
           d. Use LLM to assess novelty, actionability, relevance
        3. Filter by novelty > threshold
        4. Generate natural language explanation
        5. Save to jarvis_insights table

        Args:
            user_id: User ID for context
            events: Optional list of events to analyze
            days_back: Days to look back for events (default 7)
            min_novelty: Minimum novelty score threshold (default 0.5)

        Returns:
            List of ConnectionInsight objects sorted by novelty
        """
        logger.info(
            "Starting cross-domain connection scan",
            extra={
                "user_id": user_id,
                "events_provided": events is not None,
                "days_back": days_back,
                "min_novelty": min_novelty,
            },
        )

        # Step 1: Get events to analyze
        if events is None:
            events = await self._fetch_recent_events(user_id, days_back)

        if len(events) < 2:
            logger.info("Not enough events to find connections")
            return []

        # Limit events to prevent timeout
        events = events[: self.MAX_EVENTS_TO_SCAN]

        # Step 2: Extract entities from all events
        event_entities: dict[str, list[EntityExtraction]] = {}
        for event in events:
            entities = await self._extract_entities(event)
            event_entities[event] = entities

        # Step 3: Find connections between events
        connections: list[ConnectionInsight] = []

        # Compare pairs of events
        for i, event_a in enumerate(events):
            for event_b in events[i + 1 :]:
                connection = await self._find_connection_between(
                    event_a=event_a,
                    event_b=event_b,
                    entities_a=event_entities[event_a],
                    entities_b=event_entities[event_b],
                    _user_id=user_id,
                )
                if connection and connection.novelty_score >= min_novelty:
                    connections.append(connection)

        # Sort by novelty score
        connections.sort(key=lambda c: c.novelty_score, reverse=True)

        logger.info(
            "Cross-domain connection scan complete",
            extra={
                "user_id": user_id,
                "events_scanned": len(events),
                "connections_found": len(connections),
            },
        )

        return connections

    async def scan_with_metadata(
        self,
        user_id: str,
        request: ConnectionScanRequest,
    ) -> ConnectionScanResponse:
        """Scan for connections with full metadata response."""
        start = time.monotonic()

        connections = await self.find_connections(
            user_id=user_id,
            events=request.events,
            days_back=request.days_back,
            min_novelty=request.min_novelty,
        )

        # Count events scanned
        events_scanned = (
            len(request.events)
            if request.events
            else await self._count_recent_events(user_id, request.days_back)
        )

        elapsed_ms = (time.monotonic() - start) * 1000

        return ConnectionScanResponse(
            connections=connections,
            events_scanned=events_scanned,
            processing_time_ms=elapsed_ms,
        )

    async def save_connection_insight(
        self,
        user_id: str,
        connection: ConnectionInsight,
    ) -> str | None:
        """Save connection insight to jarvis_insights table."""
        try:
            data = {
                "user_id": user_id,
                "insight_type": "cross_domain_connection",
                "trigger_event": (
                    connection.source_events[0] if connection.source_events else ""
                ),
                "content": connection.explanation,
                "classification": connection.connection_type.value,
                "impact_score": connection.novelty_score,
                "confidence": connection.actionability_score,
                "urgency": connection.relevance_score,
                "combined_score": (
                    connection.novelty_score
                    + connection.actionability_score
                    + connection.relevance_score
                )
                / 3,
                "causal_chain": [{"event": e} for e in connection.source_events],
                "affected_goals": [],
                "recommended_actions": (
                    [connection.recommended_action]
                    if connection.recommended_action
                    else []
                ),
                "status": "new",
            }

            result = self._db.table("jarvis_insights").insert(data).execute()

            if result.data:
                return result.data[0]["id"]
            return None

        except Exception:
            logger.exception("Failed to save connection insight")
            return None

    # --- Private helper methods ---

    async def _fetch_recent_events(self, user_id: str, days_back: int) -> list[str]:
        """Fetch recent events from all sources."""
        events = []
        cutoff = datetime.now(UTC) - timedelta(days=days_back)

        # Fetch from market_signals
        try:
            result = (
                self._db.table("market_signals")
                .select("summary, created_at")
                .eq("user_id", user_id)
                .gte("created_at", cutoff.isoformat())
                .limit(20)
                .execute()
            )
            for row in result.data or []:
                if row.get("summary"):
                    events.append(f"[MARKET] {row['summary']}")
        except Exception as e:
            logger.warning(f"Failed to fetch market signals: {e}")

        # Fetch from lead_memory_events
        try:
            result = (
                self._db.table("lead_memory_events")
                .select("description, created_at")
                .eq("user_id", user_id)
                .gte("created_at", cutoff.isoformat())
                .limit(20)
                .execute()
            )
            for row in result.data or []:
                if row.get("description"):
                    events.append(f"[LEAD] {row['description']}")
        except Exception as e:
            logger.warning(f"Failed to fetch lead events: {e}")

        # Fetch from episodic_memories
        try:
            result = (
                self._db.table("episodic_memories")
                .select("content, created_at")
                .eq("user_id", user_id)
                .gte("created_at", cutoff.isoformat())
                .limit(10)
                .execute()
            )
            for row in result.data or []:
                if row.get("content"):
                    events.append(f"[MEMORY] {row['content']}")
        except Exception as e:
            logger.warning(f"Failed to fetch episodic memories: {e}")

        return events

    async def _count_recent_events(self, user_id: str, days_back: int) -> int:
        """Count recent events from all sources."""
        return len(await self._fetch_recent_events(user_id, days_back))

    async def _extract_entities(self, text: str) -> list[EntityExtraction]:
        """Extract named entities from text using LLM."""
        prompt = f"""Extract named entities from this text. Return JSON array.

Text: {text}

Return format:
[{{"name": "EntityName", "entity_type": "company|person|product|event|concept", "relevance": 0.9, "context": "why relevant"}}]

Return only the JSON array, no markdown."""

        try:
            response = await self._llm.generate_response(prompt)
            # Parse JSON, handle markdown code blocks
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = (
                    cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                )
                cleaned = (
                    cleaned.rsplit("```", 1)[0] if "```" in cleaned else cleaned
                )
            entities_data = json.loads(cleaned)
            return [EntityExtraction(**e) for e in entities_data]
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return []

    async def _find_connection_between(
        self,
        event_a: str,
        event_b: str,
        entities_a: list[EntityExtraction],
        entities_b: list[EntityExtraction],
        _user_id: str = "",  # Reserved for future use
    ) -> ConnectionInsight | None:
        """Find connection between two events."""
        # Check for entity overlap
        entity_names_a = {e.name.lower() for e in entities_a}
        entity_names_b = {e.name.lower() for e in entities_b}
        overlap = entity_names_a & entity_names_b

        connection_type = (
            ConnectionType.ENTITY_OVERLAP
            if overlap
            else ConnectionType.LLM_INFERRED
        )

        # If Graphiti available, check for paths
        graphiti_path = None
        if self._graphiti and not overlap:
            for ea in entities_a:
                for eb in entities_b:
                    path = await self._query_graphiti_path(ea.name, eb.name)
                    if path:
                        graphiti_path = path
                        connection_type = ConnectionType.GRAPHITI_PATH
                        break
                if graphiti_path:
                    break

        # Use LLM to assess the connection
        scores = await self._assess_connection_novelty(
            event_a=event_a,
            event_b=event_b,
            entities_a=entities_a,
            entities_b=entities_b,
            overlap=overlap,
            graphiti_path=graphiti_path,
        )

        if not scores:
            return None

        # Generate explanation
        explanation = await self._generate_explanation(
            event_a=event_a,
            event_b=event_b,
            entities_a=entities_a,
            entities_b=entities_b,
            connection_type=connection_type,
            scores=scores,
        )

        all_entities = list({e.name for e in entities_a + entities_b})

        return ConnectionInsight(
            id=uuid4(),
            source_events=[event_a, event_b],
            source_domains=self._extract_domains([event_a, event_b]),
            connection_type=connection_type,
            entities=all_entities,
            novelty_score=scores["novelty"],
            actionability_score=scores["actionability"],
            relevance_score=scores["relevance"],
            explanation=explanation,
            recommended_action=scores.get("recommended_action"),
        )

    async def _query_graphiti_path(
        self, entity_a: str, entity_b: str
    ) -> list | None:
        """Query Graphiti for path between entities."""
        if not self._graphiti:
            return None
        try:
            # Use Graphiti's search for relationships
            result = await self._graphiti.search(
                query=f"connection between {entity_a} and {entity_b}",
                num_results=5,
            )
            if result:
                return result
        except Exception as e:
            logger.debug(f"Graphiti path query failed: {e}")
        return None

    async def _assess_connection_novelty(
        self,
        event_a: str,
        event_b: str,
        entities_a: list[EntityExtraction],
        entities_b: list[EntityExtraction],
        overlap: set,
        graphiti_path: list | None,
    ) -> dict | None:
        """Use LLM to assess connection novelty, actionability, relevance."""
        entity_names_a = [e.name for e in entities_a]
        entity_names_b = [e.name for e in entities_b]

        overlap_text = (
            f"Shared entities: {list(overlap)}" if overlap else "No direct entity overlap"
        )
        path_text = (
            f"Graph path found: {graphiti_path}" if graphiti_path else "No graph path"
        )

        prompt = f"""Assess this connection between two events. Return JSON.

Event A: {event_a}
Entities: {entity_names_a}

Event B: {event_b}
Entities: {entity_names_b}

{overlap_text}
{path_text}

Score these aspects (0.0-1.0):
- novelty: How surprising/non-obvious is this connection? (0.5+ = not obvious)
- actionability: Can the user do something with this? (0.5+ = actionable)
- relevance: Is this relevant to business goals? (0.5+ = relevant)

If all scores < 0.3, return {{"skip": true}}.

Return format:
{{"novelty": 0.8, "actionability": 0.7, "relevance": 0.6, "recommended_action": "specific action"}}

Return only JSON, no markdown."""

        try:
            response = await self._llm.generate_response(prompt)
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = (
                    cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
                )
                cleaned = (
                    cleaned.rsplit("```", 1)[0] if "```" in cleaned else cleaned
                )
            scores = json.loads(cleaned)
            if scores.get("skip"):
                return None
            return scores
        except Exception as e:
            logger.warning(f"Novelty assessment failed: {e}")
            return None

    async def _generate_explanation(
        self,
        event_a: str,
        event_b: str,
        entities_a: list[EntityExtraction],
        entities_b: list[EntityExtraction],
        connection_type: ConnectionType,
        scores: dict,
    ) -> str:
        """Generate natural language explanation of the connection."""
        prompt = f"""Explain this cross-domain connection in 2-3 sentences.

Event A: {event_a}
Event B: {event_b}

Connection type: {connection_type.value}
Shared entities: { {e.name for e in entities_a} & {e.name for e in entities_b} }
Novelty: {scores['novelty']:.0%}
Recommended action: {scores.get('recommended_action', 'None')}

Write a clear, professional explanation suitable for a business context."""

        try:
            return await self._llm.generate_response(prompt)
        except Exception:
            return f"Connection found between: {event_a[:50]}... and {event_b[:50]}..."

    def _extract_domains(self, events: list[str]) -> list[str]:
        """Extract domain tags from event prefixes."""
        domains = []
        for event in events:
            if event.startswith("[MARKET]"):
                domains.append("market_signal")
            elif event.startswith("[LEAD]"):
                domains.append("lead_memory")
            elif event.startswith("[MEMORY]"):
                domains.append("episodic")
            else:
                domains.append("unknown")
        return domains
