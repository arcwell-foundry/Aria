# ARIA AUDIT & EXECUTION MASTER PLAN
## Multi-Conversation Controller Document

**Date:** February 28, 2026
**Purpose:** Serve as a "master controller" across multiple Claude conversations to systematically audit ARIA's current state and bring all capabilities to 100% operational status.
**Author:** Claude (for Dhruv Patwardhan / LuminOne)

---

## THE PROBLEM & THE SOLUTION

**Problem:** ARIA has ~169,000 lines of code, 125 database tables, 50+ design documents, and dozens of capability areas. No single Claude conversation can hold all of this in context. Previous attempts to do a comprehensive audit in one conversation caused context compacting and errors.

**Solution:** Break the work into **12 focused conversation sessions**, each tackling a specific domain. This document serves as the persistent reference across all sessions. Each session reads only the project files relevant to its domain, audits the current state, and produces actionable fixes.

---

## HOW TO USE THIS DOCUMENT

1. **Start each new conversation** by uploading/referencing this document
2. **Copy-paste the session prompt** from the relevant section below
3. **After each session**, update the status tracker in this doc
4. **Sessions can run in parallel** where dependencies allow (see dependency map)

---

## CURRENT BASELINE (February 28, 2026)

### Database Snapshot
- **125 tables** in Supabase (all with RLS ✅)
- **Tables with meaningful data:** messages (136), email_scan_log (288), memory_semantic (479), llm_usage (1,813), episodic_memories (53), semantic_facts (60), skills_index (64), notifications (56), delegation_traces (48), prospective_memories (44), goal_milestones (42), agent_executions (35), goal_updates (56), conversations (10), goals (7)
- **Tables with 0 rows (features built but never exercised):** leads, market_signals, meeting_briefs, battle_cards, calendar_events, discovered_leads, lead_events, monitored_entities, strategic_plans, health_score_history, and ~60 others

### Previous Audit Summary (Feb 8-12)
- **Phase completion:** 97.3% of 112 user stories implemented (per AUDIT_COMPLETENESS)
- **Beta readiness:** 78% (per AUDIT_USER_FLOWS)
- **Critical findings:** Knowledge graph disconnected from meeting prep, agents implemented but some not called at runtime, email draft generation broken, daily briefing scheduler missing, activity logging gaps
- **Known broken:** Email draft generation (JSON parsing errors, hallucinations, no reply-check)

### Key Architecture Facts
- **Backend:** Python/FastAPI, 239 files, ~105K lines
- **Frontend:** React/TypeScript, 196+ files, ~24K lines
- **6 Agents:** Hunter, Analyst, Strategist, Scribe, Operator, Scout
- **6 Memory Types:** Working, Episodic, Semantic, Procedural, Prospective, Lead
- **Skills Engine:** 64 skills registered in skills_index, orchestrator is stub
- **Integrations:** Composio OAuth (Gmail, Calendar, Salesforce, HubSpot, Slack), Tavus (avatar), Neo4j/Graphiti (knowledge graph), 15 scientific APIs

---

## SESSION DEPENDENCY MAP

```
Session 1: Database & Infrastructure Health ──┐
                                               ├──► Session 3: Agent System
Session 2: Memory System ─────────────────────┤
                                               ├──► Session 4: Chat & Conversation
                                               │
Session 5: Email Intelligence ────────────────┤
                                               ├──► Session 8: Daily Briefings & Signals
Session 6: Skills & Orchestration ────────────┤
                                               ├──► Session 11: Advanced Features
Session 7: Onboarding ───────────────────────┘
                                               
Session 9: Frontend & UX ─────── (independent)
Session 10: Integrations ─────── (independent)
Session 12: E2E Testing & Deploy (LAST - depends on all others)
```

**Parallel groups:**
- Group A: Sessions 1, 2, 9, 10 (no dependencies on each other)
- Group B: Sessions 3, 4, 5, 6, 7 (depend on Group A)
- Group C: Sessions 8, 11 (depend on Group B)
- Group D: Session 12 (depends on everything)

---

## SESSION DETAILS

---

### SESSION 1: Database & Infrastructure Health
**Estimated time:** 1 conversation
**Priority:** P0 (blocks everything)
**Key project files to reference:** AUDIT_DATABASE.md, AUDIT_COMPREHENSIVE_FEB11V4.md

#### What "100% Operational" Means:
- [ ] All 125 tables have correct schemas matching latest code expectations
- [ ] No duplicate table conflicts (aria_actions issue from Feb 8)
- [ ] All RLS policies are correct (onboarding_outcomes bug fixed)
- [ ] Missing indexes added (lead_memory_events.created_at)
- [ ] All foreign key relationships valid
- [ ] Migration sequence is clean with no conflicts
- [ ] Supabase Edge Functions deployed and healthy (if any)

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 1: Database & Infrastructure Health.

Please read the project files AUDIT_DATABASE.md and AUDIT_COMPREHENSIVE_FEB11V4.md for context. Then:

1. Connect to Supabase project asqcmailhanhmyoaujje
2. List all migrations and verify they're applied cleanly
3. Check for the known issues: aria_actions duplicate table conflict, onboarding_outcomes RLS bug, missing lead_memory_events index
4. Verify all tables referenced by backend code actually exist
5. Check for any orphaned tables or missing foreign keys
6. Fix all issues found via migrations
7. Run the Supabase security advisors check
8. Produce a summary of what was fixed and what the current clean state is

Key context: 125 tables exist, many with 0 rows. The aria_actions conflict and onboarding_outcomes RLS bug were identified Feb 8 but may not have been fixed.
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 2: Memory System End-to-End
**Estimated time:** 1-2 conversations
**Priority:** P0 (core differentiator)
**Key project files:** PHASE_2_MEMORY.md, PHASE_5_LEAD_MEMORY.md, AUDIT_COMPREHENSIVE_FEB11V4.md (Section 6)

#### What "100% Operational" Means:
- [ ] **Working Memory:** Session state persists across messages, transfers on modality switch
- [ ] **Episodic Memory:** Conversation episodes archived correctly, retrievable by context
- [ ] **Semantic Memory:** Facts extracted from conversations, stored with embeddings, searchable via pgvector
- [ ] **Procedural Memory:** Workflow patterns learned and retrievable
- [ ] **Prospective Memory:** Reminders and follow-ups trigger at correct times
- [ ] **Lead Memory:** Relationship history tracked, health scores computed, stakeholder mapping works
- [ ] **Memory priming** works at every interaction point (not just conversation start)
- [ ] **Graphiti/Neo4j** integration operational for knowledge graph queries
- [ ] **Salience decay** job running, old memories properly weighted
- [ ] **Digital Twin** profile built from user's writing samples and updated over time

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 2: Memory System End-to-End.

Please read PHASE_2_MEMORY.md, PHASE_5_LEAD_MEMORY.md, and the memory sections of AUDIT_COMPREHENSIVE_FEB11V4.md. Then:

1. Connect to Supabase (asqcmailhanhmyoaujje) and check the state of all memory tables (episodic_memories, memory_semantic, semantic_facts, procedural_memories, prospective_memories, lead_memories, digital_twin_profiles, etc.)
2. Trace the memory pipeline in the codebase: when a user sends a chat message, which memory types are read and written?
3. Verify Graphiti/Neo4j is connected and operational
4. Check if salience decay job is scheduled and running
5. Test: Can ARIA actually recall information from a previous conversation?
6. Identify every gap between designed memory behavior (per Phase 2/5 specs) and actual runtime behavior
7. Produce specific fixes for each gap, prioritized by impact

Key tables to check: episodic_memories (53 rows), memory_semantic (479), semantic_facts (60), procedural_memories (5), prospective_memories (44), digital_twin_profiles (1)
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 3: Agent System - From Implemented to Operational
**Estimated time:** 1-2 conversations
**Priority:** P0 (agents are ARIA's hands)
**Key project files:** PHASE_3_AGENTS.md, AUDIT_COMPLETENESS.md (Section 3), AUDIT_COMPREHENSIVE_FEB11V4.md (Section 5)

#### What "100% Operational" Means:
- [ ] All 6 agents callable via GoalExecutionService and produce real results (not mocks)
- [ ] **Hunter:** Discovers real leads using Exa API, enriches with real data
- [ ] **Analyst:** Queries PubMed, ClinicalTrials.gov, OpenFDA, ChEMBL successfully
- [ ] **Strategist:** Generates real strategies using LLM + account context
- [ ] **Scribe:** Drafts emails matching user's Digital Twin style
- [ ] **Operator:** Reads/writes to real CRM and Calendar via Composio
- [ ] **Scout:** Monitors real news, detects real signals via Exa API
- [ ] Agent orchestrator handles parallel execution correctly
- [ ] Agent results flow back to chat and are displayed as rich content
- [ ] 12 agent capabilities (capabilities/ folder) are wired and functional
- [ ] Agent execution logs to agent_executions table with proper audit trail

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 3: Agent System.

Please read PHASE_3_AGENTS.md and the agent sections of AUDIT_COMPREHENSIVE_FEB11V4.md. Then:

1. For each of the 6 agents (Hunter, Analyst, Strategist, Scribe, Operator, Scout):
   a. Read the agent source code
   b. Trace how it gets triggered (GoalExecutionService → agent.execute_with_skills)
   c. Test if it would produce real results or mock data
   d. Check what external APIs it actually calls
   e. Verify results flow back to the user via WebSocket/chat
2. Check the 12 capabilities in agents/capabilities/ - which are wired vs stubs?
3. Verify the agent_executions table (35 rows) - are these real executions or test data?
4. Identify what's needed to make each agent produce production-quality results
5. Prioritize fixes by which agents matter most for the Rob Douglas demo

Key context: Previous audit found "agents implemented but not called at runtime" for some. agent_executions has 35 rows. Composio OAuth exists but may not be wired to Operator agent.
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 4: Chat & Conversation Pipeline
**Estimated time:** 1 conversation
**Priority:** P0 (primary user interface)
**Key project files:** ARIA_IDD_v3.md (Sections 3-4), AUDIT_USER_FLOWS.md (Flow 2), AUDIT_COMPREHENSIVE_FEB11V4.md (Section 7)

#### What "100% Operational" Means:
- [ ] User sends message → ARIA responds with context-aware reply
- [ ] Memory priming injects relevant context at every interaction
- [ ] Digital Twin personality reflected in ARIA's responses
- [ ] Entity extraction happens on every message (feeds Lead Memory)
- [ ] Rich content cards render (GoalPlanCard, SignalCard, etc.)
- [ ] Context-adaptive suggestions appear after each response
- [ ] Tool calling loop works (ARIA can use tools mid-conversation)
- [ ] Conversation persists across page navigation
- [ ] WebSocket streaming works for real-time responses
- [ ] OODA loop cycles correctly (Observe → Orient → Decide → Act)

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 4: Chat & Conversation Pipeline.

Please read ARIA_IDD_v3.md (Sections 3-4) and AUDIT_USER_FLOWS.md (Flow 2). Then:

1. Trace the complete message flow: frontend sends message → backend processes → response streams back
2. Check: Is ConversationPrimingService called on every message? What memory does it inject?
3. Check: Is Digital Twin personality injected into the system prompt?
4. Check: Does entity extraction happen on user messages to feed Lead Memory?
5. Check: Do rich content cards (GoalPlanCard, etc.) render correctly in the frontend?
6. Check: Are context-adaptive suggestions generated after each response?
7. Check: Does the OODA loop (ooda.py) actually cycle, or is it theoretical?
8. Verify conversations table (10 rows) and messages table (136 rows) for data integrity
9. Fix all gaps found, prioritized by user impact

Key context: Previous audit said "Chat with ARIA works" but "Digital Twin injection missing" and "Lead Memory auto-updates missing." conversations=10 rows, messages=136 rows.
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 5: Email Intelligence Pipeline (THE BROKEN ONE)
**Estimated time:** 2 conversations (diagnostic + fix)
**Priority:** P0 (known broken, demo-critical)
**Key project files:** 04_email_drafting.md, ARIA_Email_Intelligence_Execution_Plan.md, AUDIT_USER_FLOWS.md (Flow 5)

#### What "100% Operational" Means:
- [ ] Email scanning: Reads inbox via Gmail/Outlook OAuth, categorizes emails correctly
- [ ] Email filtering: Identifies which emails need replies, which are FYI, which to skip
- [ ] Reply check: Before drafting, verifies email hasn't already been replied to
- [ ] Draft generation: Produces context-aware, style-matched drafts (NO hallucinations, NO raw JSON)
- [ ] Draft saving: Saves drafts to user's email client (Gmail/Outlook Drafts folder)
- [ ] ARIA notes: Each draft includes transparent reasoning ("Why I drafted this")
- [ ] Activity logging: All email actions logged to aria_activity
- [ ] Deferred drafts: Handles emails that need more context before drafting
- [ ] Morning briefing integration: Email summary included in daily briefing

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 5: Email Intelligence Pipeline.

⚠️ THIS IS THE KNOWN BROKEN AREA. The email pipeline scans and filters correctly, but draft generation is broken with JSON parsing errors, hallucinations, and failure to check if emails were already replied to.

APPROACH: Diagnostic first, then fix. Do NOT add new features.

Please read 04_email_drafting.md and ARIA_Email_Intelligence_Execution_Plan.md. Then:

1. DIAGNOSTIC PHASE:
   a. Trace the entire email pipeline end-to-end with print statements
   b. Start from email scan → filtering → draft generation → output
   c. Print intermediate values at every step
   d. Identify EXACTLY where the data flow breaks (JSON parsing? LLM prompt? Output formatting?)
   
2. Check Supabase tables:
   - email_scan_log (288 rows) - are these real scans?
   - email_drafts (2 rows) - what state are they in?
   - deferred_email_drafts (8 rows) - why deferred?
   - email_processing_runs (18 rows) - success/failure rates?
   - draft_context (17 rows) - does it have real context?
   
3. FIX PHASE (after diagnostic):
   a. Fix the reply-check to verify if emails were already replied to
   b. Fix JSON parsing in draft generation
   c. Fix hallucination in draft content (ensure real email context is used)
   d. Add activity logging for all email actions
   
4. Verify with a test: trigger email scan → confirm drafts generate correctly

Key context: Rob Douglas email test revealed ARIA drafted a hallucinated reply with raw JSON despite completing onboarding. 16+ features coded but untested at runtime.
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 6: Skills & Orchestration Engine
**Estimated time:** 1-2 conversations
**Priority:** P1 (extends agent capabilities)
**Key project files:** ARIA_SKILLS_INTEGRATION_ARCHITECTURE.md, ARIA_Skills_Implementation_Plan.docx, ARIA_Skills_Master_Execution_Plan.docx

#### What "100% Operational" Means:
- [ ] SkillOrchestrator is functional (not just stubs)
- [ ] Skills can be discovered, selected, and executed at runtime
- [ ] 64 registered skills in skills_index are actually callable
- [ ] Skill trust system works (trust levels affect execution permissions)
- [ ] Skill audit logging records all executions
- [ ] SkillAwareAgent base class properly integrates skills into agent OODA ACT phase
- [ ] Custom skills can be registered and executed
- [ ] Skill working memory persists between related executions

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 6: Skills & Orchestration Engine.

Please read ARIA_SKILLS_INTEGRATION_ARCHITECTURE.md and the Skills Master Execution Plan. Then:

1. Check skills_index table (64 rows) - what skills are registered? Are they real or seed data?
2. Read SkillOrchestrator code - is it functional or stubs?
3. Check SkillAwareAgent - is it the base class all agents extend? Does skill discovery/execution work?
4. Trace: When an agent needs a skill, how does it discover → select → execute → return results?
5. Check skill_audit_log, skill_trust_history, skill_working_memory tables (all 0 rows) - why empty?
6. Identify minimum viable set of skills needed for demo/beta
7. Fix orchestrator and wiring to make the top-priority skills operational

Key context: Previous audit said "SkillOrchestrator is STUBS" and "SkillAwareAgent is DESIGNED but not in agent classes." skills_index has 64 rows but all execution-related tables are empty.
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 7: Onboarding Flow
**Estimated time:** 1 conversation
**Priority:** P0 (first impression)
**Key project files:** PHASE_9_PRODUCT_COMPLETENESS.md (Phase 9A), AUDIT_ONBOARDING_E2E.md, AUDIT_ONBOARDING_GAPS.md

#### What "100% Operational" Means:
- [ ] 8-step onboarding flow works end-to-end
- [ ] Company discovery enriches via Exa/web and seeds all memory types
- [ ] Document upload processes and extracts intelligence
- [ ] User profile captures role, responsibilities, communication style
- [ ] Writing samples analyzed to build Digital Twin
- [ ] Email integration connects via OAuth and bootstraps email intelligence
- [ ] Integration wizard connects CRM, Calendar, etc.
- [ ] First Goal setup creates a real, executable goal
- [ ] First Conversation Generator (US-914) produces an intelligence-proving message
- [ ] Post-auth routing works (new user → onboarding, returning → dashboard)
- [ ] Readiness score calculated and displayed

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 7: Onboarding Flow.

Please read PHASE_9_PRODUCT_COMPLETENESS.md (Phase 9A) and AUDIT_ONBOARDING_E2E.md. Then:

1. Check onboarding_state table (1 row) and onboarding_outcomes (1 row) - what's the state?
2. Trace the 8-step flow: company_discovery → document_upload → user_profile → writing_samples → email_integration → integration_wizard → first_goal → activation
3. For each step: Does the backend handler exist? Does it actually process data? Does it feed memory?
4. Check US-914 (First Conversation Generator) - previous audit said "MISSING." Does first_conversation.py exist and work?
5. Test post-auth routing: Does /onboarding/routing return correct destination?
6. Verify OnboardingPage.tsx renders the conversational flow (not forms)
7. Fix critical gaps, especially US-914 which is the "$200K product first impression"

Key context: Previous audit found US-914 missing, US-911 partial. Onboarding exists with 1 completed state. The first conversation is make-or-break for design partner impressions.
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 8: Daily Briefings & Market Signals
**Estimated time:** 1 conversation
**Priority:** P1 (daily value delivery)
**Key project files:** 05_daily_intel_briefings.md, 10_market_signal_monitoring.md, AUDIT_USER_FLOWS.md (Flow 4)

#### What "100% Operational" Means:
- [ ] Daily briefing scheduler runs at 6:00 AM (or configured time)
- [ ] Briefing includes: email summary, calendar preview, market signals, action items
- [ ] Signal detection pipeline populates market_signals table
- [ ] Monitored entities auto-populated from user's leads/accounts
- [ ] Scout agent runs signal detection periodically
- [ ] Briefing rendered in DialogueMode (avatar reads morning brief)
- [ ] Briefing also available as text in dashboard
- [ ] Signal relevance scoring works
- [ ] Duplicate signal detection works

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 8: Daily Briefings & Market Signals.

Please read 05_daily_intel_briefings.md and 10_market_signal_monitoring.md. Then:

1. Check daily_briefings table (10 rows) - are these real briefings with real content?
2. Check market_signals table (0 rows) and monitored_entities (0 rows) - why empty?
3. Find the briefing scheduler job - is it running? Is it scheduled?
4. Trace the briefing generation: What data sources feed into it?
5. Check if Scout agent's signal detection is wired to a periodic job
6. Check if briefing integrates with email summary and calendar preview
7. Fix the scheduler to run daily, fix signal population pipeline
8. Verify briefing renders correctly in the frontend

Key context: Previous audit found "Daily Scheduler - High priority gap, no automatic morning briefings" and "Signal Population Pipeline - no job populating market_signals table."
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 9: Frontend & UX Audit
**Estimated time:** 1 conversation
**Priority:** P1 (polish for demo)
**Key project files:** ARIA_IDD_v3.md, ARIA_Frontend_Architecture.md, ARIA_DESIGN_SYSTEM.md, AUDIT_DESIGN_SYSTEM.md

#### What "100% Operational" Means:
- [ ] All IDD v3 pages render correctly with dark/light theme
- [ ] Sidebar navigation works with proper active states
- [ ] IntelPanel shows context-adaptive modules based on current page
- [ ] Pipeline page shows leads with health bars and filtering
- [ ] Intelligence page shows battle cards, research briefs
- [ ] Communications page shows email drafts with editing
- [ ] Actions page shows goals, milestones, delegation traces
- [ ] Settings page has all sub-sections (Profile, Integrations, Billing)
- [ ] DialogueMode (avatar) works with proper transcript display
- [ ] Command palette works for quick actions
- [ ] Empty states direct users to ARIA conversation (not forms)
- [ ] No deprecated code imported or rendered

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 9: Frontend & UX Audit.

Please read ARIA_IDD_v3.md and ARIA_DESIGN_SYSTEM.md. Then:

1. Check all page routes in the frontend - do they all resolve to real components?
2. Verify IDD v3 compliance: no CRUD/SaaS patterns, ARIA-curated content, filter chips not forms
3. Check IntelPanel modules - are all 14-15 context-adaptive modules implemented?
4. Verify dark/light theme works across all pages
5. Check empty states - do they direct to ARIA conversation?
6. Verify rich content cards render: GoalPlanCard, SignalCard, AlertCard, ExecutionPlanCard
7. Check for any console errors or broken imports
8. Test responsive behavior if applicable
9. Identify UX polish items for demo readiness

Key context: Previous audit confirmed "No _deprecated/ directory, fully cleaned" and "All pages new IDD v3 architecture." Frontend is ~24K lines across 196 files.
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 10: Integrations & External Services
**Estimated time:** 1 conversation
**Priority:** P1 (required for real data)
**Key project files:** AUDIT_COMPREHENSIVE_FEB11V4.md (Section 10), ARIA_EXA_INTEGRATION_ARCHITECTURE.md

#### What "100% Operational" Means:
- [ ] **Anthropic Claude API:** LLMClient operational with circuit breaker, correct model
- [ ] **Neo4j/Graphiti:** Connected, knowledge graph queries work, embeddings configured
- [ ] **Tavus (Avatar):** Persona configured, WebRTC room creation works
- [ ] **Composio OAuth:** All 6 integrations connectable (Google Calendar, Gmail, Outlook, Salesforce, HubSpot, Slack)
- [ ] **Exa API:** Web search, company enrichment, contact finding all functional
- [ ] **Scientific APIs:** PubMed, ClinicalTrials.gov, OpenFDA, ChEMBL, UniProt all responding
- [ ] **Resend (Email):** Transactional emails sending (follow-ups, notifications)
- [ ] OAuth token refresh working for all connected services
- [ ] Error handling and fallbacks for all external services

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 10: Integrations & External Services.

Please read ARIA_EXA_INTEGRATION_ARCHITECTURE.md and Section 10 of AUDIT_COMPREHENSIVE_FEB11V4.md. Then:

1. Check user_integrations table (1 row) - what's connected?
2. Verify each integration:
   a. Claude API - is the LLMClient configured with correct model and API key?
   b. Neo4j/Graphiti - can we connect and run a test query?
   c. Tavus - is the persona configured? Can we create a room?
   d. Composio - are OAuth flows working? Token refresh?
   e. Exa API - test a web search query
   f. Scientific APIs - test each endpoint
   g. Resend - verify email sending works
3. Check circuit breaker and rate limiter configurations
4. Check for any hardcoded API keys or missing env vars
5. Fix any broken connections
6. Document what environment variables are required for deployment

Key context: user_integrations has 1 row (down from 2 in the Feb 9 audit). Composio OAuth foundation "works" per previous audit.
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 11: Advanced Features (Battle Cards, Meeting Prep, Calendar)
**Estimated time:** 1-2 conversations
**Priority:** P2 (demo differentiators)
**Key project files:** 03_pre_meeting_research.md, 06_competitive_battle_cards.md, 07_calendar_management.md, 08_video_consultations.md

#### What "100% Operational" Means:
- [ ] **Meeting Prep:** Auto-generates briefs for upcoming meetings using calendar + CRM + knowledge graph
- [ ] **Battle Cards:** Auto-generated and auto-updated competitive intelligence cards
- [ ] **Calendar Management:** ARIA reads calendar, suggests optimal meeting times, manages scheduling
- [ ] **Video Consultations:** Avatar-based strategy sessions with transcript and follow-up
- [ ] **Pre-meeting research:** Attendee profiles, company intel, relationship history compiled
- [ ] All features accessible from the relevant frontend pages

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 11: Advanced Features.

Please read 03_pre_meeting_research.md, 06_competitive_battle_cards.md, 07_calendar_management.md. Then:

1. Check tables: meeting_briefs (0), battle_cards (0), calendar_events (0), attendee_profiles (0) - all empty
2. For each feature area, trace: Does the backend service exist? Is it wired to an API route? Does the frontend page consume it?
3. Meeting Prep: Is the meeting_brief_generator job running? Does it query Graphiti for relationship history?
4. Battle Cards: Is there a generation pipeline? Does Scout populate competitive intelligence?
5. Calendar: Does Operator agent read/write calendar via Composio?
6. Video: Does Tavus integration work end-to-end?
7. For each feature, determine: minimum viable implementation for demo
8. Fix critical wiring gaps

Key context: All these tables are empty (0 rows), suggesting these features are implemented in code but never executed at runtime. The knowledge graph integration being disconnected (per Feb audit) is a major gap for meeting prep.
```

#### Status: ⬜ Not Started
#### Notes:
---

### SESSION 12: End-to-End Testing & Deployment Readiness
**Estimated time:** 1 conversation (LAST SESSION)
**Priority:** P0 (final verification)
**Key project files:** DEMO_READINESS_REPORT.md, CLAUDE.md

#### What "100% Operational" Means:
- [ ] New user can sign up, complete onboarding, and see intelligence-proving first conversation
- [ ] User can chat with ARIA and get context-aware, memory-informed responses
- [ ] User can ask ARIA to find leads, research companies, draft emails
- [ ] Daily briefing generates automatically with real content
- [ ] Email drafts are accurate, context-aware, and saveable to email client
- [ ] Meeting prep briefs generate for upcoming calendar events
- [ ] All frontend pages show real data, not empty states
- [ ] No runtime errors in backend logs
- [ ] No console errors in frontend
- [ ] Performance acceptable (< 3s for chat responses, < 10s for agent tasks)
- [ ] Security: all env vars set, no hardcoded secrets, RLS enforced

#### Session Prompt:
```
I'm working through a multi-session audit of ARIA. This is SESSION 12: End-to-End Testing.

This is the FINAL session. All previous sessions should have fixed their respective domains.

Please read DEMO_READINESS_REPORT.md and CLAUDE.md. Then:

1. Run a complete user journey test:
   a. Check post-auth routing for a new user
   b. Verify onboarding flow progression
   c. Send a test message to ARIA and verify response quality
   d. Trigger a goal execution and verify agent produces real results
   e. Check that memory persists between messages
   f. Verify email pipeline generates real drafts
   g. Check daily briefing content
   h. Navigate all frontend pages and verify real data renders

2. Check Supabase logs for any errors
3. Check backend logs for any runtime exceptions
4. Run the Supabase security advisor
5. Verify all environment variables are set
6. Produce a final DEMO_READINESS scorecard

Key context: This should be the culmination of all 11 previous sessions. If something is still broken, note it clearly with severity.
```

#### Status: ⬜ Not Started
#### Notes:
---

## STATUS TRACKER

| Session | Domain | Priority | Status | Date Started | Date Completed | Blockers |
|---------|--------|----------|--------|--------------|----------------|----------|
| 1 | Database & Infrastructure | P0 | ⬜ Not Started | | | |
| 2 | Memory System | P0 | ⬜ Not Started | | | |
| 3 | Agent System | P0 | ⬜ Not Started | | | |
| 4 | Chat & Conversation | P0 | ⬜ Not Started | | | |
| 5 | Email Intelligence | P0 | ⬜ Not Started | | | |
| 6 | Skills & Orchestration | P1 | ⬜ Not Started | | | |
| 7 | Onboarding | P0 | ⬜ Not Started | | | |
| 8 | Daily Briefings & Signals | P1 | ⬜ Not Started | | | |
| 9 | Frontend & UX | P1 | ⬜ Not Started | | | |
| 10 | Integrations | P1 | ⬜ Not Started | | | |
| 11 | Advanced Features | P2 | ⬜ Not Started | | | |
| 12 | E2E Testing | P0 | ⬜ Not Started | | | |

---

## QUICK REFERENCE: Known Issues From Previous Audits

### P0 Blockers
1. **Email draft generation broken** - JSON parsing, hallucinations, no reply-check
2. **Knowledge graph disconnected** from meeting prep (Graphiti queries not called)
3. **Daily briefing scheduler not running** - no automatic morning briefings
4. **US-914 (First Conversation Generator)** - reported as MISSING in one audit, EXISTS in another - needs verification
5. **Signal population pipeline missing** - market_signals table perpetually empty

### P1 Degradations
1. **Digital Twin personality not injected** into chat responses
2. **Lead Memory auto-updates not happening** during conversations
3. **Activity feed logging gaps** - many actions not logged
4. **Some agents never called at runtime** despite being implemented
5. **Composio wiring to Operator agent incomplete**

### P2 Polish
1. **Battle cards, meeting briefs, calendar events** - all 0 rows (never populated)
2. **Monitored entities** - empty (should auto-populate from leads)
3. **Style recalibration** - never runs
4. **Prediction system** - tables exist, never used

---

## EXECUTION RECOMMENDATIONS

### If you have 1 day:
Focus on Sessions 1 (DB health), 5 (email fix), 7 (onboarding fix) — these are the Rob Douglas demo-critical paths.

### If you have 3 days:
Add Sessions 2 (memory), 3 (agents), 4 (chat) — these make ARIA feel intelligent.

### If you have 1 week:
Complete all 12 sessions. Group A (1,2,9,10) on Day 1-2, Group B (3,4,5,6,7) on Day 3-5, Group C+D (8,11,12) on Day 6-7.

### If using Claude Code parallel sessions:
- Session A1: Database (Session 1) + Integrations (Session 10)
- Session A2: Memory (Session 2) + Frontend (Session 9)
- Session B1: Agents (Session 3) + Skills (Session 6)
- Session B2: Email (Session 5) + Chat (Session 4)
- Session B3: Onboarding (Session 7)
- Session C1: Briefings (Session 8) + Advanced (Session 11)
- Session D1: E2E Testing (Session 12)

---

*Document Version: 1.0*
*Created: February 28, 2026*
*Last Updated: February 28, 2026*
