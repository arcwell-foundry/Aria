"""StrategistAgent module for ARIA.

Provides strategic planning and pursuit orchestration capabilities,
creating actionable strategies with phases, milestones, and agent tasks.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)


class StrategistAgent(BaseAgent):
    """Strategic planning agent for pursuit orchestration.

    The Strategist agent analyzes account context, generates pursuit
    strategies, and creates timelines with milestones and agent tasks.
    """

    name = "Strategist"
    description = "Strategic planning and pursuit orchestration"

    # Valid goal types for strategy tasks
    VALID_GOAL_TYPES = {"lead_gen", "research", "outreach", "close", "retention"}

    def __init__(self, llm_client: "LLMClient", user_id: str) -> None:
        """Initialize the Strategist agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        super().__init__(llm_client=llm_client, user_id=user_id)

    def _register_tools(self) -> dict[str, Any]:
        """Register Strategist agent's planning tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "analyze_account": self._analyze_account,
            "generate_strategy": self._generate_strategy,
            "create_timeline": self._create_timeline,
        }

    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate strategy task input before execution.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Required: goal
        if "goal" not in task:
            return False

        goal = task["goal"]
        if not isinstance(goal, dict):
            return False

        # Goal must have title and type
        if "title" not in goal or not goal["title"]:
            return False

        if "type" not in goal:
            return False

        # Validate goal type
        if goal["type"] not in self.VALID_GOAL_TYPES:
            return False

        # Required: resources
        if "resources" not in task:
            return False

        resources = task["resources"]
        if not isinstance(resources, dict):
            return False

        # Resources must have time_horizon_days
        if "time_horizon_days" not in resources:
            return False

        time_horizon = resources["time_horizon_days"]
        return isinstance(time_horizon, int) and time_horizon > 0

    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the strategist agent's primary task.

        Orchestrates the full strategy generation workflow:
        1. Extract goal, resources, constraints, context from task
        2. Analyze account context
        3. Generate pursuit strategy
        4. Create timeline with milestones

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with complete strategy data including analysis,
            strategy, timeline, and metadata.
        """
        # Extract task components
        goal = task.get("goal", {})
        resources = task.get("resources", {})
        constraints = task.get("constraints", {})
        context = task.get("context", {})

        logger.info(
            f"Executing strategy generation for goal: {goal.get('title')}",
            extra={"user_id": self.user_id, "goal_type": goal.get("type")},
        )

        # Step 1: Analyze account context
        analysis = await self._analyze_account(goal=goal, context=context)

        # Step 2: Generate pursuit strategy
        strategy = await self._generate_strategy(
            goal=goal,
            analysis=analysis,
            resources=resources,
            constraints=constraints,
        )

        # Step 3: Create timeline with milestones
        time_horizon_days = resources.get("time_horizon_days", 90)
        deadline = constraints.get("deadline")
        timeline = await self._create_timeline(
            strategy=strategy,
            time_horizon_days=time_horizon_days,
            deadline=deadline,
        )

        # Build complete result data
        result_data: dict[str, Any] = {
            "goal_id": str(uuid.uuid4()),
            "created_at": datetime.now().isoformat(),
            "analysis": analysis,
            "strategy": strategy,
            "timeline": timeline,
        }

        logger.info(
            f"Strategy generation complete for goal: {goal.get('title')}",
            extra={
                "user_id": self.user_id,
                "phases": len(strategy.get("phases", [])),
                "tasks": len(strategy.get("agent_tasks", [])),
            },
        )

        return AgentResult(success=True, data=result_data)

    async def _analyze_account(
        self,
        goal: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze account context and opportunities.

        Evaluates the goal, target company, competitive landscape,
        and stakeholder map to identify opportunities and challenges.

        Args:
            goal: Goal details including target company.
            context: Optional context with competitive landscape, stakeholders.

        Returns:
            Account analysis with opportunities, challenges, and recommendations.
        """
        context = context or {}
        target_company = goal.get("target_company", "Unknown")
        goal_type = goal.get("type", "general")

        logger.info(
            f"Analyzing account for goal: {goal.get('title')}",
            extra={"target_company": target_company, "goal_type": goal_type},
        )

        analysis: dict[str, Any] = {
            "target_company": target_company,
            "goal_type": goal_type,
            "opportunities": [],
            "challenges": [],
            "key_actions": [],
            "recommendation": "",
        }

        # Analyze competitive landscape if provided
        competitive_landscape = context.get("competitive_landscape")
        if competitive_landscape:
            analysis["competitive_analysis"] = self._analyze_competitive(competitive_landscape)
            # Add opportunities from strengths
            for strength in competitive_landscape.get("our_strengths", []):
                analysis["opportunities"].append(f"Leverage strength: {strength}")
            # Add challenges from weaknesses
            for weakness in competitive_landscape.get("our_weaknesses", []):
                analysis["challenges"].append(f"Address weakness: {weakness}")

        # Analyze stakeholder map if provided
        stakeholder_map = context.get("stakeholder_map")
        if stakeholder_map:
            analysis["stakeholder_analysis"] = self._analyze_stakeholders(stakeholder_map)
            # Add key actions based on stakeholders
            for dm in stakeholder_map.get("decision_makers", []):
                analysis["key_actions"].append(
                    f"Engage decision maker: {dm.get('name', 'Unknown')}"
                )

        # Generate default opportunities and challenges based on goal type
        if goal_type == "lead_gen":
            analysis["opportunities"].append("Identify new prospects matching ICP")
            analysis["key_actions"].append("Run Hunter agent for lead discovery")
        elif goal_type == "research":
            analysis["opportunities"].append("Gather competitive intelligence")
            analysis["key_actions"].append("Run Analyst agent for research")
        elif goal_type == "outreach":
            analysis["opportunities"].append("Personalize outreach based on research")
            analysis["key_actions"].append("Run Scribe agent for communication drafts")
        elif goal_type == "close":
            analysis["opportunities"].append("Accelerate deal timeline")
            analysis["challenges"].append("Navigate procurement process")
            analysis["key_actions"].append("Prepare proposal and ROI documentation")

        # Generate recommendation
        analysis["recommendation"] = self._generate_recommendation(
            goal_type, analysis["opportunities"], analysis["challenges"]
        )

        return analysis

    def _analyze_competitive(
        self,
        landscape: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze competitive landscape.

        Args:
            landscape: Competitive landscape data.

        Returns:
            Competitive analysis summary.
        """
        competitors = landscape.get("competitors", [])
        strengths = landscape.get("our_strengths", [])
        weaknesses = landscape.get("our_weaknesses", [])

        return {
            "competitor_count": len(competitors),
            "competitors": competitors,
            "strength_count": len(strengths),
            "weakness_count": len(weaknesses),
            "competitive_position": (
                "strong" if len(strengths) > len(weaknesses) else "needs_improvement"
            ),
        }

    def _analyze_stakeholders(
        self,
        stakeholder_map: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze stakeholder map.

        Args:
            stakeholder_map: Stakeholder information.

        Returns:
            Stakeholder analysis summary.
        """
        decision_makers = stakeholder_map.get("decision_makers", [])
        influencers = stakeholder_map.get("influencers", [])
        blockers = stakeholder_map.get("blockers", [])

        return {
            "decision_maker_count": len(decision_makers),
            "influencer_count": len(influencers),
            "blocker_count": len(blockers),
            "engagement_priority": decision_makers + influencers,
            "risk_level": "high" if blockers else "low",
        }

    def _generate_recommendation(
        self,
        goal_type: str,
        opportunities: list[str],
        challenges: list[str],
    ) -> str:
        """Generate strategic recommendation.

        Args:
            goal_type: Type of goal.
            opportunities: Identified opportunities.
            challenges: Identified challenges.

        Returns:
            Strategic recommendation text.
        """
        if not opportunities and not challenges:
            return f"Proceed with standard {goal_type} approach."

        if len(opportunities) > len(challenges):
            return (
                f"Favorable conditions for {goal_type}. "
                f"Capitalize on {len(opportunities)} identified opportunities."
            )
        else:
            return (
                f"Address {len(challenges)} challenges before proceeding with "
                f"{goal_type}. Consider risk mitigation strategies."
            )

    async def _generate_strategy(
        self,
        goal: dict[str, Any],
        analysis: dict[str, Any],
        resources: dict[str, Any],
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate pursuit strategy with phases.

        Args:
            goal: Goal details.
            analysis: Account analysis results.
            resources: Available resources and agents.
            constraints: Optional constraints like deadlines.

        Returns:
            Strategy with phases, milestones, and agent tasks.
        """
        goal_type = goal.get("type", "general")
        time_horizon = resources.get("time_horizon_days", 90)
        available_agents = resources.get("available_agents", [])
        constraints = constraints or {}

        logger.info(
            f"Generating strategy for goal: {goal.get('title')}",
            extra={"goal_type": goal_type, "time_horizon": time_horizon},
        )

        # Generate phases based on goal type
        phases = self._generate_phases(goal_type, time_horizon)

        # Generate agent tasks based on available agents and phases
        agent_tasks = self._generate_agent_tasks(goal_type, available_agents, phases, analysis)

        # Generate risks from challenges and constraints
        challenges = analysis.get("challenges", [])
        risks = self._generate_risks(challenges, constraints)

        # Generate success criteria
        success_criteria = self._generate_success_criteria(goal_type, goal)

        # Generate summary
        summary = self._generate_summary(goal, phases, agent_tasks)

        # Track applied constraints
        constraints_applied = {
            "has_deadline": "deadline" in constraints,
            "has_exclusions": "exclusions" in constraints,
            "has_compliance_notes": "compliance_notes" in constraints,
        }

        return {
            "goal_type": goal_type,
            "phases": phases,
            "agent_tasks": agent_tasks,
            "risks": risks,
            "success_criteria": success_criteria,
            "summary": summary,
            "constraints_applied": constraints_applied,
        }

    def _generate_phases(
        self,
        goal_type: str,
        time_horizon: int,
    ) -> list[dict[str, Any]]:
        """Generate phase templates based on goal type.

        Args:
            goal_type: Type of goal.
            time_horizon: Time horizon in days.

        Returns:
            List of phase dictionaries.
        """
        # Phase templates by goal type with duration percentages
        phase_templates: dict[str, list[dict[str, Any]]] = {
            "lead_gen": [
                {
                    "name": "Discovery",
                    "description": "Identify and qualify potential leads",
                    "duration_pct": 0.4,
                    "objectives": ["Define ICP criteria", "Source initial leads"],
                },
                {
                    "name": "Enrichment",
                    "description": "Enrich lead data and validate fit",
                    "duration_pct": 0.35,
                    "objectives": ["Gather company data", "Identify stakeholders"],
                },
                {
                    "name": "Handoff",
                    "description": "Prepare leads for outreach",
                    "duration_pct": 0.25,
                    "objectives": ["Score leads", "Create outreach plan"],
                },
            ],
            "research": [
                {
                    "name": "Scoping",
                    "description": "Define research scope and questions",
                    "duration_pct": 0.2,
                    "objectives": ["Identify research questions", "Define sources"],
                },
                {
                    "name": "Investigation",
                    "description": "Conduct research and gather intelligence",
                    "duration_pct": 0.5,
                    "objectives": ["Query scientific APIs", "Analyze competitors"],
                },
                {
                    "name": "Synthesis",
                    "description": "Synthesize findings and create deliverables",
                    "duration_pct": 0.3,
                    "objectives": ["Create summary report", "Identify insights"],
                },
            ],
            "outreach": [
                {
                    "name": "Preparation",
                    "description": "Research and prepare outreach materials",
                    "duration_pct": 0.3,
                    "objectives": ["Research prospect", "Draft messaging"],
                },
                {
                    "name": "Execution",
                    "description": "Execute outreach campaign",
                    "duration_pct": 0.4,
                    "objectives": ["Send communications", "Track responses"],
                },
                {
                    "name": "Follow-up",
                    "description": "Follow up and nurture responses",
                    "duration_pct": 0.3,
                    "objectives": ["Follow up on opens", "Schedule meetings"],
                },
            ],
            "close": [
                {
                    "name": "Discovery",
                    "description": "Understand needs and build relationships",
                    "duration_pct": 0.2,
                    "objectives": ["Conduct discovery calls", "Map stakeholders"],
                },
                {
                    "name": "Proposal",
                    "description": "Create and present proposal",
                    "duration_pct": 0.25,
                    "objectives": ["Draft proposal", "Present solution"],
                },
                {
                    "name": "Negotiation",
                    "description": "Navigate objections and negotiate terms",
                    "duration_pct": 0.3,
                    "objectives": ["Handle objections", "Negotiate pricing"],
                },
                {
                    "name": "Closing",
                    "description": "Finalize deal and onboard",
                    "duration_pct": 0.25,
                    "objectives": ["Complete contracts", "Plan implementation"],
                },
            ],
            "retention": [
                {
                    "name": "Assessment",
                    "description": "Assess account health and risks",
                    "duration_pct": 0.3,
                    "objectives": ["Review usage metrics", "Identify churn risks"],
                },
                {
                    "name": "Engagement",
                    "description": "Proactive engagement and value delivery",
                    "duration_pct": 0.4,
                    "objectives": ["Schedule QBRs", "Share success stories"],
                },
                {
                    "name": "Renewal",
                    "description": "Prepare and execute renewal",
                    "duration_pct": 0.3,
                    "objectives": ["Prepare renewal proposal", "Close renewal"],
                },
            ],
        }

        # Default phases for unknown goal types
        default_phases = [
            {
                "name": "Planning",
                "description": "Plan and prepare for execution",
                "duration_pct": 0.3,
                "objectives": ["Define objectives", "Allocate resources"],
            },
            {
                "name": "Execution",
                "description": "Execute planned activities",
                "duration_pct": 0.7,
                "objectives": ["Complete tasks", "Monitor progress"],
            },
        ]

        templates = phase_templates.get(goal_type, default_phases)

        phases = []
        for i, template in enumerate(templates):
            duration_days = int(time_horizon * template["duration_pct"])
            phases.append(
                {
                    "phase_number": i + 1,
                    "name": template["name"],
                    "description": template["description"],
                    "duration_days": max(1, duration_days),
                    "objectives": template["objectives"],
                }
            )

        return phases

    def _generate_agent_tasks(
        self,
        goal_type: str,
        available_agents: list[str],
        phases: list[dict[str, Any]],
        analysis: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate agent tasks based on available agents and phases.

        Args:
            goal_type: Type of goal.
            available_agents: List of available agent names.
            phases: List of phases.
            analysis: Account analysis results.

        Returns:
            List of agent task dictionaries.
        """
        # Agent capabilities and task types
        agent_capabilities: dict[str, list[dict[str, Any]]] = {
            "Hunter": [
                {
                    "task_type": "lead_discovery",
                    "description": "Discover and qualify new leads",
                    "priority": "high",
                    "goal_types": ["lead_gen", "close"],
                },
                {
                    "task_type": "lead_enrichment",
                    "description": "Enrich lead data with additional information",
                    "priority": "medium",
                    "goal_types": ["lead_gen", "outreach"],
                },
            ],
            "Analyst": [
                {
                    "task_type": "research",
                    "description": "Conduct market and competitive research",
                    "priority": "high",
                    "goal_types": ["research", "close"],
                },
                {
                    "task_type": "competitive_analysis",
                    "description": "Analyze competitive landscape",
                    "priority": "medium",
                    "goal_types": ["research", "close", "outreach"],
                },
            ],
            "Scribe": [
                {
                    "task_type": "draft_outreach",
                    "description": "Draft personalized outreach communications",
                    "priority": "high",
                    "goal_types": ["outreach", "lead_gen"],
                },
                {
                    "task_type": "draft_proposal",
                    "description": "Draft proposal and ROI documentation",
                    "priority": "high",
                    "goal_types": ["close"],
                },
            ],
            "Operator": [
                {
                    "task_type": "schedule_meetings",
                    "description": "Schedule and coordinate meetings",
                    "priority": "medium",
                    "goal_types": ["close", "outreach", "retention"],
                },
                {
                    "task_type": "crm_update",
                    "description": "Update CRM with activity data",
                    "priority": "low",
                    "goal_types": ["lead_gen", "close", "outreach", "retention"],
                },
            ],
            "Scout": [
                {
                    "task_type": "monitor_signals",
                    "description": "Monitor account signals and triggers",
                    "priority": "medium",
                    "goal_types": ["retention", "close"],
                },
            ],
        }

        tasks = []
        task_id = 1

        for agent in available_agents:
            capabilities = agent_capabilities.get(agent, [])

            for capability in capabilities:
                # Only include tasks relevant to this goal type
                if goal_type not in capability.get("goal_types", []):
                    continue

                # Determine which phase this task belongs to
                phase_num = self._determine_task_phase(
                    capability["task_type"], goal_type, len(phases)
                )

                tasks.append(
                    {
                        "id": f"task-{task_id}",
                        "agent": agent,
                        "task_type": capability["task_type"],
                        "description": capability["description"],
                        "phase": phase_num,
                        "priority": capability["priority"],
                    }
                )
                task_id += 1

        # Add tasks from key actions in analysis
        key_actions = analysis.get("key_actions", [])
        for action in key_actions:
            # Try to match action to an available agent
            assigned_agent = self._match_action_to_agent(action, available_agents)
            if assigned_agent:
                tasks.append(
                    {
                        "id": f"task-{task_id}",
                        "agent": assigned_agent,
                        "task_type": "custom_action",
                        "description": action,
                        "phase": 1,
                        "priority": "medium",
                    }
                )
                task_id += 1

        return tasks

    def _determine_task_phase(
        self,
        task_type: str,
        goal_type: str,  # noqa: ARG002
        num_phases: int,
    ) -> int:
        """Determine which phase a task belongs to.

        Args:
            task_type: Type of task.
            goal_type: Type of goal.
            num_phases: Number of phases.

        Returns:
            Phase number (1-indexed).
        """
        # Early phase tasks
        early_tasks = {"lead_discovery", "research", "competitive_analysis"}
        # Late phase tasks
        late_tasks = {"draft_proposal", "crm_update", "schedule_meetings"}

        if task_type in early_tasks:
            return 1
        elif task_type in late_tasks:
            return num_phases
        else:
            # Middle phase
            return max(1, num_phases // 2)

    def _match_action_to_agent(
        self,
        action: str,
        available_agents: list[str],
    ) -> str | None:
        """Match a key action to an available agent.

        Args:
            action: Action description.
            available_agents: List of available agent names.

        Returns:
            Agent name or None if no match.
        """
        action_lower = action.lower()

        agent_keywords: dict[str, list[str]] = {
            "Hunter": ["lead", "prospect", "discover", "find"],
            "Analyst": ["research", "analyze", "competitive", "intelligence"],
            "Scribe": ["draft", "write", "communication", "email", "proposal"],
            "Operator": ["schedule", "meeting", "crm", "sync"],
            "Scout": ["monitor", "signal", "alert", "track"],
        }

        for agent in available_agents:
            keywords = agent_keywords.get(agent, [])
            if any(keyword in action_lower for keyword in keywords):
                return agent

        # Return first available agent as fallback
        return available_agents[0] if available_agents else None

    def _generate_risks(
        self,
        challenges: list[str],
        constraints: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate risks from challenges and constraints.

        Args:
            challenges: List of identified challenges.
            constraints: Constraints dict with deadline, exclusions, etc.

        Returns:
            List of risk dictionaries.
        """
        risks = []

        # Convert challenges to risks
        for challenge in challenges:
            risk = {
                "description": challenge,
                "likelihood": "medium",
                "impact": "medium",
                "mitigation": f"Monitor and address: {challenge}",
            }

            # Adjust likelihood/impact based on keywords
            challenge_lower = challenge.lower()
            if any(word in challenge_lower for word in ["budget", "cost", "price", "funding"]):
                risk["likelihood"] = "high"
                risk["impact"] = "high"
                risk["mitigation"] = "Prepare ROI justification and flexible pricing"
            elif any(
                word in challenge_lower for word in ["timeline", "deadline", "urgent", "delay"]
            ):
                risk["likelihood"] = "medium"
                risk["impact"] = "high"
                risk["mitigation"] = "Accelerate early phases, parallel workstreams"
            elif any(
                word in challenge_lower for word in ["competitor", "competition", "alternative"]
            ):
                risk["likelihood"] = "high"
                risk["impact"] = "medium"
                risk["mitigation"] = "Emphasize differentiators, faster response"

            risks.append(risk)

        # Add deadline risk if constraint exists
        if "deadline" in constraints:
            risks.append(
                {
                    "description": f"Hard deadline: {constraints['deadline']}",
                    "likelihood": "high",
                    "impact": "high",
                    "mitigation": "Build buffer time, prioritize critical path",
                }
            )

        # Add compliance risk if noted
        if "compliance_notes" in constraints:
            risks.append(
                {
                    "description": "Compliance requirements must be met",
                    "likelihood": "medium",
                    "impact": "high",
                    "mitigation": "Review all communications for compliance",
                }
            )

        return risks

    def _generate_success_criteria(
        self,
        goal_type: str,
        goal: dict[str, Any],
    ) -> list[str]:
        """Generate success criteria based on goal type.

        Args:
            goal_type: Type of goal.
            goal: Goal details.

        Returns:
            List of success criteria strings.
        """
        criteria_templates: dict[str, list[str]] = {
            "lead_gen": [
                "Minimum qualified leads identified",
                "Lead data enrichment complete",
                "Leads scored and prioritized",
                "Outreach sequences prepared",
            ],
            "research": [
                "Research questions answered",
                "Competitive analysis complete",
                "Key insights documented",
                "Recommendations delivered",
            ],
            "outreach": [
                "Outreach sequence completed",
                "Response rate above threshold",
                "Meetings scheduled",
                "Pipeline value generated",
            ],
            "close": [
                "Proposal delivered",
                "Key stakeholder buy-in obtained",
                "Terms negotiated",
                "Contract signed",
            ],
            "retention": [
                "Account health assessed",
                "QBR completed",
                "Renewal proposal delivered",
                "Renewal confirmed",
            ],
        }

        default_criteria = [
            "Goal objectives achieved",
            "Timeline met",
            "Quality standards maintained",
        ]

        criteria = criteria_templates.get(goal_type, default_criteria)

        # Add goal-specific criteria if target company specified
        if goal.get("target_company"):
            criteria.append(f"Engagement with {goal['target_company']} established")

        return criteria

    def _generate_summary(
        self,
        goal: dict[str, Any],
        phases: list[dict[str, Any]],
        agent_tasks: list[dict[str, Any]],
    ) -> str:
        """Generate executive summary of the strategy.

        Args:
            goal: Goal details.
            phases: List of phases.
            agent_tasks: List of agent tasks.

        Returns:
            Summary text.
        """
        goal_title = goal.get("title", "Unnamed goal")
        num_phases = len(phases)
        num_tasks = len(agent_tasks)
        total_days = sum(phase.get("duration_days", 0) for phase in phases)

        # Count unique agents
        agents_involved = list({task["agent"] for task in agent_tasks})
        num_agents = len(agents_involved)

        return (
            f"Strategy for '{goal_title}': {num_phases} phases over {total_days} days, "
            f"with {num_tasks} tasks assigned to {num_agents} agent(s) "
            f"({', '.join(agents_involved) if agents_involved else 'none'})."
        )

    async def _create_timeline(
        self,
        strategy: dict[str, Any],
        time_horizon_days: int,
        deadline: str | None = None,
    ) -> dict[str, Any]:
        """Create timeline with milestones.

        Creates a detailed timeline by scheduling phases, milestones,
        and agent tasks with actual dates based on the strategy.

        Args:
            strategy: Generated strategy with phases and agent_tasks.
            time_horizon_days: Time horizon in days.
            deadline: Optional hard deadline (ISO format YYYY-MM-DD).

        Returns:
            Timeline with scheduled milestones, phase schedule, and task schedule.
        """
        phases = strategy.get("phases", [])
        agent_tasks = strategy.get("agent_tasks", [])

        logger.info(
            f"Creating timeline for {len(phases)} phases",
            extra={"time_horizon_days": time_horizon_days, "deadline": deadline},
        )

        # Parse deadline if provided
        deadline_date: datetime | None = None
        if deadline:
            deadline_date = datetime.fromisoformat(deadline)

        # Calculate total duration from phases
        total_phase_duration = sum(phase.get("duration_days", 0) for phase in phases)

        # Determine scaling factor if phases exceed time horizon or deadline
        start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        available_days = time_horizon_days

        if deadline_date:
            days_to_deadline = (deadline_date - start_date).days
            available_days = min(time_horizon_days, days_to_deadline)

        # Scale phase durations if total exceeds available time
        scale_factor = 1.0
        if total_phase_duration > available_days and total_phase_duration > 0:
            scale_factor = available_days / total_phase_duration

        # Build phase schedule with dates
        phase_schedule: list[dict[str, Any]] = []
        milestones: list[dict[str, Any]] = []
        current_date = start_date

        for phase in phases:
            phase_number = phase.get("phase_number", len(phase_schedule) + 1)
            phase_name = phase.get("name", f"Phase {phase_number}")
            duration_days = phase.get("duration_days", 7)
            objectives = phase.get("objectives", [])

            # Scale duration
            scaled_duration = max(1, int(duration_days * scale_factor))

            phase_start = current_date
            phase_end = current_date + timedelta(days=scaled_duration)

            # Respect deadline
            if deadline_date and phase_end > deadline_date:
                phase_end = deadline_date

            phase_schedule.append(
                {
                    "phase_number": phase_number,
                    "name": phase_name,
                    "start_date": phase_start.strftime("%Y-%m-%d"),
                    "end_date": phase_end.strftime("%Y-%m-%d"),
                    "duration_days": scaled_duration,
                }
            )

            # Create milestone for phase completion
            milestone_id = f"milestone-{phase_number}"
            success_criteria = objectives if objectives else [f"Complete {phase_name}"]

            milestones.append(
                {
                    "id": milestone_id,
                    "name": f"{phase_name} Complete",
                    "phase": phase_number,
                    "target_date": phase_end.strftime("%Y-%m-%d"),
                    "success_criteria": success_criteria,
                }
            )

            current_date = phase_end

        # Schedule tasks within their phases
        task_schedule: list[dict[str, Any]] = []

        for task in agent_tasks:
            task_id = task.get("id", f"task-{len(task_schedule) + 1}")
            task_phase = task.get("phase", 1)
            priority = task.get("priority", "medium")

            # Find the phase schedule for this task
            phase_info = next(
                (p for p in phase_schedule if p["phase_number"] == task_phase),
                None,
            )

            if phase_info:
                phase_start = datetime.strptime(phase_info["start_date"], "%Y-%m-%d")
                phase_end = datetime.strptime(phase_info["end_date"], "%Y-%m-%d")
                phase_duration = (phase_end - phase_start).days

                # High priority tasks start at phase start
                # Medium priority tasks start at phase midpoint
                # Low priority tasks start at 2/3 of phase
                if priority == "high":
                    task_start = phase_start
                elif priority == "medium":
                    offset = max(0, phase_duration // 2)
                    task_start = phase_start + timedelta(days=offset)
                else:  # low
                    offset = max(0, (phase_duration * 2) // 3)
                    task_start = phase_start + timedelta(days=offset)

                task_end = phase_end

                task_schedule.append(
                    {
                        "task_id": task_id,
                        "agent": task.get("agent", "Unknown"),
                        "start_date": task_start.strftime("%Y-%m-%d"),
                        "end_date": task_end.strftime("%Y-%m-%d"),
                        "priority": priority,
                    }
                )

        end_date = current_date if current_date > start_date else start_date

        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "time_horizon_days": time_horizon_days,
            "deadline": deadline,
            "schedule": phase_schedule,
            "milestones": milestones,
            "task_schedule": task_schedule,
        }
