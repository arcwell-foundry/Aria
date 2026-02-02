-- Create daily_briefings table for storing daily morning briefings
-- Part of US-404: Daily Briefing Backend

CREATE TABLE IF NOT EXISTS daily_briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    briefing_date DATE NOT NULL,
    content JSONB NOT NULL DEFAULT '{}',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ,
    delivery_method TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, briefing_date)
);

-- Index for user-date lookups (most common query pattern)
CREATE INDEX idx_daily_briefings_user_date ON daily_briefings(user_id, briefing_date DESC);

-- Index for delivery tracking
CREATE INDEX idx_daily_briefings_delivered_at ON daily_briefings(delivered_at) WHERE delivered_at IS NOT NULL;

-- GIN index for content JSONB queries
CREATE INDEX idx_daily_briefings_content ON daily_briefings USING GIN(content);

-- Enable Row Level Security
ALTER TABLE daily_briefings ENABLE ROW LEVEL SECURITY;

-- Policy: Users can read their own briefings
CREATE POLICY "Users can read own briefings"
    ON daily_briefings
    FOR SELECT
    USING (user_id = auth.uid());

-- Policy: Users can insert their own briefings
CREATE POLICY "Users can insert own briefings"
    ON daily_briefings
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Policy: Users can update their own briefings
CREATE POLICY "Users can update own briefings"
    ON daily_briefings
    FOR UPDATE
    USING (user_id = auth.uid());

-- Policy: Users can delete their own briefings
CREATE POLICY "Users can delete own briefings"
    ON daily_briefings
    FOR DELETE
    USING (user_id = auth.uid());

-- Add comment for documentation
COMMENT ON TABLE daily_briefings IS 'Stores daily morning briefings with calendar, leads, signals, and tasks';
COMMENT ON COLUMN daily_briefings.briefing_date IS 'The date for which this briefing was generated (unique per user)';
COMMENT ON COLUMN daily_briefings.content IS 'JSONB containing summary, calendar, leads, signals, and tasks';
COMMENT ON COLUMN daily_briefings.delivered_at IS 'Timestamp when the briefing was delivered to the user';
COMMENT ON COLUMN daily_briefings.delivery_method IS 'How the briefing was delivered (email, app, video)';
