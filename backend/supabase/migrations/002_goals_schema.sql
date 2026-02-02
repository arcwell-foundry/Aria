-- ARIA Goals Schema Migration
-- Phase 2: Goals, Goal Agents, and Agent Executions

-- Goals table
CREATE TABLE goals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    goal_type TEXT NOT NULL,  -- lead_gen, research, outreach, etc.
    status TEXT DEFAULT 'draft',  -- draft, active, paused, complete, failed
    strategy JSONB,  -- Generated strategy document
    config JSONB DEFAULT '{}',  -- Goal-specific configuration
    progress INT DEFAULT 0,  -- 0-100
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Add check constraint for progress range
    CONSTRAINT goals_progress_check CHECK (progress >= 0 AND progress <= 100),
    -- Add check constraint for valid status values
    CONSTRAINT goals_status_check CHECK (status IN ('draft', 'active', 'paused', 'complete', 'failed')),
    -- Add check constraint for valid goal_type values
    CONSTRAINT goals_type_check CHECK (goal_type IN ('lead_gen', 'research', 'outreach', 'analysis', 'custom'))
);

-- Goal agents junction table
CREATE TABLE goal_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id UUID REFERENCES goals(id) ON DELETE CASCADE,
    agent_type TEXT NOT NULL,
    agent_config JSONB DEFAULT '{}',
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Add check constraint for valid agent status values
    CONSTRAINT goal_agents_status_check CHECK (status IN ('pending', 'running', 'complete', 'failed'))
);

-- Agent executions history
CREATE TABLE agent_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_agent_id UUID REFERENCES goal_agents(id) ON DELETE CASCADE,
    input JSONB NOT NULL,
    output JSONB,
    status TEXT DEFAULT 'running',
    tokens_used INT DEFAULT 0,
    execution_time_ms INT,
    error TEXT,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,

    -- Add check constraint for valid execution status values
    CONSTRAINT agent_executions_status_check CHECK (status IN ('pending', 'running', 'complete', 'failed'))
);

-- RLS policies
ALTER TABLE goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE goal_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_executions ENABLE ROW LEVEL SECURITY;

-- Goals RLS policies
CREATE POLICY "Users can manage own goals" ON goals
    FOR ALL USING (user_id = auth.uid());

CREATE POLICY "Service role can manage goals" ON goals
    FOR ALL USING (auth.role() = 'service_role');

-- Goal agents RLS policies
CREATE POLICY "Users can manage own goal agents" ON goal_agents
    FOR ALL USING (goal_id IN (SELECT id FROM goals WHERE user_id = auth.uid()));

CREATE POLICY "Service role can manage goal agents" ON goal_agents
    FOR ALL USING (auth.role() = 'service_role');

-- Agent executions RLS policies
CREATE POLICY "Users can view own executions" ON agent_executions
    FOR ALL USING (goal_agent_id IN (
        SELECT ga.id FROM goal_agents ga
        JOIN goals g ON ga.goal_id = g.id
        WHERE g.user_id = auth.uid()
    ));

CREATE POLICY "Service role can manage executions" ON agent_executions
    FOR ALL USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_goals_user_status ON goals(user_id, status);
CREATE INDEX idx_goals_user_type ON goals(user_id, goal_type);
CREATE INDEX idx_goal_agents_goal ON goal_agents(goal_id);
CREATE INDEX idx_goal_agents_status ON goal_agents(goal_id, status);
CREATE INDEX idx_executions_agent ON agent_executions(goal_agent_id);
CREATE INDEX idx_executions_status ON agent_executions(goal_agent_id, status);

-- Apply updated_at triggers
CREATE TRIGGER update_goals_updated_at
    BEFORE UPDATE ON goals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
