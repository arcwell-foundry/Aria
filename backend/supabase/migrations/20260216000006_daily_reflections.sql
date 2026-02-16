-- Migration: Daily Reflections (US-806 Self-Reflection & Self-Correction)
-- Creates table for daily self-reflection summaries
-- NOTE: Table already exists in live database (created via Supabase MCP).
-- This migration file documents the schema for migration history consistency.

CREATE TABLE IF NOT EXISTS daily_reflections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    reflection_date DATE NOT NULL,
    total_interactions INTEGER DEFAULT 0,
    positive_outcomes JSONB DEFAULT '[]',
    negative_outcomes JSONB DEFAULT '[]',
    patterns_detected JSONB DEFAULT '[]',
    improvement_opportunities JSONB DEFAULT '[]',
    performance_score REAL DEFAULT 0.5,
    key_learnings JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, reflection_date)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_daily_reflections_user_date
    ON daily_reflections (user_id, reflection_date DESC);

-- Enable Row Level Security
ALTER TABLE daily_reflections ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view their own daily reflections"
    ON daily_reflections FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own daily reflections"
    ON daily_reflections FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own daily reflections"
    ON daily_reflections FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Service role policy for backend operations
CREATE POLICY "Service role full access on daily_reflections"
    ON daily_reflections FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
