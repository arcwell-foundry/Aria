-- Create prospective_memories table for storing future tasks and reminders
-- Part of US-206: Prospective Memory Implementation

CREATE TABLE IF NOT EXISTS prospective_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    task TEXT NOT NULL,
    description TEXT,
    trigger_type TEXT NOT NULL CHECK (trigger_type IN ('time', 'event', 'condition')),
    trigger_config JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'cancelled', 'overdue')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    related_goal_id UUID,
    related_lead_id UUID,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for user + status queries (most common pattern)
CREATE INDEX idx_prospective_memories_user_status ON prospective_memories(user_id, status);

-- Index for status queries (finding overdue, pending tasks)
CREATE INDEX idx_prospective_memories_status ON prospective_memories(status);

-- Index for priority queries
CREATE INDEX idx_prospective_memories_priority ON prospective_memories(user_id, priority);

-- GIN index for trigger_config JSONB queries
CREATE INDEX idx_prospective_memories_trigger ON prospective_memories USING GIN(trigger_config);

-- Index for related goal lookups
CREATE INDEX idx_prospective_memories_goal ON prospective_memories(related_goal_id) WHERE related_goal_id IS NOT NULL;

-- Index for related lead lookups
CREATE INDEX idx_prospective_memories_lead ON prospective_memories(related_lead_id) WHERE related_lead_id IS NOT NULL;

-- Enable Row Level Security
ALTER TABLE prospective_memories ENABLE ROW LEVEL SECURITY;

-- Policy: Users can read their own tasks
CREATE POLICY "Users can read own tasks"
    ON prospective_memories
    FOR SELECT
    USING (user_id = auth.uid());

-- Policy: Users can insert their own tasks
CREATE POLICY "Users can insert own tasks"
    ON prospective_memories
    FOR INSERT
    WITH CHECK (user_id = auth.uid());

-- Policy: Users can update their own tasks
CREATE POLICY "Users can update own tasks"
    ON prospective_memories
    FOR UPDATE
    USING (user_id = auth.uid());

-- Policy: Users can delete their own tasks
CREATE POLICY "Users can delete own tasks"
    ON prospective_memories
    FOR DELETE
    USING (user_id = auth.uid());

-- Add comments for documentation
COMMENT ON TABLE prospective_memories IS 'Stores future tasks, reminders, and follow-ups for prospective memory';
COMMENT ON COLUMN prospective_memories.trigger_type IS 'Type of trigger: time (due_at), event (external trigger), or condition (state-based)';
COMMENT ON COLUMN prospective_memories.trigger_config IS 'JSONB config for trigger. time: {"due_at": timestamp}, event: {"event": "email_received", "from": "john@acme.com"}, condition: {"field": "lead_stage", "value": "qualified"}';
COMMENT ON COLUMN prospective_memories.status IS 'Task status: pending, completed, cancelled, or overdue';
COMMENT ON COLUMN prospective_memories.priority IS 'Task priority: low, medium, high, or urgent';
COMMENT ON COLUMN prospective_memories.related_goal_id IS 'Optional link to a goal this task supports';
COMMENT ON COLUMN prospective_memories.related_lead_id IS 'Optional link to a lead this task relates to';
