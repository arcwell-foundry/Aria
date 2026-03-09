# Contact-Centric Communications View Design

**Date:** 2026-03-08
**Status:** Implemented

## Problem Statement

Users had no way to search for "show me all communications with [contact name]" across both drafts AND email log. They needed a unified, contact-centric view that consolidates all interactions with a specific person.

## Solution Overview

Implemented a contact-centric view within the Communications page that merges data from:
- `email_scan_log` - incoming emails FROM a contact
- `email_drafts` - outgoing drafts/sent emails TO a contact

## Implementation

### Backend Endpoint

**Route:** `GET /api/v1/communications/contact-history?email=<contact_email>`

**File:** `backend/src/api/routes/communications.py`

**Response:**
```json
{
  "contact_email": "rabi@example.com",
  "contact_name": "Rabi",
  "entries": [
    {
      "type": "received",
      "timestamp": "2026-03-08T10:00:00Z",
      "subject": "Re: Project update",
      "snippet": "Thanks for the update...",
      "status": null,
      "email_id": "...",
      "draft_id": null,
      "category": "NEEDS_REPLY",
      "urgency": "NORMAL"
    },
    {
      "type": "sent",
      "timestamp": "2026-03-07T15:00:00Z",
      "subject": "Project update",
      "snippet": "Here's the latest...",
      "status": "sent",
      "draft_id": "..."
    }
  ],
  "total_count": 15,
  "received_count": 10,
  "sent_count": 3,
  "draft_count": 2
}
```

### Frontend Components

**API Client:** `frontend/src/api/communications.ts`
- `fetchContactHistory(email, limit)` - fetches merged timeline

**ContactHistoryView:** `frontend/src/components/communications/ContactHistoryView.tsx`
- Shows unified timeline with:
  - Contact header with name and email
  - Stats bar (received/sent/pending counts)
  - Chronologically sorted timeline entries
  - Clickable drafts link to DraftDetailPage
  - Back navigation to Communications page

**Integration in CommunicationsPage:**
- Added `selectedContactEmail` state
- ContactHistoryView rendered when contact selected
- Recipient names in DraftsList are clickable (triggers contact view)
- Sender names in EmailDecisionsLog are clickable (triggers contact view)

## Entry Types

| Type | Label | Color | Description |
|------|-------|-------|-------------|
| `received` | Received | text-secondary | Incoming email from contact |
| `draft` | Draft | accent | Pending draft to contact |
| `sent` | Sent | success | Sent email to contact |
| `dismissed` | Dismissed | text-secondary | Dismissed draft |

## User Flow

1. User navigates to Communications page
2. User sees drafts or email log
3. User clicks on a contact name (recipient in Drafts, sender in Email Log)
4. ContactHistoryView opens showing all communications with that contact
5. User can click on a draft to view details
6. User clicks "Back to Communications" to return

## Technical Notes

- Uses `ilike` for case-insensitive email matching
- Merges and sorts by timestamp descending
- Snippets are auto-generated from email body (HTML stripped, truncated to 150 chars)
- Respects RLS policies (user isolation)
