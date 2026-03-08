# Placeholder Drafts — Implementation Summary

**Goal:** Fix competitive displacement drafts showing "[Contact Name]" and "pending@placeholder.com" in the Drafts list. Fix both presentation layer and underlying pipeline.

**Architecture:** Two-layer fix — frontend presentation for immediate user feedback; backend contact resolution for systemic long-term solution.

**Tech Stack:** React, TypeScript, Python FastAPI, Supabase

---

## Layer 1 — Frontend Presentation

### Files Modified
- `frontend/src/utils/isPlaceholderDraft.ts` (new) — Detection utility
- `frontend/src/utils/__tests__/isPlaceholderDraft.test.ts` (new) — 26 tests
- `frontend/src/components/pages/CommunicationsPage.tsx` — List rendering
- `frontend/src/components/pages/DraftDetailPage.tsx` — Detail view

### Detection Logic (`isPlaceholderDraft`)
A draft is a placeholder if any of these are true:
1. `status === 'pending_review'`
2. `recipient_email` contains 'placeholder' (case-insensitive)
3. `recipient_name` contains '[' (template variable marker)

### List Rendering (CommunicationsPage)
- Placeholder drafts show **"Outreach Opportunity"** instead of "[Contact Name]"
- Italic font + secondary color to visually distinguish from real drafts
- Sorted **after** real drafts in the list
- All badges preserved (confidence tier, draft type, status)
- Body preview preserved
- Click navigation to draft detail preserved

---

## Layer 2 — Backend Pipeline

### Files Modified
- `backend/src/services/contact_resolution_service.py` (new) — Contact resolution service
- `backend/src/intelligence/action_executor.py` — Integrated contact resolution

### Contact Resolution Cascade (`ContactResolutionService`)
Before creating any outreach draft, the system attempts to resolve real contacts:
1. **discovered_leads** — Contacts from lead discovery (ILIKE company name match)
2. **email_scan_log** — Senders at the company domain (domain pattern extraction)
3. **memory_semantic** — Future enhancement (TODO)

Returns max 3 contacts, deduplicated by email.

### Draft Creation Flow
- **Contacts resolved:** Creates one draft per contact with `status='draft'` (ready for review)
- **No contacts found:** Creates one placeholder draft with `status='pending_review'`, `recipient_email='pending@placeholder.com'`, `recipient_name='[Contact Name]'`
- Applies to ALL outreach types: `competitive_displacement`, `conference_outreach`, `clinical_trial_outreach`
- Logs which path was taken for debugging
