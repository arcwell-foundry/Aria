-- Video sessions with Tavus
-- Migration for US-601: Tavus Integration Setup

CREATE TABLE video_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    tavus_conversation_id TEXT NOT NULL,
    room_url TEXT,
    status TEXT DEFAULT 'created',  -- created, active, ended, error
    session_type TEXT DEFAULT 'chat',  -- chat, briefing, debrief
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds INT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Transcript entries from video sessions
CREATE TABLE video_transcript_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_session_id UUID REFERENCES video_sessions(id) ON DELETE CASCADE,
    speaker TEXT NOT NULL,  -- user, aria
    content TEXT NOT NULL,
    timestamp_ms INT NOT NULL,
    confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE video_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_transcript_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own video sessions" ON video_sessions
    FOR ALL USING (user_id = auth.uid());

CREATE POLICY "Users can view own transcripts" ON video_transcript_entries
    FOR ALL USING (video_session_id IN (
        SELECT id FROM video_sessions WHERE user_id = auth.uid()
    ));

-- Indexes
CREATE INDEX idx_video_sessions_user ON video_sessions(user_id);
CREATE INDEX idx_video_sessions_status ON video_sessions(user_id, status);
CREATE INDEX idx_video_transcripts_session ON video_transcript_entries(video_session_id);
