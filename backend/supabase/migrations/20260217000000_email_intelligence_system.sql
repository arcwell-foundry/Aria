-- Email Intelligence System Migration
-- Creates all tables needed for the email intelligence system
-- Designed to be idempotent - safe to run multiple times

-- ============================================================================
-- Part 1: Create email_scan_log table
-- ============================================================================

CREATE TABLE IF NOT EXISTS email_scan_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    email_id TEXT NOT NULL,
    thread_id TEXT,
    sender_email TEXT NOT NULL,
    sender_name TEXT,
    subject TEXT,
    snippet TEXT,
    category TEXT NOT NULL CHECK (category IN ('NEEDS_REPLY', 'FYI', 'SKIP')),
    urgency TEXT NOT NULL DEFAULT 'NORMAL' CHECK (urgency IN ('URGENT', 'NORMAL', 'LOW')),
    needs_draft BOOLEAN NOT NULL DEFAULT false,
    reason TEXT NOT NULL DEFAULT '',
    confidence FLOAT DEFAULT 0.8,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for email_scan_log
CREATE INDEX IF NOT EXISTS idx_email_scan_log_user_id ON email_scan_log(user_id);
CREATE INDEX IF NOT EXISTS idx_email_scan_log_user_date ON email_scan_log(user_id, scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_scan_log_category ON email_scan_log(user_id, category) WHERE needs_draft = true;
CREATE INDEX IF NOT EXISTS idx_email_scan_log_email_id ON email_scan_log(email_id);

-- Enable RLS on email_scan_log
ALTER TABLE email_scan_log ENABLE ROW LEVEL SECURITY;

-- RLS Policies for email_scan_log
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'email_scan_log' AND policyname = 'email_scan_log_select'
    ) THEN
        CREATE POLICY email_scan_log_select ON email_scan_log FOR SELECT USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'email_scan_log' AND policyname = 'email_scan_log_insert'
    ) THEN
        CREATE POLICY email_scan_log_insert ON email_scan_log FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'email_scan_log' AND policyname = 'email_scan_log_update'
    ) THEN
        CREATE POLICY email_scan_log_update ON email_scan_log FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'email_scan_log' AND policyname = 'email_scan_log_delete'
    ) THEN
        CREATE POLICY email_scan_log_delete ON email_scan_log FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

COMMENT ON TABLE email_scan_log IS 'Audit log of every email categorization decision by ARIA EmailAnalyzer';

-- ============================================================================
-- Part 2: Create draft_context table
-- ============================================================================

CREATE TABLE IF NOT EXISTS draft_context (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    draft_id UUID REFERENCES email_drafts(id) ON DELETE CASCADE,
    email_id TEXT,
    thread_id TEXT,
    sender_email TEXT,
    thread_summary TEXT,
    recipient_research TEXT,
    company_context TEXT,
    relationship_history TEXT,
    calendar_context TEXT,
    crm_context TEXT,
    corporate_memory_used TEXT[],
    exa_sources_used TEXT[],
    aria_notes TEXT NOT NULL DEFAULT '',
    confidence_level TEXT NOT NULL DEFAULT 'MEDIUM' CHECK (confidence_level IN ('HIGH', 'MEDIUM', 'LOW')),
    confidence_reason TEXT NOT NULL DEFAULT '',
    style_match_score FLOAT,
    recipient_tone_profile JSONB,
    -- JSONB columns for flexible nested context (backward compatibility)
    thread_context JSONB DEFAULT '{}'::jsonb,
    recipient_style JSONB DEFAULT '{}'::jsonb,
    relationship_context JSONB DEFAULT '{}'::jsonb,
    corporate_memory JSONB DEFAULT '{}'::jsonb,
    sources_used TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for draft_context
CREATE INDEX IF NOT EXISTS idx_draft_context_user_id ON draft_context(user_id);
CREATE INDEX IF NOT EXISTS idx_draft_context_draft ON draft_context(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_context_thread_id ON draft_context(thread_id);
CREATE INDEX IF NOT EXISTS idx_draft_context_sender_email ON draft_context(sender_email);
CREATE INDEX IF NOT EXISTS idx_draft_context_created_at ON draft_context(created_at DESC);

-- Enable RLS on draft_context
ALTER TABLE draft_context ENABLE ROW LEVEL SECURITY;

-- RLS Policies for draft_context
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'draft_context' AND policyname = 'draft_context_select'
    ) THEN
        CREATE POLICY draft_context_select ON draft_context FOR SELECT USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'draft_context' AND policyname = 'draft_context_insert'
    ) THEN
        CREATE POLICY draft_context_insert ON draft_context FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'draft_context' AND policyname = 'draft_context_update'
    ) THEN
        CREATE POLICY draft_context_update ON draft_context FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'draft_context' AND policyname = 'draft_context_delete'
    ) THEN
        CREATE POLICY draft_context_delete ON draft_context FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

COMMENT ON TABLE draft_context IS 'Complete context packages for email reply drafting';

-- ============================================================================
-- Part 3: Create recipient_writing_profiles table
-- ============================================================================

CREATE TABLE IF NOT EXISTS recipient_writing_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    recipient_email TEXT NOT NULL,
    recipient_name TEXT,
    relationship_type TEXT DEFAULT 'unknown'
        CHECK (relationship_type IN ('internal_team', 'external_executive', 'external_peer', 'vendor', 'new_contact', 'unknown')),
    formality_level FLOAT DEFAULT 0.5,
    average_message_length INT DEFAULT 0,
    greeting_style TEXT DEFAULT '',
    signoff_style TEXT DEFAULT '',
    tone TEXT DEFAULT 'balanced'
        CHECK (tone IN ('warm', 'direct', 'formal', 'casual', 'balanced')),
    uses_emoji BOOLEAN DEFAULT false,
    email_count INT DEFAULT 0,
    last_email_date TIMESTAMPTZ,
    style_data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, recipient_email)
);

-- Indexes for recipient_writing_profiles
CREATE INDEX IF NOT EXISTS idx_recipient_writing_profiles_user ON recipient_writing_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_recipient_writing_profiles_lookup ON recipient_writing_profiles(user_id, recipient_email);

-- Enable RLS on recipient_writing_profiles
ALTER TABLE recipient_writing_profiles ENABLE ROW LEVEL SECURITY;

-- RLS Policies for recipient_writing_profiles
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'recipient_writing_profiles' AND policyname = 'recipient_writing_profiles_select'
    ) THEN
        CREATE POLICY recipient_writing_profiles_select ON recipient_writing_profiles FOR SELECT USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'recipient_writing_profiles' AND policyname = 'recipient_writing_profiles_insert'
    ) THEN
        CREATE POLICY recipient_writing_profiles_insert ON recipient_writing_profiles FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'recipient_writing_profiles' AND policyname = 'recipient_writing_profiles_update'
    ) THEN
        CREATE POLICY recipient_writing_profiles_update ON recipient_writing_profiles FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'recipient_writing_profiles' AND policyname = 'recipient_writing_profiles_delete'
    ) THEN
        CREATE POLICY recipient_writing_profiles_delete ON recipient_writing_profiles FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

-- Create trigger for updated_at
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_recipient_writing_profiles_updated_at') THEN
        CREATE TRIGGER update_recipient_writing_profiles_updated_at
            BEFORE UPDATE ON recipient_writing_profiles
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

COMMENT ON TABLE recipient_writing_profiles IS 'Per-recipient writing style profiles for Digital Twin';

-- ============================================================================
-- Part 4: Create email_processing_runs table
-- ============================================================================

CREATE TABLE IF NOT EXISTS email_processing_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    run_type TEXT NOT NULL DEFAULT 'manual' CHECK (run_type IN ('scheduled', 'manual', 'briefing')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    emails_scanned INT DEFAULT 0,
    emails_needs_reply INT DEFAULT 0,
    emails_fyi INT DEFAULT 0,
    emails_skipped INT DEFAULT 0,
    drafts_generated INT DEFAULT 0,
    drafts_saved_to_client INT DEFAULT 0,
    errors TEXT[],
    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'completed', 'partial_failure', 'failed')),
    error_message TEXT,
    processing_time_ms INT,
    sources_used TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for email_processing_runs
CREATE INDEX IF NOT EXISTS idx_email_processing_runs_user_id ON email_processing_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_email_runs_user ON email_processing_runs(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_processing_runs_status ON email_processing_runs(status);

-- Enable RLS on email_processing_runs
ALTER TABLE email_processing_runs ENABLE ROW LEVEL SECURITY;

-- RLS Policies for email_processing_runs
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'email_processing_runs' AND policyname = 'email_processing_runs_select'
    ) THEN
        CREATE POLICY email_processing_runs_select ON email_processing_runs FOR SELECT USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'email_processing_runs' AND policyname = 'email_processing_runs_insert'
    ) THEN
        CREATE POLICY email_processing_runs_insert ON email_processing_runs FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'email_processing_runs' AND policyname = 'email_processing_runs_update'
    ) THEN
        CREATE POLICY email_processing_runs_update ON email_processing_runs FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'email_processing_runs' AND policyname = 'email_processing_runs_delete'
    ) THEN
        CREATE POLICY email_processing_runs_delete ON email_processing_runs FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

COMMENT ON TABLE email_processing_runs IS 'Tracks autonomous inbox processing runs';

-- ============================================================================
-- Part 5: Add columns to email_drafts table
-- ============================================================================

-- Add new columns for email intelligence features
ALTER TABLE email_drafts
    ADD COLUMN IF NOT EXISTS thread_id TEXT,
    ADD COLUMN IF NOT EXISTS in_reply_to TEXT,
    ADD COLUMN IF NOT EXISTS original_email_id TEXT,
    ADD COLUMN IF NOT EXISTS confidence_level FLOAT CHECK (confidence_level >= 0 AND confidence_level <= 1),
    ADD COLUMN IF NOT EXISTS aria_notes TEXT,
    ADD COLUMN IF NOT EXISTS draft_context_id UUID REFERENCES draft_context(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS saved_to_client BOOLEAN DEFAULT false,
    ADD COLUMN IF NOT EXISTS saved_to_client_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS email_client TEXT,
    ADD COLUMN IF NOT EXISTS scan_log_id UUID REFERENCES email_scan_log(id),
    ADD COLUMN IF NOT EXISTS processing_run_id UUID REFERENCES email_processing_runs(id);

-- Add 'reply' to email_purpose enum
DO $$ BEGIN
    ALTER TYPE email_purpose ADD VALUE IF NOT EXISTS 'reply';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Indexes for email_drafts new columns
CREATE INDEX IF NOT EXISTS idx_email_drafts_thread_id ON email_drafts(thread_id);
CREATE INDEX IF NOT EXISTS idx_email_drafts_original_email_id ON email_drafts(original_email_id);
CREATE INDEX IF NOT EXISTS idx_email_drafts_confidence_level ON email_drafts(confidence_level);
CREATE INDEX IF NOT EXISTS idx_email_drafts_scan_log ON email_drafts(scan_log_id);
CREATE INDEX IF NOT EXISTS idx_email_drafts_processing_run ON email_drafts(processing_run_id);

-- Comments for new columns
COMMENT ON COLUMN email_drafts.thread_id IS 'Email thread ID for grouping related emails';
COMMENT ON COLUMN email_drafts.in_reply_to IS 'Message-ID this email is replying to (for threading)';
COMMENT ON COLUMN email_drafts.original_email_id IS 'ID of the original email this is a reply to (from Composio)';
COMMENT ON COLUMN email_drafts.confidence_level IS 'ARIA confidence score (0.0-1.0) for the draft quality';
COMMENT ON COLUMN email_drafts.aria_notes IS 'Internal notes explaining ARIA reasoning and recommendations';
COMMENT ON COLUMN email_drafts.draft_context_id IS 'Reference to the full context used for generating this draft';
COMMENT ON COLUMN email_drafts.saved_to_client IS 'Whether draft was saved to user email client (Gmail/Outlook)';
COMMENT ON COLUMN email_drafts.saved_to_client_at IS 'Timestamp when draft was saved to email client';
COMMENT ON COLUMN email_drafts.email_client IS 'Which email client the draft was saved to (gmail/outlook)';
COMMENT ON COLUMN email_drafts.scan_log_id IS 'Reference to the scan log entry that triggered this draft';
COMMENT ON COLUMN email_drafts.processing_run_id IS 'Reference to the processing run that created this draft';

-- ============================================================================
-- Part 6: Verification
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Email Intelligence System Migration Complete';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Tables created:';
    RAISE NOTICE '  - email_scan_log (with RLS)';
    RAISE NOTICE '  - draft_context (with RLS)';
    RAISE NOTICE '  - recipient_writing_profiles (with RLS)';
    RAISE NOTICE '  - email_processing_runs (with RLS)';
    RAISE NOTICE '';
    RAISE NOTICE 'Tables updated:';
    RAISE NOTICE '  - email_drafts (added threading, client sync, and linking columns)';
END $$;
