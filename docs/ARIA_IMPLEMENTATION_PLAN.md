# ARIA Implementation Plan: Phase 5 Completion + Phase 5B Skills Integration

**Created:** February 4, 2026  
**Current Status:** Phase 5 at 44% (7/16 complete)

---

## Executive Summary

This document provides:
1. **Phase 5A Completion** - Remaining 9 stories to finish Lead Memory System
2. **Phase 5B Skills Integration** - 12 new stories for skills.sh integration with security
3. **Updated CLAUDE.md** - New patterns and project structure
4. **Implementation Timeline** - Optimal ordering with parallelization opportunities

---

## Part 1: Phase 5A - Lead Memory Completion

### Current Status

| Status | Count | Stories |
|--------|-------|---------|
| ✅ Complete | 7 | US-501, US-502, US-503, US-505, US-506, US-508, US-515 |
| ⚠️ Partial | 3 | US-504, US-507, US-514 |
| ❌ Not Started | 6 | US-509, US-510, US-511, US-512, US-513, US-516 |

### Remaining Work - Ordered by Dependencies

#### Sprint 5A.1: Complete Partial Stories (3-4 hours)

**US-504: Stakeholder Mapping - COMPLETE** (1h)
```
Current: Schema exists, models defined
Missing: StakeholderService, API endpoints

Tasks:
- [ ] Create src/memory/stakeholder_service.py
  - add_stakeholder(lead_id, stakeholder)
  - update_stakeholder(stakeholder_id, updates)
  - get_stakeholders(lead_id)
  - map_relationships(lead_id)
- [ ] Add API endpoints to routes/leads.py:
  - POST /leads/{id}/stakeholders
  - GET /leads/{id}/stakeholders
  - PUT /stakeholders/{id}
  - DELETE /stakeholders/{id}
- [ ] Unit tests for stakeholder operations
```

**US-507: Lead Memory API Endpoints - COMPLETE** (1.5h)
```
Current: GET/list, GET/{id}, POST/notes, POST/export
Missing: POST/create, PATCH/update, stakeholders endpoints, insights, transition

Tasks:
- [ ] POST /leads - Create new lead
- [ ] PATCH /leads/{id} - Update lead details
- [ ] POST /leads/{id}/transition - Stage transition
- [ ] GET /leads/{id}/insights - AI-generated insights
- [ ] Integration with stakeholder endpoints from US-504
- [ ] Request/response models for all endpoints
- [ ] API tests
```

**US-514: Proactive Lead Behaviors - COMPLETE** (1h)
```
Current: Alert detection in health_score.py
Missing: Briefing integration, notification triggers

Tasks:
- [ ] Connect health alerts to notification system
- [ ] Add lead alerts to morning briefing generator
- [ ] Create lead_alert_triggers table or use existing notifications
- [ ] Trigger alerts on: health drop >10 points, stage stuck >14 days, stakeholder change
```

#### Sprint 5A.2: Detail View + Creation (3-4 hours)

**US-509: Lead Memory UI - Detail View** (2h)
```
Prerequisites: US-507 complete (API endpoints)

Tasks:
- [ ] Create /dashboard/leads/[id] route
- [ ] Lead detail page components:
  - LeadHeader (name, company, stage badge, health score)
  - StakeholderMap (org chart visualization)
  - ActivityTimeline (all events chronologically)
  - HealthScoreCard (score breakdown, history chart)
  - NotesSection (add/view notes)
  - InsightsPanel (AI-generated insights)
- [ ] Stage transition UI with confirmation
- [ ] Edit mode for lead details
- [ ] Link from list view (US-508) to detail view
```

**US-510: Lead Memory Creation Triggers** (1.5h)
```
Prerequisites: US-507 complete (create endpoint)

Tasks:
- [ ] Auto-create lead from chat mentions:
  - Pattern detection: "I'm working on [Company]", "Had a call with [Contact] at [Company]"
  - LLM extraction of company/contact details
  - Prompt user to confirm before creating
- [ ] Auto-create from email (when email integration exists):
  - New thread with unknown company domain
  - Extract company info from signature
- [ ] Manual creation from:
  - Lead list view "Add Lead" button
  - Chat command: "Create a lead for [Company]"
- [ ] CRM import trigger (for US-511)
```

#### Sprint 5A.3: CRM Sync (3-4 hours)

**US-511: CRM Bidirectional Sync** (2h)
```
Prerequisites: US-510 complete (creation triggers)

Tasks:
- [ ] Create src/integrations/crm_sync.py:
  - CRMSyncService class
  - sync_lead_to_crm(lead_id) - push ARIA lead to CRM
  - sync_lead_from_crm(crm_record) - pull CRM record to ARIA
  - resolve_conflicts(aria_lead, crm_record) - conflict resolution
- [ ] Field mapping configuration:
  - Map ARIA fields to CRM fields (Salesforce, HubSpot)
  - Handle custom fields
- [ ] Sync triggers:
  - On lead update in ARIA → push to CRM
  - Webhook receiver for CRM updates
  - Scheduled full sync (nightly)
- [ ] Conflict resolution rules:
  - CRM wins for: stage, expected_value, close_date
  - ARIA wins for: health_score, insights, stakeholder_map
```

**US-512: CRM Sync Audit Trail** (1h)
```
Prerequisites: US-511 in progress

Tasks:
- [ ] Create crm_sync_audit table (or use existing audit_log)
- [ ] Log every sync operation:
  - direction (to_crm, from_crm)
  - fields_changed
  - old_values, new_values
  - conflicts_detected, resolution_applied
- [ ] API endpoint: GET /leads/{id}/sync-history
- [ ] UI component: Sync history in lead detail view
```

#### Sprint 5A.4: Advanced Features (3-4 hours)

**US-513: Multi-User Collaboration** (1.5h)
```
Prerequisites: Basic lead system complete

Tasks:
- [ ] Lead ownership and sharing:
  - owner_id (primary owner)
  - shared_with[] (additional team members)
- [ ] Permission levels:
  - Owner: full control
  - Collaborator: edit, add notes
  - Viewer: read-only
- [ ] Activity attribution:
  - Show who added each note/event
  - Filter activity by user
- [ ] Notification preferences per collaborator
```

**US-516: Cross-Lead Pattern Recognition** (1.5h)
```
Prerequisites: Multiple leads with events

Tasks:
- [ ] Pattern detection service:
  - Identify common objections across leads
  - Find successful stage transition patterns
  - Detect stakeholder patterns (who typically blocks/champions)
- [ ] Pattern storage:
  - learned_patterns table (or procedural memory)
  - Pattern confidence scores
- [ ] Surface patterns in UI:
  - "Similar leads typically..." suggestions
  - "This objection was handled successfully by..."
```

### Phase 5A Completion Checklist

```
Sprint 5A.1 (3-4h):
  [ ] US-504: Stakeholder service + API
  [ ] US-507: Remaining API endpoints
  [ ] US-514: Briefing/notification integration

Sprint 5A.2 (3-4h):
  [ ] US-509: Lead detail view page
  [ ] US-510: Creation triggers

Sprint 5A.3 (3-4h):
  [ ] US-511: CRM bidirectional sync
  [ ] US-512: Sync audit trail

Sprint 5A.4 (3-4h):
  [ ] US-513: Multi-user collaboration
  [ ] US-516: Cross-lead pattern recognition

Total: ~14-16 hours to complete Phase 5A
```

---

## Part 2: Phase 5B - Skills Integration

### Overview

Phase 5B introduces skills.sh integration with enterprise-grade security. This is a critical capability that extends all ARIA agents with community and custom skills.

### New Directory Structure

```
aria/
├── backend/src/
│   ├── skills/                    # NEW: Skills subsystem
│   │   ├── __init__.py
│   │   ├── index.py              # Skill index and discovery
│   │   ├── installer.py          # Skill installation
│   │   ├── executor.py           # Sandboxed execution
│   │   ├── orchestrator.py       # Multi-skill coordination
│   │   ├── context_manager.py    # Context budget management
│   │   └── generator.py          # Custom skill creation
│   ├── security/                  # NEW: Security subsystem
│   │   ├── __init__.py
│   │   ├── data_classification.py
│   │   ├── sanitization.py
│   │   ├── sandbox.py
│   │   ├── trust_levels.py
│   │   └── audit.py
│   ...
```

### User Stories

#### US-520: Security Foundation - Data Classification (2h)

**As** ARIA  
**I want** to classify all data by sensitivity  
**So that** skills only access appropriate data

```
Acceptance Criteria:
- [ ] Create src/security/data_classification.py
- [ ] DataClass enum: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED, REGULATED
- [ ] DataClassifier with pattern matching for:
  - PII (SSN, credit cards, DOB)
  - Financial data (revenue, pricing, contracts)
  - Health data (PHI indicators)
  - Contact info (emails, phones)
- [ ] Context-based classification (source field)
- [ ] Unit tests with sample data
```

#### US-521: Security Foundation - Trust Levels (1h)

**As** ARIA  
**I want** skill trust levels  
**So that** I can control what each skill can access

```
Acceptance Criteria:
- [ ] Create src/security/trust_levels.py
- [ ] SkillTrustLevel enum: CORE, VERIFIED, COMMUNITY, USER
- [ ] TRUST_DATA_ACCESS matrix (trust level → allowed data classes)
- [ ] TRUSTED_SKILL_SOURCES list (Anthropic, Vercel, Supabase, etc.)
- [ ] Trust level determination function
```

#### US-522: Security Foundation - Sanitization Pipeline (2h)

**As** ARIA  
**I want** to sanitize data before skills see it  
**So that** sensitive data is protected

```
Acceptance Criteria:
- [ ] Create src/security/sanitization.py
- [ ] DataSanitizer class with:
  - classify_all(data) → list of ClassifiedData
  - tokenize(data, allowed_classes) → tokenized data + token map
  - redact(data) → redacted data (for non-tokenizable)
  - detokenize(output, token_map) → original values restored
- [ ] Token format: [DATA_TYPE_NNN] (e.g., [FINANCIAL_001])
- [ ] Output validation (scan for leakage)
- [ ] Integration tests
```

#### US-523: Security Foundation - Skill Sandbox (2h)

**As** ARIA  
**I want** skills to run in sandboxed environments  
**So that** they can't access unauthorized resources

```
Acceptance Criteria:
- [ ] Create src/security/sandbox.py
- [ ] SandboxConfig dataclass:
  - timeout_seconds, memory_limit_mb, cpu_limit_percent
  - network_enabled, allowed_domains
  - can_read_files, can_write_files, can_execute_code
- [ ] SANDBOX_BY_TRUST mapping (trust level → sandbox config)
- [ ] SkillSandbox.execute() with resource limits
- [ ] Timeout enforcement using asyncio.wait_for
```

#### US-524: Skill Index Service (2h)

**As** ARIA  
**I want** a searchable index of available skills  
**So that** I can find the right skill for each task

```
Acceptance Criteria:
- [ ] Create src/skills/index.py
- [ ] SkillIndex class:
  - sync_from_skills_sh() - periodic sync from skills.sh
  - search(query) - semantic search for skills
  - get_skill(skill_id) - full skill content
  - get_summaries(skill_ids) - compact summaries for context
- [ ] Three-tier awareness:
  - Tier 1 (Core): Always loaded, full content cached
  - Tier 2 (Relevant): Life sciences + trusted, summaries cached
  - Tier 3 (Discovery): Index only, load on demand
- [ ] Database: skills_index table
- [ ] 20-word summary generation for each skill
```

#### US-525: Skill Installation Service (1.5h)

**As a** user  
**I want** to install skills from skills.sh  
**So that** ARIA gains new capabilities

```
Acceptance Criteria:
- [ ] Create src/skills/installer.py
- [ ] SkillInstaller class:
  - install(user_id, skill_path) - install skill
  - uninstall(user_id, skill_id) - remove skill
  - get_installed(user_id) - list user's skills
- [ ] Security verification before install:
  - Check trust level
  - Verify content hash
  - Admin approval for shell execute skills
- [ ] Database: user_skills table
- [ ] API endpoints: POST/DELETE /skills/install
```

#### US-526: Skill Execution Service (2h)

**As** ARIA  
**I want** to execute skills safely  
**So that** I can use skill capabilities

```
Acceptance Criteria:
- [ ] Create src/skills/executor.py
- [ ] SkillExecutor class:
  - execute(user_id, skill_id, input_data) - run skill
  - Integrates: sanitization → sandbox → validation
- [ ] Execution flow:
  1. Get skill and trust level
  2. Classify input data
  3. Sanitize based on trust
  4. Execute in sandbox
  5. Validate output
  6. Detokenize
  7. Audit log
- [ ] SkillExecution result dataclass
```

#### US-527: Skill Audit Trail (1.5h)

**As an** admin  
**I want** complete audit of skill executions  
**So that** I can ensure compliance

```
Acceptance Criteria:
- [ ] Create src/security/skill_audit.py (or extend existing)
- [ ] SkillAuditEntry dataclass with:
  - Skill identification (id, path, trust level, version)
  - Execution context (task_id, agent_id, trigger reason)
  - Data access (classes requested/granted, redacted flag, tokens used)
  - Results (input/output hash, success, error)
  - Chain integrity (previous_hash, entry_hash)
- [ ] Database: skill_audit_log table
- [ ] API: GET /skills/audit
```

#### US-528: Skill Orchestrator (3h)

**As** ARIA  
**I want** to coordinate multi-skill tasks  
**So that** complex tasks can use multiple skills

```
Acceptance Criteria:
- [ ] Create src/skills/orchestrator.py
- [ ] SkillOrchestrator class:
  - create_execution_plan(task) - build DAG
  - execute_plan(plan) - run with parallelization
  - _execute_step() - isolated sub-agent execution
- [ ] Execution plan with:
  - Dependency graph
  - Parallel groups (independent steps)
  - Estimated duration/cost
- [ ] Working memory for handoffs between skills
- [ ] Progress reporting via WebSocket
```

#### US-529: Skill Context Manager (2h)

**As** ARIA  
**I want** efficient context management for skills  
**So that** multi-skill tasks don't blow context limits

```
Acceptance Criteria:
- [ ] Create src/skills/context_manager.py
- [ ] SkillContextManager class:
  - prepare_orchestrator_context() - minimal context for planning
  - prepare_subagent_context() - isolated context per skill
  - build_working_memory_entry() - summary for handoffs
  - compact_if_needed() - structured compaction
- [ ] Context budget allocation:
  - Orchestrator: ~2000 tokens
  - Skill index: ~600 tokens
  - Working memory: ~800 tokens
  - Per skill: ~6000 tokens
- [ ] Dynamic summary verbosity (minimal/standard/detailed)
```

#### US-530: Autonomy & Trust System (2h)

**As a** user  
**I want** ARIA to build trust with skills over time  
**So that** I don't have to approve every action

```
Acceptance Criteria:
- [ ] Create src/skills/autonomy.py
- [ ] SkillAutonomyService class:
  - should_request_approval(user, skill, plan) - check if approval needed
  - record_execution_outcome(user, skill, success) - build trust
  - request_autonomy_upgrade(user, skill) - suggest increased autonomy
- [ ] Risk levels: LOW (3 successes), MEDIUM (10), HIGH (session), CRITICAL (always)
- [ ] Trust history tracking per user per skill
- [ ] Database: skill_trust_history table
```

#### US-531: Agent-Skill Integration (2h)

**As** ARIA  
**I want** agents to use skills naturally  
**So that** skills extend agent capabilities

```
Acceptance Criteria:
- [ ] Create src/agents/skill_aware_agent.py
- [ ] SkillAwareAgent base class extending BaseAgent
- [ ] AGENT_SKILLS mapping (which skills each agent can use)
- [ ] execute_with_skills() method
- [ ] _analyze_skill_needs() - LLM determines if skills help
- [ ] Update all 6 agents to extend SkillAwareAgent
- [ ] OODA loop integration (skills in ACT phase)
```

#### US-532: Skills API & UI (2h)

**As a** user  
**I want** to manage my skills  
**So that** I can customize ARIA's capabilities

```
Acceptance Criteria:
- [ ] API endpoints in routes/skills.py:
  - GET /skills/available - browsable skill index
  - GET /skills/installed - user's skills
  - POST /skills/install - install skill
  - DELETE /skills/{id} - uninstall
  - GET /skills/audit - audit history
  - GET /skills/autonomy/{id} - trust level
- [ ] Basic UI components:
  - SkillBrowser - search and install
  - InstalledSkills - manage installed
  - SkillExecutionProgress - show progress
```

### Phase 5B Implementation Order

```
Week 1: Security Foundation (7-8h)
  [ ] US-520: Data classification (2h)
  [ ] US-521: Trust levels (1h)
  [ ] US-522: Sanitization pipeline (2h)
  [ ] US-523: Skill sandbox (2h)

Week 2: Core Skills (8-9h)
  [ ] US-524: Skill index service (2h)
  [ ] US-525: Skill installation (1.5h)
  [ ] US-526: Skill execution (2h)
  [ ] US-527: Skill audit trail (1.5h)

Week 3: Orchestration & Integration (9-10h)
  [ ] US-528: Skill orchestrator (3h)
  [ ] US-529: Context manager (2h)
  [ ] US-530: Autonomy system (2h)
  [ ] US-531: Agent integration (2h)

Week 4: Polish (2h)
  [ ] US-532: API & UI (2h)

Total: ~28-30 hours for Phase 5B
```

### Parallelization Opportunities

**Can run in parallel with Phase 5A:**
- US-520-523 (Security foundation) has NO dependencies on Phase 5A
- Start security work while finishing Lead Memory

**Within Phase 5B:**
- US-520 + US-521 can run in parallel
- US-524 + US-525 can run in parallel (after 520-523)
- US-528 + US-529 can run in parallel

---

## Part 3: Database Migrations

### New Tables for Phase 5B

```sql
-- Migration: 20260204000001_create_skills_tables.sql

-- Skill index cache
CREATE TABLE skills_index (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_path TEXT NOT NULL UNIQUE,
    skill_name TEXT NOT NULL,
    description TEXT,
    full_content TEXT,
    content_hash TEXT,
    author TEXT,
    version TEXT,
    tags TEXT[],
    install_count INT DEFAULT 0,
    trust_level TEXT DEFAULT 'community',
    security_verified BOOLEAN DEFAULT FALSE,
    life_sciences_relevant BOOLEAN DEFAULT FALSE,
    declared_permissions TEXT[],
    summary_verbosity TEXT DEFAULT 'standard',
    last_synced TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- User skill installations
CREATE TABLE user_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    tenant_id UUID NOT NULL,
    skill_id TEXT NOT NULL,
    skill_path TEXT NOT NULL,
    trust_level TEXT NOT NULL,
    permissions_granted TEXT[],
    installed_at TIMESTAMPTZ DEFAULT NOW(),
    auto_installed BOOLEAN DEFAULT FALSE,
    last_used_at TIMESTAMPTZ,
    execution_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    UNIQUE(user_id, skill_id)
);

-- Skill trust history
CREATE TABLE skill_trust_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    skill_id TEXT NOT NULL,
    successful_executions INT DEFAULT 0,
    failed_executions INT DEFAULT 0,
    last_success TIMESTAMPTZ,
    last_failure TIMESTAMPTZ,
    session_trust_granted BOOLEAN DEFAULT FALSE,
    globally_approved BOOLEAN DEFAULT FALSE,
    globally_approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, skill_id)
);

-- Skill execution audit log
CREATE TABLE skill_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    tenant_id UUID NOT NULL,
    skill_id TEXT NOT NULL,
    skill_path TEXT NOT NULL,
    skill_trust_level TEXT NOT NULL,
    task_id UUID,
    agent_id TEXT,
    trigger_reason TEXT,
    data_classes_requested TEXT[],
    data_classes_granted TEXT[],
    data_redacted BOOLEAN DEFAULT FALSE,
    tokens_used TEXT[],
    input_hash TEXT NOT NULL,
    output_hash TEXT,
    execution_time_ms INT,
    success BOOLEAN NOT NULL,
    error TEXT,
    sandbox_config JSONB,
    security_flags TEXT[],
    previous_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL
);

-- Execution plans
CREATE TABLE skill_execution_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    tenant_id UUID NOT NULL,
    task_description TEXT NOT NULL,
    skills_planned TEXT[] NOT NULL,
    dependency_graph JSONB NOT NULL,
    parallel_groups JSONB NOT NULL,
    estimated_duration_ms INT,
    risk_level TEXT NOT NULL,
    approval_required BOOLEAN DEFAULT FALSE,
    approval_status TEXT,
    execution_started_at TIMESTAMPTZ,
    execution_completed_at TIMESTAMPTZ,
    success BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Working memory for skill handoffs
CREATE TABLE skill_working_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID REFERENCES skill_execution_plans(id) NOT NULL,
    step_number INT NOT NULL,
    skill_id TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT,
    artifacts JSONB,
    extracted_facts JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(plan_id, step_number)
);

-- RLS Policies
ALTER TABLE skills_index ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_skills ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_trust_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_execution_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_working_memory ENABLE ROW LEVEL SECURITY;

-- Skills index is readable by all
CREATE POLICY "skills_index_read" ON skills_index
    FOR SELECT TO authenticated USING (true);

-- User-specific policies
CREATE POLICY "user_skills_own" ON user_skills
    FOR ALL TO authenticated USING (user_id = auth.uid());

CREATE POLICY "trust_history_own" ON skill_trust_history
    FOR ALL TO authenticated USING (user_id = auth.uid());

CREATE POLICY "audit_log_read_own" ON skill_audit_log
    FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE POLICY "plans_own" ON skill_execution_plans
    FOR ALL TO authenticated USING (user_id = auth.uid());

CREATE POLICY "working_memory_via_plan" ON skill_working_memory
    FOR ALL TO authenticated USING (
        plan_id IN (SELECT id FROM skill_execution_plans WHERE user_id = auth.uid())
    );

-- Indexes
CREATE INDEX idx_skills_index_tags ON skills_index USING GIN(tags);
CREATE INDEX idx_skills_index_trust ON skills_index(trust_level);
CREATE INDEX idx_user_skills_user ON user_skills(user_id);
CREATE INDEX idx_skill_audit_user_time ON skill_audit_log(user_id, timestamp DESC);
```

---

## Part 4: Complete Timeline

```
Phase 5A: Lead Memory Completion (~14-16h)
├── Sprint 5A.1: Complete partials (3-4h)
├── Sprint 5A.2: Detail view + creation (3-4h)
├── Sprint 5A.3: CRM sync (3-4h)
└── Sprint 5A.4: Advanced features (3-4h)

Phase 5B: Skills Integration (~28-30h)
├── Week 1: Security foundation (7-8h)
├── Week 2: Core skills (8-9h)
├── Week 3: Orchestration & integration (9-10h)
└── Week 4: API & UI polish (2h)

Total: ~42-46 hours

Recommended parallel execution:
- Day 1-2: US-520-523 (security) while finishing US-504, US-507, US-514
- Day 3-4: US-509, US-510 + US-524, US-525 (can run parallel sessions)
```

---

## Part 5: Success Metrics

### Phase 5A (Lead Memory)
- [ ] Lead detail view loads in <500ms
- [ ] CRM sync latency <2s
- [ ] All 16 stories complete
- [ ] Zero data loss during sync conflicts

### Phase 5B (Skills)
- [ ] Zero security incidents (data leakage)
- [ ] 100% audit log completeness
- [ ] Skill execution P95 <30s
- [ ] Context overhead <3000 tokens for orchestrator
- [ ] 80%+ auto-approval rate after trust established
