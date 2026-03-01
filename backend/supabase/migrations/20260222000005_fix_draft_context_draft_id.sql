-- Fix: Link orphaned draft_context rows to their drafts
-- The draft_context.draft_id FK was never being populated after draft creation
-- This migration backfills the link using the existing draft_context_id FK

-- Link draft_context to drafts using the existing draft_context_id FK
UPDATE draft_context dc
SET draft_id = ed.id
FROM email_drafts ed
WHERE ed.draft_context_id = dc.id
AND dc.draft_id IS NULL;

-- Add index if not exists (should already exist from earlier migration)
CREATE INDEX IF NOT EXISTS idx_draft_context_draft ON draft_context(draft_id);

-- Verify the fix
DO $$
DECLARE
    null_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count
    FROM draft_context
    WHERE draft_id IS NULL AND id IN (
        SELECT draft_context_id FROM email_drafts WHERE draft_context_id IS NOT NULL
    );

    IF null_count > 0 THEN
        RAISE NOTICE 'WARNING: % draft_context rows still have NULL draft_id despite having matching drafts', null_count;
    ELSE
        RAISE NOTICE 'All draft_context rows successfully linked to their drafts';
    END IF;
END $$;
