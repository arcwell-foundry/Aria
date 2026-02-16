"""Causal Chain Traversal Engine for ARIA Phase 7 Jarvis Intelligence.

This engine traces how events propagate through connected entities using
a hybrid approach: Graphiti graph traversal for explicit relationships,
and LLM inference for implicit causality when edges don't exist.

Key features:
- Entity extraction from trigger events using LLM
- Graphiti search for existing causal relationships
- LLM inference for implicit causality based on domain knowledge
- BFS traversal with confidence decay (0.85 per hop)
- Cycle detection to prevent infinite loops
- Parallel chain support from single event
"""

import json
import logging
import time
from typing import Any

from src.core.llm import LLMClient
from src.intelligence.causal.models import (
    CausalChain,
    CausalHop,
    CausalTraversalRequest,
    CausalTraversalResponse,
    EntityExtraction,
    InferredRelationship,
)

logger = logging.getLogger(__name__)


class CausalChainEngine:
    """Engine for traversing causal chains from trigger events.

    Uses a hybrid approach combining:
    1. Graphiti graph search for explicit causal relationships
    2. LLM inference for implicit causality when edges don't exist

    Attributes:
        HOP_DECAY: Confidence multiplier per hop (0.85 = 15% loss per hop)
        MIN_CONFIDENCE: Minimum confidence to include a chain (0.3)
        MAX_HOPS: Maximum traversal depth (6)
    """

    HOP_DECAY: float = 0.85
    MIN_CONFIDENCE: float = 0.3
    MAX_HOPS: int = 6

    def __init__(
        self,
        graphiti_client: Any,
        llm_client: LLMClient,
        db_client: Any,
    ) -> None:
        """Initialize the causal chain engine.

        Args:
            graphiti_client: Graphiti client for knowledge graph queries
            llm_client: LLM client for entity extraction and inference
            db_client: Supabase client for context queries
        """
        self._graphiti = graphiti_client
        self._llm = llm_client
        self._db = db_client

    async def traverse(
        self,
        user_id: str,
        trigger_event: str,
        max_hops: int = 4,
        min_confidence: float = 0.3,
    ) -> list[CausalChain]:
        """Traverse causal chains from a trigger event.

        Main entry point for causal chain analysis. Extracts entities
        from the trigger event and traverses causal relationships.

        Args:
            user_id: User ID for context scoping
            trigger_event: Description of the event to analyze
            max_hops: Maximum number of hops (1-6, default 4)
            min_confidence: Minimum confidence threshold (0.1-1.0, default 0.3)

        Returns:
            List of causal chains that meet the confidence threshold
        """
        start_time = time.monotonic()

        # Clamp parameters
        max_hops = min(max_hops, self.MAX_HOPS)
        min_confidence = max(min_confidence, self.MIN_CONFIDENCE)

        logger.info(
            "Starting causal chain traversal",
            extra={
                "user_id": user_id,
                "trigger_length": len(trigger_event),
                "max_hops": max_hops,
                "min_confidence": min_confidence,
            },
        )

        # Step 1: Extract entities from the trigger event
        entities = await self._extract_entities(trigger_event)

        if not entities:
            logger.warning("No entities extracted from trigger event")
            return []

        logger.info(f"Extracted {len(entities)} entities from trigger event")

        # Step 2: Traverse from each entity
        all_chains: list[CausalChain] = []

        for entity in entities:
            chains = await self._traverse_from_entity(
                user_id=user_id,
                entity=entity,
                trigger_event=trigger_event,
                max_hops=max_hops,
                visited=set(),
                current_confidence=1.0,
                current_hops=[],
                min_confidence=min_confidence,
            )
            all_chains.extend(chains)

        # Step 3: Filter by minimum confidence and deduplicate
        filtered_chains = [
            chain for chain in all_chains if chain.final_confidence >= min_confidence and chain.hops
        ]

        # Deduplicate by final target entity
        seen_targets: set[str] = set()
        unique_chains: list[CausalChain] = []
        for chain in sorted(filtered_chains, key=lambda c: -c.final_confidence):
            if chain.hops:
                final_target = chain.hops[-1].target_entity
                if final_target not in seen_targets:
                    seen_targets.add(final_target)
                    unique_chains.append(chain)

        elapsed_ms = (time.monotonic() - start_time) * 1000
        logger.info(
            "Causal chain traversal complete",
            extra={
                "user_id": user_id,
                "total_chains": len(all_chains),
                "filtered_chains": len(filtered_chains),
                "unique_chains": len(unique_chains),
                "elapsed_ms": elapsed_ms,
            },
        )

        return unique_chains

    async def traverse_with_metadata(
        self,
        user_id: str,
        request: CausalTraversalRequest,
    ) -> CausalTraversalResponse:
        """Traverse causal chains and return full response with metadata.

        Args:
            user_id: User ID for context scoping
            request: Traversal request with parameters

        Returns:
            Full response with chains and processing metadata
        """
        start_time = time.monotonic()

        chains = await self.traverse(
            user_id=user_id,
            trigger_event=request.trigger_event,
            max_hops=request.max_hops,
            min_confidence=request.min_confidence,
        )

        # Extract entities again for count
        entities = await self._extract_entities(request.trigger_event)

        elapsed_ms = (time.monotonic() - start_time) * 1000

        return CausalTraversalResponse(
            chains=chains,
            processing_time_ms=elapsed_ms,
            entities_found=len(entities),
            trigger_event=request.trigger_event,
        )

    async def _extract_entities(self, trigger_event: str) -> list[EntityExtraction]:
        """Extract named entities from a trigger event using LLM.

        Uses Claude to identify companies, people, products, events,
        and other entities that may be causally connected.

        Args:
            trigger_event: The event description to analyze

        Returns:
            List of extracted entities with types and relevance scores
        """
        system_prompt = """You are an expert at extracting entities from business news and events.
Extract all relevant named entities that could be involved in causal relationships.

Entity types to identify:
- company: Business organizations (e.g., "Pfizer", "Moderna")
- person: Individual people (e.g., "CEO John Smith")
- product: Products or services (e.g., "COVID vaccine", "CRISPR therapy")
- technology: Technologies or methods (e.g., "mRNA platform", "gene editing")
- regulation: Laws, regulations, or guidelines (e.g., "FDA approval", "EMA guidelines")
- market: Market segments or regions (e.g., "European market", "oncology sector")
- event: Specific occurrences (e.g., "clinical trial results", "merger announcement")

Return ONLY a valid JSON array, no other text:
[
  {
    "name": "entity name",
    "entity_type": "company|person|product|technology|regulation|market|event",
    "relevance": 0.0-1.0,
    "context": "brief context about the entity's role"
  }
]"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": trigger_event}],
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=1000,
            )

            # Parse JSON response
            # Strip any markdown code blocks if present
            response = response.strip()
            if response.startswith("```"):
                # Remove markdown code block markers
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

            entities_data = json.loads(response)

            entities = [
                EntityExtraction(
                    name=str(e.get("name", "")),
                    entity_type=str(e.get("entity_type", "company")),
                    relevance=float(e.get("relevance", 0.5)),
                    context=e.get("context"),
                )
                for e in entities_data
                if e.get("name")
            ]

            return entities

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse entity extraction response: {e}")
            return []
        except Exception as e:
            logger.exception(f"Entity extraction failed: {e}")
            return []

    async def _get_graphiti_relationships(
        self,
        _user_id: str,
        entity_name: str,
    ) -> list[dict[str, Any]]:
        """Query Graphiti for existing causal relationships from an entity.

        Searches the knowledge graph for edges that represent causal
        relationships originating from the given entity.

        Args:
            user_id: User ID for scoping
            entity_name: Name of the source entity

        Returns:
            List of relationship dictionaries with target, type, confidence
        """
        try:
            # Check if Graphiti is initialized
            from src.db.graphiti import GraphitiClient

            if not GraphitiClient.is_initialized():
                logger.debug("Graphiti not initialized, skipping relationship search")
                return []

            graphiti = await GraphitiClient.get_instance()

            # Search for causal relationships involving this entity
            # The search query looks for causal patterns
            query = f"causes effects implications {entity_name}"
            results = await graphiti.search(query)

            relationships: list[dict[str, Any]] = []

            for result in results:
                # Extract relationship data from Graphiti result
                fact = getattr(result, "fact", None) or str(result)
                score = getattr(result, "score", 0.5)

                # Parse the fact to extract relationship info
                # Graphiti stores facts as natural language
                if "causes" in fact.lower() or "leads to" in fact.lower():
                    relationships.append(
                        {
                            "target_entity": self._extract_target_from_fact(fact, entity_name),
                            "relationship_type": "causes",
                            "confidence": min(score, 1.0),
                            "explanation": fact,
                            "source": "graphiti",
                        }
                    )
                elif "enables" in fact.lower() or "supports" in fact.lower():
                    relationships.append(
                        {
                            "target_entity": self._extract_target_from_fact(fact, entity_name),
                            "relationship_type": "enables",
                            "confidence": min(score, 1.0),
                            "explanation": fact,
                            "source": "graphiti",
                        }
                    )
                elif "threatens" in fact.lower() or "risks" in fact.lower():
                    relationships.append(
                        {
                            "target_entity": self._extract_target_from_fact(fact, entity_name),
                            "relationship_type": "threatens",
                            "confidence": min(score, 1.0),
                            "explanation": fact,
                            "source": "graphiti",
                        }
                    )

            return relationships

        except Exception as e:
            logger.warning(f"Graphiti relationship search failed: {e}")
            return []

    def _extract_target_from_fact(self, fact: str, source_entity: str) -> str:
        """Extract the target entity from a fact string.

        Simple heuristic extraction - looks for entities after causal keywords.
        """
        fact_lower = fact.lower()
        source_lower = source_entity.lower()

        # Remove the source entity from the fact
        fact_cleaned = fact_lower.replace(source_lower, "").strip()

        # Look for causal keywords and extract what follows
        causal_keywords = ["causes", "leads to", "affects", "impacts", "enables", "threatens"]
        for keyword in causal_keywords:
            if keyword in fact_cleaned:
                parts = fact_cleaned.split(keyword, 1)
                if len(parts) > 1:
                    target = parts[1].strip()
                    # Take first 50 chars as target
                    return target[:50].strip()

        # Fallback: return the fact itself truncated
        return fact[:50]

    async def _infer_causal_relationships(
        self,
        user_id: str,
        entity: EntityExtraction,
        trigger_event: str,
    ) -> list[InferredRelationship]:
        """Use LLM to infer causal relationships when Graphiti has no edges.

        Uses domain knowledge about life sciences and the user's context
        to infer likely causal relationships.

        Args:
            user_id: User ID for context retrieval
            entity: The entity to find downstream effects for
            trigger_event: Original trigger for context

        Returns:
            List of inferred relationships with confidence and explanations
        """
        # Gather context from user's data
        context = await self._gather_inference_context(user_id, entity.name)

        system_prompt = f"""You are an expert analyst in the life sciences industry.
Given an entity and its context, infer the most likely downstream causal effects.

Entity: {entity.name}
Entity Type: {entity.entity_type}
Trigger Event: {trigger_event}

User Context:
{context}

Consider these causal patterns in life sciences:
- Supply chain: manufacturer issues → production delays → drug shortages
- Regulatory: FDA decision → market access changes → revenue impact
- Clinical: trial results → investor confidence → stock price
- Competitive: new entrant → pricing pressure → market share shifts
- Personnel: executive departure → strategy shift → deal timeline changes

Relationship types to use:
- causes: Direct causal relationship
- enables: Makes something possible
- threatens: Creates risk or negative impact
- accelerates: Speeds up a process or outcome

Return ONLY a valid JSON array (max 5 items), no other text:
[
  {{
    "target_entity": "entity name",
    "relationship_type": "causes|enables|threatens|accelerates",
    "confidence": 0.0-1.0,
    "explanation": "why this causal link exists"
  }}
]"""

        try:
            response = await self._llm.generate_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"What are the downstream effects of {entity.name}?",
                    }
                ],
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=1000,
            )

            # Parse JSON response
            response = response.strip()
            if response.startswith("```"):
                lines = response.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response = "\n".join(lines).strip()

            relationships_data = json.loads(response)

            relationships = [
                InferredRelationship(
                    target_entity=str(r.get("target_entity", "")),
                    relationship_type=str(r.get("relationship_type", "causes")),
                    confidence=float(r.get("confidence", 0.5)),
                    explanation=str(r.get("explanation", "")),
                )
                for r in relationships_data
                if r.get("target_entity")
            ]

            return relationships[:5]  # Limit to 5 inferred relationships

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse inference response: {e}")
            return []
        except Exception as e:
            logger.exception(f"Relationship inference failed: {e}")
            return []

    async def _gather_inference_context(
        self,
        user_id: str,
        entity_name: str,
    ) -> str:
        """Gather relevant context for LLM inference.

        Pulls data from semantic memory, leads, and market signals
        to provide context for causal inference.

        Args:
            user_id: User ID
            entity_name: Entity to gather context for

        Returns:
            Formatted context string for LLM prompt
        """
        context_parts: list[str] = []

        try:
            # Get relevant semantic facts
            facts_result = (
                self._db.table("memory_semantic")
                .select("fact, confidence")
                .eq("user_id", user_id)
                .ilike("fact", f"%{entity_name}%")
                .order("confidence", desc=True)
                .limit(5)
                .execute()
            )
            if facts_result.data:
                facts = [f["fact"] for f in facts_result.data]
                context_parts.append(f"Relevant facts: {'; '.join(facts)}")

        except Exception:
            pass  # Non-critical, continue without facts

        try:
            # Get relevant leads
            leads_result = (
                self._db.table("leads")
                .select("company_name, lifecycle_stage")
                .eq("user_id", user_id)
                .ilike("company_name", f"%{entity_name}%")
                .limit(3)
                .execute()
            )
            if leads_result.data:
                leads = [
                    f"{lead['company_name']} ({lead['lifecycle_stage']})"
                    for lead in leads_result.data
                ]
                context_parts.append(f"Related leads: {', '.join(leads)}")

        except Exception:
            pass

        try:
            # Get recent market signals
            signals_result = (
                self._db.table("market_signals")
                .select("signal_type, summary")
                .eq("user_id", user_id)
                .ilike("summary", f"%{entity_name}%")
                .order("created_at", desc=True)
                .limit(3)
                .execute()
            )
            if signals_result.data:
                signals = [f"{s['signal_type']}: {s['summary'][:100]}" for s in signals_result.data]
                context_parts.append(f"Recent signals: {'; '.join(signals)}")

        except Exception:
            pass

        if context_parts:
            return "\n".join(context_parts)
        return "No specific user context available for this entity."

    async def _traverse_from_entity(
        self,
        user_id: str,
        entity: EntityExtraction,
        trigger_event: str,
        max_hops: int,
        visited: set[str],
        current_confidence: float,
        current_hops: list[CausalHop],
        min_confidence: float,
    ) -> list[CausalChain]:
        """Recursively traverse causal relationships from an entity.

        Uses BFS with confidence decay and cycle detection.

        Args:
            user_id: User ID for context
            entity: Current entity being traversed
            trigger_event: Original trigger event
            max_hops: Maximum remaining hops
            visited: Set of already visited entities (cycle detection)
            current_confidence: Confidence at this point in traversal
            current_hops: Hops accumulated so far
            min_confidence: Minimum confidence threshold

        Returns:
            List of causal chains from this traversal
        """
        # Base cases
        if max_hops <= 0:
            return []
        if entity.name in visited:
            return []
        if current_confidence < min_confidence:
            return []

        # Add to visited set
        visited = visited | {entity.name}

        # Get relationships from Graphiti
        graphiti_rels = await self._get_graphiti_relationships(user_id, entity.name)

        # If no Graphiti relationships, use LLM inference
        if not graphiti_rels:
            inferred_rels = await self._infer_causal_relationships(user_id, entity, trigger_event)
            graphiti_rels = [
                {
                    "target_entity": r.target_entity,
                    "relationship_type": r.relationship_type,
                    "confidence": r.confidence,
                    "explanation": r.explanation,
                    "source": "llm_inference",
                }
                for r in inferred_rels
            ]

        chains: list[CausalChain] = []

        for rel in graphiti_rels:
            target_name = rel["target_entity"]

            # Skip if already visited (cycle detection)
            if target_name in visited:
                continue

            # Calculate decayed confidence
            rel_confidence = rel.get("confidence", 0.5)
            new_confidence = current_confidence * self.HOP_DECAY * rel_confidence

            # Skip if below threshold
            if new_confidence < min_confidence:
                continue

            # Create hop
            hop = CausalHop(
                source_entity=entity.name,
                target_entity=target_name,
                relationship=rel["relationship_type"],
                confidence=rel_confidence,
                explanation=rel["explanation"],
            )

            new_hops = current_hops + [hop]

            # If we have meaningful hops, create a chain
            if new_hops:
                chain = CausalChain(
                    id=None,
                    trigger_event=trigger_event,
                    hops=new_hops,
                    final_confidence=new_confidence,
                    time_to_impact=None,
                    source_context=None,
                    source_id=None,
                    created_at=None,
                )
                chains.append(chain)

            # Recurse if we have more hops allowed
            if max_hops > 1:
                target_entity = EntityExtraction(
                    name=target_name,
                    entity_type="unknown",
                    relevance=1.0,
                    context=None,
                )

                sub_chains = await self._traverse_from_entity(
                    user_id=user_id,
                    entity=target_entity,
                    trigger_event=trigger_event,
                    max_hops=max_hops - 1,
                    visited=visited,
                    current_confidence=new_confidence,
                    current_hops=new_hops,
                    min_confidence=min_confidence,
                )
                chains.extend(sub_chains)

        return chains
