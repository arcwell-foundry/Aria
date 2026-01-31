# Phase 3: Agent System
## ARIA PRD - Implementation Phase 3

**Prerequisites:** Phase 2 Complete  
**Estimated Stories:** 12  
**Focus:** OODA Loop, Core Agents, Agent Orchestration, Goal System

---

## Overview

Phase 3 implements ARIA's agent architecture - the specialized workers that execute tasks under ARIA's command. This includes:

- OODA Loop cognitive processing
- Six core agents (Hunter, Analyst, Strategist, Scribe, Operator, Scout)
- Dynamic agent creation for goals
- Agent orchestration and coordination
- Goal lifecycle management

**Completion Criteria:** User can create a goal and watch ARIA spawn appropriate agents to pursue it.

---

## Agent Architecture Reference

### Core Agents

| Agent | Role | Primary Tools |
|-------|------|---------------|
| Hunter Pro | Lead discovery and prospecting | Exa, Apollo, Bright Data, LinkedIn |
| Scout | Intelligence gathering and filtering | Web search, news APIs, deduplication |
| Analyst | Scientific research | PubMed, ClinicalTrials.gov, ChEMBL, UniProt |
| Strategist | Planning and synthesis | Orchestration, brief generation |
| Scribe | Communication drafting | Email, documents, reports |
| Operator | System operations | Calendar, CRM, integrations |

### OODA Loop

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│ OBSERVE │ ──▶ │ ORIENT  │ ──▶ │ DECIDE  │ ──▶ │   ACT   │
└─────────┘     └─────────┘     └─────────┘     └─────────┘
     ▲                                               │
     └───────────────────────────────────────────────┘
```

---

## User Stories

### US-301: OODA Loop Implementation

**As** ARIA  
**I want** OODA loop cognitive processing  
**So that** I reason systematically about tasks

#### Acceptance Criteria
- [ ] `src/core/ooda.py` implements OODA cycle
- [ ] Observe: Gather context from memory and environment
- [ ] Orient: Analyze situation, identify patterns
- [ ] Decide: Select action from options
- [ ] Act: Execute chosen action
- [ ] Loop continues until goal achieved or blocked
- [ ] Each phase logged for transparency
- [ ] Configurable thinking budget per phase
- [ ] Unit tests for each phase

#### Technical Notes
```python
# src/core/ooda.py
from dataclasses import dataclass
from enum import Enum
from typing import Any

class OODAPhase(Enum):
    OBSERVE = "observe"
    ORIENT = "orient"
    DECIDE = "decide"
    ACT = "act"

@dataclass
class OODAState:
    goal_id: str
    current_phase: OODAPhase
    observations: list[dict]
    orientation: dict  # Analysis results
    decision: dict | None  # Chosen action
    action_result: Any | None
    iteration: int = 0
    max_iterations: int = 10

class OODALoop:
    def __init__(self, llm_client, memory_system):
        self.llm = llm_client
        self.memory = memory_system
    
    async def observe(self, state: OODAState, context: dict) -> OODAState:
        """Gather relevant information from memory and context."""
        # Query episodic memory for related events
        # Query semantic memory for relevant facts
        # Get current working memory state
        pass
    
    async def orient(self, state: OODAState) -> OODAState:
        """Analyze observations and identify patterns."""
        # Use LLM to synthesize observations
        # Identify threats and opportunities
        # Map to available agent capabilities
        pass
    
    async def decide(self, state: OODAState) -> OODAState:
        """Select the best action to take."""
        # Generate action options
        # Evaluate options against goal
        # Select highest-value action
        pass
    
    async def act(self, state: OODAState) -> OODAState:
        """Execute the decided action."""
        # Dispatch to appropriate agent
        # Wait for result
        # Update state with outcome
        pass
    
    async def run(self, goal: dict, context: dict) -> OODAState:
        """Execute full OODA loop until goal achieved."""
        state = OODAState(goal_id=goal["id"])
        
        while state.iteration < state.max_iterations:
            state = await self.observe(state, context)
            state = await self.orient(state)
            state = await self.decide(state)
            state = await self.act(state)
            
            if self._goal_achieved(state, goal):
                break
            
            state.iteration += 1
        
        return state
```

---

### US-302: Base Agent Class

**As a** developer  
**I want** a base agent class  
**So that** all agents share common behavior

#### Acceptance Criteria
- [ ] `src/agents/base.py` defines abstract Agent class
- [ ] Common methods: execute, validate_input, format_output
- [ ] Tool registration system
- [ ] Error handling and retry logic
- [ ] Execution logging
- [ ] Token usage tracking
- [ ] Status reporting (idle, running, complete, failed)
- [ ] Unit tests for base functionality

#### Technical Notes
```python
# src/agents/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"

@dataclass
class AgentResult:
    success: bool
    data: Any
    error: str | None = None
    tokens_used: int = 0
    execution_time_ms: int = 0

class BaseAgent(ABC):
    name: str
    description: str
    tools: dict[str, Callable]
    
    def __init__(self, llm_client, user_id: str):
        self.llm = llm_client
        self.user_id = user_id
        self.status = AgentStatus.IDLE
        self.tools = self._register_tools()
    
    @abstractmethod
    def _register_tools(self) -> dict[str, Callable]:
        """Register agent-specific tools."""
        pass
    
    @abstractmethod
    async def execute(self, task: dict) -> AgentResult:
        """Execute the agent's primary task."""
        pass
    
    def validate_input(self, task: dict) -> bool:
        """Validate task input before execution."""
        return True
    
    async def _call_tool(self, tool_name: str, **kwargs) -> Any:
        """Call a registered tool with error handling."""
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        return await self.tools[tool_name](**kwargs)
```

---

### US-303: Hunter Agent Implementation

**As** ARIA  
**I want** a Hunter agent for lead discovery  
**So that** I can find new prospects

#### Acceptance Criteria
- [ ] `src/agents/hunter.py` extends BaseAgent
- [ ] Tools: web_search, company_lookup, contact_finder
- [ ] Accepts: ICP criteria, target count, exclusions
- [ ] Returns: list of enriched leads with fit scores
- [ ] Deduplication against existing leads
- [ ] Rate limiting for external APIs
- [ ] Caching of company data
- [ ] Unit tests with mocked APIs

#### Technical Notes
```python
# src/agents/hunter.py
from src.agents.base import BaseAgent, AgentResult

class HunterAgent(BaseAgent):
    name = "Hunter Pro"
    description = "Discovers and qualifies new leads based on ICP"
    
    def _register_tools(self) -> dict:
        return {
            "search_companies": self._search_companies,
            "enrich_company": self._enrich_company,
            "find_contacts": self._find_contacts,
            "score_fit": self._score_fit,
        }
    
    async def execute(self, task: dict) -> AgentResult:
        """
        Task schema:
        {
            "icp": {"industry": str, "size": str, "geography": str, ...},
            "target_count": int,
            "exclusions": list[str]  # Company names to skip
        }
        """
        # 1. Search for companies matching ICP
        # 2. Filter against exclusions
        # 3. Enrich each company with data
        # 4. Find relevant contacts
        # 5. Score fit against ICP
        # 6. Return ranked leads
        pass
    
    async def _search_companies(self, criteria: dict) -> list[dict]:
        # Use Exa or Bright Data
        pass
    
    async def _enrich_company(self, company: dict) -> dict:
        # Add funding, size, tech stack, etc.
        pass
    
    async def _find_contacts(self, company_id: str, roles: list[str]) -> list[dict]:
        # Find decision makers
        pass
    
    async def _score_fit(self, company: dict, icp: dict) -> float:
        # Calculate 0-100 fit score
        pass
```

---

### US-304: Analyst Agent Implementation

**As** ARIA  
**I want** an Analyst agent for scientific research  
**So that** I can provide domain expertise

#### Acceptance Criteria
- [ ] `src/agents/analyst.py` extends BaseAgent
- [ ] Tools: pubmed_search, clinical_trials_search, protein_lookup
- [ ] Accepts: research question, depth level
- [ ] Returns: structured research report with citations
- [ ] Handles API rate limits gracefully
- [ ] Caches research results
- [ ] Unit tests with mocked APIs

#### Scientific APIs
```python
SCIENTIFIC_APIS = {
    "pubmed": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
    "clinicaltrials": "https://clinicaltrials.gov/api/v2/",
    "chembl": "https://www.ebi.ac.uk/chembl/api/data/",
    "uniprot": "https://rest.uniprot.org/",
    "openfda": "https://api.fda.gov/",
}
```

---

### US-305: Strategist Agent Implementation

**As** ARIA  
**I want** a Strategist agent for planning  
**So that** I can create effective pursuit strategies

#### Acceptance Criteria
- [ ] `src/agents/strategist.py` extends BaseAgent
- [ ] Tools: analyze_account, generate_strategy, create_timeline
- [ ] Accepts: goal details, available resources, constraints
- [ ] Returns: actionable strategy with phases and milestones
- [ ] Considers: competitive landscape, stakeholder map, timing
- [ ] Generates sub-tasks for other agents
- [ ] Unit tests for strategy generation

---

### US-306: Scribe Agent Implementation

**As** ARIA  
**I want** a Scribe agent for communication  
**So that** I can draft emails and documents

#### Acceptance Criteria
- [ ] `src/agents/scribe.py` extends BaseAgent
- [ ] Tools: draft_email, draft_document, personalize
- [ ] Uses Digital Twin for style matching
- [ ] Accepts: communication type, recipient, context, goal
- [ ] Returns: draft ready for user review
- [ ] Multiple tone options (formal, friendly, urgent)
- [ ] Template support for common communications
- [ ] Unit tests for drafting

---

### US-307: Operator Agent Implementation

**As** ARIA  
**I want** an Operator agent for system tasks  
**So that** I can manage calendar and CRM

#### Acceptance Criteria
- [ ] `src/agents/operator.py` extends BaseAgent
- [ ] Tools: calendar_read, calendar_write, crm_read, crm_write
- [ ] Accepts: operation type, parameters
- [ ] Returns: operation result
- [ ] Handles OAuth token refresh
- [ ] Respects user permissions
- [ ] Audit logs all operations
- [ ] Unit tests with mocked integrations

---

### US-308: Scout Agent Implementation

**As** ARIA  
**I want** a Scout agent for intelligence  
**So that** I can monitor signals and news

#### Acceptance Criteria
- [ ] `src/agents/scout.py` extends BaseAgent
- [ ] Tools: web_search, news_search, social_monitor
- [ ] Accepts: entities to monitor, signal types
- [ ] Returns: relevant signals with relevance scores
- [ ] Deduplication of signals
- [ ] Filters noise from signal
- [ ] Unit tests for signal detection

---

### US-309: Agent Orchestrator

**As** ARIA  
**I want** to orchestrate multiple agents  
**So that** complex goals can be achieved

#### Acceptance Criteria
- [ ] `src/agents/orchestrator.py` coordinates agents
- [ ] Parallel execution where possible
- [ ] Sequential execution where dependencies exist
- [ ] Handles agent failures gracefully
- [ ] Reports progress to user
- [ ] Respects resource limits (API calls, tokens)
- [ ] Unit tests for orchestration scenarios

#### Technical Notes
```python
# src/agents/orchestrator.py
import asyncio
from typing import Type
from src.agents.base import BaseAgent, AgentResult

class AgentOrchestrator:
    def __init__(self, llm_client, user_id: str):
        self.llm = llm_client
        self.user_id = user_id
        self.active_agents: dict[str, BaseAgent] = {}
    
    async def spawn_agent(
        self, 
        agent_class: Type[BaseAgent], 
        task: dict
    ) -> str:
        """Spawn an agent and return its ID."""
        agent = agent_class(self.llm, self.user_id)
        agent_id = str(uuid.uuid4())
        self.active_agents[agent_id] = agent
        return agent_id
    
    async def execute_parallel(
        self, 
        tasks: list[tuple[Type[BaseAgent], dict]]
    ) -> list[AgentResult]:
        """Execute multiple agents in parallel."""
        coros = [
            self.spawn_and_execute(agent_class, task)
            for agent_class, task in tasks
        ]
        return await asyncio.gather(*coros)
    
    async def execute_sequential(
        self, 
        tasks: list[tuple[Type[BaseAgent], dict]]
    ) -> list[AgentResult]:
        """Execute agents sequentially, passing results forward."""
        results = []
        context = {}
        for agent_class, task in tasks:
            task["context"] = context
            result = await self.spawn_and_execute(agent_class, task)
            results.append(result)
            context[agent_class.name] = result.data
        return results
```

---

### US-310: Goal Database Schema

**As a** user  
**I want** goals persisted in database  
**So that** my work is saved

#### Acceptance Criteria
- [ ] Goals table with all required fields
- [ ] Goal agents junction table
- [ ] Agent executions history table
- [ ] RLS policies for user isolation
- [ ] Indexes for common queries
- [ ] Migration script

#### SQL Schema
```sql
CREATE TABLE goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    goal_type TEXT NOT NULL,  -- lead_gen, research, outreach, etc.
    status TEXT DEFAULT 'draft',  -- draft, active, paused, complete, failed
    strategy JSONB,  -- Generated strategy document
    config JSONB DEFAULT '{}',  -- Goal-specific configuration
    progress INT DEFAULT 0,  -- 0-100
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE goal_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID REFERENCES goals(id) ON DELETE CASCADE,
    agent_type TEXT NOT NULL,
    agent_config JSONB DEFAULT '{}',
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE agent_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_agent_id UUID REFERENCES goal_agents(id) ON DELETE CASCADE,
    input JSONB NOT NULL,
    output JSONB,
    status TEXT DEFAULT 'running',
    tokens_used INT DEFAULT 0,
    execution_time_ms INT,
    error TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- RLS
ALTER TABLE goals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own goals" ON goals
    FOR ALL USING (user_id = auth.uid());

-- Indexes
CREATE INDEX idx_goals_user_status ON goals(user_id, status);
CREATE INDEX idx_goal_agents_goal ON goal_agents(goal_id);
CREATE INDEX idx_executions_agent ON agent_executions(goal_agent_id);
```

---

### US-311: Goal API Endpoints

**As a** user  
**I want** API endpoints to manage goals  
**So that** I can create and track pursuits

#### Acceptance Criteria
- [ ] `POST /api/v1/goals` - Create new goal
- [ ] `GET /api/v1/goals` - List user's goals
- [ ] `GET /api/v1/goals/{id}` - Get goal details with agents
- [ ] `PATCH /api/v1/goals/{id}` - Update goal
- [ ] `DELETE /api/v1/goals/{id}` - Delete goal
- [ ] `POST /api/v1/goals/{id}/start` - Start goal execution
- [ ] `POST /api/v1/goals/{id}/pause` - Pause execution
- [ ] `GET /api/v1/goals/{id}/progress` - Get execution progress
- [ ] Integration tests for all endpoints

---

### US-312: Goals UI Page

**As a** user  
**I want** a Goals page in the dashboard  
**So that** I can manage my ARIA pursuits

#### Acceptance Criteria
- [ ] `/dashboard/goals` route
- [ ] List view of all goals with status indicators
- [ ] Create goal button opens modal/form
- [ ] Goal detail view shows strategy and progress
- [ ] Start/pause/delete actions available
- [ ] Agent status visible for active goals
- [ ] Real-time progress updates (polling or WebSocket)
- [ ] Responsive design

---

## Phase 3 Completion Checklist

Before moving to Phase 4, verify:

- [ ] All 12 user stories completed
- [ ] All quality gates pass
- [ ] OODA loop functioning correctly
- [ ] All six core agents implemented
- [ ] Agent orchestrator coordinates execution
- [ ] Goals can be created and started
- [ ] Agent progress visible in UI
- [ ] Error handling robust

---

## Next Phase

Proceed to `PHASE_4_FEATURES.md` for Core Features implementation.
