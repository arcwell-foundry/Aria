"""Verifier agent module for ARIA.

Quality verification and compliance checking for agent outputs.
Uses extended thinking to critically evaluate accuracy, freshness,
and compliance of outputs before they reach users.
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.core.persona import PersonaBuilder
    from src.memory.cold_retrieval import ColdMemoryRetriever
    from src.memory.hot_context import HotContextBuilder

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    """Result of verifying an agent output."""

    passed: bool
    issues: list[str] = field(default_factory=list)
    confidence: float = 0.0
    suggestions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "passed": self.passed,
            "issues": list(self.issues),
            "confidence": self.confidence,
            "suggestions": list(self.suggestions),
        }


@dataclass
class VerificationPolicy:
    """Configuration of checks to run for a specific task type."""

    name: str
    checks: list[str]
    description: str = ""


# ---------------------------------------------------------------------------
# Policy registry
# ---------------------------------------------------------------------------

VERIFICATION_POLICIES: dict[str, VerificationPolicy] = {
    "RESEARCH_BRIEF": VerificationPolicy(
        name="RESEARCH_BRIEF",
        checks=["source_exists", "data_freshness", "no_hallucination", "compliance"],
        description=(
            "Verify analyst research outputs: every citation must be reachable, "
            "core data < 30 days old, key claims cross-referenced, no off-label implications"
        ),
    ),
    "EMAIL_DRAFT": VerificationPolicy(
        name="EMAIL_DRAFT",
        checks=["tone_match", "compliance", "recipient_appropriate"],
        description=(
            "Verify scribe email drafts: tone matches user's Digital Twin, "
            "no medical claims without evidence, formality matches relationship"
        ),
    ),
    "BATTLE_CARD": VerificationPolicy(
        name="BATTLE_CARD",
        checks=["data_currency", "claim_supported", "balanced"],
        description=(
            "Verify strategist battle cards: competitor data < 14 days old, "
            "each competitive claim has a source, acknowledges competitor strengths"
        ),
    ),
    "STRATEGY": VerificationPolicy(
        name="STRATEGY",
        checks=["logical_consistency", "goal_alignment", "risk_assessment"],
        description=(
            "Verify strategist plans: recommendations follow from analysis, "
            "strategy serves stated goals, downside scenarios considered"
        ),
    ),
}


# Fallback system prompt when PersonaBuilder is unavailable
_FALLBACK_SYSTEM_PROMPT = """\
You are ARIA's Verifier — a skeptical, rigorous quality reviewer for life sciences \
commercial outputs. Your job is to find problems, not to be encouraging.

Rules:
- Off-label claims are NEVER acceptable.
- Every citation must reference a real, verifiable source.
- Data older than 30 days must be flagged as stale.
- Unsupported medical claims must be caught and reported.
- When in doubt, flag it — false negatives are worse than false positives.

You must return a JSON object with exactly these fields:
{
  "passed": boolean,
  "issues": ["list of specific problems found"],
  "confidence": float between 0.0 and 1.0,
  "suggestions": ["list of concrete fixes"]
}

Return ONLY the JSON object, no other text."""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class VerifierAgent(BaseAgent):
    """Quality verification agent for ARIA.

    Validates agent outputs against verification policies using extended
    thinking for critical evaluation. Extends BaseAgent directly (not
    SkillAwareAgent) because verification is read-only.

    The primary API is ``verify(agent_output, policy)``. The ``execute()``
    method (required by BaseAgent) delegates to ``verify()``.
    """

    name = "Verifier"
    description = "Quality verification and compliance checking"

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        persona_builder: "PersonaBuilder | None" = None,
        hot_context_builder: "HotContextBuilder | None" = None,
        cold_retriever: "ColdMemoryRetriever | None" = None,
    ) -> None:
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            persona_builder=persona_builder,
            hot_context_builder=hot_context_builder,
            cold_retriever=cold_retriever,
        )

    def _register_tools(self) -> dict[str, Callable[..., Any]]:
        """Register verification tool."""
        return {"verify": self.verify}

    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate task contains agent_output."""
        return "agent_output" in task and isinstance(task.get("agent_output"), dict)

    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute verification via the standard agent interface.

        Expects task dict with:
            - agent_output: dict — the output to verify
            - policy_name: str — key in VERIFICATION_POLICIES (default "RESEARCH_BRIEF")
        """
        agent_output = task["agent_output"]
        policy_name = task.get("policy_name", "RESEARCH_BRIEF")
        policy = VERIFICATION_POLICIES.get(policy_name)

        if policy is None:
            return AgentResult(
                success=False,
                data=None,
                error=f"Unknown verification policy: {policy_name}",
            )

        result = await self.verify(agent_output, policy)

        return AgentResult(
            success=True,
            data=result.to_dict(),
        )

    async def verify(
        self,
        agent_output: dict[str, Any],
        verification_policy: VerificationPolicy,
    ) -> VerificationResult:
        """Verify agent output against a verification policy.

        Uses extended thinking ('complex' effort) to critically evaluate
        the output. Passes user_id for CostGovernor budget tracking.

        Args:
            agent_output: The agent output to verify.
            verification_policy: Policy defining which checks to run.

        Returns:
            VerificationResult with pass/fail, issues, confidence, suggestions.
        """
        try:
            system_prompt = await self._build_verifier_prompt(verification_policy)
            user_message = self._build_verification_request(
                agent_output,
                verification_policy,
            )

            response = await self.llm.generate_response_with_thinking(
                messages=[{"role": "user", "content": user_message}],
                system_prompt=system_prompt,
                thinking_effort="complex",
                user_id=self.user_id,
            )

            return self._parse_verification_response(response.text)

        except Exception as e:
            logger.warning("Verification failed, returning conservative failure: %s", e)
            return VerificationResult(
                passed=False,
                issues=[f"Verification could not be completed: {e}"],
                confidence=0.0,
                suggestions=["Manual review required"],
            )

    async def _build_verifier_prompt(
        self,
        policy: VerificationPolicy,
    ) -> str:
        """Build system prompt using PersonaBuilder or fallback."""
        checks_str = ", ".join(policy.checks)
        task_desc = (
            f"Critically verify agent output using policy '{policy.name}'. "
            f"Checks to perform: {checks_str}. "
            f"You are a skeptical reviewer — assume nothing is correct until proven. "
            f"Flag any unsupported claims, hallucinated data, compliance risks, "
            f"or logical inconsistencies."
        )

        persona_prompt = await self._get_persona_system_prompt(
            task_description=task_desc,
            output_format="json",
        )

        if persona_prompt is not None:
            return persona_prompt

        return _FALLBACK_SYSTEM_PROMPT

    @staticmethod
    def _build_verification_request(
        agent_output: dict[str, Any],
        policy: VerificationPolicy,
    ) -> str:
        """Build the user message for the verification LLM call."""
        output_json = json.dumps(agent_output, indent=2, default=str)
        checks_str = "\n".join(f"  - {check}" for check in policy.checks)

        return (
            f"## Verification Task: {policy.name}\n\n"
            f"{policy.description}\n\n"
            f"### Checks to perform:\n{checks_str}\n\n"
            f"### Agent output to verify:\n```json\n{output_json}\n```\n\n"
            f"Evaluate EACH check above. Return a JSON object with:\n"
            f'- "passed": true only if ALL checks pass\n'
            f'- "issues": list every specific problem found (empty if none)\n'
            f'- "confidence": your confidence in the verification (0.0-1.0)\n'
            f'- "suggestions": concrete fixes for each issue\n\n'
            f"Return ONLY the JSON object."
        )

    @staticmethod
    def _parse_verification_response(text: str) -> VerificationResult:
        """Parse LLM response into VerificationResult."""
        try:
            data = _extract_json_from_text(text)
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("Could not parse verification response: %s", e)
            return VerificationResult(
                passed=False,
                issues=["Verification response could not be parsed"],
                confidence=0.0,
                suggestions=["Manual review required"],
            )

        return VerificationResult(
            passed=bool(data.get("passed", False)),
            issues=list(data.get("issues", [])),
            confidence=float(data.get("confidence", 0.0)),
            suggestions=list(data.get("suggestions", [])),
        )


def _extract_json_from_text(text: str) -> Any:
    """Extract JSON from text that may be wrapped in markdown code fences."""
    text_stripped = text.strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(text_stripped)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Code fence extraction
    fence_pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
    fence_match = re.search(fence_pattern, text_stripped, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find outermost brackets/braces
    for open_char, close_char in [("{", "}"), ("[", "]")]:
        start = text_stripped.find(open_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text_stripped)):
            if text_stripped[i] == open_char:
                depth += 1
            elif text_stripped[i] == close_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text_stripped[start : i + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not extract valid JSON from text: {text_stripped[:200]}...")
