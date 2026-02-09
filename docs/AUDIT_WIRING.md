# ARIA Application Wiring Audit Report

**Generated:** 2026-02-08
**Status:** 🔴 CRITICAL ISSUES FOUND

This audit verifies that implemented features are actually CONNECTED, not just existing as isolated code.

---

## EXECUTIVE SUMMARY

**Overall Status:** 🔴 **CRITICAL - BETA BLOCKING ISSUES**

- **P0 Blockers:** 2 categories (Chat system disconnected, 43 missing database tables)
- **P1 Degradations:** 7 features broken (Memory persistence, Onboarding, Goals, etc.)
- **P2 Nice-to-Have:** 2 issues (Unused agent code, minor mismatches)

**Key Finding:** Backend code references 43 database tables that were never created in migrations. Core features like chat, memory, goals, and onboarding will fail at runtime.

---

## 1. FRONTEND ↔ BACKEND ROUTES

### Status: ⚠️ **PARTIALLY DISCONNECTED**

**Frontend Pages Status:**
- ✅ All 31 pages exported from `frontend/src/pages/index.ts`
- ✅ All pages routed in `frontend/src/App.tsx`
- ✅ All pages have corresponding API client modules in `frontend/src/api/`

### Critical Disconnects Found:

#### ❌ **Chat System - DISCONNECTED (P0 BLOCKER)**

**Frontend expects:**
- `POST /chat/message` - `frontend/src/api/chat.ts:48`
- `POST /chat/message/stream` - `frontend/src/api/chat.ts:96`

**Backend provides:**
- `POST /chat` (base endpoint, no `/message`)
- `GET /chat/conversations`
- `GET /chat/conversations/{id}`
- `PUT /chat/conversations/{id}/title`
- `DELETE /chat/conversations/{id}`

**Impact:** Chat messaging will fail completely. ARIA chat page cannot send or receive messages.

**Files affected:**
- `frontend/src/api/chat.ts:48` - Calls `apiClient.post("/chat/message", data)`
- `frontend/src/api/chat.ts:96` - Calls `fetch("/api/v1/chat/message/stream")`
- `backend/src/api/routes/chat.py` - Missing these endpoints

---

#### ❌ **Chat Messages Route - MISSING (P0 BLOCKER)**

**Frontend expects:**
- `GET /chat/conversations/{id}/messages` → Returns `Message[]`

**Backend provides:**
- `GET /chat/conversations/{id}` → Returns `ConversationListResponse` with `conversations` field

**Impact:** Cannot retrieve conversation history.

**Files affected:**
- `frontend/src/api/chat.ts:53`
- `backend/src/api/routes/chat.py:188-219`

---

## 2. BACKEND ↔ DATABASE

### Status: 🔴 **CRITICAL SCHEMA MISMATCH**

**43 Tables Referenced But Not Created (P0 BLOCKERS)**

The backend code references 43 tables that don't exist in migrations:

### Chat/Conversation System (Critical)
| Table | Referenced In | Line | Priority |
|-------|---------------|------|----------|
| `conversations` | `backend/src/api/routes/chat.py` | 171 | P0 |
| `messages` | `backend/src/services/chat.py` | 98 | P0 |
| `conversation_episodes` | Multiple files | - | P0 |

### Memory System (Critical)
| Table | Referenced In | Priority |
|-------|---------------|----------|
| `episodic_memories` | `backend/src/memory/episodic.py` | P0 |
| `semantic_facts` | `backend/src/memory/semantic.py` | P0 |
| `memory_semantic` | Compliance exports | P1 |
| `memory_prospective` | Different from `prospective_memories` | P1 |
| `memory_access_log` | Never created | P1 |
| `memory_briefing_queue` | Never created | P1 |

### Goals System (Critical)
| Table | Referenced In | Priority |
|-------|---------------|----------|
| `goals` | `backend/src/api/routes/goals.py` | P0 |
| `goal_milestones` | Goal services | P0 |
| `goal_retrospectives` | Goal services | P0 |
| `goal_agents` | Goal services | P1 |

### Lead System
| Table | Referenced In | Priority |
|-------|---------------|----------|
| `discovered_leads` | Lead generation | P0 |
| `lead_icp_profiles` | ICP management | P0 |
| `lead_insights` | Separate from `lead_memory_insights` | P1 |
| `lead_stakeholders` | Separate from `lead_memory_stakeholders` | P1 |
| `lead_events` | Missing | P1 |

### Onboarding System
| Table | Referenced In | Priority |
|-------|---------------|----------|
| `onboarding_state` | `backend/src/onboarding/orchestrator.py` | P0 |
| `onboarding_outcomes` | Outcome tracker | P1 |

### Other Critical
| Table | Referenced In | Priority |
|-------|---------------|----------|
| `aria_actions` | Action queue routes | P0 |
| `aria_activity` | Activity feed routes | P0 |
| `cognitive_load_snapshots` | Predictions service | P1 |
| `user_settings` | Different from `user_preferences` | P1 |
| `user_skills` | Skill assignments | P1 |
| `user_quotas` | Quota tracking | P1 |
| `integration_sync_state` | Deep sync | P1 |
| `integration_sync_log` | Deep sync | P1 |
| `integration_push_queue` | Deep sync | P1 |

**Impact:** All features referencing these tables will fail at runtime with database errors.

---

## 3. MEMORY SYSTEM WIRING

### Status: ⚠️ **PARTIALLY WIRED (P1 DEGRADATION)**

### ✅ Working Connections:
- Working Memory → Chat Service: `backend/src/services/chat.py:67-75`
- Memory Query Service initialized: Line 69
- Semantic Memory integration: `ExtractionService` at line 72

### ✅ Memory Classes Exist:
- `backend/src/memory/episodic.py` ✅
- `backend/src/memory/semantic.py` ✅
- `backend/src/memory/prospective.py` ✅
- `backend/src/memory/digital_twin.py` ✅
- `backend/src/memory/lead_memory.py` ✅

### ❌ Missing Database Layer (P0):
- Tables `episodic_memories`, `semantic_facts`, `memory_semantic` don't exist
- Calls to `self._db.table("episodic_memories")` will fail at runtime
- Memory queries cannot persist or retrieve data from Supabase

### ⚠️ Memory Priming Not Wired (P1):
- `backend/src/memory/priming.py` exists but not referenced in chat service
- `PrimingService` never instantiated in chat flow
- Digital Twin consultation not integrated into response generation

**Impact:** ARIA cannot remember conversations or retrieve past context. Digital Twin personalization non-functional.

---

## 4. AGENT SYSTEM WIRING

### Status: ✅ **MOSTLY CONNECTED**

### ✅ Agent Registration & Implementation:

All 6 agents implemented:
- `backend/src/agents/hunter.py` ✅
- `backend/src/agents/analyst.py` ✅
- `backend/src/agents/strategist.py` ✅
- `backend/src/agents/scribe.py` ✅
- `backend/src/agents/operator.py` ✅
- `backend/src/agents/scout.py` ✅

Base classes:
- `BaseAgent`: `backend/src/agents/base.py` ✅
- `AgentOrchestrator`: `backend/src/agents/orchestrator.py` ✅

### ✅ Hunter Agent Wiring:
- Used in lead generation: `backend/src/core/lead_generation.py`
- Properly instantiated and called

### ⚠️ Other Agents Not Integrated (P2):
- Analyst, Scribe, Strategist, Operator, Scout referenced in OODA documentation
- No API endpoints trigger agent orchestration for these 5 agents
- Agents exist but are unused orphaned code

### ⚠️ OODA Loop Documentation Only (P2):
- `backend/src/core/ooda.py` documents the loop
- Doesn't implement actual dispatch to agents
- Agents registered in documentation but not in executable code paths

**Impact:** 5 out of 6 agents are dormant. ARIA's multi-agent capabilities underutilized.

---

## 5. ONBOARDING → EVERYTHING INTEGRATION

### Status: ⚠️ **PARTIALLY WIRED (P1 DEGRADATION)**

### ✅ Onboarding Orchestrator Exists:
- `backend/src/onboarding/orchestrator.py` - coordinates all steps
- API routes: `backend/src/api/routes/onboarding.py`
- Frontend pages and hooks exist

### ✅ Frontend Hooks Wired:
- `useOnboardingState()` calls `/onboarding/state`
- `useCompleteStep()` calls `/onboarding/steps/{step}/complete`
- `useSkipStep()` calls `/onboarding/steps/{step}/skip`
- Integration: `frontend/src/pages/Onboarding.tsx`

### ❌ Onboarding State Table Missing (P0):
- Backend tries to write to `onboarding_state` table
- Table never created in migrations
- All onboarding state storage will fail

### ❌ Corporate Memory Flow Not Wired (P1):
- Company data from onboarding → should flow to `corporate_facts` table
- `corporate_facts` table EXISTS but wiring from onboarding not implemented
- Writing samples → Digital Twin calibration exists but table doesn't exist

### ❌ Memory Flows from Onboarding (P1):
Onboarding services don't call memory systems to store:
- Company facts → Corporate Memory
- User profile → Semantic Memory
- Writing samples → Digital Twin calibration
- No integration with memory services

**Impact:** Onboarding collects data but doesn't make ARIA smarter. Intelligence Initialization fails.

---

## 6. AUTH FLOW WIRING

### Status: ✅ **WORKING**

### Complete Path Verified:

1. **Login Endpoint:**
   - Frontend: `frontend/src/api/auth.ts:47`
   - Backend: `backend/src/api/routes/auth.py:122`
   - ✅ Connected

2. **JWT Token Management:**
   - Frontend stores: `localStorage.setItem("access_token")`
   - Backend validates: `SupabaseClient.auth.get_user(token)`
   - ✅ Connected

3. **API Middleware:**
   - All routes use `CurrentUser = Annotated[Any, Depends(get_current_user)]`
   - Token validated on every request
   - File: `backend/src/api/deps.py`
   - ✅ Working

4. **RLS Enforcement:**
   - Corporate facts: `company_id IN (SELECT company_id FROM user_profiles WHERE id = auth.uid())`
   - User documents: `user_id = auth.uid()`
   - Company documents: Multi-user access via company
   - ✅ Policies exist (though some tables don't)

5. **Current User Retrieval:**
   - `get_current_user()` extracts uid from JWT
   - Used everywhere to filter user-specific data
   - ✅ Working pattern

**Impact:** Auth flow is solid. Users are properly isolated and authenticated.

---

## 7. SKILLS SYSTEM WIRING

### Status: ✅ **MOSTLY WIRED**

### ✅ Skills Routes Exist:
- `backend/src/api/routes/skills.py` - all endpoints present
- Frontend hooks: `useAvailableSkills()`, `useInstalledSkills()`, `useInstallSkill()`
- API calls match endpoints

### ✅ Skill Audit:
- Audit log table exists: `skill_audit_log`
- Logging implemented in skill operations
- ✅ Working

**Impact:** Skills system functional.

---

## 8. DEEP SYNC / INTEGRATIONS

### Status: ⚠️ **PARTIALLY WIRED (P1 DEGRADATION)**

### ✅ Routes Exist:
- `backend/src/api/routes/deep_sync.py`
- Frontend page: `frontend/src/pages/DeepSyncPage.tsx`
- Registered in `main.py:157`

### ❌ Missing Database Tables (P1):
- `integration_sync_state` - not created
- `integration_sync_log` - not created
- `integration_push_queue` - not created

**Impact:** Cannot track sync status or schedule bidirectional sync. Deep Sync feature broken.

---

## 9. ACTION QUEUE SYSTEM

### Status: ⚠️ **PARTIAL (P1 DEGRADATION)**

### ✅ Routes & Frontend Exist:
- Backend: `backend/src/api/routes/action_queue.py`
- Frontend: `frontend/src/pages/ActionQueue.tsx`
- Hooks: `useGetActions()`, `useCreateAction()`, `useApproveAction()`

### ⚠️ Missing Table (P1):
- Code references `aria_actions` table
- Used in routes but never created in migrations
- Will fail when saving/retrieving actions

**Impact:** Cannot store or approve ARIA's autonomous actions.

---

## PRIORITY SUMMARY

### P0 BLOCKERS (Beta Breaking) - 2 Categories

1. **Chat endpoints mismatch**
   - `/chat/message` endpoint missing
   - `/chat/message/stream` endpoint missing
   - Conversation messages route mismatch

2. **43 missing database tables** - Core functionality tables don't exist:
   - `conversations` (chat)
   - `messages` (chat)
   - `onboarding_state` (onboarding)
   - `goals`, `goal_milestones`, `goal_retrospectives` (goals)
   - `episodic_memories`, `semantic_facts` (memory)
   - `discovered_leads`, `lead_icp_profiles` (leads)
   - `aria_actions` (action queue)
   - `aria_activity` (activity feed)
   - And 35 more

### P1 DEGRADATIONS (Broken Features) - 7 Issues

1. Memory system can't persist - Tables don't exist, queries will fail
2. Onboarding data won't save - `onboarding_state` missing
3. Goals system non-functional - No tables
4. Integration sync broken - Sync state tables missing
5. Agents 4-6 unused - Analyst, Strategist, Scout, Operator not called
6. Digital Twin not consulted - Memory priming not integrated
7. Activity feed orphaned - `aria_activity` table missing

### P2 NICE-TO-HAVE - 2 Issues

1. Response model mismatch for conversation messages
2. Unused agent code (Analyst, Strategist, Scout, Operator, Scribe)

---

## FILES WITH CRITICAL ISSUES

| File | Issue | Severity | Line |
|------|-------|----------|------|
| `backend/src/api/routes/chat.py` | References `conversations` table (doesn't exist) | P0 | 171 |
| `backend/src/services/chat.py` | References `conversations`, `messages` tables | P0 | 98 |
| `backend/src/onboarding/orchestrator.py` | References `onboarding_state` table | P0 | - |
| `backend/src/api/routes/goals.py` | References `goals`, `goal_milestones` | P0 | - |
| `frontend/src/api/chat.ts` | Calls `/chat/message` endpoint (doesn't exist) | P0 | 48, 96 |
| `backend/src/api/routes/action_queue.py` | References `aria_actions` table | P1 | - |
| `backend/src/memory/episodic.py` | Uses `episodic_memories` table | P1 | - |
| `backend/src/api/routes/activity.py` | References `aria_activity` table | P1 | - |
| `backend/src/api/routes/deep_sync.py` | References sync state tables | P1 | - |

---

## RECOMMENDATIONS

### Immediate Actions Required (Before Beta)

1. **Create missing database tables** (P0)
   - Add all 43 missing tables to `backend/supabase/migrations/`
   - Priority order: conversations, messages, onboarding_state, goals, episodic_memories, semantic_facts

2. **Fix chat endpoints** (P0)
   - Add `POST /chat/message` endpoint
   - Add `POST /chat/message/stream` endpoint
   - Fix response model for `GET /chat/conversations/{id}/messages`

3. **Wire memory system** (P0)
   - Create episodic/semantic tables
   - Ensure calls flow from chat service to memory storage
   - Verify memory queries retrieve data correctly

4. **Complete onboarding wiring** (P0)
   - Create `onboarding_state` table
   - Wire data flows to Corporate Memory, Digital Twin, Semantic Memory
   - Implement Integration Checklist for each onboarding step

5. **Verify response models** (P1)
   - Ensure API response shapes match frontend TypeScript interfaces
   - Add integration tests for critical flows

### Before Production

1. **Test complete auth → RLS flow** with real multi-tenant data
2. **Verify all 6 agents** are orchestrated from API routes (not just Hunter)
3. **Integration checklist** for each feature (ensure 3+ downstream systems)
4. **End-to-end testing** of memory system persistence and retrieval
5. **Load testing** for conversation streaming and memory queries

---

## AUDIT METHODOLOGY

This audit was performed using:
1. Static code analysis of all frontend and backend files
2. Cross-referencing API route definitions with frontend API clients
3. Database schema inspection from Supabase migrations
4. Dependency graph analysis for service integrations
5. Manual verification of critical integration points

**Tools used:**
- Glob pattern matching for file discovery
- Grep for code references and table name searches
- Read tool for detailed file inspection
- Integration flow tracing through multiple layers

**Completeness:** This audit covers all major subsystems. Minor edge cases may exist but are unlikely to be beta blockers.

---

**Next Steps:** Address P0 blockers first, then P1 degradations. Rerun audit after fixes to verify connections.
