# ARIA Frontend Architecture Document
## Technical Specification for Clean Rebuild

**Version:** 1.0 | **Date:** February 11, 2026 | **Companion to:** IDD v3.0 | **CONFIDENTIAL**

---

## 1. Architecture Overview

### 1.1 Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Framework | React 18 + TypeScript | Component framework |
| Build | Vite | Fast dev server + production builds |
| Styling | Tailwind CSS | Utility-first styling |
| State | React Context + Zustand | Global state management |
| Routing | React Router v6 | Client-side navigation (dual-control) |
| Real-time | WebSocket (native) | ARIA ↔ Frontend communication |
| Video | Tavus SDK + Daily.co | AI Avatar, WebRTC |
| Charts | Recharts | Apple Health-inspired data viz |
| Icons | Material Symbols Outlined | Consistent iconography |
| Fonts | Inter, Instrument Serif, JetBrains Mono | Typography system |

### 1.2 Directory Structure

```
frontend/src/
├── app/
│   ├── App.tsx                    # Root: providers, router
│   ├── AppShell.tsx               # Three-column layout
│   └── routes.tsx                 # Route definitions
│
├── core/                          # Core services (singletons)
│   ├── SessionManager.ts          # Cross-modal session persistence
│   ├── WebSocketManager.ts        # Persistent WS connection
│   ├── UICommandExecutor.ts       # ARIA's UI control system
│   ├── ModalityController.ts      # Chat ↔ Voice ↔ Avatar
│   ├── MemoryPrimingBridge.ts     # Triggers memory retrieval
│   └── TavusController.ts         # Avatar, TTS, Raven-0
│
├── contexts/                      # React contexts
│   ├── AuthContext.tsx             # Authentication (existing, reuse)
│   ├── SessionContext.tsx          # Unified session state
│   ├── ARIAContext.tsx             # ARIA state, modality, presence
│   ├── ThemeContext.tsx            # Dark/light theme switching
│   └── IntelPanelContext.tsx       # Right panel content state
│
├── stores/                        # Zustand stores
│   ├── conversationStore.ts       # Message thread, streaming
│   ├── agentStore.ts              # Agent status, progress
│   ├── notificationStore.ts       # Signals, alerts, badges
│   └── navigationStore.ts         # Current route, ARIA nav state
│
├── components/
│   ├── primitives/                # Extracted design primitives
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   ├── Card.tsx
│   │   ├── Badge.tsx
│   │   ├── Skeleton.tsx
│   │   ├── ProgressBar.tsx
│   │   ├── Avatar.tsx
│   │   └── Tooltip.tsx
│   │
│   ├── shell/                     # App shell components
│   │   ├── Sidebar.tsx            # 7-item nav + ARIA Pulse
│   │   ├── SidebarItem.tsx
│   │   ├── IntelPanel.tsx         # Context-adaptive right panel
│   │   ├── IntelPanelModules/     # Panel content modules
│   │   │   ├── MeetingsModule.tsx
│   │   │   ├── AlertsModule.tsx
│   │   │   ├── CompetitiveIntelModule.tsx
│   │   │   ├── DraftInsightsModule.tsx
│   │   │   ├── LeadIntelModule.tsx
│   │   │   ├── AgentStatusModule.tsx
│   │   │   └── CRMSnapshotModule.tsx
│   │   └── ARIAPulse.tsx          # Ambient presence indicator
│   │
│   ├── conversation/              # ARIA Workspace components
│   │   ├── ConversationThread.tsx  # Message list
│   │   ├── MessageBubble.tsx       # Single message (ARIA or user)
│   │   ├── StreamingText.tsx       # Typewriter effect
│   │   ├── InputBar.tsx            # Text + mic + space-to-talk
│   │   ├── SuggestionChips.tsx     # Context-aware suggestions
│   │   └── VoiceIndicator.tsx      # Waveform when listening
│   │
│   ├── rich/                      # Rich inline components (dual-use)
│   │   ├── GoalPlanCard.tsx
│   │   ├── ExecutionPlanCard.tsx
│   │   ├── ApprovalRow.tsx
│   │   ├── InsightCard.tsx
│   │   ├── DraftPreview.tsx
│   │   ├── BattleCard.tsx
│   │   ├── MeetingBriefCard.tsx
│   │   ├── LeadTable.tsx
│   │   ├── ProgressTracker.tsx
│   │   ├── AgentStatusCard.tsx
│   │   ├── DataChart.tsx
│   │   ├── SignalCard.tsx
│   │   ├── ForecastCard.tsx
│   │   ├── InventoryRiskCard.tsx
│   │   └── RichContentRenderer.tsx # Dispatches to correct component
│   │
│   ├── avatar/                    # Tavus avatar components
│   │   ├── DialogueMode.tsx        # Full split-screen layout
│   │   ├── AvatarContainer.tsx     # Tavus video embed
│   │   ├── CompactAvatar.tsx       # PiP floating avatar
│   │   ├── WaveformBars.tsx        # Audio visualization
│   │   ├── TranscriptPanel.tsx     # Right side of Dialogue Mode
│   │   └── BriefingControls.tsx    # Play/pause/skip/speed
│   │
│   └── pages/                     # Layer 2 content pages
│       ├── PipelinePage.tsx        # Lead table + filters
│       ├── IntelligencePage.tsx    # Battle cards + market signals
│       ├── CommunicationsPage.tsx  # Email drafts + sequences
│       ├── ActionsPage.tsx         # Goal progress + agent status
│       ├── LeadDetailPage.tsx      # Stakeholders + timeline
│       ├── BattleCardDetail.tsx    # Single battle card deep dive
│       └── SettingsPage.tsx        # Profile, integrations, autonomy
│
├── hooks/                         # Custom hooks
│   ├── useARIA.ts                 # Send messages, get responses
│   ├── useSession.ts              # Session state access
│   ├── useModality.ts             # Current modality, switch
│   ├── useWebSocket.ts            # WS connection + event handlers
│   ├── useIntelPanel.ts           # Panel content for current route
│   ├── useUICommands.ts           # Register for ARIA UI commands
│   ├── useTavus.ts                # Avatar session management
│   ├── useVoice.ts                # Speech-to-text, space-to-talk
│   └── useMemory.ts               # Memory retrieval triggers
│
├── api/                           # API client layer (mostly reuse)
│   ├── client.ts                  # Axios/fetch setup, auth headers
│   ├── chat.ts                    # Chat endpoints
│   ├── goals.ts                   # Goal CRUD + execution
│   ├── agents.ts                  # Agent status + control
│   ├── leads.ts                   # Lead/pipeline data
│   ├── intelligence.ts            # Battle cards, signals
│   ├── communications.ts          # Email drafts
│   ├── video.ts                   # Tavus session management
│   └── memory.ts                  # Memory retrieval endpoints
│
├── types/                         # TypeScript type definitions
│   ├── aria.ts                    # ARIAResponse, UICommand, etc.
│   ├── conversation.ts            # Message, RichContent types
│   ├── agents.ts                  # Agent, AgentStatus types
│   ├── leads.ts                   # Lead, Account, Stakeholder
│   ├── intelligence.ts            # BattleCard, Signal, etc.
│   ├── memory.ts                  # Memory types
│   └── session.ts                 # UnifiedSession type
│
├── utils/                         # Utilities
│   ├── theme.ts                   # Theme tokens + switching
│   ├── formatting.ts              # Date, number, text helpers
│   └── constants.ts               # App constants
│
└── _deprecated/                   # Old pages (git history)
    └── [all 12 old page components]
```

---

## 2. Core Services — Detailed Specifications

### 2.1 SessionManager

The SessionManager is the backbone of cross-modal persistence. It ensures ARIA never loses context regardless of how the user interacts.

```typescript
// core/SessionManager.ts

interface UnifiedSession {
  session_id: string;
  user_id: string;
  
  // Working memory state
  active_topics: Topic[];
  pending_actions: PendingAction[];
  current_goal_context: GoalContext | null;
  recent_entities: Entity[];  // Last 50 entities mentioned
  
  // Conversation thread
  conversation_thread: Message[];
  
  // UI state
  current_route: string;
  previous_routes: string[];  // Navigation history
  intel_panel_context: IntelPanelContent;
  active_modality: 'text' | 'voice' | 'avatar';
  avatar_session_id: string | null;
  
  // Session timing
  started_at: string;  // ISO8601
  last_activity_at: string;
  day_date: string;  // YYYY-MM-DD, for "new day" detection
  
  // Flags
  is_first_session: boolean;
  briefing_delivered: boolean;
}

class SessionManager {
  private session: UnifiedSession;
  private syncInterval: NodeJS.Timer;
  
  // Load existing session or create new one
  async initialize(userId: string): Promise<UnifiedSession> {
    const existing = await supabase
      .from('user_sessions')
      .select('*')
      .eq('user_id', userId)
      .eq('is_active', true)
      .single();
    
    if (existing && existing.day_date === today()) {
      // Resume existing session
      this.session = existing.session_data;
      return this.session;
    }
    
    if (existing) {
      // New day — archive old session, start fresh
      await this.archiveSession(existing);
    }
    
    // Create new session
    this.session = this.createNewSession(userId);
    await this.persist();
    
    // Start periodic sync (every 30 seconds)
    this.syncInterval = setInterval(() => this.persist(), 30000);
    
    return this.session;
  }
  
  // Persist to Supabase (survives tab close)
  async persist(): Promise<void> {
    this.session.last_activity_at = new Date().toISOString();
    await supabase
      .from('user_sessions')
      .upsert({
        session_id: this.session.session_id,
        user_id: this.session.user_id,
        session_data: this.session,
        is_active: true,
        updated_at: this.session.last_activity_at,
      });
  }
  
  // Archive to episodic memory when session ends
  async archiveSession(session: any): Promise<void> {
    await supabase
      .from('user_sessions')
      .update({ is_active: false })
      .eq('session_id', session.session_id);
    
    // Trigger episodic memory storage
    await api.post('/memory/archive-session', {
      session_id: session.session_id,
      conversation_thread: session.session_data.conversation_thread,
    });
  }
  
  // Modality switch
  switchModality(newModality: 'text' | 'voice' | 'avatar'): void {
    this.session.active_modality = newModality;
    this.persist();
  }
  
  // Route change (from user or ARIA)
  updateRoute(route: string): void {
    this.session.previous_routes.push(this.session.current_route);
    this.session.current_route = route;
    // Trigger memory priming for new context
    memoryPrimingBridge.primeForRoute(route);
  }
  
  // Add message to thread
  addMessage(message: Message): void {
    this.session.conversation_thread.push(message);
    // Extract entities for recent_entities
    if (message.entities) {
      this.session.recent_entities = [
        ...message.entities,
        ...this.session.recent_entities
      ].slice(0, 50);
    }
  }
}
```

### 2.2 WebSocketManager

Persistent WebSocket connection that handles all real-time communication:

```typescript
// core/WebSocketManager.ts

type WSEventHandler = (payload: any) => void;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private handlers: Map<string, WSEventHandler[]> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private heartbeatInterval: NodeJS.Timer;
  
  async connect(userId: string, sessionId: string): Promise<void> {
    const url = `${WS_BASE_URL}/ws/${userId}?session=${sessionId}`;
    this.ws = new WebSocket(url);
    
    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.startHeartbeat();
      console.log('[WS] Connected');
    };
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.dispatch(data.type, data.payload);
    };
    
    this.ws.onclose = () => {
      this.stopHeartbeat();
      this.reconnect(userId, sessionId);
    };
  }
  
  // Register event handlers
  on(event: string, handler: WSEventHandler): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, []);
    }
    this.handlers.get(event)!.push(handler);
    
    // Return unsubscribe function
    return () => {
      const handlers = this.handlers.get(event);
      if (handlers) {
        this.handlers.set(event, handlers.filter(h => h !== handler));
      }
    };
  }
  
  // Send message to backend
  send(type: string, payload: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, payload }));
    }
  }
  
  private dispatch(type: string, payload: any): void {
    const handlers = this.handlers.get(type) || [];
    handlers.forEach(h => h(payload));
  }
  
  private async reconnect(userId: string, sessionId: string): Promise<void> {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) return;
    this.reconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    await new Promise(r => setTimeout(r, delay));
    this.connect(userId, sessionId);
  }
  
  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      this.send('heartbeat', { timestamp: Date.now() });
    }, 30000);
  }
  
  private stopHeartbeat(): void {
    clearInterval(this.heartbeatInterval);
  }
}

// WebSocket Event Types
const WS_EVENTS = {
  // Server → Client
  ARIA_MESSAGE: 'aria.message',           // Message + rich content + UI commands
  ARIA_THINKING: 'aria.thinking',         // Processing indicator
  ARIA_SPEAKING: 'aria.speaking',         // Avatar script + emotion
  ACTION_PENDING: 'action.pending',       // Action needs approval
  ACTION_COMPLETED: 'action.completed',   // Action finished
  PROGRESS_UPDATE: 'progress.update',     // Goal progress delta
  SIGNAL_DETECTED: 'signal.detected',     // New intelligence signal
  EMOTION_DETECTED: 'emotion.detected',   // Raven-0 emotion signal
  SESSION_SYNC: 'session.sync',           // Session state delta
  
  // Client → Server
  USER_MESSAGE: 'user.message',           // Text or voice transcript
  USER_NAVIGATE: 'user.navigate',         // Route change notification
  USER_APPROVE: 'user.approve',           // Approve action
  USER_REJECT: 'user.reject',             // Reject action
  MODALITY_CHANGE: 'modality.change',     // Switched chat/voice/avatar
} as const;
```

### 2.3 UICommandExecutor

The system that lets ARIA control the entire UI:

```typescript
// core/UICommandExecutor.ts

import { NavigateFunction } from 'react-router-dom';

interface NavigateCommand {
  action: 'navigate';
  route: string;
  params?: Record<string, any>;
  transition?: 'instant' | 'smooth';  // smooth = slide animation
}

interface HighlightCommand {
  action: 'highlight';
  element: string;         // CSS selector or data-aria-id
  duration_ms?: number;    // Default 3000ms
  style?: 'glow' | 'pulse' | 'outline';  // Default 'glow'
}

interface UpdateIntelPanelCommand {
  action: 'update_intel_panel';
  content: IntelPanelContent;
}

interface ScrollToCommand {
  action: 'scroll_to';
  element: string;
  behavior?: 'smooth' | 'instant';
}

interface SwitchModeCommand {
  action: 'switch_mode';
  mode: 'workspace' | 'dialogue' | 'compact_avatar';
}

interface ShowNotificationCommand {
  action: 'show_notification';
  type: 'signal' | 'alert' | 'success' | 'info';
  message: string;
  duration_ms?: number;
}

interface UpdateBadgeCommand {
  action: 'update_sidebar_badge';
  item: string;    // sidebar item key
  count: number;
}

interface OpenModalCommand {
  action: 'open_modal';
  modal: string;
  data?: any;
}

type UICommand = NavigateCommand | HighlightCommand | UpdateIntelPanelCommand |
  ScrollToCommand | SwitchModeCommand | ShowNotificationCommand |
  UpdateBadgeCommand | OpenModalCommand;

class UICommandExecutor {
  private navigate: NavigateFunction;
  private intelPanelController: IntelPanelController;
  private notificationService: NotificationService;
  private modeController: ModeController;
  
  constructor(deps: {
    navigate: NavigateFunction;
    intelPanelController: IntelPanelController;
    notificationService: NotificationService;
    modeController: ModeController;
  }) {
    Object.assign(this, deps);
  }
  
  async execute(commands: UICommand[]): Promise<void> {
    for (const cmd of commands) {
      await this.executeOne(cmd);
      // Visual sequencing delay
      if (commands.length > 1) await this.sleep(150);
    }
  }
  
  private async executeOne(cmd: UICommand): Promise<void> {
    switch (cmd.action) {
      case 'navigate':
        if (cmd.transition === 'smooth') {
          document.querySelector('#workspace')?.classList.add('slide-out');
          await this.sleep(200);
        }
        this.navigate(cmd.route, { state: cmd.params });
        // Session manager is notified via route listener
        break;
        
      case 'highlight':
        this.highlightElement(cmd.element, cmd.duration_ms || 3000, cmd.style || 'glow');
        break;
        
      case 'update_intel_panel':
        this.intelPanelController.update(cmd.content);
        break;
        
      case 'scroll_to':
        const el = document.querySelector(`[data-aria-id="${cmd.element}"]`) ||
                   document.querySelector(cmd.element);
        el?.scrollIntoView({ behavior: cmd.behavior || 'smooth' });
        break;
        
      case 'switch_mode':
        this.modeController.switchTo(cmd.mode);
        break;
        
      case 'show_notification':
        this.notificationService.show(cmd.type, cmd.message, cmd.duration_ms);
        break;
        
      case 'update_sidebar_badge':
        // Dispatched to sidebar store
        navigationStore.getState().setBadge(cmd.item, cmd.count);
        break;
        
      case 'open_modal':
        // Dispatched to modal store
        modalStore.getState().open(cmd.modal, cmd.data);
        break;
    }
  }
  
  private highlightElement(selector: string, duration: number, style: string): void {
    const el = document.querySelector(`[data-aria-id="${selector}"]`) ||
               document.querySelector(selector);
    if (!el) return;
    
    el.classList.add(`aria-highlight-${style}`);
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    
    setTimeout(() => {
      el.classList.remove(`aria-highlight-${style}`);
    }, duration);
  }
  
  private sleep(ms: number): Promise<void> {
    return new Promise(r => setTimeout(r, ms));
  }
}

// CSS for highlight effects (added to global styles)
/*
.aria-highlight-glow {
  box-shadow: 0 0 20px rgba(46, 102, 255, 0.4), 0 0 40px rgba(46, 102, 255, 0.2);
  transition: box-shadow 0.3s ease;
}

.aria-highlight-pulse {
  animation: aria-pulse 1s ease-in-out 3;
}

@keyframes aria-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.02); box-shadow: 0 0 15px rgba(46, 102, 255, 0.3); }
}

.aria-highlight-outline {
  outline: 2px solid #2E66FF;
  outline-offset: 4px;
  transition: outline 0.3s ease;
}
*/
```

### 2.4 ModalityController

Handles seamless transitions between chat, voice, and avatar:

```typescript
// core/ModalityController.ts

type Modality = 'text' | 'voice' | 'avatar';

interface ModalityState {
  current: Modality;
  voiceActive: boolean;
  avatarSessionId: string | null;
  webcamEnabled: boolean;
  ravenEnabled: boolean;
}

class ModalityController {
  private state: ModalityState;
  private tavusController: TavusController;
  private sessionManager: SessionManager;
  private speechRecognition: SpeechRecognition | null = null;
  
  async switchTo(modality: Modality): Promise<void> {
    const previous = this.state.current;
    
    // Cleanup previous modality
    if (previous === 'voice') {
      this.stopListening();
    }
    if (previous === 'avatar') {
      await this.tavusController.endSession();
    }
    
    // Initialize new modality
    switch (modality) {
      case 'text':
        // Nothing special needed
        break;
        
      case 'voice':
        await this.startListening();
        break;
        
      case 'avatar':
        await this.startAvatarSession();
        break;
    }
    
    this.state.current = modality;
    this.sessionManager.switchModality(modality);
    
    // Notify backend of modality change
    wsManager.send(WS_EVENTS.MODALITY_CHANGE, {
      from: previous,
      to: modality,
      timestamp: Date.now(),
    });
  }
  
  // Voice: Space-to-talk
  handleSpaceDown(): void {
    if (this.state.current === 'text') {
      this.switchTo('voice');
    }
    this.startListening();
  }
  
  handleSpaceUp(): void {
    this.stopListening();
    // Voice transcript is sent automatically via onresult
  }
  
  private async startListening(): Promise<void> {
    this.speechRecognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    this.speechRecognition.continuous = false;
    this.speechRecognition.interimResults = true;
    
    this.speechRecognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map(r => r[0].transcript)
        .join('');
      
      if (event.results[0].isFinal) {
        // Send final transcript as user message
        wsManager.send(WS_EVENTS.USER_MESSAGE, {
          content: transcript,
          modality: 'voice',
        });
      }
    };
    
    this.speechRecognition.start();
    this.state.voiceActive = true;
  }
  
  private stopListening(): void {
    this.speechRecognition?.stop();
    this.state.voiceActive = false;
  }
  
  private async startAvatarSession(): Promise<void> {
    const session = await this.tavusController.createSession({
      context: this.sessionManager.getSession(),
      webcamEnabled: this.state.webcamEnabled,
      ravenEnabled: this.state.ravenEnabled,
    });
    this.state.avatarSessionId = session.id;
  }
}
```

### 2.5 TavusController

Wraps the Tavus SDK for avatar management:

```typescript
// core/TavusController.ts

interface TavusSession {
  id: string;
  conversationUrl: string;
  status: 'connecting' | 'active' | 'ended';
}

class TavusController {
  private currentSession: TavusSession | null = null;
  private dailyFrame: any = null;  // Daily.co iframe
  
  async createSession(options: {
    context: UnifiedSession;
    webcamEnabled: boolean;
    ravenEnabled: boolean;
  }): Promise<TavusSession> {
    // Call backend to create Tavus conversation
    const response = await api.post('/video/sessions', {
      context: {
        user_name: options.context.user_id,
        active_topics: options.context.active_topics,
        recent_conversation: options.context.conversation_thread.slice(-10),
      },
      webcam_enabled: options.webcamEnabled,
      raven_enabled: options.ravenEnabled,
    });
    
    this.currentSession = {
      id: response.data.session_id,
      conversationUrl: response.data.conversation_url,
      status: 'connecting',
    };
    
    // Initialize Daily.co WebRTC
    this.dailyFrame = await DailyIframe.createFrame(
      document.getElementById('avatar-container'),
      {
        url: this.currentSession.conversationUrl,
        showLeaveButton: false,
        showFullscreenButton: false,
        iframeStyle: {
          width: '100%',
          height: '100%',
          border: 'none',
          borderRadius: '12px',
        },
      }
    );
    
    await this.dailyFrame.join();
    this.currentSession.status = 'active';
    
    // Listen for Raven-0 emotion events
    if (options.ravenEnabled) {
      this.setupRavenListeners();
    }
    
    return this.currentSession;
  }
  
  async endSession(): Promise<void> {
    if (this.currentSession) {
      await api.post(`/video/sessions/${this.currentSession.id}/end`);
      this.dailyFrame?.leave();
      this.dailyFrame?.destroy();
      this.currentSession = null;
    }
  }
  
  private setupRavenListeners(): void {
    // Raven-0 sends emotion events through the Tavus SDK
    this.dailyFrame.on('app-message', (event: any) => {
      if (event.data?.type === 'emotion') {
        wsManager.send('emotion.user', {
          emotion: event.data.emotion,      // confusion, interest, frustration, etc.
          confidence: event.data.confidence,
          timestamp: Date.now(),
        });
      }
      if (event.data?.type === 'engagement') {
        wsManager.send('engagement.update', {
          score: event.data.score,          // 0-100
          attention: event.data.attention,  // looking_at_screen, looking_away
          timestamp: Date.now(),
        });
      }
    });
  }
}
```

### 2.6 MemoryPrimingBridge

Triggers memory retrieval when context changes:

```typescript
// core/MemoryPrimingBridge.ts

class MemoryPrimingBridge {
  // Called when user or ARIA navigates to a new route
  async primeForRoute(route: string): Promise<MemoryContext> {
    const routeType = this.classifyRoute(route);
    
    switch (routeType) {
      case 'pipeline':
        return await api.post('/memory/prime', {
          context: 'pipeline_overview',
          recent_entities: sessionManager.getSession().recent_entities,
        });
        
      case 'lead_detail':
        const leadId = this.extractLeadId(route);
        return await api.post('/memory/prime', {
          context: 'lead_detail',
          lead_id: leadId,
          include: ['relationship_history', 'meeting_notes', 'stakeholder_insights'],
        });
        
      case 'battle_card':
        const competitor = this.extractCompetitor(route);
        return await api.post('/memory/prime', {
          context: 'competitive_intel',
          competitor,
          include: ['past_discussions', 'win_loss_history', 'feature_comparison'],
        });
        
      case 'communications':
        return await api.post('/memory/prime', {
          context: 'communications',
          include: ['draft_history', 'recipient_preferences', 'tone_patterns'],
        });
        
      default:
        return { memories: [] };
    }
  }
  
  // Called when ARIA detects an entity in conversation
  async primeForEntity(entity: Entity): Promise<MemoryContext> {
    return await api.post('/memory/prime', {
      context: 'entity_lookup',
      entity_type: entity.type,  // person, company, product, etc.
      entity_name: entity.name,
      include: ['all_memories', 'relationship_graph', 'recent_signals'],
    });
  }
  
  // Called at session start for general priming
  async primeForSession(userId: string): Promise<MemoryContext> {
    return await api.post('/memory/prime', {
      context: 'session_start',
      user_id: userId,
      include: [
        'unfinished_items',
        'pending_followups',
        'recent_signals',
        'active_goals',
        'today_meetings',
      ],
    });
  }
  
  private classifyRoute(route: string): string {
    if (route.includes('/pipeline')) return 'pipeline';
    if (route.includes('/leads/')) return 'lead_detail';
    if (route.includes('/intelligence/battle-cards/')) return 'battle_card';
    if (route.includes('/intelligence')) return 'intelligence';
    if (route.includes('/communications')) return 'communications';
    if (route.includes('/actions')) return 'actions';
    return 'general';
  }
}
```

---

## 3. Component Specifications

### 3.1 AppShell

The root layout component that implements the three-column architecture:

```typescript
// app/AppShell.tsx

function AppShell() {
  const { currentMode } = useARIA();
  const { currentRoute } = useSession();
  const showIntelPanel = !['/', '/briefing'].includes(currentRoute) 
    && currentMode !== 'dialogue';
  
  return (
    <div className="h-screen flex overflow-hidden">
      {/* Left: Sidebar — always visible */}
      <Sidebar />
      
      {/* Center: Workspace — changes based on route/mode */}
      <main className={cn(
        "flex-1 flex flex-col overflow-hidden",
        currentMode === 'dialogue' ? 'flex-row' : ''
      )}>
        <Outlet />  {/* React Router renders current route */}
      </main>
      
      {/* Right: Intel Panel — visible on content pages only */}
      {showIntelPanel && (
        <IntelPanel />
      )}
      
      {/* Compact Avatar — floating PiP when on content pages with voice */}
      {currentMode === 'compact_avatar' && (
        <CompactAvatar />
      )}
    </div>
  );
}
```

### 3.2 RichContentRenderer

The component that dispatches ARIA's rich content to the correct sub-component. Used both in conversation messages AND on content pages:

```typescript
// components/rich/RichContentRenderer.tsx

interface RichContent {
  type: 'goal_plan' | 'execution_plan' | 'approval_row' | 'insight' |
        'draft_preview' | 'battle_card' | 'meeting_brief' | 'lead_table' |
        'progress_tracker' | 'agent_status' | 'data_chart' | 'signal' |
        'forecast' | 'inventory_risk' | 'suggestion_chips';
  data: any;
  context: 'conversation' | 'standalone';  // Renders differently based on context
}

function RichContentRenderer({ content }: { content: RichContent }) {
  const components: Record<string, React.ComponentType<any>> = {
    goal_plan: GoalPlanCard,
    execution_plan: ExecutionPlanCard,
    approval_row: ApprovalRow,
    insight: InsightCard,
    draft_preview: DraftPreview,
    battle_card: BattleCard,
    meeting_brief: MeetingBriefCard,
    lead_table: LeadTable,
    progress_tracker: ProgressTracker,
    agent_status: AgentStatusCard,
    data_chart: DataChart,
    signal: SignalCard,
    forecast: ForecastCard,
    inventory_risk: InventoryRiskCard,
    suggestion_chips: SuggestionChips,
  };
  
  const Component = components[content.type];
  if (!Component) return null;
  
  return (
    <div className={cn(
      content.context === 'conversation' ? 'max-w-2xl' : 'w-full',
      'my-3'
    )}>
      <Component {...content.data} context={content.context} />
    </div>
  );
}
```

### 3.3 ConversationThread

The primary ARIA Workspace component:

```typescript
// components/conversation/ConversationThread.tsx

function ConversationThread() {
  const { messages, isStreaming } = useConversationStore();
  const scrollRef = useRef<HTMLDivElement>(null);
  const { executeUICommands } = useUICommands();
  
  // Auto-scroll to bottom on new messages
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [messages]);
  
  // Handle incoming ARIA messages with UI commands
  useWebSocket(WS_EVENTS.ARIA_MESSAGE, (payload) => {
    conversationStore.addMessage(payload.message);
    
    // Execute UI commands (navigate, highlight, etc.)
    if (payload.ui_commands?.length > 0) {
      executeUICommands(payload.ui_commands);
    }
  });
  
  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto px-8 py-6 space-y-6 scroll-smooth"
      style={{ background: 'var(--obsidian)' }}
    >
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      
      {isStreaming && (
        <div className="flex items-center gap-2 text-[var(--text-muted)]">
          <ARIAPulse size="sm" />
          <StreamingText />
        </div>
      )}
    </div>
  );
}
```

### 3.4 IntelPanel

The context-adaptive right panel:

```typescript
// components/shell/IntelPanel.tsx

function IntelPanel() {
  const { content, title } = useIntelPanel();
  const { currentRoute } = useSession();
  
  // Determine which modules to show based on route
  const modules = useMemo(() => {
    switch (getRouteType(currentRoute)) {
      case 'pipeline':
        return [
          <AlertsModule key="alerts" alerts={content.alerts} />,
          <BuyingSignalsModule key="signals" signals={content.buyingSignals} />,
          <UpcomingRenewalsModule key="renewals" renewals={content.renewals} />,
        ];
      case 'intelligence':
        return [
          <CompetitiveIntelModule key="intel" data={content.competitiveIntel} />,
          <NewsAlertsModule key="news" alerts={content.newsAlerts} />,
          <ChatInputModule key="chat" placeholder="Ask for competitive intel..." />,
        ];
      case 'communications':
        return [
          <WhyIWroteThisModule key="why" explanation={content.draftExplanation} />,
          <ToneVoiceModule key="tone" currentTone={content.tone} />,
          <AnalysisModule key="analysis" metrics={content.draftAnalysis} />,
          <NextBestActionModule key="nba" action={content.nextAction} />,
        ];
      case 'lead_detail':
        return [
          <StrategicAdviceModule key="advice" advice={content.strategicAdvice} />,
          <BuyingSignalsModule key="signals" signals={content.buyingSignals} />,
          <ObjectionsModule key="objections" objections={content.objections} />,
          <NextStepsModule key="steps" steps={content.suggestedSteps} />,
        ];
      case 'actions':
        return [
          <AgentStatusModule key="agents" agents={content.agentStatuses} />,
        ];
      default:
        return [];
    }
  }, [currentRoute, content]);
  
  return (
    <aside className="w-80 border-l border-[var(--border-color)] flex flex-col overflow-hidden">
      <div className="h-14 px-6 border-b border-[var(--border-color)] flex items-center justify-between shrink-0">
        <h2 className="font-heading text-lg font-semibold">{title}</h2>
        <button className="text-muted hover:text-primary">
          <span className="material-symbols-outlined text-sm">more_horiz</span>
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {modules}
      </div>
    </aside>
  );
}
```

---

## 4. Theme System

### 4.1 CSS Variables

```css
/* Dark theme (ARIA Workspace, Dialogue Mode, Sidebar) */
:root[data-theme="dark"] {
  --bg-primary: #0A0A0B;        /* Obsidian */
  --bg-elevated: #121214;        /* Elevated surfaces */
  --bg-surface: #1C1C1E;         /* Cards, inputs */
  --border-color: #262629;
  --text-primary: #EDEDEF;
  --text-secondary: #A1A1AA;
  --text-muted: #52525B;
  --accent-primary: #2E66FF;     /* Electric Blue */
  --accent-muted: rgba(46, 102, 255, 0.15);
  --accent-glow: rgba(46, 102, 255, 0.4);
}

/* Light theme (Content pages) */
:root[data-theme="light"] {
  --bg-primary: #F8FAFC;         /* Warm white */
  --bg-elevated: #FFFFFF;         /* Cards */
  --bg-surface: #F1F5F9;          /* Subtle backgrounds */
  --border-color: #E2E8F0;
  --text-primary: #1E293B;
  --text-secondary: #64748B;
  --text-muted: #94A3B8;
  --accent-primary: #2563EB;      /* Slightly warmer blue */
  --accent-muted: rgba(37, 99, 235, 0.08);
}
```

### 4.2 Theme Switching Logic

```typescript
// contexts/ThemeContext.tsx

function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { currentRoute } = useSession();
  
  const theme = useMemo(() => {
    // Always dark
    if (currentRoute === '/' || currentRoute === '/briefing') return 'dark';
    // Always light
    if (currentRoute.startsWith('/settings')) return 'light';
    // Content pages: light
    if (currentRoute.startsWith('/pipeline') ||
        currentRoute.startsWith('/intelligence') ||
        currentRoute.startsWith('/communications') ||
        currentRoute.startsWith('/actions')) return 'light';
    // Default
    return 'dark';
  }, [currentRoute]);
  
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);
  
  return <ThemeContext.Provider value={{ theme }}>{children}</ThemeContext.Provider>;
}
```

---

## 5. Route Definitions

```typescript
// app/routes.tsx

const routes = [
  {
    path: '/',
    element: <AppShell />,
    children: [
      // Layer 1: ARIA Workspace (default)
      { index: true, element: <ARIAWorkspace /> },
      
      // Layer 1a: Dialogue Mode / Briefing
      { path: 'briefing', element: <DialogueMode type="briefing" /> },
      { path: 'dialogue', element: <DialogueMode type="conversation" /> },
      
      // Layer 2: Content Pages
      { path: 'pipeline', element: <PipelinePage /> },
      { path: 'pipeline/leads/:leadId', element: <LeadDetailPage /> },
      { path: 'intelligence', element: <IntelligencePage /> },
      { path: 'intelligence/battle-cards/:competitorId', element: <BattleCardDetail /> },
      { path: 'communications', element: <CommunicationsPage /> },
      { path: 'communications/drafts/:draftId', element: <DraftDetailPage /> },
      { path: 'actions', element: <ActionsPage /> },
      { path: 'actions/goals/:goalId', element: <GoalDetailPage /> },
      
      // Layer 3: Configuration
      { path: 'settings', element: <SettingsPage /> },
      { path: 'settings/:section', element: <SettingsPage /> },
    ],
  },
];
```

---

## 6. Integration Points with Backend

### 6.1 API Endpoints Required

| Endpoint | Method | Purpose | Sprint |
|----------|--------|---------|--------|
| `/ws/{user_id}` | WebSocket | Persistent real-time connection | Sprint 1 |
| `/api/v1/chat/message` | POST | Send message, get ARIA response with UI commands | Sprint 0 |
| `/api/v1/sessions` | GET/POST | Session management | Sprint 1 |
| `/api/v1/sessions/{id}/archive` | POST | Archive session to episodic memory | Sprint 1 |
| `/api/v1/goals/propose` | POST | Get goal proposals from ARIA | Sprint 2 |
| `/api/v1/goals/{id}/plan` | POST | Get execution plan | Sprint 2 |
| `/api/v1/goals/{id}/execute` | POST | Start goal execution | Sprint 2 |
| `/api/v1/goals/{id}/progress` | GET | Goal progress | Sprint 2 |
| `/api/v1/agents/status` | GET | All agent statuses | Sprint 2 |
| `/api/v1/memory/prime` | POST | Context-aware memory retrieval | Sprint 1 |
| `/api/v1/memory/archive-session` | POST | Store session to episodic memory | Sprint 1 |
| `/api/v1/video/sessions` | POST | Create Tavus avatar session | Sprint 3 |
| `/api/v1/video/sessions/{id}` | GET | Session status + room URL | Sprint 3 |
| `/api/v1/video/sessions/{id}/end` | POST | End avatar session | Sprint 3 |
| `/api/v1/leads` | GET | Lead list with filters | Sprint 3 |
| `/api/v1/leads/{id}` | GET | Lead detail with timeline | Sprint 3 |
| `/api/v1/intelligence/battle-cards` | GET | Battle cards list | Sprint 3 |
| `/api/v1/intelligence/signals` | GET | Recent signals | Sprint 3 |
| `/api/v1/communications/drafts` | GET | Email draft list | Sprint 3 |
| `/api/v1/communications/drafts/{id}` | GET/PUT | Draft detail + edit | Sprint 3 |
| `/api/v1/briefing/today` | GET | Today's briefing content | Sprint 4 |

### 6.2 Backend Response Contract

Every response from the chat/message endpoint must follow this contract:

```typescript
interface ChatResponse {
  // Required
  message_id: string;
  content: string;               // ARIA's text response
  timestamp: string;
  
  // Rich content (optional)
  rich_content?: RichContent[];  // Inline cards, tables, etc.
  
  // UI commands (optional)
  ui_commands?: UICommand[];     // Navigate, highlight, etc.
  
  // Suggestions (optional)
  suggestions?: string[];        // 2-3 context-aware suggestion chips
  
  // Avatar (optional)
  avatar_script?: string;        // Text for TTS
  voice_emotion?: string;        // Emotion hint for avatar
  
  // Memory (optional, for debug/transparency)
  memories_used?: string[];      // Which memories informed this response
  
  // Agent activity (optional)
  agents_spawned?: AgentSpawn[]; // Agents triggered by this interaction
}
```

---

## 7. Performance Requirements

| Metric | Target | Strategy |
|--------|--------|----------|
| First Contentful Paint | <1.5s | Code splitting, lazy routes |
| WebSocket connection | <500ms | Pre-connect on page load |
| Message render (text) | <100ms | Virtual list, React.memo |
| Message render (rich) | <200ms | Lazy-loaded rich components |
| UI command execution | <200ms | No DOM queries in hot path |
| Route transition | <300ms | Prefetch on hover |
| Avatar lip sync latency | <500ms | Tavus handles on their end |
| Memory priming | <1s | Parallel retrieval, caching |
| Session persistence | <500ms | Debounced Supabase writes |

---

## 8. Accessibility

| Requirement | Implementation |
|------------|----------------|
| Keyboard navigation | Tab order through all interactive elements |
| Space-to-talk | Global keyboard shortcut for voice input |
| Screen reader support | ARIA (the a11y standard) labels on all components |
| Focus management | Auto-focus input bar after ARIA speaks |
| Reduced motion | Respect `prefers-reduced-motion` for animations |
| High contrast | Theme system supports high-contrast variant |
| Voice alternatives | Every action possible via text, voice, or click |

---

> **This document is the technical companion to IDD v3.0. Implementation must follow the patterns and contracts defined here.**
