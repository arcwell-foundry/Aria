-- OODA Cycle Logs: Persistent logging for admin dashboard monitoring
CREATE TABLE IF NOT EXISTS ooda_cycle_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_id        UUID NOT NULL,
    goal_id         TEXT NOT NULL,
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    phase           TEXT NOT NULL CHECK (phase IN ('observe', 'orient', 'decide', 'act')),
    iteration       INTEGER NOT NULL DEFAULT 0,
    input_summary   TEXT,
    output_summary  TEXT,
    tokens_used     INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    thinking_effort TEXT CHECK (thinking_effort IN ('routine', 'complex', 'critical')),
    is_complete     BOOLEAN NOT NULL DEFAULT FALSE,
    agents_dispatched TEXT[],
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_ooda_cycle_logs_user_id ON ooda_cycle_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_ooda_cycle_logs_cycle_id ON ooda_cycle_logs (cycle_id);
CREATE INDEX IF NOT EXISTS idx_ooda_cycle_logs_created_at ON ooda_cycle_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ooda_cycle_logs_phase ON ooda_cycle_logs (phase);

-- RLS
ALTER TABLE ooda_cycle_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY ooda_cycle_logs_select_own ON ooda_cycle_logs
    FOR SELECT USING (user_id = auth.uid());
CREATE POLICY ooda_cycle_logs_service_all ON ooda_cycle_logs
    FOR ALL USING (auth.role() = 'service_role');
