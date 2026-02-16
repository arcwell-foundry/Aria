-- Migration: Companion Personality System (US-801)
-- Creates tables for ARIA's personality profiles and opinions

-- Companion personality profiles table
-- Stores per-user personality adaptations
CREATE TABLE IF NOT EXISTS companion_personality_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL UNIQUE,
    directness INTEGER DEFAULT 3 CHECK (directness BETWEEN 1 AND 3),
    warmth INTEGER DEFAULT 2 CHECK (warmth BETWEEN 1 AND 3),
    assertiveness INTEGER DEFAULT 2 CHECK (assertiveness BETWEEN 1 AND 3),
    humor INTEGER DEFAULT 2 CHECK (humor BETWEEN 1 AND 3),
    formality INTEGER DEFAULT 1 CHECK (formality BETWEEN 1 AND 3),
    adapted_for_user BOOLEAN DEFAULT FALSE,
    adaptation_notes TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Companion opinions table
-- Stores formed opinions and their outcomes
CREATE TABLE IF NOT EXISTS companion_opinions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    topic TEXT NOT NULL,
    opinion TEXT NOT NULL,
    confidence FLOAT NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    supporting_evidence JSONB DEFAULT '[]',
    should_push_back BOOLEAN DEFAULT FALSE,
    pushback_reason TEXT,
    pushback_generated TEXT,
    user_accepted_pushback BOOLEAN,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE companion_personality_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE companion_opinions ENABLE ROW LEVEL SECURITY;

-- RLS Policies for companion_personality_profiles
CREATE POLICY "Users can view their own personality profile"
    ON companion_personality_profiles FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own personality profile"
    ON companion_personality_profiles FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own personality profile"
    ON companion_personality_profiles FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- RLS Policies for companion_opinions
CREATE POLICY "Users can view their own opinions"
    ON companion_opinions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own opinions"
    ON companion_opinions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own opinions"
    ON companion_opinions FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_companion_personality_profiles_user_id
    ON companion_personality_profiles(user_id);

CREATE INDEX IF NOT EXISTS idx_companion_opinions_user_id
    ON companion_opinions(user_id);

CREATE INDEX IF NOT EXISTS idx_companion_opinions_created_at
    ON companion_opinions(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_companion_opinions_accepted
    ON companion_opinions(user_id, user_accepted_pushback)
    WHERE user_accepted_pushback IS NOT NULL;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_companion_personality_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_companion_personality_updated_at
    BEFORE UPDATE ON companion_personality_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_companion_personality_updated_at();
