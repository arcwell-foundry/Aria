"""TerritoryPlannerSkill — analyzes geographic distribution for territory optimization.

This is a Category B LLM skill (structured prompt chain). It uses named
templates with prompt files to produce territory analysis, white-space
identification, workload balancing, and travel optimization.

Output from the territory_map template is compatible with the
insight-visualizer treemap/heatmap rendering.

Assigned to: StrategistAgent, AnalystAgent
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
CONTEXT_TERRITORY_CONFIG = "territory_config"
CONTEXT_VISIT_HISTORY = "visit_history"

# Template name constants
TEMPLATE_TERRITORY_MAP = "territory_map"
TEMPLATE_WHITE_SPACE = "white_space_analysis"
TEMPLATE_WORKLOAD_BALANCE = "workload_balance"
TEMPLATE_TRAVEL_OPTIMIZATION = "travel_optimization"

# Required context keys per template
_TEMPLATE_REQUIREMENTS: dict[str, list[str]] = {
    TEMPLATE_TERRITORY_MAP: [
        CONTEXT_LEAD_DATA,
    ],
    TEMPLATE_WHITE_SPACE: [
        CONTEXT_LEAD_DATA,
    ],
    TEMPLATE_WORKLOAD_BALANCE: [
        CONTEXT_LEAD_DATA,
    ],
    TEMPLATE_TRAVEL_OPTIMIZATION: [
        CONTEXT_LEAD_DATA,
        CONTEXT_VISIT_HISTORY,
    ],
}


class TerritoryPlannerSkill(BaseSkillDefinition):
    """Analyze lead geographic distribution and produce territory intelligence.

    Wraps the ``territory-planner`` skill definition and provides
    template-aware territory analysis with context validation.

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
            "territory_planner",
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

    async def analyze_territory(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Run territory analysis using the specified template.

        This is the primary entry point for territory planning. It
        validates the context, delegates to :meth:`run_template`, and
        returns the structured analysis output.

        Args:
            template_name: One of the defined template names.
            context: Context dict containing the variables referenced
                in the template prompt file.

        Returns:
            Parsed JSON output with ``analysis_type``, ``territories``,
            ``recommendations``, and ``metadata`` keys.

        Raises:
            ValueError: If required context keys are missing or the
                template is unknown.
        """
        missing = self.validate_template_context(template_name, context)
        if missing:
            raise ValueError(f"Template '{template_name}' is missing required context: {missing}")

        logger.info(
            "Running territory analysis",
            extra={
                "skill": self._skill_name,
                "template": template_name,
                "context_keys": list(context.keys()),
            },
        )

        return await self.run_template(template_name, context)
