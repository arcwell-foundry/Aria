# ARIA: Autonomous Reasoning & Intelligence Agent
## Product Requirements Document v1.0

**Project:** ARIA - AI-Powered Department Director for Life Sciences Commercial Teams  
**Company:** Lumin Consults  
**Target:** Biotech, Pharma, CDMO, CRO companies  
**Pricing:** $200K/year (premium autonomous AI executive)

---

## 1. Executive Summary

ARIA is a vertical AI solution that functions as an autonomous Department Director for Life Sciences commercial teams. Unlike horizontal AI assistants, ARIA commands specialized agents, maintains sophisticated memory systems, and operates with executive-level authority.

**Core Value Proposition:** Solve the "72% admin trap" where Life Sciences sales reps spend most time on administrative tasks rather than selling. A 5-person team with ARIA performs like 7.

**Key Differentiators:**
- Six-Type Cognitive Memory (including Lead Memory)
- Temporal Knowledge Graph (Graphiti)
- User Digital Twin with writing style fingerprinting
- 15+ Scientific APIs (PubMed, ClinicalTrials.gov, ChEMBL, etc.)
- Dynamic Agent Creation per goal
- Full audit trail of all decisions

---

## 2. Technical Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Backend | Python 3.11+ / FastAPI | API server, agent orchestration |
| Frontend | React 18+ / TypeScript | Web application |
| Database | Supabase (PostgreSQL + pgvector) | Relational data, vector embeddings |
| Knowledge Graph | Graphiti on Neo4j | Temporal memory, relationships |
| LLM | Anthropic Claude API (claude-sonnet-4-20250514) | Reasoning and generation |
| Video | Tavus (Phoenix-3) | AI avatar conversations |
| WebRTC | Daily.co | Real-time video/audio |
| Auth | Supabase Auth + JWT | Multi-tenant authentication |
| Integrations | Composio | OAuth + app connectors |

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        ARIA PLATFORM                            │
├─────────────────────────────────────────────────────────────────┤
│  Frontend (React/TypeScript)                                    │
│  ├── Dashboard        ├── ARIA Chat       ├── Goals UI         │
│  ├── Settings         ├── Lead Memory     ├── Daily Briefing   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend API (FastAPI)                                          │
│  ├── /api/v1/chat          ├── /api/v1/goals                   │
│  ├── /api/v1/agents        ├── /api/v1/memory                  │
│  ├── /api/v1/leads         ├── /api/v1/integrations            │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  Supabase     │    │  Graphiti     │    │  External     │
│  (PostgreSQL) │    │  (Neo4j)      │    │  APIs         │
│  - Users      │    │  - Temporal   │    │  - PubMed     │
│  - Goals      │    │  - Memory     │    │  - ClinTrials │
│  - Sessions   │    │  - Relations  │    │  - Composio   │
└───────────────┘    └───────────────┘    └───────────────┘
```

---

## 4. Quality Gates

These commands must pass for every implementation task:

```bash
# Python Backend
pytest tests/ -v                    # Unit tests
mypy src/ --strict                  # Type checking
ruff check src/                     # Linting
ruff format src/ --check            # Formatting

# React Frontend
npm run typecheck                   # TypeScript check
npm run lint                        # ESLint
npm run test                        # Jest tests
npm run build                       # Build verification
```

---

## 5. Implementation Phases

Development follows six sequential phases. Complete each phase fully before moving to the next.

| Phase | Focus | Dependencies |
|-------|-------|--------------|
| Phase 1 | Foundation & Auth | None |
| Phase 2 | Memory Architecture | Phase 1 |
| Phase 3 | Agent System | Phase 2 |
| Phase 4 | Core Features | Phase 3 |
| Phase 5 | Lead Memory & CRM | Phase 4 |
| Phase 6 | Advanced Intelligence | Phase 5 |

**See:** `PHASE_*.md` files for detailed user stories per phase.

---

## 6. Database Schema Overview

### Core Tables (Supabase)

```sql
-- Users & Auth
users (id, email, full_name, company_id, role, created_at)
companies (id, name, domain, settings, created_at)
user_settings (user_id, preferences, integrations, created_at)

-- Goals & Agents  
goals (id, user_id, title, description, status, strategy, created_at)
goal_agents (id, goal_id, agent_type, config, status, created_at)
agent_executions (id, agent_id, input, output, tokens_used, created_at)

-- Memory System
memory_episodes (id, user_id, content, embedding, metadata, created_at)
memory_semantic (id, user_id, fact, confidence, source, valid_from, valid_to)
memory_procedural (id, user_id, workflow_name, steps, success_rate)
memory_prospective (id, user_id, task, due_date, status, created_at)

-- Lead Memory
lead_memories (id, user_id, company_name, lifecycle_stage, health_score, crm_id)
lead_memory_events (id, lead_memory_id, event_type, content, occurred_at)
lead_memory_stakeholders (id, lead_memory_id, contact_name, role, sentiment)
lead_memory_insights (id, lead_memory_id, insight_type, content, confidence)

-- Conversations & Sessions
conversations (id, user_id, goal_id, created_at)
messages (id, conversation_id, role, content, created_at)
video_sessions (id, user_id, tavus_conversation_id, status, created_at)

-- Integrations
user_integrations (id, user_id, provider, access_token_encrypted, refresh_token)
crm_sync_log (id, user_id, lead_memory_id, direction, status, synced_at)
```

---

## 7. API Endpoints Overview

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/refresh` - Refresh JWT
- `GET /api/v1/auth/me` - Current user

### Chat & Conversations
- `POST /api/v1/chat/message` - Send message to ARIA
- `GET /api/v1/chat/conversations` - List conversations
- `GET /api/v1/chat/conversations/{id}` - Get conversation

### Goals
- `POST /api/v1/goals` - Create goal
- `GET /api/v1/goals` - List user goals
- `PATCH /api/v1/goals/{id}` - Update goal
- `POST /api/v1/goals/{id}/execute` - Execute goal

### Memory
- `GET /api/v1/memory/query` - Query memory system
- `POST /api/v1/memory/episode` - Store episode
- `GET /api/v1/memory/facts` - Get semantic facts

### Lead Memory
- `POST /api/v1/leads` - Create lead memory
- `GET /api/v1/leads` - List lead memories
- `GET /api/v1/leads/{id}` - Get lead memory with full timeline
- `POST /api/v1/leads/{id}/events` - Add event to lead
- `POST /api/v1/leads/{id}/sync` - Sync with CRM

### Agents
- `GET /api/v1/agents/types` - List available agent types
- `POST /api/v1/agents/spawn` - Spawn agent for goal
- `GET /api/v1/agents/{id}/status` - Get agent status

---

## 8. Domain Terminology

| Term | Definition |
|------|------------|
| ARIA | The AI assistant persona (Autonomous Reasoning & Intelligence Agent) |
| Goal | A user-defined objective that ARIA pursues with agents |
| Agent | Specialized worker (Hunter, Analyst, Strategist, Scribe, Operator, Scout) |
| Lead Memory | Longitudinal tracking of a sales pursuit from first touch to customer |
| Episode | A discrete interaction or event stored in episodic memory |
| Semantic Fact | An extracted piece of knowledge with confidence score |
| Digital Twin | User's communication style fingerprint for personalized drafts |
| OODA Loop | Observe-Orient-Decide-Act cognitive processing cycle |
| Health Score | 0-100 score measuring lead engagement and likelihood to close |
| Corporate Memory | Shared organizational knowledge across all users |

---

## 9. File Structure

```
aria/
├── backend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── auth.py
│   │   │   │   ├── chat.py
│   │   │   │   ├── goals.py
│   │   │   │   ├── memory.py
│   │   │   │   ├── leads.py
│   │   │   │   └── agents.py
│   │   │   └── deps.py
│   │   ├── agents/
│   │   │   ├── base.py
│   │   │   ├── hunter.py
│   │   │   ├── analyst.py
│   │   │   ├── strategist.py
│   │   │   ├── scribe.py
│   │   │   ├── operator.py
│   │   │   └── scout.py
│   │   ├── memory/
│   │   │   ├── working.py
│   │   │   ├── episodic.py
│   │   │   ├── semantic.py
│   │   │   ├── procedural.py
│   │   │   ├── prospective.py
│   │   │   └── lead_memory.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── ooda.py
│   │   │   └── llm.py
│   │   ├── db/
│   │   │   ├── supabase.py
│   │   │   └── graphiti.py
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── api/
│   │   └── App.tsx
│   ├── package.json
│   └── tsconfig.json
├── CLAUDE.md
└── docs/
    ├── ARIA_PRD.md
    ├── PHASE_1_FOUNDATION.md
    ├── PHASE_2_MEMORY.md
    ├── PHASE_3_AGENTS.md
    ├── PHASE_4_FEATURES.md
    ├── PHASE_5_LEAD_MEMORY.md
    └── PHASE_6_ADVANCED.md
```

---

## 10. Environment Variables

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

# Tavus
TAVUS_API_KEY=

# Daily.co
DAILY_API_KEY=

# Composio
COMPOSIO_API_KEY=

# App
APP_SECRET_KEY=
APP_ENV=development
```

---

## Next Steps

1. Read `PHASE_1_FOUNDATION.md` for first implementation phase
2. Set up development environment per stack requirements
3. Create Supabase project and configure auth
4. Begin with US-101 (Project Setup)

**Important:** Complete each user story fully before moving to the next. Run quality gates after each story.
