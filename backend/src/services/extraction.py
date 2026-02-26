"""Information extraction service for chat conversations.

Extracts facts and entities from conversation content
and stores them in semantic memory.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.llm import LLMClient
from src.core.persona import LAYER_1_CORE_IDENTITY
from src.memory.semantic import FactSource, SemanticFact, SemanticMemory

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Analyze the following conversation and extract any factual information that should be remembered.

Focus on:
- Personal preferences stated by the user
- Facts about people, companies, or projects mentioned
- Relationships between entities
- Commitments or decisions made

Return a JSON array of facts. Each fact should have:
- "subject": The entity the fact is about
- "predicate": The relationship type (e.g., "works_at", "prefers", "has_budget")
- "object": The value or related entity
- "confidence": How confident you are (0.0-1.0) based on how explicitly it was stated

If no facts can be extracted, return an empty array: []

Example response:
[{{"subject": "John", "predicate": "works_at", "object": "Acme Corp", "confidence": 0.9}}]

Conversation:
{conversation}

Extracted facts (JSON array only, no other text):"""


class ExtractionService:
    """Service for extracting information from conversations."""

    def __init__(self) -> None:
        """Initialize extraction service."""
        self._llm_client = LLMClient()
        self._semantic_memory = SemanticMemory()

    async def extract_facts(
        self,
        conversation: list[dict[str, str]],
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Extract facts from a conversation.

        Args:
            conversation: List of messages with role and content.
            user_id: The user's ID for context.

        Returns:
            List of extracted fact dicts.
        """
        conv_text = "\n".join(f"{msg['role'].upper()}: {msg['content']}" for msg in conversation)

        task_prompt = EXTRACTION_PROMPT.format(conversation=conv_text)

        try:
            # Build with ARIA identity for voice consistency
            system_prompt = LAYER_1_CORE_IDENTITY

            response = await self._llm_client.generate_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": task_prompt},
                ],
                temperature=0.3,
            )

            facts: list[dict[str, Any]] = json.loads(response.strip())

            logger.debug(
                "Extracted facts from conversation",
                extra={
                    "user_id": user_id,
                    "fact_count": len(facts),
                },
            )

            return facts

        except json.JSONDecodeError:
            logger.warning(
                "Failed to parse extraction response as JSON",
                extra={"user_id": user_id, "response": response[:100]},
            )
            return []
        except Exception:
            logger.exception(
                "Fact extraction failed",
                extra={"user_id": user_id},
            )
            return []

    async def extract_and_store(
        self,
        conversation: list[dict[str, str]],
        user_id: str,
    ) -> list[str]:
        """Extract facts and store them in semantic memory.

        Args:
            conversation: List of messages with role and content.
            user_id: The user's ID.

        Returns:
            List of created fact IDs.
        """
        facts = await self.extract_facts(conversation, user_id)

        stored_ids: list[str] = []
        now = datetime.now(UTC)

        for fact_data in facts:
            try:
                fact = SemanticFact(
                    id=str(uuid.uuid4()),
                    user_id=user_id,
                    subject=fact_data["subject"],
                    predicate=fact_data["predicate"],
                    object=fact_data["object"],
                    confidence=fact_data.get("confidence", 0.75),
                    source=FactSource.EXTRACTED,
                    valid_from=now,
                )

                fact_id = await self._semantic_memory.add_fact(fact)
                stored_ids.append(fact_id)

                logger.info(
                    "Stored extracted fact",
                    extra={
                        "fact_id": fact_id,
                        "user_id": user_id,
                        "subject": fact.subject,
                        "predicate": fact.predicate,
                    },
                )

            except Exception:
                logger.warning(
                    "Failed to store extracted fact",
                    extra={
                        "user_id": user_id,
                        "fact_data": fact_data,
                    },
                )

        return stored_ids
