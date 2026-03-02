# First Conversation & Morning Briefing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the two most critical "first impression" moments — ARIA's intelligence-demonstrating first conversation (with GoalPlanCards) and the morning briefing flow (with rich data cards delivered via Dialogue Mode).

**Architecture:** Enhance existing `FirstConversationGenerator` and `BriefingService` to produce `rich_content[]`, `ui_commands[]`, and `suggestions[]`, then deliver via WebSocket. Build 6 new frontend rich content components (`GoalPlanCard`, `ExecutionPlanCard`, `MeetingCard`, `SignalCard`, `AlertCard`, `RichContentRenderer`) and wire them into `MessageBubble`. Connect briefing delivery to `DialogueMode`.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind (frontend), WebSocket (real-time delivery), Zustand (state), React Query (mutations), Anthropic Claude API (LLM generation)

---

### Task 1: Enhance FirstConversationMessage model with rich_content fields

**Files:**
- Modify: `backend/src/onboarding/first_conversation.py:32-39`

**Step 1: Update the Pydantic model**

Add `rich_content`, `ui_commands`, and `suggestions` fields to `FirstConversationMessage`:

```python
class FirstConversationMessage(BaseModel):
    """The structured output of ARIA's first message to a user."""

    content: str
    memory_delta: dict[str, Any]
    suggested_next_action: str
    facts_referenced: int
    confidence_level: str  # "high", "moderate", "limited"
    rich_content: list[dict[str, Any]] = Field(default_factory=list)
    ui_commands: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
```

**Step 2: Verify the import**

Ensure `Field` is imported from pydantic (it's not currently imported in this file):

```python
from pydantic import BaseModel, Field
```

**Step 3: Run linting**

Run: `cd /Users/dhruv/aria && ruff check backend/src/onboarding/first_conversation.py`
Expected: No errors

**Step 4: Commit**

```bash
git add backend/src/onboarding/first_conversation.py
git commit -m "feat: add rich_content, ui_commands, suggestions to FirstConversationMessage"
```

---

### Task 2: Add goal proposal generation to FirstConversationGenerator

**Files:**
- Modify: `backend/src/onboarding/first_conversation.py`

**Step 1: Add the `_generate_goal_proposals` method**

Add this method to `FirstConversationGenerator` after `_compose_message` (after line ~280):

```python
async def _generate_goal_proposals(
    self,
    user_profile: dict[str, Any] | None,
    classification: dict[str, Any] | None,
    facts: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate 3-4 goal proposals as GoalPlanCard rich content.

    Uses LLM to propose specific, actionable goals based on what ARIA
    learned during onboarding. Each goal includes rationale, approach,
    agents, and timeline.

    Args:
        user_profile: User profile data.
        classification: Company classification data.
        facts: Top semantic facts.
        gaps: Critical knowledge gaps.

    Returns:
        List of GoalPlanCard rich content dicts.
    """
    role = (user_profile or {}).get("role", "sales")
    title = (user_profile or {}).get("title", "")
    company_type = (classification or {}).get("company_type", "life sciences")
    sub_vertical = (classification or {}).get("sub_vertical", "")

    facts_text = "\n".join(
        f"- {f.get('fact', '')}" for f in facts[:15]
    )
    gaps_text = "\n".join(
        f"- {g.get('task', '')}" for g in gaps[:5]
    )

    prompt = (
        "You are ARIA, an AI Department Director for a life sciences commercial team.\n\n"
        f"User role: {role} ({title})\n"
        f"Company type: {company_type} — {sub_vertical}\n"
        f"Key facts learned:\n{facts_text or 'Limited data available'}\n\n"
        f"Knowledge gaps:\n{gaps_text or 'None critical'}\n\n"
        "Propose exactly 3 strategic goals for this user. For each goal, provide:\n"
        "1. title: A specific, actionable goal title (not generic)\n"
        "2. rationale: Why this goal matters NOW for this specific user/company (2 sentences)\n"
        "3. approach: Which ARIA agents will work on this and what strategy they'll use (2 sentences)\n"
        "4. agents: List of agent names from [Hunter, Analyst, Strategist, Scribe, Operator, Scout]\n"
        "5. timeline: Estimated timeline (e.g., '2 weeks', '5 days')\n"
        "6. goal_type: One of [lead_gen, research, outreach, analysis, competitive_intel, territory]\n\n"
        "IMPORTANT: Goals must be SPECIFIC to this company and role. Not generic.\n"
        "Use company facts to make rationale concrete (reference numbers, competitors, products).\n\n"
        "Respond in valid JSON array format:\n"
        '[{"title": "...", "rationale": "...", "approach": "...", "agents": ["...", "..."], '
        '"timeline": "...", "goal_type": "..."}]'
    )

    try:
        response = await self._llm.generate_response(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.7,
        )

        import json as json_module
        # Extract JSON from response (handle markdown code blocks)
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        proposals = json_module.loads(text)

        rich_content: list[dict[str, Any]] = []
        for i, proposal in enumerate(proposals[:4]):
            rich_content.append({
                "type": "goal_plan",
                "data": {
                    "id": f"proposed-goal-{i + 1}",
                    "title": proposal.get("title", f"Goal {i + 1}"),
                    "rationale": proposal.get("rationale", ""),
                    "approach": proposal.get("approach", ""),
                    "agents": proposal.get("agents", []),
                    "timeline": proposal.get("timeline", "2 weeks"),
                    "goal_type": proposal.get("goal_type", "custom"),
                    "status": "proposed",
                },
            })

        return rich_content

    except Exception as e:
        logger.warning(f"Goal proposal generation failed: {e}")
        return []
```

**Step 2: Add `_build_ui_commands` method**

Add after `_generate_goal_proposals`:

```python
def _build_ui_commands(
    self,
    facts: list[dict[str, Any]],
    classification: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build ui_commands for sidebar badge updates.

    Args:
        facts: Top semantic facts.
        classification: Company classification data.

    Returns:
        List of UICommand dicts.
    """
    commands: list[dict[str, Any]] = []

    # Update Intelligence badge with fact/competitor count
    competitor_count = sum(
        1 for f in facts
        if "competitor" in f.get("fact", "").lower()
    )
    if competitor_count > 0:
        commands.append({
            "action": "update_sidebar_badge",
            "sidebar_item": "intelligence",
            "badge_count": competitor_count,
        })

    # Update Pipeline badge with facts compiled
    if len(facts) > 0:
        commands.append({
            "action": "update_sidebar_badge",
            "sidebar_item": "pipeline",
            "badge_count": len(facts),
        })

    return commands
```

**Step 3: Update `generate()` to call new methods and populate fields**

In the `generate()` method (around line 66-118), after the `_compose_message` call but before `_store_first_message`, add:

```python
        # 3. Generate goal proposals as rich content
        goal_proposals = await self._generate_goal_proposals(
            user_profile=user_profile,
            classification=classification,
            facts=facts,
            gaps=gaps,
        )

        # 4. Build UI commands (sidebar badges)
        ui_commands = self._build_ui_commands(facts, classification)

        # 5. Build suggestions
        suggestion_list = [
            "Tell me more about the first goal",
            "What competitors did you find?",
            "Start with the pipeline goal",
            "What gaps should I fill?",
        ]

        # Attach rich_content, ui_commands, suggestions to message
        message.rich_content = goal_proposals
        message.ui_commands = ui_commands
        message.suggestions = suggestion_list[:3]
```

Note: The current compose_message returns a `FirstConversationMessage` which now has these fields defaulting to empty lists. We're setting them after compose.

**Step 4: Run linting**

Run: `cd /Users/dhruv/aria && ruff check backend/src/onboarding/first_conversation.py`
Expected: No errors

**Step 5: Commit**

```bash
git add backend/src/onboarding/first_conversation.py
git commit -m "feat: add goal proposals and UI commands to first conversation"
```

---

### Task 3: Add WebSocket delivery to first conversation endpoint

**Files:**
- Modify: `backend/src/api/routes/onboarding.py:1181-1197`

**Step 1: Enhance the `/first-conversation` endpoint to also push via WebSocket**

Replace the existing endpoint (lines 1181-1197):

```python
@router.get("/first-conversation")
async def get_first_conversation(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Get or generate ARIA's first conversation message.

    Returns the intelligence-demonstrating first message that proves
    ARIA has done her homework. If not yet generated, triggers generation
    and delivers via WebSocket for real-time experience.

    Returns:
        FirstConversationMessage with content, memory delta, rich content, and metadata.
    """
    from src.onboarding.first_conversation import FirstConversationGenerator

    generator = FirstConversationGenerator()
    message = await generator.generate(current_user.id)

    # Also deliver via WebSocket for real-time conversation experience
    try:
        from src.core.ws import ws_manager
        from src.models.ws_events import AriaMessageEvent

        event = AriaMessageEvent(
            message=message.content,
            rich_content=message.rich_content,
            ui_commands=message.ui_commands,
            suggestions=message.suggestions,
        )
        await ws_manager.send_to_user(current_user.id, event.to_ws_dict())
        logger.info(
            "First conversation delivered via WebSocket",
            extra={"user_id": current_user.id},
        )
    except Exception as e:
        logger.warning(f"WebSocket delivery failed (REST fallback): {e}")

    return message.model_dump()
```

**Step 2: Run linting**

Run: `cd /Users/dhruv/aria && ruff check backend/src/api/routes/onboarding.py`
Expected: No errors

**Step 3: Commit**

```bash
git add backend/src/api/routes/onboarding.py
git commit -m "feat: deliver first conversation via WebSocket with rich content"
```

---

### Task 4: Enhance BriefingService with rich content and WebSocket delivery

**Files:**
- Modify: `backend/src/services/briefing.py`

**Step 1: Add rich content building method**

Add after `_generate_summary` (after line ~490):

```python
    def _build_rich_content(
        self,
        calendar: dict[str, Any],
        leads: dict[str, Any],
        signals: dict[str, Any],
        tasks: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build rich content cards from briefing data.

        Args:
            calendar: Calendar data dict.
            leads: Lead data dict.
            signals: Signal data dict.
            tasks: Task data dict.

        Returns:
            List of rich content dicts for frontend rendering.
        """
        rich_content: list[dict[str, Any]] = []

        # Meeting cards
        for meeting in calendar.get("key_meetings", []):
            rich_content.append({
                "type": "meeting_card",
                "data": {
                    "id": meeting.get("id", ""),
                    "title": meeting.get("title", "Meeting"),
                    "time": meeting.get("start_time", ""),
                    "attendees": meeting.get("attendees", []),
                    "company": meeting.get("company", ""),
                    "has_brief": True,
                },
            })

        # Signal cards (hot leads with buying signals)
        for lead in leads.get("hot_leads", [])[:3]:
            rich_content.append({
                "type": "signal_card",
                "data": {
                    "id": lead.get("id", ""),
                    "company_name": lead.get("company_name", ""),
                    "signal_type": "buying_signal",
                    "headline": f"{lead.get('company_name', 'Lead')} — Health Score {lead.get('health_score', 0)}",
                    "health_score": lead.get("health_score"),
                    "lifecycle_stage": lead.get("lifecycle_stage"),
                },
            })

        # Alert cards (competitive intel)
        for signal in signals.get("competitive_intel", [])[:3]:
            rich_content.append({
                "type": "alert_card",
                "data": {
                    "id": signal.get("id", ""),
                    "company_name": signal.get("company_name", ""),
                    "headline": signal.get("headline", ""),
                    "summary": signal.get("summary", ""),
                    "severity": "high" if (signal.get("relevance_score") or 0) > 80 else "medium",
                },
            })

        # Alert cards for overdue tasks
        for task in tasks.get("overdue", [])[:2]:
            rich_content.append({
                "type": "alert_card",
                "data": {
                    "id": task.get("id", ""),
                    "company_name": "",
                    "headline": f"Overdue: {task.get('task', '')}",
                    "summary": f"Priority: {task.get('priority', 'medium')}",
                    "severity": "high",
                },
            })

        return rich_content

    def _build_briefing_ui_commands(
        self,
        calendar: dict[str, Any],
        leads: dict[str, Any],
        signals: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build UI commands for briefing delivery.

        Args:
            calendar: Calendar data.
            leads: Lead data.
            signals: Signal data.

        Returns:
            List of UICommand dicts for sidebar badge updates.
        """
        commands: list[dict[str, Any]] = []

        meeting_count = calendar.get("meeting_count", 0)
        if meeting_count > 0:
            commands.append({
                "action": "update_sidebar_badge",
                "sidebar_item": "briefing",
                "badge_count": meeting_count,
            })

        attention_count = len(leads.get("needs_attention", []))
        if attention_count > 0:
            commands.append({
                "action": "update_sidebar_badge",
                "sidebar_item": "pipeline",
                "badge_count": attention_count,
            })

        signal_count = (
            len(signals.get("competitive_intel", []))
            + len(signals.get("company_news", []))
        )
        if signal_count > 0:
            commands.append({
                "action": "update_sidebar_badge",
                "sidebar_item": "intelligence",
                "badge_count": signal_count,
            })

        return commands
```

**Step 2: Update `generate_briefing` to include rich content**

In `generate_briefing` method, after `content` dict is built (after line ~97), add the rich content and UI commands:

```python
        # Build rich content cards and UI commands
        rich_content = self._build_rich_content(calendar_data, lead_data, signal_data, task_data)
        briefing_ui_commands = self._build_briefing_ui_commands(
            calendar_data, lead_data, signal_data
        )
        briefing_suggestions = [
            "Focus on the critical meeting",
            "Show me the buying signals",
            "Update me on competitor activity",
        ]

        content["rich_content"] = rich_content
        content["ui_commands"] = briefing_ui_commands
        content["suggestions"] = briefing_suggestions
```

**Step 3: Run linting**

Run: `cd /Users/dhruv/aria && ruff check backend/src/services/briefing.py`
Expected: No errors

**Step 4: Commit**

```bash
git add backend/src/services/briefing.py
git commit -m "feat: add rich content cards and UI commands to briefing service"
```

---

### Task 5: Add briefing deliver endpoint with WebSocket push

**Files:**
- Modify: `backend/src/api/routes/briefings.py`

**Step 1: Add the `/deliver` endpoint**

Add after the existing `/regenerate` endpoint (after line ~169):

```python
@router.post("/deliver")
async def deliver_briefing(
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Generate today's briefing and deliver via WebSocket.

    Generates the briefing and pushes it as an aria.message WebSocket
    event with rich_content (MeetingCards, SignalCards, AlertCards),
    ui_commands (sidebar badges), and suggestions.

    Use this endpoint for the Dialogue Mode briefing flow where
    the briefing streams into the conversation in real-time.

    Returns:
        Briefing content dict with delivery status.
    """
    service = BriefingService()
    content = await service.generate_briefing(current_user.id)

    # Deliver via WebSocket
    try:
        from src.core.ws import ws_manager
        from src.models.ws_events import AriaMessageEvent

        event = AriaMessageEvent(
            message=content.get("summary", ""),
            rich_content=content.get("rich_content", []),
            ui_commands=content.get("ui_commands", []),
            suggestions=content.get("suggestions", []),
        )
        await ws_manager.send_to_user(current_user.id, event.to_ws_dict())
        logger.info(
            "Briefing delivered via WebSocket",
            extra={"user_id": current_user.id},
        )
        return {"briefing": content, "status": "delivered"}

    except Exception as e:
        logger.warning(f"WebSocket briefing delivery failed: {e}")
        return {"briefing": content, "status": "generated_not_delivered"}
```

**Step 2: Run linting**

Run: `cd /Users/dhruv/aria && ruff check backend/src/api/routes/briefings.py`
Expected: No errors

**Step 3: Commit**

```bash
git add backend/src/api/routes/briefings.py
git commit -m "feat: add briefing deliver endpoint with WebSocket push"
```

---

### Task 6: Add goal approval endpoint with ExecutionPlan response

**Files:**
- Modify: `backend/src/api/routes/goals.py`

**Step 1: Add approval endpoint**

Add before the standard CRUD endpoints section (before line ~260 `# --- Standard Goal CRUD Endpoints ---`):

```python
class ApproveGoalProposalRequest(BaseModel):
    """Request body for approving a goal proposal from first conversation."""

    title: str
    description: str | None = None
    goal_type: str = "custom"
    rationale: str = ""
    approach: str = ""
    agents: list[str] = Field(default_factory=list)
    timeline: str = ""


@router.post("/approve-proposal")
async def approve_goal_proposal(
    data: ApproveGoalProposalRequest,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """Approve a goal proposal from ARIA's first conversation.

    Creates the goal from the proposal data and returns an ExecutionPlanCard
    rich content response via WebSocket showing the phased execution plan.

    Args:
        data: The proposal data from GoalPlanCard approval.
        current_user: Authenticated user.

    Returns:
        Created goal with execution plan rich content.
    """
    from src.models.goal import GoalType

    # Map string to GoalType enum
    try:
        goal_type = GoalType(data.goal_type)
    except ValueError:
        goal_type = GoalType.CUSTOM

    service = _get_service()
    goal_data = GoalCreate(
        title=data.title,
        description=data.description or data.rationale,
        goal_type=goal_type,
        config={
            "source": "first_conversation_proposal",
            "rationale": data.rationale,
            "approach": data.approach,
            "agents": data.agents,
            "timeline": data.timeline,
        },
    )
    result = await service.create_goal(current_user.id, goal_data)

    # Build ExecutionPlanCard rich content
    execution_plan = {
        "type": "execution_plan",
        "data": {
            "goal_id": result["id"],
            "title": data.title,
            "phases": [
                {
                    "name": "Discovery",
                    "timeline": "Days 1-3",
                    "agents": [a for a in data.agents if a in ("Hunter", "Scout", "Analyst")],
                    "output": "Research report, lead list, or competitive data",
                    "status": "pending",
                },
                {
                    "name": "Analysis",
                    "timeline": "Days 3-5",
                    "agents": [a for a in data.agents if a in ("Analyst", "Strategist")],
                    "output": "Strategic insights and recommendations",
                    "status": "pending",
                },
                {
                    "name": "Execution",
                    "timeline": f"Days 5-{data.timeline or '14'}",
                    "agents": [a for a in data.agents if a in ("Scribe", "Operator")],
                    "output": "Drafts, outreach, or operational tasks",
                    "status": "pending",
                },
            ],
            "autonomy": {
                "autonomous": "Research, data gathering, analysis, and report generation",
                "requires_approval": "Sending emails, making calendar changes, contacting leads",
            },
        },
    }

    # Deliver response via WebSocket
    try:
        from src.core.ws import ws_manager
        from src.models.ws_events import AriaMessageEvent

        confirmation = (
            f"Great — I've created the goal **{data.title}**. "
            f"Here's my execution plan. I'll start with discovery and "
            f"keep you updated on progress."
        )

        event = AriaMessageEvent(
            message=confirmation,
            rich_content=[execution_plan],
            ui_commands=[{
                "action": "update_sidebar_badge",
                "sidebar_item": "actions",
                "badge_count": 1,
            }],
            suggestions=[
                "Approve the plan",
                "Adjust the timeline",
                "Add more detail to phase 1",
            ],
        )
        await ws_manager.send_to_user(current_user.id, event.to_ws_dict())
    except Exception as e:
        logger.warning(f"WebSocket delivery failed for goal approval: {e}")

    logger.info(
        "Goal proposal approved",
        extra={"user_id": current_user.id, "goal_id": result["id"]},
    )

    return {**result, "execution_plan": execution_plan}
```

**Step 2: Run linting**

Run: `cd /Users/dhruv/aria && ruff check backend/src/api/routes/goals.py`
Expected: No errors

**Step 3: Commit**

```bash
git add backend/src/api/routes/goals.py
git commit -m "feat: add goal proposal approval endpoint with ExecutionPlanCard"
```

---

### Task 7: Build GoalPlanCard frontend component

**Files:**
- Create: `frontend/src/components/rich/GoalPlanCard.tsx`

**Step 1: Create the component**

```tsx
import { useCallback, useState } from 'react';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import { useConversationStore } from '@/stores/conversationStore';
import { apiClient } from '@/api/client';

interface GoalPlanData {
  id: string;
  title: string;
  rationale: string;
  approach: string;
  agents: string[];
  timeline: string;
  goal_type: string;
  status: 'proposed' | 'approved' | 'rejected';
}

interface GoalPlanCardProps {
  data: GoalPlanData;
}

const AGENT_COLORS: Record<string, string> = {
  Hunter: '#2E66FF',
  Analyst: '#8B5CF6',
  Strategist: '#F59E0B',
  Scribe: '#10B981',
  Operator: '#EF4444',
  Scout: '#06B6D4',
};

export function GoalPlanCard({ data }: GoalPlanCardProps) {
  const [status, setStatus] = useState(data.status);
  const [isLoading, setIsLoading] = useState(false);
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);

  const handleApprove = useCallback(async () => {
    setIsLoading(true);
    try {
      await apiClient.post('/goals/approve-proposal', {
        title: data.title,
        description: data.rationale,
        goal_type: data.goal_type,
        rationale: data.rationale,
        approach: data.approach,
        agents: data.agents,
        timeline: data.timeline,
      });
      setStatus('approved');
    } catch {
      // Error handled by WebSocket response
    } finally {
      setIsLoading(false);
    }
  }, [data]);

  const handleDiscuss = useCallback(() => {
    const message = `Tell me more about "${data.title}"`;
    addMessage({
      role: 'user',
      content: message,
      rich_content: [],
      ui_commands: [],
      suggestions: [],
    });
    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message,
      conversation_id: activeConversationId,
    });
  }, [data.title, addMessage, activeConversationId]);

  const handleModify = useCallback(() => {
    const message = `I'd like to adjust the goal "${data.title}"`;
    addMessage({
      role: 'user',
      content: message,
      rich_content: [],
      ui_commands: [],
      suggestions: [],
    });
    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message,
      conversation_id: activeConversationId,
    });
  }, [data.title, addMessage, activeConversationId]);

  const isApproved = status === 'approved';

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`goal-plan-${data.id}`}
    >
      {/* Header */}
      <div className="px-4 pt-4 pb-2">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display italic text-base text-[var(--text-primary)] leading-snug">
            {data.title}
          </h3>
          {isApproved && (
            <span className="shrink-0 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider bg-emerald-500/20 text-emerald-400">
              Approved
            </span>
          )}
        </div>
      </div>

      {/* Rationale */}
      <div className="px-4 pb-2">
        <p className="text-sm leading-relaxed text-[var(--text-secondary)]">
          {data.rationale}
        </p>
      </div>

      {/* Approach */}
      <div className="px-4 pb-2">
        <p className="text-xs font-mono uppercase tracking-wider text-[var(--text-secondary)] mb-1 opacity-60">
          Approach
        </p>
        <p className="text-sm text-[var(--text-primary)] leading-relaxed">
          {data.approach}
        </p>
      </div>

      {/* Agents + Timeline */}
      <div className="px-4 pb-3 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {data.agents.map((agent) => (
            <span
              key={agent}
              className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider"
              style={{
                backgroundColor: `${AGENT_COLORS[agent] || '#6B7280'}20`,
                color: AGENT_COLORS[agent] || '#6B7280',
              }}
            >
              {agent}
            </span>
          ))}
        </div>
        <span className="text-xs font-mono text-[var(--text-secondary)]">
          {data.timeline}
        </span>
      </div>

      {/* Actions */}
      {!isApproved && (
        <div className="border-t border-[var(--border)] px-4 py-3 flex items-center gap-2">
          <button
            onClick={handleApprove}
            disabled={isLoading}
            className="px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {isLoading ? 'Approving...' : 'Approve'}
          </button>
          <button
            onClick={handleModify}
            className="px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            Modify
          </button>
          <button
            onClick={handleDiscuss}
            className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
          >
            Discuss
          </button>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to GoalPlanCard

**Step 3: Commit**

```bash
git add frontend/src/components/rich/GoalPlanCard.tsx
git commit -m "feat: add GoalPlanCard component for first conversation goal proposals"
```

---

### Task 8: Build ExecutionPlanCard frontend component

**Files:**
- Create: `frontend/src/components/rich/ExecutionPlanCard.tsx`

**Step 1: Create the component**

```tsx
import { useCallback, useState } from 'react';
import { apiClient } from '@/api/client';

interface Phase {
  name: string;
  timeline: string;
  agents: string[];
  output: string;
  status: 'pending' | 'active' | 'complete';
}

interface ExecutionPlanData {
  goal_id: string;
  title: string;
  phases: Phase[];
  autonomy: {
    autonomous: string;
    requires_approval: string;
  };
}

interface ExecutionPlanCardProps {
  data: ExecutionPlanData;
}

const AGENT_COLORS: Record<string, string> = {
  Hunter: '#2E66FF',
  Analyst: '#8B5CF6',
  Strategist: '#F59E0B',
  Scribe: '#10B981',
  Operator: '#EF4444',
  Scout: '#06B6D4',
};

const PHASE_ICONS: Record<string, string> = {
  pending: '\u25CB',   // ○
  active: '\u25CF',    // ●
  complete: '\u2713',  // ✓
};

export function ExecutionPlanCard({ data }: ExecutionPlanCardProps) {
  const [isApproved, setIsApproved] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleApprove = useCallback(async () => {
    setIsLoading(true);
    try {
      await apiClient.post(`/goals/${data.goal_id}/start`);
      setIsApproved(true);
    } catch {
      // Error surfaced in conversation
    } finally {
      setIsLoading(false);
    }
  }, [data.goal_id]);

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`execution-plan-${data.goal_id}`}
    >
      {/* Header */}
      <div className="px-4 pt-4 pb-2 flex items-start justify-between">
        <div>
          <p className="text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] mb-1">
            Execution Plan
          </p>
          <h3 className="font-display italic text-base text-[var(--text-primary)]">
            {data.title}
          </h3>
        </div>
        {isApproved && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono uppercase tracking-wider bg-emerald-500/20 text-emerald-400">
            Active
          </span>
        )}
      </div>

      {/* Phase Timeline */}
      <div className="px-4 pb-3">
        <div className="space-y-0">
          {data.phases.map((phase, i) => (
            <div key={phase.name} className="flex gap-3">
              {/* Timeline connector */}
              <div className="flex flex-col items-center w-5 shrink-0">
                <span
                  className="text-sm leading-none mt-1"
                  style={{
                    color: phase.status === 'complete' ? '#10B981'
                      : phase.status === 'active' ? 'var(--accent)'
                      : 'var(--text-secondary)',
                  }}
                >
                  {PHASE_ICONS[phase.status]}
                </span>
                {i < data.phases.length - 1 && (
                  <div className="w-px flex-1 min-h-[24px] bg-[var(--border)]" />
                )}
              </div>

              {/* Phase content */}
              <div className="pb-4 flex-1 min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <p className="text-sm font-medium text-[var(--text-primary)]">
                    {phase.name}
                  </p>
                  <span className="text-[10px] font-mono text-[var(--text-secondary)] shrink-0">
                    {phase.timeline}
                  </span>
                </div>
                <p className="text-xs text-[var(--text-secondary)] mt-0.5 leading-relaxed">
                  {phase.output}
                </p>
                {phase.agents.length > 0 && (
                  <div className="flex gap-1 mt-1.5">
                    {phase.agents.map((agent) => (
                      <span
                        key={agent}
                        className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider"
                        style={{
                          backgroundColor: `${AGENT_COLORS[agent] || '#6B7280'}15`,
                          color: AGENT_COLORS[agent] || '#6B7280',
                        }}
                      >
                        {agent}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Autonomy indicator */}
      <div className="border-t border-[var(--border)] px-4 py-3 space-y-1.5">
        <div className="flex items-start gap-2">
          <span className="text-emerald-400 text-xs mt-0.5 shrink-0">AUTO</span>
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
            {data.autonomy.autonomous}
          </p>
        </div>
        <div className="flex items-start gap-2">
          <span className="text-amber-400 text-xs mt-0.5 shrink-0">APPROVAL</span>
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
            {data.autonomy.requires_approval}
          </p>
        </div>
      </div>

      {/* Actions */}
      {!isApproved && (
        <div className="border-t border-[var(--border)] px-4 py-3 flex items-center gap-2">
          <button
            onClick={handleApprove}
            disabled={isLoading}
            className="px-3 py-1.5 rounded-md text-xs font-medium text-white transition-colors disabled:opacity-50"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            {isLoading ? 'Starting...' : 'Approve Plan'}
          </button>
          <button className="px-3 py-1.5 rounded-md text-xs font-medium border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
            Modify
          </button>
          <button className="px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors">
            Discuss Further
          </button>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to ExecutionPlanCard

**Step 3: Commit**

```bash
git add frontend/src/components/rich/ExecutionPlanCard.tsx
git commit -m "feat: add ExecutionPlanCard component with phased timeline and autonomy indicator"
```

---

### Task 9: Build briefing-specific cards (MeetingCard, SignalCard, AlertCard)

**Files:**
- Create: `frontend/src/components/rich/MeetingCard.tsx`
- Create: `frontend/src/components/rich/SignalCard.tsx`
- Create: `frontend/src/components/rich/AlertCard.tsx`

**Step 1: Create MeetingCard**

```tsx
interface MeetingCardData {
  id: string;
  title: string;
  time: string;
  attendees: string[];
  company: string;
  has_brief: boolean;
}

interface MeetingCardProps {
  data: MeetingCardData;
}

export function MeetingCard({ data }: MeetingCardProps) {
  const formattedTime = data.time
    ? new Date(data.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '';

  return (
    <div
      className="rounded-lg border border-[var(--border)] px-4 py-3 flex items-center gap-3"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`meeting-card-${data.id}`}
    >
      <div className="w-10 h-10 rounded-lg bg-[var(--accent)]/10 flex items-center justify-center shrink-0">
        <span className="text-[var(--accent)] text-sm font-mono">{formattedTime || '--:--'}</span>
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[var(--text-primary)] truncate">
          {data.company || data.title}
        </p>
        <p className="text-xs text-[var(--text-secondary)]">
          {data.attendees.length > 0
            ? `${data.attendees.length} attendee${data.attendees.length > 1 ? 's' : ''}`
            : data.title}
        </p>
      </div>
      {data.has_brief && (
        <button className="shrink-0 px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] border border-[var(--accent)]/30 hover:bg-[var(--accent)]/10 transition-colors">
          View Brief
        </button>
      )}
    </div>
  );
}
```

**Step 2: Create SignalCard**

```tsx
interface SignalCardData {
  id: string;
  company_name: string;
  signal_type: string;
  headline: string;
  health_score?: number;
  lifecycle_stage?: string;
}

interface SignalCardProps {
  data: SignalCardData;
}

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  buying_signal: 'BUYING SIGNAL',
  engagement: 'ENGAGEMENT',
  champion_activity: 'CHAMPION',
};

export function SignalCard({ data }: SignalCardProps) {
  return (
    <div
      className="rounded-lg border border-[var(--border)] px-4 py-3"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`signal-card-${data.id}`}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider bg-emerald-500/15 text-emerald-400">
          {SIGNAL_TYPE_LABELS[data.signal_type] || data.signal_type.toUpperCase()}
        </span>
        {data.health_score != null && (
          <span className="text-xs font-mono text-emerald-400">
            +{data.health_score}pts
          </span>
        )}
      </div>
      <p className="text-sm text-[var(--text-primary)] leading-relaxed">
        {data.headline}
      </p>
      <div className="mt-2">
        <button className="px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] border border-[var(--accent)]/30 hover:bg-[var(--accent)]/10 transition-colors">
          Draft Outreach
        </button>
      </div>
    </div>
  );
}
```

**Step 3: Create AlertCard**

```tsx
interface AlertCardData {
  id: string;
  company_name: string;
  headline: string;
  summary: string;
  severity: 'high' | 'medium' | 'low';
}

interface AlertCardProps {
  data: AlertCardData;
}

const SEVERITY_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  high: { bg: 'bg-red-500/15', text: 'text-red-400', label: 'HIGH' },
  medium: { bg: 'bg-amber-500/15', text: 'text-amber-400', label: 'MEDIUM' },
  low: { bg: 'bg-blue-500/15', text: 'text-blue-400', label: 'LOW' },
};

export function AlertCard({ data }: AlertCardProps) {
  const severity = SEVERITY_STYLES[data.severity] || SEVERITY_STYLES.medium;

  return (
    <div
      className="rounded-lg border border-[var(--border)] px-4 py-3"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`alert-card-${data.id}`}
    >
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono uppercase tracking-wider ${severity.bg} ${severity.text}`}>
          {severity.label}
        </span>
        {data.company_name && (
          <span className="text-xs font-mono text-[var(--text-secondary)]">
            {data.company_name}
          </span>
        )}
      </div>
      <p className="text-sm text-[var(--text-primary)] leading-relaxed">
        {data.headline}
      </p>
      {data.summary && (
        <p className="text-xs text-[var(--text-secondary)] mt-1 leading-relaxed">
          {data.summary}
        </p>
      )}
      <div className="mt-2">
        <button className="px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] border border-[var(--accent)]/30 hover:bg-[var(--accent)]/10 transition-colors">
          View Details
        </button>
      </div>
    </div>
  );
}
```

**Step 4: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors related to new card components

**Step 5: Commit**

```bash
git add frontend/src/components/rich/MeetingCard.tsx frontend/src/components/rich/SignalCard.tsx frontend/src/components/rich/AlertCard.tsx
git commit -m "feat: add MeetingCard, SignalCard, AlertCard components for briefing"
```

---

### Task 10: Build RichContentRenderer and wire into MessageBubble

**Files:**
- Create: `frontend/src/components/rich/RichContentRenderer.tsx`
- Modify: `frontend/src/components/conversation/MessageBubble.tsx:85-99`

**Step 1: Create RichContentRenderer**

```tsx
import type { RichContent } from '@/api/chat';
import { GoalPlanCard } from './GoalPlanCard';
import { ExecutionPlanCard } from './ExecutionPlanCard';
import { MeetingCard } from './MeetingCard';
import { SignalCard } from './SignalCard';
import { AlertCard } from './AlertCard';

interface RichContentRendererProps {
  items: RichContent[];
}

export function RichContentRenderer({ items }: RichContentRendererProps) {
  if (items.length === 0) return null;

  return (
    <div className="mt-3 space-y-2">
      {items.map((item, i) => (
        <RichContentItem key={`${item.type}-${i}`} item={item} />
      ))}
    </div>
  );
}

function RichContentItem({ item }: { item: RichContent }) {
  switch (item.type) {
    case 'goal_plan':
      return <GoalPlanCard data={item.data as never} />;
    case 'execution_plan':
      return <ExecutionPlanCard data={item.data as never} />;
    case 'meeting_card':
      return <MeetingCard data={item.data as never} />;
    case 'signal_card':
      return <SignalCard data={item.data as never} />;
    case 'alert_card':
      return <AlertCard data={item.data as never} />;
    default:
      return (
        <div
          className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2 text-xs text-[var(--text-secondary)]"
          data-aria-id={`rich-content-${item.type}`}
        >
          <span className="font-mono uppercase tracking-wider text-[var(--accent)]">
            {item.type}
          </span>
        </div>
      );
  }
}
```

**Step 2: Update MessageBubble to use RichContentRenderer**

Replace lines 85-99 in `MessageBubble.tsx` (the generic rich_content rendering block) with:

```tsx
          {message.rich_content.length > 0 && (
            <RichContentRenderer items={message.rich_content} />
          )}
```

And add the import at the top of the file:

```tsx
import { RichContentRenderer } from '@/components/rich/RichContentRenderer';
```

**Step 3: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 4: Run lint**

Run: `cd /Users/dhruv/aria/frontend && npm run lint 2>&1 | head -30`
Expected: No errors

**Step 5: Commit**

```bash
git add frontend/src/components/rich/RichContentRenderer.tsx frontend/src/components/conversation/MessageBubble.tsx
git commit -m "feat: wire RichContentRenderer into MessageBubble for goal plans and briefing cards"
```

---

### Task 11: Wire briefing delivery into DialogueMode

**Files:**
- Modify: `frontend/src/components/avatar/DialogueMode.tsx`

**Step 1: Add briefing trigger on mount**

Add a `useEffect` that triggers briefing delivery when `sessionType="briefing"`. Add after the WebSocket connection effect (after line ~43):

```tsx
  // Trigger briefing delivery when entering briefing mode
  useEffect(() => {
    if (sessionType !== 'briefing') return;

    const deliverBriefing = async () => {
      try {
        const token = localStorage.getItem('access_token');
        const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        await fetch(`${baseUrl}/api/v1/briefings/deliver`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
        });
      } catch (err) {
        // Briefing delivery failure handled by WebSocket fallback
        console.warn('Briefing delivery request failed:', err);
      }
    };

    deliverBriefing();
  }, [sessionType]);
```

**Step 2: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/avatar/DialogueMode.tsx
git commit -m "feat: trigger briefing delivery on DialogueMode mount"
```

---

### Task 12: Add frontend API function for goal proposal approval

**Files:**
- Modify: `frontend/src/api/goals.ts`

**Step 1: Add the approval API function and type**

Add after the existing types section (after line ~116):

```typescript
export interface GoalProposalApproval {
  title: string;
  description?: string;
  goal_type: string;
  rationale: string;
  approach: string;
  agents: string[];
  timeline: string;
}
```

Add after the existing API functions (after line ~223):

```typescript
export async function approveGoalProposal(data: GoalProposalApproval): Promise<Goal> {
  const response = await apiClient.post<Goal>("/goals/approve-proposal", data);
  return response.data;
}
```

**Step 2: Add the hook**

In `frontend/src/hooks/useGoals.ts`, add:

```typescript
export function useApproveGoalProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: GoalProposalApproval) => approveGoalProposal(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: goalKeys.lists() });
      queryClient.invalidateQueries({ queryKey: goalKeys.dashboard() });
    },
  });
}
```

And update the import at the top to include:

```typescript
import {
  // ... existing imports ...
  approveGoalProposal,
  type GoalProposalApproval,
} from "@/api/goals";
```

**Step 3: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty 2>&1 | head -30`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/api/goals.ts frontend/src/hooks/useGoals.ts
git commit -m "feat: add goal proposal approval API client and hook"
```

---

### Task 13: Export new rich components from barrel

**Files:**
- Create: `frontend/src/components/rich/index.ts`

**Step 1: Create barrel export**

```typescript
export { GoalPlanCard } from './GoalPlanCard';
export { ExecutionPlanCard } from './ExecutionPlanCard';
export { MeetingCard } from './MeetingCard';
export { SignalCard } from './SignalCard';
export { AlertCard } from './AlertCard';
export { RichContentRenderer } from './RichContentRenderer';
```

**Step 2: Commit**

```bash
git add frontend/src/components/rich/index.ts
git commit -m "feat: add barrel exports for rich content components"
```

---

### Task 14: Final integration verification

**Step 1: Run full backend lint**

Run: `cd /Users/dhruv/aria && ruff check backend/src/onboarding/first_conversation.py backend/src/services/briefing.py backend/src/api/routes/briefings.py backend/src/api/routes/goals.py`
Expected: No errors

**Step 2: Run frontend typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit --pretty`
Expected: No errors

**Step 3: Run frontend lint**

Run: `cd /Users/dhruv/aria/frontend && npm run lint`
Expected: No errors

**Step 4: Verify build**

Run: `cd /Users/dhruv/aria/frontend && npm run build`
Expected: Build succeeds

**Step 5: Final commit if any fixes needed**

If any lint/type issues discovered, fix and commit:

```bash
git add -A
git commit -m "fix: resolve lint and type issues in first conversation and briefing implementation"
```
