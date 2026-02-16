-- Migration: Companion Emotional Responses (US-804 Emotional Intelligence)
-- Creates table for logging emotional response interactions
-- NOTE: Table already exists in live database (created via Supabase MCP).
-- This migration file documents the schema for migration history consistency.

CREATE TABLE IF NOT EXISTS companion_emotional_responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    emotional_context TEXT NOT NULL,
    trigger_message TEXT,
    support_type TEXT NOT NULL,
    response_given TEXT NOT NULL,
    user_reaction TEXT,
    conversation_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_emotional_responses_user_created
    ON companion_emotional_responses (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_emotional_responses_context
    ON companion_emotional_responses (user_id, emotional_context);

-- Enable Row Level Security
ALTER TABLE companion_emotional_responses ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view their own emotional responses"
    ON companion_emotional_responses FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own emotional responses"
    ON companion_emotional_responses FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own emotional responses"
    ON companion_emotional_responses FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Service role policy for backend operations
CREATE POLICY "Service role full access on companion_emotional_responses"
    ON companion_emotional_responses FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');
