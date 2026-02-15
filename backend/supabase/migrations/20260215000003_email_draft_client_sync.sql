-- Email client sync fields for email drafts
-- Adds columns to track when drafts are saved to Gmail/Outlook

-- Add email client sync fields
ALTER TABLE email_drafts
ADD COLUMN IF NOT EXISTS client_draft_id TEXT,
ADD COLUMN IF NOT EXISTS client_provider TEXT CHECK (client_provider IN ('gmail', 'outlook')),
ADD COLUMN IF NOT EXISTS saved_to_client_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS in_reply_to TEXT;

-- Index for finding drafts by client ID
CREATE INDEX IF NOT EXISTS idx_email_drafts_client_draft_id
ON email_drafts(client_draft_id)
WHERE client_draft_id IS NOT NULL;

-- Column comments
COMMENT ON COLUMN email_drafts.client_draft_id IS 'ID of draft in Gmail/Outlook';
COMMENT ON COLUMN email_drafts.client_provider IS 'Email client where draft is saved (gmail or outlook)';
COMMENT ON COLUMN email_drafts.saved_to_client_at IS 'Timestamp when saved to client';
COMMENT ON COLUMN email_drafts.in_reply_to IS 'Message-ID of email being replied to (for threading)';
