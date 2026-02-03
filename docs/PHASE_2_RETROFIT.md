# Phase 2 Retrofit: Memory Foundations
## ARIA PRD - AGI Memory Enhancements

**Prerequisites:** Phase 2 Complete (US-201 through US-214)  
**Estimated Stories:** 3  
**Focus:** Salience decay, conversation continuity, cross-conversation priming

---

## Overview

This retrofit adds "colleague memory" capabilities to the existing memory system. These foundations are **required** before Phase 4 continues, as the chat interface depends on them.

**Why Retrofit?** The original Phase 2 implemented functional memory. This retrofit makes memory feel human - memories fade but don't disappear, conversations feel continuous, and ARIA remembers your shared history.

**Completion Criteria:** Memory system supports salience decay, stores conversation episodes, and primes new conversations with relevant context.

---

## User Stories

### US-218: Memory Salience Decay System

**As a** user  
**I want** ARIA's memories to naturally fade over time (but never disappear)  
**So that** recent and frequently-accessed information is prioritized

#### Acceptance Criteria
- [ ] Add `current_salience` (FLOAT, default 1.0) and `last_accessed_at` (TIMESTAMPTZ) columns to episodic_memories
- [ ] Add same columns to semantic_facts table
- [ ] Create `memory_access_log` table to track retrievals
- [ ] Implement `SalienceService` with decay calculation
- [ ] Decay formula: `salience = (base + access_boost) × 0.5^(days/half_life)`
- [ ] Default half-life: 30 days
- [ ] Access boost: +0.1 per retrieval
- [ ] Minimum salience: 0.01 (never zero)
- [ ] Background job updates salience daily
- [ ] All memory queries record access in log
- [ ] Unit tests for decay math
- [ ] Integration tests for access tracking

#### SQL Schema
```sql
-- Migration: Add salience tracking to existing tables
ALTER TABLE episodic_memories 
ADD COLUMN IF NOT EXISTS current_salience FLOAT DEFAULT 1.0,
ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0;

ALTER TABLE semantic_facts 
ADD COLUMN IF NOT EXISTS current_salience FLOAT DEFAULT 1.0,
ADD COLUMN IF NOT EXISTS last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0;

-- Memory access log for strengthening
CREATE TABLE memory_access_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id UUID NOT NULL,
    memory_type TEXT NOT NULL CHECK (memory_type IN ('episodic', 'semantic', 'lead')),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    access_context TEXT, -- what triggered the access
    accessed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for efficient access queries
CREATE INDEX idx_memory_access_log_memory ON memory_access_log(memory_id, memory_type);
CREATE INDEX idx_memory_access_log_user ON memory_access_log(user_id);

-- RLS policies
ALTER TABLE memory_access_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can only access own memory logs" ON memory_access_log
    FOR ALL USING (auth.uid() = user_id);
```

#### Technical Notes
```python
# src/memory/salience.py
from datetime import datetime, timedelta
import math
from typing import Literal

class SalienceService:
    DEFAULT_HALF_LIFE_DAYS = 30
    ACCESS_BOOST = 0.1
    MIN_SALIENCE = 0.01
    
    def __init__(self, db_client):
        self.db = db_client
    
    def calculate_decay(
        self,
        original_salience: float,
        access_count: int,
        days_since_last_access: float,
        half_life: float = DEFAULT_HALF_LIFE_DAYS
    ) -> float:
        """Calculate current salience with decay and access boost."""
        access_boost = access_count * self.ACCESS_BOOST
        base_salience = original_salience + access_boost
        decay_factor = math.pow(0.5, days_since_last_access / half_life)
        current = base_salience * decay_factor
        return max(current, self.MIN_SALIENCE)
    
    async def record_access(
        self,
        memory_id: str,
        memory_type: Literal["episodic", "semantic", "lead"],
        user_id: str,
        context: str | None = None
    ) -> None:
        """Record memory access and update salience."""
        # Log the access
        await self.db.table("memory_access_log").insert({
            "memory_id": memory_id,
            "memory_type": memory_type,
            "user_id": user_id,
            "access_context": context
        }).execute()
        
        # Update the memory's access tracking
        table = f"{memory_type}_memories" if memory_type == "episodic" else f"{memory_type}_facts"
        await self.db.table(table).update({
            "last_accessed_at": datetime.utcnow().isoformat(),
            "access_count": self.db.raw("access_count + 1")
        }).eq("id", memory_id).execute()
    
    async def update_all_salience(self, user_id: str) -> int:
        """Background job: recalculate salience for all user memories."""
        updated = 0
        
        for table, type_name in [
            ("episodic_memories", "episodic"),
            ("semantic_facts", "semantic")
        ]:
            memories = await self.db.table(table)\
                .select("id, current_salience, access_count, last_accessed_at")\
                .eq("user_id", user_id)\
                .execute()
            
            for mem in memories.data:
                days_old = (datetime.utcnow() - datetime.fromisoformat(
                    mem["last_accessed_at"]
                )).days
                
                new_salience = self.calculate_decay(
                    original_salience=1.0,  # Base is always 1.0
                    access_count=mem["access_count"],
                    days_since_last_access=days_old
                )
                
                if abs(new_salience - mem["current_salience"]) > 0.01:
                    await self.db.table(table)\
                        .update({"current_salience": new_salience})\
                        .eq("id", mem["id"]).execute()
                    updated += 1
        
        return updated
```

---

### US-219: Conversation Episode Service

**As a** user  
**I want** ARIA to extract durable memories from each conversation  
**So that** important content isn't lost when conversations end

#### Acceptance Criteria
- [ ] Create `conversation_episodes` table
- [ ] Implement `ConversationService` for episode extraction
- [ ] LLM-based conversation summarization
- [ ] Extract key topics, entities, user state
- [ ] Identify "open threads" (unresolved items)
- [ ] Record outcomes mentioned in conversation
- [ ] Triggered automatically when conversation goes idle (configurable)
- [ ] Manual trigger via API endpoint
- [ ] Episodes link to source conversation
- [ ] Integration with Graphiti for entity extraction
- [ ] Unit tests for extraction logic
- [ ] Integration tests for episode storage

#### SQL Schema
```sql
CREATE TABLE conversation_episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    conversation_id UUID NOT NULL,
    
    -- Summary content
    summary TEXT NOT NULL,
    key_topics TEXT[] DEFAULT '{}',
    entities_discussed TEXT[] DEFAULT '{}',
    
    -- User state detected
    user_state JSONB DEFAULT '{}',
    -- Example: {"mood": "stressed", "confidence": "uncertain", "focus": "pricing"}
    
    -- Outcomes and threads
    outcomes JSONB DEFAULT '[]',
    -- Example: [{"type": "decision", "content": "Will follow up with legal"}]
    
    open_threads JSONB DEFAULT '[]',
    -- Example: [{"topic": "pricing", "status": "awaiting_response", "context": "..."}]
    
    -- Metadata
    message_count INTEGER,
    duration_minutes INTEGER,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Salience (episodes also decay)
    current_salience FLOAT DEFAULT 1.0,
    last_accessed_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_conversation_episodes_user ON conversation_episodes(user_id);
CREATE INDEX idx_conversation_episodes_conversation ON conversation_episodes(conversation_id);
CREATE INDEX idx_conversation_episodes_topics ON conversation_episodes USING GIN(key_topics);
CREATE INDEX idx_conversation_episodes_salience ON conversation_episodes(user_id, current_salience DESC);

-- RLS
ALTER TABLE conversation_episodes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can only access own episodes" ON conversation_episodes
    FOR ALL USING (auth.uid() = user_id);
```

#### Technical Notes
```python
# src/memory/conversation.py
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ConversationEpisode:
    id: str
    conversation_id: str
    summary: str
    key_topics: list[str]
    entities_discussed: list[str]
    user_state: dict
    outcomes: list[dict]
    open_threads: list[dict]
    message_count: int
    duration_minutes: int
    started_at: datetime
    ended_at: datetime

class ConversationService:
    IDLE_THRESHOLD_MINUTES = 30
    
    def __init__(self, db_client, llm_client, graphiti_client):
        self.db = db_client
        self.llm = llm_client
        self.graphiti = graphiti_client
    
    async def extract_episode(
        self,
        user_id: str,
        conversation_id: str,
        messages: list[dict]
    ) -> ConversationEpisode:
        """Extract durable content from a conversation."""
        
        # 1. Generate summary via LLM
        summary_prompt = f"""Summarize this conversation concisely:
        
{self._format_messages(messages)}

Focus on:
- Key decisions made
- Information shared
- Action items agreed
- Questions left unanswered

Output a 2-3 sentence summary."""

        summary = await self.llm.generate(summary_prompt)
        
        # 2. Extract entities via Graphiti
        entities = await self.graphiti.extract_entities(messages)
        
        # 3. Extract structured information via LLM
        extraction_prompt = f"""Analyze this conversation and extract:

{self._format_messages(messages)}

Return JSON with:
- key_topics: list of main topics discussed
- user_state: {{mood, confidence, focus}} detected
- outcomes: list of {{type, content}} for decisions/agreements
- open_threads: list of {{topic, status, context}} for unresolved items

JSON only, no explanation."""

        extracted = await self.llm.generate_json(extraction_prompt)
        
        # 4. Calculate metadata
        started_at = messages[0]["created_at"]
        ended_at = messages[-1]["created_at"]
        duration = (ended_at - started_at).total_seconds() / 60
        
        # 5. Store episode
        episode_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "summary": summary,
            "key_topics": extracted.get("key_topics", []),
            "entities_discussed": [e["name"] for e in entities],
            "user_state": extracted.get("user_state", {}),
            "outcomes": extracted.get("outcomes", []),
            "open_threads": extracted.get("open_threads", []),
            "message_count": len(messages),
            "duration_minutes": int(duration),
            "started_at": started_at.isoformat(),
            "ended_at": ended_at.isoformat()
        }
        
        result = await self.db.table("conversation_episodes")\
            .insert(episode_data)\
            .execute()
        
        return ConversationEpisode(**result.data[0])
    
    async def get_recent_episodes(
        self,
        user_id: str,
        limit: int = 5,
        min_salience: float = 0.1
    ) -> list[ConversationEpisode]:
        """Get recent episodes for context priming."""
        result = await self.db.table("conversation_episodes")\
            .select("*")\
            .eq("user_id", user_id)\
            .gte("current_salience", min_salience)\
            .order("ended_at", desc=True)\
            .limit(limit)\
            .execute()
        
        return [ConversationEpisode(**e) for e in result.data]
    
    async def get_open_threads(
        self,
        user_id: str,
        limit: int = 10
    ) -> list[dict]:
        """Get all unresolved threads across conversations."""
        episodes = await self.db.table("conversation_episodes")\
            .select("open_threads, ended_at, conversation_id")\
            .eq("user_id", user_id)\
            .not_("open_threads", "eq", "[]")\
            .order("ended_at", desc=True)\
            .limit(20)\
            .execute()
        
        threads = []
        for ep in episodes.data:
            for thread in ep["open_threads"]:
                thread["from_conversation"] = ep["conversation_id"]
                thread["conversation_ended"] = ep["ended_at"]
                threads.append(thread)
        
        return threads[:limit]
```

---

### US-220: Conversation Continuity Priming

**As a** user  
**I want** ARIA to remember our previous conversations  
**So that** every conversation feels like continuing with a colleague

#### Acceptance Criteria
- [ ] Create `ConversationPrimingService` 
- [ ] At conversation start, gather: recent episodes, open threads, high-salience facts
- [ ] Build context object for LLM
- [ ] Include relevant entities from Graphiti
- [ ] Format as natural "what I remember" context
- [ ] API endpoint: `GET /api/v1/memory/prime`
- [ ] Automatically called when new conversation starts
- [ ] Configurable context window limits
- [ ] Performance: priming < 500ms
- [ ] Integration with chat backend (US-401)

#### Technical Notes
```python
# src/memory/priming.py
from dataclasses import dataclass

@dataclass
class ConversationContext:
    recent_episodes: list[dict]
    open_threads: list[dict]
    salient_facts: list[dict]
    relevant_entities: list[dict]
    formatted_context: str

class ConversationPrimingService:
    MAX_EPISODES = 3
    MAX_THREADS = 5
    MAX_FACTS = 10
    SALIENCE_THRESHOLD = 0.3
    
    def __init__(
        self,
        conversation_service,
        salience_service,
        memory_service,
        graphiti_client
    ):
        self.conversations = conversation_service
        self.salience = salience_service
        self.memory = memory_service
        self.graphiti = graphiti_client
    
    async def prime_conversation(
        self,
        user_id: str,
        initial_message: str | None = None
    ) -> ConversationContext:
        """Gather context for starting a new conversation."""
        
        # 1. Get recent conversation episodes
        episodes = await self.conversations.get_recent_episodes(
            user_id=user_id,
            limit=self.MAX_EPISODES,
            min_salience=self.SALIENCE_THRESHOLD
        )
        
        # 2. Get open threads
        threads = await self.conversations.get_open_threads(
            user_id=user_id,
            limit=self.MAX_THREADS
        )
        
        # 3. Get high-salience facts
        facts = await self.memory.get_by_salience(
            user_id=user_id,
            min_salience=self.SALIENCE_THRESHOLD,
            limit=self.MAX_FACTS
        )
        
        # 4. If we have an initial message, get relevant entities
        entities = []
        if initial_message:
            # Extract entities from message
            mentioned = await self.graphiti.extract_entities_from_text(initial_message)
            # Get related entities from graph
            for entity in mentioned:
                related = await self.graphiti.get_entity_context(entity["name"])
                entities.extend(related)
        
        # 5. Format as natural context
        formatted = self._format_context(episodes, threads, facts, entities)
        
        return ConversationContext(
            recent_episodes=[self._episode_to_dict(e) for e in episodes],
            open_threads=threads,
            salient_facts=[f.dict() for f in facts],
            relevant_entities=entities,
            formatted_context=formatted
        )
    
    def _format_context(
        self,
        episodes: list,
        threads: list,
        facts: list,
        entities: list
    ) -> str:
        """Format context as natural language for LLM."""
        parts = []
        
        if episodes:
            parts.append("## Recent Conversations")
            for ep in episodes:
                parts.append(f"- {ep.summary}")
                if ep.outcomes:
                    outcomes_text = ", ".join([o["content"] for o in ep.outcomes[:2]])
                    parts.append(f"  Outcomes: {outcomes_text}")
        
        if threads:
            parts.append("\n## Open Threads")
            for thread in threads:
                parts.append(f"- {thread['topic']}: {thread['status']}")
        
        if facts:
            parts.append("\n## Key Facts I Remember")
            for fact in facts[:5]:
                parts.append(f"- {fact.content} (confidence: {fact.confidence:.0%})")
        
        if entities:
            parts.append("\n## Relevant Context")
            for entity in entities[:3]:
                parts.append(f"- {entity['name']}: {entity.get('summary', 'No summary')}")
        
        return "\n".join(parts)
    
    def _episode_to_dict(self, episode) -> dict:
        return {
            "summary": episode.summary,
            "topics": episode.key_topics,
            "ended_at": episode.ended_at.isoformat(),
            "open_threads": episode.open_threads
        }


# API Route
# src/api/routes/memory.py

@router.get("/prime")
async def prime_conversation(
    initial_message: str | None = None,
    user: dict = Depends(get_current_user)
):
    """Get context for starting a new conversation."""
    priming_service = ConversationPrimingService(...)
    context = await priming_service.prime_conversation(
        user_id=user["id"],
        initial_message=initial_message
    )
    return {
        "recent_context": context.recent_episodes,
        "open_threads": context.open_threads,
        "salient_facts": context.salient_facts,
        "formatted_context": context.formatted_context
    }
```

---

## Phase 2 Retrofit Completion Checklist

Before continuing Phase 4, verify:

- [ ] All 3 user stories completed
- [ ] All quality gates pass
- [ ] Salience decay calculating correctly
- [ ] Memory access being tracked
- [ ] Conversation episodes extracting properly
- [ ] Open threads being identified
- [ ] Priming returning relevant context
- [ ] Performance < 500ms for priming
- [ ] Tests cover decay math edge cases
- [ ] Integration with existing memory services working

---

## Integration with Existing Services

### Memory Service Updates

The existing `MemoryService` should be updated to use salience:

```python
# Update existing memory queries to include salience

async def query_memories(
    self,
    user_id: str,
    query: str,
    min_salience: float = 0.1  # NEW: filter by salience
) -> list[Memory]:
    """Query memories with salience filtering and access tracking."""
    results = await self.db.table("semantic_facts")\
        .select("*")\
        .eq("user_id", user_id)\
        .gte("current_salience", min_salience)\  # NEW
        .execute()
    
    # NEW: Record access for each result
    for mem in results.data:
        await self.salience_service.record_access(
            memory_id=mem["id"],
            memory_type="semantic",
            user_id=user_id,
            context=f"query: {query}"
        )
    
    return results.data
```

### Chat Backend Integration (US-401)

When implementing US-401 Chat Backend, integrate priming:

```python
@router.post("/message")
async def send_message(
    message: ChatMessage,
    user: dict = Depends(get_current_user)
):
    # 1. If new conversation, prime with context
    if not message.conversation_id:
        context = await priming_service.prime_conversation(
            user_id=user["id"],
            initial_message=message.content
        )
        # Include context in LLM prompt
    
    # 2. Continue with existing logic...
```

---

## Next Steps

After completing this retrofit:

1. Continue with Phase 4 Features (US-403 onwards)
2. The chat backend (US-401/402) now uses these services
3. All memory operations automatically track access
4. Conversations automatically generate episodes when idle

---

*Document Version: 1.0*  
*Created: February 2, 2026*
