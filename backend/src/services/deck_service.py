"""Deck generation service for AI-powered Gamma presentations.

Provides high-level functions to create slide decks from:
- Meeting context (pre-meeting briefings)
- Ad-hoc prompts (user requests)

Integrates with:
- Gamma API for presentation generation
- Memory system for storing deck references
- Push notifications for surfacing completed decks
- MeetingBaaS for posting deck links to meeting chat
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from supabase import Client

from src.core.config import settings
from src.integrations.gamma.client import GammaClient, GammaClientError, GammaTextMode, get_gamma_client

logger = logging.getLogger(__name__)


class DeckServiceError(Exception):
    """Base exception for deck service errors."""

    pass


async def _get_aria_knowledge_context(db: Client) -> str:
    """Fetch all aria_knowledge rows and format as concise context for prompts.

    Returns:
        Formatted string describing ARIA's identity, agents, capabilities,
        integrations, and constraints. Empty string if unavailable.
    """
    try:
        result = db.table("aria_knowledge").select("category, name, description").execute()
        rows = result.data or []
        if not rows:
            return ""

        by_category: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_category.setdefault(row["category"], []).append(row)

        parts = ["## About ARIA (use this for accurate self-description)\n"]

        # Identity
        for row in by_category.get("identity", []):
            parts.append(f"- {row['name']}: {row['description']}")

        # Agents
        agents = by_category.get("agent", [])
        if agents:
            parts.append("\n### AI Agents")
            for row in agents:
                parts.append(f"- **{row['name']}**: {row['description']}")

        # Capabilities
        caps = by_category.get("capability", [])
        if caps:
            parts.append("\n### Capabilities")
            for row in caps:
                parts.append(f"- **{row['name']}**: {row['description']}")

        # Integrations
        integrations = by_category.get("integration", [])
        if integrations:
            parts.append("\n### Integrations")
            parts.append(", ".join(row["name"] for row in integrations))

        # Constraints
        constraints = by_category.get("does_not_do", [])
        if constraints:
            parts.append("\n### What ARIA does NOT do")
            for row in constraints:
                parts.append(f"- {row['description']}")

        return "\n".join(parts)
    except Exception:
        logger.exception("Failed to fetch aria_knowledge context for deck generation")
        return ""


async def create_deck_from_context(
    db: Client,
    user_id: str,
    meeting_id: str,
    context: dict[str, Any],
    post_to_meeting: bool = False,
) -> dict[str, Any]:
    """Create a presentation deck from meeting context.

    Generates a deck using meeting briefing data, account research,
    and other contextual information. Optionally posts the deck
    link to the meeting chat.

    Args:
        db: Supabase client instance.
        user_id: The user's ID.
        meeting_id: The meeting ID to associate the deck with.
        context: Meeting context including:
            - meeting_title: Title of the meeting
            - meeting_objective: Purpose/objective
            - attendees: List of attendees
            - account_research: Research about the account
            - talking_points: Key talking points
            - previous_interactions: History with this account
        post_to_meeting: Whether to post the deck link to meeting chat.

    Returns:
        Dict with:
            - deck_id: Internal deck record ID
            - gamma_url: URL to the generated presentation
            - gamma_id: Gamma's internal ID
            - status: "completed" or "pending"
            - credits_used: Credits deducted from Gamma account

    Raises:
        DeckServiceError: If deck generation fails.
    """
    if not settings.gamma_configured:
        raise DeckServiceError("GAMMA_API_KEY not configured")

    # Build the prompt from context
    prompt = _build_meeting_prompt(context)
    meeting_title = context.get("meeting_title", "Meeting")

    logger.info(
        "Creating deck from context: user=%s meeting=%s title='%s'",
        user_id,
        meeting_id,
        meeting_title,
    )

    # Generate deck via Gamma API first (deck_url is NOT NULL in DB)
    try:
        client = get_gamma_client()
        result = await client.generate(
            input_text=prompt,
            text_mode=GammaTextMode.GENERATE,
        )
    except GammaClientError as e:
        raise DeckServiceError(f"Failed to generate deck: {e}") from e

    # Now create the deck record with all data including deck_url
    deck_id = str(uuid.uuid4())
    deck_record = {
        "id": deck_id,
        "user_id": user_id,
        "meeting_id": meeting_id,
        "title": f"Presentation for {meeting_title}",
        "status": "completed",
        "source": "meeting_context",
        "gamma_id": result.gamma_id,
        "gamma_url": result.gamma_url,
        "created_at": datetime.now(UTC).isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
    }

    try:
        db.table("decks").insert(deck_record).execute()
        logger.info("Created deck record: deck_id=%s", deck_id)
    except Exception:
        logger.exception("Failed to create deck record: deck_id=%s user_id=%s", deck_id, user_id)

    # Store in memory_semantic for future reference
    await _store_deck_memory(db, user_id, deck_id, meeting_title, result.gamma_url)

    # Post to meeting chat if requested
    if post_to_meeting:
        await _post_deck_to_meeting(meeting_id, result.gamma_url, meeting_title)

    logger.info(
        "Deck created successfully: deck_id=%s gamma_url=%s",
        deck_id,
        result.gamma_url,
    )

    return {
        "deck_id": deck_id,
        "gamma_url": result.gamma_url,
        "gamma_id": result.gamma_id,
        "status": "completed",
        "credits_used": result.credits_deducted,
    }


async def create_adhoc_deck(
    db: Client,
    user_id: str,
    prompt: str,
    title: str | None = None,
    text_mode: str = "generate",
) -> dict[str, Any]:
    """Create a presentation deck from an ad-hoc prompt.

    Generates a deck from user-provided text or prompt. Supports
    three modes: generate (from scratch), condense (summarize),
    and preserve (format existing content).

    Args:
        db: Supabase client instance.
        user_id: The user's ID.
        prompt: The text prompt or content to generate from.
        title: Optional title for the deck.
        text_mode: "generate", "condense", or "preserve".

    Returns:
        Dict with deck_id, gamma_url, gamma_id, status, credits_used.

    Raises:
        DeckServiceError: If deck generation fails.
    """
    if not settings.gamma_configured:
        raise DeckServiceError("GAMMA_API_KEY not configured")

    mode = GammaTextMode(text_mode)
    deck_title = title or "Ad-hoc Presentation"

    logger.info(
        "Creating ad-hoc deck: user=%s mode=%s title='%s'",
        user_id,
        text_mode,
        deck_title,
    )

    # Enrich prompt with ARIA self-knowledge so decks about ARIA are accurate
    aria_context = await _get_aria_knowledge_context(db)
    if aria_context:
        prompt = f"{aria_context}\n\n---\n\n{prompt}"

    # Generate deck via Gamma API first (deck_url is NOT NULL in DB)
    try:
        client = get_gamma_client()
        result = await client.generate(
            input_text=prompt,
            text_mode=mode,
        )
    except GammaClientError as e:
        raise DeckServiceError(f"Failed to generate deck: {e}") from e

    # Now create the deck record with all data including deck_url
    deck_id = str(uuid.uuid4())
    deck_record = {
        "id": deck_id,
        "user_id": user_id,
        "title": deck_title,
        "status": "completed",
        "source": "adhoc",
        "gamma_id": result.gamma_id,
        "gamma_url": result.gamma_url,
        "created_at": datetime.now(UTC).isoformat(),
        "completed_at": datetime.now(UTC).isoformat(),
    }

    try:
        db.table("decks").insert(deck_record).execute()
        logger.info("Created deck record: deck_id=%s", deck_id)
    except Exception:
        logger.exception("Failed to create deck record: deck_id=%s user_id=%s", deck_id, user_id)

    # Store in memory_semantic
    await _store_deck_memory(db, user_id, deck_id, deck_title, result.gamma_url)

    logger.info(
        "Ad-hoc deck created: deck_id=%s gamma_url=%s",
        deck_id,
        result.gamma_url,
    )

    return {
        "deck_id": deck_id,
        "gamma_url": result.gamma_url,
        "gamma_id": result.gamma_id,
        "status": "completed",
        "credits_used": result.credits_deducted,
    }


async def list_user_decks(
    db: Client,
    user_id: str,
    limit: int = 20,
    calendar_event_id: str | None = None,
) -> list[dict[str, Any]]:
    """List decks for a user, optionally filtered by calendar event.

    Args:
        db: Supabase client instance.
        user_id: The user's ID.
        limit: Maximum number of decks to return.
        calendar_event_id: Optional calendar event ID to filter by.

    Returns:
        List of deck records.
    """
    query = (
        db.table("decks")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(limit)
    )

    if calendar_event_id:
        query = query.eq("calendar_event_id", calendar_event_id)

    result = query.execute()
    return result.data or []


def _build_meeting_prompt(context: dict[str, Any]) -> str:
    """Build a Gamma prompt from meeting context.

    Args:
        context: Meeting context dictionary.

    Returns:
        Formatted prompt string for Gamma API.
    """
    parts = []

    # Meeting info
    title = context.get("meeting_title", "Meeting")
    objective = context.get("meeting_objective", "")

    parts.append(f"Create a presentation for: {title}")
    if objective:
        parts.append(f"\nMeeting Objective: {objective}")

    # Attendees
    attendees = context.get("attendees", [])
    if attendees:
        attendee_names = [a.get("name", a.get("email", "Unknown")) for a in attendees[:5]]
        parts.append(f"\nKey Attendees: {', '.join(attendee_names)}")

    # Account research
    research = context.get("account_research", "")
    if research:
        parts.append(f"\nAccount Background:\n{research[:1000]}")

    # Talking points
    talking_points = context.get("talking_points", [])
    if talking_points:
        parts.append("\nKey Talking Points:")
        for i, point in enumerate(talking_points[:5], 1):
            parts.append(f"  {i}. {point}")

    # Previous interactions
    interactions = context.get("previous_interactions", "")
    if interactions:
        parts.append(f"\nPrevious Interactions:\n{interactions[:500]}")

    # Instructions
    parts.append(
        "\n\nCreate a professional presentation with:"
        "\n- Title slide"
        "\n- Agenda overview"
        "\n- Key discussion points"
        "\n- Relevant data or insights"
        "\n- Next steps and action items"
        "\n- Closing slide"
    )

    return "\n".join(parts)


async def _store_deck_memory(
    db: Client,
    user_id: str,
    deck_id: str,
    title: str,
    gamma_url: str,
) -> None:
    """Store deck creation in memory_semantic for future reference."""
    try:
        fact = f"Created presentation '{title}' - available at {gamma_url}"
        db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": fact,
            "confidence": 1.0,
            "source": "deck_generation",
            "metadata": json.dumps({
                "deck_id": deck_id,
                "title": title,
                "url": gamma_url,
            }),
        }).execute()
    except Exception:
        logger.exception("Failed to store deck memory for user=%s", user_id)


async def _post_deck_to_meeting(
    meeting_id: str,
    gamma_url: str,
    meeting_title: str,
) -> None:
    """Post deck link to meeting chat via MeetingBaaS."""
    try:
        from src.integrations.meetingbaas.client import get_meetingbaas_client

        client = get_meetingbaas_client()
        if not client.is_configured:
            logger.warning("MeetingBaaS not configured - skipping chat post")
            return

        message = f"Prepared a presentation for this meeting: {gamma_url}"
        await client.send_chat_message(meeting_id, message)

        logger.info("Posted deck link to meeting chat: meeting_id=%s", meeting_id)

    except Exception:
        logger.exception("Failed to post deck to meeting chat")
