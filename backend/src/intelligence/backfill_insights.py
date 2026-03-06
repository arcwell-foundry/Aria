"""
One-time backfill: Process top existing signals through Jarvis to seed insights.
Run with: PYTHONPATH=. python3 -m src.intelligence.backfill_insights
"""

import asyncio
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def backfill():
    from src.db.supabase import SupabaseClient
    from src.intelligence.orchestrator import create_orchestrator

    db = SupabaseClient.get_client()
    orch = create_orchestrator()

    # Select diverse, high-impact signals — not all 230
    # Get the top 3 signals per competitor (diverse coverage)
    result = db.table("market_signals")\
        .select("id, company_name, headline, summary, signal_type, source_name, relevance_score, detected_at")\
        .eq("user_id", "41475700-c1fb-4f66-8c56-77bd90b73abb")\
        .order("relevance_score", desc=True)\
        .order("detected_at", desc=True)\
        .execute()

    if not result.data:
        logger.error("No signals found")
        return

    # Select top 3 per company for diverse coverage
    signals_by_company: dict[str, list] = {}
    for s in result.data:
        company = s["company_name"]
        if company not in signals_by_company:
            signals_by_company[company] = []
        if len(signals_by_company[company]) < 3:
            signals_by_company[company].append(s)

    # Flatten and prioritize: competitors first (they have battle cards)
    competitor_names = {"Cytiva", "Sartorius", "Pall Corporation", "MilliporeSigma", "Thermo Fisher"}
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

    logger.info(f"Processing {len(selected)} signals across {len(set(s['company_name'] for s in selected))} companies")

    total_insights = 0
    for i, signal in enumerate(selected):
        company = signal["company_name"]
        headline = signal["headline"]
        summary = signal.get("summary", "")
        signal_type = signal.get("signal_type", "")

        event_text = f"{company}: {headline}"
        if summary:
            event_text += f" - {summary[:200]}"

        logger.info(f"[{i+1}/{len(selected)}] Processing: {company} - {headline[:60]}...")

        try:
            start = time.time()
            insights = await orch.process_event(
                user_id="41475700-c1fb-4f66-8c56-77bd90b73abb",
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
            logger.info(f"  -> {count} insights in {elapsed:.1f}s (total: {total_insights})")
        except Exception as e:
            logger.error(f"  -> Failed: {e}")

        # Rate limit: 2 second pause between signals to avoid API throttling
        await asyncio.sleep(2)

    logger.info(f"\nBackfill complete: {total_insights} insights from {len(selected)} signals")

    # Final count
    final = db.table("jarvis_insights")\
        .select("classification, engine_source")\
        .eq("user_id", "41475700-c1fb-4f66-8c56-77bd90b73abb")\
        .execute()

    if final.data:
        from collections import Counter
        cls_counts = Counter(r["classification"] for r in final.data)
        eng_counts = Counter(r["engine_source"] for r in final.data)
        logger.info(f"Final DB state: {len(final.data)} total insights")
        logger.info(f"  By classification: {dict(cls_counts)}")
        logger.info(f"  By engine: {dict(eng_counts)}")


if __name__ == "__main__":
    asyncio.run(backfill())
