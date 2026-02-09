"""Adaptive Onboarding OODA Controller (US-916).

Wraps the onboarding step sequence in OODA logic, dynamically adapting
the flow based on what ARIA learns at each step. After each step completion,
runs Observe → Orient → Decide → Act to determine whether to reorder,
emphasize, or inject contextual questions into the onboarding flow.
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import BaseModel

from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.memory.working import WorkingMemoryManager
from src.onboarding.models import OnboardingStep

logger = logging.getLogger(__name__)


class OODAAssessment(BaseModel):
    """Result of an OODA loop iteration for onboarding adaptation."""

    observation: dict[str, Any]  # What has user provided, what has enrichment found
    orientation: dict[str, Any]  # Assessment of highest-value next step
    decision: dict[str, Any]  # Step reordering, emphasis, injected questions
    reasoning: str  # Why this adaptation


class InjectedQuestion(BaseModel):
    """A contextual question ARIA injects between standard onboarding steps."""

    question: str
    context: str  # Why ARIA is asking
    insert_after_step: str  # Which step to inject after


class OnboardingOODAController:
    """Adapts onboarding flow in real-time using OODA loop.

    After each step completion, runs OODA to determine:
    - Should the default next step be reordered?
    - Should any steps be emphasized (more detail)?
    - Should contextual questions be injected?
    """

    def __init__(self) -> None:
        """Initialize with Supabase, LLM, and WorkingMemory clients."""
        self._db = SupabaseClient.get_client()
        self._llm = LLMClient()
        self._wm_manager = WorkingMemoryManager()

    async def assess_next_step(
        self, user_id: str, completed_step: OnboardingStep
    ) -> OODAAssessment:
        """Run OODA assessment after a step completes.

        Args:
            user_id: The authenticated user's ID.
            completed_step: The step that was just completed.

        Returns:
            OODAAssessment with observation, orientation, decision, and reasoning.
        """
        # Create a working memory session for this OODA cycle
        session_id = f"ooda_{user_id}_{completed_step.value}"
        wm = self._wm_manager.get_or_create(session_id, user_id)
        wm.set_goal("Adapt onboarding flow after step completion", {
            "completed_step": completed_step.value,
        })

        # OBSERVE: Gather current state
        observation = await self._observe(user_id)
        wm.add_message("system", json.dumps(observation), {"phase": "observe"})

        # ORIENT: Assess what matters most
        orientation = await self._orient(observation)
        wm.add_message("system", json.dumps(orientation), {"phase": "orient"})

        # DECIDE: Determine adaptations
        decision = await self._decide(observation, orientation, completed_step)
        wm.add_message("system", json.dumps(decision), {"phase": "decide"})

        # Build assessment
        assessment = OODAAssessment(
            observation=observation,
            orientation=orientation,
            decision=decision,
            reasoning=decision.get("reasoning", "Default step order maintained"),
        )

        # ACT: Log and store
        await self._log_assessment(user_id, assessment)

        # Clean up the working memory session after the cycle
        self._wm_manager.delete(session_id)

        return assessment

    async def get_injected_questions(
        self, user_id: str, current_step: str
    ) -> list[InjectedQuestion]:
        """Get any contextual questions to inject at current step.

        Args:
            user_id: The authenticated user's ID.
            current_step: The step to check for injected questions.

        Returns:
            List of InjectedQuestion instances for this step.
        """
        state = await self._get_onboarding_state(user_id)
        metadata: dict[str, Any] = (state or {}).get("metadata", {})
        injections: dict[str, list[dict[str, Any]]] = metadata.get("ooda_injections", {})

        questions: list[InjectedQuestion] = []
        for q in injections.get(current_step, []):
            questions.append(InjectedQuestion(**q))

        return questions

    async def _observe(self, user_id: str) -> dict[str, Any]:
        """OBSERVE: What has user provided? What has enrichment found?

        Args:
            user_id: The user's ID.

        Returns:
            Dict capturing completed steps, facts, integrations, classification.
        """
        state = await self._get_onboarding_state(user_id)
        facts = (
            self._db.table("memory_semantic")
            .select("fact, metadata")
            .eq("user_id", user_id)
            .limit(20)
            .execute()
        )
        integrations = (
            self._db.table("user_integrations").select("provider").eq("user_id", user_id).execute()
        )
        classification = await self._get_classification(user_id)

        integration_rows = cast(list[dict[str, Any]], integrations.data or [])

        return {
            "completed_steps": (state or {}).get("completed_steps", []),
            "skipped_steps": (state or {}).get("skipped_steps", []),
            "step_data": (state or {}).get("step_data", {}),
            "fact_count": len(facts.data or []),
            "classification": classification,
            "connected_integrations": [i["provider"] for i in integration_rows],
            "readiness_scores": (state or {}).get("readiness_scores", {}),
        }

    async def _orient(self, observation: dict[str, Any]) -> dict[str, Any]:
        """ORIENT: What's the highest-value next step for this user?

        Args:
            observation: The observation dict from _observe.

        Returns:
            Dict with priority_action, emphasis, and skip_recommendation.
        """
        classification = observation.get("classification", {})
        company_type = (
            classification.get("company_type", "Unknown") if classification else "Unknown"
        )

        prompt = (
            f"Given this onboarding state for a {company_type} user, "
            "assess what matters most.\n\n"
            f"Completed steps: {observation.get('completed_steps', [])}\n"
            f"Facts discovered: {observation.get('fact_count', 0)}\n"
            f"Integrations: {observation.get('connected_integrations', [])}\n"
            f"Readiness: {observation.get('readiness_scores', {})}\n\n"
            f"What is the highest-value next action for this specific user? Consider:\n"
            f"- Their company type ({company_type})\n"
            "- What data gaps exist\n"
            "- Whether they seem rushed or thorough\n\n"
            "Return JSON:\n"
            '{"priority_action": "description", "emphasis": "which step needs more '
            'attention", "skip_recommendation": "any step that can be safely de-emphasized"}'
        )

        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
        )
        try:
            return dict(json.loads(response))
        except (json.JSONDecodeError, TypeError):
            return {
                "priority_action": "Continue default order",
                "emphasis": "none",
                "skip_recommendation": "none",
            }

    async def _decide(
        self,
        observation: dict[str, Any],
        orientation: dict[str, Any],
        completed_step: OnboardingStep,
    ) -> dict[str, Any]:
        """DECIDE: Reorder, emphasize, or inject steps.

        Args:
            observation: The observation dict from _observe.
            orientation: The orientation dict from _orient.
            completed_step: The step that was just completed.

        Returns:
            Dict with reorder, emphasize, inject_questions, and reasoning.
        """
        decision: dict[str, Any] = {
            "reorder": None,
            "emphasize": orientation.get("emphasis"),
            "inject_questions": [],
            "reasoning": "Default step order maintained",
        }

        classification = observation.get("classification", {})
        company_type = (classification.get("company_type", "") if classification else "").lower()

        # CDMO user → inject question about manufacturing capabilities
        if "cdmo" in company_type and completed_step == OnboardingStep.COMPANY_DISCOVERY:
            decision["inject_questions"].append(
                {
                    "question": (
                        "I see you're at a CDMO. Which modalities does your facility "
                        "support — biologics, small molecule, cell therapy, or others?"
                    ),
                    "context": "CDMO-specific capability mapping",
                    "insert_after_step": "company_discovery",
                }
            )

        # User who connected CRM → leverage pipeline data
        connected = observation.get("connected_integrations", [])
        if "salesforce" in connected or "hubspot" in connected:
            decision["reasoning"] = (
                "CRM connected — can leverage pipeline data to pre-fill information"
            )

        # User with very few facts → emphasize document upload
        if observation.get("fact_count", 0) < 5 and completed_step in (
            OnboardingStep.COMPANY_DISCOVERY,
            OnboardingStep.DOCUMENT_UPLOAD,
        ):
            decision["emphasize"] = "document_upload"
            decision["reasoning"] = "Low fact count — document upload is high-value"

        return decision

    async def _log_assessment(self, user_id: str, assessment: OODAAssessment) -> None:
        """Log OODA reasoning to episodic memory and store injections.

        Args:
            user_id: The user's ID.
            assessment: The completed OODAAssessment.
        """
        # Record in episodic memory
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            memory = EpisodicMemory()
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type="ooda_onboarding_adaptation",
                content=assessment.reasoning,
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context={
                    "reasoning": assessment.reasoning,
                    "decision": assessment.decision,
                },
            )
            await memory.store_episode(episode)
        except Exception as e:
            logger.warning("OODA episodic log failed: %s", e)

        # Store injections for frontend to pick up
        if assessment.decision.get("inject_questions"):
            state = await self._get_onboarding_state(user_id)
            metadata: dict[str, Any] = (state or {}).get("metadata", {})
            injections: dict[str, list[dict[str, Any]]] = metadata.get("ooda_injections", {})

            for q in assessment.decision["inject_questions"]:
                step = q.get("insert_after_step", "")
                if step not in injections:
                    injections[step] = []
                injections[step].append(q)

            self._db.table("onboarding_state").update(
                {"metadata": {**metadata, "ooda_injections": injections}}
            ).eq("user_id", user_id).execute()

    async def _get_onboarding_state(self, user_id: str) -> dict[str, Any] | None:
        """Fetch raw onboarding state from DB.

        Args:
            user_id: The user's ID.

        Returns:
            Raw state dict or None.
        """
        response = (
            self._db.table("onboarding_state")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if response and response.data:
            return cast(dict[str, Any], response.data)
        return None

    async def _get_classification(self, user_id: str) -> dict[str, Any] | None:
        """Get company classification for user.

        Args:
            user_id: The user's ID.

        Returns:
            Classification dict or None.
        """
        try:
            response = (
                self._db.table("onboarding_state")
                .select("metadata")
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if response and response.data:
                row = cast(dict[str, Any], response.data)
                metadata: dict[str, Any] = row.get("metadata", {})
                if metadata.get("classification"):
                    return cast(dict[str, Any], metadata["classification"])

            # Fall back to company settings
            profile = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if profile and profile.data:
                profile_row = cast(dict[str, Any], profile.data)
                if profile_row.get("company_id"):
                    company = (
                        self._db.table("companies")
                        .select("settings")
                        .eq("id", profile_row["company_id"])
                        .maybe_single()
                        .execute()
                    )
                    if company and company.data:
                        company_row = cast(dict[str, Any], company.data)
                        settings: dict[str, Any] = company_row.get("settings", {})
                        if settings.get("classification"):
                            return cast(dict[str, Any], settings["classification"])
        except Exception as e:
            logger.warning("Failed to get classification: %s", e)

        return None
