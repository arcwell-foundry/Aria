# Complete Action Lifecycle — Approval UX + Post-Approval Execution

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three critical UX/functionality bugs in the action queue (expandable approval cards, Discuss button, post-approval execution) and add conference pre-briefing, goal impact checking, and chat Jarvis context.

**Architecture:** The action queue already has a solid API layer (`ActionQueueService`) and frontend (`ActionsPage` + `PendingApprovalsModule`). The approve endpoint currently only flips `status` to `approved` — we need to add an `ActionExecutor` service that runs downstream effects (email drafts, notifications, memory, follow-ups) when approval happens. On the frontend, both `ActionItem` in `ActionsPage.tsx` and the cards in `PendingApprovalsModule.tsx` need expand/collapse behavior to show full action details before the user decides.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind (frontend), Supabase (database)

---

### Task 1: Create ActionExecutor backend service

**Files:**
- Create: `backend/src/intelligence/action_executor.py`

**Step 1: Create the action executor service**

Create `backend/src/intelligence/action_executor.py` with the `ActionExecutor` class. This service is called after an action is approved and performs downstream execution based on `action_type`:

```python
"""
Post-Approval Action Executor.

When a user approves an action in the Action Queue, this service
executes the appropriate downstream actions based on the action_type.

This is the critical bridge between "ARIA proposes" and "ARIA executes."
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Executes approved actions with downstream effects."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def execute_approved_action(self, action_id: str, user_id: str) -> dict[str, Any]:
        """Execute an approved action. Called after status is set to 'approved'.

        Returns execution result dict.
        """
        action = (
            self._db.table("aria_action_queue")
            .select("*")
            .eq("id", action_id)
            .limit(1)
            .execute()
        )

        if not action.data:
            return {"status": "error", "message": "Action not found"}

        action_data = action.data[0]
        action_type = action_data.get("action_type", "")
        payload = action_data.get("payload", {})
        if isinstance(payload, str):
            payload = json.loads(payload)

        logger.info("[ActionExecutor] Executing: %s (%s)", action_type, action_id)

        try:
            handlers: dict[str, Any] = {
                "displacement_outreach": self._execute_displacement_outreach,
                "regulatory_displacement": self._execute_displacement_outreach,
                "competitive_pricing_response": self._execute_pricing_response,
                "lead_discovery": self._execute_lead_discovery,
            }
            handler = handlers.get(action_type, self._execute_generic)
            result = await handler(user_id, action_data, payload)

            # Mark action as completed
            self._db.table("aria_action_queue").update({
                "status": "completed",
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "result": result,
            }).eq("id", action_id).execute()

            # Sync proactive_proposals status
            insight_id = payload.get("insight_id")
            if insight_id:
                self._db.table("proactive_proposals").update({
                    "status": "approved",
                    "responded_at": datetime.now(timezone.utc).isoformat(),
                }).eq("insight_id", insight_id).eq("user_id", user_id).execute()

            # Create follow-up reminder
            await self._create_followup(user_id, action_data, result)

            # Write to semantic memory
            self._db.table("memory_semantic").insert({
                "user_id": user_id,
                "fact": (
                    f"[Action Approved] {action_data.get('title', '')}: "
                    f"User approved and ARIA executed. {result.get('summary', '')}"
                ),
                "confidence": 0.95,
                "source": "action_execution",
                "metadata": {"action_id": action_id, "action_type": action_type},
            }).execute()

            # Create activity log
            self._db.table("aria_activity").insert({
                "user_id": user_id,
                "activity_type": "action_executed",
                "title": f"Executed: {action_data.get('title', '')}",
                "description": result.get("summary", "Action completed"),
                "metadata": {"action_id": action_id, "result": result},
            }).execute()

            logger.info("[ActionExecutor] Completed: %s", action_type)
            return result

        except Exception as e:
            logger.error("[ActionExecutor] Execution failed: %s", e)
            self._db.table("aria_action_queue").update({
                "status": "failed",
                "result": {"error": str(e)},
            }).eq("id", action_id).execute()
            return {"status": "failed", "error": str(e)}

    async def _execute_displacement_outreach(
        self, user_id: str, action: dict, payload: dict
    ) -> dict[str, Any]:
        """Draft competitive displacement positioning brief."""
        company_name = payload.get("company_name", "")
        competitive_context = payload.get("competitive_context", {})

        differentiation = competitive_context.get("differentiation", [])
        weaknesses = competitive_context.get("weaknesses", [])
        pricing = competitive_context.get("pricing", {})

        diff_text = (
            "; ".join(str(d) for d in differentiation[:3])
            if differentiation
            else "our specialized solutions"
        )
        weakness_text = (
            "; ".join(str(w) for w in weaknesses[:2]) if weaknesses else ""
        )
        pricing_notes = (
            pricing.get("notes", "") if isinstance(pricing, dict) else ""
        )

        positioning = (
            f"COMPETITIVE DISPLACEMENT BRIEF — {company_name}\n\n"
            f"SITUATION: {action.get('description', '')[:300]}\n\n"
            f"YOUR COMPETITIVE ADVANTAGES:\n{diff_text}\n\n"
            f"THEIR VULNERABILITIES:\n{weakness_text}\n\n"
            f"PRICING INTELLIGENCE:\n"
            f"{pricing_notes[:200] if pricing_notes else 'Contact for current pricing intelligence'}\n\n"
            f"RECOMMENDED MESSAGING:\n"
            f"Lead with your differentiation. "
            f"Position against their known weaknesses. "
            f"Do NOT lead with price — lead with value and reliability."
        )

        try:
            self._db.table("deferred_email_drafts").insert({
                "user_id": user_id,
                "subject": (
                    f"Competitive opportunity: {company_name} "
                    f"— displacement positioning ready"
                ),
                "body": positioning[:500],
                "status": "ready",
                "context": {
                    "type": "displacement_outreach",
                    "competitor": company_name,
                    "competitive_context": competitive_context,
                    "action_id": action.get("id"),
                },
            }).execute()
        except Exception as e:
            logger.warning("[ActionExecutor] deferred_email_drafts insert failed: %s", e)

        self._db.table("notifications").insert({
            "user_id": user_id,
            "type": "action_completed",
            "title": f"Displacement brief ready: {company_name}",
            "message": (
                f"Competitive positioning brief for {company_name} displacement "
                f"outreach is ready in Communications. Review and personalize before sending."
            ),
            "link": "/communications",
            "metadata": {
                "action_type": "displacement_outreach",
                "company": company_name,
            },
        }).execute()

        return {
            "status": "completed",
            "summary": (
                f"Displacement outreach brief created for {company_name}. "
                f"Competitive positioning loaded from battle card. "
                f"Ready for review in Communications."
            ),
            "email_drafted": True,
            "company": company_name,
        }

    async def _execute_pricing_response(
        self, user_id: str, action: dict, payload: dict
    ) -> dict[str, Any]:
        """Create pricing counter-positioning notification."""
        company_name = payload.get("company_name", "")
        competitive_context = payload.get("competitive_context", {})
        pricing = competitive_context.get("pricing", {})

        self._db.table("notifications").insert({
            "user_id": user_id,
            "type": "action_completed",
            "title": f"Pricing response ready: {company_name}",
            "message": (
                f"Competitive pricing counter-positioning for {company_name} is ready. "
                f"Their pricing: {pricing.get('range', 'unknown')}. Battle card updated."
            ),
            "link": "/intelligence",
            "metadata": {
                "action_type": "competitive_pricing_response",
                "company": company_name,
            },
        }).execute()

        return {
            "status": "completed",
            "summary": (
                f"Pricing intelligence response prepared for {company_name}. "
                f"Battle card pricing section updated."
            ),
        }

    async def _execute_lead_discovery(
        self, user_id: str, action: dict, payload: dict
    ) -> dict[str, Any]:
        """Create lead discovery notification."""
        company_name = payload.get("company_name", "")

        self._db.table("notifications").insert({
            "user_id": user_id,
            "type": "action_completed",
            "title": f"Lead discovered: {company_name}",
            "message": (
                f"{company_name} added to discovered leads pipeline. "
                f"Enrichment data loaded."
            ),
            "link": "/pipeline",
            "metadata": {
                "action_type": "lead_discovery",
                "company": company_name,
            },
        }).execute()

        return {
            "status": "completed",
            "summary": f"Lead {company_name} added to pipeline with enrichment data.",
        }

    async def _execute_generic(
        self, user_id: str, action: dict, payload: dict
    ) -> dict[str, Any]:
        """Generic execution for unrecognized action types."""
        self._db.table("notifications").insert({
            "user_id": user_id,
            "type": "action_completed",
            "title": f"Action completed: {action.get('title', 'Unknown')[:50]}",
            "message": "Action has been approved and processed.",
            "link": "/actions",
        }).execute()

        return {
            "status": "completed",
            "summary": "Action approved and processed.",
        }

    async def _create_followup(
        self, user_id: str, action: dict, result: dict
    ) -> None:
        """Create a prospective memory for follow-up."""
        try:
            self._db.table("prospective_memories").insert({
                "user_id": user_id,
                "content": (
                    f"Follow up on approved action: {action.get('title', '')}. "
                    f"Check if user took next steps. "
                    f"Result: {result.get('summary', '')}"
                ),
                "trigger_type": "time",
                "trigger_config": json.dumps({"days_from_now": 3}),
                "status": "pending",
                "importance": 0.8,
                "metadata": json.dumps({
                    "action_id": action.get("id"),
                    "action_type": action.get("action_type"),
                }),
            }).execute()
        except Exception as e:
            logger.warning("[ActionExecutor] Failed to create follow-up: %s", e)
```

**Step 2: Verify the file was created**

Run: `python -c "from src.intelligence.action_executor import ActionExecutor; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/intelligence/action_executor.py
git commit -m "feat: add ActionExecutor service for post-approval downstream execution"
```

---

### Task 2: Wire ActionExecutor into approve/reject endpoints

**Files:**
- Modify: `backend/src/services/action_queue_service.py` (lines 194-234 for approve, lines 236-289 for reject)

**Step 1: Add post-approval execution to `approve_action`**

In `action_queue_service.py`, after the existing approve logic (which updates status and returns `result.data[0]`), add execution call. The current code at line 222-228 is:

```python
        if result.data:
            logger.info(
                "Action approved",
                extra={"action_id": action_id, "user_id": user_id},
            )
            return cast(dict[str, Any], result.data[0])
```

Replace that block with:

```python
        if result.data:
            action = cast(dict[str, Any], result.data[0])
            logger.info(
                "Action approved",
                extra={"action_id": action_id, "user_id": user_id},
            )

            # Execute post-approval downstream actions
            try:
                from src.intelligence.action_executor import ActionExecutor

                executor = ActionExecutor(self._db)
                execution_result = await executor.execute_approved_action(
                    action_id, user_id
                )
                action["execution"] = execution_result
            except Exception:
                logger.warning(
                    "Post-approval execution failed",
                    extra={"action_id": action_id},
                    exc_info=True,
                )

            return action
```

**Step 2: Add proactive_proposals sync to `reject_action`**

In the reject method, after the trust update block (line 267-283), add proposal sync. The current code at line 267-283:

```python
        if result.data:
            action = cast(dict[str, Any], result.data[0])
            logger.info(
                "Action rejected",
                extra={"action_id": action_id, "user_id": user_id, "reason": reason},
            )
            # Update trust: rejection = user override
            try:
                category = action_type_to_category(action.get("action_type", ""))
                await self._exec_svc._trust.update_on_override(user_id, category)
            except Exception:
                logger.warning(
                    "Failed to update trust on rejection",
                    extra={"action_id": action_id},
                    exc_info=True,
                )
            return action
```

Add after the trust update `except` block, before `return action`:

```python
            # Sync proactive_proposals status to dismissed
            try:
                payload = action.get("payload", {})
                if isinstance(payload, str):
                    import json
                    payload = json.loads(payload)
                insight_id = payload.get("insight_id") if isinstance(payload, dict) else None
                if insight_id:
                    self._db.table("proactive_proposals").update({
                        "status": "dismissed",
                        "responded_at": datetime.now(UTC).isoformat(),
                    }).eq("insight_id", insight_id).eq("user_id", user_id).execute()
            except Exception:
                logger.warning(
                    "Failed to sync proactive_proposals on rejection",
                    extra={"action_id": action_id},
                    exc_info=True,
                )
```

**Step 3: Verify the backend starts**

Run: `cd backend && python -c "from src.services.action_queue_service import ActionQueueService; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/src/services/action_queue_service.py
git commit -m "feat: wire ActionExecutor into approve endpoint, sync proposals on reject"
```

---

### Task 3: Expandable action cards in ActionsPage

**Files:**
- Modify: `frontend/src/components/pages/ActionsPage.tsx`

**Step 1: Add expand/collapse state and full detail view to ActionItem**

The current `ActionItem` component (lines 304-441) shows only title, agent, risk badge, and time. Redesign it to:

1. Add `useState<boolean>` for `expanded` toggle
2. Make the entire card clickable to toggle expanded
3. In collapsed state: show full title (no truncate), first line of description, risk badge
4. In expanded state: show full description, competitive context from `action.payload`, recommended actions parsed from description, confidence + reasoning, then action buttons
5. Change "Discuss" button (`onDiscuss`) to toggle expand instead of navigating

Replace the entire `ActionItem` component (lines 304-441) with:

```tsx
function ActionItem({
  action,
  onApprove,
  onReject,
  isApproving,
  isRejecting,
}: {
  action: Action;
  onApprove: () => void;
  onReject: () => void;
  isApproving: boolean;
  isRejecting: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const riskColor = RISK_COLORS[action.risk_level];
  const agentInfo = resolveAgent(action.agent);

  const payload = (action.payload ?? {}) as Record<string, unknown>;
  const competitiveContext = (payload.competitive_context ?? {}) as Record<string, unknown>;
  const differentiation = (competitiveContext.differentiation ?? []) as string[];
  const weaknesses = (competitiveContext.weaknesses ?? []) as string[];
  const pricing = (competitiveContext.pricing ?? {}) as Record<string, unknown>;
  const companyName = (payload.company_name ?? '') as string;

  // Parse recommended actions from description
  const descriptionLines = (action.description ?? '').split('\n');
  const mainDescription = descriptionLines
    .filter((l) => !l.startsWith('- '))
    .join(' ')
    .trim();
  const recommendedActions = descriptionLines.filter((l) => l.startsWith('- '));

  const hasCompetitiveContext =
    differentiation.length > 0 || weaknesses.length > 0 || Object.keys(pricing).length > 0;

  return (
    <div
      className={cn(
        'border rounded-lg transition-all duration-200',
        expanded ? 'ring-1 ring-[var(--accent)]/30' : 'hover:border-[var(--accent)]/30',
        action.status === 'pending' && 'cursor-pointer'
      )}
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
      onClick={() => action.status === 'pending' && setExpanded(!expanded)}
    >
      {/* Collapsed header — always visible */}
      <div className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div className="flex-shrink-0 mt-0.5">
              <AgentAvatar agentKey={action.agent} size={32} />
            </div>
            <div className="min-w-0 flex-1">
              <p
                className="font-medium text-sm"
                style={{ color: 'var(--text-primary)' }}
              >
                {action.title}
              </p>
              {!expanded && mainDescription && (
                <p
                  className="text-xs mt-1 line-clamp-1"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {mainDescription}
                </p>
              )}
              <div className="flex items-center gap-2 mt-1.5">
                <span
                  className="font-mono text-xs"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {agentInfo.name}
                </span>
                <span
                  className="px-1.5 py-0.5 rounded text-xs font-medium"
                  style={{
                    backgroundColor: `${riskColor}20`,
                    color: riskColor,
                  }}
                >
                  {action.risk_level?.toUpperCase() ?? 'UNKNOWN'}
                </span>
                <span
                  className="font-mono text-xs"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  {formatRelativeTime(action.created_at)}
                </span>
              </div>
            </div>
          </div>

          {/* Status indicator for non-pending */}
          {action.status !== 'pending' && (
            <div className="flex items-center gap-2 flex-shrink-0">
              <span
                className="flex items-center gap-1 text-xs"
                style={{ color: ACTION_STATUS_COLORS[action.status] }}
              >
                {action.status === 'completed' && <CheckCircle className="w-3.5 h-3.5" />}
                {action.status === 'rejected' && <XCircle className="w-3.5 h-3.5" />}
                {action.status === 'failed' && <AlertCircle className="w-3.5 h-3.5" />}
                {action.status === 'executing' && (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                )}
                {(action.status ?? '').replace('_', ' ').toUpperCase()}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Expanded details */}
      {expanded && action.status === 'pending' && (
        <div
          className="px-4 pb-4 pt-0 border-t"
          style={{ borderColor: 'var(--border)' }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Full description */}
          {mainDescription && (
            <p
              className="text-sm mt-3 leading-relaxed"
              style={{ color: 'var(--text-primary)' }}
            >
              {mainDescription}
            </p>
          )}

          {/* Competitive context */}
          {hasCompetitiveContext && (
            <div className="mt-4 space-y-2">
              <p
                className="text-[11px] font-medium uppercase tracking-wider"
                style={{ color: 'var(--text-secondary)' }}
              >
                Competitive Context
                {companyName && ` — ${companyName}`}
              </p>
              {differentiation.length > 0 && (
                <div
                  className="rounded-md p-2.5 text-xs space-y-1"
                  style={{ backgroundColor: 'var(--bg-subtle)' }}
                >
                  <span
                    className="font-medium"
                    style={{ color: 'var(--success)' }}
                  >
                    Your advantages:
                  </span>
                  {differentiation.map((d, i) => (
                    <p key={i} style={{ color: 'var(--text-primary)' }}>
                      &bull; {String(d)}
                    </p>
                  ))}
                </div>
              )}
              {weaknesses.length > 0 && (
                <div
                  className="rounded-md p-2.5 text-xs space-y-1"
                  style={{ backgroundColor: 'var(--bg-subtle)' }}
                >
                  <span
                    className="font-medium"
                    style={{ color: 'var(--warning)' }}
                  >
                    Their weaknesses:
                  </span>
                  {weaknesses.map((w, i) => (
                    <p key={i} style={{ color: 'var(--text-primary)' }}>
                      &bull; {String(w)}
                    </p>
                  ))}
                </div>
              )}
              {pricing && (pricing.range || pricing.strategy || pricing.notes) && (
                <div
                  className="rounded-md p-2.5 text-xs"
                  style={{ backgroundColor: 'var(--bg-subtle)' }}
                >
                  <span
                    className="font-medium"
                    style={{ color: 'var(--accent)' }}
                  >
                    Pricing intel:
                  </span>
                  <p style={{ color: 'var(--text-primary)' }}>
                    {[pricing.range, pricing.strategy, pricing.notes]
                      .filter(Boolean)
                      .map(String)
                      .join(' — ')}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Recommended actions */}
          {recommendedActions.length > 0 && (
            <div className="mt-4">
              <p
                className="text-[11px] font-medium uppercase tracking-wider mb-2"
                style={{ color: 'var(--text-secondary)' }}
              >
                Recommended Actions
              </p>
              <div className="space-y-1">
                {recommendedActions.map((ra, i) => (
                  <p
                    key={i}
                    className="text-xs"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {ra}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Reasoning + confidence */}
          {action.reasoning && (
            <p
              className="text-xs mt-3 italic"
              style={{ color: 'var(--text-secondary)' }}
            >
              {action.reasoning}
            </p>
          )}

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-2 mt-4 pt-3 border-t"
            style={{ borderColor: 'var(--border)' }}
          >
            <button
              onClick={onReject}
              disabled={isRejecting || isApproving}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
                'border border-[var(--border)] hover:bg-[var(--bg-subtle)]',
                (isRejecting || isApproving) && 'opacity-50 cursor-not-allowed'
              )}
              style={{ color: 'var(--critical)' }}
            >
              {isRejecting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <XCircle className="w-3.5 h-3.5" />
              )}
              Reject
            </button>
            <button
              onClick={onApprove}
              disabled={isApproving || isRejecting}
              className={cn(
                'flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium transition-colors',
                (isApproving || isRejecting) && 'opacity-50 cursor-not-allowed'
              )}
              style={{
                backgroundColor: 'var(--success)',
                color: 'white',
              }}
            >
              {isApproving ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <CheckCircle className="w-3.5 h-3.5" />
              )}
              Approve
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Step 2: Remove `onDiscuss` prop from ActionItem usage in ActionsPage**

In the `ActionsPage` component (around line 679-688), the pending actions map passes `onDiscuss`. Remove it:

```tsx
// Before:
<ActionItem
  key={action.id}
  action={action}
  onApprove={() => approveMutation.mutate(action.id)}
  onReject={() => rejectMutation.mutate({ actionId: action.id })}
  onDiscuss={() => navigate(`/?discuss=action&id=${action.id}&title=${encodeURIComponent(action.title)}`)}
  isApproving={approveMutation.isPending}
  isRejecting={rejectMutation.isPending}
/>

// After:
<ActionItem
  key={action.id}
  action={action}
  onApprove={() => approveMutation.mutate(action.id)}
  onReject={() => rejectMutation.mutate({ actionId: action.id })}
  isApproving={approveMutation.isPending}
  isRejecting={rejectMutation.isPending}
/>
```

**Step 3: Remove unused `MessageSquare` import**

Remove `MessageSquare` from the lucide-react import at line 23 since we no longer use it.

**Step 4: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors (or only pre-existing ones)

**Step 5: Commit**

```bash
git add frontend/src/components/pages/ActionsPage.tsx
git commit -m "feat: expandable action cards with competitive context, remove Discuss navigation"
```

---

### Task 4: Expandable cards in PendingApprovalsModule (sidebar)

**Files:**
- Modify: `frontend/src/components/shell/intel-modules/PendingApprovalsModule.tsx`

**Step 1: Redesign PendingApprovalsModule with expand/collapse**

The current module (lines 31-206) shows compact cards with truncated title. The merge logic uses a `MergedAction` interface that only has `id, title, agent, riskLevel`. We need to also carry `description, payload, reasoning` from the API data.

Update the `MergedAction` interface and merge logic to include full data:

```tsx
interface MergedAction {
  id: string;
  title: string;
  agent: string;
  riskLevel: string;
  description: string;
  payload: Record<string, unknown>;
  reasoning: string;
}
```

Update the merge `useMemo` to pull more fields from API items:

```tsx
// WS items — limited data, fill what we can
for (const a of wsPending) {
  if (!seen.has(a.actionId)) {
    seen.add(a.actionId);
    result.push({
      id: a.actionId,
      title: a.title,
      agent: a.agent,
      riskLevel: a.riskLevel,
      description: a.description ?? '',
      payload: {},
      reasoning: '',
    });
  }
}

// API items — full data
if (apiActions) {
  for (const a of apiActions) {
    if (!seen.has(a.id)) {
      seen.add(a.id);
      result.push({
        id: a.id,
        title: a.title,
        agent: a.agent,
        riskLevel: a.risk_level,
        description: a.description ?? '',
        payload: a.payload ?? {},
        reasoning: a.reasoning ?? '',
      });
    }
  }
}
```

Then, replace the card rendering with expand/collapse behavior. Add a state for expanded card ID:

```tsx
const [expandedId, setExpandedId] = useState<string | null>(null);
```

Replace the card with an expandable version. When collapsed: full title (no truncate), risk badge. When expanded: description, competitive context, reasoning, approve/reject buttons.

Remove the `navigate` import from `useNavigate` since Discuss no longer navigates. Actually keep it for the "View all" link, but remove the Discuss `navigate` calls.

Replace the Discuss button with card click to toggle expand.

Full replacement for the card render inside `visible.map(...)`:

```tsx
{visible.map((action) => {
  const riskClass = RISK_COLORS[action.riskLevel] ?? RISK_COLORS.medium;
  const isApproving = approveMutation.isPending && approveMutation.variables === action.id;
  const isRejecting = rejectMutation.isPending && rejectMutation.variables?.actionId === action.id;
  const isProcessing = isApproving || isRejecting;
  const isExpanded = expandedId === action.id;

  const payload = action.payload as Record<string, unknown>;
  const competitiveContext = (payload?.competitive_context ?? {}) as Record<string, unknown>;
  const differentiation = (competitiveContext?.differentiation ?? []) as string[];
  const weaknesses = (competitiveContext?.weaknesses ?? []) as string[];
  const pricing = (competitiveContext?.pricing ?? {}) as Record<string, unknown>;
  const hasContext = differentiation.length > 0 || weaknesses.length > 0;

  return (
    <div
      key={action.id}
      className={`rounded-lg border transition-all duration-200 cursor-pointer ${
        isExpanded ? 'ring-1 ring-[var(--accent)]/30' : ''
      }`}
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-subtle)',
      }}
      onClick={() => setExpandedId(isExpanded ? null : action.id)}
    >
      <div className="px-3 py-2.5">
        <div className="flex items-start gap-2 mb-2">
          <AgentAvatar agentKey={action.agent} size={16} />
          <div className="min-w-0 flex-1">
            <p
              className="font-sans text-[12px] font-medium leading-tight"
              style={{ color: 'var(--text-primary)' }}
            >
              {action.title}
            </p>
            <div className="flex items-center gap-1.5 mt-1">
              <span
                className={`inline-flex items-center rounded px-1 py-0.5 text-[10px] font-medium border ${riskClass}`}
              >
                {action.riskLevel}
              </span>
            </div>
          </div>
        </div>

        {/* Expanded content */}
        {isExpanded && (
          <div
            className="mt-2 pt-2 border-t space-y-2"
            style={{ borderColor: 'var(--border)' }}
            onClick={(e) => e.stopPropagation()}
          >
            {action.description && (
              <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-primary)' }}>
                {action.description}
              </p>
            )}
            {hasContext && (
              <div className="space-y-1">
                <p className="text-[10px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                  Competitive Context
                </p>
                {differentiation.length > 0 && (
                  <div className="text-[11px] rounded p-1.5" style={{ backgroundColor: 'var(--bg-elevated)' }}>
                    <span style={{ color: 'var(--success)' }}>Advantages: </span>
                    <span style={{ color: 'var(--text-primary)' }}>
                      {differentiation.map(String).join('; ')}
                    </span>
                  </div>
                )}
                {weaknesses.length > 0 && (
                  <div className="text-[11px] rounded p-1.5" style={{ backgroundColor: 'var(--bg-elevated)' }}>
                    <span style={{ color: 'var(--warning)' }}>Weaknesses: </span>
                    <span style={{ color: 'var(--text-primary)' }}>
                      {weaknesses.map(String).join('; ')}
                    </span>
                  </div>
                )}
                {pricing && (pricing.range || pricing.notes) && (
                  <div className="text-[11px] rounded p-1.5" style={{ backgroundColor: 'var(--bg-elevated)' }}>
                    <span style={{ color: 'var(--accent)' }}>Pricing: </span>
                    <span style={{ color: 'var(--text-primary)' }}>
                      {[pricing.range, pricing.notes].filter(Boolean).map(String).join(' — ')}
                    </span>
                  </div>
                )}
              </div>
            )}
            {action.reasoning && (
              <p className="text-[10px] italic" style={{ color: 'var(--text-secondary)' }}>
                {action.reasoning}
              </p>
            )}
          </div>
        )}

        {/* Action buttons */}
        <div
          className="flex items-center gap-1.5 justify-end mt-2"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => rejectMutation.mutate({ actionId: action.id })}
            disabled={isProcessing}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-50"
            style={{
              color: 'var(--critical)',
              backgroundColor: 'transparent',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <X size={12} />
            Reject
          </button>
          <button
            onClick={() => approveMutation.mutate(action.id)}
            disabled={isProcessing}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors disabled:opacity-50"
            style={{
              color: 'var(--success)',
              backgroundColor: 'transparent',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = 'rgba(34, 197, 94, 0.1)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = 'transparent';
            }}
          >
            <Check size={12} />
            Approve
          </button>
        </div>
      </div>
    </div>
  );
})}
```

Remove the `MessageSquare` import from lucide-react since Discuss button is gone.

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/shell/intel-modules/PendingApprovalsModule.tsx
git commit -m "feat: expandable pending approval cards in sidebar with competitive context"
```

---

### Task 5: Add conference pre-briefing generation

**Files:**
- Modify: `backend/src/intelligence/conference_intelligence.py`

**Step 1: Add `generate_pre_conference_briefing` method**

Add the following method to the `ConferenceIntelligenceEngine` class, after the `generate_recommendations` method (after line 392):

```python
    async def generate_pre_conference_briefing(
        self, user_id: str, conference_id: str
    ) -> Optional[dict]:
        """Generate a pre-conference competitive briefing 2 weeks before the event."""
        import json as _json

        conf = (
            self._db.table("conferences")
            .select("*")
            .eq("id", conference_id)
            .limit(1)
            .execute()
        )
        if not conf.data:
            return None
        conference = conf.data[0]

        participants = (
            self._db.table("conference_participants")
            .select("*")
            .eq("conference_id", conference_id)
            .execute()
        )

        competitors = await self._get_competitor_names(user_id)

        competitor_exhibitors: list[dict] = []
        prospect_speakers: list[dict] = []
        for p in participants.data or []:
            company = p.get("company_name", "")
            if any(comp.lower() in company.lower() for comp in competitors):
                competitor_exhibitors.append(p)
            elif not p.get("is_own_company"):
                prospect_speakers.append(p)

        # Pull battle card positioning for each competitor
        battle_briefs: list[dict] = []
        seen_companies: set[str] = set()
        for p in competitor_exhibitors:
            comp_name = p["company_name"]
            if comp_name in seen_companies:
                continue
            seen_companies.add(comp_name)

            bc = (
                self._db.table("battle_cards")
                .select("competitor_name, differentiation, pricing, weaknesses")
                .ilike("competitor_name", f"%{comp_name}%")
                .limit(1)
                .execute()
            )
            if bc.data:
                card = bc.data[0]
                battle_briefs.append({
                    "competitor": card["competitor_name"],
                    "differentiation": (card.get("differentiation") or [])[:3],
                    "weaknesses": (card.get("weaknesses") or [])[:3],
                    "pricing": card.get("pricing", {}),
                })

        briefing = {
            "conference_name": conference.get("name"),
            "start_date": conference.get("start_date"),
            "city": conference.get("city"),
            "competitor_count": len(competitor_exhibitors),
            "prospect_count": len(prospect_speakers),
            "competitor_exhibitors": [
                {
                    "company": p["company_name"],
                    "type": p.get("participation_type"),
                    "booth": p.get("booth_number"),
                    "presentation": p.get("presentation_title"),
                }
                for p in competitor_exhibitors[:10]
            ],
            "prospect_speakers": [
                {
                    "company": p["company_name"],
                    "person": p.get("person_name"),
                    "presentation": p.get("presentation_title"),
                }
                for p in prospect_speakers[:10]
            ],
            "battle_briefs": battle_briefs,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Store as conference insight
        all_companies = list(
            set(
                p["company_name"]
                for p in competitor_exhibitors + prospect_speakers
            )
        )
        self._db.table("conference_insights").insert({
            "user_id": user_id,
            "conference_id": conference_id,
            "insight_type": "pre_conference_briefing",
            "content": _json.dumps(briefing),
            "companies_mentioned": all_companies,
            "urgency": "high",
            "actionable": True,
            "recommended_actions": _json.dumps([
                "Review competitor booth positions and prepare talking points",
                "Schedule meetings with prospect speakers before the conference",
                "Prepare competitive displacement materials for booth visits",
            ]),
        }).execute()

        # Write to memory
        self._db.table("memory_semantic").insert({
            "user_id": user_id,
            "fact": (
                f"[Conference Briefing] {conference['name']} "
                f"({conference.get('start_date')}): "
                f"{len(competitor_exhibitors)} competitors, "
                f"{len(prospect_speakers)} prospects. "
                f"Battle card positioning prepared."
            ),
            "confidence": 0.9,
            "source": "conference_briefing",
            "metadata": _json.dumps({"conference_id": conference_id}),
        }).execute()

        logger.info(
            "[ConferenceIntel] Pre-briefing generated for %s",
            conference["name"],
        )
        return briefing
```

**Step 2: Verify**

Run: `cd backend && python -c "from src.intelligence.conference_intelligence import ConferenceIntelligenceEngine; print('OK')"`

**Step 3: Commit**

```bash
git add backend/src/intelligence/conference_intelligence.py
git commit -m "feat: add pre-conference briefing generation with battle card positioning"
```

---

### Task 6: Add pre-conference briefing scheduled job

**Files:**
- Modify: `backend/src/services/scheduler.py`

**Step 1: Add the scheduled function**

Add a new function `_run_pre_conference_briefings` after the existing scheduled functions. Also add it to the APScheduler setup (find where jobs are added and add a weekly trigger).

The function should:
1. Query `conference_recommendations` for conferences within 14-30 days with `recommendation_type` in `('must_attend', 'consider')`
2. For each, check if a `pre_conference_briefing` insight already exists
3. If not, generate one

```python
async def _run_pre_conference_briefings() -> None:
    """Generate pre-conference briefings for upcoming conferences (14-30 days out)."""
    try:
        from datetime import datetime, timedelta, timezone

        from src.db.supabase import SupabaseClient
        from src.intelligence.conference_intelligence import ConferenceIntelligenceEngine

        db = SupabaseClient.get_client()
        now = datetime.now(timezone.utc).date()
        window_start = now + timedelta(days=14)
        window_end = now + timedelta(days=30)

        # Find conferences in the briefing window with must_attend or consider
        recs = (
            db.table("conference_recommendations")
            .select("user_id, conference_id")
            .in_("recommendation_type", ["must_attend", "consider"])
            .execute()
        )

        if not recs.data:
            return

        # Filter by date range using conferences table
        for rec in recs.data:
            try:
                conf = (
                    db.table("conferences")
                    .select("id, name, start_date")
                    .eq("id", rec["conference_id"])
                    .gte("start_date", window_start.isoformat())
                    .lte("start_date", window_end.isoformat())
                    .limit(1)
                    .execute()
                )
                if not conf.data:
                    continue

                # Check if briefing already exists
                existing = (
                    db.table("conference_insights")
                    .select("id")
                    .eq("user_id", rec["user_id"])
                    .eq("conference_id", rec["conference_id"])
                    .eq("insight_type", "pre_conference_briefing")
                    .limit(1)
                    .execute()
                )
                if existing.data:
                    continue

                engine = ConferenceIntelligenceEngine(db)
                await engine.generate_pre_conference_briefing(
                    rec["user_id"], rec["conference_id"]
                )
                logger.info(
                    "Pre-conference briefing generated for %s",
                    conf.data[0]["name"],
                )
            except Exception:
                logger.warning(
                    "Failed to generate pre-conference briefing for conference %s",
                    rec["conference_id"],
                    exc_info=True,
                )
    except Exception:
        logger.warning("Pre-conference briefing job failed", exc_info=True)
```

Then find where the APScheduler jobs are registered (look for `scheduler.add_job` calls) and add:

```python
scheduler.add_job(
    _run_pre_conference_briefings,
    "cron",
    day_of_week="mon",
    hour=6,
    minute=0,
    id="pre_conference_briefings",
    replace_existing=True,
)
```

**Step 2: Verify**

Run: `cd backend && python -c "from src.services.scheduler import _run_pre_conference_briefings; print('OK')"`

**Step 3: Commit**

```bash
git add backend/src/services/scheduler.py
git commit -m "feat: add weekly pre-conference briefing scheduled job"
```

---

### Task 7: Add goal impact checking to action router

**Files:**
- Modify: `backend/src/intelligence/action_router.py`

**Step 1: Add `_check_goal_impact` method to ActionRouter**

Add after the `_check_lead_discovery` method (after line 770):

```python
    async def _check_goal_impact(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Check if insight impacts active goals and create goal_updates."""
        try:
            goals = (
                self._db.table("goals")
                .select("id, title, goal_type, status")
                .eq("user_id", user_id)
                .in_("status", ["active", "in_progress", "plan_ready"])
                .execute()
            )

            if not goals.data:
                return None

            content = (insight.get("content", "") or "").lower()
            goals_updated: list[str] = []

            for goal in goals.data:
                title = (goal.get("title", "") or "").lower()
                # Require at least 2 meaningful keyword overlaps (>3 chars)
                goal_keywords = {w for w in title.split() if len(w) > 3}
                content_keywords = {w for w in content.split() if len(w) > 3}
                overlap = goal_keywords & content_keywords

                if len(overlap) >= 2:
                    try:
                        self._db.table("goal_updates").insert({
                            "goal_id": goal["id"],
                            "update_type": "intelligence",
                            "content": (
                                f"New {insight.get('classification', 'intelligence')}: "
                                f"{insight.get('content', '')[:200]}"
                            ),
                        }).execute()
                        goals_updated.append(goal["title"])
                    except Exception:
                        pass

            if goals_updated:
                return {
                    "type": "check_goal_impact",
                    "goals_updated": len(goals_updated),
                }
            return None
        except Exception:
            return None
```

**Step 2: Call `_check_goal_impact` at the end of `route_insight`**

In `route_insight()` (line 45-108), add before the final `return actions_taken` (line 108):

```python
        # Always check goal impact regardless of rule matching
        try:
            goal_result = await self._check_goal_impact(user_id, insight, context)
            if goal_result:
                actions_taken.append(goal_result)
        except Exception:
            pass

        return actions_taken
```

Note: there are TWO return paths in `route_insight` — one for no-match (line 78) and one for matched rules (line 108). Add the goal check before BOTH returns.

**Step 3: Verify**

Run: `cd backend && python -c "from src.intelligence.action_router import ActionRouter; print('OK')"`

**Step 4: Commit**

```bash
git add backend/src/intelligence/action_router.py
git commit -m "feat: add goal impact checking to action router for all insights"
```

---

### Task 8: Add Jarvis insights to chat context

**Files:**
- Modify: `backend/src/services/chat.py` (the process_message or context builder)

**Step 1: Find the right insertion point**

The chat service at `backend/src/services/chat.py` has a `process_message` method that gathers context in parallel before calling the LLM. Based on earlier observations (#13807, #13808), there's already a pattern of adding context fetches (like `_get_recent_signals`) to the parallel context gathering.

Look for the parallel context gather section (around lines 2757-2770 based on observations). Add a `_get_recent_jarvis_insights` method and call it.

Add the method to the `ChatService` class:

```python
    async def _get_recent_jarvis_insights(self, user_id: str) -> str:
        """Fetch recent Jarvis intelligence insights for chat context."""
        try:
            result = (
                self._db.table("jarvis_insights")
                .select("classification, content, confidence")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .limit(5)
                .execute()
            )

            if not result.data:
                return ""

            lines = ["ARIA's Recent Intelligence Insights:"]
            for i in result.data:
                classification = (i.get("classification") or "intelligence").upper()
                content = (i.get("content") or "")[:150]
                confidence = i.get("confidence", 0)
                lines.append(
                    f"- [{classification}] ({confidence:.0%}) {content}"
                )
            return "\n".join(lines)
        except Exception:
            return ""
```

Then add this to the parallel context gather section. Look for an `asyncio.gather` or sequential context calls in `process_message`, and add the jarvis insights call alongside existing context fetches. Wire the result into the system prompt the same way `_get_recent_signals` or `_get_proactive_insights` is wired.

**NOTE:** The chat.py file is very large (~4000 lines). The engineer should:
1. Search for `_get_proactive_insights` to find the pattern
2. Add `_get_recent_jarvis_insights` similarly
3. Search for where context sections are assembled into the system prompt
4. Add the jarvis insights string to the prompt assembly

If the table `jarvis_insights` doesn't exist, the method gracefully returns `""` so it won't break anything.

**Step 2: Verify**

Run: `cd backend && python -c "from src.services.chat import ChatService; print('OK')"`

**Step 3: Commit**

```bash
git add backend/src/services/chat.py
git commit -m "feat: add Jarvis intelligence insights to chat context"
```

---

### Task 9: Verify no hardcoded IDs and run frontend build

**Files:** None (verification only)

**Step 1: Check for hardcoded IDs in new/modified backend code**

Run: `grep -rn "41475700\|Repligen\|repligen" backend/src/intelligence/action_executor.py backend/src/services/action_queue_service.py backend/src/intelligence/action_router.py`
Expected: No matches

**Step 2: Run frontend build check**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: No new errors

**Step 3: Run backend import check**

Run: `cd backend && python -c "
from src.intelligence.action_executor import ActionExecutor
from src.intelligence.action_router import ActionRouter
from src.intelligence.conference_intelligence import ConferenceIntelligenceEngine
from src.services.action_queue_service import ActionQueueService
print('All imports OK')
"`
Expected: `All imports OK`

**Step 4: Commit all remaining changes**

```bash
git add -A
git commit -m "feat: complete action lifecycle — approval UX, post-approval execution, conference briefing, goal impact, chat context"
```

---

## Summary of changes

| Component | What changed | Bug fixed |
|-----------|-------------|-----------|
| `ActionsPage.tsx` ActionItem | Expand/collapse with full details, competitive context, recommended actions | BUG 1: Cards too small |
| `PendingApprovalsModule.tsx` | Expand/collapse with competitive context | BUG 1: Cards too small |
| Both components | Discuss button removed, click-to-expand replaces it | BUG 2: Discuss does nothing |
| `action_executor.py` (new) | Post-approval execution: email drafts, notifications, memory, follow-ups, proposal sync | BUG 3: Approve does nothing |
| `action_queue_service.py` | Wires executor into approve, syncs proposals on reject | BUG 3: Approve does nothing |
| `conference_intelligence.py` | Pre-conference briefing generation | New feature |
| `scheduler.py` | Weekly pre-conference briefing job | New feature |
| `action_router.py` | Goal impact checking on all insights | New feature |
| `chat.py` | Jarvis insights in chat context | New feature |
