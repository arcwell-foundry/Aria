"""ComplianceGuardianSkill — hybrid compliance detection using code + LLM.

This is a hybrid skill: RegEx-based pattern detection runs first (code),
then the LLM performs contextual analysis on flagged segments. The code
component lives in ``src/agents/capabilities/compliance.py`` and provides
``auto_redact()`` and ``check_sunshine_act()`` functions that can be
called independently of the LLM skill.

Assigned to: ScribeAgent, OperatorAgent, AnalystAgent
Trust level: core
"""

import logging
from pathlib import Path
from typing import Any

from src.core.llm import LLMClient
from src.skills.definitions.base import BaseSkillDefinition

logger = logging.getLogger(__name__)

# Context variable keys expected by templates
CONTEXT_TEXT_CONTENT = "text_content"
CONTEXT_INTERACTION_DATA = "interaction_data"

# Template name constants
TEMPLATE_COMPLIANCE_REVIEW = "compliance_review"
TEMPLATE_REDACTION_REPORT = "redaction_report"

# Required context keys per template
_TEMPLATE_REQUIREMENTS: dict[str, list[str]] = {
    TEMPLATE_COMPLIANCE_REVIEW: [
        CONTEXT_TEXT_CONTENT,
    ],
    TEMPLATE_REDACTION_REPORT: [
        CONTEXT_TEXT_CONTENT,
    ],
}


class ComplianceGuardianSkill(BaseSkillDefinition):
    """Detect PHI/PII and flag Sunshine Act reporting requirements.

    This skill combines pattern-based detection (via the compliance
    capability module) with LLM contextual analysis for comprehensive
    compliance scanning.

    The ``pre_scan`` method runs regex patterns before the LLM call to
    provide structured hints that improve LLM accuracy.

    Args:
        llm_client: LLM client for contextual analysis.
        definitions_dir: Override for the skill definitions base directory.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        definitions_dir: Path | None = None,
    ) -> None:
        super().__init__(
            "compliance_guardian",
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

    async def review_compliance(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Run compliance analysis using pre-scan + LLM.

        Performs regex pre-scan via the compliance capability module,
        injects findings into the context, then delegates to the LLM
        for contextual analysis.

        Args:
            template_name: One of the defined template names.
            context: Context dict containing at least ``text_content``.

        Returns:
            Parsed JSON output with ``review_type``, ``findings``,
            ``risk_level``, and ``metadata`` keys.

        Raises:
            ValueError: If required context keys are missing.
        """
        missing = self.validate_template_context(template_name, context)
        if missing:
            raise ValueError(f"Template '{template_name}' is missing required context: {missing}")

        # Run code-based pre-scan and inject results into context
        try:
            from src.agents.capabilities.compliance import ComplianceScanner

            scanner = ComplianceScanner()
            pre_scan = scanner.scan_text(context.get("text_content", ""))
            context["pre_scan_findings"] = pre_scan.to_context_string()
        except ImportError:
            logger.warning("Compliance capability module not available, skipping pre-scan")
            context["pre_scan_findings"] = "Pre-scan unavailable."

        logger.info(
            "Running compliance review",
            extra={
                "skill": self._skill_name,
                "template": template_name,
                "context_keys": list(context.keys()),
            },
        )

        return await self.run_template(template_name, context)
