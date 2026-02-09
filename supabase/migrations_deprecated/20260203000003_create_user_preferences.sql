-- ARIA User Preferences Migration
-- US-414: Settings - Preferences
-- Creates user_preferences table for storing user notification and briefing preferences

-- Create user_preferences table
CREATE TABLE IF NOT EXISTS user_preferences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    briefing_time TIME DEFAULT '08:00' NOT NULL,
    meeting_brief_lead_hours INT DEFAULT 24 NOT NULL,
    notification_email BOOLEAN DEFAULT true NOT NULL,
    notification_in_app BOOLEAN DEFAULT true NOT NULL,
    default_tone TEXT DEFAULT 'friendly' NOT NULL,
    tracked_competitors TEXT[] DEFAULT '{}' NOT NULL,
    timezone TEXT DEFAULT 'UTC' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(user_id),
    CONSTRAINT valid_tone CHECK (default_tone IN ('formal', 'friendly', 'urgent')),
    CONSTRAINT valid_lead_hours CHECK (meeting_brief_lead_hours IN (2, 6, 12, 24))
);

-- Add table comment
COMMENT ON TABLE user_preferences IS 'Stores user preferences for notifications, briefings, and communication settings';

-- Create index on user_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);

-- Enable Row Level Security
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user_preferences

-- Users can view their own preferences
CREATE POLICY "Users can view own preferences" ON user_preferences
    FOR SELECT USING (auth.uid() = user_id);

-- Users can update their own preferences
CREATE POLICY "Users can update own preferences" ON user_preferences
    FOR UPDATE USING (auth.uid() = user_id);

-- Users can insert their own preferences
CREATE POLICY "Users can insert own preferences" ON user_preferences
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Users can delete their own preferences
CREATE POLICY "Users can delete own preferences" ON user_preferences
    FOR DELETE USING (auth.uid() = user_id);

-- Service role bypass policy (for backend operations)
CREATE POLICY "Service role can manage user_preferences" ON user_preferences
    FOR ALL USING (auth.role() = 'service_role');

-- Apply updated_at trigger (uses existing function from 001_initial_schema.sql)
CREATE TRIGGER update_user_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
