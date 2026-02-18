"""Signal-to-Orient graph analysis pipeline.

Enriches detected signals with knowledge graph context and
runs implication analysis to surface proactive intelligence.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Minimum combined_score for an implication to be routed to the user
ALERT_THRESHOLD = 0.6


def _score_to_severity(score: float) -> str:
    """Map combined_score to WebSocket severity level."""
    if score >= 0.8:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


async def analyze_signal_with_graph(
    user_id: str,
    signal: dict[str, Any],
    cold_retriever: Any,
    implication_engine: Any,
    ws_manager: Any,
    proactive_router: Any,
) -> list[Any]:
    """Analyze a signal with graph context and route implications.

    Pipeline:
    1. Extract entity from signal (company_name)
    2. Query graph neighborhood via ColdMemoryRetriever
    3. Run ImplicationEngine.analyze_event() for causal chain reasoning
    4. Filter by score threshold
    5. Push high-score implications via WebSocket + ProactiveRouter

    Args:
        user_id: The user to analyze for.
        signal: Signal dict with company_name, signal_type, headline, etc.
        cold_retriever: ColdMemoryRetriever instance.
        implication_engine: ImplicationEngine instance.
        ws_manager: WebSocket ConnectionManager for real-time alerts.
        proactive_router: ProactiveRouter for offline delivery.

    Returns:
        List of implications that met the alert threshold.
    """
    company = signal.get("company_name", "")
    headline = signal.get("headline", "")
    signal_type = signal.get("signal_type", "unknown")

    # Step 1: Get graph context for the signal's company
    graph_context_str = ""
    try:
        entity_ctx = await cold_retriever.retrieve_for_entity(
            user_id=user_id,
            entity_id=company,
            hops=3,
        )
        if entity_ctx:
            parts: list[str] = []
            for fact in getattr(entity_ctx, "direct_facts", [])[:5]:
                parts.append(f"Fact: {fact.content}")
            for rel in getattr(entity_ctx, "relationships", [])[:5]:
                parts.append(f"Relationship: {rel.content}")
            for interaction in getattr(entity_ctx, "recent_interactions", [])[:3]:
                parts.append(f"Recent: {interaction.content}")
            graph_context_str = "\n".join(parts)
    except Exception as e:
        logger.warning("Graph retrieval failed for signal company %s: %s", company, e)

    # Step 2: Run implication analysis
    event_description = f"{headline}"
    if graph_context_str:
        event_description += f"\n\nGraph context:\n{graph_context_str}"

    try:
        implications = await implication_engine.analyze_event(
            user_id=user_id,
            event=event_description,
            max_hops=4,
        )
    except Exception as e:
        logger.error("Implication analysis failed for signal: %s", e)
        return []

    # Step 3: Filter by threshold
    actionable = [impl for impl in implications if impl.combined_score >= ALERT_THRESHOLD]

    if not actionable:
        return []

    # Step 4: Route the top implication
    top = actionable[0]
    severity = _score_to_severity(top.combined_score)

    # WebSocket push
    try:
        await ws_manager.send_signal(
            user_id=user_id,
            signal_type=f"implication.{signal_type}",
            title=f"{headline}: {top.content[:100]}",
            severity=severity,
            data={
                "original_signal": signal,
                "implication": top.content,
                "causal_chain": top.causal_chain,
                "recommended_actions": top.recommended_actions,
                "combined_score": top.combined_score,
                "graph_context_available": bool(graph_context_str),
            },
        )
    except Exception as e:
        logger.warning("WebSocket signal push failed: %s", e)

    # ProactiveRouter for offline delivery
    try:
        from src.services.proactive_router import InsightCategory, InsightPriority

        priority = InsightPriority.HIGH if severity == "high" else InsightPriority.MEDIUM

        await proactive_router.route(
            user_id=user_id,
            priority=priority,
            category=InsightCategory.MARKET_SIGNAL,
            title=headline,
            message=top.content,
            metadata={
                "signal_type": signal_type,
                "company": company,
                "combined_score": top.combined_score,
                "recommended_actions": top.recommended_actions,
            },
        )
    except Exception as e:
        logger.warning("ProactiveRouter delivery failed: %s", e)

    return actionable
