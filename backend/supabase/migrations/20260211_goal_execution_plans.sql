-- Goal execution plans — stores decomposed sub-tasks for goals
CREATE TABLE IF NOT EXISTS goal_execution_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    tasks JSONB NOT NULL DEFAULT '[]',
    execution_mode TEXT NOT NULL DEFAULT 'parallel',
    estimated_total_minutes INTEGER NOT NULL DEFAULT 60,
    reasoning TEXT DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_goal_execution_plans_goal
    ON goal_execution_plans(goal_id);

ALTER TABLE goal_execution_plans ENABLE ROW LEVEL SECURITY;

CREATE POLICY goal_execution_plans_select ON goal_execution_plans
    FOR SELECT USING (
        goal_id IN (SELECT id FROM goals WHERE user_id = auth.uid())
    );

CREATE POLICY goal_execution_plans_insert ON goal_execution_plans
    FOR INSERT WITH CHECK (
        goal_id IN (SELECT id FROM goals WHERE user_id = auth.uid())
    );

CREATE POLICY goal_execution_plans_update ON goal_execution_plans
    FOR UPDATE USING (
        goal_id IN (SELECT id FROM goals WHERE user_id = auth.uid())
    );
