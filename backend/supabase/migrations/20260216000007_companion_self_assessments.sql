-- Migration: Companion Self-Assessments (US-806 Self-Reflection & Self-Correction)
-- Creates table for periodic self-assessment reports
-- NOTE: Table already exists in live database (created via Supabase MCP).
-- This migration file documents the schema for migration history consistency.

CREATE TABLE IF NOT EXISTS companion_self_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    assessment_type TEXT NOT NULL DEFAULT 'weekly',
    overall_score REAL DEFAULT 0.5,
    strengths JSONB DEFAULT '[]',
    weaknesses JSONB DEFAULT '[]',
    mistakes_acknowledged JSONB DEFAULT '[]',
    improvement_plan JSONB DEFAULT '[]',
    user_feedback_summary JSONB DEFAULT '{}',
    trend TEXT DEFAULT 'stable',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_self_assessments_user_created
    ON companion_self_assessments (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_self_assessments_user_period
    ON companion_self_assessments (user_id, period_start, period_end);

-- Enable Row Level Security
ALTER TABLE companion_self_assessments ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view their own self assessments"
    ON companion_self_assessments FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own self assessments"
    ON companion_self_assessments FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own self assessments"
    ON companion_self_assessments FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Service role policy for backend operations
CREATE POLICY "Service role full access on companion_self_assessments"
    ON companion_self_assessments FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
