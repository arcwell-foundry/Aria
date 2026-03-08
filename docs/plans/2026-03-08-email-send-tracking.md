# Email Send Tracking & Follow-up System

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Track sent emails, detect stale threads (no reply), and suggest follow-ups. Works systemically for ALL users, ALL sent emails.

**Tech Stack:** React, TypeScript, React Query, FastAPI, Supabase, Composio (Gmail/Outlook)

---

## Part A: Stale Thread Detection (NEW)

### Problem
ARIA has no tracking of whether contacts replied after the user sent an email. This creates missed opportunities where important threads go cold without follow-up.

### Solution
Add a **stale thread detection system** that:
1. Tracks all sent/saved drafts
2. Monitors for replies in the same thread
3. Surfaces threads that need follow-up in the Communications page

---

## Task A1: Create Backend Follow-up Tracker Service

**File:** `backend/src/services/followup_tracker.py` (NEW)

```python
"""Service for detecting stale email threads that need follow-up."""

import logging
from datetime import datetime, UTC, timedelta
from typing import Any

from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)


class StaleThread:
    """A stale thread that needs follow-up."""

    def __init__(
        self,
        draft_id: str,
        recipient_name: str | None,
        recipient_email: str,
        subject: str,
        sent_at: str,
        days_since_sent: int,
        urgency: str,
        thread_id: str | None,
    ):
        self.draft_id = draft_id
        self.recipient_name = recipient_name
        self.recipient_email = recipient_email
        self.subject = subject
        self.sent_at = sent_at
        self.days_since_sent = days_since_sent
        self.urgency = urgency
        self.thread_id = thread_id

    @property
    def suggested_action(self) -> str:
        """Generate a human-readable suggested action."""
        if self.urgency == "URGENT":
            return "Follow up urgently"
        elif self.urgency == "LOW":
            return "Check in when convenient"
        return "Consider a gentle follow-up"

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "recipient_name": self.recipient_name,
            "recipient_email": self.recipient_email,
            "subject": self.subject,
            "sent_at": self.sent_at,
            "days_since_sent": self.days_since_sent,
            "urgency": self.urgency,
            "thread_id": self.thread_id,
            "suggested_action": self.suggested_action,
        }


class FollowupTracker:
    """Detects stale email threads that need follow-up."""

    # Configurable thresholds (days)
    THRESHOLDS = {
        "URGENT": 3,
        "NORMAL": 5,
        "LOW": 7,
    }
    DEFAULT_THRESHOLD_DAYS = 5
    MINIMUM_THRESHOLD_DAYS = 3  # Don't show anything younger than this

    async def get_stale_threads(self, user_id: str) -> list[StaleThread]:
        """Find sent drafts where recipient hasn't replied within threshold.

        Args:
            user_id: The user ID to check stale threads for.

        Returns:
            List of StaleThread objects sorted by days_since_sent DESC.
        """
        try:
            client = SupabaseClient.get_client()

            # Query sent drafts older than minimum threshold with no reply
            # Uses LEFT JOIN to get original email urgency from email_scan_log
            result = client.rpc(
                "get_stale_threads",
                {"p_user_id": user_id}
            ).execute()

            if not result.data:
                return []

            threads = []
            for row in result.data:
                threads.append(StaleThread(
                    draft_id=row["draft_id"],
                    recipient_name=row.get("recipient_name"),
                    recipient_email=row["recipient_email"],
                    subject=row["subject"],
                    sent_at=row["sent_at"],
                    days_since_sent=row["days_since_sent"],
                    urgency=row.get("urgency", "NORMAL"),
                    thread_id=row.get("thread_id"),
                ))

            # Filter by urgency-specific threshold
            filtered = []
            for thread in threads:
                threshold = self.THRESHOLDS.get(thread.urgency, self.DEFAULT_THRESHOLD_DAYS)
                if thread.days_since_sent >= threshold:
                    filtered.append(thread)

            # Sort by days_since_sent DESC
            filtered.sort(key=lambda t: t.days_since_sent, reverse=True)

            logger.info(
                "Found %d stale threads for user %s",
                len(filtered),
                user_id,
            )
            return filtered

        except Exception:
            logger.exception("Failed to get stale threads for user %s", user_id)
            return []


# Singleton instance
_followup_tracker: FollowupTracker | None = None


def get_followup_tracker() -> FollowupTracker:
    """Get or create FollowupTracker singleton."""
    global _followup_tracker
    if _followup_tracker is None:
        _followup_tracker = FollowupTracker()
    return _followup_tracker
```

---

## Task A2: Create Database Function for Stale Threads Query

**File:** `backend/supabase/migrations/20260308110000_stale_threads_function.sql` (NEW)

```sql
-- Stale threads detection function for follow-up tracking
-- Finds sent drafts where the recipient hasn't replied within the threshold

CREATE OR REPLACE FUNCTION get_stale_threads(p_user_id UUID)
RETURNS TABLE (
    draft_id UUID,
    recipient_name TEXT,
    recipient_email TEXT,
    subject TEXT,
    sent_at TIMESTAMPTZ,
    days_since_sent INTEGER,
    urgency TEXT,
    thread_id TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id AS draft_id,
        d.recipient_name,
        d.recipient_email,
        d.subject,
        d.sent_at,
        EXTRACT(DAY FROM NOW() - d.sent_at)::INTEGER AS days_since_sent,
        COALESCE(e.urgency, 'NORMAL')::TEXT AS urgency,
        d.thread_id
    FROM email_drafts d
    LEFT JOIN email_scan_log e
        ON e.email_id = d.original_email_id
        AND e.user_id = d.user_id
    WHERE d.user_id = p_user_id
      AND d.status IN ('sent', 'saved_to_client', 'approved')
      AND d.sent_at < NOW() - INTERVAL '3 days'
      AND (
          d.thread_id IS NULL
          OR NOT EXISTS (
              SELECT 1 FROM email_scan_log s
              WHERE s.user_id = p_user_id
                AND s.thread_id = d.thread_id
                AND s.sender_email = d.recipient_email
                AND s.scanned_at > d.sent_at
                AND s.category != 'SKIP'
          )
      )
    ORDER BY days_since_sent DESC;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_stale_threads IS 'Finds sent drafts where the recipient has not replied. Used for follow-up tracking.';
```

---

## Task A3: Add Stale Threads API Endpoint

**File:** `backend/src/api/routes/drafts.py` (MODIFY)

Add to imports:
```python
from src.services.followup_tracker import get_followup_tracker
```

Add new response models and endpoint:
```python
class StaleThreadResponse(BaseModel):
    """A stale thread that needs follow-up."""
    draft_id: str = Field(..., description="ID of the sent draft")
    recipient_name: str | None = Field(None, description="Recipient name")
    recipient_email: str = Field(..., description="Recipient email")
    subject: str = Field(..., description="Email subject")
    sent_at: str = Field(..., description="When the email was sent")
    days_since_sent: int = Field(..., description="Days since the email was sent")
    urgency: str = Field(..., description="Original email urgency (URGENT, NORMAL, LOW)")
    thread_id: str | None = Field(None, description="Thread ID for context")
    suggested_action: str = Field(..., description="Human-readable follow-up suggestion")


class StaleThreadsResponse(BaseModel):
    """Response for stale threads endpoint."""
    threads: list[StaleThreadResponse] = Field(default_factory=list)
    total: int = Field(..., description="Total number of stale threads")


@router.get("/stale-threads", response_model=StaleThreadsResponse)
async def get_stale_threads(current_user: CurrentUser) -> dict[str, Any]:
    """Get stale threads that need follow-up.

    Finds sent emails where the recipient hasn't replied within the
    configurable threshold (3 days for urgent, 5 days for normal).

    Args:
        current_user: The authenticated user.

    Returns:
        List of stale threads sorted by days_since_sent DESC.
    """
    tracker = get_followup_tracker()
    threads = await tracker.get_stale_threads(current_user.id)

    return {
        "threads": [t.to_dict() for t in threads],
        "total": len(threads),
    }
```

---

## Task A4: Add Frontend Types and API Client

**File:** `frontend/src/api/drafts.ts` (MODIFY)

Add types:
```typescript
export interface StaleThread {
  draft_id: string;
  recipient_name?: string;
  recipient_email: string;
  subject: string;
  sent_at: string;
  days_since_sent: number;
  urgency: 'URGENT' | 'NORMAL' | 'LOW';
  thread_id?: string;
  suggested_action: string;
}

export interface StaleThreadsResponse {
  threads: StaleThread[];
  total: number;
}
```

Add API function:
```typescript
export async function getStaleThreads(): Promise<StaleThreadsResponse> {
  const response = await apiClient.get('/drafts/stale-threads');
  return response.data;
}
```

---

## Task A5: Add React Hook for Stale Threads

**File:** `frontend/src/hooks/useDrafts.ts` (MODIFY)

Add import:
```typescript
import { getStaleThreads, StaleThread } from '@/api/drafts';
```

Add hook:
```typescript
export function useStaleThreads() {
  return useQuery({
    queryKey: ['stale-threads'],
    queryFn: getStaleThreads,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}
```

---

## Task A6: Add Follow-up Needed Section to Communications Page

**File:** `frontend/src/components/pages/CommunicationsPage.tsx` (MODIFY)

Add imports:
```typescript
import { useStaleThreads } from '@/hooks/useDrafts';
import { AlertTriangle, ChevronDown, ChevronUp, MailOpen } from 'lucide-react';
```

Add new component before `DraftsList`:
```typescript
// Follow-up Needed Section
function FollowupNeededSection() {
  const navigate = useNavigate();
  const { data, isLoading } = useStaleThreads();
  const [isExpanded, setIsExpanded] = useState(true);

  // Don't show if no stale threads
  if (isLoading || !data || data.total === 0) {
    return null;
  }

  const threads = data.threads;

  return (
    <div
      className="mb-6 border rounded-xl overflow-hidden"
      style={{
        borderColor: 'rgba(245, 158, 11, 0.5)',
        backgroundColor: 'var(--bg-elevated)',
      }}
    >
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-[var(--bg-subtle)] transition-colors"
      >
        <div className="flex items-center gap-3">
          <AlertTriangle
            className="w-5 h-5"
            style={{ color: '#f59e0b' }}
          />
          <span
            className="font-medium"
            style={{ color: 'var(--text-primary)' }}
          >
            Follow-up Needed
          </span>
          <span
            className="px-2 py-0.5 rounded-full text-xs font-medium"
            style={{
              backgroundColor: '#f59e0b',
              color: 'white',
            }}
          >
            {data.total}
          </span>
        </div>
        {isExpanded ? (
          <ChevronUp className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        ) : (
          <ChevronDown className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        )}
      </button>

      {/* Thread list */}
      {isExpanded && (
        <div className="border-t" style={{ borderColor: 'var(--border)' }}>
          {threads.map((thread) => (
            <div
              key={thread.draft_id}
              className="flex items-center justify-between p-4 border-b last:border-b-0 hover:bg-[var(--bg-subtle)] transition-colors"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
                  style={{ backgroundColor: 'var(--bg-subtle)' }}
                >
                  <MailOpen
                    className="w-5 h-5"
                    style={{ color: 'var(--text-secondary)' }}
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className="font-medium text-sm truncate"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {thread.recipient_name || thread.recipient_email}
                    </span>
                    <span
                      className="text-xs px-2 py-0.5 rounded-full"
                      style={{
                        backgroundColor: thread.urgency === 'URGENT' ? '#ef4444' : '#f59e0b',
                        color: 'white',
                      }}
                    >
                      {thread.days_since_sent}d ago
                    </span>
                  </div>
                  <p
                    className="text-sm truncate"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {thread.subject}
                  </p>
                  <p
                    className="text-xs"
                    style={{ color: 'var(--text-tertiary, var(--text-secondary))', opacity: 0.7 }}
                  >
                    Sent {new Date(thread.sent_at).toLocaleDateString()} · No reply
                  </p>
                </div>
              </div>
              <button
                onClick={() => navigate(`/?prompt=${encodeURIComponent(
                  `Draft a follow-up email to ${thread.recipient_name || thread.recipient_email} about "${thread.subject}". My last email was sent ${thread.days_since_sent} days ago with no reply.`
                )}`)}
                className={cn(
                  'flex-shrink-0 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                  'bg-[var(--accent)] text-white hover:opacity-90'
                )}
              >
                Draft Follow-up
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

Update `DraftsList` to include the section:
```typescript
// In DraftsList component, add after the header and before "Content":
{/* Follow-up Needed Section */}
<FollowupNeededSection />
```

---

## Part B: Send Flow Verification (EXISTING - Previously Implemented)

**Note:** The following tasks were part of the original send tracking implementation. They verify the send flow works correctly.

**Architecture:** The backend already has the complete send flow with status update, sent_at, and error_message handling in `DraftService.send_draft()`. The frontend has `useSendDraft()` hook and the Send Email button wired up. The Sent Rate calculation in `AnalysisModule.tsx` correctly computes `sent / total * 100`. The issue is likely that no emails have actually been sent yet (no active email integration connected). This plan verifies all wiring is correct and adds a success toast for better UX.

---

## Task 1: Verify Backend Send Email Flow

**Files:**
- Verify: `backend/src/services/draft_service.py:664-762`
- Verify: `backend/src/api/routes/drafts.py:560-583`

**Step 1: Review DraftService.send_draft() implementation**

The existing implementation in `draft_service.py:664-762` already:
1. Validates draft exists and is not already sent
2. Gets email integration (Gmail or Outlook) via `_get_email_integration()`
3. Sends via Composio using `oauth_client.execute_action()`
4. Updates status to 'sent' and sets `sent_at` timestamp
5. Records activity with `activity_type="email_sent"`
6. On failure, updates status to 'failed' with `error_message`

**No changes needed - implementation is complete.**

**Step 2: Review API route /drafts/{draft_id}/send**

The existing route in `drafts.py:560-583`:
1. Calls `service.send_draft()`
2. Returns `EmailSendResponse` with id, status, sent_at, error_message
3. Handles `NotFoundError` (404) and `EmailSendError` (502)

**No changes needed - implementation is complete.**

---

## Task 2: Add Success Toast Notification

**Files:**
- Modify: `frontend/src/components/pages/DraftDetailPage.tsx`
- Modify: `frontend/src/hooks/useDrafts.ts`

**Step 1: Install toast notification library if not present**

Run: `cd frontend && npm list sonner`
Expected: sonner@2.x.x (or similar toast library)

If not installed:
Run: `cd frontend && npm install sonner`

**Step 2: Add toast import and use in DraftDetailPage**

```tsx
// Add to imports at top of DraftDetailPage.tsx
import { toast } from 'sonner';

// Update handleSend function (lines 90-94)
const handleSend = async () => {
  if (!draft) return;
  try {
    await sendDraft.mutateAsync(draftId);
    toast.success(`Email sent to ${draft.recipient_name || draft.recipient_email}`);
    navigate('/communications');
  } catch (error) {
    toast.error('Failed to send email. Please try again.');
  }
};
```

**Step 3: Verify toast provider exists in app root**

Check: `frontend/src/App.tsx` for `<Toaster />` component from sonner.

If not present, add to App.tsx:
```tsx
import { Toaster } from 'sonner';

// Add inside the main component's return, after any routers/providers
<Toaster position="top-right" />
```

---

## Task 3: Verify Sent/Failed Filter Tabs Work

**Files:**
- Verify: `frontend/src/components/pages/CommunicationsPage.tsx:36-41`

**Step 1: Review STATUS_FILTERS constant**

The existing code at lines 36-41:
```tsx
const STATUS_FILTERS: { label: string; value: EmailDraftStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Draft', value: 'draft' },
  { label: 'Sent', value: 'sent' },
  { label: 'Failed', value: 'failed' },
];
```

**Status filters are already defined for 'sent' and 'failed'.**

**Step 2: Verify list_drafts passes status filter to API**

In CommunicationsPage.tsx lines 181-183:
```tsx
const { data: drafts, isLoading, error } = useDrafts(
  statusFilter !== 'all' ? statusFilter : undefined
);
```

The hook passes the status filter to the API. **No changes needed.**

**Step 3: Verify backend handles status filter**

In draft_service.py:246-286 `list_drafts()`:
```python
if status:
    query = query.eq("status", status)
```

**Backend correctly filters by status. No changes needed.**

---

## Task 4: Add Empty States for Sent/Failed Tabs

**Files:**
- Modify: `frontend/src/components/pages/CommunicationsPage.tsx`

**Step 1: Update empty state message to be context-aware**

Find the EmptyState component (lines 286-296):
```tsx
<EmptyState
  title="No drafts yet."
  description={
    searchQuery || statusFilter !== 'all'
      ? 'No drafts match your current filters. Try adjusting your search criteria.'
      : 'Ask ARIA to draft an email to get started.'
  }
  ...
/>
```

Update to provide better empty state messages:
```tsx
<EmptyState
  title={
    statusFilter === 'sent'
      ? 'No emails sent yet.'
      : statusFilter === 'failed'
        ? 'No failed emails.'
        : 'No drafts yet.'
  }
  description={
    statusFilter === 'sent'
      ? 'When you send emails through ARIA, they will appear here.'
      : statusFilter === 'failed'
        ? 'Failed email sends will appear here for review.'
        : searchQuery
          ? 'No drafts match your current filters. Try adjusting your search criteria.'
          : 'Ask ARIA to draft an email to get started.'
  }
  suggestion={statusFilter === 'all' ? 'Start a conversation' : undefined}
  onSuggestion={statusFilter === 'all' ? () => navigate('/') : undefined}
  icon={<Mail className="w-8 h-8" />}
/>
```

---

## Task 5: Verify Communication Analysis Sent Rate Calculation

**Files:**
- Verify: `frontend/src/components/shell/intel-modules/AnalysisModule.tsx:24-66`

**Step 1: Review sent rate calculation**

The existing code at lines 32-35:
```tsx
const total = drafts.length;
const sent = drafts.filter((d) => d.status === 'sent').length;
const sentRate = total > 0 ? Math.round((sent / total) * 100) : 0;
```

**Calculation is correct. It counts drafts where `status === 'sent'`.**

**Step 2: Verify useIntelDrafts hook fetches drafts**

In `useIntelPanelData.ts:207-213`:
```tsx
export function useIntelDrafts() {
  return useQuery({
    queryKey: intelKeys.drafts(),
    queryFn: () => listDrafts(undefined, 20),
    staleTime: 1000 * 60 * 2,
  });
}
```

This fetches drafts without status filter, so it gets all drafts including sent ones.

**Step 3: Ensure cache invalidation after send**

In `useDrafts.ts:100-110`:
```tsx
export function useSendDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (draftId: string) => sendDraft(draftId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.invalidateQueries({ queryKey: draftKeys.detail(result.id) });
    },
  });
}
```

**Issue found:** This invalidates `draftKeys.lists()` but not `intelKeys.drafts()`. The AnalysisModule uses a separate cache key. Need to add invalidation.

**Step 4: Fix cache invalidation to include IntelPanel cache**

Update `useSendDraft` in `frontend/src/hooks/useDrafts.ts`:
```tsx
export function useSendDraft() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (draftId: string) => sendDraft(draftId),
    onSuccess: (result) => {
      // Invalidate all draft list queries
      queryClient.invalidateQueries({ queryKey: draftKeys.lists() });
      queryClient.invalidateQueries({ queryKey: draftKeys.detail(result.id) });
      // Also invalidate IntelPanel's separate cache
      queryClient.invalidateQueries({ queryKey: ['intel-panel', 'drafts'] });
    },
  });
}
```

---

## Task 6: Verify Failed Status Handling

**Files:**
- Verify: `backend/src/services/draft_service.py:753-762`
- Verify: `frontend/src/components/pages/CommunicationsPage.tsx:65-73`

**Step 1: Review backend failure handling**

In draft_service.py:753-762:
```python
except Exception as e:
    # Try to update draft status to failed
    with contextlib.suppress(Exception):
        await self.update_draft(
            user_id, draft_id, {"status": "failed", "error_message": str(e)}
        )
    logger.exception("Failed to send email draft")
    raise EmailSendError(str(e), draft_id=draft_id) from e
```

**Backend correctly sets status='failed' and error_message on failure.**

**Step 2: Review frontend failed status badge**

In CommunicationsPage.tsx:65-73:
```tsx
const STATUS_STYLES: Record<EmailDraftStatus, { label: string; bg: string; text: string }> = {
  draft: { label: 'DRAFTING', bg: 'var(--accent)', text: 'white' },
  sent: { label: 'SENT', bg: 'var(--success)', text: 'white' },
  failed: { label: 'FAILED', bg: 'var(--critical)', text: 'white' },
  pending_review: { label: 'PENDING', bg: '#6366f1', text: 'white' },
  approved: { label: 'APPROVED', bg: 'var(--success)', text: 'white' },
  dismissed: { label: 'DISMISSED', bg: 'var(--text-secondary)', text: 'white' },
  saved_to_client: { label: 'SAVED', bg: '#0891b2', text: 'white' },
};
```

**Failed status has proper styling. No changes needed.**

---

## Task 7: Add Error Message Display for Failed Drafts

**Files:**
- Modify: `frontend/src/components/pages/DraftDetailPage.tsx`

**Step 1: Add error message display in DraftDetailPage**

In the status section (around line 191-209), add error display when draft is failed:

```tsx
{/* Error message for failed drafts */}
{draft.status === 'failed' && draft.error_message && (
  <div
    className="mb-4 p-3 rounded-lg border"
    style={{
      borderColor: 'var(--critical)',
      backgroundColor: 'rgba(239, 68, 68, 0.1)',
    }}
  >
    <p className="text-sm font-medium" style={{ color: 'var(--critical)' }}>
      Send failed: {draft.error_message}
    </p>
  </div>
)}
```

---

## Task 8: Verify TypeScript Types Include error_message

**Files:**
- Verify: `frontend/src/api/drafts.ts:39-71`

**Step 1: Check EmailDraft interface**

The existing interface at lines 39-71:
```tsx
export interface EmailDraft {
  id: string;
  user_id: string;
  recipient_email: string;
  recipient_name?: string;
  subject: string;
  body: string;
  purpose: EmailDraftPurpose;
  tone: EmailDraftTone;
  context?: { ... };
  lead_memory_id?: string;
  style_match_score?: number;
  confidence_tier?: ConfidenceTier;
  status: EmailDraftStatus;
  sent_at?: string;
  error_message?: string;  // ✓ Already present
  client_draft_id?: string;
  client_provider?: "gmail" | "outlook";
  saved_to_client_at?: string;
  created_at: string;
  updated_at: string;
  ...
}
```

**Types are correct. error_message is already defined.**

---

## Task 9: Final Verification Checklist

**Step 1: Build frontend**

Run: `cd frontend && npm run build`
Expected: Build succeeds without TypeScript errors

**Step 2: Type check**

Run: `cd frontend && npm run typecheck`
Expected: No type errors

**Step 3: Verify Send Email button is wired**

The button in DraftDetailPage.tsx lines 514-531 calls `handleSend()` which:
1. Calls `sendDraft.mutateAsync(draftId)`
2. Which calls backend `POST /drafts/{draft_id}/send`
3. Backend updates status to 'sent' and sets sent_at
4. Frontend invalidates cache and navigates back to list

**Step 4: Manual verification checklist**

- [ ] Send Email button exists on draft detail page
- [ ] Button shows loading state while sending
- [ ] Success toast appears after send
- [ ] Draft status changes from 'pending_review' to 'sent'
- [ ] Sent tab shows the sent email
- [ ] Communication Analysis panel updates sent rate
- [ ] Failed sends show error message
- [ ] Failed tab shows failed emails

---

## Summary of Changes

| File | Change |
|------|--------|
| `frontend/src/hooks/useDrafts.ts` | Add IntelPanel cache invalidation on send |
| `frontend/src/components/pages/DraftDetailPage.tsx` | Add success toast, add error message display |
| `frontend/src/components/pages/CommunicationsPage.tsx` | Improve empty state messages for sent/failed tabs |
| `frontend/src/App.tsx` | Ensure Toaster component is present (if needed) |

## Root Cause Analysis

The 0% sent rate is NOT a bug - it's expected behavior when no emails have been sent yet. The user needs an active Gmail or Outlook integration connected via Composio to send emails. Once emails are sent:

1. Backend updates `email_drafts.status = 'sent'` and sets `sent_at`
2. Frontend cache invalidation refreshes the list
3. AnalysisModule recalculates: `sent / total * 100`

The wiring is correct. This plan adds polish (toast notifications, better empty states) and fixes one cache invalidation bug where the IntelPanel's separate cache wasn't being invalidated after send.
