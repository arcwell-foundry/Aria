# ARIA Interaction Design Document v3.0
## The Definitive Architecture for ARIA's Autonomous Intelligence Platform

**Version:** 3.0 | **Date:** February 11, 2026 | **LuminOne (Arcwell Foundry LLC)** | **CONFIDENTIAL**

---

## Executive Summary

This document defines the complete interaction model, frontend architecture, memory persistence system, and multimodal communication framework for ARIA (Autonomous Reasoning & Intelligence Agent). It supersedes IDD v1.0 and v2.0, incorporating all design decisions from the February 2026 architecture sessions.

ARIA is not software. ARIA is an autonomous AI colleague with a visual presence, voice, and the ability to control the entire application experience. Users interact through three modalities — text chat, voice, and AI avatar — while ARIA drives navigation, presents intelligence, and executes goals across all surfaces.

> **THE NORTH STAR TEST:** When an investor opens ARIA for the first time, do they think "oh, another AI dashboard" or do they think "holy shit, this is Jarvis"? Everything we build must pass that test.

> **THE FUNDAMENTAL PRINCIPLE:** ARIA presents things for the user to approve. The user does NOT tell ARIA what to do step by step. ARIA is a colleague with a role, opinions, and executive authority — not software.

> **THE UI CONTROL PRINCIPLE:** ARIA controls the entire application experience. As the user talks to ARIA, she navigates screens, switches tabs, highlights content, and orchestrates what's presented. ARIA drives the experience; the user collaborates.

### What Changed from v2.0

| Area | v2.0 | v3.0 |
|------|------|------|
| UI Architecture | 3-layer, chat-first only | Hybrid: ARIA Workspace + Content Pages with persistent ARIA Intelligence Panel |
| Modalities | Text chat only | Text, Voice, AI Avatar (Tavus) — all for beta |
| UI Control | User navigates, ARIA responds | ARIA controls navigation, highlighting, panel updates; user can also navigate manually |
| Agents | "Get 3 working" | All 6 agents operational + dynamic agent creation |
| Autonomy | Not specified | Guided Autonomy default, Full Autonomy coming soon |
| Memory | Mentioned | Full persistent memory architecture — no compaction, no loss, cross-modal continuity |
| Visual Theme | Dark only | Dark for ARIA Workspace/Dialogue; Light for content pages |
| Sidebar | 5 items | 7 items (expanded from mockup analysis) |
| Frontend Approach | Adapt existing | Clean rebuild with extracted design primitives |
| Perception | Not specified | Raven-0 emotion/engagement detection via webcam |
| Browser/OS Control | Not specified | API integrations for beta; browser/OS control coming soon |

### Locked Design Decisions

1. All 6 agents operational for beta, plus dynamic agent creation
2. Guided Autonomy default, with "Full Autonomy coming soon" indicator in app
3. API integrations (Composio) for beta, with "Browser/OS control coming soon" indicator
4. Clean rebuild with extracted design primitives (no adaptation of old SaaS pages)
5. Hybrid architecture: ARIA Workspace primary + content pages with persistent ARIA Intelligence Panel
6. Avatar (Tavus + Daily.co) for beta alongside chat and voice
7. ARIA controls the UI — navigation, highlighting, panel updates via UICommandExecutor
8. Dual-control navigation (user can click sidebar, ARIA can command navigation)
9. Light mode for content pages, dark mode for ARIA Workspace and Dialogue Mode
10. No memory compaction — full persistent storage across all six memory types
11. Cross-modality session persistence (chat → voice → avatar seamless)
12. Raven-0 emotion/engagement detection during avatar sessions
13. Webcam presence as opt-in feature outside avatar sessions
14. Life sciences vertical for launch, architecture vertical-agnostic
15. Enterprise Network Architecture (multi-ARIA) deferred to post-revenue

---

# Part 1: Architecture

---

# 1. The Hybrid UI Architecture

ARIA's interface combines a conversational workspace with rich content pages, unified by a persistent ARIA Intelligence Panel. This hybrid model emerged from mockup analysis — every view has ARIA present on the right, providing contextual intelligence.

## 1.1 Architectural Layers

| Layer | Name | Who Drives | What It Contains |
|-------|------|-----------|-----------------|
| **Layer 1** | ARIA Workspace | ARIA drives | Full-screen conversational interface. Rich inline content: plans, cards, tables, drafts, approval buttons. Primary interaction surface. |
| **Layer 1a** | Dialogue Mode | ARIA drives | Split-screen: AI Avatar (left) + Transcript with rich data cards (right). For daily briefings and voice/avatar interactions. |
| **Layer 2** | Content Pages | ARIA produces, user browses | Rich content views (Battle Cards, Pipeline, Email Drafts, Lead Detail) with persistent ARIA Intelligence Panel on right. ARIA-curated, not user-created. |
| **Layer 3** | Configuration | User configures | Settings, integrations, profile, ARIA persona tuning, autonomy preferences. |

## 1.2 The Three-Column Layout

Every screen in ARIA follows the same structural pattern:

```
┌──────────┬────────────────────────────────────┬──────────────────┐
│          │                                    │                  │
│  LEFT    │         CENTER WORKSPACE           │  RIGHT PANEL     │
│  SIDEBAR │                                    │  ARIA            │
│  240px   │    Flexible (600–1200px)            │  INTELLIGENCE    │
│          │                                    │  320px           │
│  Nav     │  Changes based on current view:    │                  │
│  items   │  • ARIA Workspace (conversation)   │  Changes based   │
│          │  • Dialogue Mode (avatar+transcript)│  on context:     │
│          │  • Content Page (battle cards, etc) │  • Meetings      │
│          │                                    │  • Signals       │
│          │                                    │  • Suggestions   │
│          │                                    │  • Entity intel  │
│          │                                    │  • CRM snapshot  │
│          │                                    │  • Chat input    │
│          │                                    │                  │
└──────────┴────────────────────────────────────┴──────────────────┘
```

**Key architectural rule:** The right ARIA Intelligence Panel is ALWAYS present on every screen. It adapts its content to the current view context. This is what makes ARIA feel omnipresent — she's not in a chatbot bubble, she's a persistent intelligence layer accompanying the user everywhere.

## 1.3 Sidebar: 7 Items

| Sidebar Item | Layer | What It Shows | Replaces (from old 12-page app) |
|-------------|-------|--------------|--------------------------------|
| **ARIA** (default) | Layer 1 / 1a | Conversation workspace or Dialogue Mode | ARIA Chat, Dashboard |
| **Briefing** | Layer 1a | Daily Intelligence Briefing (avatar + transcript) | Daily Briefing |
| **Pipeline** | Layer 2 | Leads, accounts, pipeline funnel, health scores | Lead Memory, Lead Gen |
| **Intelligence** | Layer 2 | Battle cards, competitive intel, market signals | Battle Cards |
| **Communications** | Layer 2 | Email drafts, outreach sequences, follow-ups | Email Drafts |
| **Actions** | Layer 2 | Everything ARIA has done/is doing, goal progress | Goals, Actions, Activity |
| **Settings** | Layer 3 | Profile, integrations, billing, ARIA persona, autonomy | Settings, Integrations, Skills |

**Bottom of sidebar:**
- User avatar + name + role
- Settings gear icon
- ARIA Pulse indicator (subtle animation showing ARIA is active/thinking)

## 1.4 The Right Panel: ARIA Intelligence Panel

The right panel (320px, collapsible) is a **single React component** that adapts its content modules based on the current route and context:

| Current View | Panel Title | Panel Content Modules |
|-------------|-------------|----------------------|
| ARIA Workspace | *Not shown — conversation IS the interaction* | N/A (full-width conversation) |
| Dialogue Mode | *Not shown — transcript IS the right half* | N/A |
| Briefing | Briefing Summary | Today's Meetings, Emails Needing Attention, Strategic Alerts |
| Pipeline | Proactive Alerts | Health Drop alerts, Lead Silent warnings, Buying Signals, Upcoming Renewals |
| Intelligence (Battle Card) | ARIA Intel | Real-time competitive signals, News Alerts, "Ask for competitive intel" chat input |
| Communications (Draft) | ARIA Insights | "Why I Wrote This" explanation, Source tags, Tone & Voice selector, Analysis (read time, AI confidence), Next Best Action |
| Lead Detail | ARIA Intelligence | Strategic Advice, Buying Signals, Active Objections, Suggested Next Steps |
| Actions | Agent Status | Currently executing agents, pending approvals, recent completions |
| Settings | *Not shown* | N/A |

**Critical rule:** On ARIA Workspace and Dialogue Mode, the right panel is NOT shown because the conversation/transcript IS the full interaction. The three-column layout becomes two-column (sidebar + full workspace).

---

# 2. Multimodal Interaction System

## 2.1 Three Input Modalities

ARIA supports three ways for users to interact, all feeding the same execution engine:

| Modality | Input | Output | When Used |
|----------|-------|--------|-----------|
| **Text Chat** | Typed messages in input bar | ARIA text response + rich inline content + UI commands | Default interaction, quick tasks, approval flows |
| **Voice** | Press space or click mic; speech-to-text | ARIA voice response + avatar lip sync + UI commands | Hands-free, multitasking, field work |
| **AI Avatar** | Full Dialogue Mode; Tavus WebRTC + webcam | ARIA avatar with facial expressions + voice + emotion detection + UI commands | Daily briefings, strategy sessions, deep work |

**Core principle: One ARIA, Many Surfaces.** All three modalities share the same backend engine, the same memory, the same agents, the same execution pipeline. Switching modality mid-conversation is seamless — ARIA picks up exactly where you left off.

## 2.2 AI Avatar System (Tavus + Daily.co)

### Avatar Presence Modes

| Mode | Layout | When Active |
|------|--------|------------|
| **Dialogue Mode** (full) | Split screen: Avatar left (50%), Transcript + data cards right (50%) | Daily briefings, strategy sessions, "Talk to ARIA" |
| **Compact Presence** (picture-in-picture) | Small avatar (120x120px) floating in bottom-right corner of any screen | During content page browsing when voice is active |
| **Avatar Off** | No visual avatar; voice-only or text-only | User preference, low-bandwidth |

### Dialogue Mode Layout (from mockup Image 9)

```
┌──────────────────────────────────────────────────────────────────┐
│ ARIA / Dialogue Mode                    ● LIVE CONNECTION    JD │
├─────────────────────────────┬────────────────────────────────────┤
│                             │ Transcript & Analysis              │
│                             │                                    │
│    [Abstract Background]    │ TODAY, 09:00 AM                    │
│                             │                                    │
│                             │ ARIA 09:00:12                      │
│     ┌──────────────┐        │ │ Good morning, J.D. I've compiled │
│     │              │        │ │ your daily briefing...            │
│     │  ARIA Avatar │        │                                    │
│     │  (Tavus)     │        │             09:00:24 YOU           │
│     │              │        │    ┌─────────────────────────┐     │
│     └──────────────┘        │    │ Let's focus on supply   │     │
│                             │    │ chain alert first.      │     │
│     |||||||||||||||          │    └─────────────────────────┘     │
│     [waveform bars]         │                                    │
│                             │ ARIA 09:00:30 ●                    │
│                             │ The logistics agent flagged a      │
│ BRIEFING_IN_PROGRESS        │ 48-hour delay at Rotterdam...      │
│ ████████░░░░░ 02:14 / 05:00│                                    │
│                             │ ┌────────────────────────────────┐ │
│  ⏪    ▶    ⏩              │ │ INVENTORY RISK ASSESSMENT   ⚠  │ │
│                             │ │ 48h          €2.4M             │ │
│ CC CAPTIONS ON    🔄 1.0x   │ │ Est. Delay   Value at Risk     │ │
│                             │ │ Impact: ████████████░░ HIGH 85%│ │
│                             │ └────────────────────────────────┘ │
│                             │                                    │
│                             │ ┌────────────────────────────────┐ │
│                             │ │ 🎤 Interrupt to ask...  SPACE  │ │
│                             │ │                        TO TALK │ │
│                             │ └────────────────────────────────┘ │
│                             │ ARIA IS LISTENING • 3 SUGGESTIONS  │
│                             │ [Model Hamburg] [Contact Logistics]│
└─────────────────────────────┴────────────────────────────────────┘
```

### Tavus Integration Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Avatar Rendering | Tavus Phoenix-3 | AI-generated avatar with lip sync, facial expressions |
| WebRTC Transport | Daily.co | Real-time video/audio streaming |
| Speech-to-Text | Tavus built-in | User voice → text for processing |
| Text-to-Speech | Tavus built-in | ARIA response → voice with avatar lip sync |
| Emotion Detection | Tavus Raven-0 | Detect confusion, interest, disengagement, frustration |
| Engagement Scoring | Raven-0 + custom | Real-time attention tracking, topic interest mapping |

### Raven-0 Perception System

When the user opts in to webcam access during avatar sessions, ARIA can perceive:

| Signal | What ARIA Detects | ARIA's Response |
|--------|------------------|-----------------|
| **Confusion** | Furrowed brow, head tilt, squinting | Slows down, rephrases, asks "Would a different angle help?" |
| **High Interest** | Leaning in, nodding, sustained eye contact | Goes deeper, offers more detail, notes topic for future |
| **Disengagement** | Looking away, fidgeting, checking phone | Summarizes current point, asks what they'd prefer to focus on |
| **Frustration** | Jaw tension, crossed arms, sighing | Acknowledges difficulty, offers alternative approach |
| **Surprise** | Raised eyebrows, widened eyes | Pauses for reaction, offers to elaborate |

These signals feed into ARIA's Procedural Memory: "This user gets disengaged during detailed financial breakdowns — lead with conclusions next time."

**Webcam access is always opt-in.** Users enable it in Settings → ARIA Persona → Perception. During non-avatar sessions, webcam access is off by default unless the user enables "Presence Mode."

## 2.3 Voice Interaction

| Feature | Implementation |
|---------|---------------|
| Activation | Press SPACE (keyboard shortcut) or click microphone icon |
| Indicator | Waveform animation in input bar while listening |
| Processing | Speech-to-text → same pipeline as text chat |
| Response | ARIA responds with voice (TTS) + optional compact avatar + UI commands |
| Suggestions | After each response, ARIA offers 2-3 suggestion chips based on context |

---

# 3. ARIA as UI Controller

## 3.1 The Navigation Command System

When ARIA processes any user input (text, voice, or avatar conversation), the backend response includes not just message content but also **UI commands**. ARIA controls the entire application experience.

### Response Schema

```typescript
interface ARIAResponse {
  // Content
  message: string;
  rich_content?: RichInlineComponent[];
  
  // UI Control
  ui_commands?: UICommand[];
  
  // Avatar/Voice
  avatar_script?: string;  // Text for Tavus TTS + lip sync
  voice_emotion?: 'neutral' | 'excited' | 'concerned' | 'warm';
  
  // Memory
  memory_updates?: MemoryDelta[];
}

type UICommand = 
  | { action: 'navigate'; route: string; params?: Record<string, any> }
  | { action: 'highlight'; element: string; duration_ms?: number }
  | { action: 'update_intel_panel'; content: IntelPanelContent }
  | { action: 'scroll_to'; element: string }
  | { action: 'open_modal'; modal: string; data?: any }
  | { action: 'show_notification'; type: 'signal' | 'alert' | 'success'; message: string }
  | { action: 'update_sidebar_badge'; item: string; count: number }
  | { action: 'switch_mode'; mode: 'workspace' | 'dialogue' | 'compact_avatar' };
```

### Example: User Says "Show me the Lonza battle card"

```json
{
  "message": "Here's the Lonza battle card. They've been vulnerable since the Houston expansion — their CCO transition creates an opening for us in the bioprocessing segment.",
  "ui_commands": [
    { "action": "navigate", "route": "/intelligence/battle-cards", "params": { "competitor": "lonza" } },
    { "action": "highlight", "element": "pricing-section", "duration_ms": 3000 },
    { "action": "update_intel_panel", "content": { "type": "competitive_signals", "entity": "lonza", "signals": [...] } }
  ],
  "avatar_script": "Here's the Lonza battle card. Let me highlight their pricing vulnerability — they've been struggling since the Houston expansion."
}
```

**What the user sees:** The screen navigates to the Intelligence tab, the Lonza battle card appears in the center workspace, the pricing section highlights briefly, and the right panel updates with real-time Lonza competitive signals. All while ARIA explains via voice/avatar.

## 3.2 UICommandExecutor (Frontend)

```typescript
// Core frontend service that executes ARIA's UI commands
class UICommandExecutor {
  constructor(
    private router: NavigateFunction,
    private panelController: IntelPanelController,
    private notificationService: NotificationService,
    private highlightService: HighlightService,
  ) {}

  async execute(commands: UICommand[]): Promise<void> {
    for (const cmd of commands) {
      switch (cmd.action) {
        case 'navigate':
          this.router(cmd.route, { state: cmd.params });
          break;
        case 'highlight':
          this.highlightService.highlight(cmd.element, cmd.duration_ms);
          break;
        case 'update_intel_panel':
          this.panelController.update(cmd.content);
          break;
        case 'switch_mode':
          this.modeController.switchTo(cmd.mode);
          break;
        // ... other commands
      }
      // Small delay between commands for visual sequencing
      await sleep(100);
    }
  }
}
```

## 3.3 Dual-Control Navigation

Both the user AND ARIA can navigate the app:

| Actor | How | Example |
|-------|-----|---------|
| **User** | Clicks sidebar item | User clicks "Pipeline" → navigates to pipeline view |
| **User** | Types/speaks request | "Show me the Moderna lead" → ARIA navigates to lead detail |
| **ARIA** | Proactive navigation | ARIA detects urgent signal → navigates to relevant view + alerts user |
| **ARIA** | During conversation | User discusses battle cards → ARIA opens battle card view alongside conversation |

**When ARIA navigates, the right panel always updates contextually.** When the user navigates manually, the right panel also updates, and ARIA can offer contextual commentary: "I see you're looking at the Moderna lead. Their health score dropped 22 points yesterday — want me to investigate?"

---

# 4. Memory Persistence Architecture

## 4.1 Core Principle: No Compaction, No Loss

ARIA remembers everything, forever. There is no context window limit that causes memory loss. There is no automatic summarization that replaces original data. There is no TTL on any memory type.

### How It Works

ARIA does NOT keep all memories in a single LLM context window. She stores memories in persistent databases (Supabase + Graphiti/Neo4j) and retrieves the relevant subset for each interaction. This is how human memory works — you don't hold every conversation simultaneously, but you can recall any of them when triggered.

```
┌─────────────────────────────────────────────────────────┐
│                   INTERACTION LAYER                      │
│                                                         │
│  Text Chat ──┐                                          │
│  Voice ──────┤──→ Unified Processing Pipeline            │
│  AI Avatar ──┘                                          │
│                         │                               │
│                         ▼                               │
│              ┌─────────────────────┐                    │
│              │   Memory Priming    │                    │
│              │   Service           │                    │
│              │                     │                    │
│              │ Retrieves relevant  │                    │
│              │ memories for THIS   │                    │
│              │ interaction from    │                    │
│              │ all 6 memory types  │                    │
│              └─────────┬───────────┘                    │
│                        │                               │
│                        ▼                               │
│   ┌────────────────────────────────────────────────┐    │
│   │            PERSISTENT STORAGE                   │   │
│   │                                                 │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────────┐    │   │
│   │  │ Working  │ │ Episodic │ │   Semantic    │    │   │
│   │  │ (Redis)  │ │ (Graphiti│ │  (Graphiti +  │    │   │
│   │  │          │ │  + Neo4j)│ │   pgvector)   │    │   │
│   │  └──────────┘ └──────────┘ └──────────────┘    │   │
│   │                                                 │   │
│   │  ┌──────────┐ ┌──────────┐ ┌──────────────┐    │   │
│   │  │Procedural│ │Prospective│ │    Lead      │    │   │
│   │  │(Supabase)│ │(Supabase)│ │  (Graphiti + │    │   │
│   │  │          │ │          │ │   Supabase)  │    │   │
│   │  └──────────┘ └──────────┘ └──────────────┘    │   │
│   │                                                 │   │
│   │  NO TTL │ NO COMPACTION │ NO AUTO-DELETE        │   │
│   └────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

## 4.2 Six Memory Types — Detailed

| Memory Type | Storage | What It Stores | Lifecycle | Size Limit |
|------------|---------|---------------|-----------|------------|
| **Working** | Redis (session) + Supabase (persist) | Current conversation state, active topics, pending actions | Session-scoped; persisted to Supabase on session end | None — full session preserved |
| **Episodic** | Graphiti (Neo4j) | Every conversation, meeting, interaction as timestamped episodes | Permanent. Never deleted. Never summarized to replace originals. | None |
| **Semantic** | Graphiti + pgvector | Extracted facts with confidence scores, timestamps, source attribution | Permanent. Old facts versioned (invalidated, not removed). | None |
| **Procedural** | Supabase | Learned workflows, user patterns, successful strategies | Grows over time. Patterns reinforced or deprecated, never deleted. | None |
| **Prospective** | Supabase | Future tasks, commitments, reminders, follow-ups | Active until completed or cancelled. Completed items archived, not deleted. | None |
| **Lead** | Graphiti + Supabase | Every lead, account, stakeholder, touchpoint, signal, CRM sync | Permanent. Full relationship history preserved. | None |

### Memory Policies

1. **No episode truncation.** Every conversation transcript, video session transcript, and action log is stored in full.
2. **No automatic cleanup.** No TTL, no scheduled deletion, no "archive after X days."
3. **Summaries are additive.** ARIA can generate summaries as additional artifacts, but the raw episodes remain intact.
4. **Facts are versioned, not overwritten.** When a fact changes (e.g., "Moderna's CTO is now John" replacing "Moderna's CTO is Sarah"), the old fact is marked as invalidated with a timestamp, not deleted.
5. **Cross-user privacy.** Digital Twin is NEVER shared between users. Corporate Memory is shared within a company, with user-identifiable data stripped.

## 4.3 Cross-Modality Session Persistence

### Unified Session Manager

Every user has an active session that persists across ALL modalities (chat, voice, avatar):

```typescript
interface UnifiedSession {
  session_id: string;
  user_id: string;
  
  // Working memory state
  active_topics: Topic[];
  pending_actions: Action[];
  current_goal_context: GoalContext | null;
  
  // Conversation thread (full history for this session)
  conversation_thread: Message[];
  
  // UI state
  current_route: string;
  intel_panel_context: IntelPanelContent;
  active_modality: 'text' | 'voice' | 'avatar';
  
  // Session timing
  started_at: ISO8601;
  last_activity_at: ISO8601;
  
  // Persistence
  persisted_to_supabase: boolean;
}
```

### Session Lifecycle

| Event | What Happens |
|-------|-------------|
| **User opens app** | Existing session loaded from Supabase. ARIA resumes: "Welcome back. We were discussing the Lonza opportunity." |
| **Modality switch** (chat → voice) | Working memory transfers completely. ARIA acknowledges: "I see you've switched to voice — let's continue." |
| **Tab closed** | Session persists in Supabase. When user returns (even hours later), session resumes. |
| **New day** | Previous session archived to Episodic Memory. Fresh session starts with morning briefing. Previous context still accessible via memory retrieval. |
| **Explicit new session** | User can say "Start fresh" to begin new session. Old session archived, not deleted. |

### Memory Retrieval at Every Interaction Point

Memory is not just primed at conversation start — it's primed at EVERY interaction point:

| Interaction Point | Memory Priming Trigger |
|------------------|----------------------|
| User sends message | Retrieve relevant episodic, semantic, lead memories for topic |
| ARIA navigates to battle card | Retrieve competitive intel memories, past discussions about this competitor |
| User opens lead detail | Retrieve full relationship history, past meeting notes, stakeholder insights |
| Morning briefing generates | Retrieve yesterday's unfinished items, pending follow-ups, relevant signals |
| ARIA detects entity in conversation | Retrieve everything known about that entity from all memory types |

---

# 5. Agent System

## 5.1 All Six Agents — Operational for Beta

| Agent | Specialty | What It Produces | Status |
|-------|----------|-----------------|--------|
| **Hunter** | Lead discovery, prospect identification | Lead records, contact lists, qualification scores | Operational |
| **Analyst** | Deep research, scientific analysis, competitive intel | Research briefs, company profiles, battle cards | Operational |
| **Strategist** | Planning, synthesis, positioning, forecasting | Execution plans, strategy recommendations, forecasts | Operational |
| **Scribe** | Drafting emails, reports, documents, presentations | Email drafts, briefs, reports, slide decks | Operational |
| **Operator** | CRM operations, calendar, integrations, internal tasks | CRM records, calendar events, integration actions | Operational |
| **Scout** | News monitoring, signal detection, market intelligence | Signals, alerts, market updates, regulatory intel | Operational |

## 5.2 Dynamic Agent Creation

When a goal requires capabilities beyond the six core agents, ARIA can dynamically create specialized sub-agents:

```
User: "I need to prepare for a board presentation on Q3 pipeline performance."

ARIA's reasoning:
- Strategist: Overall narrative and positioning
- Analyst: Data gathering and analysis
- Scribe: Slide deck creation
- NEW: "BoardPrepAgent" — specialized for executive audience
  - Combines Strategist + Analyst + Scribe capabilities
  - Adds: executive summary format, ROI framing, risk mitigation language
  - Temporary: exists for this goal only
```

Dynamic agents extend BaseAgent, inherit core capabilities, and are scoped to a specific goal. They're logged in Procedural Memory for potential reuse.

## 5.3 Agent Execution Pipeline

| Stage | What Happens | Where | User Visibility |
|-------|-------------|-------|----------------|
| 1 | Goal approved by user | ARIA Workspace conversation | Approve button click |
| 2 | GoalExecutionService decomposes into sub-tasks | Backend | Progress indicator |
| 3 | Agents spawned for sub-tasks | Backend | Agent Status panel updates |
| 4 | Agents execute via OODA loop | Backend | Real-time progress via WebSocket |
| 5 | Results stored in memory | Memory system | None (background) |
| 6 | Actions classified by risk | GoalExecutionService | None (background) |
| 7 | Low-risk: auto-executed | Backend | Activity feed entry |
| 8 | High-risk: presented for approval | WebSocket → ARIA conversation | Approval card in conversation |
| 9 | Results browsable | Layer 2 content pages | Intelligence/Pipeline badges |

## 5.4 Action Risk Routing

| Risk Level | Examples | Behavior | "Coming Soon" |
|-----------|----------|----------|---------------|
| **LOW** | Research, data gathering, memory updates | Auto-execute. Log to Activity. | Full Autonomy: identical |
| **MEDIUM** | CRM field updates, calendar suggestions | Notify. Auto-execute if not rejected in 30 min. | Full Autonomy: auto-execute immediately |
| **HIGH** | Email drafts, meeting invites, strategy changes | Require approval. Presented in conversation. | Full Autonomy: auto-execute with notification |
| **CRITICAL** | Sending external emails, modifying deal stages, financial commitments | Always require approval. Cannot be auto-executed. | Full Autonomy: still requires approval |

**In-app indicator:** Settings → Autonomy shows current level (Guided) with a preview of Full Autonomy capabilities marked "Coming Soon — Q3 2026."

---

# 6. Interaction Flows

## 6.1 First Login (Post-Onboarding)

**Mode:** ARIA Workspace (full conversation) or Dialogue Mode (avatar briefing)

ARIA's presence resolves. First message streams in:

> **ARIA:** Good morning, Dhruv. I've been getting up to speed on Repligen since you brought me on.
>
> Here's where I am: I've compiled 28 facts about Repligen, identified 6 competitors in the bioprocessing space, and mapped your company's product portfolio across chromatography, filtration, and analytics.
>
> Based on your BD role and what I've learned, I'd like to propose my first priorities. Can we discuss?

ARIA then presents 3–4 proposed goals as **Goal Plan Cards** inline. User discusses, approves, modifies, or rejects each.

**UI Commands fired:** ARIA updates the sidebar badges (Intelligence: "6 competitors mapped", Pipeline: "28 facts compiled").

## 6.2 Daily Use: Morning Briefing

**Mode:** Dialogue Mode (avatar delivers briefing) or ARIA Workspace (text briefing)

The user's day starts with ARIA's briefing. If Dialogue Mode, ARIA's avatar appears on the left, the transcript with rich data cards on the right:

> **ARIA (avatar speaking):** Good morning, Dhruv. Three things matter today.
>
> First, you have 4 meetings. The critical one is Samsung Biologics at 10 AM — I've prepared a full brief with their recent capacity expansion data and competitive positioning against Lonza.
>
> **[MEETING CARD: Samsung Biologics — 10:00 AM — View Brief]**
>
> Second, overnight I found a buying signal: Hooli's champion viewed your pricing page 3 times yesterday. Health score jumped 15 points. I'd recommend reaching out today.
>
> **[SIGNAL CARD: Hooli Buying Signal — +15pts — Draft Outreach]**
>
> Third, Competitor X announced a 15% price cut in APAC. This affects 2 accounts in your pipeline. I've updated the battle card with counter-positioning.
>
> **[ALERT CARD: Competitor Price Cut — View Battle Card]**
>
> What would you like to focus on first?

**UI Commands fired:** While delivering the briefing, ARIA updates sidebar badges, pre-loads the Samsung brief in Intelligence, and flags Hooli in Pipeline.

## 6.3 Conversational Navigation

User can navigate the app entirely through conversation:

> **User:** "Pull up the Lonza battle card"
> 
> **ARIA navigates to Intelligence → Battle Cards → Lonza**
> **Right panel updates with Lonza competitive signals**
> 
> **ARIA:** "Here's Lonza. Since our last review, they've lost 3 key accounts and their new CCO is restructuring the sales org. This is our window — want me to draft outreach to their displaced customers?"

> **User:** "Show me leads that went silent"
>
> **ARIA navigates to Pipeline with filter: Last Activity > 14 days**
> **Right panel shows health drop alerts**
>
> **ARIA:** "I found 4 leads with no activity in the past two weeks. Initech is the most concerning — they were at 'Proposal Sent' stage. Want me to draft re-engagement emails?"

## 6.4 Email Draft Review (from mockup Image 5)

When user navigates to Communications → Draft, or ARIA presents a draft:

**Center workspace:** Full email preview with To, Subject, body, formatting toolbar, and Send/Save/Regenerate actions.

**Right panel — ARIA Insights:**
- **WHY I WROTE THIS:** "Referenced Q3 Pitch Deck Slide 4 regarding retention metrics. The recipient (Sarah) previously asked about unit economics." Source tags: `source:salesforce` `source:g-drive`
- **TONE & VOICE:** Selector chips: Professional (active), Casual, Urgent, Empathetic
- **ANALYSIS:** Read Time: 45s | AI Confidence: 98%
- **NEXT BEST ACTION:** "Schedule a follow-up task if no reply within 3 days." [Auto-schedule Task]
- **SUGGESTED REFINEMENTS:** "Make it more assertive →" "Shorten the CTA →"

## 6.5 Lead Detail View (from mockup Image 7)

Three-column layout for individual lead:

**Left section:** Stakeholder cards (Sarah Jenkins, CTO — Decision Maker — Positive Sentiment)

**Center section:** Relationship Lifecycle timeline (Market Signal: Series B → Email: Budget Approved → Zoom Meeting: Product Demo)

**Right panel — ARIA Intelligence:**
- **STRATEGIC ADVICE:** "Sarah is the key blocker. Sentiment analysis suggests she needs technical validation. Suggest sending the security whitepaper now." [Generate Email Draft]
- **BUYING SIGNALS:** High Intent — "Mentioned 'deployment timeline' 3x in last call" ✓ "Asked about SLA specifically for enterprise tier" ✓
- **ACTIVE OBJECTIONS:** 1 Critical — "Pricing: Concern regarding cost per seat for 500+ users." [View Talking Points]
- **SUGGESTED NEXT STEPS:** □ Send Technical Whitepaper □ Schedule follow-up with Mark

## 6.6 "Coming Soon" Indicators

Placed naturally within the app where users would expect expanded capabilities:

| Location | Indicator | Text |
|----------|-----------|------|
| Settings → Autonomy | Disabled toggle with badge | "Full Autonomy — Coming Q3 2026. ARIA will execute all non-critical actions automatically." |
| Settings → Integrations | Section | "Browser & OS Control — Coming Q3 2026. ARIA will be able to interact with any application on your computer." |
| Settings → Integrations | Section | "Enterprise Network — Coming 2027. Connect your ARIA with your team's ARIAs for organizational intelligence." |

---

# 7. Frontend Architecture

## 7.1 Clean Rebuild Strategy

**Approach:** Clean rebuild with extracted design primitives. Move all 12 old pages to `_deprecated/` folder. Extract atomic components (buttons, badges, cards, skeleton loaders) into a clean component library. Build all new pages and layouts fresh.

### What Gets Extracted (Reused)

| Component Category | Examples | Why Reusable |
|-------------------|----------|-------------|
| Design primitives | Button, Input, Card, Badge, Skeleton | Framework-agnostic, design-system aligned |
| Data display atoms | HealthScoreBadge, StakeholderCard, SignalCard | Render identically in pages and conversation |
| API client | Supabase hooks, auth context, API functions | Backend interface unchanged |
| Design tokens | Tailwind config, CSS variables, color system | Design system is settled |

### What Gets Rebuilt (New)

| Component Category | Examples | Why New |
|-------------------|----------|---------|
| App shell | Three-column layout, sidebar, routing | Dual-control navigation requirement |
| ARIA Workspace | Conversation thread, rich inline components | Core interaction model |
| Dialogue Mode | Avatar container, transcript, data cards | Doesn't exist yet |
| Content pages | Battle Cards, Pipeline, Communications, etc. | ARIA Intelligence Panel integration |
| UICommandExecutor | Navigation commands, highlighting, panel updates | Entirely new concept |
| SessionManager | Cross-modal persistence, session state | Entirely new concept |
| ModalityController | Chat/voice/avatar switching | Entirely new concept |
| IntelPanelController | Context-adaptive right panel | Entirely new concept |

## 7.2 Core Frontend Services

| Service | Purpose | State Management |
|---------|---------|-----------------|
| **SessionManager** | Persists user session across modalities, tab closes, page reloads | Supabase-backed, not localStorage |
| **UICommandExecutor** | Executes ARIA's navigation, highlighting, and panel commands | Receives commands via WebSocket |
| **ModalityController** | Manages transitions between chat, voice, and avatar | React context |
| **IntelPanelController** | Adapts right panel content to current route/context | Route-aware React context |
| **WebSocketManager** | Persistent connection for real-time communication | Singleton, auto-reconnect |
| **MemoryPrimingBridge** | Triggers memory retrieval when user navigates or context changes | Calls backend Memory Priming Service |
| **TavusController** | Manages Tavus avatar session, Raven-0 signals, WebRTC | Wraps Tavus SDK |

## 7.3 WebSocket as Primary Communication Channel

All real-time communication flows through a persistent WebSocket connection:

| Event | Direction | Payload | Frontend Action |
|-------|-----------|---------|-----------------|
| `aria.message` | Server → Client | Message + rich components + UI commands | Render message, execute UI commands |
| `aria.thinking` | Server → Client | Processing indicator | Show ambient presence animation |
| `aria.speaking` | Server → Client | Avatar script + emotion | Trigger Tavus TTS + lip sync |
| `action.pending` | Server → Client | Action details + risk level | HIGH: show in conversation. MEDIUM: badge. |
| `action.completed` | Server → Client | Action summary | Update Activity feed |
| `progress.update` | Server → Client | Goal delta | Update progress tracker |
| `signal.detected` | Server → Client | Signal details + salience | High: conversation interrupt. Low: badge. |
| `emotion.detected` | Server → Client | Raven-0 emotion signal | Adjust ARIA's response style |
| `user.message` | Client → Server | Text/voice transcript | Process through ARIA engine |
| `user.navigate` | Client → Server | Route change | Trigger contextual memory priming |
| `session.sync` | Bidirectional | Session state delta | Keep client and server in sync |

## 7.4 Visual Theme System

| Context | Theme | Background | Text | Accents |
|---------|-------|-----------|------|---------|
| ARIA Workspace | Dark | #0A0A0B (Obsidian) | #EDEDEF | Electric Blue #2E66FF |
| Dialogue Mode | Dark | #0A0A0B (Obsidian) | #EDEDEF | Electric Blue #2E66FF |
| Content Pages | Light | #F8FAFC (Warm white) | #1E293B | Muted blue #5B6E8A |
| Sidebar | Always Dark | #0F1117 | #E8E6E1 | Active: #2E66FF bg |
| Right Panel (on dark) | Dark elevated | #121214 | #EDEDEF | — |
| Right Panel (on light) | Light elevated | #FFFFFF | #1E293B | — |

### Typography

| Usage | Font | Weight | Size |
|-------|------|--------|------|
| Headings (dark context) | Instrument Serif | Italic | 18–32px |
| Headings (light context) | Instrument Serif | Regular/Italic | 18–32px |
| Body text | Inter | 300–400 | 14–16px |
| UI elements | Inter | 500–600 | 12–14px |
| Data labels, timestamps | JetBrains Mono | 400–500 | 10–12px |
| ARIA's key insights | Instrument Serif | Regular | 16px |

---

# 8. Rich Inline Content Components

These components appear BOTH inside ARIA's conversation messages (Layer 1) AND as standalone elements on content pages (Layer 2). They are built once and work in both contexts.

| Component | In Conversation | On Content Page | Interaction |
|-----------|----------------|-----------------|-------------|
| **Goal Plan Card** | ARIA proposes a goal | Actions page shows all goals | Approve / Modify / Reject |
| **Execution Plan Card** | ARIA shows planned approach | Goal detail view | Approve Plan / Modify |
| **Lead Table** | ARIA presents discovered leads | Pipeline page | Sort, filter, approve/reject |
| **Draft Preview** | ARIA shows email draft | Communications page | Edit, approve, send |
| **Insight Card** | ARIA surfaces a signal | Intelligence page | Acknowledge, investigate |
| **Battle Card** | ARIA presents competitive intel | Intelligence page | Review, edit, request more |
| **Meeting Brief Card** | ARIA prepares for meeting | Briefing section | View full brief, discuss |
| **Inventory Risk Card** | ARIA flags supply chain risk | Intelligence page | Model scenarios, take action |
| **Approval Button Row** | Any action needing sign-off | Action queue | Approve, Reject, Defer |
| **Progress Tracker** | Goal execution progress | Actions page | Visual milestones |
| **Agent Status Indicator** | Which agents are working | Actions page | Per-agent status, pause/redirect |
| **Data Chart** | Pipeline metrics, trends | Dashboard/Briefing | Apple Health-inspired, Recharts |
| **Suggestion Chips** | Context-aware next actions | Bottom of conversation | Click to execute |
| **Forecast Card** | Revenue predictions, accuracy | Pipeline page | Approve forecast, adjust |

---

# 9. Implementation Sequence

## Sprint 0: Foundation (2 days)

| Task | Priority | Notes |
|------|----------|-------|
| Run all 43 missing database migrations | P0 | Unblocks everything |
| Fix chat endpoint mismatch (/chat/message vs /chat) | P0 | Chat must work |
| Wire memory persistence (episodic, semantic to real tables) | P0 | ARIA must remember |
| Inject Digital Twin into chat responses | P0 | ARIA must know the user |
| Extract reusable design primitives to component library | P0 | Foundation for rebuild |
| Move old 12 pages to _deprecated/ folder | P0 | Clean slate |

## Sprint 1: Core Shell + ARIA Workspace (4 days)

| Task | Priority |
|------|----------|
| Three-column AppShell (sidebar + workspace + intel panel) | P0 |
| SessionManager (Supabase-backed, cross-modal persistence) | P0 |
| WebSocketManager (persistent connection, auto-reconnect) | P0 |
| UICommandExecutor (navigate, highlight, panel update) | P0 |
| ARIA Workspace — full conversation with streaming | P0 |
| Rich inline components (Goal Plan Card, Approval Row, Insight Card, Draft Preview) | P0 |
| Sidebar with 7 items, ARIA Pulse indicator | P0 |
| IntelPanelController (context-adaptive right panel) | P1 |

## Sprint 2: Execution Engine (4 days)

| Task | Priority |
|------|----------|
| GoalExecutionService (core orchestrator) | P0 |
| Wire ALL 6 agents to execution pipeline | P0 |
| Dynamic agent creation framework | P0 |
| OODA loop implementation (not just documentation) | P0 |
| Action risk routing (LOW/MEDIUM/HIGH/CRITICAL) | P0 |
| Agent spawning with real context passing | P0 |
| WebSocket events for agent → frontend pipeline | P0 |

## Sprint 3: Content Pages + Avatar (4 days)

| Task | Priority |
|------|----------|
| Dialogue Mode (split screen: avatar + transcript) | P0 |
| Tavus integration (avatar, TTS, lip sync) | P0 |
| Voice input (speech-to-text, space-to-talk) | P0 |
| ModalityController (chat ↔ voice ↔ avatar transitions) | P0 |
| Pipeline page (lead table + ARIA intel panel) | P0 |
| Intelligence page (battle cards + ARIA intel panel) | P0 |
| Communications page (email drafts + ARIA insights panel) | P1 |
| Lead Detail page (stakeholders + timeline + ARIA intelligence) | P1 |

## Sprint 4: Wire + Polish (3 days)

| Task | Priority |
|------|----------|
| First Conversation Generator (post-login goal proposals) | P0 |
| Morning briefing flow (Dialogue Mode or text) | P0 |
| Raven-0 emotion detection integration | P1 |
| "Coming Soon" indicators (Full Autonomy, Browser Control, Enterprise Network) | P0 |
| Error states (ARIA explains gracefully in conversation) | P0 |
| Empty states ("ARIA is building this analysis") | P0 |
| Actions page (goal progress, agent status, action queue) | P0 |
| Settings page (profile, integrations, autonomy, ARIA persona) | P1 |

## Sprint 5: Demo-Ready (2 days)

| Task | Priority |
|------|----------|
| 3-minute investor demo path optimization | P0 |
| Presence animations (The Pulse, The Arrival, The Settle) | P1 |
| Suggestion chips after every ARIA response | P0 |
| Dual-control navigation polish (ARIA drives smoothly) | P0 |
| Cross-modality session handoff testing | P0 |
| Webcam opt-in flow for Raven-0 | P1 |

---

# 10. Success Criteria

## Investor Demo (3 minutes)

1. ARIA's avatar greets by name, demonstrates company knowledge
2. ARIA proposes strategic goals with rationale (Goal Plan Cards)
3. Investor approves → sees execution plan with agents and timeline
4. ARIA navigates to relevant content pages while explaining
5. ARIA highlights competitive intelligence, presents battle card
6. Real-time progress: agents execute, results appear
7. ARIA speaks through avatar with lip sync and emotion
8. Reaction: "holy shit, this is Jarvis"

## Quantitative Targets

| Metric | Target |
|--------|--------|
| Time in ARIA Workspace + Dialogue Mode vs. content pages | >60% in Layer 1/1a |
| Goals with full agent execution | 100% trigger agents |
| All 6 agents producing real output | 100% |
| Morning briefing delivered before user's configured time | 100% |
| Cross-modal session persistence (no context loss on switch) | 100% |
| Memory recall accuracy (can ARIA find past info?) | >95% |
| Forms/CRUD pages remaining | 0 (except Settings) |
| Avatar lip sync latency | <500ms |
| UI command execution latency | <200ms |

## The Tests

| Test | Pass | Fail |
|------|------|------|
| Who initiates? | ARIA proposes | User clicks "New" button |
| Content source? | Agent produces, ARIA presents | User types into form |
| Who navigates? | ARIA drives, user can also click | Only user navigates |
| Memory persistent? | ARIA remembers everything across sessions and modalities | "I don't have context on that" |
| Avatar present? | Tavus avatar with voice and lip sync | Text-only chatbot |
| Right panel adaptive? | Changes with every context/route | Static or absent |
| Empty state? | "ARIA is working on this" | "No data. Click to add." |
| Errors? | ARIA explains in conversation | Red toast with error code |

---

> **DOCUMENT AUTHORITY:** This Interaction Design Document v3.0 is the north star. When Claude Code output conflicts with this document, this document wins. Apply the test: "holy shit, this is Jarvis."
