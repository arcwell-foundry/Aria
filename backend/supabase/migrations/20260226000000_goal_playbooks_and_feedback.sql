-- ARIA Goal Playbooks & Feedback Migration
-- Adds goal_playbooks for reusable plan templates learned from successful goals,
-- goal_feedback for user rating of goal outcomes, and extends existing tables
-- with playbook tracking columns.

-- ============================================================
-- 1. goal_playbooks table
-- ============================================================
CREATE TABLE goal_playbooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    playbook_name TEXT NOT NULL,
    description TEXT,
    trigger_pattern TEXT NOT NULL,
    goal_type TEXT,
    keywords JSONB DEFAULT '[]',
    plan_template JSONB NOT NULL DEFAULT '[]',
    execution_mode TEXT DEFAULT 'sequential',
    source_goal_ids JSONB DEFAULT '[]',
    success_metrics JSONB DEFAULT '{}',
    negative_patterns JSONB DEFAULT '[]',
    times_used INT DEFAULT 0,
    times_succeeded INT DEFAULT 0,
    times_failed INT DEFAULT 0,
    positive_feedback_count INT DEFAULT 0,
    negative_feedback_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    is_shared BOOLEAN DEFAULT FALSE,
    version INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT goal_playbooks_execution_mode_check
        CHECK (execution_mode IN ('parallel', 'sequential', 'mixed'))
);

-- ============================================================
-- 2. goal_feedback table
-- ============================================================
CREATE TABLE goal_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    goal_id UUID REFERENCES goals(id) ON DELETE CASCADE NOT NULL,
    rating TEXT NOT NULL,
    comment TEXT,
    feedback_context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT goal_feedback_rating_check
        CHECK (rating IN ('up', 'down')),
    CONSTRAINT goal_feedback_unique_per_user
        UNIQUE (user_id, goal_id)
);

-- ============================================================
-- 3. Extend goal_execution_plans with playbook tracking
-- ============================================================
ALTER TABLE goal_execution_plans
    ADD COLUMN IF NOT EXISTS playbook_id UUID REFERENCES goal_playbooks(id) ON DELETE SET NULL;

-- ============================================================
-- 4. Extend goal_retrospectives with metadata for failure context
-- ============================================================
ALTER TABLE goal_retrospectives
    ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

-- ============================================================
-- 5. Row Level Security
-- ============================================================

-- goal_playbooks
ALTER TABLE goal_playbooks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own playbooks" ON goal_playbooks
    FOR ALL USING (user_id = auth.uid());

CREATE POLICY "Users can view shared playbooks" ON goal_playbooks
    FOR SELECT USING (is_shared = TRUE);

CREATE POLICY "Service role can manage playbooks" ON goal_playbooks
    FOR ALL USING (auth.role() = 'service_role');

-- goal_feedback
ALTER TABLE goal_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own feedback" ON goal_feedback
    FOR ALL USING (user_id = auth.uid());

CREATE POLICY "Service role can manage feedback" ON goal_feedback
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- 6. Indexes
-- ============================================================
CREATE INDEX idx_goal_playbooks_user ON goal_playbooks(user_id);
CREATE INDEX idx_goal_playbooks_type ON goal_playbooks(user_id, goal_type) WHERE is_active = TRUE;
CREATE INDEX idx_goal_playbooks_active ON goal_playbooks(user_id, is_active);
CREATE INDEX idx_goal_feedback_goal ON goal_feedback(goal_id);
CREATE INDEX idx_goal_feedback_user ON goal_feedback(user_id);
CREATE INDEX idx_goal_execution_plans_playbook ON goal_execution_plans(playbook_id) WHERE playbook_id IS NOT NULL;

-- ============================================================
-- 7. updated_at triggers
-- ============================================================
CREATE TRIGGER update_goal_playbooks_updated_at
    BEFORE UPDATE ON goal_playbooks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_goal_feedback_updated_at
    BEFORE UPDATE ON goal_feedback
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
