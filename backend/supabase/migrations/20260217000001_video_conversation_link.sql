-- Link video sessions to chat conversations for cross-modality context bridging.
-- Enables the ContextBridgeService to persist video transcripts back into the
-- originating chat conversation and load chat history into video context.

ALTER TABLE video_sessions
ADD COLUMN IF NOT EXISTS conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_video_sessions_conversation_id
ON video_sessions(conversation_id);
