-- Migration: Create decks table for Gamma AI-powered presentations
-- Created: 2026-03-09

-- Create decks table
CREATE TABLE IF NOT EXISTS decks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    meeting_id UUID REFERENCES calendar_events(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'generating' CHECK (status IN ('generating', 'completed', 'failed')),
    source TEXT NOT NULL DEFAULT 'adhoc' CHECK (source IN ('meeting_context', 'adhoc')),
    gamma_id TEXT,
    gamma_url TEXT,
    credits_used INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_decks_user_id ON decks(user_id);
CREATE INDEX IF NOT EXISTS idx_decks_meeting_id ON decks(meeting_id);
CREATE INDEX IF NOT EXISTS idx_decks_status ON decks(status);
CREATE INDEX IF NOT EXISTS idx_decks_created_at ON decks(created_at DESC);

-- Enable RLS
ALTER TABLE decks ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only see their own decks
CREATE POLICY "Users can view their own decks" ON decks
    FOR SELECT USING (auth.uid()::text = user_id::text);

-- RLS Policy: Service role has full access
CREATE POLICY "Service role has full access to decks" ON decks
    FOR ALL USING (auth.role() = 'service_role');

-- Add comment
COMMENT ON TABLE decks IS 'AI-powered presentation decks created via Gamma API';
COMMENT ON COLUMN decks.gamma_id IS 'Gamma''s internal presentation ID';
COMMENT ON COLUMN decks.gamma_url IS 'Public URL to view/edit the presentation';
COMMENT ON COLUMN decks.credits_used IS 'Gamma API credits consumed for this generation';
