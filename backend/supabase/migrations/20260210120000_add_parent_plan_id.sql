-- Migration: Add parent_plan_id to skill_execution_plans
-- Supports plan extension (extend_plan) by linking child plans to their parent.

ALTER TABLE skill_execution_plans
    ADD COLUMN IF NOT EXISTS parent_plan_id UUID REFERENCES skill_execution_plans(id);

CREATE INDEX IF NOT EXISTS idx_skill_execution_plans_parent_plan_id
    ON skill_execution_plans(parent_plan_id)
    WHERE parent_plan_id IS NOT NULL;

COMMENT ON COLUMN skill_execution_plans.parent_plan_id IS 'UUID of the parent plan when this plan extends a prior execution';
