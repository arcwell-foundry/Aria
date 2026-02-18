-- Delegation Traces — immutable audit trail for every agent delegation.
-- Each row records one delegator→delegatee dispatch with full context.

CREATE TABLE IF NOT EXISTS delegation_traces (
    trace_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal_id           UUID,
    parent_trace_id   UUID REFERENCES delegation_traces(trace_id),
    user_id           UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    delegator         TEXT NOT NULL,
    delegatee         TEXT NOT NULL,
    task_description  TEXT NOT NULL,
    task_characteristics JSONB,
    capability_token  JSONB,
    inputs            JSONB NOT NULL DEFAULT '{}'::jsonb,
    outputs           JSONB,
    thinking_trace    TEXT,
    verification_result JSONB,
    approval_record   JSONB,
    cost_usd          NUMERIC(10,4) DEFAULT 0,
    status            TEXT NOT NULL DEFAULT 'dispatched'
                      CHECK (status IN (
                          'dispatched', 'executing', 'completed',
                          'failed', 'cancelled', 're_delegated'
                      )),
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ,
    duration_ms       INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for common access patterns
CREATE INDEX IF NOT EXISTS idx_delegation_traces_user_id
    ON delegation_traces (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_delegation_traces_goal_id
    ON delegation_traces (goal_id, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_delegation_traces_parent
    ON delegation_traces (parent_trace_id);
CREATE INDEX IF NOT EXISTS idx_delegation_traces_status
    ON delegation_traces (status) WHERE status IN ('dispatched', 'executing');

-- RLS
ALTER TABLE delegation_traces ENABLE ROW LEVEL SECURITY;

CREATE POLICY delegation_traces_select_own ON delegation_traces
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY delegation_traces_service_all ON delegation_traces
    FOR ALL USING (auth.role() = 'service_role');
