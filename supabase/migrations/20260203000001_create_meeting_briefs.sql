-- Meeting briefs for pre-meeting research
-- Generated 24h before meetings with attendee/company intel

CREATE TABLE IF NOT EXISTS meeting_briefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    calendar_event_id TEXT NOT NULL,
    meeting_title TEXT,
    meeting_time TIMESTAMPTZ NOT NULL,
    attendees TEXT[] DEFAULT '{}',
    brief_content JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'generating', 'completed', 'failed')),
    generated_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, calendar_event_id)
);

-- Enable RLS
ALTER TABLE meeting_briefs ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view own meeting briefs"
    ON meeting_briefs FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own meeting briefs"
    ON meeting_briefs FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own meeting briefs"
    ON meeting_briefs FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own meeting briefs"
    ON meeting_briefs FOR DELETE
    USING (auth.uid() = user_id);

CREATE POLICY "Service role full access to meeting briefs"
    ON meeting_briefs
    FOR ALL
    USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_meeting_briefs_user_id ON meeting_briefs(user_id);
CREATE INDEX idx_meeting_briefs_meeting_time ON meeting_briefs(meeting_time);
CREATE INDEX idx_meeting_briefs_status ON meeting_briefs(status);
CREATE INDEX idx_meeting_briefs_user_time ON meeting_briefs(user_id, meeting_time);

-- Updated at trigger (reuse existing function)
CREATE TRIGGER update_meeting_briefs_updated_at
    BEFORE UPDATE ON meeting_briefs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Table comment
COMMENT ON TABLE meeting_briefs IS 'Pre-meeting research briefs generated 24h before meetings';
