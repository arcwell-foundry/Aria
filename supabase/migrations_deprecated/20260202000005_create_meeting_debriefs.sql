-- Meeting debriefs table for post-meeting insights
-- Stores structured debrief data including action items, commitments, and insights

CREATE TABLE IF NOT EXISTS meeting_debriefs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    meeting_id TEXT NOT NULL,
    meeting_title TEXT,
    meeting_time TIMESTAMPTZ,
    raw_notes TEXT,
    summary TEXT,
    outcome TEXT,  -- positive, neutral, negative
    action_items JSONB DEFAULT '[]',
    commitments_ours JSONB DEFAULT '[]',
    commitments_theirs JSONB DEFAULT '[]',
    insights JSONB DEFAULT '[]',
    follow_up_needed BOOLEAN DEFAULT false,
    follow_up_draft TEXT,
    linked_lead_id UUID REFERENCES lead_memories(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE meeting_debriefs ENABLE ROW LEVEL SECURITY;

-- Policy: Users can manage own debriefs
CREATE POLICY "Users can manage own debriefs" ON meeting_debriefs
    FOR ALL USING (user_id = auth.uid());

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_debriefs_user ON meeting_debriefs(user_id);
CREATE INDEX IF NOT EXISTS idx_debriefs_meeting ON meeting_debriefs(user_id, meeting_id);
CREATE INDEX IF NOT EXISTS idx_debriefs_time ON meeting_debriefs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_debriefs_lead ON meeting_debriefs(linked_lead_id);

-- Index for filtering by outcome
CREATE INDEX IF NOT EXISTS idx_debriefs_outcome ON meeting_debriefs(user_id, outcome);
