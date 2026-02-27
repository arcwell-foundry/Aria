"""Base skill definition for ARIA.

A skill definition is a YAML-backed specification that tells the LLM
*what* a skill does, *how* to format its output, and *who* may invoke it.

Directory layout for a skill called ``meeting_summarizer``::

    src/skills/definitions/meeting_summarizer/
        skill.yaml          # Declarative definition (loaded by this class)

YAML schema::

    name: meeting_summarizer
    description: Summarise a meeting transcript into action items and key decisions.
    agent_assignment:
      - scribe
      - analyst
    system_prompt: |
      You are an expert meeting summariser ...
    output_schema:          # JSON Schema for structured output validation
      type: object
      required: [summary, action_items]
      properties:
        summary:
          type: string
        action_items:
          type: array
          items:
            type: object
    input_requirements:
      - transcript
    trust_level: core       # core | verified | community | user
    estimated_seconds: 15

Usage::

    class MeetingSummarizerSkill(BaseSkillDefinition):
        def __init__(self, llm_client):
            super().__init__("meeting_summarizer", llm_client)
"""

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import yaml
from pydantic import BaseModel, Field

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.security.trust_levels import SkillTrustLevel

logger = logging.getLogger(__name__)

# Root directory for built-in skill definitions
_DEFINITIONS_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Pydantic model for the parsed YAML
# ---------------------------------------------------------------------------


class TemplateDefinition(BaseModel):
    """A named prompt template within a skill definition."""

    description: str = Field(..., description="Human-readable template description")
    prompt_file: str = Field(
        default="",
        description="Filename in prompts/ directory (auto-derived from key if empty)",
    )


class SkillDefinition(BaseModel):
    """Parsed, validated representation of a ``skill.yaml`` file.

    All fields correspond to top-level keys in the YAML document.
    """

    name: str = Field(..., description="Unique skill identifier")
    description: str = Field(..., description="One-line human description")
    agent_assignment: list[str] = Field(
        default_factory=list,
        description="Agent types that may use this skill",
    )
    system_prompt: str = Field(..., description="System prompt sent to the LLM")
    output_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for validating structured output",
    )
    input_requirements: list[str] = Field(
        default_factory=list,
        description="Required keys in the input context dict",
    )
    trust_level: str = Field(
        default="community",
        description="Skill trust level (core, verified, community, user)",
    )
    estimated_seconds: int = Field(
        default=30,
        description="Expected wall-clock execution time in seconds",
    )
    templates: dict[str, TemplateDefinition] = Field(
        default_factory=dict,
        description="Named prompt templates for multi-template skills",
    )


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class BaseSkillDefinition:
    """Load a YAML skill definition and execute it through the LLM.

    Parameters:
        skill_name: Directory name under ``src/skills/definitions/``.
        llm_client: :class:`LLMClient` used for prompt execution.
        definitions_dir: Override the base directory (useful in tests).
    """

    def __init__(
        self,
        skill_name: str,
        llm_client: LLMClient,
        *,
        definitions_dir: Path | None = None,
    ) -> None:
        self._skill_name = skill_name
        self._llm = llm_client
        self._base_dir = definitions_dir or _DEFINITIONS_DIR

        self._definition: SkillDefinition = self._load_definition()
        self._prompts: dict[str, str] = self._load_prompts()

    # -- Properties ------------------------------------------------------------

    @property
    def definition(self) -> SkillDefinition:
        """Return the parsed YAML definition."""
        return self._definition

    @property
    def prompts(self) -> dict[str, str]:
        """Return loaded prompt templates keyed by template name."""
        return dict(self._prompts)

    @property
    def available_templates(self) -> list[str]:
        """Return names of available templates defined in the skill YAML."""
        return list(self._definition.templates.keys())

    @property
    def trust_level(self) -> SkillTrustLevel:
        """Map the YAML trust_level string to the enum."""
        mapping: dict[str, SkillTrustLevel] = {
            "core": SkillTrustLevel.CORE,
            "verified": SkillTrustLevel.VERIFIED,
            "community": SkillTrustLevel.COMMUNITY,
            "user": SkillTrustLevel.USER,
        }
        return mapping.get(self._definition.trust_level, SkillTrustLevel.COMMUNITY)

    # -- YAML loading ----------------------------------------------------------

    def _load_definition(self) -> SkillDefinition:
        """Load and validate ``skill.yaml`` from the skill directory.

        Raises:
            FileNotFoundError: If the YAML file does not exist.
            yaml.YAMLError: If the file is not valid YAML.
            pydantic.ValidationError: If the YAML does not match the schema.
        """
        yaml_path = self._base_dir / self._skill_name / "skill.yaml"

        if not yaml_path.exists():
            raise FileNotFoundError(f"Skill definition not found: {yaml_path}")

        with open(yaml_path) as fh:
            raw: dict[str, Any] = yaml.safe_load(fh)

        logger.info(
            "Loaded skill definition",
            extra={"skill": self._skill_name, "path": str(yaml_path)},
        )
        return SkillDefinition(**raw)

    def _load_prompts(self) -> dict[str, str]:
        """Load prompt template files from the ``prompts/`` subdirectory.

        Each ``.md`` file is keyed by its stem (e.g. ``account_plan.md``
        → ``"account_plan"``). If the skill defines templates in its YAML,
        only files referenced by those templates are loaded.

        Returns:
            Mapping of template name → prompt text.
        """
        prompts_dir = self._base_dir / self._skill_name / "prompts"
        if not prompts_dir.is_dir():
            return {}

        loaded: dict[str, str] = {}
        for prompt_file in prompts_dir.glob("*.md"):
            loaded[prompt_file.stem] = prompt_file.read_text(encoding="utf-8")

        if loaded:
            logger.info(
                "Loaded prompt templates",
                extra={
                    "skill": self._skill_name,
                    "templates": list(loaded.keys()),
                },
            )

        return loaded

    # -- Prompt building -------------------------------------------------------

    def build_prompt(self, context: dict[str, Any]) -> str:
        """Build a complete user-message prompt from the definition and *context*.

        The system prompt comes from the YAML; the user message is composed
        from the supplied context values.  Subclasses may override this to
        inject additional formatting.

        Args:
            context: Runtime context dict.  Must contain all keys listed in
                ``input_requirements``.

        Returns:
            Formatted user-message string.

        Raises:
            ValueError: If a required input key is missing.
        """
        missing = [key for key in self._definition.input_requirements if key not in context]
        if missing:
            raise ValueError(f"Skill '{self._skill_name}' missing required inputs: {missing}")

        # Build a structured user message from context
        parts: list[str] = [f"# Task: {self._definition.description}"]
        for key, value in context.items():
            parts.append(f"\n## {key}\n{value}")

        if self._definition.output_schema:
            parts.append(
                "\n## Output format\n"
                "Respond with valid JSON matching this schema:\n"
                f"```json\n{json.dumps(self._definition.output_schema, indent=2)}\n```"
            )

        return "\n".join(parts)

    def build_template_prompt(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> str:
        """Build a user-message prompt from a named template and *context*.

        Loads the prompt file associated with the template, substitutes
        context variables using ``str.format_map``, and appends the
        output schema instruction.

        Args:
            template_name: Key from the ``templates`` section of skill.yaml.
            context: Runtime context dict with variables referenced in
                the prompt template (e.g. ``{lead_data}``, ``{stakeholders}``).

        Returns:
            Formatted user-message string.

        Raises:
            ValueError: If the template name is unknown or its prompt file
                is not loaded.
        """
        templates = self._definition.templates
        if template_name not in templates:
            available = list(templates.keys())
            raise ValueError(
                f"Unknown template '{template_name}' for skill "
                f"'{self._skill_name}'. Available: {available}"
            )

        template_def = templates[template_name]
        prompt_key = template_def.prompt_file or template_name

        if prompt_key not in self._prompts:
            raise ValueError(
                f"Prompt file for template '{template_name}' not found. "
                f"Expected '{prompt_key}.md' in prompts/ directory."
            )

        raw_prompt = self._prompts[prompt_key]

        # Substitute context variables — use format_map so missing keys
        # raise KeyError rather than silently passing through.
        try:
            formatted = raw_prompt.format_map(context)
        except KeyError as exc:
            raise ValueError(
                f"Template '{template_name}' requires context variable "
                f"{exc} which was not provided."
            ) from exc

        parts: list[str] = [formatted]

        if self._definition.output_schema:
            parts.append(
                "\n## Output format\n"
                "Respond with valid JSON matching this schema:\n"
                f"```json\n{json.dumps(self._definition.output_schema, indent=2)}\n```"
            )

        return "\n".join(parts)

    # -- Output parsing & validation -------------------------------------------

    def parse_output(self, raw: str) -> dict[str, Any]:
        """Extract JSON from the raw LLM response.

        Handles responses that wrap JSON in markdown code-fences
        (````json ... ````).

        Args:
            raw: Raw LLM text output.

        Returns:
            Parsed dict.

        Raises:
            json.JSONDecodeError: If no valid JSON can be extracted.
        """
        text = raw.strip()

        # Strip markdown code fences
        if text.startswith("```"):
            # Remove opening fence (possibly with language tag)
            first_newline = text.index("\n")
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3].rstrip()

        return json.loads(text)

    def validate_output(self, parsed: dict[str, Any]) -> bool:
        """Validate *parsed* output against the YAML ``output_schema``.

        Args:
            parsed: Previously parsed JSON dict.

        Returns:
            ``True`` if valid (or if no schema is defined), ``False`` otherwise.
        """
        schema = self._definition.output_schema
        if not schema:
            return True

        try:
            jsonschema.validate(instance=parsed, schema=schema)
            return True
        except jsonschema.ValidationError as exc:
            logger.warning(
                "Skill output validation failed",
                extra={
                    "skill": self._skill_name,
                    "error": str(exc.message),
                },
            )
            return False

    # -- LLM execution ---------------------------------------------------------

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Build the prompt, call the LLM, parse and validate the output.

        This is a convenience method that chains :meth:`build_prompt`,
        the LLM call, :meth:`parse_output`, and :meth:`validate_output`.

        Args:
            context: Input context dict.

        Returns:
            Parsed and validated output dict.

        Raises:
            ValueError: If output fails validation.
        """
        user_prompt = self.build_prompt(context)

        raw_response = await self._llm.generate_response(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=self._definition.system_prompt,
            temperature=0.4,
            task=TaskType.SKILL_EXECUTE,
            agent_id="skill_base",
        )

        parsed = self.parse_output(raw_response)

        if not self.validate_output(parsed):
            raise ValueError(f"Skill '{self._skill_name}' produced invalid output")

        return parsed

    async def run_template(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a template prompt, call the LLM, parse and validate output.

        Equivalent to :meth:`run` but uses a named template instead of
        the generic ``build_prompt`` approach.

        Args:
            template_name: Key from the ``templates`` section.
            context: Input context dict with template variables.

        Returns:
            Parsed and validated output dict.

        Raises:
            ValueError: If the template is unknown or output fails validation.
        """
        user_prompt = self.build_template_prompt(template_name, context)

        raw_response = await self._llm.generate_response(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=self._definition.system_prompt,
            temperature=0.4,
            task=TaskType.SKILL_EXECUTE,
            agent_id="skill_base",
        )

        parsed = self.parse_output(raw_response)

        if not self.validate_output(parsed):
            raise ValueError(
                f"Skill '{self._skill_name}' template '{template_name}' produced invalid output"
            )

        return parsed
