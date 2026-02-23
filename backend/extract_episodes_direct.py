#!/usr/bin/env python3
"""Direct episode extraction script using service role key.

Bypasses HTTP endpoint and authentication by using Supabase service role key.
Finds conversations without episodes, extracts summaries via Claude, and stores them.
"""

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

# Prompts from ConversationService
SUMMARY_PROMPT = """Summarize this conversation concisely in 2-3 sentences:

{conversation}

Focus on:
- Key decisions made
- Important information shared
- Action items agreed
- Questions left unanswered

Summary:"""

EXTRACTION_PROMPT = """Analyze this conversation and extract structured information:

{conversation}

Return a JSON object with:
- "key_topics": list of 3-5 main topics discussed (short phrases)
- "user_state": object with "mood" (stressed/neutral/positive), "confidence" (uncertain/moderate/high), "focus" (main area of attention)
- "outcomes": list of objects with "type" (decision/action_item/information) and "content" (what was decided/agreed)
- "open_threads": list of objects with "topic", "status" (pending/awaiting_response/blocked), and "context" (brief explanation)

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


def parse_extraction_response(response: str) -> dict:
    """Parse LLM extraction response JSON with defaults for failures."""
    defaults = {
        "key_topics": [],
        "user_state": {},
        "outcomes": [],
        "open_threads": [],
    }
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
        return {
            "key_topics": parsed.get("key_topics", []),
            "user_state": parsed.get("user_state", {}),
            "outcomes": parsed.get("outcomes", []),
            "open_threads": parsed.get("open_threads", []),
        }
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON: {response[:100]}...")
        return defaults


async def extract_and_store_episode(
    db,
    llm: LLMClient,
    user_id: str,
    conversation_id: str,
    messages: list[dict],
) -> dict | None:
    """Extract episode from messages and store in database."""
    if not messages or len(messages) < 2:
        logger.info(f"Skipping conversation {conversation_id}: insufficient messages")
        return None

    # Format conversation
    formatted = format_messages(messages)

    # Generate summary
    logger.info(f"Generating summary for conversation {conversation_id}...")
    summary_prompt = SUMMARY_PROMPT.format(conversation=formatted)
    summary = await llm.generate_response(
        messages=[{"role": "user", "content": summary_prompt}],
        max_tokens=500,
        temperature=0.3,
    )

    # Extract structured info
    logger.info(f"Extracting structured info for conversation {conversation_id}...")
    extraction_prompt = EXTRACTION_PROMPT.format(conversation=formatted)
    extraction_response = await llm.generate_response(
        messages=[{"role": "user", "content": extraction_prompt}],
        max_tokens=1000,
        temperature=0.2,
    )
    extracted = parse_extraction_response(extraction_response)

    # Calculate duration
    first_msg = messages[0]
    last_msg = messages[-1]

    started_at_str = first_msg.get("created_at")
    ended_at_str = last_msg.get("created_at")

    if started_at_str:
        started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
    else:
        started_at = datetime.now(UTC)

    if ended_at_str:
        ended_at = datetime.fromisoformat(ended_at_str.replace("Z", "+00:00"))
    else:
        ended_at = datetime.now(UTC)

    duration_minutes = max(1, int((ended_at - started_at).total_seconds() / 60))

    # Prepare episode data
    now = datetime.now(UTC)
    episode_data = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "summary": summary.strip(),
        "key_topics": extracted["key_topics"],
        "entities_discussed": [],  # Graphiti not configured for bulk extraction
        "user_state": extracted["user_state"],
        "outcomes": extracted["outcomes"],
        "open_threads": extracted["open_threads"],
        "message_count": len(messages),
        "duration_minutes": duration_minutes,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "current_salience": 1.0,
        "last_accessed_at": now.isoformat(),
        "access_count": 0,
    }

    # Insert into database
    result = db.table("conversation_episodes").insert(episode_data).execute()

    if result.data:
        logger.info(f"Created episode for conversation {conversation_id}")
        return result.data[0]
    else:
        logger.error(f"Failed to insert episode for {conversation_id}")
        return None


async def main():
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

    # Step 1: Get all conversations
    conversations_result = db.table("conversations").select("id, user_id").execute()
    all_conversations = conversations_result.data or []
    logger.info(f"Found {len(all_conversations)} total conversations")

    if not all_conversations:
        logger.info("No conversations found. Nothing to do.")
        return

    # Step 2: Get existing episodes
    conv_ids = [c["id"] for c in all_conversations]
    episodes_result = (
        db.table("conversation_episodes")
        .select("conversation_id")
        .in_("conversation_id", conv_ids)
        .execute()
    )
    existing_episode_ids = {e["conversation_id"] for e in (episodes_result.data or [])}
    logger.info(f"Found {len(existing_episode_ids)} existing episodes")

    # Step 3: Find conversations without episodes
    missing = [c for c in all_conversations if c["id"] not in existing_episode_ids]
    logger.info(f"Found {len(missing)} conversations without episodes")

    if not missing:
        logger.info("All conversations have episodes. Nothing to do.")
        return

    # Step 4: Process each missing conversation
    created = 0
    failed = 0

    for conv in missing:
        conv_id = conv["id"]
        user_id = conv["user_id"]

        try:
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

            # Extract and store episode
            result = await extract_and_store_episode(
                db=db,
                llm=llm,
                user_id=user_id,
                conversation_id=conv_id,
                messages=messages,
            )

            if result:
                created += 1
            else:
                failed += 1

        except Exception as e:
            logger.error(f"Error processing conversation {conv_id}: {e}")
            failed += 1

    # Summary
    logger.info(f"\n{'='*50}")
    logger.info(f"EXTRACTION COMPLETE")
    logger.info(f"  Total conversations checked: {len(all_conversations)}")
    logger.info(f"  Missing episodes: {len(missing)}")
    logger.info(f"  Created: {created}")
    logger.info(f"  Failed: {failed}")
    logger.info(f"{'='*50}")

    # Verify results
    logger.info("\nVerifying conversation_episodes table...")
    verify_result = (
        db.table("conversation_episodes")
        .select("conversation_id, summary, key_topics, created_at")
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )

    if verify_result.data:
        logger.info(f"\nRecent episodes in database ({len(verify_result.data)} shown):")
        for ep in verify_result.data:
            summary_preview = ep.get("summary", "")[:80]
            logger.info(f"  - {ep['conversation_id'][:8]}...: {summary_preview}...")
            logger.info(f"    Topics: {ep.get('key_topics', [])}")


if __name__ == "__main__":
    asyncio.run(main())
