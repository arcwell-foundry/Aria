-- API Usage Tracking — tracks external API calls per user per day.
-- Covers Exa searches, Composio actions, and other non-LLM API calls.
-- Complements the existing usage_tracking table (which tracks LLM tokens).

CREATE TABLE IF NOT EXISTS api_usage_tracking (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    date        DATE NOT NULL DEFAULT CURRENT_DATE,
    api_type    TEXT NOT NULL,  -- 'exa', 'composio', 'pubmed', 'fda', etc.
    call_count  INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    cost_cents  NUMERIC(10,2) NOT NULL DEFAULT 0,
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, date, api_type)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_api_usage_user_date
    ON api_usage_tracking (user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_api_usage_api_type
    ON api_usage_tracking (api_type, date DESC);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_api_usage_tracking_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_api_usage_tracking_updated_at
    BEFORE UPDATE ON api_usage_tracking
    FOR EACH ROW
    EXECUTE FUNCTION update_api_usage_tracking_updated_at();

-- Atomic increment RPC for API usage
CREATE OR REPLACE FUNCTION increment_api_usage(
    p_user_id    UUID,
    p_date       DATE,
    p_api_type   TEXT,
    p_calls      INTEGER DEFAULT 1,
    p_errors     INTEGER DEFAULT 0,
    p_cost_cents NUMERIC DEFAULT 0
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO api_usage_tracking (
        user_id, date, api_type, call_count, error_count, cost_cents
    ) VALUES (
        p_user_id, p_date, p_api_type, p_calls, p_errors, p_cost_cents
    )
    ON CONFLICT (user_id, date, api_type) DO UPDATE SET
        call_count  = api_usage_tracking.call_count  + EXCLUDED.call_count,
        error_count = api_usage_tracking.error_count + EXCLUDED.error_count,
        cost_cents  = api_usage_tracking.cost_cents  + EXCLUDED.cost_cents;
END;
$$;

-- RLS
ALTER TABLE api_usage_tracking ENABLE ROW LEVEL SECURITY;

-- Users can read their own rows
CREATE POLICY api_usage_tracking_select_own ON api_usage_tracking
    FOR SELECT USING (user_id = auth.uid());

-- Service role has full access
CREATE POLICY api_usage_tracking_service_all ON api_usage_tracking
    FOR ALL USING (auth.role() = 'service_role');
