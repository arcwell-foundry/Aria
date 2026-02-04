-- Migration: Create health_score_history table
-- Description: Track historical health scores for lead memory analytics

-- Create health_score_history table
CREATE TABLE IF NOT EXISTS health_score_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_memory_id UUID NOT NULL REFERENCES lead_memories(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    score INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Component scores for analytics
    component_frequency FLOAT,
    component_response_time FLOAT,
    component_sentiment FLOAT,
    component_breadth FLOAT,
    component_velocity FLOAT
);

-- Create index for efficient score history queries
CREATE INDEX IF NOT EXISTS idx_health_score_history_lead_memory_id
    ON health_score_history(lead_memory_id, calculated_at DESC);

CREATE INDEX IF NOT EXISTS idx_health_score_history_user_id
    ON health_score_history(user_id);

-- Create index for time-based queries
CREATE INDEX IF NOT EXISTS idx_health_score_history_calculated_at
    ON health_score_history(calculated_at DESC);

-- Enable Row Level Security
ALTER TABLE health_score_history ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can only access their own health score history
CREATE POLICY "Users can view own health score history"
    ON health_score_history FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own health score history"
    ON health_score_history FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Comments for documentation
COMMENT ON TABLE health_score_history IS 'Historical health scores for lead analytics and trend tracking';
COMMENT ON COLUMN health_score_history.score IS 'Health score value (0-100)';
COMMENT ON COLUMN health_score_history.component_frequency IS 'Communication frequency component score (0-1)';
COMMENT ON COLUMN health_score_history.component_response_time IS 'Response time component score (0-1)';
COMMENT ON COLUMN health_score_history.component_sentiment IS 'Sentiment component score (0-1)';
COMMENT ON COLUMN health_score_history.component_breadth IS 'Stakeholder breadth component score (0-1)';
COMMENT ON COLUMN health_score_history.component_velocity IS 'Stage velocity component score (0-1)';
