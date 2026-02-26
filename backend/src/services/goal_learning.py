"""Goal learning service for retrospective analysis and playbook generation.

Provides a learning loop on top of goal execution:
- Extract reusable playbooks from successful goals
- Generate failure retrospectives with root cause analysis
- Match existing playbooks when planning new goals
- Collect and apply user feedback on goal outcomes
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.core.persona import LAYER_1_CORE_IDENTITY

logger = logging.getLogger(__name__)


class GoalLearningService:
    """Learns from goal outcomes to improve future execution."""

    def __init__(self) -> None:
        from src.db.supabase import get_supabase_client

        self._db = get_supabase_client()

    # ── Completion learning ─────────────────────────────────────

    async def process_goal_completion(
        self,
        user_id: str,
        goal_id: str,
        retro: dict[str, Any],
    ) -> None:
        """Learn from a successfully completed goal.

        Checks for an existing matching playbook. If found, merges
        success data. Otherwise extracts a new playbook via LLM.

        Args:
            user_id: The user who owns the goal.
            goal_id: The completed goal ID.
            retro: The retrospective data generated for this goal.
        """
        # Fetch goal and plan data
        goal = self._fetch_goal(goal_id, user_id)
        if not goal:
            return

        plan_data = self._fetch_plan(goal_id)

        # Check if this was already executed from a playbook
        existing_playbook_id = plan_data.get("playbook_id") if plan_data else None
        if existing_playbook_id:
            await self._update_playbook_on_success(existing_playbook_id, goal_id, retro)
            return

        # Try to find a matching playbook to merge into
        goal_type = goal.get("goal_type", "")
        match = await self.find_matching_playbook(
            user_id,
            goal.get("title", ""),
            goal.get("description", ""),
            goal_type,
        )

        if match and match.get("confidence", 0) >= 0.7:
            await self._update_playbook_on_success(
                match["playbook"]["id"], goal_id, retro
            )
        else:
            # Extract a new playbook
            plan = plan_data.get("plan") if plan_data else None
            if plan:
                await self._extract_playbook(user_id, goal_id, retro, plan, goal)

    async def _update_playbook_on_success(
        self,
        playbook_id: str,
        goal_id: str,
        retro: dict[str, Any],
    ) -> None:
        """Merge success data into an existing playbook."""
        try:
            result = (
                self._db.table("goal_playbooks")
                .select("*")
                .eq("id", playbook_id)
                .maybe_single()
                .execute()
            )
            if not result or not result.data:
                return

            pb = result.data
            source_ids = pb.get("source_goal_ids", []) or []
            if goal_id not in source_ids:
                source_ids.append(goal_id)

            # Merge success metrics
            metrics = pb.get("success_metrics", {}) or {}
            retro_effectiveness = retro.get("agent_effectiveness", {})
            if retro_effectiveness:
                existing_eff = metrics.get("agent_effectiveness", {})
                for agent, data in retro_effectiveness.items():
                    if agent not in existing_eff:
                        existing_eff[agent] = data
                metrics["agent_effectiveness"] = existing_eff

            self._db.table("goal_playbooks").update({
                "times_succeeded": pb.get("times_succeeded", 0) + 1,
                "source_goal_ids": source_ids,
                "success_metrics": metrics,
                "updated_at": datetime.now(UTC).isoformat(),
            }).eq("id", playbook_id).execute()

            logger.info(
                "Updated playbook on goal success",
                extra={"playbook_id": playbook_id, "goal_id": goal_id},
            )
        except Exception as e:
            logger.debug("Failed to update playbook on success: %s", e)

    async def _extract_playbook(
        self,
        user_id: str,
        goal_id: str,
        retro: dict[str, Any],
        plan: dict[str, Any] | str,
        goal: dict[str, Any],
    ) -> str | None:
        """Extract a reusable playbook from a successful goal via LLM.

        Generalizes specific names/values into placeholders and generates
        a trigger pattern for future matching.

        Args:
            user_id: The user who owns the goal.
            goal_id: The completed goal ID.
            retro: The retrospective data.
            plan: The execution plan (dict or JSON string).
            goal: The goal record.

        Returns:
            The new playbook ID, or None if extraction failed.
        """
        from src.core.llm import LLMClient

        if isinstance(plan, str):
            try:
                plan = json.loads(plan)
            except json.JSONDecodeError:
                plan = {"raw": plan}

        tasks = plan.get("tasks", []) if isinstance(plan, dict) else []

        task_prompt = (
            "Analyze this completed goal and its execution plan to extract a reusable playbook template.\n\n"
            f"Goal title: {goal.get('title', '')}\n"
            f"Goal description: {goal.get('description', '')}\n"
            f"Goal type: {goal.get('goal_type', '')}\n"
            f"Execution plan tasks: {json.dumps(tasks, default=str)}\n"
            f"Retrospective: {json.dumps(retro, default=str)}\n\n"
            "Create a generalized playbook by:\n"
            "1. Replacing specific company/people names with placeholders like "
            "{{target_company}}, {{contact_name}}, {{therapeutic_area}}\n"
            "2. Writing a natural language trigger_pattern describing when to use this\n"
            "3. Extracting keywords for fast pre-filtering\n"
            "4. Summarizing success metrics\n\n"
            "Respond with ONLY a JSON object:\n"
            "{\n"
            '  "playbook_name": "Short descriptive name",\n'
            '  "description": "What this playbook does",\n'
            '  "trigger_pattern": "Natural language description of when to use this playbook",\n'
            '  "keywords": ["keyword1", "keyword2"],\n'
            '  "plan_template": [{"title": "...", "description": "...", "agent": "...", '
            '"tools_needed": [], "estimated_minutes": 30}],\n'
            '  "execution_mode": "sequential|parallel|mixed",\n'
            '  "success_metrics": {"avg_duration_minutes": 0, "key_agents": []}\n'
            "}"
        )

        llm = LLMClient()
        try:
            # Build with ARIA identity for voice consistency
            system_prompt = LAYER_1_CORE_IDENTITY

            raw = await llm.generate_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": task_prompt},
                ],
                max_tokens=2048,
                temperature=0.3,
            )
            playbook_data = json.loads(raw)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Playbook extraction failed: %s", exc)
            return None

        playbook_id = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()

        try:
            self._db.table("goal_playbooks").insert({
                "id": playbook_id,
                "user_id": user_id,
                "playbook_name": playbook_data.get("playbook_name", f"Playbook from {goal.get('title', 'goal')}"),
                "description": playbook_data.get("description", ""),
                "trigger_pattern": playbook_data.get("trigger_pattern", ""),
                "goal_type": goal.get("goal_type", ""),
                "keywords": playbook_data.get("keywords", []),
                "plan_template": playbook_data.get("plan_template", []),
                "execution_mode": playbook_data.get("execution_mode", "sequential"),
                "source_goal_ids": [goal_id],
                "success_metrics": playbook_data.get("success_metrics", {}),
                "negative_patterns": [],
                "times_used": 0,
                "times_succeeded": 1,
                "times_failed": 0,
                "is_active": True,
                "is_shared": False,
                "version": 1,
                "created_at": now,
                "updated_at": now,
            }).execute()

            logger.info(
                "Extracted new playbook from goal",
                extra={
                    "playbook_id": playbook_id,
                    "goal_id": goal_id,
                    "playbook_name": playbook_data.get("playbook_name"),
                },
            )
            return playbook_id
        except Exception as e:
            logger.warning("Failed to store extracted playbook: %s", e)
            return None

    # ── Failure learning ────────────────────────────────────────

    async def process_goal_failure(
        self,
        user_id: str,
        goal_id: str,
        error: str,
    ) -> None:
        """Learn from a failed goal execution.

        Generates a failure-focused retrospective via LLM and stores it.
        If a matching playbook exists, appends to its negative_patterns.

        Args:
            user_id: The user who owns the goal.
            goal_id: The failed goal ID.
            error: The error message from the failure.
        """
        from src.core.llm import LLMClient

        goal = self._fetch_goal(goal_id, user_id)
        if not goal:
            return

        plan_data = self._fetch_plan(goal_id)

        # Generate failure retrospective
        task_prompt = (
            "Analyze this failed goal execution.\n\n"
            f"Goal title: {goal.get('title', '')}\n"
            f"Goal description: {goal.get('description', '')}\n"
            f"Goal type: {goal.get('goal_type', '')}\n"
            f"Error: {error}\n"
            f"Execution plan: {json.dumps(plan_data.get('plan', {}), default=str) if plan_data else 'None'}\n\n"
            "Analyze the failure and respond with ONLY a JSON object:\n"
            "{\n"
            '  "summary": "Brief description of what happened",\n'
            '  "root_cause": "Primary reason for failure",\n'
            '  "failed_step": "Which step failed and why",\n'
            '  "what_worked": ["Steps that completed successfully"],\n'
            '  "what_didnt": ["What went wrong"],\n'
            '  "retry_strategy": "How to approach this differently next time",\n'
            '  "warning_for_similar": "What to watch out for in similar goals",\n'
            '  "learnings": ["Key takeaways"]\n'
            "}"
        )

        llm = LLMClient()
        try:
            # Build with ARIA identity for voice consistency
            system_prompt = LAYER_1_CORE_IDENTITY

            raw = await llm.generate_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": task_prompt},
                ],
                max_tokens=1024,
                temperature=0.3,
            )
            failure_data = json.loads(raw)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failure retrospective generation failed: %s", exc)
            failure_data = {
                "summary": f"Goal failed: {error}",
                "root_cause": error,
                "failed_step": "Unknown",
                "what_worked": [],
                "what_didnt": [error],
                "retry_strategy": "Review error and retry",
                "warning_for_similar": "",
                "learnings": [],
            }

        # Store failure retrospective
        now = datetime.now(UTC).isoformat()
        try:
            self._db.table("goal_retrospectives").upsert(
                {
                    "goal_id": goal_id,
                    "summary": failure_data.get("summary", ""),
                    "what_worked": failure_data.get("what_worked", []),
                    "what_didnt": failure_data.get("what_didnt", []),
                    "time_analysis": {},
                    "agent_effectiveness": {},
                    "learnings": failure_data.get("learnings", []),
                    "metadata": {
                        "type": "failure",
                        "root_cause": failure_data.get("root_cause", ""),
                        "failed_step": failure_data.get("failed_step", ""),
                        "retry_strategy": failure_data.get("retry_strategy", ""),
                        "warning_for_similar": failure_data.get("warning_for_similar", ""),
                        "error": error,
                    },
                    "updated_at": now,
                },
                on_conflict="goal_id",
            ).execute()
        except Exception as e:
            logger.debug("Failed to store failure retrospective: %s", e)

        # Update matching playbook with negative pattern
        playbook_id = plan_data.get("playbook_id") if plan_data else None
        if playbook_id:
            await self._add_negative_pattern(playbook_id, goal_id, failure_data)
        else:
            # Try to find a matching playbook to warn
            goal_type = goal.get("goal_type", "")
            match = await self.find_matching_playbook(
                user_id,
                goal.get("title", ""),
                goal.get("description", ""),
                goal_type,
            )
            if match and match.get("confidence", 0) >= 0.6:
                await self._add_negative_pattern(
                    match["playbook"]["id"], goal_id, failure_data
                )
            else:
                # Store as standalone failure warning in procedural memory
                await self._store_failure_as_procedural(user_id, goal_id, goal, failure_data)

    async def _add_negative_pattern(
        self,
        playbook_id: str,
        goal_id: str,
        failure_data: dict[str, Any],
    ) -> None:
        """Add a negative pattern warning to an existing playbook."""
        try:
            result = (
                self._db.table("goal_playbooks")
                .select("negative_patterns, times_failed")
                .eq("id", playbook_id)
                .maybe_single()
                .execute()
            )
            if not result or not result.data:
                return

            patterns = result.data.get("negative_patterns", []) or []
            patterns.append({
                "goal_id": goal_id,
                "root_cause": failure_data.get("root_cause", ""),
                "warning": failure_data.get("warning_for_similar", ""),
                "retry_strategy": failure_data.get("retry_strategy", ""),
                "recorded_at": datetime.now(UTC).isoformat(),
            })

            times_failed = result.data.get("times_failed", 0) + 1

            update: dict[str, Any] = {
                "negative_patterns": patterns,
                "times_failed": times_failed,
                "updated_at": datetime.now(UTC).isoformat(),
            }

            # Deactivate playbook if failure ratio is too high
            times_succeeded = result.data.get("times_succeeded", 0)
            total = times_succeeded + times_failed
            if total >= 3 and times_failed / total > 0.5:
                update["is_active"] = False
                logger.info(
                    "Deactivating playbook due to high failure rate",
                    extra={"playbook_id": playbook_id, "failure_rate": times_failed / total},
                )

            self._db.table("goal_playbooks").update(update).eq("id", playbook_id).execute()
        except Exception as e:
            logger.debug("Failed to add negative pattern to playbook: %s", e)

    async def _store_failure_as_procedural(
        self,
        user_id: str,
        goal_id: str,
        goal: dict[str, Any],
        failure_data: dict[str, Any],
    ) -> None:
        """Store a standalone failure warning in procedural memories."""
        try:
            from src.memory.procedural import ProceduralMemory, Workflow

            procedural = ProceduralMemory()
            workflow = Workflow(
                id=str(uuid.uuid4()),
                user_id=user_id,
                workflow_name=f"FAILURE WARNING: {goal.get('title', goal_id)}",
                description=failure_data.get("summary", ""),
                trigger_conditions={
                    "goal_type": goal.get("goal_type", ""),
                    "pattern_type": "failure_warning",
                },
                steps=[{
                    "title": "Warning",
                    "description": failure_data.get("warning_for_similar", ""),
                    "root_cause": failure_data.get("root_cause", ""),
                    "retry_strategy": failure_data.get("retry_strategy", ""),
                }],
                success_count=0,
                failure_count=1,
                is_shared=False,
                version=1,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            await procedural.create_workflow(workflow)
        except Exception as e:
            logger.debug("Failed to store failure as procedural memory: %s", e)

    # ── Playbook matching ───────────────────────────────────────

    async def find_matching_playbook(
        self,
        user_id: str,
        goal_title: str,
        goal_description: str,
        goal_type: str,
    ) -> dict[str, Any] | None:
        """Find the best matching playbook for a new goal.

        Pre-filters by goal_type and is_active, then uses LLM to score
        candidates against the goal description.

        Args:
            user_id: The user to find playbooks for.
            goal_title: The new goal's title.
            goal_description: The new goal's description.
            goal_type: The new goal's type.

        Returns:
            Dict with playbook, confidence, reasoning, and adaptation_notes,
            or None if no match found.
        """
        # Pre-filter candidates
        try:
            query = (
                self._db.table("goal_playbooks")
                .select("*")
                .eq("user_id", user_id)
                .eq("is_active", True)
            )
            if goal_type:
                query = query.eq("goal_type", goal_type)

            result = query.order("times_succeeded", desc=True).limit(10).execute()

            if not result or not result.data:
                return None

            candidates = result.data
        except Exception as e:
            logger.debug("Failed to query playbooks: %s", e)
            return None

        # Single candidate with high success rate — skip LLM
        if len(candidates) == 1:
            pb = candidates[0]
            total = pb.get("times_succeeded", 0) + pb.get("times_failed", 0)
            if total > 0 and pb.get("times_succeeded", 0) / total >= 0.7:
                return {
                    "playbook": pb,
                    "confidence": 0.75,
                    "reasoning": f"Only matching playbook with {pb['times_succeeded']}/{total} success rate",
                    "adaptation_notes": "",
                }

        # Use LLM to score candidates
        from src.core.llm import LLMClient

        candidate_summaries = []
        for i, pb in enumerate(candidates):
            candidate_summaries.append(
                f"[{i}] {pb['playbook_name']}: {pb['trigger_pattern']} "
                f"(succeeded {pb.get('times_succeeded', 0)}x, "
                f"failed {pb.get('times_failed', 0)}x)"
            )

        task_prompt = (
            "Match a goal to the best playbook.\n\n"
            f"New goal title: {goal_title}\n"
            f"New goal description: {goal_description or 'None'}\n"
            f"Goal type: {goal_type}\n\n"
            "Available playbooks:\n"
            + "\n".join(candidate_summaries)
            + "\n\n"
            "Respond with ONLY a JSON object:\n"
            "{\n"
            '  "best_index": 0,\n'
            '  "confidence": 0.0,\n'
            '  "reasoning": "Why this playbook matches",\n'
            '  "adaptation_notes": "How to adapt the template for this specific goal"\n'
            "}\n\n"
            "Set confidence to 0.0 if none of the playbooks are a good match."
        )

        llm = LLMClient()
        try:
            # Build with ARIA identity for voice consistency
            system_prompt = LAYER_1_CORE_IDENTITY

            raw = await llm.generate_response(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": task_prompt},
                ],
                max_tokens=512,
                temperature=0.1,
            )
            match_data = json.loads(raw)
        except (json.JSONDecodeError, Exception) as exc:
            logger.debug("Playbook matching LLM call failed: %s", exc)
            return None

        confidence = match_data.get("confidence", 0)
        if confidence < 0.6:
            return None

        best_idx = match_data.get("best_index", 0)
        if best_idx < 0 or best_idx >= len(candidates):
            return None

        return {
            "playbook": candidates[best_idx],
            "confidence": confidence,
            "reasoning": match_data.get("reasoning", ""),
            "adaptation_notes": match_data.get("adaptation_notes", ""),
        }

    # ── User feedback ───────────────────────────────────────────

    async def record_goal_feedback(
        self,
        user_id: str,
        goal_id: str,
        rating: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Record user feedback on a completed goal.

        Upserts into goal_feedback, then updates the linked playbook's
        feedback counts. Deactivates the playbook if negative feedback
        ratio exceeds threshold.

        Args:
            user_id: The user submitting feedback.
            goal_id: The goal being rated.
            rating: 'up' or 'down'.
            comment: Optional comment.

        Returns:
            The stored feedback record.
        """
        now = datetime.now(UTC).isoformat()

        # Look up playbook linked to this goal
        playbook_id = None
        try:
            plan_result = (
                self._db.table("goal_execution_plans")
                .select("playbook_id")
                .eq("goal_id", goal_id)
                .order("created_at", desc=True)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if plan_result and plan_result.data:
                playbook_id = plan_result.data.get("playbook_id")
        except Exception:
            pass

        # Build feedback context
        feedback_context: dict[str, Any] = {}
        if playbook_id:
            feedback_context["playbook_id"] = playbook_id
        try:
            goal_result = (
                self._db.table("goals")
                .select("goal_type")
                .eq("id", goal_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            if goal_result and goal_result.data:
                feedback_context["goal_type"] = goal_result.data.get("goal_type")
        except Exception:
            pass

        # Upsert feedback
        result = (
            self._db.table("goal_feedback")
            .upsert(
                {
                    "user_id": user_id,
                    "goal_id": goal_id,
                    "rating": rating,
                    "comment": comment,
                    "feedback_context": feedback_context,
                    "updated_at": now,
                },
                on_conflict="user_id,goal_id",
            )
            .execute()
        )

        feedback = result.data[0] if result.data else {}

        # Update playbook feedback counts
        if playbook_id:
            await self._update_playbook_feedback(playbook_id, rating)

        logger.info(
            "Recorded goal feedback",
            extra={
                "goal_id": goal_id,
                "rating": rating,
                "playbook_id": playbook_id,
            },
        )

        return feedback

    async def _update_playbook_feedback(
        self,
        playbook_id: str,
        rating: str,
    ) -> None:
        """Update playbook feedback counts and deactivate if warranted."""
        try:
            result = (
                self._db.table("goal_playbooks")
                .select("positive_feedback_count, negative_feedback_count")
                .eq("id", playbook_id)
                .maybe_single()
                .execute()
            )
            if not result or not result.data:
                return

            pos = result.data.get("positive_feedback_count", 0)
            neg = result.data.get("negative_feedback_count", 0)

            update: dict[str, Any] = {"updated_at": datetime.now(UTC).isoformat()}
            if rating == "up":
                update["positive_feedback_count"] = pos + 1
                pos += 1
            else:
                update["negative_feedback_count"] = neg + 1
                neg += 1

            # Deactivate if feedback is overwhelmingly negative
            total = pos + neg
            if total >= 3 and neg / total > 0.6:
                update["is_active"] = False
                logger.info(
                    "Deactivating playbook due to negative feedback",
                    extra={"playbook_id": playbook_id, "neg_ratio": neg / total},
                )

            self._db.table("goal_playbooks").update(update).eq("id", playbook_id).execute()
        except Exception as e:
            logger.debug("Failed to update playbook feedback counts: %s", e)

    # ── Helpers ─────────────────────────────────────────────────

    def _fetch_goal(self, goal_id: str, user_id: str) -> dict[str, Any] | None:
        """Fetch a goal record."""
        try:
            result = (
                self._db.table("goals")
                .select("*")
                .eq("id", goal_id)
                .eq("user_id", user_id)
                .maybe_single()
                .execute()
            )
            return result.data if result and result.data else None
        except Exception as e:
            logger.debug("Failed to fetch goal %s: %s", goal_id, e)
            return None

    def _fetch_plan(self, goal_id: str) -> dict[str, Any] | None:
        """Fetch the latest execution plan for a goal."""
        try:
            result = (
                self._db.table("goal_execution_plans")
                .select("plan, tasks, playbook_id")
                .eq("goal_id", goal_id)
                .order("created_at", desc=True)
                .limit(1)
                .maybe_single()
                .execute()
            )
            if not result or not result.data:
                return None

            data = result.data
            plan_raw = data.get("plan") or data.get("tasks", "{}")
            plan = json.loads(plan_raw) if isinstance(plan_raw, str) else plan_raw

            return {
                "plan": plan,
                "playbook_id": data.get("playbook_id"),
            }
        except Exception as e:
            logger.debug("Failed to fetch plan for goal %s: %s", goal_id, e)
            return None
