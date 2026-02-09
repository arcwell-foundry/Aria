-- Create procedural_memories table for storing learned workflows
-- Part of US-205: Procedural Memory Implementation

CREATE TABLE IF NOT EXISTS procedural_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    workflow_name TEXT NOT NULL,
    description TEXT,
    trigger_conditions JSONB NOT NULL DEFAULT '{}',
    steps JSONB NOT NULL DEFAULT '[]',
    success_count INT NOT NULL DEFAULT 0,
    failure_count INT NOT NULL DEFAULT 0,
    is_shared BOOLEAN NOT NULL DEFAULT FALSE,
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for user lookups (most common query pattern)
CREATE INDEX idx_procedural_memories_user_id ON procedural_memories(user_id);

-- Index for finding shared workflows
CREATE INDEX idx_procedural_memories_is_shared ON procedural_memories(is_shared) WHERE is_shared = TRUE;

-- GIN index for trigger condition JSONB queries
CREATE INDEX idx_procedural_memories_trigger ON procedural_memories USING GIN(trigger_conditions);

-- Enable Row Level Security
ALTER TABLE procedural_memories ENABLE ROW LEVEL SECURITY;

-- Policy: Users can read their own workflows and shared workflows
CREATE POLICY "Users can read own and shared workflows"
    ON procedural_memories
    FOR SELECT
    USING (user_id = auth.uid() OR is_shared = TRUE);

-- Policy: Users can insert their own workflows
CREATE POLICY "Users can insert own workflows"
    ON procedural_memories
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Policy: Users can update their own workflows
CREATE POLICY "Users can update own workflows"
    ON procedural_memories
    FOR UPDATE
    USING (user_id = auth.uid());

-- Policy: Users can delete their own workflows
CREATE POLICY "Users can delete own workflows"
    ON procedural_memories
    FOR DELETE
    USING (user_id = auth.uid());

-- Add comment for documentation
COMMENT ON TABLE procedural_memories IS 'Stores learned workflow patterns with success tracking for procedural memory';
COMMENT ON COLUMN procedural_memories.trigger_conditions IS 'JSONB conditions that determine when this workflow should be used';
COMMENT ON COLUMN procedural_memories.steps IS 'Ordered JSONB array of actions to perform in this workflow';
COMMENT ON COLUMN procedural_memories.success_count IS 'Number of times this workflow executed successfully';
COMMENT ON COLUMN procedural_memories.failure_count IS 'Number of times this workflow failed';
COMMENT ON COLUMN procedural_memories.is_shared IS 'If true, workflow is available to all users in the same company';
COMMENT ON COLUMN procedural_memories.version IS 'Incremented on each update for optimistic concurrency';
