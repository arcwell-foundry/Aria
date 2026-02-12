-- Goal updates table for tracking goal progress, milestones, blockers, and notes.
-- Referenced by GoalExecutionService for future goal tracking features.

CREATE TABLE IF NOT EXISTS goal_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    update_type TEXT NOT NULL,  -- progress, milestone, blocker, note
    content TEXT,
    progress_delta INTEGER DEFAULT 0,
    created_by TEXT NOT NULL DEFAULT 'aria',  -- 'aria' or 'user'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_goal_updates_goal_id ON goal_updates(goal_id);
CREATE INDEX IF NOT EXISTS idx_goal_updates_created_at ON goal_updates(created_at DESC);

ALTER TABLE goal_updates ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view updates for their goals"
    ON goal_updates FOR SELECT
    USING (goal_id IN (SELECT id FROM goals WHERE user_id = auth.uid()));

CREATE POLICY "Users can insert updates for their goals"
    ON goal_updates FOR INSERT
    WITH CHECK (goal_id IN (SELECT id FROM goals WHERE user_id = auth.uid()));
