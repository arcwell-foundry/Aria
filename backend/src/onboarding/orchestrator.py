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

        Also backfills step_data from existing database records if missing
        (for users who completed steps before step_data persistence was added).

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

            # Backfill step_data from existing database records if missing
            state = await self._backfill_step_data(user_id, state)

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

    async def _backfill_step_data(
        self, user_id: str, state: OnboardingState
    ) -> OnboardingState:
        """Backfill step_data from existing database records.

        This handles users who completed steps before step_data persistence
        was added, ensuring their forms are pre-filled when navigating back.

        Args:
            user_id: The authenticated user's ID.
            state: Current onboarding state.

        Returns:
            Updated state with backfilled step_data.
        """
        step_data = dict(state.step_data)
        updated = False

        # Backfill company_discovery from companies table
        if "company_discovery" not in step_data and OnboardingStep.COMPANY_DISCOVERY.value in state.completed_steps:
            profile = (
                self._db.table("user_profiles")
                .select("company_id, companies(name, domain, website)")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if profile and profile.data:
                company = profile.data.get("companies", {})
                if company:
                    step_data["company_discovery"] = {
                        "company_name": company.get("name", ""),
                        "website": company.get("website", "") or f"https://{company.get('domain', '')}",
                        "email": "",  # Can't retrieve from auth for privacy
                        "company_id": profile.data.get("company_id"),
                    }
                    updated = True

        # Backfill user_profile from user_profiles table
        if "user_profile" not in step_data and OnboardingStep.USER_PROFILE.value in state.completed_steps:
            profile = (
                self._db.table("user_profiles")
                .select("full_name, title, department, linkedin_url, phone, role_type")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if profile and profile.data:
                step_data["user_profile"] = {
                    "full_name": profile.data.get("full_name", ""),
                    "title": profile.data.get("title", ""),
                    "department": profile.data.get("department", ""),
                    "linkedin_url": profile.data.get("linkedin_url", ""),
                    "phone": profile.data.get("phone", ""),
                    "role_type": profile.data.get("role_type", ""),
                }
                updated = True

        if updated:
            # Update the state and persist
            state.step_data = step_data
            self._db.table("onboarding_state").update({"step_data": step_data}).eq(
                "user_id", user_id
            ).execute()
            logger.info(
                "Backfilled step_data for user",
                extra={"user_id": user_id, "keys": list(step_data.keys())},
            )

        return state

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

        # Idempotency: if the step was already completed, return current state
        if step.value in current.completed_steps:
            return self._build_response(current)

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

        # Record procedural memory for step completion (P2-15)
        await self._record_procedural_memory(user_id, step, step_data)

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

        # Onboarding exists but not complete -> route to onboarding page
        return "onboarding"

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
        step_data: dict[str, Any],
    ) -> None:
        """Trigger async background processing for a completed step.

        Dispatches to step-specific memory services so that each step's
        data flows into the appropriate memory systems (Integration Checklist).

        Args:
            user_id: The user's ID.
            step: The completed step.
            step_data: Data collected during the step.
        """
        logger.info(
            "Triggering background processing for step",
            extra={"step": step.value, "user_id": user_id},
        )

        try:
            if step == OnboardingStep.USER_PROFILE:
                await self._process_user_profile(user_id, step_data)
            elif step == OnboardingStep.INTEGRATION_WIZARD:
                await self._process_integration_wizard(user_id)
        except Exception as e:
            # Non-critical — log and continue so step completion isn't blocked
            logger.warning(
                "Background step processing failed",
                extra={"step": step.value, "user_id": user_id, "error": str(e)},
            )

    async def _process_user_profile(
        self,
        user_id: str,
        step_data: dict[str, Any],
    ) -> None:
        """Store user profile in user_profiles table and Semantic Memory.

        Updates the user_profiles table with structured fields, merges into
        semantic memory via ProfileMergeService, and triggers LinkedIn research
        if a LinkedIn URL is provided.

        Args:
            user_id: The user's ID.
            step_data: Profile data from the step (full_name, title, etc.).
        """
        if not step_data:
            return

        # Update user_profiles table with structured fields
        profile_update: dict[str, Any] = {}
        if step_data.get("full_name"):
            profile_update["full_name"] = step_data["full_name"]
        if step_data.get("title"):
            profile_update["title"] = step_data["title"]
        if step_data.get("department"):
            profile_update["department"] = step_data["department"]
        if step_data.get("linkedin_url"):
            profile_update["linkedin_url"] = step_data["linkedin_url"]
        if step_data.get("phone"):
            profile_update["phone"] = step_data["phone"]

        if profile_update:
            self._db.table("user_profiles").update(profile_update).eq("id", user_id).execute()

        # Merge into semantic memory via ProfileMergeService
        from src.memory.profile_merge import ProfileMergeService

        merge_service = ProfileMergeService()
        old_data: dict[str, Any] = {}
        await merge_service.process_update(user_id, old_data, step_data)

        # Trigger LinkedIn research if URL provided (non-blocking background task)
        linkedin_url = step_data.get("linkedin_url")
        if linkedin_url and isinstance(linkedin_url, str) and linkedin_url.strip():
            asyncio.create_task(self._trigger_linkedin_research(user_id, step_data))

        # Update readiness score for digital_twin (profile data contributes to identity)
        try:
            await self.update_readiness_scores(user_id, {"digital_twin": 10.0})
        except Exception as e:
            logger.warning(
                "Failed to update readiness after profile merge",
                extra={"user_id": user_id, "error": str(e)},
            )

        logger.info(
            "User profile processed",
            extra={"user_id": user_id, "fields": list(step_data.keys())},
        )

    async def _trigger_linkedin_research(
        self,
        user_id: str,
        step_data: dict[str, Any],
    ) -> None:
        """Background task to research LinkedIn profile.

        Uses LinkedInResearchService to enrich user profile data from LinkedIn
        and store it in the digital twin and semantic memory.

        Args:
            user_id: The user's ID.
            step_data: Profile data including linkedin_url, full_name, title.
        """
        try:
            # Get company name for context
            profile = (
                self._db.table("user_profiles")
                .select("company_id, companies(name)")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )

            company_name = ""
            if profile and profile.data:
                company = profile.data.get("companies")
                if company:
                    company_name = company.get("name", "")

            from src.onboarding.linkedin_research import LinkedInResearchService

            service = LinkedInResearchService()
            await service.research_profile(
                user_id=user_id,
                linkedin_url=step_data.get("linkedin_url", ""),
                full_name=step_data.get("full_name", ""),
                job_title=step_data.get("title", ""),
                company_name=company_name,
            )

            logger.info(
                "LinkedIn research completed",
                extra={"user_id": user_id},
            )
        except Exception as e:
            logger.warning(
                "LinkedIn research failed (non-blocking)",
                extra={"user_id": user_id, "error": str(e)},
            )

    async def _process_integration_wizard(self, user_id: str) -> None:
        """Enrich integration_wizard step_data with actual connection flags.

        The IntegrationWizardService stores connections in user_integrations
        but does not populate step_data. The activation flow reads
        crm_connected/email_connected from step_data, so we bridge the gap
        by querying actual integration status and patching step_data.

        Args:
            user_id: The user's ID.
        """
        # Query actual integration connections
        result = (
            self._db.table("user_integrations")
            .select("integration_type, status")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )

        connected_providers = [row["integration_type"] for row in (result.data or [])]
        connected_lower = {p.lower() for p in connected_providers if p}

        crm_types = {"salesforce", "hubspot"}
        email_types = {"gmail", "outlook", "google", "microsoft"}
        calendar_types = {"googlecalendar", "outlook365calendar", "google_calendar", "outlook_calendar"}

        integration_flags: dict[str, Any] = {
            "crm_connected": bool(crm_types & connected_lower),
            "email_connected": bool(email_types & connected_lower),
            "calendar_connected": bool(calendar_types & connected_lower),
            "slack_connected": "slack" in connected_lower,
            "connected_providers": connected_providers,
        }

        # Patch the stored step_data so activation.py can read the flags
        state = await self._get_state(user_id)
        if state:
            merged = {**state.step_data}
            existing_wizard_data = merged.get("integration_wizard", {})
            if isinstance(existing_wizard_data, dict):
                merged["integration_wizard"] = {**existing_wizard_data, **integration_flags}
            else:
                merged["integration_wizard"] = integration_flags

            self._db.table("onboarding_state").update({"step_data": merged}).eq(
                "user_id", user_id
            ).execute()

        logger.info(
            "Integration wizard step_data enriched with connection flags",
            extra={"user_id": user_id, "flags": integration_flags},
        )

        # Update readiness score for integrations domain
        connected_count = len(connected_providers)
        # Score: 0 = no integrations, 30 = 1, 60 = 2, 80 = 3+
        if connected_count >= 3:
            integrations_score = 80.0
        elif connected_count == 2:
            integrations_score = 60.0
        elif connected_count == 1:
            integrations_score = 30.0
        else:
            integrations_score = 0.0

        try:
            await self.update_readiness_scores(user_id, {"integrations": integrations_score})
        except Exception as e:
            logger.warning(
                "Failed to update integrations readiness",
                extra={"user_id": user_id, "error": str(e)},
            )

        # Create knowledge gaps for missing integrations → Prospective Memory
        missing_categories: list[str] = []
        if not integration_flags["crm_connected"]:
            missing_categories.append("CRM (Salesforce/HubSpot)")
        if not integration_flags["email_connected"]:
            missing_categories.append("Email (Gmail/Outlook)")
        if not integration_flags["calendar_connected"]:
            missing_categories.append("Calendar")

        if missing_categories:
            try:
                for category in missing_categories:
                    self._db.table("prospective_memories").insert(
                        {
                            "user_id": user_id,
                            "task": f"Connect {category} integration for enhanced ARIA capabilities",
                            "status": "pending",
                            "metadata": {
                                "type": "knowledge_gap",
                                "priority": "medium",
                                "source": "integration_wizard",
                                "gap_domain": "integrations",
                            },
                        }
                    ).execute()
            except Exception as e:
                logger.warning(
                    "Failed to create integration gap entries",
                    extra={"user_id": user_id, "error": str(e)},
                )

        # Record episodic memory of integration wizard completion
        await self._record_episodic_event(
            user_id,
            "integration_wizard_completed",
            {
                "connected_providers": connected_providers,
                "connected_count": connected_count,
                "integrations_readiness": integrations_score,
                "missing_categories": missing_categories,
            },
        )

    async def _record_procedural_memory(
        self,
        user_id: str,
        step: OnboardingStep,
        step_data: dict[str, Any],
    ) -> None:
        """Record an onboarding step as a procedural memory workflow pattern.

        Feeds the adaptive controller's learning about which patterns
        lead to higher readiness scores.

        Args:
            user_id: The user's ID.
            step: The completed onboarding step.
            step_data: Data collected during the step.
        """
        try:
            from src.memory.procedural import ProceduralMemory, Workflow

            memory = ProceduralMemory()
            now = datetime.now(UTC)

            # Determine data quality: how many non-empty fields were provided
            provided_fields = [k for k, v in step_data.items() if v] if step_data else []
            data_quality = min(100, len(provided_fields) * 20) if provided_fields else 0

            workflow = Workflow(
                id=str(uuid.uuid4()),
                user_id=user_id,
                workflow_name=f"onboarding_{step.value}",
                description=f"Onboarding step '{step.value}' completed",
                trigger_conditions={
                    "event": "onboarding_step_complete",
                    "step": step.value,
                },
                steps=[
                    {
                        "action": "complete_step",
                        "step_name": step.value,
                        "data_quality_score": data_quality,
                        "fields_provided": provided_fields,
                        "fields_skipped": [k for k, v in (step_data or {}).items() if not v],
                    }
                ],
                success_count=1,
                failure_count=0,
                is_shared=False,
                version=1,
                created_at=now,
                updated_at=now,
            )
            await memory.create_workflow(workflow)
        except Exception as e:
            # Non-critical — log and continue
            logger.warning(
                "Failed to record procedural memory for step",
                extra={"step": step.value, "error": str(e)},
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
