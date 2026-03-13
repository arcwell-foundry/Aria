"""Proactive Scout signal scanning job (Task d).

Runs every 15 minutes. For each active user, instantiates the ScoutAgent
to detect new market signals for tracked competitors and active leads.
New signals are stored in ``market_signals`` and routed through
the ProactiveRouter based on relevance score.

High-relevance signals (>= 0.8) are additionally evaluated by the
ProactiveGoalProposer to generate actionable goal proposals delivered
via WebSocket (or queued for next login).

FIXES APPLIED:
- FIX 1A: Update monitored_entities.last_checked_at after each user scan
- FIX 1C: Second pass for ICP-relevant industry term scanning
"""

import logging
from datetime import UTC, datetime
from typing import Any

from src.core.business_hours import get_active_user_ids, get_user_timezone, is_business_hours
from src.core.text_cleaning import clean_signal_summary
from src.db.supabase import SupabaseClient
from src.services.proactive_router import InsightCategory, InsightPriority, ProactiveRouter
from src.utils.company_aliases import normalize_company_name

logger = logging.getLogger(__name__)

# Minimum relevance score to trigger a goal proposal (not just a notification)
_GOAL_PROPOSAL_THRESHOLD = 0.8

# FIX 1C: Default ICP-relevant industry search terms for life sciences
DEFAULT_INDUSTRY_SEARCH_TERMS = [
    "CDMO facility expansion",
    "biologics manufacturing funding",
    "bioprocessing equipment procurement",
    "GMP capacity addition",
    "cell therapy manufacturing scale-up",
    "bioreactor capacity expansion",
    "downstream processing investment",
    "upstream bioprocessing innovation",
    "pharmaceutical cold chain expansion",
    "biomanufacturing workforce hiring",
]


async def run_scout_signal_scan_job() -> dict[str, Any]:
    """Run Scout agent signal scan for all active users.

    For each user (within business hours):
    1. Read tracked_competitors from user_preferences + company names from leads
    2. Instantiate ScoutAgent and execute entity search
    3. Deduplicate against existing market_signals
    4. Store new signals and route via ProactiveRouter
    5. FIX 1A: Update monitored_entities.last_checked_at
    6. FIX 1C: Run industry term scan for ICP-relevant signals

    Returns:
        Summary dict with scan statistics.
    """
    stats: dict[str, Any] = {
        "users_checked": 0,
        "users_skipped_off_hours": 0,
        "signals_detected": 0,
        "signals_routed_high": 0,
        "signals_routed_medium": 0,
        "signals_routed_low": 0,
        "goal_proposals_generated": 0,
        "industry_signals_detected": 0,
        "monitored_entities_updated": 0,
        "errors": 0,
    }

    db = SupabaseClient.get_client()
    router = ProactiveRouter()
    all_user_ids = get_active_user_ids()
    processed_user_ids: list[str] = []  # Track users we actually processed
    scanned_entities_by_user: dict[str, list[str]] = {}  # Track entity names per user for last_checked_at

    logger.info("Scout signal scan: processing %d users", len(all_user_ids))

    for user_id in all_user_ids:
        try:
            tz = get_user_timezone(user_id)
            if not is_business_hours(tz):
                stats["users_skipped_off_hours"] += 1
                continue

            stats["users_checked"] += 1
            processed_user_ids.append(user_id)

            # Look up company_id for dynamic alias resolution
            company_id: str | None = None
            try:
                profile = db.table("user_profiles").select("company_id").eq("id", user_id).limit(1).execute()
                if profile.data:
                    company_id = profile.data[0].get("company_id")
            except Exception:
                pass

            # Gather entities to scan
            entities = await _get_scan_entities(db, user_id)
            if not entities:
                continue

            scanned_entities_by_user[user_id] = entities

            # Run Scout agent
            try:
                from src.agents.scout import ScoutAgent
                from src.core.llm import LLMClient

                scout = ScoutAgent(llm_client=LLMClient(), user_id=user_id)
                result = await scout.execute(
                    {"entities": entities, "signal_types": ["news", "funding", "regulatory"]}
                )

                if not result.success or not result.data:
                    continue

                signals = result.data if isinstance(result.data, list) else []
            except Exception:
                logger.warning(
                    "Scout agent execution failed for user %s",
                    user_id,
                    exc_info=True,
                )
                stats["errors"] += 1
                continue

            # Deduplicate and store
            for signal in signals:
                headline = signal.get("headline", "")
                if not headline:
                    continue

                # Extract actual article company (may differ from search entity)
                raw_company_name = signal.get("company_name", "Unknown")
                search_trigger = raw_company_name
                raw_company_name = _extract_article_company(
                    headline=headline,
                    summary=signal.get("summary", ""),
                    search_company=raw_company_name,
                )
                canonical_company_name = normalize_company_name(
                    raw_company_name, company_id=company_id, supabase_client=db,
                )

                if await _signal_exists(db, user_id, headline, canonical_company_name):
                    logger.debug("Duplicate signal skipped: %s", headline[:60])
                    continue

                # Store in market_signals (the canonical table read by briefing,
                # signals API, causal reasoning, and all downstream consumers)
                relevance = float(signal.get("relevance_score", 0.5))
                signal_id: str | None = None
                try:
                    # Clean the summary to remove web scraping markup
                    cleaned_summary = clean_signal_summary(
                        raw_text=signal.get("summary", ""),
                        headline=headline,
                        max_length=500,
                    )
                    insert_result = db.table("market_signals").insert(
                        {
                            "user_id": user_id,
                            "company_name": canonical_company_name,
                            "signal_type": signal.get("signal_type", "news"),
                            "headline": headline,
                            "summary": cleaned_summary,
                            "source_name": signal.get("source", "scout_agent"),
                            "source_url": signal.get("source_url"),
                            "relevance_score": relevance,
                            "search_trigger_company": search_trigger,
                            "metadata": signal.get("metadata", {}),
                        }
                    ).execute()
                    if insert_result.data:
                        signal_id = insert_result.data[0].get("id")
                except Exception:
                    logger.debug("Failed to store signal: %s", headline[:80])
                    continue

                stats["signals_detected"] += 1

                # Check watch topics for this signal
                try:
                    from src.intelligence.watch_topics_service import WatchTopicsService

                    wts = WatchTopicsService(db)
                    watch_matches = await wts.match_signal(
                        user_id=user_id,
                        signal={
                            "id": signal_id,
                            "headline": headline,
                            "company_name": canonical_company_name,
                            "signal_type": signal.get("signal_type", "news"),
                        },
                    )
                    if watch_matches:
                        logger.debug(
                            "Signal matched %d watch topics: %s",
                            len(watch_matches),
                            headline[:60],
                        )
                except Exception:
                    logger.debug("Watch topic matching failed", exc_info=True)

                # Memory compounding: write high-relevance signals to institutional memory
                if relevance >= 0.85:
                    try:
                        db.table("memory_semantic").insert(
                            {
                                "user_id": user_id,
                                "fact": f"[Signal] {canonical_company_name}: {headline[:200]}",
                                "confidence": relevance,
                                "source": "market_signal",
                                "metadata": {
                                    "signal_type": signal.get("signal_type", "news"),
                                    "entities": [canonical_company_name],
                                },
                            }
                        ).execute()
                    except Exception:
                        logger.debug("Failed to write signal memory: %s", headline[:60])

                # Route through Intelligence Pulse Engine
                try:
                    from src.services.intelligence_pulse import get_pulse_engine

                    pulse_engine = get_pulse_engine()
                    await pulse_engine.process_signal(
                        user_id=user_id,
                        signal={
                            "source": "scout_agent",
                            "title": headline,
                            "content": signal.get("summary", ""),
                            "signal_category": signal.get("signal_type", "news"),
                            "pulse_type": "event",
                            "entities": [signal.get("company_name", "Unknown")],
                            "raw_data": signal,
                        },
                    )
                except Exception:
                    logger.debug("Pulse engine routing failed for signal: %s", headline[:60])

                # Route through Jarvis Intelligence engines (non-blocking)
                try:
                    from src.intelligence.orchestrator import create_orchestrator

                    jarvis = create_orchestrator()
                    event_text = (
                        f"{canonical_company_name}: "
                        f"{headline} - {signal.get('summary', '')}"
                    )
                    await jarvis.process_event(
                        user_id=str(user_id),
                        event=event_text,
                        source_context="scout_signal_scan",
                        source_id=signal_id,
                    )
                except Exception:
                    logger.debug("Jarvis processing failed for signal: %s", headline[:60])

                # Route based on relevance
                if relevance >= _GOAL_PROPOSAL_THRESHOLD:
                    priority = InsightPriority.HIGH
                    stats["signals_routed_high"] += 1
                elif relevance >= 0.6:
                    priority = InsightPriority.MEDIUM
                    stats["signals_routed_medium"] += 1
                else:
                    priority = InsightPriority.LOW
                    stats["signals_routed_low"] += 1

                # For HIGH signals: generate a goal proposal with GoalPlanCard
                if relevance >= _GOAL_PROPOSAL_THRESHOLD and signal_id:
                    proposed = await _maybe_propose_goal(
                        user_id=user_id,
                        signal_id=signal_id,
                        signal=signal,
                        relevance=relevance,
                    )
                    if proposed:
                        stats["goal_proposals_generated"] += 1
                        # Goal proposer already handles WebSocket/login delivery,
                        # so skip the plain ProactiveRouter notification
                        continue

                # Fallback: route as a plain notification (no goal card)
                await router.route(
                    user_id=user_id,
                    priority=priority,
                    category=InsightCategory.MARKET_SIGNAL,
                    title=f"Market Signal: {headline[:60]}",
                    message=signal.get("summary", headline),
                    link="/intelligence",
                    metadata={
                        "signal_type": signal.get("signal_type"),
                        "relevance": relevance,
                    },
                )

        except Exception:
            logger.warning(
                "Scout signal scan failed for user %s",
                user_id,
                exc_info=True,
            )
            stats["errors"] += 1

    # FIX 1A: Update monitored_entities.last_checked_at for scanned entities
    for user_id, entity_names in scanned_entities_by_user.items():
        try:
            db.table("monitored_entities").update(
                {"last_checked_at": datetime.now(UTC).isoformat()}
            ).eq("user_id", user_id).in_("entity_name", entity_names).execute()
            stats["monitored_entities_updated"] += 1
        except Exception:
            logger.debug("Failed to update last_checked_at for user %s", user_id)

    # FIX 1C: Scan for ICP-relevant industry terms (second pass)
    try:
        industry_stats = await _scan_industry_terms(db, processed_user_ids)
        stats["industry_signals_detected"] = industry_stats.get("signals_detected", 0)
    except Exception:
        logger.debug("Industry term scan failed", exc_info=True)

    # Post-scan deduplication: cluster near-duplicate signals
    try:
        from src.intelligence.signal_deduplication import SignalDeduplicator

        dedup = SignalDeduplicator(db)
        clusters = await dedup.deduplicate_signals(window_hours=48)
        if clusters > 0:
            logger.info("Signal deduplication: %d clusters created", clusters)
    except Exception:
        logger.debug("Signal deduplication failed", exc_info=True)

    logger.info("Scout signal scan complete", extra=stats)
    return stats


async def _get_scan_entities(db: Any, user_id: str) -> list[str]:
    """Gather entity names to scan from all available sources."""
    entities: set[str] = set()

    # 1. Tracked competitors from user_preferences
    try:
        prefs_result = (
            db.table("user_preferences")
            .select("tracked_competitors")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        prefs = prefs_result.data[0] if prefs_result and prefs_result.data else None
        if prefs:
            competitors = prefs.get("tracked_competitors") or []
            if isinstance(competitors, list):
                entities.update(c for c in competitors if isinstance(c, str))
    except Exception:
        pass

    # 2. Company names from active leads (lead_memories)
    try:
        leads_result = (
            db.table("lead_memories")
            .select("company_name")
            .eq("user_id", user_id)
            .eq("status", "active")
            .limit(20)
            .execute()
        )
        for lead in leads_result.data or []:
            name = lead.get("company_name")
            if name:
                entities.add(name)
    except Exception:
        pass

    # 3. Entity names from monitored_entities table
    try:
        monitored_result = (
            db.table("monitored_entities")
            .select("entity_name")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .limit(20)
            .execute()
        )
        for entity in monitored_result.data or []:
            name = entity.get("entity_name")
            if name:
                entities.add(name)
    except Exception:
        pass

    # 4. Company names from discovered_leads (populated by Hunter agent)
    try:
        discovered_result = (
            db.table("discovered_leads")
            .select("company_name")
            .eq("user_id", user_id)
            .limit(20)
            .execute()
        )
        for lead in discovered_result.data or []:
            name = lead.get("company_name")
            if name:
                entities.add(name)
    except Exception:
        pass

    # 5. Company names from existing market_signals (bootstrap from past analysis)
    if not entities:
        try:
            signals_result = (
                db.table("market_signals")
                .select("company_name")
                .eq("user_id", user_id)
                .neq("company_name", "Market")
                .limit(10)
                .execute()
            )
            for sig in signals_result.data or []:
                name = sig.get("company_name")
                if name:
                    entities.add(name)
        except Exception:
            pass

    return list(entities)


async def _scan_industry_terms(db: Any, user_ids: list[str]) -> dict[str, Any]:
    """FIX 1C: Scan for ICP-relevant industry term signals.

    Searches Exa for industry-wide signals that don't map to specific competitors
    but are relevant to the user's ICP and market. Uses search_vocabulary from
    memory_semantic, watch_topics keywords, and default life sciences terms.

    Args:
        db: Supabase client
        user_ids: List of user IDs to scan for

    Returns:
        Dict with signals_detected count
    """
    stats = {"signals_detected": 0}

    for user_id in user_ids[:5]:  # Limit to 5 users per scan to avoid API limits
        try:
            # Gather user-specific search terms
            search_terms: set[str] = set(DEFAULT_INDUSTRY_SEARCH_TERMS)

            # 1. Get search_vocabulary from memory_semantic
            try:
                vocab_result = (
                    db.table("memory_semantic")
                    .select("fact")
                    .eq("user_id", user_id)
                    .eq("entity_type", "search_vocabulary")
                    .limit(20)
                    .execute()
                )
                for row in vocab_result.data or []:
                    fact = row.get("fact", "")
                    if fact and len(fact) > 3:
                        search_terms.add(fact[:100])
            except Exception:
                pass

            # 2. Get watch_topics keywords
            try:
                topics_result = (
                    db.table("watch_topics")
                    .select("keywords")
                    .eq("user_id", user_id)
                    .eq("is_active", True)
                    .limit(10)
                    .execute()
                )
                for row in topics_result.data or []:
                    keywords = row.get("keywords", [])
                    if isinstance(keywords, list):
                        for kw in keywords[:5]:
                            if kw and len(kw) > 3:
                                search_terms.add(kw[:100])
            except Exception:
                pass

            # 3. Run Scout agent for industry terms
            try:
                from src.agents.scout import ScoutAgent
                from src.core.llm import LLMClient

                scout = ScoutAgent(llm_client=LLMClient(), user_id=user_id)
                result = await scout.execute(
                    {
                        "entities": list(search_terms)[:15],  # Limit to 15 terms
                        "signal_types": ["news", "funding", "regulatory", "partnership"],
                        "industry_scan": True,  # Flag to indicate broad industry scan
                    }
                )

                if result.success and result.data:
                    signals = result.data if isinstance(result.data, list) else []

                    for signal in signals:
                        headline = signal.get("headline", "")
                        if not headline:
                            continue

                        # Extract actual article company
                        raw_industry_company = signal.get("company_name", "Industry")
                        if raw_industry_company == "Unknown":
                            raw_industry_company = "Industry"
                        industry_search_trigger = raw_industry_company
                        company_name = _extract_article_company(
                            headline=headline,
                            summary=signal.get("summary", ""),
                            search_company=raw_industry_company,
                        )

                        if await _signal_exists(db, user_id, headline, company_name):
                            continue

                        # Store as industry signal
                        try:
                            cleaned_summary = clean_signal_summary(
                                raw_text=signal.get("summary", ""),
                                headline=headline,
                                max_length=500,
                            )
                            db.table("market_signals").insert(
                                {
                                    "user_id": user_id,
                                    "company_name": company_name,
                                    "signal_type": signal.get("signal_type", "market_trend"),
                                    "headline": headline,
                                    "summary": cleaned_summary,
                                    "source_name": signal.get("source", "industry_scan"),
                                    "source_url": signal.get("source_url"),
                                    "relevance_score": signal.get("relevance_score", 0.5),
                                    "search_trigger_company": industry_search_trigger,
                                    "metadata": {
                                        **signal.get("metadata", {}),
                                        "scan_type": "industry_term",
                                    },
                                }
                            ).execute()
                            stats["signals_detected"] += 1
                        except Exception:
                            logger.debug("Failed to store industry signal: %s", headline[:80])

            except Exception:
                logger.debug("Industry term Scout scan failed for user %s", user_id)

        except Exception:
            logger.debug("Industry term scan failed for user %s", user_id, exc_info=True)

    if stats["signals_detected"] > 0:
        logger.info("Industry term scan detected %d signals", stats["signals_detected"])

    return stats


def _extract_article_company(headline: str, summary: str, search_company: str) -> str:
    """Extract the actual company the article is about.

    If the headline mentions a specific company other than the search trigger,
    prefer that. Otherwise use the search trigger company.

    Args:
        headline: Article headline text.
        summary: Article summary text.
        search_company: The company name that triggered the Exa search.

    Returns:
        The extracted company name, or the search_company as fallback.
    """
    import re

    if not headline:
        return search_company

    # If the search company IS mentioned prominently in the headline, keep it
    if search_company.lower() in headline.lower()[:120]:
        return search_company

    # Article headline doesn't mention the search company —
    # try to extract the actual subject from the headline
    # Look for a capitalized company name before a verb phrase
    match = re.match(
        r'^([A-Z][A-Za-z0-9\s&\-\.]+?)(?:\s+(?:to|and|is|has|will|announces|launches|reports|acquires|partners|signs|receives|expands|closes|completes|enters|unveils|secures))',
        headline,
    )
    if match:
        extracted = match.group(1).strip()
        if len(extracted) > 2 and extracted != search_company:
            return extracted

    return search_company


async def _signal_exists(
    db: Any, user_id: str, headline: str, company_name: str | None = None
) -> bool:
    """Check if a signal with the same headline (and optionally company) already exists.

    Deduplication is based on headline + company_name combination to prevent
    duplicate signals for the same event from the same company.
    """
    try:
        query = (
            db.table("market_signals")
            .select("id")
            .eq("user_id", user_id)
            .eq("headline", headline)
        )
        if company_name:
            query = query.eq("company_name", company_name)
        result = query.limit(1).execute()
        return bool(result.data)
    except Exception:
        return False


async def _maybe_propose_goal(
    user_id: str,
    signal_id: str,
    signal: dict[str, Any],
    relevance: float,
) -> bool:
    """Evaluate a high-relevance signal and generate a goal proposal.

    Calls ProactiveGoalProposer.evaluate_signal() which handles:
    - LLM-based goal proposal generation
    - Deduplication (won't re-propose for same signal)
    - Storage in proactive_proposals table
    - WebSocket delivery (or login queue if offline)
    - Rich GoalPlanCard rendering

    Args:
        user_id: Target user UUID.
        signal_id: UUID of the stored market_signals row.
        signal: Raw signal dict from Scout agent.
        relevance: Relevance score (0-1).

    Returns:
        True if a proposal was generated and routed.
    """
    try:
        from src.services.proactive_goal_proposer import ProactiveGoalProposer

        proposer = ProactiveGoalProposer()
        proposed = await proposer.evaluate_signal(
            user_id=user_id,
            signal_id=signal_id,
            signal_type=signal.get("signal_type", "news"),
            headline=signal.get("headline", ""),
            summary=signal.get("summary"),
            relevance_score=relevance,
            company_name=signal.get("company_name"),
        )
        if proposed:
            logger.info(
                "Goal proposal generated from signal",
                extra={
                    "user_id": user_id,
                    "signal_id": signal_id,
                    "headline": signal.get("headline", "")[:80],
                },
            )
        return proposed
    except Exception:
        logger.debug(
            "Goal proposal generation failed for signal %s",
            signal_id,
            exc_info=True,
        )
        return False
