#!/usr/bin/env python3
"""Backfill market_signals from memory_semantic.

This script one-time migrates existing semantic memory facts into market signals.
It queries facts from memory_semantic where source is in ('enrichment_news',
'inferred_during_onboarding', 'enrichment_leadership'), deduplicates them,
classifies by signal type, and inserts into market_signals.

Usage:
    cd backend
    python scripts/backfill_market_signals.py
"""

import asyncio
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.supabase import SupabaseClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Signal type classification rules - ordered by specificity
SIGNAL_TYPE_RULES = [
    ("fda_approval", ["fda approval", "fda cleared", "fda approved", "regulatory approval"]),
    ("clinical_trial", ["clinical trial", "phase i", "phase ii", "phase iii", "phase 1", "phase 2", "phase 3", "clinical study"]),
    ("funding", ["acquisition", "acquire", "acquired", "invested", "funding", "ipo", "market value", "merger", "buyout"]),
    ("leadership", ["ceo", "president", "chief", "appointed", "joined as", "promoted to", "officer", "executive", "board member"]),
    ("partnership", ["partner", "partnership", "agreement", "collaborated", "alliance", "joint venture", "strategic alliance"]),
    ("patent", ["patent", "intellectual property", "ip protection"]),
    ("earnings", ["revenue", "earnings", "quarterly", "financial report", "q1 ", "q2 ", "q3 ", "q4 ", "annual report"]),
    ("regulatory", ["compliance", "regulation", "sustainability", "esg"]),
    ("hiring", ["hiring", "recruited", "expanding team", "job opening"]),
    ("product", ["launched", "product", "introduced", "exhibited", "conference", "bio ", "showcase", "announcement"]),
]


def classify_signal_type(fact: str) -> str:
    """Classify a fact into a signal type using keyword matching.

    Args:
        fact: The fact text to classify.

    Returns:
        Signal type string.
    """
    fact_lower = fact.lower()

    for signal_type, keywords in SIGNAL_TYPE_RULES:
        for keyword in keywords:
            if keyword in fact_lower:
                return signal_type

    # Default to 'product' if no match
    return "product"


def extract_headline(fact: str, max_length: int = 80) -> str:
    """Extract a headline from a fact.

    Args:
        fact: The fact text.
        max_length: Maximum headline length.

    Returns:
        Headline string.
    """
    # Try to get first sentence
    first_sentence_match = re.match(r"^(.+?[.!?])\s", fact)
    if first_sentence_match:
        headline = first_sentence_match.group(1)
    else:
        headline = fact

    # Truncate if needed
    if len(headline) > max_length:
        headline = headline[:max_length].rsplit(" ", 1)[0] + "..."

    return headline


def extract_company_name(fact: str, metadata: dict | None) -> str:
    """Extract company name from fact or metadata.

    Args:
        fact: The fact text.
        metadata: The fact's metadata.

    Returns:
        Company name string.
    """
    # Check metadata first
    if metadata and "entities" in metadata:
        entities = metadata["entities"]
        if isinstance(entities, list):
            for entity in entities:
                if isinstance(entity, dict) and entity.get("type") == "company":
                    return entity.get("name", "Unknown")
                elif isinstance(entity, str):
                    return entity

    # Try to extract from fact (look for common patterns)
    # "Repligen announced..." or "Company X..."
    patterns = [
        r"^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+(?:announced|reported|launched|partnered|acquired)",
        r"^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)\s+(?:and|&)",
    ]

    for pattern in patterns:
        match = re.match(pattern, fact)
        if match:
            return match.group(1)

    # Default company name
    return "Repligen"  # Most facts are about Repligen based on the evidence


def get_relevance_score(source: str) -> float:
    """Get relevance score based on source.

    Args:
        source: The fact's source.

    Returns:
        Relevance score (0.0-1.0).
    """
    if source == "enrichment_news":
        return 0.9
    elif source == "inferred_during_onboarding":
        return 0.7
    elif source == "enrichment_leadership":
        return 0.85
    else:
        return 0.7


async def backfill_market_signals() -> int:
    """Backfill market_signals from memory_semantic.

    Returns:
        Number of signals created.
    """
    db = SupabaseClient.get_client()

    # Get the user ID (should be single user - Dhruv)
    users_result = db.table("users").select("id").limit(1).execute()
    if not users_result.data:
        logger.error("No users found in database")
        return 0

    user_id = users_result.data[0]["id"]
    logger.info(f"Using user_id: {user_id}")

    # Query distinct facts from relevant sources
    sources = ["enrichment_news", "inferred_during_onboarding", "enrichment_leadership"]

    # Get all facts from these sources
    facts_result = (
        db.table("memory_semantic")
        .select("id, fact, confidence, source, metadata, created_at")
        .in_("source", sources)
        .execute()
    )

    all_facts = facts_result.data
    logger.info(f"Found {len(all_facts)} total facts from relevant sources")

    # Deduplicate by exact fact text
    seen_facts: set[str] = set()
    unique_facts = []
    for fact_record in all_facts:
        fact_text = fact_record["fact"]
        if fact_text not in seen_facts:
            seen_facts.add(fact_text)
            unique_facts.append(fact_record)

    logger.info(f"Found {len(unique_facts)} unique facts after deduplication")

    # Get existing market signals to avoid duplicates
    existing_signals = db.table("market_signals").select("headline").eq("user_id", user_id).execute()
    existing_headlines = {s["headline"] for s in existing_signals.data}
    logger.info(f"Found {len(existing_headlines)} existing market signals")

    # Classify and prepare signals
    signals_by_type: dict[str, list[dict]] = defaultdict(list)
    signals_to_create = []

    for fact_record in unique_facts:
        fact_text = fact_record["fact"]
        source = fact_record["source"]
        metadata = fact_record.get("metadata")
        created_at = fact_record.get("created_at")

        # Classify signal type
        signal_type = classify_signal_type(fact_text)

        # Extract headline
        headline = extract_headline(fact_text)

        # Skip if already exists
        if headline in existing_headlines:
            continue

        # Extract company name
        company_name = extract_company_name(fact_text, metadata)

        # Get relevance score
        relevance_score = get_relevance_score(source)

        signal_data = {
            "user_id": user_id,
            "company_name": company_name,
            "signal_type": signal_type,
            "headline": headline,
            "summary": fact_text,
            "source_name": source,
            "relevance_score": relevance_score,
            "detected_at": created_at,
            "metadata": {
                "source_fact_id": fact_record["id"],
                "confidence": fact_record.get("confidence", 0.5),
                "backfilled": True,
            },
        }

        signals_to_create.append(signal_data)
        signals_by_type[signal_type].append(signal_data)

    # Log distribution
    logger.info("Signal type distribution:")
    for signal_type, signals in sorted(signals_by_type.items(), key=lambda x: -len(x[1])):
        logger.info(f"  {signal_type}: {len(signals)}")

    logger.info(f"Total signals to create: {len(signals_to_create)}")

    # Insert signals in batches
    batch_size = 50
    created_count = 0

    for i in range(0, len(signals_to_create), batch_size):
        batch = signals_to_create[i : i + batch_size]
        try:
            result = db.table("market_signals").insert(batch).execute()
            created_count += len(result.data)
            logger.info(f"Created batch {i // batch_size + 1}: {len(result.data)} signals")
        except Exception as e:
            logger.error(f"Failed to insert batch: {e}")
            # Try individual inserts
            for signal in batch:
                try:
                    db.table("market_signals").insert(signal).execute()
                    created_count += 1
                except Exception as e2:
                    logger.warning(f"Failed to insert signal '{signal['headline'][:50]}...': {e2}")

    logger.info(f"Successfully created {created_count} market signals")

    # Verify the results
    verify_result = db.table("market_signals").select("signal_type").eq("user_id", user_id).execute()
    type_counts: dict[str, int] = defaultdict(int)
    for signal in verify_result.data:
        type_counts[signal["signal_type"]] += 1

    logger.info("Final market_signals distribution:")
    for signal_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        logger.info(f"  {signal_type}: {count}")

    return created_count


async def main() -> None:
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Starting market_signals backfill from memory_semantic")
    logger.info("=" * 60)

    try:
        # Initialize Supabase client
        SupabaseClient.get_client()
        logger.info("Supabase client initialized")

        # Run backfill
        created = await backfill_market_signals()

        logger.info("=" * 60)
        logger.info(f"Backfill complete. Created {created} signals.")
        logger.info("=" * 60)
    except Exception as e:
        logger.exception(f"Backfill failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
