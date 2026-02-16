-- Migration: Narrative Identity Engine (US-807)
-- Creates tables for tracking relationship milestones and shared narrative

-- User narratives table
-- Stores the current state of the user-ARIA relationship
CREATE TABLE IF NOT EXISTS user_narratives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL UNIQUE,
    relationship_start TIMESTAMPTZ NOT NULL,
    total_interactions INTEGER DEFAULT 0,
    trust_score FLOAT DEFAULT 0.5 CHECK (trust_score BETWEEN 0 AND 1),
    shared_victories JSONB DEFAULT '[]',
    shared_challenges JSONB DEFAULT '[]',
    inside_references JSONB DEFAULT '[]',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Relationship milestones table
-- Stores individual milestones in the relationship
CREATE TABLE IF NOT EXISTS relationship_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    type TEXT NOT NULL,
    date TIMESTAMPTZ NOT NULL,
    description TEXT NOT NULL,
    significance FLOAT DEFAULT 0.5 CHECK (significance BETWEEN 0 AND 1),
    related_entity_type TEXT,
    related_entity_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE user_narratives ENABLE ROW LEVEL SECURITY;
ALTER TABLE relationship_milestones ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user_narratives
CREATE POLICY "Users can view their own narrative"
    ON user_narratives FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own narrative"
    ON user_narratives FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own narrative"
    ON user_narratives FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- RLS Policies for relationship_milestones
CREATE POLICY "Users can view their own milestones"
    ON relationship_milestones FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own milestones"
    ON relationship_milestones FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own milestones"
    ON relationship_milestones FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_narratives_user_id
    ON user_narratives(user_id);

CREATE INDEX IF NOT EXISTS idx_relationship_milestones_user_id
    ON relationship_milestones(user_id);

CREATE INDEX IF NOT EXISTS idx_relationship_milestones_date
    ON relationship_milestones(user_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_relationship_milestones_type
    ON relationship_milestones(user_id, type);

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_user_narratives_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_user_narratives_updated_at
    BEFORE UPDATE ON user_narratives
    FOR EACH ROW
    EXECUTE FUNCTION update_user_narratives_updated_at();
