-- Migration: Add lifecycle columns to goal_execution_plans
-- Required by: Plan-Present-Approve loop (plan persistence, approval tracking)

ALTER TABLE goal_execution_plans
  ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'draft',
  ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS presented_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS conversation_id UUID,
  ADD COLUMN IF NOT EXISTS plan_message_id UUID;

CREATE INDEX IF NOT EXISTS idx_goal_execution_plans_status
    ON goal_execution_plans(status);
