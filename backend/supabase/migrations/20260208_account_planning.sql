-- US-941: Account Planning & Strategic Workflows
-- account_plans: LLM-generated strategy documents per lead
CREATE TABLE IF NOT EXISTS account_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    lead_memory_id UUID NOT NULL REFERENCES lead_memories(id) ON DELETE CASCADE,
    strategy TEXT NOT NULL DEFAULT '',
    next_actions JSONB NOT NULL DEFAULT '[]',
    stakeholder_summary JSONB NOT NULL DEFAULT '{}',
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, lead_memory_id)
);

ALTER TABLE account_plans ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_account_plans" ON account_plans
    FOR ALL TO authenticated USING (user_id = auth.uid());

CREATE INDEX idx_account_plans_user ON account_plans(user_id);
CREATE INDEX idx_account_plans_lead ON account_plans(lead_memory_id);

-- user_quotas: quota tracking per user per period
CREATE TABLE IF NOT EXISTS user_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    period TEXT NOT NULL,  -- e.g. '2026-Q1', '2026-02'
    target_value NUMERIC NOT NULL DEFAULT 0,
    actual_value NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, period)
);

ALTER TABLE user_quotas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_user_quotas" ON user_quotas
    FOR ALL TO authenticated USING (user_id = auth.uid());

CREATE INDEX idx_user_quotas_user_period ON user_quotas(user_id, period);
