-- Trust Score History table for tracking trust changes over time.
-- Powers the per-category trust trend chart in the Autonomy settings dashboard.

CREATE TABLE IF NOT EXISTS trust_score_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action_category TEXT NOT NULL,
    trust_score     DOUBLE PRECISION NOT NULL
                    CHECK (trust_score >= 0.0 AND trust_score <= 1.0),
    change_type     TEXT NOT NULL CHECK (change_type IN ('success', 'failure', 'override', 'manual')),
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trust_history_user_cat_time
    ON trust_score_history (user_id, action_category, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_trust_history_user_time
    ON trust_score_history (user_id, recorded_at DESC);

ALTER TABLE trust_score_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY trust_history_select_own ON trust_score_history
    FOR SELECT USING (user_id = auth.uid());
CREATE POLICY trust_history_service_all ON trust_score_history
    FOR ALL USING (auth.role() = 'service_role');
