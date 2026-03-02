"""Skill creation engine — ARIA builds her own skills when no tool exists.

Three types:
- prompt_chain: LLM-based, no code execution, safest
- api_wrapper: Wraps a public API with sandboxed Python
- composite_workflow: Chains existing capabilities into reusable workflow
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.models.capability import SkillCreationProposal

logger = logging.getLogger(__name__)


class SkillCreationEngine:
    """ARIA creates her own skills when no existing tool fills a capability gap."""

    def __init__(self, db_client: Any) -> None:
        self._db = db_client

    async def assess_creation_opportunity(
        self,
        capability_name: str,
        description: str,
        user_id: str,
    ) -> Optional[SkillCreationProposal]:
        """Determine if ARIA can create a skill for this capability gap.

        Returns a proposal with skill type, estimated quality, and preview.
        Returns None if creation isn't feasible or tenant disallows it.
        """
        # Check tenant config
        tenant_config = await self._get_tenant_config(user_id)
        if tenant_config and not tenant_config.get("allow_skill_creation", True):
            return None

        prompt = (
            "You are ARIA, an AI colleague for life sciences commercial teams.\n"
            f'A user needs the capability "{capability_name}": {description}\n\n'
            "No existing tool was found. Assess whether you can BUILD a skill.\n\n"
            "Consider:\n"
            "1. Is there a public API? (FDA, PubMed, USPTO, etc.)\n"
            "2. Can this be done by chaining existing capabilities?\n"
            "3. Can a structured LLM prompt template produce reliable results?\n\n"
            "Return JSON:\n"
            '{"can_create": true/false, "skill_type": "prompt_chain"|"api_wrapper"|"composite_workflow",\n'
            ' "confidence": 0.0-1.0, "skill_name": "name", "description": "what it does",\n'
            ' "estimated_quality": 0.0-1.0, "approach": "how to build it",\n'
            ' "public_api_url": "URL or null", "required_capabilities": [],\n'
            ' "reason_if_no": "why not or null"}'
        )

        try:
            response = await self._generate(prompt)
            assessment = json.loads(response.strip())
        except (json.JSONDecodeError, Exception):
            logger.warning("Failed to assess skill creation opportunity", exc_info=True)
            return None

        if not assessment.get("can_create", False):
            return None

        return SkillCreationProposal(**assessment)

    async def create_skill(
        self,
        proposal: SkillCreationProposal,
        user_id: str,
        tenant_id: str,
        goal_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a new skill based on the proposal. Returns the DB record."""
        if proposal.skill_type == "prompt_chain":
            definition = await self._create_prompt_chain(proposal)
        elif proposal.skill_type == "api_wrapper":
            definition = await self._create_api_wrapper(proposal)
        elif proposal.skill_type == "composite_workflow":
            definition = await self._create_composite_workflow(proposal)
        else:
            raise ValueError(f"Unknown skill type: {proposal.skill_type}")

        skill_record: dict[str, Any] = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "skill_name": proposal.skill_name,
            "display_name": proposal.skill_name.replace("_", " ").title(),
            "description": proposal.description,
            "skill_type": proposal.skill_type,
            "created_from_capability_gap": None,
            "created_from_goal_id": goal_id,
            "creation_reasoning": proposal.approach,
            "definition": definition,
            "generated_code": definition.get("code") if proposal.skill_type == "api_wrapper" else None,
            "status": "draft",
            "trust_level": "LOW",
        }

        if skill_record.get("generated_code"):
            skill_record["code_hash"] = hashlib.sha256(
                skill_record["generated_code"].encode()
            ).hexdigest()

        result = self._db.table("aria_generated_skills").insert(skill_record).execute()
        return result.data[0] if result.data else skill_record

    async def test_skill_in_sandbox(
        self, skill_id: str, test_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Test a generated skill in sandbox environment.

        Returns: {passed: bool, output: Any, errors: list, execution_time_ms: int}
        """
        skill_result = (
            self._db.table("aria_generated_skills")
            .select("*")
            .eq("id", skill_id)
            .single()
            .execute()
        )
        skill = skill_result.data

        start_time = datetime.now(timezone.utc)
        errors: list[str] = []
        output = None

        try:
            if skill["skill_type"] == "prompt_chain":
                output = await self._test_prompt_chain(skill["definition"], test_input)
            elif skill["skill_type"] == "api_wrapper":
                output = await self._test_api_wrapper(skill, test_input)
            elif skill["skill_type"] == "composite_workflow":
                output = await self._test_composite(skill["definition"], test_input)
        except Exception as e:
            errors.append(str(e))

        elapsed_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )
        passed = len(errors) == 0 and output is not None

        # Update skill record
        try:
            (
                self._db.table("aria_generated_skills")
                .update({
                    "sandbox_test_passed": passed,
                    "sandbox_test_output": {"output": output, "errors": errors},
                    "sandbox_tested_at": datetime.now(timezone.utc).isoformat(),
                    "status": "tested" if passed else "draft",
                })
                .eq("id", skill_id)
                .execute()
            )
        except Exception:
            logger.warning("Failed to update skill sandbox test results", exc_info=True)

        return {
            "passed": passed,
            "output": output,
            "errors": errors,
            "execution_time_ms": elapsed_ms,
        }

    # ------------------------------------------------------------------
    # Private: skill definition generators
    # ------------------------------------------------------------------

    async def _create_prompt_chain(self, proposal: SkillCreationProposal) -> dict[str, Any]:
        """Generate a prompt chain skill definition."""
        prompt = (
            f"Create a prompt chain skill definition for: {proposal.description}\n\n"
            "Each step needs: name, prompt (use {variable} for inputs), "
            "output_schema, capability_required (or null), input_from (or null).\n\n"
            "Return JSON: {\"steps\": [...], \"input_schema\": {...}, \"output_schema\": {...}}\n"
            "Be specific. Life-sciences-aware. Include error handling in prompts."
        )
        response = await self._generate(prompt)
        return json.loads(response.strip())

    async def _create_api_wrapper(self, proposal: SkillCreationProposal) -> dict[str, Any]:
        """Generate a Python API wrapper skill."""
        prompt = (
            f"Create a Python API wrapper for: {proposal.description}\n"
            f"API URL: {proposal.public_api_url or 'determine from description'}\n\n"
            "Use httpx, async, error handling, type hints, under 100 lines.\n"
            "NO secrets or private API keys. Define an `execute(input_data)` function.\n\n"
            'Return JSON: {"code": "...", "api_url": "...", "allowed_domains": [...], '
            '"input_schema": {...}, "output_schema": {...}, "test_input": {...}}'
        )
        response = await self._generate(prompt)
        return json.loads(response.strip())

    async def _create_composite_workflow(self, proposal: SkillCreationProposal) -> dict[str, Any]:
        """Generate a composite workflow that chains existing capabilities."""
        prompt = (
            f"Create a composite workflow for: {proposal.description}\n"
            f"Available capabilities: {proposal.required_capabilities}\n\n"
            "Each step references an existing capability with data flow.\n\n"
            'Return JSON: {"steps": [...], "synthesis_prompt": "...", '
            '"trigger": null, "auto_execute": false, '
            '"input_schema": {...}, "output_schema": {...}}'
        )
        response = await self._generate(prompt)
        return json.loads(response.strip())

    # ------------------------------------------------------------------
    # Private: sandbox test runners
    # ------------------------------------------------------------------

    async def _test_prompt_chain(
        self, definition: dict[str, Any], test_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute prompt chain steps with test data."""
        context = {**test_input}
        for step in definition.get("steps", []):
            prompt = step["prompt"]
            for key, value in context.items():
                if isinstance(value, str):
                    prompt = prompt.replace(f"{{{key}}}", value)

            response = await self._generate(prompt)
            try:
                step_output = json.loads(response.strip())
            except json.JSONDecodeError:
                step_output = {"raw": response.strip()}

            context[step["name"]] = step_output

        return context

    async def _test_api_wrapper(
        self, skill: dict[str, Any], test_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Test API wrapper code — placeholder for full sandbox (Phase C)."""
        code = skill.get("generated_code", "")
        if not code:
            raise ValueError("No generated code found")
        # Full sandbox implementation deferred to Phase C
        raise NotImplementedError("API wrapper sandbox not yet implemented")

    async def _test_composite(
        self, definition: dict[str, Any], test_input: dict[str, Any]
    ) -> dict[str, Any]:
        """Dry-run composite workflow — verify step structure."""
        steps = definition.get("steps", [])
        if not steps:
            raise ValueError("Composite workflow has no steps")
        return {"dry_run": True, "steps_validated": len(steps)}

    # ------------------------------------------------------------------
    # Private: helpers
    # ------------------------------------------------------------------

    async def _generate(self, prompt: str) -> str:
        """Generate LLM response. Override in tests."""
        from src.core.llm import LLMClient, TaskType

        llm = LLMClient()
        return await llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a skill engineering assistant. Output only valid JSON.",
            temperature=0.0,
            max_tokens=2000,
            task=TaskType.SKILL_EXECUTE,
            agent_id="skill_creation_engine",
        )

    async def _get_tenant_config(self, user_id: str) -> dict[str, Any] | None:
        """Load tenant config for skill creation permissions."""
        try:
            profile_result = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if not profile_result.data or not profile_result.data.get("company_id"):
                return None

            config_result = (
                self._db.table("tenant_capability_config")
                .select("*")
                .eq("tenant_id", profile_result.data["company_id"])
                .limit(1)
                .maybe_single()
                .execute()
            )
            return config_result.data if config_result.data else None
        except Exception as e:
            logger.debug("Failed to load tenant config: %s", e)
            return None
