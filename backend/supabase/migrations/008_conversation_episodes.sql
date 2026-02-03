-- Migration: US-219 Conversation Episode Service
-- Stores durable memories extracted from conversations

-- =============================================================================
-- Conversation Episodes Table
-- =============================================================================

CREATE TABLE conversation_episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    conversation_id UUID NOT NULL,

    -- Summary content
    summary TEXT NOT NULL,
    key_topics TEXT[] DEFAULT '{}',
    entities_discussed TEXT[] DEFAULT '{}',

    -- User state detected during conversation
    user_state JSONB DEFAULT '{}',
    -- Example: {"mood": "stressed", "confidence": "uncertain", "focus": "pricing"}

    -- Outcomes and open threads
    outcomes JSONB DEFAULT '[]',
    -- Example: [{"type": "decision", "content": "Will follow up with legal"}]

    open_threads JSONB DEFAULT '[]',
    -- Example: [{"topic": "pricing", "status": "awaiting_response", "context": "..."}]

    -- Metadata
    message_count INTEGER NOT NULL DEFAULT 0,
    duration_minutes INTEGER,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ NOT NULL,

    -- Salience tracking (episodes also decay)
    current_salience FLOAT DEFAULT 1.0 CHECK (current_salience >= 0 AND current_salience <= 2),
    last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,

    -- Standard timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Indexes
-- =============================================================================

CREATE INDEX idx_conversation_episodes_user ON conversation_episodes(user_id);
CREATE INDEX idx_conversation_episodes_conversation ON conversation_episodes(conversation_id);
CREATE INDEX idx_conversation_episodes_topics ON conversation_episodes USING GIN(key_topics);
CREATE INDEX idx_conversation_episodes_salience ON conversation_episodes(user_id, current_salience DESC);
CREATE INDEX idx_conversation_episodes_ended ON conversation_episodes(user_id, ended_at DESC);
CREATE INDEX idx_conversation_episodes_open_threads ON conversation_episodes(user_id)
    WHERE open_threads != '[]'::jsonb;

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE conversation_episodes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own episodes" ON conversation_episodes
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Service role full access to episodes" ON conversation_episodes
    FOR ALL USING (auth.role() = 'service_role');

-- =============================================================================
-- Triggers for updated_at
-- =============================================================================

CREATE TRIGGER update_conversation_episodes_updated_at
    BEFORE UPDATE ON conversation_episodes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
