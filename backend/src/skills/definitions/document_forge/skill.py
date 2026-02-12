"""DocumentForgeSkill — generates professional documents from ARIA context.

This is a Category B LLM skill (structured prompt chain), not a
capability module. It uses named templates with prompt files to
produce different document types through the same skill definition.

Assigned to: ScribeAgent
Trust level: core
"""

import logging
from pathlib import Path
from typing import Any

from src.core.llm import LLMClient
from src.skills.definitions.base import BaseSkillDefinition

logger = logging.getLogger(__name__)

# Context variable keys expected by templates
CONTEXT_LEAD_DATA = "lead_data"
CONTEXT_STAKEHOLDERS = "stakeholders"
CONTEXT_RECENT_SIGNALS = "recent_signals"
CONTEXT_BATTLE_CARD_DATA = "battle_card_data"
CONTEXT_MEETING_DETAILS = "meeting_details"

# Template name constants
TEMPLATE_ACCOUNT_PLAN = "account_plan"
TEMPLATE_MEETING_ONE_PAGER = "meeting_one_pager"
TEMPLATE_QBR_DECK = "qbr_deck"
TEMPLATE_BATTLE_CARD = "battle_card"
TEMPLATE_TERRITORY_MAP = "territory_map"

# Required context keys per template
_TEMPLATE_REQUIREMENTS: dict[str, list[str]] = {
    TEMPLATE_ACCOUNT_PLAN: [
        CONTEXT_LEAD_DATA,
        CONTEXT_STAKEHOLDERS,
        CONTEXT_RECENT_SIGNALS,
    ],
    TEMPLATE_MEETING_ONE_PAGER: [
        CONTEXT_MEETING_DETAILS,
        CONTEXT_LEAD_DATA,
        CONTEXT_STAKEHOLDERS,
        CONTEXT_RECENT_SIGNALS,
    ],
    TEMPLATE_QBR_DECK: [
        CONTEXT_LEAD_DATA,
        CONTEXT_STAKEHOLDERS,
        CONTEXT_RECENT_SIGNALS,
    ],
    TEMPLATE_BATTLE_CARD: [
        CONTEXT_BATTLE_CARD_DATA,
        CONTEXT_LEAD_DATA,
        CONTEXT_RECENT_SIGNALS,
    ],
    TEMPLATE_TERRITORY_MAP: [
        CONTEXT_LEAD_DATA,
        CONTEXT_STAKEHOLDERS,
        CONTEXT_RECENT_SIGNALS,
    ],
}


class DocumentForgeSkill(BaseSkillDefinition):
    """Generate professional documents from ARIA's intelligence context.

    Wraps the ``document-forge`` skill definition and provides
    template-aware document generation with context validation.

    Args:
        llm_client: LLM client for prompt execution.
        definitions_dir: Override for the skill definitions base directory.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        definitions_dir: Path | None = None,
    ) -> None:
        super().__init__(
            "document_forge",
            llm_client,
            definitions_dir=definitions_dir,
        )

    def validate_template_context(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> list[str]:
        """Check that all required context keys are present for a template.

        Args:
            template_name: The template to validate against.
            context: The context dict to check.

        Returns:
            List of missing key names (empty if all present).
        """
        required = _TEMPLATE_REQUIREMENTS.get(template_name, [])
        return [key for key in required if key not in context]

    async def generate_document(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a document using the specified template.

        This is the primary entry point for document generation. It
        validates the context, delegates to :meth:`run_template`, and
        returns the structured document output.

        Args:
            template_name: One of the defined template names.
            context: Context dict containing the variables referenced
                in the template prompt file.

        Returns:
            Parsed JSON output with ``title``, ``sections``, and
            ``metadata`` keys.

        Raises:
            ValueError: If required context keys are missing or the
                template is unknown.
        """
        missing = self.validate_template_context(template_name, context)
        if missing:
            raise ValueError(f"Template '{template_name}' is missing required context: {missing}")

        logger.info(
            "Generating document",
            extra={
                "skill": self._skill_name,
                "template": template_name,
                "context_keys": list(context.keys()),
            },
        )

        return await self.run_template(template_name, context)
