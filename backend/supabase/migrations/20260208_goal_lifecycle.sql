-- ARIA Goal Lifecycle Migration
-- Adds milestones, retrospectives, and expanded goal types for
-- the Goal Lifecycle feature (US-942).

-- ============================================================
-- 1. goal_milestones table
-- ============================================================
CREATE TABLE goal_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID REFERENCES goals(id) ON DELETE CASCADE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    due_date TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'pending',
    sort_order INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT goal_milestones_status_check
        CHECK (status IN ('pending', 'in_progress', 'complete', 'skipped'))
);

-- ============================================================
-- 2. goal_retrospectives table
-- ============================================================
CREATE TABLE goal_retrospectives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID REFERENCES goals(id) ON DELETE CASCADE NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    what_worked JSONB DEFAULT '[]',
    what_didnt JSONB DEFAULT '[]',
    time_analysis JSONB DEFAULT '{}',
    agent_effectiveness JSONB DEFAULT '{}',
    learnings JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- 3. ALTER goals table — new columns & expanded constraints
-- ============================================================
ALTER TABLE goals ADD COLUMN target_date TIMESTAMPTZ;
ALTER TABLE goals ADD COLUMN health TEXT DEFAULT 'on_track';

-- Drop the old type constraint and replace with expanded values
ALTER TABLE goals DROP CONSTRAINT goals_type_check;
ALTER TABLE goals ADD CONSTRAINT goals_type_check
    CHECK (goal_type IN (
        'lead_gen', 'research', 'outreach', 'analysis', 'custom',
        'meeting_prep', 'competitive_intel', 'territory'
    ));

-- Health constraint
ALTER TABLE goals ADD CONSTRAINT goals_health_check
    CHECK (health IN ('on_track', 'at_risk', 'behind', 'blocked'));

-- ============================================================
-- 4. Row Level Security
-- ============================================================

-- goal_milestones
ALTER TABLE goal_milestones ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage milestones for own goals" ON goal_milestones
    FOR ALL USING (
        goal_id IN (SELECT id FROM goals WHERE user_id = auth.uid())
    );

CREATE POLICY "Service role can manage milestones" ON goal_milestones
    FOR ALL USING (auth.role() = 'service_role');

-- goal_retrospectives
ALTER TABLE goal_retrospectives ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage retrospectives for own goals" ON goal_retrospectives
    FOR ALL USING (
        goal_id IN (SELECT id FROM goals WHERE user_id = auth.uid())
    );

CREATE POLICY "Service role can manage retrospectives" ON goal_retrospectives
    FOR ALL USING (auth.role() = 'service_role');

-- ============================================================
-- 5. Indexes
-- ============================================================
CREATE INDEX idx_goal_milestones_goal ON goal_milestones(goal_id);
CREATE INDEX idx_goal_milestones_status ON goal_milestones(goal_id, status);
CREATE INDEX idx_goal_retrospectives_goal ON goal_retrospectives(goal_id);

-- ============================================================
-- 6. updated_at trigger for goal_retrospectives
-- ============================================================
CREATE TRIGGER update_goal_retrospectives_updated_at
    BEFORE UPDATE ON goal_retrospectives
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
