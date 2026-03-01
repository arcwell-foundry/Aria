-- Add ActionGatekeeper columns to email_drafts
-- auto_approve_at: Timestamp after which MEDIUM-risk drafts are auto-saved to client
-- risk_level: Risk classification from ActionGatekeeper policy

ALTER TABLE email_drafts
    ADD COLUMN IF NOT EXISTS auto_approve_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS risk_level TEXT DEFAULT 'HIGH';

-- Index for the auto-approve background job query
CREATE INDEX IF NOT EXISTS idx_email_drafts_auto_approve
ON email_drafts (auto_approve_at)
WHERE status = 'pending_review' AND auto_approve_at IS NOT NULL;

-- Column comments
COMMENT ON COLUMN email_drafts.auto_approve_at IS 'Timestamp after which a MEDIUM-risk draft auto-saves to email client. NULL = never auto-approve.';
COMMENT ON COLUMN email_drafts.risk_level IS 'Risk level from ActionGatekeeper: MEDIUM, HIGH, or CRITICAL.';
