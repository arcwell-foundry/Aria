-- Daily briefings table for US-404: Daily Briefing Backend
-- Stores daily morning briefings with calendar, leads, signals, and tasks summary
-- Supports automatic generation and historical lookup

-- Main daily_briefings table
CREATE TABLE daily_briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    briefing_date DATE NOT NULL,
    content JSONB NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    delivered_at TIMESTAMPTZ,
    delivery_method TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, briefing_date)
);

-- Add table comment
COMMENT ON TABLE daily_briefings IS 'Stores daily morning briefings containing calendar, leads, signals, and tasks summaries. One briefing per user per day.';

-- Create indexes for efficient querying
CREATE INDEX idx_daily_briefings_user_id ON daily_briefings(user_id);
CREATE INDEX idx_daily_briefings_date ON daily_briefings(briefing_date DESC);
CREATE INDEX idx_daily_briefings_user_date ON daily_briefings(user_id, briefing_date DESC);

-- Enable Row Level Security
ALTER TABLE daily_briefings ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user isolation (multi-tenant)
CREATE POLICY "Users can view their own briefings" ON daily_briefings
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create their own briefings" ON daily_briefings
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own briefings" ON daily_briefings
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own briefings" ON daily_briefings
    FOR DELETE USING (auth.uid() = user_id);

-- Service role bypass policy (for backend operations)
CREATE POLICY "Service role can manage daily_briefings" ON daily_briefings
    FOR ALL USING (auth.role() = 'service_role');
