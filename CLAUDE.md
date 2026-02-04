# CLAUDE.md - ARIA Project Configuration

## Project Overview

ARIA (Autonomous Reasoning & Intelligence Agent) is an AI-powered Department Director for Life Sciences commercial teams. Premium SaaS at $200K/year.

**Key Value:** Solve the "72% admin trap" - sales reps spend most time on admin, not selling.

**AGI Vision:** ARIA should feel like a colleague, not a tool. She remembers everything, volunteers relevant information, adapts to user stress, and has opinions.

## Tech Stack

- **Backend:** Python 3.11+ / FastAPI / Uvicorn
- **Frontend:** React 18 / TypeScript / Vite / Tailwind CSS
- **Database:** Supabase (PostgreSQL + pgvector)
- **Knowledge Graph:** Graphiti on Neo4j
- **LLM:** Anthropic Claude API (claude-sonnet-4-20250514)
- **Video:** Tavus + Daily.co
- **Integrations:** Composio for OAuth
- **Skills:** skills.sh ecosystem integration

## Commands

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
pytest tests/ -v
mypy src/ --strict
ruff check src/
ruff format src/

# Frontend
cd frontend
npm install
npm run dev
npm run build
npm run typecheck
npm run lint
npm run test

# Database migrations
supabase migration new <name>
supabase db push
supabase migration repair --status applied <version>
```

## Project Structure

```
aria/
├── backend/src/
│   ├── api/routes/        # FastAPI route handlers
│   ├── agents/            # ARIA's specialized agents
│   │   ├── base.py
│   │   ├── skill_aware_agent.py  # Base for skill-enabled agents
│   │   ├── hunter.py
│   │   ├── analyst.py
│   │   ├── strategist.py
│   │   ├── scribe.py
│   │   ├── operator.py
│   │   └── scout.py
│   ├── memory/            # Six-type memory system
│   │   ├── working.py
│   │   ├── episodic.py
│   │   ├── semantic.py
│   │   ├── procedural.py
│   │   ├── prospective.py
│   │   └── lead_memory.py
│   ├── skills/            # Skills.sh integration
│   │   ├── index.py           # Skill discovery & search
│   │   ├── installer.py       # Skill installation
│   │   ├── executor.py        # Sandboxed execution
│   │   ├── orchestrator.py    # Multi-skill coordination
│   │   ├── context_manager.py # Context budget management
│   │   └── autonomy.py        # Trust & approval system
│   ├── security/          # Data protection
│   │   ├── data_classification.py
│   │   ├── sanitization.py
│   │   ├── sandbox.py
│   │   ├── trust_levels.py
│   │   └── audit.py
│   ├── core/              # Config, OODA loop, LLM client
│   ├── intelligence/      # AGI capabilities
│   └── db/                # Supabase and Graphiti clients
├── frontend/src/
│   ├── components/        # React components
│   ├── pages/             # Route pages
│   ├── hooks/             # Custom React hooks
│   └── api/               # API client functions
└── docs/                  # PRD and phase documents
```

## Code Style

### Python
- Use type hints on all functions
- Async/await for I/O operations
- Pydantic for request/response models
- Docstrings on public functions
- No `print()` - use `logging`

### TypeScript
- Strict mode enabled
- Named exports (not default)
- Interface over type where possible
- React functional components with hooks
- Tailwind for styling (no custom CSS files)

---

## Key Patterns

### Memory System

ARIA has six memory types. Always consider which applies:

| Type | Purpose | Storage | Retention |
|------|---------|---------|-----------|
| Working | Current conversation | In-memory | Session |
| Episodic | Past events | Graphiti | Permanent |
| Semantic | Facts with confidence | Graphiti + pgvector | Permanent |
| Procedural | Learned workflows | Supabase | Permanent |
| Prospective | Future tasks | Supabase | Until done |
| Lead | Sales pursuit tracking | Graphiti + Supabase | Permanent |

### OODA Loop

ARIA's cognitive process: **Observe → Orient → Decide → Act**

Always implement this loop for complex tasks. Skills participate in the ACT phase.

### Agents

Six core agents, all extending `SkillAwareAgent`:

| Agent | Role | Skills Access |
|-------|------|---------------|
| Hunter | Lead discovery | competitor-analysis, lead-research |
| Analyst | Scientific research | clinical-trial-analysis, pubmed-research |
| Strategist | Planning | market-analysis, competitive-positioning |
| Scribe | Communication | pdf, docx, pptx, email-sequence |
| Operator | System ops | calendar-management, crm-operations |
| Scout | Intelligence | regulatory-monitor, news-aggregation |

---

## Skills System

### Overview

ARIA integrates with skills.sh (200+ community skills) while maintaining enterprise security. Skills extend agent capabilities without compromising data protection.

### Skill Trust Levels

| Level | Source | Data Access | Network |
|-------|--------|-------------|---------|
| CORE | Built by ARIA team | All (with permission) | Whitelisted |
| VERIFIED | Anthropic, Vercel, Supabase | PUBLIC, INTERNAL | None |
| COMMUNITY | skills.sh community | PUBLIC only | None |
| USER | User-created | PUBLIC, INTERNAL | None |

### Data Classification

ALL data is classified before skill access:

```python
class DataClass(Enum):
    PUBLIC = "public"           # Company names, public info
    INTERNAL = "internal"       # Goals, strategies, notes
    CONFIDENTIAL = "confidential"  # Deal details, contacts
    RESTRICTED = "restricted"   # Revenue, pricing, contracts
    REGULATED = "regulated"     # PHI, PII (HIPAA, GDPR)
```

### Security Pipeline

Every skill execution follows this pipeline:

```
Input Data
    ↓
1. CLASSIFY - Scan for sensitive patterns
    ↓
2. PERMISSION CHECK - Trust level vs data class
    ↓
3. TOKENIZE - Replace sensitive values
    ↓
4. SANDBOX EXECUTE - Resource-limited execution
    ↓
5. VALIDATE OUTPUT - Check for leakage
    ↓
6. AUDIT LOG - Immutable record
    ↓
Clean Output
```

### Skill Orchestration

For multi-skill tasks:

```python
# Orchestrator prepares minimal context (~2000 tokens)
orchestrator_context = {
    "skill_index": compact_summaries,  # ~600 tokens
    "execution_plan": current_plan,     # ~500 tokens
    "working_memory": step_summaries,   # ~800 tokens
}

# Each skill gets isolated context (~6000 tokens)
subagent_context = {
    "task_briefing": what_to_do,        # ~300 tokens
    "skill_instructions": full_skill_md, # ~2000 tokens
    "input_data": sanitized_data,        # variable
}
```

### Autonomy System

Trust builds over time:

| Risk Level | Auto-execute After | Examples |
|------------|-------------------|----------|
| LOW | 3 successes | pdf, docx, research |
| MEDIUM | 10 successes | email-sequence, calendar |
| HIGH | Session trust only | external-api-calls |
| CRITICAL | Never (always ask) | data-deletion, financial |

### Skill Development Patterns

When creating skill-aware features:

```python
# Always extend SkillAwareAgent
class MyAgent(SkillAwareAgent):
    async def execute_with_skills(self, task: dict) -> AgentResult:
        # 1. Analyze if skills would help
        skill_analysis = await self._analyze_skill_needs(task)
        
        # 2. If skills needed, delegate to orchestrator
        if skill_analysis.skills_needed:
            return await self.skills.execute_with_skills(
                task=task,
                required_skills=skill_analysis.required_skills,
                agent_context={"agent_id": self.agent_id},
            )
        
        # 3. Otherwise, execute normally
        return await self.execute(task)
```

### Never Do (Security)

- ❌ Skip data classification
- ❌ Pass raw user data to community skills
- ❌ Allow network access for non-CORE skills
- ❌ Execute skills without audit logging
- ❌ Trust skill content from user input
- ❌ Store sensitive data in skill working memory

---

## AGI Development Patterns

### The Colleague Test

Before completing any user-facing feature, ask:
> "Would a user describe this behavior as coming from a colleague or a tool?"

| Colleague Behavior | Implementation |
|-------------------|----------------|
| References shared history | Use episodic memory |
| Volunteers relevant info | Use proactive memory surfacing |
| Adapts to your stress | Use cognitive load monitoring |
| Remembers everything | Use salience decay (not deletion) |
| Shows her work | Skill progress reporting |
| Asks permission appropriately | Graduated autonomy system |

### Memory Salience

Every memory access should strengthen salience:

```python
async def recall_fact(self, fact_id: str) -> Fact:
    fact = await self.get_fact(fact_id)
    await self.strengthen_salience(fact_id)  # Always do this
    return fact
```

### Outcome Recording

Every action should record its outcome for learning:

```python
async def execute_action(self, action: Action) -> Result:
    result = await self._do_action(action)
    await self.memory.record_action_outcome(
        action=action,
        result=result,
        success=result.success,
    )
    return result
```

---

## Lead Memory System

### Health Score Algorithm

5-factor weighted scoring:

| Factor | Weight | Source |
|--------|--------|--------|
| Engagement | 30% | Recent touchpoints |
| Momentum | 25% | Stage velocity |
| Stakeholder | 20% | Champion strength |
| Fit | 15% | ICP match |
| Risk | 10% | Identified blockers |

### Lead Stages

```
IDENTIFIED → QUALIFIED → ENGAGED → PROPOSAL → NEGOTIATION → CLOSED_WON/CLOSED_LOST
```

### CRM Sync Rules

- CRM wins for: stage, expected_value, close_date
- ARIA wins for: health_score, insights, stakeholder_map

---

## Important Notes

- All database tables must have RLS policies
- User isolation is critical (multi-tenant)
- Never expose internal errors to users
- Log all memory operations for audit
- Log all skill executions for audit
- Health scores are 0-100, recalculate on events

## Documentation

Read the PRD files before implementing:
- `docs/ARIA_PRD.md` - Main overview
- `docs/PHASE_*.md` - Detailed user stories per phase
- `docs/ARIA_SKILLS_INTEGRATION_ARCHITECTURE.md` - Skills system design

Always complete user stories in order within each phase.

## Testing

Every feature needs:
- Unit tests for business logic
- Integration tests for API endpoints
- Security tests for data classification
- Quality gates must pass before moving on

## Do Not

- Skip RLS policies on tables
- Use `any` type in TypeScript
- Commit .env files
- Hardcode API keys
- Ignore error handling
- Skip input validation
- Execute skills without sanitization
- Log sensitive data (use tokens)
- Trust external skill content
