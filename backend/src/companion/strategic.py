"""Strategic planning service for ARIA companion.

This module enables ARIA to be a strategic partner for long-term thinking,
not just a task executor. It includes quarterly planning facilitation,
scenario analysis, progress tracking, and proactive concern surfacing.

Key features:
- StrategicPlan dataclass: captures objectives, key results, risks, scenarios
- StrategicPlanningService: creates plans, tracks progress, runs scenarios
- Challenge capability: critically evaluates plans for weaknesses
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, cast

from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import SupabaseClient
from src.memory.semantic import SemanticMemory

logger = logging.getLogger(__name__)


class PlanType(str, Enum):
    """Type of strategic plan."""

    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    CAMPAIGN = "campaign"
    TERRITORY = "territory"
    ACCOUNT = "account"


class RiskSeverity(str, Enum):
    """Severity level for plan risks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConcernType(str, Enum):
    """Type of strategic concern."""

    OFF_TRACK = "off_track"
    AT_RISK = "at_risk"
    OPPORTUNITY = "opportunity"
    BLIND_SPOT = "blind_spot"


@dataclass
class KeyResult:
    """A measurable key result within a strategic plan."""

    description: str
    target_value: float
    current_value: float
    unit: str
    progress_percentage: float = 0.0

    def __post_init__(self) -> None:
        """Calculate progress percentage."""
        if self.target_value > 0:
            self.progress_percentage = min(100.0, (self.current_value / self.target_value) * 100)
        elif self.target_value == 0 and self.current_value > 0:
            # Handle negative targets or targets achieved without numeric goal
            self.progress_percentage = 100.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "description": self.description,
            "target_value": self.target_value,
            "current_value": self.current_value,
            "unit": self.unit,
            "progress_percentage": round(self.progress_percentage, 1),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KeyResult":
        """Create from dictionary."""
        return cls(
            description=data.get("description", ""),
            target_value=float(data.get("target_value", 0)),
            current_value=float(data.get("current_value", 0)),
            unit=data.get("unit", ""),
            progress_percentage=float(data.get("progress_percentage", 0)),
        )


@dataclass
class Risk:
    """A risk associated with a strategic plan."""

    description: str
    severity: RiskSeverity
    likelihood: float  # 0.0-1.0
    impact: float  # 0.0-1.0
    mitigation: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "description": self.description,
            "severity": self.severity.value,
            "likelihood": self.likelihood,
            "impact": self.impact,
            "mitigation": self.mitigation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Risk":
        """Create from dictionary."""
        severity_str = data.get("severity", "medium")
        severity = (
            RiskSeverity(severity_str)
            if severity_str in [e.value for e in RiskSeverity]
            else RiskSeverity.MEDIUM
        )
        return cls(
            description=data.get("description", ""),
            severity=severity,
            likelihood=float(data.get("likelihood", 0.5)),
            impact=float(data.get("impact", 0.5)),
            mitigation=data.get("mitigation", ""),
        )


@dataclass
class Scenario:
    """A scenario analysis for a strategic plan."""

    name: str  # optimistic, realistic, pessimistic
    description: str
    probability: float  # 0.0-1.0
    key_factors: list[str] = field(default_factory=list)
    outcomes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "probability": self.probability,
            "key_factors": self.key_factors,
            "outcomes": self.outcomes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scenario":
        """Create from dictionary."""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            probability=float(data.get("probability", 0.33)),
            key_factors=data.get("key_factors", []),
            outcomes=data.get("outcomes", {}),
        )


@dataclass
class StrategicPlan:
    """A complete strategic plan with objectives, key results, and risks."""

    id: str
    user_id: str
    title: str
    plan_type: PlanType
    objectives: list[str] = field(default_factory=list)
    key_results: list[KeyResult] = field(default_factory=list)
    risks: list[Risk] = field(default_factory=list)
    scenarios: list[Scenario] = field(default_factory=list)
    progress_score: float = 0.0
    aria_assessment: str = ""
    aria_concerns: list[str] = field(default_factory=list)
    status: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "plan_type": self.plan_type.value,
            "objectives": self.objectives,
            "key_results": [kr.to_dict() for kr in self.key_results],
            "risks": [r.to_dict() for r in self.risks],
            "scenarios": [s.to_dict() for s in self.scenarios],
            "progress_score": round(self.progress_score, 2),
            "aria_assessment": self.aria_assessment,
            "aria_concerns": self.aria_concerns,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategicPlan":
        """Create from dictionary."""
        plan_type_str = data.get("plan_type", "quarterly")
        plan_type = (
            PlanType(plan_type_str)
            if plan_type_str in [e.value for e in PlanType]
            else PlanType.QUARTERLY
        )

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        elif created_at is None:
            created_at = datetime.now(UTC)

        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        elif updated_at is None:
            updated_at = datetime.now(UTC)

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            user_id=data.get("user_id", ""),
            title=data.get("title", ""),
            plan_type=plan_type,
            objectives=data.get("objectives", []),
            key_results=[KeyResult.from_dict(kr) for kr in data.get("key_results", [])],
            risks=[Risk.from_dict(r) for r in data.get("risks", [])],
            scenarios=[Scenario.from_dict(s) for s in data.get("scenarios", [])],
            progress_score=float(data.get("progress_score", 0)),
            aria_assessment=data.get("aria_assessment", ""),
            aria_concerns=data.get("aria_concerns", []),
            status=data.get("status", "active"),
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass
class StrategicConcern:
    """A concern about a strategic plan."""

    plan_id: str
    plan_title: str
    concern_type: ConcernType
    description: str
    severity: str
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "plan_id": self.plan_id,
            "plan_title": self.plan_title,
            "concern_type": self.concern_type.value,
            "description": self.description,
            "severity": self.severity,
            "recommendation": self.recommendation,
        }


class StrategicPlanningService:
    """Service for strategic planning capabilities.

    This service enables ARIA to:
    - Create strategic plans with objectives and key results
    - Track progress against plans
    - Run scenario analyses
    - Challenge plans with critical evaluation
    - Surface strategic concerns proactively
    """

    def __init__(
        self,
        db_client: Any = None,
        llm_client: Any = None,
        personality_service: Any = None,
        metacognition_service: Any = None,
        memory_service: Any = None,
    ) -> None:
        """Initialize the Strategic Planning service.

        Args:
            db_client: Optional Supabase client (will create if not provided).
            llm_client: Optional LLM client (will create if not provided).
            personality_service: Optional PersonalityService for tone calibration.
            metacognition_service: Optional MetacognitionService for confidence tracking.
            memory_service: Optional memory service for context retrieval.
        """
        self._db = db_client or SupabaseClient.get_client()
        self._llm = llm_client or LLMClient()
        self._personality = personality_service
        self._metacognition = metacognition_service
        self._memory = memory_service or SemanticMemory()

    async def create_plan(
        self,
        user_id: str,
        title: str,
        plan_type: PlanType,
        objectives: list[str],
    ) -> StrategicPlan:
        """Create a new strategic plan with LLM-generated assessment.

        Steps:
        1. Generate initial key results suggestions via LLM
        2. Identify initial risks via LLM analysis
        3. Generate scenarios (optimistic, realistic, pessimistic)
        4. Generate ARIA assessment
        5. Store in database
        6. Return complete StrategicPlan

        Args:
            user_id: User identifier.
            title: Plan title.
            plan_type: Type of plan (quarterly, annual, etc.).
            objectives: List of strategic objectives.

        Returns:
            Complete StrategicPlan with assessment and scenarios.

        Raises:
            ValueError: If objectives list is empty.
        """
        if not objectives:
            raise ValueError("At least one objective is required")

        plan_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        # Generate key results suggestions
        key_results = await self._generate_key_results(objectives)

        # Identify risks
        risks = await self._identify_risks(objectives, plan_type)

        # Generate scenarios
        scenarios = await self._generate_scenarios(objectives, plan_type)

        # Get personality directness for assessment tone
        directness = await self._get_personality_directness(user_id)

        # Generate ARIA assessment
        aria_assessment = await self._generate_assessment(
            title=title,
            objectives=objectives,
            key_results=key_results,
            risks=risks,
            directness=directness,
        )

        # Build the plan
        plan = StrategicPlan(
            id=plan_id,
            user_id=user_id,
            title=title,
            plan_type=plan_type,
            objectives=objectives,
            key_results=key_results,
            risks=risks,
            scenarios=scenarios,
            progress_score=0.0,
            aria_assessment=aria_assessment,
            aria_concerns=[],
            status="active",
            created_at=now,
            updated_at=now,
        )

        # Store in database
        await self._store_plan(plan)

        logger.info(
            "Created strategic plan",
            extra={
                "plan_id": plan_id,
                "user_id": user_id,
                "title": title,
                "plan_type": plan_type.value,
            },
        )

        return plan

    async def get_active_plans(self, user_id: str) -> list[StrategicPlan]:
        """Get all active strategic plans for a user.

        Args:
            user_id: User identifier.

        Returns:
            List of active StrategicPlan objects, ordered by updated_at desc.
        """
        try:
            result = (
                self._db.table("strategic_plans")
                .select("*")
                .eq("user_id", user_id)
                .eq("status", "active")
                .order("updated_at", desc=True)
                .execute()
            )

            if not result.data:
                return []

            return [StrategicPlan.from_dict(cast(dict[str, Any], row)) for row in result.data]

        except Exception as e:
            logger.warning(
                "Failed to get active plans",
                extra={"user_id": user_id, "error": str(e)},
            )
            return []

    async def get_plan(self, plan_id: str, user_id: str) -> StrategicPlan | None:
        """Get a specific strategic plan.

        Args:
            plan_id: Plan identifier.
            user_id: User identifier for ownership verification.

        Returns:
            StrategicPlan if found and owned by user, None otherwise.
        """
        try:
            result = (
                self._db.table("strategic_plans")
                .select("*")
                .eq("id", plan_id)
                .eq("user_id", user_id)
                .eq("status", "active")
                .single()
                .execute()
            )

            if not result.data:
                return None

            return StrategicPlan.from_dict(cast(dict[str, Any], result.data))

        except Exception as e:
            logger.warning(
                "Failed to get plan",
                extra={"plan_id": plan_id, "user_id": user_id, "error": str(e)},
            )
            return None

    async def update_progress(
        self,
        plan_id: str,
        user_id: str,
        progress_data: dict[str, float],
    ) -> StrategicPlan | None:
        """Update progress on key results for a plan.

        Steps:
        1. Load existing plan
        2. Update key_results progress values
        3. Recalculate overall progress_score
        4. Re-assess risks based on new progress
        5. Surface concerns if progress deviates significantly
        6. Update updated_at timestamp
        7. Store updated plan

        Args:
            plan_id: Plan identifier.
            user_id: User identifier for ownership verification.
            progress_data: Dict mapping key result descriptions to new current values.

        Returns:
            Updated StrategicPlan, or None if not found.
        """
        plan = await self.get_plan(plan_id, user_id)
        if plan is None:
            return None

        # Update key results
        for kr in plan.key_results:
            if kr.description in progress_data:
                kr.current_value = progress_data[kr.description]
                kr.progress_percentage = min(
                    100.0, (kr.current_value / kr.target_value * 100) if kr.target_value > 0 else 0
                )

        # Calculate overall progress score (weighted average)
        if plan.key_results:
            total_progress = sum(kr.progress_percentage for kr in plan.key_results)
            plan.progress_score = total_progress / len(plan.key_results)

        # Re-assess risks and generate concerns
        new_concerns = await self._assess_progress_concerns(plan)
        plan.aria_concerns = new_concerns

        # Update timestamp
        plan.updated_at = datetime.now(UTC)

        # Store updated plan
        await self._update_plan(plan)

        logger.info(
            "Updated plan progress",
            extra={
                "plan_id": plan_id,
                "user_id": user_id,
                "progress_score": plan.progress_score,
                "concerns_count": len(new_concerns),
            },
        )

        return plan

    async def run_scenario(
        self,
        plan_id: str,
        user_id: str,
        scenario_description: str,
    ) -> dict[str, Any]:
        """Run a "what-if" scenario analysis on a plan.

        Uses LLM + memory context to simulate scenario impact.

        Args:
            plan_id: Plan identifier.
            user_id: User identifier.
            scenario_description: Description of the scenario to simulate.

        Returns:
            Dict with:
            - scenario_description: str
            - affected_objectives: list[str]
            - risk_changes: list[dict]
            - recommended_adjustments: list[str]
            - confidence: float
        """
        plan = await self.get_plan(plan_id, user_id)
        if plan is None:
            return {
                "scenario_description": scenario_description,
                "affected_objectives": [],
                "risk_changes": [],
                "recommended_adjustments": [],
                "confidence": 0.0,
                "error": "Plan not found",
            }

        # Build context for LLM
        plan_context = self._build_plan_context(plan)

        # Get relevant memory context
        memory_context = await self._get_memory_context(user_id, scenario_description)

        prompt = f"""Analyze this scenario against a strategic plan and predict impacts.

PLAN CONTEXT:
{plan_context}

SCENARIO TO ANALYZE:
{scenario_description}

RELEVANT CONTEXT FROM MEMORY:
{memory_context}

Output ONLY valid JSON with this structure:
{{
    "affected_objectives": ["list of objectives that would be impacted"],
    "risk_changes": [
        {{
            "risk": "risk description",
            "current_severity": "low/medium/high/critical",
            "new_severity": "low/medium/high/critical",
            "reason": "why it changed"
        }}
    ],
    "recommended_adjustments": ["specific adjustments to make to the plan"],
    "confidence": 0.0 to 1.0 (how confident in this analysis)
}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                task=TaskType.STRATEGIST_PLAN,
                agent_id="strategic",
            )

            # Parse JSON response
            content = self._extract_json(response)

            result = json.loads(content)
            return {
                "scenario_description": scenario_description,
                "affected_objectives": result.get("affected_objectives", []),
                "risk_changes": result.get("risk_changes", []),
                "recommended_adjustments": result.get("recommended_adjustments", []),
                "confidence": float(result.get("confidence", 0.5)),
            }

        except Exception as e:
            logger.warning(
                "Failed to run scenario analysis",
                extra={"plan_id": plan_id, "error": str(e)},
            )
            return {
                "scenario_description": scenario_description,
                "affected_objectives": [],
                "risk_changes": [],
                "recommended_adjustments": [],
                "confidence": 0.0,
                "error": str(e),
            }

    async def challenge_plan(
        self,
        plan_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """Critically evaluate a plan for weaknesses and blind spots.

        ARIA uses her personality directness to calibrate tone.

        Args:
            plan_id: Plan identifier.
            user_id: User identifier.

        Returns:
            Dict with:
            - assumptions_challenged: list[str]
            - blind_spots: list[str]
            - alternatives_considered: list[str]
            - recommended_revisions: list[str]
            - directness_level: int (1-3)
        """
        plan = await self.get_plan(plan_id, user_id)
        if plan is None:
            return {
                "assumptions_challenged": [],
                "blind_spots": [],
                "alternatives_considered": [],
                "recommended_revisions": [],
                "directness_level": 3,
                "error": "Plan not found",
            }

        # Get personality directness for tone
        directness = await self._get_personality_directness(user_id)

        # Build context
        plan_context = self._build_plan_context(plan)

        # Determine tone based on directness
        tone_guidance = {
            1: "Be gentle and supportive. Frame critiques as questions or suggestions.",
            2: "Be balanced. Acknowledge strengths while pointing out concerns clearly.",
            3: "Be direct and candid. Don't sugarcoat. Challenge assumptions forcefully.",
        }

        prompt = f"""Critically evaluate this strategic plan. Look for weaknesses, blind spots, and unrealistic assumptions.

PLAN CONTEXT:
{plan_context}

TONE: {tone_guidance.get(directness, tone_guidance[2])}

Be a critical thinking partner. Challenge the plan thoroughly. Look for:
1. Unstated assumptions that may not hold
2. Blind spots the planner might have
3. Alternative approaches not considered
4. Areas where the plan is vague or unrealistic

Output ONLY valid JSON with this structure:
{{
    "assumptions_challenged": [
        "specific assumption being challenged and why it might not hold"
    ],
    "blind_spots": [
        "blind spot identified and its potential impact"
    ],
    "alternatives_considered": [
        "alternative approach that should be considered"
    ],
    "recommended_revisions": [
        "specific revision to improve the plan"
    ]
}}"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                task=TaskType.STRATEGIST_PLAN,
                agent_id="strategic",
            )

            # Parse JSON response
            content = self._extract_json(response)

            result = json.loads(content)
            return {
                "assumptions_challenged": result.get("assumptions_challenged", []),
                "blind_spots": result.get("blind_spots", []),
                "alternatives_considered": result.get("alternatives_considered", []),
                "recommended_revisions": result.get("recommended_revisions", []),
                "directness_level": directness,
            }

        except Exception as e:
            logger.warning(
                "Failed to challenge plan",
                extra={"plan_id": plan_id, "error": str(e)},
            )
            return {
                "assumptions_challenged": [],
                "blind_spots": [],
                "alternatives_considered": [],
                "recommended_revisions": [],
                "directness_level": directness,
                "error": str(e),
            }

    async def get_strategic_concerns(self, user_id: str) -> list[StrategicConcern]:
        """Get prioritized strategic concerns across all active plans.

        Checks each plan for:
        - Progress vs timeline (off track)
        - At-risk key results
        - Escalating risks
        - Missed opportunities

        Args:
            user_id: User identifier.

        Returns:
            List of StrategicConcern objects, prioritized by severity.
        """
        concerns: list[StrategicConcern] = []

        plans = await self.get_active_plans(user_id)

        for plan in plans:
            # Check progress vs expected
            progress_concern = self._check_progress_concern(plan)
            if progress_concern:
                concerns.append(progress_concern)

            # Check for at-risk key results
            kr_concerns = self._check_key_result_concerns(plan)
            concerns.extend(kr_concerns)

            # Check for high/critical risks
            risk_concerns = self._check_risk_concerns(plan)
            concerns.extend(risk_concerns)

        # Sort by severity (critical > high > medium > low)
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        concerns.sort(key=lambda c: severity_order.get(c.severity, 4))

        return concerns

    async def update_plan(
        self,
        plan_id: str,
        user_id: str,
        updates: dict[str, Any],
    ) -> StrategicPlan | None:
        """Update plan details (objectives, key results, etc.).

        Args:
            plan_id: Plan identifier.
            user_id: User identifier.
            updates: Dict of fields to update.

        Returns:
            Updated StrategicPlan, or None if not found.
        """
        plan = await self.get_plan(plan_id, user_id)
        if plan is None:
            return None

        # Apply updates
        if "objectives" in updates:
            plan.objectives = updates["objectives"]
        if "key_results" in updates:
            plan.key_results = [KeyResult.from_dict(kr) for kr in updates["key_results"]]
        if "title" in updates:
            plan.title = updates["title"]
        if "status" in updates:
            plan.status = updates["status"]

        plan.updated_at = datetime.now(UTC)

        # Store updated plan
        await self._update_plan(plan)

        logger.info(
            "Updated plan",
            extra={"plan_id": plan_id, "user_id": user_id, "fields": list(updates.keys())},
        )

        return plan

    # ── Private Methods ─────────────────────────────────────────────────────

    async def _generate_key_results(
        self,
        objectives: list[str],
    ) -> list[KeyResult]:
        """Generate suggested key results for objectives using LLM."""
        prompt = f"""Generate measurable key results for these strategic objectives:

OBJECTIVES:
{chr(10).join(f"- {obj}" for obj in objectives)}

For each objective, create 1-2 key results that are:
- Specific and measurable
- Time-bound
- Achievable but ambitious

Output ONLY valid JSON array:
[
    {{
        "description": "clear description of the key result",
        "target_value": numeric_target,
        "unit": "unit of measurement (e.g., %, $, count)",
        "current_value": 0
    }}
]"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                task=TaskType.STRATEGIST_PLAN,
                agent_id="strategic",
            )

            content = self._extract_json(response)
            data = json.loads(content)

            if isinstance(data, list):
                return [
                    KeyResult(
                        description=item.get("description", ""),
                        target_value=float(item.get("target_value", 0)),
                        current_value=float(item.get("current_value", 0)),
                        unit=item.get("unit", ""),
                    )
                    for item in data
                ]

        except Exception as e:
            logger.warning("Failed to generate key results: %s", str(e))

        # Return empty list on failure
        return []

    async def _identify_risks(
        self,
        objectives: list[str],
        plan_type: PlanType,
    ) -> list[Risk]:
        """Identify risks for a plan using LLM."""
        prompt = f"""Identify potential risks for this {plan_type.value} strategic plan:

OBJECTIVES:
{chr(10).join(f"- {obj}" for obj in objectives)}

Consider:
- Execution risks
- Market/competitive risks
- Resource risks
- Timing risks

Output ONLY valid JSON array:
[
    {{
        "description": "risk description",
        "severity": "low/medium/high/critical",
        "likelihood": 0.0 to 1.0,
        "impact": 0.0 to 1.0,
        "mitigation": "suggested mitigation strategy"
    }}
]"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                task=TaskType.STRATEGIST_PLAN,
                agent_id="strategic",
            )

            content = self._extract_json(response)
            data = json.loads(content)

            if isinstance(data, list):
                return [Risk.from_dict(item) for item in data]

        except Exception as e:
            logger.warning("Failed to identify risks: %s", str(e))

        return []

    async def _generate_scenarios(
        self,
        objectives: list[str],
        plan_type: PlanType,
    ) -> list[Scenario]:
        """Generate optimistic, realistic, and pessimistic scenarios."""
        prompt = f"""Generate three scenarios for this {plan_type.value} strategic plan:

OBJECTIVES:
{chr(10).join(f"- {obj}" for obj in objectives)}

Create three scenarios:
1. Optimistic - everything goes better than expected
2. Realistic - most likely outcome based on current trajectory
3. Pessimistic - significant challenges materialize

Output ONLY valid JSON array:
[
    {{
        "name": "optimistic/realistic/pessimistic",
        "description": "detailed description of this scenario",
        "probability": 0.0 to 1.0,
        "key_factors": ["factors that lead to this scenario"],
        "outcomes": {{
            "key_result_description": "expected outcome value"
        }}
    }}
]"""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                task=TaskType.STRATEGIST_PLAN,
                agent_id="strategic",
            )

            content = self._extract_json(response)
            data = json.loads(content)

            if isinstance(data, list):
                return [Scenario.from_dict(item) for item in data]

        except Exception as e:
            logger.warning("Failed to generate scenarios: %s", str(e))

        # Return default scenarios on failure
        return [
            Scenario(
                name="realistic",
                description="Expected outcomes based on current trajectory",
                probability=0.5,
            ),
        ]

    async def _generate_assessment(
        self,
        title: str,
        objectives: list[str],
        key_results: list[KeyResult],
        risks: list[Risk],
        directness: int,
    ) -> str:
        """Generate ARIA's assessment of a plan."""
        tone_guidance = {
            1: "Supportive and encouraging, with gentle suggestions.",
            2: "Balanced - acknowledge strengths while noting concerns.",
            3: "Direct and candid - call out issues plainly.",
        }

        kr_text = (
            "\n".join(
                f"- {kr.description} (target: {kr.target_value} {kr.unit})" for kr in key_results
            )
            or "No key results defined yet."
        )

        risk_text = (
            "\n".join(f"- [{r.severity.value}] {r.description}" for r in risks)
            or "No major risks identified."
        )

        prompt = f"""Provide a strategic assessment of this plan.

PLAN: {title}

OBJECTIVES:
{chr(10).join(f"- {obj}" for obj in objectives)}

KEY RESULTS:
{kr_text}

RISKS:
{risk_text}

TONE: {tone_guidance.get(directness, tone_guidance[2])}

Write a 2-4 sentence assessment that:
1. Summarizes your overall take on the plan
2. Highlights the most important strength
3. Notes the biggest concern or risk
4. Suggests one area for improvement

Output ONLY the assessment text, no JSON."""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.6,
                max_tokens=200,
                task=TaskType.STRATEGIST_PLAN,
                agent_id="strategic",
            )
            return response.strip()
        except Exception as e:
            logger.warning("Failed to generate assessment: %s", str(e))
            return "Assessment unavailable."

    async def _get_personality_directness(self, user_id: str) -> int:
        """Get personality directness level for a user."""
        if self._personality is None:
            try:
                from src.companion.personality import PersonalityService

                self._personality = PersonalityService()
            except Exception:
                return 3  # Default to high directness

        try:
            profile = await self._personality.get_profile(user_id)
            return int(profile.directness)
        except Exception:
            return 3

    def _build_plan_context(self, plan: StrategicPlan) -> str:
        """Build a text summary of a plan for LLM context."""
        kr_text = (
            "\n".join(
                f"- {kr.description}: {kr.current_value}/{kr.target_value} {kr.unit} ({kr.progress_percentage:.0f}%)"
                for kr in plan.key_results
            )
            or "No key results"
        )

        risk_text = (
            "\n".join(
                f"- [{r.severity.value}] {r.description} (likelihood: {r.likelihood:.0%}, impact: {r.impact:.0%})"
                for r in plan.risks
            )
            or "No risks identified"
        )

        return f"""PLAN: {plan.title}
Type: {plan.plan_type.value}
Status: {plan.status}
Progress: {plan.progress_score:.0f}%

OBJECTIVES:
{chr(10).join(f"- {obj}" for obj in plan.objectives)}

KEY RESULTS:
{kr_text}

RISKS:
{risk_text}"""

    async def _get_memory_context(self, user_id: str, query: str) -> str:
        """Get relevant context from semantic memory."""
        try:
            if hasattr(self._memory, "search_facts"):
                facts = await self._memory.search_facts(
                    user_id=user_id,
                    query=query,
                    limit=5,
                )
                if facts:
                    return "\n".join(f"- {f.subject} {f.predicate} {f.object}" for f in facts[:5])
        except Exception as e:
            logger.debug("Memory context lookup failed: %s", str(e))

        return "No relevant memory context available."

    async def _assess_progress_concerns(self, plan: StrategicPlan) -> list[str]:
        """Generate concerns based on progress assessment."""
        concerns = []

        # Check for key results significantly behind
        for kr in plan.key_results:
            if kr.progress_percentage < 25 and kr.target_value > 0:
                concerns.append(
                    f"Key result '{kr.description}' is significantly behind at {kr.progress_percentage:.0f}%"
                )

        # Check for high risks without mitigation
        for risk in plan.risks:
            if risk.severity in [RiskSeverity.HIGH, RiskSeverity.CRITICAL] and not risk.mitigation:
                concerns.append(
                    f"High-severity risk '{risk.description}' has no mitigation strategy"
                )

        return concerns

    def _check_progress_concern(self, plan: StrategicPlan) -> StrategicConcern | None:
        """Check if plan progress is concerning."""
        # For quarterly plans, expect ~8% progress per week
        # For annual plans, expect ~2% progress per week
        days_active = (datetime.now(UTC) - plan.created_at).days
        weeks_active = days_active / 7

        expected_progress = {
            PlanType.QUARTERLY: min(100, weeks_active * 8),
            PlanType.ANNUAL: min(100, weeks_active * 2),
            PlanType.CAMPAIGN: min(100, weeks_active * 10),
            PlanType.TERRITORY: min(100, weeks_active * 5),
            PlanType.ACCOUNT: min(100, weeks_active * 10),
        }.get(plan.plan_type, weeks_active * 5)

        # If progress is more than 20% below expected
        if plan.progress_score < expected_progress * 0.8 and weeks_active >= 2:
            return StrategicConcern(
                plan_id=plan.id,
                plan_title=plan.title,
                concern_type=ConcernType.OFF_TRACK,
                description=f"Plan progress ({plan.progress_score:.0f}%) is below expected ({expected_progress:.0f}%)",
                severity="medium" if plan.progress_score > expected_progress * 0.5 else "high",
                recommendation="Review key results and identify blockers. Consider adjusting timeline or resources.",
            )

        return None

    def _check_key_result_concerns(self, plan: StrategicPlan) -> list[StrategicConcern]:
        """Check for at-risk key results."""
        concerns = []

        for kr in plan.key_results:
            if kr.progress_percentage < 50 and kr.target_value > 0:
                severity = "critical" if kr.progress_percentage < 25 else "high"
                concerns.append(
                    StrategicConcern(
                        plan_id=plan.id,
                        plan_title=plan.title,
                        concern_type=ConcernType.AT_RISK,
                        description=f"Key result '{kr.description}' at {kr.progress_percentage:.0f}%",
                        severity=severity,
                        recommendation=f"Focus resources on '{kr.description}' or reassess feasibility.",
                    )
                )

        return concerns

    def _check_risk_concerns(self, plan: StrategicPlan) -> list[StrategicConcern]:
        """Check for concerning risks."""
        concerns = []

        for risk in plan.risks:
            if risk.severity == RiskSeverity.CRITICAL:
                concerns.append(
                    StrategicConcern(
                        plan_id=plan.id,
                        plan_title=plan.title,
                        concern_type=ConcernType.AT_RISK,
                        description=f"Critical risk: {risk.description}",
                        severity="critical",
                        recommendation=f"Implement mitigation: {risk.mitigation or 'Develop mitigation strategy immediately'}",
                    )
                )
            elif risk.severity == RiskSeverity.HIGH and risk.likelihood > 0.5:
                concerns.append(
                    StrategicConcern(
                        plan_id=plan.id,
                        plan_title=plan.title,
                        concern_type=ConcernType.AT_RISK,
                        description=f"High-likelihood risk: {risk.description}",
                        severity="high",
                        recommendation=f"Prepare contingency for: {risk.description}",
                    )
                )

        return concerns

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response, handling markdown code blocks."""
        content = text.strip()

        # Handle markdown code blocks
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line if it's a code block start
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove last line if it's a code block end
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        return content

    async def _store_plan(self, plan: StrategicPlan) -> None:
        """Store a new plan in the database."""
        try:
            self._db.table("strategic_plans").insert(
                {
                    "id": plan.id,
                    "user_id": plan.user_id,
                    "title": plan.title,
                    "plan_type": plan.plan_type.value,
                    "status": plan.status,
                    "objectives": plan.objectives,
                    "key_results": [kr.to_dict() for kr in plan.key_results],
                    "risks": [r.to_dict() for r in plan.risks],
                    "scenarios": [s.to_dict() for s in plan.scenarios],
                    "progress_score": plan.progress_score,
                    "aria_assessment": plan.aria_assessment,
                    "aria_concerns": plan.aria_concerns,
                    "created_at": plan.created_at.isoformat(),
                    "updated_at": plan.updated_at.isoformat(),
                }
            ).execute()

        except Exception:
            logger.exception(
                "Failed to store plan",
                extra={"plan_id": plan.id, "user_id": plan.user_id},
            )
            raise

    async def _update_plan(self, plan: StrategicPlan) -> None:
        """Update an existing plan in the database."""
        try:
            self._db.table("strategic_plans").update(
                {
                    "title": plan.title,
                    "status": plan.status,
                    "objectives": plan.objectives,
                    "key_results": [kr.to_dict() for kr in plan.key_results],
                    "risks": [r.to_dict() for r in plan.risks],
                    "scenarios": [s.to_dict() for s in plan.scenarios],
                    "progress_score": plan.progress_score,
                    "aria_assessment": plan.aria_assessment,
                    "aria_concerns": plan.aria_concerns,
                    "updated_at": plan.updated_at.isoformat(),
                }
            ).eq("id", plan.id).execute()

        except Exception:
            logger.exception(
                "Failed to update plan",
                extra={"plan_id": plan.id},
            )
            raise
