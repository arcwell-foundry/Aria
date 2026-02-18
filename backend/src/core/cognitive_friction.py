"""Cognitive Friction Engine — ARIA's pushback mechanism.

Evaluates user requests before execution and decides whether to comply,
flag, challenge, or refuse.  This is the engine only; wiring into
chat.py / OODA is out of scope.

Decision levels:
    comply     — proceed without comment
    flag       — proceed but surface a note to the user
    challenge  — pause and push back; wait for confirmation
    refuse     — decline to execute (compliance / ethical violations)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.llm import LLMClient, LLMResponse
    from src.core.persona import PersonaBuilder
    from src.core.task_characteristics import TaskCharacteristics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRICTION_COMPLY = "comply"
FRICTION_FLAG = "flag"
FRICTION_CHALLENGE = "challenge"
FRICTION_REFUSE = "refuse"

_VALID_LEVELS = {FRICTION_COMPLY, FRICTION_FLAG, FRICTION_CHALLENGE, FRICTION_REFUSE}

FAST_PATH_THRESHOLD = 0.15

FRICTION_EVALUATION_PROMPT = """\
## Cognitive Friction Evaluation

You are evaluating a user request on behalf of ARIA to decide whether to \
proceed, flag a concern, push back, or refuse.

Evaluate against these four criteria:

1. **Goal conflict** — Does the request contradict the user's own stated \
goals, priorities, or strategy?
2. **Context conflict** — Does it conflict with known stakeholder \
preferences, prior commitments, or relationship history?
3. **Risk-reversibility** — Is the action hard to undo? Could it have \
lasting negative consequences?
4. **Colleague test** — Would a sharp, trusted human colleague speak up?

Decision levels:
- **comply** — No specific, articulable concern. This is the default.
- **flag** — Minor concern worth noting, but proceed.
- **challenge** — Significant concern. Push back and wait for confirmation.
- **refuse** — Compliance or ethical violation. Do not execute.

Rules:
- Default to "comply" unless there is a specific, articulable reason not to.
- Never challenge on vague feelings — cite specific context.
- "refuse" is ONLY for compliance or ethical violations.
- Pushback language must be direct and specific: "I'd push back — the CFO \
explicitly asked for ROI numbers" not "you might want to reconsider".

Respond with ONLY a JSON object (no markdown fences):
{
    "level": "comply" | "flag" | "challenge" | "refuse",
    "reasoning": "Internal reasoning for the audit trail",
    "user_message": "Message to show the user (null for comply)"
}
"""

_FALLBACK_SYSTEM_PROMPT = """\
You are ARIA, an autonomous AI colleague for Life Sciences commercial teams. \
You are evaluating whether to push back on a user request.

""" + FRICTION_EVALUATION_PROMPT


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class FrictionDecision:
    """Result of a cognitive friction evaluation."""

    level: str
    """One of 'comply', 'flag', 'challenge', 'refuse'."""

    reasoning: str
    """Internal reasoning for trace / audit."""

    user_message: str | None
    """ARIA's pushback message shown to the user.  ``None`` for comply."""

    proceed_if_confirmed: bool
    """``True`` for comply / flag / challenge; ``False`` for refuse."""


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class CognitiveFrictionEngine:
    """Evaluates user requests and decides whether ARIA should push back.

    Constructor accepts optional *llm_client* and *persona_builder*.
    When omitted, singletons are lazily initialised on first use.
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        persona_builder: PersonaBuilder | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._persona_builder = persona_builder

    # -- public API ----------------------------------------------------------

    async def evaluate(
        self,
        user_id: str,
        user_request: str,
        task_characteristics: TaskCharacteristics | None = None,
        user_context: dict[str, Any] | None = None,
    ) -> FrictionDecision:
        """Evaluate a user request and return a friction decision.

        Args:
            user_id: Requesting user.
            user_request: The raw user request text.
            task_characteristics: Risk profile. Defaults to neutral 0.5s.
            user_context: Optional dict of goals, stakeholder info, history,
                compliance notes, etc.

        Returns:
            A ``FrictionDecision`` indicating comply / flag / challenge / refuse.
        """
        try:
            return await self._evaluate_inner(
                user_id, user_request, task_characteristics, user_context,
            )
        except Exception:
            logger.warning(
                "Cognitive friction evaluation failed — failing open (comply)",
                exc_info=True,
            )
            return FrictionDecision(
                level=FRICTION_COMPLY,
                reasoning="Friction evaluation error — fail-open",
                user_message=None,
                proceed_if_confirmed=True,
            )

    # -- private implementation ----------------------------------------------

    async def _evaluate_inner(
        self,
        user_id: str,
        user_request: str,
        task_characteristics: TaskCharacteristics | None,
        user_context: dict[str, Any] | None,
    ) -> FrictionDecision:
        # 1. Default nils
        if task_characteristics is None:
            from src.core.task_characteristics import TaskCharacteristics as TC
            task_characteristics = TC()
        if user_context is None:
            user_context = {}

        risk = task_characteristics.risk_score

        # 2. Fast-path COMPLY for low-risk requests
        if risk < FAST_PATH_THRESHOLD:
            return FrictionDecision(
                level=FRICTION_COMPLY,
                reasoning=f"Fast-path: risk_score {risk:.3f} < {FAST_PATH_THRESHOLD}",
                user_message=None,
                proceed_if_confirmed=True,
            )

        # 3. Build system prompt
        system_prompt = await self._build_system_prompt(user_id)

        # 4. Build user prompt
        user_prompt = self._build_user_prompt(
            user_request, task_characteristics, user_context,
        )

        # 5. Call LLM
        messages = [{"role": "user", "content": user_prompt}]
        llm_client = self._ensure_llm_client()

        if risk >= 0.4:
            response: LLMResponse = await llm_client.generate_response_with_thinking(
                messages=messages,
                system_prompt=system_prompt,
                thinking_effort="routine",
            )
            raw_text = response.text
        else:
            raw_text = await llm_client.generate_response(
                messages=messages,
                system_prompt=system_prompt,
                temperature=0.2,
            )

        # 6. Parse & validate
        return self._parse_llm_response(raw_text)

    async def _build_system_prompt(self, user_id: str) -> str:
        """Build persona-aware system prompt with friction instructions."""
        try:
            from src.core.persona import PersonaRequest as PR

            builder = self._ensure_persona_builder()
            ctx = await builder.build(
                PR(
                    user_id=user_id,
                    agent_name="cognitive_friction",
                    agent_role_description="Evaluates whether ARIA should push back on a user request",
                    task_description="Friction evaluation",
                    output_format="json",
                ),
            )
            return ctx.to_system_prompt() + "\n\n" + FRICTION_EVALUATION_PROMPT
        except Exception:
            logger.debug(
                "PersonaBuilder unavailable — using fallback system prompt",
                exc_info=True,
            )
            return _FALLBACK_SYSTEM_PROMPT

    def _build_user_prompt(
        self,
        user_request: str,
        task_characteristics: TaskCharacteristics,
        user_context: dict[str, Any],
    ) -> str:
        """Assemble the user-side prompt with request + risk profile + context."""
        parts: list[str] = [
            "## User Request\n",
            user_request,
            "\n## Risk Profile\n",
            f"- risk_score: {task_characteristics.risk_score:.3f}",
            f"- criticality: {task_characteristics.criticality}",
            f"- reversibility: {task_characteristics.reversibility}",
            f"- uncertainty: {task_characteristics.uncertainty}",
            f"- complexity: {task_characteristics.complexity}",
            f"- contextuality: {task_characteristics.contextuality}",
        ]

        if user_context:
            parts.append("\n## User Context\n")
            for key, value in user_context.items():
                parts.append(f"- {key}: {value}")

        return "\n".join(parts)

    def _parse_llm_response(self, raw_text: str) -> FrictionDecision:
        """Parse LLM output JSON into a FrictionDecision."""
        try:
            data = _extract_json_from_text(raw_text)
        except ValueError:
            logger.warning("Could not parse friction JSON — defaulting to comply")
            return FrictionDecision(
                level=FRICTION_COMPLY,
                reasoning="LLM response was not valid JSON — fail-open",
                user_message=None,
                proceed_if_confirmed=True,
            )

        level = str(data.get("level", "comply")).lower()
        if level not in _VALID_LEVELS:
            logger.warning("Invalid friction level %r — defaulting to comply", level)
            level = FRICTION_COMPLY

        reasoning = str(data.get("reasoning", ""))
        user_message = data.get("user_message")
        if user_message is not None:
            user_message = str(user_message)
        if level == FRICTION_COMPLY:
            user_message = None

        proceed = level != FRICTION_REFUSE

        return FrictionDecision(
            level=level,
            reasoning=reasoning,
            user_message=user_message,
            proceed_if_confirmed=proceed,
        )

    # -- lazy initialisation -------------------------------------------------

    def _ensure_llm_client(self) -> LLMClient:
        if self._llm_client is None:
            from src.core.llm import LLMClient as _LLMClient
            self._llm_client = _LLMClient()
        return self._llm_client

    def _ensure_persona_builder(self) -> PersonaBuilder:
        if self._persona_builder is None:
            from src.core.persona import get_persona_builder
            self._persona_builder = get_persona_builder()
        return self._persona_builder


# ---------------------------------------------------------------------------
# JSON extraction (replicated from scribe.py)
# ---------------------------------------------------------------------------

def _extract_json_from_text(text: str) -> Any:
    """Extract JSON from text that may be wrapped in markdown code fences.

    Strategies (in order):
    1. Direct ``json.loads()`` on the full text.
    2. Regex extraction from ````` code fences.
    3. Bracket / brace boundary detection.

    Raises:
        ValueError: If no valid JSON can be extracted.
    """
    stripped = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: code-fence regex
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    fence_match = fence_pattern.search(text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: bracket/brace boundary detection
    for open_char, close_char in [("{", "}"), ("[", "]")]:
        start_idx = text.find(open_char)
        if start_idx == -1:
            continue

        depth = 0
        in_string = False
        escape_next = False
        for i in range(start_idx, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start_idx : i + 1]
                    try:
                        return json.loads(candidate)
                    except (json.JSONDecodeError, ValueError):
                        break

    raise ValueError(f"No valid JSON found in text: {text[:200]}...")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: CognitiveFrictionEngine | None = None


def get_cognitive_friction_engine() -> CognitiveFrictionEngine:
    """Get or create the module-level CognitiveFrictionEngine singleton."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = CognitiveFrictionEngine()
    return _engine
