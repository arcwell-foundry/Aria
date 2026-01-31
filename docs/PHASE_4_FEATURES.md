# Phase 4: Core Features
## ARIA PRD - Implementation Phase 4

**Prerequisites:** Phase 3 Complete  
**Estimated Stories:** 15  
**Focus:** Chat Interface, Daily Briefing, Pre-Meeting Research, Email Drafting, Battle Cards

---

## Overview

Phase 4 implements the user-facing features that deliver daily value. This includes:

- Full ARIA Chat Interface
- Daily Morning Briefing
- Pre-Meeting Research & Briefs
- Email Draft Generation
- Competitive Battle Cards

**Completion Criteria:** User experiences ARIA as a functional Department Director with proactive daily intelligence and reactive assistance.

---

## User Stories

### US-401: ARIA Chat Backend

**As a** user  
**I want** to chat with ARIA  
**So that** I can get assistance on demand

#### Acceptance Criteria
- [ ] `POST /api/v1/chat/message` - Send message, get response
- [ ] Streaming response support (SSE)
- [ ] Memory context included in LLM calls
- [ ] OODA loop triggered for actionable requests
- [ ] Conversation history persisted
- [ ] Message references goals when relevant
- [ ] Performance: first token < 1s
- [ ] Integration tests for chat flow

#### Technical Notes
```python
# src/api/routes/chat.py
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from src.core.ooda import OODALoop
from src.memory import MemorySystem

router = APIRouter(prefix="/chat", tags=["chat"])

class ChatMessage(BaseModel):
    content: str
    conversation_id: str | None = None
    goal_id: str | None = None

@router.post("/message")
async def send_message(
    message: ChatMessage,
    user: dict = Depends(get_current_user)
):
    # 1. Load/create conversation
    # 2. Query relevant memories
    # 3. Build context for LLM
    # 4. Determine if OODA loop needed
    # 5. Generate response
    # 6. Extract and store new memories
    # 7. Return response
    pass

@router.post("/message/stream")
async def send_message_stream(
    message: ChatMessage,
    user: dict = Depends(get_current_user)
):
    async def generate():
        # Yield tokens as they're generated
        pass
    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

### US-402: ARIA Chat UI

**As a** user  
**I want** a chat interface with ARIA  
**So that** I can interact naturally

#### Acceptance Criteria
- [ ] `/dashboard/aria` route with chat interface
- [ ] Message input with send button and Enter key
- [ ] Message history displayed in scrollable area
- [ ] ARIA messages styled distinctly from user
- [ ] Streaming response with typing indicator
- [ ] Markdown rendering in responses
- [ ] Code block syntax highlighting
- [ ] Copy button on code blocks
- [ ] Mobile responsive

---

### US-403: Conversation Management

**As a** user  
**I want** to manage my conversations  
**So that** I can organize my ARIA interactions

#### Acceptance Criteria
- [ ] `GET /api/v1/chat/conversations` - List conversations
- [ ] Sidebar shows recent conversations
- [ ] Click conversation to load history
- [ ] New conversation button
- [ ] Delete conversation option
- [ ] Conversation titles (auto-generated or editable)
- [ ] Search conversations

---

### US-404: Daily Briefing Backend

**As a** user  
**I want** a daily morning briefing  
**So that** I start each day informed

#### Acceptance Criteria
- [ ] `daily_briefings` table created
- [ ] Scheduled job generates briefing at configured time
- [ ] Briefing includes: calendar overview, priority leads, market signals
- [ ] `GET /api/v1/briefings/today` - Get today's briefing
- [ ] `GET /api/v1/briefings` - List past briefings
- [ ] Briefing content stored for reference
- [ ] Regenerate option if data changes

#### SQL Schema
```sql
CREATE TABLE daily_briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    briefing_date DATE NOT NULL,
    content JSONB NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    delivered_at TIMESTAMPTZ,
    delivery_method TEXT,  -- email, app, video
    UNIQUE(user_id, briefing_date)
);
```

#### Briefing Content Structure
```json
{
  "summary": "Executive summary paragraph",
  "calendar": {
    "meeting_count": 5,
    "key_meetings": [
      {"time": "10:00", "title": "Acme Discovery Call", "attendees": [...]}
    ]
  },
  "leads": {
    "hot_leads": [...],
    "needs_attention": [...],
    "recently_active": [...]
  },
  "signals": {
    "company_news": [...],
    "market_trends": [...],
    "competitive_intel": [...]
  },
  "tasks": {
    "overdue": [...],
    "due_today": [...]
  }
}
```

---

### US-405: Daily Briefing UI

**As a** user  
**I want** to view my daily briefing  
**So that** I can quickly get up to speed

#### Acceptance Criteria
- [ ] `/dashboard` shows today's briefing prominently
- [ ] Collapsible sections for each briefing area
- [ ] Quick actions from briefing items
- [ ] Calendar items link to meeting details
- [ ] Lead items link to Lead Memory
- [ ] Refresh button to regenerate
- [ ] Historical briefings accessible

---

### US-406: Pre-Meeting Research Backend

**As a** user  
**I want** auto-generated meeting briefs  
**So that** I'm prepared for every meeting

#### Acceptance Criteria
- [ ] `meeting_briefs` table created
- [ ] Triggered 24h before meetings (configurable)
- [ ] Research includes: attendee profiles, company info, talking points
- [ ] `GET /api/v1/meetings/{id}/brief` - Get meeting brief
- [ ] On-demand generation option
- [ ] Brief stored for reference

#### SQL Schema
```sql
CREATE TABLE meeting_briefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    calendar_event_id TEXT NOT NULL,
    meeting_title TEXT,
    meeting_time TIMESTAMPTZ,
    brief_content JSONB NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, calendar_event_id)
);

CREATE TABLE attendee_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    title TEXT,
    company TEXT,
    linkedin_url TEXT,
    profile_data JSONB,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);
```

#### Brief Content Structure
```json
{
  "summary": "One paragraph meeting context",
  "attendees": [
    {
      "name": "John Smith",
      "title": "VP Procurement",
      "company": "Acme Corp",
      "linkedin": "...",
      "background": "15 years in life sciences procurement...",
      "recent_activity": ["Published article on...", "Promoted in..."],
      "talking_points": ["Ask about Q3 budget cycle", "Mention mutual connection at..."]
    }
  ],
  "company": {
    "name": "Acme Corp",
    "industry": "Biotech",
    "size": "500-1000",
    "recent_news": [...],
    "our_history": "First contacted 3 months ago..."
  },
  "suggested_agenda": [...],
  "risks_opportunities": [...]
}
```

---

### US-407: Meeting Brief UI

**As a** user  
**I want** to view meeting briefs  
**So that** I can prepare quickly

#### Acceptance Criteria
- [ ] Meeting brief card in daily briefing
- [ ] Dedicated brief view page
- [ ] Attendee profiles with photos (when available)
- [ ] Expandable sections
- [ ] Print/export option
- [ ] Notes field for user additions
- [ ] Quick access from calendar

---

### US-408: Email Drafting Backend

**As a** user  
**I want** ARIA to draft emails  
**So that** I can communicate efficiently

#### Acceptance Criteria
- [ ] `POST /api/v1/drafts/email` - Generate email draft
- [ ] Uses Digital Twin for style matching
- [ ] Context-aware (pulls from Lead Memory, history)
- [ ] Multiple draft options (formal, friendly)
- [ ] Draft storage for review
- [ ] Edit and regenerate capability
- [ ] Send integration (via Composio/OAuth)

#### Technical Notes
```python
class EmailDraftRequest(BaseModel):
    recipient_email: str
    subject_hint: str | None = None
    purpose: str  # intro, follow_up, proposal, thank_you
    context: str | None = None  # Additional context
    tone: Literal["formal", "friendly", "urgent"] = "friendly"
    lead_memory_id: str | None = None  # Pull context from lead

class EmailDraft(BaseModel):
    id: str
    to: str
    subject: str
    body: str
    style_match_score: float
    created_at: datetime
```

---

### US-409: Email Draft UI

**As a** user  
**I want** to review and edit email drafts  
**So that** I maintain control

#### Acceptance Criteria
- [ ] Draft composer with rich text editor
- [ ] Preview as recipient would see
- [ ] Edit subject, body, tone
- [ ] Regenerate button
- [ ] Style match score displayed
- [ ] Send button (with confirmation)
- [ ] Save as template option

---

### US-410: Battle Cards Backend

**As a** user  
**I want** competitive battle cards  
**So that** I can handle competitive situations

#### Acceptance Criteria
- [ ] `battle_cards` table created
- [ ] Scout agent monitors competitors
- [ ] Auto-generated from web research
- [ ] Manual override/additions supported
- [ ] `GET /api/v1/battlecards` - List cards
- [ ] `GET /api/v1/battlecards/{competitor}` - Get specific card
- [ ] Change detection and alerts

#### SQL Schema
```sql
CREATE TABLE battle_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    competitor_name TEXT NOT NULL,
    competitor_data JSONB NOT NULL,
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    update_source TEXT,  -- auto, manual
    UNIQUE(company_id, competitor_name)
);

CREATE TABLE battle_card_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    battle_card_id UUID REFERENCES battle_cards(id),
    change_type TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### Battle Card Structure
```json
{
  "competitor": "Competitor Inc",
  "overview": "Brief description...",
  "strengths": ["Strong brand", "Large customer base"],
  "weaknesses": ["Slow implementation", "Limited customization"],
  "pricing": {
    "model": "Per seat",
    "range": "$50-200/user/month"
  },
  "differentiation": [
    {
      "area": "Memory System",
      "our_advantage": "Six-type cognitive memory vs. basic context"
    }
  ],
  "objection_handlers": [
    {
      "objection": "They're more established",
      "response": "While they've been around longer, our vertical focus..."
    }
  ],
  "recent_news": [...],
  "last_updated": "2026-01-30"
}
```

---

### US-411: Battle Cards UI

**As a** user  
**I want** to view battle cards  
**So that** I can access competitive intel

#### Acceptance Criteria
- [ ] `/dashboard/battlecards` route
- [ ] Card list with search/filter
- [ ] Detailed card view
- [ ] Side-by-side comparison option
- [ ] Quick access during calls (floating widget)
- [ ] Edit capability for manual additions
- [ ] Change history visible

---

### US-412: Market Signal Detection

**As a** user  
**I want** market signals detected automatically  
**So that** I stay informed about accounts

#### Acceptance Criteria
- [ ] `market_signals` table created
- [ ] Signal types: funding, hiring, leadership, product, partnership
- [ ] Scout agent runs on schedule
- [ ] Deduplication of signals
- [ ] Relevance scoring
- [ ] Integration with Lead Memory
- [ ] Surfaced in daily briefing

#### SQL Schema
```sql
CREATE TABLE market_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    company_name TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    source_url TEXT,
    relevance_score FLOAT,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    read_at TIMESTAMPTZ
);

CREATE TABLE monitored_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id),
    entity_type TEXT NOT NULL,  -- company, person, topic
    entity_name TEXT NOT NULL,
    monitoring_config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

### US-413: Settings Page - Integrations

**As a** user  
**I want** to manage my integrations  
**So that** ARIA connects to my tools

#### Acceptance Criteria
- [ ] `/dashboard/settings/integrations` route
- [ ] Connect Google Calendar via OAuth
- [ ] Connect Gmail via OAuth
- [ ] Connect Outlook via OAuth
- [ ] Connect Salesforce/HubSpot via OAuth
- [ ] Status indicator for each integration
- [ ] Disconnect option
- [ ] Sync status and last sync time

---

### US-414: Settings Page - Preferences

**As a** user  
**I want** to configure ARIA preferences  
**So that** she works my way

#### Acceptance Criteria
- [ ] `/dashboard/settings/preferences` route
- [ ] Briefing time preference
- [ ] Meeting brief lead time (24h, 12h, etc.)
- [ ] Notification preferences
- [ ] Default tone for communications
- [ ] Competitors to track
- [ ] Save and apply immediately

---

### US-415: Notification System

**As a** user  
**I want** notifications from ARIA  
**So that** I don't miss important updates

#### Acceptance Criteria
- [ ] In-app notification bell
- [ ] Notification types: briefing ready, signal detected, task due
- [ ] Mark as read
- [ ] Click to navigate to relevant item
- [ ] Email notification option (configurable)
- [ ] Notification preferences in settings

---

## Phase 4 Completion Checklist

Before moving to Phase 5, verify:

- [ ] All 15 user stories completed
- [ ] All quality gates pass
- [ ] Chat interface fully functional
- [ ] Daily briefing generating correctly
- [ ] Meeting briefs auto-generated
- [ ] Email drafts match user style
- [ ] Battle cards populated
- [ ] Market signals detecting
- [ ] Integrations connecting via OAuth
- [ ] Notifications working

---

## Next Phase

Proceed to `PHASE_5_LEAD_MEMORY.md` for Lead Memory System implementation.
