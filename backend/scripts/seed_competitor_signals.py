#!/usr/bin/env python3
"""One-time Exa enrichment scan for competitor and market intelligence.

Seeds market_signals and memory_semantic with signals about COMPETITORS,
POTENTIAL CUSTOMERS, and MARKET trends — not just the user's own company.

Uses the existing ExaEnrichmentProvider.search_news() method.

Cost limit: Max 30 Exa queries. This script uses 24.

Usage:
    cd backend
    python scripts/seed_competitor_signals.py
"""

import asyncio
import logging
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.capabilities.enrichment_providers.exa_provider import (
    ExaEnrichmentProvider,
    ExaSearchResult,
)
from src.db.supabase import SupabaseClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

COMPETITORS = [
    "Cytiva",
    "Sartorius",
    "Pall Danaher",
    "MilliporeSigma",
    "Thermo Fisher Scientific",
]

# Per-competitor query templates: (query_suffix, num_results)
COMPETITOR_QUERIES = [
    ("bioprocessing 2025 2026", 10),
    ("FDA approval regulatory", 5),
    ("CEO hired appointed leadership", 5),
    ("partnership acquisition deal", 5),
]

# Market-level queries: (query, num_results)
MARKET_QUERIES = [
    ("bioprocessing industry funding 2025 2026", 10),
    ("FDA bioprocessing guidance approval 2025 2026", 10),
    ("bioprocessing clinical trial expansion", 10),
    ("bioprocessing conference event 2026", 5),
]

# Signal type classification rules (same as backfill_market_signals.py)
SIGNAL_TYPE_RULES = [
    ("fda_approval", ["fda approval", "fda cleared", "fda approved", "regulatory approval", "fda granted", "fda authorized"]),
    ("clinical_trial", ["clinical trial", "phase i", "phase ii", "phase iii", "phase 1", "phase 2", "phase 3", "clinical study", "pivotal trial"]),
    ("funding", ["acquisition", "acquire", "acquired", "invested", "funding", "ipo", "market value", "merger", "buyout", "raised", "series"]),
    ("leadership", ["ceo", "president", "chief", "appointed", "joined as", "promoted to", "officer", "executive", "board member", "hired"]),
    ("partnership", ["partner", "partnership", "agreement", "collaborated", "alliance", "joint venture", "strategic alliance", "deal", "contract"]),
    ("patent", ["patent", "intellectual property", "ip protection"]),
    ("earnings", ["revenue", "earnings", "quarterly", "financial report", "q1 ", "q2 ", "q3 ", "q4 ", "annual report", "profit"]),
    ("regulatory", ["compliance", "regulation", "sustainability", "esg", "guidance", "gmp", "regulatory change"]),
    ("hiring", ["hiring", "recruited", "expanding team", "job opening", "workforce", "headcount"]),
    ("product", ["launched", "product", "introduced", "exhibited", "conference", "bio ", "showcase", "announcement", "release"]),
]


def classify_signal_type(text: str) -> str:
    """Classify text into a signal type using keyword matching."""
    text_lower = text.lower()
    for signal_type, keywords in SIGNAL_TYPE_RULES:
        for keyword in keywords:
            if keyword in text_lower:
                return signal_type
    return "product"


def extract_headline(title: str, text: str, max_length: int = 120) -> str:
    """Extract a headline from the Exa result title or text."""
    # Prefer the Exa title if it's meaningful
    if title and len(title) > 10:
        headline = title.strip()
    elif text:
        # First sentence from text
        match = re.match(r"^(.+?[.!?])\s", text)
        headline = match.group(1) if match else text[:max_length]
    else:
        headline = "Market signal detected"

    if len(headline) > max_length:
        headline = headline[:max_length].rsplit(" ", 1)[0] + "..."
    return headline


def extract_company_from_text(text: str, default: str) -> str:
    """Try to extract a company name from text, falling back to default."""
    # Look for known competitors mentioned in text
    all_known = COMPETITORS + ["Repligen"]
    text_lower = text.lower()
    for company in all_known:
        if company.lower() in text_lower:
            return company
    return default


async def run_exa_scan(
    exa: ExaEnrichmentProvider,
) -> list[tuple[str, str, ExaSearchResult]]:
    """Run all Exa queries and return (company_name, query_context, result) tuples.

    Total queries: 5 competitors * 4 queries + 4 market = 24.
    """
    all_results: list[tuple[str, str, ExaSearchResult]] = []
    query_count = 0

    # --- Competitor queries ---
    for competitor in COMPETITORS:
        for query_suffix, num_results in COMPETITOR_QUERIES:
            query = f"{competitor} {query_suffix}"
            logger.info(f"[Query {query_count + 1}/24] Searching: {query}")
            try:
                results = await exa.search_news(
                    query=query,
                    num_results=num_results,
                    days_back=180,  # 6 months of history
                )
                for r in results:
                    all_results.append((competitor, query_suffix, r))
                logger.info(f"  -> {len(results)} results")
            except Exception as e:
                logger.error(f"  -> Failed: {e}")
            query_count += 1

            # Small delay to be respectful of rate limits
            await asyncio.sleep(0.5)

    # --- Market-level queries ---
    for query, num_results in MARKET_QUERIES:
        logger.info(f"[Query {query_count + 1}/24] Searching: {query}")
        try:
            results = await exa.search_news(
                query=query,
                num_results=num_results,
                days_back=180,
            )
            for r in results:
                # For market queries, try to extract company from text
                company = extract_company_from_text(
                    f"{r.title} {r.text}", "Life Sciences Industry"
                )
                all_results.append((company, "market", r))
            logger.info(f"  -> {len(results)} results")
        except Exception as e:
            logger.error(f"  -> Failed: {e}")
        query_count += 1
        await asyncio.sleep(0.5)

    logger.info(f"Total Exa queries executed: {query_count}")
    logger.info(f"Total raw results: {len(all_results)}")
    return all_results


async def seed_competitor_signals() -> int:
    """Main seed function: query Exa, deduplicate, store signals + semantic memory."""
    db = SupabaseClient.get_client()

    # Get user ID
    users_result = db.table("user_profiles").select("id").limit(1).execute()
    if not users_result.data:
        logger.error("No users found in database")
        return 0
    user_id = users_result.data[0]["id"]
    logger.info(f"Using user_id: {user_id}")

    # Get existing headlines for deduplication
    existing_result = (
        db.table("market_signals")
        .select("headline, source_url")
        .eq("user_id", user_id)
        .execute()
    )
    existing_headlines: set[str] = {s["headline"] for s in existing_result.data}
    existing_urls: set[str] = {
        s["source_url"] for s in existing_result.data if s.get("source_url")
    }
    logger.info(f"Found {len(existing_headlines)} existing signals (for dedup)")

    # Run Exa searches
    exa = ExaEnrichmentProvider()
    raw_results = await run_exa_scan(exa)

    # Deduplicate by URL and headline
    seen_urls: set[str] = set()
    seen_headlines: set[str] = set()
    signals_to_create: list[dict] = []
    semantic_to_create: list[dict] = []
    signals_by_type: dict[str, int] = defaultdict(int)
    signals_by_company: dict[str, int] = defaultdict(int)

    for company_name, query_context, result in raw_results:
        # Skip if URL already exists
        if result.url in existing_urls or result.url in seen_urls:
            continue
        seen_urls.add(result.url)

        # Build headline
        headline = extract_headline(result.title, result.text)
        if headline in existing_headlines or headline in seen_headlines:
            continue
        seen_headlines.add(headline)

        # Classify signal type from title + text
        combined_text = f"{result.title} {result.text} {query_context}"
        signal_type = classify_signal_type(combined_text)

        # Determine relevance score
        is_direct_competitor = company_name in COMPETITORS
        relevance_score = 0.95 if is_direct_competitor else 0.80

        # Build summary (truncate text to reasonable length)
        summary = result.text[:500] if result.text else headline

        # Parse detected_at from published_date
        detected_at = None
        if result.published_date:
            try:
                # Exa returns ISO format dates
                detected_at = result.published_date
            except Exception:
                pass

        signal_data = {
            "user_id": user_id,
            "company_name": company_name,
            "signal_type": signal_type,
            "headline": headline,
            "summary": summary,
            "source_url": result.url,
            "source_name": "exa_competitor_scan",
            "relevance_score": relevance_score,
            "detected_at": detected_at or datetime.now(UTC).isoformat(),
            "metadata": {
                "exa_score": result.score,
                "query_context": query_context,
                "backfilled": True,
                "source": "seed_competitor_signals",
            },
        }
        signals_to_create.append(signal_data)
        signals_by_type[signal_type] += 1
        signals_by_company[company_name] += 1

        # Also prepare semantic memory entry
        semantic_fact = f"{company_name}: {headline}"
        if summary and summary != headline:
            semantic_fact = f"{company_name}: {summary[:300]}"

        semantic_data = {
            "user_id": user_id,
            "fact": semantic_fact,
            "confidence": 0.80,
            "source": "intelligence_heartbeat",
            "metadata": {
                "signal_type": signal_type,
                "company_name": company_name,
                "source_url": result.url,
                "exa_score": result.score,
            },
        }
        semantic_to_create.append(semantic_data)

    # Log distribution before insert
    logger.info(f"\nSignals to create: {len(signals_to_create)}")
    logger.info("\nBy signal type:")
    for stype, count in sorted(signals_by_type.items(), key=lambda x: -x[1]):
        logger.info(f"  {stype}: {count}")
    logger.info("\nBy company:")
    for company, count in sorted(signals_by_company.items(), key=lambda x: -x[1]):
        logger.info(f"  {company}: {count}")

    # --- Insert market_signals in batches ---
    created_signals = 0
    batch_size = 50
    for i in range(0, len(signals_to_create), batch_size):
        batch = signals_to_create[i : i + batch_size]
        try:
            result = db.table("market_signals").insert(batch).execute()
            created_signals += len(result.data)
            logger.info(f"Inserted market_signals batch {i // batch_size + 1}: {len(result.data)} rows")
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            for signal in batch:
                try:
                    db.table("market_signals").insert(signal).execute()
                    created_signals += 1
                except Exception as e2:
                    logger.warning(f"Individual insert failed: {signal['headline'][:50]}: {e2}")

    # --- Insert memory_semantic in batches ---
    created_semantic = 0
    for i in range(0, len(semantic_to_create), batch_size):
        batch = semantic_to_create[i : i + batch_size]
        try:
            result = db.table("memory_semantic").insert(batch).execute()
            created_semantic += len(result.data)
            logger.info(f"Inserted memory_semantic batch {i // batch_size + 1}: {len(result.data)} rows")
        except Exception as e:
            logger.error(f"Semantic batch insert failed: {e}")
            for entry in batch:
                try:
                    db.table("memory_semantic").insert(entry).execute()
                    created_semantic += 1
                except Exception as e2:
                    logger.warning(f"Semantic insert failed: {e2}")

    logger.info(f"\nCreated {created_signals} market signals")
    logger.info(f"Created {created_semantic} semantic memory entries")

    # --- Verify final state ---
    verify = (
        db.table("market_signals")
        .select("company_name, signal_type")
        .eq("user_id", user_id)
        .execute()
    )
    final_by_company: dict[str, int] = defaultdict(int)
    final_by_type: dict[str, int] = defaultdict(int)
    for s in verify.data:
        final_by_company[s["company_name"]] += 1
        final_by_type[s["signal_type"]] += 1

    logger.info(f"\n{'='*60}")
    logger.info("FINAL market_signals state:")
    logger.info(f"Total signals: {len(verify.data)}")
    logger.info("\nBy company:")
    for company, count in sorted(final_by_company.items(), key=lambda x: -x[1]):
        logger.info(f"  {company}: {count}")
    logger.info("\nBy signal type:")
    for stype, count in sorted(final_by_type.items(), key=lambda x: -x[1]):
        logger.info(f"  {stype}: {count}")
    logger.info(f"{'='*60}")

    return created_signals


async def main() -> None:
    """Entry point."""
    logger.info("=" * 60)
    logger.info("SEED COMPETITOR & MARKET INTELLIGENCE")
    logger.info("One-time Exa enrichment scan (max 24 queries)")
    logger.info("=" * 60)

    try:
        SupabaseClient.get_client()
        logger.info("Supabase client initialized")

        created = await seed_competitor_signals()

        logger.info("=" * 60)
        logger.info(f"Seed complete. Created {created} new market signals.")
        logger.info("=" * 60)
    except Exception as e:
        logger.exception(f"Seed failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
