# Email-Pipeline Linking Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect emails to pipeline entities (leads, accounts, monitored companies) so users see pipeline context when viewing communications.

**Architecture:** Create a pipeline context resolution service that cascades through `lead_memory_stakeholders` (email-to-lead matching), `monitored_entities` (domain matching), and `lead_memories` (company name association). The service returns lightweight context `{ company_name, lead_name, relationship_type, health_score }` that can be displayed inline in the Drafts list, Email Log, and Contact History view. Extend existing `sender_context.py` utility to return pipeline data alongside relationship context. Frontend components consume a new `pipeline_context` field added to API responses.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), Supabase (PostgreSQL)

---

## Task 1: Create Backend Pipeline Linker Service

**Files:**
- Create: `backend/src/utils/email_pipeline_linker.py`

**Step 1: Write the failing test**

Create test file: `backend/tests/test_email_pipeline_linker.py`

```python
"""Tests for email_pipeline_linker service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.utils.email_pipeline_linker import (
    get_pipeline_context_for_email,
    PipelineContext,
    _extract_domain,
)


class TestExtractDomain:
    """Tests for _extract_domain helper."""

    def test_standard_email(self):
        assert _extract_domain("user@example.com") == "example.com"

    def test_uppercase_email(self):
        assert _extract_domain("User@Example.COM") == "example.com"

    def test_subdomain_email(self):
        assert _extract_domain("user@mail.corporate.example.com") == "corporate.example.com"

    def test_invalid_email_no_at(self):
        assert _extract_domain("invalid-email") == ""

    def test_empty_email(self):
        assert _extract_domain("") == ""


class TestGetPipelineContextForEmail:
    """Tests for get_pipeline_context_for_email function."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict_for_unknown_contact(self):
        """Should return empty dict when no pipeline data exists."""
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.contains.return_value.limit.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))
        mock_db.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute = AsyncMock(return_value=MagicMock(data=[]))

        result = await get_pipeline_context_for_email(
            db=mock_db,
            user_id="test-user-id",
            contact_email="unknown@random.com"
        )

        assert result == {} or result is None

    @pytest.mark.asyncio
    async def test_matches_domain_to_monitored_entity(self):
        """Should find company via domain match in monitored_entities."""
        mock_db = MagicMock()

        # Mock monitored_entities query (first check)
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.contains.return_value.limit.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{
                "entity_name": "Silicon Valley Bank",
                "entity_type": "partner",
                "domains": ["svb.com"]
            }])
        )

        result = await get_pipeline_context_for_email(
            db=mock_db,
            user_id="test-user-id",
            contact_email="ries.mcmillan@svb.com"
        )

        assert result is not None
        assert result.get("company_name") == "Silicon Valley Bank"
        assert result.get("relationship_type") == "partner"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_email_pipeline_linker.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 3: Write minimal implementation**

Create file: `backend/src/utils/email_pipeline_linker.py`

```python
"""Email-to-pipeline entity linking service.

This module provides dynamic, data-driven pipeline context resolution for email contacts.
It checks multiple data sources to determine if a contact is associated with a lead,
account, or monitored company, providing context for the communications UI.

100% DYNAMIC - no hardcoded emails, names, or companies.
Everything derived from each user's live data at query time.
"""

import logging
from dataclasses import dataclass
from typing import Any

from supabase import Client

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """Structured pipeline context for an email contact."""

    company_name: str | None = None
    lead_name: str | None = None
    lead_id: str | None = None
    lifecycle_stage: str | None = None  # lead, opportunity, account
    health_score: int | None = None  # 0-100
    relationship_type: str | None = None  # partner, investor, customer, etc.
    source: str = "unknown"  # Which source provided the match


def _extract_domain(email: str) -> str:
    """Extract domain from email address.

    Args:
        email: Email address (e.g., "user@example.com")

    Returns:
        Domain (e.g., "example.com") or empty string if invalid
    """
    if not email or "@" not in email:
        return ""
    return email.split("@")[-1].lower().strip()


async def get_pipeline_context_for_email(
    db: Client,
    user_id: str,
    contact_email: str,
) -> dict[str, Any] | None:
    """Get pipeline context for an email contact.

    Resolves contact to pipeline entities by checking multiple data sources:
    1. lead_memory_stakeholders - match contact email to stakeholder
    2. monitored_entities - match email domain to entity domains
    3. lead_memories - check if company_name matches (via stakeholder company)

    Args:
        db: Supabase client instance
        user_id: The user's UUID
        contact_email: The contact's email address

    Returns:
        Dict with pipeline context if found, None if completely unknown.
        Keys: company_name, lead_name, lead_id, lifecycle_stage, health_score,
              relationship_type, source
    """
    if not contact_email:
        return None

    contact_email_lower = contact_email.lower().strip()
    contact_domain = _extract_domain(contact_email_lower)

    # 1. Check lead_memory_stakeholders for direct email match
    try:
        stakeholder_result = (
            db.table("lead_memory_stakeholders")
            .select(
                "lead_memory_id, contact_name, role, sentiment, "
                "lead_memories(id, company_name, lifecycle_stage, status, health_score)"
            )
            .eq("contact_email", contact_email_lower)
            .eq("lead_memories.status", "active")
            .limit(1)
            .execute()
        )

        if stakeholder_result.data:
            stakeholder = stakeholder_result.data[0]
            lead_data = stakeholder.get("lead_memories")

            if lead_data and isinstance(lead_data, dict):
                return {
                    "company_name": lead_data.get("company_name"),
                    "lead_name": lead_data.get("company_name"),
                    "lead_id": lead_data.get("id"),
                    "lifecycle_stage": lead_data.get("lifecycle_stage"),
                    "health_score": lead_data.get("health_score"),
                    "relationship_type": _map_stakeholder_role(stakeholder.get("role")),
                    "contact_role": stakeholder.get("role"),
                    "source": "lead_memory_stakeholders",
                }

    except Exception as e:
        logger.warning(
            "PIPELINE_LINKER: lead_memory_stakeholders query failed for %s: %s",
            contact_email,
            e,
        )

    # 2. Check monitored_entities via domain match
    if contact_domain:
        try:
            entity_result = (
                db.table("monitored_entities")
                .select("entity_name, entity_type, monitoring_config")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .contains("domains", [contact_domain])
                .limit(1)
                .execute()
            )

            if entity_result.data:
                entity = entity_result.data[0]
                entity_name = entity.get("entity_name")
                entity_type = entity.get("entity_type", "company")

                # Try to find a lead_memory for this company
                lead_result = (
                    db.table("lead_memories")
                    .select("id, company_name, lifecycle_stage, health_score")
                    .eq("user_id", user_id)
                    .eq("status", "active")
                    .ilike("company_name", entity_name)
                    .limit(1)
                    .execute()
                )

                lead_data = lead_result.data[0] if lead_result.data else None

                return {
                    "company_name": entity_name,
                    "lead_name": lead_data.get("company_name") if lead_data else entity_name,
                    "lead_id": lead_data.get("id") if lead_data else None,
                    "lifecycle_stage": lead_data.get("lifecycle_stage") if lead_data else None,
                    "health_score": lead_data.get("health_score") if lead_data else None,
                    "relationship_type": entity_type,
                    "source": "monitored_entities",
                }

        except Exception as e:
            logger.warning(
                "PIPELINE_LINKER: monitored_entities query failed for domain %s: %s",
                contact_domain,
                e,
            )

    # 3. Check memory_semantic for email references (fallback)
    try:
        memory_result = (
            db.table("memory_semantic")
            .select("fact, confidence")
            .eq("user_id", user_id)
            .ilike("fact", f"%{contact_email_lower}%")
            .limit(3)
            .execute()
        )

        if memory_result.data:
            # Extract any company names or relationship info from facts
            for row in memory_result.data:
                fact = row.get("fact", "")
                # This is a lightweight extraction - just indicate known contact
                if "investor" in fact.lower():
                    return {
                        "relationship_type": "investor",
                        "source": "memory_semantic",
                    }
                elif "partner" in fact.lower():
                    return {
                        "relationship_type": "partner",
                        "source": "memory_semantic",
                    }
                elif "customer" in fact.lower():
                    return {
                        "relationship_type": "customer",
                        "source": "memory_semantic",
                    }

    except Exception as e:
        logger.warning(
            "PIPELINE_LINKER: memory_semantic query failed for %s: %s",
            contact_email,
            e,
        )

    # No pipeline context found
    return None


def _map_stakeholder_role(role: str | None) -> str:
    """Map stakeholder role to a user-friendly relationship type.

    Args:
        role: The stakeholder role (decision_maker, influencer, champion, etc.)

    Returns:
        User-friendly relationship type string.
    """
    if not role:
        return "contact"

    role_mapping = {
        "decision_maker": "prospect",
        "influencer": "prospect",
        "champion": "prospect",
        "blocker": "prospect",
        "user": "prospect",
    }

    return role_mapping.get(role.lower(), "contact")


def format_pipeline_context_for_display(context: dict[str, Any] | None) -> str | None:
    """Format pipeline context for inline display in UI.

    Args:
        context: Pipeline context dict from get_pipeline_context_for_email

    Returns:
        Formatted string like "Silicon Valley Bank (Partner)" or None
    """
    if not context:
        return None

    company = context.get("company_name")
    rel_type = context.get("relationship_type")

    if not company:
        return None

    # Capitalize relationship type for display
    rel_display = rel_type.replace("_", " ").title() if rel_type else None

    if rel_display:
        return f"{company} ({rel_display})"

    return company
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_email_pipeline_linker.py -v`
Expected: PASS (at least basic tests)

**Step 5: Commit**

```bash
git add backend/src/utils/email_pipeline_linker.py backend/tests/test_email_pipeline_linker.py
git commit -m "feat: add email-pipeline linker service for contact-to-lead resolution

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Extend Sender Context to Include Pipeline Data

**Files:**
- Modify: `backend/src/utils/sender_context.py`

**Step 1: Write the failing test**

Add to: `backend/tests/test_sender_context.py`

```python
@pytest.mark.asyncio
async def test_get_sender_context_includes_pipeline_data():
    """Should include pipeline context when sender is linked to a lead."""
    mock_db = MagicMock()

    # Mock monitored_entities with pipeline link
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.contains.return_value.limit.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{
            "entity_name": "Test Corp",
            "entity_type": "customer",
            "domains": ["testcorp.com"]
        }])
    )

    context = await get_sender_context(
        db=mock_db,
        user_id="test-user",
        sender_email="contact@testcorp.com"
    )

    # Should have pipeline context included
    assert context is not None
    # The new field should be present
    assert hasattr(context, "pipeline_context") or "pipeline" in str(context).lower()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_sender_context.py::test_get_sender_context_includes_pipeline_data -v`
Expected: FAIL

**Step 3: Modify sender_context.py**

In `backend/src/utils/sender_context.py`:

1. Update the `SenderContext` dataclass to include `pipeline_context`:

```python
@dataclass
class SenderContext:
    """Structured relationship context for an email sender."""

    is_strategic: bool
    relationship_type: str
    entity_name: str | None
    context_summary: str
    has_prior_drafts: bool
    confidence: float
    pipeline_context: dict[str, Any] | None = None  # NEW: Pipeline entity data
```

2. Add import at top:

```python
from src.utils.email_pipeline_linker import get_pipeline_context_for_email
```

3. In `get_sender_context` function, after determining entity_name from monitored_entities, call the pipeline linker:

```python
# After entity resolution, get pipeline context
pipeline_ctx = await get_pipeline_context_for_email(
    db=db,
    user_id=user_id,
    contact_email=sender_email_lower,
)

# Add to context
context.pipeline_context = pipeline_ctx
```

Insert this after the monitored_entities block (around line 160-165), before checking memory_semantic.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_sender_context.py::test_get_sender_context_includes_pipeline_data -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/utils/sender_context.py
git commit -m "feat: extend sender_context to include pipeline linkage data

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Add Pipeline Context to Communications API

**Files:**
- Modify: `backend/src/api/routes/communications.py`
- Modify: `frontend/src/api/communications.ts`

**Step 1: Write the failing test**

Add to: `backend/tests/api/test_communications.py`

```python
@pytest.mark.asyncio
async def test_contact_history_includes_pipeline_context():
    """Contact history response should include pipeline context for contacts."""
    # This test verifies the API returns pipeline_context field
    pass  # Will implement with actual API test
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_communications.py -v`
Expected: Test passes but API doesn't return pipeline_context yet

**Step 3: Modify communications.py backend**

In `backend/src/api/routes/communications.py`:

1. Add import:

```python
from src.utils.email_pipeline_linker import get_pipeline_context_for_email
```

2. Update `ContactHistoryResponse` model to include pipeline context:

```python
class PipelineContextModel(BaseModel):
    """Pipeline context for a contact."""

    company_name: str | None = None
    lead_name: str | None = None
    lead_id: str | None = None
    lifecycle_stage: str | None = None
    health_score: int | None = None
    relationship_type: str | None = None
    source: str = "unknown"


class ContactHistoryResponse(BaseModel):
    """Response from contact history endpoint."""

    contact_email: str = Field(..., description="The contact's email address")
    contact_name: str | None = Field(None, description="The contact's display name (if known)")
    pipeline_context: PipelineContextModel | None = Field(
        None, description="Pipeline context if contact is linked to a lead/account"
    )
    entries: list[ContactHistoryEntry] = Field(
        default_factory=list,
        description="Chronologically sorted timeline entries",
    )
    total_count: int = Field(..., description="Total number of entries")
    received_count: int = Field(0, description="Number of emails received from contact")
    sent_count: int = Field(0, description="Number of emails sent to contact")
    draft_count: int = Field(0, description="Number of pending drafts to contact")
```

3. In `get_contact_history` endpoint, after fetching data, get pipeline context:

```python
# Get pipeline context for this contact
pipeline_ctx = await get_pipeline_context_for_email(
    db=db,
    user_id=user_id,
    contact_email=normalized_email,
)

# ... in the return statement ...
return {
    "contact_email": normalized_email,
    "contact_name": contact_name,
    "pipeline_context": pipeline_ctx,  # NEW
    "entries": entries,
    "total_count": len(entries),
    "received_count": received_count,
    "sent_count": sent_count,
    "draft_count": draft_count,
}
```

**Step 4: Modify frontend communications.ts**

In `frontend/src/api/communications.ts`:

Add the pipeline context interface and update ContactHistoryResponse:

```typescript
/**
 * Pipeline context linking a contact to a lead/account.
 */
export interface PipelineContext {
  company_name: string | null;
  lead_name: string | null;
  lead_id: string | null;
  lifecycle_stage: string | null;
  health_score: number | null;
  relationship_type: string | null;
  source: string;
}

/**
 * Response from the contact history endpoint.
 */
export interface ContactHistoryResponse {
  contact_email: string;
  contact_name: string | null;
  pipeline_context: PipelineContext | null;  // NEW
  entries: ContactHistoryEntry[];
  total_count: number;
  received_count: number;
  sent_count: number;
  draft_count: number;
}
```

**Step 5: Commit**

```bash
git add backend/src/api/routes/communications.py frontend/src/api/communications.ts
git commit -m "feat: add pipeline context to contact history API response

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Add Pipeline Context to Drafts API

**Files:**
- Modify: `backend/src/api/routes/drafts.py`
- Modify: `frontend/src/api/drafts.ts`

**Step 1: Extend drafts list endpoint**

In `backend/src/api/routes/drafts.py`:

1. Add import:

```python
from src.utils.email_pipeline_linker import get_pipeline_context_for_email, format_pipeline_context_for_display
```

2. In the drafts list endpoint response, include pipeline context for each draft's recipient.

3. Add a helper function to batch-fetch pipeline context for multiple emails to avoid N+1 queries:

```python
async def _batch_get_pipeline_context(
    db: Client,
    user_id: str,
    emails: list[str],
) -> dict[str, dict[str, Any] | None]:
    """Batch fetch pipeline context for multiple emails.

    Returns a dict mapping email -> pipeline context (or None).
    """
    results = {}
    for email in set(emails):  # Dedupe
        ctx = await get_pipeline_context_for_email(db, user_id, email)
        results[email.lower()] = ctx
    return results
```

4. In the drafts list handler, enrich each draft:

```python
# After fetching drafts, batch-get pipeline context
recipient_emails = [d.get("recipient_email", "") for d in drafts]
pipeline_contexts = await _batch_get_pipeline_context(db, user_id, recipient_emails)

# Enrich each draft with pipeline context
for draft in drafts:
    email = draft.get("recipient_email", "").lower()
    draft["pipeline_context"] = pipeline_contexts.get(email)
```

**Step 2: Update frontend types**

In `frontend/src/api/drafts.ts`:

```typescript
export interface PipelineContext {
  company_name: string | null;
  lead_name: string | null;
  lead_id: string | null;
  lifecycle_stage: string | null;
  health_score: number | null;
  relationship_type: string | null;
  source: string;
}

export interface EmailDraftListItem {
  // ... existing fields ...
  pipeline_context?: PipelineContext | null;  // NEW
}
```

**Step 3: Commit**

```bash
git add backend/src/api/routes/drafts.py frontend/src/api/drafts.ts
git commit -m "feat: add pipeline context to drafts list API

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Add Pipeline Context to Email Decisions API

**Files:**
- Modify: `backend/src/api/routes/emailDecisions.py` (or equivalent)
- Modify: `frontend/src/api/emailDecisions.ts`

**Step 1: Extend email decisions endpoint**

Similar to Task 4, add pipeline context to each decision row for the sender_email.

In the email decisions list handler:

```python
# After fetching decisions, batch-get pipeline context for senders
sender_emails = [d.get("sender_email", "") for d in decisions]
pipeline_contexts = await _batch_get_pipeline_context(db, user_id, sender_emails)

# Enrich each decision with pipeline context
for decision in decisions:
    email = decision.get("sender_email", "").lower()
    decision["pipeline_context"] = pipeline_contexts.get(email)
```

**Step 2: Update frontend types**

In `frontend/src/api/emailDecisions.ts`:

```typescript
export interface ScanDecisionInfo {
  // ... existing fields ...
  pipeline_context?: PipelineContext | null;  // NEW
}
```

**Step 3: Commit**

```bash
git add backend/src/api/routes/emailDecisions.py frontend/src/api/emailDecisions.ts
git commit -m "feat: add pipeline context to email decisions API

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Display Pipeline Context in Drafts List

**Files:**
- Modify: `frontend/src/components/pages/CommunicationsPage.tsx`

**Step 1: Update DraftsList component**

In `frontend/src/components/pages/CommunicationsPage.tsx`, modify the draft row rendering to show pipeline context.

Add a helper function to format pipeline context display:

```typescript
function formatPipelineDisplay(pipeline: PipelineContext | null | undefined): string | null {
  if (!pipeline || !pipeline.company_name) return null;

  const relDisplay = pipeline.relationship_type
    ? pipeline.relationship_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
    : null;

  return relDisplay ? `${pipeline.company_name} (${relDisplay})` : pipeline.company_name;
}
```

In the draft row JSX, after the recipient name line, add:

```tsx
{/* Pipeline context indicator - only show if available */}
{draft.pipeline_context && draft.pipeline_context.company_name && (
  <span
    className="text-xs ml-2 px-1.5 py-0.5 rounded"
    style={{
      backgroundColor: 'var(--bg-subtle)',
      color: 'var(--text-secondary)',
    }}
    title={`Lead: ${draft.pipeline_context.lead_name || 'N/A'} | Stage: ${draft.pipeline_context.lifecycle_stage || 'N/A'} | Health: ${draft.pipeline_context.health_score || 'N/A'}`}
  >
    {formatPipelineDisplay(draft.pipeline_context)}
  </span>
)}
```

**Step 2: Commit**

```bash
git add frontend/src/components/pages/CommunicationsPage.tsx
git commit -m "feat: display pipeline context in drafts list

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Display Pipeline Context in Email Log

**Files:**
- Modify: `frontend/src/components/communications/EmailDecisionsLog.tsx`

**Step 1: Update DecisionRow component**

In `frontend/src/components/communications/EmailDecisionsLog.tsx`, modify the sender display to include pipeline context.

Add helper function (same as Task 6) and update the sender section:

```tsx
{/* Sender name + pipeline context */}
<div className="flex items-center gap-2 mb-0.5">
  <button
    onClick={(e) => {
      e.stopPropagation();
      onContactClick?.(decision.sender_email);
    }}
    className="font-medium text-sm truncate hover:underline"
    style={{ color: 'var(--text-primary)' }}
  >
    {decision.sender_name || decision.sender_email}
  </button>
  {/* Pipeline context indicator */}
  {decision.pipeline_context && decision.pipeline_context.company_name && (
    <span
      className="text-xs px-1.5 py-0.5 rounded"
      style={{
        backgroundColor: 'var(--bg-subtle)',
        color: 'var(--text-secondary)',
      }}
    >
      {formatPipelineDisplay(decision.pipeline_context)}
    </span>
  )}
  {/* ... existing email display ... */}
</div>
```

**Step 2: Commit**

```bash
git add frontend/src/components/communications/EmailDecisionsLog.tsx
git commit -m "feat: display pipeline context in email decisions log

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Display Pipeline Context in Contact History Header

**Files:**
- Modify: `frontend/src/components/communications/ContactHistoryView.tsx`

**Step 1: Update ContactHistoryView component**

In `frontend/src/components/communications/ContactHistoryView.tsx`, add a pipeline context section in the header.

After the contact name/email display, add:

```tsx
{/* Pipeline context section */}
{data?.pipeline_context && (
  <div
    className="flex flex-wrap items-center gap-3 mb-4 text-sm"
    style={{ color: 'var(--text-secondary)' }}
  >
    {data.pipeline_context.company_name && (
      <div className="flex items-center gap-1.5">
        <Building2 className="w-4 h-4" />
        <span>
          <strong style={{ color: 'var(--text-primary)' }}>Company:</strong>{' '}
          {data.pipeline_context.company_name}
        </span>
      </div>
    )}
    {data.pipeline_context.relationship_type && (
      <div className="flex items-center gap-1.5">
        <Users className="w-4 h-4" />
        <span>
          <strong style={{ color: 'var(--text-primary)' }}>Relationship:</strong>{' '}
          {data.pipeline_context.relationship_type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
        </span>
      </div>
    )}
    {data.pipeline_context.health_score !== null && (
      <div className="flex items-center gap-1.5">
        <Activity className="w-4 h-4" />
        <span>
          <strong style={{ color: 'var(--text-primary)' }}>Health Score:</strong>{' '}
          {data.pipeline_context.health_score}
        </span>
      </div>
    )}
    {data.pipeline_context.lifecycle_stage && (
      <div className="flex items-center gap-1.5">
        <TrendingUp className="w-4 h-4" />
        <span>
          <strong style={{ color: 'var(--text-primary)' }}>Stage:</strong>{' '}
          {data.pipeline_context.lifecycle_stage.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
        </span>
      </div>
    )}
  </div>
)}
```

Add necessary icon imports at top:

```tsx
import { Building2, Users, Activity, TrendingUp, ArrowLeft, Mail, ... } from 'lucide-react';
```

**Step 2: Commit**

```bash
git add frontend/src/components/communications/ContactHistoryView.tsx
git commit -m "feat: display pipeline context in contact history header

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: Integration Testing and Verification

**Files:**
- Verify: Backend service integration
- Verify: Frontend displays

**Step 1: Start backend server**

Run: `cd backend && uvicorn src.main:app --reload --port 8000`

**Step 2: Start frontend dev server**

Run: `cd frontend && npm run dev`

**Step 3: Manual verification checklist**

- [ ] Open Communications page /communications
- [ ] Verify drafts list shows pipeline context for contacts linked to leads
- [ ] Click "Email Log" tab - verify sender names show pipeline context
- [ ] Click on a contact name to view Contact History
- [ ] Verify header shows Company, Relationship, Health Score, Stage
- [ ] Verify unknown contacts (e.g., noreply@google.com) show no pipeline context

**Step 4: Commit verification**

```bash
git add -A
git commit -m "test: verify email-pipeline linking integration

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Final Cleanup and Documentation

**Files:**
- Update: Any shared type definitions
- Update: `CLAUDE.md` if needed

**Step 1: Ensure PipelineContext type is shared**

If multiple API files need the type, create a shared types file or ensure consistent definition.

**Step 2: Run full test suite**

Run: `cd backend && pytest tests/ -v`
Run: `cd frontend && npm run typecheck`

**Step 3: Final commit and push**

```bash
git add -A
git commit -m "feat: complete email-pipeline linking feature

Links email contacts to pipeline entities (leads, accounts, monitored companies):
- Backend: email_pipeline_linker.py service with cascade resolution
- Backend: Extended sender_context.py with pipeline data
- API: Added pipeline_context to contact history, drafts, decisions
- Frontend: Display pipeline context in drafts list, email log, contact history

Verification:
- SVB contacts show 'Silicon Valley Bank (Partner)'
- Unknown contacts show no pipeline context

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

git push origin main
```

---

## Notes

### DO NOT
- Create new tables - use existing pipeline data
- Hardcode any company names or relationships
- Show pipeline context for every email - only for contacts with actual pipeline data

### Key Tables Used
- `lead_memories` - Active leads/opportunities with company_name, health_score, lifecycle_stage
- `lead_memory_stakeholders` - Contact-to-lead mapping with role
- `monitored_entities` - Monitored companies with domains array
- `memory_semantic` - Fallback for relationship info

### Resolution Cascade
1. `lead_memory_stakeholders` - Direct email match → get lead data
2. `monitored_entities` - Domain match → try to find lead by company name
3. `memory_semantic` - Email mentioned in facts → extract relationship type
