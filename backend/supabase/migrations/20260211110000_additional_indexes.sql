-- Migration: Additional Indexes for Performance
-- Adds missing indexes on skill_execution_plans and messages tables.
-- Uses IF NOT EXISTS for idempotency.

-- =============================================================================
-- 1. skill_execution_plans: (user_id, created_at DESC)
--    Optimizes queries that list a user's plans ordered by most recent first.
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_skill_execution_plans_user_created
    ON skill_execution_plans(user_id, created_at DESC);

-- =============================================================================
-- 2. skill_execution_plans: (status)
--    Optimizes queries that filter plans by status alone (e.g., pending_approval).
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_skill_execution_plans_status
    ON skill_execution_plans(status);

-- =============================================================================
-- 3. messages: (conversation_id, created_at)
--    Already created in 20260209000001_create_messages.sql as
--    idx_messages_conversation_created. Re-stated here for completeness;
--    IF NOT EXISTS makes this a no-op if it already exists.
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
    ON messages(conversation_id, created_at ASC);
