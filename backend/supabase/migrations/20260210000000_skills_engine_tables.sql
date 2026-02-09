-- Migration: Skills Engine Tables
-- Creates messages, skill_execution_plans, skill_working_memory, custom_skills
-- Part of ARIA Skills Integration Architecture (Part 5)

-- =============================================================================
-- 1. Messages Table
-- =============================================================================
-- NOTE: messages table may already exist from 20260209000001_create_messages.sql
-- Using IF NOT EXISTS for idempotency.

CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id
    ON messages(conversation_id);

ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

-- RLS: users see own messages via conversations.user_id join
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'messages' AND policyname = 'messages_select_own') THEN
        CREATE POLICY "messages_select_own" ON messages
            FOR SELECT USING (
                EXISTS (
                    SELECT 1 FROM conversations c
                    WHERE c.id = messages.conversation_id
                    AND c.user_id = auth.uid()
                )
            );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'messages' AND policyname = 'messages_insert_own') THEN
        CREATE POLICY "messages_insert_own" ON messages
            FOR INSERT WITH CHECK (
                EXISTS (
                    SELECT 1 FROM conversations c
                    WHERE c.id = messages.conversation_id
                    AND c.user_id = auth.uid()
                )
            );
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'messages' AND policyname = 'messages_service_role') THEN
        CREATE POLICY "messages_service_role" ON messages
            FOR ALL USING (auth.role() = 'service_role');
    END IF;
END $$;

-- =============================================================================
-- 2. Skill Execution Plans Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS skill_execution_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    task_description TEXT,
    plan_dag JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft', 'pending_approval', 'approved', 'executing',
        'completed', 'failed', 'cancelled'
    )),
    risk_level TEXT NOT NULL DEFAULT 'low' CHECK (risk_level IN (
        'low', 'medium', 'high', 'critical'
    )),
    reasoning TEXT,
    estimated_seconds INT,
    actual_seconds INT,
    approved_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skill_execution_plans_user_status
    ON skill_execution_plans(user_id, status);

ALTER TABLE skill_execution_plans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "skill_execution_plans_own" ON skill_execution_plans;
CREATE POLICY "skill_execution_plans_own" ON skill_execution_plans
    FOR ALL USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "skill_execution_plans_service_role" ON skill_execution_plans;
CREATE POLICY "skill_execution_plans_service_role" ON skill_execution_plans
    FOR ALL USING (auth.role() = 'service_role');

COMMENT ON TABLE skill_execution_plans IS 'Multi-skill execution plans with DAG-based step ordering and approval workflow';

-- =============================================================================
-- 3. Skill Working Memory Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS skill_working_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL REFERENCES skill_execution_plans(id) ON DELETE CASCADE,
    step_number INT NOT NULL,
    skill_id TEXT NOT NULL,
    input_summary TEXT,
    output_summary TEXT,
    artifacts JSONB DEFAULT '[]'::jsonb,
    extracted_facts JSONB DEFAULT '[]'::jsonb,
    next_step_hints JSONB DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'running', 'completed', 'failed'
    )),
    execution_time_ms INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skill_working_memory_plan_id
    ON skill_working_memory(plan_id);

ALTER TABLE skill_working_memory ENABLE ROW LEVEL SECURITY;

-- RLS: access via plan_id join to skill_execution_plans.user_id
DROP POLICY IF EXISTS "skill_working_memory_via_plan" ON skill_working_memory;
CREATE POLICY "skill_working_memory_via_plan" ON skill_working_memory
    FOR ALL USING (
        EXISTS (
            SELECT 1 FROM skill_execution_plans sep
            WHERE sep.id = skill_working_memory.plan_id
            AND sep.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM skill_execution_plans sep
            WHERE sep.id = skill_working_memory.plan_id
            AND sep.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "skill_working_memory_service_role" ON skill_working_memory;
CREATE POLICY "skill_working_memory_service_role" ON skill_working_memory
    FOR ALL USING (auth.role() = 'service_role');

COMMENT ON TABLE skill_working_memory IS 'Per-step working memory for skill execution plan handoffs';

-- =============================================================================
-- 4. Custom Skills Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS custom_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    skill_name TEXT NOT NULL,
    description TEXT,
    skill_type TEXT NOT NULL CHECK (skill_type IN (
        'llm_definition', 'workflow', 'agent_capability'
    )),
    definition JSONB NOT NULL,
    trust_level TEXT DEFAULT 'user',
    performance_metrics JSONB DEFAULT '{"success_rate":0,"executions":0,"avg_satisfaction":0}'::jsonb,
    is_published BOOLEAN DEFAULT FALSE,
    version INT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_custom_skills_tenant_id
    ON custom_skills(tenant_id);

ALTER TABLE custom_skills ENABLE ROW LEVEL SECURITY;

-- RLS: tenant_id matches user's company_id via user_profiles
DROP POLICY IF EXISTS "custom_skills_tenant" ON custom_skills;
CREATE POLICY "custom_skills_tenant" ON custom_skills
    FOR ALL USING (
        tenant_id = (SELECT company_id FROM user_profiles WHERE id = auth.uid())
    )
    WITH CHECK (
        tenant_id = (SELECT company_id FROM user_profiles WHERE id = auth.uid())
    );

DROP POLICY IF EXISTS "custom_skills_service_role" ON custom_skills;
CREATE POLICY "custom_skills_service_role" ON custom_skills
    FOR ALL USING (auth.role() = 'service_role');

-- updated_at trigger
CREATE OR REPLACE FUNCTION update_custom_skills_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_update_custom_skills_updated_at ON custom_skills;
CREATE TRIGGER trigger_update_custom_skills_updated_at
    BEFORE UPDATE ON custom_skills
    FOR EACH ROW
    EXECUTE FUNCTION update_custom_skills_updated_at();

COMMENT ON TABLE custom_skills IS 'User/tenant-created custom skills with performance tracking';
