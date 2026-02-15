-- ============================================================
-- draft_context
-- Stores complete context packages for email reply drafting.
-- Enables audit trail and context reuse for follow-ups.
-- ============================================================

CREATE TABLE IF NOT EXISTS draft_context (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    email_id            TEXT NOT NULL,
    thread_id           TEXT NOT NULL,
    sender_email        TEXT NOT NULL,
    subject             TEXT,

    -- JSONB columns for flexible nested context
    thread_context      JSONB DEFAULT '{}'::jsonb,
    recipient_research  JSONB DEFAULT '{}'::jsonb,
    recipient_style     JSONB DEFAULT '{}'::jsonb,
    relationship_history JSONB DEFAULT '{}'::jsonb,
    corporate_memory    JSONB DEFAULT '{}'::jsonb,
    calendar_context    JSONB DEFAULT '{}'::jsonb,
    crm_context         JSONB DEFAULT '{}'::jsonb,

    -- Source tracking
    sources_used        TEXT[] DEFAULT '{}',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE draft_context ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only see their own contexts
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'draft_context'
        AND policyname = 'draft_context_user_own'
    ) THEN
        CREATE POLICY draft_context_user_own
            ON draft_context FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

-- RLS Policy: Service role full access
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'draft_context'
        AND policyname = 'draft_context_service_role'
    ) THEN
        CREATE POLICY draft_context_service_role
            ON draft_context FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_draft_context_user_id ON draft_context(user_id);
CREATE INDEX IF NOT EXISTS idx_draft_context_thread_id ON draft_context(thread_id);
CREATE INDEX IF NOT EXISTS idx_draft_context_sender_email ON draft_context(sender_email);
CREATE INDEX IF NOT EXISTS idx_draft_context_created_at ON draft_context(created_at DESC);

-- Table comment
COMMENT ON TABLE draft_context IS 'Complete context packages for email reply drafting. Includes thread history, recipient research, relationship data, calendar and CRM context.';
