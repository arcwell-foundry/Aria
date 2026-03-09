# Communication Analytics Enhancement Design

 Date: 2026-03-08

## Overview

 Enhancement to the Communication Analysis panel in the Intelligence Panel to provide VPs with response time analytics: their communication velocity at all times.


 ## Current State
 The AnalysisModule currently shows basic metrics:
- Sent Rate % (percentage of drafts sent)
- Style Match % (Learning / Improving / calibrated) - Total drafts count

 These metrics are calculated entirely from draft data and no connection to email scan metrics.

 ## Requirements
 Create backend endpoint `GET /api/v1/communications/analytics` that:
- Response time analytics: Average time between incoming email scan and draft creation for reply drafts
- Contact type response times: Investors, partners, customers, other
- Draft coverage rate: Percentage of NEEDS_REPLY emails that have drafts
- 7-day volume trends: Received, drafted, sent counts per day
- Classification distribution: NEEDS_REPLY/FYI/SKIP counts and percentages
- Graceful degradation: Show contextual messages for insufficient data (no fake numbers)

 ## Database Schemas
 The `email_scan_log` table contains:
- `scanned_at`: timestamp when email was scanned
- `category`: NEEDS_REPLY/FYI/SKIP
- `urgency`: URGENT/NORMAL/LOW
- `sender_email`, `sender_name`: contact info
- `confidence`: classification confidence score

 The `email_drafts` table contains
- `created_at`: draft creation timestamp
- `original_email_id`: links to email_scan_log.email_id
- `status`: draft/sent/dismissed
- `recipient_email`: contact email

            The `monitored_entities` table provides contact type classification:
- `entity_type`: investor/partner/customer/etc.
- `domains`: array of domains for matching

 ## Implementation Plan
            ### Backend (Task #1)
 1. Create Pydantic models in `backend/src/models/communications.py`:
 2. Create service method in `backend/src/services/analytics_service.py`:
 3. Add route handler in `backend/src/api/routes/communications.py`

            ### Frontend (Task #2)
 1. Create API client function in `frontend/src/api/communications.ts`
 2. Create React Query hook in `frontend/src/hooks/useIntelPanelData.ts`
 3. Update AnalysisModule component in `frontend/src/components/shell/intel-modules/AnalysisModule.tsx`

            ### Testing (Task #3)
 1. Run backend tests
 2. Run frontend typecheck
 3. Manual verification of the metrics panel shows correctly
