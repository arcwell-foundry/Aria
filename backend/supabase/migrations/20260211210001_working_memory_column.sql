-- Add working_memory JSONB column to conversations table for session persistence.
-- Allows WorkingMemoryManager to persist/restore conversation context across restarts.

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS working_memory JSONB;
