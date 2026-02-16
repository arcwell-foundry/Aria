-- Migration: Strategic Plans (US-802 Constructive Pushback / Strategic Planning)
-- Creates table for strategic plans with CRUD and scenario analysis
-- NOTE: Table already exists in live database (created via Supabase MCP).
-- This migration file documents the schema for migration history consistency.

CREATE TABLE IF NOT EXISTS strategic_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    title TEXT NOT NULL,
    plan_type TEXT NOT NULL DEFAULT 'quarterly',
    period_label TEXT,
    objectives JSONB DEFAULT '[]',
    key_results JSONB DEFAULT '[]',
    risks JSONB DEFAULT '[]',
    assumptions JSONB DEFAULT '[]',
    scenarios JSONB DEFAULT '[]',
    progress_score REAL DEFAULT 0.0,
    aria_assessment TEXT,
    aria_concerns JSONB DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_strategic_plans_user_status
    ON strategic_plans (user_id, status);

CREATE INDEX IF NOT EXISTS idx_strategic_plans_user_created
    ON strategic_plans (user_id, created_at DESC);

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_strategic_plans_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_strategic_plans_updated_at
    BEFORE UPDATE ON strategic_plans
    FOR EACH ROW
    EXECUTE FUNCTION update_strategic_plans_updated_at();

-- Enable Row Level Security
ALTER TABLE strategic_plans ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view their own strategic plans"
    ON strategic_plans FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own strategic plans"
    ON strategic_plans FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own strategic plans"
    ON strategic_plans FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own strategic plans"
    ON strategic_plans FOR DELETE
    USING (auth.uid() = user_id);

-- Service role policy for backend operations
CREATE POLICY "Service role full access on strategic_plans"
    ON strategic_plans FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
