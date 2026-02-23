"""Implication-aware skill triggering for signal-to-action pipeline.

Connects ARIA's signal radar implication detection to the skill orchestration
system. When a market signal is detected, this module analyses the non-obvious
implications against the user's portfolio and automatically maps each
actionable implication to a skill or workflow execution plan.

Flow:
    Signal detected → implication analysis (LLM + knowledge graph) →
    action mapping → execution plan creation → approval/auto-execute →
    proactive notification

Integrates with:
- ``signal_radar.py``: Consumes ``Signal`` and ``Implication`` models
- ``orchestrator.py``: Creates ``ExecutionPlan`` / ``ExecutionStep`` instances
- ``autonomy.py``: Checks risk levels for auto-execute vs approval
- ``notification_integration.py``: Pushes proactive notifications
- ``activity_service.py``: Records activity feed entries
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from src.agents.capabilities.signal_radar import Implication, Signal
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient
from src.services.activity_service import ActivityService
from src.services.notification_service import NotificationService
from src.skills.autonomy import SkillAutonomyService, SkillRiskLevel
from src.skills.orchestrator import ExecutionPlan, ExecutionStep

logger = logging.getLogger(__name__)


# ── Skill mapping constants ──────────────────────────────────────────

# Maps implication action categories to skill identifiers and risk levels.
# Each entry: (skill_path, default_risk_level)
SKILL_ACTION_MAP: dict[str, tuple[str, SkillRiskLevel]] = {
    "update_stakeholder_profile": ("aria:contact-enricher", SkillRiskLevel.LOW),
    "enrich_contact": ("aria:contact-enricher", SkillRiskLevel.LOW),
    "refresh_battle_card": ("aria:document-forge", SkillRiskLevel.LOW),
    "update_competitive_brief": ("aria:document-forge", SkillRiskLevel.LOW),
    "draft_outreach": ("aria:email-intelligence", SkillRiskLevel.MEDIUM),
    "draft_proactive_email": ("aria:email-intelligence", SkillRiskLevel.MEDIUM),
    "update_lead_health": ("aria:crm-sync", SkillRiskLevel.MEDIUM),
    "refresh_territory_analysis": ("aria:territory-planner", SkillRiskLevel.LOW),
    "update_pipeline_forecast": ("aria:financial-intel", SkillRiskLevel.LOW),
    "schedule_follow_up": ("aria:calendar-intel", SkillRiskLevel.MEDIUM),
    "regulatory_impact_review": ("aria:compliance-guardian", SkillRiskLevel.LOW),
    "clinical_trial_analysis": ("aria:trial-radar", SkillRiskLevel.LOW),
    "kol_mapping_update": ("aria:kol-mapper", SkillRiskLevel.LOW),
    "research_deep_dive": ("aria:web-intel", SkillRiskLevel.LOW),
}


# ── Domain models ────────────────────────────────────────────────────


class SkillTrigger(BaseModel):
    """A skill execution triggered by an implication.

    Maps a single implication to a concrete skill invocation with
    input data, risk assessment, and approval requirements.

    Attributes:
        trigger_id: Unique identifier for this trigger.
        implication: The source implication that prompted this trigger.
        skill_path: Path of the skill to execute (e.g. "aria:contact-enricher").
        action_type: Category of action (e.g. "update_stakeholder_profile").
        risk_level: Risk assessment for autonomy decisions.
        auto_execute: Whether this can run without user approval.
        input_data: Skill-specific input parameters.
        priority: Execution priority (1=highest, 5=lowest).
        reasoning: Why this action was selected.
    """

    trigger_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    implication: Implication
    skill_path: str
    action_type: str
    risk_level: str = "low"
    auto_execute: bool = False
    input_data: dict[str, Any] = Field(default_factory=dict)
    priority: int = 3
    reasoning: str = ""


class ImplicationPlan(BaseModel):
    """An execution plan derived from signal implications.

    Groups multiple skill triggers into a coordinated plan with
    parallel execution groups and a user-facing summary.

    Attributes:
        plan_id: Unique plan identifier.
        signal: The source market signal.
        implications: All implications detected for this signal.
        triggers: Skill triggers mapped from implications.
        execution_plan: The orchestrator ExecutionPlan (set after creation).
        summary: Human-readable summary for notification.
        created_at: When this plan was generated.
    """

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal: Signal
    implications: list[Implication] = Field(default_factory=list)
    triggers: list[SkillTrigger] = Field(default_factory=list)
    execution_plan_id: str | None = None
    summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Main service ─────────────────────────────────────────────────────


class ImplicationAwareSkillTrigger:
    """Bridges signal implication detection and skill orchestration.

    When ``process_signal_implications`` is called with a new signal, it:
    1. Runs LLM implication analysis with knowledge graph context
    2. Maps each implication to concrete skill actions
    3. Builds an execution plan with parallel groups
    4. Persists the plan (pending_approval or auto-approved)
    5. Sends a proactive notification to the user

    Usage::

        trigger = ImplicationAwareSkillTrigger(user_id="...")
        triggers = await trigger.process_signal_implications(signal)
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id
        self._llm = LLMClient()
        self._activity = ActivityService()

    def _get_db(self) -> Any:
        """Lazy Supabase client accessor."""
        return SupabaseClient.get_client()

    # ── Public API ────────────────────────────────────────────────────

    async def process_signal_implications(self, signal: Signal) -> list[SkillTrigger]:
        """Analyse a signal's implications and map them to skill triggers.

        This is the main entry point. Call it from ``signal_radar.create_alerts``
        or ``run_signal_radar_scan`` before sending plain notifications.

        Args:
            signal: The detected market signal to analyse.

        Returns:
            List of SkillTrigger objects, one per actionable implication.
            Returns empty list if no actionable implications are found.
        """
        # Step 1: Build enriched context (leads, competitors, knowledge graph)
        knowledge_context = await self._build_enriched_context()

        # Step 2: Run implication analysis with action mapping via LLM
        implications, triggers = await self._analyse_and_map(signal, knowledge_context)

        if not triggers:
            logger.info(
                "No actionable implications for signal %s",
                signal.id,
                extra={"user_id": self._user_id},
            )
            return []

        # Step 3: Apply autonomy checks — determine auto-execute vs approval
        for trigger in triggers:
            trigger.auto_execute = await self._check_autonomy(trigger)

        # Step 4: Build and persist execution plan
        plan = await self._build_execution_plan(signal, implications, triggers)

        # Step 5: Send proactive notification
        await self.proactive_notification(
            user_id=self._user_id,
            implication_plan=plan,
        )

        # Step 6: Record activity
        await self._record_activity(signal, plan)

        logger.info(
            "Implication analysis complete for signal %s: %d triggers",
            signal.id,
            len(triggers),
            extra={
                "user_id": self._user_id,
                "signal_type": signal.signal_type,
                "company": signal.company_name,
                "auto_execute_count": sum(1 for t in triggers if t.auto_execute),
            },
        )

        return triggers

    async def proactive_notification(
        self,
        user_id: str,
        implication_plan: ImplicationPlan,
    ) -> None:
        """Push a proactive notification about detected implications.

        Creates an in-app notification via the notification service and
        records the event in the activity feed. The notification includes
        a summary of what was detected, what's affected, and what actions
        ARIA has prepared.

        Args:
            user_id: Target user UUID.
            implication_plan: The plan with signal, implications, and triggers.
        """
        signal = implication_plan.signal
        triggers = implication_plan.triggers
        num_auto = sum(1 for t in triggers if t.auto_execute)
        num_approval = len(triggers) - num_auto

        # Build user-facing message
        affected_summary = self._build_affected_summary(implication_plan)
        actions_summary = self._build_actions_summary(triggers)

        message_parts = [
            f"I detected that {signal.company_name} — {signal.headline}.",
        ]
        if affected_summary:
            message_parts.append(affected_summary)
        if actions_summary:
            message_parts.append(actions_summary)
        if num_approval > 0:
            message_parts.append(f"{num_approval} action(s) need your approval.")
        if num_auto > 0:
            message_parts.append(f"{num_auto} low-risk action(s) will run automatically.")

        message = " ".join(message_parts)

        # In-app notification
        try:
            await NotificationService.create_notification(
                user_id=user_id,
                type="signal_detected",
                title=f"Signal Intelligence: {signal.company_name}",
                message=message[:500],
                link=f"/signals/{signal.id}",
                metadata={
                    "signal_id": signal.id,
                    "signal_type": signal.signal_type,
                    "company_name": signal.company_name,
                    "plan_id": implication_plan.plan_id,
                    "trigger_count": len(triggers),
                    "auto_execute_count": num_auto,
                    "approval_required_count": num_approval,
                    "implications": [
                        {
                            "description": impl.description,
                            "confidence": impl.confidence,
                        }
                        for impl in implication_plan.implications[:5]
                    ],
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to create implication notification for signal %s: %s",
                signal.id,
                exc,
            )

    # ── Internal methods ──────────────────────────────────────────────

    async def _build_enriched_context(self) -> dict[str, Any]:
        """Build enriched knowledge context for implication analysis.

        Pulls from monitored entities, leads, user profile, and recent
        signal history to give the LLM maximum context for identifying
        non-obvious implications.

        Returns:
            Dict with tracked_competitors, lead_companies, leads_detail,
            therapeutic_areas, products, company_name, recent_signals.
        """
        client = self._get_db()
        context: dict[str, Any] = {
            "tracked_competitors": [],
            "lead_companies": [],
            "leads_detail": [],
            "therapeutic_areas": [],
            "products": [],
            "company_name": "",
            "recent_signals": [],
        }

        try:
            # Monitored entities
            entities_resp = (
                client.table("monitored_entities")
                .select("entity_type, entity_name, monitoring_config")
                .eq("user_id", self._user_id)
                .eq("is_active", True)
                .execute()
            )
            for entity in entities_resp.data or []:
                if entity.get("entity_type") == "company":
                    context["tracked_competitors"].append(entity["entity_name"])
                elif entity.get("entity_type") == "topic":
                    context["therapeutic_areas"].append(entity["entity_name"])

            # Leads with detail (company, contacts, stage)
            leads_resp = (
                client.table("leads")
                .select("id, company_name, contact_name, lifecycle_stage, health_score, metadata")
                .eq("user_id", self._user_id)
                .in_("lifecycle_stage", ["active", "nurturing", "negotiation"])
                .limit(100)
                .execute()
            )
            for lead in leads_resp.data or []:
                if lead.get("company_name"):
                    context["lead_companies"].append(lead["company_name"])
                context["leads_detail"].append(
                    {
                        "id": lead["id"],
                        "company": lead.get("company_name", ""),
                        "contact": lead.get("contact_name", ""),
                        "stage": lead.get("lifecycle_stage", ""),
                        "health": lead.get("health_score", 0),
                    }
                )

            # Deduplicate lead companies
            context["lead_companies"] = list(set(context["lead_companies"]))

            # User profile from user_profiles with companies join
            profile_resp = (
                client.table("user_profiles")
                .select("company_id, companies(name, settings)")
                .eq("id", self._user_id)
                .maybe_single()
                .execute()
            )
            if profile_resp and profile_resp.data:
                company_data = profile_resp.data.get("companies")
                if company_data and isinstance(company_data, dict):
                    context["company_name"] = company_data.get("name", "")
                    # Products and therapeutic areas from company settings
                    company_settings = company_data.get("settings") or {}
                    context["products"] = company_settings.get("products", [])
                    if not context["therapeutic_areas"]:
                        context["therapeutic_areas"] = company_settings.get("therapeutic_areas", [])

            # Recent high-relevance signals (last 7 days) for pattern detection
            recent_resp = (
                client.table("market_signals")
                .select("company_name, signal_type, headline")
                .eq("user_id", self._user_id)
                .gte("relevance_score", 0.6)
                .order("detected_at", desc=True)
                .limit(10)
                .execute()
            )
            context["recent_signals"] = [
                {
                    "company": s.get("company_name", ""),
                    "type": s.get("signal_type", ""),
                    "headline": s.get("headline", ""),
                }
                for s in (recent_resp.data or [])
            ]

        except Exception as exc:
            logger.warning(
                "Failed to build enriched context for user %s: %s",
                self._user_id,
                exc,
            )

        return context

    async def _analyse_and_map(
        self,
        signal: Signal,
        knowledge_context: dict[str, Any],
    ) -> tuple[list[Implication], list[SkillTrigger]]:
        """Run LLM implication analysis and map to skill triggers.

        Uses a single LLM call that both identifies implications AND
        maps them to concrete actions, reducing latency vs two calls.

        Args:
            signal: The market signal to analyse.
            knowledge_context: Enriched user context.

        Returns:
            Tuple of (implications, skill_triggers).
        """
        prompt = self._build_analysis_prompt(signal, knowledge_context)

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are ARIA's strategic intelligence engine. Analyse "
                    "the market signal in the context of the user's portfolio "
                    "and identify non-obvious implications. For each implication, "
                    "map it to a concrete action from the available action types. "
                    "Focus on second-order effects, competitive dynamics, and "
                    "actionable opportunities. Respond with valid JSON only."
                ),
                max_tokens=3000,
                temperature=0.4,
            )

            return self._parse_analysis_response(response, signal)

        except Exception as exc:
            logger.warning(
                "Implication analysis failed for signal %s: %s",
                signal.id,
                exc,
            )
            return [], []

    def _build_analysis_prompt(
        self,
        signal: Signal,
        knowledge_context: dict[str, Any],
    ) -> str:
        """Build the combined implication + action mapping prompt.

        Args:
            signal: The market signal.
            knowledge_context: User's enriched context.

        Returns:
            Formatted prompt string.
        """
        competitors = ", ".join(knowledge_context.get("tracked_competitors", [])[:10])
        leads_detail = knowledge_context.get("leads_detail", [])
        leads_text = "\n".join(
            f"  - {lead['company']} ({lead['contact']}) — {lead['stage']}, health={lead['health']}"
            for lead in leads_detail[:15]
        )
        areas = ", ".join(knowledge_context.get("therapeutic_areas", [])[:10])
        products = ", ".join(knowledge_context.get("products", [])[:10])
        user_company = knowledge_context.get("company_name", "Unknown")
        recent = "\n".join(
            f"  - [{s['type']}] {s['company']}: {s['headline']}"
            for s in knowledge_context.get("recent_signals", [])[:5]
        )

        available_actions = "\n".join(
            f"  - {action_type}: uses {skill_path} (risk: {risk.value})"
            for action_type, (skill_path, risk) in SKILL_ACTION_MAP.items()
        )

        return f"""Analyse this market signal and identify 1-5 non-obvious implications for the user's business. For EACH implication, map it to a concrete action.

SIGNAL:
- Company: {signal.company_name}
- Type: {signal.signal_type}
- Headline: {signal.headline}
- Summary: {signal.summary}

USER CONTEXT:
- User's company: {user_company}
- Tracked competitors: {competitors or "None"}
- Therapeutic areas: {areas or "None"}
- Products: {products or "None"}
- Active leads:
{leads_text or "  None"}
- Recent signals:
{recent or "  None"}

AVAILABLE ACTIONS (pick from these):
{available_actions}

Think about:
1. Which specific leads/contacts are affected by this signal?
2. What competitive dynamics shift?
3. What proactive outreach opportunities open up?
4. What existing documents (battle cards, briefs) need refreshing?
5. Are there regulatory or pipeline implications?

Respond with JSON:
{{
  "implications": [
    {{
      "description": "Brief description of the implication",
      "affected_entities": ["entity1", "entity2"],
      "confidence": 0.0-1.0,
      "action_suggestion": "What the user should do",
      "reasoning": "Why this matters",
      "mapped_action": {{
        "action_type": "one of the available action types above",
        "priority": 1-5,
        "input_context": {{
          "target_entities": ["affected lead/company names"],
          "focus": "what specifically to do"
        }},
        "reasoning": "Why this skill is the right response"
      }}
    }}
  ]
}}"""

    def _parse_analysis_response(
        self,
        response: str,
        signal: Signal,
    ) -> tuple[list[Implication], list[SkillTrigger]]:
        """Parse the combined LLM response into implications and triggers.

        Args:
            response: Raw LLM response string.
            signal: Source signal for ID references.

        Returns:
            Tuple of (implications, skill_triggers).
        """
        implications: list[Implication] = []
        triggers: list[SkillTrigger] = []

        try:
            # Strip markdown code fences if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)

            for item in data.get("implications", []):
                # Build Implication
                impl = Implication(
                    signal_id=signal.id,
                    description=item.get("description", ""),
                    affected_entities=item.get("affected_entities", []),
                    confidence=float(item.get("confidence", 0.5)),
                    action_suggestion=item.get("action_suggestion", ""),
                    reasoning=item.get("reasoning", ""),
                )
                implications.append(impl)

                # Build SkillTrigger from mapped action
                mapped = item.get("mapped_action", {})
                action_type = mapped.get("action_type", "")

                if action_type not in SKILL_ACTION_MAP:
                    logger.debug(
                        "Unknown action type '%s' from LLM, skipping",
                        action_type,
                    )
                    continue

                skill_path, risk_level = SKILL_ACTION_MAP[action_type]

                trigger = SkillTrigger(
                    implication=impl,
                    skill_path=skill_path,
                    action_type=action_type,
                    risk_level=risk_level.value,
                    input_data={
                        "signal_id": signal.id,
                        "signal_type": signal.signal_type,
                        "company_name": signal.company_name,
                        "headline": signal.headline,
                        "implication": impl.description,
                        "affected_entities": impl.affected_entities,
                        **(mapped.get("input_context") or {}),
                    },
                    priority=int(mapped.get("priority", 3)),
                    reasoning=mapped.get("reasoning", impl.reasoning),
                )
                triggers.append(trigger)

        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Failed to parse implication analysis response: %s", exc)

        return implications, triggers

    async def _check_autonomy(self, trigger: SkillTrigger) -> bool:
        """Check if a trigger can auto-execute based on trust history.

        Args:
            trigger: The skill trigger to check.

        Returns:
            True if auto-execution is permitted.
        """
        risk = SkillRiskLevel(trigger.risk_level)

        # HIGH and CRITICAL always require approval
        if risk in (SkillRiskLevel.HIGH, SkillRiskLevel.CRITICAL):
            return False

        # Check trust history for this user + skill
        try:
            autonomy = SkillAutonomyService()
            decision = await autonomy.check_approval(
                user_id=self._user_id,
                skill_id=trigger.skill_path,
                risk_level=risk,
            )
            return decision.auto_approved
        except Exception as exc:
            logger.debug(
                "Autonomy check failed for %s, defaulting to approval required: %s",
                trigger.skill_path,
                exc,
            )
            return False

    async def _build_execution_plan(
        self,
        signal: Signal,
        implications: list[Implication],
        triggers: list[SkillTrigger],
    ) -> ImplicationPlan:
        """Build and persist an execution plan from skill triggers.

        Groups triggers by dependency and risk level into parallel groups.
        Low-risk read-only triggers run first in parallel, followed by
        medium-risk actions that depend on enriched data.

        Args:
            signal: Source signal.
            implications: Detected implications.
            triggers: Mapped skill triggers.

        Returns:
            ImplicationPlan with a persisted execution plan.
        """
        plan = ImplicationPlan(
            signal=signal,
            implications=implications,
            triggers=triggers,
        )

        # Sort triggers by priority
        sorted_triggers = sorted(triggers, key=lambda t: t.priority)

        # Group into parallel execution tiers:
        # Tier 1: LOW risk (read-only enrichment) — run in parallel
        # Tier 2: MEDIUM risk (external actions) — run after tier 1
        tier_1: list[SkillTrigger] = []
        tier_2: list[SkillTrigger] = []

        for trigger in sorted_triggers:
            risk = SkillRiskLevel(trigger.risk_level)
            if risk == SkillRiskLevel.LOW:
                tier_1.append(trigger)
            else:
                tier_2.append(trigger)

        # Build ExecutionSteps
        steps: list[ExecutionStep] = []
        parallel_groups: list[list[int]] = []

        step_num = 1

        # Tier 1 steps (parallel)
        tier_1_step_nums: list[int] = []
        for trigger in tier_1:
            steps.append(
                ExecutionStep(
                    step_number=step_num,
                    skill_id=trigger.trigger_id,
                    skill_path=trigger.skill_path,
                    depends_on=[],
                    status="pending",
                    input_data=trigger.input_data,
                )
            )
            tier_1_step_nums.append(step_num)
            step_num += 1

        if tier_1_step_nums:
            parallel_groups.append(tier_1_step_nums)

        # Tier 2 steps (parallel with each other, depend on tier 1)
        tier_2_step_nums: list[int] = []
        for trigger in tier_2:
            steps.append(
                ExecutionStep(
                    step_number=step_num,
                    skill_id=trigger.trigger_id,
                    skill_path=trigger.skill_path,
                    depends_on=tier_1_step_nums,
                    status="pending",
                    input_data=trigger.input_data,
                )
            )
            tier_2_step_nums.append(step_num)
            step_num += 1

        if tier_2_step_nums:
            parallel_groups.append(tier_2_step_nums)

        # Determine overall risk and approval
        has_medium = any(SkillRiskLevel(t.risk_level) != SkillRiskLevel.LOW for t in triggers)
        all_auto = all(t.auto_execute for t in triggers)

        execution_plan = ExecutionPlan(
            plan_id=plan.plan_id,
            task_description=(
                f"Signal-triggered actions for: {signal.company_name} — {signal.headline}"
            ),
            steps=steps,
            parallel_groups=parallel_groups,
            estimated_duration_ms=len(steps) * 5000,
            risk_level="medium" if has_medium else "low",
            approval_required=not all_auto,
            reasoning=(
                f"Signal '{signal.headline}' triggered {len(implications)} "
                f"implication(s) mapping to {len(triggers)} skill action(s). "
                f"Tier 1 ({len(tier_1)} read-only) runs in parallel, "
                f"Tier 2 ({len(tier_2)} external) follows."
            ),
        )

        # Persist to database
        await self._persist_plan(execution_plan)

        plan.execution_plan_id = execution_plan.plan_id
        plan.summary = self._build_plan_summary(signal, implications, triggers)

        return plan

    async def _persist_plan(self, plan: ExecutionPlan) -> None:
        """Persist an execution plan to the skill_execution_plans table.

        Args:
            plan: The execution plan to persist.
        """
        client = self._get_db()
        status = "pending_approval" if plan.approval_required else "approved"

        try:
            client.table("skill_execution_plans").insert(
                {
                    "id": plan.plan_id,
                    "user_id": self._user_id,
                    "task_description": plan.task_description,
                    "steps": json.dumps(
                        [
                            {
                                "step_number": s.step_number,
                                "skill_id": s.skill_id,
                                "skill_path": s.skill_path,
                                "depends_on": s.depends_on,
                                "status": s.status,
                                "input_data": s.input_data,
                            }
                            for s in plan.steps
                        ]
                    ),
                    "parallel_groups": json.dumps(plan.parallel_groups),
                    "estimated_duration_ms": plan.estimated_duration_ms,
                    "risk_level": plan.risk_level,
                    "approval_required": plan.approval_required,
                    "status": status,
                    "reasoning": plan.reasoning,
                    "created_at": datetime.now(UTC).isoformat(),
                    "metadata": json.dumps(
                        {
                            "source": "implication_trigger",
                            "signal_id": plan.task_description.split(": ", 1)[-1]
                            if ": " in plan.task_description
                            else "",
                        }
                    ),
                }
            ).execute()

            logger.info(
                "Persisted implication execution plan %s (status=%s)",
                plan.plan_id,
                status,
                extra={"user_id": self._user_id},
            )
        except Exception as exc:
            logger.warning(
                "Failed to persist execution plan %s: %s",
                plan.plan_id,
                exc,
            )

    async def _record_activity(self, signal: Signal, plan: ImplicationPlan) -> None:
        """Record the implication analysis in the activity feed.

        Args:
            signal: Source signal.
            plan: The generated implication plan.
        """
        try:
            await self._activity.record(
                user_id=self._user_id,
                agent="scout",
                activity_type="implication_analysis",
                title=f"Signal Intelligence: {signal.company_name}",
                description=plan.summary,
                reasoning=(
                    f"Detected {len(plan.implications)} implication(s) from "
                    f"'{signal.headline}', mapped to {len(plan.triggers)} "
                    f"skill action(s)."
                ),
                confidence=0.85,
                related_entity_type="signal",
                related_entity_id=signal.id,
                metadata={
                    "signal_type": signal.signal_type,
                    "plan_id": plan.plan_id,
                    "trigger_count": len(plan.triggers),
                    "auto_execute_count": sum(1 for t in plan.triggers if t.auto_execute),
                },
            )
        except Exception as exc:
            logger.warning("Failed to record implication activity: %s", exc)

    # ── Summary helpers ───────────────────────────────────────────────

    def _build_affected_summary(self, plan: ImplicationPlan) -> str:
        """Build a human-readable summary of affected entities.

        Args:
            plan: The implication plan.

        Returns:
            Summary string like "This affects 3 of your contacts at Novartis."
        """
        all_entities: list[str] = []
        for impl in plan.implications:
            all_entities.extend(impl.affected_entities)

        unique_entities = list(dict.fromkeys(all_entities))
        if not unique_entities:
            return ""

        if len(unique_entities) == 1:
            return f"This affects {unique_entities[0]}."
        elif len(unique_entities) <= 3:
            joined = ", ".join(unique_entities[:-1]) + f" and {unique_entities[-1]}"
            return f"This affects {joined}."
        else:
            return (
                f"This affects {len(unique_entities)} entities including "
                f"{unique_entities[0]} and {unique_entities[1]}."
            )

    def _build_actions_summary(self, triggers: list[SkillTrigger]) -> str:
        """Build a human-readable summary of planned actions.

        Args:
            triggers: The skill triggers.

        Returns:
            Summary string describing the prepared actions.
        """
        if not triggers:
            return ""

        action_descriptions: list[str] = []
        for trigger in triggers:
            action_type = trigger.action_type.replace("_", " ")
            action_descriptions.append(action_type)

        unique_actions = list(dict.fromkeys(action_descriptions))

        if len(unique_actions) == 1:
            return f"I've prepared to {unique_actions[0]}."
        elif len(unique_actions) <= 3:
            joined = ", ".join(unique_actions[:-1]) + f" and {unique_actions[-1]}"
            return f"I've prepared to {joined}."
        else:
            return (
                f"I've prepared {len(unique_actions)} actions including "
                f"{unique_actions[0]} and {unique_actions[1]}."
            )

    def _build_plan_summary(
        self,
        signal: Signal,
        implications: list[Implication],
        triggers: list[SkillTrigger],
    ) -> str:
        """Build a complete plan summary for storage and display.

        Args:
            signal: Source signal.
            implications: Detected implications.
            triggers: Mapped skill triggers.

        Returns:
            Multi-line summary string.
        """
        lines = [
            f"Signal: {signal.company_name} — {signal.headline}",
            f"Implications detected: {len(implications)}",
        ]

        for i, impl in enumerate(implications[:5], 1):
            lines.append(f"  {i}. {impl.description} (confidence: {impl.confidence:.0%})")

        lines.append(f"Actions planned: {len(triggers)}")
        for trigger in triggers[:5]:
            auto_label = "auto" if trigger.auto_execute else "needs approval"
            lines.append(f"  - {trigger.action_type} via {trigger.skill_path} [{auto_label}]")

        return "\n".join(lines)


# ── Integration helper ───────────────────────────────────────────────


async def process_signal_with_implications(signal: Signal, user_id: str) -> list[SkillTrigger]:
    """Convenience function for integrating with signal_radar.

    Call this from ``signal_radar.create_alerts`` or
    ``run_signal_radar_scan`` to add implication-driven skill triggering
    to the signal processing pipeline.

    Args:
        signal: The detected market signal.
        user_id: User UUID.

    Returns:
        List of SkillTrigger objects created.
    """
    trigger = ImplicationAwareSkillTrigger(user_id=user_id)
    return await trigger.process_signal_implications(signal)
