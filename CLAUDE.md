# CLAUDE.md - ARIA Project Configuration

## Project Overview

ARIA (Autonomous Reasoning & Intelligence Agent) is an AI-powered Department Director for Life Sciences commercial teams. Premium SaaS at $200K/year.

**Key Value:** Solve the "72% admin trap" - sales reps spend most time on admin, not selling.

**AGI Vision:** ARIA should feel like a colleague, not a tool. She remembers everything, volunteers relevant information, adapts to user stress, and has opinions.

## Tech Stack

- **Backend:** Python 3.11+ / FastAPI / Uvicorn
- **Frontend:** React 18 / TypeScript / Vite / Tailwind CSS
- **Database:** Supabase (PostgreSQL + pgvector)
- **Knowledge Graph:** Graphiti on Neo4j
- **LLM:** Anthropic Claude API (claude-sonnet-4-20250514)
- **Video:** Tavus + Daily.co
- **Integrations:** Composio for OAuth

## Commands

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000
pytest tests/ -v
mypy src/ --strict
ruff check src/
ruff format src/

# Frontend
cd frontend
npm install
npm run dev
npm run build
npm run typecheck
npm run lint
npm run test
```

## Project Structure

```
aria/
├── backend/src/
│   ├── api/routes/      # FastAPI route handlers
│   ├── agents/          # ARIA's specialized agents
│   ├── memory/          # Six-type memory system + AGI services
│   ├── core/            # Config, OODA loop, LLM client
│   ├── intelligence/    # AGI capabilities (predictive, cognitive, etc.)
│   └── db/              # Supabase and Graphiti clients
├── frontend/src/
│   ├── components/      # React components
│   ├── pages/           # Route pages
│   ├── hooks/           # Custom React hooks
│   └── api/             # API client functions
└── docs/                # PRD and phase documents
```

## Code Style

### Python
- Use type hints on all functions
- Async/await for I/O operations
- Pydantic for request/response models
- Docstrings on public functions
- No `print()` - use `logging`

### TypeScript
- Strict mode enabled
- Named exports (not default)
- Interface over type where possible
- React functional components with hooks
- Tailwind for styling (no custom CSS files)

## Key Patterns

### Memory System
ARIA has six memory types. Always consider which memory type applies:
1. **Working** - Current conversation (in-memory)
2. **Episodic** - Past events (Graphiti)
3. **Semantic** - Facts with confidence (Graphiti + pgvector)
4. **Procedural** - Workflows (Supabase)
5. **Prospective** - Future tasks (Supabase)
6. **Lead** - Sales pursuit tracking (Graphiti + Supabase)

### OODA Loop
ARIA's cognitive process: Observe → Orient → Decide → Act
Always implement this loop for complex tasks.

### Agents
Six core agents: Hunter, Analyst, Strategist, Scribe, Operator, Scout
Extend `BaseAgent` class for any new agents.

---

## AGI Development Patterns

### The Colleague Test
Before completing any user-facing feature, ask:
> "Would a user describe this behavior as coming from a colleague or a tool?"

| Colleague Behavior | Implementation |
|-------------------|----------------|
| References shared history | Use conversation_episodes |
| Volunteers relevant info | Use proactive_memory |
| Adapts to your stress | Use cognitive_load_monitor |
| Remembers everything | Use salience decay (not deletion) |
| Has opinions | Phase 8 personality system |

### Memory Salience

Every memory access should strengthen salience. Every query should update `last_accessed_at`:

```python
async def get_facts_about(self, user_id: str, entity: str) -> list[SemanticFact]:
    facts = await self.db.table("semantic_facts")...
    
    # Strengthen salience on access
    for fact in facts:
        await self.salience_service.record_access(fact.id, "semantic")
    
    return facts
```

**Salience Formula:**
```
current_salience = (original_salience + access_boost) × decay_factor
decay_factor = 0.5 ^ (days_since_last_access / half_life)
```

- Default half-life: 30 days
- Access boost: 0.1 per retrieval
- Minimum salience: 0.01 (never truly forgotten)

### Cognitive Load Awareness

Detect user state and adapt responses:

```python
# In chat handlers, always check cognitive load
load_state = await cognitive_load_monitor.estimate_load(user_id, recent_messages)

if load_state.is_high:
    # Be concise, offer to handle things
    context["response_style"] = "concise"
else:
    # Full detail is fine
    context["response_style"] = "detailed"
```

**Indicators of High Load:**
- Short, terse messages
- Multiple rapid messages
- Typos/errors
- Time-of-day patterns
- Calendar density

### Proactive Memory Surfacing

Don't just answer questions - volunteer relevant context:

```python
# Before generating response, find volunteerable memories
insights = await proactive_memory.find_volunteerable_context(
    user_id=user_id,
    current_message=message.content,
    conversation=conversation.messages
)

# Include top insights in LLM context
if insights:
    context["proactive_insights"] = insights[:2]
```

**Trigger Types:**
- Pattern matches (same topic mentioned in past)
- Connection discoveries (new link between entities)
- Temporal triggers (anniversaries, deadlines)
- Goal relevance (relates to active goals)

### Prediction Registration

When ARIA makes predictions, register them for later validation:

```python
# After generating response, extract and register predictions
predictions = await extract_predictions(response)
for pred in predictions:
    await prediction_service.register(
        user_id=user_id,
        prediction=pred.content,
        expected_resolution=pred.timeframe,
        confidence=pred.confidence
    )
```

### Conversation Continuity

End every conversation by extracting durable content:

```python
async def end_conversation(conversation_id: str):
    # 1. Generate summary
    summary = await summarize_conversation(conversation)
    
    # 2. Extract facts to semantic memory
    facts = await extract_facts(conversation.messages)
    await store_facts(facts)
    
    # 3. Store as episode for future reference
    await store_conversation_episode(
        conversation_id=conversation_id,
        summary=summary,
        key_topics=extract_topics(conversation),
        open_threads=find_unresolved_items(conversation)
    )
```

### Start of Conversation Priming

Prime new conversations with relevant context:

```python
async def prime_conversation(user_id: str):
    # Get recent episodes
    episodes = await conversation_service.get_recent_episodes(user_id, limit=3)
    
    # Find open threads
    open_threads = [e.open_threads for e in episodes if e.open_threads]
    
    # Get high-salience memories
    salient_facts = await memory.get_by_salience(user_id, threshold=0.7, limit=5)
    
    return {
        "recent_context": episodes,
        "open_threads": open_threads,
        "salient_facts": salient_facts
    }
```

---

## AGI Quality Checklist

When implementing any feature, ask:

- [ ] **Salience:** Does this update memory access timestamps?
- [ ] **Predictions:** Are we registering any predictions for validation?
- [ ] **Cognitive Load:** Does response adapt to user state?
- [ ] **Proactive:** Are we surfacing relevant memories unprompted?
- [ ] **Continuity:** Will this be remembered next conversation?
- [ ] **Causal:** Are we capturing cause-effect relationships?
- [ ] **Outcomes:** Are we recording results for learning?

---

## Intelligence Pulse Patterns

### Salience Scoring
All signals scored by weighted factors:
- Goal relevance (0.30)
- Time sensitivity (0.25)
- Value impact (0.20)
- User preference (0.15)
- Surprise factor (0.10)

### Delivery Routing
```
Score 90-100: Immediate interrupt
Score 70-89:  Next check-in mention  
Score 50-69:  Morning brief
Score 30-49:  Weekly digest
Score <30:    Silent log only
```

---

## Predictive Processing Patterns

### Prediction Types
```python
class PredictionType(Enum):
    USER_ACTION = "user_action"      # What user will do
    EXTERNAL_EVENT = "external"      # Market/competitor events
    DEAL_OUTCOME = "deal_outcome"    # Lead progression
    TIMING = "timing"                # When something will happen
```

### Confidence Calibration
Track prediction outcomes to calibrate confidence:
```python
async def update_calibration(prediction_id: str, actual_outcome: str):
    prediction = await get_prediction(prediction_id)
    was_correct = prediction.predicted_outcome == actual_outcome
    
    # Update calibration curve
    await calibration_service.record_outcome(
        confidence=prediction.confidence,
        was_correct=was_correct,
        prediction_type=prediction.type
    )
```

---

## Important Notes

- All database tables must have RLS policies
- User isolation is critical (multi-tenant)
- Never expose internal errors to users
- Log all memory operations for audit
- CRM sync: CRM wins for structured data, ARIA wins for insights
- Health scores are 0-100, recalculate on events
- **Memory never truly deletes** - use salience decay instead
- **Every interaction strengthens memory** - record all access

## Documentation

Read the PRD files before implementing:
- `docs/ARIA_PRD.md` - Main overview
- `docs/PHASE_*.md` - Detailed user stories per phase
- `docs/PHASE_2_RETROFIT.md` - Memory foundations (implement before Phase 4)
- `docs/PHASE_7_JARVIS.md` - Jarvis Intelligence
- `docs/PHASE_8_AGI_COMPANION.md` - AGI Companion

Always complete user stories in order within each phase.

## Testing

Every feature needs:
- Unit tests for business logic
- Integration tests for API endpoints
- Quality gates must pass before moving on

### AGI-Specific Testing
- Test salience decay over simulated time
- Test cognitive load detection with various message patterns
- Test proactive surfacing relevance
- Test prediction accuracy tracking

## Do Not

- Skip RLS policies on tables
- Use `any` type in TypeScript
- Commit .env files
- Hardcode API keys
- Ignore error handling
- Skip input validation
- **Delete memories** - decay them instead
- **Answer without checking context** - always prime conversations
- **Ignore user state** - adapt to cognitive load
