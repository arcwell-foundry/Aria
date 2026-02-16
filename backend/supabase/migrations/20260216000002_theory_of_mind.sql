-- Migration: Theory of Mind Module (US-802)
-- Creates tables for mental state inference and behavioral patterns

-- Mental state snapshots
-- Stores inferred mental states for users over time
CREATE TABLE IF NOT EXISTS user_mental_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    stress_level TEXT NOT NULL CHECK (stress_level IN ('relaxed', 'normal', 'elevated', 'high', 'critical')),
    confidence TEXT NOT NULL CHECK (confidence IN ('very_uncertain', 'uncertain', 'neutral', 'confident', 'very_confident')),
    current_focus TEXT,
    emotional_tone TEXT NOT NULL,
    needs_support BOOLEAN DEFAULT FALSE,
    needs_space BOOLEAN DEFAULT FALSE,
    recommended_response_style TEXT NOT NULL,
    inferred_at TIMESTAMPTZ DEFAULT NOW(),
    session_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Behavioral patterns
-- Stores detected patterns in user behavior and mental states
CREATE TABLE IF NOT EXISTS user_state_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    pattern_type TEXT NOT NULL,
    pattern_data JSONB NOT NULL,
    confidence FLOAT DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
    observed_count INTEGER DEFAULT 1,
    last_observed TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE user_mental_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_state_patterns ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user_mental_states
CREATE POLICY "Users can view their own mental states"
    ON user_mental_states FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own mental states"
    ON user_mental_states FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own mental states"
    ON user_mental_states FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- RLS Policies for user_state_patterns
CREATE POLICY "Users can view their own patterns"
    ON user_state_patterns FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own patterns"
    ON user_state_patterns FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own patterns"
    ON user_state_patterns FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_mental_states_user
    ON user_mental_states(user_id, inferred_at DESC);

CREATE INDEX IF NOT EXISTS idx_mental_states_session
    ON user_mental_states(session_id)
    WHERE session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_state_patterns_user_type
    ON user_state_patterns(user_id, pattern_type);

CREATE INDEX IF NOT EXISTS idx_state_patterns_last_observed
    ON user_state_patterns(user_id, last_observed DESC);
