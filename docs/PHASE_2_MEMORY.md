# Phase 2: Memory Architecture
## ARIA PRD - Implementation Phase 2

**Prerequisites:** Phase 1 Complete  
**Estimated Stories:** 14  
**Focus:** Six-Type Cognitive Memory, Graphiti integration, Digital Twin foundation

---

## Overview

Phase 2 implements ARIA's bleeding-edge memory architecture - the core differentiator from horizontal AI platforms. This includes:

- Six-Type Cognitive Memory System
- Graphiti (Temporal Knowledge Graph) integration
- Three-Layer Corporate Memory architecture
- User Digital Twin foundation
- Confidence scoring for facts

**Completion Criteria:** ARIA can store, retrieve, and query memories across all six types with temporal awareness and confidence scoring.

---

## Memory Architecture Reference

### Six-Type Cognitive Memory

| Type | Purpose | Storage | Retention |
|------|---------|---------|-----------|
| Working | Current conversation context | In-memory | Session only |
| Episodic | Past events and interactions | Graphiti | Permanent |
| Semantic | Facts and knowledge | Graphiti + pgvector | Permanent |
| Procedural | Learned workflows | Supabase | Permanent |
| Prospective | Future tasks/reminders | Supabase | Until completed |
| Lead | Sales pursuit tracking | Graphiti + Supabase | Permanent |

### Three-Layer Corporate Memory

```
┌─────────────────────────────────────────┐
│  Community Layer (Cross-user patterns)  │
├─────────────────────────────────────────┤
│  Semantic Layer (Extracted facts)       │
├─────────────────────────────────────────┤
│  Episodic Layer (Raw events)            │
└─────────────────────────────────────────┘
```

---

## User Stories

### US-201: Graphiti Client Setup

**As a** developer  
**I want** Graphiti client integration  
**So that** ARIA can use temporal knowledge graphs

#### Acceptance Criteria
- [ ] `src/db/graphiti.py` created with async client
- [ ] Connection to Neo4j database established
- [ ] Graphiti SDK initialized with proper config
- [ ] Health check endpoint verifies Neo4j connection
- [ ] Basic CRUD operations for nodes and edges
- [ ] Error handling for connection failures
- [ ] Unit tests for client operations

#### Technical Notes
```python
# src/db/graphiti.py
from graphiti_core import Graphiti
from graphiti_core.llm_client import AnthropicClient
from src.core.config import settings

class GraphitiClient:
    _instance: Graphiti | None = None
    
    @classmethod
    async def get_instance(cls) -> Graphiti:
        if cls._instance is None:
            llm_client = AnthropicClient(api_key=settings.ANTHROPIC_API_KEY)
            cls._instance = Graphiti(
                uri=settings.NEO4J_URI,
                user=settings.NEO4J_USER,
                password=settings.NEO4J_PASSWORD,
                llm_client=llm_client
            )
            await cls._instance.build_indices()
        return cls._instance
```

---

### US-202: Working Memory Implementation

**As** ARIA  
**I want** working memory for current context  
**So that** I maintain conversation coherence

#### Acceptance Criteria
- [ ] `src/memory/working.py` created
- [ ] In-memory storage per conversation session
- [ ] Stores: current goal, recent messages, active entities
- [ ] Max context window management (truncation strategy)
- [ ] Serialization for context handoff
- [ ] Clear on conversation end
- [ ] Unit tests for all operations

#### Technical Notes
```python
# src/memory/working.py
from dataclasses import dataclass, field
from typing import Any

@dataclass
class WorkingMemory:
    conversation_id: str
    user_id: str
    current_goal: dict | None = None
    messages: list[dict] = field(default_factory=list)
    active_entities: dict[str, Any] = field(default_factory=dict)
    context_tokens: int = 0
    max_tokens: int = 100000
    
    def add_message(self, role: str, content: str) -> None:
        # Add message, manage token count
        pass
    
    def get_context_for_llm(self) -> list[dict]:
        # Return formatted messages for Claude
        pass
    
    def set_entity(self, key: str, value: Any) -> None:
        self.active_entities[key] = value
    
    def clear(self) -> None:
        self.messages = []
        self.active_entities = {}
        self.current_goal = None
```

---

### US-203: Episodic Memory Implementation

**As** ARIA  
**I want** episodic memory for past events  
**So that** I remember what happened in previous interactions

#### Acceptance Criteria
- [ ] `src/memory/episodic.py` created
- [ ] Episodes stored in Graphiti with temporal metadata
- [ ] Fields: user_id, event_type, content, participants, occurred_at, context
- [ ] Bi-temporal tracking: event_time vs. recorded_time
- [ ] Query by time range
- [ ] Query by event type
- [ ] Query by participant
- [ ] Semantic search on content
- [ ] Unit tests for CRUD and queries

#### Technical Notes
```python
# src/memory/episodic.py
from datetime import datetime
from dataclasses import dataclass
from src.db.graphiti import GraphitiClient

@dataclass
class Episode:
    id: str
    user_id: str
    event_type: str  # meeting, email, call, decision, etc.
    content: str
    participants: list[str]
    occurred_at: datetime
    recorded_at: datetime
    context: dict
    
class EpisodicMemory:
    async def store_episode(self, episode: Episode) -> str:
        graphiti = await GraphitiClient.get_instance()
        # Store as Graphiti episode with temporal metadata
        pass
    
    async def query_by_time_range(
        self, 
        user_id: str, 
        start: datetime, 
        end: datetime
    ) -> list[Episode]:
        pass
    
    async def query_by_participant(
        self, 
        user_id: str, 
        participant: str
    ) -> list[Episode]:
        pass
    
    async def semantic_search(
        self, 
        user_id: str, 
        query: str, 
        limit: int = 10
    ) -> list[Episode]:
        pass
```

---

### US-204: Semantic Memory Implementation

**As** ARIA  
**I want** semantic memory for facts and knowledge  
**So that** I know things about the user and their world

#### Acceptance Criteria
- [ ] `src/memory/semantic.py` created
- [ ] Facts stored with confidence scores (0.0-1.0)
- [ ] Temporal validity: valid_from, valid_to, invalidated_at
- [ ] Source tracking for each fact
- [ ] Contradiction detection when adding facts
- [ ] Fact updates preserve history (soft invalidation)
- [ ] Query facts by entity
- [ ] Query facts by topic
- [ ] Vector similarity search
- [ ] Unit tests for all operations

#### Technical Notes
```python
# src/memory/semantic.py
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

class FactSource(Enum):
    USER_STATED = "user_stated"
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    CRM_IMPORT = "crm_import"
    WEB_RESEARCH = "web_research"

@dataclass
class SemanticFact:
    id: str
    user_id: str
    subject: str  # Entity the fact is about
    predicate: str  # Relationship type
    object: str  # Value or related entity
    confidence: float  # 0.0 to 1.0
    source: FactSource
    valid_from: datetime
    valid_to: datetime | None = None
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None

class SemanticMemory:
    async def add_fact(self, fact: SemanticFact) -> str:
        # Check for contradictions
        # If contradicting fact exists, invalidate old one
        # Store new fact with temporal metadata
        pass
    
    async def get_facts_about(
        self, 
        user_id: str, 
        subject: str,
        as_of: datetime | None = None
    ) -> list[SemanticFact]:
        # Return facts valid at given time (or now)
        pass
    
    async def search_facts(
        self, 
        user_id: str, 
        query: str,
        min_confidence: float = 0.5
    ) -> list[SemanticFact]:
        pass
```

---

### US-205: Procedural Memory Implementation

**As** ARIA  
**I want** procedural memory for learned workflows  
**So that** I can repeat successful patterns

#### Acceptance Criteria
- [ ] `src/memory/procedural.py` created
- [ ] Workflows stored in Supabase with steps
- [ ] Track success/failure rate per workflow
- [ ] Version history for workflow updates
- [ ] User-specific vs. shared workflows
- [ ] Query workflows by trigger condition
- [ ] Execute workflow returns step sequence
- [ ] Unit tests for CRUD and execution

#### SQL Schema
```sql
CREATE TABLE procedural_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    workflow_name TEXT NOT NULL,
    description TEXT,
    trigger_conditions JSONB,  -- When to use this workflow
    steps JSONB NOT NULL,  -- Ordered list of actions
    success_count INT DEFAULT 0,
    failure_count INT DEFAULT 0,
    is_shared BOOLEAN DEFAULT FALSE,
    version INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_procedural_user ON procedural_memories(user_id);
CREATE INDEX idx_procedural_trigger ON procedural_memories USING GIN(trigger_conditions);
```

#### Technical Notes
```python
# src/memory/procedural.py
@dataclass
class Workflow:
    id: str
    user_id: str
    workflow_name: str
    description: str
    trigger_conditions: dict
    steps: list[dict]
    success_rate: float
    
class ProceduralMemory:
    async def find_matching_workflow(
        self, 
        user_id: str, 
        context: dict
    ) -> Workflow | None:
        # Match trigger conditions against context
        pass
    
    async def record_outcome(
        self, 
        workflow_id: str, 
        success: bool
    ) -> None:
        # Update success/failure counts
        pass
```

---

### US-206: Prospective Memory Implementation

**As** ARIA  
**I want** prospective memory for future tasks  
**So that** I don't forget commitments and follow-ups

#### Acceptance Criteria
- [ ] `src/memory/prospective.py` created
- [ ] Tasks stored in Supabase with due dates
- [ ] Status: pending, completed, cancelled, overdue
- [ ] Trigger types: time-based, event-based, condition-based
- [ ] Query upcoming tasks
- [ ] Query overdue tasks
- [ ] Mark task complete/cancel
- [ ] Link tasks to goals and leads
- [ ] Unit tests for all operations

#### SQL Schema
```sql
CREATE TABLE prospective_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    task TEXT NOT NULL,
    description TEXT,
    trigger_type TEXT NOT NULL,  -- time, event, condition
    trigger_config JSONB NOT NULL,  -- {"due_at": timestamp} or {"event": "email_received", "from": "john@acme.com"}
    status TEXT DEFAULT 'pending',
    priority TEXT DEFAULT 'medium',
    related_goal_id UUID,
    related_lead_id UUID,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_prospective_user_status ON prospective_memories(user_id, status);
CREATE INDEX idx_prospective_trigger ON prospective_memories USING GIN(trigger_config);
```

---

### US-207: Memory Query API

**As** ARIA  
**I want** a unified memory query interface  
**So that** I can search across all memory types

#### Acceptance Criteria
- [ ] `GET /api/v1/memory/query` endpoint
- [ ] Accepts: query string, memory types filter, time range
- [ ] Returns ranked results from all specified memory types
- [ ] Results include source memory type and confidence
- [ ] Pagination support
- [ ] Performance: < 500ms for typical queries
- [ ] Integration tests for cross-memory queries

#### Technical Notes
```python
# src/api/routes/memory.py
from fastapi import APIRouter, Query
from typing import Literal

router = APIRouter(prefix="/memory", tags=["memory"])

class MemoryQueryResult(BaseModel):
    id: str
    memory_type: Literal["episodic", "semantic", "procedural", "prospective"]
    content: str
    relevance_score: float
    confidence: float | None
    timestamp: datetime

@router.get("/query")
async def query_memory(
    q: str = Query(..., min_length=1),
    types: list[str] = Query(default=["episodic", "semantic"]),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 20,
    user: dict = Depends(get_current_user)
) -> list[MemoryQueryResult]:
    pass
```

---

### US-208: Memory Store API

**As** ARIA  
**I want** endpoints to store memories  
**So that** learning persists across sessions

#### Acceptance Criteria
- [ ] `POST /api/v1/memory/episode` - Store new episode
- [ ] `POST /api/v1/memory/fact` - Store new semantic fact
- [ ] `POST /api/v1/memory/task` - Store new prospective task
- [ ] `POST /api/v1/memory/workflow` - Store new procedural workflow
- [ ] Input validation with Pydantic models
- [ ] Returns created memory with ID
- [ ] Integration tests for all endpoints

---

### US-209: Digital Twin Foundation

**As** ARIA  
**I want** to build a user's Digital Twin  
**So that** I can communicate in their style

#### Acceptance Criteria
- [ ] `src/memory/digital_twin.py` created
- [ ] Captures: writing style, vocabulary, tone preferences
- [ ] Extracts patterns from user's emails/messages
- [ ] Stores fingerprint in semantic memory
- [ ] Method to get style guidelines for a user
- [ ] Method to score style match of generated text
- [ ] Updates incrementally with new samples
- [ ] Unit tests for fingerprint extraction

#### Technical Notes
```python
# src/memory/digital_twin.py
@dataclass
class WritingStyleFingerprint:
    user_id: str
    average_sentence_length: float
    vocabulary_level: str  # simple, moderate, advanced
    formality_score: float  # 0-1, informal to formal
    common_phrases: list[str]
    greeting_style: str
    sign_off_style: str
    emoji_usage: bool
    punctuation_patterns: dict
    
class DigitalTwin:
    async def analyze_sample(
        self, 
        user_id: str, 
        text: str, 
        text_type: str  # email, message, document
    ) -> None:
        # Extract style features and update fingerprint
        pass
    
    async def get_style_guidelines(self, user_id: str) -> str:
        # Return prompt-ready style instructions
        pass
    
    async def score_style_match(
        self, 
        user_id: str, 
        generated_text: str
    ) -> float:
        # Return 0-1 score of how well text matches user's style
        pass
```

---

### US-210: Confidence Scoring System

**As** ARIA  
**I want** confidence scores on all facts  
**So that** I know how certain I am about information

#### Acceptance Criteria
- [ ] Confidence calculation based on source reliability
- [ ] Confidence decay over time (configurable)
- [ ] Confidence boost from corroboration
- [ ] Threshold for including facts in responses
- [ ] Display confidence to user when relevant
- [ ] Configuration for confidence parameters
- [ ] Unit tests for scoring calculations

#### Confidence Factors
```python
# Base confidence by source
SOURCE_CONFIDENCE = {
    FactSource.USER_STATED: 0.95,
    FactSource.CRM_IMPORT: 0.90,
    FactSource.EXTRACTED: 0.75,
    FactSource.WEB_RESEARCH: 0.70,
    FactSource.INFERRED: 0.60,
}

# Decay: 5% per month for non-refreshed facts
# Boost: +10% for each corroborating source (max 0.99)
```

---

### US-211: Memory Audit Log

**As** an admin  
**I want** all memory operations logged  
**So that** there's a full audit trail

#### Acceptance Criteria
- [ ] `memory_audit_log` table created
- [ ] Logs: operation, memory_type, memory_id, user_id, timestamp
- [ ] Logs both writes and significant reads
- [ ] No sensitive content in logs (just IDs)
- [ ] Retention policy: 90 days default
- [ ] Query endpoint for admin users
- [ ] Unit tests for logging

#### SQL Schema
```sql
CREATE TABLE memory_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    operation TEXT NOT NULL,  -- create, update, delete, query
    memory_type TEXT NOT NULL,
    memory_id UUID,
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_user_time ON memory_audit_log(user_id, created_at DESC);
```

---

### US-212: Corporate Memory Schema

**As** ARIA  
**I want** corporate memory shared across users  
**So that** organizational knowledge benefits everyone

#### Acceptance Criteria
- [ ] Company-level facts stored separately from user facts
- [ ] Community patterns extracted from cross-user data
- [ ] Privacy: no user-identifiable data in corporate memory
- [ ] Access control: users can read company facts
- [ ] Admin can manage corporate facts
- [ ] Graphiti namespace separation for multi-tenant
- [ ] Unit tests for isolation

---

### US-213: Memory Integration in Chat

**As** a user  
**I want** ARIA to use memory in conversations  
**So that** she remembers context about me

#### Acceptance Criteria
- [ ] Chat endpoint queries relevant memories before responding
- [ ] Relevant facts included in LLM context
- [ ] Memory citations in responses when appropriate
- [ ] New information extracted and stored during chat
- [ ] Working memory updated with conversation flow
- [ ] Performance: memory retrieval < 200ms
- [ ] Integration test for memory-aware chat

---

### US-214: Point-in-Time Memory Queries

**As** ARIA  
**I want** to query "what did I know on date X"  
**So that** I can reason about past states

#### Acceptance Criteria
- [ ] `as_of` parameter on fact queries
- [ ] Returns only facts valid at that timestamp
- [ ] Handles invalidated facts correctly
- [ ] Works for both episodic and semantic memory
- [ ] API endpoint supports temporal queries
- [ ] Unit tests for temporal correctness

---

## Phase 2 Completion Checklist

Before moving to Phase 3, verify:

- [ ] All 14 user stories completed
- [ ] All quality gates pass
- [ ] Graphiti connected and operational
- [ ] All six memory types implemented
- [ ] Memory query API returning results
- [ ] Facts have confidence scores
- [ ] Audit log capturing operations
- [ ] Chat uses memory context
- [ ] Temporal queries working

---

## Next Phase

Proceed to `PHASE_3_AGENTS.md` for Agent System implementation.
