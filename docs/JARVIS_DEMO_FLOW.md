# JARVIS Demo Flow: Monday Morning with ARIA

> **Purpose:** Step-by-step walkthrough of the full ARIA experience for investor demos and beta user onboarding.
>
> **Duration:** ~12 minutes live demo, ~20 minutes interactive
>
> **Audience:** Investors (pre-seed), beta life-sciences sales reps

---

## Demo Narrative

**Persona:** Jordan Rivera, Account Executive at a mid-size CDMO broker covering 15 accounts in the life sciences space. Jordan has 3 meetings today and ARIA has been running autonomously overnight.

---

## Phase A: 6 AM — ARIA Works While You Sleep

*ARIA's cron scheduler fires. No human involved.*

| Step | What Happens | Backend Service | Tavus Feature | Frontend Component |
|------|-------------|----------------|---------------|-------------------|
| A1 | Morning briefing generated | `BriefingService.generate_briefing()` | — | — (stored in DB) |
| A2 | 3 meeting briefs prepped | `AnalystAgent.execute(type="meeting_prep")` + `ScoutAgent.execute()` | — | — |
| A3 | Overnight signal detected: Catalent $200M funding | `ScoutAgent.execute(type="market_scan")` via `scout_signal_scan_job.py` | — | — |
| A4 | Video briefing session created | `VideoSessionService.create_session(type="briefing")` | Phoenix-3 persona configured | — |
| A5 | Stale lead alert queued | `ProactiveRouter.route(priority=MEDIUM, category=STALE_LEAD)` | — | — |
| A6 | Activity logged (6 items) | `ActivityService.log_activity()` ×6 | — | — |

**Key code path:**
```
src/tasks/scheduled.py → cron entry point (every 15 min)
  ├── _check_and_prompt_debriefs() → DebriefScheduler
  ├── _scout_signal_scan() → ScoutAgent market detection
  ├── _stale_leads_check() → ProactiveRouter
  └── daily_briefing_job.py → BriefingService (timezone-aware, fires ~6 AM user local)
```

**Demo note:** This happens before the user wakes up. Show the activity log timestamps.

---

## Phase B: 8 AM — Jordan Logs In

*Jordan opens ARIA. Everything is ready.*

| Step | What Happens | Backend Service | Tavus Feature | Frontend Component |
|------|-------------|----------------|---------------|-------------------|
| B1 | Dashboard shows "Morning Briefing Ready" with video play button | `GET /briefings/today` | — | `VideoBriefingCard` (blue gradient play button) |
| B2 | Intelligence panel shows 2 new signals | `GET /signals?status=new` | — | `IntelPanel` → `JarvisInsightsModule`, `NewsAlertsModule` |
| B3 | Activity feed shows 6 overnight items | `ActivityFeedService.get_activity_feed()` | — | `ActivityFeed` (compact mode in sidebar) |
| B4 | Chat has ARIA message: "Good morning! I've prepared your briefing..." | WebSocket `aria.message` on connect | — | `ConversationThread` → `MessageBubble` |
| B5 | Suggestion chips: "Watch briefing", "Show meeting schedule", "What's new?" | `suggestions[]` in WS payload | — | `SuggestionChips` |

**Key frontend path:**
```
frontend/src/components/pages/ARIAWorkspace.tsx
  ├── useTodayBriefing() → injects VideoBriefingCard
  ├── ConversationThread → shows ARIA greeting
  └── useWebSocket → receives overnight queued messages

frontend/src/components/shell/IntelPanel.tsx
  ├── JarvisInsightsModule → shows JARVIS intelligence
  └── NewsAlertsModule → shows market signals

frontend/src/components/activity/ActivityFeed.tsx
  └── compact mode → shows 6 overnight items
```

**Demo script:** "Notice ARIA has already been working. She generated your briefing at 6 AM, prepped your meetings, and spotted that your competitor Catalent just closed a $200M round. Let's watch the briefing."

---

## Phase C: Video Briefing

*Jordan clicks "Watch Briefing". Split-screen dialogue mode opens.*

| Step | What Happens | Backend Service | Tavus Feature | Frontend Component |
|------|-------------|----------------|---------------|-------------------|
| C1 | Dialogue mode opens: avatar left, transcript right | `VideoSessionService` | Phoenix-3 avatar renders | `DialogueMode` (split layout) |
| C2 | ARIA speaks about today's schedule | Pre-loaded briefing content via Knowledge Base | CVI lip-sync, natural speech | `AvatarContainer` + `TranscriptPanel` |
| C3 | ARIA covers lead updates and Catalent signal | Briefing data fed to CVI | Natural voice modulation | `TranscriptPanel` entries |
| C4 | Jordan asks: "Tell me more about the Novartis restructuring" | User speech → STT → CVI tool call | Raven-1 detects curiosity | `TranscriptPanel` (user entry) |
| C5 | Tool call: `lookup_company("Novartis")` → Scout agent | `VideoToolExecutor.execute_tool()` → `ScoutAgent` | Tool call routing | — (backend only) |
| C6 | Battle card overlay appears on screen | `ToolResult.rich_content` → `content_overlay` WS event | — | `VideoToastStack` → battle card |
| C7 | ARIA explains implications vocally | Scout result → natural language via LLM | CVI speaks result | `AvatarContainer` |
| C8 | Raven-1: Jordan is engaged (leaning forward, eye contact) | `PerceptionIntelligenceService.process_perception_analysis()` | Raven-1 perception webhook | — (backend processes) |
| C9 | Briefing ends, summary appears in chat | `ContextBridgeService.video_to_chat_context()` | — | `BriefingSummaryCard` in `ConversationThread` |
| C10 | Transcript stored as episodic memory | `EpisodicMemory.store()` via `VideoSessionService.end_session()` | — | — |

**Key code path — Tool call during video:**
```
Tavus CVI → conversation.tool_call event
  → Frontend: POST /video/tools/execute
    → VideoToolExecutor.execute_tool("lookup_company", {...})
      → ScoutAgent.execute(task={type: "company_research"})
      → LLMClient.generate_response() → natural language
    → ToolResult(spoken_text="...", rich_content={battle_card: {...}})
  → Frontend: conversation.echo (spoken text back to CVI)
  → Frontend: VideoToastStack renders battle card overlay
```

**Key code path — Perception:**
```
Raven-1 webhook → POST /perception/analysis
  → PerceptionIntelligenceService.process_perception_analysis()
    → Store metrics in perception_analysis table
    → If linked to lead → feed_to_conversion_scoring()
```

**Key code path — Context bridge:**
```
VideoSessionService.end_session()
  → ContextBridgeService.video_to_chat_context()
    → LLM extracts summary, action_items, commitments from transcript
    → ProspectiveMemory.store() for each action item
    → WorkingMemoryManager updates session context
    → ws_manager.emit("aria.message") → BriefingSummaryCard in chat
```

**Demo script:** "ARIA is speaking naturally about Jordan's day. Watch — Jordan asks about Novartis and ARIA immediately pulls up a competitive battle card. Notice the overlay — that's real-time tool execution during a video conversation. And look at Raven detecting Jordan's engagement level."

---

## Phase D: Post-Meeting Debrief

*Jordan comes back from the Moderna meeting at 11 AM.*

| Step | What Happens | Backend Service | Tavus Feature | Frontend Component |
|------|-------------|----------------|---------------|-------------------|
| D1 | ARIA prompts: "How did your Moderna meeting go?" | `DebriefScheduler` → `ProactiveRouter.route(DEBRIEF_PROMPT)` | — | `MessageBubble` with debrief CTA |
| D2 | Jordan starts debrief video session | `VideoSessionService.create_session(type="debrief")` | Phoenix-3 avatar, debrief persona | `DialogueMode` (debrief mode) |
| D3 | ARIA asks structured questions | CVI guided by debrief prompt template | Natural conversational flow | `TranscriptPanel` |
| D4 | ARIA extracts action items from conversation | `DebriefService.process_debrief()` → Anthropic extraction | — | — |
| D5 | Raven-1: Jordan seemed confident → positive outcome | `PerceptionIntelligenceService` → outcome signal | Raven-1 emotion detection | — |
| D6 | Follow-up email draft auto-generated | `ScribeAgent.execute(type="email_draft")` | — | `DraftPreview` in chat |
| D7 | Action items stored as prospective memories | `ProspectiveMemory.store()` per item | — | — |
| D8 | Lead health score recalculated | `HealthScoreCalculator.calculate()` + DB update | — | `IntelPanel` → lead health badge |
| D9 | Conversion score recalculated | `PerceptionIntelligenceService.feed_to_conversion_scoring()` | — | — |
| D10 | Debrief summary + video context bridged to chat | `ContextBridgeService.video_to_chat_context()` | — | `ConversationThread` |

**Key code path — Debrief extraction:**
```
User speaks debrief notes in video
  → VideoSessionService captures transcript
  → On session end:
    → DebriefService.process_debrief(notes=transcript_text)
      → Anthropic API extracts: summary, outcome, action_items, commitments, insights
      → DebriefService.post_process_debrief()
        → LeadEventService.record_event(type="debrief_completed")
        → ProspectiveMemory.store() for each action item
        → ScribeAgent.execute(type="email_draft") for follow-up
        → HealthScoreCalculator.calculate() → updates lead_memory
        → ActivityService.log_activity(type="debrief_processed")
```

**Key code path — Perception → Lead health:**
```
Raven-1 perception data (confidence detected)
  → PerceptionIntelligenceService.process_perception_analysis()
    → calculate_meeting_quality_score()
    → generate_perception_insights()
    → feed_to_conversion_scoring(lead_memory_id)
      → Updates conversion_scores table
      → HealthScoreCalculator factors in perception sentiment
```

**Demo script:** "Notice ARIA proactively asked about the meeting — she knew it ended 30 minutes ago. Jordan debriefs naturally by talking, and ARIA extracts two action items, identifies a buying signal, and auto-drafts a follow-up email. The lead health score just jumped from 65 to 82."

---

## Phase E: Autonomous Follow-Through

*ARIA presents the email draft for approval.*

| Step | What Happens | Backend Service | Tavus Feature | Frontend Component |
|------|-------------|----------------|---------------|-------------------|
| E1 | Email draft presented for approval | `ActionQueueService.queue_action(risk="high")` | — | `DraftPreview` + approve/reject buttons |
| E2 | Autonomy check: level 2 → requires approval | `AutonomyCalibrationService.can_auto_execute()` → `False` | — | — |
| E3 | Jordan approves the email | `ActionQueueService.approve_action()` | — | Button click → WS `user.approve` |
| E4 | Email sent via Composio integration | `ScribeAgent` → Composio OAuth → Gmail/Outlook | — | — |
| E5 | Activity logged | `ActivityService.log_activity(type="email_drafted")` | — | `ActivityFeed` new item |
| E6 | ARIA confirms: "Email sent to Sarah at Moderna" | WS `aria.message` | — | `MessageBubble` |

**Alternative path (autonomy level >= 3):**
```
AutonomyCalibrationService.can_auto_execute("email_draft") → True (medium risk, level 3+)
  → ScribeAgent auto-sends
  → ProactiveRouter.route(priority=LOW, category="action_completed")
  → Activity logged
  → WS notification: "I sent the follow-up to Sarah. Here's what I wrote: [preview]"
```

**Key code path — Autonomy routing:**
```
Action created (email_send, risk=high)
  → AutonomyCalibrationService.can_auto_execute(user_id, "email_send")
    → Fetch user autonomy_level from user_settings
    → Check _LEVEL_PERMISSIONS[level] against _HIGH_RISK_ACTIONS
    → Level 1-3: return False (requires approval)
    → Level 4-5: return True (auto-execute)
  → If False: ActionQueueService.queue_action(status="pending_approval")
    → WS event: action.pending → frontend shows approval UI
  → If True: Execute immediately, notify after
```

**Demo script:** "ARIA drafted this email based on the debrief. At autonomy level 2, she asks Jordan to review it first. One click to approve. Over time, as ARIA earns trust, she'll auto-send low-risk follow-ups and just notify Jordan after."

---

## Integration Wiring Verification

All 12 integration points confirmed wired:

| # | Integration Point | Status | Verification |
|---|------------------|--------|-------------|
| 1 | Video transcript → episodic memory | Wired | `VideoSessionService.end_session()` calls `EpisodicMemory.store()` |
| 2 | Debrief insights → semantic + lead memory | Wired | `DebriefService.post_process_debrief()` → `LeadEventService`, semantic facts |
| 3 | Action items → prospective memory | Wired | `ContextBridgeService` + `DebriefService` → `ProspectiveMemory.store()` |
| 4 | Raven-1 perception → lead health score | Wired | `PerceptionIntelligenceService.feed_to_conversion_scoring()` |
| 5 | Tool calls during video → all 6 agents | Wired | `VideoToolExecutor` → `TOOL_AGENT_MAP` routes to agents |
| 6 | Chat <-> video context bridge | Wired | `ContextBridgeService.chat_to_video_context()` + `video_to_chat_context()` |
| 7 | Cron → proactive briefings + alerts | Wired | `src/tasks/scheduled.py` runs 5 tasks every 15 min |
| 8 | Autonomy calibration → action approval | Wired | `AutonomyCalibrationService` + `ActionQueueService` |
| 9 | Activity feed <- everything | Wired | `ActivityService.log_activity()` called from all services |
| 10 | Knowledge Base → 30ms RAG in video | Wired | `_DEFAULT_KB_TAGS` in `VideoSessionService` fed to Tavus CVI |
| 11 | Tavus memories → cross-session continuity | Wired | `ARIAPersonaManager` maintains persona state across sessions |
| 12 | Audio-only mode for mobile | Wired | `DialogueMode` supports `audioOnly` prop, `ModalityController.switchTo("audio")` |

---

## File Reference Map

### Backend Services (by phase)

| Phase | File | Class/Function |
|-------|------|---------------|
| A | `src/services/briefing.py` | `BriefingService.generate_briefing()` |
| A | `src/agents/scout.py` | `ScoutAgent.execute()` |
| A | `src/agents/analyst.py` | `AnalystAgent.execute()` |
| A | `src/services/video_service.py` | `VideoSessionService.create_session()` |
| A | `src/services/proactive_router.py` | `ProactiveRouter.route()` |
| A | `src/tasks/scheduled.py` | Cron entry point |
| A | `src/jobs/daily_briefing_job.py` | Timezone-aware briefing generation |
| A | `src/jobs/scout_signal_scan_job.py` | Scout market scanning |
| A | `src/jobs/stale_leads_job.py` | Stale lead detection |
| B | `src/services/activity_feed_service.py` | `ActivityFeedService.get_activity_feed()` |
| B | `src/services/signal_service.py` | `SignalService` |
| C | `src/integrations/tavus_tool_executor.py` | `VideoToolExecutor.execute_tool()` |
| C | `src/integrations/tavus_tools.py` | `TOOL_AGENT_MAP`, `VALID_TOOL_NAMES` |
| C | `src/services/perception_intelligence.py` | `PerceptionIntelligenceService` |
| C | `src/services/context_bridge.py` | `ContextBridgeService` |
| C | `src/memory/episodic.py` | `EpisodicMemory.store()` |
| D | `src/services/debrief_service.py` | `DebriefService` (3-phase workflow) |
| D | `src/services/debrief_scheduler.py` | `DebriefScheduler` |
| D | `src/agents/scribe.py` | `ScribeAgent.execute()` |
| D | `src/memory/prospective.py` | `ProspectiveMemory.store()` |
| D | `src/memory/health_score.py` | `HealthScoreCalculator.calculate()` |
| E | `src/services/autonomy_calibration.py` | `AutonomyCalibrationService` |
| E | `src/services/action_queue_service.py` | `ActionQueueService` |
| E | `src/services/activity_service.py` | `ActivityService.log_activity()` |

### Frontend Components (by phase)

| Phase | File | Component |
|-------|------|-----------|
| B | `src/components/briefing/VideoBriefingCard.tsx` | `VideoBriefingCard` |
| B | `src/components/shell/IntelPanel.tsx` | `IntelPanel` |
| B | `src/components/activity/ActivityFeed.tsx` | `ActivityFeed` |
| B | `src/components/conversation/ConversationThread.tsx` | `ConversationThread` |
| B | `src/components/conversation/SuggestionChips.tsx` | `SuggestionChips` |
| C | `src/components/avatar/DialogueMode.tsx` | `DialogueMode` |
| C | `src/components/avatar/AvatarContainer.tsx` | `AvatarContainer` |
| C | `src/components/avatar/TranscriptPanel.tsx` | `TranscriptPanel` |
| C | `src/components/video/VideoContentToast.tsx` | `VideoToastStack` |
| C | `src/components/briefing/BriefingSummaryCard.tsx` | `BriefingSummaryCard` |
| D | `src/components/avatar/DialogueMode.tsx` | `DialogueMode` (debrief mode) |
| E | `src/components/rich/DraftPreview.tsx` | `DraftPreview` |
| All | `src/core/UICommandExecutor.ts` | UI automation |
| All | `src/core/WebSocketManager.ts` | Real-time communication |
| All | `src/core/ModalityController.ts` | Mode switching |

---

## Key Metrics to Highlight During Demo

- **Time saved:** 3 meetings prepped in 0 minutes (ARIA did it at 6 AM)
- **Signal detection:** Competitor funding round caught within hours
- **Debrief to action:** Meeting → follow-up email in < 2 minutes
- **Memory persistence:** Every interaction permanently stored, never lost
- **Autonomy calibration:** Trust builds over time, ARIA becomes more autonomous
- **Cross-modality:** Seamless text → video → text transitions

---

## Investor Talking Points

1. **"72% admin trap":** A 5-person team with ARIA performs like 7. ARIA handles the admin.
2. **Proactive, not reactive:** ARIA works at 6 AM. The user wakes up to a prepared day.
3. **Multi-modal intelligence:** Text, voice, and video — all sharing one brain.
4. **Perception-driven:** Raven-1 reads emotional cues to calibrate follow-ups.
5. **Trust calibration:** Progressive autonomy. ARIA earns the right to act independently.
6. **Enterprise memory:** Nothing is ever lost. Six memory types, all persistent.
