# ARIA Comprehensive State Audit

**Date:** February 11, 2026
**Prepared for:** External architect review
**Auditor:** Automated analysis of full codebase
**Commit:** a9b14e1 (main branch)

---

## SECTION 1: PROJECT STRUCTURE & FILE INVENTORY

### Code Volume

| Category | Count |
|----------|-------|
| Backend Python files (`backend/src/`) | 203 |
| Frontend TS/TSX files (`frontend/src/`) | 266 (132 active + 134 deprecated) |
| Database migration files | 62 SQL files |
| Backend lines of code | ~102,185 |
| Frontend lines of code | ~64,058 |
| **Total lines of code** | **~166,243** |

### Backend Directory Structure

| Directory | Files | Purpose |
|-----------|-------|---------|
| `agents/` | 16 | 6 core agents + base + orchestrator + dynamic factory + 12 capabilities |
| `api/routes/` | 40 | REST endpoints (38 routers registered + 2 supporting files) |
| `core/` | 12 | Config, OODA loop, LLM client, WebSocket manager, event bus, security |
| `memory/` | 25 | 6 memory types + sub-modules (salience, priming, health score, etc.) |
| `models/` | 22 | Pydantic request/response models |
| `services/` | 35 | Business logic services |
| `onboarding/` | 24 | 8-step onboarding pipeline |
| `skills/` | 31 | Skill engine + 8 skill definitions + 8 workflows |
| `integrations/` | 8 | Tavus, Composio, deep sync, OAuth |
| `intelligence/` | 3 | Cognitive load, proactive memory |
| `jobs/` | 4 | Scheduled jobs (briefings, meeting briefs, salience decay) |
| `security/` | 6 | Data classification, sandbox, sanitization, trust levels |
| `db/` | 3 | Supabase and Graphiti clients |

### Frontend Directory Structure (Active Code Only)

| Directory | Files | Purpose |
|-----------|-------|---------|
| `components/pages/` | 12 | Page-level components |
| `components/conversation/` | 10 | Chat thread, input bar, message rendering |
| `components/shell/` | 18 | Sidebar, IntelPanel + 15 context-adaptive modules |
| `components/avatar/` | 8 | DialogueMode, avatar container, transcript |
| `components/rich/` | 6 | GoalPlanCard, ExecutionPlanCard, AlertCard, etc. |
| `components/primitives/` | 8 | Button, Card, Badge, Input, etc. |
| `components/settings/` | 7 | Settings sub-sections |
| `components/pipeline/` | 2 | LeadTable, HealthBar |
| `components/common/` | 5 | AgentAvatar, CommandPalette, etc. |
| `api/` | 36 | API client functions |
| `hooks/` | 35 | React Query hooks |
| `stores/` | 5 | Zustand stores |
| `core/` | 4 | WebSocketManager, SessionManager, UICommandExecutor, ModalityController |
| `contexts/` | 4 | Auth, Session, Theme, IntelPanel |
| `_deprecated/` | 134 | Old SaaS architecture (NOT imported by active code) |

### Backend Dependencies (requirements.txt)

| Category | Packages |
|----------|----------|
| Core | FastAPI, Uvicorn, Pydantic |
| LLM | anthropic (>=0.40.0) |
| Database | supabase, graphiti-core |
| HTTP | httpx, python-dotenv |
| Documents | PyMuPDF, python-docx, python-pptx, openpyxl, pytesseract, Pillow |
| Integrations | composio |
| Security | pyotp, qrcode |
| Billing | stripe |
| Rate Limiting | slowapi, limits |
| Scheduling | apscheduler |
| Email | resend |
| Testing/Dev | pytest, pytest-asyncio, pytest-cov, mypy, ruff |

### Frontend Dependencies (package.json)

| Category | Packages |
|----------|----------|
| Framework | React 19.2, React Router DOM 7.13 |
| State | Zustand 5.0, @tanstack/react-query 5.90 |
| UI | Tailwind CSS 4.1, Lucide React, Framer Motion 11.18 |
| Rich Text | @tiptap/react 3.19 |
| Charts | Recharts 2.15 |
| Build | Vite 7.2, TypeScript 5.9 |
| Testing | Vitest 4.0, @testing-library/react 16.3 |

---

## SECTION 2: DATABASE STATE

### Migration Files

62 SQL migrations spanning from `001_initial_schema.sql` through `20260211200000_add_battle_card_analysis.sql`.

### Table Audit

| Table | EXISTS? | Migration File |
|-------|---------|----------------|
| `conversations` | **Y** | `20260202000006_create_conversations.sql` + `20260209000000_repair_conversations_table.sql` |
| `messages` | **Y** | `20260209000001_create_messages.sql` |
| `onboarding_state` | **Y** | `20260206000000_onboarding_state.sql` |
| `onboarding_outcomes` | **Y** | `20260207120000_onboarding_outcomes.sql` |
| `goals` | **Y** | `002_goals_schema.sql` |
| `goal_milestones` | **Y** | `20260208020000_goal_lifecycle.sql` |
| `goal_updates` | **N** | No CREATE TABLE in any migration. **MISSING.** |
| `goal_retrospectives` | **Y** | `20260208020000_goal_lifecycle.sql` |
| `episodic_memories` | **Y** | `20260211000000_missing_tables_comprehensive.sql` |
| `semantic_facts` | **Y** | `20260211000000_missing_tables_comprehensive.sql` |
| `discovered_leads` | **Y** | `20260207170000_lead_generation.sql` |
| `lead_icp_profiles` | **Y** | `20260207170000_lead_generation.sql` |
| `aria_actions` | **Y** | `20260207130000_roi_analytics.sql` |
| `aria_activity` | **Y** | `20260208030000_activity_feed.sql` |
| `daily_briefings` | **Y** | `20260203000001_create_daily_briefings.sql` |
| `user_settings` | **Y** | `001_initial_schema.sql` |
| `skill_execution_plans` | **Y** | `20260210000000_skills_engine_tables.sql` |
| `skill_working_memory` | **Y** | `20260210000000_skills_engine_tables.sql` |

**Result:** 17 of 18 tables exist. `goal_updates` is missing from all migrations.

### Notable Database Issues

1. **Dual action tables:** Both `aria_actions` (in `roi_analytics.sql`) and `aria_action_queue` (in `action_queue.sql`) exist. May be overlapping or one may be dead.
2. **`conversations` table repaired:** Was recreated in a repair migration, suggesting schema issues were encountered.
3. **`messages` table defined twice:** Both in `20260209000001` and `20260210000000` with `IF NOT EXISTS` -- safe but indicates coordination gaps.

---

## SECTION 3: BACKEND API ROUTES

### Router Registration

**38 routers registered** in `main.py` at prefix `/api/v1` + 1 WebSocket at root + 4 system health endpoints.

### Complete Route Inventory

| Router File | Prefix | Key Endpoints | Endpoint Count |
|-------------|--------|---------------|----------------|
| `auth.py` | `/auth` | signup, login, logout, refresh, me | 5 |
| `chat.py` | `/chat` | send message, stream, conversations, messages | 6 |
| `goals.py` | `/goals` | create, propose, plan, execute, events (SSE), cancel, CRUD | 23 |
| `leads.py` | `/leads` | list, create, update, pipeline, timeline, stakeholders, insights, export | 27 |
| `onboarding.py` | `/onboarding` | state, steps, company discovery, documents, email, integrations, first goal, activate | 40+ |
| `memory.py` | `/memory` | query, store episode/fact/task/workflow, fingerprint, corporate, prime, delta | 19 |
| `briefings.py` | `/briefings` | today, list, by-date, generate, regenerate, deliver | 6 |
| `battle_cards.py` | `/battlecards` | list, get, create, update, delete, history, objections | 7 |
| `action_queue.py` | `/actions` | list, create, pending-count, approve, reject, execute | 8 |
| `activity.py` | `/activity` | list, agents, get, create | 4 |
| `drafts.py` | `/drafts` | create email, list, get, update, delete, regenerate, send | 7 |
| `integrations.py` | `/integrations` | list, available, auth-url, callback, disconnect, sync | 6 |
| `signals.py` | `/signals` | list, unread count, read, dismiss, monitored | 8 |
| `skills.py` | `/skills` | available, installed, install, execute, feedback, performance, audit, autonomy | 13 |
| `video.py` | `/video` | create session, get session, end session | 3 |
| `meetings.py` | `/meetings` | upcoming, brief, generate brief | 3 |
| `notifications.py` | `/notifications` | list, unread count, mark read, read all, delete | 5 |
| `billing.py` | `/billing` | status, checkout, portal, webhook, invoices | 5 |
| `admin.py` | `/admin` | team, invites, roles, company, audit log | 11 |
| `profile.py` | `/profile` | get, update user, update company, documents, preferences | 5 |
| `account.py` | `/account` | profile, 2FA setup/verify, sessions, API keys | 10 |
| `accounts.py` | `/accounts` | territory, forecast, quota, plans | 7 |
| `analytics.py` | `/analytics` | ROI, trend, export | 3 |
| `predictions.py` | `/predictions` | create, list, pending, calibration, accuracy, validate | 7 |
| `search.py` | `/search` | global, recent | 2 |
| `workflows.py` | `/workflows` | prebuilt, CRUD, execute | 7 |
| `compliance.py` | `/compliance` | content audit, rules, reports | 7 |
| `debriefs.py` | `/debriefs` | create, list, get, by meeting | 4 |
| `deep_sync.py` | `/integrations/sync` | sync, status, queue, config | 4 |
| `social.py` | `/social` | drafts, approve, reject, publish, schedule, stats | 8 |
| `feedback.py` | `/feedback` | response feedback, general feedback | 2 |
| `perception.py` | `/perception` | emotion, engagement | 2 |
| `cognitive_load.py` | `/user` | cognitive load, history | 2 |
| `communication.py` | `/communicate` | send communication | 1 |
| `aria_config.py` | `/aria-config` | get, update, reset personality, preview | 4 |
| `preferences.py` | `/settings/preferences` | get, update | 2 |
| `email_preferences.py` | `/settings/email-preferences` | get, update | 2 |
| `insights.py` | `/insights` | proactive, engage, dismiss, history | 4 |
| `ambient_onboarding.py` | `/ambient-onboarding` | status, fill gaps | 2 |
| `websocket.py` | (root) | `/ws/{user_id}` | 1 |

**Approximate total: ~280 endpoints across 38 REST routers + 1 WebSocket.**

### Route Issues

| Issue | Severity |
|-------|----------|
| `skill_replay.py` exists but is NOT registered in `main.py` -- `/api/v1/audit/*` endpoints unreachable | HIGH |
| `account.py` `/profile` overlaps with `profile.py` `/profile` -- duplicate user profile endpoints | MEDIUM |
| `cognitive_load.py` mounted at `/user` prefix -- naming mismatch with file | LOW |

---

## SECTION 4: FRONTEND PAGES & ROUTING

### Route Table

| Route | Component | IDD v3 Layer | Architecture |
|-------|-----------|-------------|--------------|
| `/login` | `LoginPage` | Auth | N/A |
| `/signup` | `SignupPage` | Auth | N/A |
| `/` (index) | `ARIAWorkspace` | Layer 1 (ARIA Workspace) | IDD v3 compliant |
| `/dialogue` | `DialogueMode` | Layer 1a (Dialogue) | IDD v3 compliant |
| `/briefing` | `DialogueMode` (sessionType="briefing") | Layer 1a (Briefing) | IDD v3 compliant |
| `/pipeline` | `PipelinePage` | Layer 2 (Content) | IDD v3 compliant |
| `/pipeline/leads/:leadId` | `PipelinePage` | Layer 2 (Detail) | IDD v3 compliant |
| `/intelligence` | `IntelligencePage` | Layer 2 (Content) | IDD v3 compliant |
| `/intelligence/battle-cards/:competitorId` | `IntelligencePage` | Layer 2 (Detail) | IDD v3 compliant |
| `/communications` | `CommunicationsPage` | Layer 2 (Content) | IDD v3 compliant |
| `/communications/drafts/:draftId` | `CommunicationsPage` | Layer 2 (Detail) | IDD v3 compliant |
| `/actions` | `ActionsPage` | Layer 2 (Content) | IDD v3 compliant |
| `/actions/goals/:goalId` | `ActionsPage` | Layer 2 (Detail) | IDD v3 compliant |
| `/settings` | `SettingsPage` | Layer 3 (Config) | IDD v3 compliant |
| `/settings/:section` | `SettingsPage` | Layer 3 (Config) | IDD v3 compliant |

**All 16 routes follow IDD v3 architecture. Zero imports from `_deprecated/`.**

### Orphaned Page Components (exist but not routed)

- `BriefingPage.tsx` -- superseded by DialogueMode with sessionType="briefing"
- `BattleCardDetail.tsx` -- detail handled inline by IntelligencePage
- `LeadDetailPage.tsx` -- detail handled inline by PipelinePage
- `DraftDetailPage.tsx` -- detail handled inline by CommunicationsPage

---

## SECTION 5: AGENT SYSTEM

### Agent Inventory

| Agent | File | Lines | Implementation | Imported By | Trigger |
|-------|------|-------|----------------|-------------|---------|
| **Hunter** | `agents/hunter.py` | 438 | Full: ICP search, company filtering, enrichment, contact finding, fit scoring | GoalExecutionService, LeadGenerationService | Goal execution, lead discovery API, OODA "search" |
| **Analyst** | `agents/analyst.py` | 639 | Full: PubMed, ClinicalTrials.gov, FDA, ChEMBL API calls with depth-based execution | GoalExecutionService | Goal execution, OODA "research" |
| **Strategist** | `agents/strategist.py` | 1,092 | Full: Strategy creation, phase/milestone generation, task assignment | GoalExecutionService | Goal execution, OODA "plan" |
| **Scribe** | `agents/scribe.py` | 539 | Full: Communication drafting, style matching via Digital Twin, email/doc/message types | GoalExecutionService | Goal execution, OODA "communicate" |
| **Operator** | `agents/operator.py` | 449 | Full: Calendar read/write, CRM operations via Composio | GoalExecutionService | Goal execution, OODA "schedule" |
| **Scout** | `agents/scout.py` | 457 | Full: Web search, news monitoring, signal filtering, deduplication | GoalExecutionService, MeetingBriefService | Goal execution, meeting briefs, OODA "monitor" |

### Agent Infrastructure

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| BaseAgent (ABC) | `agents/base.py` | 298 | Solid abstract base with `AgentResult`, `AgentStatus`, abstract `execute` |
| AgentOrchestrator | `agents/orchestrator.py` | 480 | Real parallel/sequential execution, token/concurrency limits |
| DynamicAgentFactory | `agents/dynamic_factory.py` | -- | Runtime agent creation support |
| SkillAwareAgent | `agents/skill_aware_agent.py` | -- | Intermediate base adding skill orchestration |
| 12 Capabilities | `agents/capabilities/` | -- | Calendar, CRM, email, LinkedIn, meeting, messenger, signal, web, compliance, enrichment |

### OODA Loop (`core/ooda.py`, 870 lines)

- Fully implemented 4-phase loop: Observe, Orient, Decide, Act
- Memory integration: queries Episodic, Semantic, Working memory during Observe
- Agent dispatch: Act phase dispatches via configurable `agent_executor` callback
- Config: 50K token budget, max 10 iterations

### Verdict

**All 6 agents are fully implemented with real business logic, properly wired into GoalExecutionService, and triggered by goal execution + OODA decisions.** This is not a stub system.

---

## SECTION 6: MEMORY SYSTEM

### Memory Type Audit

| Memory Type | File | Lines | Store/Retrieve | Called in Chat | DB Table | E2E Flow |
|-------------|------|-------|----------------|----------------|----------|----------|
| **Episodic** | `memory/episodic.py` | 626 | Y (store_episode, get_episode, semantic_search) | Y (store after every turn, query before response) | Graphiti/Neo4j | **Y** |
| **Semantic** | `memory/semantic.py` | 907 | Y (add_fact, get_fact, search_facts, invalidate_fact) | Y (query during chat, OODA observe) | Graphiti/Neo4j + pgvector | **Y** |
| **Procedural** | `memory/procedural.py` | 543 | Y (create_workflow, get_workflow, record_outcome) | Y (query during chat) | `procedural_memories` | **Y** |
| **Working** | `memory/working.py` | 258 | Y (add_message, get_context_for_llm) | Y (heavy use every turn) | In-memory only | **PARTIAL** |
| **Prospective** | `memory/prospective.py` | 635 | Y (create_task, get_upcoming, get_overdue) | Y (query during chat) | `prospective_memories` | **Y** |
| **Lead Memory** | `memory/lead_memory.py` | 886 | Y (create, get_by_id, list, update, health score) | N (not in unified chat query) | `lead_memories` | **PARTIAL** |

### Memory Gaps

1. **Working Memory not persisted:** CLAUDE.md spec says "Session-scoped; persisted on end." Current implementation is purely in-memory (`dict[str, WorkingMemory]`). Lost on server restart.
2. **Lead Memory excluded from chat context:** The `MemoryQueryService` queries episodic, semantic, procedural, and prospective during chat, but NOT lead memory. ARIA cannot automatically recall lead details in conversation.

### Chat Memory Flow

```
User message → WorkingMemory.add_message()
            → MemoryQueryService.query() [episodic, semantic, procedural, prospective in parallel]
            → Build memory context string
            → Inject into system prompt
            → Claude API call
            → Store conversation turn as episodic memory
            → WorkingMemory.add_message() for assistant response
            → Return response
```

---

## SECTION 7: CHAT SYSTEM (End-to-End)

### Message Flow Trace

```
[InputBar] → user types, presses Enter
    ↓
[ARIAWorkspace.handleSend] → adds to Zustand store (optimistic) + wsManager.send('user.message', {...})
    ↓
[WebSocketManager.send]
    ├── WS OPEN: sends JSON envelope over WebSocket
    │       ↓
    │   [Backend WS handler] → ONLY handles "ping" → user.message SILENTLY DROPPED ❌
    │
    └── SSE FALLBACK: POSTs to /api/v1/chat/stream
            ↓
        [chat.py /stream endpoint] → ChatService → memory query → LLM call → SSE tokens → response ✅
```

### CRITICAL BUG: WebSocket Does Not Handle Chat Messages

**The backend WebSocket handler (`api/routes/websocket.py`) only processes `"ping"` messages.** It has no handler for `"user.message"`, `"heartbeat"`, `"user.navigate"`, `"user.approve"`, `"user.reject"`, or any other client event.

**Impact:** When WebSocket is connected (which is the primary path), the user's message is sent, the backend receives it, and **silently drops it**. The user sees their message appear but never gets a response.

**Saving grace:** If the WebSocket fails to connect (server down, CORS block, timeout), the frontend falls back to SSE mode which POSTs to `/api/v1/chat/stream` -- this path works end-to-end.

### Additional WebSocket Issues

| Issue | Detail | Impact |
|-------|--------|--------|
| Session param name mismatch | Frontend sends `?session=`, backend expects `?session_id=` | Session binding always null |
| Heartbeat event mismatch | Frontend sends `"heartbeat"`, backend only handles `"ping"` | Connection may timeout behind proxies |

### REST Chat Endpoints (working)

| Method | Path | Status |
|--------|------|--------|
| POST | `/api/v1/chat` | Works (non-streaming, not used by ARIAWorkspace) |
| POST | `/api/v1/chat/stream` | Works (SSE streaming, used only in fallback) |
| GET | `/api/v1/chat/conversations` | Works |
| GET | `/api/v1/chat/conversations/{id}/messages` | Works |

---

## SECTION 8: GOAL EXECUTION SERVICE

### Does It Exist With Real Implementation? **YES**

`services/goal_execution.py` -- **1,690 lines** with:
- `execute_goal_sync()` -- sequential inline execution (for onboarding)
- `execute_goal_async()` -- background execution via `asyncio.Task` with SSE/WS events
- `propose_goals()` -- LLM-powered goal proposal from context
- `plan_goal()` -- decomposes into sub-tasks with agent assignments
- `_execute_agent()` -- dual-path: skill-aware first, prompt-based fallback
- `_create_agent_instance()` -- instantiates all 6 agents + dynamic agents

### Is It Wired To Agents? **YES**

All 6 core agents imported at line 304-320 with dedicated prompt builders:
- `_build_scout_prompt()`, `_build_analyst_prompt()`, `_build_hunter_prompt()`
- `_build_strategist_prompt()`, `_build_scribe_prompt()`, `_build_operator_prompt()`

### Is It Wired To OODA? **PARTIAL**

The scheduler (`services/scheduler.py`) creates `OODALoop` instances for active goals and runs `run_single_iteration()`. However, the OODALoop is instantiated **without** an `agent_executor` callback, so the OODA Act phase always returns `{"pending": True, "message": "Agent executor not configured"}`.

The OODA loop can observe, orient, and decide, but cannot dispatch agents autonomously. Goal execution only happens through explicit API calls (`POST /goals/{id}/execute`).

### Full Flow

| Step | Mechanism | Works? |
|------|-----------|--------|
| 1. User sets goal | `POST /goals` → GoalService.create_goal() | **Y** |
| 2. ARIA proposes goals | `POST /goals/propose` → LLM analysis | **Y** |
| 3. ARIA creates plan | `POST /goals/{id}/plan` → decompose into tasks | **Y** |
| 4. Goal execution starts | `POST /goals/{id}/execute` → async background | **Y** |
| 5. Agents execute | skill-aware + prompt-based dual path | **Y** |
| 6. Results stream | SSE via `GET /goals/{id}/events` + WebSocket events | **Y** |
| 7. Goal completes | Status updated, retrospective generated | **Y** |
| 8. OODA monitors | Scheduler runs OODA, but Act phase cannot dispatch | **PARTIAL** |

---

## SECTION 9: ONBOARDING FLOW

### Backend Implementation

**24 files, ~11,961 lines of onboarding code.**

| Step | Service File | Lines | Implementation |
|------|-------------|-------|----------------|
| 1. Company Discovery | `company_discovery.py` | 357 | Company info collection, triggers enrichment |
| 2. Document Upload | `document_ingestion.py` | 925 | PDF/DOCX/PPTX extraction and analysis |
| 3. User Profile | (via profile routes) | -- | Profile and role collection |
| 4. Writing Samples | `writing_analysis.py` | 333 | Style fingerprinting for Digital Twin |
| 5. Email Integration | `email_bootstrap.py` | 873 | Relationship mining from email |
| 6. Integration Wizard | `integration_wizard.py` | 487 | CRM and app connections via Composio |
| 7. First Goal | `first_goal.py` | 960 | LLM-suggested goals + SMART validation |
| 8. Activation | `activation.py` | 925 | Memory construction + goal execution + first conversation |

**Supporting modules:** orchestrator (691L), enrichment (1,149L), memory_constructor (360L), gap_detector (577L), personality_calibrator (478L), adaptive_controller (442L), outcome_tracker (431L), readiness (421L), ambient_gap_filler (397L), cross_user (499L), skill_recommender (263L), linkedin_research (336L)

### First Conversation Generator

**790 lines of real implementation.** Assembles top 30 semantic facts, identifies knowledge gaps, loads Digital Twin config, finds the most surprising fact via LLM, composes a personalized first message with rich content cards, goal proposals, UI commands, and records to episodic memory.

### Memory Pipeline

Onboarding data flows to memory through multiple paths:
- Enrichment → Semantic Memory (facts + hypotheses)
- Orchestrator → Episodic Memory (milestone events)
- Orchestrator → Procedural Memory (workflow patterns)
- Memory Constructor → conflict resolution using source hierarchy (user_stated > crm_import > document_upload > email_bootstrap > enrichment)
- Activation → chains goal execution → first conversation → first briefing

### Frontend Onboarding State

**GAP:** All frontend onboarding step components live in `_deprecated/` (14 TSX files). No non-deprecated replacements exist. The backend API (40+ endpoints) and hooks (`useOnboarding.ts`) work, but the visual step UI has not been rebuilt.

---

## SECTION 10: INTEGRATIONS & EXTERNAL SERVICES

| Service | .env.example Key | Real Code | Lines | Status |
|---------|-----------------|-----------|-------|--------|
| **Anthropic Claude** | `ANTHROPIC_API_KEY` | `core/llm.py` | ~110 | Production-ready (circuit breaker, streaming) |
| **Supabase** | `SUPABASE_URL`, `_ANON_KEY`, `_SERVICE_ROLE_KEY` | `db/supabase.py` | Core | Production-ready |
| **Graphiti/Neo4j** | `NEO4J_URI`, `_USER`, `_PASSWORD` | `db/graphiti.py` | 211 | Production-ready (singleton, circuit breaker) |
| **Tavus** | `TAVUS_API_KEY` | `integrations/tavus.py` | 190 | Production-ready (v2 API client) |
| **Daily.co** | `DAILY_API_KEY` | Via Tavus | -- | Indirect (room URLs from Tavus) |
| **Composio** | `COMPOSIO_API_KEY` | `integrations/oauth.py` | 247 | Production-ready (15 consumer files) |
| **Exa** | Missing from .env.example | `capabilities/enrichment_providers/exa_provider.py` | ~150 | Implementation exists, env key undocumented |
| **PubMed/ClinicalTrials/FDA** | N/A (public) | `agents/analyst.py` + skills | Multiple | Production-ready |
| **Resend** | Missing from .env.example | `services/email_service.py` | 370 | Implementation exists, env key undocumented |
| **Stripe** | Missing from .env.example | `services/billing_service.py` | 711 | Implementation exists, env keys undocumented |
| **Twilio** | N/A | Not implemented | -- | Not used |
| **SendGrid** | N/A | Not implemented | -- | Resend used instead |

### Integration Gaps

- `.env.example` missing: `RESEND_API_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `EXA_API_KEY`
- These services have full code but new deployments won't know they need these keys

---

## SECTION 11: FRONTEND ARCHITECTURE STATE

### Deprecated vs Active

| Category | Count |
|----------|-------|
| Deprecated files in `_deprecated/` | 134 TSX + 22 page files = 156 total |
| Active component files | 88 |
| Cross-imports from deprecated | **0** (clean separation) |

### IDD v3 Compliance

| Component | Status | Detail |
|-----------|--------|--------|
| Three-column layout (AppShell) | **Implemented** | Sidebar 240px + Center flex + IntelPanel 320px |
| ARIA Workspace (Layer 1) | **Implemented** | `ARIAWorkspace.tsx`, 184 lines |
| Dialogue Mode (Layer 1a) | **Implemented** | `DialogueMode.tsx`, 289 lines with avatar + transcript |
| Content Pages (Layer 2) | **Implemented** | Pipeline, Intelligence, Communications, Actions |
| Settings (Layer 3) | **Implemented** | 7 sub-sections |
| Intelligence Panel | **Implemented** | 15 context-adaptive modules |
| Sidebar (7 items) | **Implemented** | ARIA, Briefing, Pipeline, Intelligence, Communications, Actions, Settings |
| Design System (CSS variables) | **Implemented** | 20 token definitions, 52 files using `var(--)` |
| Dark/Light themes | **Implemented** | Dark default, `.light` class for content pages |
| Typography | **Mostly** | Instrument Serif + JetBrains Mono loaded. Uses Satoshi instead of Inter for body (minor deviation) |
| Command Palette | **Implemented** | Cmd+K shortcut |
| Rich Content Cards | **Implemented** | GoalPlanCard, ExecutionPlanCard, AlertCard, MeetingCard, SignalCard |
| UICommandExecutor | **Implemented** | `core/UICommandExecutor.ts` -- processes navigate, highlight, update_intel_panel |
| Agent Avatars | **Implemented** | `AGENT_REGISTRY` with distinct identities for all 6 agents |

### Frontend Gap

No active onboarding step components exist -- all 14 are in `_deprecated/`.

---

## SECTION 12: QUALITY & TEST STATE

### Test Inventory

| Category | Count |
|----------|-------|
| Backend test files | **225** |
| Frontend test files (active code) | **2** |
| Frontend test files (deprecated) | 11 |

### Static Analysis

| Tool | Result |
|------|--------|
| TypeScript (`tsc --noEmit`) | **0 errors** -- clean pass |
| Ruff (Python linter) | **0 errors** -- "All checks passed!" |
| Mypy (`--strict`) | **2,545 errors in 81 files** |

### Mypy Issues

The 2,545 mypy errors include real bugs, not just type annotation gaps. Example:

```
src/api/routes/onboarding.py:1522: error: Value of type "Coroutine[Any, Any, dict[str, Any]]" is not indexable
src/api/routes/onboarding.py:1522: note: Maybe you forgot to use "await"?
```

Missing `await` calls in `onboarding.py` (appears 4 times) would cause **runtime errors**.

### Quality Assessment

- TypeScript is solid (0 errors) -- frontend type safety is maintained
- Python style is consistent (0 ruff errors)
- Backend test coverage is extensive (225 files)
- Frontend has virtually no test coverage for active code (2 files)
- Mypy strict mode reveals thousands of type annotation gaps and some real bugs

---

## SECTION 13: CRITICAL WIRING GAPS

### Gap 1: WebSocket Does Not Handle Chat Messages

| | Detail |
|---|--------|
| **What's disconnected** | Frontend `WebSocketManager.send('user.message', ...)` → Backend `websocket.py` only handles `"ping"` |
| **Files** | `frontend/src/core/WebSocketManager.ts` → `backend/src/api/routes/websocket.py` |
| **Impact** | **Chat is broken when WebSocket is connected.** User sends message, no response. Only works in SSE fallback mode (when WS is down). |
| **Effort** | 4-8 hours. Add `user.message` handler to WS that calls `ChatService` and streams response tokens back over WS. |

### Gap 2: WebSocket Session Parameter Mismatch

| | Detail |
|---|--------|
| **What's disconnected** | Frontend sends `?session=<id>`, backend expects `?session_id=<id>` |
| **Files** | `frontend/src/core/WebSocketManager.ts:80` → `backend/src/api/routes/websocket.py` FastAPI param |
| **Impact** | Session binding is always null on backend. Session-specific WS features don't work. |
| **Effort** | 15 minutes. Change one param name. |

### Gap 3: WebSocket Heartbeat Mismatch

| | Detail |
|---|--------|
| **What's disconnected** | Frontend sends `{ type: "heartbeat" }`, backend only handles `"ping"` |
| **Files** | `frontend/src/core/WebSocketManager.ts` → `backend/src/api/routes/websocket.py` |
| **Impact** | Heartbeats silently dropped. Connection may timeout behind reverse proxies (Nginx/CloudFront 60s idle). |
| **Effort** | 15 minutes. Add heartbeat handler or change frontend to send "ping". |

### Gap 4: OODA Act Phase Has No Agent Executor

| | Detail |
|---|--------|
| **What's disconnected** | `OODALoop` instantiated in scheduler without `agent_executor` callback |
| **Files** | `backend/src/services/scheduler.py` → `backend/src/core/ooda.py` |
| **Impact** | OODA can observe/orient/decide but cannot autonomously dispatch agents. Goals only execute via explicit REST API calls. |
| **Effort** | 2-4 hours. Pass `GoalExecutionService._execute_agent` as callback when creating OODALoop. |

### Gap 5: Working Memory Not Persisted

| | Detail |
|---|--------|
| **What's disconnected** | `WorkingMemoryManager._memories` is a Python dict, no Supabase persistence |
| **Files** | `backend/src/memory/working.py` |
| **Impact** | Server restart loses all working memory. CLAUDE.md spec says "persisted on end". |
| **Effort** | 4-6 hours. Add serialize/deserialize to Supabase on session boundaries. |

### Gap 6: Lead Memory Not in Chat Context

| | Detail |
|---|--------|
| **What's disconnected** | `MemoryQueryService.query()` doesn't include lead memory in parallel queries |
| **Files** | `backend/src/api/routes/memory.py` (MemoryQueryService), `backend/src/memory/lead_memory.py` |
| **Impact** | ARIA can't automatically recall lead details during conversation. Must use leads API explicitly. |
| **Effort** | 2-3 hours. Add lead memory adapter to MemoryQueryService. |

### Gap 7: `goal_updates` Table Missing

| | Detail |
|---|--------|
| **What's disconnected** | No CREATE TABLE for `goal_updates` in any migration |
| **Files** | All 62 migration files checked |
| **Impact** | Any backend code referencing `goal_updates` will fail at runtime. |
| **Effort** | 30 minutes. Create migration. |

### Gap 8: `skill_replay.py` Router Not Registered

| | Detail |
|---|--------|
| **What's disconnected** | `skill_replay.py` defines routes at `/audit` prefix but never `include_router`'d in `main.py` |
| **Files** | `backend/src/api/routes/skill_replay.py` → `backend/src/main.py` |
| **Impact** | Skill execution replay and PDF export endpoints unreachable. |
| **Effort** | 5 minutes. Add one line to main.py. |

### Gap 9: Frontend Onboarding UI Not Rebuilt

| | Detail |
|---|--------|
| **What's disconnected** | Backend has 40+ onboarding endpoints and 24 service files. Frontend has API client + hooks. But all step components are in `_deprecated/`. |
| **Files** | `frontend/src/_deprecated/components/onboarding/` (14 files) |
| **Impact** | No visual onboarding flow for new users in the new architecture. |
| **Effort** | 16-24 hours. Rebuild 8 step components in IDD v3 architecture (conversation-driven, not form-based). |

### Gap 10: `.env.example` Missing Required Keys

| | Detail |
|---|--------|
| **What's disconnected** | Code imports `resend`, `stripe`, Exa API but keys not in `.env.example` |
| **Files** | `backend/.env.example` |
| **Impact** | New deployments won't know they need RESEND_API_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, EXA_API_KEY. |
| **Effort** | 10 minutes. Add entries to .env.example. |

### Gap 11: Missing `await` in Onboarding Routes

| | Detail |
|---|--------|
| **What's disconnected** | 4 async function calls in `onboarding.py` (lines 1522-1525) are not awaited |
| **Files** | `backend/src/api/routes/onboarding.py` |
| **Impact** | Runtime errors when those onboarding endpoints are hit. Coroutine objects returned instead of results. |
| **Effort** | 15 minutes. Add `await` keyword. |

---

## SECTION 14: EXECUTIVE SUMMARY

### Overall Health Score: **62/100**

The architecture is sound, the design system is implemented, and the backend is comprehensive. However, the primary interaction path (WebSocket chat) is broken, onboarding has no frontend, and there are real runtime bugs lurking.

### Top 5 P0 Blockers

1. **WebSocket chat handler missing** -- The primary chat path silently drops messages. Users type and get no response. (Gap 1)
2. **No frontend onboarding flow** -- New users have no way to go through onboarding in the new architecture. (Gap 9)
3. **Missing `await` in onboarding routes** -- Runtime errors on 4 onboarding endpoints. (Gap 11)
4. **OODA loop cannot dispatch agents** -- Autonomous goal monitoring is observe-only; cannot act. (Gap 4)
5. **Working memory lost on restart** -- Server restart erases all session context. (Gap 5)

### Top 5 Things That ARE Working Well

1. **All 6 agents fully implemented** -- Hunter, Analyst, Strategist, Scribe, Operator, Scout all have real business logic (not stubs), real API integrations (PubMed, ClinicalTrials, FDA, ChEMBL), and are properly wired into GoalExecutionService. ~3,614 lines of agent code.
2. **IDD v3 frontend architecture** -- Three-column layout, 7-item sidebar, 15-module context-adaptive IntelPanel, DialogueMode, rich content cards, design system with CSS variables, dark/light themes. 88 new components with zero deprecated imports. TypeScript compiles cleanly.
3. **Memory system** -- 5 of 6 memory types flow end-to-end through chat. Episodic memories stored after every conversation turn. Semantic facts queried with confidence scoring. ~3,855 lines of memory code.
4. **Goal execution pipeline** -- User can create goal → ARIA proposes → creates plan → dispatches agents → streams results via SSE → completes with retrospective. 1,690 lines of execution code.
5. **Onboarding backend** -- 8 steps, 24 files, ~11,961 lines. First Conversation Generator (790 lines) assembles 30+ facts into a personalized intelligence-demonstrating first message. Memory construction pipeline resolves conflicts across sources.

### "Can a user do X?" Checklist

| Question | Answer | Detail |
|----------|--------|--------|
| Can a user sign up and log in? | **Y** | Auth routes exist with Supabase Auth. LoginPage and SignupPage implemented. |
| Can a user chat with ARIA and get a response? | **N*** | *Only if WebSocket fails to connect (triggering SSE fallback). With WS connected, messages are silently dropped. |
| Can a user complete onboarding? | **N** | Backend is comprehensive, but frontend step components are all deprecated. No rebuilt UI. |
| Does ARIA remember context across conversations? | **Y** | Episodic memory stores every turn, semantic facts persist. Queried on each new message. |
| Can ARIA execute a goal autonomously? | **Y** | Via explicit `POST /goals/{id}/execute`. Not via autonomous OODA loop (agent_executor not wired). |
| Does the morning briefing generate and deliver? | **Y** | `daily_briefing_job.py` scheduled job + `briefing.py` service + `/briefings/generate` endpoint + DialogueMode briefing variant on frontend. |
| Do battle cards exist and update? | **Y** | Full CRUD + LLM-generated analysis + `/battlecards` endpoints + BattleCardPreview component + IntelligencePage. |
| Does pre-meeting research work? | **Y** | Scout agent + MeetingBriefService + `/meetings/{id}/brief` endpoint. |
| Does email drafting work? | **Y** | Scribe agent + DraftService + `/drafts/email` endpoint + CommunicationsPage. |
| Does the knowledge graph have data? | **Depends** | Graphiti/Neo4j client is production-ready. Data exists only if onboarding enrichment ran successfully (requires Neo4j to be running). |
| Are any agents actually executing in production? | **Y** | Via goal execution REST API. Not via autonomous OODA scheduling. |
| Is the frontend the new IDD v3 architecture or old SaaS? | **IDD v3** | Clean rebuild. 88 new components. Zero imports from `_deprecated/`. Old code completely isolated. |

### Honest Assessment: What Would Adri Scalora Experience Today?

If Adri opened ARIA for the first time today:

1. **She would see a polished login page** and could create an account via Supabase Auth.

2. **She would land on the ARIA Workspace** -- a dark, premium-looking interface with the three-column layout, sidebar with 7 items, and a conversation thread. The visual design would make a good first impression.

3. **She would type "Hello" and get silence.** The WebSocket would connect successfully, her message would appear in the thread, and nothing would happen. No response from ARIA. She would wait, confused, and likely refresh the page. If the WebSocket failed to connect on the retry (unlikely but possible), she'd suddenly get responses.

4. **She would have no onboarding experience.** No guided setup, no "tell me about your company," no document upload wizard, no integration connection flow. She'd be dropped straight into an empty workspace with no context.

5. **She could click through the sidebar** and see Pipeline, Intelligence, Communications, Actions, and Settings pages. These would be mostly empty because no data has been seeded through onboarding.

6. **The Intelligence Panel on the right** would show context-adaptive modules, but without data they'd be skeletal.

7. **If she somehow got to Dialogue Mode** (`/dialogue`), she'd see the avatar split-screen layout, which would look impressive architecturally even without a live Tavus connection.

**Bottom line:** The architecture and design are enterprise-grade. The component library is substantial. But the two most critical user paths -- chatting with ARIA and onboarding -- are broken. Fixing the WebSocket chat handler (Gap 1) would immediately unlock the core experience, since the LLM integration, memory system, and agent pipeline behind it are all functional. Rebuilding the onboarding frontend is the second priority to make the first-run experience work.

**The distance from "broken demo" to "impressive demo" is surprisingly short** -- fixing the WebSocket handler (4-8 hours) and adding a minimal onboarding conversation flow would unlock the full backend capability that already exists.

---

## Appendix: Complete File Counts

| Category | Count |
|----------|-------|
| Backend Python source files | 203 |
| Backend test files | 225 |
| Frontend active TS/TSX files | 132 |
| Frontend deprecated files | 134 |
| Frontend active test files | 2 |
| Database migrations | 62 |
| **Total source files** | **335 active + 134 deprecated = 469** |
| **Total lines of code** | **~166,243** |
| Backend API endpoints | ~280 |
| Frontend routes | 16 |
| Memory types implemented | 6 |
| Agents implemented | 6 |
| Onboarding steps | 8 |
| Integration services | 8 |
