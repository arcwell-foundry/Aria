# Phase 9: Intelligence Initialization & Product Completeness
## ARIA PRD — Implementation Phase 9

**Prerequisites:** Phase 5B Complete (US-532)  
**Estimated Stories:** 43  
**Focus:** Onboarding as Intelligence Initialization, Profile Management, SaaS Infrastructure, ARIA Product Experience  
**Philosophy:** Onboarding is ARIA's first cognitive act, not a form the user fills out. Every data point flows into every system.

---

## Overview

Phase 9 addresses the comprehensive gap analysis that revealed ARIA's intelligence engine (Phases 1-8) lacks the user experience shell needed for a complete $200K/year product. This phase implements:

- **9A: Intelligence Initialization** — Adaptive onboarding that seeds all memory systems, activates agents, and demonstrates intelligence from moment one
- **9B: Profile Management & Continuous Learning** — Ongoing profile updates, retroactive enrichment, and self-improving onboarding
- **9C: SaaS Infrastructure** — Billing, team admin, compliance, error handling, security hardening — the "plumbing" every enterprise product needs
- **9D: ARIA Product Experience** — Role configuration, goal lifecycle, autonomous actions, activity feed, reporting — how users direct and benefit from ARIA

**Completion Criteria:** A new user can sign up, complete onboarding, and within 24 hours experience ARIA as an autonomous, intelligent colleague who already knows their company, their style, and their priorities — all within a production-grade SaaS shell.

---

## The Intelligence Initialization Test

Every onboarding story must pass:
> "Does this step make ARIA measurably smarter about this user and their company? Does the data flow into at least 3 downstream systems?"

If a step only collects data and stores it in one place, it's a form — not intelligence initialization.

---

## Integration Checklist Pattern

Every story in Phase 9A includes an **Integration Checklist** in its acceptance criteria. This ensures data flows into all relevant systems:

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

---

# PHASE 9A: INTELLIGENCE INITIALIZATION (20 Stories)

**Priority:** Must-have before first paying customer  
**Estimated Effort:** 80-100 hours  
**Dependencies:** Phase 2 (Memory), Phase 3 (Agents/OODA), Phase 5B (Skills)

---

### US-901: Onboarding Orchestrator & State Machine

**As a** new user  
**I want** a guided onboarding that remembers my progress  
**So that** I can resume where I left off and never lose work

#### Acceptance Criteria
- [ ] `src/onboarding/orchestrator.py` — OnboardingOrchestrator class
- [ ] State machine with states: `company_discovery`, `document_upload`, `user_profile`, `writing_samples`, `email_integration`, `integration_wizard`, `first_goal`, `activation`
- [ ] Each state persisted in `onboarding_state` table (user_id, current_step, step_data JSONB, started_at, completed_steps[], skipped_steps[])
- [ ] Post-auth routing logic (Section 2.4 of onboarding report):
  - New user with no profile → onboarding flow
  - Returning user with incomplete onboarding → resume at last completed step
  - Returning user with complete onboarding → dashboard
  - LuminOne admin → admin panel
- [ ] Skip affordance on non-critical steps (document upload, writing samples, email integration)
- [ ] Step completion triggers background processing (async, non-blocking)
- [ ] Progress indicator UI component showing completed/current/remaining steps
- [ ] Frontend route: `/onboarding` with step-based navigation
- [ ] RLS: Users can only access their own onboarding state
- [ ] Unit tests for state transitions, resume logic

#### Integration Checklist
- [ ] Episodic memory: Records onboarding start event
- [ ] Readiness score: Initialized at 0 for all sub-domains
- [ ] Audit log: Onboarding session created

#### Database Schema
```sql
CREATE TABLE onboarding_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    current_step TEXT NOT NULL DEFAULT 'company_discovery',
    step_data JSONB DEFAULT '{}',
    completed_steps TEXT[] DEFAULT '{}',
    skipped_steps TEXT[] DEFAULT '{}',
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    readiness_scores JSONB DEFAULT '{"corporate_memory": 0, "digital_twin": 0, "relationship_graph": 0, "integrations": 0, "goal_clarity": 0}',
    UNIQUE(user_id)
);

-- RLS
ALTER TABLE onboarding_state ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_onboarding" ON onboarding_state
    FOR ALL TO authenticated USING (user_id = auth.uid());
```

---

### US-902: Company Discovery & Life Sciences Gate

**As a** new user  
**I want** to tell ARIA about my company  
**So that** ARIA begins learning about my world immediately

#### Acceptance Criteria
- [ ] UI: Company name (text), company website URL (text), user's corporate email
- [ ] Email domain validation — reject personal email domains (gmail.com, yahoo.com, hotmail.com, etc.)
- [ ] Life Sciences gate check — LLM-based judgment (not keyword list) to determine if company is in life sciences vertical
- [ ] If outside life sciences: Graceful acknowledgment explaining current vertical focus, option to join waitlist
- [ ] On submit: Immediately trigger Company Enrichment Engine (US-903) asynchronously
- [ ] On submit: Check if company already exists in Corporate Memory (for cross-user acceleration — US-917)
- [ ] UI shows "ARIA is researching your company..." with progress indicators while enrichment runs
- [ ] User proceeds to next step without waiting for enrichment to complete
- [ ] Frontend component: `CompanyDiscoveryStep`

#### Integration Checklist
- [ ] Corporate Memory: Company profile node created in Graphiti
- [ ] Semantic Memory: Company name, website, industry stored as facts
- [ ] Readiness score: `corporate_memory` updated based on data collected
- [ ] Episodic memory: "User registered company X" event
- [ ] Audit log: Company registration event

---

### US-903: Company Enrichment Engine

**As** ARIA  
**I want** to deeply research the user's company automatically  
**So that** I know the company like a tenured employee by the end of onboarding

#### Acceptance Criteria
- [ ] `src/onboarding/enrichment.py` — CompanyEnrichmentEngine class
- [ ] Exa API integration for web research
- [ ] LLM classification to determine:
  - Company type (Biotech, Large Pharma, CDMO, CRO, Cell/Gene Therapy, Diagnostics, Medical Device)
  - Primary modality (Biologics, Small Molecule, Cell Therapy, Gene Therapy, etc.)
  - Company posture (Buyer or Seller of services)
  - Likely pain points (mapped from company type + modality)
- [ ] Deep research job (runs asynchronously):
  - Website crawling and content extraction
  - ClinicalTrials.gov query for active trials
  - FDA database query (approvals, submissions)
  - SEC filings (if public company)
  - News aggregation via Exa (press releases, funding, partnerships, leadership changes)
  - Competitor identification (same space, modality, geography)
  - Leadership team mapping (C-suite identification via web research)
  - Product/service catalog extraction from website
- [ ] **Causal graph seeding**: For each major fact discovered, generate 1-2 causal hypotheses using LLM
  - Example: "Series C funding → hiring ramp likely → pipeline generation need"
  - Tag as `source: inferred_during_onboarding`, confidence: 0.50-0.60
- [ ] **Knowledge gap identification**: Compare discovered facts against ideal company profile; flag gaps
- [ ] Store all results in Corporate Memory with source attribution and confidence scores
- [ ] Progress reporting via WebSocket to frontend (percentage complete, facts discovered count)
- [ ] Enrichment quality score: How complete is the company profile? (0-100)

#### Integration Checklist
- [ ] Corporate Memory: All facts stored with source, confidence, timestamps
- [ ] Semantic Memory: Entities (companies, people, products, therapeutic areas) extracted and linked
- [ ] Causal graph: Hypothesis edges created in Graphiti with `inferred_during_onboarding` tag
- [ ] Prospective Memory: Knowledge gaps → agent tasks (e.g., "Research manufacturing capacity within 48h" → Analyst)
- [ ] Readiness score: `corporate_memory` updated based on enrichment completeness
- [ ] Episodic memory: "Enrichment completed for Company X — discovered N facts, identified M gaps"
- [ ] Audit log: Research sources used, data points extracted

---

### US-904: Document Upload & Ingestion Pipeline

**As a** new user  
**I want** to upload company documents  
**So that** ARIA learns from our own materials, not just public info

#### Acceptance Criteria
- [ ] Upload zone UI with drag-and-drop, supporting: PDF, DOCX, PPTX, TXT, MD, CSV, XLSX, images
- [ ] File size limits (50MB per file, 500MB total per company)
- [ ] OCR for scanned PDFs and images
- [ ] Document ingestion pipeline:
  1. Format detection & parsing (text extraction per file type)
  2. Semantic chunking (respecting document structure — headers, paragraphs, tables — not naive character splitting)
  3. Entity extraction & linking (NER for companies, people, products, therapeutic areas, modalities)
  4. Embedding generation (pgvector)
  5. Source quality scoring (capabilities deck > generic industry report)
  6. Knowledge extraction (LLM-powered: products, services, therapeutic areas, certifications, differentiators, partnerships)
- [ ] Each document tracked in `company_documents` table with processing status
- [ ] Progress indicator per document (uploading → processing → complete)
- [ ] Documents stored in Supabase Storage with company-scoped access
- [ ] All users in company can read; only uploader can delete their uploads
- [ ] Skip affordance (not all users have documents ready)

#### Integration Checklist
- [ ] Corporate Memory: Extracted knowledge stored as facts with `source: document_upload`
- [ ] Semantic Memory: Entities linked to existing graph nodes or new nodes created
- [ ] Embeddings: Chunks stored in pgvector for semantic search
- [ ] Readiness score: `corporate_memory` boosted based on document richness
- [ ] Episodic memory: "User uploaded N documents, extracted M facts"

---

### US-905: User Profile & LinkedIn Research

**As a** new user  
**I want** ARIA to know who I am professionally  
**So that** she can contextualize everything to my role and expertise

#### Acceptance Criteria
- [ ] UI: Full name, job title, department/function, LinkedIn profile URL, phone (optional), role dropdown (Sales, BD, Marketing, Operations, Executive, etc.)
- [ ] On submit with LinkedIn URL: Fire background research job
  - LinkedIn profile analysis: career history, education, skills, endorsements, publications
  - Professional background synthesis: tenure in industry, past companies, expertise areas
  - Cross-validation: LinkedIn profile matches stated title and company
  - Public content analysis: conference presentations, published articles, blog posts (if available)
- [ ] User research uses name + title + company as triangulated search for accuracy
- [ ] Research results stored in Digital Twin (private, never shared)
- [ ] UI shows summary of what ARIA discovered: "I found your LinkedIn profile — you've been in life sciences for 12 years, most recently focused on biologics CDMOs. Is this right?"
- [ ] User can confirm or correct

#### Integration Checklist
- [ ] Digital Twin: Professional background, expertise areas, career trajectory
- [ ] Semantic Memory: User's domain expertise (for calibrating response depth)
- [ ] Readiness score: `digital_twin` updated
- [ ] Episodic memory: "Researched user profile, found LinkedIn with N years experience"
- [ ] Personality calibration trigger: Professional background informs initial tone

---

### US-906: Writing Sample Analysis & Digital Twin Bootstrap

**As a** new user  
**I want** ARIA to learn my writing style  
**So that** everything she drafts sounds like me

#### Acceptance Criteria
- [ ] Upload zone for writing samples: past emails, documents, reports, proposals, blog posts, LinkedIn posts
- [ ] WritingStyleFingerprint generation from uploaded materials:
  - Sentence length distribution (avg, variance, range)
  - Vocabulary sophistication (lexical diversity score)
  - Formality index (formal:casual ratio)
  - Punctuation patterns (em-dashes, semicolons, exclamation points, ellipses)
  - Opening/closing signatures (how user starts/ends emails)
  - Paragraph structure (short punchy vs. long detailed)
  - Rhetorical patterns (persuasion style)
  - Emoji/emoticon usage frequency
  - Hedging language frequency ("I think", "perhaps", "might")
  - Data reference style (inline vs. attached)
- [ ] Tone & persona analysis: assertive vs. diplomatic, direct vs. indirect, data-driven vs. narrative
- [ ] Style fingerprint stored in Digital Twin (private)
- [ ] UI shows preview: "Based on your samples, here's how I'd describe your style: [direct, data-driven, formal with occasional warmth]. Sound right?"
- [ ] User can adjust characterization
- [ ] Skip affordance (email integration in US-907/908 will also build the fingerprint)

#### Integration Checklist
- [ ] Digital Twin: WritingStyleFingerprint stored
- [ ] Scribe Agent: Can immediately use fingerprint for drafts
- [ ] Readiness score: `digital_twin` significantly boosted
- [ ] Personality calibration: Directness/warmth signals feed into US-919
- [ ] Episodic memory: "Analyzed N writing samples, generated style fingerprint"

---

### US-907: Email Integration & Privacy Controls

**As a** new user  
**I want** to connect my email so ARIA learns from my communications  
**So that** ARIA understands my relationships, patterns, and priorities

#### Acceptance Criteria
- [ ] OAuth consent flow for Google Workspace (Gmail) and Microsoft 365 (Outlook)
- [ ] Scopes: `gmail.readonly` + optional `gmail.send` (Google), `Mail.Read` + optional `Mail.Send` (Microsoft)
- [ ] Privacy exclusion configuration before ingestion starts:
  - Exclude specific senders/domains (e.g., "don't learn from personal@gmail.com")
  - Auto-detection of likely personal emails (spouse, doctor, etc.) with opt-in
  - Per-category toggles (personal, financial, medical)
- [ ] Email ingestion scope: 1-year archive (configurable), all folders
- [ ] Clear explanation of what ARIA will and won't do with email data
- [ ] All email content encrypted at rest
- [ ] Email content never shared between users, even within same company
- [ ] Attachment ingestion requires per-attachment user approval
- [ ] Skip affordance (can connect later from profile page)
- [ ] Connection status indicator (connected/disconnected/syncing)

#### Integration Checklist
- [ ] Readiness score: `relationship_graph` and `digital_twin` updated based on connection status
- [ ] Triggers US-908 (Priority Email Bootstrap) immediately upon connection
- [ ] Audit log: Email integration connected, privacy exclusions configured

---

### US-908: Priority Email Bootstrap (Accelerated Ingestion)

**As** ARIA  
**I want** to rapidly process the user's recent emails during onboarding  
**So that** I know their world by the end of day one, not after the first nightly batch

#### Acceptance Criteria
- [ ] `src/onboarding/email_bootstrap.py` — PriorityEmailIngestion class
- [ ] On email connection: Immediately process last 60 days of SENT mail (not waiting for nightly cron)
- [ ] Extraction per email:
  - Sender/recipient → relationship mapping, stakeholder identification
  - Subject + body → context understanding, writing style learning, commitment tracking
  - Timestamps → temporal patterns, response time analysis
  - Threads → conversation context, follow-up tracking
  - CC/BCC patterns → organizational hierarchy inference
  - Email signatures → contact info extraction, title/role updates
- [ ] Communication pattern extraction:
  - Response time by sender priority
  - Email volume by day/time
  - Follow-up cadence
  - Channel preferences
- [ ] Top contacts identification: 20 most-communicated contacts with frequency, recency, context
- [ ] Active deal detection: Identify email threads that appear to be active negotiations/deals
- [ ] Writing style refinement: Augment style fingerprint from US-906 with real email data
- [ ] Full archive (1 year) queued for nightly batch processing
- [ ] Progress reporting: "Processed X of Y emails... Found N contacts, M active threads"
- [ ] Respects all privacy exclusions from US-907

#### Integration Checklist
- [ ] Digital Twin: Writing style fingerprint refined, communication patterns stored
- [ ] Corporate Memory: Relationship graph seeded (contacts, companies, frequency)
- [ ] Lead Memory: Auto-create Lead Memory for detected active deals (with user confirmation)
- [ ] Prospective Memory: Follow-up commitments detected → scheduled reminders
- [ ] Readiness score: `digital_twin` and `relationship_graph` significantly updated
- [ ] Episodic memory: "Bootstrap processed N emails, identified M contacts, K active threads"

---

### US-909: Integration Wizard (CRM, Calendar, Slack)

**As a** new user  
**I want** to connect my business tools  
**So that** ARIA has full context on my pipeline, schedule, and team communications

#### Acceptance Criteria
- [ ] CRM connection: Salesforce and/or HubSpot via Composio OAuth
  - On connect: Pull current pipeline (opportunities, stages, amounts, close dates)
  - Pull contact and account data
  - Identify data quality issues (stale opportunities, missing fields)
- [ ] Calendar integration: Google Calendar and/or Outlook Calendar
  - On connect: Pull next 2 weeks of meetings
  - Identify meetings with external contacts (potential meeting prep targets)
  - Extract scheduling patterns (meeting preferences, availability)
- [ ] Slack connection (optional): Workspace OAuth
  - Configure which channels ARIA monitors
  - Configure notification routing preferences
- [ ] Each integration: Connection testing, status indicator, graceful error handling
- [ ] Skip affordance per integration (can connect later)
- [ ] Builds on US-413 (OAuth integration settings page)

#### Integration Checklist
- [ ] Lead Memory: CRM opportunities → Lead Memory creation (with user confirmation)
- [ ] Corporate Memory: CRM accounts → company entities in knowledge graph
- [ ] Prospective Memory: Upcoming meetings → pre-meeting research tasks for Analyst agent
- [ ] Digital Twin: Calendar patterns → scheduling preferences
- [ ] Readiness score: `integrations` updated per connected tool
- [ ] Episodic memory: "Connected CRM with N opportunities, Calendar with M upcoming meetings"

---

### US-910: First Goal & Activation

**As a** new user  
**I want** to tell ARIA what's most urgent  
**So that** she starts working on what matters to me right now

#### Acceptance Criteria
- [ ] Goal selection UI with three paths:
  1. **Suggested goals** — Based on what ARIA learned during onboarding (e.g., "You have a meeting with Pfizer in 3 days — want me to prepare a brief?")
  2. **Goal templates** — Common goals by role: pipeline building, meeting prep, competitive intel, territory planning
  3. **Free-form** — User describes their goal in natural language
- [ ] SMART validation: ARIA assesses if goal is Specific, Measurable, Achievable, Relevant, Time-bound
- [ ] If vague: ARIA asks clarifying questions ("What's your target timeline?" "How many leads are you looking for?")
- [ ] Goal decomposition: Complex goals → sub-tasks with agent assignments
- [ ] Goal stored using existing Goal system (US-310-312)
- [ ] **Goal-first onboarding signal**: If user expresses urgency, ARIA adjusts remaining onboarding to prioritize relevant integrations
  - Meeting prep goal → prioritize calendar integration
  - Lead gen goal → prioritize CRM and document upload
  - Competitive intel goal → prioritize competitor identification
- [ ] Transition trigger: Completing this step marks onboarding as complete

#### Integration Checklist
- [ ] Goal System: Goal created with sub-tasks and agent assignments
- [ ] Agent Orchestrator: Agents spawned based on goal requirements
- [ ] Prospective Memory: Goal milestones → scheduled check-ins
- [ ] Readiness score: `goal_clarity` updated
- [ ] Episodic memory: "User set first goal: [description]"
- [ ] Triggers US-915 (Onboarding Completion → Agent Activation)

---

### US-911: Background Memory Construction Orchestrator

**As** ARIA  
**I want** to construct Corporate Memory and Digital Twin in parallel during onboarding  
**So that** both memory systems are rich by the time the user reaches the dashboard

#### Acceptance Criteria
- [ ] `src/onboarding/memory_constructor.py` — MemoryConstructionOrchestrator class
- [ ] Runs asynchronously during Steps 1-8, coordinating all background processes
- [ ] Corporate Memory construction:
  1. Temporal knowledge graph creation (Graphiti) — facts with event_time and ingestion_time
  2. Three-layer structure: Episodic (raw observations), Semantic (extracted facts), Community (patterns — empty at onboarding, populated over time)
  3. Entity relationship mapping: Companies, people, products, therapeutic areas, competitors, partners
  4. Knowledge gap identification: Compare known vs. ideal profile completeness
  5. Initial confidence scoring per Section 12 of onboarding report
- [ ] Digital Twin construction:
  1. Communication style fingerprint (from writing samples + email data)
  2. Initial preference model (communication timing, meeting formats, content types)
  3. Relationship map initialization (key contacts, roles, relationship dynamics)
  4. Temporal pattern baseline (activity patterns, work schedule signals)
- [ ] Merges data from all sources (enrichment, documents, user input, email, CRM) with conflict resolution:
  - User-stated > CRM > Document > Web research > Inferred
- [ ] Progress tracking per memory domain
- [ ] Completion event triggers US-914 (First Conversation Generator)

#### Integration Checklist
- [ ] All six memory types populated as appropriate
- [ ] Graphiti knowledge graph: Entity nodes and relationship edges created
- [ ] pgvector: Embeddings stored for all textual content
- [ ] Readiness score: All sub-scores recalculated
- [ ] Audit log: Memory construction summary (facts created, sources used, gaps identified)

---

### US-912: Knowledge Gap Detection & Prospective Memory Generation

**As** ARIA  
**I want** to identify what I don't know but should  
**So that** I proactively fill gaps through agent actions and natural conversation

#### Acceptance Criteria
- [ ] `src/onboarding/gap_detector.py` — KnowledgeGapDetector class
- [ ] Runs at onboarding completion (and periodically thereafter)
- [ ] Gap analysis per memory domain:
  - Corporate Memory completeness: Does ARIA know products, competitors, market position, leadership team, certifications, pricing?
  - Digital Twin completeness: Does ARIA have writing style, communication patterns, scheduling preferences, relationship context?
  - Competitive intelligence: Are key competitors identified with profiles?
  - Integration connectivity: Which tools are connected vs. missing?
- [ ] Each gap → Prospective Memory entry with:
  - Appropriate trigger (time-based, event-based, or condition-based)
  - Agent assignment (which agent should fill this gap)
  - Priority based on gap importance
- [ ] Gaps that require user input → natural conversation prompts (not pop-ups)
  - Example: "I don't have pricing info" → next chat session, ARIA asks naturally
- [ ] Gap report stored for reference
- [ ] API endpoint: `GET /api/v1/onboarding/gaps` — returns current gaps by domain

#### Integration Checklist
- [ ] Prospective Memory: Gap-filling tasks created with triggers and agent assignments
- [ ] Agent task queue: Auto-generated research tasks for Analyst, Scout, Hunter
- [ ] Readiness score: Gap count inversely affects domain scores
- [ ] Episodic memory: "Identified N knowledge gaps across M domains"

---

### US-913: Onboarding Readiness Score

**As a** user and as ARIA  
**I want** a readiness score per memory domain  
**So that** I know how well-initialized ARIA is and what's still needed

#### Acceptance Criteria
- [ ] `src/onboarding/readiness.py` — OnboardingReadinessService class
- [ ] Sub-scores (0-100 each):
  - `corporate_memory`: Company profile completeness, document coverage, competitive intel depth
  - `digital_twin`: Writing style confidence, communication pattern coverage, relationship graph density
  - `relationship_graph`: Number of contacts mapped, interaction history depth, stakeholder coverage
  - `integrations`: Connected tools count, data freshness, sync status
  - `goal_clarity`: Goal specificity, decomposition quality, agent assignment completeness
- [ ] Overall readiness = weighted average (corporate: 25%, twin: 25%, relationships: 20%, integrations: 15%, goals: 15%)
- [ ] Readiness recalculates on every relevant event (document upload, email processed, CRM sync, etc.)
- [ ] Informs confidence levels across ALL features:
  - Low Digital Twin readiness → email drafts show lower confidence disclaimer
  - Low Corporate Memory → battle cards show "based on limited data" caveat
  - Low integrations → daily briefings are shallower
- [ ] UI component: Subtle readiness indicator on dashboard (not overwhelming — think Apple-clean)
- [ ] API endpoint: `GET /api/v1/readiness` — returns all sub-scores and overall
- [ ] Stored in `onboarding_state.readiness_scores` (JSONB)

#### Integration Checklist
- [ ] Confidence scoring (Phase 2 US-210): Readiness feeds into confidence modifiers
- [ ] Intelligence Pulse (Phase 4 US-416): Readiness affects pulse depth
- [ ] Scribe agent: Draft confidence calibrated to Digital Twin readiness
- [ ] All features: Readiness-aware confidence disclaimers

---

### US-914: First Conversation Generator (Intelligence Demonstration)

**As a** new user  
**I want** ARIA's first message to demonstrate what she already knows  
**So that** I trust she's worth $200K/year from the first interaction

#### Acceptance Criteria
- [ ] `src/onboarding/first_conversation.py` — FirstConversationGenerator class
- [ ] Runs after memory construction completes (US-911)
- [ ] Assembles highest-confidence facts from all memory systems
- [ ] Identifies the most interesting/surprising finding from enrichment
- [ ] Generates a personalized opening message that demonstrates:
  - Corporate Memory ("I've researched your company...")
  - Competitive awareness ("Only 3 CDMOs in North America have dedicated ADC suites...")
  - Knowledge gap honesty ("I haven't found your pricing model yet — can you tell me about it?")
  - Goal orientation ("Based on your upcoming meeting with Pfizer, I've already started preparing...")
- [ ] Message calibrated to user's detected communication style (even from limited data)
- [ ] Includes a Memory Delta: "Here's what I know so far — anything I got wrong?"
- [ ] Includes a natural next step: "Want to start with [suggested action based on goal]?"
- [ ] NOT a wall of text — concise, high-signal, colleague-like
- [ ] Stored as first message in first conversation thread

#### Integration Checklist
- [ ] All memory types: Read for content assembly
- [ ] Personality System (Phase 8): Shapes tone if available, otherwise uses Digital Twin signals
- [ ] Memory Delta Presenter (US-920): Used for the "here's what I know" section
- [ ] Episodic memory: "Delivered first conversation — highlighted N insights"

---

### US-915: Onboarding Completion → Agent Activation

**As** ARIA  
**I want** to start working the moment onboarding completes  
**So that** the user's first morning briefing is impressive, not empty

#### Acceptance Criteria
- [ ] `src/onboarding/activation.py` — OnboardingCompletionOrchestrator class
- [ ] Triggered when last onboarding step completes (or user clicks "Skip to dashboard")
- [ ] Agent activation based on onboarding data:
  - **Scout**: Begin monitoring competitors, industry news, regulatory updates. Monitoring targets derived from Corporate Memory.
  - **Analyst**: Start background research on user's top 3 accounts (from CRM or email analysis). Produce pre-meeting briefs for next 48 hours of meetings.
  - **Hunter**: If lead gen goal set, begin ICP refinement and initial prospect identification.
  - **Operator**: Scan CRM for data quality issues (stale opportunities, missing fields). Prepare pipeline health snapshot.
  - **Scribe**: Pre-draft follow-up emails for any detected stale conversations.
- [ ] Each activation creates a proper Goal (US-310) with agents assigned via orchestrator (US-309)
- [ ] Activation tasks are LOW priority — they yield to any user-initiated tasks
- [ ] Results appear in first daily briefing (next morning)
- [ ] Activity feed shows "ARIA is getting to work..." with agent status

#### Integration Checklist
- [ ] Goal System: Initial goals created for each agent activation
- [ ] Agent Orchestrator: Agents spawned and monitored
- [ ] Prospective Memory: Scheduled check-ins for each activation task
- [ ] Daily Briefing (Phase 4): First briefing populated with activation results
- [ ] Episodic memory: "Post-onboarding activation: spawned N agents for M tasks"

---

### US-916: Adaptive Onboarding OODA Controller

**As** ARIA  
**I want** to adapt the onboarding flow based on what I learn at each step  
**So that** onboarding is a conversation, not a fixed form

#### Acceptance Criteria
- [ ] `src/onboarding/adaptive_controller.py` — OnboardingOODAController class
- [ ] Wraps the step sequence in OODA logic:
  - **Observe**: What has user provided so far? What has enrichment discovered? What integrations are connected?
  - **Orient**: Assess: What's the highest-value next step for THIS specific user? What gaps matter most for their stated goal?
  - **Decide**: Reorder, emphasize, or inject steps based on assessment
  - **Act**: Present the adapted next step
- [ ] Step reordering examples:
  - CDMO user → emphasize competitor identification, manufacturing capabilities
  - User with urgent meeting → fast-track calendar integration and meeting prep
  - User who connected CRM first → leverage CRM data to pre-fill company info
- [ ] Injected questions: ARIA can inject contextual questions between standard steps
  - "I see Samsung Biologics works across biologics, biosimilars, and ADCs. Which therapeutic areas does your team focus on?"
- [ ] Step emphasis: Some steps get more detailed UI based on OODA assessment
- [ ] The step sequence from US-901 remains the default fallback
- [ ] OODA reasoning logged for debugging

#### Integration Checklist
- [ ] OODA Loop (US-301): Uses existing OODA infrastructure
- [ ] Corporate Memory: OODA reads enrichment results to inform decisions
- [ ] Episodic memory: "OODA adapted onboarding: reordered step X before Y because [reason]"
- [ ] Procedural memory: Learns which adaptations lead to higher readiness scores (over time)

---

### US-917: Cross-User Onboarding Acceleration

**As** user #2+ at a company  
**I want** onboarding to be faster because ARIA already knows my company  
**So that** I don't repeat what my colleague already provided

#### Acceptance Criteria
- [ ] On company discovery (US-902): Check if company already exists in Corporate Memory
- [ ] If exists: Calculate `corporate_memory_richness` score for existing data
- [ ] If richness > 70%: Skip/shorten company discovery and document upload
  - Show: "I already know quite a bit about [Company] from working with your colleagues. Here's what I have — anything outdated?"
  - Present Memory Delta of key company facts for confirmation
  - User can correct/update but doesn't need to re-provide
- [ ] If richness 30-70%: Partial skip — show existing data, ask user to fill gaps
- [ ] Steps 4-8 (user-specific) remain full — every user needs their own profile
- [ ] Privacy: User #2 never sees user #1's Digital Twin or personal data
- [ ] Shared Corporate Memory is the design intent per multi-tenant architecture

#### Integration Checklist
- [ ] Corporate Memory: Read existing, merge any new user contributions
- [ ] Readiness score: User's corporate_memory sub-score inherits from company baseline
- [ ] Episodic memory: "Cross-user acceleration applied — skipped N steps based on existing data"
- [ ] Audit log: Which data was inherited vs. newly provided

---

### US-918: Skills Pre-Configuration from Onboarding

**As** ARIA  
**I want** to pre-install relevant skills based on what I learned during onboarding  
**So that** I have the right capabilities ready before the user needs them

#### Acceptance Criteria
- [ ] `src/onboarding/skill_recommender.py` — SkillRecommendationEngine class
- [ ] Mapping: Company type + user role + therapeutic area → recommended skill set
  - Cell therapy company → clinical-trial-analysis, regulatory-monitor (RMAT), pubmed-research
  - CDMO → competitive-positioning, manufacturing-capacity-analysis
  - Large pharma → market-analysis, KOL-mapping, patent-monitor
- [ ] Pre-install recommended skills at COMMUNITY trust level
- [ ] Present recommendations to user: "Based on your role in cell therapy, I've equipped myself with these capabilities: [list]. Want to add or remove any?"
- [ ] Trust builds through usage as designed in US-530 (Autonomy System)
- [ ] Skills that require higher trust start at COMMUNITY and earn trust
- [ ] Integrates with Skill Index Service (US-524)

#### Integration Checklist
- [ ] Skills System (Phase 5B): Skills installed via SkillInstaller (US-525)
- [ ] Agent capabilities: Pre-installed skills immediately available to agents
- [ ] Readiness score: Higher integrations score when relevant skills are ready
- [ ] Episodic memory: "Pre-configured N skills based on user profile"

---

### US-919: Personality Calibration from Onboarding Data

**As** ARIA  
**I want** to calibrate my personality to each user from day one  
**So that** my communication style matches what they respond to best

#### Acceptance Criteria
- [ ] `src/onboarding/personality_calibrator.py` — PersonalityCalibration class
- [ ] Input: Digital Twin writing style fingerprint (from US-906, US-908)
- [ ] Output: Personality trait adjustments for this user:
  - Directness (from hedging language frequency, direct statement ratio)
  - Warmth (from emoji usage, relationship-building language, opening/closing warmth)
  - Assertiveness (from persuasion style, pushback frequency)
  - Detail orientation (from paragraph length, data reference style)
  - Formality (from formality index)
- [ ] NOT mimicry — ARIA maintains her own personality but adjusts the dial
  - Direct user → "I'd push back on that discount" (assertive)
  - Diplomatic user → "Have you considered holding at 15%?" (same insight, softer)
- [ ] Calibration stored in Digital Twin, refreshed when Digital Twin evolves
- [ ] Feeds into Phase 8's Personality System (US-801) when available
- [ ] If Phase 8 not built yet: Calibration stored for future use, basic tone adjustment applied
- [ ] Recalibrates on every user edit to an ARIA draft (highest-signal event)

#### Integration Checklist
- [ ] Digital Twin: Personality calibration stored
- [ ] Phase 8 (US-801): Personality System reads calibration as input
- [ ] Phase 8 (US-802): Theory of Mind uses calibration for adaptation
- [ ] Scribe agent: All drafts use calibrated tone
- [ ] All ARIA responses: Tone adjusted per calibration
- [ ] Episodic memory: "Calibrated personality for user: directness=high, warmth=medium..."

---

### US-920: Memory Delta Presenter

**As a** user  
**I want** ARIA to show me what she learned and let me correct it  
**So that** I trust her intelligence and can fix mistakes early

#### Acceptance Criteria
- [ ] `src/memory/delta_presenter.py` — MemoryDeltaPresenter class
- [ ] Reusable pattern across the entire app (not onboarding-specific)
- [ ] Generates human-readable summaries of what changed in any memory system
- [ ] Confidence indicators per fact (qualitative, not numerical):
  - 95%+ → stated as fact
  - 80-94% → stated with conviction ("Based on your communications...")
  - 60-79% → hedged ("It appears that...")
  - 40-59% → explicit uncertainty ("I'm not certain, but...")
  - <40% → asks for confirmation ("Can you confirm...?")
- [ ] Correction affordance: User can click any fact to correct it
- [ ] Corrections immediately update memory with `source: user_stated`, confidence: 0.95
- [ ] Used during:
  - Post-onboarding enrichment ("Here's what I found about your company")
  - Post-email processing ("I analyzed your email patterns — here's what I learned")
  - Post-meeting debrief ("Based on today's meeting, I updated the stakeholder map")
  - Profile updates ("Here's what changed after your update")
- [ ] Frontend component: `MemoryDelta` — clean, scannable, with expand/collapse per domain
- [ ] API endpoint: `GET /api/v1/memory/delta?since={timestamp}` — returns deltas since time
- [ ] API endpoint: `POST /api/v1/memory/correct` — submit correction

#### Integration Checklist
- [ ] All memory types: Reads changes, generates summaries
- [ ] Confidence scoring (US-210): Uses confidence for language calibration
- [ ] Audit log: All corrections logged with before/after values
- [ ] Episodic memory: "Presented delta with N facts, user corrected M"

---

# PHASE 9B: PROFILE MANAGEMENT & CONTINUOUS LEARNING (5 Stories)

**Priority:** Must-have before 10 customers  
**Estimated Effort:** 20-25 hours  
**Dependencies:** Phase 9A complete

---

### US-921: Profile Page (User Details, Company Details, Documents)

**As a** user  
**I want** to update my information and my company's information at any time  
**So that** ARIA stays current as things change

#### Acceptance Criteria
- [ ] Frontend route: `/settings/profile`
- [ ] User details section: Name, title, department, LinkedIn URL, communication preferences, competitors to track, default tone, privacy exclusion rules
- [ ] Company details section: Company name, website, industry, sub-vertical, description, key products/services
- [ ] Document management:
  - Company Documents folder: Upload, delete, update. All company users can read; only uploader can delete.
  - User Documents folder: Upload, delete, update writing samples. Strictly private.
- [ ] Integration settings: Connect/disconnect email, CRM, calendar, Slack. Manage OAuth permissions. Configure notification preferences.
- [ ] All fields pre-populated from onboarding data
- [ ] Save triggers US-922 (Profile Update → Memory Merge Pipeline)

---

### US-922: Profile Update → Memory Merge Pipeline

**As** ARIA  
**I want** to detect what changed and update my knowledge accordingly  
**So that** profile updates make me smarter, not just update a database record

#### Acceptance Criteria
- [ ] `src/memory/profile_merge.py` — ProfileMergeService class
- [ ] Diff detection: Identify what changed between old and new profile data
- [ ] Re-research trigger: If company details changed (name, website, industry), re-run Company Enrichment Engine
- [ ] Document re-ingestion: New documents go through full ingestion pipeline (US-904)
- [ ] Memory merge: Cross-reference new information against existing memory
- [ ] Contradiction resolution: If new facts conflict, use source hierarchy (user-stated > CRM > web > inferred)
- [ ] Memory Delta presentation (US-920): Show user what ARIA learned that's new or different
- [ ] User confirmation: User confirms or corrects before merge completes
- [ ] Audit log: All changes recorded with timestamps, source, before/after values
- [ ] Readiness score recalculated

---

### US-923: Retroactive Enrichment Service

**As** ARIA  
**I want** to go back and enrich earlier memories when I learn new information  
**So that** my understanding of entities deepens over time, not just accumulates

#### Acceptance Criteria
- [ ] `src/memory/retroactive_enrichment.py` — RetroactiveEnrichmentService class
- [ ] Triggered after major data ingestion events: email archive processing, CRM full sync, document batch upload
- [ ] Identifies entities that were partially known and enriches them with new data
  - Example: "Moderna" was a CRM record → email processing reveals 47 threads with 3 stakeholders → retroactively enrich Lead Memory with full relationship history
- [ ] Stakeholder maps updated retroactively
- [ ] Health scores recalculated with richer data
- [ ] Each enrichment logged as episodic memory ("I learned more about X")
- [ ] Significant enrichments flagged for next briefing or conversation via Memory Delta

---

### US-924: Onboarding Procedural Memory (Self-Improving Onboarding)

**As** ARIA  
**I want** to learn how to onboard better over time  
**So that** each new user has a better experience than the last

#### Acceptance Criteria
- [ ] `src/onboarding/outcome_tracker.py` — OnboardingOutcomeTracker class
- [ ] Measures onboarding quality per user:
  - Completeness scores (readiness sub-scores at onboarding end)
  - Time to complete onboarding
  - Time to first meaningful ARIA interaction
  - Feature engagement in week 1 (which features used, how often)
  - User satisfaction signals (edits to ARIA outputs, corrections to Memory Deltas)
- [ ] Feeds outcomes into procedural memory:
  - "CDMO users who upload capabilities decks have 40% richer Corporate Memory after 1 week"
  - "Users who set meeting prep as first goal engage 3x more in week 1"
- [ ] Multi-tenant safe: Procedural learning about the PROCESS, not about company data. Stored at system level.
- [ ] Quarterly consolidation: Episodic (individual onboarding events) → Semantic (general truths about onboarding effectiveness)
- [ ] Insights influence adaptive onboarding (US-916) over time

---

### US-925: Continuous Onboarding Loop (Ambient Gap Filling)

**As** ARIA  
**I want** to proactively fill knowledge gaps after formal onboarding ends  
**So that** I keep getting smarter about the user through natural interaction

#### Acceptance Criteria
- [ ] Background service: Runs daily, checks readiness sub-scores per user
- [ ] If any sub-score is below threshold (configurable, default 60%):
  - Generate a natural prompt to surface in the next conversation
  - NOT a pop-up or notification — woven into natural ARIA interaction
  - Example: "I noticed I don't have many examples of your writing style yet. If you forward me a few recent emails, I'll match your voice much more closely in drafts."
- [ ] Prompt generation is Theory of Mind-aware (US-802): Don't nag busy users. Space prompts appropriately. Detect when user seems receptive.
- [ ] Tracks which prompts were successful (user provided data) vs. dismissed (user ignored)
- [ ] Successful prompts → procedural memory for future gap-filling strategies
- [ ] Readiness scores gradually improve toward 100% through ambient collection

---

# PHASE 9C: SAAS INFRASTRUCTURE (9 Stories)

**Priority:** Must-have before first paying customer (US-926-930), before 10 customers (US-931-934)  
**Estimated Effort:** 35-45 hours  
**Dependencies:** Phase 1 (Auth foundation)

---

### US-926: Account & Identity Management

**As a** user  
**I want** complete account management  
**So that** I can secure and manage my account

#### Acceptance Criteria
- [ ] Password reset: Full self-service flow via Supabase Auth (replace current placeholder)
- [ ] Email verification: Verification email on signup, must confirm before proceeding
- [ ] Profile editing: Name, email, avatar from `/settings/account`
- [ ] Password change: Current password required to set new password
- [ ] Two-factor authentication (2FA): TOTP-based (Google Authenticator, Authy)
- [ ] Session management: View active sessions, revoke specific sessions
- [ ] Account deletion: Self-service with confirmation, triggers full data purge
- [ ] All security events logged to audit trail

---

### US-927: Team & Company Administration

**As a** company admin  
**I want** to manage my team  
**So that** the right people have the right access

#### Acceptance Criteria
- [ ] Invite flow: Admin can invite users by email, new users get invite link
- [ ] Role management (Admin, Manager, User per Section 2.3 of onboarding report):
  - Admin: Full access, manage users, billing, all corporate memory, user management
  - Manager: Access all team members' shared content, cannot manage billing
  - User: Access own Digital Twin + shared Corporate Memory, own goals
- [ ] First user at a company = Admin (auto-assigned)
- [ ] Admin panel: `/admin/team` — list users, change roles, deactivate accounts
- [ ] RLS enforcement: Roles enforced at database level, not just UI
- [ ] Team directory: See who's on your team, their roles, their status
- [ ] Digital Twin privacy: Admins cannot see other users' Digital Twins (enforced by architecture)

---

### US-928: Billing & Subscription Management

**As a** company admin  
**I want** to manage our subscription  
**So that** we can pay for and continue using ARIA

#### Acceptance Criteria
- [ ] Stripe integration for payment processing
- [ ] Subscription plans: Annual contract ($200K/year), with per-seat pricing for additional users
- [ ] Billing portal: `/admin/billing` — current plan, usage, invoices, payment method
- [ ] Trial/demo mode: Free trial period with feature limitations
- [ ] Upgrade/downgrade flows
- [ ] Invoice generation and history
- [ ] Payment failure handling: Grace period, notifications, eventual suspension
- [ ] Usage tracking: API calls, storage, seats
- [ ] SOC 2 compliant payment data handling (Stripe handles PCI)

---

### US-929: Data Management & Compliance

**As a** user  
**I want** control over my data  
**So that** we meet regulatory requirements and I trust the platform

#### Acceptance Criteria
- [ ] Data export: User can export their complete Digital Twin data (JSON)
- [ ] Data deletion: User can delete their Digital Twin (triggers full memory purge)
- [ ] Company data export: Admin can export all company data
- [ ] GDPR/CCPA compliance:
  - Right to access: Export all personal data
  - Right to deletion: Delete all personal data with cascade
  - Right to rectification: Edit/correct personal data (Memory Delta corrections)
  - Data processing consent: Documented in onboarding, revocable
- [ ] Retention policies: Configurable per data type
  - Audit logs: 90 days for query logs, permanent for write logs
  - Email data: Configurable retention (default 1 year)
  - Conversation history: Permanent unless deleted
- [ ] "Don't learn" retroactive marking: User can mark specific content as off-limits
- [ ] Privacy exclusion management (extends US-907)

---

### US-930: Error Handling & Edge Cases

**As a** user  
**I want** graceful error handling  
**So that** the product never feels broken

#### Acceptance Criteria
- [ ] Global error boundary (React): Catches all unhandled errors, shows friendly fallback
- [ ] Empty states for all major views: No leads yet, no goals yet, no briefings yet — with clear CTAs
- [ ] Loading states: Skeleton screens for all data-dependent views
- [ ] Offline handling: Detect offline, show banner, queue actions for retry
- [ ] API error handling: Standardized error response format, retry logic with exponential backoff
- [ ] Rate limiting: 429 responses handled gracefully with user-facing message
- [ ] Background job failure: Failed enrichment, failed email processing — retry with notification
- [ ] Partial failure handling: If one integration fails during onboarding, others continue

---

### US-931: Search & Navigation

**As a** user  
**I want** to quickly find anything in ARIA  
**So that** I don't waste time navigating

#### Acceptance Criteria
- [ ] Global search: `Cmd+K` / `Ctrl+K` command palette
- [ ] Searchable entities: Leads, contacts, companies, conversations, goals, documents, briefings
- [ ] Search backed by pgvector semantic search (not just text matching)
- [ ] Recent items: Quick access to recently viewed entities
- [ ] Keyboard shortcuts: Navigation, common actions, documented in help
- [ ] Deep linking: Every entity has a shareable URL
- [ ] Breadcrumb navigation on all pages

---

### US-932: Security Hardening

**As a** platform  
**I want** enterprise-grade security  
**So that** customers trust us with their sensitive data

#### Acceptance Criteria
- [ ] CSRF protection on all state-changing endpoints
- [ ] Rate limiting on authentication endpoints (prevent brute force)
- [ ] Rate limiting on API endpoints (prevent abuse)
- [ ] Input validation on all endpoints (Pydantic models)
- [ ] SQL injection prevention (parameterized queries — Supabase handles this)
- [ ] XSS prevention (React handles this, but audit custom HTML rendering)
- [ ] Audit log for all security-relevant events (login, failed login, password change, role change, data export, data deletion)
- [ ] Secrets management: All API keys in environment variables, rotatable
- [ ] HTTPS enforcement
- [ ] Content Security Policy headers
- [ ] Security headers (X-Frame-Options, X-Content-Type-Options, etc.)

---

### US-933: Content & Help System

**As a** user  
**I want** help when I'm stuck  
**So that** I can use ARIA effectively

#### Acceptance Criteria
- [ ] In-app help: `?` icon on every major feature with contextual tooltips
- [ ] Help center: `/help` with searchable articles
- [ ] Onboarding tooltips: First-time feature usage tooltips (dismissable, don't repeat)
- [ ] Changelog: `/changelog` — what's new in ARIA
- [ ] Feedback mechanism: Thumbs up/down on ARIA responses, free-form feedback
- [ ] Support contact: Email/chat link for support requests

---

### US-934: Transactional Email System

**As a** platform  
**I want** to send operational emails  
**So that** users stay informed and engaged

#### Acceptance Criteria
- [ ] Email service integration (Resend, SendGrid, or Postmark)
- [ ] Templates for:
  - Welcome email (post-signup)
  - Onboarding completion ("ARIA is ready")
  - Team invite
  - Password reset
  - Weekly summary (opt-in)
  - Payment receipt
  - Payment failure notification
  - Feature announcements (opt-in)
- [ ] Unsubscribe handling for marketing-type emails
- [ ] Email preference management in user settings
- [ ] Consistent branding across all emails

---

# PHASE 9D: ARIA PRODUCT EXPERIENCE (9 Stories)

**Priority:** Must-have for product completeness  
**Estimated Effort:** 45-55 hours  
**Dependencies:** Phase 9A (onboarding provides the data these features need)

---

### US-935: ARIA Role Configuration & Persona UI

**As a** user  
**I want** to configure ARIA's role and expertise  
**So that** she focuses on what matters for my job

#### Acceptance Criteria
- [ ] Role assignment UI: User selects ARIA's focus area (Sales Ops, BD, Marketing, Executive Support, or custom)
- [ ] Persona tuning: Adjustable traits (proactiveness, verbosity, formality, assertiveness)
- [ ] Domain focus: Select therapeutic areas, modalities, geographies ARIA should prioritize
- [ ] Competitor watchlist: Name specific competitors for monitoring
- [ ] Communication preferences: Preferred channels, notification frequency, response depth
- [ ] Builds on Phase 8 Personality System (US-801) where available
- [ ] Stored in user settings, feeds into all agent decisions
- [ ] Frontend route: `/settings/aria-config`

---

### US-936: Goal Lifecycle Management

**As a** user  
**I want** full goal management  
**So that** ARIA and I can plan, execute, and learn from goals together

#### Acceptance Criteria
- [ ] Goal dashboard: `/goals` — list all goals with status, progress, health
- [ ] Goal creation with ARIA collaboration: ARIA suggests refinements, sub-tasks, timeline
- [ ] Goal templates by role and company type
- [ ] Goal planning UI: Visual decomposition of goal → sub-tasks → agent assignments
- [ ] Goal progress tracking: Milestones, metrics, blockers
- [ ] Goal retrospective: What worked, what didn't, learnings (after goal completes)
- [ ] Goal budgets: Time allocation, resource estimation
- [ ] Goal sharing: Share goals with team members (optional)
- [ ] Extends US-310-312 (basic goal CRUD)

---

### US-937: Autonomous Action Queue & Approval Workflow

**As a** user  
**I want** to see what ARIA is doing and approve/reject actions  
**So that** I maintain control while ARIA works autonomously

#### Acceptance Criteria
- [ ] Action queue UI: `/actions` — pending, approved, completed, rejected actions
- [ ] Action types: Email draft, CRM update, research report, meeting prep, lead generation
- [ ] Approval workflow:
  - LOW risk actions: Auto-execute after trust established (per US-530 Autonomy System)
  - MEDIUM risk: Notify user, auto-execute if not rejected within timeframe
  - HIGH risk: Require explicit approval
  - CRITICAL: Always require approval (sending emails, modifying CRM)
- [ ] Delegation inbox: User can forward tasks to ARIA ("ARIA, handle this")
- [ ] Undo/rollback: Reverse actions within timeframe (where possible)
- [ ] Batch approval: Approve multiple similar actions at once
- [ ] Action history with reasoning: Why ARIA took/suggested each action

---

### US-938: Communication Surface Orchestration

**As a** user  
**I want** to interact with ARIA through multiple channels  
**So that** ARIA meets me where I work

#### Acceptance Criteria
- [ ] Chat (existing): Primary in-app interaction
- [ ] Email notifications: Configurable alerts for briefings, action items, signals
- [ ] Slack integration: @mention ARIA in channels, DM ARIA for quick queries
- [ ] Notification routing intelligence: ARIA decides which channel based on urgency and user preferences
  - Critical → push notification + in-app
  - Important → email or Slack (based on user preference)
  - FYI → in-app activity feed only
- [ ] Channel context persistence: Conversation started in Slack can continue in app
- [ ] Voice interface (future-ready): Architecture supports future "Hey ARIA" integration

---

### US-939: Lead Generation Workflow

**As a** user  
**I want** a complete lead gen pipeline  
**So that** I can go from ICP definition to qualified pipeline

#### Acceptance Criteria
- [ ] ICP builder: Define Ideal Customer Profile with ARIA's help (industry, size, modality, geography, signals)
- [ ] Lead discovery: Hunter agent finds prospects matching ICP
- [ ] Lead review queue: User reviews discovered leads — approve, reject, save for later
- [ ] Lead scoring with explainability: Why did ARIA score this lead highly?
- [ ] Outreach campaign management: Draft sequences, schedule sends, track responses
- [ ] Pipeline view: Visual funnel from prospect → lead → opportunity → customer
- [ ] Extends Hunter agent (US-303) and Lead Memory (Phase 5)

---

### US-940: ARIA Activity Feed / Command Center

**As a** user  
**I want** a central view of everything ARIA is doing  
**So that** I can monitor her work and stay in control

#### Acceptance Criteria
- [ ] Activity feed: `/activity` — chronological stream of all ARIA actions
- [ ] Feed items: Research completed, emails drafted, signals detected, goals progressed, agents activated, CRM synced
- [ ] Real-time updates via WebSocket
- [ ] Filtering: By agent, by type, by priority, by date range
- [ ] Agent status indicators: What each agent is currently working on
- [ ] Reasoning transparency: Click any activity to see ARIA's reasoning chain
- [ ] Confidence indicators: How confident ARIA is in each action/insight
- [ ] Links to relevant entities (leads, goals, conversations)

---

### US-941: Account Planning & Strategic Workflows

**As a** user  
**I want** strategic account management tools  
**So that** I can plan and execute account strategies

#### Acceptance Criteria
- [ ] Account plan view: Per-account strategy document (auto-generated, user-editable)
- [ ] Territory planning: Visual map of accounts by geography, segment, priority
- [ ] Forecasting: Pipeline forecast based on Lead Memory health scores
- [ ] Quota tracking: User enters quota, ARIA tracks progress against it
- [ ] Win/loss analysis: Post-close analysis of what worked/didn't (from Lead Memory lifecycle)
- [ ] Recommended next-best actions per account
- [ ] Integrates with CRM data (US-909)

---

### US-942: Integration Depth

**As a** user  
**I want** deep integrations, not shallow connections  
**So that** ARIA truly understands my tools

#### Acceptance Criteria
- [ ] CRM deep integration:
  - Bidirectional sync with conflict resolution (CRM wins for structured, ARIA wins for insights)
  - Custom field mapping
  - Activity logging in CRM (tagged "[ARIA Summary - Date]")
  - Opportunity stage monitoring with alerts
- [ ] Email intelligence:
  - Thread-level analysis (not just individual emails)
  - Commitment detection ("I'll send the proposal by Friday")
  - Sentiment tracking across threads
  - Response time monitoring with alerts
- [ ] Document/file management:
  - Upload documents from any context (chat, lead, goal)
  - Document version tracking
  - Search within documents
- [ ] Extends Phase 4 (Composio integrations) and Phase 5 (CRM sync)

---

### US-943: Reporting & Value Demonstration

**As a** user / buyer  
**I want** to see ARIA's ROI  
**So that** I can justify the $200K/year investment

#### Acceptance Criteria
- [ ] ROI dashboard: `/dashboard/roi`
- [ ] Time saved metrics:
  - Hours saved on meeting prep (vs. manual research)
  - Hours saved on email drafting (vs. writing from scratch)
  - Hours saved on competitive intel (vs. manual monitoring)
- [ ] Activity metrics: Emails drafted, research briefs generated, signals surfaced, leads discovered
- [ ] Outcome metrics: Deals influenced, pipeline generated, meetings prepared
- [ ] Usage reports: Feature adoption, active days, agent utilization
- [ ] Activity attribution: Which ARIA action led to which outcome
- [ ] Exportable reports (PDF) for executive presentations
- [ ] Comparison: "Your team with ARIA" vs. industry benchmarks

---

# PHASE 9 COMPLETION CHECKLIST

Before declaring Phase 9 complete, verify:

**9A: Intelligence Initialization**
- [ ] All 20 stories completed and passing quality gates
- [ ] New user can complete onboarding in < 15 minutes
- [ ] Corporate Memory populated with 50+ facts after onboarding
- [ ] Digital Twin has writing style fingerprint after onboarding
- [ ] First conversation demonstrates real intelligence
- [ ] Agents activated and producing results within 24 hours
- [ ] Readiness score framework operational
- [ ] Memory Deltas appearing naturally across the app

**9B: Continuous Learning**
- [ ] All 5 stories completed
- [ ] Profile updates trigger memory merge pipeline
- [ ] Retroactive enrichment improving historical data
- [ ] Ambient gap-filling prompts appearing naturally

**9C: SaaS Infrastructure**
- [ ] All 9 stories completed
- [ ] Password reset fully functional
- [ ] Billing integration processing payments
- [ ] GDPR data export/deletion working
- [ ] Global error handling prevents raw errors reaching users

**9D: ARIA Product Experience**
- [ ] All 9 stories completed
- [ ] Goal lifecycle from creation to retrospective
- [ ] Action queue with approval workflow operational
- [ ] Activity feed showing real-time ARIA activity
- [ ] ROI dashboard calculating meaningful metrics

---

## Implementation Order

### Sprint 9.1: Onboarding Core (40-50h)
```
US-901 → US-902 → US-903 → US-904 → US-905 → US-906 →
US-907 → US-908 → US-909 → US-910 → US-911
```

### Sprint 9.2: Onboarding Intelligence (30-35h)
```
US-912 → US-913 → US-914 → US-915 → US-920 →
US-916 → US-917 → US-918 → US-919
```

### Sprint 9.3: SaaS Infrastructure (35-45h)
```
US-926 → US-927 → US-928 → US-929 → US-930 →
US-932 → US-931 → US-933 → US-934
```

### Sprint 9.4: Continuous Learning + ARIA Experience (45-55h)
```
US-921 → US-922 → US-923 → US-924 → US-925 →
US-935 → US-936 → US-937 → US-938 → US-939 →
US-940 → US-941 → US-942 → US-943
```

**Parallelization opportunity:** Sprint 9.3 (SaaS infrastructure) is largely independent of Sprint 9.2 (onboarding intelligence). These can run in parallel across separate Claude Code sessions.

---

## Next Phase

Proceed to Phase 10 or revisit Phases 6-8 to build the Jarvis and AGI Companion layers that many Phase 9 stories reference for future integration.
