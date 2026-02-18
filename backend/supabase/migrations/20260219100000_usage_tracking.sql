-- Usage Tracking for Cost Governor (Wave 0)
-- One row per user per day, upserted atomically via RPC.

CREATE TABLE IF NOT EXISTS usage_tracking (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    date        DATE NOT NULL DEFAULT CURRENT_DATE,
    input_tokens_total          BIGINT  NOT NULL DEFAULT 0,
    output_tokens_total         BIGINT  NOT NULL DEFAULT 0,
    thinking_tokens_total       BIGINT  NOT NULL DEFAULT 0,
    cache_read_tokens_total     BIGINT  NOT NULL DEFAULT 0,
    cache_creation_tokens_total BIGINT  NOT NULL DEFAULT 0,
    llm_calls_total             INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd          NUMERIC(10,6) NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, date)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_usage_tracking_user_date
    ON usage_tracking (user_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_usage_tracking_date
    ON usage_tracking (date DESC);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_usage_tracking_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_usage_tracking_updated_at
    BEFORE UPDATE ON usage_tracking
    FOR EACH ROW
    EXECUTE FUNCTION update_usage_tracking_updated_at();

-- Atomic increment RPC
-- Uses INSERT ... ON CONFLICT so the caller never needs to check existence.
-- SECURITY DEFINER bypasses RLS for the upsert but only touches the
-- row matching p_user_id, so it's safe.
CREATE OR REPLACE FUNCTION increment_usage_tracking(
    p_user_id               UUID,
    p_date                  DATE,
    p_input_tokens          BIGINT  DEFAULT 0,
    p_output_tokens         BIGINT  DEFAULT 0,
    p_thinking_tokens       BIGINT  DEFAULT 0,
    p_cache_read_tokens     BIGINT  DEFAULT 0,
    p_cache_creation_tokens BIGINT  DEFAULT 0,
    p_estimated_cost        NUMERIC DEFAULT 0
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO usage_tracking (
        user_id, date,
        input_tokens_total, output_tokens_total, thinking_tokens_total,
        cache_read_tokens_total, cache_creation_tokens_total,
        llm_calls_total, estimated_cost_usd
    ) VALUES (
        p_user_id, p_date,
        p_input_tokens, p_output_tokens, p_thinking_tokens,
        p_cache_read_tokens, p_cache_creation_tokens,
        1, p_estimated_cost
    )
    ON CONFLICT (user_id, date) DO UPDATE SET
        input_tokens_total          = usage_tracking.input_tokens_total          + EXCLUDED.input_tokens_total,
        output_tokens_total         = usage_tracking.output_tokens_total         + EXCLUDED.output_tokens_total,
        thinking_tokens_total       = usage_tracking.thinking_tokens_total       + EXCLUDED.thinking_tokens_total,
        cache_read_tokens_total     = usage_tracking.cache_read_tokens_total     + EXCLUDED.cache_read_tokens_total,
        cache_creation_tokens_total = usage_tracking.cache_creation_tokens_total + EXCLUDED.cache_creation_tokens_total,
        llm_calls_total             = usage_tracking.llm_calls_total             + 1,
        estimated_cost_usd          = usage_tracking.estimated_cost_usd          + EXCLUDED.estimated_cost_usd;
END;
$$;

-- RLS
ALTER TABLE usage_tracking ENABLE ROW LEVEL SECURITY;

-- Users can read their own rows
CREATE POLICY usage_tracking_select_own ON usage_tracking
    FOR SELECT USING (user_id = auth.uid());

-- Service role has full access (for the RPC and admin queries)
CREATE POLICY usage_tracking_service_all ON usage_tracking
    FOR ALL USING (auth.role() = 'service_role');
