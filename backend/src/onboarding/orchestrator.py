"""Onboarding orchestrator and state machine for ARIA Intelligence Initialization.

Manages the onboarding flow: step progression, skip logic, resume capability,
and triggers background processing on step completion. Each step seeds ARIA's
memory systems, making her measurably smarter about the user and their company.
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from src.db.supabase import SupabaseClient
from src.onboarding.models import (
    SKIPPABLE_STEPS,
    STEP_ORDER,
    OnboardingState,
    OnboardingStateResponse,
    OnboardingStep,
    ReadinessScores,
)

logger = logging.getLogger(__name__)


class OnboardingOrchestrator:
    """Manages onboarding state machine for new users.

    Handles step progression, skip logic, resume capability,
    and triggers background processing on step completion.
    """

    def __init__(self) -> None:
        """Initialize orchestrator with Supabase client."""
        self._db = SupabaseClient.get_client()

    async def get_or_create_state(self, user_id: str) -> OnboardingStateResponse:
        """Get existing onboarding state or create a new one for user.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            Current onboarding state with progress metadata.
        """
        response = (
            self._db.table("onboarding_state")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if response and response.data:
            state = self._parse_state(cast(dict[str, Any], response.data))
            return self._build_response(state)

        # Create new state
        new_state: dict[str, Any] = {
            "user_id": user_id,
            "current_step": OnboardingStep.COMPANY_DISCOVERY.value,
            "step_data": {},
            "completed_steps": [],
            "skipped_steps": [],
            "readiness_scores": ReadinessScores().model_dump(),
            "metadata": {},
        }
        insert_response = self._db.table("onboarding_state").insert(new_state).execute()

        logger.info(
            "Onboarding state created",
            extra={"user_id": user_id},
        )

        # Record onboarding start in episodic memory
        await self._record_episodic_event(
            user_id,
            "started",
            {"timestamp": datetime.now(UTC).isoformat()},
        )

        row = cast(dict[str, Any], insert_response.data[0])
        state = self._parse_state(row)
        return self._build_response(state)

    async def complete_step(
        self,
        user_id: str,
        step: OnboardingStep,
        step_data: dict[str, Any],
    ) -> OnboardingStateResponse:
        """Mark a step as complete and advance to the next step.

        Args:
            user_id: The authenticated user's ID.
            step: The step being completed.
            step_data: Data collected during this step.

        Returns:
            Updated onboarding state with progress metadata.

        Raises:
            ValueError: If the step doesn't match the current step or no state exists.
        """
        current = await self._get_state(user_id)
        if not current:
            raise ValueError("No onboarding state found")

        if step.value != current.current_step.value:
            raise ValueError(
                f"Cannot complete step '{step.value}' — "
                f"current step is '{current.current_step.value}'"
            )

        # Merge step data
        merged_data = {**current.step_data, step.value: step_data}
        completed = list(set(current.completed_steps + [step.value]))

        # Determine next step
        next_step = self._get_next_step(step, completed, current.skipped_steps)
        is_complete = next_step is None

        update: dict[str, Any] = {
            "current_step": next_step.value if next_step else step.value,
            "step_data": merged_data,
            "completed_steps": completed,
        }
        if is_complete:
            update["completed_at"] = datetime.now(UTC).isoformat()

        result = self._db.table("onboarding_state").update(update).eq("user_id", user_id).execute()

        # Trigger background processing (non-blocking)
        await self._trigger_step_processing(user_id, step, step_data)

        # Trigger agent activation if onboarding is complete (US-915)
        if is_complete:
            try:
                from src.onboarding.activation import OnboardingCompletionOrchestrator

                activator = OnboardingCompletionOrchestrator()
                # Run activation in background without blocking response
                asyncio.create_task(activator.activate(user_id, merged_data))
            except Exception as e:
                logger.warning(
                    "Agent activation failed to launch",
                    extra={"user_id": user_id, "error": str(e)},
                )

        # Run OODA adaptive controller (non-blocking background task)
        try:
            from src.onboarding.adaptive_controller import OnboardingOODAController

            ooda = OnboardingOODAController()
            asyncio.create_task(ooda.assess_next_step(user_id, step))
        except Exception as e:
            logger.warning("OODA assessment failed to launch: %s", e)

        # Record episodic event
        await self._record_episodic_event(
            user_id,
            "step_completed",
            {
                "step": step.value,
                "next_step": next_step.value if next_step else "complete",
            },
        )

        row = cast(dict[str, Any], result.data[0])
        state = self._parse_state(row)
        return self._build_response(state)

    async def skip_step(
        self,
        user_id: str,
        step: OnboardingStep,
        reason: str | None = None,
    ) -> OnboardingStateResponse:
        """Skip a non-critical step and advance.

        Args:
            user_id: The authenticated user's ID.
            step: The step to skip.
            reason: Optional reason for skipping.

        Returns:
            Updated onboarding state with progress metadata.

        Raises:
            ValueError: If the step is not skippable or no state exists.
        """
        if step not in SKIPPABLE_STEPS:
            raise ValueError(f"Step '{step.value}' cannot be skipped")

        current = await self._get_state(user_id)
        if not current:
            raise ValueError("No onboarding state found")

        skipped = list(set(current.skipped_steps + [step.value]))
        next_step = self._get_next_step(step, current.completed_steps, skipped)

        update: dict[str, Any] = {
            "current_step": next_step.value if next_step else step.value,
            "skipped_steps": skipped,
            "metadata": {
                **current.metadata,
                f"skip_reason_{step.value}": reason or "user_skipped",
            },
        }
        if next_step is None:
            update["completed_at"] = datetime.now(UTC).isoformat()

        result = self._db.table("onboarding_state").update(update).eq("user_id", user_id).execute()

        # Trigger agent activation if onboarding is complete via skipping (US-915)
        if next_step is None:
            try:
                from src.onboarding.activation import OnboardingCompletionOrchestrator

                activator = OnboardingCompletionOrchestrator()
                state_data = current.step_data if current else {}
                # Run activation in background without blocking response
                asyncio.create_task(activator.activate(user_id, state_data))
            except Exception as e:
                logger.warning(
                    "Agent activation failed to launch",
                    extra={"user_id": user_id, "error": str(e)},
                )

        await self._record_episodic_event(
            user_id,
            "step_skipped",
            {"step": step.value, "reason": reason},
        )

        row = cast(dict[str, Any], result.data[0])
        state = self._parse_state(row)
        return self._build_response(state)

    async def update_readiness_scores(
        self,
        user_id: str,
        updates: dict[str, float],
    ) -> None:
        """Update specific readiness sub-scores, clamped to 0-100.

        Args:
            user_id: The authenticated user's ID.
            updates: Mapping of score name to new value.
        """
        current = await self._get_state(user_id)
        if not current:
            return

        scores = current.readiness_scores.model_dump()
        for key, value in updates.items():
            if key in scores:
                scores[key] = min(100.0, max(0.0, value))

        (
            self._db.table("onboarding_state")
            .update({"readiness_scores": scores})
            .eq("user_id", user_id)
            .execute()
        )

    async def get_routing_decision(self, user_id: str) -> str:
        """Determine where to route user post-auth.

        Args:
            user_id: The authenticated user's ID.

        Returns:
            One of 'onboarding', 'resume', 'dashboard', or 'admin'.
        """
        # Check admin status
        profile_response = (
            self._db.table("user_profiles")
            .select("role")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        if profile_response and profile_response.data:
            profile_data = cast(dict[str, Any], profile_response.data)
            if profile_data.get("role") == "admin":
                return "admin"

        # Check onboarding state
        state_response = (
            self._db.table("onboarding_state")
            .select("completed_at, current_step")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )

        if not state_response or not state_response.data:
            return "onboarding"

        state_data = cast(dict[str, Any], state_response.data)
        if state_data.get("completed_at"):
            return "dashboard"

        return "resume"

    # --- Private helpers ---

    def _get_next_step(
        self,
        current: OnboardingStep,
        completed: list[str],
        skipped: list[str],
    ) -> OnboardingStep | None:
        """Get the next uncompleted, unskipped step after current.

        Args:
            current: The current step.
            completed: List of completed step values.
            skipped: List of skipped step values.

        Returns:
            The next step, or None if all remaining steps are done.
        """
        current_idx = STEP_ORDER.index(current)
        for step in STEP_ORDER[current_idx + 1 :]:
            if step.value not in completed and step.value not in skipped:
                return step
        return None

    def _build_response(self, state: OnboardingState) -> OnboardingStateResponse:
        """Build response with progress metadata.

        Args:
            state: The current onboarding state.

        Returns:
            Response with progress percentage, counts, and completion flag.
        """
        total = len(STEP_ORDER)
        completed_count = len(state.completed_steps)
        skipped_count = len(state.skipped_steps)
        effective_total = total - skipped_count

        try:
            current_idx = STEP_ORDER.index(OnboardingStep(state.current_step))
        except ValueError:
            current_idx = 0

        progress = (completed_count / effective_total * 100) if effective_total > 0 else 0

        return OnboardingStateResponse(
            state=state,
            progress_percentage=round(progress, 1),
            total_steps=total,
            completed_count=completed_count,
            current_step_index=current_idx,
            is_complete=state.completed_at is not None,
        )

    def _parse_state(self, data: dict[str, Any]) -> OnboardingState:
        """Parse raw DB row into OnboardingState model.

        Args:
            data: Row dict from the onboarding_state table.

        Returns:
            Parsed OnboardingState instance.
        """
        return OnboardingState(
            id=str(data["id"]),
            user_id=str(data["user_id"]),
            current_step=data["current_step"],
            step_data=data.get("step_data", {}),
            completed_steps=data.get("completed_steps", []),
            skipped_steps=data.get("skipped_steps", []),
            started_at=data["started_at"],
            updated_at=data["updated_at"],
            completed_at=data.get("completed_at"),
            readiness_scores=ReadinessScores(**data.get("readiness_scores", {})),
            metadata=data.get("metadata", {}),
        )

    async def _get_state(self, user_id: str) -> OnboardingState | None:
        """Fetch current state from DB.

        Args:
            user_id: The user's ID.

        Returns:
            OnboardingState if found, None otherwise.
        """
        response = (
            self._db.table("onboarding_state")
            .select("*")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
        if response and response.data:
            return self._parse_state(cast(dict[str, Any], response.data))
        return None

    async def _trigger_step_processing(
        self,
        user_id: str,
        step: OnboardingStep,
        _step_data: dict[str, Any],
    ) -> None:
        """Trigger async background processing for a completed step.

        Each step may kick off enrichment, analysis, or other
        intelligence-building processes. Concrete implementations
        come with each step's user story (US-903, US-904, etc.).

        Args:
            user_id: The user's ID.
            step: The completed step.
            _step_data: Data collected during the step (used by future implementations).
        """
        logger.info(
            "Triggering background processing for step",
            extra={"step": step.value, "user_id": user_id},
        )

    async def _record_episodic_event(
        self,
        user_id: str,
        event_type: str,
        details: dict[str, Any],
    ) -> None:
        """Record an onboarding event to episodic memory.

        Args:
            user_id: The user's ID.
            event_type: Short event label (e.g. 'started', 'step_completed').
            details: Event metadata dict.
        """
        try:
            from src.memory.episodic import Episode, EpisodicMemory

            memory = EpisodicMemory()
            now = datetime.now(UTC)
            episode = Episode(
                id=str(uuid.uuid4()),
                user_id=user_id,
                event_type=f"onboarding_{event_type}",
                content=str(details),
                participants=[],
                occurred_at=now,
                recorded_at=now,
                context=details,
            )
            await memory.store_episode(episode)
        except Exception as e:
            # Non-critical — log and continue
            logger.warning(
                "Failed to record episodic event",
                extra={"event_type": event_type, "error": str(e)},
            )
