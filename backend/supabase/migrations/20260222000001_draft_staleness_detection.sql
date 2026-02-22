-- Draft Staleness Detection Migration
-- Adds columns to track when drafts become stale due to thread evolution
-- A draft is stale if the thread has new messages since it was created

-- Add staleness tracking columns to email_drafts
ALTER TABLE email_drafts
    ADD COLUMN IF NOT EXISTS is_stale BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS stale_reason TEXT;

-- Create index for efficient stale draft queries
CREATE INDEX IF NOT EXISTS idx_email_drafts_stale
    ON email_drafts(user_id, is_stale)
    WHERE is_stale = TRUE AND status = 'draft';

-- Add comments
COMMENT ON COLUMN email_drafts.is_stale IS 'Whether the draft is stale (thread evolved after draft creation)';
COMMENT ON COLUMN email_drafts.stale_reason IS 'Human-readable explanation of why the draft is stale';

-- Verification notice
DO $$
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Draft Staleness Detection Migration Complete';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Columns added:';
    RAISE NOTICE '  - is_stale (BOOLEAN, default FALSE)';
    RAISE NOTICE '  - stale_reason (TEXT)';
    RAISE NOTICE '';
    RAISE NOTICE 'Index created:';
    RAISE NOTICE '  - idx_email_drafts_stale';
END $$;
