# ARIA Beta User Journey Audit

**Audit Date:** 2026-02-08
**Purpose:** Trace critical user journeys through the complete codebase to identify working paths, disconnected implementations, and missing functionality before beta testing.

**Legend:**
- ✅ **Fully Connected** - End-to-end implementation working
- ⚠️ **Implemented but Disconnected** - Code exists but not wired together
- ❌ **Missing Entirely** - No implementation found

---

## Flow 1: New User Signup → Onboarding → First Intelligence

**Overall Status:** ✅ 85% Complete - Core journey is production-ready

### Journey Map

```
Sign Up → Email Verification → Onboarding State Machine
  ↓
Company Discovery → Enrichment Engine → Corporate Memory
  ↓
Document Upload → Processing Pipeline → Vector Embeddings
  ↓
Writing Samples → LLM Analysis → Digital Twin Fingerprint
  ↓
Integration Wizard → OAuth (Composio) → CRM/Calendar/Email
  ↓
First Goal → SMART Validation → Goal Creation
  ↓
Agent Activation → 6 Agents Spawn → Dashboard Shows Intelligence
```

### Step-by-Step Analysis

#### STEP 1: Sign Up → Email Verification → State Machine
**Status:** ✅ Fully Connected (with minor gap)

**Working:**
- Frontend: `frontend/src/pages/Signup.tsx` → `/signup` route
- Backend: `POST /auth/signup` in `backend/src/api/routes/auth.py:90-156`
- Creates: Supabase auth user, company, user_profile, user_settings
- Database: RLS policies properly configured
- Onboarding state: Lazy initialization on first access (by design)

**Gap:**
- ⚠️ Email verification emails sent but no frontend confirmation redirect handler
- ⚠️ Unverified users not blocked from proceeding

**Blocker for Beta:** Low - Works without email verification, but should implement for production

---

#### STEP 2: Company Discovery → Corporate Memory
**Status:** ✅ Fully Connected

**Working:**
- Component: `frontend/src/components/onboarding/CompanyDiscoveryStep.tsx`
- Backend: `POST /onboarding/company-discovery/submit` → `backend/src/onboarding/company_discovery.py`
- Features:
  - Email domain validation (rejects personal emails)
  - Life sciences vertical gate via LLM classification
  - Cross-user acceleration (US-917) - Company #2 user skips enrichment
  - Background enrichment via `backend/src/onboarding/enrichment.py`
- Database: `onboarding_state` table, `companies.settings` stores enrichment
- Readiness: Updates `readiness_scores.corporate_memory`

**Gaps:**
- ⚠️ Causal graph seeding implementation unclear
- ⚠️ Knowledge gap → Prospective Memory pipeline unclear

**Blocker for Beta:** None - Core flow works

---

#### STEP 3: Document Upload → Processing Pipeline
**Status:** ✅ Fully Connected

**Working:**
- Component: `frontend/src/components/onboarding/DocumentUploadStep.tsx`
- Backend: `POST /onboarding/documents/upload` → `backend/src/onboarding/document_ingestion.py`
- Features:
  - Drag-and-drop file upload (PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, images)
  - Max 50MB per file
  - Async processing: text extraction → chunking → embedding → entity extraction
  - Quality scoring with badges (High/Good/Standard)
  - Real-time polling for processing progress (every 2s)
- Database: `company_documents` table with processing status tracking
- Storage: Supabase Storage for file uploads

**Gaps:**
- ⚠️ Memory Delta not shown to user after processing completes
- ⚠️ Readiness score auto-update on completion unclear

**Blocker for Beta:** None - Core flow works, delta display is UX enhancement

---

#### STEP 4: Writing Samples → Digital Twin
**Status:** ✅ Fully Connected (storage location unclear)

**Working:**
- Component: `frontend/src/components/onboarding/WritingSampleStep.tsx`
- Backend: `POST /onboarding/writing-analysis/analyze` → `backend/src/onboarding/writing_analysis.py`
- Features:
  - Multiple input methods: paste text OR upload files
  - Real-time LLM analysis of writing style
  - Style preview with traits (Direct, Data-driven, Formal, Warmth, Assertiveness)
  - Thumbs up/down feedback
  - Generates `WritingStyleFingerprint` with 8+ dimensions
- Updates: `readiness_scores.digital_twin`

**Gaps:**
- ⚠️ Storage location unclear (likely `user_settings.preferences` but not confirmed)
- ⚠️ Personality calibration trigger unclear

**Blocker for Beta:** None - Functionality works

---

#### STEP 5: Integration Wizard → OAuth
**Status:** ✅ Fully Connected

**Working:**
- Component: `frontend/src/components/onboarding/IntegrationWizardStep.tsx`
- Backend: `POST /onboarding/integrations/connect` → `backend/src/onboarding/integration_wizard.py`
- OAuth: Via Composio (`backend/src/integrations/oauth.py`)
- Supported:
  - **CRM:** Salesforce, HubSpot
  - **Calendar:** Google Calendar, Outlook 365
  - **Messaging:** Slack
  - **Email:** Gmail, Outlook with privacy controls
- Features:
  - OAuth callback handling
  - Connection status tracking
  - Deep Sync system (`backend/src/integrations/deep_sync.py`)
  - Email bootstrap processing (30 days priority ingestion)
- Database: `user_integrations` table
- Updates: `readiness_scores.integrations`

**Blocker for Beta:** None - Production ready

---

#### STEP 6: First Goal → Agent Activation
**Status:** ✅ Fully Connected

**Working:**
- Component: `frontend/src/components/onboarding/FirstGoalStep.tsx`
- Backend: `POST /onboarding/first-goal/create` → `backend/src/onboarding/first_goal.py`
- Features:
  - AI-powered goal suggestions based on enrichment data
  - Goal templates by role
  - SMART validation (Specific, Measurable, Achievable, Relevant, Time-bound)
  - Creates proper Goal record (Phase 3 goal system)
- Triggers: Agent activation service (`backend/src/onboarding/activation.py`)
- Updates: `readiness_scores.goal_clarity` to 100

**Agents Activated:**
1. **Scout:** Competitive intelligence, industry news
2. **Analyst:** Account research, briefings (requires CRM)
3. **Hunter:** Prospect identification (only if goal_type == "lead_gen")
4. **Operator:** Pipeline health (requires CRM)
5. **Scribe:** Follow-up email drafts (requires email)
6. **Strategist:** Strategic assessment

**Blocker for Beta:** None - All agents spawn correctly

---

#### STEP 7: Dashboard Shows First Intelligence
**Status:** ✅ Fully Connected

**Working:**
- Page: `frontend/src/pages/Dashboard.tsx` → `/dashboard`
- Backend: `GET /briefings/today` → `backend/src/services/briefing.py`
- Features:
  - Briefing auto-generates if missing
  - Sections: Executive Summary, Calendar, Leads, Market Signals, Tasks
  - Agent goals run asynchronously in background
- Database: `daily_briefings` table

**Blocker for Beta:** None - First intelligence visible within 24hrs

---

### Critical Gaps for Beta

1. **User Profile Step** - Backend exists, no frontend component found
2. **Stakeholder Mapping Step** - Backend exists, no frontend component found
3. **Skills Configuration Step** - Backend exists (`backend/src/onboarding/skill_recommender.py`), no frontend component found
4. **Email Verification Flow** - No confirmation handler in frontend

### Files Reference

**Backend:**
- `/Users/dhruv/aria/backend/src/api/routes/auth.py`
- `/Users/dhruv/aria/backend/src/onboarding/orchestrator.py`
- `/Users/dhruv/aria/backend/src/onboarding/enrichment.py`
- `/Users/dhruv/aria/backend/src/onboarding/document_ingestion.py`
- `/Users/dhruv/aria/backend/src/onboarding/writing_analysis.py`
- `/Users/dhruv/aria/backend/src/onboarding/integration_wizard.py`
- `/Users/dhruv/aria/backend/src/onboarding/first_goal.py`
- `/Users/dhruv/aria/backend/src/onboarding/activation.py`

**Frontend:**
- `/Users/dhruv/aria/frontend/src/pages/Signup.tsx`
- `/Users/dhruv/aria/frontend/src/components/onboarding/CompanyDiscoveryStep.tsx`
- `/Users/dhruv/aria/frontend/src/components/onboarding/DocumentUploadStep.tsx`
- `/Users/dhruv/aria/frontend/src/components/onboarding/WritingSampleStep.tsx`
- `/Users/dhruv/aria/frontend/src/components/onboarding/IntegrationWizardStep.tsx`
- `/Users/dhruv/aria/frontend/src/components/onboarding/FirstGoalStep.tsx`
- `/Users/dhruv/aria/frontend/src/pages/Onboarding.tsx`

---

## Flow 2: Daily Usage — Chat with ARIA

**Overall Status:** ⚠️ 75% Complete - Core chat works but missing intelligence features

### Journey Map

```
User Opens Chat → Working Memory Loaded
  ↓
User Asks Question → Query Episodic + Semantic Memory (Graphiti)
  ↓
ARIA Responds → [Digital Twin Calibration MISSING]
  ↓
Conversation Stored → Episodic Memory
  ↓
[Lead/Account Updates MISSING]
```

### Step-by-Step Analysis

#### STEP 1: User Opens Chat → Context Loaded
**Status:** ✅ Fully Connected

**Working:**
- Frontend: `frontend/src/pages/AriaChat.tsx` → `/chat`
- Hook: `useConversationMessages(conversationId)` loads history
- Backend: `GET /api/v1/chat/conversations/{conversation_id}` → `backend/src/services/conversations.py`
- Memory: Working memory restored via `backend/src/memory/working.py:196-227`
- Token management: 100K token limit prevents context overflow

**Blocker for Beta:** None

---

#### STEP 2: Semantic Search → Knowledge Graph
**Status:** ✅ Fully Connected

**Working:**
- Backend: `POST /api/v1/chat` → `backend/src/services/chat.py:204-332`
- Memory queries:
  - `MemoryQueryService.query()` in `backend/src/api/routes/memory.py`
  - **Episodic Memory:** Graphiti search (`backend/src/memory/episodic.py:251-302`)
  - **Semantic Memory:** Graphiti search (`backend/src/memory/semantic.py:409-468`)
- Knowledge graph: Neo4j via `backend/src/db/graphiti.py`
- Features:
  - Claude Sonnet 4 + OpenAI embeddings for semantic search
  - Confidence scores and citations
  - Temporal relationship traversal

**Blocker for Beta:** None

---

#### STEP 3: Digital Twin Calibration
**Status:** ⚠️ Implemented but NOT Connected

**What Exists:**
- Service: `backend/src/memory/digital_twin.py`
- Calibration: `backend/src/onboarding/personality_calibrator.py`
- Features:
  - Generates tone guidance from writing fingerprint
  - Adjusts 5 dials: directness, warmth, assertiveness, detail, formality
  - Stored in `user_settings.preferences.digital_twin.personality_calibration`

**What's Missing:**
- ❌ `ChatService.process_message()` does NOT retrieve personality calibration
- ❌ No call to `PersonalityCalibrator.get_calibration()` in chat flow
- ❌ Tone guidance not injected into LLM system prompt

**Fix Required:**
```python
# backend/src/services/chat.py - line ~240
calibration = await PersonalityCalibrator.get_calibration(user_id)
system_prompt += f"\n\nUser Communication Style:\n{calibration.tone_guidance}"
```

**Blocker for Beta:** Medium - ARIA won't match user's communication style

---

#### STEP 4: Conversation → Episodic Memory
**Status:** ✅ Fully Connected

**Working:**
- Service: `backend/src/memory/conversation.py`
- Flow:
  1. Messages stored in Working Memory during conversation
  2. `ExtractionService.extract_and_store()` called fire-and-forget
  3. `EpisodicMemory.store_episode()` saves to Graphiti
- LLM extraction captures:
  - Summary (2-3 sentences)
  - Key topics
  - User emotional state
  - Outcomes and decisions
  - Open threads requiring follow-up
- Bi-temporal tracking: `occurred_at` vs `recorded_at`

**Blocker for Beta:** None

---

#### STEP 5: Lead/Account Auto-Updates
**Status:** ⚠️ Implemented but NOT Connected

**What Exists:**
- Lead Memory: `backend/src/memory/lead_memory.py`
- Event Service: `backend/src/memory/lead_memory_events.py`
- Health Scores: `backend/src/memory/health_score.py`
- Retroactive Enrichment: `backend/src/memory/retroactive_enrichment.py`

**What's Missing:**
- ❌ ChatService does NOT call `LeadEventService` when leads mentioned
- ❌ No automatic health score recalculation from conversation content
- ❌ No entity extraction → lead memory update pipeline

**Fix Required:**
```python
# backend/src/services/chat.py - after episodic memory storage
entities = await ExtractionService.extract_entities(conversation)
for entity in entities:
    if entity.type == "company":
        await LeadEventService.record_conversation_activity(entity.id, conversation_id)
        await HealthScoreService.recalculate(entity.id)
```

**Blocker for Beta:** High - Lead intelligence won't stay current

---

#### STEP 6: OODA Loop for Complex Queries
**Status:** ❌ Not Used in Chat

**What Exists:**
- OODA Loop: `backend/src/core/ooda.py` (814 lines)
- Phases: Observe → Orient → Decide → Act
- Used for goal pursuit and multi-step tasks

**What's Missing:**
- ❌ Chat uses direct LLM call, not OODA cognitive cycle
- ❌ No detection of multi-step intent (e.g., "Research Acme Corp and draft email")
- ❌ No routing to OODA for complex queries

**Blocker for Beta:** Low - Simple chat works, OODA is optimization

---

### Critical Gaps for Beta

1. **Digital Twin NOT Injected** - High priority - ARIA won't match user's style
2. **Lead Memory NOT Auto-Updated** - High priority - Intelligence will be stale
3. **OODA Loop NOT Used** - Low priority - Nice-to-have for complex queries

### Files Reference

**Backend:**
- `/Users/dhruv/aria/backend/src/api/routes/chat.py`
- `/Users/dhruv/aria/backend/src/services/chat.py`
- `/Users/dhruv/aria/backend/src/memory/working.py`
- `/Users/dhruv/aria/backend/src/memory/episodic.py`
- `/Users/dhruv/aria/backend/src/memory/semantic.py`
- `/Users/dhruv/aria/backend/src/db/graphiti.py`
- `/Users/dhruv/aria/backend/src/memory/digital_twin.py`
- `/Users/dhruv/aria/backend/src/onboarding/personality_calibrator.py`
- `/Users/dhruv/aria/backend/src/core/ooda.py`

**Frontend:**
- `/Users/dhruv/aria/frontend/src/pages/AriaChat.tsx`
- `/Users/dhruv/aria/frontend/src/api/chat.ts`

---

## Flow 3: Pre-Meeting Preparation

**Overall Status:** ⚠️ 60% Complete - Infrastructure exists but missing core intelligence

### Journey Map

```
Meeting Detected (24hr window)
  ↓
Background Job → MeetingBriefService
  ↓
Attendee Profiles (Cached) ✅
  ↓
Company Intel (Scout Agent) ✅
  ↓
[Knowledge Graph Queries MISSING] ❌
  ↓
[Account History MISSING] ❌
  ↓
LLM Synthesis → Brief Generated ✅
  ↓
User Views/Edits Brief ✅
```

### Step-by-Step Analysis

#### STEP 1: Meeting Prep Activation
**Status:** ✅ Fully Connected

**Working:**
- Background job: `backend/src/jobs/meeting_brief_generator.py`
  - `find_meetings_needing_briefs()` - Scans 24-hour window
  - `run_meeting_brief_job()` - Hourly cron/scheduler
- Agent: Scout Agent (`backend/src/agents/scout.py`) for research
- Service: `backend/src/services/meeting_brief.py`

**Blocker for Beta:** None

---

#### STEP 2: Data Collection
**Status:** ⚠️ Partially Connected - Missing Core Intelligence

**Working:**
- Attendee Profiles: `backend/src/services/attendee_profile.py` (cached data)
- Company Intelligence: Scout Agent searches for company signals
- API: `POST /api/v1/meetings/{calendar_event_id}/brief/generate`

**Missing:**
- ❌ **Knowledge Graph Queries** - No Graphiti integration in meeting_brief.py
  - No queries to Neo4j for relationship history
  - No episodic memory lookups for past interactions
  - No lead memory graph queries
- ❌ **Account History** - No CRM integration for historical data
  - `our_history` field exists but unpopulated
  - No lead tracking history
  - No previous proposals/quotes
  - No past email exchanges
- ⚠️ **Attendee Enrichment** - Limited to cached/static data
  - No real-time LinkedIn scraping
  - No CRM data merge
  - No email archive analysis

**Expected Integration (Missing):**
```python
# backend/src/services/meeting_brief.py - MISSING
from src.memory.lead_memory_graph import LeadMemoryGraph
from src.db.graphiti import GraphitiClient

# Should query:
# - Episodic memories of past meetings with attendees
# - Lead memory for company engagement history
# - Semantic facts about relationships
# - Causal graph connections
```

**Blocker for Beta:** High - Missing the differentiating "intelligence" feature

---

#### STEP 3: Briefing Generation
**Status:** ✅ Fully Connected

**Working:**
- LLM: Claude Sonnet 4 synthesizes available data
- Output: summary, suggested_agenda, risks_opportunities
- Database: `meeting_briefs` table with status tracking
- Notification: Sent on completion

**Blocker for Beta:** None

---

#### STEP 4: User Views and Edits Brief
**Status:** ✅ Fully Connected

**Working:**
- Page: `frontend/src/pages/MeetingBrief.tsx` → `/dashboard/meetings/:id/brief`
- Components (all in `frontend/src/components/meetingBrief/`):
  - MeetingBriefHeader - Title, time, regenerate/print
  - BriefSummary - Meeting context
  - AttendeesSection - Attendee cards with talking points
  - CompanySection - Company intel
  - AgendaSection - Suggested agenda items
  - RisksOpportunitiesSection - Color-coded risks/opportunities
  - BriefNotesSection - Inline editable notes
- Hooks: `useMeetingBrief(id)` polls every 3s while generating

**Blocker for Beta:** None

---

#### STEP 5: Light Theme
**Status:** ⚠️ Print Only - Screen Uses Dark Theme

**Working:**
- Print styles: Lines 138-157 in MeetingBriefPage.tsx convert to light theme
- Default view: Dark theme (slate-800, slate-700 backgrounds)

**Gap:**
- Design requirement states "light theme" but implementation uses dark mode for screen
- Only print view uses light theme

**Blocker for Beta:** Low - UX preference, not functional issue

---

### Critical Gaps for Beta

1. **Knowledge Graph Integration** - High - Missing core value prop
2. **Account History** - High - `our_history` field unpopulated
3. **Attendee Real-Time Enrichment** - Medium - Relies on cached data
4. **Light Theme for Screen** - Low - Design preference

### Files Reference

**Backend:**
- `/Users/dhruv/aria/backend/src/jobs/meeting_brief_generator.py`
- `/Users/dhruv/aria/backend/src/services/meeting_brief.py`
- `/Users/dhruv/aria/backend/src/services/attendee_profile.py`
- `/Users/dhruv/aria/backend/src/agents/scout.py`
- `/Users/dhruv/aria/backend/src/api/routes/meetings.py`

**Frontend:**
- `/Users/dhruv/aria/frontend/src/pages/MeetingBrief.tsx`
- `/Users/dhruv/aria/frontend/src/components/meetingBrief/*.tsx`
- `/Users/dhruv/aria/frontend/src/hooks/useMeetingBrief.ts`
- `/Users/dhruv/aria/frontend/src/api/meetingBriefs.ts`

---

## Flow 4: Daily Intel Briefing

**Overall Status:** ⚠️ 80% Complete - UI and API work, missing automation

### Journey Map

```
[Daily Scheduler MISSING] ❌
  ↓
Scout Agent (company signals) ✅
Analyst Agent (research) ✅
  ↓
[Signal Population MISSING] ⚠️
  ↓
BriefingService queries market_signals ✅
  ↓
LLM generates summary ✅
  ↓
Dashboard displays briefing ✅
```

### Step-by-Step Analysis

#### STEP 1: Briefing Generation
**Status:** ✅ Backend Fully Implemented

**Working:**
- **Scout Agent:** `backend/src/agents/scout.py`
  - Tools: `web_search`, `news_search`, `social_monitor`, `detect_signals`
  - Deduplication and relevance filtering (min 0.5 score)
  - Returns: company_name, signal_type, headline, summary, source, relevance_score
- **Analyst Agent:** `backend/src/agents/analyst.py`
  - Real APIs: PubMed, ClinicalTrials.gov, FDA, ChEMBL
  - Rate limiting and caching
  - Returns: structured research reports
- **Briefing Service:** `backend/src/services/briefing.py`
  - Data sources:
    1. `_get_signal_data()` - Queries `market_signals` table (past 7 days)
    2. `_get_lead_data()` - Queries `lead_memories` (health scores)
    3. `_get_task_data()` - Queries `prospective_memories` (overdue/due today)
    4. `_get_calendar_data()` - Checks integrations (OAuth pending)
  - LLM summary: Claude Sonnet 4 generates executive summary
  - Storage: Upserts to `daily_briefings` table

**Note:** Scout/Analyst agents are NOT directly invoked by briefing service. Briefing service queries the `market_signals` table which should be populated separately.

**Blocker for Beta:** None - Service works if signals exist

---

#### STEP 2: Scheduling
**Status:** ❌ MISSING - No Automated Daily Generation

**What Exists:**
- Integration sync scheduler (`backend/src/integrations/sync_scheduler.py`) for CRM/Calendar
- Runs every 60 seconds but only handles syncs, not briefings

**What's Missing:**
- ❌ No daily scheduler for automatic briefing generation
- ❌ No cron job at 6:00 AM to generate briefings for all users
- ❌ No background task to run Scout agent overnight
- ❌ Briefings only generated on-demand via API calls

**Fix Required:**
```python
# backend/src/jobs/daily_briefing_job.py - MISSING
async def generate_daily_briefings():
    # 1. Get all active users
    # 2. For each user:
    #    a. Run Scout agent to detect new signals
    #    b. Run Analyst agent for company research
    #    c. Invoke BriefingService.generate_briefing()
```

**Blocker for Beta:** High - Users won't get automatic morning briefings

---

#### STEP 3: Signal Storage
**Status:** ✅ Fully Implemented

**Working:**
- Database: `backend/supabase/migrations/003_market_signals.sql`
  - `market_signals` table with proper indexes
  - `monitored_entities` table for tracking
- Service: `backend/src/services/signal_service.py`
  - CRUD operations: create, get, mark_as_read, dismiss
  - Entity monitoring: add/remove monitored entities
- Signal types: Funding, leadership_change, product_launch, expansion, partnership, acquisition, regulatory, market_trend

**Blocker for Beta:** None

---

#### STEP 4: API Routes
**Status:** ✅ Fully Connected

**Working:**
- File: `backend/src/api/routes/briefings.py`
- Endpoints:
  - `GET /api/v1/briefings/today` - Get today's briefing (generates if missing)
  - `GET /api/v1/briefings` - List recent briefings
  - `GET /api/v1/briefings/{briefing_date}` - Get specific date
  - `POST /api/v1/briefings/generate` - Generate for specific date
  - `POST /api/v1/briefings/regenerate` - Force refresh today
- Registration: ✅ In `backend/src/main.py:132`

**Blocker for Beta:** None

---

#### STEP 5: Frontend Display
**Status:** ✅ Fully Implemented with Dark Theme

**Working:**
- Page: `frontend/src/pages/Dashboard.tsx` → `/dashboard`
- Components (`frontend/src/components/briefing/`):
  - BriefingHeader - Greeting, refresh, history modal
  - ExecutiveSummary - LLM-generated summary
  - SignalsSection - Color-coded by type (blue/green/purple)
  - LeadsSection - Hot leads, needs attention, recently active
  - TasksSection - Overdue and due today
  - CalendarSection - Events for the day
  - BriefingHistoryModal - Past briefings
  - BriefingSkeleton - Loading state
  - BriefingEmpty - Empty state
- API Client: `frontend/src/api/briefings.ts`
- Hooks: `frontend/src/hooks/useBriefing.ts` with React Query
- Theme: ✅ Dark theme with slate palette
  - Signal categories: blue (company), green (market), purple (competitive)
  - Custom animations: `aria-breathe`, `aria-drift`, `aria-glow`

**Blocker for Beta:** None

---

#### STEP 6: Signal Detail Drill-Down
**Status:** ⚠️ Partially Implemented

**Working:**
- Signal cards displayed with headline and summary
- SignalService has full CRUD operations

**Missing:**
- ❌ No click interaction to view full signal details
- ❌ No signal detail modal/page
- ❌ No dismiss button in briefing view

**Blocker for Beta:** Low - Signals visible, detail view is enhancement

---

### Critical Gaps for Beta

1. **Daily Scheduler** - High - No automatic morning briefings
2. **Signal Population Pipeline** - High - No job populating `market_signals` table
3. **Monitored Entity Auto-Population** - Medium - No automatic addition of user's leads
4. **Signal Detail View** - Low - Enhancement, not blocker

### Files Reference

**Backend:**
- `/Users/dhruv/aria/backend/src/agents/scout.py`
- `/Users/dhruv/aria/backend/src/agents/analyst.py`
- `/Users/dhruv/aria/backend/src/services/briefing.py`
- `/Users/dhruv/aria/backend/src/services/signal_service.py`
- `/Users/dhruv/aria/backend/src/api/routes/briefings.py`
- `/Users/dhruv/aria/backend/supabase/migrations/003_market_signals.sql`

**Frontend:**
- `/Users/dhruv/aria/frontend/src/pages/Dashboard.tsx`
- `/Users/dhruv/aria/frontend/src/components/briefing/*.tsx`
- `/Users/dhruv/aria/frontend/src/api/briefings.ts`
- `/Users/dhruv/aria/frontend/src/hooks/useBriefing.ts`

---

## Flow 5: Email Drafting

**Overall Status:** ⚠️ 85% Complete - Core flow works, missing activity logging

### Journey Map

```
User Requests Email Draft
  ↓
Scribe Agent + DraftService ✅
  ↓
Digital Twin Style Applied ✅
  ↓
Draft Shown in [Dark Theme] ⚠️ (Spec says light)
  ↓
User Edits/Approves ✅
  ↓
Email Sent via Composio ✅
  ↓
[Activity Feed Logging MISSING] ❌
```

### Step-by-Step Analysis

#### STEP 1: User Requests Draft
**Status:** ✅ Fully Connected

**Working:**
- **Scribe Agent:** `backend/src/agents/scribe.py:20-279`
  - Registers `draft_email` tool
  - `_draft_email()` generates template-based emails
  - `_personalize()` applies Digital Twin style (greeting, signature)
- **Draft Service:** `backend/src/services/draft_service.py:59-169`
  - `create_draft()` orchestrates full workflow
  - Builds generation prompt with style guidelines
  - LLM generates email content
  - Scores style match against Digital Twin
- **API:** `POST /drafts/email` in `backend/src/api/routes/drafts.py:32-75`
- **Frontend:** `frontend/src/pages/EmailDrafts.tsx`
  - "Compose" button triggers `DraftComposeModal`
  - Hook: `useCreateDraft()` mutation

**Blocker for Beta:** None

---

#### STEP 2: Digital Twin Style
**Status:** ✅ Fully Connected

**Working:**
- Service: `backend/src/memory/digital_twin.py`
  - `get_style_guidelines()` (lines 796-862) - Prompt-ready instructions
  - `score_style_match()` (lines 864-931) - Compares to user's fingerprint
  - `WritingStyleFingerprint` captures:
    - Sentence length, vocabulary level, formality
    - Common phrases, greeting/sign-off styles
    - Emoji usage, punctuation patterns
- Integration:
  - DraftService fetches style guidelines (line 93)
  - Appends to LLM prompt (line 598)
  - Scores generated draft (line 125)
  - Stores `style_match_score` (0.0-1.0) in database
- Database: `email_drafts.style_match_score` column

**Blocker for Beta:** None

---

#### STEP 3: Draft Display Theme
**Status:** ⚠️ Dark Theme (Spec Says Light)

**Current Implementation:**
- `frontend/src/components/drafts/DraftDetailModal.tsx`
  - Uses `bg-slate-800` (DARK theme) - Line 111
  - Shows `StyleMatchIndicator` with confidence score
  - Subject input, rich text editor, tone selector
- `frontend/src/pages/EmailDrafts.tsx`
  - Dark gradient background (line 97)
- `frontend/src/components/drafts/StyleMatchIndicator.tsx`
  - Color-coded score indicator

**Gap:**
- ⚠️ Entire app uses dark theme (slate-900/800)
- ⚠️ No light theme option or toggle found
- ⚠️ "Light theme" requirement appears to be spec error (app designed for dark)

**Blocker for Beta:** Low - Functional, just theme preference

---

#### STEP 4: Edit, Approve, Send
**Status:** ✅ Fully Connected

**Working:**
- **Edit:** `DraftDetailModal.tsx:32-35`
  - Local state for subject, body, tone
  - `handleSave()` calls backend update (lines 76-83)
  - `handleRegenerate()` regenerates with new tone (lines 85-88)
  - Save button enabled only if changes detected (lines 247-265)
- **Send:** `DraftDetailModal.tsx:90-98`
  - `handleSendClick()` shows confirmation modal
  - "Send Email" button (lines 267-277)
  - Confirmation modal with recipient preview (lines 284-332)
- **Backend:**
  - `PUT /drafts/{draft_id}` - Update draft (drafts.py:122-151)
  - `POST /drafts/{draft_id}/regenerate` - Regenerate (lines 178-212)
  - `POST /drafts/{draft_id}/send` - Send email (lines 215-237)
- **Send Service:** `backend/src/services/draft_service.py:404-482`
  - Gets email integration (Gmail/Outlook via Composio)
  - Executes send via OAuth client (lines 447-456)
  - Updates status to "sent" with timestamp (lines 459-461)

**Blocker for Beta:** None

---

#### STEP 5: Activity Feed Logging
**Status:** ❌ MISSING - No Integration

**What Exists:**
- **ActivityService:** `backend/src/services/activity_service.py:23-78`
  - `record()` method to log agent activities
  - Documents `"email_drafted"` as valid activity type (line 41)
  - Database: `aria_activity` table exists
- **Activity Feed UI:** `frontend/src/pages/ActivityFeedPage.tsx`
  - Shows activities with type badges (lines 138-155)
  - `EnvelopeIcon` for email activities (lines 208-214)
  - Displays email activities with amber badge (lines 282-283)

**What's Missing:**
- ❌ DraftService does NOT call `ActivityService.record()`
- ❌ No logging on draft creation or sending
- ❌ No import of ActivityService in draft_service.py

**Fix Required:**
```python
# backend/src/services/draft_service.py - MISSING
from src.services.activity_service import ActivityService

async def send_draft(...):
    # ... existing send logic ...
    await ActivityService.record(
        user_id=user_id,
        agent_type="scribe",
        activity_type="email_drafted",
        description=f"Drafted and sent email to {draft.recipient}",
        confidence=draft.style_match_score
    )
```

**Blocker for Beta:** Medium - No audit trail of email activity

---

### Critical Gaps for Beta

1. **Activity Feed Logging** - Medium - No audit trail
2. **Light Theme** - Low - Spec discrepancy, works in dark
3. **Send Notification** - Low - No user feedback on successful send

### Files Reference

**Backend:**
- `/Users/dhruv/aria/backend/src/agents/scribe.py`
- `/Users/dhruv/aria/backend/src/services/draft_service.py`
- `/Users/dhruv/aria/backend/src/api/routes/drafts.py`
- `/Users/dhruv/aria/backend/src/memory/digital_twin.py`
- `/Users/dhruv/aria/backend/src/services/activity_service.py`

**Frontend:**
- `/Users/dhruv/aria/frontend/src/pages/EmailDrafts.tsx`
- `/Users/dhruv/aria/frontend/src/components/drafts/DraftDetailModal.tsx`
- `/Users/dhruv/aria/frontend/src/components/drafts/StyleMatchIndicator.tsx`
- `/Users/dhruv/aria/frontend/src/hooks/useDrafts.ts`
- `/Users/dhruv/aria/frontend/src/api/drafts.ts`

---

## Flow 6: Competitive Battle Cards

**Overall Status:** ✅ 85% Complete - Manual CRUD works, auto-update needs wiring

### Journey Map

```
Battle Cards Exist ✅
  ↓
Manual CRUD Operations ✅
  ↓
[Auto-Update Pipeline MISSING] ⚠️
  ↓
Market Signals Detected ✅
  ↓
[Signal → Battle Card Connection MISSING] ❌
  ↓
Frontend Display (Dark Theme) ✅
  ↓
[PDF Export MISSING] ❌
```

### Step-by-Step Analysis

#### STEP 1: Data Model & Storage
**Status:** ✅ Fully Connected

**Working:**
- Database: `backend/supabase/migrations/20260203000002_create_battle_cards.sql`
  - `battle_cards` table - Main competitive intelligence
  - `battle_card_changes` table - Complete audit history
  - Fields: competitor_name, competitor_domain, overview, strengths, weaknesses, pricing, differentiation, objection_handlers, update_source, last_updated
  - Security: RLS policies enforce company-scoped access
  - Uniqueness: (company_id, competitor_name)
- Service: `backend/src/services/battle_card_service.py`
  - CRUD operations, change tracking, objection handlers
  - Full logging and error handling

**Blocker for Beta:** None

---

#### STEP 2: Manual Operations
**Status:** ✅ Fully Connected

**Working:**
- API: `backend/src/api/routes/battle_cards.py`
  - Registration: `backend/src/main.py:130`
  - Full CRUD: create, read, update, delete, history
- Frontend CRUD: `frontend/src/api/battleCards.ts`
  - listBattleCards, getBattleCard, createBattleCard, updateBattleCard, deleteBattleCard, getBattleCardHistory, addObjectionHandler
- Hooks: `frontend/src/hooks/useBattleCards.ts`
  - Query key factory, optimistic updates, cache invalidation

**Blocker for Beta:** None

---

#### STEP 3: Auto-Update Mechanism
**Status:** ⚠️ Infrastructure Exists, Connection Missing

**What Exists:**
- `update_source` field: "manual" | "auto"
- UI shows "Auto-updated by Scout" badge when source is "auto"
- Change history tracks all updates
- Scout Agent: `backend/src/agents/scout.py` with intelligence tools
- Signal Service: `backend/src/services/signal_service.py` tracks market signals
- Monitored Entities: System for tracking competitors

**What's Missing:**
- ❌ No automated job/scheduler connecting Scout to battle cards
- ❌ No integration between signal detection and battle card updates
- ❌ No automatic triggering of battle card refreshes

**Fix Required:**
```python
# backend/src/jobs/battle_card_refresh.py - MISSING
async def refresh_competitor_intelligence():
    # 1. Get all monitored_entities where entity_type='competitor'
    # 2. For each competitor, run Scout agent
    # 3. If Scout finds new signals, update battle card with update_source='auto'
    # 4. Record changes in battle_card_changes table
```

**Blocker for Beta:** Medium - Users must manually update battle cards

---

#### STEP 4: Market Signal Integration
**Status:** ⚠️ Both Systems Exist, Not Connected

**Working:**
- Signal Service: `backend/src/services/signal_service.py`
- API: `backend/src/api/routes/signals.py`
- Database: `market_signals` and `monitored_entities` tables
- Signal types: Funding, leadership_change, product_launch, expansion, partnership, acquisition, regulatory, market_trend
- Features: Create, read, mark read/dismissed, unread counts, notifications

**Missing:**
- ❌ No pipeline from market signals → battle card updates
- ❌ No scheduler monitoring signals and triggering Scout refresh
- ❌ User can see signals but they don't auto-update battle cards

**Blocker for Beta:** Medium - Intelligence not automated

---

#### STEP 5: Frontend Components
**Status:** ✅ Fully Connected with Dark Theme

**Working:**
- Page: `frontend/src/pages/BattleCards.tsx` → `/dashboard/battlecards`
  - Route registered in App.tsx:185-188
  - Search, grid view, compare mode (select 2)
- Components (`frontend/src/components/battleCards/`):
  - BattleCardGridItem - Hover effects, comparison selection
  - BattleCardDetailModal - Tabbed view (overview, differentiation, objections, history)
  - BattleCardCompareModal - Side-by-side comparison
  - BattleCardEditModal - Create/edit with dynamic fields
  - EmptyBattleCards - Empty state
- Design System:
  - ✅ Dark theme (`bg-slate-800`, `border-slate-700`)
  - ✅ Color system: emerald (strengths), amber (weaknesses), primary (differentiation)
  - ✅ Auto-update indicator: animated ping dot + badge
  - ✅ Hover effects: gradient borders, shadows, -translate-y-1
  - ✅ Staggered animations: 50ms delay per card
  - ✅ Keyboard support: Escape to close

**Blocker for Beta:** None

---

#### STEP 6: Export Functionality
**Status:** ❌ Missing

**What Exists:**
- History tab shows all changes
- Detail modal shows full competitive intelligence
- Compare modal for side-by-side analysis

**What's Missing:**
- ❌ No PDF export button
- ❌ No share functionality
- ❌ No download/print optimized view
- ❌ No email/Slack sharing integration

**Blocker for Beta:** Low - Nice-to-have, not essential

---

### Critical Gaps for Beta

1. **Auto-Update Pipeline** - Medium - No scheduler connecting Scout to battle cards
2. **Signal Integration** - Medium - Both systems exist but not wired together
3. **PDF Export** - Low - Enhancement, not blocker

### Files Reference

**Backend:**
- `/Users/dhruv/aria/backend/supabase/migrations/20260203000002_create_battle_cards.sql`
- `/Users/dhruv/aria/backend/src/services/battle_card_service.py`
- `/Users/dhruv/aria/backend/src/api/routes/battle_cards.py`
- `/Users/dhruv/aria/backend/src/services/signal_service.py`
- `/Users/dhruv/aria/backend/src/api/routes/signals.py`
- `/Users/dhruv/aria/backend/src/agents/scout.py`

**Frontend:**
- `/Users/dhruv/aria/frontend/src/pages/BattleCards.tsx`
- `/Users/dhruv/aria/frontend/src/components/battleCards/*.tsx`
- `/Users/dhruv/aria/frontend/src/api/battleCards.ts`
- `/Users/dhruv/aria/frontend/src/hooks/useBattleCards.ts`

---

## Summary: Beta Readiness Assessment

### Overall Completeness by Flow

| Flow | Status | Completeness | Critical Blockers |
|------|--------|--------------|-------------------|
| **1. Signup → Onboarding** | ✅ | 85% | None - Production ready |
| **2. Chat with ARIA** | ⚠️ | 75% | Digital Twin not injected, Lead updates missing |
| **3. Meeting Prep** | ⚠️ | 60% | Knowledge graph missing, No account history |
| **4. Daily Briefing** | ⚠️ | 80% | No daily scheduler, No signal population |
| **5. Email Drafting** | ⚠️ | 85% | Activity logging missing |
| **6. Battle Cards** | ✅ | 85% | Auto-update not wired (manual works) |

### High-Priority Fixes for Beta (< 1 Week)

#### 1. **Chat: Digital Twin Integration** (2 days)
- **File:** `backend/src/services/chat.py:240`
- **Fix:** Inject personality calibration into LLM system prompt
- **Impact:** ARIA will match user's communication style

#### 2. **Chat: Lead Memory Auto-Updates** (3 days)
- **File:** `backend/src/services/chat.py:310`
- **Fix:** Extract entities and update lead memory + health scores
- **Impact:** Intelligence stays current as users chat

#### 3. **Daily Briefing: Scheduler** (3 days)
- **File:** `backend/src/jobs/daily_briefing_job.py` (create)
- **Fix:** Implement daily 6:00 AM briefing generation
- **Impact:** Users get automatic morning briefings

#### 4. **Meeting Prep: Knowledge Graph Integration** (4 days)
- **File:** `backend/src/services/meeting_brief.py`
- **Fix:** Query Graphiti for relationship history and past interactions
- **Impact:** Meeting briefs show real intelligence, not just cached data

#### 5. **Email Drafting: Activity Logging** (1 day)
- **File:** `backend/src/services/draft_service.py:480`
- **Fix:** Call ActivityService.record() after sending
- **Impact:** Audit trail of all email activity

### Medium-Priority Enhancements (1-2 Weeks)

#### 6. **Battle Cards: Auto-Update Pipeline** (4 days)
- **Files:** `backend/src/jobs/battle_card_refresh.py` (create)
- **Fix:** Connect Scout agent to battle card updates via scheduler
- **Impact:** Battle cards stay current automatically

#### 7. **Daily Briefing: Signal Population** (3 days)
- **Fix:** Background job to populate market_signals using Scout
- **Impact:** Briefings show real market intelligence

#### 8. **Meeting Prep: Account History** (3 days)
- **Fix:** Populate `our_history` field from CRM + lead memory
- **Impact:** Briefs show complete relationship context

### Low-Priority Polish (Post-Beta)

9. **Onboarding: Missing Frontend Steps** (3 days)
   - User Profile, Stakeholder Mapping, Skills Configuration
10. **Email Verification Flow** (1 day)
11. **Battle Cards: PDF Export** (2 days)
12. **Signal Detail Drill-Down** (1 day)
13. **Theme Standardization** (1 day) - Verify light vs dark requirements

---

## Beta Testing Recommendations

### Week 1: Core Flows Only
Test flows that work end-to-end without high-priority fixes:
- ✅ Flow 1: Signup → Onboarding → First Intelligence
- ✅ Flow 6: Battle Cards (manual operations)

### Week 2: After Critical Fixes
Test flows after Digital Twin, Lead Updates, and Scheduler implemented:
- ✅ Flow 2: Chat with ARIA (with personality + intelligence)
- ✅ Flow 4: Daily Briefing (automated)
- ✅ Flow 5: Email Drafting (with logging)

### Week 3: Full Beta
Test after Knowledge Graph integration:
- ✅ Flow 3: Meeting Prep (with real intelligence)
- ✅ All flows end-to-end

---

## Developer Quick Reference

### Top 5 Files to Fix for Beta

1. **`backend/src/services/chat.py`** - Add Digital Twin + Lead Memory integration
2. **`backend/src/jobs/daily_briefing_job.py`** - CREATE: Daily scheduler
3. **`backend/src/services/meeting_brief.py`** - Add Graphiti knowledge graph queries
4. **`backend/src/services/draft_service.py`** - Add ActivityService logging
5. **`backend/src/jobs/battle_card_refresh.py`** - CREATE: Auto-update pipeline

### Testing Checklist

Before claiming a flow is "working", verify:

- [ ] **Data flows through all systems** - Check Integration Checklist in CLAUDE.md
- [ ] **Memory updates automatically** - Don't require manual triggers
- [ ] **RLS policies enforced** - Test with multiple users
- [ ] **Error handling** - Test with missing/invalid data
- [ ] **Real-time updates** - WebSocket/polling works
- [ ] **Audit logs** - Activity feed shows all actions
- [ ] **Confidence scores** - Memory Delta shown to user

---

**Report Generated:** 2026-02-08
**Next Audit:** After high-priority fixes implemented
