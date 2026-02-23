-- Fix BL-9: Update increment_usage_tracking function to match Python cost_governor.py
-- The deployed function had parameters: p_agent, p_model, p_request_count, etc.
-- which didn't match what the Python code sends.
--
-- Additionally, the deployed table schema uses different column names:
-- - input_tokens (not input_tokens_total)
-- - output_tokens (not output_tokens_total)
-- - extended_thinking_tokens (not thinking_tokens_total)
-- - estimated_cost_cents (not estimated_cost_usd)
--
-- This function bridges the Python params to the existing DB schema.

-- Drop old function signatures
DROP FUNCTION IF EXISTS increment_usage_tracking(UUID, DATE, TEXT, TEXT, BIGINT, BIGINT, BIGINT, BIGINT, NUMERIC);

-- Create function with Python-expected params that maps to existing table
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
    -- Map Python params to existing table schema:
    -- p_input_tokens -> input_tokens
    -- p_output_tokens -> output_tokens
    -- p_thinking_tokens -> extended_thinking_tokens
    -- p_estimated_cost (dollars) -> estimated_cost_cents
    -- cache tokens -> metadata JSONB
    INSERT INTO usage_tracking (
        user_id, date,
        input_tokens, output_tokens, extended_thinking_tokens,
        estimated_cost_cents, request_count, metadata
    ) VALUES (
        p_user_id, p_date,
        p_input_tokens::int, p_output_tokens::int, p_thinking_tokens::int,
        (p_estimated_cost * 100)::numeric,
        1,
        jsonb_build_object(
            'cache_read_tokens', p_cache_read_tokens,
            'cache_creation_tokens', p_cache_creation_tokens
        )
    )
    ON CONFLICT (user_id, date, agent) DO UPDATE SET
        input_tokens = usage_tracking.input_tokens + EXCLUDED.input_tokens,
        output_tokens = usage_tracking.output_tokens + EXCLUDED.output_tokens,
        extended_thinking_tokens = usage_tracking.extended_thinking_tokens + EXCLUDED.extended_thinking_tokens,
        estimated_cost_cents = usage_tracking.estimated_cost_cents + EXCLUDED.estimated_cost_cents,
        request_count = usage_tracking.request_count + 1,
        metadata = usage_tracking.metadata || EXCLUDED.metadata,
        updated_at = now();
END;
$$;
