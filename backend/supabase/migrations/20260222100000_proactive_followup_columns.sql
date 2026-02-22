-- Add metadata JSONB to prospective_memories for rich context on commitments
-- (sender_email, sender_name, who, thread_id, email_id, source).
ALTER TABLE prospective_memories
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_prospective_memories_metadata
    ON prospective_memories USING gin (metadata);

-- Add draft_type and source_commitment_id to email_drafts
-- so proactive follow-up drafts are distinguishable from regular reply drafts.
ALTER TABLE email_drafts
    ADD COLUMN IF NOT EXISTS draft_type TEXT DEFAULT 'reply',
    ADD COLUMN IF NOT EXISTS source_commitment_id UUID;

CREATE INDEX IF NOT EXISTS idx_email_drafts_draft_type
    ON email_drafts (draft_type)
    WHERE draft_type != 'reply';

CREATE INDEX IF NOT EXISTS idx_email_drafts_source_commitment_id
    ON email_drafts (source_commitment_id)
    WHERE source_commitment_id IS NOT NULL;
