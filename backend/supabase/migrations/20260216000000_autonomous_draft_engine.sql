-- Autonomous Draft Engine Migration
-- Part 1: Add columns to email_drafts for reply drafts
-- Part 2: Create email_processing_runs table for tracking

-- ============================================================================
-- Part 1: Add columns to email_drafts
-- ============================================================================

-- Add new columns for reply draft metadata
ALTER TABLE email_drafts
    ADD COLUMN IF NOT EXISTS original_email_id TEXT,
    ADD COLUMN IF NOT EXISTS thread_id TEXT,
    ADD COLUMN IF NOT EXISTS confidence_level FLOAT
        CHECK (confidence_level >= 0 AND confidence_level <= 1),
    ADD COLUMN IF NOT EXISTS aria_notes TEXT,
    ADD COLUMN IF NOT EXISTS draft_context_id UUID
        REFERENCES draft_context(id) ON DELETE SET NULL;

-- Add 'reply' to email_purpose enum
DO $$ BEGIN
    ALTER TYPE email_purpose ADD VALUE IF NOT EXISTS 'reply';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_email_drafts_thread_id ON email_drafts(thread_id);
CREATE INDEX IF NOT EXISTS idx_email_drafts_original_email_id ON email_drafts(original_email_id);
CREATE INDEX IF NOT EXISTS idx_email_drafts_confidence_level ON email_drafts(confidence_level);

-- Add comments to new columns
COMMENT ON COLUMN email_drafts.original_email_id IS 'ID of the original email this is a reply to (from Composio)';
COMMENT ON COLUMN email_drafts.thread_id IS 'Email thread ID for grouping related emails';
COMMENT ON COLUMN email_drafts.confidence_level IS 'ARIA confidence score (0.0-1.0) for the draft quality';
COMMENT ON COLUMN email_drafts.aria_notes IS 'Internal notes explaining ARIA reasoning and recommendations';
COMMENT ON COLUMN email_drafts.draft_context_id IS 'Reference to the full context used for generating this draft';

-- ============================================================================
-- Part 2: Create email_processing_runs table
-- ============================================================================

CREATE TABLE IF NOT EXISTS email_processing_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    emails_scanned INTEGER DEFAULT 0,
    emails_needing_reply INTEGER DEFAULT 0,
    drafts_generated INTEGER DEFAULT 0,
    drafts_failed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'partial_failure', 'failed')),
    error_message TEXT,
    processing_time_ms INTEGER,
    sources_used TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Add table comment
COMMENT ON TABLE email_processing_runs IS 'Tracks autonomous inbox processing runs - each time ARIA scans the inbox and generates reply drafts';

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_email_processing_runs_user_id ON email_processing_runs(user_id);
CREATE INDEX IF NOT EXISTS idx_email_processing_runs_status ON email_processing_runs(status);
CREATE INDEX IF NOT EXISTS idx_email_processing_runs_started_at ON email_processing_runs(started_at DESC);

-- Enable Row Level Security
ALTER TABLE email_processing_runs ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user isolation
CREATE POLICY "Users can view their own processing runs" ON email_processing_runs
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create their own processing runs" ON email_processing_runs
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own processing runs" ON email_processing_runs
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own processing runs" ON email_processing_runs
    FOR DELETE USING (auth.uid() = user_id);
