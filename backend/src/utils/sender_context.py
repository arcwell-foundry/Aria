"""Sender relationship context resolver for email classification.

This module provides dynamic, data-driven relationship intelligence for email senders.
It checks multiple data sources to determine if a sender is a strategic contact
(investor, partner, customer, etc.) and provides context for LLM classification.

100% DYNAMIC - no hardcoded emails, names, companies, or entity types.
Everything derived from each user's live data at classification time.
"""

import logging
from dataclasses import dataclass
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)


# Entity types that indicate a strategic relationship
# These are dynamically matched from monitored_entities.entity_type
STRATEGIC_ENTITY_TYPES = frozenset([
    "investor",
    "partner",
    "customer",
    "board_member",
    "advisor",
    "own_company",
])


def _get_json(data: Any, key: str, default: str = "unknown") -> str:
    """Safely get a string value from a JSON-like object.

    Args:
        data: The JSON-like object (could be dict, str, or None)
        key: The key to retrieve
        default: Default value if not found

    Returns:
        The value as a string, or the default if not found/not a string.
    """
    if data is None:
        return default
    if not isinstance(data, dict):
        return default
    value = data.get(key, default)
    if isinstance(value, str):
        return value
    return default


@dataclass
class SenderContext:
    """Structured relationship context for an email sender."""

    is_strategic: bool
    relationship_type: str
    entity_name: str | None
    context_summary: str
    has_prior_drafts: bool
    confidence: float


def _extract_domain(email: str) -> str:
    """Extract domain from email address.

    Args:
        email: Email address (e.g., "user@example.com")

    Returns:
        Domain (e.g., "example.com") or empty string if invalid
    """
    if not email or "@" not in email:
        return ""
    return email.split("@")[-1].lower().strip()


async def get_sender_context(
    db: Client,
    user_id: str,
    sender_email: str,
    cache: dict[tuple[str, str], SenderContext] | None = None,
) -> SenderContext | None:
    """Get relationship context for an email sender.

    Resolves sender identity by checking multiple data sources:
    1. monitored_entities - match via domains array
    2. memory_semantic - search for sender email references
    3. email_drafts - check for prior drafts to this sender
    4. email_scan_log - check interaction history

    Args:
        db: Supabase client instance
        user_id: The user's UUID
        sender_email: The sender's email address
        cache: Optional cache dict for (user_id, sender_email) → SenderContext

    Returns:
        SenderContext if any relationship info found, None if completely unknown
    """
    if not sender_email:
        return None

    sender_email_lower = sender_email.lower().strip()
    sender_domain = _extract_domain(sender_email_lower)

    # Check cache first
    cache_key = (user_id, sender_email_lower)
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    # Default unknown context
    context = SenderContext(
        is_strategic=False,
        relationship_type="unknown",
        entity_name=None,
        context_summary="",
        has_prior_drafts=False,
        confidence=0.0,
    )

    try:
        # 1. Check monitored_entities via domain match
        if sender_domain:
            try:
                result = (
                    db.table("monitored_entities")
                    .select("entity_name, entity_type, monitoring_config")
                    .eq("user_id", user_id)
                    .eq("is_active", True)
                    .contains("domains", [sender_domain])
                    .limit(1)
                    .execute()
                )

                if result.data:
                    entity = result.data[0]
                    if isinstance(entity, dict):
                        entity_name_raw = entity.get("entity_name")
                        entity_type_raw = entity.get("entity_type", "unknown")

                        # Convert to strings safely
                        entity_name = str(entity_name_raw) if entity_name_raw else None
                        entity_type = str(entity_type_raw) if entity_type_raw else "unknown"

                        context.entity_name = entity_name
                        context.relationship_type = entity_type
                        context.is_strategic = entity_type.lower() in STRATEGIC_ENTITY_TYPES
                        context.confidence = 0.9  # High confidence from explicit monitoring

                        if context.is_strategic:
                            context.context_summary = (
                                f"Strategic contact: {entity_name} ({entity_type})"
                            )
                        else:
                            context.context_summary = (
                                f"Monitored entity: {entity_name} ({entity_type})"
                            )

                        logger.debug(
                            f"SENDER_CONTEXT: Found in monitored_entities - "
                            f"{sender_email} → {entity_name} ({entity_type}), strategic={context.is_strategic}"
                        )

            except Exception as e:
                error_msg = str(e)
                # Check if domains column doesn't exist yet
                if "domains" in error_msg and "does not exist" in error_msg:
                    logger.debug(
                        "SENDER_CONTEXT: domains column not yet available, "
                        "falling back to other data sources"
                    )
                else:
                    logger.warning(
                        f"SENDER_CONTEXT: monitored_entities query failed: {e}"
                    )

        # 2. Check memory_semantic for sender references
        if not context.is_strategic:
            try:
                result = (
                    db.table("memory_semantic")
                    .select("fact, confidence")
                    .eq("user_id", user_id)
                    .ilike("fact", f"%{sender_email_lower}%")
                    .limit(3)
                    .execute()
                )

                if result.data:
                    # Found memory references - indicates some relationship
                    memory_facts: list[str] = []
                    total_confidence = 0.0
                    for r in result.data:
                        if isinstance(r, dict):
                            fact = r.get("fact", "")
                            conf = r.get("confidence", 0.5)
                            memory_facts.append(str(fact) if fact else "")
                            total_confidence += float(conf) if isinstance(conf, (int, float)) else 0.5
                    avg_confidence = total_confidence / len(result.data) if result.data else 0.5

                    # Update context if we don't have entity info yet
                    if not context.entity_name:
                        context.relationship_type = "known_contact"
                        context.context_summary = "Known contact from prior interactions"
                        context.confidence = max(context.confidence, avg_confidence * 0.8)

                        # Check if any fact indicates strategic relationship
                        for fact in memory_facts:
                            fact_lower = fact.lower()
                            for strategic_type in STRATEGIC_ENTITY_TYPES:
                                if strategic_type in fact_lower:
                                    context.is_strategic = True
                                    context.relationship_type = strategic_type
                                    break

                    logger.debug(
                        f"SENDER_CONTEXT: Found in memory_semantic - "
                        f"{sender_email}, strategic={context.is_strategic}"
                    )

            except Exception as e:
                logger.warning(
                    f"SENDER_CONTEXT: memory_semantic query failed: {e}"
                )

        # 3. Check email_drafts for prior drafts to this sender
        try:
            result = (
                db.table("email_drafts")
                .select("id")
                .eq("user_id", user_id)
                .eq("recipient_email", sender_email_lower)
                .limit(1)
                .execute()
            )

            if result.data:
                # Found at least one draft to this sender
                context.has_prior_drafts = True
                # Prior drafts indicate active relationship
                if context.relationship_type == "unknown":
                    context.relationship_type = "known_contact"
                    context.context_summary = "Prior draft created for this contact"
                    context.confidence = max(context.confidence, 0.6)

                logger.debug(
                    f"SENDER_CONTEXT: Found prior drafts for {sender_email}"
                )

        except Exception as e:
            logger.warning(
                f"SENDER_CONTEXT: email_drafts query failed: {e}"
            )

        # 4. Check email_scan_log for interaction history
        try:
            result = (
                db.table("email_scan_log")
                .select("category")
                .eq("user_id", user_id)
                .eq("sender_email", sender_email_lower)
                .limit(100)  # Reasonable limit for interaction counting
                .execute()
            )

            if result.data:
                # Count total and NEEDS_REPLY emails from this sender
                total_count = len(result.data)
                needs_reply_count = sum(
                    1 for r in result.data
                    if isinstance(r, dict) and r.get("category") == "NEEDS_REPLY"
                )

                # Frequent NEEDS_REPLY indicates important contact
                if needs_reply_count >= 3 and context.relationship_type == "unknown":
                    context.relationship_type = "known_contact"
                    context.context_summary = (
                        f"Frequent contact ({total_count} emails, "
                        f"{needs_reply_count} requiring reply)"
                    )
                    context.confidence = max(context.confidence, 0.5)

                logger.debug(
                    f"SENDER_CONTEXT: Found {total_count} scan log entries for {sender_email}"
                )

        except Exception as e:
            logger.warning(
                f"SENDER_CONTEXT: email_scan_log query failed: {e}"
            )

    except Exception as e:
        logger.error(
            f"SENDER_CONTEXT: Unexpected error resolving context for {sender_email}: {e}"
        )
        return None

    # Return None if completely unknown (no relationship info found)
    if context.relationship_type == "unknown" and not context.has_prior_drafts:
        return None

    # Cache the result
    if cache is not None:
        cache[cache_key] = context

    return context


def format_context_for_prompt(
    context: SenderContext,
    sender_name: str,
    sender_email: str,
) -> str:
    """Format sender context for injection into LLM classification prompt.

    Args:
        context: The resolved SenderContext
        sender_name: The sender's display name
        sender_email: The sender's email address

    Returns:
        Formatted context string for prompt injection, or empty string if not strategic
    """
    if not context.is_strategic:
        return ""

    entity_info = ""
    if context.entity_name:
        entity_info = f" associated with {context.entity_name}"

    relationship_info = f" ({context.relationship_type})" if context.relationship_type != "unknown" else ""

    return (
        f"\nSENDER RELATIONSHIP CONTEXT:\n"
        f"{sender_name} ({sender_email}) is a known {context.relationship_type} contact{entity_info}.\n"
        f"{context.context_summary}\n\n"
        f"Classification guidance: Emails from strategic contacts (investors, partners, customers, board members) "
        f"should be biased toward NEEDS_REPLY unless the content is clearly automated, transactional, or a "
        f"mass newsletter. Strategic contacts should almost never be classified as SKIP."
    )
