-- Migration: Skill Feedback Table
-- Stores user thumbs up/down feedback per skill execution

CREATE TABLE IF NOT EXISTS skill_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    feedback TEXT NOT NULL CHECK (feedback IN ('positive', 'negative')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- One vote per user per execution
CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_feedback_unique
    ON skill_feedback(user_id, execution_id);

CREATE INDEX IF NOT EXISTS idx_skill_feedback_skill_id
    ON skill_feedback(skill_id);

CREATE INDEX IF NOT EXISTS idx_skill_feedback_user_id
    ON skill_feedback(user_id);

ALTER TABLE skill_feedback ENABLE ROW LEVEL SECURITY;

-- RLS: users manage own feedback only
CREATE POLICY "skill_feedback_select_own" ON skill_feedback
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "skill_feedback_insert_own" ON skill_feedback
    FOR INSERT WITH CHECK (user_id = auth.uid());

CREATE POLICY "skill_feedback_update_own" ON skill_feedback
    FOR UPDATE USING (user_id = auth.uid());

CREATE POLICY "skill_feedback_service_role" ON skill_feedback
    FOR ALL USING (auth.role() = 'service_role');

COMMENT ON TABLE skill_feedback IS 'User satisfaction votes (thumbs up/down) for skill executions';
