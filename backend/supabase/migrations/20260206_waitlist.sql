-- Migration: Create waitlist table for non-life-sciences companies
-- User Story: US-902 Company Discovery & Life Sciences Gate
--
-- Stores companies that fail the life sciences gate check for future
-- notification when ARIA expands to new verticals.

CREATE TABLE IF NOT EXISTS waitlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL,
    company_name TEXT,
    website TEXT,
    gate_reasoning TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(email)
);

-- Enable RLS
ALTER TABLE waitlist ENABLE ROW LEVEL SECURITY;

-- Create index on email for quick lookups
CREATE INDEX IF NOT EXISTS idx_waitlist_email ON waitlist(email);

-- Create index on created_at for sorting
CREATE INDEX IF NOT EXISTS idx_waitlist_created_at ON waitlist(created_at DESC);

-- RLS Policy: Allow service role full access (used by backend)
-- This table is system-managed, not user-facing
CREATE POLICY "service_full_access" ON waitlist
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- RLS Policy: No direct user access (this is an internal table)
CREATE POLICY "no_user_access" ON waitlist
    FOR ALL TO authenticated
    USING (false)
    WITH CHECK (false);

-- Add comment
COMMENT ON TABLE waitlist IS 'Waitlist for companies outside life sciences vertical';
COMMENT ON COLUMN waitlist.gate_reasoning IS 'LLM reasoning for why company was classified as non-life-sciences';
