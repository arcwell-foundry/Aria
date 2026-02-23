#!/usr/bin/env python3
"""Direct fact extraction script using service role key.

Bypasses HTTP endpoint and authentication by using Supabase service role key.
Finds conversations with episodes, extracts structured facts via Claude, and stores them.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.core.llm import LLMClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

FACT_EXTRACTION_PROMPT = """Extract structured facts from this conversation as subject-predicate-object triples.

{conversation}

Extract facts about:
- User's role, responsibilities, team structure (e.g., "User manages 5 sales reps")
- Account/company details (e.g., "Savillex evaluating ZoomInfo")
- Key relationships (e.g., "Rob Douglas is the decision maker")
- Timeline information (e.g., "Decision expected by March 1")
- Active deals/pursuits (e.g., "Discovery call scheduled with Dave Stephens")
- Preferences and priorities (e.g., "User prefers email over phone")

Return a JSON object with a "facts" array where each fact has:
- "subject": who/what the fact is about (e.g., "User", "Savillex", "Rob Douglas")
- "predicate": the relationship/action (e.g., "manages", "is evaluating", "will decide by")
- "object": the value/target (e.g., "5 sales reps", "ZoomInfo", "March 1")
- "confidence": 0.0-1.0 (0.95 for user-stated, 0.75 for implied, 0.6 for inferred)

Extract 3-8 meaningful facts. Focus on actionable, specific information.

Return ONLY valid JSON, no explanation:"""


def format_messages(messages: list[dict]) -> str:
    """Format messages as readable conversation text."""
    if not messages:
        return ""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def parse_fact_response(response: str) -> list[dict]:
    """Parse LLM fact extraction response."""
    try:
        # Strip markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        facts = parsed.get("facts", [])

        # Validate each fact has required fields
        valid_facts = []
        for fact in facts:
            if (
                isinstance(fact, dict)
                and fact.get("subject")
                and fact.get("predicate")
                and fact.get("object")
            ):
                valid_facts.append({
                    "subject": fact["subject"],
                    "predicate": fact["predicate"],
                    "object": fact["object"],
                    "confidence": float(fact.get("confidence", 0.75)),
                })

        return valid_facts

    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON: {response[:100]}...")
        return []


async def extract_and_store_facts(
    db,
    llm: LLMClient,
    user_id: str,
    conversation_id: str,
    messages: list[dict],
    dry_run: bool = False,
) -> list[dict]:
    """Extract facts from messages and store in database."""
    if not messages or len(messages) < 2:
        logger.info(f"Skipping conversation {conversation_id}: insufficient messages")
        return []

    # Format conversation
    formatted = format_messages(messages)

    # Extract facts using LLM
    logger.info(f"Extracting facts for conversation {conversation_id}...")
    fact_prompt = FACT_EXTRACTION_PROMPT.format(conversation=formatted)
    fact_response = await llm.generate_response(
        messages=[{"role": "user", "content": fact_prompt}],
        max_tokens=1000,
        temperature=0.2,
    )

    facts = parse_fact_response(fact_response)

    if not facts:
        logger.info(f"No facts extracted from conversation {conversation_id}")
        return []

    if dry_run:
        logger.info(f"DRY RUN: Would store {len(facts)} facts:")
        for f in facts:
            logger.info(f"  - {f['subject']} {f['predicate']} {f['object']} (conf: {f['confidence']})")
        return facts

    # Store facts in database
    stored_facts = []
    for fact in facts:
        try:
            fact_data = {
                "user_id": user_id,
                "subject": fact["subject"],
                "predicate": fact["predicate"],
                "object": fact["object"],
                "confidence": fact["confidence"],
                "source": "conversation_extraction",
                "metadata": {
                    "conversation_id": conversation_id,
                    "extracted_at": datetime.now(UTC).isoformat(),
                },
            }

            result = db.table("semantic_facts").insert(fact_data).execute()
            if result.data:
                stored_facts.append({**fact_data, "id": result.data[0]["id"]})
                logger.info(
                    f"  Stored: {fact['subject']} {fact['predicate']} {fact['object']}"
                )
        except Exception as e:
            logger.warning(f"Failed to store fact: {e}")

    return stored_facts


async def main():
    parser = argparse.ArgumentParser(description="Extract semantic facts from conversations")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be extracted without storing")
    parser.add_argument("--conversation-id", type=str, help="Extract facts for a specific conversation ID")
    args = parser.parse_args()

    # Get credentials
    supabase_url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not service_role_key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        return

    # Create Supabase client with service role key (bypasses RLS)
    db = create_client(supabase_url, service_role_key)
    logger.info("Connected to Supabase with service role key")

    # Initialize LLM client
    llm = LLMClient()
    logger.info("Initialized LLM client")

    # Check existing facts count
    existing_result = db.table("semantic_facts").select("id", count="exact").execute()
    existing_count = existing_result.count if hasattr(existing_result, "count") else 0
    logger.info(f"Existing semantic_facts: {existing_count} records")

    # Get conversations with episodes (these have been processed)
    if args.conversation_id:
        # Single conversation mode
        conv_result = (
            db.table("conversations")
            .select("id, user_id")
            .eq("id", args.conversation_id)
            .execute()
        )
        conversations = conv_result.data or []
        logger.info(f"Processing single conversation: {args.conversation_id}")
    else:
        # Get all conversations that have episodes
        episodes_result = db.table("conversation_episodes").select("conversation_id, user_id").execute()
        episode_data = episodes_result.data or []

        # Group by conversation
        conversations = [
            {"id": ep["conversation_id"], "user_id": ep["user_id"]}
            for ep in episode_data
        ]
        # Remove duplicates
        seen = set()
        unique_conversations = []
        for c in conversations:
            if c["id"] not in seen:
                seen.add(c["id"])
                unique_conversations.append(c)
        conversations = unique_conversations

    logger.info(f"Found {len(conversations)} conversations with episodes")

    if not conversations:
        logger.info("No conversations to process. Nothing to do.")
        return

    # Process each conversation
    total_facts = 0
    processed = 0
    failed = 0

    for conv in conversations:
        conv_id = conv["id"]
        user_id = conv["user_id"]

        try:
            # Check if facts already exist for this conversation
            if not args.dry_run:
                existing = (
                    db.table("semantic_facts")
                    .select("id")
                    .eq("user_id", user_id)
                    .contains("metadata", {"conversation_id": conv_id})
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    logger.info(f"Skipping {conv_id}: facts already extracted")
                    continue

            # Get messages for this conversation
            msgs_result = (
                db.table("messages")
                .select("role, content, created_at")
                .eq("conversation_id", conv_id)
                .order("created_at")
                .execute()
            )

            messages = msgs_result.data or []

            if len(messages) < 2:
                logger.info(f"Skipping {conv_id}: only {len(messages)} messages")
                continue

            # Extract and store facts
            facts = await extract_and_store_facts(
                db=db,
                llm=llm,
                user_id=user_id,
                conversation_id=conv_id,
                messages=messages,
                dry_run=args.dry_run,
            )

            total_facts += len(facts)
            processed += 1

        except Exception as e:
            logger.error(f"Error processing conversation {conv_id}: {e}")
            failed += 1

    # Summary
    logger.info(f"\n{'='*50}")
    logger.info(f"FACT EXTRACTION {'DRY RUN ' if args.dry_run else ''}COMPLETE")
    logger.info(f"  Total conversations processed: {processed}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"  Total facts extracted: {total_facts}")
    logger.info(f"{'='*50}")

    if not args.dry_run:
        # Verify results
        logger.info("\nVerifying semantic_facts table...")
        verify_result = (
            db.table("semantic_facts")
            .select("subject, predicate, object, confidence, created_at")
            .order("created_at", desc=True)
            .limit(15)
            .execute()
        )

        if verify_result.data:
            logger.info(f"\nRecent facts in database ({len(verify_result.data)} shown):")
            for fact in verify_result.data:
                logger.info(
                    f"  - {fact['subject']} {fact['predicate']} {fact['object']} "
                    f"(conf: {fact['confidence']:.2f})"
                )


if __name__ == "__main__":
    asyncio.run(main())
