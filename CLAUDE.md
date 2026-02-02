# CLAUDE.md - ARIA Project Configuration (Enhanced)

## Project Overview

ARIA (Autonomous Reasoning & Intelligence Agent) is an AI-powered Department Director for Life Sciences commercial teams. Premium SaaS at $200K/year.

**Core Value Proposition:** Solve the "72% admin trap" - sales reps spend most time on admin, not selling. A 5-person team with ARIA performs like 7.

**Key Differentiators:**
- Six-Type Cognitive Memory (including Lead Memory)
- Temporal Knowledge Graph (Graphiti on Neo4j)
- User Digital Twin with writing style fingerprinting
- 15+ Scientific APIs (PubMed, ClinicalTrials.gov, ChEMBL, etc.)
- Dynamic Agent Creation per goal
- Full audit trail of all decisions

**North Star Vision:** Jarvis-level intelligence - ambient awareness, causal reasoning, calibrated autonomy.

---

## Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Backend | Python 3.11+ / FastAPI / Uvicorn | API server, agent orchestration |
| Frontend | React 18 / TypeScript / Vite / Tailwind CSS | Web application |
| Database | Supabase (PostgreSQL + pgvector) | Relational data, vector embeddings |
| Knowledge Graph | Graphiti on Neo4j | Temporal memory, relationships |
| LLM | Anthropic Claude API (claude-sonnet-4-20250514) | Reasoning and generation |
| Video | Tavus + Daily.co | AI avatar conversations |
| Integrations | Composio | OAuth + app connectors |
| UI Components | shadcn/ui | Pre-built accessible components |

---

## Quality Gates (MUST PASS BEFORE COMMITTING)

```bash
# Backend - Run ALL of these
cd backend
pytest tests/ -v                    # Unit tests must pass
mypy src/ --strict                  # Type checking - no errors
ruff check src/                     # Linting - no warnings
ruff format src/ --check            # Formatting check

# Frontend - Run ALL of these
cd frontend
npm run typecheck                   # TypeScript - no errors
npm run lint                        # ESLint - no warnings
npm run test                        # Jest tests must pass
npm run build                       # Build must succeed
```

**CRITICAL:** Never commit code that fails quality gates. Fix issues before proceeding.

---

## Project Structure

```
aria/
├── backend/
│   ├── src/
│   │   ├── api/routes/      # FastAPI route handlers
│   │   │   ├── auth.py
│   │   │   ├── chat.py
│   │   │   ├── goals.py
│   │   │   ├── memory.py
│   │   │   ├── leads.py
│   │   │   └── agents.py
│   │   ├── agents/          # ARIA's specialized agents
│   │   │   ├── base.py      # Abstract base class
│   │   │   ├── hunter.py    # Lead discovery
│   │   │   ├── analyst.py   # Scientific research
│   │   │   ├── strategist.py # Planning
│   │   │   ├── scribe.py    # Communication drafting
│   │   │   ├── operator.py  # System operations
│   │   │   └── scout.py     # Intelligence gathering
│   │   ├── memory/          # Six-type memory system
│   │   │   ├── working.py   # Current conversation (in-memory)
│   │   │   ├── episodic.py  # Past events (Graphiti)
│   │   │   ├── semantic.py  # Facts with confidence (Graphiti + pgvector)
│   │   │   ├── procedural.py # Learned workflows (Supabase)
│   │   │   ├── prospective.py # Future tasks (Supabase)
│   │   │   └── lead_memory.py # Sales pursuit tracking (both)
│   │   ├── core/
│   │   │   ├── config.py    # Pydantic settings
│   │   │   ├── ooda.py      # OODA loop implementation
│   │   │   ├── llm.py       # Claude API client
│   │   │   └── exceptions.py # Custom exceptions
│   │   ├── db/
│   │   │   ├── supabase.py  # Supabase client
│   │   │   └── graphiti.py  # Graphiti/Neo4j client
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/      # Reusable UI components
│   │   │   └── ui/          # shadcn/ui components
│   │   ├── pages/           # Route pages
│   │   ├── hooks/           # Custom React hooks
│   │   ├── api/             # API client functions
│   │   ├── contexts/        # React contexts (Auth, etc.)
│   │   └── App.tsx
│   ├── package.json
│   └── tsconfig.json
├── docs/                    # PRD and phase documents
│   ├── ARIA_PRD.md
│   ├── PHASE_1_FOUNDATION.md
│   ├── PHASE_2_MEMORY.md
│   ├── PHASE_3_AGENTS.md
│   ├── PHASE_4_FEATURES.md
│   ├── PHASE_5_LEAD_MEMORY.md
│   └── PHASE_6_ADVANCED.md
├── .claude/
│   ├── skills/              # Claude Code skills
│   │   └── frontend-design/ # UI generation skill
│   └── agents/              # Subagents for specialized tasks
├── scripts/                 # Build and utility scripts
└── CLAUDE.md               # This file
```

---

## Commands Reference

```bash
# Backend Development
cd backend
pip install -r requirements.txt     # Install dependencies
uvicorn src.main:app --reload --port 8000  # Run dev server
pytest tests/ -v                    # Run tests
pytest tests/test_specific.py -v    # Run specific test file
mypy src/ --strict                  # Type check
ruff check src/ --fix               # Lint and auto-fix
ruff format src/                    # Format code

# Frontend Development
cd frontend
npm install                         # Install dependencies
npm run dev                         # Run dev server (port 3000)
npm run build                       # Production build
npm run typecheck                   # TypeScript check
npm run lint                        # ESLint
npm run lint:fix                    # ESLint with auto-fix
npm run test                        # Run tests
npm run test:watch                  # Tests in watch mode

# Database
supabase start                      # Start local Supabase
supabase db reset                   # Reset database
supabase migration new <name>       # Create migration

# Neo4j (for Graphiti)
docker-compose up neo4j             # Start Neo4j container
```

---

## Code Style Guidelines

### Python (Backend)

```python
# ALWAYS use type hints
async def get_user_by_id(user_id: str) -> User | None:
    """Fetch user by ID from database.
    
    Args:
        user_id: The unique identifier for the user.
        
    Returns:
        User object if found, None otherwise.
    """
    pass

# Use Pydantic for request/response models
class CreateGoalRequest(BaseModel):
    title: str
    description: str | None = None
    goal_type: GoalType

# Async/await for ALL I/O operations
async def process_message(message: str) -> str:
    result = await llm_client.generate(message)
    await memory.store_episode(result)
    return result

# NEVER use print() - use logging
import logging
logger = logging.getLogger(__name__)
logger.info("Processing goal", extra={"goal_id": goal_id})

# Custom exceptions with context
class LeadNotFoundError(ARIAException):
    def __init__(self, lead_id: str):
        super().__init__(
            message=f"Lead {lead_id} not found",
            code="LEAD_NOT_FOUND",
            status_code=404
        )
```

### TypeScript (Frontend)

```typescript
// Use ES modules with named exports (NOT default exports)
export { UserProfile } from './UserProfile';
export { useAuth } from './useAuth';

// Destructure imports
import { useState, useEffect, useCallback } from 'react';
import { Button, Card, Input } from '@/components/ui';

// Interface over type where possible
interface User {
  id: string;
  email: string;
  fullName: string;
  companyId: string;
}

// Props interfaces for components
interface GoalCardProps {
  goal: Goal;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
}

// Functional components with hooks
export function GoalCard({ goal, onEdit, onDelete }: GoalCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  
  return (
    // JSX here
  );
}

// NEVER use 'any' - use 'unknown' and type guards instead
function processApiResponse(data: unknown): User {
  if (!isUser(data)) {
    throw new Error('Invalid user data');
  }
  return data;
}
```

### CSS/Styling

```typescript
// Use Tailwind CSS classes directly - NO separate CSS files
// Use shadcn/ui components as the foundation
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardContent } from '@/components/ui/card';

// When frontend-design skill is active, follow its guidance:
// - Choose distinctive fonts (NOT Inter, Arial, Roboto)
// - Use atmospheric backgrounds, not plain white
// - Implement purposeful animations
// - Commit to a cohesive aesthetic theme
```

---

## Memory System Architecture

ARIA has six memory types. ALWAYS consider which type applies:

| Type | Storage | When to Use |
|------|---------|-------------|
| **Working** | In-memory | Current conversation context only |
| **Episodic** | Graphiti (Neo4j) | Past events, interactions, meetings |
| **Semantic** | Graphiti + pgvector | Facts with confidence scores |
| **Procedural** | Supabase | Learned workflows and patterns |
| **Prospective** | Supabase | Future tasks, reminders, follow-ups |
| **Lead** | Graphiti + Supabase | Full sales pursuit lifecycle |

### Memory Storage Rules

```python
# Episodic Memory - Use Graphiti
await graphiti.add_episode(
    name=f"Meeting with {attendee}",
    episode_body=meeting_notes,
    source_description="calendar_sync",
    reference_time=meeting_time
)

# Semantic Memory - Use Graphiti for relationships, pgvector for similarity
fact = SemanticFact(
    subject="Acme Corp",
    predicate="has_budget_cycle",
    object="Q3",
    confidence=0.85,
    source=FactSource.USER_STATED
)

# Procedural Memory - Use Supabase
await supabase.table("procedural_memories").insert({
    "workflow_name": "follow_up_sequence",
    "steps": [...],
    "success_rate": 0.75
})

# Lead Memory - Spans both systems
# - Timeline events → Graphiti (relationships)
# - Structured data → Supabase (queries, CRM sync)
```

### Causal Relationships in Memory (AGI Foundation)

When storing facts or episodes, **always consider causal links**. This enables future implication reasoning.

```python
# GOOD: Captures causality for future reasoning
fact = SemanticFact(
    subject="FDA",
    predicate="rejected",
    object="Competitor X BLA",
    confidence=0.95,
    source=FactSource.EXTRACTED,
    # Include causal metadata when relevant
    metadata={
        "causes": ["competitor_timeline_delay", "market_opportunity"],
        "caused_by": ["incomplete_data_package"],
        "causal_strength": 0.8
    }
)

# BAD: Just the fact, no causal context
fact = SemanticFact(
    subject="FDA",
    predicate="rejected", 
    object="Competitor X BLA"
)
```

### Causal Relationship Types

Use these standard types when extracting cause-effect relationships:

| Type | Meaning | Example |
|------|---------|---------|
| `CAUSES` | Direct causation | FDA rejection CAUSES competitor delay |
| `ENABLES` | Makes possible | Budget approval ENABLES project start |
| `PREVENTS` | Blocks outcome | Regulatory hold PREVENTS trial enrollment |
| `BLOCKS` | Stops progress | Missing data BLOCKS submission |
| `INFLUENCES` | Indirect effect | Market news INFLUENCES stock price |

### Confidence Decay

Facts should age. Implement decay logic:

```python
def calculate_current_confidence(
    original_confidence: float,
    fact_age_days: int,
    last_confirmed_days: int | None = None
) -> float:
    """
    Confidence decays 5% per month if not refreshed.
    Confirmation resets decay.
    """
    if last_confirmed_days is not None:
        decay_days = last_confirmed_days
    else:
        decay_days = fact_age_days
    
    decay_rate = 0.05 / 30  # 5% per month
    decay = decay_rate * decay_days
    
    return max(0.1, original_confidence - decay)  # Floor at 0.1
```

---

## Agent System (OODA Loop)

All agents follow the OODA loop: **Observe → Orient → Decide → Act**

```python
# When implementing agent logic:
class HunterAgent(BaseAgent):
    async def execute(self, task: dict) -> AgentResult:
        # 1. OBSERVE - Gather context
        memory_context = await self.memory.query_relevant(task)
        
        # 2. ORIENT - Analyze situation
        analysis = await self.llm.analyze(memory_context, task)
        
        # 3. DECIDE - Select action
        action = await self.llm.select_action(analysis)
        
        # 4. ACT - Execute and return
        result = await self._execute_action(action)
        
        # Store in episodic memory
        await self.memory.store_episode(result)
        
        # ALWAYS record outcome for future learning
        await self.record_outcome(
            action_type=self.name,
            input_summary=task.get("summary"),
            output_summary=result.summary,
            success=result.success,
            metrics={
                "execution_time_ms": result.duration,
                "tokens_used": result.tokens,
                "confidence": result.confidence
            }
        )
        
        return result
```

---

## Security Architecture (Enterprise-Ready)

ARIA will be sold to enterprises. Build security in from day 1.

### Action Risk Classification

Every autonomous action has a risk level:

```python
class ActionRisk(Enum):
    LOW = "low"           # Read-only, internal only
    MEDIUM = "medium"     # Modifies internal state
    HIGH = "high"         # External communication
    CRITICAL = "critical" # Financial, legal, irreversible

# Examples
ACTION_RISK_MAP = {
    "query_memory": ActionRisk.LOW,
    "update_goal_progress": ActionRisk.MEDIUM,
    "send_email": ActionRisk.HIGH,
    "submit_contract": ActionRisk.CRITICAL,
}
```

### Audit Trail Requirements

Log every significant action:

```python
async def audit_log(
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    risk_level: ActionRisk,
    details: dict,
    outcome: str  # success, failure, pending_approval
) -> None:
    """Every action that modifies state or communicates externally MUST be logged."""
    await supabase.table("audit_log").insert({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "risk_level": risk_level.value,
        "details": details,
        "outcome": outcome,
        "timestamp": datetime.utcnow().isoformat()
    })
```

### Human-in-the-Loop for High-Risk Actions

```python
async def execute_with_approval(
    action: Action,
    risk_level: ActionRisk
) -> ActionResult:
    if risk_level in [ActionRisk.HIGH, ActionRisk.CRITICAL]:
        # Queue for approval, don't execute
        approval_request = await create_approval_request(action)
        return ActionResult(
            status="pending_approval",
            approval_id=approval_request.id,
            message="Action requires user approval"
        )
    else:
        # Execute immediately
        return await execute_action(action)
```

---

## Database Conventions

### Supabase Tables

```sql
-- ALWAYS enable RLS on every table
ALTER TABLE table_name ENABLE ROW LEVEL SECURITY;

-- ALWAYS create user isolation policy
CREATE POLICY "Users can only access own data" ON table_name
    FOR ALL USING (user_id = auth.uid());

-- ALWAYS include audit columns
created_at TIMESTAMPTZ DEFAULT NOW(),
updated_at TIMESTAMPTZ DEFAULT NOW()

-- Use UUID for all primary keys
id UUID PRIMARY KEY DEFAULT gen_random_uuid()

-- Index foreign keys and common query columns
CREATE INDEX idx_tablename_user_id ON table_name(user_id);
CREATE INDEX idx_tablename_status ON table_name(status);
```

### Graphiti (Neo4j)

```python
# Use typed relationships
# Lead Memory relationships:
# - OWNED_BY → User
# - HAS_CONTACT → Stakeholder
# - HAS_COMMUNICATION → Email/Meeting
# - ABOUT_COMPANY → Company
# - SYNCED_TO → CRM Record

# Causal relationships (for AGI reasoning):
# - CAUSES → Effect
# - ENABLES → Possibility
# - PREVENTS → Blocked outcome
# - INFLUENCES → Indirect effect

# Always include temporal metadata
await graphiti.add_episode(
    reference_time=datetime.now(),  # When event occurred
    # ... other params
)
```

---

## API Design Standards

```python
# Consistent endpoint patterns
POST   /api/v1/{resource}           # Create
GET    /api/v1/{resource}           # List
GET    /api/v1/{resource}/{id}      # Get single
PATCH  /api/v1/{resource}/{id}      # Update
DELETE /api/v1/{resource}/{id}      # Delete
POST   /api/v1/{resource}/{id}/action  # Custom action

# Consistent error responses
{
    "detail": "Human-readable error message",
    "code": "ERROR_CODE",
    "request_id": "uuid-for-tracking"
}

# Pagination for list endpoints
{
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "has_more": true
}
```

---

## Testing Requirements

Every feature needs:

1. **Unit tests** - Business logic in isolation
2. **Integration tests** - API endpoints with database
3. **Type coverage** - mypy strict mode must pass

```python
# Test file naming: test_{module}.py
# Test function naming: test_{function}_{scenario}

async def test_create_goal_success():
    """Test successful goal creation."""
    pass

async def test_create_goal_invalid_type_returns_400():
    """Test that invalid goal type returns 400."""
    pass

async def test_create_goal_unauthorized_returns_401():
    """Test that missing auth returns 401."""
    pass
```

---

## Frontend UI Standards

### When frontend-design skill is active:

1. **Typography**: Use distinctive fonts, NEVER Inter/Arial/Roboto
2. **Color**: Commit to cohesive themes, use CSS variables
3. **Motion**: Purposeful animations, staggered reveals on load
4. **Backgrounds**: Atmospheric depth, not plain solid colors
5. **Layout**: Asymmetry and unexpected compositions when appropriate

### Component Patterns

```typescript
// Use shadcn/ui as foundation
import { Card, CardHeader, CardContent, CardFooter } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

// Consistent loading states
if (isLoading) return <Skeleton className="h-48 w-full" />;

// Consistent error states
if (error) return <ErrorCard message={error.message} onRetry={refetch} />;

// Empty states with clear CTAs
if (items.length === 0) return <EmptyState onAction={handleCreate} />;
```

---

## Intelligence Pulse (Proactive Surfacing)

Instead of just responding to queries, ARIA proactively surfaces important information.

### Salience Scoring

When deciding what to surface to the user, score by salience:

```python
def calculate_salience(
    content: str,
    user_goals: list[Goal],
    recency_hours: float,
    is_surprising: bool = False
) -> float:
    """
    Salience = how important is this to surface right now?
    """
    score = 0.0
    
    # Goal relevance (0-0.4)
    goal_relevance = calculate_goal_overlap(content, user_goals)
    score += goal_relevance * 0.4
    
    # Recency (0-0.3) - exponential decay
    recency_score = math.exp(-recency_hours / 168)  # 1 week half-life
    score += recency_score * 0.3
    
    # Surprise bonus (0-0.3) - unexpected info is more salient
    if is_surprising:
        score += 0.3
    
    return min(1.0, score)
```

### Pulse Types

```python
class PulseType(Enum):
    ALERT = "alert"         # Something needs attention NOW
    INSIGHT = "insight"     # Connection or pattern discovered
    REMINDER = "reminder"   # Upcoming commitment or deadline
    ANOMALY = "anomaly"     # Something unusual detected
```

---

## Security Checklist

- [ ] RLS policies on ALL Supabase tables
- [ ] User isolation in ALL queries
- [ ] JWT validation on ALL protected routes
- [ ] Input validation with Pydantic
- [ ] No sensitive data in logs
- [ ] No secrets in code (use environment variables)
- [ ] CORS configured for specific origins only
- [ ] Audit logging for all state-changing operations
- [ ] Risk classification for autonomous actions

---

## Performance Targets

| Operation | Target |
|-----------|--------|
| Chat first token | < 1s (p95) |
| Memory query | < 200ms (p95) |
| Page load | < 2s (p95) |
| Simple API endpoints | < 500ms (p95) |

---

## Development Workflow

### For each User Story:

1. **Read** the user story and acceptance criteria completely
2. **Plan** the implementation approach
3. **Implement** following code style guidelines
4. **Test** - write tests, ensure they pass
5. **Quality check** - run ALL quality gates
6. **Commit** - only after gates pass

### Commit Message Format

```
type(scope): description

feat(memory): implement episodic memory storage
fix(auth): handle expired JWT tokens correctly
test(goals): add integration tests for goal creation
docs(readme): update setup instructions
```

---

## AGI-Ready Development Checklist

When implementing any feature, ask:

- [ ] **Causal Links:** Does this capture cause-effect relationships?
- [ ] **Outcome Recording:** Will we be able to learn from this later?
- [ ] **Confidence Tracking:** Do we know how certain we are?
- [ ] **Salience Scoring:** Can we prioritize this against other information?
- [ ] **Audit Trail:** Is this action logged for enterprise compliance?
- [ ] **Risk Classification:** What could go wrong if this runs autonomously?

---

## Do Not

- ❌ Skip RLS policies on tables
- ❌ Use `any` type in TypeScript
- ❌ Commit .env files
- ❌ Hardcode API keys or secrets
- ❌ Ignore error handling
- ❌ Skip input validation
- ❌ Use `print()` instead of logging
- ❌ Commit code that fails quality gates
- ❌ Use generic fonts (Inter, Arial, Roboto) in UI
- ❌ Create plain white backgrounds in UI
- ❌ Skip writing tests
- ❌ Store facts without considering causal relationships
- ❌ Execute actions without recording outcomes

---

## Documentation

Read the PRD files before implementing:
- `docs/ARIA_PRD.md` - Main overview and architecture
- `docs/PHASE_*.md` - Detailed user stories per phase

**ALWAYS complete user stories in order within each phase.**

---

## Environment Variables Required

```bash
# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=

# Anthropic
ANTHROPIC_API_KEY=

# Neo4j (Graphiti)
NEO4J_URI=
NEO4J_USER=
NEO4J_PASSWORD=

# Tavus (Phase 6)
TAVUS_API_KEY=

# Daily.co (Phase 6)
DAILY_API_KEY=

# Composio
COMPOSIO_API_KEY=

# App
APP_SECRET_KEY=
APP_ENV=development
```

---

## Quick Reference

### Start Development
```bash
# Terminal 1: Backend
cd backend && uvicorn src.main:app --reload

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: Database (if local)
supabase start
```

### Before Every Commit
```bash
# Backend
cd backend && pytest && mypy src/ --strict && ruff check src/

# Frontend
cd frontend && npm run typecheck && npm run lint && npm run test && npm run build
```
