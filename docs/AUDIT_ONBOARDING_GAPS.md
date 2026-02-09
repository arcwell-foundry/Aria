# Onboarding Gaps Audit: Design vs. Implementation

**Date:** 2026-02-09
**Auditor:** Claude Code (Opus 4.6)
**Scope:** Every onboarding step (US-901 through US-920) traced from frontend through backend to database
**Method:** Code-level trace of every function call, database write, and background job trigger

---

## Resolution Status (2026-02-09)

All gaps from this audit have been addressed across 4 sprints + P2 fixes + final verification pass:
- **Sprint 1** (817a2bf): Data integrity — website URL, migration consolidation, tables, cross-user
- **Sprint 2** (20c9576): Action layer — agent execution engine, dashboard population, first conversation
- **Sprint 3** (cf55c13): Intelligence wiring — personality, OODA frontend, skills, delta, graphiti, causal, integrations
- **Sprint 4** (8656fb1): Depth — LinkedIn research, goal decomposition, role config, goal lifecycle, activity feed
- **P2 fixes** (fad733b): OCR, procedural memory, working memory, scheduler, personality depth, SMART validation, phone, readiness cap
- **Final verification** (this commit): Error handling, integration preferences, bootstrap progress, causal doc hypotheses, readiness recalc, migration cleanup, action queue wiring, role config consumption

### Part 1 Verification (#1-#21)

| # | Gap | Status |
|---|-----|--------|
| 1 | Website URL not saved | **FIXED** — Sprint 1 |
| 2 | Missing role dropdown | **FIXED** — Sprint 4 |
| 3 | Missing phone field | **FIXED** — P2 fixes |
| 4 | LinkedIn research not firing | **FIXED** — Sprint 4 |
| 5 | PersonalityCalibrator timing | **FIXED** — Final verification (early calibration after writing analysis) |
| 6 | No sub-goal decomposition | **FIXED** — Sprint 4 |
| 7+21 | Agent execution engine | **FIXED** — Sprint 2 |
| 8 | No readiness final recalculation | **FIXED** — Final verification (recalculation added to activation) |
| 9 | First conversation not auto-triggered | **FIXED** — Sprint 2 |
| 10 | Split migration directories | **FIXED** — Final verification (root deprecated, backend canonical) |
| 11 | conversations/messages tables | **FIXED** — Sprint 1 |
| 12 | Readiness scores exceed 100 | **FIXED** — P2 fixes |
| 13 | No Memory Delta after enrichment | **FIXED** — Sprint 3 |
| 14 | No causal hypotheses from documents | **FIXED** — Final verification (hypothesis generation added) |
| 15 | ProfileMerge fire-and-forget | **FIXED** — Final verification (error callbacks added) |
| 16 | Integration preferences not called | **FIXED** — Final verification (frontend now calls saveIntegrationPreferences) |
| 17 | Email bootstrap progress not shown | **FIXED** — Final verification (polling + progress UI added) |
| 18 | Free-form goals not decomposed | **FIXED** — Sprint 4 (same as #6) |
| 19 | Empty dashboard first visit | **FIXED** — Sprint 2 |
| 20 | No E2E integration tests | **FIXED** — Sprint 2 |

### Part 2 Verification (#1-#37)

| # | System | Was | Now |
|---|--------|-----|-----|
| 1 | Company Enrichment Engine | RUNNING | RUNNING |
| 2 | Corporate Memory | RUNNING | RUNNING |
| 3 | Causal Graph Seeding | PARTIALLY WIRED | **FIXED** — Sprint 3 |
| 4 | Knowledge Gap Detection | RUNNING | RUNNING |
| 5 | Cross-User Acceleration | RUNNING | RUNNING |
| 6 | Digital Twin Creation | RUNNING | RUNNING |
| 7 | LinkedIn Background Research | DEAD CODE | **FIXED** — Sprint 4 |
| 8 | Writing Style Fingerprint | PARTIALLY WIRED | **FIXED** — P2 fixes |
| 9 | Personality Calibration | PARTIALLY WIRED | **FIXED** — Sprint 3 |
| 10 | Email Bootstrap | RUNNING | RUNNING |
| 11 | Document Ingestion Pipeline | RUNNING | RUNNING |
| 12 | OCR for Scanned PDFs | DEAD CODE | **FIXED** — P2 fixes |
| 13 | Semantic Memory | RUNNING | RUNNING |
| 14 | Episodic Memory | RUNNING | RUNNING |
| 15 | Procedural Memory | PARTIALLY WIRED | **FIXED** — P2 fixes |
| 16 | Prospective Memory | RUNNING | RUNNING |
| 17 | Working Memory | PARTIALLY WIRED | **FIXED** — P2 fixes |
| 18 | Graphiti/Neo4j Entity Graph | PARTIALLY WIRED | **FIXED** — Sprint 3 |
| 19 | OODA Adaptive Controller | PARTIALLY WIRED | **FIXED** — Sprint 3 |
| 20 | Memory Delta Presenter | PARTIALLY WIRED | **FIXED** — Sprint 3 |
| 21 | Skills Pre-Configuration | PARTIALLY WIRED | **FIXED** — Sprint 3 |
| 22 | First Conversation Generator | RUNNING | RUNNING |
| 23 | Memory Construction Orchestrator | RUNNING | RUNNING |
| 24 | Source Hierarchy | RUNNING | RUNNING |
| 25 | Goal SMART Validation | PARTIALLY WIRED | **FIXED** — P2 fixes |
| 26 | Goal Decomposition | PARTIALLY WIRED | **FIXED** — Sprint 4 |
| 27 | Agent Activation | RUNNING | RUNNING |
| 28 | Agent Execution Engine | DEAD CODE | **FIXED** — Sprint 2 |
| 29 | Readiness Scores | RUNNING | RUNNING |
| 30 | Dashboard Population | PARTIALLY WIRED | **FIXED** — Sprint 2 |
| 31 | Activity Feed | PARTIALLY WIRED | **FIXED** — Sprint 4 |
| 32 | Action Queue | DEAD CODE | **FIXED** — Final verification (agents now submit actions) |
| 33 | Role Configuration | PARTIALLY WIRED | **FIXED** — Final verification (config consumed in goal execution) |
| 34 | Goal Lifecycle | PARTIALLY WIRED | **FIXED** — Sprint 4 |
| 35 | Profile Update → Memory Merge | RUNNING | RUNNING |
| 36 | Ambient Gap Filler | PARTIALLY WIRED | **FIXED** — P2 fixes |
| 37 | Onboarding Procedural Memory | RUNNING | RUNNING |

Remaining items: **None — all gaps resolved**

---

## Executive Summary

**Overall Status:** Onboarding is substantially implemented but has **7 P0 gaps**, **8 P1 gaps**, and **6 P2 gaps**.

The good news: the core architecture is solid. State machine, readiness scoring, episodic memory, OODA adaptive controller, and multi-system data flows are all wired and working. The gaps are surgical — specific fields not saved, specific background jobs not triggered, specific features not implemented.

Previous audit documents (AUDIT_WIRING.md, AUDIT_COMPLETENESS.md) contain **false positives** — several items flagged as "missing" actually exist (onboarding_state table, first_conversation.py). This audit corrects those.

---

## Gap Summary Table

| # | Step | Gap Description | Severity | Category |
|---|------|----------------|----------|----------|
| 1 | Company Discovery | Website URL not saved to `companies.website` column | **P0** | Data loss |
| 2 | User Profile | Missing `role` dropdown field (Sales, BD, Marketing, etc.) | **P1** | Missing field |
| 3 | User Profile | Missing `phone` field | **P2** | Missing field |
| 4 | User Profile | LinkedIn background research job never fires | **P1** | Missing feature |
| 5 | Writing Samples | PersonalityCalibrator only runs at activation, not after analysis | **P2** | Timing |
| 6 | First Goal | No sub-goal decomposition — only agent type assignment | **P1** | Missing feature |
| 7 | Activation | Agent goals created but no execution engine picks them up | **P0** | Dead code |
| 8 | Activation | No readiness score final recalculation | **P2** | Missing update |
| 9 | First Conversation | Not auto-triggered after activation completes | **P1** | Missing trigger |
| 10 | Cross-cutting | Split migration directories (root vs backend) | **P0** | Deployment risk |
| 11 | Cross-cutting | `conversations` and `messages` tables may not exist in deployed DB | **P0** | Schema gap |
| 12 | Cross-cutting | Readiness scores can theoretically exceed 100 | **P2** | Edge case |
| 13 | Company Discovery | No Memory Delta shown to user after enrichment completes | **P1** | Missing UX |
| 14 | Document Upload | No causal hypothesis generation from documents | **P2** | Missing feature |
| 15 | User Profile | ProfileMergeService runs as fire-and-forget — no error surfacing | **P1** | Error handling |
| 16 | Integration Wizard | `save_integration_preferences()` not called by frontend component | **P1** | Disconnected |
| 17 | Email Integration | Email bootstrap progress not visible in frontend | **P1** | Missing UX |
| 18 | First Goal | Free-form goals not decomposed into concrete sub-tasks | **P1** | Missing feature |
| 19 | Activation | Dashboard daily briefing will be empty on first visit | **P0** | Empty state |
| 20 | Cross-cutting | No E2E integration tests for onboarding flow | **P0** | Test gap |
| 21 | Cross-cutting | Agent execution engine not wired to pick up activation goals | **P0** | Dead code |

---

## Detailed Gap Analysis by Step

### A. Company Discovery (US-902 + US-903)

#### What the spec says:
- Collect company name, website URL, corporate email
- Validate email domain (reject personal)
- LLM-based life sciences gate check
- Trigger Company Enrichment Engine asynchronously
- Check for cross-user acceleration (US-917)
- Store company in Corporate Memory

#### What actually happens:
- Frontend collects `company_name`, `website`, `email` — correct
- Email validation works — rejects gmail.com, yahoo.com, etc.
- Life sciences gate works — LLM classifies with definitions including CDMOs
- Enrichment engine fires via `asyncio.create_task()` — correct
- Cross-user check runs — looks for existing company domain
- Episodic memory recorded, readiness updated (+10 corporate_memory)

#### Gap #1: Website URL not saved to companies table
- **Severity: P0 (data loss)**
- **File:** `backend/src/onboarding/company_discovery.py:204-210`
- **What happens:** `create_company_profile()` builds `company_data` with only `name`, `domain`, and `settings`. The `website` parameter is received but discarded.
- **Database:** `companies.website` column exists (added in migration `20260207120000_us921_profile_page.sql:16`) but is never populated.
- **Impact:** Full website URL is lost. Only the extracted domain is stored. The enrichment engine receives the website (it's passed as a parameter) but the authoritative record is incomplete.
- **Fix:** Add `"website": website` to the `company_data` dict at line 204.

#### Gap #13: No Memory Delta shown after enrichment
- **Severity: P1 (degraded experience)**
- **File:** `backend/src/onboarding/enrichment.py`
- **What happens:** Enrichment stores facts in memory_semantic and updates readiness, but never generates a Memory Delta for the user to review and correct.
- **Spec says:** "UI shows 'ARIA is researching your company...' with progress indicators while enrichment runs" and the enrichment results should be presented via Memory Delta.
- **Impact:** User never sees what ARIA learned about their company during onboarding. Misses the trust-building moment.
- **Fix:** After enrichment completes, call `MemoryDeltaPresenter.generate_delta()` and store result in `onboarding_state.step_data.enrichment_delta` for frontend to display.

#### Verified Working:
- Life sciences gate correctly identifies CDMOs like Repligen
- Enrichment stores facts in `memory_semantic` with confidence scores
- Causal hypotheses generated and stored (confidence 0.50-0.60)
- Knowledge gaps written to `prospective_memories`
- Readiness capped at 60 for enrichment-only data
- Episodic memory records 2 events (registration + enrichment complete)

---

### B. User Profile (US-905)

#### What the spec says:
- Collect: full name, job title, department/function, LinkedIn URL, phone (optional), role dropdown (Sales, BD, Marketing, Operations, Executive, etc.)
- On LinkedIn submit: fire background research job (career history, education, skills, publications)
- Store results in Digital Twin (private)
- Show summary of what ARIA discovered
- User can confirm or correct

#### What actually happens:
- Frontend collects: `full_name`, `title`, `department`, `linkedin_url` — 4 of 6 fields
- Calls `PUT /profile/user` which updates `user_profiles` table
- Triggers `ProfileMergeService.process_update()` as background task
- ProfileMergeService stores facts in `memory_semantic` with source: user_stated, confidence: 0.95
- Readiness updated: digital_twin +10
- Loading saved data on revisit works correctly via `getFullProfile()`

#### Gap #2: Missing role dropdown
- **Severity: P1 (degraded experience)**
- **File:** `frontend/src/components/onboarding/UserProfileStep.tsx:11-16`
- **What happens:** The component's `formData` state only has `full_name`, `title`, `department`, `linkedin_url`. No `role` field.
- **Impact:** The role field is used downstream by SkillRecommendationEngine (US-918) to map user role to recommended skills, and by the OODA adaptive controller to prioritize steps. Without it, skill recommendations default to generic and onboarding adaptation is less targeted.
- **Fix:** Add a `role` dropdown to the form with options: Sales, BD, Marketing, Operations, Executive, Other. Send as part of the payload. Add `role` column to `user_profiles` if not present.

#### Gap #3: Missing phone field
- **Severity: P2 (nice to have)**
- **File:** `frontend/src/components/onboarding/UserProfileStep.tsx`
- **What happens:** No phone input field in the component.
- **Impact:** Minor — phone is optional and not used by any downstream system currently.

#### Gap #4: LinkedIn background research job never fires
- **Severity: P1 (degraded experience)**
- **Files:** No `linkedin_research.py` exists anywhere in the codebase
- **What happens:** The LinkedIn URL is collected, stored in `user_profiles.linkedin_url`, and merged into semantic memory as a fact. But NO background research job runs to analyze the LinkedIn profile.
- **Spec says:** "On submit with LinkedIn URL: Fire background research job — LinkedIn profile analysis: career history, education, skills, endorsements, publications. Professional background synthesis. Cross-validation."
- **Impact:** ARIA doesn't learn from the user's professional background. The Digital Twin is shallower than intended. The "I found your LinkedIn profile — you've been in life sciences for 12 years" moment never happens.
- **Fix:** Implement a `LinkedInResearchService` that takes the LinkedIn URL, uses Exa API to research the person (name + title + company triangulation), extracts career facts, and stores in Digital Twin. Trigger as `asyncio.create_task()` after profile save.

#### Gap #15: ProfileMergeService fire-and-forget error handling
- **Severity: P1 (silent failure)**
- **File:** `backend/src/services/profile_service.py:200-203`
- **What happens:** `asyncio.create_task(ProfileMergeService().process_update(...))` fires the merge pipeline but any errors are silently lost. If the merge fails, facts are never stored in semantic memory.
- **Impact:** Profile data might be saved to `user_profiles` but never flow to memory systems. Silent degradation.
- **Fix:** Add error logging in the task wrapper, or use a try/except with logging inside the task.

---

### C. Writing Samples (US-906)

#### What the spec says:
- Upload/paste writing samples
- Generate WritingStyleFingerprint with 20+ fields
- Store in Digital Twin
- Calibrate personality
- Show preview: "Based on your samples, here's how I'd describe your style..."
- User can adjust

#### What actually happens:
- Frontend supports dual input (paste text + upload files) — correct
- Backend `WritingAnalysisService.analyze_samples()` calls LLM with samples
- Generates `WritingStyleFingerprint` with all 20 required fields
- Stores at `user_settings.preferences.digital_twin.writing_style`
- Readiness updated: digital_twin = min(40, confidence * 40)
- Episodic memory recorded
- Frontend shows style summary and derived traits with thumbs up/down
- PersonalityCalibrator reads fingerprint on activation

#### Gap #5: PersonalityCalibrator timing
- **Severity: P2 (minor)**
- **File:** `backend/src/api/routes/onboarding.py:928-931`
- **What happens:** PersonalityCalibrator only runs as part of the activation step, not immediately after writing analysis. This means the personality calibration isn't available until the very end of onboarding.
- **Impact:** Minor — the calibration is primarily used for post-onboarding interactions. The timing is acceptable.

#### Verified Working:
- All 20 fingerprint fields present in dataclass
- LLM analysis with fallback on parse failure (confidence 0.3)
- Samples capped at 10, 6000 chars total
- Fingerprint retrieval endpoint works
- Comprehensive test coverage

---

### D. Email Integration (US-907 + US-908)

#### What actually happens:
- OAuth flow works for Google Workspace and Microsoft 365
- Privacy exclusions saved to `user_settings.integrations.email`
- Email bootstrap fires via `asyncio.create_task()` after privacy config saved
- Bootstrap processes last 60 days of sent mail
- Contacts extracted to `memory_semantic`, deals to `memory_semantic` (needs_user_confirmation), commitments to `prospective_memories`
- Writing samples from emails fed to `WritingAnalysisService`
- Communication patterns stored in Digital Twin
- Retroactive enrichment triggered
- Readiness updated: relationship_graph and digital_twin

#### Gap #17: Email bootstrap progress not visible
- **Severity: P1 (degraded experience)**
- **File:** `frontend/src/components/onboarding/EmailIntegrationStep.tsx`
- **What happens:** The frontend has no visible progress indicator for the email bootstrap. The backend stores progress in `onboarding_state.metadata.email_bootstrap` and has a `GET /onboarding/email/bootstrap/status` endpoint, but the frontend component doesn't poll it or show progress.
- **Impact:** User connects email and sees nothing happening. The "Processed X of Y emails... Found N contacts" experience described in US-908 doesn't exist.
- **Fix:** Add polling of `/email/bootstrap/status` in the EmailIntegrationStep component with a progress indicator.

#### Verified Working:
- Privacy exclusions respected (sender, domain, category filtering)
- Readiness updates: relationship_graph +15, digital_twin +15 on connect; more from bootstrap
- Episodic memory recorded for both connect and bootstrap complete
- Skip case handled correctly

---

### E. Integration Wizard (US-909)

#### What actually happens:
- Frontend shows CRM (Salesforce, HubSpot), Calendar (Google, Outlook), Messaging (Slack)
- OAuth flows work via Composio
- Connection status tracked in `user_integrations` table
- Orchestrator enriches `step_data` with connection flags after completion
- Readiness updated: integrations = min(60, connected_count * 15)
- Knowledge gaps created for missing integrations
- Episodic memory recorded

#### Gap #16: save_integration_preferences() not called by frontend
- **Severity: P1 (missing data flow)**
- **File:** `frontend/src/components/onboarding/IntegrationWizardStep.tsx`
- **What happens:** The frontend component manages connections (connect/disconnect) but never calls `saveIntegrationPreferences()`. This means:
  - Readiness scores are NOT updated during the integration wizard step from the frontend
  - Knowledge gap entries are NOT created
  - Episodic memory is NOT recorded
  - The backend method `save_integration_preferences()` has all this logic but it's never invoked
- **Why it partially works:** The orchestrator's `_process_integration_wizard()` does run after step completion and enriches step_data with connection flags. But the readiness update, gap detection, and episodic logging in `save_integration_preferences()` are bypassed.
- **Impact:** Integration readiness score not updated until after step completes (if at all). Knowledge gaps for missing integrations not created.
- **Fix:** Call `saveIntegrationPreferences()` when user clicks Continue, or wire the readiness/gap/episodic logic into the orchestrator's `_process_integration_wizard()`.

---

### F. First Goal (US-910)

#### What the spec says:
- Three paths: suggested goals, templates, free-form
- SMART validation
- Goal decomposition into sub-tasks with agent assignments
- Goal stored in goals table
- Triggers activation on completion

#### What actually happens:
- Frontend shows all three paths correctly
- SMART validation runs via LLM (returns score 0-100, feedback, refined version)
- Goal created in `goals` table with proper fields
- Agents assigned in `goal_agents` table based on goal_type mapping
- Readiness updated: goal_clarity +30
- Prospective memory created for tomorrow's check-in
- Episodic memory recorded
- Audit logged

#### Gap #6: No sub-goal decomposition
- **Severity: P1 (degraded experience)**
- **File:** `backend/src/onboarding/first_goal.py:674-712`
- **What happens:** Agent assignment maps goal_type to 1-2 agent types (e.g., lead_gen → hunter + analyst). But there is NO actual decomposition of the goal into concrete sub-tasks/milestones. The spec says "Complex goals → sub-tasks with agent assignments."
- **Impact:** The goal is created as a single monolithic item. No breakdown into actionable steps. No milestones for tracking progress.
- **Fix:** Add a `_decompose_goal()` method that uses LLM to break the goal into 3-5 sub-tasks, then creates `goal_milestones` records for each.

#### Gap #18: Free-form goals not decomposed
- **Severity: P1 (same as #6)**
- This is the same issue — free-form goals are SMART-validated but not decomposed into sub-tasks. The SMART refinement suggests improvements but doesn't create actionable milestones.

---

### G. Activation (US-915)

#### What the spec says:
- Triggered on last step complete or skip-to-dashboard
- Scout, Analyst, Hunter, Operator, Scribe agents activated based on onboarding data
- Each creates a proper Goal with agents assigned
- Results appear in first daily briefing
- Activity feed shows "ARIA is getting to work..."

#### What actually happens:
- Triggered correctly when onboarding completes
- Creates 2-6 LOW-PRIORITY goal records (Scout + Strategist always; others conditional on integrations)
- PersonalityCalibrator runs as background task
- OnboardingOutcomeTracker records outcome
- Episodic memory recorded
- User routed to dashboard

#### Gap #7 + #21: Agent goals created but no execution engine
- **Severity: P0 (beta blocker)**
- **File:** `backend/src/onboarding/activation.py:44-127`
- **What happens:** Activation creates goal records in the `goals` table with agent_type in config. But there is NO background execution engine that:
  1. Picks up these goals
  2. Instantiates the actual agent classes (Hunter, Analyst, etc.)
  3. Executes the agent's OODA loop
  4. Stores results
- **Impact:** The 6 agents are "activated" in name only. No competitive intel monitoring starts. No account research runs. No prospect identification begins. The first daily briefing will have no agent-generated content. The entire "ARIA starts working immediately" promise is broken.
- **Fix:** Implement a `GoalExecutionService` or `AgentScheduler` that:
  1. Queries for goals with status="draft" and config.source="onboarding_activation"
  2. Instantiates the appropriate agent class
  3. Calls `agent.execute()` with the goal config
  4. Updates goal status and stores results
  5. Runs as a background task or scheduled job

#### Gap #8: No readiness final recalculation
- **Severity: P2 (minor)**
- **File:** `backend/src/onboarding/activation.py`
- **What happens:** Activation doesn't recalculate the overall readiness score. After all steps complete, the readiness should be recalculated one final time.
- **Impact:** Minor — the score is approximately correct from individual step updates.

#### Gap #19: Dashboard daily briefing empty on first visit
- **Severity: P0 (beta blocker)**
- **File:** `frontend/src/pages/Dashboard.tsx`
- **What happens:** After activation, user is routed to `/dashboard`. The dashboard calls `useTodayBriefing()` to fetch today's briefing. But since agents haven't executed (Gap #7), there's no content for the briefing. The briefing will be empty or show a generic placeholder.
- **Impact:** First impression after completing onboarding is an empty dashboard. For a $200K/year product, this is unacceptable.
- **Fix:** Either (a) implement agent execution so briefing has content, or (b) create a special "first briefing" that's generated from onboarding data (enrichment facts, goals, upcoming meetings) without waiting for agents.

---

### H. First Conversation (US-914)

#### Correction from Previous Audit:
The AUDIT_COMPLETENESS.md incorrectly flagged US-914 as "MISSING STANDALONE IMPLEMENTATION." **The file exists:** `backend/src/onboarding/first_conversation.py` with a `FirstConversationGenerator` class that has all required methods: `generate()`, `_identify_surprising_fact()`, `_compose_message()`, `_build_memory_delta()`, `_store_first_message()`.

#### Gap #9: First conversation not auto-triggered
- **Severity: P1 (missed moment)**
- **File:** `backend/src/onboarding/orchestrator.py:137-149`
- **What happens:** The activation step creates agent goals and runs PersonalityCalibrator, but does NOT automatically trigger `FirstConversationGenerator.generate()`. The first conversation is only available via `GET /onboarding/first-conversation` — it must be explicitly requested.
- **Impact:** The trust-building "first message that proves ARIA did her homework" moment doesn't happen automatically. User has to navigate to chat, and even then the first conversation generator may not be called.
- **Fix:** Add `FirstConversationGenerator.generate()` as a background task in the activation flow, OR ensure the dashboard/chat page calls it on first load after onboarding.

---

### I. Cross-Cutting Issues

#### Gap #10: Split migration directories
- **Severity: P0 (deployment risk)**
- **Locations:**
  - `/Users/dhruv/aria/supabase/migrations/` — 27 files (through Feb 7)
  - `/Users/dhruv/aria/backend/supabase/migrations/` — 38 files (through Feb 9)
- **What happens:** Migrations are split across two directories. The root directory is 2 days behind. Supabase CLI configuration determines which directory is used for deployment. If pointing to root, recent tables (onboarding_state, company_documents, action_queue, activity_feed, etc.) will NOT be deployed.
- **Impact:** Tables referenced by onboarding code may not exist in the deployed database, causing runtime failures.
- **Fix:** Consolidate all migrations into one directory. Verify Supabase CLI config points to the correct location. Ensure all 38 migrations are applied to the remote database.

#### Gap #11: conversations/messages tables deployment status
- **Severity: P0 (potential runtime failure)**
- **File:** `backend/supabase/migrations/20260202000006_create_conversations.sql` and `20260209000000_repair_conversations_table.sql`
- **What happens:** The conversations table migration exists in the backend migrations directory, plus a repair migration. But given the split directory issue (Gap #10), these may not be applied to production.
- **Impact:** `FirstConversationGenerator._store_first_message()` writes to `conversations` and `messages` tables. If these don't exist, the first conversation feature fails silently.
- **Fix:** Verify tables exist in production database. Apply all pending migrations.

#### Gap #12: Readiness scores can exceed 100
- **Severity: P2 (edge case)**
- **File:** `backend/src/onboarding/orchestrator.py:241-266`
- **What happens:** `update_readiness_scores()` increments scores and clamps to 0-100. However, multiple steps updating the same domain could compound. For example, company discovery sets corporate_memory to 10, enrichment sets it to 60, document upload adds up to 10 per doc. The clamping at 100 works, but the intent isn't always clear.
- **Impact:** Minimal — clamping prevents actual overflow. Logic is just slightly unclear.

#### Gap #20: No E2E integration tests
- **Severity: P0 (quality risk)**
- **What exists:** Unit tests for individual services with mocked dependencies
- **What's missing:** No test that traces a complete onboarding flow from company discovery through activation, verifying that data flows correctly across all systems.
- **Impact:** Bugs at integration boundaries (e.g., Gap #1 website not saved, Gap #16 preferences not called) aren't caught. Each service passes its unit tests but the flow is broken at the seams.
- **Fix:** Implement at least one happy-path E2E test: create user → company discovery → document upload → profile → writing samples → email → integrations → first goal → activation → verify all tables populated correctly.

---

## Priority Classification

### P0 — Blocks Beta (7 gaps)

| # | Gap | Fix Effort | Why P0 |
|---|-----|-----------|--------|
| 1 | Website URL not saved | 1 line | Data permanently lost for every new company |
| 7+21 | Agent execution engine missing | Large | "ARIA starts working immediately" is the core promise |
| 10 | Split migration directories | Medium | Production DB may be missing tables |
| 11 | conversations/messages deployment | Medium | First conversation feature crashes |
| 19 | Empty dashboard on first visit | Medium | First impression of $200K product is empty page |
| 20 | No E2E integration tests | Large | Integration bugs undetectable |

### P1 — Degraded Experience (8 gaps)

| # | Gap | Fix Effort | Why P1 |
|---|-----|-----------|--------|
| 2 | Missing role dropdown | Small | Skill recommendations and OODA adaptation are less targeted |
| 4 | LinkedIn research not firing | Medium | Digital Twin is shallower than intended |
| 6+18 | No goal decomposition | Medium | Goals are monolithic, no milestones |
| 9 | First conversation not auto-triggered | Small | Trust-building moment missed |
| 13 | No Memory Delta after enrichment | Medium | User doesn't see what ARIA learned |
| 15 | ProfileMerge fire-and-forget errors | Small | Silent failures in memory pipeline |
| 16 | Integration preferences not called | Small | Readiness/gaps not updated during wizard |
| 17 | Email bootstrap progress not shown | Small | User sees no activity after email connect |

### P2 — Nice to Have (6 gaps)

| # | Gap | Fix Effort | Why P2 |
|---|-----|-----------|--------|
| 3 | Missing phone field | Trivial | Optional, no downstream use |
| 5 | PersonalityCalibrator timing | None | Works at activation, acceptable |
| 8 | No readiness final recalculation | Trivial | Approximately correct already |
| 12 | Readiness score overflow edge case | Trivial | Clamping works |
| 14 | No causal hypotheses from documents | Small | Data stored, just not as graph edges |

---

## P0 Fix Details

### Fix #1: Website URL not saved
**File:** `backend/src/onboarding/company_discovery.py`
**Line:** 204-210
**Change:** Add `"website": website` to the `company_data` dict:
```python
company_data: dict[str, Any] = {
    "name": company_name,
    "domain": domain,
    "website": website,  # ADD THIS LINE
    "settings": {
        "source": "onboarding",
        "registered_by": user_id,
    },
}
```

### Fix #7+21: Agent execution engine
**New file:** `backend/src/services/agent_executor.py`
**What it needs:**
1. A `GoalExecutionService` class that:
   - Queries `goals` table for status="draft" with config.source="onboarding_activation"
   - For each goal, instantiates the agent class (`ScoutAgent`, `AnalystAgent`, etc.)
   - Calls `agent.execute()` with goal config as context
   - Updates goal status to "active" then "complete"
   - Stores agent results in appropriate memory systems
2. Called as background task from activation, or as a periodic scheduler
3. Must respect LOW priority — yields to user-initiated tasks

### Fix #10: Migration directory consolidation
**Action:**
1. Verify which directory Supabase CLI uses (check `supabase/config.toml` or `.supabase` config)
2. Copy all migrations from `backend/supabase/migrations/` to the configured directory (or vice versa)
3. Ensure no duplicate filenames
4. Run `supabase db push` to apply all pending migrations
5. Delete the unused directory or add a README pointing to the canonical location

### Fix #11: Verify conversations/messages tables
**Action:**
1. Run: `SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('conversations', 'messages');`
2. If missing, apply migrations from `backend/supabase/migrations/20260202000006_create_conversations.sql` and `20260209000000_repair_conversations_table.sql`

### Fix #19: Empty dashboard on first visit
**Options (pick one):**
A. **Generate a "first briefing" from onboarding data** — Use enrichment facts, first goal, upcoming meetings (if calendar connected), and readiness assessment to create a meaningful first briefing without waiting for agents.
B. **Show onboarding summary instead** — After onboarding, show a "What ARIA learned" page with Memory Delta, readiness scores, and next steps before redirecting to dashboard.
C. **Fast-execute one agent** — Run the Scout agent synchronously (or with short timeout) during activation to have at least competitive intel ready.

### Fix #20: E2E integration test
**New file:** `backend/tests/integration/test_onboarding_e2e.py`
**What it needs:**
1. Create test user via auth
2. Call company discovery → verify companies table, enrichment triggered
3. Upload document → verify company_documents, document_chunks populated
4. Save profile → verify user_profiles, memory_semantic facts created
5. Analyze writing → verify user_settings.preferences.digital_twin.writing_style
6. Connect email (mock OAuth) → verify readiness updated
7. Save integrations → verify step_data enriched
8. Create first goal → verify goals and goal_agents tables
9. Activate → verify agent goals created
10. Assert readiness scores across all 5 domains > 0

---

## Corrections to Previous Audits

| Previous Claim | Source | Actual Status |
|---------------|--------|---------------|
| "onboarding_state table missing" | AUDIT_WIRING.md | **EXISTS** at `backend/supabase/migrations/20260206000000_onboarding_state.sql` |
| "US-914 FirstConversationGenerator MISSING" | AUDIT_COMPLETENESS.md | **EXISTS** at `backend/src/onboarding/first_conversation.py` |
| "43 missing database tables" | AUDIT_WIRING.md | **OVERSTATED** — many tables exist in `backend/supabase/migrations/` directory that the audit didn't check |
| "Onboarding data won't save" | AUDIT_WIRING.md | **INCORRECT** — onboarding_state table exists and orchestrator reads/writes it correctly |
| "Memory flows from onboarding not implemented" | AUDIT_WIRING.md | **PARTIALLY INCORRECT** — ProfileMergeService, WritingAnalysisService, and EmailBootstrap all flow data to memory systems |

**Root cause of false positives:** The AUDIT_WIRING.md only checked `supabase/migrations/` (root directory) and missed `backend/supabase/migrations/` (where most recent tables were created). This is itself evidence of Gap #10.

---

## What's Working Well

To balance this audit, here's what's solidly implemented:

1. **State machine** — 8 steps, resume logic, skip affordance, progress tracking
2. **Readiness scoring** — 5 domains, weighted average, API endpoint, recalculation
3. **Episodic memory** — Events recorded at every step via Graphiti
4. **OODA adaptive controller** — Runs after every step, injects contextual questions
5. **Company Enrichment Engine** — Full research pipeline with Exa, classification, fact extraction, gap detection
6. **Email Bootstrap** — 60-day processing, contact extraction, commitment detection, writing refinement
7. **Cross-user acceleration** — Corporate Memory sharing works
8. **Writing analysis** — Full fingerprint with 20 fields, personality calibration, Digital Twin storage
9. **Privacy controls** — Exclusion management, category toggles, attachment approval
10. **Frontend UX** — Sidebar navigation, step resumption, loading states, error handling

---

## Recommended Fix Order

1. **Gap #1** (website URL) — 5 minutes, prevents data loss immediately
2. **Gap #10** (migration directories) — 30 minutes, prevents deployment failures
3. **Gap #11** (verify deployed tables) — 15 minutes, confirms DB is correct
4. **Gap #19** (empty dashboard) — 2-4 hours, critical first impression
5. **Gap #16** (integration preferences) — 30 minutes, fixes readiness flow
6. **Gap #9** (first conversation trigger) — 30 minutes, enables trust moment
7. **Gap #17** (email bootstrap progress) — 1 hour, shows activity to user
8. **Gap #2** (role dropdown) — 1 hour, improves downstream features
9. **Gap #4** (LinkedIn research) — 4-6 hours, enriches Digital Twin
10. **Gap #7+21** (agent execution) — 8-16 hours, most complex but most impactful
11. **Gap #6+18** (goal decomposition) — 2-4 hours, improves goal tracking
12. **Gap #13** (Memory Delta after enrichment) — 2-4 hours, trust-building UX
13. **Gap #20** (E2E tests) — 4-8 hours, prevents future regressions
14. **Gap #15** (ProfileMerge errors) — 30 minutes, improves reliability
15. **Remaining P2 gaps** — as time permits

---

**Audit completed:** 2026-02-09 13:15 EST
**Methodology:** Parallel code exploration agents traced every onboarding step from frontend component through API route, backend service, database write, and background job trigger. Cross-referenced against Phase 9 spec (US-901 through US-920) acceptance criteria.

---

## Part 2: Design-Intent Intelligence Verification

**Date:** 2026-02-09
**Scope:** US-901 through US-943 — every intelligence system behind onboarding
**Method:** 5 parallel code-trace agents examined every file, function call, database write, and background job trigger referenced by the Phase 9 spec. Each item traced from trigger point through execution to storage.

### Summary

Of 37 intelligence systems audited:

| Status | Count | Items |
|--------|-------|-------|
| **RUNNING** | 17 | #1, #2, #4, #5, #6, #10, #11, #13, #14, #16, #22, #23, #24, #27, #29, #35, #37 |
| **PARTIALLY WIRED** | 13 | #3, #8, #9, #15, #17, #18, #19, #21, #25, #26, #30, #34, #36 |
| **DEAD CODE** | 7 | #7, #12, #20 (enrichment context), #28, #31 (onboarding-specific), #32 (agent-produced), #33 (behavior config) |

**Critical finding:** The intelligence *collection* layer is largely operational. The intelligence *action* layer is broken — agents are activated but never execute, goals are created but never decomposed, and the dashboard will be empty on first visit because nothing runs the agents that would populate it.

---

### COMPANY INTELLIGENCE

#### #1 — Company Enrichment Engine (US-903)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - Triggered as `asyncio.create_task()` from `company_discovery.py:291-301` when company step completes
  - Full 7-stage pipeline in `enrichment.py:122-238` (CLASSIFYING → RESEARCHING → EXTRACTING → SEEDING_GRAPH → IDENTIFYING_GAPS → COMPLETE/FAILED)
  - **Exa API:** Called at `enrichment.py:335-378` (website), `enrichment.py:380-425` (news), `enrichment.py:479-522` (leadership). Requires `EXA_API_KEY` in config — gracefully degrades if missing (logs warning, continues)
  - **ClinicalTrials.gov:** Queries `clinicaltrials.gov/api/v2/studies` at `enrichment.py:427-477`. No API key needed — always runs
  - **FDA/SEC:** NOT queried. No FDA or SEC API integration exists
  - **Competitor identification:** Done via LLM classification during enrichment
  - **Leadership mapping:** Done via Exa search at `enrichment.py:479-522`
- **Missing:** FDA database queries, SEC filing queries. These are spec'd in US-903 but not implemented. Exa API key must be configured for 3 of 4 research modules to run.

#### #2 — Corporate Memory (Semantic Storage)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - Facts stored in `memory_semantic` table at `enrichment.py:790-807`
  - Each fact includes: `user_id`, `fact` (text), `confidence` (0-1.0), `source` (e.g. `enrichment_website`, `enrichment_clinical_trials`), `metadata` (category, entities, company_id)
  - Source attribution and confidence scores are present on every insert
- **Caveat:** Cross-user service reads from `corporate_facts` table (`cross_user.py:177-182`), not `memory_semantic`. No ETL between these tables is visible — see Item #5 note.

#### #3 — Causal Graph Seeding
- **Status: PARTIALLY WIRED**
- **Severity: P1**
- **Evidence:**
  - Hypotheses generated at `enrichment.py:577-645` via LLM with examples ("Series C funding → hiring ramp → pipeline generation need")
  - 5-10 hypotheses per enrichment, confidence 0.50-0.60, source: `inferred_during_onboarding`
  - **Stored to Supabase `memory_semantic` only** at `enrichment.py:809-825`
  - Comment at line 809 says "(Graphiti fallback)" — but Graphiti integration is NOT implemented
  - No `GraphitiClient` import in enrichment.py. No Neo4j operations
- **Missing:** Hypotheses should be stored as causal edges in Graphiti/Neo4j for graph traversal. Currently only queryable via SQL, not graph queries.

#### #4 — Knowledge Gap Detection (US-912)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - `gap_detector.py:116-186` — Full `KnowledgeGapDetector` class
  - API endpoint at `onboarding.py:958-962` (`POST /gaps`)
  - Analyzes 4 domains: Corporate Memory (lines 188-226), Digital Twin (228-301), Competitive Intel (303-364), Integration (366-397)
  - Gaps written to `prospective_memories` at `gap_detector.py:413-442` with metadata (domain, subdomain, priority, fill_strategy, suggested_agent)
  - Also called by `ambient_gap_filler.py:8-14` for continuous post-onboarding gap filling
- **Note:** Enrichment has its OWN gap detection (`enrichment.py:647-720`) that runs independently — no deduplication between the two systems.

#### #5 — Cross-User Acceleration (US-917)
- **Status: RUNNING**
- **Severity: P2 (data flow concern)**
- **Evidence:**
  - Company detection at `company_discovery.py:137-161` — queries `companies` table by domain
  - `cross_user.py:86-314` — Full `CrossUserAccelerationService`
  - Richness calculated at `cross_user.py:316-364`: fact_count × 40% + predicate_diversity × 30% + avg_confidence × 30%
  - Step skipping: richness > 30% → skip company_discovery; richness > 70% → skip document_upload (`cross_user.py:265-289`)
  - Readiness inheritance: `inherited_readiness = richness * 0.8` (line 260)
  - Memory Delta of company facts shown for user confirmation
- **Concern:** Cross-user reads from `corporate_facts` table, but enrichment writes to `memory_semantic`. No ETL pipeline bridges these tables — User #2 may not see User #1's enrichment facts.

---

### USER INTELLIGENCE

#### #6 — Digital Twin Creation
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - Two implementations:
    - **Graphiti-based:** `memory/digital_twin.py:461` — `DigitalTwin` class, 13-field `WritingStyleFingerprint` dataclass (lines 32-103), stores via `add_episode()` (lines 741-747)
    - **Supabase-based:** `onboarding/writing_analysis.py:104` — `WritingAnalysisService`, 20-field `WritingStyleFingerprint` Pydantic model (lines 26-66), stores at `user_settings.preferences.digital_twin.writing_style` (lines 232-234)
  - Created via onboarding route `POST /onboarding/writing-analysis/analyze` (onboarding.py:392-404)
  - Also refined by email bootstrap at `email_bootstrap.py:711-726`
  - Data stored: writing style fingerprint, communication patterns, personality calibration

#### #7 — LinkedIn Background Research (US-905)
- **Status: DEAD CODE**
- **Severity: P1**
- **Evidence:**
  - **No `linkedin_research.py` exists anywhere in the codebase**
  - No background research job is triggered when LinkedIn URL is submitted
  - LinkedIn URL is collected and stored in `user_profiles.linkedin_url`
  - ProfileMergeService stores it as a semantic fact ("User's LinkedIn profile is {value}") at `profile_merge.py:65`
  - No Exa API call for person research exists
- **Missing:** A `LinkedInResearchService` that takes the URL, uses Exa API to triangulate (name + title + company), extracts career facts, and stores in Digital Twin. The "I found your LinkedIn profile — you've been in life sciences for 12 years" moment described in US-905 cannot happen.

#### #8 — Writing Style Fingerprint (US-906)
- **Status: PARTIALLY WIRED**
- **Severity: P2**
- **Evidence:**
  - Full 20-field fingerprint defined at `writing_analysis.py:26-66`: avg_sentence_length, sentence_length_variance, paragraph_style, lexical_diversity, formality_index, vocabulary_sophistication, uses_em_dashes, uses_semicolons, exclamation_frequency, ellipsis_usage, opening_style, closing_style, directness, warmth, assertiveness, data_driven, hedging_frequency, emoji_usage, rhetorical_style, style_summary, confidence
  - LLM analysis produces all 20 fields at `writing_analysis.py:166-198`
  - Stored in `user_settings.preferences.digital_twin.writing_style` (line 232)
  - Readiness updated (line 146), episodic event recorded (line 149)
- **Partially wired because:** Fingerprint is produced but only 5 of 20 fields are consumed downstream (by PersonalityCalibrator — see #9). The other 15 fields sit unused.

#### #9 — Personality Calibration (US-919)
- **Status: PARTIALLY WIRED**
- **Severity: P1**
- **Evidence:**
  - `personality_calibrator.py:47` — Full `PersonalityCalibrator` class
  - Reads fingerprint from `user_settings.preferences.digital_twin.writing_style` at `personality_calibrator.py:242-270`
  - Calculates 5 traits: directness, warmth, assertiveness, detail_orientation, formality
  - Generates `tone_guidance` (string for LLM prompt injection) and `example_adjustments`
  - Stored at `user_settings.preferences.digital_twin.personality_calibration` (line 302)
  - Triggered during activation at `onboarding.py:927-931` as background task
- **Missing:** Calibration is generated and stored but **NOT consumed by any LLM prompt builder**. No evidence of retrieval in Scribe agent or any draft generation service. The tone_guidance string is generated but never injected into prompts. This makes the calibration DEAD on arrival — it exists in the DB but doesn't influence ARIA's output.

#### #10 — Email Bootstrap (US-908)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - `email_bootstrap.py:85` — Full `PriorityEmailIngestion` class
  - Fetches 60 days of SENT mail via Composio GMAIL_FETCH_EMAILS action (line 262), max 500 emails
  - Contact extraction at `email_bootstrap.py:322-362` — deduplicates recipients, classifies top 20 via LLM, returns up to 50
  - Deal detection at `email_bootstrap.py:415-458` — finds threads with 3+ messages, classifies as deal/project/routine/personal
  - Writing refinement at `email_bootstrap.py:711-726` — calls `WritingAnalysisService.analyze_samples()` with email samples
  - Communication pattern analysis at `email_bootstrap.py:576-613` — peak hours, volume, cadence
  - Contacts → `memory_semantic` (confidence 0.85), deals → `memory_semantic` (needs_user_confirmation), commitments → `prospective_memories`
  - Triggered after privacy config saved at `email_integration.py:250-264` as background task
  - Retroactive enrichment triggered at `email_bootstrap.py:805-856`

---

### DOCUMENT PROCESSING

#### #11 — Document Ingestion Pipeline (US-904)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - `document_ingestion.py:45-776` — Full pipeline
  - Upload route triggers async processing via `asyncio.create_task()` (line 154-157)
  - Pipeline stages (lines 181-284):
    1. Text extraction: Format detection via `_extract_text()` (line 200)
    2. Semantic chunking: Structure-aware at lines 411-456
    3. Entity extraction: LLM-powered NER (line 218)
    4. Embedding generation: OpenAI text-embedding-3-small (lines 489-520)
    5. Quality scoring: Domain-specific assessment (lines 522-558)
    6. Knowledge extraction: Facts stored in `memory_semantic` (lines 592-604)
  - Chunks stored in `document_chunks` table with embeddings and entities (lines 222-232)
  - Entity seeding to Graphiti via episodic events (lines 623-701)
  - Readiness updated (line 268), episodic memory recorded (line 271)

#### #12 — OCR for Scanned PDFs
- **Status: DEAD CODE**
- **Severity: P2**
- **Evidence:**
  - `document_ingestion.py:310-312`: Explicitly logs "Image OCR not yet implemented — skipping text extraction" and returns empty string
  - PDF extraction uses PyMuPDF's `.get_text()` (lines 317-337) — works for native/searchable PDFs only
  - No `pytesseract`, `tesseract`, `pdf2image`, or OCR library in `requirements.txt`
  - Scanned PDFs with embedded images will silently return empty text
- **Missing:** OCR library (e.g. pytesseract + Tesseract binary) and integration into the text extraction pipeline.

---

### MEMORY SYSTEMS

#### #13 — Semantic Memory
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - Inserts into `memory_semantic` from multiple onboarding sources:
    - Document ingestion (document_ingestion.py:592-604)
    - Email bootstrap (email_bootstrap.py — multiple inserts)
    - Enrichment (enrichment.py:790-807)
    - Profile merge (profile_merge.py:212-305)
  - Company facts, user profile facts, and enrichment discoveries all stored with source attribution and confidence scores
  - Memory constructor gathers all facts at `memory_constructor.py:162` for conflict resolution

#### #14 — Episodic Memory
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - `memory/episodic.py:85-296` — `store_episode()` writes to Graphiti/Neo4j via `client.add_episode()` (line 251)
  - Events recorded at:
    - Onboarding start (orchestrator.py:76-81)
    - Document processing (document_ingestion.py:271-274)
    - Entity extraction (document_ingestion.py:668-689)
    - Gap analysis (gap_detector.py:165-182)
    - Memory construction complete (memory_constructor.py:303-330)
    - Activation (activation.py:481-519)
    - Email bootstrap, writing analysis, personality calibration — each records an event
  - Graphiti client properly wired at `db/graphiti.py:130-162`

#### #15 — Procedural Memory
- **Status: PARTIALLY WIRED**
- **Severity: P2**
- **Evidence:**
  - Full `ProceduralMemory` class at `memory/procedural.py:109-543` — supports workflow creation, retrieval, updating, outcome tracking
  - Uses Supabase `procedural_memories` table
  - **Zero calls to ProceduralMemory during onboarding** — no imports in orchestrator, enrichment, document ingestion, or gap detector
  - The service is production-ready but sits idle during Phase 9A
- **Missing:** No onboarding steps record procedural memory. Spec (US-916) says procedural memory should learn "which adaptations lead to higher readiness scores" but this isn't implemented during onboarding.

#### #16 — Prospective Memory
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - Gap detector creates entries at `gap_detector.py:413-442` — each knowledge gap becomes a pending task with priority, fill_strategy, suggested_agent
  - Email bootstrap creates commitment entries at `email_bootstrap.py:686-709`
  - First goal creates check-in reminders at `first_goal.py:731-763`
  - Full `ProspectiveTask` service at `memory/prospective.py:131-635`

#### #17 — Working Memory
- **Status: PARTIALLY WIRED**
- **Severity: P2**
- **Evidence:**
  - Full `WorkingMemory` class at `memory/working.py:32-259` — stores conversation context, messages, entities, goals
  - `WorkingMemoryManager` singleton at line 196 — manages multiple sessions with token counting
  - **NOT used by OODA Adaptive Controller** — `adaptive_controller.py` does not import or use WorkingMemory
  - Controller maintains state via Supabase `onboarding_state` table, not in-memory working memory
  - Each OODA loop is stateless relative to prior observations — no persistent working context across step transitions
- **Missing:** Integration between adaptive controller and working memory. OODA `_observe()` gathers facts but returns a dict, not a memory object.

#### #18 — Graphiti/Neo4j Entity Graph
- **Status: PARTIALLY WIRED**
- **Severity: P1**
- **Evidence:**
  - GraphitiClient at `db/graphiti.py:19-180` — `add_episode()` (line 130) and `search()` (line 165) methods exist
  - **Episodic events flow to Graphiti correctly** — all store_episode() calls work
  - **Entity graph seeding BROKEN:** `memory_constructor.py:245` calls `graphiti.add_entity()` — but **GraphitiClient does NOT have an `add_entity()` method**. Only `add_episode()` and `search()` exist.
  - Call silently fails (caught by try/except at lines 254-258, logged as warning)
  - Entities fall back to Supabase JSON storage in `document_chunks.entities` field
- **Missing:** `add_entity()` method on GraphitiClient, or refactoring to use `add_episode()` with entity-type episodes. Without this, no entity relationship graph is built in Neo4j — only flat episodes exist.

---

### INTELLIGENCE ORCHESTRATION

#### #19 — OODA Adaptive Controller (US-916)
- **Status: PARTIALLY WIRED**
- **Severity: P1**
- **Evidence:**
  - Full `OnboardingOODAController` at `adaptive_controller.py:1-360` with OBSERVE, ORIENT, DECIDE, ACT methods
  - Called by orchestrator at `orchestrator.py:151-158` as non-blocking `asyncio.create_task()` for `assess_next_step()`
  - Contextual question injection logic at lines 214-225 (e.g. CDMO-specific therapeutic area question)
  - Step reordering logic at lines 188-242
  - API endpoints: `POST /onboarding/assess-next-step` and `GET /onboarding/steps/{step}/injected-questions` (onboarding.py:1080-1127)
  - Injected questions stored in `onboarding_state.metadata.ooda_injections` (line 287)
- **Missing:** Frontend does not consume `get_injected_questions()`. The adaptive questions are generated and stored but never displayed to the user between steps. The backend runs OODA but the UI ignores its output.

#### #20 — Memory Delta Presenter (US-920)
- **Status: PARTIALLY WIRED**
- **Severity: P1**
- **Evidence:**
  - Backend: `memory/delta_presenter.py:1-343` — Full `MemoryDeltaPresenter` with `generate_delta()` (lines 98-128), `apply_correction()` (lines 130-214), confidence → language mapping (lines 62-68, 285-327)
  - Frontend: `components/memory/MemoryDelta.tsx:1-150` — React component with domain grouping, confidence tiers, fact correction UI
  - Hook: `hooks/useMemoryDelta.ts` — `useCorrectMemory()` for correction workflow
  - Used by profile_merge at `profile_merge.py:307-337` — generates delta after profile updates
  - Used by first_conversation at `onboarding.py:1000-1007` — returns delta in first conversation message
- **GAP:** After enrichment completes, **NO Memory Delta is generated or shown**. The enrichment engine (`enrichment.py`) does not call `MemoryDeltaPresenter.generate_delta()`. The "ARIA is researching your company..." → "Here's what I found" trust-building moment does not exist. Delta only appears in first conversation (end of onboarding) and profile updates (post-onboarding).

#### #21 — Skills Pre-Configuration (US-918)
- **Status: PARTIALLY WIRED (effectively DEAD CODE during activation)**
- **Severity: P1**
- **Evidence:**
  - `skill_recommender.py:1-169` — Full `SkillRecommendationEngine`
  - Mapping: Company type → skill set (lines 23-66): Cell/Gene Therapy, CDMO, Large Pharma, Biotech, CRO, Diagnostics, Medical Device
  - `recommend()` at lines 90-118 returns recommendations with COMMUNITY trust level
  - `pre_install()` at lines 120-168 calls `SkillInstaller.install()` with `auto_installed=True`
  - API endpoints: `POST /onboarding/skills/recommend` and `POST /onboarding/skills/pre-install` (onboarding.py:1311-1396)
  - **NOT called during activation** — `activation.py` does not import `SkillRecommendationEngine`
- **Missing:** A call to `SkillRecommendationEngine.pre_install()` during the activation flow. Skills exist as infrastructure but are never auto-configured based on onboarding data.

#### #22 — First Conversation Generator (US-914)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - `first_conversation.py:1-592` — Full `FirstConversationGenerator`
  - `generate()` at lines 55-116: gathers top facts (line 67), gets company classification (line 68), identifies surprising fact (line 75), composes message via LLM (line 78), stores as first message (line 89), records episodic event (line 92)
  - Called by memory constructor at `memory_constructor.py:115-127` after construction completes
  - Also callable via API: `GET /onboarding/first-conversation` (onboarding.py:995-1007)
  - Stores result in `conversations` and `messages` tables with metadata including memory_delta, facts_referenced, confidence_level (first_conversation.py:377-423)

#### #23 — Memory Construction Orchestrator (US-911)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - `memory_constructor.py:1-361` — Dedicated `MemoryConstructionOrchestrator`
  - Runs full pipeline at lines 59-151:
    1. Gathers all facts from all sources (line 74)
    2. Resolves conflicts using source hierarchy (line 77)
    3. Builds entity relationship graph (line 80) — though `add_entity()` fails silently (see #18)
    4. Calculates readiness scores (line 83)
    5. Records episodic event (line 95)
    6. Logs audit (line 108)
    7. Triggers first conversation (line 122)
    8. Triggers agent activation (line 137)
  - Called during activation at `onboarding.py:900-939` as background task (line 937)
  - Source hierarchy defined at lines 21-30: user_stated (5.0) > crm_import (4.0) > document_upload (3.0) > email_bootstrap (2.5) > enrichment (1.5-2.0) > inferred (1.0)

#### #24 — Source Hierarchy Conflict Resolution
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - **Memory Constructor** at `memory_constructor.py:21-30`: Priority scale (5.0 → 1.0)
  - **Profile Merge** at `profile_merge.py:41-52`: Confidence scale (0.95 → 0.55)
  - Both follow user > CRM > document > web > inferred pattern per CLAUDE.md
  - Conflict resolution in profile_merge: `_merge_changes()` at lines 212-305 — searches for existing facts in same category, finds conflicts, supersedes lower-confidence facts (reduces to 0.3x confidence), inserts new user_stated fact (0.95)
  - Memory constructor: `_resolve_conflicts()` at lines 165-192 — applies source priority boost: `adjusted = min(0.99, original_confidence * (0.8 + base_priority * 0.04))`

---

### GOAL & AGENT ACTIVATION

#### #25 — Goal SMART Validation
- **Status: PARTIALLY WIRED**
- **Severity: P2**
- **Evidence:**
  - `first_goal.py:537-593` — `validate_smart()` method implemented
  - LLM call at lines 577-581 with detailed prompt requesting: is_smart, score (0-100), feedback, refined_version
  - Response parsed into `SmartValidation` model (line 583)
  - **Available as a separate method** — frontend can call it via API
  - **NOT auto-called during goal creation** — `create_first_goal()` at lines 595-672 does not invoke `validate_smart()` before persisting
- **Missing:** Automatic SMART validation before goal persistence. Validation exists as opt-in, not mandatory.

#### #26 — Goal Decomposition
- **Status: PARTIALLY WIRED**
- **Severity: P1**
- **Evidence:**
  - `first_goal.py:731-763` — `_create_goal_milestones()` creates a single prospective memory entry for "tomorrow's check-in"
  - No sub-goal decomposition into concrete tasks with agent assignments
  - No `goal_milestones` table for structured lifecycle tracking
  - Strategist agent has milestone concepts in strategic planning but NOT wired to first goal flow
- **Missing:** LLM-powered decomposition of goals into 3-5 sub-tasks, `goal_milestones` table, and agent assignment per sub-task.

#### #27 — Agent Activation (US-915)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - `activation.py:1-127` — `OnboardingCompletionOrchestrator.activate()`
  - Creates goals for 6 agents at lines 77-96:
    - Scout (line 175): monitor competitors
    - Analyst (line 236): research accounts, prepare briefs
    - Hunter (line 289): ICP refinement, prospect identification (conditional)
    - Operator (line 350): pipeline health analysis
    - Scribe (line 412): follow-up email drafts
    - Strategist (line 465): strategic assessment
  - Each creates a Goal via `GoalService.create_goal()` with priority: LOW, auto_execute: false
  - PersonalityCalibrator runs as background task (onboarding.py:927-931)
  - OnboardingOutcomeTracker records outcome (line 103-104)
  - Episodic memory recorded (lines 481-519)

#### #28 — Agent Execution Engine
- **Status: DEAD CODE (infrastructure exists, connection missing)**
- **Severity: P0**
- **Evidence:**
  - `agents/orchestrator.py:77-149` — `AgentOrchestrator` class exists with:
    - `spawn_agent()` at line 106 — instantiates agents
    - Parallel and sequential execution modes (ExecutionMode enum, lines 28-32)
    - Token budgeting and resource limits (lines 131-148)
  - Individual agents all have `execute()` methods (Hunter, Analyst, Scout, Scribe, Operator, Strategist)
  - **BUT: No system connects goals to agent execution**
    - Goals created with `auto_execute: false` (activation.py)
    - No background job queries for pending goals
    - No scheduler invokes `AgentOrchestrator.spawn_agent()` with goal context
    - No API endpoint triggers goal-based agent execution
  - No `GoalExecutionService`, `AgentScheduler`, or similar service exists
- **Missing:** A service that: (1) queries goals with status="draft" and source="onboarding_activation", (2) instantiates appropriate agent, (3) calls `agent.execute()`, (4) updates goal status. Without this, all agent goals from activation sit permanently idle in the database.

---

### DOWNSTREAM INTEGRATION

#### #29 — Readiness Scores (US-913)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - `readiness.py:1-240` — Full `OnboardingReadinessService`
  - 5 sub-scores with weights: corporate_memory (25%), digital_twin (25%), relationship_graph (20%), integrations (15%), goal_clarity (15%) — lines 25-26
  - `_calculate_overall()` at lines 99-105 — weighted average
  - `recalculate()` at lines 112-193 — full recalculation from source data with concurrent queries
  - Stored in `onboarding_state.readiness_scores` (lines 73-77)
  - `_get_confidence_modifier()` at lines 224-239 — maps score to qualitative language (low/moderate/high/very_high)
  - Updated throughout onboarding by every step that changes data

#### #30 — Dashboard Population
- **Status: PARTIALLY WIRED**
- **Severity: P0**
- **Evidence:**
  - `Dashboard.tsx:1-162` — Frontend renders 5 sections: ExecutiveSummary, CalendarSection, LeadsSection, SignalsSection, TasksSection (lines 132-142)
  - `useTodayBriefing()` hook fetches daily briefing (line 16)
  - `<AgentActivationStatus />` component shows agent activation progress (lines 105-108)
  - **Problem:** Briefing generation depends on agents having executed (see #28 — they don't). Without agent execution, briefing will have no competitive intel, no account research, no prospect lists. CalendarSection requires calendar integration. LeadsSection requires CRM sync or Hunter agent output.
- **Missing:** Either agent execution (so briefing has content) or a "first briefing" generator that uses onboarding data (enrichment facts, first goal, upcoming meetings) to populate the dashboard without agent output.

#### #31 — Activity Feed (US-938/US-940)
- **Status: RUNNING (infrastructure), PARTIALLY WIRED (onboarding context)**
- **Severity: P2**
- **Evidence:**
  - `api/routes/activity.py:1-94` — Full CRUD: `GET /activity` (line 21), `GET /activity/agents` (line 51), `GET /activity/{id}` (line 61), `POST /activity` (line 74)
  - `services/activity_service.py:17-196` — `record()` (line 23), `get_feed()` (line 80), `get_agent_status()` (line 150)
  - Table: `aria_activity` with user_id, agent, activity_type, title, description, reasoning, confidence
  - **Onboarding gap:** No onboarding steps call `ActivityService.record()`. The "ARIA is getting to work..." entries described in US-915 spec don't appear because activation creates goals but agents don't execute (see #28). Activity feed will be empty after onboarding.
- **Missing:** Activity records from onboarding steps (enrichment running, documents processing, email bootstrap progress) and from agent execution (which doesn't happen — see #28).

#### #32 — Action Queue (US-937)
- **Status: RUNNING (infrastructure), DEAD CODE (agent-produced actions)**
- **Severity: P1**
- **Evidence:**
  - `api/routes/action_queue.py:1-204` — Full workflow: submit, approve/reject, batch-approve, execute
  - `services/action_queue_service.py:1-351` — Risk-based routing (LOW → auto_approved, MEDIUM/HIGH/CRITICAL → pending), execution tracking
  - Table: `aria_action_queue` with statuses: PENDING, APPROVED, AUTO_APPROVED, REJECTED, EXECUTING, COMPLETED
  - **Problem:** No agent produces actions. Since agents don't execute (#28), no actions ever enter the queue. The approval workflow infrastructure is complete but has zero throughput.
- **Missing:** Agent execution that produces actions requiring approval.

#### #33 — Role Configuration (US-935)
- **Status: RUNNING (storage/UI), PARTIALLY WIRED (behavioral impact)**
- **Severity: P1**
- **Evidence:**
  - `api/routes/aria_config.py:1-100` — `GET/PUT /aria-config`, reset-personality, preview endpoints
  - `services/aria_config_service.py:1-200` — Stores config in `user_settings.preferences.aria_config`
  - Config structure: role (SALES_OPS, BD_SALES, MARKETING, EXECUTIVE_SUPPORT, CUSTOM), personality (assertiveness, verbosity, formality, proactiveness), domain_focus (therapeutic_areas, modalities, geographies), competitor_watchlist, communication preferences
  - **Behavioral impact gap:** Config is stored but no evidence that agent execution reads it to adjust behavior. Personality calibration (#9) generates tone_guidance but it's not injected into LLM prompts. Role selection doesn't visibly alter ARIA's behavior.
- **Missing:** Config consumption in agent execution, LLM prompt building, and feature prioritization.

#### #34 — Goal Lifecycle (US-936)
- **Status: PARTIALLY WIRED**
- **Severity: P1**
- **Evidence:**
  - `services/goal_service.py:1-200` — Basic CRUD: `create_goal()` (line 29), `get_goal()` (line 68), `list_goals()` (line 94), `update_goal()` (line 124), `delete_goal()` (line 162), `start_goal()` (line 177)
  - Status progression: DRAFT → ACTIVE (started_at timestamp set)
  - `tests/test_goal_lifecycle_service.py` exists (lifecycle service likely extends basic CRUD)
- **Missing:** Goal retrospective (what worked/didn't), milestone completion tracking, goal budgets, win/loss analysis. Only create-start-update exists — no completion workflow, no post-goal review.

---

### POST-ONBOARDING TIE-INS

#### #35 — Profile Update → Memory Merge (US-922)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - `memory/profile_merge.py:1-446` — Full `ProfileMergeService`
  - `process_update()` at line 85: orchestrates full pipeline
  - Steps: diff detection (lines 129-160) → re-enrichment trigger if company changed (lines 173-210) → memory merge with conflict resolution (lines 212-305) → delta generation (lines 307-337) → readiness recalculation (lines 339-362) → audit log (lines 364-397)
  - Source hierarchy enforced: user_stated (0.95) > CRM (0.85) > document (0.80) > enrichment (0.70) > inferred (0.55)
  - Old conflicting facts superseded at 0.3x confidence (line 273)

#### #36 — Ambient Gap Filling (US-925)
- **Status: PARTIALLY WIRED**
- **Severity: P2**
- **Evidence:**
  - `onboarding/ambient_gap_filler.py:1-398` — Full `AmbientGapFiller`
  - `check_and_generate()` at line 46: daily check logic
  - Threshold: 60% (line 37), spacing: 3 days between prompts (line 38), weekly limit: 2 prompts (line 39)
  - Steps: get readiness scores → find domains below 60% → check spacing → pick lowest-scoring domain → generate natural prompt → store to `ambient_prompts` table
  - Prompt retrieval at lines 290-335: `get_pending_prompt()` — marks as delivered
  - Outcome tracking at lines 337-397: engaged/dismissed/deferred
  - API routes: `GET /ambient-onboarding/ambient-prompt` and `POST /ambient-onboarding/ambient-prompt/{id}/outcome`
- **Missing:** No visible background scheduler (cron, Celery, APScheduler) to run `check_and_generate()` daily. Service is callable but nothing invokes it automatically. Must be triggered externally.

#### #37 — Onboarding Procedural Memory (US-924)
- **Status: RUNNING**
- **Severity: —**
- **Evidence:**
  - `onboarding/outcome_tracker.py:1-432` — Full `OnboardingOutcomeTracker`
  - `record_outcome()` at line 45: records at onboarding completion
  - Metrics: readiness_at_completion, time_to_complete_minutes, steps_completed, steps_skipped, company_type, first_goal_category, documents_uploaded, email_connected, crm_connected
  - Inserts to `onboarding_outcomes` table (lines 158-175)
  - `get_system_insights()` at lines 188-321: cross-user pattern aggregation (min 3 samples), groups by company_type, correlates document uploads with readiness
  - `consolidate_to_procedural()` at lines 323-405: quarterly conversion to semantic truths in `procedural_insights` table
  - Called during activation at `activation.py:103-104`

---

### P0 Gaps (Blocks Beta)

| # | Item | What's Broken | Fix |
|---|------|--------------|-----|
| 28 | Agent Execution Engine | Goals created by activation sit permanently idle — no service picks them up and runs agents | Implement `GoalExecutionService` that queries pending goals, instantiates agents via `AgentOrchestrator`, executes, and updates goal status |
| 30 | Dashboard Population | First visit after onboarding shows empty briefing — agents haven't run, no content generated | Either fix #28, or implement "first briefing" from onboarding data (enrichment facts, first goal, upcoming meetings) |

### P1 Gaps (Degraded Intelligence)

| # | Item | What's Broken | Fix |
|---|------|--------------|-----|
| 3 | Causal Graph Seeding | Hypotheses stored in Supabase only, not Neo4j/Graphiti — no graph traversal | Add `GraphitiClient.add_entity()` or use `add_episode()` for hypothesis edges |
| 7 | LinkedIn Background Research | Entirely unimplemented — LinkedIn URL collected but never researched | Build `LinkedInResearchService` using Exa API triangulation |
| 9 | Personality Calibration | Calibration generated but never consumed by any LLM prompt builder | Inject `tone_guidance` into Scribe/draft service system prompts |
| 18 | Graphiti Entity Graph | `memory_constructor.py:245` calls non-existent `add_entity()` — silently fails | Implement `add_entity()` on GraphitiClient or refactor to use episode-based entity creation |
| 19 | OODA Adaptive Controller | Questions generated but frontend never displays them | Wire `get_injected_questions()` into onboarding step UI |
| 20 | Memory Delta (Enrichment) | No delta shown after enrichment — trust-building moment missed | Call `MemoryDeltaPresenter.generate_delta()` after enrichment, store for frontend |
| 21 | Skills Pre-Configuration | `SkillRecommendationEngine` never called during activation | Add `skill_recommender.pre_install()` call to activation flow |
| 26 | Goal Decomposition | Goals are monolithic — no sub-tasks or milestone agent assignments | Add LLM decomposition in `create_first_goal()` creating `goal_milestones` |
| 32 | Action Queue (Agent Actions) | Infrastructure complete but zero throughput — agents don't produce actions | Dependent on #28 (agent execution) |
| 33 | Role Config (Behavioral) | Config stored but doesn't influence ARIA's behavior or agent decisions | Inject config into agent execution context and LLM prompts |
| 34 | Goal Lifecycle | No retrospective, milestone tracking, or completion workflow | Extend `goal_service.py` with milestone completion and review endpoints |

### P2 Gaps (Nice to Have)

| # | Item | What's Broken | Fix |
|---|------|--------------|-----|
| 5 | Cross-User Data Flow | `corporate_facts` vs `memory_semantic` table mismatch | Add ETL or unify table references |
| 8 | Writing Fingerprint Usage | 20 fields defined, only 5 consumed downstream | Expand personality calibrator to use all fields |
| 12 | OCR for Scanned PDFs | Explicitly unimplemented — returns empty string | Add pytesseract + Tesseract to pipeline |
| 15 | Procedural Memory | Infrastructure exists, zero onboarding integration | Add procedural memory creation for workflow patterns |
| 17 | Working Memory | Full service built, not used by OODA controller | Integrate WorkingMemory into adaptive_controller.py |
| 25 | SMART Validation Auto | Exists as opt-in method, not mandatory before persistence | Auto-call during `create_first_goal()` |
| 31 | Activity Feed (Onboarding) | No onboarding steps record activities | Add `ActivityService.record()` calls to enrichment, docs, email |
| 36 | Ambient Gap Filler Scheduler | Service exists, no automatic daily trigger | Add APScheduler or Celery beat task |

---

### Architecture Observations

1. **The Intelligence Gap is at the Action Layer.** Data collection (enrichment, email bootstrap, document ingestion) works well. Data storage (semantic memory, episodic memory, prospective memory) works well. But the conversion of stored intelligence into *action* is broken: agents don't execute, skills aren't pre-installed, personality calibration isn't consumed, role config doesn't influence behavior.

2. **Two Table Problem.** Enrichment writes to `memory_semantic`. Cross-user reads from `corporate_facts`. These are different tables with no ETL between them. This means User #2 at a company may not see User #1's enrichment discoveries.

3. **Silent Failures.** `memory_constructor.py:245` calls `graphiti.add_entity()` which doesn't exist — caught by try/except, logged as warning, execution continues. Entity graphs silently never get built. This pattern of "infrastructure exists, integration silently fails" appears in multiple places.

4. **Personality Calibration Island.** The calibration pipeline works end-to-end: fingerprint → calibration → tone_guidance. But the tone_guidance string is never injected into any LLM prompt. It's generated, stored, and forgotten. Every ARIA response uses the same generic tone regardless of calibration.

5. **OODA Without Output.** The OODA adaptive controller runs, generates contextual questions, stores them in onboarding_state.metadata — but the frontend never retrieves or displays them. The adaptation intelligence exists server-side but has no visible effect.

---

**Part 2 audit completed:** 2026-02-09
**Methodology:** 5 parallel code exploration agents traced all 37 items from Phase 9 spec (US-901 through US-943) through frontend components, API routes, backend services, database writes, and background job triggers. Each item traced from trigger to storage to downstream consumption.
