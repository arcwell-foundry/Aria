# ARIA Claude Code Execution Plan
## Session-by-Session Implementation Guide

**Version:** 1.0 | **Date:** February 11, 2026 | **Companion to:** IDD v3.0 + Frontend Architecture v1.0

---

## MANDATORY CONTEXT FOR EVERY SESSION

Copy-paste this header into EVERY Claude Code session:

```
CRITICAL CONTEXT — READ BEFORE WRITING ANY CODE:

1. ARIA is NOT a SaaS application. ARIA is an autonomous AI colleague with a visual 
   presence (Tavus avatar), voice, and the ability to control the entire app experience.

2. The user does NOT tell ARIA what to do — ARIA proposes and the user approves.
   NO forms for user input (except Settings). NO "Add New" buttons. NO CRUD pages.

3. ARIA controls the UI. Backend responses include ui_commands[] that the frontend's 
   UICommandExecutor processes to navigate screens, highlight elements, and update panels.

4. Three interaction modalities: text chat, voice (space-to-talk), AI avatar (Tavus).
   All share the same backend engine, memory, and execution pipeline.

5. Memory is PERSISTENT. No compaction, no TTL, no automatic deletion. Six memory types 
   stored in Supabase + Graphiti/Neo4j. Sessions persist across tab closes and modality switches.

6. Architecture: Three-column layout (sidebar + center workspace + ARIA Intelligence Panel).
   The right panel adapts its content based on current route/context.

7. Dark theme for ARIA Workspace and Dialogue Mode. Light theme for content pages.

8. When in doubt: "Is ARIA driving this, or is the user?" If user is driving, design is wrong.

Reference docs: ARIA_IDD_v3.md, ARIA_Frontend_Architecture.md, CLAUDE.md
```

---

## Sprint 0: Foundation (Estimated: 1-2 days)

### Session 0A: Database Migrations

**Goal:** Run all 43 missing database migrations so the backend can persist data.

```
PROMPT:

[Paste mandatory context header]

TASK: Run all missing database migrations for ARIA's Supabase database.

CURRENT STATE: The audit found 43 missing database tables. The backend code references 
these tables but they don't exist, so nothing persists.

WHAT TO DO:
1. Read AUDIT_WIRING.md and AUDIT_DATABASE.md for the list of missing tables
2. Read the existing migration files in backend/src/db/migrations/ (if any)
3. Read the model definitions in backend/src/ to understand table schemas
4. Create Supabase migrations for ALL missing tables including:
   - episodic_memories, semantic_facts, procedural_patterns
   - conversations, messages
   - goals, goal_tasks, goal_progress
   - agent_executions, agent_results
   - actions, action_approvals
   - signals, briefings
   - user_sessions (NEW — for cross-modal session persistence)
   - Any others referenced in code but missing from DB
5. Enable Row Level Security (RLS) on ALL tables
6. Create appropriate indexes (user_id, created_at, entity lookups)
7. Run migrations and verify

CRITICAL: Include a user_sessions table with this schema:
- session_id (UUID, primary key)
- user_id (UUID, foreign key to auth.users)
- session_data (JSONB — stores full UnifiedSession object)
- is_active (boolean, default true)
- day_date (date — for new-day detection)
- created_at, updated_at (timestamptz)
RLS: Users can only access their own sessions.

DO NOT skip any tables. The entire memory and execution system depends on this.
```

### Session 0B: Chat Endpoint Fix + Memory Wiring

**Goal:** Fix the chat endpoint mismatch and wire memory persistence.

```
PROMPT:

[Paste mandatory context header]

TASK: Fix the chat system so it actually works end-to-end.

CURRENT PROBLEMS (from AUDIT_WIRING.md):
1. Frontend calls POST /chat/message but backend serves POST /chat
2. Memory system exists but can't persist (tables were missing, now fixed)
3. Digital Twin is not injected into chat responses
4. Only the Hunter agent is wired; other 5 agents sit idle

WHAT TO DO:

1. Fix the chat endpoint:
   - Either rename backend endpoint to match /chat/message
   - OR update frontend to call /chat
   - Ensure the request/response schema matches

2. Wire memory persistence:
   - After each conversation turn, store to episodic_memories table
   - Extract semantic facts and store with confidence scores
   - Update the user's Digital Twin with new observations
   - Read from existing memories to inform responses

3. Inject Digital Twin into chat:
   - When building the LLM prompt, include the user's Digital Twin context
   - This makes ARIA feel like she knows the user

4. Update the chat response schema to include:
   - message (string)
   - rich_content (array of typed components — can be empty for now)
   - ui_commands (array of UICommand objects — can be empty for now)
   - suggestions (array of 2-3 contextual suggestions)
   
5. Test: Send a message, verify it persists in episodic_memories, 
   verify Digital Twin context appears in response.

FILES TO EXAMINE:
- backend/src/services/chat.py (or chat_service.py)
- backend/src/memory/ (all memory type implementations)
- backend/src/models/digital_twin.py
- frontend/src/api/chat.ts (the frontend call)
```

### Session 0C: Extract Design Primitives

**Goal:** Extract reusable atomic components from the old frontend.

```
PROMPT:

[Paste mandatory context header]

TASK: Extract reusable design primitives from the existing frontend and set up 
the new component library structure.

WHAT TO DO:

1. Examine the existing frontend/src/components/ directory
2. Identify atomic components that are framework-agnostic:
   - Button, Input, Card, Badge, Skeleton, ProgressBar, Avatar, Tooltip
   - Any data display atoms (HealthScoreBadge, etc.)
3. Copy these to a new structure:
   frontend/src/components/primitives/
4. Clean them up:
   - Remove any page-level logic
   - Ensure they work with both dark and light themes
   - Use CSS variables (var(--text-primary), etc.) not hardcoded colors
   - Add TypeScript prop interfaces
5. Move ALL existing page components to:
   frontend/src/_deprecated/
6. Set up the new directory structure per ARIA_Frontend_Architecture.md:
   - components/primitives/
   - components/shell/
   - components/conversation/
   - components/rich/
   - components/avatar/
   - components/pages/
   - core/
   - contexts/
   - stores/
   - hooks/
   - types/
7. Set up the theme system CSS variables (dark + light)
8. Install new dependencies if needed: zustand

DO NOT delete old components — move to _deprecated/.
DO NOT build new components yet — just set up structure and extract primitives.
```

---

## Sprint 1: Core Shell + ARIA Workspace (Estimated: 3-4 days)

### Session 1A: AppShell + Routing + Session

**Goal:** Build the three-column layout, sidebar, routing, and session management.

```
PROMPT:

[Paste mandatory context header]

TASK: Build the core application shell with three-column layout, 7-item sidebar, 
route definitions, and session management.

WHAT TO BUILD:

1. AppShell.tsx — Three-column layout:
   - Left: Sidebar (240px, always visible)
   - Center: Outlet (flexible, renders current route)
   - Right: IntelPanel (320px, hidden on ARIA Workspace and Dialogue Mode)
   - Full height, no scroll on shell (children scroll internally)

2. Sidebar.tsx — 7 items:
   - ARIA (default, icon: graphic_eq) — routes to /
   - Briefing (icon: today) — routes to /briefing
   - Pipeline (icon: groups) — routes to /pipeline
   - Intelligence (icon: shield) — routes to /intelligence
   - Communications (icon: mail) — routes to /communications
   - Actions (icon: bolt) — routes to /actions
   - Settings (icon: settings) — routes to /settings (at bottom)
   - User avatar + name at very bottom
   - ARIA Pulse indicator (subtle blue glow animation)
   - Badge support on each item (for notification counts)
   - Always dark theme (#0F1117 background)
   - Active item: electric blue (#2E66FF) background

3. routes.tsx — Route definitions per ARIA_Frontend_Architecture.md
   - All Layer 2 pages can be placeholder components for now

4. SessionContext.tsx + SessionManager.ts:
   - On app load, check Supabase for active session
   - If same day: resume session
   - If new day: archive old, create new
   - Persist session to Supabase every 30 seconds
   - Track current_route, active_modality, conversation_thread

5. ThemeContext.tsx:
   - Determine theme based on current route
   - Dark for / and /briefing
   - Light for /pipeline, /intelligence, /communications, /actions
   - Set data-theme attribute on document root

VISUAL REFERENCE: Think of the mockups — sidebar always dark on left, 
center content changes, right panel on content pages only.

CRITICAL: The sidebar MUST feel premium. Use Instrument Serif for the "ARIA" logo text.
Subtle transitions. No chunky borders. The ARIA Pulse should be an almost-imperceptible 
blue glow that pulses slowly when ARIA is active.
```

### Session 1B: WebSocket + ARIA Workspace

**Goal:** Build the WebSocket connection and the primary ARIA conversation workspace.

```
PROMPT:

[Paste mandatory context header]

TASK: Build the WebSocket manager and ARIA Workspace (the primary conversation interface).

WHAT TO BUILD:

1. WebSocketManager.ts:
   - Connect to backend WebSocket at /ws/{user_id}?session={session_id}
   - Auto-reconnect with exponential backoff (max 10 attempts)
   - Heartbeat every 30 seconds
   - Event registration (on/off pattern)
   - Send helper method
   - All events typed (see WS_EVENTS in ARIA_Frontend_Architecture.md)

2. conversationStore.ts (Zustand):
   - messages: Message[]
   - isStreaming: boolean
   - addMessage, updateMessage, setStreaming actions
   - Message type includes: id, role (aria|user), content, rich_content[], 
     ui_commands[], suggestions[], timestamp

3. ConversationThread.tsx:
   - Scrollable message list
   - Auto-scroll to bottom on new messages
   - Messages from ARIA: left-aligned, elevated dark background, 
     Instrument Serif for key insights
   - Messages from user: right-aligned, standard background
   - Rich content rendered inline via RichContentRenderer
   - Streaming indicator when ARIA is thinking

4. MessageBubble.tsx:
   - Renders a single message
   - ARIA messages can contain rich_content[] → each rendered by RichContentRenderer
   - User messages are plain text
   - Timestamps in JetBrains Mono, muted color

5. InputBar.tsx:
   - Full-width input at bottom of workspace
   - Left: microphone button (for voice)
   - Center: text input ("Ask ARIA anything..." placeholder)
   - Right: "SPACE TO TALK" badge + send button (electric blue)
   - Subtle gradient glow behind the bar (from mockup)
   - On submit: send via WebSocket, add user message to store

6. SuggestionChips.tsx:
   - Renders 2-3 contextual suggestion pills below input bar
   - "ARIA IS LISTENING • 3 SUGGESTIONS AVAILABLE"
   - Clicking a chip sends it as a message

7. ARIAWorkspace page component:
   - Full width (no right panel)
   - ConversationThread + InputBar + SuggestionChips
   - Dark theme (#0A0A0B background)
   - Listen for aria.message WebSocket events

CRITICAL VISUAL DETAILS:
- ARIA's messages have a LEFT border in electric blue (2px), not a bubble background
- User messages have a subtle surface background with rounded corners
- The input bar has a gradient glow effect behind it (from mockup)
- JetBrains Mono for timestamps and system labels
- Instrument Serif italic for section headings within ARIA's messages
```

### Session 1C: UICommandExecutor + IntelPanel

**Goal:** Build ARIA's UI control system and the context-adaptive right panel.

```
PROMPT:

[Paste mandatory context header]

TASK: Build the UICommandExecutor (ARIA's ability to control the UI) and 
the IntelPanel (context-adaptive right panel).

WHAT TO BUILD:

1. UICommandExecutor.ts:
   - Receives UICommand[] from ARIA's WebSocket messages
   - Executes commands sequentially with 150ms delay between for visual effect
   - Command types: navigate, highlight, update_intel_panel, scroll_to, 
     switch_mode, show_notification, update_sidebar_badge, open_modal
   - Highlight effects: CSS classes for glow, pulse, outline
   - Uses React Router's navigate function for route changes
   - Updates SessionManager when navigating

2. useUICommands.ts hook:
   - Wraps UICommandExecutor
   - Provides executeUICommands(commands) function
   - Auto-initializes with router navigate function
   - Listens for aria.message events and auto-executes ui_commands

3. IntelPanelContext.tsx:
   - Stores current panel content, title
   - update(content) method
   - Reacts to route changes (auto-selects appropriate modules)

4. IntelPanel.tsx:
   - 320px right sidebar
   - Header: title + "..." menu
   - Scrollable content area
   - Renders different modules based on current route:
     - Pipeline → AlertsModule, BuyingSignalsModule
     - Intelligence → CompetitiveIntelModule, NewsAlertsModule  
     - Communications → WhyIWroteThisModule, ToneModule, AnalysisModule
     - Lead Detail → StrategicAdviceModule, ObjectionsModule, NextStepsModule
     - Actions → AgentStatusModule
   - Light theme when on content pages, dark when on dark pages

5. IntelPanel modules (create all as stubs with proper interfaces):
   - AlertsModule.tsx
   - BuyingSignalsModule.tsx
   - CompetitiveIntelModule.tsx
   - NewsAlertsModule.tsx
   - WhyIWroteThisModule.tsx
   - ToneModule.tsx
   - AnalysisModule.tsx
   - NextBestActionModule.tsx
   - StrategicAdviceModule.tsx
   - ObjectionsModule.tsx
   - NextStepsModule.tsx
   - AgentStatusModule.tsx
   - CRMSnapshotModule.tsx
   - ChatInputModule.tsx (mini chat input for contextual questions)

   Each module should accept typed props and render a reasonable placeholder 
   with the correct layout. We'll wire real data later.

6. Add CSS for highlight effects:
   .aria-highlight-glow — box-shadow with electric blue
   .aria-highlight-pulse — scale animation
   .aria-highlight-outline — outline with offset

CRITICAL: The IntelPanel must feel like ARIA is always present. Even as stubs, 
each module should show the RIGHT kind of content for its context. Use realistic 
placeholder data that looks like what ARIA would actually surface.
```

---

## Sprint 2: Execution Engine (Estimated: 3-4 days)

### Session 2A: GoalExecutionService

**Goal:** Build the core orchestrator that makes agents actually execute.

```
PROMPT:

[Paste mandatory context header]

TASK: Build the GoalExecutionService — the "ignition" that makes ARIA's agents 
actually execute goals.

CURRENT STATE: All 6 agents exist as classes but none execute. The OODA loop 
is documented but doesn't dispatch. Goals have no execution pipeline.

WHAT TO BUILD:

1. GoalExecutionService class (backend/src/services/goal_execution.py):

   Methods:
   - propose_goals(user_id) → Generate 3-4 goal proposals using context from 
     memory, CRM, calendar, market signals. Returns GoalProposal[] with rationale.
   
   - plan_goal(goal_id) → Decompose approved goal into sub-tasks, assign agents, 
     create timeline. Returns ExecutionPlan with phases.
   
   - execute_goal(goal_id) → Start execution. Spawn agents for Phase 1 tasks. 
     Begin OODA loop monitoring. Send progress via WebSocket.
   
   - check_progress(goal_id) → OODA Observe phase. Gather agent statuses, 
     check for blockers, evaluate progress against timeline.
   
   - handle_agent_result(agent_id, result) → Process agent output. Classify 
     risk. Route to appropriate channel (auto-execute, notify, or require approval).
   
   - route_action(action) → Risk classification:
     LOW → auto-execute, log to Activity
     MEDIUM → notify, auto-execute if not rejected in 30 min
     HIGH → present approval card in conversation via WebSocket
     CRITICAL → always require explicit approval
   
   - report_progress(goal_id) → Generate progress update for user.
   
   - complete_goal(goal_id) → Mark complete, trigger retrospective, 
     store learnings in procedural memory.

2. Wire ALL 6 agents to the execution pipeline:
   - Hunter: receives lead discovery tasks
   - Analyst: receives research/analysis tasks
   - Strategist: receives planning/positioning tasks
   - Scribe: receives drafting tasks
   - Operator: receives CRM/calendar/integration tasks
   - Scout: receives monitoring/signal detection tasks
   
   Each agent should:
   - Accept a task context (from GoalExecutionService)
   - Execute via their existing logic
   - Return structured results
   - Store results in appropriate memory type

3. OODA Loop (make it actually run):
   - OBSERVE: Gather agent statuses, new data, signals
   - ORIENT: Analyze context (is goal on track? blockers? opportunities?)
   - DECIDE: Choose next actions (which agents, what tasks, what to present)
   - ACT: Spawn agents, create actions, generate messages
   - Run every 30 minutes for active goals (cron or background task)

4. API endpoints:
   - POST /api/v1/goals/propose — triggers propose_goals
   - POST /api/v1/goals/{id}/approve — approves goal, triggers plan_goal
   - POST /api/v1/goals/{id}/plan/approve — approves plan, triggers execute_goal
   - GET /api/v1/goals/{id}/progress — returns current progress
   - POST /api/v1/actions/{id}/approve — approves a pending action
   - POST /api/v1/actions/{id}/reject — rejects a pending action

5. WebSocket events (send from backend):
   - progress.update when goal progress changes
   - action.pending when HIGH/CRITICAL action needs approval
   - action.completed when action finishes
   - signal.detected when Scout finds something

CRITICAL: This is the most important session. Without GoalExecutionService, 
ARIA is just a chatbot. With it, ARIA is an autonomous agent that actually DOES things.

Test: Create a goal "Build CDMO Pipeline", approve it, verify agents spawn, 
verify results come back via WebSocket.
```

### Session 2B: Dynamic Agent Creation + WebSocket Backend

**Goal:** Implement dynamic agent creation and the backend WebSocket server.

```
PROMPT:

[Paste mandatory context header]

TASK: Implement dynamic agent creation and the backend WebSocket server 
for real-time communication.

WHAT TO BUILD:

1. Dynamic Agent Creation:
   - DynamicAgentFactory class
   - Takes: goal context, required capabilities, task description
   - Creates: new agent instance extending BaseAgent
   - Configures: system prompt, tool access, memory access
   - Registers: with GoalExecutionService for task routing
   - Logs: to procedural_patterns table for future reuse
   - Example: BoardPrepAgent, DueDiligenceAgent, EventPlanningAgent

2. Backend WebSocket Server:
   - Endpoint: /ws/{user_id}
   - Query param: session_id for session binding
   - Connection management: track active connections per user
   - Heartbeat: respond to client pings
   - Broadcasting: send events to specific user's connection(s)
   
   Event sending functions:
   - send_aria_message(user_id, message, rich_content, ui_commands, suggestions)
   - send_thinking(user_id)
   - send_action_pending(user_id, action)
   - send_progress_update(user_id, goal_id, progress)
   - send_signal(user_id, signal)
   
3. Update chat endpoint to use new response schema:
   - Include ui_commands in response based on conversation analysis
   - Include suggestions based on current context
   - Include rich_content when ARIA presents structured data

4. Wire GoalExecutionService to WebSocket:
   - When agent completes: send result via WebSocket
   - When action needs approval: send approval card via WebSocket
   - When progress changes: send update via WebSocket

Test: Connect to WebSocket, send a message, receive response with suggestions.
Then approve a goal and watch progress events stream in.
```

---

## Sprint 3: Content Pages + Avatar (Estimated: 3-4 days)

### Session 3A: Dialogue Mode + Tavus Avatar

**Goal:** Build the split-screen Dialogue Mode and integrate Tavus avatar.

```
PROMPT:

[Paste mandatory context header]

TASK: Build Dialogue Mode — the split-screen avatar + transcript layout — 
and integrate Tavus for the AI avatar.

VISUAL REFERENCE: Image 9 from the Stitch mockups — left half shows ARIA's 
avatar with waveform bars and playback controls, right half shows the 
transcript with rich inline data cards.

WHAT TO BUILD:

1. DialogueMode.tsx — Full-screen split layout:
   - Left 50%: Avatar container (dark, centered)
     - Background: abstract dark gradient
     - Circular avatar frame with electric blue border + subtle glow
     - Waveform bars below avatar (animated when ARIA speaks)
     - Progress bar at bottom (for briefings with known duration)
     - Playback controls: rewind 10s, play/pause, forward 10s
     - Bottom labels: "CAPTIONS ON" toggle, playback speed
   - Right 50%: Transcript panel
     - Same as ConversationThread but with timestamps for each message
     - Rich inline data cards (inventory risk, meeting cards, etc.)
     - Input bar at bottom with "Interrupt to ask a question..."
     - Suggestion chips below input

2. AvatarContainer.tsx:
   - Wraps Tavus Daily.co iframe
   - Circular frame with animated border
   - Fallback: static avatar image when not in active session
   - WaveformBars component that animates during speech

3. WaveformBars.tsx:
   - 12 vertical bars
   - Animated with staggered timing
   - Electric blue color
   - Visible when ARIA is speaking

4. BriefingControls.tsx:
   - Progress bar (percentage complete)
   - Rewind/Forward 10 seconds
   - Play/Pause
   - Speed control (0.75x, 1.0x, 1.25x, 1.5x)
   - "BRIEFING_IN_PROGRESS" label with timestamp

5. TranscriptPanel.tsx:
   - Extends ConversationThread with timestamps
   - Each ARIA message has: "ARIA" label in electric blue, timestamp
   - Each user message has: timestamp, "YOU" label
   - Active message highlighted, previous messages dimmed
   - Share and Download buttons in header

6. ModalityController.ts:
   - switchTo('avatar') → creates Tavus session, loads into AvatarContainer
   - switchTo('voice') → starts SpeechRecognition, shows compact waveform
   - switchTo('text') → default state
   - Modality switches preserve conversation thread and working memory

7. Backend: Video session endpoints
   - POST /api/v1/video/sessions — create Tavus conversation
   - GET /api/v1/video/sessions/{id} — get room URL
   - POST /api/v1/video/sessions/{id}/end — end session, trigger transcript save

8. CompactAvatar.tsx:
   - Small floating avatar (120x120px) in bottom-right
   - Shown when user navigates to content pages while in voice/avatar mode
   - Click to expand back to Dialogue Mode
   - Shows waveform when ARIA is speaking

CRITICAL: The Dialogue Mode must be the "wow" moment for investors. 
The split-screen with avatar on left and rich data cards on right 
is what makes people say "this is Jarvis."

DARK THEME throughout Dialogue Mode. Electric blue accents.
JetBrains Mono for status labels. Instrument Serif italic for "Transcript & Analysis" header.
```

### Session 3B: Content Pages (Pipeline + Intelligence)

**Goal:** Build the Pipeline and Intelligence content pages with ARIA Intelligence Panel.

```
PROMPT:

[Paste mandatory context header]

TASK: Build the Pipeline and Intelligence content pages — Layer 2 views 
where users browse ARIA's work with the persistent Intelligence Panel on the right.

REMEMBER: These are NOT CRUD pages. There are NO "Add Lead" or "Add Competitor" 
buttons. Everything shown was produced by ARIA's agents.

WHAT TO BUILD:

1. PipelinePage.tsx (route: /pipeline):
   - LIGHT THEME
   - Header: "Lead Memory // Pipeline Overview"
   - Subtitle: "● Command Mode: Active monitoring of high-velocity leads."
   - Search bar + filter chips (Status, Health 0-100, Owner)
   - Lead table with columns: Company, Health Score, Last Activity, Expected Value, Stakeholders
   - Health scores as colored progress bars (green >70, orange 40-70, red <40)
   - Last Activity with warning indicators (⚠ if >14 days)
   - Stakeholder avatars
   - Pagination: "Showing 1-5 of 24 leads"
   - Click row → navigates to lead detail
   
   Right Panel (Proactive Alerts):
   - Health Drop alerts (red, with "Investigate" button)
   - Lead Silent warnings (with "Suggest outreach" action)
   - Buying Signal notifications (with point changes)
   - Upcoming Renewal reminders
   - "View All Alerts" link at bottom

2. LeadDetailPage.tsx (route: /pipeline/leads/:leadId):
   - LIGHT THEME
   - Header: Company name (large, Instrument Serif), verified badge
   - Status tag (Opportunity Stage), Lead ID
   - Health score bar (visual) + "Synced to Salesforce" indicator
   
   Three-section layout:
   - Left: Stakeholder cards (name, title, role tag, sentiment indicator)
   - Center: Relationship Lifecycle timeline (chronological events with cards)
   - Right Panel: ARIA Intelligence (Strategic Advice, Buying Signals, Active Objections, Suggested Next Steps)

3. IntelligencePage.tsx (route: /intelligence):
   - LIGHT THEME  
   - Battle Cards section: grid of competitor cards
   - Each card shows: competitor name, market cap gap, win rate, pricing delta, last signal
   - Click → BattleCardDetail
   
   Market Signals section: recent signals feed
   
   Right Panel (ARIA Intel):
   - Real-time competitive signals
   - News Alerts
   - Mini chat input: "Ask for competitive intel..."

4. BattleCardDetail.tsx (route: /intelligence/battle-cards/:id):
   - LIGHT THEME with some dark accent sections
   - Header: "Battle Cards: Competitor Analysis" + competitor selector
   - Top metrics bar: Market Cap Gap, Win Rate, Pricing Delta, Last Signal
   - Main sections:
     - "How to Win" — strategic talking points in cards
     - "Feature Gap Analysis" — comparison bars (ARIA vs competitor)
     - "Critical Gaps" — checklist with ✓/✗
     - "Objection Handling Scripts" — expandable accordion
   
   Right Panel:
   - Live competitive signals
   - News alerts about this competitor
   - "Generate Comparison Deck" button
   - Chat input for competitive questions

ALL CONTENT PAGES must use data-aria-id attributes on key elements so 
UICommandExecutor can highlight them when ARIA references them.

Use realistic placeholder/mock data that looks like a life sciences sales context:
Companies like Moderna, Lonza, Catalent, WuXi Biologics, Samsung Biologics.
```

### Session 3C: Communications Page + Settings

**Goal:** Build the Communications (email drafts) page and Settings.

```
PROMPT:

[Paste mandatory context header]

TASK: Build Communications page (email drafts view) and Settings page.

WHAT TO BUILD:

1. CommunicationsPage.tsx (route: /communications):
   - LIGHT THEME
   - Draft list with: recipient, subject, status (DRAFTING/READY/SENT), auto-saved time
   - Click → DraftDetailPage

2. DraftDetailPage.tsx (route: /communications/drafts/:id):
   - LIGHT THEME
   - Header: breadcrumb (Campaigns > Series B Outreach > Draft #14)
   - Status badge (DRAFTING), "Preview" button, "Approve & Schedule" CTA
   - Email preview: To field, Subject field, rich text body
   - Bottom actions: Send Email, Save Draft, Regenerate
   - Inline refinement suggestions (highlighted in email body)
   
   Right Panel — ARIA Insights:
   - "WHY I WROTE THIS": explanation with source tags (source:salesforce, source:g-drive)
   - "TONE & VOICE": selector chips (Professional, Casual, Urgent, Empathetic)
   - "ANALYSIS": Read Time + AI Confidence score
   - "NEXT BEST ACTION": with auto-schedule button
   - "SUGGESTED REFINEMENTS": clickable refinement options

3. ActionsPage.tsx (route: /actions):
   - LIGHT THEME
   - Active Goals section: goal cards with progress trackers
   - Agent Activity section: which agents are running, what they're doing
   - Action Queue: pending approvals, recent completions
   - Right Panel: Agent status overview

4. SettingsPage.tsx (route: /settings):
   - LIGHT THEME, no right panel
   - Sections (as sub-routes or tabs):
     - Profile: name, role, company, avatar
     - Integrations: connected apps (Salesforce, HubSpot, Google, etc.)
     - ARIA Persona: name preference, communication style, briefing time
     - Autonomy: current level (Guided) with "Full Autonomy — Coming Q3 2026" 
       disabled toggle with badge
     - Perception: webcam opt-in for Raven-0 emotion detection
     - Billing: plan details
   
   "Coming Soon" indicators:
   - Under Integrations: "Browser & OS Control — Coming Q3 2026"
   - Under Autonomy: "Full Autonomy" toggle with coming soon badge
   - At bottom: "Enterprise Network — Connect your ARIA with your team's ARIAs — Coming 2027"

CRITICAL for Settings: The "Coming Soon" indicators must feel like real features 
that are just locked, not placeholder text. Use disabled toggles with subtle 
styling, lock icons, and brief descriptions of what they'll do.
```

---

## Sprint 4: Wire + Polish (Estimated: 2-3 days)

### Session 4A: First Conversation Generator + Morning Briefing

**Goal:** Build the flows that make ARIA feel alive on first use and every morning.

```
PROMPT:

[Paste mandatory context header]

TASK: Build the First Conversation Generator and Morning Briefing flow — 
the two most critical "first impression" moments.

WHAT TO BUILD:

1. First Conversation Generator (backend/src/services/first_conversation.py):
   - Triggered on first login after onboarding
   - Gathers: user profile, company info, role, connected integrations
   - Generates: ARIA's opening message with:
     a. Personalized greeting using user's name
     b. Summary of what ARIA has learned ("28 facts about Repligen, 6 competitors...")
     c. 3-4 Goal Plan Cards with rationale
   - Sends via WebSocket as aria.message with rich_content (GoalPlanCards)
   - Include ui_commands to update sidebar badges
   - Include suggestions: ["Tell me more about Goal 1", "What competitors did you find?", "Start with the pipeline goal"]

2. GoalPlanCard component (frontend):
   - Title (bold)
   - Rationale (why ARIA recommends this)
   - Approach (which agents, what strategy)
   - Timeline estimate
   - Buttons: [Approve] [Modify] [Discuss]
   - Approve → POST /goals/{id}/approve → ARIA responds with ExecutionPlanCard
   - Discuss → sends "Tell me more about [goal title]" as user message

3. ExecutionPlanCard component:
   - Phased timeline (Phase 1: Discovery, Phase 2: Qualification, etc.)
   - Each phase: timeline, agents assigned, expected output
   - Autonomy indicator: "I'll need your approval before sending emails. Research I handle autonomously."
   - Buttons: [Approve Plan] [Modify] [Discuss Further]

4. Morning Briefing Generator (backend/src/services/briefing.py):
   - Runs at user's configured time (default 8am)
   - Gathers: calendar (today's meetings), overnight emails, goal progress, 
     new leads, pipeline changes, signals from Scout
   - Generates briefing with sections:
     a. Greeting + priority summary
     b. Meeting cards (with "View Brief" action)
     c. Items needing attention (drafts, leads, follow-ups)
     d. Signals (competitive, market, customer)
     e. "What would you like to focus on first?"
   - Can be delivered as:
     a. Dialogue Mode briefing (avatar speaks it)
     b. Text briefing in ARIA Workspace
   - Sends via WebSocket

5. Wire the briefing to Dialogue Mode:
   - User navigates to /briefing or clicks Briefing in sidebar
   - Avatar loads, briefing streams as transcript
   - Rich data cards appear alongside avatar's speech
   - User can interrupt via text or voice

CRITICAL: The first conversation is what investors see first. It must be 
jaw-dropping. ARIA must demonstrate she KNOWS things about the user's company 
and has OPINIONS about what to prioritize. Not generic — specific.

Test: Log in as new user, verify first conversation appears with company-specific 
goal proposals. Then test morning briefing flow.
```

### Session 4B: Raven-0 + Voice + Polish

**Goal:** Wire Raven-0 emotion detection, voice input, and visual polish.

```
PROMPT:

[Paste mandatory context header]

TASK: Wire Raven-0 emotion detection, voice input (space-to-talk), 
and visual polish across the app.

WHAT TO BUILD:

1. Voice Input (space-to-talk):
   - Global keyboard listener for SPACE key
   - On SPACE down: show voice indicator, start SpeechRecognition
   - On SPACE up: stop listening, send transcript
   - VoiceIndicator.tsx: waveform animation in input bar
   - Works in both ARIA Workspace and Dialogue Mode
   - Visual: "SPACE TO TALK" badge next to send button

2. Raven-0 Integration:
   - Listen for emotion events from Tavus SDK
   - Send to backend: POST /api/v1/perception/emotion
   - Backend adjusts ARIA's response style based on detected emotion
   - Frontend: subtle indicator when emotion is detected (optional, for debug)
   - Store engagement patterns in procedural_patterns table

3. Presence Animations:
   - The Pulse: sidebar ARIA icon has a subtle breathing glow
   - The Arrival: when ARIA starts typing, a soft light sweeps across 
     the message area before text appears
   - The Settle: after ARIA finishes, the UI settles with a micro-ease
   - Streaming text: typewriter effect with 20ms per character

4. Highlight Effects:
   - When ARIA references an entity, the corresponding element on the 
     current page gets a brief glow effect
   - CSS: .aria-highlight-glow, .aria-highlight-pulse, .aria-highlight-outline

5. Error States:
   - ARIA explains errors in conversation, not as toasts
   - "I ran into an issue connecting to Salesforce. Want me to retry?"
   - Graceful fallback when WebSocket disconnects: "Reconnecting..."

6. Empty States:
   - No "No data. Click to add." anywhere
   - Instead: "ARIA is building your competitive intelligence. Check back in a few hours."
   - Or: "ARIA hasn't discovered any signals for this account yet. Want me to research them?"

7. Suggestion Chips everywhere:
   - After every ARIA response, show 2-3 contextual suggestions
   - Suggestions should feel natural and useful, not generic
   - Examples: "Model Hamburg Scenario", "Draft outreach to Lonza", 
     "Show me pipeline health"

TEST THE INVESTOR DEMO PATH:
1. Log in → ARIA greets, proposes goals (wow moment #1)
2. Approve a goal → see execution plan with agents
3. Navigate to Pipeline → see leads with ARIA intelligence panel
4. Open a battle card → ARIA highlights competitive advantage
5. Switch to Dialogue Mode → avatar delivers briefing (wow moment #2)
6. Throughout: ARIA controls navigation, panels update, presence is felt
```

---

## Sprint 5: Demo-Ready (Estimated: 1-2 days)

### Session 5A: Demo Path Optimization

```
PROMPT:

[Paste mandatory context header]

TASK: Optimize the 3-minute investor demo path. Every second must count.

THE DEMO FLOW:
1. (0:00-0:30) Log in → ARIA's avatar greets by name, demonstrates company knowledge
2. (0:30-1:00) ARIA proposes goals → investor sees Goal Plan Cards with life sciences specifics
3. (1:00-1:30) Approve goal → execution plan appears, agents start working
4. (1:30-2:00) ARIA navigates to Intelligence → Battle Card with competitive data, 
   right panel shows real-time signals
5. (2:00-2:30) Show Pipeline → leads with health scores, ARIA highlights buying signal
6. (2:30-3:00) Switch to Dialogue Mode → avatar delivers briefing with rich data cards

WHAT TO OPTIMIZE:
1. Pre-load demo data for a life sciences context (Repligen, Lonza, Catalent, etc.)
2. Ensure transitions between views are smooth (< 300ms)
3. Ensure ARIA's first message appears within 2 seconds of login
4. Avatar session should connect within 3 seconds
5. Suggestion chips should feel contextually perfect
6. "Coming Soon" indicators visible in natural flow (not hidden)
7. The right panel should update INSTANTLY when ARIA navigates
8. All elements have data-aria-id for highlight targeting

CREATE a demo seed script that populates:
- 5 battle cards for bioprocessing competitors
- 15 leads with varied health scores
- 3 email drafts in various stages
- 5 market signals
- 2 active goals with progress
- Meeting schedule for today

This should be runnable as: python scripts/seed_demo_data.py
```

---

## Parallel Execution Strategy

For maximum velocity, run sessions in parallel where dependencies allow:

```
WEEK 1:
  Session 0A (Database) ──────────────┐
  Session 0B (Chat Fix) ──────────────┤──→ All Sprint 0 done
  Session 0C (Extract Primitives) ────┘
  
  Then immediately:
  Session 1A (AppShell) ──────────────┐
  Session 2A (GoalExecutionService) ──┤──→ Frontend + Backend in parallel
                                      │
WEEK 2:                               │
  Session 1B (WebSocket + Workspace) ─┤
  Session 2B (Dynamic Agents + WS) ───┤
  Session 1C (UICommandExec + Panel) ─┘
  
  Then:
  Session 3A (Dialogue + Avatar) ─────┐
  Session 3B (Pipeline + Intel pages) ┤──→ Content + Avatar in parallel
  Session 3C (Communications + Settings)┘
  
WEEK 3:
  Session 4A (First Convo + Briefing) ┐
  Session 4B (Voice + Polish) ────────┤──→ Polish
  Session 5A (Demo Optimization) ─────┘
```

**Model Assignment (per Dhruv's preferences):**
- Sessions 0A, 0B, 2A, 2B: Opus 4.5 (complex backend reasoning)
- Sessions 0C, 3B, 3C: Sonnet 4.5 or GLM 4.7 (CRUD-like page building)
- Sessions 1A, 1B, 1C: Opus 4.5 (core architecture, must be right)
- Sessions 3A, 4A, 4B: Opus 4.5 (avatar integration, polish, wow moments)
- Session 5A: Opus 4.5 (demo path is critical)

---

## Quality Gates

Every session must pass before moving to next sprint:

| Sprint | Quality Gate |
|--------|-------------|
| Sprint 0 | All tables exist. Chat endpoint works end-to-end. Memory persists. |
| Sprint 1 | Three-column layout renders. WebSocket connects. Messages send/receive. |
| Sprint 2 | Goal proposal → approve → agents execute → results via WebSocket. |
| Sprint 3 | Dialogue Mode renders with avatar. Content pages show data with Intel Panel. |
| Sprint 4 | First conversation wows. Morning briefing flows. Voice works. |
| Sprint 5 | 3-minute demo runs flawlessly. No loading spinners. No errors. |

---

> **This execution plan is designed for parallel Claude Code sessions. Each session prompt 
> is self-contained with the mandatory context header. Follow the dependency graph for ordering.**
