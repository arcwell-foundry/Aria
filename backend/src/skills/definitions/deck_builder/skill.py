"""DeckBuilderSkill — generates python-pptx compatible slide specifications.

This is a Category B LLM skill (structured prompt chain). It uses named
templates with prompt files to produce presentation slide specifications
as JSON that a backend service converts to .pptx files.

Data is injected from battle_cards, lead_memories, and health_score_history
to produce data-driven presentations.

Assigned to: ScribeAgent, StrategistAgent
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
CONTEXT_BATTLE_CARDS = "battle_card_data"
CONTEXT_HEALTH_HISTORY = "health_score_history"
CONTEXT_MEETING_CONTEXT = "meeting_context"
CONTEXT_PIPELINE_DATA = "pipeline_data"
CONTEXT_FORECAST_DATA = "forecast_data"
CONTEXT_AUDIENCE = "audience"

# Template name constants
TEMPLATE_PITCH_DECK = "pitch_deck"
TEMPLATE_LEAVE_BEHIND = "leave_behind"
TEMPLATE_QBR_PRESENTATION = "qbr_presentation"

# Required context keys per template
_TEMPLATE_REQUIREMENTS: dict[str, list[str]] = {
    TEMPLATE_PITCH_DECK: [
        CONTEXT_LEAD_DATA,
        CONTEXT_BATTLE_CARDS,
    ],
    TEMPLATE_LEAVE_BEHIND: [
        CONTEXT_LEAD_DATA,
        CONTEXT_MEETING_CONTEXT,
    ],
    TEMPLATE_QBR_PRESENTATION: [
        CONTEXT_PIPELINE_DATA,
        CONTEXT_HEALTH_HISTORY,
        CONTEXT_FORECAST_DATA,
    ],
}


class DeckBuilderSkill(BaseSkillDefinition):
    """Generate python-pptx compatible slide specifications.

    Wraps the ``deck-builder`` skill definition and provides
    template-aware deck generation with context validation.

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
            "deck_builder",
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

    async def build_deck(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a slide deck specification using the specified template.

        This is the primary entry point for deck generation. It validates
        the context, delegates to :meth:`run_template`, and returns the
        structured slide specification.

        Args:
            template_name: One of the defined template names.
            context: Context dict containing the variables referenced
                in the template prompt file.

        Returns:
            Parsed JSON output with ``deck_type``, ``slides``, and
            ``metadata`` keys.

        Raises:
            ValueError: If required context keys are missing or the
                template is unknown.
        """
        missing = self.validate_template_context(template_name, context)
        if missing:
            raise ValueError(f"Template '{template_name}' is missing required context: {missing}")

        logger.info(
            "Building presentation deck",
            extra={
                "skill": self._skill_name,
                "template": template_name,
                "context_keys": list(context.keys()),
            },
        )

        return await self.run_template(template_name, context)
