-- Migration: Continuous Self-Improvement Loop (US-809)
-- Creates tables for improvement cycles and applied learnings

-- Improvement cycle results
-- Stores results of each improvement cycle run with identified gaps and action plans
CREATE TABLE IF NOT EXISTS companion_improvement_cycles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    improvement_areas JSONB DEFAULT '[]',
    performance_trend JSONB DEFAULT '{}',
    action_plan JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Applied learnings
-- Stores individual learnings applied from improvement cycles
CREATE TABLE IF NOT EXISTS companion_learnings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    area TEXT NOT NULL,
    learning_data JSONB DEFAULT '{}',
    applied_changes JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient querying by user and time
CREATE INDEX IF NOT EXISTS idx_improvement_cycles_user_created
    ON companion_improvement_cycles (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_learnings_user_created
    ON companion_learnings (user_id, created_at DESC);

-- Enable Row Level Security
ALTER TABLE companion_improvement_cycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE companion_learnings ENABLE ROW LEVEL SECURITY;

-- RLS Policies for companion_improvement_cycles
CREATE POLICY "Users can view their own improvement cycles"
    ON companion_improvement_cycles FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own improvement cycles"
    ON companion_improvement_cycles FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own improvement cycles"
    ON companion_improvement_cycles FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- RLS Policies for companion_learnings
CREATE POLICY "Users can view their own learnings"
    ON companion_learnings FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own learnings"
    ON companion_learnings FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own learnings"
    ON companion_learnings FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
