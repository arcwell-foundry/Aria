"""
One-time backfill: Process top existing signals through Jarvis to seed insights.
Run with: PYTHONPATH=. python3 -m src.intelligence.backfill_insights [user_id]

If no user_id is given, auto-discovers the first user with market signals.
"""

import asyncio
import logging
import sys
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def backfill(user_id: str) -> None:
    from src.db.supabase import SupabaseClient
    from src.intelligence.orchestrator import create_orchestrator

    db = SupabaseClient.get_client()
    orch = create_orchestrator()

    # Select diverse, high-impact signals — not all 230
    # Get the top 3 signals per competitor (diverse coverage)
    result = db.table("market_signals")\
        .select("id, company_name, headline, summary, signal_type, source_name, relevance_score, detected_at")\
        .eq("user_id", user_id)\
        .order("relevance_score", desc=True)\
        .order("detected_at", desc=True)\
        .execute()

    if not result.data:
        logger.error("No signals found for user %s", user_id)
        return

    # Select top 3 per company for diverse coverage
    signals_by_company: dict[str, list] = {}
    for s in result.data:
        company = s["company_name"]
        if company not in signals_by_company:
            signals_by_company[company] = []
        if len(signals_by_company[company]) < 3:
            signals_by_company[company].append(s)

    # Get competitors dynamically from battle_cards for this user
    company_id: str | None = None
    try:
        profile = db.table("user_profiles").select("company_id").eq("user_id", user_id).limit(1).execute()
        if profile.data:
            company_id = profile.data[0].get("company_id")
    except Exception:
        pass

    competitor_names: set[str] = set()
    if company_id:
        try:
            bc_result = db.table("battle_cards").select("competitor_name").eq("company_id", company_id).execute()
            competitor_names = {r["competitor_name"] for r in (bc_result.data or [])}
        except Exception:
            pass

    selected = []

    # Competitors first (most valuable insights)
    for company in competitor_names:
        if company in signals_by_company:
            selected.extend(signals_by_company[company])

    # Then other companies (industry context)
    for company, signals in signals_by_company.items():
        if company not in competitor_names:
            selected.extend(signals[:2])  # Max 2 per non-competitor

    # Cap at 20 total
    selected = selected[:20]

    logger.info(
        "Processing %d signals across %d companies",
        len(selected),
        len({s["company_name"] for s in selected}),
    )

    total_insights = 0
    for i, signal in enumerate(selected):
        company = signal["company_name"]
        headline = signal["headline"]
        summary = signal.get("summary", "")
        signal_type = signal.get("signal_type", "")

        event_text = f"{company}: {headline}"
        if summary:
            event_text += f" - {summary[:200]}"

        logger.info("[%d/%d] Processing: %s - %s...", i + 1, len(selected), company, headline[:60])

        try:
            start = time.time()
            insights = await orch.process_event(
                user_id=user_id,
                event=event_text,
                context={
                    "company_name": company,
                    "signal_type": signal_type,
                    "source": signal.get("source_name", ""),
                    "signal_id": signal.get("id", ""),
                },
            )
            elapsed = time.time() - start
            count = len(insights) if isinstance(insights, list) else 0
            total_insights += count
            logger.info("  -> %d insights in %.1fs (total: %d)", count, elapsed, total_insights)
        except Exception as e:
            logger.error("  -> Failed: %s", e)

        # Rate limit: 2 second pause between signals to avoid API throttling
        await asyncio.sleep(2)

    logger.info("Backfill complete: %d insights from %d signals", total_insights, len(selected))

    # Final count
    final = db.table("jarvis_insights")\
        .select("classification, engine_source")\
        .eq("user_id", user_id)\
        .execute()

    if final.data:
        from collections import Counter
        cls_counts = Counter(r["classification"] for r in final.data)
        eng_counts = Counter(r["engine_source"] for r in final.data)
        logger.info("Final DB state: %d total insights", len(final.data))
        logger.info("  By classification: %s", dict(cls_counts))
        logger.info("  By engine: %s", dict(eng_counts))


if __name__ == "__main__":
    target_user_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not target_user_id:
        # Auto-discover: find the first user with market signals
        from src.db.supabase import SupabaseClient

        _db = SupabaseClient.get_client()
        _users = _db.table("market_signals").select("user_id").limit(100).execute()
        _unique_ids = list({r["user_id"] for r in (_users.data or []) if r.get("user_id")})
        if _unique_ids:
            target_user_id = _unique_ids[0]
            logger.info("Auto-discovered user: %s", target_user_id)
        else:
            logger.error("No users with market signals found. Pass user_id as argument.")
            sys.exit(1)

    asyncio.run(backfill(target_user_id))
