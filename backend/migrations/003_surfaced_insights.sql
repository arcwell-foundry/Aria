-- backend/migrations/003_surfaced_insights.sql
-- Proactive Memory Surfacing - Surfaced Insights Table

CREATE TABLE surfaced_insights (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    memory_type TEXT NOT NULL CHECK (memory_type IN ('semantic', 'episodic', 'prospective', 'conversation_episode')),
    memory_id UUID NOT NULL,
    insight_type TEXT NOT NULL CHECK (insight_type IN ('pattern_match', 'connection', 'temporal', 'goal_relevant')),
    context TEXT,
    relevance_score FLOAT NOT NULL CHECK (relevance_score >= 0.0 AND relevance_score <= 1.0),
    explanation TEXT,
    surfaced_at TIMESTAMPTZ DEFAULT NOW(),
    engaged BOOLEAN DEFAULT FALSE,
    engaged_at TIMESTAMPTZ,
    dismissed BOOLEAN DEFAULT FALSE,
    dismissed_at TIMESTAMPTZ
);

-- Index for finding recent surfaced insights by user (for cooldown check)
CREATE INDEX idx_surfaced_insights_user ON surfaced_insights(user_id, surfaced_at DESC);

-- Index for finding if a specific memory was recently surfaced (for cooldown check)
CREATE INDEX idx_surfaced_insights_memory ON surfaced_insights(memory_id, surfaced_at DESC);

-- Index for analytics on insight engagement
CREATE INDEX idx_surfaced_insights_engagement ON surfaced_insights(user_id, engaged, surfaced_at DESC);

-- Enable Row Level Security
ALTER TABLE surfaced_insights ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Users can only access their own surfaced insights
CREATE POLICY "Users can only access own surfaced insights" ON surfaced_insights
    FOR ALL USING (auth.uid() = user_id);
