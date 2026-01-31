# Phase 5: Lead Memory System
## ARIA PRD - Implementation Phase 5

**Prerequisites:** Phase 4 Complete  
**Estimated Stories:** 16  
**Focus:** Lead Memory lifecycle, CRM sync, multi-user collaboration, conversation intelligence

---

## Overview

Phase 5 implements ARIA's bleeding-edge Lead Memory system - a dedicated, longitudinal memory type that tracks the entire relationship lifecycle for each sales pursuit. This is a key differentiator.

**Lead Memory Features:**
- Full timeline from first touch to closed-won
- Stakeholder mapping with sentiment tracking
- Bidirectional CRM sync
- Conversation intelligence (objections, signals, commitments)
- Health scoring
- Multi-user collaboration

**Completion Criteria:** User can track leads through full lifecycle with AI-powered insights and CRM integration.

---

## Lead Memory Architecture Reference

### Lifecycle State Machine

```
┌─────────────┐    Qualified    ┌──────────────────┐   Closed-Won   ┌────────────────┐
│ Lead Memory │ ──────────────▶ │ Opportunity Mem. │ ─────────────▶ │ Account Memory │
└─────────────┘                 └──────────────────┘                └────────────────┘
     │                                   │                                  │
     │ Tracks:                           │ Adds:                            │ Adds:
     │ - Outreach                        │ - Proposals                      │ - Renewals
     │ - Qualification                   │ - Negotiations                   │ - Upsells
     │ - Nurturing                       │ - Contracts                      │ - Support
     └───────────────────────────────────┴──────────────────────────────────┘
                              Full History Preserved
```

### Health Score Components

| Factor | Weight | Positive | Negative |
|--------|--------|----------|----------|
| Communication Frequency | 25% | Increasing | Decreasing/silent |
| Response Time | 20% | Quick replies | Slow/no response |
| Sentiment | 20% | Positive tone | Concerns/objections |
| Stakeholder Breadth | 20% | Multiple engaged | Single thread |
| Stage Velocity | 15% | Moving forward | Stuck in stage |

---

## User Stories

### US-501: Lead Memory Database Schema

**As a** developer  
**I want** Lead Memory tables  
**So that** leads are persisted correctly

#### Acceptance Criteria
- [ ] `lead_memories` table with all fields
- [ ] `lead_memory_events` for timeline
- [ ] `lead_memory_stakeholders` for contacts
- [ ] `lead_memory_insights` for AI insights
- [ ] `lead_memory_contributions` for multi-user
- [ ] `lead_memory_crm_sync` for sync state
- [ ] RLS policies for user isolation
- [ ] Indexes for common queries

#### SQL Schema
```sql
-- Core Lead Memory
CREATE TABLE lead_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    company_id UUID REFERENCES companies(id),
    company_name TEXT NOT NULL,
    lifecycle_stage TEXT DEFAULT 'lead',  -- lead, opportunity, account
    status TEXT DEFAULT 'active',  -- active, won, lost, dormant
    health_score INT DEFAULT 50,  -- 0-100
    crm_id TEXT,  -- External CRM record ID
    crm_provider TEXT,  -- salesforce, hubspot
    first_touch_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ,
    expected_close_date DATE,
    expected_value DECIMAL,
    tags TEXT[],
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Timeline Events
CREATE TABLE lead_memory_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,  -- email_sent, email_received, meeting, call, note, signal
    direction TEXT,  -- inbound, outbound
    subject TEXT,
    content TEXT,
    participants TEXT[],
    occurred_at TIMESTAMPTZ NOT NULL,
    source TEXT,  -- gmail, calendar, manual, crm
    source_id TEXT,  -- Original message/event ID
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Stakeholder Map
CREATE TABLE lead_memory_stakeholders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    contact_email TEXT NOT NULL,
    contact_name TEXT,
    title TEXT,
    role TEXT,  -- decision_maker, influencer, champion, blocker, user
    influence_level INT DEFAULT 5,  -- 1-10
    sentiment TEXT DEFAULT 'neutral',  -- positive, neutral, negative, unknown
    last_contacted_at TIMESTAMPTZ,
    notes TEXT,
    personality_insights JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(lead_memory_id, contact_email)
);

-- AI-Generated Insights
CREATE TABLE lead_memory_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    insight_type TEXT NOT NULL,  -- objection, buying_signal, commitment, risk, opportunity
    content TEXT NOT NULL,
    confidence FLOAT DEFAULT 0.7,
    source_event_id UUID REFERENCES lead_memory_events(id),
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    addressed_at TIMESTAMPTZ,
    addressed_by UUID REFERENCES auth.users(id)
);

-- Multi-User Contributions
CREATE TABLE lead_memory_contributions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    contributor_id UUID REFERENCES auth.users(id) NOT NULL,
    contribution_type TEXT NOT NULL,  -- event, note, insight
    contribution_id UUID,  -- Reference to the contributed item
    status TEXT DEFAULT 'pending',  -- pending, merged, rejected
    reviewed_by UUID REFERENCES auth.users(id),
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- CRM Sync State
CREATE TABLE lead_memory_crm_sync (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE CASCADE,
    last_sync_at TIMESTAMPTZ,
    sync_direction TEXT,  -- push, pull, bidirectional
    last_push_at TIMESTAMPTZ,
    last_pull_at TIMESTAMPTZ,
    pending_changes JSONB DEFAULT '[]',
    conflict_log JSONB DEFAULT '[]',
    status TEXT DEFAULT 'synced',  -- synced, pending, conflict, error
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_lead_memories_user ON lead_memories(user_id);
CREATE INDEX idx_lead_memories_status ON lead_memories(user_id, status);
CREATE INDEX idx_lead_events_lead ON lead_memory_events(lead_memory_id);
CREATE INDEX idx_lead_events_time ON lead_memory_events(lead_memory_id, occurred_at DESC);
CREATE INDEX idx_lead_stakeholders_lead ON lead_memory_stakeholders(lead_memory_id);
CREATE INDEX idx_lead_insights_lead ON lead_memory_insights(lead_memory_id);

-- RLS
ALTER TABLE lead_memories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can manage own leads" ON lead_memories
    FOR ALL USING (user_id = auth.uid());
```

---

### US-502: Lead Memory Core Implementation

**As** ARIA  
**I want** Lead Memory core functionality  
**So that** I can track sales pursuits

#### Acceptance Criteria
- [ ] `src/memory/lead_memory.py` created
- [ ] Create lead memory with initial data
- [ ] Update lead memory fields
- [ ] Transition lifecycle stages
- [ ] Calculate health score
- [ ] Query leads by status, health, etc.
- [ ] Unit tests for all operations

#### Technical Notes
```python
# src/memory/lead_memory.py
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class LifecycleStage(Enum):
    LEAD = "lead"
    OPPORTUNITY = "opportunity"
    ACCOUNT = "account"

class LeadStatus(Enum):
    ACTIVE = "active"
    WON = "won"
    LOST = "lost"
    DORMANT = "dormant"

@dataclass
class LeadMemory:
    id: str
    user_id: str
    company_name: str
    lifecycle_stage: LifecycleStage
    status: LeadStatus
    health_score: int
    first_touch_at: datetime
    last_activity_at: datetime
    events: list["LeadEvent"]
    stakeholders: list["Stakeholder"]
    insights: list["Insight"]

class LeadMemoryService:
    async def create(
        self, 
        user_id: str, 
        company_name: str,
        trigger: str  # email_approved, manual, crm_import, inbound
    ) -> LeadMemory:
        pass
    
    async def add_event(
        self, 
        lead_id: str, 
        event: "LeadEvent"
    ) -> None:
        # Also triggers insight extraction
        pass
    
    async def calculate_health_score(self, lead_id: str) -> int:
        # Apply health score algorithm
        pass
    
    async def transition_stage(
        self, 
        lead_id: str, 
        new_stage: LifecycleStage
    ) -> None:
        # Preserve history, add capabilities
        pass
```

---

### US-503: Lead Memory Event Tracking

**As** ARIA  
**I want** to track all lead events  
**So that** I have a complete timeline

#### Acceptance Criteria
- [ ] Store email events (sent, received)
- [ ] Store meeting events (from calendar)
- [ ] Store call events (transcripts if available)
- [ ] Store manual notes
- [ ] Store market signals
- [ ] Query timeline by date range
- [ ] Query by event type
- [ ] Automatic event extraction from integrations

---

### US-504: Stakeholder Mapping

**As** ARIA  
**I want** to map stakeholders for each lead  
**So that** I understand the buying committee

#### Acceptance Criteria
- [ ] Extract contacts from emails automatically
- [ ] Manual contact addition
- [ ] Role assignment (decision maker, influencer, etc.)
- [ ] Influence level (1-10)
- [ ] Sentiment tracking (updated from interactions)
- [ ] Personality insights storage
- [ ] Relationship visualization data
- [ ] Unit tests for stakeholder operations

---

### US-505: Conversation Intelligence

**As** ARIA  
**I want** to extract insights from conversations  
**So that** I provide strategic guidance

#### Acceptance Criteria
- [ ] Detect objections mentioned
- [ ] Detect buying signals
- [ ] Detect commitments made (by us and them)
- [ ] Detect risks and concerns
- [ ] Confidence scoring on insights
- [ ] Link insights to source events
- [ ] Mark insights as addressed
- [ ] Unit tests for extraction

#### Technical Notes
```python
# src/memory/conversation_intelligence.py
class ConversationIntelligence:
    async def analyze_event(
        self, 
        event: LeadEvent
    ) -> list[Insight]:
        """Extract insights from an event using LLM."""
        prompt = f"""
        Analyze this {event.event_type} and extract:
        1. Any objections or concerns raised
        2. Buying signals indicating readiness
        3. Commitments made by either party
        4. Risks to the deal
        5. Opportunities to advance
        
        Content: {event.content}
        
        Return JSON with insight_type, content, confidence.
        """
        # Call LLM and parse response
        pass
```

---

### US-506: Health Score Algorithm

**As** ARIA  
**I want** automatic health scoring  
**So that** users know which leads need attention

#### Acceptance Criteria
- [ ] Score calculated from 5 factors (see reference)
- [ ] Real-time recalculation on new events
- [ ] Historical health tracking
- [ ] Configurable weights
- [ ] Alert when health drops significantly
- [ ] Unit tests for scoring accuracy

#### Technical Notes
```python
class HealthScoreCalculator:
    WEIGHTS = {
        "communication_frequency": 0.25,
        "response_time": 0.20,
        "sentiment": 0.20,
        "stakeholder_breadth": 0.20,
        "stage_velocity": 0.15,
    }
    
    async def calculate(self, lead: LeadMemory) -> int:
        scores = {
            "communication_frequency": self._score_frequency(lead.events),
            "response_time": self._score_response_time(lead.events),
            "sentiment": self._score_sentiment(lead.insights),
            "stakeholder_breadth": self._score_breadth(lead.stakeholders),
            "stage_velocity": self._score_velocity(lead),
        }
        
        weighted_sum = sum(
            scores[factor] * weight 
            for factor, weight in self.WEIGHTS.items()
        )
        return int(weighted_sum * 100)
```

---

### US-507: Lead Memory API Endpoints

**As a** user  
**I want** API endpoints for Lead Memory  
**So that** the frontend can interact with leads

#### Acceptance Criteria
- [ ] `POST /api/v1/leads` - Create lead memory
- [ ] `GET /api/v1/leads` - List leads with filters
- [ ] `GET /api/v1/leads/{id}` - Get full lead with timeline
- [ ] `PATCH /api/v1/leads/{id}` - Update lead
- [ ] `POST /api/v1/leads/{id}/events` - Add event
- [ ] `POST /api/v1/leads/{id}/stakeholders` - Add stakeholder
- [ ] `GET /api/v1/leads/{id}/insights` - Get insights
- [ ] `POST /api/v1/leads/{id}/transition` - Change lifecycle stage
- [ ] Integration tests for all endpoints

---

### US-508: Lead Memory UI - List View

**As a** user  
**I want** to see all my leads  
**So that** I can manage my pipeline

#### Acceptance Criteria
- [ ] `/dashboard/leads` route
- [ ] Table/card view of leads
- [ ] Health indicator (🟢🟡🔴)
- [ ] Sort by: health, last activity, name, value
- [ ] Filter by: status, stage, health range
- [ ] Search by company name
- [ ] Quick actions (view, add note)
- [ ] Bulk actions (export)

---

### US-509: Lead Memory UI - Detail View

**As a** user  
**I want** a detailed lead view  
**So that** I can see full context

#### Acceptance Criteria
- [ ] `/dashboard/leads/{id}` route
- [ ] Header: company name, health score, stage
- [ ] Timeline tab: chronological events
- [ ] Stakeholders tab: contact map
- [ ] Insights tab: objections, signals, commitments
- [ ] Activity tab: all interactions
- [ ] Add note/event inline
- [ ] Edit stakeholder details
- [ ] Transition stage button

---

### US-510: Lead Memory Creation Triggers

**As** ARIA  
**I want** automatic lead creation  
**So that** tracking starts seamlessly

#### Acceptance Criteria
- [ ] Create when user approves outbound email
- [ ] Create on manual "track this" action
- [ ] Create on CRM import
- [ ] Create on inbound response
- [ ] Retroactive creation: scan history when new lead detected
- [ ] Deduplication: merge if company already tracked
- [ ] Unit tests for each trigger

---

### US-511: CRM Bidirectional Sync

**As a** user  
**I want** Lead Memory synced with CRM  
**So that** data stays consistent

#### Acceptance Criteria
- [ ] Connect to Salesforce via Composio
- [ ] Connect to HubSpot via Composio
- [ ] Push: ARIA summaries → CRM notes (tagged [ARIA])
- [ ] Pull: CRM stage changes → Lead Memory
- [ ] Pull: CRM activity → Lead events
- [ ] Conflict resolution: CRM wins for structured fields
- [ ] Sync state tracking per lead
- [ ] Manual sync trigger option
- [ ] Sync error handling and retry

---

### US-512: CRM Sync Audit Trail

**As** an admin  
**I want** CRM sync logged  
**So that** I can audit data flow

#### Acceptance Criteria
- [ ] Log all sync operations
- [ ] Log conflicts and resolutions
- [ ] Queryable by lead, direction, status
- [ ] Visible in lead detail view
- [ ] Export capability

---

### US-513: Multi-User Collaboration

**As a** team member  
**I want** to contribute to shared leads  
**So that** team knowledge is captured

#### Acceptance Criteria
- [ ] Lead has single owner (primary ARIA)
- [ ] Other users can be contributors
- [ ] Contributions flagged for owner review
- [ ] Owner can merge or reject
- [ ] Full audit trail of who contributed what
- [ ] Contributor list visible on lead
- [ ] Notification to owner on new contribution

---

### US-514: Proactive Lead Behaviors

**As a** user  
**I want** ARIA to proactively alert me  
**So that** I don't miss opportunities

#### Acceptance Criteria
- [ ] Alert: Lead silent for 14+ days
- [ ] Alert: Health score dropped 20+ points
- [ ] Suggestion: Follow-up draft when engagement drops
- [ ] Suggestion: Stakeholder expansion when single-threaded
- [ ] Suggestion: Stage transition when criteria met
- [ ] Alerts appear in daily briefing
- [ ] Alerts appear as notifications
- [ ] Configurable alert thresholds

---

### US-515: Lead Memory in Knowledge Graph

**As** ARIA  
**I want** Lead Memory in Graphiti  
**So that** I can query across leads

#### Acceptance Criteria
- [ ] Lead Memory as first-class node
- [ ] Typed relationships: OWNED_BY, HAS_CONTACT, HAS_EVENT, etc.
- [ ] Cross-lead queries: "leads where we discussed pricing"
- [ ] Pattern detection: "leads that went silent"
- [ ] Relationship mapping to Corporate Memory
- [ ] Unit tests for graph queries

#### Graph Structure
```
[Lead Memory: Acme Corp]
├── OWNED_BY → [User: Sarah]
├── CONTRIBUTED_BY → [User: Mike]
├── ABOUT_COMPANY → [Company: Acme Corp]
├── HAS_CONTACT → [John Smith, VP Procurement]
├── HAS_COMMUNICATION → [Email: Jan 15 pricing]
├── HAS_SIGNAL → [Market Signal: Series B]
└── SYNCED_TO → [CRM: Salesforce Opp #12345]
```

---

### US-516: Cross-Lead Pattern Recognition

**As** ARIA  
**I want** to learn patterns across leads  
**So that** I can apply learnings

#### Acceptance Criteria
- [ ] Detect: Average time to close by segment
- [ ] Detect: Common objection patterns
- [ ] Detect: Successful engagement patterns
- [ ] Apply warnings to current leads
- [ ] Store patterns in Corporate Memory
- [ ] Privacy: No user-identifiable data in patterns
- [ ] Unit tests for pattern detection

---

## Phase 5 Completion Checklist

Before moving to Phase 6, verify:

- [ ] All 16 user stories completed
- [ ] All quality gates pass
- [ ] Lead Memory fully functional
- [ ] Timeline tracking all events
- [ ] Stakeholder mapping working
- [ ] Conversation intelligence extracting insights
- [ ] Health scores calculating correctly
- [ ] CRM sync bidirectional
- [ ] Multi-user contributions working
- [ ] Proactive alerts firing
- [ ] Graphiti integration complete

---

## Next Phase

Proceed to `PHASE_6_ADVANCED.md` for Advanced Intelligence implementation.
