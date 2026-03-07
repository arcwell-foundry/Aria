-- Migration: Create watch_topics table for user-defined monitoring topics
-- Users can define topics (keywords, companies, therapeutic areas) to watch

CREATE TABLE IF NOT EXISTS watch_topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    topic_type TEXT NOT NULL CHECK (topic_type IN ('keyword', 'company', 'therapeutic_area')),
    topic_value TEXT NOT NULL,
    description TEXT,
    keywords JSONB DEFAULT '[]',
    signal_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    last_matched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, topic_type, topic_value)
);

-- Enable Row Level Security
ALTER TABLE watch_topics ENABLE ROW LEVEL SECURITY;

-- RLS policies
CREATE POLICY "Users can manage own watch topics" ON watch_topics
    FOR ALL USING (user_id = auth.uid());

CREATE POLICY "Service role can manage watch_topics" ON watch_topics
    FOR ALL USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX IF NOT EXISTS idx_watch_topics_user_active ON watch_topics(user_id, is_active)
    WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_watch_topics_user_type ON watch_topics(user_id, topic_type);

-- Comments
COMMENT ON TABLE watch_topics IS 'User-defined monitoring topics for intelligence alerting';
COMMENT ON COLUMN watch_topics.topic_type IS 'Type of topic: keyword, company, therapeutic_area';
COMMENT ON COLUMN watch_topics.keywords IS 'Derived keywords for signal matching (auto-generated from topic_value)';
COMMENT ON COLUMN watch_topics.signal_count IS 'Number of signals matched to this topic';
