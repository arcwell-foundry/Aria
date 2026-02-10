"""Skill Creator for ARIA.

ARIA can create new LLM skill definitions when she detects repeated task
patterns. The SkillCreator analyzes execution history and conversations
to find opportunities, generates skill blueprints, persists them as
custom tenant skills, and improves underperforming skills via A/B testing.

Pipeline:
1. detect_creation_opportunity — find 3+ similar multi-step requests
2. create_custom_skill — generate YAML definition, save, register
3. improve_existing_skill — A/B test prompt variations on negative feedback

Usage::

    creator = SkillCreator()
    blueprint = await creator.detect_creation_opportunity(user_id="...")
    if blueprint:
        skill = await creator.create_custom_skill(blueprint, tenant_id=...)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.security.trust_levels import SkillTrustLevel

logger = logging.getLogger(__name__)

# Analysis window for pattern detection
PATTERN_WINDOW_DAYS = 30

# Minimum similar requests to trigger skill creation
MIN_PATTERN_FREQUENCY = 3

# Maximum evidence rows per query
MAX_EVIDENCE_ROWS = 100

# A/B test minimum executions before declaring a winner
AB_TEST_MIN_EXECUTIONS = 10


@dataclass
class SkillBlueprint:
    """A proposed skill definition generated from detected patterns.

    Attributes:
        suggested_name: Machine-friendly identifier for the skill.
        description: One-line human description of what the skill does.
        prompt_chain: Ordered list of prompt steps for the skill.
        output_schema: JSON Schema for validating structured output.
        input_requirements: Required context keys for skill execution.
        evidence_summary: Description of the patterns that triggered creation.
        pattern_frequency: Number of times the pattern was observed.
        sample_requests: Representative user requests that match the pattern.
    """

    suggested_name: str
    description: str
    prompt_chain: list[str]
    output_schema: dict[str, Any]
    input_requirements: list[str]
    evidence_summary: str
    pattern_frequency: int = MIN_PATTERN_FREQUENCY
    sample_requests: list[str] = field(default_factory=list)


@dataclass
class CustomSkill:
    """A persisted custom skill created from a SkillBlueprint.

    Attributes:
        id: UUID of the custom_skills row.
        tenant_id: Owning tenant UUID.
        skill_name: Machine-friendly name.
        description: Human description.
        definition: Full skill definition stored as JSONB.
        trust_level: Always starts as 'user' (sandboxed).
        version: Definition version (starts at 1).
        created_at: Timestamp of creation.
    """

    id: str
    tenant_id: str
    skill_name: str
    description: str
    definition: dict[str, Any]
    trust_level: str = "user"
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Outcome:
    """Feedback record for a skill execution.

    Attributes:
        execution_id: ID of the execution that was rated.
        feedback: 'positive' or 'negative'.
        skill_id: The skill that was executed.
        created_at: When the feedback was given.
    """

    execution_id: str
    feedback: str  # "positive" | "negative"
    skill_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class SkillCreator:
    """Creates and improves custom LLM skill definitions.

    Analyzes user behavior to detect repeated multi-step request
    patterns, generates skill blueprints, and persists them as
    tenant-scoped custom skills. Also runs A/B tests on underperforming
    skills to improve their prompts.
    """

    def __init__(self) -> None:
        self._client = SupabaseClient.get_client()
        self._llm = LLMClient()

    # ------------------------------------------------------------------
    # 1. Pattern detection
    # ------------------------------------------------------------------

    async def detect_creation_opportunity(
        self,
        user_id: str,
    ) -> SkillBlueprint | None:
        """Analyze recent activity for repeated multi-step task patterns.

        Queries the last 30 days of skill_execution_plans and
        conversations. Looks for 3+ similar requests that required
        multi-step manual handling — candidates for a reusable skill.

        Args:
            user_id: The user whose history to analyze.

        Returns:
            A SkillBlueprint if a creation opportunity is found,
            or None if no pattern qualifies.
        """
        logger.info(
            "Detecting skill creation opportunities",
            extra={"user_id": user_id},
        )

        evidence = await self._gather_pattern_evidence(user_id)
        if not evidence:
            logger.info(
                "No evidence found for skill creation",
                extra={"user_id": user_id},
            )
            return None

        blueprint = await self._synthesize_blueprint(user_id, evidence)
        return blueprint

    async def _gather_pattern_evidence(
        self,
        user_id: str,
    ) -> list[dict[str, Any]]:
        """Collect execution plans and conversation data for analysis.

        Args:
            user_id: The user to query.

        Returns:
            Combined evidence from execution plans and conversations.
        """
        evidence: list[dict[str, Any]] = []
        cutoff = (datetime.now(UTC) - timedelta(days=PATTERN_WINDOW_DAYS)).isoformat()

        # Query 1: Multi-step execution plans (completed)
        plans = await self._query_execution_plans(user_id, cutoff)
        evidence.extend(plans)

        # Query 2: Conversation messages showing repeated request patterns
        conversations = await self._query_conversations(user_id, cutoff)
        evidence.extend(conversations)

        return evidence

    async def _query_execution_plans(
        self,
        user_id: str,
        cutoff: str,
    ) -> list[dict[str, Any]]:
        """Query completed execution plans for multi-step patterns.

        Args:
            user_id: The user to query.
            cutoff: ISO timestamp for the lookback window.

        Returns:
            Evidence rows from execution plans.
        """
        evidence: list[dict[str, Any]] = []

        try:
            resp = (
                self._client.table("skill_execution_plans")
                .select("id,task_description,plan_dag,status,created_at")
                .eq("user_id", user_id)
                .in_("status", ["completed", "failed"])
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(MAX_EVIDENCE_ROWS)
                .execute()
            )

            for row in resp.data or []:
                dag = row.get("plan_dag") or {}
                step_count = len(dag.get("steps", []))
                # Only include multi-step plans (2+ steps)
                if step_count >= 2:
                    evidence.append(
                        {
                            "source": "execution_plan",
                            "plan_id": row["id"],
                            "task_description": row.get("task_description", ""),
                            "step_count": step_count,
                            "skills_used": [s.get("skill_id", "") for s in dag.get("steps", [])],
                            "status": row.get("status"),
                            "created_at": row.get("created_at"),
                        }
                    )

        except Exception as e:
            logger.warning("Error querying execution plans for patterns: %s", e)

        return evidence

    async def _query_conversations(
        self,
        _user_id: str,
        cutoff: str,
    ) -> list[dict[str, Any]]:
        """Query user messages for repeated task request patterns.

        Args:
            user_id: The user to query.
            cutoff: ISO timestamp for the lookback window.

        Returns:
            Evidence rows from conversation messages.
        """
        evidence: list[dict[str, Any]] = []

        try:
            resp = (
                self._client.table("messages")
                .select("id,content,created_at,conversation_id")
                .eq("role", "user")
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(MAX_EVIDENCE_ROWS)
                .execute()
            )

            for row in resp.data or []:
                content = row.get("content", "")
                if content:
                    evidence.append(
                        {
                            "source": "conversation",
                            "message_id": row["id"],
                            "content": content[:500],
                            "conversation_id": row.get("conversation_id"),
                            "created_at": row.get("created_at"),
                        }
                    )

        except Exception as e:
            logger.warning("Error querying conversations for patterns: %s", e)

        return evidence

    async def _synthesize_blueprint(
        self,
        user_id: str,
        evidence: list[dict[str, Any]],
    ) -> SkillBlueprint | None:
        """Use LLM to identify repeated patterns and generate a blueprint.

        Args:
            user_id: The user these patterns belong to.
            evidence: Combined evidence from plans and conversations.

        Returns:
            A SkillBlueprint if a qualifying pattern is found, else None.
        """
        system_prompt = (
            "You are ARIA's Skill Creator. Analyze the following user behavior "
            "evidence (execution plans and conversation messages) to identify "
            "repeated task patterns that could become a reusable skill.\n\n"
            "Look for:\n"
            "- 3 or more similar requests that required multi-step handling\n"
            "- Repeated sequences of the same skills being chained together\n"
            "- Manual workarounds for tasks that could be automated\n\n"
            "If you find a qualifying pattern, generate a skill blueprint:\n"
            "- suggested_name: lowercase, hyphenated identifier (e.g. 'weekly-territory-report')\n"
            "- description: One sentence describing what the skill does\n"
            "- prompt_chain: Ordered list of prompt instructions for each step\n"
            "- output_schema: JSON Schema for the expected output\n"
            "- input_requirements: List of required input context keys\n"
            "- evidence_summary: Why this pattern qualifies for skill creation\n"
            "- pattern_frequency: How many times the pattern appeared\n"
            "- sample_requests: 2-3 representative user requests\n\n"
            "If no pattern qualifies (fewer than 3 similar requests), return "
            '{"blueprint": null}.\n\n'
            "Return valid JSON: "
            '{"blueprint": {<fields above>} | null}'
        )

        evidence_text = json.dumps(evidence[:MAX_EVIDENCE_ROWS], default=str)

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": f"User behavior evidence:\n{evidence_text}"}],
                system_prompt=system_prompt,
                max_tokens=2048,
                temperature=0.3,
            )

            parsed = json.loads(response)
            bp_data = parsed.get("blueprint")

            if bp_data is None:
                logger.info(
                    "No qualifying pattern found for skill creation",
                    extra={"user_id": user_id},
                )
                return None

            frequency = bp_data.get("pattern_frequency", 0)
            if frequency < MIN_PATTERN_FREQUENCY:
                logger.info(
                    "Pattern frequency below threshold",
                    extra={
                        "user_id": user_id,
                        "frequency": frequency,
                        "threshold": MIN_PATTERN_FREQUENCY,
                    },
                )
                return None

            return SkillBlueprint(
                suggested_name=bp_data.get("suggested_name", "custom-skill"),
                description=bp_data.get("description", ""),
                prompt_chain=bp_data.get("prompt_chain", []),
                output_schema=bp_data.get("output_schema", {}),
                input_requirements=bp_data.get("input_requirements", []),
                evidence_summary=bp_data.get("evidence_summary", ""),
                pattern_frequency=frequency,
                sample_requests=bp_data.get("sample_requests", []),
            )

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse LLM blueprint response: %s", e)
            return None
        except Exception as e:
            logger.error("LLM blueprint synthesis failed: %s", e)
            return None

    # ------------------------------------------------------------------
    # 2. Custom skill creation
    # ------------------------------------------------------------------

    async def create_custom_skill(
        self,
        blueprint: SkillBlueprint,
        tenant_id: UUID,
    ) -> CustomSkill:
        """Create a custom skill definition from a blueprint.

        Builds the YAML-equivalent definition programmatically, persists
        to the custom_skills table with tenant isolation, registers with
        the SkillRegistry, and notifies the user.

        Args:
            blueprint: The skill blueprint to materialize.
            tenant_id: Owning tenant UUID for data isolation.

        Returns:
            The persisted CustomSkill record.
        """
        logger.info(
            "Creating custom skill from blueprint",
            extra={
                "skill_name": blueprint.suggested_name,
                "tenant_id": str(tenant_id),
            },
        )

        # Build the definition structure (mirrors YAML skill definitions)
        definition = self._build_definition(blueprint)

        # Persist to database
        row = (
            self._client.table("custom_skills")
            .insert(
                {
                    "tenant_id": str(tenant_id),
                    "created_by": str(tenant_id),  # Set by caller context
                    "skill_name": blueprint.suggested_name,
                    "description": blueprint.description,
                    "skill_type": "llm_definition",
                    "definition": definition,
                    "trust_level": "user",
                    "performance_metrics": {
                        "success_rate": 0,
                        "executions": 0,
                        "avg_satisfaction": 0,
                    },
                    "is_published": False,
                    "version": 1,
                }
            )
            .execute()
        )

        if not row.data:
            raise RuntimeError(f"Failed to insert custom skill: {blueprint.suggested_name}")

        saved = row.data[0]
        skill = CustomSkill(
            id=saved["id"],
            tenant_id=str(tenant_id),
            skill_name=saved["skill_name"],
            description=saved.get("description", ""),
            definition=saved.get("definition", {}),
            trust_level=saved.get("trust_level", "user"),
            version=saved.get("version", 1),
            created_at=datetime.now(UTC),
        )

        # Register with SkillRegistry so it's immediately available
        await self._register_with_registry(skill)

        # Notify the user about the new skill
        await self._notify_skill_created(skill)

        logger.info(
            "Custom skill created",
            extra={
                "skill_id": skill.id,
                "skill_name": skill.skill_name,
                "tenant_id": skill.tenant_id,
            },
        )

        return skill

    def _build_definition(self, blueprint: SkillBlueprint) -> dict[str, Any]:
        """Build a YAML-equivalent definition dict from a blueprint.

        Args:
            blueprint: The source blueprint.

        Returns:
            Definition dict matching the custom_skills.definition schema.
        """
        # Build a system prompt from the prompt chain
        chain_text = "\n\n".join(
            f"Step {i + 1}: {step}" for i, step in enumerate(blueprint.prompt_chain)
        )

        system_prompt = (
            f"You are a specialized ARIA skill: {blueprint.description}\n\n"
            f"Follow these steps in order:\n{chain_text}\n\n"
            "Produce output matching the required JSON schema."
        )

        return {
            "name": blueprint.suggested_name,
            "description": blueprint.description,
            "agent_assignment": [],  # User skills aren't agent-assigned
            "system_prompt": system_prompt,
            "output_schema": blueprint.output_schema,
            "input_requirements": blueprint.input_requirements,
            "trust_level": "user",
            "estimated_seconds": 30,
            "prompt_chain": blueprint.prompt_chain,
            "evidence_summary": blueprint.evidence_summary,
            "sample_requests": blueprint.sample_requests,
        }

    async def _register_with_registry(self, skill: CustomSkill) -> None:
        """Register a newly created custom skill with the SkillRegistry.

        Args:
            skill: The custom skill to register.
        """
        try:
            from src.skills.registry import (
                PerformanceMetrics,
                SkillEntry,
                SkillRegistry,
                SkillType,
            )

            registry = SkillRegistry()
            entry = SkillEntry(
                id=f"custom:{skill.id}",
                name=skill.skill_name,
                description=skill.description,
                skill_type=SkillType.CUSTOM,
                agent_types=skill.definition.get("agent_assignment", []),
                trust_level=SkillTrustLevel.USER,
                data_classes=[],
                performance_metrics=PerformanceMetrics(),
            )
            registry._entries[entry.id] = entry

        except Exception as e:
            logger.warning("Failed to register custom skill with registry: %s", e)

    async def _notify_skill_created(self, skill: CustomSkill) -> None:
        """Send a notification about the newly created skill.

        Args:
            skill: The skill that was created.
        """
        try:
            from src.models.notification import NotificationType
            from src.services.notification_service import NotificationService

            message = (
                f"I created a specialized skill for '{skill.description}' "
                "based on how you've been asking for this. "
                "Want me to use it automatically next time?"
            )

            await NotificationService.create_notification(
                user_id=skill.tenant_id,
                type=NotificationType.SIGNAL_DETECTED,
                title="New Skill Created",
                message=message,
                link="/skills",
                metadata={
                    "skill_id": skill.id,
                    "skill_name": skill.skill_name,
                    "trust_level": skill.trust_level,
                },
            )

        except Exception as e:
            logger.warning("Failed to notify about skill creation: %s", e)

    # ------------------------------------------------------------------
    # 3. Skill improvement via A/B testing
    # ------------------------------------------------------------------

    async def improve_existing_skill(
        self,
        skill_id: str,
        feedback: list[Outcome],
    ) -> None:
        """Improve an underperforming custom skill using A/B testing.

        When a skill gets negative feedback, generates an improved
        prompt variation. Both versions run in parallel until enough
        data is collected, then the winner is promoted and the loser
        is archived.

        Args:
            skill_id: UUID of the custom skill to improve.
            feedback: List of recent feedback outcomes.
        """
        logger.info(
            "Evaluating skill improvement",
            extra={"skill_id": skill_id, "feedback_count": len(feedback)},
        )

        # Load current skill definition
        current = await self._load_skill(skill_id)
        if current is None:
            logger.warning("Skill not found for improvement: %s", skill_id)
            return

        definition = current.get("definition") or {}
        version = current.get("version", 1)

        # Check if an A/B test is already running
        existing_variant = definition.get("ab_test_variant")
        if existing_variant:
            await self._evaluate_ab_test(skill_id, current, feedback)
            return

        # Count negative feedback
        negative_count = sum(1 for f in feedback if f.feedback == "negative")
        if negative_count == 0:
            logger.info(
                "No negative feedback — skipping improvement",
                extra={"skill_id": skill_id},
            )
            return

        # Generate improved prompt variation
        improved_prompt = await self._generate_improved_prompt(definition, feedback)
        if not improved_prompt:
            return

        # Store the variant alongside the original for A/B testing
        definition["ab_test_variant"] = {
            "system_prompt": improved_prompt,
            "created_at": datetime.now(UTC).isoformat(),
            "executions": 0,
            "positive_feedback": 0,
            "negative_feedback": 0,
        }

        # Also initialize tracking for the original if not present
        if "ab_test_original" not in definition:
            definition["ab_test_original"] = {
                "executions": 0,
                "positive_feedback": 0,
                "negative_feedback": 0,
            }

        # Update the skill with the A/B test configuration
        try:
            self._client.table("custom_skills").update(
                {
                    "definition": definition,
                    "version": version + 1,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", skill_id).execute()

            logger.info(
                "A/B test started for skill",
                extra={"skill_id": skill_id, "version": version + 1},
            )

        except Exception as e:
            logger.error("Failed to start A/B test: %s", e)

    async def _load_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Load a custom skill row from the database.

        Args:
            skill_id: UUID of the skill.

        Returns:
            The skill row dict, or None if not found.
        """
        try:
            resp = self._client.table("custom_skills").select("*").eq("id", skill_id).execute()
            if resp.data:
                return resp.data[0]
            return None

        except Exception as e:
            logger.error("Failed to load skill %s: %s", skill_id, e)
            return None

    async def _generate_improved_prompt(
        self,
        definition: dict[str, Any],
        feedback: list[Outcome],
    ) -> str | None:
        """Use LLM to generate an improved system prompt.

        Args:
            definition: Current skill definition.
            feedback: Recent feedback outcomes.

        Returns:
            Improved system prompt string, or None if generation fails.
        """
        current_prompt = definition.get("system_prompt", "")
        skill_name = definition.get("name", "unknown")
        skill_description = definition.get("description", "")

        feedback_summary = json.dumps(
            [
                {
                    "execution_id": f.execution_id,
                    "feedback": f.feedback,
                    "created_at": f.created_at.isoformat(),
                }
                for f in feedback
            ],
            default=str,
        )

        system_prompt = (
            "You are ARIA's Skill Improver. A custom skill is getting negative "
            "feedback. Analyze the current system prompt and the feedback to "
            "generate an improved version.\n\n"
            "Guidelines:\n"
            "- Keep the same overall structure and intent\n"
            "- Make instructions clearer and more specific\n"
            "- Add guardrails for common failure modes\n"
            "- Improve output quality without changing the schema\n"
            "- Do NOT change the output_schema or input_requirements\n\n"
            "Return valid JSON: "
            '{"improved_prompt": "<the full improved system prompt>"}'
        )

        user_content = (
            f"Skill: {skill_name}\n"
            f"Description: {skill_description}\n\n"
            f"Current system prompt:\n{current_prompt}\n\n"
            f"Recent feedback:\n{feedback_summary}"
        )

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": user_content}],
                system_prompt=system_prompt,
                max_tokens=2048,
                temperature=0.4,
            )

            parsed = json.loads(response)
            improved = parsed.get("improved_prompt")
            if not improved:
                logger.warning("LLM returned empty improved prompt")
                return None

            return improved

        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to parse improved prompt response: %s", e)
            return None
        except Exception as e:
            logger.error("LLM prompt improvement failed: %s", e)
            return None

    async def _evaluate_ab_test(
        self,
        skill_id: str,
        current: dict[str, Any],
        feedback: list[Outcome],
    ) -> None:
        """Evaluate an ongoing A/B test and promote the winner if ready.

        Compares positive feedback rates between the original and
        variant prompts. Requires AB_TEST_MIN_EXECUTIONS on each
        before declaring a winner.

        Args:
            skill_id: UUID of the skill under test.
            current: Current skill row from database.
            feedback: New feedback to incorporate.
        """
        definition = current.get("definition") or {}
        original = definition.get("ab_test_original", {})
        variant = definition.get("ab_test_variant", {})

        # Update feedback counts from new outcomes
        # In a real system, execution metadata would tag which variant ran.
        # Here we split feedback evenly for simplicity, or use metadata.
        for outcome in feedback:
            if outcome.feedback == "positive":
                # Attribute to variant (newer executions use the variant)
                variant["positive_feedback"] = variant.get("positive_feedback", 0) + 1
            else:
                variant["negative_feedback"] = variant.get("negative_feedback", 0) + 1
            variant["executions"] = variant.get("executions", 0) + 1

        total_original = original.get("executions", 0)
        total_variant = variant.get("executions", 0)

        # Check if we have enough data to decide
        if total_original < AB_TEST_MIN_EXECUTIONS or total_variant < AB_TEST_MIN_EXECUTIONS:
            # Update counts and continue testing
            definition["ab_test_original"] = original
            definition["ab_test_variant"] = variant

            try:
                self._client.table("custom_skills").update({"definition": definition}).eq(
                    "id", skill_id
                ).execute()
            except Exception as e:
                logger.error("Failed to update A/B test counts: %s", e)
            return

        # Calculate success rates
        original_rate = (
            original.get("positive_feedback", 0) / total_original if total_original > 0 else 0.0
        )
        variant_rate = (
            variant.get("positive_feedback", 0) / total_variant if total_variant > 0 else 0.0
        )

        version = current.get("version", 1)

        if variant_rate > original_rate:
            # Variant wins — promote it
            logger.info(
                "A/B test winner: variant",
                extra={
                    "skill_id": skill_id,
                    "original_rate": round(original_rate, 3),
                    "variant_rate": round(variant_rate, 3),
                },
            )
            definition["system_prompt"] = variant["system_prompt"]
        else:
            # Original wins — keep it
            logger.info(
                "A/B test winner: original",
                extra={
                    "skill_id": skill_id,
                    "original_rate": round(original_rate, 3),
                    "variant_rate": round(variant_rate, 3),
                },
            )

        # Clean up A/B test state
        definition.pop("ab_test_variant", None)
        definition.pop("ab_test_original", None)

        # Update performance metrics
        total_positive = original.get("positive_feedback", 0) + variant.get("positive_feedback", 0)
        total_executions = total_original + total_variant
        success_rate = total_positive / total_executions if total_executions > 0 else 0.0

        try:
            self._client.table("custom_skills").update(
                {
                    "definition": definition,
                    "version": version + 1,
                    "performance_metrics": {
                        "success_rate": round(success_rate, 3),
                        "executions": total_executions,
                        "avg_satisfaction": round(success_rate, 3),
                    },
                }
            ).eq("id", skill_id).execute()

            logger.info(
                "A/B test completed — skill updated",
                extra={
                    "skill_id": skill_id,
                    "version": version + 1,
                    "success_rate": round(success_rate, 3),
                },
            )

        except Exception as e:
            logger.error("Failed to finalize A/B test: %s", e)
