-- Migration: US-420 Cognitive Load Monitor
-- Creates cognitive_load_snapshots table for tracking user cognitive state

-- =============================================================================
-- Cognitive Load Snapshots Table
-- =============================================================================

CREATE TABLE cognitive_load_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,

    -- Load indicators
    load_level TEXT NOT NULL CHECK (load_level IN ('low', 'medium', 'high', 'critical')),
    load_score FLOAT NOT NULL CHECK (load_score >= 0 AND load_score <= 1),

    -- Contributing factors (JSONB for flexibility)
    -- Example: {
    --   "message_brevity": 0.8,
    --   "typo_rate": 0.3,
    --   "message_velocity": 0.6,
    --   "calendar_density": 0.9,
    --   "time_of_day": 0.4
    -- }
    factors JSONB NOT NULL DEFAULT '{}',

    -- Context
    session_id UUID,
    measured_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX idx_cognitive_load_user ON cognitive_load_snapshots(user_id, measured_at DESC);
CREATE INDEX idx_cognitive_load_level ON cognitive_load_snapshots(user_id, load_level);
CREATE INDEX idx_cognitive_load_session ON cognitive_load_snapshots(session_id) WHERE session_id IS NOT NULL;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE cognitive_load_snapshots ENABLE ROW LEVEL SECURITY;

-- Users can only access their own load data
CREATE POLICY "Users can view own cognitive load data" ON cognitive_load_snapshots
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own cognitive load data" ON cognitive_load_snapshots
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Service role bypass for backend operations
CREATE POLICY "Service role full access to cognitive load" ON cognitive_load_snapshots
    FOR ALL USING (auth.role() = 'service_role');
