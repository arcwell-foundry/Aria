# CLAUDE.md - ARIA Project Configuration

## Project Overview

ARIA (Autonomous Reasoning & Intelligence Agent) is an AI-powered Department Director for Life Sciences commercial teams. Premium SaaS at $200K/year.

**Key Value:** Solve the "72% admin trap" - sales reps spend most time on admin, not selling.

## Tech Stack

- **Backend:** Python 3.11+ / FastAPI / Uvicorn
- **Frontend:** React 18 / TypeScript / Vite / Tailwind CSS
- **Database:** Supabase (PostgreSQL + pgvector)
- **Knowledge Graph:** Graphiti on Neo4j
- **LLM:** Anthropic Claude API (claude-sonnet-4-20250514)
- **Video:** Tavus + Daily.co
- **Integrations:** Composio for OAuth
- **Email Service:** Resend/SendGrid (transactional emails)
- **Payments:** Stripe (billing & subscriptions)

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
```

## Project Structure

```
aria/
├── backend/src/
│   ├── api/routes/          # FastAPI route handlers
│   ├── agents/              # ARIA's specialized agents (Hunter, Analyst, Strategist, Scribe, Operator, Scout)
│   ├── memory/              # Six-type memory system + Memory Delta Presenter
│   │   ├── delta_presenter.py   # Reusable Memory Delta pattern (US-920)
│   │   ├── profile_merge.py     # Profile update → memory merge pipeline (US-922)
│   │   └── retroactive_enrichment.py  # Post-ingestion back-enrichment (US-923)
│   ├── onboarding/          # Intelligence Initialization (Phase 9A)
│   │   ├── orchestrator.py      # State machine & step coordination (US-901)
│   │   ├── adaptive_controller.py  # OODA-driven step adaptation (US-916)
│   │   ├── enrichment.py        # Company Enrichment Engine (US-903)
│   │   ├── email_bootstrap.py   # Priority email ingestion (US-908)
│   │   ├── gap_detector.py      # Knowledge gap → Prospective Memory (US-912)
│   │   ├── readiness.py         # Readiness score per memory domain (US-913)
│   │   ├── first_conversation.py  # Intelligence demonstration (US-914)
│   │   ├── activation.py        # Agent activation on completion (US-915)
│   │   ├── skill_recommender.py # Skills pre-configuration (US-918)
│   │   ├── personality_calibrator.py  # Tone calibration from Digital Twin (US-919)
│   │   └── outcome_tracker.py   # Self-improving onboarding (US-924)
│   ├── core/                # Config, OODA loop, LLM client
│   ├── skills/              # Phase 5B skills system
│   └── db/                  # Supabase and Graphiti clients
├── frontend/src/
│   ├── components/
│   │   ├── onboarding/      # Step components (CompanyDiscoveryStep, DocumentUploadStep, etc.)
│   │   ├── memory/          # MemoryDelta component (reusable across app)
│   │   └── ...              # Other component groups
│   ├── pages/               # Route pages
│   ├── hooks/               # Custom React hooks
│   └── api/                 # API client functions
└── docs/                    # PRD and phase documents
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

## Key Patterns

### Memory System
ARIA has six memory types. Always consider which memory type applies:
1. **Working** - Current conversation (in-memory)
2. **Episodic** - Past events (Graphiti)
3. **Semantic** - Facts with confidence (Graphiti + pgvector)
4. **Procedural** - Workflows (Supabase)
5. **Prospective** - Future tasks (Supabase)
6. **Lead** - Sales pursuit tracking (Graphiti + Supabase)

### OODA Loop
ARIA's cognitive process: Observe → Orient → Decide → Act
Always implement this loop for complex tasks. The onboarding flow itself runs through OODA — it adapts based on what ARIA learns at each step.

### Agents
Six core agents: Hunter, Analyst, Strategist, Scribe, Operator, Scout
Extend `BaseAgent` class for any new agents.

### Integration Checklist (Phase 9+)
Every feature that collects or processes data MUST include an Integration Checklist in its implementation. Ask: "Where else does this data need to flow?"

A data point should flow into at least 3 downstream systems. If it only stores in one place, it's a form — not intelligence.

```
Integration Checklist:
- [ ] Data stored in correct memory type(s)
- [ ] Causal graph seeds generated (if applicable)
- [ ] Knowledge gaps identified → Prospective Memory entries created
- [ ] Readiness sub-score updated
- [ ] Downstream features notified (list which)
- [ ] Audit log entry created
- [ ] Episodic memory records the event
```

### Memory Delta Pattern
The Memory Delta is a reusable UX pattern for trust-building. Whenever ARIA learns something significant, she shows the user what she learned with confidence indicators and correction affordances.

Use `MemoryDeltaPresenter` (backend) and `<MemoryDelta>` component (frontend) everywhere ARIA learns:
- Post-onboarding enrichment
- Post-email processing
- Post-meeting debrief
- Profile updates
- Any significant memory event

Confidence → language mapping:
- 95%+ → stated as fact
- 80-94% → "Based on your communications..."
- 60-79% → "It appears that..."
- 40-59% → "I'm not certain, but..."
- <40% → "Can you confirm...?"

### Readiness Scoring
Every user has readiness sub-scores (0-100) across five domains:
- `corporate_memory` (25% weight)
- `digital_twin` (25% weight)
- `relationship_graph` (20% weight)
- `integrations` (15% weight)
- `goal_clarity` (15% weight)

Readiness scores inform feature confidence. Low readiness in a domain = lower confidence disclaimers on features that depend on that domain.

### Continuous Onboarding
Onboarding never truly ends. After formal onboarding, ARIA proactively fills knowledge gaps through natural conversation — not pop-ups. Use `KnowledgeGapDetector` to identify gaps and `ProspectiveMemory` to schedule gap-filling prompts.

### Retroactive Enrichment
When ARIA learns something new, she checks if it enriches earlier memories. Example: Email archive reveals deep relationship with a contact that was only superficially captured during CRM import → retroactively enrich Lead Memory, update stakeholder map, recalculate health score.

Use `RetroactiveEnrichmentService` after major data ingestion events.

### Source Hierarchy for Conflict Resolution
When data conflicts, follow this priority:
1. User-stated (confidence 0.95)
2. CRM data (confidence 0.85)
3. Document-extracted (confidence 0.80)
4. Web research (confidence 0.70)
5. Inferred/causal (confidence 0.50-0.60)

### Causal Graph Seeding
During enrichment and data processing, generate causal hypotheses using the LLM. Tag as `source: inferred_during_[context]` with confidence 0.50-0.60. These feed Phase 7 Jarvis engines later. Example: "Series C funding → hiring ramp likely → pipeline generation need"

### Personality Calibration
ARIA calibrates her tone per user based on their Digital Twin (writing style, communication patterns). This is NOT mimicry — it adjusts dials (directness, warmth, assertiveness, detail, formality). Use `PersonalityCalibration` service. Recalibrate on every user edit to an ARIA draft.

## Important Notes

- All database tables must have RLS policies
- User isolation is critical (multi-tenant)
- Never expose internal errors to users
- Log all memory operations for audit
- CRM sync: CRM wins for structured data, ARIA wins for insights
- Health scores are 0-100, recalculate on events
- Corporate Memory is shared within a company; Digital Twin is NEVER shared
- Onboarding is intelligence initialization, not form-filling
- Every data collection step should make ARIA measurably smarter
- Cross-user onboarding: User #2+ at a company inherits Corporate Memory, not Digital Twin

## Documentation

Read the PRD files before implementing:
- `docs/ARIA_PRD.md` - Main overview
- `docs/PHASE_*.md` - Detailed user stories per phase (Phases 1-8)
- `docs/PHASE_9_PRODUCT_COMPLETENESS.md` - Intelligence Initialization, SaaS Infrastructure, ARIA Product Experience

Always complete user stories in order within each phase.

## Testing

Every feature needs:
- Unit tests for business logic
- Integration tests for API endpoints
- Quality gates must pass before moving on

## Do Not

- Skip RLS policies on tables
- Use `any` type in TypeScript
- Commit .env files
- Hardcode API keys
- Ignore error handling
- Skip input validation
- Store data in only one system without checking the Integration Checklist
- Share Digital Twin data between users (even within same company)
- Show raw confidence numbers to users (use qualitative language via Memory Delta pattern)
- Build features that collect data without flowing it into downstream systems
- Skip readiness score updates when data changes
